"use client";

import {
  ResearchBoundary,
  ResearchReportPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";

export default function ResearchNotesPage() {
  const { report, health, loading, error } = useResearchData();

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow="Research Notes"
        title="DeepSeek 研究报告"
        description="mock 模式下的结构化摘要、风险复核与反方观点。"
        status={health}
        loading={loading}
        error={error}
      />
      <ResearchReportPanel report={report} />
      <ResearchBoundary />
    </div>
  );
}
