"""Capture tag pixels and expand measured anchors into one planar board layout."""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SOURCE = ROOT / "src" / "console"
if str(CONSOLE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SOURCE))

from vision.board_calibration import (  # noqa: E402
    BoardCalibrationError,
    detect_apriltag_pixels,
    parse_center_anchor_layout,
    solve_board_layout,
)
from vision.calibration import parse_board_layout  # noqa: E402


DICTIONARY = "DICT_APRILTAG_36H11"
IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parse_ids(value):
    try:
        ids = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError as error:
        raise argparse.ArgumentTypeError("IDs must be comma-separated non-negative integers") from error
    if not ids or ids[0] < 0:
        raise argparse.ArgumentTypeError("IDs must be comma-separated non-negative integers")
    return ids


def _parse_stations(value):
    stations = [item.strip() for item in value.split(",") if item.strip()]
    if not stations:
        raise argparse.ArgumentTypeError("stations must be comma-separated non-empty labels")
    return stations


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Observation-only planar AprilTag board calibration; never sends robot commands."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture", help="Capture decoded tag pixel corners")
    capture.add_argument("--source", required=True, help="RTSP URL, image, directory, or image glob")
    capture.add_argument("--output", required=True, help="Observation JSON to create or append")
    capture.add_argument("--station", required=True, help="Stable stop label recorded on every frame")
    capture.add_argument("--append", action="store_true", help="Append to an existing observation JSON")
    capture.add_argument("--max-frames", type=_positive_int, default=20, help="Detection-bearing frames to save")
    capture.add_argument("--timeout-s", type=_positive_float, default=30.0, help="RTSP capture deadline")
    capture.add_argument("--detection-fps", type=_positive_float, default=5.0)
    capture.add_argument("--min-tag-edge-px", type=_positive_float, default=12.0)

    solve = commands.add_parser("solve", help="Fit unknown tag world corners from measured anchors")
    solve.add_argument("--observations", required=True)
    solve.add_argument(
        "--anchors",
        required=True,
        help="Measured center-anchor JSON or legacy measured four-corner board JSON",
    )
    solve.add_argument("--target-ids", required=True, type=_parse_ids, help="All intended IDs, comma-separated")
    solve.add_argument("--layout-id", required=True)
    solve.add_argument("--output", required=True, help="Generated complete board JSON")
    solve.add_argument("--report", required=True, help="Residual and connectivity report JSON")
    solve.add_argument("--tag-size-mm", type=_positive_float, default=None)
    solve.add_argument("--min-samples-per-tag", type=_positive_int, default=3)
    solve.add_argument("--min-stations-per-tag", type=_positive_int, default=2)
    solve.add_argument("--outlier-threshold-mm", type=_positive_float, default=5.0)
    solve.add_argument("--refinement-iterations", type=int, default=8)
    solve.add_argument(
        "--stations",
        type=_parse_stations,
        default=None,
        help="Only use frames from these comma-separated station labels",
    )
    return parser.parse_args(argv)


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoardCalibrationError("json_read_failed:%s" % Path(path).name) from error
    if not isinstance(value, dict):
        raise BoardCalibrationError("json_object_required:%s" % Path(path).name)
    return value


def _write_json(path, value):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _new_observation_document():
    return {"schema_version": 1, "dictionary": DICTIONARY, "frames": []}


def _load_capture_destination(path, append):
    destination = Path(path)
    if not append:
        if destination.exists():
            raise BoardCalibrationError("output_exists_use_append_or_new_path")
        return _new_observation_document()
    if not destination.exists():
        return _new_observation_document()
    document = _read_json(destination)
    if (
        document.get("schema_version") != 1
        or document.get("dictionary") != DICTIONARY
        or not isinstance(document.get("frames"), list)
    ):
        raise BoardCalibrationError("existing_observation_schema_invalid")
    return document


def _frame_record(image, source, station, min_tag_edge_px):
    result = detect_apriltag_pixels(image, min_tag_edge_px=min_tag_edge_px)
    return {
        "captured_at_ms": int(time.time() * 1000),
        "station": station,
        "source": source,
        **result,
    }


def _image_paths(source):
    source_path = Path(source)
    if source_path.is_dir():
        return sorted(path for path in source_path.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if source_path.is_file():
        return [source_path]
    return sorted(
        Path(path) for path in glob.glob(source)
        if Path(path).is_file() and Path(path).suffix.lower() in IMAGE_SUFFIXES
    )


def _capture_images(args, document):
    import cv2

    paths = _image_paths(args.source)
    if not paths:
        raise BoardCalibrationError("source_images_unavailable")
    added = 0
    for path in paths[:args.max_frames]:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        frame = _frame_record(image, path.name, args.station, args.min_tag_edge_px)
        if frame["observations"]:
            document["frames"].append(frame)
            added += 1
    return added


def _capture_rtsp(args, document):
    import cv2

    capture = cv2.VideoCapture(args.source)
    if not capture.isOpened():
        capture.release()
        raise BoardCalibrationError("rtsp_source_unavailable")
    deadline = time.monotonic() + args.timeout_s
    next_detection = 0.0
    added = 0
    try:
        while added < args.max_frames and time.monotonic() < deadline:
            available, image = capture.read()
            if not available or image is None:
                time.sleep(0.02)
                continue
            now = time.monotonic()
            if now < next_detection:
                continue
            next_detection = now + 1.0 / args.detection_fps
            frame = _frame_record(image, "rtsp", args.station, args.min_tag_edge_px)
            if frame["observations"]:
                document["frames"].append(frame)
                added += 1
    finally:
        capture.release()
    return added


def capture_command(args):
    document = _load_capture_destination(args.output, args.append)
    if args.source.lower().startswith(("rtsp://", "rtsps://")):
        added = _capture_rtsp(args, document)
    else:
        added = _capture_images(args, document)
    if added == 0:
        raise BoardCalibrationError("no_detection_bearing_frames_captured")
    _write_json(args.output, document)
    print(json.dumps({
        "status": "captured",
        "station": args.station,
        "added_frames": added,
        "total_frames": len(document["frames"]),
        "output": str(Path(args.output)),
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


def solve_command(args):
    if args.refinement_iterations < 0:
        raise BoardCalibrationError("refinement_iterations_must_be_non_negative")
    observations = _read_json(args.observations)
    if args.stations:
        requested_stations = set(args.stations)
        available_stations = {
            str(frame.get("station", ""))
            for frame in observations.get("frames", [])
            if isinstance(frame, dict)
        }
        missing_stations = sorted(requested_stations - available_stations)
        if missing_stations:
            raise BoardCalibrationError(
                "observation_stations_not_found:%s" % ",".join(missing_stations)
            )
        observations = {
            **observations,
            "frames": [
                frame
                for frame in observations.get("frames", [])
                if isinstance(frame, dict)
                and str(frame.get("station", "")) in requested_stations
            ],
        }
    raw_anchors = _read_json(args.anchors)
    anchors = (
        parse_center_anchor_layout(raw_anchors)
        if "anchors" in raw_anchors
        else parse_board_layout(raw_anchors)
    )
    board, report = solve_board_layout(
        anchors,
        observations,
        target_ids=args.target_ids,
        layout_id=args.layout_id,
        tag_size_mm=args.tag_size_mm,
        min_samples_per_tag=args.min_samples_per_tag,
        min_stations_per_tag=args.min_stations_per_tag,
        outlier_threshold_mm=args.outlier_threshold_mm,
        refinement_iterations=args.refinement_iterations,
    )
    parse_board_layout(board)
    _write_json(args.output, board)
    _write_json(args.report, report)
    print(json.dumps({
        "status": report["status"],
        "layout_id": report["layout_id"],
        "frame_count": report["frame_count"],
        "estimated_ids": report["estimated_ids"],
        "cross_validated_corner_rmse_mm": report["cross_validated_corner_rmse_mm"],
        "output": str(Path(args.output)),
        "report": str(Path(args.report)),
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command == "capture":
            return capture_command(args)
        return solve_command(args)
    except Exception as error:
        print("AprilTag board calibration failed: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
