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
import { ui } from "@/i18n";

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
        eyebrow={ui.pages.backtest.eyebrow}
        title={ui.pages.backtest.title}
        description={ui.pages.backtest.description}
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
              <EquityPanel equityCurve={realEquity?.points ?? []} tall subtitle={ui.panels.realEquityCurve} />
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
