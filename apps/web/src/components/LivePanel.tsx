"use client";

import Link from "next/link";

import { api } from "@/lib/api";
import { formatDate, formatNumber, formatPct, formatTL, signClass } from "@/lib/format";
import { usePolling } from "@/lib/usePolling";

import { Badge, Card, StatTile, WarningList } from "./ui";

const REFRESH_MS = 60_000;

/** Gecikmeli (≈15 dk) fiyatlarla portföyün anlık değeri; 60 sn'de bir yenilenir. */
export function LivePanel({ portfolioId, compact = false }: { portfolioId: string; compact?: boolean }) {
  const live = usePolling(() => api.live(portfolioId), REFRESH_MS, [portfolioId]);
  const d = live.data;

  return (
    <Card
      title="Gün içi takip"
      subtitle={d ? `${d.label} · son fiyat zamanı ${d.as_of ? `${formatDate(d.as_of)} ${d.as_of.slice(11, 16)}` : "—"} (borsa saati)` : "Yükleniyor…"}
      actions={
        <div className="flex items-center gap-2 text-xs text-muted">
          <Badge tone="warning">≈15 dk gecikmeli</Badge>
          {live.updatedAt && <span>Yenilendi {live.updatedAt.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>}
          <button className="btn text-xs" onClick={live.refresh}>Şimdi yenile</button>
        </div>
      }
    >
      {live.error && <p className="text-xs text-critical">✖ {live.error}</p>}
      {d && !d.available && <p className="text-sm text-secondary">{d.message}</p>}
      {d && d.available && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Anlık değer" value={formatTL(d.current_value)} hint={`Nakit ${formatTL(d.cash)}`} />
            <StatTile label="Bugünkü değişim" value={formatTL(d.day_change)} hint={formatPct(d.day_change_pct, 2, true)} delta={d.day_change} tone="signed" />
            <StatTile label="Girişten bu yana K/Z" value={formatTL(d.total_pnl)} hint={formatPct(d.total_return, 2, true)} delta={d.total_pnl} tone="signed" />
            <StatTile label="Başlangıç sermayesi" value={formatTL(d.initial_capital)} hint={d.from_cache ? "Cache'ten (≤60 sn)" : "Sağlayıcıdan yeni çekildi"} />
          </div>
          {!compact && (
            <div className="mt-3 overflow-auto">
              <table className="table-dense w-full text-xs">
                <thead>
                  <tr>
                    <th>Sembol</th>
                    <th className="text-right">Lot</th>
                    <th className="text-right">Giriş</th>
                    <th className="text-right">Son fiyat</th>
                    <th>Zaman</th>
                    <th className="text-right">Bugün</th>
                    <th className="text-right">Değer</th>
                    <th className="text-right">K/Z</th>
                    <th className="text-right">Getiri</th>
                    <th className="text-right">Ağırlık</th>
                  </tr>
                </thead>
                <tbody>
                  {d.positions.map((p) => (
                    <tr key={p.symbol}>
                      <td className="num font-semibold">
                        <Link href={`/stocks/${p.symbol}`} className="hover:underline">{p.symbol.replace(".IS", "")}</Link>
                        {p.fallback && <span className="ml-1 text-warning" title="Canlı fiyat alınamadı; son kapanış">†</span>}
                      </td>
                      <td className="num text-right">{p.quantity}</td>
                      <td className="num text-right">{formatNumber(p.entry_price, 2)}</td>
                      <td className="num text-right">{formatNumber(p.last_price, 2)}</td>
                      <td className="num text-muted">{p.last_time ? p.last_time.slice(11, 16) : "—"}</td>
                      <td className={`num text-right ${signClass(p.day_change_pct)}`}>{formatPct(p.day_change_pct, 2, true)}</td>
                      <td className="num text-right">{formatTL(p.market_value)}</td>
                      <td className={`num text-right ${signClass(p.pnl)}`}>{formatTL(p.pnl)}</td>
                      <td className={`num text-right ${signClass(p.return_pct)}`}>{formatPct(p.return_pct, 2, true)}</td>
                      <td className="num text-right">{formatPct(p.weight, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-2">
            <WarningList warnings={d.warnings} />
          </div>
          <p className="mt-2 text-[11px] text-muted">
            Anlık değer sağlayıcının verdiği son fiyatla (≈15 dk gecikmeli, tick akışı değil) hesaplanır; resmî günlük değerleme gün sonu kapanışıyla ayrıca yapılır.
          </p>
        </>
      )}
    </Card>
  );
}
