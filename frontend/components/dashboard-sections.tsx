"use client";

import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  CircleDollarSign,
  Gauge,
  LineChart,
  Scale,
  Shield,
  WalletCards
} from "lucide-react";
import { EquityCurveChart, WeightBars } from "./charts";
import { formatNumber, formatPercent, formatWeight, toNumber } from "@/lib/format";
import type { DeepSeekReport, EquityPoint, HealthResponse } from "@/lib/types";
import { machineLabel, ui } from "@/i18n";

export function SectionHeader({
  eyebrow,
  title,
  description,
  status,
  loading,
  error
}: {
  eyebrow: string;
  title: string;
  description: string;
  status: HealthResponse | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="panel px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="metric-label">{eyebrow}</div>
          <h1 className="mt-1 text-2xl font-semibold text-slate-50 md:text-3xl">{title}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
            {loading ? ui.common.syncing : status?.status === "ok" ? ui.common.apiOnline : ui.common.apiPending}
          </div>
          {error ? <div className="max-w-md text-right text-xs text-signal-red">{error}</div> : null}
        </div>
      </div>
    </section>
  );
}

export function MetricGrid({ metrics }: { metrics?: Record<string, any> }) {
  const items = [
    {
      label: ui.metrics.annualized_return,
      value: formatPercent(metrics?.annualized_return),
      icon: LineChart,
      accent: "text-signal-teal"
    },
    {
      label: ui.metrics.max_drawdown,
      value: formatPercent(metrics?.max_drawdown),
      icon: Shield,
      accent: "text-signal-red"
    },
    {
      label: ui.metrics.sharpe_ratio,
      value: formatNumber(metrics?.sharpe_ratio),
      icon: Gauge,
      accent: "text-signal-cyan"
    },
    {
      label: ui.metrics.calmar_ratio,
      value: formatNumber(metrics?.calmar_ratio),
      icon: Scale,
      accent: "text-signal-amber"
    },
    {
      label: ui.metrics.cash_weight,
      value: formatPercent(metrics?.cash_weight),
      icon: CircleDollarSign,
      accent: "text-signal-green"
    }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.label} className="panel px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="metric-label">{item.label}</div>
                <div className="metric-value mt-2">{item.value}</div>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
                <Icon className={`h-5 w-5 ${item.accent}`} aria-hidden="true" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function EquityPanel({
  equityCurve,
  tall = false,
  subtitle = ui.panels.mockEquityCurve
}: {
  equityCurve: EquityPoint[];
  tall?: boolean;
  subtitle?: string;
}) {
  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.equityCurve} subtitle={subtitle} icon={LineChart} />
      <div className="mt-4">
        <EquityCurveChart points={equityCurve} height={tall ? 360 : 285} />
      </div>
    </section>
  );
}

export function AllocationPanel({ weights }: { weights: Record<string, number> }) {
  const cashWeight = Math.max(0, 1 - Object.values(weights).reduce((sum, weight) => sum + weight, 0));

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.targetWeights} subtitle={`${ui.metrics.cash_weight} ${formatWeight(cashWeight)}`} icon={WalletCards} />
      <div className="mt-5">
        <WeightBars weights={weights} />
      </div>
    </section>
  );
}

export function HoldingTablePanel({
  weights,
  selectedSymbols,
  scores
}: {
  weights: Record<string, number>;
  selectedSymbols: string[];
  scores: Record<string, number>;
}) {
  const rows = selectedSymbols.map((symbol) => ({
    symbol,
    weight: weights[symbol] ?? 0,
    score: scores[symbol]
  }));

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.portfolioDetails} subtitle={ui.common.symbols(rows.length)} icon={WalletCards} />
      <div className="mt-4 overflow-hidden rounded-lg border border-white/10">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs text-slate-500">
            <tr>
              <th className="px-4 py-3">{ui.tables.symbol}</th>
              <th className="px-4 py-3">{ui.tables.weight}</th>
              <th className="px-4 py-3">{ui.tables.score}</th>
              <th className="px-4 py-3">{ui.tables.state}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {rows.map((row) => (
              <tr key={row.symbol} className="text-slate-300">
                <td className="px-4 py-3 font-mono text-slate-100">{row.symbol}</td>
                <td className="px-4 py-3 font-mono">{formatWeight(row.weight)}</td>
                <td className="px-4 py-3 font-mono">{formatNumber(row.score, 1)}</td>
                <td className="px-4 py-3">
                  <span className="rounded-lg border border-signal-teal/25 bg-signal-teal/10 px-2 py-1 text-xs text-signal-teal">
                    {ui.panels.researchTarget}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RejectionPanel({
  rejected,
  warnings
}: {
  rejected: Record<string, string>;
  warnings: string[];
}) {
  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.candidateFilters} subtitle={ui.common.records(Object.keys(rejected).length)} icon={AlertTriangle} />
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {Object.entries(rejected).map(([symbol, reason]) => (
          <div key={symbol} className="panel-soft p-4">
            <div className="font-mono text-sm text-slate-100">{symbol}</div>
            <div className="mt-2 text-sm text-slate-300">{ui.panels.rejectedCandidate}</div>
            <details className="mt-2 text-xs text-slate-500">
              <summary className="cursor-pointer">{ui.panels.originalTechnicalReason}</summary>
              <div className="mt-2 break-words font-mono">{reason}</div>
            </details>
          </div>
        ))}
        {warnings.map((warning) => (
          <div key={warning} className="panel-soft p-4 text-sm text-slate-400">
            <div className="text-slate-300">{ui.panels.pipelineWarning}</div>
            <details className="mt-2 text-xs text-slate-500">
              <summary className="cursor-pointer">{ui.report.viewRawDetails}</summary>
              <div className="mt-2 break-words font-mono">{warning}</div>
            </details>
          </div>
        ))}
      </div>
    </section>
  );
}

export function FactorSnapshotPanel({ factor }: { factor?: Record<string, any> }) {
  const buckets = factor?.score_buckets ?? {};

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.factorDistribution} subtitle={ui.panels.compositeBuckets} icon={Gauge} />
      <div className="mt-5 grid grid-cols-3 gap-3">
        {[
          ["gte_80", "80+"],
          ["60_to_80", "60-80"],
          ["lt_60", "<60"]
        ].map(([key, label]) => (
          <div key={key} className="panel-soft p-4 text-center">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-slate-50">{buckets[key] ?? 0}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <SmallStat label={ui.panels.mean} value={formatNumber(factor?.mean_score, 1)} />
        <SmallStat label={ui.panels.minimum} value={formatNumber(factor?.min_score, 1)} />
        <SmallStat label={ui.panels.maximum} value={formatNumber(factor?.max_score, 1)} />
      </div>
    </section>
  );
}

export function FactorTablePanel({ scores }: { scores: Record<string, number> }) {
  const rows = Object.entries(scores).sort((a, b) => b[1] - a[1]);

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.scoreRanking} subtitle={ui.common.candidates(rows.length)} icon={Gauge} />
      <div className="mt-4 space-y-3">
        {rows.map(([symbol, score]) => (
          <div key={symbol} className="grid grid-cols-[82px_1fr_64px] items-center gap-3">
            <div className="font-mono text-sm text-slate-200">{symbol}</div>
            <div className="h-2.5 rounded-full bg-white/7">
              <div className="h-2.5 rounded-full bg-signal-cyan" style={{ width: `${score}%` }} />
            </div>
            <div className="text-right font-mono text-sm text-slate-300">{formatNumber(score, 1)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function MacroSnapshotPanel({ macro }: { macro?: Record<string, any> }) {
  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.macroState} subtitle={ui.panels.macroSnapshot} icon={Shield} />
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <SmallStat label={ui.panels.regime} value={machineLabel("macroRegime", String(macro?.regime ?? "not_provided"))} technicalValue={String(macro?.regime ?? "not_provided")} />
        <SmallStat label={ui.panels.multiplier} value={formatNumber(macro?.equity_position_multiplier, 2)} />
        <SmallStat label={ui.panels.growth} value={formatNumber(macro?.growth_score, 1)} />
        <SmallStat label={ui.panels.externalRisk} value={formatNumber(macro?.external_risk_score, 1)} />
      </div>
    </section>
  );
}

export function MacroDetailPanel({ macro }: { macro?: Record<string, any> }) {
  const metrics = [
    ["growth_score", ui.panels.growthDimension],
    ["inflation_score", ui.panels.inflationDimension],
    ["liquidity_score", ui.panels.liquidityDimension],
    ["credit_score", ui.panels.creditDimension],
    ["policy_score", ui.panels.policyDimension],
    ["external_risk_score", ui.panels.externalRiskDimension]
  ];

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.macroDimensions} subtitle={ui.panels.researchScale} icon={Shield} />
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {metrics.map(([key, label]) => {
          const value = toNumber(macro?.[key]) ?? 0;
          return (
            <div key={key} className="panel-soft p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-slate-300">{label}</div>
                <div className="font-mono text-sm text-slate-100">{formatNumber(value, 1)}</div>
              </div>
              <div className="mt-3 h-2 rounded-full bg-white/7">
                <div className="h-2 rounded-full bg-signal-green" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function ReturnPlaceholderPanel() {
  const months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

  return (
    <section className="panel p-5">
      <PanelTitle title={ui.panels.monthlyAnnualReturns} subtitle={ui.panels.reservedReturns} icon={LineChart} />
      <div className="mt-4 grid grid-cols-3 gap-3 md:grid-cols-6 xl:grid-cols-12">
        {months.map((month) => (
          <div key={month} className="panel-soft p-3 text-center">
            <div className="text-xs text-slate-500">{month}</div>
            <div className="mt-2 text-sm text-slate-300">{ui.panels.pendingIntegration}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {["2021", "2022", "2023", "2024"].map((year) => (
          <div key={year} className="panel-soft p-4">
            <div className="text-xs text-slate-500">{year}</div>
            <div className="mt-2 text-lg font-semibold text-slate-300">{ui.panels.pendingIntegration}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ResearchReportPanel({ report }: { report: DeepSeekReport | null }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="panel p-5">
        <PanelTitle title={ui.panels.mockResearchSummary} subtitle={report?.metadata?.model ? `${ui.common.technicalValue} ${report.metadata.model}` : ui.panels.mockModel} icon={BrainCircuit} />
        <p className="prose-copy mt-4 text-sm leading-7 text-slate-300">
          {report?.research_note?.summary ?? ui.panels.waitingMockReport}
        </p>
        <div className="mt-5 space-y-3">
          {(report?.research_note?.key_points ?? []).map((point) => (
            <div key={point} className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-300">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-signal-teal" aria-hidden="true" />
              <span>{point}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <PanelTitle title={ui.panels.riskReview} subtitle={ui.common.flags(report?.risk_flags?.length ?? 0)} icon={AlertTriangle} />
        <div className="mt-4 grid gap-3">
          {(report?.risk_flags ?? []).map((flag) => (
            <div key={`${flag.category}-${flag.description}`} className="panel-soft p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-slate-100">{machineLabel("warningCategory", flag.category)}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{flag.category}</div>
                </div>
                <span className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 px-2 py-1 text-xs text-signal-amber">
                  {machineLabel("severity", flag.severity)} <span className="font-mono text-slate-500">({flag.severity})</span>
                </span>
              </div>
              <div className="mt-2 text-sm text-slate-400">{flag.description}</div>
              <div className="mt-2 text-xs text-slate-500">{flag.review_focus}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5 xl:col-span-2">
        <PanelTitle title={ui.panels.counterargumentReview} subtitle={ui.common.items(report?.counter_arguments?.length ?? 0)} icon={Scale} />
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {(report?.counter_arguments ?? []).map((item) => (
            <div key={item.topic} className="panel-soft p-4">
              <div className="text-sm font-semibold text-slate-100">{item.topic}</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">{item.argument}</div>
              <div className="mt-4 text-xs text-slate-500">{ui.panels.evidence}</div>
              <ul className="mt-2 space-y-1 text-xs text-slate-400">
                {item.evidence_needed.map((evidence) => (
                  <li key={evidence}>{evidence}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ResearchBoundary() {
  return (
    <section className="rounded-lg border border-signal-amber/20 bg-signal-amber/8 p-4 text-sm leading-6 text-slate-300">
      {ui.common.researchBoundary}
    </section>
  );
}

function PanelTitle({
  title,
  subtitle,
  icon: Icon
}: {
  title: string;
  subtitle: string;
  icon: typeof LineChart;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-slate-50">{title}</h2>
        <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
      </div>
      <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
        <Icon className="h-4 w-4 text-signal-cyan" aria-hidden="true" />
      </div>
    </div>
  );
}

function SmallStat({ label, value, technicalValue }: { label: string; value: string; technicalValue?: string }) {
  return (
    <div className="panel-soft p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
      {technicalValue ? <div className="mt-1 font-mono text-xs text-slate-500">{technicalValue}</div> : null}
    </div>
  );
}
