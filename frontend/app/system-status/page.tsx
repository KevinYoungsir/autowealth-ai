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
      label: "前端运行状态",
      value: "running",
      detail: "Next.js 页面已加载",
      healthy: true,
      icon: Activity
    },
    {
      label: "API 运行状态",
      value: apiAvailable ? health?.status ?? "ok" : "unavailable",
      detail: apiAvailable ? health?.service ?? "Research API" : "未收到有效健康响应",
      healthy: apiAvailable,
      icon: Server
    },
    {
      label: "Research runs",
      value: health?.research_runs_available ? "available" : "unavailable",
      detail: health?.latest_run_available ? "存在已落盘运行" : "没有可用的最新运行",
      healthy: health?.research_runs_available === true,
      icon: Database
    },
    {
      label: "API 地址摘要",
      value: summarizeApiTarget(),
      detail: "仅显示协议类别和公开主机，不显示变量原值",
      healthy: apiTargetConfigured(),
      icon: Globe2
    }
  ];

  return (
    <div className="space-y-5">
      <DataSourceBanner source={dataSource} summary={realDetail?.summary} />
      <SectionHeader
        eyebrow="System Status"
        title="部署与数据状态"
        description="只读检查前端、研究 API 和已落盘运行，不触发研究任务。"
        status={health}
        loading={loading}
        error={error}
      />

      {noArtifacts ? (
        <section className="rounded-lg border border-signal-amber/30 bg-signal-amber/10 p-4 text-sm text-slate-200">
          <div className="flex items-center gap-2 font-semibold text-signal-amber">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            暂无真实研究运行
          </div>
          <p className="mt-2 text-slate-400">API 已启动且运行目录可访问，当前看板使用明确标记的演示数据。</p>
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
              <p className="mt-2 text-xs leading-5 text-slate-500">{item.detail}</p>
            </section>
          );
        })}
      </div>

      <section className="panel p-5">
        <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-50">最近运行状态</h2>
            <p className="mt-1 text-xs text-slate-500">仅显示公开研究摘要字段</p>
          </div>
          {latest ? <CheckCircle2 className="h-4 w-4 text-signal-green" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4 text-signal-amber" aria-hidden="true" />}
        </div>
        <dl className="grid gap-x-8 md:grid-cols-2">
          <StatusRow label="数据来源" value={dataSource} />
          <StatusRow label="最新 run_id" value={latest?.run_id ?? "暂无"} mono />
          <StatusRow label="最新 run_status" value={latest?.run_status ?? "暂无"} />
          <StatusRow label="Benchmark" value={latest?.benchmark_status ?? "暂无"} />
          <StatusRow label="Warning 数量" value={latest ? String(latest.warning_count) : "0"} />
          <StatusRow
            label="最后 API 检查"
            value={lastApiCheck ? `${lastApiCheck.status} · ${formatCheckTime(lastApiCheck.checkedAt)}` : "尚未完成"}
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
  mono = false
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex min-h-14 items-center justify-between gap-4 border-b border-white/10 py-3">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className={mono ? "max-w-[65%] break-all text-right font-mono text-sm text-slate-200" : "text-right text-sm text-slate-200"}>{value}</dd>
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
    return process.env.NODE_ENV === "production" ? "生产 API 未配置" : "本地 HTTP API";
  }
  try {
    const url = new URL(configured);
    const local = url.hostname === "127.0.0.1" || url.hostname === "localhost";
    if (local) return "本地 HTTP API";
    return `${url.protocol === "https:" ? "HTTPS" : "HTTP"} · ${url.hostname}`;
  } catch {
    return "API 地址格式无效";
  }
}

function formatCheckTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "时间不可用" : date.toLocaleString("zh-CN");
}
