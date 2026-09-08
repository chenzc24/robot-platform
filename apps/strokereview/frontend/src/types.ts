export type Point = [number, number];
export type Decision = "keep" | "uncertain" | "discard";

export interface CanvasSpec {
  width: number;
  height: number;
  source_width: number;
  source_height: number;
  source_aspect_ratio: number;
  target_width_mm: number;
  target_height_mm: number;
}

export interface StrokePath {
  id: string;
  points: Point[];
  closed: boolean;
}

export interface StrokeGeometry extends StrokePath {
  order: number;
}

export interface StrokesDocument {
  version: "1.0";
  coordinate_space: "normalized";
  axis: {
    origin: "top-left";
    x_positive: "right";
    y_positive: "down";
  };
  canvas: CanvasSpec;
  strokes: StrokeGeometry[];
}

export interface ProcessingParameters {
  provider: string;
  detail_level: number;
  cleanup_strength: number;
  minimum_length_mm: number;
  smoothing: number;
  target_width_mm: number;
  target_height_mm: number;
  pen_width_mm: number;
  effective_resolution_mm: number;
  spur_prune_length_mm: number;
  smooth_tolerance_mm: number;
  geometry_tolerance_mm: number;
  max_segment_length_mm: number;
  max_strokes: number;
  ai_semantic_review: boolean;
  ai_review_quality: "economy" | "standard" | "fine";
  max_cloud_review_calls: number;
  provider_parameters: Record<string, unknown>;
}

export interface ProviderOption {
  id: string;
  label: string;
  description: string;
  implementation: string;
  requires_model_service: boolean;
  is_cloud: boolean;
  available: boolean;
  availability_reason: string | null;
  usage_notice: string | null;
}

export interface Capabilities {
  providers: string[];
  provider_options: ProviderOption[];
  accepted_types: string[];
  max_upload_mb: number;
}

export interface AuditStroke extends StrokePath {
  source: "raster" | "svg" | "mock" | "manual";
  source_ref: string | null;
  source_order: number | null;
  confidence: number;
  decision: Decision;
  decision_source: "algorithm" | "user";
  reversible: boolean;
  reasons: string[];
  scores: {
    risk: number;
    line_confidence: number;
    outline_likelihood?: number;
    color_contrast?: number;
    importance?: number;
    marginal_coverage?: number;
    semantic_importance?: number;
    removal_damage?: number;
    model_confidence?: number;
  };
  length_mm: number;
  importance_rank?: number | null;
  semantic_role?: string | null;
  model_reason?: string | null;
}

export interface StrokeSelectionSummary {
  recommended_min_strokes: number;
  requested_max_strokes: number;
  candidate_count: number;
  automatic_keep_count: number;
  target_coverage: number;
  achieved_coverage: number;
  footprint_cell_mm: number;
  physical_feature_scale_mm: number;
}

export interface SemanticReviewSummary {
  status: "disabled" | "completed" | "partial" | "fallback";
  model: string | null;
  call_count: number;
  cache_hit_count: number;
  reviewed_stroke_count: number;
  unreviewed_stroke_count: number;
  main_subjects: string[];
  relationships: string[];
  message: string | null;
}

export interface AuditDocument {
  version: "1.0";
  coordinate_space: "normalized";
  axis: StrokesDocument["axis"];
  canvas: CanvasSpec;
  processing: {
    requested_provider: string;
    actual_provider: string;
    parameters: ProcessingParameters;
    source_sha256: string;
  };
  strokes: AuditStroke[];
  warnings: string[];
  selection_summary?: StrokeSelectionSummary | null;
  semantic_review?: SemanticReviewSummary;
}

export interface ProcessResponse {
  processing_id: string;
  filename: string;
  strokes_document: StrokesDocument;
  audit_document: AuditDocument;
  diagnostics: {
    binary_png_data_url: string;
    skeleton_png_data_url: string;
  } | null;
}
