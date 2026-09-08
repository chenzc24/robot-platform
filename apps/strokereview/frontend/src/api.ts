import type { Capabilities, ProcessResponse, ProcessingParameters } from "./types";

export async function getCapabilities(): Promise<Capabilities> {
  const response = await fetch("/api/v1/capabilities");
  if (!response.ok) throw new Error(`无法读取处理算法（HTTP ${response.status}）`);
  return response.json() as Promise<Capabilities>;
}

export async function processFile(
  file: File,
  parameters: ProcessingParameters,
  signal?: AbortSignal,
): Promise<ProcessResponse> {
  const body = new FormData();
  body.set("file", file);
  body.set("parameters", JSON.stringify(parameters));
  const response = await fetch("/api/v1/process", { method: "POST", body, signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `处理失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<ProcessResponse>;
}
