"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge, Card, DemoBanner, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { formatCompact, formatDateTime, formatNumber, formatPct, signClass } from "@/lib/format";
import type { Quote } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

type SortKey = "symbol" | "last_price" | "day_change_pct" | "day_volume" | "sector";

export default function MarketPage() {
  const quotes = usePolling(() => api.quotes(), 60_000, []);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("day_change_pct");
  const [asc, setAsc] = useState(false);
  const d = quotes.data;

  const rows = useMemo(() => {
    const list = (d?.quotes ?? []).filter((q) => {
      const s = query.trim().toLowerCase();
      return !s || q.symbol.toLowerCase().includes(s) || (q.name ?? "").toLowerCase().includes(s);
    });
    const val = (q: Quote): number | string => {
      if (sortKey === "symbol") return q.symbol;
      if (sortKey === "sector") return q.sector ?? "";
      return q[sortKey] ?? Number.NEGATIVE_INFINITY;
    };
    return [...list].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const cmp = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : Number(va) - Number(vb);
      return asc ? cmp : -cmp;
    });
  }, [d, query, sortKey, asc]);

  const toggle = (key: SortKey) => {
    if (sortKey === key) setAsc((v) => !v);
    else {
      setSortKey(key);
      setAsc(key === "symbol" || key === "sector");
    }
  };
  const th = (key: SortKey, label: string, align = "text-left") => (
    <th className={`${align} cursor-pointer select-none`} onClick={() => toggle(key)}>
      {label} {sortKey === key ? (asc ? "↑" : "↓") : ""}
    </th>
  );

  const up = rows.filter((q) => (q.day_change_pct ?? 0) > 0).length;
  const down = rows.filter((q) => (q.day_change_pct ?? 0) < 0).length;

  return (
    <div className="space-y-4">
      <PageHeader title="Piyasa" description="BIST 100 hisselerinin son fiyatları. Yahoo Finance ≈15 dakika gecikmeli; 60 saniyede bir yenilenir. Sembole tıklayınca hisse paneli açılır.">
        {d && (
          <>
            <Badge tone="warning">{d.label}</Badge>
            <span className="text-xs text-muted">Sağlayıcıdan çekildi: {formatDateTime(d.fetched_at)} · {up} ▲ / {down} ▼</span>
            <button className="btn text-xs" onClick={quotes.refresh}>Şimdi yenile</button>
          </>
        )}
      </PageHeader>
      {d && <DemoBanner isDemo={d.is_demo} />}
      {d && !d.available && <ErrorBox message={d.message ?? "Canlı fiyat kullanılamıyor."} />}
      {quotes.error && <ErrorBox message={quotes.error} onRetry={quotes.refresh} />}
      {quotes.loading && !d && <Loading />}
      {d && d.available && (
        <Card actions={<input type="text" placeholder="Sembol / şirket ara" value={query} onChange={(e) => setQuery(e.target.value)} className="w-56" />}>
          <div className="max-h-[75vh] overflow-auto">
            <table className="table-dense w-full text-xs">
              <thead>
                <tr>
                  {th("symbol", "Sembol")}
                  <th>Şirket</th>
                  {th("sector", "Sektör")}
                  {th("last_price", "Son", "text-right")}
                  <th className="text-right">Değişim</th>
                  {th("day_change_pct", "%", "text-right")}
                  <th className="text-right">Önceki kap.</th>
                  <th className="text-right">Açılış</th>
                  <th className="text-right">Yüksek</th>
                  <th className="text-right">Düşük</th>
                  {th("day_volume", "Hacim (lot)", "text-right")}
                  <th>Zaman</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => (
                  <tr key={q.symbol}>
                    <td className="num font-semibold">
                      <Link href={`/stocks/${q.symbol}`} className="text-accent hover:underline">{q.symbol.replace(".IS", "")}</Link>
                    </td>
                    <td className="max-w-[240px] truncate text-secondary" title={q.name ?? ""}>{q.name}</td>
                    <td className="max-w-[160px] truncate text-muted" title={q.sector ?? ""}>{q.sector ?? "—"}</td>
                    <td className="num text-right">{q.last_price != null ? formatNumber(q.last_price, 2) : <span className="text-warning" title={q.message}>—</span>}</td>
                    <td className={`num text-right ${signClass(q.day_change)}`}>{q.day_change != null ? formatNumber(q.day_change, 2) : "—"}</td>
                    <td className={`num text-right ${signClass(q.day_change_pct)}`}>{formatPct(q.day_change_pct, 2, true)}</td>
                    <td className="num text-right text-secondary">{formatNumber(q.previous_close, 2)}</td>
                    <td className="num text-right text-secondary">{formatNumber(q.day_open, 2)}</td>
                    <td className="num text-right text-secondary">{formatNumber(q.day_high, 2)}</td>
                    <td className="num text-right text-secondary">{formatNumber(q.day_low, 2)}</td>
                    <td className="num text-right text-secondary">{formatCompact(q.day_volume)}</td>
                    <td className="num text-muted">{q.last_time ? `${q.last_time.slice(8, 10)}.${q.last_time.slice(5, 7)} ${q.last_time.slice(11, 16)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
