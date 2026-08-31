"""Minimal MaixCam H.264 RTSP service with no robot-control dependencies."""

import argparse
import json
import signal
import sys
import time


DEFAULT_PORT = 8554
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 20
DEFAULT_BITRATE = 2_000_000


def build_parser():
    parser = argparse.ArgumentParser(description="Run the MaixCam RTSP video service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    return parser


def validate_settings(args):
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if args.width <= 0 or args.height <= 0:
        raise ValueError("width and height must be positive")
    if not 1 <= args.fps <= 60:
        raise ValueError("fps must be between 1 and 60")
    if args.bitrate <= 0:
        raise ValueError("bitrate must be positive")


def run(args):
    validate_settings(args)

    from maix import camera, comm, err, image, rtsp

    # Importing MaixPy can create its default UART0 protocol listener. This
    # standalone video process does not own a robot UART, so release it before
    # opening the camera. Future gateway code must assign UART ownership itself.
    uart_listener_removed = comm.rm_default_comm_listener()

    camera_device = camera.Camera(
        args.width,
        args.height,
        image.Format.FMT_YVU420SP,
    )
    server = rtsp.Rtsp(
        port=args.port,
        fps=args.fps,
        stream_type=rtsp.RtspStreamType.RTSP_STREAM_H264,
        bitrate=args.bitrate,
    )
    server.bind_camera(camera_device)

    result = server.start()
    if result != err.Err.ERR_NONE:
        raise RuntimeError("RTSP server failed to start: {}".format(result))

    state = {"stop": False}

    def request_stop(_signum, _frame):
        state["stop"] = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    print(
        json.dumps(
            {
                "event": "rtsp_started",
                "url": server.get_url(),
                "codec": "h264",
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "bitrate": args.bitrate,
                "default_uart_listener_removed": uart_listener_removed,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    try:
        while not state["stop"]:
            time.sleep(0.5)
    finally:
        server.stop()
        print(json.dumps({"event": "rtsp_stopped"}), flush=True)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception as exc:
        print(json.dumps({"event": "rtsp_error", "error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
