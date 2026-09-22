"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge, Card, DemoBanner, ErrorBox, Loading, PageHeader, WarningList } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { CRITERIA_LABELS, clampWeights, formatCompact, formatDate, formatNumber, formatPct, rankDeltaLabel, weightsEqual } from "@/lib/format";
import { CRITERIA_ORDER, type CriterionKey, type Profile, type RankingRun, type Weights } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type SortKey = "rank" | "cce10" | "fss_rank" | "rank_delta_vs_fss" | "symbol" | CriterionKey;

export default function RankingsPage() {
  const profiles = useApi(() => api.profiles(), []);
  const [profileId, setProfileId] = useState("balanced");
  const [weights, setWeights] = useState<Weights>({ return: 0.8, dividend: 0.6, liquidity: 0.6, risk: 0.8 });
  const [run, setRun] = useState<RankingRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortAsc, setSortAsc] = useState(true);
  const [tab, setTab] = useState<"main" | "compare">("main");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const profileMap = useMemo(() => Object.fromEntries((profiles.data ?? []).map((p) => [p.id, p])) as Record<string, Profile>, [profiles.data]);
  const activeProfile = profileMap[profileId];
  const isCustom = activeProfile ? !weightsEqual(activeProfile.weights, weights) : false;

  // Profil değişimi: güncel veriyle taze önizleme (persist=false); kayıt için buton kullanılır.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .rankingsRun({ profile_id: profileId, persist: false })
      .then((r) => {
        if (cancelled) return;
        setRun(r);
        setWeights(clampWeights(r.weights));
        setError(null);
      })
      .catch((e: unknown) => !cancelled && setError(describeError(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  // Slider değişimi: gecikmeli önizleme (persist=false)
  const preview = (next: Weights) => {
    setWeights(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      api
        .rankingsRun({ profile_id: profileId, weights: next, persist: false })
        .then((r) => {
          setRun(r);
          setError(null);
        })
        .catch((e: unknown) => setError(describeError(e)))
        .finally(() => setLoading(false));
    }, 350);
  };

  const persistRun = async () => {
    setLoading(true);
    try {
      const r = await api.rankingsRun({ profile_id: profileId, weights, persist: true });
      setRun(r);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  };

  const sectors = useMemo(() => Array.from(new Set((run?.results ?? []).map((r) => r.sector).filter(Boolean))) as string[], [run]);

  const rows = useMemo(() => {
    const list = (run?.results ?? []).filter((r) => {
      const q = query.trim().toLowerCase();
      const matches = !q || r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q);
      const sectorOk = !sectorFilter || r.sector === sectorFilter;
      return matches && sectorOk;
    });
    const value = (r: RankingRun["results"][number]): number | string => {
      if (sortKey === "symbol") return r.symbol;
      if (sortKey === "rank" || sortKey === "cce10" || sortKey === "fss_rank" || sortKey === "rank_delta_vs_fss") return r[sortKey];
      return r.membership[sortKey];
    };
    return [...list].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      const cmp = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : Number(va) - Number(vb);
      return sortAsc ? cmp : -cmp;
    });
  }, [run, query, sectorFilter, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(key === "rank" || key === "fss_rank" || key === "symbol");
    }
  };

  const th = (key: SortKey, label: string, align = "text-left") => (
    <th className={`${align} cursor-pointer select-none`} onClick={() => toggleSort(key)}>
      {label} {sortKey === key ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Hisse Sıralaması" description="fpfs/CCE10 skoruna göre BIST 100 sıralaması. Ağırlıklar (μ_j) fpfs matrisinin sıfırıncı satırıdır; slider ile değiştirip sıralamanın nasıl değiştiğini görebilirsiniz.">
        {run && (
          <>
            <Badge tone={run.is_demo ? "warning" : "good"}>{run.is_demo ? "Demo veri" : run.data_source}</Badge>
            <span className="text-xs text-muted">
              Veri: <span className="num">{formatDate(run.window_start)} – {formatDate(run.data_as_of)}</span> · {run.scored_count}/{run.universe_size} hisse · {run.model_version}
            </span>
          </>
        )}
      </PageHeader>
      {run && <DemoBanner isDemo={run.is_demo} />}

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        <Card title="Profil ve ağırlıklar" subtitle="Başlangıç/demo parametreleri; akademik olarak doğrulanmış evrensel profiller değildir.">
          {profiles.error && <ErrorBox message={profiles.error} onRetry={profiles.reload} />}
          <div className="mb-3 flex flex-wrap gap-1">
            {(profiles.data ?? []).map((p) => (
              <button key={p.id} className={`btn text-xs ${p.id === profileId && !isCustom ? "btn-primary" : ""}`} onClick={() => setProfileId(p.id)}>
                {p.label}
              </button>
            ))}
            {isCustom && <Badge tone="accent">Özel ağırlık</Badge>}
          </div>
          {activeProfile && <p className="mb-3 text-xs text-muted">{activeProfile.description}</p>}
          <div className="space-y-3">
            {CRITERIA_ORDER.map((key) => (
              <label key={key} className="block text-xs">
                <div className="mb-1 flex justify-between">
                  <span className="text-secondary">
                    {CRITERIA_LABELS[key]} <span className="text-muted">(μ)</span>
                  </span>
                  <span className="num">{weights[key].toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={weights[key]}
                  onChange={(e) => preview(clampWeights({ ...weights, [key]: Number(e.target.value) }))}
                  className="w-full"
                />
              </label>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-primary text-xs" onClick={persistRun} disabled={loading}>
              Sıralamayı kaydet
            </button>
            {activeProfile && (
              <button className="btn text-xs" onClick={() => preview(clampWeights(activeProfile.weights))}>
                Profile dön
              </button>
            )}
          </div>
          {run && (
            <div className="mt-3 text-[11px] text-muted">
              Normalizasyon: getiri min-max (benefit), risk min-max (cost), temettü/likidite maksimuma bölme. Sabit sütun politikası: {run.constant_policy}.
              {run.persisted ? " Kayıtlı çalışma." : " Önizleme (kaydedilmedi)."}
            </div>
          )}
        </Card>

        <Card
          title={tab === "main" ? "CCE10 sıralaması" : "Operatör karşılaştırması"}
          actions={
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button className={`btn ${tab === "main" ? "btn-primary" : ""}`} onClick={() => setTab("main")}>fpfs / üyelikler</button>
              <button className={`btn ${tab === "compare" ? "btn-primary" : ""}`} onClick={() => setTab("compare")}>FSS · DRF · DMF</button>
              <input type="text" placeholder="Sembol / şirket ara" value={query} onChange={(e) => setQuery(e.target.value)} className="w-44" />
              <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)}>
                <option value="">Tüm sektörler</option>
                {sectors.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          }
        >
          {error && <ErrorBox message={error} />}
          {loading && !run && <Loading />}
          {run && (
            <>
              <WarningList warnings={run.warnings} />
              <div className={`mt-2 max-h-[70vh] overflow-auto ${loading ? "opacity-60" : ""}`}>
                <table className="table-dense w-full text-xs">
                  <thead>
                    {tab === "main" ? (
                      <tr>
                        {th("rank", "#")}
                        {th("symbol", "Sembol")}
                        <th>Şirket</th>
                        {th("cce10", "fpfs skoru", "text-right")}
                        {th("return", "Getiri üy.", "text-right")}
                        {th("risk", "Risk üy.", "text-right")}
                        {th("dividend", "Temettü üy.", "text-right")}
                        {th("liquidity", "Likidite üy.", "text-right")}
                        {th("rank_delta_vs_fss", "FSS farkı", "text-right")}
                      </tr>
                    ) : (
                      <tr>
                        {th("rank", "CCE10 #")}
                        {th("symbol", "Sembol")}
                        {th("cce10", "CCE10", "text-right")}
                        {th("fss_rank", "FSS #", "text-right")}
                        <th className="text-right">FSS</th>
                        <th className="text-right">DRF # / DRF</th>
                        <th className="text-right">DMF # / DMF</th>
                        <th className="text-right">Yıllık getiri*</th>
                        <th className="text-right">Aşağı risk</th>
                        <th className="text-right">Temettü ver.</th>
                        <th className="text-right">Likidite proxy</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.symbol}>
                        <td className="num">{r.rank}</td>
                        <td className="num font-semibold"><Link href={`/stocks/${r.symbol}`} className="text-accent hover:underline">{r.symbol.replace(".IS", "")}</Link></td>
                        {tab === "main" ? (
                          <>
                            <td className="max-w-[260px] truncate text-secondary" title={r.name}>{r.name}</td>
                            <td className="num text-right">{formatNumber(r.cce10, 4)}</td>
                            <td className="num text-right">{formatNumber(r.membership.return, 3)}</td>
                            <td className="num text-right">{formatNumber(r.membership.risk, 3)}</td>
                            <td className="num text-right">{formatNumber(r.membership.dividend, 3)}</td>
                            <td className="num text-right">{formatNumber(r.membership.liquidity, 3)}</td>
                            <td className={`num text-right ${r.rank_delta_vs_fss > 0 ? "pos" : r.rank_delta_vs_fss < 0 ? "neg" : "text-muted"}`}>{rankDeltaLabel(r.rank_delta_vs_fss)}</td>
                          </>
                        ) : (
                          <>
                            <td className="num text-right">{formatNumber(r.cce10, 4)}</td>
                            <td className="num text-right">{r.fss_rank}</td>
                            <td className="num text-right">{formatNumber(r.fss, 4)}</td>
                            <td className="num text-right">{r.drf_rank} / {formatNumber(r.drf, 3)}</td>
                            <td className="num text-right">{r.dmf_rank} / {formatNumber(r.dmf, 2)}</td>
                            <td className="num text-right">{formatPct(r.criteria.annualized_return, 1, true)}</td>
                            <td className="num text-right">{formatPct(r.criteria.risk, 3)}</td>
                            <td className="num text-right" title={r.criteria.dividend_status}>{formatPct(r.criteria.dividend, 2)}{r.criteria.dividend_status !== "observed" ? "†" : ""}</td>
                            <td className="num text-right">{formatCompact(r.criteria.liquidity)} ₺</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {tab === "compare" && (
                <p className="mt-2 text-[11px] text-muted">
                  * Yıllık getiri yalnızca gösterim içindir (günlük ortalama × 252); üyelikler dönemsel (günlük) ortalamadan üretilir. † Temettü gözlenmedi veya sağlayıcıdan alınamadı. Likidite proxy = medyan(kapanış × hacim), gerçek devir hızı değildir.
                </p>
              )}
              {Object.keys(run.excluded).length > 0 && (
                <details className="mt-2 text-xs text-muted">
                  <summary>Dışlanan semboller ({Object.keys(run.excluded).length})</summary>
                  <ul className="mt-1 list-disc pl-4">
                    {Object.entries(run.excluded).map(([s, reason]) => (
                      <li key={s}><span className="num">{s}</span>: {reason}</li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
