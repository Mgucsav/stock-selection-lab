"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate, formatNumber, formatPct, formatTL } from "@/lib/format";
import type { SeriesPoint } from "@/lib/types";

const SERIES_1 = "var(--series-1)";
const SERIES_2 = "var(--series-2)";

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
}

function ChartTooltip({ active, payload, label, mode }: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  mode: "value" | "normalized";
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded border border-border-strong bg-surface-2 px-3 py-2 text-xs shadow">
      <div className="mb-1 text-muted">{formatDate(String(label))}</div>
      {payload.map((item) => (
        <div key={item.name} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: item.color }} />
          <span className="text-secondary">{item.name}</span>
          <span className="num ml-auto">
            {typeof item.value === "number" ? (mode === "value" ? formatTL(item.value) : formatNumber(item.value, 1)) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function PortfolioChart({ series, mode, benchmarkAvailable, height = 280 }: {
  series: SeriesPoint[];
  mode: "value" | "normalized";
  benchmarkAvailable: boolean;
  height?: number;
}) {
  if (series.length === 0) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted">Değerleme serisi yok.</div>;
  }
  const portfolioKey = mode === "value" ? "value" : "portfolio_norm";
  const benchKey = mode === "value" ? "benchmark_value" : "benchmark_norm";
  const showBench = benchmarkAvailable && mode === "normalized";
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={series} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="date" tickFormatter={(v: string) => formatDate(v).slice(0, 5)} stroke="var(--text-muted)" tick={{ fontSize: 11 }} minTickGap={32} />
          <YAxis
            stroke="var(--text-muted)"
            tick={{ fontSize: 11 }}
            width={64}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => (mode === "value" ? `${Math.round(v / 1000)}k` : formatNumber(v, 0))}
          />
          <Tooltip content={<ChartTooltip mode={mode} />} cursor={{ stroke: "var(--border-strong)" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey={portfolioKey} name="Model portföy" stroke={SERIES_1} strokeWidth={2} dot={false} isAnimationActive={false} />
          {showBench && (
            <Line type="monotone" dataKey={benchKey} name="BIST 100 (XU100)" stroke={SERIES_2} strokeWidth={2} dot={false} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
      {mode === "normalized" && !benchmarkAvailable && (
        <p className="mt-1 text-xs text-warning">⚠ BIST 100 benchmark verisi bulunamadı; karşılaştırma çizgisi gösterilemiyor.</p>
      )}
    </div>
  );
}

/** Ağırlık dağılımı: yatay ince çubuklar, doğrudan etiketli. */
export function AllocationBars({ items, max }: { items: Array<{ label: string; value: number; hint?: string }>; max?: number }) {
  const top = max ?? Math.max(...items.map((i) => i.value), 0.0001);
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.label} className="grid grid-cols-[80px_1fr_56px] items-center gap-2 text-xs">
          <span className="num truncate text-secondary" title={item.hint}>{item.label}</span>
          <span className="h-2 overflow-hidden rounded-sm bg-surface-2">
            <span className="block h-full rounded-sm bg-series-1" style={{ width: `${Math.min(100, (item.value / top) * 100)}%` }} />
          </span>
          <span className="num text-right">{formatPct(item.value, 1)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Tek hissenin fiyat grafiği (günlük veya gün içi barlar). Renk: seri-1; referans çizgi: önceki kapanış. */
export function PriceChart({ bars, intraday, referencePrice, height = 320 }: {
  bars: Array<{ t: string; c: number | null; v: number | null }>;
  intraday: boolean;
  referencePrice?: number | null;
  height?: number;
}) {
  const data = bars.filter((b) => b.c !== null).map((b) => ({ t: b.t, c: b.c as number, v: b.v ?? 0 }));
  if (data.length === 0) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted">Bu aralık için veri yok.</div>;
  }
  const first = data[0].c;
  const last = data[data.length - 1].c;
  const stroke = last >= first ? "var(--good)" : "var(--critical)";
  const fmtTick = (t: string) => (intraday ? t.slice(11, 16) : formatDate(t).slice(0, 5));
  const fmtLabel = (t: string) => (intraday ? `${formatDate(t)} ${t.slice(11, 16)}` : formatDate(t));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmtTick} stroke="var(--text-muted)" tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} width={64} domain={["auto", "auto"]} tickFormatter={(v: number) => formatNumber(v, 2)} />
        <Tooltip
          cursor={{ stroke: "var(--border-strong)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload || payload.length === 0) return null;
            const point = payload[0].payload as { c: number; v: number };
            return (
              <div className="rounded border border-border-strong bg-surface-2 px-3 py-2 text-xs shadow">
                <div className="text-muted">{fmtLabel(String(label))}</div>
                <div className="num">Fiyat: {formatNumber(point.c, 2)} ₺</div>
                <div className="num text-secondary">Hacim: {formatNumber(point.v, 0)}</div>
              </div>
            );
          }}
        />
        {referencePrice != null && (
          <ReferenceLine y={referencePrice} stroke="var(--text-muted)" strokeDasharray="4 4" label={{ value: "önceki kapanış", fill: "var(--text-muted)", fontSize: 10, position: "insideTopRight" }} />
        )}
        <Line type="monotone" dataKey="c" name="Fiyat" stroke={stroke} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
