"""图片转笔触流程的统一输入参数、正式输出和审核输出数据模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


Point = tuple[float, float]


class Decision(StrEnum):
    """算法和用户都使用的三态审核结果。"""

    KEEP = "keep"
    UNCERTAIN = "uncertain"
    DISCARD = "discard"


class AxisSpec(BaseModel):
    origin: Literal["top-left"] = "top-left"
    x_positive: Literal["right"] = "right"
    y_positive: Literal["down"] = "down"


class CanvasSpec(BaseModel):
    """归一化画布、原图像素尺寸和目标物理尺寸。"""

    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    source_aspect_ratio: float = Field(gt=0)
    target_width_mm: float = Field(gt=0)
    target_height_mm: float = Field(gt=0)


class ProcessingParameters(BaseModel):
    """网页传给图片到笔触算法的集中参数。

    detail_level 只控制工作/模型分辨率；cleanup_strength 控制小区域清理；
    minimum_length_mm 参与审核风险判断；四个 tolerance/length 参数分别控制
    图级毛刺、物理平滑、输出误差和最大段长，不再借用 detail_level 决定点密度。
    smoothing 保留为旧网页的兼容强度开关；provider_parameters 留给替换算法。
    """

    provider: str = Field(default="classic", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    detail_level: int = Field(default=50, ge=0, le=100)
    cleanup_strength: int = Field(default=50, ge=0, le=100)
    minimum_length_mm: float = Field(default=1.0, ge=0)
    smoothing: int = Field(default=25, ge=0, le=100)
    target_width_mm: float = Field(default=210.0, gt=0, le=5000)
    target_height_mm: float | None = Field(default=None, gt=0, le=5000)
    pen_width_mm: float = Field(default=0.5, gt=0, le=100)
    effective_resolution_mm: float = Field(default=0.25, gt=0, le=100)
    spur_prune_length_mm: float = Field(default=1.2, ge=0, le=100)
    smooth_tolerance_mm: float = Field(default=0.30, ge=0, le=100)
    geometry_tolerance_mm: float = Field(default=0.20, gt=0, le=100)
    max_segment_length_mm: float = Field(default=3.0, gt=0, le=1000)
    max_strokes: int = Field(default=50, ge=1, le=5000)
    ai_semantic_review: bool = False
    ai_review_quality: Literal["economy", "standard", "fine"] = "standard"
    max_cloud_review_calls: int = Field(default=8, ge=1, le=50)
    provider_parameters: dict[str, Any] = Field(default_factory=dict)


class StrokeGeometry(BaseModel):
    id: str
    points: list[Point] = Field(min_length=2)
    closed: bool = False


class DrawingStrokeGeometry(StrokeGeometry):
    order: int = Field(ge=1)


class StrokesDocument(BaseModel):
    """面向下游的精简几何契约，只包含审核结果为 keep 的笔触。"""

    version: Literal["1.0"] = "1.0"
    coordinate_space: Literal["normalized"] = "normalized"
    axis: AxisSpec = Field(default_factory=AxisSpec)
    canvas: CanvasSpec
    strokes: list[DrawingStrokeGeometry]


class AuditScores(BaseModel):
    risk: float = Field(ge=0, le=1)
    line_confidence: float = Field(ge=0, le=1)
    # 与栅格图最外层边界的接近程度。默认值保证旧 audit.json 仍可读取。
    outline_likelihood: float = Field(default=0.0, ge=0, le=1)
    # 笔触法向两侧的原图颜色分离程度；纯线稿模式不使用此门槛。
    color_contrast: float = Field(default=1.0, ge=0, le=1)
    # 本地结构/物理评分与模型语义评分的最终融合结果。
    importance: float = Field(default=0.0, ge=0, le=1)
    # 该笔触相对已经保留笔触贡献的新墨迹比例。
    marginal_coverage: float = Field(default=1.0, ge=0, le=1)
    semantic_importance: float = Field(default=0.0, ge=0, le=1)
    removal_damage: float = Field(default=0.0, ge=0, le=1)
    model_confidence: float = Field(default=0.0, ge=0, le=1)


class AuditStroke(StrokeGeometry):
    """可恢复的完整候选笔触，包含置信度、判断原因和风险评分。"""

    source: Literal["raster", "svg", "mock", "manual"] = "mock"
    source_ref: str | None = None
    source_order: int | None = None
    confidence: float = Field(ge=0, le=1)
    decision: Decision
    decision_source: Literal["algorithm", "user"] = "algorithm"
    reversible: bool = True
    reasons: list[str] = Field(default_factory=list)
    scores: AuditScores
    length_mm: float = Field(ge=0)
    importance_rank: int | None = Field(default=None, ge=1)
    semantic_role: str | None = None
    model_reason: str | None = None


class AuditProcessing(BaseModel):
    requested_provider: str
    actual_provider: str
    parameters: ProcessingParameters
    source_sha256: str


class StrokeSelectionSummary(BaseModel):
    """自动筛选和物理墨迹覆盖的可审计摘要。"""

    recommended_min_strokes: int = Field(default=0, ge=0)
    requested_max_strokes: int = Field(default=50, ge=1, le=5000)
    candidate_count: int = Field(default=0, ge=0)
    automatic_keep_count: int = Field(default=0, ge=0)
    target_coverage: float = Field(default=0.0, ge=0, le=1)
    achieved_coverage: float = Field(default=0.0, ge=0, le=1)
    footprint_cell_mm: float = Field(default=0.0, ge=0)
    physical_feature_scale_mm: float = Field(default=0.0, ge=0)


class SemanticReviewSummary(BaseModel):
    """视觉模型审核状态；详细逐笔结果保存在 AuditStroke。"""

    status: Literal["disabled", "completed", "partial", "fallback"] = "disabled"
    model: str | None = None
    call_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    reviewed_stroke_count: int = Field(default=0, ge=0)
    unreviewed_stroke_count: int = Field(default=0, ge=0)
    main_subjects: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    message: str | None = None


class AuditDocument(BaseModel):
    """面向人工审核和调试的完整文档，保留所有三态笔触。"""

    version: Literal["1.0"] = "1.0"
    coordinate_space: Literal["normalized"] = "normalized"
    axis: AxisSpec = Field(default_factory=AxisSpec)
    canvas: CanvasSpec
    processing: AuditProcessing
    strokes: list[AuditStroke]
    warnings: list[str] = Field(default_factory=list)
    selection_summary: StrokeSelectionSummary | None = None
    semantic_review: SemanticReviewSummary = Field(default_factory=SemanticReviewSummary)


class DiagnosticImages(BaseModel):
    binary_png_data_url: str
    skeleton_png_data_url: str


class ProcessResponse(BaseModel):
    processing_id: str
    filename: str
    strokes_document: StrokesDocument
    audit_document: AuditDocument
    diagnostics: DiagnosticImages | None = None


class ProviderOption(BaseModel):
    id: str
    label: str
    description: str
    implementation: str
    requires_model_service: bool = False
    is_cloud: bool = False
    available: bool = True
    availability_reason: str | None = None
    usage_notice: str | None = None


class Capabilities(BaseModel):
    providers: list[str]
    provider_options: list[ProviderOption] = Field(default_factory=list)
    accepted_types: list[str]
    max_upload_mb: int
