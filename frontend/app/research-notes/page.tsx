"use client";

import {
  ResearchBoundary,
  ResearchReportPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import { DataSourceBanner } from "@/components/real-run-sections";

export default function ResearchNotesPage() {
  const { report, health, loading, error, dataSource, realDetail } = useResearchData();

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow="Research Notes"
        title="DeepSeek 研究报告"
        description="mock 模式下的结构化摘要、风险复核与反方观点。"
        status={health}
        loading={loading}
        error={error}
      />
      <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4 text-sm text-slate-300">
        当前内容为 mock review，仅用于验证摘要与风险复核展示；它不是所选真实 artifacts 的模型结论。
      </section>
      <ResearchReportPanel report={report} />
      <ResearchBoundary />
    </div>
  );
}
