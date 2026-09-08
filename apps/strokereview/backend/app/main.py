"""FastAPI 入口：接收图片和参数，并把请求交给可替换算法管线。

本文件只负责上传校验、访问保护和路由，不包含图像算法本身。
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import (
    AuditDocument,
    Capabilities,
    ProcessingParameters,
    ProviderOption,
    StrokesDocument,
)
from .pipelines import PipelineRequest, UnknownPipelineError, build_pipeline_registry
from .qwen_cloud_provider import QwenCloudError


MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/svg+xml"}
pipeline_registry = build_pipeline_registry()


def _valid_file(content: bytes, content_type: str | None, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".svg":
        return b"<svg" in content[:4096].lower()
    return content_type in ACCEPTED_TYPES


def _basic_auth_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": 'Basic realm="Stroke Review"'},
    )


app = FastAPI(title="Stroke Review API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


@app.middleware("http")
async def optional_basic_auth(request: Request, call_next):
    if request.url.path == "/api/health":
        return await call_next(request)
    username = os.getenv("APP_ACCESS_USERNAME")
    password = os.getenv("APP_ACCESS_PASSWORD")
    if bool(username) != bool(password):
        return JSONResponse(
            status_code=503,
            content={"detail": "Both APP_ACCESS_USERNAME and APP_ACCESS_PASSWORD must be set"},
        )
    if not username:
        return await call_next(request)
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Basic "):
        return _basic_auth_response()
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        supplied_username, supplied_password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return _basic_auth_response()
    if not (
        hmac.compare_digest(supplied_username, username)
        and hmac.compare_digest(supplied_password, password)
    ):
        return _basic_auth_response()
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": "classic"}


@app.get("/api/v1/capabilities", response_model=Capabilities)
def capabilities() -> Capabilities:
    selectable = pipeline_registry.selectable_pipelines()
    options: list[ProviderOption] = []
    for pipeline in selectable:
        availability = getattr(pipeline, "availability", None)
        available, availability_reason = (
            availability() if callable(availability) else (True, None)
        )
        options.append(
            ProviderOption(
                id=pipeline.metadata.id,
                label=pipeline.metadata.label,
                description=pipeline.metadata.description,
                implementation=pipeline.metadata.implementation,
                requires_model_service=pipeline.metadata.requires_model_service,
                is_cloud=pipeline.metadata.is_cloud,
                available=available,
                availability_reason=availability_reason,
                usage_notice=pipeline.metadata.usage_notice,
            )
        )
    return Capabilities(
        providers=[pipeline.metadata.id for pipeline in selectable],
        provider_options=options,
        accepted_types=sorted(ACCEPTED_TYPES),
        max_upload_mb=MAX_UPLOAD_MB,
    )


@app.get("/api/v1/schema/strokes.json")
def strokes_schema() -> dict:
    return StrokesDocument.model_json_schema()


@app.get("/api/v1/schema/audit.json")
def audit_schema() -> dict:
    return AuditDocument.model_json_schema()


@app.post("/api/v1/process")
async def process(
    file: UploadFile = File(...),
    parameters: str = Form("{}"),
):
    """统一处理 PNG/JPG/SVG 上传，返回正式笔触、审核数据和诊断图。"""

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB")
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")
    if not _valid_file(content, file.content_type, file.filename or ""):
        raise HTTPException(status_code=415, detail="Only valid PNG, JPEG, and SVG files are accepted")
    try:
        parsed_parameters = ProcessingParameters.model_validate(json.loads(parameters))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid processing parameters: {exc}") from exc
    # 输入类型和用户参数被包装成与 FastAPI 无关的 PipelineRequest，方便
    # 完整算法管线独立测试或替换。
    is_svg = file.content_type == "image/svg+xml" or (file.filename or "").lower().endswith(".svg")
    request = PipelineRequest(
        content=content,
        filename=file.filename or ("upload.svg" if is_svg else "upload"),
        content_type=file.content_type,
        input_kind="svg" if is_svg else "raster",
        parameters=parsed_parameters,
    )
    try:
        # 注册表负责选择 classic、模型管线或 SVG 管线。
        return await pipeline_registry.process(request)
    except QwenCloudError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (UnknownPipelineError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
