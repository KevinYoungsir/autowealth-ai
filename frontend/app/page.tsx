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
import {
  DataSourceBanner,
  FactorCoveragePanel,
  MacroArtifactPanel,
  RealHoldingsPanel,
  RealMetricGrid,
  RunLimitationsPanel,
  WarningSummaryPanel
} from "@/components/real-run-sections";

export default function DashboardPage() {
  const {
    demo,
    health,
    loading,
    error,
    dataSource,
    realDetail,
    realEquity,
    realHoldings,
    realFactors,
    realWarnings
  } = useResearchData();
  const result = demo?.result;
  const summary = demo?.summary;
  const real = dataSource === "real_artifacts" ? realDetail : null;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow="Dashboard"
        title="研究总览"
        description={real ? `${real.summary.experiment_name} 的只读研究 artifacts。` : "基于本地 mock 研究 API 的演示快照。"}
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
              <EquityPanel equityCurve={realEquity?.points ?? []} subtitle="Real artifact equity curve" />
            </>
          ) : null}
          {realHoldings ? <RealHoldingsPanel data={realHoldings} /> : null}
          <div className="grid gap-5 xl:grid-cols-2">
            <MacroArtifactPanel detail={real} />
            {realFactors ? <FactorCoveragePanel data={realFactors} /> : null}
          </div>
          {realWarnings ? <WarningSummaryPanel data={realWarnings} /> : null}
        </>
      ) : (
        <>
          <MetricGrid metrics={summary?.backtest_metrics} />
          <div className="grid gap-5 xl:grid-cols-[1.45fr_0.95fr]">
            <EquityPanel equityCurve={result?.equity_curve ?? []} />
            <AllocationPanel weights={result?.target_weights ?? {}} />
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <MacroSnapshotPanel macro={summary?.macro_summary} />
            <FactorSnapshotPanel factor={summary?.factor_summary} />
          </div>
        </>
      )}
      <ResearchBoundary />
    </div>
  );
}
