"use client";

import {
  EquityPanel,
  MetricGrid,
  ReturnPlaceholderPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";

export default function BacktestPage() {
  const { demo, health, loading, error } = useResearchData();

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow="Backtest"
        title="回测表现"
        description="历史样本下的研究指标与权益曲线展示。"
        status={health}
        loading={loading}
        error={error}
      />
      <MetricGrid metrics={demo?.summary.backtest_metrics} />
      <EquityPanel equityCurve={demo?.result.equity_curve ?? []} tall />
      <ReturnPlaceholderPanel />
    </div>
  );
}
