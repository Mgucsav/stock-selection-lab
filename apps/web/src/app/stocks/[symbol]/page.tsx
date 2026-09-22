"use client";

import Link from "next/link";
import { use, useState } from "react";

import { PriceChart } from "@/components/charts";
import { DailySeriesTable, StockStatsPanel } from "@/components/StockStatsPanel";
import { Badge, Card, DemoBanner, ErrorBox, Loading, PageHeader, StatTile, WarningList } from "@/components/ui";
import { api } from "@/lib/api";
import { CRITERIA_LABELS, formatCompact, formatDate, formatNumber, formatPct, signClass } from "@/lib/format";
import { CRITERIA_ORDER, type HistoryInterval } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { usePolling } from "@/lib/usePolling";

const RANGES: Array<{ interval: HistoryInterval; label: string; hint: string }> = [
  { interval: "1m", label: "1G · 1dk", hint: "son 7 gün, 1 dakikalık" },
  { interval: "5m", label: "1A · 5dk", hint: "son 60 gün, 5 dakikalık" },
  { interval: "15m", label: "2A · 15dk", hint: "son 60 gün, 15 dakikalık" },
  { interval: "1h", label: "2Y · 1sa", hint: "son 730 gün, saatlik" },
  { interval: "1d", label: "3Y · günlük", hint: "günlük kapanış (cache)" },
];

export default function StockPage({ params }: PageProps<"/stocks/[symbol]">) {
  const { symbol } = use(params);
  return <StockDetail symbol={decodeURIComponent(symbol).toUpperCase()} />;
}

function StockDetail({ symbol }: { symbol: string }) {
  const summary = usePolling(() => api.stock(symbol), 60_000, [symbol]);
  const [interval, setRange] = useState<HistoryInterval>("1d");
  const history = useApi(() => api.stockHistory(symbol, interval), [symbol, interval]);
  const daily = useApi(() => api.stockHistory(symbol, "1d"), [symbol]);
  const s = summary.data;
  const q = s?.quote ?? null;

  if (summary.error && !s) return <ErrorBox message={summary.error} onRetry={summary.refresh} />;
  if (!s) return <Loading />;

  const bars = history.data?.bars ?? [];
  const dailyBars = daily.data?.bars ?? [];
  const intraday = interval !== "1d";
  const oneDayBars = interval === "1m" && bars.length > 0 ? bars.filter((b) => b.t.slice(0, 10) === bars[bars.length - 1].t.slice(0, 10)) : bars;

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${symbol.replace(".IS", "")} · ${s.name}`}
        description={<>{s.sector ?? "Sektör bilgisi yok"} · {s.in_universe ? "BIST 100 evreninde" : "Evren dışı"} · <Link href="/market" className="text-accent underline">Piyasa</Link></>}
      >
        <Badge tone="warning">≈15 dk gecikmeli</Badge>
        {summary.updatedAt && <span className="text-xs text-muted">Yenilendi {summary.updatedAt.toLocaleTimeString("tr-TR")}</span>}
        <button className="btn text-xs" onClick={summary.refresh}>Şimdi yenile</button>
      </PageHeader>
      <DemoBanner isDemo={s.is_demo} />

      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <div className="card flex flex-wrap items-end gap-6 p-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted">Son fiyat</div>
              <div className={`num text-4xl font-semibold ${signClass(q?.day_change)}`}>
                {q?.last_price != null ? formatNumber(q.last_price, 2) : formatNumber(s.daily_last_close, 2)} <span className="text-lg text-muted">₺</span>
              </div>
              <div className="text-xs text-muted">
                {q?.last_time ? `Fiyat zamanı ${formatDate(q.last_time)} ${q.last_time.slice(11, 16)} (borsa saati)` : `Günlük kapanış ${formatDate(s.daily_last_date)}`}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">Bugün</div>
              <div className={`num text-xl ${signClass(q?.day_change)}`}>
                {q?.day_change != null ? `${q.day_change > 0 ? "+" : ""}${formatNumber(q.day_change, 2)}` : "—"} ({formatPct(q?.day_change_pct, 2, true)})
              </div>
              <div className="text-xs text-muted">Önceki kapanış {formatNumber(q?.previous_close, 2)}</div>
            </div>
            <div className="num text-xs text-secondary">
              <div>Açılış <span className="text-primary">{formatNumber(q?.day_open, 2)}</span></div>
              <div>Yüksek <span className="text-primary">{formatNumber(q?.day_high, 2)}</span></div>
              <div>Düşük <span className="text-primary">{formatNumber(q?.day_low, 2)}</span></div>
              <div>Hacim <span className="text-primary">{formatCompact(q?.day_volume)} lot</span></div>
            </div>
            {q && q.outcome !== "ok" && <span className="text-xs text-warning">⚠ {q.message}</span>}
          </div>

          <Card
            title="Fiyat grafiği"
            subtitle={RANGES.find((r) => r.interval === interval)?.hint}
            actions={
              <div className="flex flex-wrap gap-1 text-xs">
                {RANGES.map((r) => (
                  <button key={r.interval} className={`btn ${interval === r.interval ? "btn-primary" : ""}`} onClick={() => setRange(r.interval)} disabled={s.is_demo && r.interval !== "1d"}>
                    {r.label}
                  </button>
                ))}
              </div>
            }
          >
            {history.error && <ErrorBox message={history.error} onRetry={history.reload} />}
            {history.loading && !history.data && <Loading />}
            {history.data && (
              <>
                <PriceChart bars={oneDayBars} intraday={intraday} referencePrice={interval === "1m" ? q?.previous_close : null} showAverages={interval === "1d"} />
                <p className="mt-1 text-[11px] text-muted">{history.data.count} bar · {history.data.label}. {history.data.warnings.join(" ")}</p>
              </>
            )}
          </Card>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="1 hafta" value={formatPct(s.change_1w, 2, true)} delta={s.change_1w} tone="signed" />
            <StatTile label="1 ay" value={formatPct(s.change_1m, 2, true)} delta={s.change_1m} tone="signed" />
            <StatTile label="3 ay" value={formatPct(s.change_3m, 2, true)} delta={s.change_3m} tone="signed" />
            <StatTile label="1 yıl" value={formatPct(s.change_1y, 2, true)} delta={s.change_1y} tone="signed" />
          </div>

          <StockStatsPanel stats={s.stats} />

          <Card title="Günlük zaman serisi" subtitle="Son 60 işlem günü · açılış, yüksek, düşük, kapanış, hacim">
            <DailySeriesTable bars={dailyBars} />
            <p className="mt-1 text-[11px] text-muted">
              Kapanışlar Yahoo Finance günlük serisinden; kurumsal işlem düzeltmesi getiri hesaplarında adj_close ile yapılır.
            </p>
          </Card>
        </div>

        <div className="space-y-3">
          <Card title="Temettüler" subtitle={`Yahoo Finance nakit temettü olayları (3 yıl) · son 12 ay verimi ${formatPct(s.dividend_yield_12m, 2)}`}>
            {s.dividends.length === 0 ? (
              <p className="text-xs text-muted">Bu dönemde temettü gözlenmedi (no_dividend_observed).</p>
            ) : (
              <table className="table-dense w-full text-xs">
                <thead>
                  <tr><th>Tarih</th><th className="text-right">Tutar (₺)</th><th className="text-right">Kapanış</th><th className="text-right">Verim</th></tr>
                </thead>
                <tbody>
                  {s.dividends.slice(0, 12).map((dv) => (
                    <tr key={dv.date}>
                      <td className="num">{formatDate(dv.date)}</td>
                      <td className="num text-right">{formatNumber(dv.amount, 4)}</td>
                      <td className="num text-right">{formatNumber(dv.close, 2)}</td>
                      <td className="num text-right">{dv.close ? formatPct(dv.amount / dv.close, 2) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="fpfs değerlendirmesi" subtitle={s.ranking ? `Dengeli profil · veri ${formatDate(s.ranking.data_as_of)}` : "Henüz kayıtlı sıralama yok"}>
            {s.ranking ? (
              <>
                <div className="mb-2 flex items-baseline gap-3">
                  <span className="num text-2xl font-semibold">#{s.ranking.rank}</span>
                  <span className="num text-sm text-secondary">CCE10 {formatNumber(s.ranking.cce10, 4)}</span>
                  <span className="num text-xs text-muted">FSS #{s.ranking.fss_rank}</span>
                </div>
                <ul className="space-y-1 text-xs">
                  {CRITERIA_ORDER.map((k) => (
                    <li key={k} className="grid grid-cols-[110px_1fr_44px] items-center gap-2">
                      <span className="text-secondary">{CRITERIA_LABELS[k]}</span>
                      <span className="h-1.5 overflow-hidden rounded-sm bg-surface-2"><span className="block h-full bg-series-1" style={{ width: `${s.ranking!.membership[k] * 100}%` }} /></span>
                      <span className="num text-right">{formatNumber(s.ranking!.membership[k], 2)}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-muted">
                  Yıllık getiri {formatPct(s.ranking.criteria.annualized_return, 1, true)} · aşağı risk {formatPct(s.ranking.criteria.risk, 3)} · likidite proxy {formatCompact(s.ranking.criteria.liquidity)} ₺ · {s.ranking.criteria.dividend_status}
                </p>
                <Link href="/rankings" className="mt-2 inline-block text-xs text-accent underline">Sıralamaya git</Link>
              </>
            ) : (
              <Link href="/rankings" className="text-xs text-accent underline">Sıralama çalıştır</Link>
            )}
          </Card>
          <WarningList warnings={history.data?.warnings.filter((w) => !w.includes("15 dk")) ?? []} />
          <p className="text-[11px] text-muted">Fiyatlar TL cinsindendir; araştırma amaçlıdır, yatırım tavsiyesi değildir.</p>
        </div>
      </div>
    </div>
  );
}
