import type { AuditDocument, StrokesDocument } from "./types";
import { strToU8, zipSync } from "fflate";
import type { Zippable } from "fflate";

export function uncertainCount(audit: AuditDocument): number {
  return audit.strokes.filter((stroke) => stroke.decision === "uncertain").length;
}

function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadJson(filename: string, value: StrokesDocument | AuditDocument): void {
  downloadBlob(filename, new Blob([JSON.stringify(value, null, 2) + "\n"], {
    type: "application/json;charset=utf-8",
  }));
}

export function strokePythonSource(stroke: StrokesDocument["strokes"][number]): string {
  return `#笔画编号 ${stroke.order}\n# version: Python3\npoints = ${JSON.stringify(stroke.points, null, 2)}\n`;
}

export function buildPythonStrokeFiles(document: StrokesDocument): Record<string, Uint8Array> {
  const width = Math.max(4, String(document.strokes.length).length);
  return Object.fromEntries(
    [...document.strokes]
      .sort((first, second) => first.order - second.order)
      .map((stroke) => [
        `stroke_${String(stroke.order).padStart(width, "0")}.py`,
        // TextEncoder can return a typed array from another JS realm (notably
        // embedded WebViews/test DOMs). Normalize it so ZIP libraries recognize
        // this as file data instead of recursively treating byte indexes as folders.
        new Uint8Array(strToU8(strokePythonSource(stroke))),
      ]),
  );
}

export function buildPythonStrokesZip(document: StrokesDocument): Uint8Array {
  const entries: Zippable = {};
  for (const [filename, data] of Object.entries(buildPythonStrokeFiles(document))) {
    entries[filename] = [data, { level: 6 }];
  }
  return zipSync(entries);
}

export function downloadPythonStrokesZip(document: StrokesDocument): boolean {
  if (!document.strokes.length) return false;
  const archive = buildPythonStrokesZip(document);
  downloadBlob("strokes_python.zip", new Blob([archive.buffer as ArrayBuffer], {
    type: "application/zip",
  }));
  return true;
}
