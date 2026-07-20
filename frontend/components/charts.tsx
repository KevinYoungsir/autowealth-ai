"use client";

import type { EquityPoint } from "@/lib/types";
import { compactDate, formatPercent, toNumber } from "@/lib/format";
import { ui } from "@/i18n";

export function EquityCurveChart({
  points,
  height = 280
}: {
  points: EquityPoint[];
  height?: number;
}) {
  const normalized = points
    .map((point) => ({ ...point, equity: toNumber(point.equity) ?? 0 }))
    .filter((point) => Number.isFinite(point.equity));

  if (normalized.length < 2) {
    return (
      <div className="flex h-72 items-center justify-center rounded-lg border border-dashed border-white/15 text-sm text-slate-500">
        {ui.common.pendingData}
      </div>
    );
  }

  const sample = samplePoints(normalized, 120);
  const values = sample.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const width = 900;
  const topPad = 18;
  const bottomPad = 34;
  const usableHeight = height - topPad - bottomPad;

  const coords = sample.map((point, index) => {
    const x = sample.length === 1 ? 0 : (index / (sample.length - 1)) * width;
    const y = topPad + (1 - (point.equity - min) / spread) * usableHeight;
    return { x, y, point };
  });
  const polyline = coords.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `0,${height - bottomPad} ${polyline} ${width},${height - bottomPad}`;
  const first = normalized[0];
  const last = normalized[normalized.length - 1];

  return (
    <div className="relative">
      <svg
        role="img"
        aria-label={ui.aria.equityCurve}
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full overflow-visible"
      >
        <rect x="0" y="0" width={width} height={height} rx="8" fill="#0d1118" />
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line
            key={ratio}
            x1="0"
            x2={width}
            y1={topPad + ratio * usableHeight}
            y2={topPad + ratio * usableHeight}
            stroke="rgba(255,255,255,0.08)"
          />
        ))}
        <polygon points={area} fill="rgba(45, 212, 191, 0.14)" />
        <polyline
          points={polyline}
          fill="none"
          stroke="#2dd4bf"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="3"
        />
        <circle cx={coords[coords.length - 1].x} cy={coords[coords.length - 1].y} r="5" fill="#f5c451" />
        <text x="12" y={height - 12} fill="#94a3b8" fontSize="22">
          {compactDate(first.date)}
        </text>
        <text x={width - 110} y={height - 12} fill="#94a3b8" fontSize="22">
          {compactDate(last.date)}
        </text>
      </svg>
    </div>
  );
}

export function WeightBars({ weights }: { weights: Record<string, number> }) {
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    return <div className="text-sm text-slate-500">{ui.common.pendingData}</div>;
  }

  const max = Math.max(...entries.map(([, weight]) => weight), 0.01);

  return (
    <div className="space-y-3">
      {entries.map(([symbol, weight]) => (
        <div key={symbol} className="grid grid-cols-[72px_1fr_68px] items-center gap-3">
          <div className="font-mono text-sm text-slate-200">{symbol}</div>
          <div className="h-2.5 rounded-full bg-white/7">
            <div
              className="h-2.5 rounded-full bg-signal-teal"
              style={{ width: `${Math.max(4, (weight / max) * 100)}%` }}
            />
          </div>
          <div className="text-right font-mono text-sm text-slate-300">{formatPercent(weight)}</div>
        </div>
      ))}
    </div>
  );
}

function samplePoints<T>(points: T[], limit: number): T[] {
  if (points.length <= limit) return points;
  const result: T[] = [];
  for (let index = 0; index < limit; index += 1) {
    const sourceIndex = Math.round((index / (limit - 1)) * (points.length - 1));
    result.push(points[sourceIndex]);
  }
  return result;
}
