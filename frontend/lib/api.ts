import type { DeepSeekReport, DemoResponse, HealthResponse, ResearchResult } from "./types";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Research API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/api/research/health");
}

export function fetchDemo(): Promise<DemoResponse> {
  return fetchJson<DemoResponse>("/api/research/demo");
}

export function fetchMockReport(result: ResearchResult): Promise<DeepSeekReport> {
  return fetchJson<DeepSeekReport>("/api/research/deepseek/mock-report", {
    method: "POST",
    body: JSON.stringify(result)
  });
}
