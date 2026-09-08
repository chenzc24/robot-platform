import { type DragEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent, useEffect, useMemo, useRef, useState } from "react";
import { getCapabilities, processFile } from "./api";
import { downloadJson, downloadPythonStrokesZip, uncertainCount } from "./export-utils";
import { getParameterVisibility, getParameterVisibilityNote } from "./parameter-visibility";
import { addManualStroke, applyOptimizedStrokeOrder, enterPositiveSelection, nearestPointOnStroke, selectOuterContourStrokes, splitStrokeAtPosition, updateStrokeDecision, updateStrokeDecisions } from "./review-utils";
import { planStrokeOrder, type PlannedStroke } from "./stroke-order";
import type { AuditStroke, Decision, Point, ProcessResponse, ProcessingParameters, ProviderOption } from "./types";
import "./styles.css";

const defaultParameters: ProcessingParameters = {
  provider: "classic",
  detail_level: 50,
  cleanup_strength: 50,
  minimum_length_mm: 1,
  smoothing: 25,
  target_width_mm: 210,
  target_height_mm: 210,
  pen_width_mm: 0.5,
  effective_resolution_mm: 0.25,
  spur_prune_length_mm: 1.2,
  smooth_tolerance_mm: 0.30,
  geometry_tolerance_mm: 0.20,
  max_segment_length_mm: 3.0,
  max_strokes: 50,
  ai_semantic_review: false,
  ai_review_quality: "standard",
  max_cloud_review_calls: 8,
  provider_parameters: {},
};

const defaultProviderOptions: ProviderOption[] = [
  { id: "classic", label: "经典 OpenCV（线稿/扫描稿）", description: "本地经典图像处理与骨架流程", implementation: "builtin", requires_model_service: false, is_cloud: false, available: true, availability_reason: null, usage_notice: null },
  { id: "lineart", label: "Lineart（插画，CPU）", description: "本地 Lineart 模型", implementation: "builtin", requires_model_service: true, is_cloud: false, available: true, availability_reason: null, usage_notice: null },
  { id: "pidinet", label: "PiDiNet（照片，CPU）", description: "本地 PiDiNet 模型", implementation: "builtin", requires_model_service: true, is_cloud: false, available: true, availability_reason: null, usage_notice: null },
  { id: "hed", label: "HED（备用，CPU）", description: "本地 HED 模型", implementation: "builtin", requires_model_service: true, is_cloud: false, available: true, availability_reason: null, usage_notice: null },
  { id: "qwen_cloud", label: "API 模式（千问云端线稿）", description: "调用阿里云百炼生成线稿", implementation: "builtin", requires_model_service: false, is_cloud: true, available: false, availability_reason: "正在读取后端云端配置…", usage_notice: "图片会上传至阿里云百炼；未命中缓存的成功生成可能消耗免费额度或产生费用。" },
  { id: "mock", label: "Mock（诊断）", description: "固定测试输出", implementation: "builtin", requires_model_service: false, is_cloud: false, available: true, availability_reason: null, usage_notice: null },
];

const colors = { keep: "#21c98b", uncertain: "#f5a524", discard: "#718096" };
const MAX_STROKE_ZOOM = 128;
const DENSE_SVG_THRESHOLD = 1200;
const SOURCE_PREVIEW_MAX_DIMENSION = 1600;

interface Viewport {
  x: number;
  y: number;
  width: number;
  height: number;
}

function clientPointInCanvas(svg: SVGSVGElement, clientX: number, clientY: number, width: number, height: number, viewport?: Viewport): Point | null {
  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
  const matrix = typeof svg.getScreenCTM === "function" ? svg.getScreenCTM() : null;
  if (matrix && typeof svg.createSVGPoint === "function") {
    const pointer = svg.createSVGPoint();
    pointer.x = clientX;
    pointer.y = clientY;
    const local = pointer.matrixTransform(matrix.inverse());
    return [
      Math.max(0, Math.min(width, local.x)),
      Math.max(0, Math.min(height, local.y)),
    ];
  }
  const bounds = svg.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return null;
  const visible = viewport ?? { x: 0, y: 0, width, height };
  const scale = Math.min(bounds.width / visible.width, bounds.height / visible.height);
  const horizontalPadding = (bounds.width - visible.width * scale) / 2;
  const verticalPadding = (bounds.height - visible.height * scale) / 2;
  return [
    Math.max(0, Math.min(width, visible.x + (clientX - bounds.left - horizontalPadding) / scale)),
    Math.max(0, Math.min(height, visible.y + (clientY - bounds.top - verticalPadding) / scale)),
  ];
}

function pointerInCanvas(event: ReactMouseEvent<SVGGElement>, width: number, height: number, viewport: Viewport): Point | null {
  const svg = event.currentTarget.ownerSVGElement;
  return svg ? clientPointInCanvas(svg, event.clientX, event.clientY, width, height, viewport) : null;
}

function ParameterSlider({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="field slider-field">
      <span>{label}</span>
      <input type="range" min="0" max="100" value={value} onChange={(event) => onChange(Number(event.target.value))} />
      <output>{value}</output>
    </label>
  );
}

async function createSourcePreviewUrl(file: File): Promise<string> {
  if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
    return URL.createObjectURL(file);
  }
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const scale = Math.min(1, SOURCE_PREVIEW_MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("浏览器无法创建图片预览画布");
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (created) => created ? resolve(created) : reject(new Error("浏览器无法生成缩略预览")),
        "image/jpeg",
        0.9,
      );
    });
    return URL.createObjectURL(blob);
  } finally {
    bitmap.close();
  }
}

export function StrokePreview({
  strokes,
  width,
  height,
  penWidthMm = 0.5,
  targetWidthMm = 210,
  selectedId,
  selectedIds,
  showOnlyKeep,
  showDeleted,
  splitMode,
  addMode,
  drawingPlan,
  onSelect,
  onSplit,
  onAdd,
}: {
  strokes: AuditStroke[];
  width: number;
  height: number;
  penWidthMm?: number;
  targetWidthMm?: number;
  selectedId: string | null;
  selectedIds?: ReadonlySet<string>;
  showOnlyKeep: boolean;
  showDeleted: boolean;
  splitMode: boolean;
  addMode: boolean;
  drawingPlan?: PlannedStroke[];
  onSelect: (strokeId: string | null) => void;
  onSplit: (strokeId: string, segmentIndex: number, point: Point) => void;
  onAdd: (points: Point[]) => void;
}) {
  const previewRef = useRef<HTMLDivElement>(null);
  const [draftPoints, setDraftPoints] = useState<Point[]>([]);
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, width, height });
  const [panMode, setPanMode] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const draftRef = useRef<Point[]>([]);
  const panRef = useRef<{
    pointerId: number;
    clientX: number;
    clientY: number;
    viewport: Viewport;
  } | null>(null);
  const zoom = width / viewport.width;

  function fullscreenTarget(): HTMLElement | null {
    return previewRef.current?.closest<HTMLElement>(".preview-panel") ?? previewRef.current;
  }

  useEffect(() => {
    setViewport({ x: 0, y: 0, width, height });
    setPanMode(false);
  }, [width, height]);

  useEffect(() => {
    if (!addMode) {
      draftRef.current = [];
      setDraftPoints([]);
    }
    if (addMode) setPanMode(false);
  }, [addMode]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(document.fullscreenElement === fullscreenTarget());
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  function clampViewport(next: Viewport): Viewport {
    return {
      ...next,
      x: Math.max(0, Math.min(width - next.width, next.x)),
      y: Math.max(0, Math.min(height - next.height, next.y)),
    };
  }

  function changeZoom(calculateZoom: (currentZoom: number) => number, anchor?: Point) {
    setViewport((current) => {
      const currentZoom = width / current.width;
      const nextZoom = Math.max(1, Math.min(MAX_STROKE_ZOOM, calculateZoom(currentZoom)));
      if (Math.abs(nextZoom - currentZoom) < 1e-9) return current;
      const focus = anchor ?? [current.x + current.width / 2, current.y + current.height / 2];
      const horizontalRatio = (focus[0] - current.x) / current.width;
      const verticalRatio = (focus[1] - current.y) / current.height;
      const nextWidth = width / nextZoom;
      const nextHeight = height / nextZoom;
      return clampViewport({
        x: focus[0] - horizontalRatio * nextWidth,
        y: focus[1] - verticalRatio * nextHeight,
        width: nextWidth,
        height: nextHeight,
      });
    });
  }

  function zoomAround(factor: number, anchor?: Point) {
    changeZoom((currentZoom) => currentZoom * factor, anchor);
  }

  function adjustZoom(step: number) {
    changeZoom((currentZoom) => Math.round((currentZoom + step) * 10) / 10);
  }

  function resetViewport() {
    setViewport({ x: 0, y: 0, width, height });
    setPanMode(false);
  }

  async function toggleFullscreen() {
    const target = fullscreenTarget();
    try {
      if (document.fullscreenElement === target) {
        await document.exitFullscreen();
      } else if (target?.requestFullscreen) {
        await target.requestFullscreen();
      }
    } catch {
      // 浏览器拒绝全屏时保持当前显示，不影响笔触审核。
    }
  }

  function handleWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const anchor = clientPointInCanvas(event.currentTarget, event.clientX, event.clientY, width, height, viewport);
    zoomAround(event.deltaY < 0 ? 1.6 : 1 / 1.6, anchor ?? undefined);
  }

  function beginPan(event: ReactPointerEvent<SVGSVGElement>) {
    if (addMode || (!panMode && event.button !== 1)) return false;
    event.preventDefault();
    if (typeof event.currentTarget.setPointerCapture === "function") event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      viewport,
    };
    return true;
  }

  function continuePan(event: ReactPointerEvent<SVGSVGElement>) {
    const start = panRef.current;
    if (!start || start.pointerId !== event.pointerId) return false;
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return true;
    setViewport(clampViewport({
      ...start.viewport,
      x: start.viewport.x - (event.clientX - start.clientX) * start.viewport.width / bounds.width,
      y: start.viewport.y - (event.clientY - start.clientY) * start.viewport.height / bounds.height,
    }));
    return true;
  }

  function finishPan(event: ReactPointerEvent<SVGSVGElement>) {
    if (!panRef.current || panRef.current.pointerId !== event.pointerId) return false;
    event.preventDefault();
    if (typeof event.currentTarget.releasePointerCapture === "function" && event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    panRef.current = null;
    return true;
  }

  function beginManualStroke(event: ReactPointerEvent<SVGSVGElement>) {
    if (!addMode) return;
    event.preventDefault();
    const point = clientPointInCanvas(event.currentTarget, event.clientX, event.clientY, width, height, viewport);
    if (!point) return;
    if (typeof event.currentTarget.setPointerCapture === "function") event.currentTarget.setPointerCapture(event.pointerId);
    draftRef.current = [point];
    setDraftPoints([point]);
  }

  function continueManualStroke(event: ReactPointerEvent<SVGSVGElement>) {
    if (!addMode || draftRef.current.length === 0) return;
    event.preventDefault();
    const point = clientPointInCanvas(event.currentTarget, event.clientX, event.clientY, width, height, viewport);
    if (!point) return;
    const previous = draftRef.current[draftRef.current.length - 1];
    if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) < Math.max(width, height) * 0.0025 / zoom) return;
    draftRef.current = [...draftRef.current, point];
    setDraftPoints(draftRef.current);
  }

  function finishManualStroke(event: ReactPointerEvent<SVGSVGElement>) {
    if (!addMode || draftRef.current.length === 0) return;
    event.preventDefault();
    if (typeof event.currentTarget.releasePointerCapture === "function" && event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const finalPoint = clientPointInCanvas(event.currentTarget, event.clientX, event.clientY, width, height, viewport);
    const previous = draftRef.current[draftRef.current.length - 1];
    const completed = finalPoint && Math.hypot(finalPoint[0] - previous[0], finalPoint[1] - previous[1]) >= Math.max(width, height) * 0.0025 / zoom
      ? [...draftRef.current, finalPoint]
      : draftRef.current;
    draftRef.current = [];
    setDraftPoints([]);
    if (completed.length >= 2) onAdd(completed);
  }

  const visibleStrokes = useMemo(() => strokes.filter((stroke) =>
    (!showOnlyKeep || stroke.decision === "keep")
    && (showDeleted || stroke.decision !== "discard"),
  ), [showDeleted, showOnlyKeep, strokes]);
  const planById = useMemo(
    () => new Map((drawingPlan ?? planStrokeOrder(strokes)).map((item) => [item.id, item])),
    [drawingPlan, strokes],
  );
  const densePreview = visibleStrokes.length > DENSE_SVG_THRESHOLD;
  const batchedPaths = useMemo(() => {
    if (!densePreview) return null;
    const paths: Record<Decision, string[]> = { keep: [], uncertain: [], discard: [] };
    for (const stroke of visibleStrokes) {
      if (stroke.id === selectedId) continue;
      const points = planById.get(stroke.id)?.points ?? stroke.points;
      if (points.length < 2) continue;
      paths[stroke.decision].push(
        points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" "),
      );
    }
    return {
      keep: paths.keep.join(" "),
      uncertain: paths.uncertain.join(" "),
      discard: paths.discard.join(" "),
    };
  }, [densePreview, planById, selectedId, visibleStrokes]);
  const individuallyRenderedStrokes = densePreview
    ? visibleStrokes.filter((stroke) => stroke.id === selectedId)
    : visibleStrokes;
  const batchSelectionPath = useMemo(() => {
    if (!selectedIds?.size) return "";
    return visibleStrokes
      .filter((stroke) => stroke.id !== selectedId && selectedIds.has(stroke.id))
      .map((stroke) => {
        const points = planById.get(stroke.id)?.points ?? stroke.points;
        return points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" ");
      })
      .join(" ");
  }, [planById, selectedId, selectedIds, visibleStrokes]);
  const lineScale = Math.pow(zoom, 0.55);
  const physicalStrokeWidth = Math.max(1e-6, penWidthMm * width / targetWidthMm);
  const selectionOutlineWidth = Math.max(1, 7 / lineScale);
  const hitStrokeWidth = Math.max(1.4, 16 / Math.pow(zoom, 0.7));
  const endpointScale = Math.max(width, height) / zoom;
  const zoomLabel = zoom.toFixed(1);

  function selectFromDensePreview(event: ReactMouseEvent<SVGSVGElement>) {
    const target = clientPointInCanvas(event.currentTarget, event.clientX, event.clientY, width, height, viewport);
    if (!target) return onSelect(null);
    let nearest: { stroke: AuditStroke; segmentIndex: number; point: Point; distance: number } | null = null;
    for (const stroke of visibleStrokes) {
      const location = nearestPointOnStroke(stroke.points, target);
      if (!location) continue;
      const candidateDistance = Math.hypot(target[0] - location.point[0], target[1] - location.point[1]);
      if (!nearest || candidateDistance < nearest.distance) {
        nearest = { stroke, ...location, distance: candidateDistance };
      }
    }
    const tolerance = Math.max(viewport.width, viewport.height) * 0.018;
    if (!nearest || nearest.distance > tolerance) return onSelect(null);
    if (nearest.stroke.id === selectedId && splitMode) {
      onSplit(nearest.stroke.id, nearest.segmentIndex, nearest.point);
    } else {
      onSelect(nearest.stroke.id);
    }
  }

  return (
    <div ref={previewRef} className="stroke-preview-shell">
      {densePreview && <div className="dense-preview-note">高密度快速预览 · {visibleStrokes.length} 条</div>}
      <div className="stroke-zoom-controls" onPointerDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="缩小笔触画布" disabled={zoom <= 1} onClick={() => adjustZoom(-0.1)}>−</button>
        <output aria-label="当前缩放倍数">{zoomLabel}×</output>
        <button type="button" aria-label="放大笔触画布" disabled={zoom >= MAX_STROKE_ZOOM} onClick={() => adjustZoom(0.1)}>+</button>
        <button type="button" className="pan-toggle" aria-pressed={panMode} disabled={addMode || zoom <= 1} onClick={() => setPanMode((active) => !active)}>平移</button>
        <button type="button" aria-label="复位笔触画布" disabled={zoom <= 1} onClick={resetViewport}>复位</button>
        <button type="button" aria-label={isFullscreen ? "退出全屏" : "全屏显示笔触结果"} onClick={() => void toggleFullscreen()}>{isFullscreen ? "退出全屏" : "全屏"}</button>
      </div>
      <svg
      className={`stroke-canvas ${addMode ? "add-mode" : ""} ${panMode ? "pan-mode" : ""}`}
      viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`}
      role="img"
      aria-label={addMode ? "人工添加笔触画布" : "可审核笔触预览"}
      onClick={(event) => {
        if (addMode || panMode) return;
        if (densePreview) selectFromDensePreview(event);
        else onSelect(null);
      }}
      onWheel={handleWheel}
      onPointerDown={(event) => { if (!beginPan(event)) beginManualStroke(event); }}
      onPointerMove={(event) => { if (!continuePan(event)) continueManualStroke(event); }}
      onPointerUp={(event) => { if (!finishPan(event)) finishManualStroke(event); }}
      onPointerCancel={(event) => { if (!finishPan(event)) finishManualStroke(event); }}
    >
      <defs>
        <marker id="direction-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,5 L4.5,2.5 z" fill="context-stroke" />
        </marker>
      </defs>
      <rect width={width} height={height} fill="#fffdf8" />
      {batchedPaths && (Object.keys(batchedPaths) as Decision[]).map((decision) => batchedPaths[decision] && (
        <path
          key={decision}
          className={`stroke-visible batched ${decision === "discard" ? "discarded" : ""}`}
          d={batchedPaths[decision]}
          fill="none"
          stroke={colors[decision]}
          strokeWidth={physicalStrokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          pointerEvents="none"
        />
      ))}
      {densePreview && batchSelectionPath && <path className="stroke-batch-selection" d={batchSelectionPath} fill="none" stroke="#e53935" strokeWidth={Math.max(physicalStrokeWidth, selectionOutlineWidth / 3)} strokeLinecap="round" strokeLinejoin="round" pointerEvents="none" />}
      {individuallyRenderedStrokes.map((stroke) => {
        const planned = planById.get(stroke.id);
        const displayPoints = planned?.points ?? stroke.points;
        const points = displayPoints.map(([x, y]) => `${x},${y}`).join(" ");
        const [startX, startY] = displayPoints[0];
        const [endX, endY] = displayPoints[displayPoints.length - 1];
        const primarySelected = stroke.id === selectedId;
        const selected = primarySelected || Boolean(selectedIds?.has(stroke.id));
        const strokeColor = selected ? "#e53935" : colors[stroke.decision];
        return (
          <g
            key={stroke.id}
            className={`stroke-group ${stroke.decision === "discard" ? "discarded" : ""} ${selected ? "selected" : ""} ${primarySelected && splitMode ? "split-target" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={primarySelected && splitMode ? `点击笔触 ${stroke.id} 上的拆分位置` : `选择笔触 ${stroke.id}，当前状态 ${stroke.decision}`}
            onClick={(event) => {
              event.stopPropagation();
              if (addMode) return;
              if (primarySelected && splitMode) {
                const target = pointerInCanvas(event, width, height, viewport);
                const location = target ? nearestPointOnStroke(stroke.points, target) : null;
                if (location) onSplit(stroke.id, location.segmentIndex, location.point);
                return;
              }
              onSelect(stroke.id);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(stroke.id);
              }
            }}
          >
            <polyline className="stroke-hit-area" points={points} fill="none" stroke="transparent" strokeWidth={hitStrokeWidth} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            {selected && <polyline className="stroke-selection" points={points} fill="none" stroke="#ffffff" strokeWidth={selectionOutlineWidth} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />}
            <polyline className="stroke-visible" points={points} fill="none" stroke={strokeColor} strokeWidth={physicalStrokeWidth} strokeLinecap="round" strokeLinejoin="round" markerEnd={primarySelected ? "url(#direction-arrow)" : undefined} />
            {primarySelected && <>
              <circle cx={startX} cy={startY} r={endpointScale * 0.007} fill={strokeColor} stroke="#fff" strokeWidth={Math.max(0.5, 1.5 / lineScale)} vectorEffect="non-scaling-stroke" />
              <circle cx={endX} cy={endY} r={endpointScale * 0.004} fill="#fff" stroke={strokeColor} strokeWidth={Math.max(0.5, 1.5 / lineScale)} vectorEffect="non-scaling-stroke" />
            </>}
          </g>
        );
      })}
      {draftPoints.length >= 2 && <polyline className="manual-draft" points={draftPoints.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#315f9b" strokeWidth={physicalStrokeWidth} strokeLinecap="round" strokeLinejoin="round" />}
      </svg>
    </div>
  );
}

export default function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const processingControllerRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourcePreviewMessage, setSourcePreviewMessage] = useState<string | null>(null);
  const [parameters, setParameters] = useState(defaultParameters);
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedStrokeId, setSelectedStrokeId] = useState<string | null>(null);
  const [batchSelectionMode, setBatchSelectionMode] = useState(false);
  const [batchSelectedIds, setBatchSelectedIds] = useState<Set<string>>(() => new Set());
  const [showOnlyKeep, setShowOnlyKeep] = useState(false);
  const [showDeleted, setShowDeleted] = useState(false);
  const [splitMode, setSplitMode] = useState(false);
  const [splitMessage, setSplitMessage] = useState<string | null>(null);
  const [addMode, setAddMode] = useState(false);
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [positiveSelectionMode, setPositiveSelectionMode] = useState(false);
  const [positiveSelectionBaseline, setPositiveSelectionBaseline] = useState<ProcessResponse | null>(null);
  const [outlineSelectionMessage, setOutlineSelectionMessage] = useState<string | null>(null);
  const [providerOptions, setProviderOptions] = useState(defaultProviderOptions);

  useEffect(() => {
    let active = true;
    getCapabilities()
      .then((capabilities) => {
        if (active && capabilities.provider_options.length) setProviderOptions(capabilities.provider_options);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => () => processingControllerRef.current?.abort(), []);

  useEffect(() => {
    if (!file) {
      setSourceUrl(null);
      setSourcePreviewMessage(null);
      return;
    }
    let active = true;
    let createdUrl: string | null = null;
    setSourceUrl(null);
    setSourcePreviewMessage("正在生成轻量预览…");
    void createSourcePreviewUrl(file)
      .then((url) => {
        createdUrl = url;
        if (active) {
          setSourceUrl(url);
          setSourcePreviewMessage(null);
        } else {
          URL.revokeObjectURL(url);
        }
      })
      .catch((caught) => {
        if (active) setSourcePreviewMessage(caught instanceof Error ? caught.message : "无法生成原图预览");
      });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [file]);

  const counts = useMemo(() => {
    const initial = { keep: 0, uncertain: 0, discard: 0 };
    return result?.audit_document.strokes.reduce((acc, stroke) => {
      acc[stroke.decision] += 1;
      return acc;
    }, initial) ?? initial;
  }, [result]);

  const selectedStroke = useMemo(
    () => result?.audit_document.strokes.find((stroke) => stroke.id === selectedStrokeId) ?? null,
    [result, selectedStrokeId],
  );

  const selectedStrokeNumber = useMemo(() => {
    if (!result || !selectedStrokeId) return null;
    const index = result.audit_document.strokes.findIndex((stroke) => stroke.id === selectedStrokeId);
    return index >= 0 ? index + 1 : null;
  }, [result, selectedStrokeId]);

  const selectedDrawingOrder = useMemo(() => {
    if (!result || !selectedStrokeId) return null;
    return result.strokes_document.strokes.find((stroke) => stroke.id === selectedStrokeId)?.order ?? null;
  }, [result, selectedStrokeId]);

  const drawingPlan = useMemo(
    () => result?.strokes_document.strokes.map((stroke) => ({ ...stroke, reversed: false })) ?? [],
    [result],
  );

  const inputKind = file && (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) ? "svg" : "raster";
  const selectedProvider = providerOptions.find((provider) => provider.id === parameters.provider);
  const visibleParameters = getParameterVisibility(parameters.provider, inputKind);
  const parameterVisibilityNote = getParameterVisibilityNote(parameters.provider, inputKind);

  function chooseFile(nextFile: File | null) {
    if (!nextFile) return;
    processingControllerRef.current?.abort();
    setFile(nextFile);
    setResult(null);
    setSelectedStrokeId(null);
    setBatchSelectionMode(false);
    setBatchSelectedIds(new Set());
    setSplitMode(false);
    setSplitMessage(null);
    setAddMode(false);
    setAddMessage(null);
    setPositiveSelectionMode(false);
    setPositiveSelectionBaseline(null);
    setOutlineSelectionMessage(null);
    setError(null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    chooseFile(event.dataTransfer.files.item(0));
  }

  async function runProcessing() {
    if (!file || busy) return;
    if ((selectedProvider?.is_cloud || parameters.ai_semantic_review) && inputKind === "raster" && !window.confirm(
      "将使用千问云端服务：当前图片以及候选笔触预览会上传到阿里云百炼。未命中本地缓存时可能消耗额度或产生费用。是否继续？",
    )) return;
    const controller = new AbortController();
    processingControllerRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      setResult(applyOptimizedStrokeOrder(await processFile(file, parameters, controller.signal)));
      setSelectedStrokeId(null);
      setBatchSelectionMode(false);
      setBatchSelectedIds(new Set());
      setSplitMode(false);
      setSplitMessage(null);
      setAddMode(false);
      setAddMessage(null);
      setPositiveSelectionMode(false);
      setPositiveSelectionBaseline(null);
      setOutlineSelectionMessage(null);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError("已取消等待本次处理。服务器会在当前算法安全结束后恢复空闲。");
      } else {
        setError(caught instanceof Error ? caught.message : "处理失败");
      }
    } finally {
      if (processingControllerRef.current === controller) {
        processingControllerRef.current = null;
        setBusy(false);
      }
    }
  }

  function setSelectedDecision(decision: Decision) {
    if (!selectedStrokeId) return;
    setResult((current) => current ? updateStrokeDecision(current, selectedStrokeId, decision) : current);
    setBatchSelectedIds((current) => {
      if (!current.has(selectedStrokeId)) return current;
      const next = new Set(current);
      next.delete(selectedStrokeId);
      return next;
    });
    setSplitMode(false);
    setSplitMessage(null);
  }

  function selectStroke(strokeId: string | null) {
    if (batchSelectionMode) {
      if (!strokeId) return;
      const stroke = result?.audit_document.strokes.find((candidate) => candidate.id === strokeId);
      if (!stroke || stroke.decision !== "uncertain") return;
      setBatchSelectedIds((current) => {
        const next = new Set(current);
        if (next.has(strokeId)) next.delete(strokeId);
        else next.add(strokeId);
        return next;
      });
      setSelectedStrokeId(null);
      setSplitMode(false);
      setSplitMessage(null);
      return;
    }
    if (positiveSelectionMode && strokeId) {
      setResult((current) => {
        if (!current) return current;
        const stroke = current.audit_document.strokes.find((candidate) => candidate.id === strokeId);
        return stroke
          ? updateStrokeDecision(current, strokeId, stroke.decision === "keep" ? "uncertain" : "keep")
          : current;
      });
    }
    setSelectedStrokeId(strokeId);
    setSplitMode(false);
    setSplitMessage(null);
  }

  function toggleBatchSelectionMode() {
    setBatchSelectionMode((active) => !active);
    setBatchSelectedIds(new Set());
    setSelectedStrokeId(null);
    setPositiveSelectionMode(false);
    setSplitMode(false);
    setAddMode(false);
    setShowOnlyKeep(false);
    setShowDeleted(false);
  }

  function selectAllUncertainStrokes() {
    if (!result) return;
    setBatchSelectedIds(new Set(
      result.audit_document.strokes
        .filter((stroke) => stroke.decision === "uncertain")
        .map((stroke) => stroke.id),
    ));
    setSelectedStrokeId(null);
  }

  function applyBatchDecision(decision: Decision) {
    if (batchSelectedIds.size === 0) return;
    setResult((current) => current ? updateStrokeDecisions(current, batchSelectedIds, decision) : current);
    setBatchSelectedIds(new Set());
    setSelectedStrokeId(null);
  }

  function togglePositiveSelectionMode() {
    if (!result) return;
    if (positiveSelectionMode) {
      setPositiveSelectionMode(false);
      return;
    }
    const resumeExistingSession = positiveSelectionBaseline !== null;
    if (!resumeExistingSession) setPositiveSelectionBaseline(result);
    setResult(enterPositiveSelection(result, resumeExistingSession));
    setOutlineSelectionMessage(null);
    setPositiveSelectionMode(true);
    setBatchSelectionMode(false);
    setBatchSelectedIds(new Set());
    setShowOnlyKeep(false);
    setShowDeleted(false);
    setSelectedStrokeId(null);
    setSplitMode(false);
    setAddMode(false);
  }

  function finishPositiveSelectionSession() {
    setPositiveSelectionMode(false);
    setPositiveSelectionBaseline(null);
    setOutlineSelectionMessage(null);
    setSelectedStrokeId(null);
    setSplitMode(false);
    setAddMode(false);
  }

  function applyOuterContourSelection() {
    if (!result) return;
    const selected = selectOuterContourStrokes(result);
    if (!selected) {
      setOutlineSelectionMessage("当前结果没有可识别的外轮廓候选；请保留现有结果并用正向选择手动点选。");
      return;
    }
    if (!positiveSelectionBaseline) setPositiveSelectionBaseline(result);
    setResult(selected.result);
    setPositiveSelectionMode(false);
    setBatchSelectionMode(false);
    setBatchSelectedIds(new Set());
    setShowOnlyKeep(true);
    setShowDeleted(false);
    setSelectedStrokeId(null);
    setSplitMode(false);
    setAddMode(false);
    setOutlineSelectionMessage(`已只保留 ${selected.selectedCount} 条最外层轮廓；内部细节均转为待确认，不进入正式导出。`);
  }

  function restorePositiveSelectionBaseline() {
    if (!positiveSelectionBaseline) return;
    setResult(positiveSelectionBaseline);
    setPositiveSelectionMode(false);
    setBatchSelectionMode(false);
    setBatchSelectedIds(new Set());
    setPositiveSelectionBaseline(null);
    setOutlineSelectionMessage(null);
    setSelectedStrokeId(null);
    setSplitMode(false);
    setAddMode(false);
  }

  function splitStroke(strokeId: string, segmentIndex: number, point: Point) {
    if (!result) return;
    const split = splitStrokeAtPosition(result, strokeId, { segmentIndex, point });
    if (!split) {
      setSplitMessage("拆分点不能位于端点或过于靠近端点，请换一个位置。");
      return;
    }
    setResult(split.result);
    setSelectedStrokeId(split.strokeIds[0]);
    setSplitMode(false);
    setAddMode(false);
    setSplitMessage("拆分完成：原笔触已替换为前后两条独立笔触。");
  }

  function addStroke(points: Point[]) {
    if (!result) return;
    const added = addManualStroke(result, points);
    if (!added) {
      setAddMessage("绘制距离太短，没有创建笔触，请按住并拖动一段距离。");
      return;
    }
    setResult(added.result);
    setSelectedStrokeId(added.strokeId);
    setAddMessage("人工笔触已添加并默认保留，可继续绘制下一条。");
  }

  function exportStrokes() {
    if (!result) return;
    const count = uncertainCount(result.audit_document);
    if (count > 0 && !window.confirm(`当前仍有 ${count} 条 uncertain 笔触。它们不会进入正式 strokes.json，是否继续导出？`)) return;
    downloadJson("strokes.json", result.strokes_document);
  }

  function exportPythonStrokesZip() {
    if (!result) return;
    const count = uncertainCount(result.audit_document);
    if (count > 0 && !window.confirm(`当前仍有 ${count} 条 uncertain 笔触。压缩包只会包含 keep 笔触，是否继续？`)) return;
    if (!downloadPythonStrokesZip(result.strokes_document)) {
      setError("当前没有正式保留的笔触，无法生成 Python 压缩包。");
    }
  }

  return (
    <main>
      <header className="hero">
        <div>
          <p className="eyebrow">MOBILE ROBOT DRAWING PIPELINE</p>
          <h1>线稿预处理与笔触审核工具</h1>
          <p className="subtitle">本地经典算法、CPU 深度模型与千问云端 API · 参数修改后手动重新处理</p>
        </div>
        <span className="provider-badge">{result?.audit_document.processing.actual_provider.toUpperCase() ?? "LOCAL READY"}</span>
      </header>

      <section className="workspace-grid">
        <aside className="panel controls">
          <div>
            <p className="section-label">01 · 输入</p>
            <div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={onDrop} onClick={() => inputRef.current?.click()}>
              <input ref={inputRef} type="file" accept=".png,.jpg,.jpeg,.svg,image/png,image/jpeg,image/svg+xml" hidden onChange={(event) => chooseFile(event.target.files?.item(0) ?? null)} />
              <span className="upload-icon">↥</span>
              <strong>{file ? file.name : "拖放或选择作品"}</strong>
              <small>PNG · JPG · SVG，最大 25 MB</small>
            </div>
          </div>

          <div className="parameter-block">
            <p className="section-label">02 · 参数</p>
            <label className="field">
              <span>处理算法</span>
              <select value={parameters.provider} onChange={(event) => {
                const provider = event.target.value as ProcessingParameters["provider"];
                setParameters({
                  ...parameters,
                  provider,
                  ai_semantic_review: provider === "qwen_cloud" ? true : parameters.ai_semantic_review,
                });
              }}>
                {providerOptions.map((provider) => <option key={provider.id} value={provider.id} disabled={!provider.available}>{provider.label}{provider.available ? "" : "（未配置）"}</option>)}
              </select>
              <small className="provider-note">{selectedProvider?.description}</small>
            </label>
            {selectedProvider?.is_cloud && <div className="cloud-provider-notice" role="note">
              <strong>云端 API 模式</strong>
              <span>{selectedProvider.usage_notice}</span>
              {selectedProvider.availability_reason && <small>{selectedProvider.availability_reason}</small>}
            </div>}
            {visibleParameters.detailLevel && <ParameterSlider label="细节等级" value={parameters.detail_level} onChange={(value) => setParameters({ ...parameters, detail_level: value })} />}
            {visibleParameters.cleanupStrength && <ParameterSlider label="清理强度" value={parameters.cleanup_strength} onChange={(value) => setParameters({ ...parameters, cleanup_strength: value })} />}
            {visibleParameters.smoothing && <ParameterSlider label="平滑程度（兼容强度）" value={parameters.smoothing} onChange={(value) => setParameters({ ...parameters, smoothing: value })} />}
            {visibleParameters.canvasSize && <>
              <div className="number-grid canvas-size-grid">
                <label className="field"><span>画布宽度 mm</span><input type="number" min="1" value={parameters.target_width_mm} onChange={(event) => setParameters({ ...parameters, target_width_mm: Number(event.target.value) })} /></label>
                <label className="field"><span>画布高度 mm</span><input type="number" min="1" value={parameters.target_height_mm} onChange={(event) => setParameters({ ...parameters, target_height_mm: Number(event.target.value) })} /></label>
              </div>
              <p className="parameter-note">作品保持原始比例并居中放入画布，不会因画布宽高而拉伸。</p>
            </>}
            <div className="number-grid">
              {visibleParameters.penWidth && <label className="field"><span>笔头直径 mm</span><input type="number" min="0.05" max="100" step="0.05" value={parameters.pen_width_mm} onChange={(event) => setParameters({ ...parameters, pen_width_mm: Number(event.target.value) })} /></label>}
              {visibleParameters.minimumLength && <label className="field"><span>最小线长 mm</span><input type="number" min="0" step="0.1" value={parameters.minimum_length_mm} onChange={(event) => setParameters({ ...parameters, minimum_length_mm: Number(event.target.value) })} /></label>}
            </div>
            {visibleParameters.penWidth && <p className="parameter-note">长距离平行且落入一个笔头直径内的重复笔触会自动转为“待确认”，不会永久删除。</p>}
            {visibleParameters.maxStrokes && <label className="field">
              <span>自动保留最大笔数</span>
              <input type="number" min="1" max="5000" step="1" value={parameters.max_strokes} onChange={(event) => setParameters({ ...parameters, max_strokes: Math.max(1, Math.min(5000, Number(event.target.value))) })} />
              <small>只限制自动筛选；人工恢复、补画或拆分后可以超过此上限。</small>
            </label>}
            {visibleParameters.semanticReview && <div className="semantic-review-controls">
              <label className="visibility-toggle">
                <input type="checkbox" checked={parameters.ai_semantic_review} onChange={(event) => setParameters({ ...parameters, ai_semantic_review: event.target.checked })} />
                使用千问理解内容并判断笔触重要性
              </label>
              {parameters.ai_semantic_review && <>
                <label className="field">
                  <span>语义审核强度</span>
                  <select value={parameters.ai_review_quality} onChange={(event) => setParameters({ ...parameters, ai_review_quality: event.target.value as ProcessingParameters["ai_review_quality"] })}>
                    <option value="economy">经济（较少调用）</option>
                    <option value="standard">标准（推荐）</option>
                    <option value="fine">精细（审核更多候选）</option>
                  </select>
                </label>
                <label className="field">
                  <span>单次任务最多云端审核调用</span>
                  <input type="number" min="1" max="50" step="1" value={parameters.max_cloud_review_calls} onChange={(event) => setParameters({ ...parameters, max_cloud_review_calls: Math.max(1, Math.min(50, Number(event.target.value))) })} />
                </label>
                <p className="parameter-note">启用后，原图及候选笔触预览会上传给千问视觉模型；结果会缓存。接口失败时自动退回本地重要性判断。</p>
              </>}
            </div>}
            {visibleParameters.geometryControls && <div className="number-grid geometry-parameter-grid">
              <label className="field"><span>毛刺剪枝 mm</span><input type="number" min="0" step="0.1" value={parameters.spur_prune_length_mm} onChange={(event) => setParameters({ ...parameters, spur_prune_length_mm: Number(event.target.value) })} /></label>
              <label className="field"><span>平滑容差 mm</span><input type="number" min="0" step="0.05" value={parameters.smooth_tolerance_mm} onChange={(event) => setParameters({ ...parameters, smooth_tolerance_mm: Number(event.target.value) })} /></label>
              <label className="field"><span>几何误差 mm</span><input type="number" min="0.01" step="0.05" value={parameters.geometry_tolerance_mm} onChange={(event) => setParameters({ ...parameters, geometry_tolerance_mm: Number(event.target.value) })} /></label>
              <label className="field"><span>最大段长 mm</span><input type="number" min="0.1" step="0.5" value={parameters.max_segment_length_mm} onChange={(event) => setParameters({ ...parameters, max_segment_length_mm: Number(event.target.value) })} /></label>
            </div>}
            <p className="parameter-note">{parameterVisibilityNote}</p>
            <p className="parameter-note">调整参数不会自动请求服务器，请点击下方按钮。</p>
            <div className="processing-actions">
              <button className="primary-button" disabled={!file || busy || selectedProvider?.available === false} onClick={runProcessing}>{busy ? (selectedProvider?.is_cloud ? "云端生成并提取笔触中…" : "处理中…首次模型加载可能较慢") : result ? "重新处理" : "开始处理"}</button>
              {busy && <button className="cancel-processing-button" onClick={() => processingControllerRef.current?.abort()}>取消等待</button>}
            </div>
            {error && <p className="error-message">{error}</p>}
          </div>
        </aside>

        <section className="panel preview-panel">
          <div className="panel-heading">
            <div><p className="section-label">03 · 预览</p><h2>{result ? "处理结果" : "等待处理"}</h2></div>
            {result && <code>{result.processing_id}</code>}
          </div>
          <div className="preview-grid">
            <article className="preview-card">
              <h3>原始作品</h3>
              <div className="image-stage">{sourceUrl ? <img src={sourceUrl} alt="上传的原始作品" /> : <p>{sourcePreviewMessage ?? "上传文件后显示原图"}</p>}</div>
            </article>
            {result?.diagnostics && <article className="preview-card">
              <h3>二值线稿</h3>
              <div className="image-stage"><img src={result.diagnostics.binary_png_data_url} alt="二值线稿" /></div>
            </article>}
            {result?.diagnostics && <article className="preview-card">
              <h3>单像素骨架</h3>
              <div className="image-stage"><img src={result.diagnostics.skeleton_png_data_url} alt="单像素骨架" /></div>
            </article>}
            <article className="preview-card stroke-result-card">
              <h3>笔触结果</h3>
              <div className="image-stage">{result ? <StrokePreview strokes={result.audit_document.strokes} width={result.audit_document.canvas.width} height={result.audit_document.canvas.height} penWidthMm={result.audit_document.processing.parameters.pen_width_mm} targetWidthMm={result.audit_document.canvas.target_width_mm} selectedId={selectedStrokeId} selectedIds={batchSelectedIds} showOnlyKeep={showOnlyKeep} showDeleted={showDeleted} splitMode={splitMode} addMode={addMode} drawingPlan={drawingPlan} onSelect={selectStroke} onSplit={splitStroke} onAdd={addStroke} /> : <p>处理后显示结构化笔触</p>}</div>
            </article>
          </div>

          {result?.audit_document.selection_summary && <section className="selection-summary" aria-label="自动筛选摘要">
            <div><strong>{result.audit_document.selection_summary.automatic_keep_count}</strong><span>自动保留</span></div>
            <div><strong>{result.audit_document.selection_summary.recommended_min_strokes}</strong><span>建议至少</span></div>
            <div><strong>{result.audit_document.selection_summary.requested_max_strokes}</strong><span>用户上限</span></div>
            <div><strong>{(result.audit_document.selection_summary.achieved_coverage * 100).toFixed(1)}%</strong><span>有效墨迹覆盖</span></div>
            {result.audit_document.selection_summary.requested_max_strokes < result.audit_document.selection_summary.recommended_min_strokes && <p className="selection-warning">当前最大笔数低于建议下限，仍会严格采用你的上限；可在参数区提高。</p>}
          </section>}
          {result?.audit_document.semantic_review && result.audit_document.semantic_review.status !== "disabled" && <section className={`semantic-summary ${result.audit_document.semantic_review.status}`}>
            <strong>千问语义审核：{result.audit_document.semantic_review.status}</strong>
            <span>模型 {result.audit_document.semantic_review.model ?? "未配置"} · 调用 {result.audit_document.semantic_review.call_count} 次 · 缓存命中 {result.audit_document.semantic_review.cache_hit_count} 次</span>
            {result.audit_document.semantic_review.main_subjects.length > 0 && <span>主体：{result.audit_document.semantic_review.main_subjects.join("、")}</span>}
            {result.audit_document.semantic_review.message && <small>{result.audit_document.semantic_review.message}</small>}
          </section>}
          <div className="legend"><span><i className="keep-dot" />keep</span><span><i className="uncertain-dot" />uncertain</span><span><i className="discard-dot" />已删除</span></div>
          <section className="review-panel" aria-label="笔触审核">
            <div className="review-heading">
              <div>
                <strong>笔触审核</strong>
                <p>点击画面中的线条，再选择是否进入正式导出。</p>
              </div>
              <div className="review-filters">
                <label className="visibility-toggle">
                  <input type="checkbox" checked={showDeleted} disabled={batchSelectionMode} onChange={(event) => setShowDeleted(event.target.checked)} />
                  显示已删除笔触
                </label>
                <label className="visibility-toggle">
                  <input type="checkbox" checked={showOnlyKeep} disabled={batchSelectionMode} onChange={(event) => setShowOnlyKeep(event.target.checked)} />
                  只显示正式保留效果
                </label>
              </div>
            </div>
            <div className="batch-selection-controls">
              <button
                className="batch-selection-button"
                aria-pressed={batchSelectionMode}
                disabled={!result || (!batchSelectionMode && counts.uncertain === 0)}
                onClick={toggleBatchSelectionMode}
              >
                {batchSelectionMode ? "结束批量选择" : "批量选择待确认笔触"}
              </button>
              {batchSelectionMode && <>
                <button className="batch-select-all-button" disabled={counts.uncertain === 0} onClick={selectAllUncertainStrokes}>全选待确认</button>
                <button
                  className="batch-clear-button"
                  disabled={batchSelectedIds.size === 0}
                  onClick={() => {
                    setBatchSelectedIds(new Set());
                    setSelectedStrokeId(null);
                  }}
                >
                  清空选择
                </button>
                <strong className="batch-selection-count">已选择 {batchSelectedIds.size} 条</strong>
                <div className="batch-decision-actions" role="group" aria-label="批量修改笔触状态">
                  <button className="decision-button keep" disabled={batchSelectedIds.size === 0} onClick={() => applyBatchDecision("keep")}>一起保留</button>
                  <button className="decision-button uncertain" disabled={batchSelectedIds.size === 0} onClick={() => applyBatchDecision("uncertain")}>一起待确认</button>
                  <button className="decision-button discard" disabled={batchSelectedIds.size === 0} onClick={() => applyBatchDecision("discard")}>一起删除</button>
                </div>
                <p>只选择橙色待确认笔触；逐条点击可选中或取消，也可以一次全选。</p>
              </>}
            </div>
            <div className="positive-selection-controls">
              <button
                className="positive-selection-button"
                aria-pressed={positiveSelectionMode}
                disabled={!result}
                onClick={togglePositiveSelectionMode}
              >
                {positiveSelectionMode
                  ? "暂存并编辑"
                  : positiveSelectionBaseline
                    ? "继续正向选择"
                    : "全不选并开始正选"}
              </button>
              <button className="outline-selection-button" disabled={!result} onClick={applyOuterContourSelection}>只选极简外轮廓</button>
              {positiveSelectionBaseline && <button className="selection-save-button" onClick={finishPositiveSelectionSession}>完成并保存选择</button>}
              {positiveSelectionBaseline && <button className="restore-selection-button" onClick={restorePositiveSelectionBaseline}>恢复开始前状态</button>}
              <p>{outlineSelectionMessage ?? (positiveSelectionMode
                ? "正向选择已开启：点击候选笔触可切换保留；需要补画或拆分时点击“暂存并编辑”。"
                : positiveSelectionBaseline
                  ? "选择进度已暂存。现在可以补画、拆分或修改状态；之后点击“继续正向选择”会从当前结果接着选。"
                  : "“极简外轮廓”会检查原图中线条两侧的颜色差；两侧近色的五官、纹理和内部墨线不会入选（线稿模式除外）。")}</p>
            </div>
            <div className="manual-add-controls">
              <button
                className="add-stroke-button"
                aria-pressed={addMode}
                onClick={() => {
                  setAddMode((active) => !active);
                  setPositiveSelectionMode(false);
                  setBatchSelectionMode(false);
                  setBatchSelectedIds(new Set());
                  setOutlineSelectionMessage(null);
                  setSplitMode(false);
                  setSplitMessage(null);
                  setAddMessage(null);
                }}
              >
                {addMode ? "结束添加" : "人工添加笔触"}
              </button>
              <p>{addMode ? "添加模式已开启：在上方笔触画布中按住鼠标或触控笔拖动。" : "可以直接在笔触画布上补画新的连续笔触。"}</p>
            </div>
            {addMessage && <p className="add-message" role="status">{addMessage}</p>}
            {selectedStroke ? (
              <div className="selected-stroke">
                <div className="selected-details">
                  {selectedStrokeNumber !== null && <strong className="selected-stroke-number">候选编号 #{selectedStroke.source_order ?? selectedStrokeNumber}</strong>}
                  {selectedStroke.importance_rank != null && <span>重要性排名 #{selectedStroke.importance_rank}</span>}
                  <span>正式绘制顺序 {selectedDrawingOrder == null ? "未进入正式输出" : `#${selectedDrawingOrder}`}</span>
                  <code>{selectedStroke.id}</code>
                  <span>{selectedStroke.length_mm.toFixed(2)} mm</span>
                  <span>置信度 {(selectedStroke.confidence * 100).toFixed(0)}%</span>
                  <span className={`decision-label ${selectedStroke.decision}`}>{selectedStroke.decision}</span>
                </div>
                {(selectedStroke.semantic_role || selectedStroke.model_reason) && <div className="semantic-stroke-detail">
                  {selectedStroke.semantic_role && <strong>语义角色：{selectedStroke.semantic_role}</strong>}
                  {selectedStroke.model_reason && <p>{selectedStroke.model_reason}</p>}
                  <small>综合重要性 {((selectedStroke.scores.importance ?? 0) * 100).toFixed(0)}% · 新增覆盖 {((selectedStroke.scores.marginal_coverage ?? 0) * 100).toFixed(0)}% · 语义重要性 {((selectedStroke.scores.semantic_importance ?? 0) * 100).toFixed(0)}%</small>
                </div>}
                <div className="decision-actions" role="group" aria-label="修改笔触状态">
                  <button className="decision-button keep" aria-pressed={selectedStroke.decision === "keep"} onClick={() => setSelectedDecision("keep")}>保留</button>
                  <button className="decision-button uncertain" aria-pressed={selectedStroke.decision === "uncertain"} onClick={() => setSelectedDecision("uncertain")}>待确认</button>
                  <button className="decision-button discard" aria-pressed={selectedStroke.decision === "discard"} onClick={() => setSelectedDecision("discard")}>删除</button>
                </div>
                <div className="split-controls">
                  <button
                    className="split-button"
                    aria-pressed={splitMode}
                    disabled={(selectedStroke.decision === "discard" && !showDeleted) || (showOnlyKeep && selectedStroke.decision !== "keep")}
                    onClick={() => {
                      setSplitMode((active) => !active);
                      setPositiveSelectionMode(false);
                      setBatchSelectionMode(false);
                      setBatchSelectedIds(new Set());
                      setOutlineSelectionMessage(null);
                      setAddMode(false);
                      setAddMessage(null);
                      setSplitMessage(null);
                    }}
                  >
                    {splitMode ? "取消拆分" : "拆分笔触"}
                  </button>
                  <p>{splitMode ? "拆分模式已开启：请直接点击选中线条上希望断开的位置。" : "可在这条笔触的任意位置拆成前后两条。"}</p>
                </div>
                {splitMessage && <p className="split-message" role="status">{splitMessage}</p>}
                {selectedStroke.decision === "discard" && !showDeleted && <p className="hidden-stroke-note">这条笔触已删除并从画面隐藏，点击“保留”可立即恢复。</p>}
                {selectedStroke.decision === "uncertain" && showOnlyKeep && <p className="hidden-stroke-note">这条待确认笔触已从正式效果中隐藏，点击“保留”可恢复。</p>}
              </div>
            ) : (
              <p className="review-empty">尚未选择笔触。所有彩色线条都可以选择并删除；打开“显示已删除笔触”可恢复误删内容。</p>
            )}
          </section>
          <div className="stats">
            <div><strong>{counts.keep}</strong><span>正式笔触</span></div>
            <div><strong>{counts.uncertain}</strong><span>待确认</span></div>
            <div><strong>{counts.discard}</strong><span>已删除</span></div>
            <div><strong>{result?.audit_document.strokes.reduce((sum, stroke) => sum + stroke.length_mm, 0).toFixed(1) ?? "0.0"}</strong><span>总长 mm</span></div>
          </div>

          <div className="export-bar">
            <div><strong>正式导出仅包含 keep</strong><p>uncertain 与 discard 只保存在 audit.json。</p></div>
            <div className="export-actions">
              <button className="secondary-button" disabled={!result} onClick={() => result && downloadJson("audit.json", result.audit_document)}>导出 audit.json</button>
              <button className="primary-button compact" disabled={!result} onClick={exportStrokes}>导出 strokes.json</button>
              <button className="primary-button compact" disabled={!result || result.strokes_document.strokes.length === 0} onClick={exportPythonStrokesZip}>导出逐笔 Python ZIP</button>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
