"""Semantic drawing review using an OpenAI-compatible Qwen vision model.

The vision model never emits geometry. It describes the scene, scores stable
candidate IDs and validates progressive previews; deterministic local code
remains responsible for topology, physical pen coverage and final JSON.
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

from .classic_provider import refinalize_raster_result
from .models import (
    AuditStroke,
    Decision,
    ProcessResponse,
    SemanticReviewSummary,
)


PROMPT_VERSION = "semantic-stroke-review-v1"
DEFAULT_VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_VISION_MODEL = "qwen3.8-max-0902"


class QwenVisionReviewError(RuntimeError):
    pass


class QwenVisionConfigurationError(QwenVisionReviewError):
    pass


class SceneSubject(BaseModel):
    name: str
    priority: float = Field(default=0.5, ge=0, le=1)
    bbox: list[float] | None = None
    identity_features: list[str] = Field(default_factory=list)


class ScenePlan(BaseModel):
    main_subjects: list[SceneSubject] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    required_structures: list[str] = Field(default_factory=list)
    discardable_details: list[str] = Field(default_factory=list)


class LineartCritique(BaseModel):
    acceptable: bool = True
    recognizability: float = Field(default=1.0, ge=0, le=1)
    missing_features: list[str] = Field(default_factory=list)
    dense_or_redundant_regions: list[str] = Field(default_factory=list)
    correction_prompt: str = ""


class StrokeReviewItem(BaseModel):
    id: str
    role: str = "unknown"
    semantic_importance: float = Field(default=50, ge=0, le=100)
    removal_damage: float = Field(default=50, ge=0, le=100)
    confidence: float = Field(default=50, ge=0, le=100)
    recommendation: str = "uncertain"
    reason: str = ""


class StrokeReviewBatch(BaseModel):
    strokes: list[StrokeReviewItem] = Field(default_factory=list)


class ProgressiveReview(BaseModel):
    recommended_min_strokes: int = Field(default=0, ge=0)
    earliest_recognizable_panel: int | None = None
    promote_ids: list[str] = Field(default_factory=list)
    demote_ids: list[str] = Field(default_factory=list)
    reason: str = ""


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise QwenVisionConfigurationError(f"{name} must be a positive integer") from exc


def _positive_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError as exc:
        raise QwenVisionConfigurationError(f"{name} must be a positive number") from exc


def _default_cache_dir() -> Path:
    configured = os.getenv("QWEN_VISION_CACHE_DIR") or os.getenv("QWEN_CACHE_DIR")
    if configured:
        return Path(configured).expanduser() / "vision-review"
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "StrokeReview" / "qwen-cache" / "vision-review"
    return Path.home() / ".cache" / "stroke-review" / "qwen-vision"


@dataclass(frozen=True)
class QwenVisionConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    daily_request_limit: int
    cache_enabled: bool
    cache_dir: Path

    @classmethod
    def from_env(cls) -> "QwenVisionConfig":
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        base_url = os.getenv("QWEN_VISION_BASE_URL", DEFAULT_VISION_BASE_URL).strip().rstrip("/")
        model = os.getenv("QWEN_VISION_MODEL", DEFAULT_VISION_MODEL).strip()
        if not api_key:
            raise QwenVisionConfigurationError("DASHSCOPE_API_KEY is missing")
        if not model:
            raise QwenVisionConfigurationError("QWEN_VISION_MODEL is missing")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not (parsed.hostname or "").lower().endswith(".aliyuncs.com")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise QwenVisionConfigurationError(
                "QWEN_VISION_BASE_URL must be an HTTPS aliyuncs.com compatible endpoint"
            )
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=_positive_float("QWEN_VISION_TIMEOUT_SECONDS", 180),
            daily_request_limit=_positive_int("QWEN_VISION_DAILY_REQUEST_LIMIT", 100),
            cache_enabled=os.getenv("QWEN_VISION_CACHE_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            cache_dir=_default_cache_dir(),
        )


@dataclass
class VisionReviewSession:
    config: QwenVisionConfig
    max_calls: int
    call_count: int = 0
    cache_hit_count: int = 0


class _DailyVisionBudget:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def reserve(self, config: QwenVisionConfig) -> None:
        async with self._lock:
            config.cache_dir.mkdir(parents=True, exist_ok=True)
            path = config.cache_dir / "daily-vision-requests.json"
            today = date.today().isoformat()
            count = 0
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                if state.get("date") == today:
                    count = int(state.get("count", 0))
            except (FileNotFoundError, ValueError, OSError):
                pass
            if count >= config.daily_request_limit:
                raise QwenVisionReviewError(
                    f"Qwen vision daily request limit reached ({config.daily_request_limit})"
                )
            path.write_text(
                json.dumps({"date": today, "count": count + 1}),
                encoding="utf-8",
            )


_daily_budget = _DailyVisionBudget()
_vision_semaphore = asyncio.Semaphore(_positive_int("QWEN_VISION_MAX_CONCURRENCY", 1))


def create_review_session(max_calls: int) -> VisionReviewSession:
    return VisionReviewSession(
        config=QwenVisionConfig.from_env(),
        max_calls=max(1, max_calls),
    )


def _mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _read_cache(config: QwenVisionConfig, key: str) -> dict[str, Any] | None:
    if not config.cache_enabled:
        return None
    try:
        value = json.loads((config.cache_dir / f"{key}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _write_cache(config: QwenVisionConfig, key: str, value: dict[str, Any]) -> None:
    if not config.cache_enabled:
        return
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    destination = config.cache_dir / f"{key}.json"
    temporary = config.cache_dir / f".{key}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(destination)


async def _structured_call(
    session: VisionReviewSession,
    *,
    task: str,
    prompt: str,
    images: list[tuple[bytes, str]],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    identity = {
        "version": PROMPT_VERSION,
        "task": task,
        "model": session.config.model,
        "prompt": prompt,
        "images": [hashlib.sha256(content).hexdigest() for content, _mime in images],
    }
    key = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cached = _read_cache(session.config, key)
    if cached is not None:
        session.cache_hit_count += 1
        return cached
    if session.call_count >= session.max_calls:
        raise QwenVisionReviewError(
            f"Per-image vision call limit reached ({session.max_calls})"
        )
    content_items: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for content, mime_type in images:
        encoded = base64.b64encode(content).decode("ascii")
        content_items.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
            }
        )
    payload = {
        "model": session.config.model,
        "messages": [{"role": "user", "content": content_items}],
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
        "temperature": 0,
        "max_completion_tokens": 6000,
    }
    endpoint = session.config.base_url + "/chat/completions"
    try:
        async with _vision_semaphore:
            await _daily_budget.reserve(session.config)
            session.call_count += 1
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(session.config.timeout_seconds),
                transport=transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {session.config.api_key}"},
                    json=payload,
                )
        if response.is_error:
            try:
                upstream = response.json()
                message = str(upstream.get("message") or upstream.get("code") or "upstream error")
            except (ValueError, AttributeError):
                message = "upstream error"
            raise QwenVisionReviewError(
                f"Qwen vision request failed ({response.status_code}): {message[:300]}"
            )
        raw_content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        if not isinstance(parsed, dict):
            raise ValueError("structured output is not an object")
    except httpx.TimeoutException as exc:
        raise QwenVisionReviewError("Qwen vision request timed out") from exc
    except httpx.HTTPError as exc:
        raise QwenVisionReviewError(
            f"Qwen vision network error: {type(exc).__name__}"
        ) from exc
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise QwenVisionReviewError("Qwen vision returned invalid structured output") from exc
    _write_cache(session.config, key, parsed)
    return parsed


async def analyze_scene(
    session: VisionReviewSession,
    content: bytes,
    filename: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ScenePlan:
    prompt = """分析第一张原图，制定机械臂极简轮廓画的语义计划。只返回JSON对象：
{
  "main_subjects":[{"name":"主体名称","priority":0到1,"bbox":[x1,y1,x2,y2],"identity_features":["特征"]}],
  "relationships":["主体之间必须保留的姿态、遮挡或互动"],
  "required_structures":["缺失后将无法辨认的轮廓或结构"],
  "discardable_details":["纹理、阴影、装饰和背景杂物"]
}
bbox使用0到1归一化坐标。关注辨识度，不要描述颜色和审美。"""
    try:
        return ScenePlan.model_validate(
            await _structured_call(
                session,
                task="scene-plan",
                prompt=prompt,
                images=[(content, _mime_type(filename))],
                transport=transport,
            )
        )
    except ValidationError as exc:
        raise QwenVisionReviewError("Scene plan did not match the required schema") from exc


async def critique_lineart(
    session: VisionReviewSession,
    original: bytes,
    filename: str,
    lineart_png: bytes,
    scene_plan: ScenePlan,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LineartCritique:
    prompt = f"""第一张图是原图，第二张图是供机械臂绘制的黑白线稿。
绘画计划：{scene_plan.model_dump_json()}
检查主体类别、数量、姿态、互动和关键轮廓是否保留，同时查找碎线、平行重复线、纹理和错误断裂。
只返回JSON：
{{
  "acceptable":true或false,
  "recognizability":0到1,
  "missing_features":["缺失内容"],
  "dense_or_redundant_regions":["过密区域"],
  "correction_prompt":"若不合格，给图像编辑模型的精确中文修订指令；合格则为空字符串"
}}"""
    try:
        return LineartCritique.model_validate(
            await _structured_call(
                session,
                task="lineart-critique",
                prompt=prompt,
                images=[
                    (original, _mime_type(filename)),
                    (lineart_png, "image/png"),
                ],
                transport=transport,
            )
        )
    except ValidationError as exc:
        raise QwenVisionReviewError("Line-art critique did not match the required schema") from exc


def _candidate_atlas(
    strokes: list[AuditStroke],
    canvas_width: float,
    canvas_height: float,
) -> bytes:
    width = 1400
    height = max(500, int(round(width * canvas_height / max(canvas_width, 1e-9))))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for index, stroke in enumerate(strokes):
        hue = (index * 0.61803398875) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.9, 0.75)
        color = (int(red * 255), int(green * 255), int(blue * 255))
        points = [
            (
                int(round(point[0] / canvas_width * (width - 1))),
                int(round(point[1] / canvas_height * (height - 1))),
            )
            for point in stroke.points
        ]
        draw.line(points, fill=color, width=4, joint="curve")
        midpoint = points[len(points) // 2]
        label = str(stroke.source_order or stroke.importance_rank or index + 1)
        box = draw.textbbox(midpoint, label, font=font, stroke_width=2)
        draw.rectangle((box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1), fill="white")
        draw.text(midpoint, label, fill="black", font=font, stroke_width=1, stroke_fill="white")
    return _png_bytes(image)


async def _score_stroke_batch(
    session: VisionReviewSession,
    original: bytes,
    filename: str,
    strokes: list[AuditStroke],
    result: ProcessResponse,
    scene_plan: ScenePlan,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[StrokeReviewItem]:
    id_map = [
        {
            "number": stroke.source_order or stroke.importance_rank or index + 1,
            "id": stroke.id,
            "length_mm": stroke.length_mm,
        }
        for index, stroke in enumerate(strokes)
    ]
    prompt = f"""第一张图是原图，第二张是候选笔触审查图，每条彩色线旁有候选编号。
语义计划：{scene_plan.model_dump_json()}
编号到稳定ID：{json.dumps(id_map, ensure_ascii=False)}
逐条判断“删除它以后，原图主体、姿态或关系的辨识度下降多少”。不要因为线长就自动判重要。
role优先使用main_silhouette、pose、relationship、identity_feature、necessary_structure、environment、detail、texture或noise。
只返回JSON：{{"strokes":[{{"id":"稳定ID","role":"角色","semantic_importance":0到100,
"removal_damage":0到100,"confidence":0到100,"recommendation":"keep|uncertain|discard","reason":"简短原因"}}]}}。
必须使用给出的稳定ID，不得编造ID。"""
    atlas = _candidate_atlas(
        strokes,
        result.audit_document.canvas.width,
        result.audit_document.canvas.height,
    )
    try:
        parsed = StrokeReviewBatch.model_validate(
            await _structured_call(
                session,
                task="stroke-score",
                prompt=prompt,
                images=[
                    (original, _mime_type(filename)),
                    (atlas, "image/png"),
                ],
                transport=transport,
            )
        )
    except ValidationError as exc:
        raise QwenVisionReviewError("Stroke review did not match the required schema") from exc
    allowed = {stroke.id for stroke in strokes}
    return [item for item in parsed.strokes if item.id in allowed]


def _progressive_montage(result: ProcessResponse, counts: list[int]) -> bytes:
    canvas = result.audit_document.canvas
    columns = 3
    panel_width = 480
    panel_height = max(220, int(round(panel_width * canvas.height / canvas.width)))
    rows = math.ceil(len(counts) / columns)
    image = Image.new("RGB", (columns * panel_width, rows * (panel_height + 32)), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    kept = [stroke for stroke in result.audit_document.strokes if stroke.decision == Decision.KEEP]
    for panel_index, count in enumerate(counts):
        left = (panel_index % columns) * panel_width
        top = (panel_index // columns) * (panel_height + 32)
        draw.text((left + 8, top + 6), f"first {count} strokes", fill="black", font=font)
        for stroke in kept[:count]:
            points = [
                (
                    left + int(round(point[0] / canvas.width * (panel_width - 1))),
                    top + 30 + int(round(point[1] / canvas.height * (panel_height - 1))),
                )
                for point in stroke.points
            ]
            draw.line(points, fill="black", width=2, joint="curve")
    return _png_bytes(image)


async def _validate_progressive_order(
    session: VisionReviewSession,
    original: bytes,
    filename: str,
    result: ProcessResponse,
    scene_plan: ScenePlan,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProgressiveReview:
    kept_count = len(result.strokes_document.strokes)
    counts = sorted({count for count in (10, 20, 30, 50, kept_count) if 0 < count <= kept_count})
    if not counts:
        return ProgressiveReview()
    prompt = f"""第一张是原图，第二张按标题展示只画前N笔的渐进结果。
语义计划：{scene_plan.model_dump_json()}
候选面板笔数：{counts}
判断最早多少笔可以辨认主体、构图和主要动作。指出被排得太晚或不该靠前的稳定笔触ID；
若无法从图中可靠读出ID，相应数组留空。只返回JSON：
{{"recommended_min_strokes":整数,"earliest_recognizable_panel":整数或null,
"promote_ids":["稳定ID"],"demote_ids":["稳定ID"],"reason":"简短原因"}}"""
    try:
        return ProgressiveReview.model_validate(
            await _structured_call(
                session,
                task="progressive-review",
                prompt=prompt,
                images=[
                    (original, _mime_type(filename)),
                    (_progressive_montage(result, counts), "image/png"),
                ],
                transport=transport,
            )
        )
    except ValidationError as exc:
        raise QwenVisionReviewError("Progressive review did not match the required schema") from exc


async def review_process_result(
    content: bytes,
    filename: str,
    result: ProcessResponse,
    *,
    session: VisionReviewSession | None = None,
    scene_plan: ScenePlan | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProcessResponse:
    """Apply semantic scoring and progressive validation to a raster result."""

    parameters = result.audit_document.processing.parameters
    if not parameters.ai_semantic_review:
        return result
    try:
        session = session or create_review_session(parameters.max_cloud_review_calls)
        scene_plan = scene_plan or await analyze_scene(
            session, content, filename, transport=transport
        )
        candidates = [
            stroke for stroke in result.audit_document.strokes
            if stroke.decision != Decision.DISCARD
        ]
        candidates.sort(
            key=lambda stroke: (
                stroke.importance_rank if stroke.importance_rank is not None else 10**9,
                stroke.id,
            )
        )
        if parameters.ai_review_quality == "economy":
            batch_size, maximum_reviewed = 80, 80
        elif parameters.ai_review_quality == "fine":
            batch_size, maximum_reviewed = 40, 240
        else:
            batch_size, maximum_reviewed = 50, 150
        selected_candidates = candidates[:maximum_reviewed]
        reviewed_ids: set[str] = set()
        stroke_by_id = {stroke.id: stroke for stroke in result.audit_document.strokes}
        for start in range(0, len(selected_candidates), batch_size):
            if session.call_count >= session.max_calls:
                break
            batch = selected_candidates[start : start + batch_size]
            for item in await _score_stroke_batch(
                session,
                content,
                filename,
                batch,
                result,
                scene_plan,
                transport=transport,
            ):
                stroke = stroke_by_id[item.id]
                reviewed_ids.add(item.id)
                stroke.semantic_role = item.role[:64]
                stroke.model_reason = item.reason[:500] or None
                stroke.scores.semantic_importance = round(item.semantic_importance / 100.0, 6)
                stroke.scores.removal_damage = round(item.removal_damage / 100.0, 6)
                stroke.scores.model_confidence = round(item.confidence / 100.0, 6)
                recommendation = item.recommendation.lower()
                if recommendation == "discard" and item.confidence >= 70:
                    if "model_recommends_discard" not in stroke.reasons:
                        stroke.reasons.append("model_recommends_discard")
                    # Cloud judgment is recoverable: it may move an algorithmic
                    # keep to uncertain, but never permanently deletes geometry
                    # or overrides an explicit user choice.
                    if (
                        stroke.decision_source == "algorithm"
                        and stroke.decision == Decision.KEEP
                    ):
                        stroke.decision = Decision.UNCERTAIN
                elif recommendation == "keep" and item.confidence >= 70:
                    if "model_recommends_keep" not in stroke.reasons:
                        stroke.reasons.append("model_recommends_keep")
                    hard_physical_reasons = {
                        "pruned_spur",
                        "below_physical_feature_scale",
                        "pen_footprint_redundant",
                    }
                    if (
                        stroke.decision_source == "algorithm"
                        and stroke.decision != Decision.DISCARD
                        and hard_physical_reasons.isdisjoint(stroke.reasons)
                    ):
                        stroke.decision = Decision.KEEP
        result = refinalize_raster_result(result)

        progressive = ProgressiveReview()
        if (
            parameters.ai_review_quality != "economy"
            and session.call_count < session.max_calls
        ):
            progressive = await _validate_progressive_order(
                session,
                content,
                filename,
                result,
                scene_plan,
                transport=transport,
            )
            valid_ids = set(stroke_by_id)
            changed = False
            for stroke_id in progressive.promote_ids:
                if stroke_id in valid_ids:
                    stroke = stroke_by_id[stroke_id]
                    stroke.scores.semantic_importance = max(
                        stroke.scores.semantic_importance, 0.90
                    )
                    stroke.scores.removal_damage = max(stroke.scores.removal_damage, 0.90)
                    changed = True
            for stroke_id in progressive.demote_ids:
                if stroke_id in valid_ids:
                    stroke = stroke_by_id[stroke_id]
                    stroke.scores.semantic_importance *= 0.5
                    stroke.scores.removal_damage *= 0.5
                    changed = True
            if changed:
                result = refinalize_raster_result(result)
            if result.audit_document.selection_summary and progressive.recommended_min_strokes > 0:
                result.audit_document.selection_summary.recommended_min_strokes = min(
                    progressive.recommended_min_strokes,
                    len(candidates),
                )

        unreviewed = len(candidates) - len(reviewed_ids)
        status = "completed" if unreviewed == 0 else "partial"
        result.audit_document.semantic_review = SemanticReviewSummary(
            status=status,
            model=session.config.model,
            call_count=session.call_count,
            cache_hit_count=session.cache_hit_count,
            reviewed_stroke_count=len(reviewed_ids),
            unreviewed_stroke_count=max(0, unreviewed),
            main_subjects=[subject.name for subject in scene_plan.main_subjects],
            relationships=scene_plan.relationships,
            message=progressive.reason or None,
        )
        result.audit_document.warnings.append(
            f"semantic_review:{status}:{session.config.model}"
        )
        return result
    except (QwenVisionReviewError, QwenVisionConfigurationError) as exc:
        model = session.config.model if session is not None else None
        calls = session.call_count if session is not None else 0
        cache_hits = session.cache_hit_count if session is not None else 0
        result.audit_document.semantic_review = SemanticReviewSummary(
            status="fallback",
            model=model,
            call_count=calls,
            cache_hit_count=cache_hits,
            unreviewed_stroke_count=len(result.audit_document.strokes),
            message=str(exc)[:500],
        )
        result.audit_document.warnings.extend(
            [
                "semantic_review_fallback",
                f"semantic_review_error:{type(exc).__name__}",
            ]
        )
        return result
