export interface ParameterVisibility {
  detailLevel: boolean;
  cleanupStrength: boolean;
  smoothing: boolean;
  canvasSize: boolean;
  penWidth: boolean;
  minimumLength: boolean;
  geometryControls: boolean;
  maxStrokes: boolean;
  semanticReview: boolean;
}

const ALL_PARAMETERS: ParameterVisibility = {
  detailLevel: true,
  cleanupStrength: true,
  smoothing: true,
  canvasSize: true,
  penWidth: true,
  minimumLength: true,
  geometryControls: true,
  maxStrokes: true,
  semanticReview: true,
};

/**
 * Keep the controls aligned with parameters that the selected backend path
 * actually reads. Unknown partner pipelines retain every control because they
 * may interpret the standard parameters themselves.
 */
export function getParameterVisibility(provider: string, inputKind: "raster" | "svg"): ParameterVisibility {
  const effectiveProvider = inputKind === "svg" && provider !== "mock" ? "svg" : provider;
  if (effectiveProvider === "svg") {
    return { detailLevel: true, cleanupStrength: false, smoothing: false, canvasSize: true, penWidth: false, minimumLength: false, geometryControls: false, maxStrokes: false, semanticReview: false };
  }
  if (effectiveProvider === "mock") {
    return { detailLevel: false, cleanupStrength: false, smoothing: false, canvasSize: true, penWidth: false, minimumLength: false, geometryControls: false, maxStrokes: false, semanticReview: false };
  }
  if (["lineart", "pidinet", "hed", "qwen_cloud"].includes(effectiveProvider)) {
    return { detailLevel: true, cleanupStrength: false, smoothing: true, canvasSize: true, penWidth: true, minimumLength: true, geometryControls: true, maxStrokes: true, semanticReview: true };
  }
  return { ...ALL_PARAMETERS };
}

export function getParameterVisibilityNote(provider: string, inputKind: "raster" | "svg"): string {
  if (inputKind === "svg" && provider !== "mock") {
    return "SVG 会直接保留并采样矢量路径，仅显示影响采样精度和物理尺寸的参数。";
  }
  if (provider === "mock") {
    return "Mock 不分析图片内容，仅显示会影响测试数据物理尺寸的参数。";
  }
  if (["lineart", "pidinet", "hed", "qwen_cloud"].includes(provider)) {
    if (provider === "qwen_cloud") {
      return "千问负责生成线稿，随后仍使用当前几何、平滑和物理尺寸参数提取笔触；经典清理强度不参与计算。";
    }
    return "该模型直接生成线稿，经典流程的清理强度不参与计算，因此已隐藏。";
  }
  return "当前仅显示该处理算法实际使用的参数。";
}
