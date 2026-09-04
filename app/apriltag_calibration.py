"""Observation-only CLI for PC AprilTag board localization."""

import argparse
import json
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SOURCE = ROOT / "src" / "console"
if str(CONSOLE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SOURCE))

from vision.apriltag_localizer import AprilTagBoardLocalizer
from vision.calibration import load_board_layout, load_camera_calibration
from vision.worker import RtspAprilTagWorker, VisionEventLog


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect AprilTag 36h11 board pose on the PC; never sends robot commands."
    )
    parser.add_argument("--source", required=True, help="Image path or RTSP URL")
    parser.add_argument("--board", default="config/apriltag-board.local.json")
    parser.add_argument("--camera", default="config/camera-calibration.local.json")
    parser.add_argument("--detection-fps", type=float, default=5.0)
    parser.add_argument("--min-tag-edge-px", type=float, default=24.0)
    parser.add_argument("--max-reprojection-error-px", type=float, default=5.0)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--log", default="logs/vision/apriltag-cli.log")
    parser.add_argument("--result-json", default="", help="Overwrite with the latest complete result")
    parser.add_argument("--max-results", type=int, default=0, help="Stop an RTSP run after N results; 0 runs until Ctrl-C")
    return parser.parse_args(argv)


def _emit(result, destination=None):
    line = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(line, flush=True)
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _localizer(args):
    return AprilTagBoardLocalizer(
        load_camera_calibration(args.camera),
        load_board_layout(args.board),
        min_tag_edge_px=args.min_tag_edge_px,
        max_reprojection_error_px=args.max_reprojection_error_px,
        min_confidence=args.min_confidence,
    )


def main(argv=None):
    args = parse_args(argv)
    if args.detection_fps <= 0 or args.max_results < 0 or not 0 <= args.min_confidence <= 1:
        print("Invalid numeric option", file=sys.stderr)
        return 2
    try:
        localizer = _localizer(args)
        if not args.source.lower().startswith("rtsp://"):
            import cv2

            image = cv2.imread(args.source, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("source_image_unavailable")
            result = localizer.process(image)
            _emit(result, args.result_json)
            VisionEventLog(args.log).write(
                "localization_image",
                source=str(Path(args.source).name),
                status=result["status"],
                accepted=result["accepted"],
                confidence=result["confidence"],
                reprojection_rmse_px=result["reprojection_rmse_px"],
                T_camera_from_board=result["T_camera_from_board"],
            )
            return 0 if result["pose_solved"] else 1

        completed = threading.Event()
        count = [0]

        def on_result(result):
            _emit(result, args.result_json)
            count[0] += 1
            if args.max_results and count[0] >= args.max_results:
                completed.set()

        worker = RtspAprilTagWorker(
            args.source,
            3.0,
            args.detection_fps,
            localizer,
            on_result,
            VisionEventLog(args.log),
        )
        worker.start()
        try:
            while not completed.wait(0.25):
                if not worker.running:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            worker.stop()
        return 0
    except Exception as error:
        print("AprilTag localization failed: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
