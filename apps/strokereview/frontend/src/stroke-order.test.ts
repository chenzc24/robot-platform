import { describe, expect, it } from "vitest";
import { planStrokeOrder, plannedPenUpDistance } from "./stroke-order";
import type { AuditStroke } from "./types";

function stroke(id: string, start: [number, number], end: [number, number]): AuditStroke {
  return {
    id,
    source: "raster",
    source_ref: null,
    source_order: null,
    points: [start, end],
    closed: false,
    confidence: 1,
    decision: "keep",
    decision_source: "algorithm",
    reversible: true,
    reasons: [],
    scores: { risk: 0, line_confidence: 1 },
    length_mm: 1,
  };
}

describe("stroke drawing order", () => {
  it("orders by importance and never reverses geometry", () => {
    const low = { ...stroke("low", [10, 0], [9, 0]), importance_rank: 3, scores: { risk: 0, line_confidence: 1, importance: 0.2 } };
    const high = { ...stroke("high", [0, 0], [1, 0]), importance_rank: 1, scores: { risk: 0, line_confidence: 1, importance: 0.9 } };
    const middle = { ...stroke("middle", [2, 0], [8, 0]), importance_rank: 2, scores: { risk: 0, line_confidence: 1, importance: 0.5 } };
    const plan = planStrokeOrder([low, high, middle]);
    expect(plan.map((item) => item.id)).toEqual(["high", "middle", "low"]);
    expect(plan.map((item) => item.order)).toEqual([1, 2, 3]);
    expect(plan[2].points).toEqual([[10, 0], [9, 0]]);
    expect(plan.every((item) => item.reversed === false)).toBe(true);
    expect(plannedPenUpDistance(plan)).toBeGreaterThan(0);
  });

  it("excludes non-kept strokes and is deterministic", () => {
    const kept = stroke("keep", [0, 0], [1, 0]);
    const discarded = { ...stroke("discard", [2, 0], [3, 0]), decision: "discard" as const };
    const first = planStrokeOrder([discarded, kept]);
    const second = planStrokeOrder([kept, discarded]);
    expect(first).toEqual(second);
    expect(first.map((item) => item.id)).toEqual(["keep"]);
  });

  it("uses a bounded deterministic importance sort for thousands of strokes", () => {
    const dense = Array.from({ length: 5000 }, (_, index) => {
      const x = (index % 100) / 100;
      const y = Math.floor(index / 100) / 50;
      return stroke(`dense_${index.toString().padStart(5, "0")}`, [x, y], [x + 0.004, y + 0.002]);
    });
    const started = performance.now();
    const first = planStrokeOrder(dense);
    const elapsed = performance.now() - started;
    const second = planStrokeOrder([...dense].reverse());

    expect(first).toHaveLength(5000);
    expect(first).toEqual(second);
    expect(elapsed).toBeLessThan(1000);
  });
});
