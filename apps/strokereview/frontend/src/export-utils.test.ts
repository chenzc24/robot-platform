import { describe, expect, it } from "vitest";
import { strFromU8, unzipSync } from "fflate";
import { buildPythonStrokeFiles, buildPythonStrokesZip, strokePythonSource, uncertainCount } from "./export-utils";
import type { AuditDocument, StrokesDocument } from "./types";

const audit = {
  strokes: [
    { decision: "keep" },
    { decision: "uncertain" },
    { decision: "discard" },
    { decision: "uncertain" },
  ],
} as unknown as AuditDocument;

describe("export safeguards", () => {
  it("counts uncertain strokes before official export", () => {
    expect(uncertainCount(audit)).toBe(2);
  });

  it("creates one ordered Python file per official stroke", () => {
    const document = {
      strokes: [
        { id: "b", order: 2, points: [[0.3, 0.4], [0.5, 0.6]], closed: false },
        { id: "a", order: 1, points: [[0.1, 0.2], [0.2, 0.3]], closed: false },
      ],
    } as unknown as StrokesDocument;

    const files = buildPythonStrokeFiles(document);
    expect(Object.keys(files)).toEqual(["stroke_0001.py", "stroke_0002.py"]);
    expect(strFromU8(files["stroke_0001.py"])).toBe(strokePythonSource(document.strokes[1]));
    expect(strFromU8(files["stroke_0001.py"])).toContain(
      "#笔画编号 1\n# version: Python3\npoints = [\n",
    );
  });

  it("produces files accepted by a ZIP reader", () => {
    const document = {
      strokes: [{ id: "a", order: 1, points: [[0, 0], [1, 1]], closed: false }],
    } as unknown as StrokesDocument;
    // Use the same file map consumed by the download function and verify its
    // UTF-8 content survives an actual ZIP round trip.
    const archive = unzipSync(buildPythonStrokesZip(document));
    expect(Object.keys(archive)).toEqual(["stroke_0001.py"]);
    expect(strFromU8(archive["stroke_0001.py"])).toContain("points = [");
  });
});
