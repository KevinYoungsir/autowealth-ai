"use client";

import {
  MacroDetailPanel,
  MacroSnapshotPanel,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";

export default function MacroPage() {
  const { demo, health, loading, error } = useResearchData();
  const macro = demo?.summary.macro_summary;

  return (
    <div className="space-y-5">
      <SectionHeader
        eyebrow="Macro"
        title="宏观周期"
        description="宏观状态、权益仓位系数与外部风险维度。"
        status={health}
        loading={loading}
        error={error}
      />
      <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <MacroSnapshotPanel macro={macro} />
        <MacroDetailPanel macro={macro} />
      </div>
    </div>
  );
}
