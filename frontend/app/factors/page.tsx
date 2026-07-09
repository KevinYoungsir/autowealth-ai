"use client";

import {
  FactorSnapshotPanel,
  FactorTablePanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";

export default function FactorsPage() {
  const { demo, health, loading, error } = useResearchData();
  const factor = demo?.summary.factor_summary;

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow="Factors"
        title="因子评分"
        description="多因子综合评分与候选池分布。"
        status={health}
        loading={loading}
        error={error}
      />
      <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <FactorSnapshotPanel factor={factor} />
        <FactorTablePanel scores={factor?.scores_by_symbol ?? {}} />
      </div>
    </div>
  );
}
