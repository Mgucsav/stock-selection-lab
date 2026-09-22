"use client";

import { formatCompact, formatDate, formatNumber, formatPct, signClass } from "@/lib/format";
import type { HistoryBar, StockStats } from "@/lib/types";

import { Card } from "./ui";

function Row({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: string; tone?: number | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-1.5 last:border-b-0">
      <span className="text-xs text-secondary" title={hint}>{label}</span>
      <span className={`num text-sm ${tone !== undefined ? signClass(tone) : ""}`}>{value}</span>
    </div>
  );
}

/** Temel istatistikler: volatilite, risk, hareketli ortalamalar, hacim, beta. */
export function StockStatsPanel({ stats }: { stats: StockStats }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card title="Oynaklık ve risk" subtitle="Yıllıklandırılmış, gözlenen geçmişten">
        <Row label="Volatilite (30 gün)" value={formatPct(stats.volatility_30d, 1)} hint="Son 30 günlük getirilerin standart sapması × √252" />
        <Row label="Volatilite (90 gün)" value={formatPct(stats.volatility_90d, 1)} />
        <Row label="Volatilite (1 yıl)" value={formatPct(stats.volatility_1y, 1)} />
        <Row label="Aşağı yönlü risk" value={formatPct(stats.downside_risk, 3)} hint="Yarı-mutlak sapma: mean(max(0, ortalama − getiri)); modeldeki risk kriteri" />
        <Row label="Maks. düşüş (1 yıl)" value={formatPct(stats.max_drawdown_1y, 1)} tone={stats.max_drawdown_1y} />
        <Row label="Maks. düşüş (tüm dönem)" value={formatPct(stats.max_drawdown_all, 1)} tone={stats.max_drawdown_all} />
        <Row label="Beta (BIST 100, 1 yıl)" value={formatNumber(stats.beta_1y, 2)} hint="cov(hisse, XU100) / var(XU100)" />
        <Row label="Korelasyon (BIST 100)" value={formatNumber(stats.correlation_1y, 2)} />
      </Card>

      <Card title="Fiyat ve ortalamalar" subtitle="Kapanışlara göre">
        <Row label="Son kapanış" value={formatNumber(stats.last_close, 2)} />
        <Row label="SMA 20" value={formatNumber(stats.sma20, 2)} hint="Son 20 kapanışın ortalaması" />
        <Row label="SMA 50" value={formatNumber(stats.sma50, 2)} />
        <Row label="SMA 200" value={formatNumber(stats.sma200, 2)} />
        <Row label="SMA 50'ye uzaklık" value={formatPct(stats.price_vs_sma50, 2, true)} tone={stats.price_vs_sma50} />
        <Row label="SMA 200'e uzaklık" value={formatPct(stats.price_vs_sma200, 2, true)} tone={stats.price_vs_sma200} />
        <Row label="52 hafta yüksek" value={formatNumber(stats.high_52w, 2)} />
        <Row label="52 hafta düşük" value={formatNumber(stats.low_52w, 2)} />
        <Row label="Zirveden uzaklık" value={formatPct(stats.from_high_52w, 2, true)} tone={stats.from_high_52w} />
        <Row label="Dipten uzaklık" value={formatPct(stats.from_low_52w, 2, true)} tone={stats.from_low_52w} />
      </Card>

      <Card title="Getiri ve hacim" subtitle="Son 1 yıl / son 30 gün">
        <Row label="Ortalama günlük getiri" value={formatPct(stats.mean_daily_return, 3, true)} tone={stats.mean_daily_return} />
        <Row label="Yıllık karşılığı*" value={formatPct(stats.annualized_mean_return, 1, true)} tone={stats.annualized_mean_return} hint="Ortalama günlük getiri × 252; tahmin değildir" />
        <Row label="Pozitif gün oranı" value={formatPct(stats.positive_day_ratio, 1)} />
        <Row label="En iyi gün" value={<span>{formatPct(stats.best_day, 2, true)} <span className="text-muted">{formatDate(stats.best_day_date)}</span></span>} tone={stats.best_day} />
        <Row label="En kötü gün" value={<span>{formatPct(stats.worst_day, 2, true)} <span className="text-muted">{formatDate(stats.worst_day_date)}</span></span>} tone={stats.worst_day} />
        <Row label="Ort. hacim (30 gün)" value={`${formatCompact(stats.avg_volume_30d)} lot`} />
        <Row label="Ort. TL hacim (30 gün)" value={`${formatCompact(stats.avg_tl_volume_30d)} ₺`} hint="Modeldeki likidite proxy'sinin temeli" />
        <Row label="Gözlem" value={`${stats.observations} gün`} hint={`${formatDate(stats.first_date)} – ${formatDate(stats.last_date)}`} />
      </Card>
    </div>
  );
}

/** Günlük zaman serisi tablosu: OHLCV + günlük değişim (en yeni üstte). */
export function DailySeriesTable({ bars, limit = 60 }: { bars: HistoryBar[]; limit?: number }) {
  const rows = bars
    .filter((b) => b.c !== null)
    .map((bar, index, list) => {
      const previous = index > 0 ? list[index - 1].c : null;
      return { ...bar, change: previous && bar.c ? bar.c / previous - 1 : null };
    })
    .slice(-limit)
    .reverse();

  if (rows.length === 0) return <p className="text-xs text-muted">Günlük veri yok.</p>;
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="table-dense w-full text-xs">
        <thead>
          <tr>
            <th>Tarih</th>
            <th className="text-right">Açılış</th>
            <th className="text-right">Yüksek</th>
            <th className="text-right">Düşük</th>
            <th className="text-right">Kapanış</th>
            <th className="text-right">Değişim</th>
            <th className="text-right">Hacim (lot)</th>
            <th className="text-right">TL hacim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.t}>
              <td className="num">{formatDate(r.t)}</td>
              <td className="num text-right text-secondary">{formatNumber(r.o, 2)}</td>
              <td className="num text-right text-secondary">{formatNumber(r.h, 2)}</td>
              <td className="num text-right text-secondary">{formatNumber(r.l, 2)}</td>
              <td className="num text-right">{formatNumber(r.c, 2)}</td>
              <td className={`num text-right ${signClass(r.change)}`}>{formatPct(r.change, 2, true)}</td>
              <td className="num text-right text-secondary">{formatCompact(r.v)}</td>
              <td className="num text-right text-secondary">{formatCompact(r.c && r.v ? r.c * r.v : null)} ₺</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
