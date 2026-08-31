"""Command-line entry point for the guarded MaixCam RTSP video service."""

import argparse
import signal
import time

from maix_runtime_status import RuntimeStatus
from video_service import (
    DEFAULT_BITRATE,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_PORT,
    DEFAULT_WIDTH,
    RtspVideoService,
    VideoSettings,
)


def build_parser():
    parser = argparse.ArgumentParser(description="Run the MaixCam RTSP video service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    return parser


def settings_from_args(args):
    """Convert parsed arguments to a validated settings object."""
    return VideoSettings(
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        bitrate=args.bitrate,
    )


def validate_settings(args):
    """Keep the original validation entry point for host-side tests."""
    settings_from_args(args)


def run(args, service_factory=None, status=None):
    """Run until a termination signal requests a guarded service stop."""
    settings = settings_from_args(args)
    status = status or RuntimeStatus("maixcam", "video")
    service_factory = service_factory or RtspVideoService
    service = service_factory(settings=settings, status=status)
    stop_requested = {"value": False}

    def request_stop(_signum, _frame):
        stop_requested["value"] = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    service.start()
    try:
        while not stop_requested["value"]:
            time.sleep(0.5)
    finally:
        service.stop()


def main(argv=None):
    args = build_parser().parse_args(argv)
    status = RuntimeStatus("maixcam", "video")
    try:
        run(args, status=status)
    except Exception as error:
        if status.state != "fault":
            status.transition(
                "fault",
                event="rtsp_error",
                error_code="video_runtime_failed",
                detail={"error_type": type(error).__name__},
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
