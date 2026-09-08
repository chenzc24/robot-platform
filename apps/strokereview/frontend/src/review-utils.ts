import type { Decision, Point, ProcessResponse, StrokeGeometry } from "./types";
import { planStrokeOrder } from "./stroke-order";

export interface SplitLocation {
  segmentIndex: number;
  point: Point;
}

export interface SplitResult {
  result: ProcessResponse;
  strokeIds: [string, string];
}

export interface ManualStrokeResult {
  result: ProcessResponse;
  strokeId: string;
}

export interface OuterContourSelectionResult {
  result: ProcessResponse;
  selectedCount: number;
}

function officialGeometry(strokes: ProcessResponse["audit_document"]["strokes"]): StrokeGeometry[] {
  return planStrokeOrder(strokes).map(({ id, order, points, closed }) => ({ id, order, points, closed }));
}

export function applyOptimizedStrokeOrder(result: ProcessResponse): ProcessResponse {
  return {
    ...result,
    strokes_document: {
      ...result.strokes_document,
      strokes: officialGeometry(result.audit_document.strokes),
    },
  };
}

function polylineLength(points: Point[]): number {
  let length = 0;
  for (let index = 1; index < points.length; index += 1) {
    length += Math.hypot(
      points[index][0] - points[index - 1][0],
      points[index][1] - points[index - 1][1],
    );
  }
  return length;
}

function samePoint(first: Point, second: Point): boolean {
  return Math.abs(first[0] - second[0]) < 1e-9 && Math.abs(first[1] - second[1]) < 1e-9;
}

function stableToken(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function addManualStroke(
  result: ProcessResponse,
  inputPoints: Point[],
): ManualStrokeResult | null {
  const points: Point[] = [];
  for (const inputPoint of inputPoints) {
    const point: Point = [
      Math.round(inputPoint[0] * 1_000_000) / 1_000_000,
      Math.round(inputPoint[1] * 1_000_000) / 1_000_000,
    ];
    if (!points.length || !samePoint(points[points.length - 1], point)) points.push(point);
  }
  const normalizedLength = polylineLength(points);
  if (points.length < 2 || normalizedLength < 1e-6) return null;

  const token = stableToken(JSON.stringify(points));
  const prefix = `stroke_manual_${token}`;
  const occurrence = result.audit_document.strokes.filter((stroke) => stroke.id.startsWith(prefix)).length + 1;
  const strokeId = `${prefix}_${occurrence}`;
  const lengthMm = normalizedLength
    * result.audit_document.canvas.target_width_mm
    / result.audit_document.canvas.width;
  const stroke = {
    id: strokeId,
    source: "manual" as const,
    source_ref: "user_drawn",
    source_order: null,
    points,
    closed: false,
    confidence: 1,
    decision: "keep" as const,
    decision_source: "user" as const,
    reversible: true,
    reasons: ["user_added"],
    scores: {
      risk: 0,
      line_confidence: 1,
      importance: 1,
      marginal_coverage: 1,
      semantic_importance: 1,
      removal_damage: 1,
      model_confidence: 1,
    },
    length_mm: Math.round(lengthMm * 10_000) / 10_000,
    importance_rank: 1,
    semantic_role: "user_added",
    model_reason: null,
  };
  const strokes = [...result.audit_document.strokes, stroke];
  return {
    strokeId,
    result: {
      ...result,
      audit_document: { ...result.audit_document, strokes },
      strokes_document: {
        ...result.strokes_document,
        strokes: officialGeometry(strokes),
      },
    },
  };
}

export function nearestPointOnStroke(points: Point[], target: Point): SplitLocation | null {
  if (points.length < 2) return null;
  let nearest: SplitLocation | null = null;
  let nearestDistanceSquared = Number.POSITIVE_INFINITY;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const denominator = dx * dx + dy * dy;
    if (denominator === 0) continue;
    const projection = Math.max(0, Math.min(1,
      ((target[0] - start[0]) * dx + (target[1] - start[1]) * dy) / denominator,
    ));
    const point: Point = [
      Math.round((start[0] + projection * dx) * 1_000_000) / 1_000_000,
      Math.round((start[1] + projection * dy) * 1_000_000) / 1_000_000,
    ];
    const distanceSquared = (target[0] - point[0]) ** 2 + (target[1] - point[1]) ** 2;
    if (distanceSquared < nearestDistanceSquared) {
      nearestDistanceSquared = distanceSquared;
      nearest = { segmentIndex: index, point };
    }
  }
  return nearest;
}

export function splitStrokeAtPosition(
  result: ProcessResponse,
  strokeId: string,
  location: SplitLocation,
): SplitResult | null {
  const strokeIndex = result.audit_document.strokes.findIndex((stroke) => stroke.id === strokeId);
  if (strokeIndex < 0) return null;
  const stroke = result.audit_document.strokes[strokeIndex];
  if (location.segmentIndex < 0 || location.segmentIndex >= stroke.points.length - 1) return null;

  const splitPoint: Point = [
    Math.round(location.point[0] * 1_000_000) / 1_000_000,
    Math.round(location.point[1] * 1_000_000) / 1_000_000,
  ];
  const allPoints = [...stroke.points];
  let splitIndex: number;
  if (samePoint(splitPoint, allPoints[location.segmentIndex])) {
    splitIndex = location.segmentIndex;
  } else if (samePoint(splitPoint, allPoints[location.segmentIndex + 1])) {
    splitIndex = location.segmentIndex + 1;
  } else {
    splitIndex = location.segmentIndex + 1;
    allPoints.splice(splitIndex, 0, splitPoint);
  }
  if (splitIndex === 0 || splitIndex === allPoints.length - 1) return null;

  const firstPoints = allPoints.slice(0, splitIndex + 1);
  const secondPoints = allPoints.slice(splitIndex);
  const firstGeometryLength = polylineLength(firstPoints);
  const secondGeometryLength = polylineLength(secondPoints);
  const totalGeometryLength = firstGeometryLength + secondGeometryLength;
  if (totalGeometryLength === 0) return null;
  const minimumPartLength = Math.max(totalGeometryLength * 0.002, 1e-6);
  if (firstGeometryLength < minimumPartLength || secondGeometryLength < minimumPartLength) return null;

  const token = stableToken(`${stroke.id}|${splitIndex}|${splitPoint[0]},${splitPoint[1]}`);
  const strokeIds: [string, string] = [
    `${stroke.id}_split_${token}_a`,
    `${stroke.id}_split_${token}_b`,
  ];
  const reasons = stroke.reasons.includes("user_split")
    ? stroke.reasons
    : [...stroke.reasons, "user_split"];
  const firstLengthMm = stroke.length_mm * firstGeometryLength / totalGeometryLength;
  const secondLengthMm = stroke.length_mm - firstLengthMm;
  const splitStrokes = [
    {
      ...stroke,
      id: strokeIds[0],
      points: firstPoints,
      closed: false,
      decision_source: "user" as const,
      reasons,
      length_mm: Math.round(firstLengthMm * 10_000) / 10_000,
    },
    {
      ...stroke,
      id: strokeIds[1],
      points: secondPoints,
      closed: false,
      decision_source: "user" as const,
      reasons,
      length_mm: Math.round(secondLengthMm * 10_000) / 10_000,
    },
  ];
  const strokes = [...result.audit_document.strokes];
  strokes.splice(strokeIndex, 1, ...splitStrokes);
  return {
    strokeIds,
    result: {
      ...result,
      audit_document: { ...result.audit_document, strokes },
      strokes_document: {
        ...result.strokes_document,
        strokes: officialGeometry(strokes),
      },
    },
  };
}

export function updateStrokeDecision(
  result: ProcessResponse,
  strokeId: string,
  decision: Decision,
): ProcessResponse {
  const strokes = result.audit_document.strokes.map((stroke) =>
    stroke.id === strokeId
      ? { ...stroke, decision, decision_source: "user" as const }
      : stroke,
  );
  return {
    ...result,
    audit_document: {
      ...result.audit_document,
      strokes,
    },
    strokes_document: {
      ...result.strokes_document,
      strokes: officialGeometry(strokes),
    },
  };
}

export function updateStrokeDecisions(
  result: ProcessResponse,
  strokeIds: Iterable<string>,
  decision: Decision,
): ProcessResponse {
  const selected = new Set(strokeIds);
  if (selected.size === 0) return result;
  const strokes = result.audit_document.strokes.map((stroke) =>
    selected.has(stroke.id)
      ? { ...stroke, decision, decision_source: "user" as const }
      : stroke,
  );
  return {
    ...result,
    audit_document: { ...result.audit_document, strokes },
    strokes_document: {
      ...result.strokes_document,
      strokes: officialGeometry(strokes),
    },
  };
}

export function updateAllStrokeDecisions(
  result: ProcessResponse,
  decision: Decision,
): ProcessResponse {
  const strokes = result.audit_document.strokes.map((stroke) => ({
    ...stroke,
    decision,
    decision_source: "user" as const,
  }));
  return {
    ...result,
    audit_document: {
      ...result.audit_document,
      strokes,
    },
    strokes_document: {
      ...result.strokes_document,
      strokes: officialGeometry(strokes),
    },
  };
}

export function enterPositiveSelection(
  result: ProcessResponse,
  resumeExistingSession: boolean,
): ProcessResponse {
  // 只有首次进入才执行“全不选”。暂停后继续必须原样保留已经选中的
  // keep、人工补画和拆分结果。
  return resumeExistingSession ? result : updateAllStrokeDecisions(result, "uncertain");
}

export function selectOuterContourStrokes(
  result: ProcessResponse,
): OuterContourSelectionResult | null {
  const selectedIds = new Set(
    result.audit_document.strokes
      .filter((stroke) =>
        stroke.reasons.includes("outer_contour_candidate")
        && !stroke.reasons.includes("near_duplicate_parallel")
        && !stroke.reasons.includes("pen_footprint_redundant")
        && !stroke.reasons.includes("pruned_spur"),
      )
      .map((stroke) => stroke.id),
  );
  if (!selectedIds.size) return null;

  const strokes = result.audit_document.strokes.map((stroke) => ({
    ...stroke,
    decision: (selectedIds.has(stroke.id) ? "keep" : "uncertain") as Decision,
    decision_source: "user" as const,
  }));
  return {
    selectedCount: selectedIds.size,
    result: {
      ...result,
      audit_document: { ...result.audit_document, strokes },
      strokes_document: {
        ...result.strokes_document,
        strokes: officialGeometry(strokes),
      },
    },
  };
}
