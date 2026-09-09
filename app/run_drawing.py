"""One dry-run-first PC entry point for image or JSON drawing tasks."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
for directory in (ROOT / "protocol", ROOT / "src" / "console", APP_ROOT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from drawing import (
    DrawingError,
    DrawingExecutionAdmission,
    RelocationAdmission,
    build_drawing_plan,
    execute_drawing,
    load_drawing_site_config,
    load_drawing_job,
    process_image_to_artifacts,
    validate_job_canvas,
)
from localized_baseline_run import (
    ArmWithChassisGuard,
    EventLog,
    GuardedChassisSession,
    _wait_for_initial_lock,
)
from localization import create_localization_state_machine
from runtime_config import RuntimeConfigError, load_runtime_config
from runtime_core import close_client, default_arm_factory, default_chassis_factory
from status_mapping import StatusMappingError, parse_chassis_status
from vision.worker import create_vision_worker


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input_path", type=Path, help="image/SVG or exported stroke JSON")
    result.add_argument("--site-config", type=Path, default=ROOT / "config" / "drawing.local.json")
    result.add_argument("--runtime-config", type=Path, default=ROOT / "config" / "console.local.json")
    result.add_argument("--stroke-api-url", default="http://127.0.0.1:8000")
    result.add_argument("--stroke-provider", default="classic")
    result.add_argument("--stroke-parameters", default="{}", help="extra StrokeReview parameters as JSON")
    result.add_argument("--artifact-dir", type=Path)
    result.add_argument(
        "--allow-uniform-canvas-rescale", action="store_true",
        help="explicitly scale a JSON canvas uniformly to the configured board",
    )
    result.add_argument("--stroke-timeout", type=float, default=600.0)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--attended", action="store_true")
    result.add_argument("--log", type=Path)
    return result


def _parameters(raw):
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DrawingError("invalid_stroke_parameters") from error
    if not isinstance(result, dict):
        raise DrawingError("image_parameters_must_be_object")
    return result


def _artifact_dir(args, config, parameters):
    if args.artifact_dir is not None:
        return args.artifact_dir
    digest = hashlib.sha256()
    digest.update(args.input_path.resolve().read_bytes())
    digest.update(json.dumps({
        "provider": args.stroke_provider,
        "parameters": parameters,
        "canvas": [config.geometry.canvas_width_mm, config.geometry.canvas_height_mm],
    }, sort_keys=True).encode("utf-8"))
    return ROOT / "dataset" / "generated" / (
        "%s-%s-%d" % (
            args.input_path.stem, digest.hexdigest()[:12], time.time_ns()
        )
    )


def _prepare_job(args, config, image_config):
    is_json = args.input_path.suffix.lower() == ".json"
    artifact = None
    drawing_path = args.input_path
    if not is_json:
        parameters = _parameters(args.stroke_parameters)
        artifact = process_image_to_artifacts(
            args.input_path,
            _artifact_dir(args, config, parameters),
            config.geometry.canvas_width_mm,
            config.geometry.canvas_height_mm,
            content_margin_mm=image_config.short_edge_margin_mm,
            provider=args.stroke_provider,
            base_url=args.stroke_api_url,
            extra_parameters=parameters,
            timeout_seconds=args.stroke_timeout,
        )
        drawing_path = artifact["drawing_path"]
    job = load_drawing_job(drawing_path, flat_group_name=config.flat_group_name)
    board = validate_job_canvas(
        job, config,
        allow_uniform_rescale=args.allow_uniform_canvas_rescale,
    )
    return job, board, artifact, is_json


def _summary(job, drawing_config, control_config, board, artifact):
    initial_offset = (
        control_config.baseline.initial_json_axis_offset_mm
        if control_config.selected_mode == "baseline" else 0.0
    )
    first_plan = build_drawing_plan(job, drawing_config, initial_offset)
    return {
        "mode": control_config.selected_mode,
        "source": "json" if artifact is None else "image_auto_review",
        "generated_drawing_path": None if artifact is None else str(artifact["drawing_path"]),
        "generated_audit_path": None if artifact is None else str(artifact["audit_path"]),
        "job_sha256": job.canonical_sha256,
        "drawing_config_sha256": drawing_config.canonical_sha256,
        "production_ready": drawing_config.production_ready,
        "drawing_board": board,
        "groups": len(job.groups),
        "strokes": job.stroke_count,
        "points": job.point_count,
        "initial_json_axis_offset_mm": initial_offset,
        "requires_initial_apriltag_lock": control_config.selected_mode != "baseline",
        "first_window_complete": first_plan.complete,
        "first_checkpoint": None if first_plan.next_checkpoint is None else first_plan.next_checkpoint.to_dict(),
    }


def main(argv=None):
    raw_chassis = chassis = arm = vision = log = None
    chassis_enabled = False
    try:
        args = parser().parse_args(argv)
        site = load_drawing_site_config(args.site_config)
        drawing_config = site.drawing
        control_config = site.control
        job, board, artifact, is_json = _prepare_job(
            args, drawing_config,
            site.image_to_json,
        )
        summary = _summary(job, drawing_config, control_config, board, artifact)
        if not args.execute:
            print(json.dumps({**summary, "execute": False}, ensure_ascii=False, indent=2, sort_keys=True))
            print("DRY_RUN no device connection or motion")
            return 0

        execution_admission = DrawingExecutionAdmission(args.attended)
        execution_admission.require()
        if not site.production_ready:
            raise DrawingError("drawing_site_not_production_ready")

        runtime_config = load_runtime_config(args.runtime_config)
        if site is not None:
            runtime_config = site.apply_runtime(runtime_config)
        localized = control_config.selected_mode != "baseline"
        if localized:
            if not runtime_config.vision.complete or not runtime_config.localization.complete:
                raise DrawingError("localized_runtime_configuration_incomplete")
            if runtime_config.localization.json_mm_per_rail_mm != control_config.json_mm_per_rail_mm:
                raise DrawingError("localized_runtime_scale_mismatch")

        log_path = args.log or ROOT / "logs" / "drawing" / (
            "%s-%s-%s.jsonl" % (
                time.strftime("%Y%m%d-%H%M%S"),
                control_config.selected_mode,
                job.canonical_sha256[:8],
            )
        )
        log = EventLog(log_path)
        log.emit({"event": "execution_requested", **summary})
        raw_chassis = default_chassis_factory(runtime_config.chassis)
        raw_chassis.enable()
        chassis_enabled = True
        status = parse_chassis_status(raw_chassis.status())
        if (
            status.service_state != "ready"
            or status.chassis_state != "enabled_stopped"
            or not status.motion_permitted
            or status.last_error != "none"
        ):
            raise DrawingError("chassis_preflight_rejected")
        chassis = GuardedChassisSession(
            raw_chassis, runtime_config.manual_chassis.health_interval_ms / 1000.0
        )
        chassis.start()

        localization = None
        if localized:
            localization = create_localization_state_machine(runtime_config)
            localization.on_chassis_status(status.chassis_state)
            vision = create_vision_worker(runtime_config, localization.observe_vision)
            vision.start()
            settings = (
                control_config.localized_baseline
                if control_config.selected_mode == "localized_baseline"
                else control_config.advanced
            )
            _wait_for_initial_lock(
                localization, chassis, settings.localization_timeout_ms,
                settings.poll_ms, log.emit,
            )

        arm = default_arm_factory(runtime_config.arm)
        result = execute_drawing(
            ArmWithChassisGuard(arm, chassis), chassis, localization,
            job, drawing_config, control_config, execution_admission,
            RelocationAdmission(args.attended, True, "enabled_stopped"),
            "drawing-" + job.canonical_sha256[:16], log.emit,
        )
        log.emit({"event": "execution_done", **result})
        print(json.dumps({**summary, **result, "execute": True}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (
        DrawingError, RuntimeConfigError, StatusMappingError,
        OSError, RuntimeError, ValueError,
    ) as error:
        code = getattr(error, "code", str(error))
        if log is not None:
            log.emit({"event": "execution_failed", "error_code": code})
        print("ERROR: %s" % code, file=sys.stderr)
        return 2
    finally:
        if vision is not None:
            vision.stop()
        if chassis is not None:
            chassis.close()
        if raw_chassis is not None and chassis_enabled:
            try:
                raw_chassis.stop()
            except Exception:
                pass
            try:
                raw_chassis.disable()
            except Exception:
                pass
        close_client(arm)
        close_client(raw_chassis)
        if log is not None:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
