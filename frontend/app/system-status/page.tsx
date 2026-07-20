"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Globe2,
  Server
} from "lucide-react";
import {
  ResearchBoundary,
  SectionHeader
} from "@/components/dashboard-sections";
import { useResearchData } from "@/components/research-data-provider";
import { DataSourceBanner } from "@/components/real-run-sections";
import { machineLabel, ui } from "@/i18n";

export default function SystemStatusPage() {
  const {
    health,
    loading,
    error,
    dataSource,
    runList,
    realDetail,
    lastApiCheck
  } = useResearchData();
  const latest = realDetail?.summary ?? runList[0] ?? null;
  const apiAvailable = health?.status === "ok";
  const noArtifacts =
    health?.research_runs_available === true &&
    health.latest_run_available === false;

  const statusItems = [
    {
      label: ui.system.frontendStatus,
      value: machineLabel("serviceStatus", "running"),
      technicalValue: "running",
      detail: ui.system.frontendLoaded,
      healthy: true,
      icon: Activity
    },
    {
      label: ui.system.apiStatus,
      value: machineLabel("serviceStatus", apiAvailable ? health?.status ?? "ok" : "unavailable"),
      technicalValue: apiAvailable ? health?.status ?? "ok" : "unavailable",
      detail: apiAvailable ? health?.service ?? "Research API" : ui.system.noHealthResponse,
      healthy: apiAvailable,
      icon: Server
    },
    {
      label: ui.system.researchRuns,
      value: machineLabel("availability", health?.research_runs_available ? "available" : "unavailable"),
      technicalValue: health?.research_runs_available ? "available" : "unavailable",
      detail: health?.latest_run_available ? ui.system.persistedRunAvailable : ui.system.noLatestRun,
      healthy: health?.research_runs_available === true,
      icon: Database
    },
    {
      label: ui.system.apiTarget,
      value: summarizeApiTarget(),
      technicalValue: null,
      detail: ui.system.apiTargetDetail,
      healthy: apiTargetConfigured(),
      icon: Globe2
    }
  ];

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow={ui.pages.systemStatus.eyebrow}
        title={ui.pages.systemStatus.title}
        description={ui.pages.systemStatus.description}
        status={health}
        loading={loading}
        error={error}
      />

      {noArtifacts ? (
        <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4 text-sm text-slate-200">
          <div className="flex items-center gap-2 font-semibold text-signal-amber">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            {ui.system.noRealRunsTitle}
          </div>
          <p className="mt-2 text-slate-400">{ui.system.noRealRunsDetail}</p>
        </section>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {statusItems.map((item) => {
          const Icon = item.icon;
          return (
            <section key={item.label} className="panel min-h-40 p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-slate-500">{item.label}</span>
                <Icon className="h-4 w-4 text-signal-cyan" aria-hidden="true" />
              </div>
              <div className={item.healthy ? "mt-4 text-lg font-semibold text-signal-green" : "mt-4 text-lg font-semibold text-signal-amber"}>
                {item.value}
              </div>
              {item.technicalValue ? (
                <div className="mt-1 font-mono text-xs text-slate-500">{item.technicalValue}</div>
              ) : null}
              <p className="mt-2 text-xs leading-5 text-slate-500">{item.detail}</p>
            </section>
          );
        })}
      </div>

      <section className="panel p-5">
        <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-50">{ui.system.latestRun}</h2>
            <p className="mt-1 text-xs text-slate-500">{ui.system.publicFieldsOnly}</p>
          </div>
          {latest ? <CheckCircle2 className="h-4 w-4 text-signal-green" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4 text-signal-amber" aria-hidden="true" />}
        </div>
        <dl className="grid gap-x-8 md:grid-cols-2">
          <StatusRow label={ui.common.dataSource} value={machineLabel("dataSource", dataSource)} technicalValue={dataSource} />
          <StatusRow label={ui.system.latestRunId} value={latest?.run_id ?? ui.common.noRecords} mono />
          <StatusRow label={ui.system.latestRunStatus} value={latest ? machineLabel("runStatus", latest.run_status) : ui.common.noRecords} technicalValue={latest?.run_status} />
          <StatusRow label={ui.system.benchmark} value={latest ? machineLabel("availability", latest.benchmark_status) : ui.common.noRecords} technicalValue={latest?.benchmark_status} />
          <StatusRow label={ui.system.warningCount} value={latest ? String(latest.warning_count) : "0"} />
          <StatusRow
            label={ui.system.lastApiCheck}
            value={lastApiCheck ? `${machineLabel("serviceStatus", lastApiCheck.status)} · ${formatCheckTime(lastApiCheck.checkedAt)}` : ui.system.notCompleted}
            technicalValue={lastApiCheck?.status}
          />
        </dl>
        {lastApiCheck ? (
          <p className="mt-4 border-t border-white/10 pt-4 text-sm text-slate-400">{lastApiCheck.message}</p>
        ) : null}
      </section>

      <ResearchBoundary />
    </div>
  );
}

function StatusRow({
  label,
  value,
  mono = false,
  technicalValue
}: {
  label: string;
  value: string;
  mono?: boolean;
  technicalValue?: string | null;
}) {
  return (
    <div className="flex min-h-14 items-center justify-between gap-4 border-b border-white/10 py-3">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className={mono ? "max-w-[65%] break-all text-right font-mono text-sm text-slate-200" : "max-w-[65%] text-right text-sm text-slate-200"}>
        <span>{value}</span>
        {technicalValue ? <span className="ml-2 font-mono text-xs text-slate-500">({technicalValue})</span> : null}
      </dd>
    </div>
  );
}

function configuredApiUrl(): string | undefined {
  return process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
}

function apiTargetConfigured(): boolean {
  const configured = configuredApiUrl();
  if (!configured) return process.env.NODE_ENV !== "production";
  try {
    const url = new URL(configured);
    const local = url.hostname === "127.0.0.1" || url.hostname === "localhost";
    return local || url.protocol === "https:";
  } catch {
    return false;
  }
}

function summarizeApiTarget(): string {
  const configured = configuredApiUrl();
  if (!configured) {
    return process.env.NODE_ENV === "production" ? ui.system.productionApiMissing : ui.system.localHttpApi;
  }
  try {
    const url = new URL(configured);
    const local = url.hostname === "127.0.0.1" || url.hostname === "localhost";
    if (local) return ui.system.localHttpApi;
    return `${url.protocol === "https:" ? "HTTPS" : "HTTP"} · ${url.hostname}`;
  } catch {
    return ui.system.invalidApiUrl;
  }
}

function formatCheckTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? ui.system.timeUnavailable : date.toLocaleString("zh-CN");
}
