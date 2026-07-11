"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import {
  fetchDemo,
  fetchHealth,
  fetchMockReport,
  fetchLatestResearchRun,
  fetchResearchBenchmark,
  fetchResearchEquity,
  fetchResearchFactors,
  fetchResearchHoldings,
  fetchResearchRun,
  fetchResearchRuns,
  fetchResearchWarnings
} from "@/lib/api";
import type {
  DeepSeekReport,
  DemoResponse,
  HealthResponse,
  ResearchBenchmarkCurveResponse,
  ResearchDataSource,
  ResearchEquityCurveResponse,
  ResearchFactorsResponse,
  ResearchHoldingsResponse,
  ResearchRunDetail,
  ResearchRunSummary,
  ResearchWarningsResponse
} from "@/lib/types";

type ResearchDataContextValue = {
  health: HealthResponse | null;
  demo: DemoResponse | null;
  report: DeepSeekReport | null;
  runList: ResearchRunSummary[];
  selectedRunId: string | null;
  realDetail: ResearchRunDetail | null;
  realEquity: ResearchEquityCurveResponse | null;
  realBenchmark: ResearchBenchmarkCurveResponse | null;
  realHoldings: ResearchHoldingsResponse | null;
  realFactors: ResearchFactorsResponse | null;
  realWarnings: ResearchWarningsResponse | null;
  dataSource: ResearchDataSource;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  selectRun: (runId: string) => Promise<void>;
};

const ResearchDataContext = createContext<ResearchDataContextValue | null>(null);

export function ResearchDataProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demo, setDemo] = useState<DemoResponse | null>(null);
  const [report, setReport] = useState<DeepSeekReport | null>(null);
  const [runList, setRunList] = useState<ResearchRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [realDetail, setRealDetail] = useState<ResearchRunDetail | null>(null);
  const [realEquity, setRealEquity] = useState<ResearchEquityCurveResponse | null>(null);
  const [realBenchmark, setRealBenchmark] = useState<ResearchBenchmarkCurveResponse | null>(null);
  const [realHoldings, setRealHoldings] = useState<ResearchHoldingsResponse | null>(null);
  const [realFactors, setRealFactors] = useState<ResearchFactorsResponse | null>(null);
  const [realWarnings, setRealWarnings] = useState<ResearchWarningsResponse | null>(null);
  const [dataSource, setDataSource] = useState<ResearchDataSource>("api_unavailable");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMockReview = useCallback(async () => {
    const demoResponse = await fetchDemo();
    setDemo(demoResponse);
    setReport(await fetchMockReport(demoResponse.result));
  }, []);

  const loadRealRun = useCallback(async (
    runId: string,
    preloadedDetail?: ResearchRunDetail
  ) => {
    const [detail, equity, benchmark, holdings, factors, warnings] = await Promise.all([
      preloadedDetail ?? fetchResearchRun(runId),
      fetchResearchEquity(runId),
      fetchResearchBenchmark(runId),
      fetchResearchHoldings(runId),
      fetchResearchFactors(runId),
      fetchResearchWarnings(runId)
    ]);
    setSelectedRunId(runId);
    setRealDetail(detail);
    setRealEquity(equity);
    setRealBenchmark(benchmark);
    setRealHoldings(holdings);
    setRealFactors(factors);
    setRealWarnings(warnings);
    setDataSource("real_artifacts");
  }, []);

  const selectRun = useCallback(
    async (runId: string) => {
      setLoading(true);
      setError(null);
      try {
        await loadRealRun(runId);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "研究运行读取失败");
      } finally {
        setLoading(false);
      }
    },
    [loadRealRun]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await fetchHealth());
      const runs = await fetchResearchRuns();
      setRunList(runs.runs);
      if (runs.runs.length > 0) {
        const latest = await fetchLatestResearchRun();
        await loadRealRun(latest.summary.run_id, latest);
        try {
          await loadMockReview();
        } catch {
          setDemo(null);
          setReport(null);
        }
      } else {
        await loadMockReview();
        setSelectedRunId(null);
        setRealDetail(null);
        setRealEquity(null);
        setRealBenchmark(null);
        setRealHoldings(null);
        setRealFactors(null);
        setRealWarnings(null);
        setDataSource("mock_demo");
      }
    } catch (caught) {
      try {
        await loadMockReview();
        setDataSource("mock_demo");
        setError("真实研究运行不可用，当前显示演示数据");
      } catch {
        setDataSource("api_unavailable");
        setError(caught instanceof Error ? caught.message : "Research API unavailable");
      }
    } finally {
      setLoading(false);
    }
  }, [loadMockReview, loadRealRun]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({
      health,
      demo,
      report,
      runList,
      selectedRunId,
      realDetail,
      realEquity,
      realBenchmark,
      realHoldings,
      realFactors,
      realWarnings,
      dataSource,
      loading,
      error,
      refresh,
      selectRun
    }),
    [
      health,
      demo,
      report,
      runList,
      selectedRunId,
      realDetail,
      realEquity,
      realBenchmark,
      realHoldings,
      realFactors,
      realWarnings,
      dataSource,
      loading,
      error,
      refresh,
      selectRun
    ]
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
