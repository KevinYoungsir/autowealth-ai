"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { fetchDemo, fetchHealth, fetchMockReport } from "@/lib/api";
import type { DeepSeekReport, DemoResponse, HealthResponse } from "@/lib/types";

type ResearchDataContextValue = {
  health: HealthResponse | null;
  demo: DemoResponse | null;
  report: DeepSeekReport | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const ResearchDataContext = createContext<ResearchDataContextValue | null>(null);

export function ResearchDataProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demo, setDemo] = useState<DemoResponse | null>(null);
  const [report, setReport] = useState<DeepSeekReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthResponse, demoResponse] = await Promise.all([
        fetchHealth(),
        fetchDemo()
      ]);
      const reportResponse = await fetchMockReport(demoResponse.result);
      setHealth(healthResponse);
      setDemo(demoResponse);
      setReport(reportResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Research API unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ health, demo, report, loading, error, refresh }),
    [health, demo, report, loading, error, refresh]
  );

  return (
    <ResearchDataContext.Provider value={value}>
      {children}
    </ResearchDataContext.Provider>
  );
}

export function useResearchData() {
  const context = useContext(ResearchDataContext);
  if (!context) {
    throw new Error("useResearchData must be used inside ResearchDataProvider");
  }
  return context;
}
