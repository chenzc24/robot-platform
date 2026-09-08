from __future__ import annotations

import hashlib
import json
import math
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .canvas_layout import fit_canvas_layout
from .models import (
    AuditDocument,
    AuditProcessing,
    AuditScores,
    AuditStroke,
    CanvasSpec,
    Decision,
    ProcessingParameters,
    ProcessResponse,
    DrawingStrokeGeometry,
    StrokesDocument,
)


def _source_dimensions(content: bytes, content_type: str | None) -> tuple[int, int]:
    if content_type == "image/svg+xml" or b"<svg" in content[:2048].lower():
        return 1000, 1000
    try:
        with Image.open(BytesIO(content)) as image:
            return image.size
    except (UnidentifiedImageError, OSError):
        return 1000, 1000


def _length_mm(points: list[tuple[float, float]], canvas: CanvasSpec) -> float:
    scale = canvas.target_width_mm / canvas.width
    return round(
        sum(math.dist(points[index - 1], points[index]) for index in range(1, len(points)))
        * scale,
        4,
    )


def _stroke_id(source_hash: str, points: list[tuple[float, float]], closed: bool) -> str:
    canonical = json.dumps([points, closed], separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(f"{source_hash}:{canonical}".encode()).hexdigest()[:12]
    return f"stroke_{digest}"


def process_mock(
    content: bytes,
    filename: str,
    content_type: str | None,
    parameters: ProcessingParameters,
) -> ProcessResponse:
    source_hash = hashlib.sha256(content).hexdigest()
    source_width, source_height = _source_dimensions(content, content_type)
    physical_layout = fit_canvas_layout(
        source_width,
        source_height,
        parameters,
        source_width=source_width,
        source_height=source_height,
    )
    canvas = physical_layout.canvas

    # A deterministic placeholder result. Real geometry providers replace only this layer.
    jitter = (int(source_hash[:2], 16) / 255 - 0.5) * 0.04
    def fitted(x_ratio: float, y_ratio: float) -> tuple[float, float]:
        return physical_layout.normalize_source_point(
            source_width * x_ratio,
            source_height * y_ratio,
        )

    candidates: list[tuple[list[tuple[float, float]], bool, Decision, float, list[str], float]] = [
        ([fitted(0.12, 0.24), fitted(0.5, 0.12), fitted(0.88, 0.24)], False, Decision.KEEP, 0.96, [], 0.08),
        ([fitted(0.12, 0.5 + jitter), fitted(0.36, 0.42), fitted(0.64, 0.58), fitted(0.88, 0.5 + jitter)], False, Decision.UNCERTAIN, 0.61, ["mock_uncertain"], 0.52),
        ([fitted(0.46, 0.76), fitted(0.54, 0.76)], False, Decision.DISCARD, 0.22, ["mock_too_short_isolated"], 0.91),
    ]

    audit_strokes: list[AuditStroke] = []
    for points, closed, decision, confidence, reasons, risk in candidates:
        rounded_points = [(round(x, 6), round(y, 6)) for x, y in points]
        audit_strokes.append(
            AuditStroke(
                id=_stroke_id(source_hash, rounded_points, closed),
                points=rounded_points,
                closed=closed,
                confidence=confidence,
                decision=decision,
                reasons=reasons,
                scores=AuditScores(risk=risk, line_confidence=confidence),
                length_mm=_length_mm(rounded_points, canvas),
            )
        )

    kept_strokes = [stroke for stroke in audit_strokes if stroke.decision == Decision.KEEP]
    lean_strokes = [
        DrawingStrokeGeometry(
            id=stroke.id,
            order=order,
            points=stroke.points,
            closed=stroke.closed,
        )
        for order, stroke in enumerate(kept_strokes, start=1)
    ]
    strokes_document = StrokesDocument(canvas=canvas, strokes=lean_strokes)
    audit_document = AuditDocument(
        canvas=canvas,
        processing=AuditProcessing(
            requested_provider=parameters.provider,
            actual_provider="mock",
            parameters=parameters,
            source_sha256=source_hash,
        ),
        strokes=audit_strokes,
        warnings=["mock_provider_output"],
    )
    processing_fingerprint = hashlib.sha256(
        (source_hash + parameters.model_dump_json()).encode()
    ).hexdigest()[:12]
    return ProcessResponse(
        processing_id=f"process_{processing_fingerprint}",
        filename=filename,
        strokes_document=strokes_document,
        audit_document=audit_document,
    )
