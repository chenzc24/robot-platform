import { afterEach, describe, expect, it, vi } from "vitest";

import { processFile } from "./api";
import type { ProcessingParameters } from "./types";

const parameters: ProcessingParameters = {
  provider: "mock",
  detail_level: 50,
  cleanup_strength: 50,
  smoothing: 25,
  target_width_mm: 210,
  target_height_mm: 210,
  minimum_length_mm: 1,
  pen_width_mm: 0.5,
  effective_resolution_mm: 0.25,
  spur_prune_length_mm: 1.2,
  smooth_tolerance_mm: 0.3,
  geometry_tolerance_mm: 0.2,
  max_segment_length_mm: 3,
  max_strokes: 50,
  ai_semantic_review: false,
  ai_review_quality: "standard",
  max_cloud_review_calls: 8,
  provider_parameters: {},
};

describe("processFile", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("passes the caller's cancellation signal to fetch", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ processing_id: "test" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await processFile(new File(["test"], "sample.png", { type: "image/png" }), parameters, controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/process",
      expect.objectContaining({ method: "POST", signal: controller.signal }),
    );
  });
});
