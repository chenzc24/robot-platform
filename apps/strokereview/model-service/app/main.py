"""本地 CPU 线稿模型服务的 HTTP 入口。

此服务只做“图片 -> 灰度线稿图”，不直接生成 Stroke。主后端收到线稿后
还会执行骨架化、图结构组合、评分和坐标归一化。
"""

from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .detectors import UnknownDetectorError, build_detector_registry, resolve_model_repository


MODEL_REPOSITORY = resolve_model_repository()
MAX_UPLOAD_BYTES = int(os.getenv("MODEL_MAX_UPLOAD_MB", "25")) * 1024 * 1024
detector_registry = build_detector_registry()

app = FastAPI(title="Local Line-Art Model Service", version="0.2.0")


class ExtractResponse(BaseModel):
    model: str
    model_repository: str
    detector_implementation: str
    line_png_base64: str
    device: Literal["cpu"] = "cpu"


@app.get("/api/health")
def health() -> dict:
    detectors = detector_registry.values()
    return {
        "status": "ok",
        "device": "cpu",
        "models": detector_registry.ids(),
        "loaded_models": [detector.metadata.id for detector in detectors if detector.loaded],
        "model_repository": MODEL_REPOSITORY,
        "detectors": [
            {
                "id": detector.metadata.id,
                "label": detector.metadata.label,
                "repository": detector.metadata.repository,
                "implementation": detector.metadata.implementation,
                "loaded": detector.loaded,
            }
            for detector in detectors
        ],
    }


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract(
    file: UploadFile = File(...),
    model: str = Form(..., pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$"),
    detect_resolution: int = Form(512, ge=256, le=2048),
) -> ExtractResponse:
    """校验并解码图片，调用所选适配器，返回 base64 PNG 线稿图。"""

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large")
    try:
        with Image.open(BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Image could not be decoded") from exc
    try:
        # 通过注册表按 ID 获取实现，API 本身不绑定 Lineart/PiDiNet/HED。
        detector = detector_registry.get(model)
    except UnknownDetectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        # 模型权重在第一次 predict 时延迟加载，后续请求复用内存中的模型。
        # Weight loading and CPU inference are synchronous and may take a long
        # time. Keep them off the ASGI event loop so /api/health and error
        # reporting remain responsive during inference.
        output = await run_in_threadpool(detector.predict, image, detect_resolution)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    encoded = BytesIO()
    output.save(encoded, format="PNG", optimize=True)
    return ExtractResponse(
        model=model,
        model_repository=detector.metadata.repository,
        detector_implementation=detector.metadata.implementation,
        line_png_base64=base64.b64encode(encoded.getvalue()).decode("ascii"),
    )
