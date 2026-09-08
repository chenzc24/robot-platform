import type { AuditStroke, Point, StrokeGeometry } from "./types";

export interface PlannedStroke extends StrokeGeometry {
  order: number;
  reversed: boolean;
}

function distance(first: Point, second: Point): number {
  return Math.hypot(first[0] - second[0], first[1] - second[1]);
}

function numericScore(value: number | undefined): number {
  return Number.isFinite(value) ? (value as number) : 0;
}

/**
 * Every physical stroke starts at, and returns to, the same robot origin.
 * Inter-stroke travel therefore cannot be improved by a TSP route. Preserve
 * semantic importance and point direction so the result becomes recognizable
 * as early as possible and remains deterministic.
 */
export function planStrokeOrder(input: AuditStroke[]): PlannedStroke[] {
  return input
    .filter((stroke) => stroke.decision === "keep" && stroke.points.length >= 2)
    .sort((first, second) => {
      const firstManual = first.source === "manual" || first.reasons?.includes("user_added") ? 0 : 1;
      const secondManual = second.source === "manual" || second.reasons?.includes("user_added") ? 0 : 1;
      if (firstManual !== secondManual) return firstManual - secondManual;

      const firstRank = first.importance_rank ?? Number.POSITIVE_INFINITY;
      const secondRank = second.importance_rank ?? Number.POSITIVE_INFINITY;
      if (firstRank !== secondRank) return firstRank - secondRank;

      const importance = numericScore(second.scores?.importance) - numericScore(first.scores?.importance);
      if (importance !== 0) return importance;
      const semantic = numericScore(second.scores?.semantic_importance) - numericScore(first.scores?.semantic_importance);
      if (semantic !== 0) return semantic;

      const firstSourceOrder = first.source_order ?? Number.POSITIVE_INFINITY;
      const secondSourceOrder = second.source_order ?? Number.POSITIVE_INFINITY;
      if (firstSourceOrder !== secondSourceOrder) return firstSourceOrder - secondSourceOrder;
      return first.id.localeCompare(second.id);
    })
    .map((stroke, index) => ({
      id: stroke.id,
      points: [...stroke.points],
      closed: stroke.closed,
      order: index + 1,
      reversed: false,
    }));
}

// Kept as a diagnostic helper; distance is no longer an ordering objective.
export function plannedPenUpDistance(plan: PlannedStroke[]): number {
  let total = 0;
  for (let index = 1; index < plan.length; index += 1) {
    const previous = plan[index - 1];
    const previousEnd = previous.closed
      ? previous.points[0]
      : previous.points[previous.points.length - 1];
    total += distance(previousEnd, plan[index].points[0]);
  }
  return total;
}
