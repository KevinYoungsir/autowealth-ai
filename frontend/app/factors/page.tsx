"use client";

import {
  FactorSnapshotPanel,
  FactorTablePanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import {
  DataSourceBanner,
  FactorCoveragePanel
} from "@/components/real-run-sections";

export default function FactorsPage() {
  const {
    demo,
    health,
    loading,
    error,
    dataSource,
    realDetail,
    realFactors
  } = useResearchData();
  const factor = demo?.summary.factor_summary;
  const real = dataSource === "real_artifacts" ? realDetail : null;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={real?.summary} />
      <SectionHeader
        eyebrow="Factors"
        title="因子评分"
        description="多因子综合评分与候选池分布。"
        status={health}
        loading={loading}
        error={error}
      />
      {real && realFactors ? (
        <FactorCoveragePanel data={realFactors} />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
          <FactorSnapshotPanel factor={factor} />
          <FactorTablePanel scores={factor?.scores_by_symbol ?? {}} />
        </div>
      )}
    </div>
  );
}
