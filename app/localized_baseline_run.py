"""Dry-run or explicitly execute AprilTag-localized direct-drive drawing."""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "protocol", ROOT / "src" / "console"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from drawing import (
    DrawingError,
    DrawingExecutionAdmission,
    DrawingExecutionError,
    RelocationAdmission,
    build_drawing_plan,
    execute_localized_drawing,
    load_drawing_site_config,
    load_drawing_job,
)
from localization import create_localization_state_machine
from runtime_config import RuntimeConfigError, load_runtime_config
from runtime_core import close_client, default_arm_factory, default_chassis_factory
from status_mapping import StatusMappingError, parse_chassis_status
from vision.worker import create_vision_worker


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("drawing_path", type=Path)
    result.add_argument("--site-config", type=Path, default=ROOT / "config" / "drawing.local.json")
    result.add_argument("--runtime-config", type=Path, default=ROOT / "config" / "console.local.json")
    result.add_argument("--execute", action="store_true")
    result.add_argument("--attended", action="store_true")
    result.add_argument("--log", type=Path)
    return result


class EventLog:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("x", encoding="utf-8")
        self._lock = threading.Lock()

    def emit(self, event):
        record = {"time_ms": int(time.time() * 1000), **event}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock:
            self.stream.write(line)
            name = str(event.get("event") or event.get("state") or "")
            if (
                name in {
                    "execution_requested", "execution_done", "execution_failed",
                    "execution_stopped", "baseline_done",
                    "localized_baseline_done", "advanced_done",
                }
                or name.endswith("_window_done")
                or name.endswith("_relocation_done")
            ):
                self.stream.flush()
                os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


class GuardedChassisSession:
    """Serialize the one ESP32 session and keep it alive during arm windows."""

    def __init__(self, client, interval_seconds=0.5):
        self.client = client
        self.interval_seconds = interval_seconds
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._fault = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._keepalive, name="localized-baseline-chassis", daemon=True
        )
        self._thread.start()

    def _keepalive(self):
        while not self._stop.wait(self.interval_seconds):
            try:
                with self._lock:
                    self.client.ping()
            except Exception as error:
                self._fault = error
                return

    def check(self):
        if self._fault is not None:
            raise DrawingError("chassis_keepalive_failed") from self._fault

    def _call(self, name, *args):
        self.check()
        with self._lock:
            return getattr(self.client, name)(*args)

    def velocity(self, *args):
        return self._call("velocity", *args)

    def stop(self):
        with self._lock:
            return self.client.stop()

    def status(self):
        return self._call("status")

    def ping(self):
        return self._call("ping")

    def line_follow_start(self, *args):
        return self._call("line_follow_start", *args)

    def line_follow_status(self):
        return self._call("line_follow_status")

    def line_follow_stop(self):
        return self._call("line_follow_stop")

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 1.0)


class ArmWithChassisGuard:
    """Stop submitting later arm commands after an ESP32 keepalive fault."""

    def __init__(self, arm, chassis):
        self.arm = arm
        self.chassis = chassis

    def __getattr__(self, name):
        target = getattr(self.arm, name)
        if not callable(target):
            return target

        def guarded(*args, **kwargs):
            self.chassis.check()
            return target(*args, **kwargs)

        return guarded


def _wait_for_initial_lock(localization, chassis, timeout_ms, poll_ms, emit):
    before = localization.snapshot().get("generation", 0)
    localization.request_relocalization()
    deadline = time.monotonic() + timeout_ms / 1000.0
    emit({"event": "initial_localization_start", "previous_generation": before})
    while time.monotonic() < deadline:
        chassis.ping()
        snapshot = localization.snapshot()
        if snapshot.get("state") == "locked" and snapshot.get("generation", 0) > before:
            emit({
                "event": "initial_localization_locked",
                "generation": snapshot["generation"],
                "context": snapshot["context"],
            })
            return snapshot["context"]
        if snapshot.get("state") in ("blocked", "invalid", "disabled"):
            raise DrawingError("initial_localization_%s" % snapshot.get("state"))
        time.sleep(poll_ms / 1000.0)
    raise DrawingError("initial_localization_timeout")


def _summary(job, drawing_config, control_config, first_plan):
    return {
        "mode": control_config.selected_mode,
        "production_ready": drawing_config.production_ready,
        "job_sha256": job.canonical_sha256,
        "drawing_config_sha256": drawing_config.canonical_sha256,
        "groups": len(job.groups),
        "strokes": job.stroke_count,
        "points": job.point_count,
        "requires_initial_apriltag_lock": True,
        "offset_zero_preview_complete": first_plan.complete,
        "offset_zero_preview_checkpoint": (
            None if first_plan.next_checkpoint is None
            else first_plan.next_checkpoint.to_dict()
        ),
    }


def main(argv=None):
    raw_chassis = chassis = arm = vision = log = None
    chassis_enabled = False
    try:
        args = parser().parse_args(argv)
        site = load_drawing_site_config(args.site_config)
        drawing_config = site.drawing
        control_config = site.control
        if control_config.selected_mode != "localized_baseline":
            raise DrawingError("localized_baseline_mode_required")
        job = load_drawing_job(
            args.drawing_path, flat_group_name=drawing_config.flat_group_name
        )
        first_plan = build_drawing_plan(job, drawing_config)
        summary = _summary(job, drawing_config, control_config, first_plan)
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
        if not runtime_config.vision.complete or not runtime_config.localization.complete:
            raise DrawingError("localized_runtime_configuration_incomplete")
        if runtime_config.localization.json_mm_per_rail_mm != control_config.json_mm_per_rail_mm:
            raise DrawingError("localized_baseline_localization_scale_mismatch")

        log_path = args.log or ROOT / "logs" / "drawing" / (
            "%s-localized_baseline-%s.jsonl" % (
                time.strftime("%Y%m%d-%H%M%S"), job.canonical_sha256[:8]
            )
        )
        log = EventLog(log_path)
        log.emit({"event": "execution_requested", **summary})
        localization = create_localization_state_machine(runtime_config)
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
        localization.on_chassis_status(status.chassis_state)
        chassis = GuardedChassisSession(
            raw_chassis,
            runtime_config.manual_chassis.health_interval_ms / 1000.0,
        )
        chassis.start()
        vision = create_vision_worker(runtime_config, localization.observe_vision)
        vision.start()
        settings = control_config.localized_baseline
        _wait_for_initial_lock(
            localization, chassis, settings.localization_timeout_ms,
            settings.poll_ms, log.emit,
        )
        arm = default_arm_factory(runtime_config.arm)
        result = execute_localized_drawing(
            ArmWithChassisGuard(arm, chassis), chassis, localization,
            job, drawing_config, control_config, execution_admission,
            RelocationAdmission(args.attended, True, "enabled_stopped"),
            "drawing-" + job.canonical_sha256[:16], log.emit,
        )
        log.emit({"event": "execution_done", **result})
        print(json.dumps({**summary, **result, "execute": True}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (
        DrawingError, DrawingExecutionError, RuntimeConfigError,
        StatusMappingError, OSError, RuntimeError, ValueError,
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
