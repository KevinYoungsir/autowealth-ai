"use client";

import {
  MacroDetailPanel,
  MacroSnapshotPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import {
  DataSourceBanner,
  MacroArtifactPanel
} from "@/components/real-run-sections";

export default function MacroPage() {
  const { demo, health, loading, error, dataSource, realDetail } = useResearchData();
  const macro = demo?.summary.macro_summary;
  const real = dataSource === "real_artifacts" ? realDetail : null;

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={real?.summary} />
      <SectionHeader
        eyebrow="Macro"
        title="宏观周期"
        description="宏观状态、权益仓位系数与外部风险维度。"
        status={health}
        loading={loading}
        error={error}
      />
      {real ? (
        <MacroArtifactPanel detail={real} />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
          <MacroSnapshotPanel macro={macro} />
          <MacroDetailPanel macro={macro} />
        </div>
      )}
    </div>
  );
}
