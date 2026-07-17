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
  fetchResearchReport,
  fetchResearchRun,
  fetchResearchRuns,
  fetchResearchWarnings
} from "@/lib/api";
import { loadResearchReportForSource } from "@/lib/research-report-loader";
import type {
  DemoResponse,
  HealthResponse,
  ResearchBenchmarkCurveResponse,
  ResearchDataSource,
  ResearchEquityCurveResponse,
  ResearchFactorsResponse,
  ResearchHoldingsResponse,
  ResearchReport,
  ResearchRunDetail,
  ResearchRunSummary,
  ResearchWarningsResponse
} from "@/lib/types";

type ResearchDataContextValue = {
  health: HealthResponse | null;
  demo: DemoResponse | null;
  report: ResearchReport | null;
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
  reportLoading: boolean;
  reportError: string | null;
  lastApiCheck: {
    checkedAt: string;
    status: "ok" | "degraded" | "unavailable";
    message: string;
  } | null;
  refresh: () => Promise<void>;
  selectRun: (runId: string) => Promise<void>;
  loadReport: () => Promise<void>;
};

const ResearchDataContext = createContext<ResearchDataContextValue | null>(null);

export function ResearchDataProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demo, setDemo] = useState<DemoResponse | null>(null);
  const [report, setReport] = useState<ResearchReport | null>(null);
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
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [lastApiCheck, setLastApiCheck] = useState<
    ResearchDataContextValue["lastApiCheck"]
  >(null);

  const loadDemo = useCallback(async () => {
    const demoResponse = await fetchDemo();
    setDemo(demoResponse);
    return demoResponse;
  }, []);

  const loadReport = useCallback(async () => {
    setReportLoading(true);
    setReportError(null);
    try {
      const loaded = await loadResearchReportForSource(
        dataSource,
        selectedRunId,
        {
          fetchRealReport: fetchResearchReport,
          fetchDemo,
          fetchMockReport
        }
      );
      if (loaded.demo) setDemo(loaded.demo);
      setReport(loaded.report);
    } catch (caught) {
      setReport(null);
      setReportError(
        caught instanceof Error ? caught.message : "Research review unavailable"
      );
    } finally {
      setReportLoading(false);
    }
  }, [dataSource, selectedRunId]);

  const clearRealData = useCallback(() => {
    setRunList([]);
    setSelectedRunId(null);
    setRealDetail(null);
    setRealEquity(null);
    setRealBenchmark(null);
    setRealHoldings(null);
    setRealFactors(null);
    setRealWarnings(null);
    setReport(null);
    setReportError(null);
  }, []);

  const loadRealRun = useCallback(async (
    runId: string,
    preloadedDetail?: ResearchRunDetail
  ) => {
    setReport(null);
    setReportError(null);
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
    setHealth(null);
    try {
      setHealth(await fetchHealth());
      const runs = await fetchResearchRuns();
      setRunList(runs.runs);
      if (runs.runs.length > 0) {
        const latest = await fetchLatestResearchRun();
        await loadRealRun(latest.summary.run_id, latest);
        setLastApiCheck({
          checkedAt: new Date().toISOString(),
          status: "ok",
          message: `已读取真实运行 ${latest.summary.run_id}`
        });
      } else {
        await loadDemo();
        clearRealData();
        setDataSource("mock_demo");
        setLastApiCheck({
          checkedAt: new Date().toISOString(),
          status: "ok",
          message: "API 正常，暂无真实研究运行"
        });
      }
    } catch (caught) {
      try {
        await loadDemo();
        clearRealData();
        setDataSource("mock_demo");
        setError("真实研究运行不可用，当前显示演示数据");
        setLastApiCheck({
          checkedAt: new Date().toISOString(),
          status: "degraded",
          message: "真实运行接口不可用，演示接口可用"
        });
      } catch {
        clearRealData();
        setDemo(null);
        setDataSource("api_unavailable");
        setError(caught instanceof Error ? caught.message : "Research API unavailable");
        setLastApiCheck({
          checkedAt: new Date().toISOString(),
          status: "unavailable",
          message: "研究 API 不可用"
        });
      }
    } finally {
      setLoading(false);
    }
  }, [clearRealData, loadDemo, loadRealRun]);

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
      reportLoading,
      reportError,
      lastApiCheck,
      refresh,
      selectRun,
      loadReport
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
      reportLoading,
      reportError,
      lastApiCheck,
      refresh,
      selectRun,
      loadReport
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
