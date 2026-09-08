"""帮助自定义算法把候选笔触组装成项目统一、确定性的输出格式。"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from ..canvas_layout import fit_canvas_layout
from ..models import (
    AuditDocument,
    AuditProcessing,
    AuditScores,
    AuditStroke,
    CanvasSpec,
    Decision,
    DiagnosticImages,
    ProcessResponse,
    DrawingStrokeGeometry,
    StrokesDocument,
)
from .base import PipelineRequest


@dataclass(frozen=True)
class PipelineStroke:
    """自定义完整管线返回的单条候选笔触。

    points 使用来源作品坐标系：左上为原点、来源最长边归一化为 1。
    builder 会把它们保持比例、居中映射到最终物理画布。
    decision/reasons/risk 会进入 audit.json，只有 keep 会进入 strokes.json。
    """

    points: list[tuple[float, float]]
    closed: bool = False
    confidence: float = 1.0
    decision: Decision = Decision.KEEP
    reasons: list[str] = field(default_factory=list)
    risk: float = 0.0
    length_mm: float | None = None
    source_ref: str | None = None
    source_order: int | None = None


def _length(points: list[tuple[float, float]]) -> float:
    """计算归一化折线长度；相邻采样点之间按欧氏距离累加。"""

    return sum(math.dist(points[index - 1], points[index]) for index in range(1, len(points)))


def build_pipeline_response(
    request: PipelineRequest,
    *,
    actual_provider: str,
    source_width: int,
    source_height: int,
    strokes: list[PipelineStroke],
    diagnostics: DiagnosticImages | None = None,
    warnings: list[str] | None = None,
) -> ProcessResponse:
    """为自定义栅格管线构造确定性的正式文档和审核文档。

    这里集中完成边界校验、毫米长度换算、稳定 ID、keep 过滤和 processing ID，
    让替换算法只关注如何得到候选几何，不必重复实现数据契约。
    """

    if source_width <= 0 or source_height <= 0:
        raise ValueError("Custom pipeline source dimensions must be positive")
    source_longest = max(source_width, source_height)
    physical_layout = fit_canvas_layout(
        source_width,
        source_height,
        request.parameters,
        source_width=source_width,
        source_height=source_height,
    )
    canvas = physical_layout.canvas
    source_hash = hashlib.sha256(request.content).hexdigest()
    audit_strokes: list[AuditStroke] = []
    for order, candidate in enumerate(strokes):
        if len(candidate.points) < 2:
            raise ValueError("Custom pipeline strokes must contain at least two points")
        source_points = [(round(x, 6), round(y, 6)) for x, y in candidate.points]
        if any(
            not math.isfinite(x)
            or not math.isfinite(y)
            or x < 0
            or y < 0
            or x > source_width / source_longest
            or y > source_height / source_longest
            for x, y in source_points
        ):
            raise ValueError("Custom pipeline points must be finite and inside the normalized source bounds")
        points = [
            tuple(round(value, 6) for value in physical_layout.normalize_source_point(
                x * source_longest,
                y * source_longest,
            ))
            for x, y in source_points
        ]
        # 输入哈希、算法名、顺序和几何共同生成稳定 ID。
        identity = json.dumps([order, points, candidate.closed], separators=(",", ":"))
        stroke_id = "stroke_" + hashlib.sha256(
            f"{source_hash}:{actual_provider}:{identity}".encode()
        ).hexdigest()[:12]
        normalized_length = _length(source_points)
        length_mm = candidate.length_mm
        if length_mm is None:
            length_mm = (
                normalized_length
                * source_longest
                * physical_layout.millimeters_per_source_unit
            )
        audit_strokes.append(
            AuditStroke(
                id=stroke_id,
                source="raster",
                source_ref=candidate.source_ref,
                source_order=candidate.source_order if candidate.source_order is not None else order,
                points=points,
                closed=candidate.closed,
                confidence=candidate.confidence,
                decision=candidate.decision,
                reasons=candidate.reasons,
                scores=AuditScores(risk=candidate.risk, line_confidence=candidate.confidence),
                length_mm=round(length_mm, 4),
            )
        )
    # 正式下游契约只保留 keep；其余候选仍完整保存在审核文档。
    kept_strokes = [stroke for stroke in audit_strokes if stroke.decision == Decision.KEEP]
    official = [
        DrawingStrokeGeometry(
            id=stroke.id,
            order=order,
            points=stroke.points,
            closed=stroke.closed,
        )
        for order, stroke in enumerate(kept_strokes, start=1)
    ]
    fingerprint = hashlib.sha256(
        (source_hash + request.parameters.model_dump_json() + actual_provider).encode()
    ).hexdigest()[:12]
    return ProcessResponse(
        processing_id=f"process_{fingerprint}",
        filename=request.filename,
        strokes_document=StrokesDocument(canvas=canvas, strokes=official),
        audit_document=AuditDocument(
            canvas=canvas,
            processing=AuditProcessing(
                requested_provider=request.parameters.provider,
                actual_provider=actual_provider,
                parameters=request.parameters,
                source_sha256=source_hash,
            ),
            strokes=audit_strokes,
            warnings=warnings or [],
        ),
        diagnostics=diagnostics,
    )
