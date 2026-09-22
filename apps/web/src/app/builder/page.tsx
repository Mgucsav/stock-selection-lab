"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AllocationBars } from "@/components/charts";
import { Badge, Card, DemoBanner, ErrorBox, KeyValue, PageHeader, WarningList } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { CRITERIA_LABELS, formatDate, formatNumber, formatPct, formatTL } from "@/lib/format";
import { CRITERIA_ORDER, type Candidate } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SCHEME_LABELS: Record<string, string> = {
  inverse_downside_risk: "Ters aşağı yönlü risk",
  half_score_half_inverse_risk: "%50 fpfs skor payı + %50 ters risk payı",
  score_proportional: "fpfs skoruyla orantılı",
};

export default function BuilderPage() {
  const router = useRouter();
  const status = useApi(() => api.dataStatus(), []);
  const [capital, setCapital] = useState(1_000_000);
  const [decisionInput, setDecisionInput] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);

  const latest = status.data?.date_range?.end ?? "";
  // Kullanıcı bir tarih seçmediyse son veri günü kullanılır (türetilmiş durum, effect yok).
  const decisionDate = decisionInput ?? latest;
  const setDecisionDate = (value: string) => setDecisionInput(value || null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await api.generatePortfolios({ capital, decision_date: decisionDate || undefined });
      setCandidates(response.candidates);
      setIsDemo(response.is_demo);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const select = async (candidate: Candidate) => {
    setSelecting(candidate.candidate_id);
    setError(null);
    try {
      const detail = await api.selectPortfolio(candidate.candidate_id, { initial_capital: capital });
      try {
        window.localStorage.setItem("ssl.selectedPortfolioId", detail.portfolio_id);
      } catch {
        /* yok say */
      }
      router.push(`/portfolios/${detail.portfolio_id}`);
    } catch (e) {
      setError(describeError(e));
      setSelecting(null);
    }
  };

  const isLatest = decisionDate === latest;
  const shiftDate = (days: number) => {
    if (!latest) return;
    const d = new Date(`${latest}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - days);
    setDecisionDate(d.toISOString().slice(0, 10));
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Portföy Oluşturucu" description="fpfs sıralaması hisseleri seçer; ağırlıklandırma ayrı, şeffaf bir uygulama katmanıdır. Üç model portföy, üç profilin sıralamasından üretilir.">
        {status.data && <Badge tone={status.data.is_demo ? "warning" : "good"}>{status.data.is_demo ? "Demo veri" : status.data.data_source}</Badge>}
      </PageHeader>
      {status.data && <DemoBanner isDemo={status.data.is_demo} />}
      {status.error && <ErrorBox message={status.error} onRetry={status.reload} />}

      <Card title="Parametreler">
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label className="block">
            <div className="mb-1 text-xs text-muted">Başlangıç sermayesi (TL)</div>
            <input type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(Number(e.target.value))} className="num w-44" />
          </label>
          <label className="block">
            <div className="mb-1 text-xs text-muted">Karar tarihi (yalnızca bu tarihe kadar olan veri kullanılır)</div>
            <input type="date" value={decisionDate} max={latest || undefined} onChange={(e) => setDecisionDate(e.target.value)} className="num" />
          </label>
          <div className="flex gap-1 text-xs">
            <button className="btn" onClick={() => setDecisionDate(latest)}>Son veri</button>
            <button className="btn" onClick={() => shiftDate(90)}>90 gün önce</button>
            <button className="btn" onClick={() => shiftDate(180)}>180 gün önce</button>
          </div>
          <button className="btn btn-primary" onClick={generate} disabled={busy || !decisionDate || capital <= 0}>
            {busy ? "Hesaplanıyor…" : "Model portföyleri üret"}
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">
          {isLatest
            ? "Karar tarihi son veri günü: giriş fiyatı bir sonraki işlem gününde oluşacağı için seçilen portföy 'beklemede' kalır."
            : "Tarihsel simülasyon: giriş fiyatı karar tarihinden sonraki ilk işlem gününün açılışından alınır; sıralama yalnızca karar tarihine kadar olan veriyle hesaplanır (look-ahead yok)."}
        </p>
      </Card>

      {error && <ErrorBox message={error} />}

      {candidates && (
        <div className="grid gap-3 xl:grid-cols-3">
          {candidates.map((c) => (
            <Card
              key={c.candidate_id}
              title={`${c.profile_label} portföy`}
              subtitle={`${c.size} hisse · ${SCHEME_LABELS[c.weighting_scheme] ?? c.weighting_scheme} · tek hisse ≤ ${formatPct(c.max_weight, 0)}`}
              actions={<Badge tone={isDemo ? "warning" : "good"}>{c.data_source}</Badge>}
            >
              <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded bg-surface-2 p-2">
                  <div className="text-muted">Ortalama fpfs skoru</div>
                  <div className="num text-base">{formatNumber(c.average_score, 4)}</div>
                </div>
                <div className="rounded bg-surface-2 p-2">
                  <div className="text-muted">Tarihsel volatilite (yıllık)</div>
                  <div className="num text-base">{formatPct(c.stats.volatility, 1)}</div>
                </div>
                <div className="rounded bg-surface-2 p-2">
                  <div className="text-muted">Tarihsel maks. düşüş</div>
                  <div className="num text-base neg">{formatPct(c.stats.max_drawdown, 1)}</div>
                </div>
                <div className="rounded bg-surface-2 p-2">
                  <div className="text-muted">Backtest dönemi</div>
                  <div className="num">{formatDate(c.stats.backtest_start)} – {formatDate(c.stats.backtest_end)}</div>
                </div>
              </div>
              <AllocationBars items={c.holdings.map((h) => ({ label: h.symbol.replace(".IS", ""), value: h.weight, hint: h.name }))} max={c.max_weight} />
              <details className="mt-3 text-xs">
                <summary className="cursor-pointer text-secondary">Hisseler, lot tahmini ve sektör dağılımı</summary>
                <table className="table-dense mt-2 w-full">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Sembol</th>
                      <th className="text-right">Ağırlık</th>
                      <th className="text-right">fpfs</th>
                      <th className="text-right">Aşağı risk</th>
                      <th className="text-right">Hedef tutar*</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.holdings.map((h) => (
                      <tr key={h.symbol}>
                        <td className="num">{h.rank}</td>
                        <td className="num" title={h.name}>{h.symbol.replace(".IS", "")}</td>
                        <td className="num text-right">{formatPct(h.weight, 2)}</td>
                        <td className="num text-right">{formatNumber(h.cce10, 4)}</td>
                        <td className="num text-right">{formatPct(h.downside_risk, 3)}</td>
                        <td className="num text-right">{formatTL(capital * h.weight)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-1 text-muted">* Hedef tutar = sermaye × ağırlık. Lotlar seçim anında bir sonraki işlem gününün fiyatıyla hesaplanır: floor(sermaye × ağırlık / giriş fiyatı).</p>
                {c.sector_exposure && (
                  <div className="mt-2">
                    <div className="mb-1 text-muted">Sektör yoğunlaşması</div>
                    <AllocationBars items={Object.entries(c.sector_exposure).map(([k, v]) => ({ label: k, value: v }))} />
                  </div>
                )}
              </details>
              <div className="mt-3">
                <KeyValue
                  items={[
                    ["Karar / veri tarihi", `${formatDate(c.decision_date)} / ${formatDate(c.data_as_of)}`],
                    ["Model sürümü", c.model_version],
                    ["Profil ağırlıkları", CRITERIA_ORDER.map((k) => `${CRITERIA_LABELS[k].split(" ")[0]} ${c.profile_weights[k].toFixed(2)}`).join(" · ")],
                    ["Sermaye", formatTL(c.capital)],
                  ]}
                />
              </div>
              <WarningList warnings={c.warnings} />
              <button className="btn btn-primary mt-3 w-full" onClick={() => select(c)} disabled={selecting !== null}>
                {selecting === c.candidate_id ? "Kaydediliyor…" : "Bu portföyü seç ve başlat"}
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
