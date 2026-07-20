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
import { ui } from "@/i18n";

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
        eyebrow={ui.pages.factors.eyebrow}
        title={ui.pages.factors.title}
        description={ui.pages.factors.description}
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
