from __future__ import annotations

import asyncio
import json
from io import BytesIO

import httpx
from PIL import Image, ImageDraw

from app.classic_provider import process_classic
from app.models import ProcessingParameters
from app.vision_review_provider import review_process_result


def drawing_bytes() -> bytes:
    image = Image.new("RGB", (128, 128), "white")
    ImageDraw.Draw(image).line((12, 64, 116, 64), fill="black", width=4)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def configure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "vision-test-key")
    monkeypatch.setenv("QWEN_VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("QWEN_VISION_MODEL", "qwen3.8-max-0902")
    monkeypatch.setenv("QWEN_VISION_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("QWEN_VISION_DAILY_REQUEST_LIMIT", "20")


def response(value: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]},
    )


def test_semantic_review_scores_stable_ids_and_is_cached(monkeypatch, tmp_path) -> None:
    configure(monkeypatch, tmp_path)
    content = drawing_bytes()
    parameters = ProcessingParameters(
        provider="classic",
        smoothing=0,
        minimum_length_mm=0,
        ai_semantic_review=True,
        ai_review_quality="economy",
        max_cloud_review_calls=3,
    )
    original = process_classic(content, "line.png", parameters)
    stroke_id = original.audit_document.strokes[0].id
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer vision-test-key"
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["model"] == "qwen3.8-max-0902"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["enable_thinking"] is False
        prompt = payload["messages"][0]["content"][0]["text"]
        if "制定机械臂极简轮廓画" in prompt:
            return response({
                "main_subjects": [{"name": "横线", "priority": 1, "bbox": [0.1, 0.4, 0.9, 0.6], "identity_features": ["整体方向"]}],
                "relationships": [],
                "required_structures": ["横向主轮廓"],
                "discardable_details": [],
            })
        return response({
            "strokes": [{
                "id": stroke_id,
                "role": "main_silhouette",
                "semantic_importance": 96,
                "removal_damage": 98,
                "confidence": 94,
                "recommendation": "keep",
                "reason": "唯一的主体轮廓",
            }]
        })

    reviewed = asyncio.run(review_process_result(
        content,
        "line.png",
        original,
        transport=httpx.MockTransport(handler),
    ))
    assert len(calls) == 2
    stroke = reviewed.audit_document.strokes[0]
    assert stroke.semantic_role == "main_silhouette"
    assert stroke.scores.semantic_importance == 0.96
    assert stroke.scores.removal_damage == 0.98
    assert reviewed.audit_document.semantic_review.status == "completed"
    assert reviewed.audit_document.semantic_review.model == "qwen3.8-max-0902"

    second_input = process_classic(content, "line.png", parameters)
    cached = asyncio.run(review_process_result(
        content,
        "line.png",
        second_input,
        transport=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("network call"))),
    ))
    assert cached.audit_document.semantic_review.call_count == 0
    assert cached.audit_document.semantic_review.cache_hit_count == 2


def test_semantic_failure_falls_back_to_local_result(monkeypatch, tmp_path) -> None:
    configure(monkeypatch, tmp_path)
    content = drawing_bytes()
    parameters = ProcessingParameters(
        provider="classic",
        smoothing=0,
        ai_semantic_review=True,
        ai_review_quality="economy",
    )
    original = process_classic(content, "line.png", parameters)
    reviewed = asyncio.run(review_process_result(
        content,
        "line.png",
        original,
        transport=httpx.MockTransport(lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[]"}}]},
        )),
    ))

    assert reviewed.audit_document.semantic_review.status == "fallback"
    assert "semantic_review_fallback" in reviewed.audit_document.warnings
    assert reviewed.strokes_document.strokes == original.strokes_document.strokes
