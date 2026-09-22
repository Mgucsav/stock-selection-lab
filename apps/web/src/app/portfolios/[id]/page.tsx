"use client";

import { use, useState } from "react";

import Link from "next/link";

import { PortfolioChart } from "@/components/charts";
import { LivePanel } from "@/components/LivePanel";
import { Badge, Card, DemoBanner, ErrorBox, KeyValue, Loading, PageHeader, StatTile, WarningList } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { CRITERIA_LABELS, PROFILE_LABELS, formatDate, formatDateTime, formatNumber, formatPct, formatTL, signClass } from "@/lib/format";
import { CRITERIA_ORDER } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function PortfolioDetailPage({ params }: PageProps<"/portfolios/[id]">) {
  const { id } = use(params);
  return <Detail id={id} />;
}

function Detail({ id }: { id: string }) {
  const detail = useApi(() => api.portfolio(id), [id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"value" | "normalized">("value");

  const revalue = async () => {
    setBusy(true);
    setError(null);
    try {
      detail.setData(await api.revalue(id));
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  if (detail.loading && !detail.data) return <Loading />;
  if (detail.error && !detail.data) return <ErrorBox message={detail.error} onRetry={detail.reload} />;
  const d = detail.data;
  if (!d) return null;
  const m = d.valuation;
  const positions = d.snapshot.positions ?? [];
  const contributionMap = Object.fromEntries(d.contributions.map((c) => [c.symbol, c]));

  return (
    <div className="space-y-4">
      <PageHeader title={d.name} description={`${PROFILE_LABELS[d.profile_id] ?? d.profile_id} profili · karar tarihi ${formatDate(d.decision_date)} · ${d.model_version}`}>
        <Badge tone={d.status === "active" ? "good" : "warning"}>{d.status === "active" ? "aktif" : "beklemede"}</Badge>
        <Badge tone={d.is_demo ? "warning" : "neutral"}>{d.data_source}</Badge>
        <button className="btn" onClick={revalue} disabled={busy}>{busy ? "Değerleniyor…" : "Yeniden değerle"}</button>
      </PageHeader>
      <DemoBanner isDemo={d.is_demo} />
      {error && <ErrorBox message={error} />}

      {d.status !== "active" && (
        <Card title="Portföy beklemede">
          <p className="text-sm text-secondary">
            Karar tarihinden ({formatDate(d.decision_date)}) sonraki işlem günü henüz veri setinde yok. Giriş fiyatları o günün açılışından alınacak; lotlar ve nakit o anda kilitlenecek.
            Bekleyen semboller: <span className="num">{d.snapshot.entry_pending.map((s) => s.replace(".IS", "")).join(", ")}</span>
          </p>
          {d.snapshot.source_mismatch && <p className="mt-2 text-sm text-warning">⚠ {d.snapshot.source_mismatch}</p>}
        </Card>
      )}

      {d.status === "active" && <LivePanel portfolioId={d.portfolio_id} />}

      {m && d.status === "active" && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Güncel değer" value={formatTL(m.current_value)} hint={`Başlangıç ${formatTL(d.initial_capital)} · ${formatDate(m.as_of)}`} />
            <StatTile label="Toplam K/Z" value={formatTL(m.total_pnl)} hint={formatPct(m.total_return, 2, true)} delta={m.total_pnl} tone="signed" />
            <StatTile label="Günlük değişim" value={formatTL(m.daily_change)} hint={formatPct(m.daily_return, 2, true)} delta={m.daily_change} tone="signed" />
            <StatTile label="BIST 100 göreceli" value={formatPct(m.relative_return, 2, true)} hint={m.benchmark_return != null ? `BIST 100 ${formatPct(m.benchmark_return, 2, true)}` : "Benchmark yok"} delta={m.relative_return} tone="signed" />
            <StatTile label="Volatilite (yıllık)" value={formatPct(m.volatility, 1)} hint="Gerçekleşen günlük getirilerden" />
            <StatTile label="Maksimum düşüş" value={formatPct(m.max_drawdown, 2)} hint="Portföy değeri zirvesinden" />
            <StatTile label="Nakit" value={formatTL(m.cash)} hint={`Nakit oranı ${formatPct(m.cash_ratio, 2)}`} />
            <StatTile label="Gözlem" value={m.observations ?? "—"} hint={`${formatDate(m.start_date)} – ${formatDate(m.as_of)}`} />
          </div>

          <Card
            title={mode === "value" ? "Gün sonu değerleme · Portföy değeri (TL)" : "Gün sonu değerleme · Başlangıç = 100 · BIST 100"}
            actions={
              <div className="flex gap-1 text-xs">
                <button className={`btn ${mode === "value" ? "btn-primary" : ""}`} onClick={() => setMode("value")}>TL değer</button>
                <button className={`btn ${mode === "normalized" ? "btn-primary" : ""}`} onClick={() => setMode("normalized")}>Normalize (100)</button>
              </div>
            }
          >
            <PortfolioChart series={d.series} mode={mode} benchmarkAvailable={d.benchmark_available} height={320} />
          </Card>
        </>
      )}

      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <Card title="Pozisyonlar" subtitle="Giriş fiyatı, lot, güncel değer, kazanç/kayıp ve katkı">
          <div className="overflow-auto">
            <table className="table-dense w-full text-xs">
              <thead>
                <tr>
                  <th>Sembol</th>
                  <th className="text-right">Hedef ağ.</th>
                  <th>Giriş tarihi</th>
                  <th className="text-right">Giriş fiyatı</th>
                  <th className="text-right">Lot</th>
                  <th className="text-right">Maliyet</th>
                  <th className="text-right">Son fiyat</th>
                  <th className="text-right">Değer</th>
                  <th className="text-right">K/Z</th>
                  <th className="text-right">Getiri</th>
                  <th className="text-right">Katkı</th>
                  <th className="text-right">Güncel ağ.</th>
                </tr>
              </thead>
              <tbody>
                {(positions.length > 0 ? positions : Object.entries(d.snapshot.target_weights).map(([symbol, w]) => ({ symbol, target_weight: w, entry_date: null, entry_price: null, price_field: null, quantity: 0, cost: 0 }))).map((p) => {
                  const c = contributionMap[p.symbol];
                  return (
                    <tr key={p.symbol}>
                      <td className="num font-semibold"><Link href={`/stocks/${p.symbol}`} className="hover:underline">{p.symbol.replace(".IS", "")}</Link></td>
                      <td className="num text-right">{formatPct(p.target_weight, 2)}</td>
                      <td className="num">{formatDate(p.entry_date)}{p.price_field ? <span className="text-muted"> ({p.price_field})</span> : ""}</td>
                      <td className="num text-right">{formatNumber(p.entry_price, 2)}</td>
                      <td className="num text-right">{p.quantity}</td>
                      <td className="num text-right">{formatTL(p.cost, true)}</td>
                      <td className="num text-right">{formatNumber(c?.last_price, 2)}</td>
                      <td className="num text-right">{formatTL(c?.market_value)}</td>
                      <td className={`num text-right ${signClass(c?.pnl)}`}>{formatTL(c?.pnl)}</td>
                      <td className={`num text-right ${signClass(c?.return_pct)}`}>{formatPct(c?.return_pct, 2, true)}</td>
                      <td className={`num text-right ${signClass(c?.contribution_pct)}`}>{formatPct(c?.contribution_pct, 2, true)}</td>
                      <td className="num text-right">{formatPct(c?.current_weight, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Model anlık görüntüsü" subtitle="Değiştirilemez; seçim anında kaydedildi">
          <KeyValue
            items={[
              ["Portföy ID", d.portfolio_id.slice(0, 8)],
              ["Skor çalışması", d.score_run_id.slice(0, 8)],
              ["Aday ID", d.candidate_id.slice(0, 8)],
              ["Karar tarihi", formatDate(d.decision_date)],
              ["Veri tarihi", formatDate(d.data_as_of)],
              ["Giriş tarihi", formatDate(d.snapshot.entry_date)],
              ["Profil", PROFILE_LABELS[d.profile_id] ?? d.profile_id],
              ["Model sürümü", d.model_version],
              ["Veri kaynağı", d.data_source],
              ["Başlangıç sermayesi", formatTL(d.initial_capital)],
              ["Yatırılan", formatTL(d.snapshot.invested ?? null)],
              ["Kalan nakit", formatTL(d.snapshot.cash, true)],
              ["Oluşturma", formatDateTime(d.created_at)],
              ["Aktivasyon", formatDateTime(d.activated_at)],
            ]}
          />
          <div className="mt-3 text-xs">
            <div className="mb-1 text-muted">Profil ağırlıkları (μ)</div>
            <ul className="space-y-0.5">
              {CRITERIA_ORDER.map((k) => (
                <li key={k} className="flex justify-between"><span className="text-secondary">{CRITERIA_LABELS[k]}</span><span className="num">{d.profile_weights[k].toFixed(2)}</span></li>
              ))}
            </ul>
          </div>
          <div className="mt-3">
            <WarningList warnings={[...d.warnings, ...(d.snapshot.run_warnings ?? [])]} />
          </div>
        </Card>
      </div>
    </div>
  );
}
