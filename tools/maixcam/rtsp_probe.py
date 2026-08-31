"""Receive a MaixCam RTSP stream, report media facts, and save one frame."""

import argparse
import json
import pathlib
import socket
import time
import urllib.parse


DEFAULT_URL = "rtsp://maixcam-6c7d.local:8554/live"


def build_parser():
    parser = argparse.ArgumentParser(description="Probe and capture a MaixCam RTSP stream")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--transport", choices=("auto", "udp", "tcp"), default="tcp")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("tmp/maixcam-frame.png"))
    return parser


def validate_settings(args):
    if not args.url.startswith("rtsp://"):
        raise ValueError("url must use rtsp://")
    if args.seconds <= 0:
        raise ValueError("seconds must be positive")
    if args.timeout <= 0:
        raise ValueError("timeout must be positive")


def resolve_ipv4_url(url):
    """Resolve an RTSP hostname explicitly to IPv4 for mixed mDNS results."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname is None:
        raise ValueError("url must contain a hostname")
    port = parsed.port or 554
    addresses = socket.getaddrinfo(parsed.hostname, port, socket.AF_INET, socket.SOCK_STREAM)
    if not addresses:
        raise RuntimeError("no IPv4 address found for {}".format(parsed.hostname))
    address = addresses[0][4][0]
    netloc = "{}:{}".format(address, port)
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def probe(args):
    validate_settings(args)
    import av

    args.output.parent.mkdir(parents=True, exist_ok=True)
    resolved_url = resolve_ipv4_url(args.url)
    options = {}
    if args.transport != "auto":
        options["rtsp_transport"] = args.transport
    started = time.monotonic()
    frames = 0
    first_frame_at = None
    first_media_time = None
    last_media_time = None

    with av.open(
        resolved_url,
        mode="r",
        options=options,
        timeout=(args.timeout, args.timeout),
    ) as container:
        stream = next((item for item in container.streams if item.type == "video"), None)
        if stream is None:
            raise RuntimeError("RTSP source has no video stream")

        for frame in container.decode(stream):
            now = time.monotonic()
            frames += 1
            if first_frame_at is None:
                first_frame_at = now
                first_media_time = frame.time
                frame.to_image().save(args.output)
            last_media_time = frame.time
            if now - started >= args.seconds:
                break

        elapsed = time.monotonic() - started
        if frames == 0 or first_frame_at is None:
            raise RuntimeError("RTSP source produced no decoded frames")

        codec = stream.codec_context.name
        width = stream.codec_context.width
        height = stream.codec_context.height
        declared_rate = stream.average_rate or stream.guessed_rate
        nominal_rate = float(declared_rate) if declared_rate else None

    media_span = None
    media_fps = None
    if first_media_time is not None and last_media_time is not None:
        media_span = last_media_time - first_media_time
        if media_span > 0 and frames > 1:
            media_fps = (frames - 1) / media_span

    return {
        "url": args.url,
        "resolved_url": resolved_url,
        "codec": codec,
        "width": width,
        "height": height,
        "nominal_fps": nominal_rate,
        "frames": frames,
        "elapsed_seconds": round(elapsed, 3),
        "media_seconds": round(media_span, 3) if media_span is not None else None,
        "measured_fps": round(media_fps, 3) if media_fps is not None else None,
        "first_frame_seconds": round(first_frame_at - started, 3),
        "frame_path": str(args.output.resolve()),
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    print(json.dumps(probe(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
