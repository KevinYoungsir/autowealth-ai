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

const statusLabels = {
  success: "完整运行",
  partial_success: "部分完成",
  failed: "运行失败"
};

export function DataSourceBanner({
  source,
  summary
}: {
  source: ResearchDataSource;
  summary?: ResearchRunSummary;
}) {
  const isReal = source === "real_artifacts";
  const label = isReal ? "real_artifacts" : source === "mock_demo" ? "演示数据" : "API 不可用";
  return (
    <section className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        <Database className={isReal ? "h-4 w-4 text-signal-green" : "h-4 w-4 text-signal-amber"} />
        <div>
          <div className="text-xs text-slate-500">数据来源</div>
          <div className="text-sm font-semibold text-slate-100">{label}</div>
        </div>
      </div>
      {summary ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="font-mono">{summary.run_id}</span>
          <span>{summary.start_date} 至 {summary.end_date}</span>
          <span className={summary.run_status === "success" ? "text-signal-green" : "text-signal-amber"}>
            {statusLabels[summary.run_status]}
          </span>
        </div>
      ) : (
        <div className="text-xs text-slate-500">当前内容不是已落盘的真实研究运行</div>
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
    ["年化收益", formatPercent(summary.annualized_return)],
    ["总收益", formatPercent(summary.total_return)],
    ["最大回撤", formatPercent(summary.max_drawdown)],
    ["夏普比率", formatNumber(summary.sharpe_ratio)],
    ["价格覆盖率", formatPercent(summary.price_coverage_ratio)],
    ["因子覆盖率", formatPercent(factorCoverage)],
    ["Warning", String(summary.warning_count)],
    ["换手率", formatPercent(metrics.turnover)]
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
        {statusLabels[detail.summary.run_status]}
      </div>
      <ul className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
        {reasons.map((reason) => <li key={reason}>{reason}</li>)}
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
          <h2 className="text-base font-semibold text-slate-50">收益与基准</h2>
          <div className="mt-1 text-xs text-slate-500">年度、最近月度与基准可用状态</div>
        </div>
        <BarChart3 className="h-4 w-4 text-signal-cyan" />
      </div>
      <div className="mt-4 grid gap-5 xl:grid-cols-2">
        <div>
          <div className="text-xs text-slate-500">年度收益</div>
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
          <div className="text-xs text-slate-500">最近月度收益</div>
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
        基准状态：<span className={benchmark?.status === "available" ? "text-signal-green" : "text-signal-amber"}>{benchmark?.status ?? detail.summary.benchmark_status}</span>
        {benchmark && Object.keys(benchmark.reasons).length ? (
          <span className="ml-3 text-slate-500">{Object.values(benchmark.reasons).join("；")}</span>
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
          <h2 className="text-base font-semibold text-slate-50">最近调仓持仓</h2>
          <div className="mt-1 text-xs text-slate-500">{latestDate ?? "暂无调仓记录"}</div>
        </div>
        <div className={meetsMinimum ? "text-xs text-signal-green" : "text-xs text-signal-amber"}>
          {count} / min {data.min_holdings ?? "--"}
        </div>
      </div>
      <div className="mt-4 overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs text-slate-500">
            <tr><th className="px-4 py-3">股票代码</th><th className="px-4 py-3">权重</th><th className="px-4 py-3">份额</th><th className="px-4 py-3">调仓日期</th></tr>
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
        <span>现金比例 {formatPercent(cashWeight)}</span>
        <span className={meetsMinimum ? "text-signal-green" : "text-signal-amber"}>{meetsMinimum ? "达到最小持仓数" : "低于最小持仓数"}</span>
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
        <div><h2 className="text-base font-semibold text-slate-50">因子覆盖率</h2><div className="mt-1 text-xs text-slate-500">全运行覆盖与最近实际复合权重</div></div>
        <Gauge className="h-4 w-4 text-signal-cyan" />
      </div>
      <div className="mt-4 overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs text-slate-500"><tr><th className="px-4 py-3">因子</th><th className="px-4 py-3">Available</th><th className="px-4 py-3">Missing</th><th className="px-4 py-3">Coverage</th><th className="px-4 py-3">实际权重</th></tr></thead>
          <tbody className="divide-y divide-white/10">
            {Object.entries(data.coverage_overall).map(([factor, coverage]) => (
              <tr key={factor}>
                <td className="px-4 py-3 text-slate-100">{factor}</td>
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
        <div className="mt-4 flex items-center gap-2 text-sm text-signal-amber"><AlertTriangle className="h-4 w-4" />存在缺失因子输入，复合权重以 artifacts 中的实际权重为准。</div>
      ) : null}
    </section>
  );
}

export function MacroArtifactPanel({ detail }: { detail: ResearchRunDetail }) {
  const coverage = (detail.manifest.coverage_summary ?? {}) as Record<string, unknown>;
  const count = toNumber(coverage.macro_observation_count) ?? 0;
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between"><div><h2 className="text-base font-semibold text-slate-50">宏观数据状态</h2><div className="mt-1 text-xs text-slate-500">真实运行 manifest</div></div><Waves className="h-4 w-4 text-signal-cyan" /></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="panel-soft p-4"><div className="text-xs text-slate-500">宏观观测数量</div><div className="mt-2 text-2xl font-semibold text-slate-50">{count}</div></div>
        <div className="panel-soft p-4"><div className="text-xs text-slate-500">仓位乘数状态</div><div className={count === 0 ? "mt-2 text-lg font-semibold text-signal-amber" : "mt-2 text-lg font-semibold text-signal-green"}>{count === 0 ? "使用中性乘数" : "使用已公布宏观记录"}</div></div>
      </div>
      {count === 0 ? <div className="mt-4 text-sm text-slate-400">当前运行没有真实宏观观察值，结果中的宏观调整不应被解释为有效宏观判断。</div> : null}
    </section>
  );
}

export function WarningSummaryPanel({ data }: { data: ResearchWarningsResponse }) {
  const categories = Object.entries(data.summary.categories).filter(([, count]) => count > 0);
  return (
    <section className="panel p-5">
      <div className="flex items-center justify-between"><div><h2 className="text-base font-semibold text-slate-50">Warning 摘要</h2><div className="mt-1 text-xs text-slate-500">共 {data.summary.total} 条，不默认展开全部内容</div></div><AlertTriangle className="h-4 w-4 text-signal-amber" /></div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {categories.map(([category, count]) => (
          <div key={category} className="panel-soft p-4">
            <div className="flex justify-between gap-3"><span className="text-sm text-slate-200">{category}</span><span className="font-mono text-sm text-signal-amber">{count}</span></div>
            <div className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{(data.summary.samples[category] ?? []).map((sample) => <div key={sample}>{sample}</div>)}</div>
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
