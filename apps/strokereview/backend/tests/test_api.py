from __future__ import annotations

import base64
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


client = TestClient(app)


def png_bytes(width: int = 320, height: int = 180) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def process_image(parameters: str = '{"provider":"mock"}'):
    return client.post(
        "/api/v1/process",
        files={"file": ("sample.png", png_bytes(), "image/png")},
        data={"parameters": parameters},
    )


def test_health_and_capabilities() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "provider": "classic"}
    capabilities = client.get("/api/v1/capabilities").json()
    assert capabilities["providers"] == ["classic", "lineart", "pidinet", "hed", "qwen_cloud", "mock"]
    assert [option["id"] for option in capabilities["provider_options"]] == capabilities["providers"]
    assert capabilities["provider_options"][0]["implementation"].endswith("ClassicPipeline")
    assert "image/svg+xml" in capabilities["accepted_types"]
    cloud = next(option for option in capabilities["provider_options"] if option["id"] == "qwen_cloud")
    assert cloud["is_cloud"] is True
    assert cloud["usage_notice"]


def test_unconfigured_qwen_mode_fails_without_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("QWEN_IMAGE_MODEL", raising=False)
    response = process_image('{"provider":"qwen_cloud"}')
    assert response.status_code == 503
    assert "missing DASHSCOPE_API_KEY" in response.json()["detail"]


def test_mock_processing_separates_downstream_and_audit_contracts() -> None:
    response = process_image()
    assert response.status_code == 200
    payload = response.json()

    official = payload["strokes_document"]
    audit = payload["audit_document"]
    assert official["canvas"]["width"] == 1.0
    assert official["canvas"]["height"] == 0.5625
    assert len(official["strokes"]) == 1
    assert set(official["strokes"][0]) == {"id", "order", "points", "closed"}
    assert official["strokes"][0]["order"] == 1

    assert [stroke["decision"] for stroke in audit["strokes"]] == [
        "keep",
        "uncertain",
        "discard",
    ]
    assert audit["processing"]["actual_provider"] == "mock"
    assert audit["warnings"] == ["mock_provider_output"]


def test_mock_processing_is_deterministic() -> None:
    first = process_image().json()
    second = process_image().json()
    assert first == second


def test_processing_parameters_are_audited() -> None:
    response = process_image(
        '{"provider":"mock", "detail_level": 80, "target_width_mm": 300, "target_height_mm": 200}'
    )
    assert response.status_code == 200
    parameters = response.json()["audit_document"]["processing"]["parameters"]
    assert parameters["detail_level"] == 80
    assert parameters["target_width_mm"] == 300
    assert parameters["target_height_mm"] == 200
    assert response.json()["audit_document"]["canvas"]["target_height_mm"] == 200


def test_invalid_upload_is_rejected() -> None:
    response = client.post(
        "/api/v1/process",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
        data={"parameters": "{}"},
    )
    assert response.status_code == 415


def test_unknown_pipeline_is_rejected_with_available_options() -> None:
    response = process_image('{"provider":"not_registered"}')
    assert response.status_code == 422
    assert "Available providers" in response.json()["detail"]


def test_optional_basic_auth(monkeypatch) -> None:
    monkeypatch.setenv("APP_ACCESS_USERNAME", "reviewer")
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "secret")
    assert client.get("/api/v1/capabilities").status_code == 401
    token = base64.b64encode(b"reviewer:secret").decode()
    response = client.get(
        "/api/v1/capabilities", headers={"Authorization": f"Basic {token}"}
    )
    assert response.status_code == 200
