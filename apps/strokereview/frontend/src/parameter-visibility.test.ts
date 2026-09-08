import { describe, expect, it } from "vitest";
import { getParameterVisibility } from "./parameter-visibility";

describe("processing parameter visibility", () => {
  it("shows every current control for the classic raster pipeline", () => {
    expect(getParameterVisibility("classic", "raster")).toEqual({
      detailLevel: true,
      cleanupStrength: true,
      smoothing: true,
      canvasSize: true,
      penWidth: true,
      minimumLength: true,
      geometryControls: true,
      maxStrokes: true,
      semanticReview: true,
    });
  });

  it("hides classic cleanup for model line extraction", () => {
    expect(getParameterVisibility("lineart", "raster").cleanupStrength).toBe(false);
    expect(getParameterVisibility("pidinet", "raster").smoothing).toBe(true);
    expect(getParameterVisibility("hed", "raster").minimumLength).toBe(true);
    expect(getParameterVisibility("qwen_cloud", "raster").cleanupStrength).toBe(false);
  });

  it("shows only parameters consumed by SVG and mock paths", () => {
    expect(getParameterVisibility("classic", "svg")).toEqual({
      detailLevel: true,
      cleanupStrength: false,
      smoothing: false,
      canvasSize: true,
      penWidth: false,
      minimumLength: false,
      geometryControls: false,
      maxStrokes: false,
      semanticReview: false,
    });
    expect(getParameterVisibility("mock", "raster")).toEqual({
      detailLevel: false,
      cleanupStrength: false,
      smoothing: false,
      canvasSize: true,
      penWidth: false,
      minimumLength: false,
      geometryControls: false,
      maxStrokes: false,
      semanticReview: false,
    });
  });

  it("does not hide controls from unknown partner pipelines", () => {
    expect(Object.values(getParameterVisibility("partner_pipeline", "raster"))).not.toContain(false);
  });
});
