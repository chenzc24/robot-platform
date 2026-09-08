import { describe, expect, it } from "vitest";
import { addManualStroke, enterPositiveSelection, nearestPointOnStroke, selectOuterContourStrokes, splitStrokeAtPosition, updateAllStrokeDecisions, updateStrokeDecision, updateStrokeDecisions } from "./review-utils";
import type { ProcessResponse } from "./types";

const result = {
  strokes_document: {
    strokes: [
      { id: "keep", points: [[0, 0], [1, 1]], closed: false },
    ],
  },
  audit_document: {
    strokes: [
      {
        id: "keep",
        points: [[0, 0], [1, 1]],
        closed: false,
        decision: "keep",
        decision_source: "algorithm",
      },
      {
        id: "discard",
        points: [[0, 1], [1, 0]],
        closed: false,
        decision: "discard",
        decision_source: "algorithm",
      },
    ],
  },
} as unknown as ProcessResponse;

describe("manual stroke review", () => {
  it("removes a user-discarded stroke from the official geometry", () => {
    const updated = updateStrokeDecision(result, "keep", "discard");
    expect(updated.audit_document.strokes[0]).toMatchObject({
      decision: "discard",
      decision_source: "user",
    });
    expect(updated.strokes_document.strokes).toEqual([]);
    expect(result.audit_document.strokes[0].decision).toBe("keep");
  });

  it("restores a discarded stroke into the official geometry", () => {
    const updated = updateStrokeDecision(result, "discard", "keep");
    expect(updated.strokes_document.strokes.map((stroke) => stroke.id).sort()).toEqual([
      "discard",
      "keep",
    ]);
    expect(updated.audit_document.strokes[1].decision_source).toBe("user");
  });

  it("keeps uncertain strokes out of the official geometry", () => {
    const updated = updateStrokeDecision(result, "keep", "uncertain");
    expect(updated.strokes_document.strokes).toEqual([]);
  });

  it("allows an uncertain stroke to be manually kept or discarded", () => {
    const uncertain = updateStrokeDecision(result, "keep", "uncertain");
    const kept = updateStrokeDecision(uncertain, "keep", "keep");
    expect(kept.audit_document.strokes[0]).toMatchObject({
      decision: "keep",
      decision_source: "user",
    });
    expect(kept.strokes_document.strokes.map((stroke) => stroke.id)).toEqual(["keep"]);
    expect(kept.strokes_document.strokes[0].order).toBe(1);

    const discarded = updateStrokeDecision(uncertain, "keep", "discard");
    expect(discarded.audit_document.strokes[0]).toMatchObject({
      decision: "discard",
      decision_source: "user",
    });
    expect(discarded.strokes_document.strokes).toEqual([]);
  });

  it("applies one decision to several selected strokes", () => {
    const uncertain = updateAllStrokeDecisions(result, "uncertain");
    const kept = updateStrokeDecisions(uncertain, ["keep", "discard"], "keep");

    expect(kept.audit_document.strokes.every((stroke) => stroke.decision === "keep")).toBe(true);
    expect(kept.audit_document.strokes.every((stroke) => stroke.decision_source === "user")).toBe(true);
    expect(kept.strokes_document.strokes.map((stroke) => stroke.id).sort()).toEqual(["discard", "keep"]);
  });

  it("starts positive selection with every candidate visible but unselected", () => {
    const updated = updateAllStrokeDecisions(result, "uncertain");
    expect(updated.audit_document.strokes.every((stroke) => stroke.decision === "uncertain")).toBe(true);
    expect(updated.audit_document.strokes.every((stroke) => stroke.decision_source === "user")).toBe(true);
    expect(updated.strokes_document.strokes).toEqual([]);
  });

  it("resumes positive selection without clearing saved keep decisions", () => {
    const started = enterPositiveSelection(result, false);
    const selected = updateStrokeDecision(started, "keep", "keep");
    const resumed = enterPositiveSelection(selected, true);

    expect(resumed).toBe(selected);
    expect(resumed.audit_document.strokes.find((stroke) => stroke.id === "keep")?.decision).toBe("keep");
    expect(resumed.strokes_document.strokes.map((stroke) => stroke.id)).toEqual(["keep"]);
  });

  it("keeps only safe outer-contour candidates in the minimal outline preset", () => {
    const outlined = {
      ...result,
      audit_document: {
        ...result.audit_document,
        strokes: [
          {
            ...result.audit_document.strokes[0],
            id: "outer",
            reasons: ["outer_contour_candidate"],
            scores: { risk: 0.8, line_confidence: 0.5, outline_likelihood: 0.9 },
          },
          {
            ...result.audit_document.strokes[0],
            id: "detail",
            reasons: [],
            scores: { risk: 0.1, line_confidence: 0.9, outline_likelihood: 0.1 },
          },
          {
            ...result.audit_document.strokes[0],
            id: "duplicate",
            reasons: ["outer_contour_candidate", "near_duplicate_parallel"],
            scores: { risk: 0.5, line_confidence: 0.8, outline_likelihood: 0.95 },
          },
        ],
      },
    } as unknown as ProcessResponse;

    const selected = selectOuterContourStrokes(outlined);

    expect(selected?.selectedCount).toBe(1);
    expect(selected?.result.strokes_document.strokes.map((stroke) => stroke.id)).toEqual(["outer"]);
    expect(selected?.result.audit_document.strokes.map((stroke) => stroke.decision)).toEqual([
      "keep",
      "uncertain",
      "uncertain",
    ]);
  });

  it("finds the nearest position on a polyline", () => {
    expect(nearestPointOnStroke([[0, 0], [1, 0], [1, 1]], [0.4, 0.2])).toEqual({
      segmentIndex: 0,
      point: [0.4, 0],
    });
  });

  it("splits a two-point stroke at an arbitrary position", () => {
    const editable = {
      ...result,
      audit_document: {
        ...result.audit_document,
        canvas: { width: 1, target_width_mm: 200 },
        strokes: [{
          id: "line",
          source: "raster",
          source_ref: null,
          source_order: null,
          points: [[0, 0], [1, 0]],
          closed: false,
          confidence: 0.9,
          decision: "keep",
          decision_source: "algorithm",
          reversible: true,
          reasons: [],
          scores: { risk: 0.1, line_confidence: 0.9 },
          length_mm: 100,
        }],
      },
    } as unknown as ProcessResponse;
    const split = splitStrokeAtPosition(editable, "line", { segmentIndex: 0, point: [0.25, 0] });
    expect(split).not.toBeNull();
    expect(split!.result.audit_document.strokes).toHaveLength(2);
    expect(split!.result.audit_document.strokes.map((stroke) => stroke.points)).toEqual([
      [[0, 0], [0.25, 0]],
      [[0.25, 0], [1, 0]],
    ]);
    expect(split!.result.audit_document.strokes.map((stroke) => stroke.length_mm)).toEqual([25, 75]);
    expect(split!.result.audit_document.strokes.every((stroke) => stroke.reasons.includes("user_split"))).toBe(true);
    expect(split!.result.strokes_document.strokes).toHaveLength(2);
  });

  it("adds a user-drawn keep stroke to audit and official geometry", () => {
    const editable = {
      ...result,
      audit_document: {
        ...result.audit_document,
        canvas: { width: 0.5, target_width_mm: 100 },
        strokes: [],
      },
      strokes_document: { ...result.strokes_document, strokes: [] },
    } as unknown as ProcessResponse;
    const added = addManualStroke(editable, [[0.1, 0.1], [0.2, 0.2], [0.4, 0.2]]);
    expect(added).not.toBeNull();
    expect(added!.result.audit_document.strokes[0]).toMatchObject({
      id: added!.strokeId,
      source: "manual",
      decision: "keep",
      decision_source: "user",
      reasons: ["user_added"],
    });
    expect(added!.result.strokes_document.strokes[0].id).toBe(added!.strokeId);
  });
});
