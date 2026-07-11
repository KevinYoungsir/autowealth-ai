"use client";

import {
  EquityPanel,
  MetricGrid,
  ReturnPlaceholderPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import {
  DataSourceBanner,
  RealMetricGrid,
  RealReturnsPanel,
  RunLimitationsPanel
} from "@/components/real-run-sections";

export default function BacktestPage() {
  const {
    demo,
    health,
    loading,
    error,
    dataSource,
    realDetail,
    realEquity,
    realBenchmark
  } = useResearchData();
  const real = dataSource === "real_artifacts" ? realDetail : null;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={real?.summary} />
      <SectionHeader
        eyebrow="Backtest"
        title="回测表现"
        description="历史样本下的研究指标与权益曲线展示。"
        status={health}
        loading={loading}
        error={error}
      />
      {real ? (
        <>
          <RunLimitationsPanel detail={real} />
          {real.summary.run_status !== "failed" ? (
            <>
              <RealMetricGrid detail={real} />
              <EquityPanel equityCurve={realEquity?.points ?? []} tall subtitle="Real artifact equity curve" />
              <RealReturnsPanel detail={real} benchmark={realBenchmark} />
            </>
          ) : null}
        </>
      ) : (
        <>
          <MetricGrid metrics={demo?.summary.backtest_metrics} />
          <EquityPanel equityCurve={demo?.result.equity_curve ?? []} tall />
          <ReturnPlaceholderPanel />
        </>
      )}
    </div>
  );
}
