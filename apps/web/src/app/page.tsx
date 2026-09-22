"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { PortfolioChart } from "@/components/charts";
import { LivePanel } from "@/components/LivePanel";
import { Badge, Card, DemoBanner, ErrorBox, Loading, PageHeader, StatTile, WarningList } from "@/components/ui";
import { api } from "@/lib/api";
import { PROFILE_LABELS, formatDate, formatDateTime, formatPct, formatTL, signClass } from "@/lib/format";
import type { PortfolioDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STORAGE_KEY = "ssl.selectedPortfolioId";

export default function DashboardPage() {
  const status = useApi(() => api.dataStatus(), []);
  const list = useApi(() => api.portfolios(), []);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mode, setMode] = useState<"value" | "normalized">("normalized");

  const portfolios = useMemo(() => list.data?.portfolios ?? [], [list.data]);

  // Seçim: kullanıcının seçtiği, yoksa localStorage'daki, yoksa ilk aktif portföy (türetilmiş durum).
  const selectedId = useMemo(() => {
    if (portfolios.length === 0) return null;
    if (chosenId && portfolios.some((p) => p.portfolio_id === chosenId)) return chosenId;
    let stored: string | null = null;
    try {
      stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    } catch {
      stored = null;
    }
    const preferred = portfolios.find((p) => p.portfolio_id === stored) ?? portfolios.find((p) => p.status === "active") ?? portfolios[0];
    return preferred.portfolio_id;
  }, [portfolios, chosenId]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    api
      .revalue(selectedId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setDetailError(null);
      })
      .catch((e: unknown) => !cancelled && setDetailError(e instanceof Error ? e.message : "Değerleme alınamadı."));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const metrics = detail?.valuation ?? null;
  const contributions = useMemo(() => [...(detail?.contributions ?? [])].sort((a, b) => b.pnl - a.pnl), [detail]);

  if (status.error && !status.data) return <ErrorBox message={status.error} onRetry={status.reload} />;

  return (
    <div className="space-y-4">
      <PageHeader title="Panel" description="Seçili model portföyün güncel değeri, günlük/toplam değişimi ve BIST 100 karşılaştırması.">
        {status.data && (
          <span className="text-xs text-muted">
            Son veri: <span className="num text-secondary">{formatDate(status.data.date_range?.end)}</span>
            {status.data.last_success_at && <> · Güncelleme: <span className="num text-secondary">{formatDateTime(status.data.last_success_at)}</span></>}
            {" · "}
            <Badge>{status.data.data_label}</Badge>
          </span>
        )}
      </PageHeader>
      {status.data && <DemoBanner isDemo={status.data.is_demo} dataLabel={status.data.data_label} />}

      {list.loading && <Loading />}
      {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}

      {!list.loading && portfolios.length === 0 && (
        <Card title="Henüz model portföy yok">
          <p className="text-sm text-secondary">
            Portföy Oluşturucu ile üç model portföyden birini seçip başlatın; panel seçilen portföyü takip eder.
          </p>
          <Link href="/builder" className="btn btn-primary mt-3 inline-block">
            Portföy Oluşturucu’ya git
          </Link>
        </Card>
      )}

      {portfolios.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="text-muted">Takip edilen portföy:</label>
          <select
            value={selectedId ?? ""}
            onChange={(e) => {
              setChosenId(e.target.value);
              try {
                window.localStorage.setItem(STORAGE_KEY, e.target.value);
              } catch {
                /* yok say */
              }
            }}
          >
            {portfolios.map((p) => (
              <option key={p.portfolio_id} value={p.portfolio_id}>
                {p.name} · {PROFILE_LABELS[p.profile_id] ?? p.profile_id} · {p.status === "active" ? "aktif" : "beklemede"}
              </option>
            ))}
          </select>
          {detail && (
            <Link href={`/portfolios/${detail.portfolio_id}`} className="text-accent underline">
              Detaya git →
            </Link>
          )}
        </div>
      )}

      {detailError && <ErrorBox message={detailError} />}

      {detail && detail.status !== "active" && (
        <Card title="Portföy beklemede">
          <p className="text-sm text-secondary">
            Karar tarihi <span className="num">{formatDate(detail.decision_date)}</span>; giriş fiyatı bir sonraki işlem gününden alınacağı için
            portföy henüz aktif değil. Yeni veri geldiğinde “Yeniden değerle” ile başlatılır.
          </p>
          {detail.snapshot.source_mismatch && <p className="mb-2 text-sm text-warning">⚠ {detail.snapshot.source_mismatch}</p>}
          <WarningList warnings={detail.warnings} />
        </Card>
      )}

      {detail && metrics && detail.status === "active" && (
        <>
          <LivePanel portfolioId={detail.portfolio_id} compact />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Toplam portföy değeri" value={formatTL(metrics.current_value)} hint={`Başlangıç ${formatTL(metrics.initial_capital)}`} />
            <StatTile
              label="Günlük değişim"
              value={formatTL(metrics.daily_change)}
              hint={<span className={signClass(metrics.daily_return)}>{formatPct(metrics.daily_return, 2, true)}</span>}
              delta={metrics.daily_change}
              tone="signed"
            />
            <StatTile
              label="Toplam kazanç/kayıp"
              value={formatTL(metrics.total_pnl)}
              hint={<span className={signClass(metrics.total_return)}>{formatPct(metrics.total_return, 2, true)}</span>}
              delta={metrics.total_pnl}
              tone="signed"
            />
            <StatTile
              label="BIST 100 göreceli getiri"
              value={formatPct(metrics.relative_return, 2, true)}
              hint={metrics.benchmark_return != null ? `BIST 100: ${formatPct(metrics.benchmark_return, 2, true)}` : "Benchmark verisi yok"}
              delta={metrics.relative_return}
              tone="signed"
            />
          </div>

          <Card
            title="Portföy / BIST 100"
            subtitle={`${formatDate(metrics.start_date)} – ${formatDate(metrics.as_of)} · başlangıç = 100`}
            actions={
              <div className="flex gap-1 text-xs">
                <button className={`btn ${mode === "normalized" ? "btn-primary" : ""}`} onClick={() => setMode("normalized")}>Normalize (100)</button>
                <button className={`btn ${mode === "value" ? "btn-primary" : ""}`} onClick={() => setMode("value")}>TL değer</button>
              </div>
            }
          >
            <PortfolioChart series={detail.series} mode={mode} benchmarkAvailable={detail.benchmark_available} />
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            <Card title="En iyi katkı" subtitle="Giriş fiyatına göre TL kazanç">
              <ContributionTable rows={contributions.slice(0, 5)} />
            </Card>
            <Card title="En kötü katkı" subtitle="Giriş fiyatına göre TL kayıp">
              <ContributionTable rows={[...contributions].reverse().slice(0, 5)} />
            </Card>
          </div>
          <WarningList warnings={detail.warnings} />
        </>
      )}
    </div>
  );
}

function ContributionTable({ rows }: { rows: PortfolioDetail["contributions"] }) {
  if (rows.length === 0) return <p className="text-xs text-muted">Katkı verisi yok.</p>;
  return (
    <table className="table-dense w-full text-xs">
      <thead>
        <tr>
          <th>Sembol</th>
          <th className="text-right">K/Z (TL)</th>
          <th className="text-right">Getiri</th>
          <th className="text-right">Katkı</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.symbol}>
            <td className="num"><Link href={`/stocks/${r.symbol}`} className="hover:underline">{r.symbol.replace(".IS", "")}</Link></td>
            <td className={`num text-right ${signClass(r.pnl)}`}>{formatTL(r.pnl)}</td>
            <td className={`num text-right ${signClass(r.return_pct)}`}>{formatPct(r.return_pct, 2, true)}</td>
            <td className={`num text-right ${signClass(r.contribution_pct)}`}>{formatPct(r.contribution_pct, 2, true)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
