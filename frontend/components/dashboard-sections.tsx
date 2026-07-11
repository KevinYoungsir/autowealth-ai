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
            {loading ? "Syncing" : status?.status === "ok" ? "API online" : "API pending"}
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
      label: "年化收益",
      value: formatPercent(metrics?.annualized_return),
      icon: LineChart,
      accent: "text-signal-teal"
    },
    {
      label: "最大回撤",
      value: formatPercent(metrics?.max_drawdown),
      icon: Shield,
      accent: "text-signal-red"
    },
    {
      label: "夏普比率",
      value: formatNumber(metrics?.sharpe_ratio),
      icon: Gauge,
      accent: "text-signal-cyan"
    },
    {
      label: "卡玛比率",
      value: formatNumber(metrics?.calmar_ratio),
      icon: Scale,
      accent: "text-signal-amber"
    },
    {
      label: "现金仓位",
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
  subtitle = "Mock research equity curve"
}: {
  equityCurve: EquityPoint[];
  tall?: boolean;
  subtitle?: string;
}) {
  return (
    <section className="panel p-5">
      <PanelTitle title="权益曲线" subtitle={subtitle} icon={LineChart} />
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
      <PanelTitle title="目标持仓权重" subtitle={`现金仓位 ${formatWeight(cashWeight)}`} icon={WalletCards} />
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
      <PanelTitle title="组合明细" subtitle={`${rows.length} 个研究标的`} icon={WalletCards} />
      <div className="mt-4 overflow-hidden rounded-lg border border-white/10">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.14em] text-slate-500">
            <tr>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Weight</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">State</th>
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
                    research target
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
      <PanelTitle title="候选过滤记录" subtitle={`${Object.keys(rejected).length} 条记录`} icon={AlertTriangle} />
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {Object.entries(rejected).map(([symbol, reason]) => (
          <div key={symbol} className="panel-soft p-4">
            <div className="font-mono text-sm text-slate-100">{symbol}</div>
            <div className="mt-2 text-sm text-slate-400">{reason}</div>
          </div>
        ))}
        {warnings.map((warning) => (
          <div key={warning} className="panel-soft p-4 text-sm text-slate-400">
            {warning}
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
      <PanelTitle title="因子分布" subtitle="Composite score buckets" icon={Gauge} />
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
        <SmallStat label="Mean" value={formatNumber(factor?.mean_score, 1)} />
        <SmallStat label="Min" value={formatNumber(factor?.min_score, 1)} />
        <SmallStat label="Max" value={formatNumber(factor?.max_score, 1)} />
      </div>
    </section>
  );
}

export function FactorTablePanel({ scores }: { scores: Record<string, number> }) {
  const rows = Object.entries(scores).sort((a, b) => b[1] - a[1]);

  return (
    <section className="panel p-5">
      <PanelTitle title="评分排行" subtitle={`${rows.length} 个候选评分`} icon={Gauge} />
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
      <PanelTitle title="宏观状态" subtitle="Research regime snapshot" icon={Shield} />
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <SmallStat label="Regime" value={String(macro?.regime ?? "--")} />
        <SmallStat label="Multiplier" value={formatNumber(macro?.equity_position_multiplier, 2)} />
        <SmallStat label="Growth" value={formatNumber(macro?.growth_score, 1)} />
        <SmallStat label="External Risk" value={formatNumber(macro?.external_risk_score, 1)} />
      </div>
    </section>
  );
}

export function MacroDetailPanel({ macro }: { macro?: Record<string, any> }) {
  const metrics = [
    ["growth_score", "经济增长"],
    ["inflation_score", "通胀环境"],
    ["liquidity_score", "流动性"],
    ["credit_score", "信用周期"],
    ["policy_score", "政策环境"],
    ["external_risk_score", "外部风险"]
  ];

  return (
    <section className="panel p-5">
      <PanelTitle title="宏观维度" subtitle="0-100 research scale" icon={Shield} />
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
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  return (
    <section className="panel p-5">
      <PanelTitle title="月度 / 年度收益" subtitle="Reserved return matrix" icon={LineChart} />
      <div className="mt-4 grid grid-cols-3 gap-3 md:grid-cols-6 xl:grid-cols-12">
        {months.map((month) => (
          <div key={month} className="panel-soft p-3 text-center">
            <div className="text-xs text-slate-500">{month}</div>
            <div className="mt-2 text-sm text-slate-300">待接入</div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {["2021", "2022", "2023", "2024"].map((year) => (
          <div key={year} className="panel-soft p-4">
            <div className="text-xs text-slate-500">{year}</div>
            <div className="mt-2 text-lg font-semibold text-slate-300">待接入</div>
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
        <PanelTitle title="研究摘要" subtitle={report?.metadata?.model ? `model ${report.metadata.model}` : "mock"} icon={BrainCircuit} />
        <p className="mt-4 text-sm leading-6 text-slate-300">
          {report?.research_note?.summary ?? "等待 mock 研究报告"}
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
        <PanelTitle title="风险复核" subtitle={`${report?.risk_flags?.length ?? 0} flags`} icon={AlertTriangle} />
        <div className="mt-4 grid gap-3">
          {(report?.risk_flags ?? []).map((flag) => (
            <div key={`${flag.category}-${flag.description}`} className="panel-soft p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slate-100">{flag.category}</div>
                <span className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 px-2 py-1 text-xs text-signal-amber">
                  {flag.severity}
                </span>
              </div>
              <div className="mt-2 text-sm text-slate-400">{flag.description}</div>
              <div className="mt-2 text-xs text-slate-500">{flag.review_focus}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5 xl:col-span-2">
        <PanelTitle title="反方观点" subtitle={`${report?.counter_arguments?.length ?? 0} items`} icon={Scale} />
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {(report?.counter_arguments ?? []).map((item) => (
            <div key={item.topic} className="panel-soft p-4">
              <div className="text-sm font-semibold text-slate-100">{item.topic}</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">{item.argument}</div>
              <div className="mt-4 text-xs uppercase tracking-[0.14em] text-slate-500">Evidence</div>
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
      当前看板仅展示研究实验、mock 数据与结构化复核结果；历史指标不代表未来表现，不构成投资建议或交易指令。
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

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-soft p-4">
      <div className="text-xs uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}
