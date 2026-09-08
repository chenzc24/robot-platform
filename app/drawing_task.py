"""Build a deterministic PC drawing preview; this command cannot execute motion."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SOURCE = ROOT / "src" / "console"
if str(CONSOLE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SOURCE))

from drawing import (
    DrawingError,
    PlanCheckpoint,
    build_drawing_plan,
    load_drawing_config,
    load_drawing_job,
)


def build_preview(drawing_path, config_path, json_axis_offset_mm=0.0, checkpoint=None):
    config = load_drawing_config(config_path)
    job = load_drawing_job(drawing_path, flat_group_name=config.flat_group_name)
    plan = build_drawing_plan(
        job,
        config,
        json_axis_offset_mm=json_axis_offset_mm,
        checkpoint=checkpoint,
    )
    return job, config, plan


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "drawing_path",
        nargs="?",
        type=Path,
        default=ROOT / "dataset" / "dobot-generation-1.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "drawing.local.json",
    )
    parser.add_argument("--json-axis-offset-mm", type=float, default=0.0)
    parser.add_argument(
        "--checkpoint",
        type=int,
        nargs=3,
        metavar=("GROUP", "STROKE", "NEXT_POINT"),
    )
    parser.add_argument("--show-steps", action="store_true")
    parser.add_argument("--output-plan", type=Path)
    return parser


def main(argv=None):
    try:
        args = argument_parser().parse_args(argv)
        checkpoint = (
            None if args.checkpoint is None else PlanCheckpoint(*args.checkpoint)
        )
        job, config, plan = build_preview(
            args.drawing_path,
            args.config,
            args.json_axis_offset_mm,
            checkpoint,
        )
        summary = plan.to_dict(include_steps=False)
        summary.update(
            {
                "preview_only": True,
                "production_ready": config.production_ready,
                "source_shape": job.source_shape,
                "groups": len(job.groups),
                "strokes_total": job.stroke_count,
                "points_total": job.point_count,
                "canvas_metadata_mm": [
                    job.canvas.target_width_mm,
                    job.canvas.target_height_mm,
                ],
                "configured_canvas_mm": [
                    config.geometry.canvas_width_mm,
                    config.geometry.canvas_height_mm,
                ],
            }
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        if args.show_steps:
            for index, step in enumerate(plan.steps, 1):
                print(
                    json.dumps(
                        {"index": index, **step.to_dict()},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        if args.output_plan is not None:
            if args.output_plan.exists():
                raise DrawingError("output plan already exists")
            args.output_plan.parent.mkdir(parents=True, exist_ok=True)
            args.output_plan.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print("WROTE_PREVIEW_PLAN %s" % args.output_plan.resolve())
        print("PREVIEW_ONLY no device modules loaded; no connection or motion path exists")
        return 0
    except (DrawingError, OSError, ValueError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
