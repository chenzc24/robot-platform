from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image

from app.main import app


def test_health_does_not_download_models() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["device"] == "cpu"
    assert payload["models"] == ["lineart", "pidinet", "hed"]
    assert payload["loaded_models"] == []
    assert [detector["id"] for detector in payload["detectors"]] == payload["models"]


def test_unknown_detector_is_rejected_without_loading_weights() -> None:
    image = BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, "PNG")
    response = TestClient(app).post(
        "/v1/extract",
        files={"file": ("sample.png", image.getvalue(), "image/png")},
        data={"model": "missing", "detect_resolution": "256"},
    )
    assert response.status_code == 422
    assert "Available detectors" in response.json()["detail"]
