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
import { ui } from "@/i18n";

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
    ? ui.pages.researchNotes.realTitle
    : isMock
      ? ui.pages.researchNotes.mockTitle
      : ui.pages.researchNotes.unavailableTitle;
  const description = isReal
    ? ui.pages.researchNotes.realDescription
    : isMock
      ? ui.pages.researchNotes.mockDescription
      : ui.pages.researchNotes.unavailableDescription;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow={ui.pages.researchNotes.eyebrow}
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
        locale={realReport?.locale ?? "zh-CN"}
      />
      {realDetail ? <RunLimitationsPanel detail={realDetail} /> : null}
      {dataSource === "mock_demo" ? (
        <section className="rounded-lg border border-signal-cyan/25 bg-signal-cyan/5 p-4 text-sm text-slate-300">
          {ui.pages.researchNotes.mockDisclosure}
        </section>
      ) : null}
      {isReal && realReport ? (
        <RealResearchReportPanel report={realReport} />
      ) : isReal ? (
        <section className="panel p-5 text-sm text-slate-400">
          {reportLoading
            ? ui.pages.researchNotes.loadingReal
            : reportError ?? ui.pages.researchNotes.waitingReal}
        </section>
      ) : isMock ? (
        <ResearchReportPanel report={mockReport} />
      ) : (
        <section className="panel p-5 text-sm text-slate-500">
          {ui.pages.researchNotes.unavailable}
        </section>
      )}
      {isMock ? <ResearchBoundary /> : null}
    </div>
  );
}
