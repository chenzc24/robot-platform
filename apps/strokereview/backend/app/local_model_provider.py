"""后端与本地深度线稿模型服务之间的桥接层。

Lineart、PiDiNet、HED 只负责把 RGB 图片变成灰度线稿图。本文件把模型
输出转换为统一的二值 mask/置信度，然后交给 classic_provider 继续完成
骨架化、分支组合、平滑、审核评分和 Stroke 数据输出。
"""

from __future__ import annotations

import base64
import binascii
import os
from functools import partial

import httpx
from starlette.concurrency import run_in_threadpool

from .classic_provider import process_classic
from .line_map import decode_line_map_png
from .models import ProcessingParameters, ProcessResponse


def _detector_resolution(detail_level: int) -> int:
    """把网页的 0~100 细节等级换算成模型推理分辨率（256~1024）。

    对齐到 64 的倍数可兼容常见卷积模型；分辨率越大通常细节更多、速度越慢。
    """

    raw = 256 + detail_level / 100 * 768
    return max(256, min(1024, round(raw / 64) * 64))


async def process_local_model(
    content: bytes,
    filename: str,
    content_type: str | None,
    parameters: ProcessingParameters,
) -> ProcessResponse:
    """请求本地 CPU 模型提取线稿，再复用经典骨架到笔触流程。

    模型服务不可用、权重加载失败或返回无效数据时，会降级到纯经典流程；
    降级原因会写入 audit warnings，不会静默伪装成模型成功。
    """

    service_url = os.getenv("LINEART_LOCAL_SERVICE_URL", "http://127.0.0.1:8010").rstrip("/")
    timeout = float(os.getenv("LINEART_LOCAL_TIMEOUT_SECONDS", "300"))
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(
                f"{service_url}/v1/extract",
                files={"file": (filename, content, content_type or "application/octet-stream")},
                data={
                    "model": parameters.provider,
                    "detect_resolution": str(_detector_resolution(parameters.detail_level)),
                },
            )
        response.raise_for_status()
        payload = response.json()
        line_mask, confidence = decode_line_map_png(
            base64.b64decode(payload["line_png_base64"], validate=True),
            source="The local model",
        )
        # 模型只提供 line_mask/confidence；后续几何处理仍走统一实现。
        result = await run_in_threadpool(
            partial(
                process_classic,
                content,
                filename,
                parameters,
                line_mask=line_mask,
                confidence_map=confidence,
                actual_provider=f"local-{parameters.provider}",
            )
        )
        result.audit_document.warnings.append(
            f"model_repository:{payload.get('model_repository', 'unknown')}"
        )
        result.audit_document.warnings.append(
            f"detector_implementation:{payload.get('detector_implementation', 'unknown')}"
        )
        result.audit_document.warnings.append("model_weights_license_unverified")
        return result
    except (httpx.HTTPError, ValueError, KeyError, binascii.Error) as exc:
        # 保证没有模型服务时网站仍可用，并在 audit.json 中记录真实路径。
        fallback = await run_in_threadpool(
            partial(
                process_classic,
                content,
                filename,
                parameters,
                actual_provider="classic-fallback",
            )
        )
        fallback.audit_document.warnings.extend(
            [
                f"local_model_fallback:{parameters.provider}",
                f"local_model_error:{type(exc).__name__}",
            ]
        )
        return fallback
