"""Minimal StrokeReview HTTP client for downstream integration."""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload an image to StrokeReview and save its JSON outputs."
    )
    parser.add_argument("image", type=Path, help="PNG, JPEG, or SVG input file")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="StrokeReview service base URL",
    )
    parser.add_argument("--provider", default="classic", help="Processing provider ID")
    parser.add_argument(
        "--parameters",
        help="Extra processing parameters as a JSON object; provider is overridden by --provider",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("stroke-output"))
    parser.add_argument("--username", help="Optional HTTP Basic Auth username")
    parser.add_argument("--password", help="Optional HTTP Basic Auth password")
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


def load_parameters(raw: str | None, provider: str) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("--parameters must be a JSON object")
        parameters.update(parsed)
    parameters["provider"] = provider
    return parameters


def main() -> int:
    args = parse_args()
    image_path = args.image.resolve()
    if not image_path.is_file():
        raise SystemExit(f"Input file does not exist: {image_path}")

    try:
        parameters = load_parameters(args.parameters, args.provider)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid parameters: {exc}") from exc

    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    auth = None
    if args.username is not None or args.password is not None:
        if not args.username or args.password is None:
            raise SystemExit("--username and --password must be provided together")
        auth = httpx.BasicAuth(args.username, args.password)

    endpoint = args.base_url.rstrip("/") + "/api/v1/process"
    with image_path.open("rb") as image_file, httpx.Client(
        timeout=args.timeout,
        auth=auth,
        follow_redirects=False,
    ) as client:
        response = client.post(
            endpoint,
            files={"file": (image_path.name, image_file, content_type)},
            data={"parameters": json.dumps(parameters, ensure_ascii=False)},
        )

    if response.is_error:
        detail = response.text[:2000]
        raise SystemExit(f"StrokeReview returned HTTP {response.status_code}: {detail}")

    payload = response.json()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "process-response.json": payload,
        "strokes.json": payload["strokes_document"],
        "audit.json": payload["audit_document"],
    }
    for filename, document in outputs.items():
        destination = output_dir / filename
        destination.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    stroke_count = len(payload["strokes_document"]["strokes"])
    print(f"Saved {stroke_count} strokes to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
