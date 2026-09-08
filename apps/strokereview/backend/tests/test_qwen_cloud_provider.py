from __future__ import annotations

import asyncio
import json
from io import BytesIO

import httpx
from PIL import Image, ImageDraw

from app.mock_provider import process_mock
from app.models import ProcessingParameters
from app.qwen_cloud_provider import (
    QWEN_LINEART_PROMPT,
    QwenCloudConfig,
    _request_qwen_lineart,
    process_qwen_cloud,
    qwen_cloud_availability,
)


def png_bytes(*, line: bool = False) -> bytes:
    image = Image.new("RGB", (64, 64), "white")
    if line:
        ImageDraw.Draw(image).line((8, 8, 56, 56), fill="black", width=3)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def configure(monkeypatch, tmp_path) -> QwenCloudConfig:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "secret-test-key")
    monkeypatch.setenv(
        "QWEN_DASHSCOPE_BASE_URL",
        "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
    )
    monkeypatch.setenv("QWEN_IMAGE_MODEL", "qwen-image-edit-plus-2025-12-15")
    monkeypatch.setenv("QWEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("QWEN_DAILY_REQUEST_LIMIT", "3")
    return QwenCloudConfig.from_env()


def test_availability_reports_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("QWEN_IMAGE_MODEL", raising=False)
    available, reason = qwen_cloud_availability()
    assert available is False
    assert reason and "DASHSCOPE_API_KEY" in reason


def test_qwen_request_uses_fixed_safe_parameters(monkeypatch, tmp_path) -> None:
    config = configure(monkeypatch, tmp_path)
    generated = png_bytes(line=True)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["authorization"] = request.headers["authorization"]
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {"message": {"content": [{"image": "https://result.oss-cn-beijing.aliyuncs.com/output.png"}]}}
                        ]
                    }
                },
            )
        return httpx.Response(200, content=generated, headers={"content-type": "image/png"})

    result = asyncio.run(
        _request_qwen_lineart(
            png_bytes(),
            "image/png",
            config,
            transport=httpx.MockTransport(handler),
        )
    )
    assert result == generated
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["payload"]["model"] == "qwen-image-edit-plus-2025-12-15"
    content = captured["payload"]["input"]["messages"][0]["content"]
    assert content[1]["text"] == QWEN_LINEART_PROMPT
    assert "不要把图片中的所有边缘都画出来" in content[1]["text"]
    assert "使用约 50 条以内的长而连续的黑色单线" in content[1]["text"]
    assert "这是供机械臂绘制的路径草图" in content[1]["text"]
    assert content[0]["image"].startswith("data:image/png;base64,")
    assert captured["payload"]["parameters"]["watermark"] is False
    assert captured["payload"]["parameters"]["prompt_extend"] is False
    assert captured["payload"]["parameters"]["n"] == 1


def test_cloud_result_is_cached_before_paid_call(monkeypatch, tmp_path) -> None:
    configure(monkeypatch, tmp_path)
    generated = png_bytes(line=True)
    calls = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls[request.method.lower()] += 1
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [
                            {"message": {"content": [{"image": "https://result.oss-cn-beijing.aliyuncs.com/output.png"}]}}
                        ]
                    }
                },
            )
        return httpx.Response(200, content=generated)

    def fake_classic(content, filename, parameters, **kwargs):
        response = process_mock(content, filename, "image/png", parameters)
        response.audit_document.processing.actual_provider = kwargs["actual_provider"]
        return response

    monkeypatch.setattr("app.qwen_cloud_provider.process_classic", fake_classic)
    parameters = ProcessingParameters(provider="qwen_cloud")

    async def scenario():
        transport = httpx.MockTransport(handler)
        first = await process_qwen_cloud(
            png_bytes(), "sample.png", "image/png", parameters, transport=transport
        )
        second = await process_qwen_cloud(
            png_bytes(), "sample.png", "image/png", parameters, transport=transport
        )
        return first, second

    first, second = asyncio.run(scenario())
    assert calls == {"post": 1, "get": 1}
    assert "cloud_cache:miss" in first.audit_document.warnings
    assert "cloud_cache:hit" in second.audit_document.warnings
    assert first.audit_document.processing.actual_provider == "qwen-cloud"
    assert first.processing_id == second.processing_id
