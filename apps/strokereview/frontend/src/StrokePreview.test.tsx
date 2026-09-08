import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StrokePreview } from "./App";
import type { AuditStroke } from "./types";

const stroke = {
  id: "stroke_visible",
  source: "raster",
  source_ref: null,
  source_order: null,
  points: [[0.1, 0.2], [0.5, 0.4], [0.9, 0.7]],
  closed: false,
  confidence: 0.9,
  decision: "keep",
  decision_source: "algorithm",
  reversible: true,
  reasons: [],
  scores: { risk: 0.1, line_confidence: 0.9 },
  length_mm: 20,
} as AuditStroke;

describe("stroke preview", () => {
  it("renders line width from the physical pen diameter", () => {
    const { container } = render(
      <StrokePreview strokes={[stroke]} width={1} height={1} penWidthMm={1} targetWidthMm={200} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    const line = container.querySelector(".stroke-visible");
    expect(line).toHaveAttribute("stroke-width", "0.005");
    expect(line).not.toHaveAttribute("vector-effect");
    expect(container.querySelector(".stroke-order-label")).not.toBeInTheDocument();
    expect(container.querySelectorAll("circle")).toHaveLength(0);
  });

  it("batches thousands of strokes instead of creating thousands of SVG groups", () => {
    const dense = Array.from({ length: 1201 }, (_, index) => ({
      ...stroke,
      id: `stroke_${index}`,
      points: [[index / 1201, 0.1], [index / 1201, 0.9]] as AuditStroke["points"],
    }));
    const { container } = render(
      <StrokePreview strokes={dense} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );

    expect(container.querySelector(".dense-preview-note")).toHaveTextContent("1201 条");
    expect(container.querySelectorAll(".stroke-group")).toHaveLength(0);
    expect(container.querySelectorAll(".stroke-visible.batched")).toHaveLength(1);
  });

  it("selects a line and shows its endpoints and direction", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <StrokePreview strokes={[stroke]} width={1} height={1} selectedId="stroke_visible" showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={onSelect} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    fireEvent.click(container.querySelector(".stroke-visible")!);
    expect(onSelect).toHaveBeenCalledWith("stroke_visible");
    expect(container.querySelector(".stroke-visible")).toHaveAttribute("marker-end", "url(#direction-arrow)");
    expect(container.querySelector(".stroke-visible")).toHaveAttribute("stroke", "#e53935");
    expect(container.querySelectorAll("circle")[0]).toHaveAttribute("fill", "#e53935");
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("highlights several batch-selected strokes at the same time", () => {
    const second = {
      ...stroke,
      id: "stroke_second",
      points: [[0.1, 0.8], [0.9, 0.3]] as AuditStroke["points"],
      decision: "uncertain" as const,
    };
    const { container } = render(
      <StrokePreview strokes={[{ ...stroke, decision: "uncertain" }, second]} width={1} height={1} selectedId="stroke_second" selectedIds={new Set(["stroke_visible", "stroke_second"])} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );

    expect(container.querySelectorAll(".stroke-group.selected")).toHaveLength(2);
    expect(Array.from(container.querySelectorAll(".stroke-visible")).every((line) => line.getAttribute("stroke") === "#e53935")).toBe(true);
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("adjusts zoom while preserving the physical pen width", () => {
    const { container } = render(
      <StrokePreview strokes={[stroke]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    const svg = container.querySelector("svg")!;
    const initialViewBox = svg.getAttribute("viewBox");
    const zoomIn = container.querySelector('[aria-label="放大笔触画布"]')!;
    const zoomOut = container.querySelector('[aria-label="缩小笔触画布"]')!;
    fireEvent.click(zoomIn);
    fireEvent.click(zoomIn);
    fireEvent.click(zoomIn);
    expect(container.querySelector('[aria-label="当前缩放倍数"]')).toHaveTextContent("1.3×");
    fireEvent.click(zoomOut);
    expect(container.querySelector('[aria-label="当前缩放倍数"]')).toHaveTextContent("1.2×");

    for (let index = 0; index < 20; index += 1) fireEvent.wheel(svg, { deltaY: -100, clientX: 50, clientY: 50 });

    expect(container.querySelector('[aria-label="当前缩放倍数"]')).toHaveTextContent("128.0×");
    expect(svg.getAttribute("viewBox")).not.toBe(initialViewBox);
    expect(container.querySelector(".stroke-visible")).toHaveAttribute("stroke-width", "0.002380952380952381");
    expect(Number(container.querySelector(".stroke-hit-area")!.getAttribute("stroke-width"))).toBeLessThanOrEqual(1.5);

    fireEvent.click(container.querySelector('[aria-label="复位笔触画布"]')!);
    expect(container.querySelector('[aria-label="当前缩放倍数"]')).toHaveTextContent("1.0×");
    expect(container.querySelector(".stroke-visible")).toHaveAttribute("stroke-width", "0.002380952380952381");
  });

  it("enters fullscreen on the surrounding preview panel so review controls remain available", async () => {
    const { container } = render(
      <section className="preview-panel">
        <StrokePreview strokes={[stroke]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />
        <div aria-label="笔触审核">审核操作</div>
      </section>,
    );
    const panel = container.querySelector(".preview-panel")!;
    const requestFullscreen = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(panel, "requestFullscreen", { configurable: true, value: requestFullscreen });

    fireEvent.click(container.querySelector('[aria-label="全屏显示笔触结果"]')!);

    expect(requestFullscreen).toHaveBeenCalledTimes(1);
    expect(panel.querySelector('[aria-label="笔触审核"]')).toBeInTheDocument();
  });

  it("hides discarded strokes in official-result view", () => {
    const discarded = { ...stroke, decision: "discard" as const };
    const { container } = render(
      <StrokePreview strokes={[discarded]} width={1} height={1} selectedId={null} showOnlyKeep showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    expect(container.querySelector(".stroke-visible")).not.toBeInTheDocument();
  });

  it("hides deleted strokes by default and can reveal them for recovery", () => {
    const discarded = { ...stroke, decision: "discard" as const };
    const { container, rerender } = render(
      <StrokePreview strokes={[discarded]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    expect(container.querySelector(".stroke-visible")).not.toBeInTheDocument();
    rerender(
      <StrokePreview strokes={[discarded]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted splitMode={false} addMode={false} onSelect={() => undefined} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    expect(container.querySelector(".stroke-visible")).toBeInTheDocument();
  });

  it("shows uncertain strokes for review and hides them in official-result view", () => {
    const uncertain = { ...stroke, decision: "uncertain" as const };
    const onSelect = vi.fn();
    const { container, rerender } = render(
      <StrokePreview strokes={[uncertain]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode={false} onSelect={onSelect} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    const line = container.querySelector(".stroke-visible")!;
    expect(line).toHaveAttribute("stroke", "#f5a524");
    fireEvent.click(line);
    expect(onSelect).toHaveBeenCalledWith("stroke_visible");
    rerender(
      <StrokePreview strokes={[uncertain]} width={1} height={1} selectedId={null} showOnlyKeep showDeleted={false} splitMode={false} addMode={false} onSelect={onSelect} onSplit={() => undefined} onAdd={() => undefined} />,
    );
    expect(container.querySelector(".stroke-visible")).not.toBeInTheDocument();
  });

  it("projects a click onto the selected stroke in split mode", () => {
    const onSplit = vi.fn();
    const { container } = render(
      <StrokePreview strokes={[stroke]} width={1} height={1} selectedId="stroke_visible" showOnlyKeep={false} showDeleted={false} splitMode addMode={false} onSelect={() => undefined} onSplit={onSplit} onAdd={() => undefined} />,
    );
    const svg = container.querySelector("svg")!;
    vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.click(container.querySelector(".stroke-visible")!, { clientX: 50, clientY: 40 });
    expect(onSplit).toHaveBeenCalledWith("stroke_visible", 0, [0.5, 0.4]);
  });

  it("collects a dragged manual stroke in add mode", () => {
    const onAdd = vi.fn();
    const { container } = render(
      <StrokePreview strokes={[]} width={1} height={1} selectedId={null} showOnlyKeep={false} showDeleted={false} splitMode={false} addMode onSelect={() => undefined} onSplit={() => undefined} onAdd={onAdd} />,
    );
    const svg = container.querySelector("svg")!;
    vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.pointerDown(svg, { clientX: 10, clientY: 20, pointerId: 1 });
    fireEvent.pointerMove(svg, { clientX: 50, clientY: 40, pointerId: 1 });
    fireEvent.pointerUp(svg, { clientX: 90, clientY: 70, pointerId: 1 });
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd.mock.calls[0][0]).toEqual([[0.1, 0.2], [0.5, 0.4], [0.9, 0.7]]);
  });
});
