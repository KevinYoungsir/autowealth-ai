"use client";

import {
  AllocationPanel,
  HoldingTablePanel,
  RejectionPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import {
  DataSourceBanner,
  RealHoldingsPanel,
  RunLimitationsPanel
} from "@/components/real-run-sections";

export default function PortfolioPage() {
  const {
    demo,
    health,
    loading,
    error,
    dataSource,
    realDetail,
    realHoldings
  } = useResearchData();
  const real = dataSource === "real_artifacts" ? realDetail : null;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={real?.summary} />
      <SectionHeader
        eyebrow="Portfolio"
        title="当前组合"
        description="展示研究目标权重、现金仓位与候选过滤记录。"
        status={health}
        loading={loading}
        error={error}
      />
      {real && realHoldings ? (
        <>
          <RunLimitationsPanel detail={real} />
          <RealHoldingsPanel data={realHoldings} />
        </>
      ) : (
        <>
          <div className="grid gap-5 xl:grid-cols-[0.9fr_1.2fr]">
            <AllocationPanel weights={demo?.result.target_weights ?? {}} />
            <HoldingTablePanel
              weights={demo?.result.target_weights ?? {}}
              selectedSymbols={demo?.result.selected_symbols ?? []}
              scores={demo?.summary.factor_summary?.scores_by_symbol ?? {}}
            />
          </div>
          <RejectionPanel rejected={demo?.result.rejected_symbols ?? {}} warnings={demo?.result.warnings ?? []} />
        </>
      )}
    </div>
  );
}
