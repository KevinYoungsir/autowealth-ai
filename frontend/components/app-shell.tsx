"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BrainCircuit,
  Gauge,
  LayoutDashboard,
  PieChart,
  RefreshCw,
  ShieldCheck,
  Waves
} from "lucide-react";
import { useResearchData } from "./research-data-provider";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/backtest", label: "Backtest", icon: BarChart3 },
  { href: "/portfolio", label: "Portfolio", icon: PieChart },
  { href: "/factors", label: "Factors", icon: Gauge },
  { href: "/macro", label: "Macro", icon: Waves },
  { href: "/research-notes", label: "Research Notes", icon: BrainCircuit }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { refresh, loading, health } = useResearchData();

  return (
    <div className="relative min-h-screen bg-ink-950 text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-72 border-r border-white/10 bg-ink-900/95 px-4 py-5 lg:block">
        <div className="mb-7 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-signal-teal/40 bg-signal-teal/10">
            <Activity className="h-5 w-5 text-signal-teal" aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-50">AutoWealth</div>
            <div className="text-xs text-slate-400">Research cockpit</div>
          </div>
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "flex h-11 items-center gap-3 rounded-lg px-3 text-sm transition",
                  active
                    ? "border border-signal-cyan/30 bg-signal-cyan/10 text-slate-50"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                ].join(" ")}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-10 border-b border-white/10 bg-ink-950/88 px-4 py-3 backdrop-blur md:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-signal-green" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-slate-100">outlook.xin prototype</div>
                <div className="text-xs text-slate-500">研究展示 · mock API · 非交易系统</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
                API {health?.mock_mode ? "mock" : "unknown"}
              </span>
              <button
                type="button"
                onClick={() => void refresh()}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-signal-teal/30 bg-signal-teal/10 px-3 text-sm text-slate-100 transition hover:bg-signal-teal/15 disabled:cursor-wait disabled:opacity-60"
                disabled={loading}
              >
                <RefreshCw className={["h-4 w-4", loading ? "animate-spin" : ""].join(" ")} aria-hidden="true" />
                <span>Refresh</span>
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1560px] px-4 py-5 md:px-6 md:py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
