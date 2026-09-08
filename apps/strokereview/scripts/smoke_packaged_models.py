"""Run real offline inference against the packaged Windows model service."""

from __future__ import annotations

import argparse
import base64
import io
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _sample_png() -> bytes:
    image = Image.new("RGB", (128, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((22, 18, 106, 102), outline="black", width=5)
    draw.line((35, 95, 64, 116, 94, 95), fill="black", width=5)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return encoded.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("desktop_directory", type=Path)
    parser.add_argument("--models", nargs="+", default=["pidinet", "hed"])
    args = parser.parse_args()

    service_directory = args.desktop_directory.resolve() / "model-service"
    executable = service_directory / "StrokeModelService.exe"
    repository = service_directory / "models"
    if not executable.is_file() or not repository.is_dir():
        raise SystemExit(f"Packaged model service is incomplete: {service_directory}")

    port = _free_port()
    environment = os.environ.copy()
    environment.update({
        "LINEART_MODEL_REPOSITORY": str(repository),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    log = tempfile.NamedTemporaryFile(prefix="stroke-model-smoke-", suffix=".log", delete=False)
    log_path = Path(log.name)
    process = subprocess.Popen(
        [str(executable), "--host", "127.0.0.1", "--port", str(port)],
        cwd=service_directory,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Model service exited with {process.returncode}")
            try:
                response = httpx.get(f"{base_url}/api/health", timeout=2)
                response.raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            raise RuntimeError("Model service did not become healthy")

        image = _sample_png()
        for model in args.models:
            response = httpx.post(
                f"{base_url}/v1/extract",
                files={"file": ("smoke.png", image, "image/png")},
                data={"model": model, "detect_resolution": "256"},
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            decoded = base64.b64decode(payload["line_png_base64"], validate=True)
            with Image.open(io.BytesIO(decoded)) as result:
                result.verify()
            print(f"{model}: OK ({len(decoded)} PNG bytes, offline repository={payload['model_repository']})")
    except Exception:
        log.flush()
        details = log_path.read_text(encoding="utf-8", errors="replace")
        if details:
            print(details)
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
        log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
