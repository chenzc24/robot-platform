from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app


def main() -> None:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 216, 216), outline="black", width=5)
    draw.line((40, 128, 216, 128), fill="black", width=4)
    buffer = BytesIO()
    image.save(buffer, "PNG")

    response = TestClient(app).post(
        "/api/v1/process",
        files={"file": ("e2e.png", buffer.getvalue(), "image/png")},
        data={
            "parameters": '{"provider":"lineart","detail_level":0,"smoothing":0}'
        },
    )
    response.raise_for_status()
    payload = response.json()
    processing = payload["audit_document"]["processing"]
    assert processing["actual_provider"] == "local-lineart", payload["audit_document"]
    assert payload["diagnostics"]["binary_png_data_url"].startswith(
        "data:image/png;base64,"
    )
    assert payload["diagnostics"]["skeleton_png_data_url"].startswith(
        "data:image/png;base64,"
    )
    print(
        {
            "status": response.status_code,
            "provider": processing["actual_provider"],
            "audit_strokes": len(payload["audit_document"]["strokes"]),
            "official_strokes": len(payload["strokes_document"]["strokes"]),
            "warnings": payload["audit_document"]["warnings"],
        }
    )


if __name__ == "__main__":
    main()
