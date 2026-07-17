"use client";

import { useEffect } from "react";
import {
  ResearchBoundary,
  ResearchReportPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import {
  DataSourceBanner,
  RunLimitationsPanel
} from "@/components/real-run-sections";
import {
  RealResearchReportPanel,
  ResearchReportMetadata
} from "@/components/real-research-report";

export default function ResearchNotesPage() {
  const {
    report,
    health,
    loading,
    error,
    reportLoading,
    reportError,
    loadReport,
    dataSource,
    realDetail,
    selectedRunId
  } = useResearchData();

  useEffect(() => {
    if (loading) return;
    if (dataSource === "mock_demo") void loadReport();
    if (dataSource === "real_artifacts" && selectedRunId) void loadReport();
  }, [dataSource, loadReport, loading, selectedRunId]);

  const realReport =
    report && "data_source" in report && report.data_source === "real_artifacts"
      ? report
      : null;
  const mockReport = report && !("data_source" in report) ? report : null;
  const isReal = dataSource === "real_artifacts";
  const isMock = dataSource === "mock_demo";
  const title = isReal
    ? "真实研究复核报告"
    : isMock
      ? "演示研究报告"
      : "研究报告不可用";
  const description = isReal
    ? "基于所选 run_id 已落盘 artifacts 生成的确定性、只读复核。"
    : isMock
      ? "无真实运行时使用离线演示数据生成的 mock 结构化复核。"
      : "研究 API 当前不可用，页面不会把占位内容标记为真实报告。";

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow="Research Notes"
        title={title}
        description={description}
        status={health}
        loading={loading || reportLoading}
        error={reportError ?? error}
      />
      <ResearchReportMetadata
        dataSource={dataSource}
        runId={realReport?.run_id ?? selectedRunId ?? (isMock ? "mock_demo" : "unavailable")}
        runStatus={realReport?.run_status ?? realDetail?.summary.run_status ?? (isMock ? "demo" : "unavailable")}
        generatedMode={realReport?.generated_mode ?? (isReal ? "deterministic" : isMock ? "mock" : "unavailable")}
      />
      {realDetail ? <RunLimitationsPanel detail={realDetail} /> : null}
      {dataSource === "mock_demo" ? (
        <section className="rounded-lg border border-signal-cyan/25 bg-signal-cyan/5 p-4 text-sm text-slate-300">
          当前没有可用真实运行，页面显示 mock_demo 演示复核；它不代表真实 artifacts 的结论。
        </section>
      ) : null}
      {isReal && realReport ? (
        <RealResearchReportPanel report={realReport} />
      ) : isReal ? (
        <section className="panel p-5 text-sm text-slate-400">
          {reportLoading
            ? "正在读取所选 run_id 的真实研究复核报告。"
            : reportError ?? "真实研究复核报告尚未返回。"}
        </section>
      ) : isMock ? (
        <ResearchReportPanel report={mockReport} />
      ) : (
        <section className="panel p-5 text-sm text-slate-500">
          研究 API 不可用，当前没有可展示的研究报告。
        </section>
      )}
      {isMock ? <ResearchBoundary /> : null}
    </div>
  );
}
