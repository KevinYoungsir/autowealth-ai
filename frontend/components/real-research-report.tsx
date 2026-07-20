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
import { machineLabel, ui } from "@/i18n";
import { groupWarningPresentations } from "@/lib/warning-presentations";
import type {
  ArtifactReportSection,
  RealResearchReport,
  ResearchDataSource,
  WarningPresentation
} from "@/lib/types";

export function ResearchReportMetadata({
  dataSource,
  runId,
  runStatus,
  generatedMode,
  locale
}: {
  dataSource: ResearchDataSource;
  runId: string;
  runStatus: string;
  generatedMode: string;
  locale: string;
}) {
  const values = [
    [ui.report.metadata.dataSource, dataSource, machineLabel("dataSource", dataSource)],
    [ui.report.metadata.runId, runId, runId],
    [ui.report.metadata.runStatus, runStatus, machineLabel("runStatus", runStatus)],
    [ui.report.metadata.generatedMode, generatedMode, machineLabel("generatedMode", generatedMode)],
    ["locale", locale, locale]
  ];
  return (
    <section className="panel grid divide-y divide-white/10 md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-5">
      {values.map(([label, value, displayValue]) => (
        <div key={label} className="min-w-0 px-4 py-3">
          <div className="text-xs text-slate-500">{label}</div>
          <div
            className={`mt-1 break-words text-sm font-semibold ${
              value === "partial_success"
                ? "text-signal-amber"
                : "text-slate-100"
            }`}
          >
            {displayValue}
          </div>
          {displayValue !== value ? <div className="mt-1 break-all font-mono text-xs text-slate-500">{value}</div> : null}
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
  const parsedWarningPresentations = asWarningPresentations(
    report.data_quality_review.evidence.warning_presentations
  );
  const warningPresentations = parsedWarningPresentations.length
    ? parsedWarningPresentations
    : warnings.map((sourceMessage) => ({
        source_message: sourceMessage,
        display_message: ui.report.warningFallback,
        category: "system",
        category_label: machineLabel("warningCategory", "system")
      }));
  const warningGroups = groupWarningPresentations(warningPresentations, 3);
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
          title={ui.report.sections.executiveSummary}
          subtitle={machineLabel("reportStatus", report.executive_summary.status)}
          technicalSubtitle={report.executive_summary.status}
          icon={Database}
        />
        <p className="prose-copy mt-4 text-sm leading-7 text-slate-300">
          {report.executive_summary.summary}
        </p>
        <ObservationList section={report.executive_summary} />
      </section>

      <section className="panel p-5">
        <ReportHeading
          title={ui.report.sections.performanceReview}
          subtitle={machineLabel("reportStatus", report.performance_review.status)}
          technicalSubtitle={report.performance_review.status}
          icon={BarChart3}
        />
        <p className="mt-4 text-sm leading-6 text-slate-400">
          {report.performance_review.summary}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10 md:grid-cols-4 xl:grid-cols-7">
          {[
            [ui.metrics.annualized_return, formatPercent(metrics.annualized_return)],
            [ui.metrics.total_return, formatPercent(metrics.total_return)],
            [ui.metrics.max_drawdown, formatPercent(metrics.max_drawdown)],
            [ui.metrics.volatility, formatPercent(metrics.volatility)],
            [ui.metrics.sharpe_ratio, formatNumber(metrics.sharpe_ratio)],
            [ui.metrics.calmar_ratio, formatNumber(metrics.calmar_ratio)],
            [ui.metrics.turnover, formatPercent(metrics.turnover)]
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
          title={ui.report.sections.riskFlags}
          subtitle={ui.common.flags(report.risk_flags.length)}
          icon={AlertTriangle}
        />
        <div className="mt-4 divide-y divide-white/10">
          {report.risk_flags.map((flag) => (
            <div key={flag.code} className="grid gap-2 py-4 md:grid-cols-[180px_1fr]">
              <div>
                <div className="text-sm font-semibold text-slate-100">{flag.title}</div>
                <div className={`mt-1 text-xs ${severityClass(flag.severity)}`}>
                  {machineLabel("severity", flag.severity)} / {machineLabel("warningCategory", flag.category)}
                </div>
                <div className="mt-1 font-mono text-xs text-slate-500">
                  {flag.code} · {flag.severity} / {flag.category}
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
            title={ui.report.sections.factorReview}
            subtitle={machineLabel("reportStatus", report.factor_review.status)}
            technicalSubtitle={report.factor_review.status}
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
                  <span className="text-slate-300">{machineLabel("factor", name)}<span className="ml-2 font-mono text-xs text-slate-500">{name}</span></span>
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
            title={ui.report.sections.benchmarkReview}
            subtitle={machineLabel("reportStatus", report.benchmark_review.status)}
            technicalSubtitle={report.benchmark_review.status}
            icon={Gauge}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.benchmark_review.summary}
          </p>
          <div className="mt-4 divide-y divide-white/10">
            {Object.entries(benchmarkReasons).map(([symbol, reason]) => (
              <div key={symbol} className="py-3">
                <div className="font-mono text-sm text-signal-amber">{symbol}</div>
                <details className="mt-1 text-xs leading-5 text-slate-500">
                  <summary className="cursor-pointer">{ui.report.viewRawDetails}</summary>
                  <div className="mt-2 break-words font-mono">{String(reason)}</div>
                </details>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-5">
          <ReportHeading
            title={ui.report.sections.macroReview}
            subtitle={machineLabel("reportStatus", report.macro_review.status)}
            technicalSubtitle={report.macro_review.status}
            icon={Gauge}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.macro_review.summary}
          </p>
          <div className="mt-4 border-t border-white/10 pt-4">
            <div className="text-xs text-slate-500">{ui.report.macroObservationCount}</div>
            <div className="font-mono text-[11px] text-slate-600">macro_observation_count</div>
            <div className="mt-1 font-mono text-xl font-semibold text-slate-100">
              {macroCount ?? 0}
            </div>
          </div>
        </section>

        <section className="panel p-5">
          <ReportHeading
            title={ui.report.sections.dataQualityReview}
            subtitle={ui.common.warnings(report.warning_count)}
            icon={FileWarning}
          />
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {report.data_quality_review.summary}
          </p>
          <WarningOverview groups={warningGroups} warningCount={report.warning_count} />
        </section>
      </div>

      <section className="panel p-5">
        <ReportHeading
          title={ui.report.sections.counterarguments}
          subtitle={ui.common.items(report.counterarguments.length)}
          icon={Scale}
        />
        <div className="mt-4 divide-y divide-white/10">
          {report.counterarguments.map((item) => (
            <div key={item.topic} className="grid gap-3 py-4 lg:grid-cols-[220px_1fr]">
              <div className="text-sm font-semibold text-slate-100">{item.topic}</div>
              <div>
                <p className="text-sm leading-6 text-slate-300">{item.argument}</p>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {ui.report.evidenceNeeded}：{item.evidence_needed.join(" / ")}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-5">
        <ReportHeading
          title={ui.report.sections.researchBoundaries}
          subtitle={machineLabel("reportStatus", report.research_boundaries.status)}
          technicalSubtitle={report.research_boundaries.status}
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

function WarningOverview({
  groups,
  warningCount
}: {
  groups: ReturnType<typeof groupWarningPresentations>;
  warningCount: number;
}) {
  if (!warningCount) {
    return <div className="mt-4 text-sm text-slate-500">{ui.report.noWarnings}</div>;
  }
  return (
    <div className="mt-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-100">{ui.report.warningOverview}</h3>
        <span className="font-mono text-xs text-signal-amber">{warningCount}</span>
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {groups.map((group) => (
          <div key={group.category} className="panel-soft min-w-0 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-200">{group.categoryLabel}</div>
                <div className="mt-1 font-mono text-xs text-slate-500">{group.category}</div>
              </div>
              <span className="font-mono text-sm text-signal-amber">{group.count}</span>
            </div>
            <div className="mt-3 space-y-2">
              {group.samples.map((sample, index) => (
                <p key={`${group.category}-${index}`} className="break-words text-xs leading-6 text-slate-400">
                  {sample.display_message}
                </p>
              ))}
            </div>
            <details className="mt-3 border-t border-white/10 pt-3 text-xs text-slate-500">
              <summary className="cursor-pointer text-slate-400">{ui.report.viewRawDetails}</summary>
              <div className="mt-3 max-h-72 space-y-3 overflow-y-auto pr-2" aria-label={ui.aria.originalWarnings}>
                {group.items.map((item, index) => (
                  <div key={`${group.category}-raw-${index}`} className="break-words font-mono leading-5">
                    <span className="mr-2 text-slate-600">{index + 1}</span>
                    {item.source_message}
                  </div>
                ))}
              </div>
            </details>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportHeading({
  title,
  subtitle,
  technicalSubtitle,
  icon: Icon
}: {
  title: string;
  subtitle: string;
  technicalSubtitle?: string;
  icon: typeof Database;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-slate-50">{title}</h2>
        <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
        {technicalSubtitle && technicalSubtitle !== subtitle ? (
          <div className="mt-0.5 font-mono text-[11px] text-slate-600">{technicalSubtitle}</div>
        ) : null}
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

function asWarningPresentations(value: unknown): WarningPresentation[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is WarningPresentation => {
    if (!item || typeof item !== "object") return false;
    const record = item as Record<string, unknown>;
    return (
      typeof record.source_message === "string" &&
      typeof record.display_message === "string" &&
      typeof record.category === "string" &&
      typeof record.category_label === "string"
    );
  });
}

function severityClass(severity: string): string {
  if (severity === "critical" || severity === "high") return "text-signal-red";
  if (severity === "medium") return "text-signal-amber";
  return "text-signal-cyan";
}
