"""Alibaba Cloud Model Studio Qwen image-edit to line-art bridge.

The cloud model only replaces the line-art extraction stage. Its PNG output is
decoded into the same mask/confidence pair used by local detectors, then the
existing classic skeleton, geometry, review and export pipeline remains in
charge. API credentials never enter request parameters, responses or logs.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from starlette.concurrency import run_in_threadpool

from .classic_provider import process_classic
from .line_map import decode_line_map_png
from .models import ProcessingParameters, ProcessResponse
from .vision_review_provider import (
    QwenVisionReviewError,
    ScenePlan,
    analyze_scene,
    create_review_session,
    critique_lineart,
    review_process_result,
)


QWEN_LINEART_PROMPT = """请把输入图片转换成“极简但高度可辨认的黑白轮廓简笔画”。

第一步先理解图片内容：

- 判断画面的主要主体是什么；
- 判断哪些物体、轮廓、姿态、空间关系和局部特征决定了这张图片的辨识度；
- 区分主要轮廓、必要结构线与无关细节；
- 不要把图片中的所有边缘都画出来。

绘制目标： 使用约 50 条以内的长而连续的黑色单线，以最少的线条准确概括原图。即使删除颜色和细节，观看者仍应能认出原图中的主要内容、构图和动作关系。

保留优先级：

1. 主体的整体剪影和外轮廓；
2. 主体的姿态、朝向、比例及主要组成部分；
3. 最能识别主体类别和身份的特征；
4. 多个主体之间的重要位置、遮挡和互动关系；
5. 对理解场景必不可少的少量环境线；
6. 必要的内部结构线。

根据内容自动选择重点：

- 人物：脸型、发型大轮廓、姿态、肢体关系和标志性服饰；
- 动物：身体轮廓、头部形状、耳朵、尾巴、四肢姿态和典型花纹边界；
- 车辆或产品：整体造型、关键部件和最有辨识度的结构比例；
- 建筑：建筑外形、屋顶、门窗的主要排列和透视关系；
- 植物：整体姿态、主干、主要枝叶轮廓，不逐片描绘叶脉；
- 风景：地平线、山体、水岸、主要建筑或树木，只保留决定场景的层次；
- 多主体场景：优先保留主要主体及其互动，次要物体高度概括；
- 抽象或特殊物体：保留最具辨识度的几何形状、连接关系和视觉节奏。

必须删除：

- 背景杂物和不影响理解的物体；
- 光影、明暗、渐变、反光和颜色边界；
- 材质纹理、草地纹理、墙面纹理、毛发细节、衣服褶皱；
- 过小的五官或零件；
- 重复轮廓、平行轮廓、阴影边缘；
- 素描排线、涂黑、灰色区域和装饰性笔触；
- 大量短线、碎线和孤立点。

线条规范：

- 纯白背景，纯黑等宽单线；
- 无颜色、无灰度、无阴影、无填充；
- 优先采用平滑、连续、较长的曲线；
- 每个结构尽量只用一条线表达；
- 能连接的轮廓合并成连续线；
- 不沿同一条边缘绘制两条平行线；
- 避免封闭的小区域和密集交叉；
- 不改变主体类别、数量、姿态和主要构图；
- 不添加输入图片中不存在的物体。

这是供机械臂绘制的路径草图。核心标准不是细节丰富，而是：
“只保留画面中最重要、最有信息量的线，让寥寥几笔仍然能够看出原图画了什么。”"""

QWEN_NEGATIVE_PROMPT = (
    "彩色，灰色背景，阴影，渐变，明暗边界，反光，材质，纹理，网点，照片效果，"
    "衣服花纹，发丝，过多衣褶，装饰细节，文字，水印，噪点，密集线，排线，交叉排线，"
    "平行线，双重轮廓，极其接近的线条，重复线，短碎线，填充线，黑色填充，封闭小黑块"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class QwenCloudError(RuntimeError):
    """Base exception carrying the HTTP status exposed by the main API."""

    status_code = 502


class QwenCloudConfigurationError(QwenCloudError):
    status_code = 503


class QwenCloudLimitError(QwenCloudError):
    status_code = 429


class QwenCloudTimeoutError(QwenCloudError):
    status_code = 504


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise QwenCloudConfigurationError(f"{name} must be a positive integer") from exc


def _positive_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError as exc:
        raise QwenCloudConfigurationError(f"{name} must be a positive number") from exc


def _default_cache_dir() -> Path:
    configured = os.getenv("QWEN_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "StrokeReview" / "qwen-cache"
    return Path.home() / ".cache" / "stroke-review" / "qwen-cloud"


@dataclass(frozen=True)
class QwenCloudConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    daily_request_limit: int
    max_output_bytes: int
    cache_enabled: bool
    cache_dir: Path
    seed: int

    @classmethod
    def from_env(cls) -> "QwenCloudConfig":
        enabled = os.getenv("QWEN_CLOUD_ENABLED", "true").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            raise QwenCloudConfigurationError("Qwen API mode is disabled by QWEN_CLOUD_ENABLED")
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        base_url = os.getenv("QWEN_DASHSCOPE_BASE_URL", "").strip().rstrip("/")
        model = os.getenv("QWEN_IMAGE_MODEL", "").strip()
        missing = [
            name
            for name, value in (
                ("DASHSCOPE_API_KEY", api_key),
                ("QWEN_DASHSCOPE_BASE_URL", base_url),
                ("QWEN_IMAGE_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise QwenCloudConfigurationError(
                "Qwen API mode is not configured; missing " + ", ".join(missing)
            )
        _validate_base_url(base_url)
        try:
            seed = int(os.getenv("QWEN_IMAGE_SEED", "20260902"))
        except ValueError as exc:
            raise QwenCloudConfigurationError("QWEN_IMAGE_SEED must be an integer") from exc
        if not 0 <= seed <= 2_147_483_647:
            raise QwenCloudConfigurationError("QWEN_IMAGE_SEED must be between 0 and 2147483647")
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=_positive_float("QWEN_CLOUD_TIMEOUT_SECONDS", 600),
            daily_request_limit=_positive_int("QWEN_DAILY_REQUEST_LIMIT", 20),
            max_output_bytes=_positive_int("QWEN_MAX_OUTPUT_MB", 20) * 1024 * 1024,
            cache_enabled=os.getenv("QWEN_CACHE_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            cache_dir=_default_cache_dir(),
            seed=seed,
        )


def qwen_cloud_availability() -> tuple[bool, str | None]:
    try:
        config = QwenCloudConfig.from_env()
    except QwenCloudConfigurationError as exc:
        return False, str(exc)
    return True, f"已配置 {config.model}；成功生成可能消耗免费额度或产生费用"


def _validate_base_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host.endswith(".maas.aliyuncs.com")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith("/api/v1")
    ):
        raise QwenCloudConfigurationError(
            "QWEN_DASHSCOPE_BASE_URL must be an HTTPS Model Studio /api/v1 workspace URL"
        )


def _validate_result_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith((".aliyuncs.com", ".aliyun.com")):
        raise QwenCloudError("Qwen returned an untrusted image download URL")


def _mime_type(filename: str, content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in {"image/png", "image/jpeg"}:
        return normalized
    suffix = Path(filename).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    raise QwenCloudError("Qwen API mode only accepts PNG and JPEG input")


def _cache_key(
    content: bytes,
    mime_type: str,
    config: QwenCloudConfig,
    *,
    prompt: str = QWEN_LINEART_PROMPT,
    reference_png: bytes | None = None,
) -> str:
    identity = {
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "mime_type": mime_type,
        "model": config.model,
        "prompt": prompt,
        "negative_prompt": QWEN_NEGATIVE_PROMPT,
        "seed": config.seed,
        "prompt_extend": False,
        "watermark": False,
        "reference_sha256": (
            hashlib.sha256(reference_png).hexdigest()
            if reference_png is not None
            else None
        ),
    }
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_cache(config: QwenCloudConfig, key: str) -> bytes | None:
    if not config.cache_enabled:
        return None
    path = config.cache_dir / f"{key}.png"
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return None
    if not content.startswith(PNG_SIGNATURE):
        return None
    return content


def _write_cache(config: QwenCloudConfig, key: str, content: bytes) -> None:
    if not config.cache_enabled:
        return
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    destination = config.cache_dir / f"{key}.png"
    temporary = config.cache_dir / f".{key}.{os.getpid()}.tmp"
    temporary.write_bytes(content)
    temporary.replace(destination)


class _DailyRequestBudget:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def reserve(self, config: QwenCloudConfig) -> None:
        async with self._lock:
            config.cache_dir.mkdir(parents=True, exist_ok=True)
            path = config.cache_dir / "daily-requests.json"
            today = date.today().isoformat()
            state: dict[str, Any] = {"date": today, "count": 0}
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if loaded.get("date") == today:
                    state = loaded
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass
            count = int(state.get("count", 0))
            if count >= config.daily_request_limit:
                raise QwenCloudLimitError(
                    f"Qwen daily request limit reached ({config.daily_request_limit}); cached results remain available"
                )
            path.write_text(
                json.dumps({"date": today, "count": count + 1}), encoding="utf-8"
            )

    async def release(self, config: QwenCloudConfig) -> None:
        async with self._lock:
            path = config.cache_dir / "daily-requests.json"
            today = date.today().isoformat()
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return
            if state.get("date") == today and int(state.get("count", 0)) > 0:
                state["count"] = int(state["count"]) - 1
                path.write_text(json.dumps(state), encoding="utf-8")


_daily_budget = _DailyRequestBudget()
_cloud_semaphore = asyncio.Semaphore(_positive_int("QWEN_MAX_CONCURRENCY", 1))


async def _download_result(
    client: httpx.AsyncClient, url: str, max_output_bytes: int
) -> bytes:
    _validate_result_url(url)
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > max_output_bytes:
            raise QwenCloudError("Qwen output image exceeds the configured size limit")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > max_output_bytes:
                raise QwenCloudError("Qwen output image exceeds the configured size limit")
            chunks.append(chunk)
    content = b"".join(chunks)
    if not content.startswith(PNG_SIGNATURE):
        raise QwenCloudError("Qwen returned an invalid PNG image")
    return content


async def _request_qwen_lineart(
    content: bytes,
    mime_type: str,
    config: QwenCloudConfig,
    *,
    prompt: str = QWEN_LINEART_PROMPT,
    reference_png: bytes | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    encoded = base64.b64encode(content).decode("ascii")
    message_content: list[dict[str, str]] = [
        {"image": f"data:{mime_type};base64,{encoded}"},
    ]
    if reference_png is not None:
        reference_encoded = base64.b64encode(reference_png).decode("ascii")
        message_content.append(
            {"image": f"data:image/png;base64,{reference_encoded}"}
        )
    message_content.append({"text": prompt})
    payload = {
        "model": config.model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": message_content,
                }
            ]
        },
        "parameters": {
            "n": 1,
            "watermark": False,
            "prompt_extend": False,
            "negative_prompt": QWEN_NEGATIVE_PROMPT,
            "seed": config.seed,
        },
    }
    endpoint = config.base_url + "/services/aigc/multimodal-generation/generation"
    timeout = httpx.Timeout(config.timeout_seconds)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            if response.is_error:
                try:
                    error = response.json()
                    message = str(error.get("message") or error.get("code") or "upstream error")
                except (ValueError, AttributeError):
                    message = "upstream error"
                raise QwenCloudError(
                    f"Qwen API request failed ({response.status_code}): {message[:300]}"
                )
            result = response.json()
            image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
            if not isinstance(image_url, str) or not image_url:
                raise KeyError("image")
            return await _download_result(client, image_url, config.max_output_bytes)
    except httpx.TimeoutException as exc:
        raise QwenCloudTimeoutError("Qwen API request timed out") from exc
    except httpx.HTTPError as exc:
        raise QwenCloudError(f"Qwen API network error: {type(exc).__name__}") from exc
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, QwenCloudError):
            raise
        raise QwenCloudError("Qwen API returned an unexpected response") from exc


async def process_qwen_cloud(
    content: bytes,
    filename: str,
    content_type: str | None,
    parameters: ProcessingParameters,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProcessResponse:
    """Generate cloud line art, then reuse the classic geometry pipeline."""

    config = QwenCloudConfig.from_env()
    mime_type = _mime_type(filename, content_type)
    session = None
    scene_plan: ScenePlan | None = None
    semantic_warnings: list[str] = []
    generation_prompt = QWEN_LINEART_PROMPT
    if parameters.ai_semantic_review:
        try:
            session = create_review_session(parameters.max_cloud_review_calls)
            scene_plan = await analyze_scene(
                session,
                content,
                filename,
                transport=transport,
            )
            generation_prompt += (
                "\n\n必须遵守以下原图语义绘画计划，只保留决定辨识度的内容：\n"
                + scene_plan.model_dump_json()
            )
        except QwenVisionReviewError as exc:
            semantic_warnings.extend(
                [
                    "semantic_scene_plan_fallback",
                    f"semantic_scene_plan_error:{type(exc).__name__}",
                ]
            )
            session = None
            scene_plan = None

    key = _cache_key(
        content,
        mime_type,
        config,
        prompt=generation_prompt,
    )
    generated = _read_cache(config, key)
    cache_status = "hit"
    if generated is None:
        cache_status = "miss"
        async with _cloud_semaphore:
            # Recheck after waiting: another default-concurrency request may have filled it.
            generated = _read_cache(config, key)
            if generated is not None:
                cache_status = "hit-after-wait"
            else:
                await _daily_budget.reserve(config)
                try:
                    generated = await _request_qwen_lineart(
                        content,
                        mime_type,
                        config,
                        prompt=generation_prompt,
                        transport=transport,
                    )
                except Exception:
                    await _daily_budget.release(config)
                    raise
                _write_cache(config, key, generated)

    critique = None
    if (
        session is not None
        and scene_plan is not None
        and parameters.ai_review_quality != "economy"
        and session.call_count < session.max_calls
    ):
        try:
            critique = await critique_lineart(
                session,
                content,
                filename,
                generated,
                scene_plan,
                transport=transport,
            )
            if (
                not critique.acceptable
                and critique.correction_prompt.strip()
                and parameters.ai_review_quality in {"standard", "fine"}
            ):
                revision_prompt = (
                    QWEN_LINEART_PROMPT
                    + "\n\n第一张是原图，第二张是待修订线稿。"
                    + "只修正下列问题，保持已经正确的主体、数量、姿态和构图：\n"
                    + critique.correction_prompt.strip()
                )
                revision_key = _cache_key(
                    content,
                    mime_type,
                    config,
                    prompt=revision_prompt,
                    reference_png=generated,
                )
                revised = _read_cache(config, revision_key)
                if revised is None:
                    async with _cloud_semaphore:
                        revised = _read_cache(config, revision_key)
                        if revised is None:
                            await _daily_budget.reserve(config)
                            try:
                                revised = await _request_qwen_lineart(
                                    content,
                                    mime_type,
                                    config,
                                    prompt=revision_prompt,
                                    reference_png=generated,
                                    transport=transport,
                                )
                            except Exception:
                                await _daily_budget.release(config)
                                raise
                            _write_cache(config, revision_key, revised)
                generated = revised
                cache_status += "+semantic-revision"
        except (QwenVisionReviewError, QwenCloudError) as exc:
            semantic_warnings.extend(
                [
                    "semantic_lineart_critique_fallback",
                    f"semantic_lineart_critique_error:{type(exc).__name__}",
                ]
            )

    output_hash = hashlib.sha256(generated).hexdigest()
    line_mask, confidence = decode_line_map_png(generated, source="Qwen")
    result = await run_in_threadpool(
        partial(
            process_classic,
            content,
            filename,
            parameters,
            line_mask=line_mask,
            confidence_map=confidence,
            actual_provider="qwen-cloud",
            identity_salt=f"{config.model}:{output_hash}",
        )
    )
    result.audit_document.warnings.extend(
        [
            f"cloud_model:{config.model}",
            f"cloud_output_sha256:{output_hash}",
            f"cloud_cache:{cache_status}",
            "cloud_generation_is_probabilistic",
            *semantic_warnings,
        ]
    )
    if parameters.ai_semantic_review:
        result = await review_process_result(
            content,
            filename,
            result,
            session=session,
            scene_plan=scene_plan,
            transport=transport,
        )
        if critique is not None:
            result.audit_document.warnings.append(
                f"lineart_recognizability:{critique.recognizability:.3f}"
            )
    return result
