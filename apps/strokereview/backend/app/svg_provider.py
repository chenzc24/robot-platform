"""SVG 矢量作品转统一 Stroke 数据的处理流程。

与 PNG/JPG 不同，SVG 已经包含路径语义，因此不应先栅格化再骨架化。
这里用 defusedxml 安全读取 XML，用 svgelements 解析形状、path 和嵌套
transform，再对直线、Bezier 和圆弧自适应采样，最后输出同一数据契约。
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from io import BytesIO
from xml.etree import ElementTree

import cv2
import numpy as np
from defusedxml import ElementTree as SafeElementTree
from svgelements import Close, Move, Path, SVG, Shape

from .canvas_layout import fit_canvas_layout
from .models import (
    AuditDocument,
    AuditProcessing,
    AuditScores,
    AuditStroke,
    CanvasSpec,
    Decision,
    DiagnosticImages,
    ProcessingParameters,
    ProcessResponse,
    DrawingStrokeGeometry,
    StrokesDocument,
)


def _point(value) -> np.ndarray:
    """把 svgelements 的坐标对象转换为统一的 NumPy x/y 向量。"""

    return np.array([float(value.x), float(value.y)], dtype=np.float64)


def _distance_to_chord(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    """计算采样点到弦线段的距离，用于判断曲线是否需要继续细分。"""

    chord = end - start
    denominator = float(np.dot(chord, chord))
    if denominator == 0:
        return float(np.linalg.norm(point - start))
    projection = np.clip(float(np.dot(point - start, chord)) / denominator, 0, 1)
    return float(np.linalg.norm(point - (start + projection * chord)))


def _sample_segment(segment, tolerance: float, start_t: float = 0, end_t: float = 1, depth: int = 0) -> list[np.ndarray]:
    """递归、自适应地把任意 SVG 曲线段采样成折线。

    取区间内 1/4、1/2、3/4 三点检查与弦的偏差；偏差大于 tolerance
    就继续二分。最大深度 12 防止异常路径导致无限递归。
    """

    start = _point(segment.point(start_t))
    end = _point(segment.point(end_t))
    middle_t = (start_t + end_t) / 2
    checkpoints = [
        _point(segment.point(start_t + (end_t - start_t) * fraction))
        for fraction in (0.25, 0.5, 0.75)
    ]
    if depth >= 12 or max(_distance_to_chord(point, start, end) for point in checkpoints) <= tolerance:
        return [end]
    return (
        _sample_segment(segment, tolerance, start_t, middle_t, depth + 1)
        + _sample_segment(segment, tolerance, middle_t, end_t, depth + 1)
    )


def _paint_visible(paint) -> bool:
    """判断 stroke/fill 是否实际可见，排除 none、transparent 和零透明度。"""

    if paint is None or str(paint).lower() in {"none", "transparent"}:
        return False
    return getattr(paint, "alpha", 255) != 0


def _sample_path(path: Path, tolerance: float) -> tuple[list[np.ndarray], bool]:
    """按 SVG 段顺序采样一条子路径，并保留 Close 带来的闭合语义。"""

    points: list[np.ndarray] = []
    closed = False
    for segment in path:
        if isinstance(segment, Move):
            if segment.end is not None:
                points.append(_point(segment.end))
            continue
        if isinstance(segment, Close):
            closed = True
            continue
        if segment.start is not None and not points:
            points.append(_point(segment.start))
        points.extend(_sample_segment(segment, tolerance))
    if closed and points and not np.allclose(points[0], points[-1]):
        points.append(points[0])
    return points, closed


def _canonical(points: list[tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    """为闭环选择确定的起点和方向，使稳定 ID 不受遍历方式影响。"""

    if not closed:
        return points
    body = points[:-1] if points[0] == points[-1] else points
    forward_start = min(range(len(body)), key=lambda index: body[index])
    forward = body[forward_start:] + body[:forward_start]
    reversed_body = list(reversed(body))
    backward_start = min(range(len(reversed_body)), key=lambda index: reversed_body[index])
    backward = reversed_body[backward_start:] + reversed_body[:backward_start]
    chosen = min(forward, backward)
    return chosen + [chosen[0]]


def _diagnostic(strokes: list[AuditStroke], canvas: CanvasSpec) -> str:
    """用 OpenCV 绘制诊断预览；它只供网页显示，不参与 SVG 几何生成。"""

    longest = 1024
    width = max(1, round(canvas.width * longest))
    height = max(1, round(canvas.height * longest))
    image = np.full((height, width), 255, dtype=np.uint8)
    for stroke in strokes:
        points = np.array(
            [[round(x / canvas.width * (width - 1)), round(y / canvas.height * (height - 1))] for x, y in stroke.points],
            dtype=np.int32,
        )
        if len(points) >= 2:
            cv2.polylines(image, [points], stroke.closed, 0, 1, lineType=cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not encode SVG diagnostic")
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def process_svg(
    content: bytes,
    filename: str,
    parameters: ProcessingParameters,
) -> ProcessResponse:
    """解析 SVG、保留可见描边路径并转换为统一的笔触文档。"""

    # defusedxml 先阻止危险 XML 实体；清洗后的 XML 再交给成熟的
    # svgelements 处理 path、基础形状和 transform。
    try:
        root = SafeElementTree.fromstring(content)
    except Exception as exc:
        raise ValueError(f"SVG XML could not be parsed safely: {exc}") from exc

    # 当前基础闭环暂不解释文本、滤镜、裁剪路径和嵌入位图；这些内容不会
    # 被静默丢弃，而会形成结构化 warning 写入 audit.json。
    warnings: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        element_id = element.attrib.get("id", tag)
        if tag == "text":
            warnings.append(f"unsupported_text:{element_id}")
        elif tag == "image":
            href = element.attrib.get("href") or element.attrib.get("{http://www.w3.org/1999/xlink}href", "")
            warnings.append(
                f"embedded_image_not_processed:{element_id}"
                if href.startswith("data:")
                else f"external_image_blocked:{element_id}"
            )
        if "filter" in element.attrib:
            warnings.append(f"filter_ignored:{element_id}")
        if "clip-path" in element.attrib:
            warnings.append(f"clip_path_ignored:{element_id}")

    sanitized = ElementTree.tostring(root, encoding="utf-8")
    try:
        svg = SVG.parse(BytesIO(sanitized), reify=True, ppi=96)
    except Exception as exc:
        raise ValueError(f"SVG geometry could not be parsed: {exc}") from exc

    # reify=True 已把嵌套 transform 应用到几何坐标；此处再读取最终画布。
    viewbox = svg.viewbox
    origin_x = float(viewbox.x) if viewbox is not None else 0.0
    origin_y = float(viewbox.y) if viewbox is not None else 0.0
    width = float(viewbox.width) if viewbox is not None else float(svg.width or 0)
    height = float(viewbox.height) if viewbox is not None else float(svg.height or 0)
    if width <= 0 or height <= 0:
        raise ValueError("SVG must define a positive width/height or viewBox")
    physical_layout = fit_canvas_layout(
        width,
        height,
        parameters,
        source_width=max(1, round(width)),
        source_height=max(1, round(height)),
    )
    canvas = physical_layout.canvas
    # 容差同时考虑物理有效分辨率和细节等级：细节越高，采样越密。
    tolerance = max(
        0.05,
        parameters.effective_resolution_mm / physical_layout.millimeters_per_source_unit
        * (1.5 - parameters.detail_level / 100),
    )
    source_hash = hashlib.sha256(content).hexdigest()
    audit_strokes: list[AuditStroke] = []
    source_order = 0
    # 按 SVG 元素顺序遍历，从而保留基本创作/绘制顺序。
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        element_id = getattr(element, "id", None)
        stroke = getattr(element, "stroke", None)
        fill = getattr(element, "fill", None)
        # 第一阶段只把可见 stroke 视为候选笔触；仅填充形状记录提示。
        if not _paint_visible(stroke):
            if _paint_visible(fill):
                warnings.append(f"fill_only_ignored:{element_id or source_order}")
            source_order += 1
            continue
        explicit_attributes = getattr(element, "values", {}).get("attributes", {})
        if _paint_visible(fill) and "fill" in explicit_attributes:
            warnings.append(f"fill_ignored:{element_id or source_order}")
        # svgelements 将 line/polyline/polygon/circle/ellipse/rect 统一转换为 Path。
        path = Path(element)
        for subpath_index, subpath in enumerate(path.as_subpaths()):
            sampled, closed = _sample_path(Path(subpath), tolerance)
            if len(sampled) < 2:
                continue
            # 与栅格流程使用同一物理画布，保持比例并居中适配。
            normalized = [
                tuple(round(value, 6) for value in physical_layout.normalize_source_point(
                    float(point[0]) - origin_x,
                    float(point[1]) - origin_y,
                ))
                for point in sampled
            ]
            normalized = _canonical(normalized, closed)
            length = sum(math.dist(sampled[index - 1], sampled[index]) for index in range(1, len(sampled)))
            length_mm = length * physical_layout.millimeters_per_source_unit
            source_ref = element_id or f"element_{source_order}"
            # 输入哈希、元素引用、子路径和规范化几何共同生成确定性 ID。
            identity = json.dumps([source_ref, subpath_index, normalized, closed], separators=(",", ":"))
            stroke_id = "stroke_" + hashlib.sha256(f"{source_hash}:{identity}".encode()).hexdigest()[:12]
            audit_strokes.append(
                AuditStroke(
                    id=stroke_id,
                    source="svg",
                    source_ref=source_ref,
                    source_order=source_order,
                    points=normalized,
                    closed=closed,
                    confidence=1.0,
                    decision=Decision.KEEP,
                    reasons=[],
                    scores=AuditScores(risk=0.0, line_confidence=1.0),
                    length_mm=round(length_mm, 4),
                )
            )
        source_order += 1

    # 当前 SVG 描边默认全部 keep；正式文档精简字段，审核文档保留来源信息。
    lean = [
        DrawingStrokeGeometry(
            id=stroke.id,
            order=order,
            points=stroke.points,
            closed=stroke.closed,
        )
        for order, stroke in enumerate(audit_strokes, start=1)
    ]
    processing_id = "process_" + hashlib.sha256(
        (source_hash + parameters.model_dump_json() + "svg").encode()
    ).hexdigest()[:12]
    diagnostic = _diagnostic(audit_strokes, canvas)
    return ProcessResponse(
        processing_id=processing_id,
        filename=filename,
        strokes_document=StrokesDocument(canvas=canvas, strokes=lean),
        audit_document=AuditDocument(
            canvas=canvas,
            processing=AuditProcessing(
                requested_provider=parameters.provider,
                actual_provider="svg",
                parameters=parameters,
                source_sha256=source_hash,
            ),
            strokes=audit_strokes,
            warnings=sorted(set(warnings)),
        ),
        diagnostics=DiagnosticImages(
            binary_png_data_url=diagnostic,
            skeleton_png_data_url=diagnostic,
        ),
    )
