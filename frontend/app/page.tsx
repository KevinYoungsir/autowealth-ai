"use client";

import {
  AllocationPanel,
  EquityPanel,
  FactorSnapshotPanel,
  MacroSnapshotPanel,
  MetricGrid,
  ResearchBoundary,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";

export default function DashboardPage() {
  const { demo, health, loading, error } = useResearchData();
  const result = demo?.result;
  const summary = demo?.summary;

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow="Dashboard"
        title="研究总览"
        description="基于本地 mock 研究 API 的组合研究快照。"
        status={health}
        loading={loading}
        error={error}
      />
      <MetricGrid metrics={summary?.backtest_metrics} />
      <div className="grid gap-5 xl:grid-cols-[1.45fr_0.95fr]">
        <EquityPanel equityCurve={result?.equity_curve ?? []} />
        <AllocationPanel weights={result?.target_weights ?? {}} />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <MacroSnapshotPanel macro={summary?.macro_summary} />
        <FactorSnapshotPanel factor={summary?.factor_summary} />
      </div>
      <ResearchBoundary />
    </div>
  );
}
