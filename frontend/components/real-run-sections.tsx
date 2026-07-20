"use client";

import {
  AlertTriangle,
  BarChart3,
  Database,
  Gauge,
  ShieldAlert,
  Waves
} from "lucide-react";
import { formatNumber, formatPercent, formatWeight, toNumber } from "@/lib/format";
import type {
  ResearchBenchmarkCurveResponse,
  ResearchDataSource,
  ResearchFactorsResponse,
  ResearchHoldingsResponse,
  ResearchRunDetail,
  ResearchRunSummary,
  ResearchWarningsResponse
} from "@/lib/types";
import { machineLabel, runReasonLabel, ui } from "@/i18n";

export function DataSourceBanner({
  source,
  summary
}: {
  source: ResearchDataSource;
  summary?: ResearchRunSummary;
}) {
  const isReal = source === "real_artifacts";
  const label = machineLabel("dataSource", source);
  return (
    <section className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        <Database className={isReal ? "h-4 w-4 text-signal-green" : "h-4 w-4 text-signal-amber"} />
        <div>
          <div className="text-xs text-slate-500">{ui.common.dataSource}</div>
          <div className="text-sm font-semibold text-slate-100">{label}</div>
          <div className="mt-0.5 font-mono text-xs text-slate-500">{source}</div>
        </div>
      </div>
      {summary ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="font-mono">{summary.run_id}</span>
          <span>{ui.common.dateRange(summary.start_date, summary.end_date)}</span>
          <span className={summary.run_status === "success" ? "text-signal-green" : "text-signal-amber"}>
            {machineLabel("runStatus", summary.run_status)} <span className="font-mono text-slate-500">({summary.run_status})</span>
          </span>
        </div>
      ) : (
        <div className="text-xs text-slate-500">{source === "mock_demo" ? ui.pages.researchNotes.mockDisclosure : ui.errors.apiUnavailable}</div>
      )}
    </section>
  );
}

export function RealMetricGrid({ detail }: { detail: ResearchRunDetail }) {
  const { summary, metrics } = detail;
  const coverageValues = Object.values(summary.factor_coverage_overall);
  const factorCoverage = coverageValues.length
    ? coverageValues.reduce((sum, item) => sum + item.coverage_ratio, 0) / coverageValues.length
    : null;
  const items = [
    [ui.metrics.annualized_return, formatPercent(summary.annualized_return)],
    [ui.metrics.total_return, formatPercent(summary.total_return)],
    [ui.metrics.max_drawdown, formatPercent(summary.max_drawdown)],
    [ui.metrics.sharpe_ratio, formatNumber(summary.sharpe_ratio)],
    [ui.metrics.price_coverage_ratio, formatPercent(summary.price_coverage_ratio)],
    [ui.metrics.factor_coverage_ratio, formatPercent(factorCoverage)],
    [ui.metrics.warning_count, String(summary.warning_count)],
    [ui.metrics.turnover, formatPercent(metrics.turnover)]
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="panel px-4 py-4">
          <div className="metric-label">{label}</div>
          <div className="metric-value mt-2">{value}</div>
        </div>
      ))}
    </div>
  );
}

export function RunLimitationsPanel({ detail }: { detail: ResearchRunDetail }) {
  const reasons = Array.isArray(detail.manifest.run_status_reasons)
    ? detail.manifest.run_status_reasons.map(String)
    : [];
  if (detail.summary.run_status === "success" && reasons.length === 0) return null;
  return (
    <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-signal-amber">
        <ShieldAlert className="h-4 w-4" />
        {machineLabel("runStatus", detail.summary.run_status)}
        <span className="font-mono text-xs text-slate-500">({detail.summary.run_status})</span>
      </div>
      <ul className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
        {reasons.map((reason) => (
          <li key={reason}>
            <div>{runReasonLabel(reason)}</div>
            <details className="mt-1 text-xs text-slate-500">
              <summary className="cursor-pointer">{ui.report.viewRawDetails}</summary>
              <div className="mt-1 break-words font-mono">{reason}</div>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RealReturnsPanel({
  detail,
  benchmark
}: {
  detail: ResearchRunDetail;
  benchmark: ResearchBenchmarkCurveResponse | null;
}) {
  const annual = Object.entries(detail.metrics.annual_returns ?? {});
  const monthly = Object.entries(detail.metrics.monthly_returns ?? {}).slice(-12);
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-50">{ui.panels.returnsAndBenchmark}</h2>
          <div className="mt-1 text-xs text-slate-500">{ui.panels.returnSubtitle}</div>
        </div>
        <BarChart3 className="h-4 w-4 text-signal-cyan" />
      </div>
      <div className="mt-4 grid gap-5 xl:grid-cols-2">
        <div>
          <div className="text-xs text-slate-500">{ui.panels.annualReturns}</div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {annual.map(([period, value]) => (
              <div key={period} className="panel-soft p-3">
                <div className="text-xs text-slate-500">{period}</div>
                <div className="mt-1 font-mono text-sm text-slate-100">{formatPercent(value)}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">{ui.panels.recentMonthlyReturns}</div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {monthly.map(([period, value]) => (
              <div key={period} className="panel-soft p-3">
                <div className="text-xs text-slate-500">{period}</div>
                <div className="mt-1 font-mono text-sm text-slate-100">{formatPercent(value)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-5 border-t border-white/10 pt-4 text-sm text-slate-300">
        {ui.panels.benchmarkStatus}：<span className={benchmark?.status === "available" ? "text-signal-green" : "text-signal-amber"}>{machineLabel("availability", benchmark?.status ?? detail.summary.benchmark_status)}</span>
        <span className="ml-2 font-mono text-xs text-slate-500">({benchmark?.status ?? detail.summary.benchmark_status})</span>
        {benchmark && Object.keys(benchmark.reasons).length ? (
          <details className="ml-3 inline-block text-slate-500">
            <summary className="cursor-pointer">{ui.report.viewRawDetails}</summary>
            <div className="mt-2 break-words font-mono text-xs">{Object.values(benchmark.reasons).join("；")}</div>
          </details>
        ) : null}
      </div>
    </section>
  );
}

export function RealHoldingsPanel({ data }: { data: ResearchHoldingsResponse }) {
  const latestDate = data.records[0]?.rebalance_date;
  const rows = data.records.filter((record) => record.rebalance_date === latestDate);
  const count = latestDate ? data.holdings_count_by_rebalance[latestDate.slice(0, 10)] ?? rows.length : 0;
  const meetsMinimum = data.min_holdings === null || count >= data.min_holdings;
  const cashWeight = rows[0]?.cash_weight;
  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-50">{ui.panels.latestHoldings}</h2>
          <div className="mt-1 text-xs text-slate-500">{latestDate ?? ui.panels.noRebalance}</div>
        </div>
        <div className={meetsMinimum ? "text-xs text-signal-green" : "text-xs text-signal-amber"}>
          {count} / {ui.panels.minimumHoldingCount(data.min_holdings)}
        </div>
      </div>
      <div className="mt-4 overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs text-slate-500">
            <tr><th className="px-4 py-3">{ui.tables.symbol}</th><th className="px-4 py-3">{ui.tables.weight}</th><th className="px-4 py-3">{ui.tables.shares}</th><th className="px-4 py-3">{ui.tables.rebalanceDate}</th></tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {rows.map((row) => (
              <tr key={`${row.rebalance_date}-${row.symbol}`}>
                <td className="px-4 py-3 font-mono text-slate-100">{row.symbol}</td>
                <td className="px-4 py-3 font-mono text-slate-300">{formatWeight(row.weight)}</td>
                <td className="px-4 py-3 font-mono text-slate-400">{formatNumber(row.shares, 2)}</td>
                <td className="px-4 py-3 text-slate-400">{row.rebalance_date.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex gap-5 text-sm text-slate-400">
        <span>{ui.panels.cashRatio} {formatPercent(cashWeight)}</span>
        <span className={meetsMinimum ? "text-signal-green" : "text-signal-amber"}>{meetsMinimum ? ui.panels.meetsMinimum : ui.panels.belowMinimum}</span>
      </div>
    </section>
  );
}

export function FactorCoveragePanel({ data }: { data: ResearchFactorsResponse }) {
  const latestDate = Object.keys(data.coverage_by_rebalance).sort().at(-1);
  const latestRecords = latestDate
    ? data.records.filter((record) => String(record.rebalance_date).startsWith(latestDate))
    : [];
  const weights = averageCompositeWeights(latestRecords);
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between gap-3">
        <div><h2 className="text-base font-semibold text-slate-50">{ui.panels.factorCoverage}</h2><div className="mt-1 text-xs text-slate-500">{ui.panels.factorCoverageSubtitle}</div></div>
        <Gauge className="h-4 w-4 text-signal-cyan" />
      </div>
      <div className="mt-4 overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs text-slate-500"><tr><th className="px-4 py-3">{ui.tables.factor}</th><th className="px-4 py-3">{ui.tables.available}</th><th className="px-4 py-3">{ui.tables.missing}</th><th className="px-4 py-3">{ui.tables.coverage}</th><th className="px-4 py-3">{ui.tables.effectiveWeight}</th></tr></thead>
          <tbody className="divide-y divide-white/10">
            {Object.entries(data.coverage_overall).map(([factor, coverage]) => (
              <tr key={factor}>
                <td className="px-4 py-3 text-slate-100">{machineLabel("factor", factor)}<div className="mt-1 font-mono text-xs text-slate-500">{factor}</div></td>
                <td className="px-4 py-3 font-mono text-slate-300">{coverage.available_count}</td>
                <td className="px-4 py-3 font-mono text-slate-300">{coverage.missing_count}</td>
                <td className="px-4 py-3 font-mono text-slate-300">{formatPercent(coverage.coverage_ratio)}</td>
                <td className="px-4 py-3 font-mono text-slate-300">{formatPercent(weights[factor])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {Object.entries(data.coverage_overall).some(([, item]) => item.missing_count > 0) ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-signal-amber"><AlertTriangle className="h-4 w-4" />{ui.panels.factorMissingNotice}</div>
      ) : null}
    </section>
  );
}

export function MacroArtifactPanel({ detail }: { detail: ResearchRunDetail }) {
  const coverage = (detail.manifest.coverage_summary ?? {}) as Record<string, unknown>;
  const count = toNumber(coverage.macro_observation_count) ?? 0;
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between"><div><h2 className="text-base font-semibold text-slate-50">{ui.panels.macroDataStatus}</h2><div className="mt-1 text-xs text-slate-500">{ui.panels.realManifest}</div></div><Waves className="h-4 w-4 text-signal-cyan" /></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="panel-soft p-4"><div className="text-xs text-slate-500">{ui.panels.macroObservationCount}</div><div className="mt-2 text-2xl font-semibold text-slate-50">{count}</div></div>
        <div className="panel-soft p-4"><div className="text-xs text-slate-500">{ui.panels.multiplierStatus}</div><div className={count === 0 ? "mt-2 text-lg font-semibold text-signal-amber" : "mt-2 text-lg font-semibold text-signal-green"}>{count === 0 ? ui.panels.neutralFallbackUsed : ui.panels.publishedMacroUsed}</div></div>
      </div>
      {count === 0 ? <div className="prose-copy mt-4 text-sm text-slate-400">{ui.panels.macroMissingExplanation}</div> : null}
    </section>
  );
}

export function WarningSummaryPanel({ data }: { data: ResearchWarningsResponse }) {
  const categories = Object.entries(data.summary.categories).filter(([, count]) => count > 0);
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between"><div><h2 className="text-base font-semibold text-slate-50">{ui.panels.warningSummary}</h2><div className="mt-1 text-xs text-slate-500">{ui.panels.warningSummarySubtitle(data.summary.total)}</div></div><AlertTriangle className="h-4 w-4 text-signal-amber" /></div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {categories.map(([category, count]) => (
          <div key={category} className="panel-soft p-4">
            <div className="flex justify-between gap-3"><span className="text-sm text-slate-200">{machineLabel("warningCategory", category)}<span className="ml-2 font-mono text-xs text-slate-500">{category}</span></span><span className="font-mono text-sm text-signal-amber">{count}</span></div>
            <details className="mt-3 text-xs leading-5 text-slate-500">
              <summary className="cursor-pointer">{ui.report.viewRawDetails}</summary>
              <div className="mt-2 space-y-2 font-mono">{(data.summary.samples[category] ?? []).map((sample) => <div className="break-words" key={sample}>{sample}</div>)}</div>
            </details>
          </div>
        ))}
      </div>
    </section>
  );
}

function averageCompositeWeights(records: Array<Record<string, any>>): Record<string, number> {
  const totals: Record<string, number> = {};
  let parsedCount = 0;
  for (const record of records) {
    try {
      const weights = typeof record.composite_weights === "string" ? JSON.parse(record.composite_weights) : record.composite_weights;
      if (!weights || typeof weights !== "object") continue;
      parsedCount += 1;
      for (const [factor, value] of Object.entries(weights)) totals[factor] = (totals[factor] ?? 0) + (toNumber(value) ?? 0);
    } catch {
      continue;
    }
  }
  if (!parsedCount) return totals;
  return Object.fromEntries(Object.entries(totals).map(([factor, value]) => [factor, value / parsedCount]));
}
