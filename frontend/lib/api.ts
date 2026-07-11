import type {
  DeepSeekReport,
  DemoResponse,
  HealthResponse,
  ResearchBenchmarkCurveResponse,
  ResearchEquityCurveResponse,
  ResearchFactorsResponse,
  ResearchHoldingsResponse,
  ResearchResult,
  ResearchRunDetail,
  ResearchRunListResponse,
  ResearchWarningsResponse
} from "./types";

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

export function fetchResearchRuns(limit = 50): Promise<ResearchRunListResponse> {
  return fetchJson<ResearchRunListResponse>(`/api/research/runs?limit=${limit}`);
}

export function fetchLatestResearchRun(): Promise<ResearchRunDetail> {
  return fetchJson<ResearchRunDetail>("/api/research/runs/latest");
}

export function fetchResearchRun(runId: string): Promise<ResearchRunDetail> {
  return fetchJson<ResearchRunDetail>(`/api/research/runs/${encodeURIComponent(runId)}`);
}

export function fetchResearchEquity(runId: string): Promise<ResearchEquityCurveResponse> {
  return fetchJson<ResearchEquityCurveResponse>(
    `/api/research/runs/${encodeURIComponent(runId)}/equity-curve?downsample=800`
  );
}

export function fetchResearchBenchmark(runId: string): Promise<ResearchBenchmarkCurveResponse> {
  return fetchJson<ResearchBenchmarkCurveResponse>(
    `/api/research/runs/${encodeURIComponent(runId)}/benchmark-curve?downsample=800`
  );
}

export function fetchResearchHoldings(runId: string): Promise<ResearchHoldingsResponse> {
  return fetchJson<ResearchHoldingsResponse>(
    `/api/research/runs/${encodeURIComponent(runId)}/holdings?limit=500`
  );
}

export function fetchResearchFactors(runId: string): Promise<ResearchFactorsResponse> {
  return fetchJson<ResearchFactorsResponse>(
    `/api/research/runs/${encodeURIComponent(runId)}/factors?limit=1000`
  );
}

export function fetchResearchWarnings(runId: string): Promise<ResearchWarningsResponse> {
  return fetchJson<ResearchWarningsResponse>(
    `/api/research/runs/${encodeURIComponent(runId)}/warnings?sample_limit=3&raw_limit=20`
  );
}
