"""Dry-run or explicitly execute one complete arm-only Baseline drawing."""

import argparse
import json
import os
import sys
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
    build_drawing_plan,
    execute_drawing_plan,
    flatten_plan_steps,
    load_drawing_site_config,
    load_drawing_job,
)
from maixcam_arm_client import MaixCamArmClient, open_connection


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("drawing_path", type=Path)
    result.add_argument("--config", type=Path, default=ROOT / "config" / "drawing.local.json")
    result.add_argument("--arm-host", default="maixcam-6c7d.local")
    result.add_argument("--arm-port", type=int, default=8780)
    result.add_argument("--connect-timeout", type=float, default=5.0)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--attended", action="store_true")
    result.add_argument("--log", type=Path)
    return result


def _summary(job, config, plan):
    steps = flatten_plan_steps(plan)
    return {
        "mode": "baseline_arm_only",
        "production_ready": config.production_ready,
        "job_sha256": job.canonical_sha256,
        "config_sha256": config.canonical_sha256,
        "groups": len(job.groups),
        "strokes": job.stroke_count,
        "points": job.point_count,
        "atomic_steps": len(steps),
        "arm_commands": sum(kind != "sleep" for _, kind, _ in steps),
        "sleep_steps": sum(kind == "sleep" for _, kind, _ in steps),
        "chassis_commands": 0,
        "complete": plan.complete,
    }


class EventLog:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("x", encoding="utf-8")

    def emit(self, event):
        event = {"time_ms": int(time.time() * 1000), **event}
        self.stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        if event.get("event") in {
            "execution_requested", "execution_done", "execution_failed",
            "execution_stopped",
        }:
            self.stream.flush()
            os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def main(argv=None):
    client = log = None
    try:
        args = parser().parse_args(argv)
        config = load_drawing_site_config(args.config).drawing
        job = load_drawing_job(args.drawing_path, flat_group_name=config.flat_group_name)
        plan = build_drawing_plan(job, config)
        summary = _summary(job, config, plan)
        if not args.execute:
            print(json.dumps({**summary, "execute": False}, ensure_ascii=False, indent=2, sort_keys=True))
            print("DRY_RUN no device connection or motion")
            return 0
        admission = DrawingExecutionAdmission(args.attended)
        admission.require()
        if not config.production_ready:
            raise DrawingExecutionError("drawing_not_production_ready")
        log_path = args.log or ROOT / "logs" / "drawing" / (
            "%s-baseline-arm-%s.jsonl" % (
                time.strftime("%Y%m%d-%H%M%S"), job.canonical_sha256[:8]
            )
        )
        log = EventLog(log_path)
        log.emit({"event": "execution_requested", **summary})
        connection = open_connection(args.arm_host, args.arm_port, args.connect_timeout)
        client = MaixCamArmClient(connection, "baseline-drawing")
        result = execute_drawing_plan(client, plan, config, admission, log.emit)
        print(json.dumps({**summary, **result, "execute": True}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (DrawingError, DrawingExecutionError, OSError, ValueError) as error:
        code = getattr(error, "code", str(error))
        if log is not None:
            log.emit({"event": "execution_failed", "error_code": code})
        print("ERROR: %s" % code, file=sys.stderr)
        return 2
    finally:
        if client is not None:
            close = getattr(client.connection, "close", None)
            if callable(close):
                close()
        if log is not None:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
