"use client";

import {
  AlertTriangle,
  BarChart3,
  Database,
  FileWarning,
  Gauge,
  Layers3,
  Scale,
  ShieldCheck
} from "lucide-react";
import { formatNumber, formatPercent, toNumber } from "@/lib/format";
import type {
  ArtifactReportSection,
  RealResearchReport,
  ResearchDataSource
} from "@/lib/types";

export function ResearchReportMetadata({
  dataSource,
  runId,
  runStatus,
  generatedMode
}: {
  dataSource: ResearchDataSource;
  runId: string;
  runStatus: string;
  generatedMode: string;
}) {
  const values = [
    ["data_source", dataSource],
    ["run_id", runId],
    ["run_status", runStatus],
    ["generated_mode", generatedMode]
  ];
  return (
    <section className="panel grid divide-y divide-white/10 md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-4">
      {values.map(([label, value]) => (
        <div key={label} className="min-w-0 px-4 py-3">
          <div className="text-xs text-slate-500">{label}</div>
          <div
            className={`mt-1 break-words font-mono text-sm font-semibold ${
              label === "run_status" && value === "partial_success"
                ? "text-signal-amber"
                : "text-slate-100"
            }`}
          >
            {value}
          </div>
        </div>
      ))}
    </section>
  );
}

export function RealResearchReportPanel({
  report
}: {
  report: RealResearchReport;
}) {
  const metrics = asRecord(report.performance_review.evidence.core_metrics);
  const warnings = asStrings(report.data_quality_review.evidence.warnings);
  const warningCategories = asRecord(
    report.data_quality_review.evidence.warning_categories
  );
  const factorCoverage = asRecord(report.factor_review.evidence.coverage_overall);
  const benchmarkReasons = asRecord(
    report.benchmark_review.evidence.unavailable_reasons
  );
  const macroCount = toNumber(
    report.macro_review.evidence.macro_observation_count
  );

  return (
    <div className="space-y-5">
      <section className="panel p-5">
        <ReportHeading
          title="执行摘要"
          subtitle={report.executive_summary.status}
          icon={Database}
        />
        <p className="mt-4 text-sm leading-7 text-slate-300">
          {report.executive_summary.summary}
        </p>
        <ObservationList section={report.executive_summary} />
      </section>

      <section className="panel p-5">
        <ReportHeading
          title="历史表现复核"
          subtitle={report.performance_review.status}
          icon={BarChart3}
        />
        <p className="mt-4 text-sm leading-6 text-slate-400">
          {report.performance_review.summary}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10 md:grid-cols-4 xl:grid-cols-7">
          {[
            ["年化收益", formatPercent(metrics.annualized_return)],
            ["总收益", formatPercent(metrics.total_return)],
            ["最大回撤", formatPercent(metrics.max_drawdown)],
            ["波动率", formatPercent(metrics.volatility)],
            ["夏普比率", formatNumber(metrics.sharpe_ratio)],
            ["卡玛比率", formatNumber(metrics.calmar_ratio)],
            ["换手率", formatPercent(metrics.turnover)]
          ].map(([label, value]) => (
            <div key={label} className="bg-ink-900 px-3 py-4">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="mt-2 font-mono text-sm font-semibold text-slate-100">
                {value}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <ReportHeading
          title="风险复核"
          subtitle={`${report.risk_flags.length} flags`}
          icon={AlertTriangle}
        />
        <div className="mt-4 divide-y divide-white/10">
          {report.risk_flags.map((flag) => (
            <div key={flag.code} className="grid gap-2 py-4 md:grid-cols-[180px_1fr]">
              <div>
                <div className="text-sm font-semibold text-slate-100">{flag.title}</div>
                <div className="mt-1 font-mono text-xs text-signal-amber">
                  {flag.severity} / {flag.category}
                </div>
              </div>
              <div>
                <p className="text-sm leading-6 text-slate-300">{flag.description}</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  {flag.review_focus}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="panel p-5">
          <ReportHeading
            title="因子复核"
            subtitle={report.factor_review.status}
            icon={Layers3}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.factor_review.summary}
          </p>
          <div className="mt-4 divide-y divide-white/10">
            {Object.entries(factorCoverage).map(([name, raw]) => {
              const coverage = asRecord(raw);
              return (
                <div key={name} className="flex items-center justify-between gap-3 py-3 text-sm">
                  <span className="text-slate-300">{name}</span>
                  <span className="font-mono text-slate-100">
                    {formatPercent(coverage.coverage_ratio)} · {String(coverage.available_count ?? 0)}/
                    {String(
                      Number(coverage.available_count ?? 0) +
                        Number(coverage.missing_count ?? 0)
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel p-5">
          <ReportHeading
            title="基准复核"
            subtitle={report.benchmark_review.status}
            icon={Gauge}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.benchmark_review.summary}
          </p>
          <div className="mt-4 divide-y divide-white/10">
            {Object.entries(benchmarkReasons).map(([symbol, reason]) => (
              <div key={symbol} className="py-3">
                <div className="font-mono text-sm text-signal-amber">{symbol}</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">{String(reason)}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-5">
          <ReportHeading
            title="宏观复核"
            subtitle={report.macro_review.status}
            icon={Gauge}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.macro_review.summary}
          </p>
          <div className="mt-4 border-t border-white/10 pt-4">
            <div className="text-xs text-slate-500">macro_observation_count</div>
            <div className="mt-1 font-mono text-xl font-semibold text-slate-100">
              {macroCount ?? 0}
            </div>
          </div>
        </section>

        <section className="panel p-5">
          <ReportHeading
            title="数据质量复核"
            subtitle={`${report.warning_count} warnings`}
            icon={FileWarning}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.data_quality_review.summary}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10 sm:grid-cols-3">
            {Object.entries(warningCategories)
              .filter(([, count]) => Number(count) > 0)
              .map(([category, count]) => (
                <div key={category} className="bg-ink-900 px-3 py-3">
                  <div className="truncate text-xs text-slate-500">{category}</div>
                  <div className="mt-1 font-mono text-sm text-slate-100">{String(count)}</div>
                </div>
              ))}
          </div>
        </section>
      </div>

      <section className="panel p-5">
        <ReportHeading
          title="完整 Warning 记录"
          subtitle={`${warnings.length} persisted items`}
          icon={FileWarning}
        />
        <div className="mt-4 max-h-80 divide-y divide-white/10 overflow-y-auto border-y border-white/10 pr-2">
          {warnings.map((warning, index) => (
            <div key={`${index}-${warning}`} className="py-3 text-xs leading-5 text-slate-400">
              <span className="mr-3 font-mono text-slate-600">{index + 1}</span>
              {warning}
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <ReportHeading
          title="反方观点"
          subtitle={`${report.counterarguments.length} items`}
          icon={Scale}
        />
        <div className="mt-4 divide-y divide-white/10">
          {report.counterarguments.map((item) => (
            <div key={item.topic} className="grid gap-3 py-4 lg:grid-cols-[220px_1fr]">
              <div className="text-sm font-semibold text-slate-100">{item.topic}</div>
              <div>
                <p className="text-sm leading-6 text-slate-300">{item.argument}</p>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  复核证据：{item.evidence_needed.join(" / ")}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-5">
        <ReportHeading
          title="研究边界"
          subtitle={report.research_boundaries.status}
          icon={ShieldCheck}
        />
        <p className="mt-4 text-sm leading-7 text-slate-200">
          {report.research_boundaries.summary}
        </p>
        <ObservationList section={report.research_boundaries} />
      </section>
    </div>
  );
}

function ObservationList({ section }: { section: ArtifactReportSection }) {
  const items = [...section.observations, ...section.limitations];
  if (!items.length) return null;
  return (
    <ul className="mt-4 divide-y divide-white/10 border-y border-white/10 text-xs leading-5 text-slate-400">
      {items.map((item, index) => (
        <li key={`${index}-${item}`} className="py-2.5">
          {item}
        </li>
      ))}
    </ul>
  );
}

function ReportHeading({
  title,
  subtitle,
  icon: Icon
}: {
  title: string;
  subtitle: string;
  icon: typeof Database;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-slate-50">{title}</h2>
        <div className="mt-1 font-mono text-xs text-slate-500">{subtitle}</div>
      </div>
      <Icon className="h-4 w-4 text-signal-cyan" aria-hidden="true" />
    </div>
  );
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}
