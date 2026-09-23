"use client";

import { useMemo, useState } from "react";

import { Badge, Card, DemoBanner, ErrorBox, KeyValue, Loading, PageHeader, StatTile, WarningList } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { formatDate, formatDateTime, formatNumber, formatPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function DataHealthPage() {
  const status = useApi(() => api.dataStatus(), []);
  const universe = useApi(() => api.universe(), []);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "failed" | "stale">("all");
  const [csvText, setCsvText] = useState("");
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const refresh = async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      status.setData(await api.dataRefresh());
      await universe.reload();
    } catch (e) {
      setRefreshError(describeError(e));
      await status.reload();
    } finally {
      setRefreshing(false);
    }
  };

  const upload = async () => {
    setUploadMessage(null);
    try {
      const result = await api.uploadUniverse(csvText);
      setUploadMessage(`Evren güncellendi: ${result.count} sembol${result.is_complete ? "" : " (universe incomplete)"}. Veriyi yenileyin.`);
      universe.setData(result);
      setCsvText("");
    } catch (e) {
      setUploadMessage(describeError(e));
    }
  };

  const s = status.data;
  const rows = useMemo(() => {
    const all = s?.symbol_statuses ?? [];
    if (filter === "failed") return all.filter((r) => r.outcome !== "ok" || r.clean_rows === 0);
    if (filter === "stale") return all.filter((r) => r.is_stale);
    return all;
  }, [s, filter]);

  return (
    <div className="space-y-4">
      <PageHeader title="Veri Sağlığı" description="Evren, sağlayıcı durumu, başarılı/başarısız çekimler, bayat semboller ve kalite uyarıları. Başarısız semboller gizlenmez.">
        <button className="btn btn-primary" onClick={refresh} disabled={refreshing}>
          {refreshing ? "Yahoo Finance’tan indiriliyor…" : "Canlı veriyi yenile (yfinance)"}
        </button>
      </PageHeader>
      {s && <DemoBanner isDemo={s.is_demo} dataLabel={s.data_label} />}
      {status.error && !s && <ErrorBox message={status.error} onRetry={status.reload} />}
      {refreshError && <ErrorBox message={`Canlı veri yenileme başarısız: ${refreshError}. Mevcut veri korunuyor; demo veri sessizce canlı veri yerine kullanılmaz.`} />}
      {s?.last_error && <ErrorBox message={`Son yenileme hatası: ${s.last_error}`} />}

      {status.loading && !s && <Loading />}
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Evren sembol sayısı" value={`${s.universe_size} / 100`} hint={s.universe_complete === false ? <span className="text-warning">⚠ universe incomplete</span> : "Tam BIST 100"} />
            <StatTile label="Başarılı çekim" value={s.ok_count} hint={`${s.failed_count} başarısız / eksik`} />
            <StatTile label="Bayat sembol" value={s.stale_symbols.length} hint={`Eşik: son gözlem > ${7} gün`} />
            <StatTile label="Veri aralığı" value={<span className="text-base">{formatDate(s.date_range?.start)} – {formatDate(s.date_range?.end)}</span>} hint={s.data_label} />
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <Card title="Sağlayıcı ve durum">
              <KeyValue
                items={[
                  ["Veri kaynağı", <Badge key="src" tone={s.is_demo ? "warning" : "good"}>{s.data_source}</Badge>],
                  ["Sağlayıcı adaptörü", s.provider],
                  ["Son yenileme denemesi", formatDateTime(s.last_refresh_at)],
                  ["Son başarılı güncelleme", formatDateTime(s.last_success_at)],
                  ["Benchmark", `${s.benchmark_symbol ?? "—"} · ${s.benchmark_available ? "mevcut" : "YOK"}`],
                  ["Evren geçerlilik tarihi", formatDate(s.universe_as_of)],
                  ["Evren kaynağı", s.universe_sources.join("; ") || "—"],
                  ["Otomatik yenileme", s.auto_refresh?.enabled
                    ? `${s.auto_refresh.running ? "şu an çalışıyor" : (s.auto_refresh.last_result ?? "bekliyor")} · veri ${s.auto_refresh.max_age_hours} saatten eskiyse yenilenir · son kontrol ${formatDateTime(s.auto_refresh.last_check_at)}${s.auto_refresh.last_error ? ` · hata: ${s.auto_refresh.last_error}` : ""}`
                    : "kapalı (SSL_AUTO_REFRESH_HOURS=0)"],
                  ["Ham satır / temiz / ret", `${String(s.quality_report.raw_rows ?? "—")} / ${String(s.quality_report.clean_rows ?? "—")} / ${String(s.quality_report.rejected_rows ?? "—")}`],
                ]}
              />
              {Boolean(s.quality_report.reasons) && Object.keys(s.quality_report.reasons as Record<string, number>).length > 0 && (
                <div className="mt-2 text-xs text-muted">
                  Ret nedenleri:{" "}
                  {Object.entries(s.quality_report.reasons as Record<string, number>).map(([k, v]) => `${k} (${String(v)})`).join(", ")}
                </div>
              )}
            </Card>
            <Card title="İkinci kaynakla doğrulama" subtitle="İş Yatırım kapanışlarıyla çapraz kontrol ve eksik gün tamamlama">
              {!s.verification?.available ? (
                <p className="text-xs text-muted">{s.verification?.message ?? "Son yenilemede doğrulama yapılmadı."}</p>
              ) : (
                <>
                  <KeyValue
                    items={[
                      ["Kaynak", s.verification.provider ?? "—"],
                      ["Pencere", `${formatDate(s.verification.window?.start)} – ${formatDate(s.verification.window?.end)}`],
                      ["Karşılaştırılan", `${s.verification.compared_rows ?? 0} satır · ${s.verification.compared_symbols ?? 0} sembol`],
                      ["Maks. kapanış sapması", formatPct(s.verification.max_deviation ?? null, 4)],
                      ["Medyan sapma", formatPct(s.verification.median_deviation ?? null, 6)],
                      ["Tolerans", formatPct(s.verification.tolerance ?? null, 2)],
                      ["Eksikten tamamlanan", `${s.verification.filled_rows ?? 0} sembol-gün`],
                      ["İkincil kaynakta alınamayan", `${s.verification.reference_failures?.length ?? 0} sembol`],
                    ]}
                  />
                  {(s.verification.mismatches?.length ?? 0) > 0 && (
                    <table className="table-dense mt-2 w-full text-xs">
                      <thead>
                        <tr><th>Sembol</th><th>Tarih</th><th className="text-right">Birincil</th><th className="text-right">İş Yatırım</th><th className="text-right">Sapma</th></tr>
                      </thead>
                      <tbody>
                        {s.verification.mismatches!.map((m) => (
                          <tr key={`${m.symbol}-${m.date}`}>
                            <td className="num">{m.symbol.replace(".IS", "")}</td>
                            <td className="num">{formatDate(m.date)}</td>
                            <td className="num text-right">{formatNumber(m.primary_close, 2)}</td>
                            <td className="num text-right">{formatNumber(m.reference_close, 2)}</td>
                            <td className="num text-right text-warning">{formatPct(m.deviation, 3)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </Card>

            <Card title="Kalite uyarıları">
              <WarningList warnings={[...s.warnings, ...(universe.data?.warnings ?? [])]} title="Evren ve veri uyarıları" />
              {s.warnings.length === 0 && (universe.data?.warnings.length ?? 0) === 0 && <p className="text-xs text-muted">Uyarı yok.</p>}
              {s.missing_symbols.length > 0 && (
                <p className="mt-2 text-xs text-secondary">
                  Eksik/başarısız: <span className="num">{s.missing_symbols.map((x) => x.replace(".IS", "")).join(", ")}</span>
                </p>
              )}
              {s.stale_symbols.length > 0 && (
                <p className="mt-1 text-xs text-secondary">
                  Bayat: <span className="num">{s.stale_symbols.map((x) => x.replace(".IS", "")).join(", ")}</span>
                </p>
              )}
            </Card>
          </div>

          <Card
            title="Sembol bazında durum"
            actions={
              <div className="flex gap-1 text-xs">
                {(["all", "failed", "stale"] as const).map((f) => (
                  <button key={f} className={`btn ${filter === f ? "btn-primary" : ""}`} onClick={() => setFilter(f)}>
                    {f === "all" ? `Tümü (${s.symbol_statuses.length})` : f === "failed" ? `Başarısız (${s.failed_count})` : `Bayat (${s.stale_symbols.length})`}
                  </button>
                ))}
              </div>
            }
          >
            <div className="max-h-[60vh] overflow-auto">
              <table className="table-dense w-full text-xs">
                <thead>
                  <tr>
                    <th>Sembol</th>
                    <th>Şirket</th>
                    <th>Sektör</th>
                    <th>Sonuç</th>
                    <th className="text-right">Temiz satır</th>
                    <th className="text-right">Ret</th>
                    <th>İlk</th>
                    <th>Son</th>
                    <th className="text-right">Eksik gün</th>
                    <th>Temettü</th>
                    <th>Not</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.symbol}>
                      <td className="num font-semibold">{r.symbol.replace(".IS", "")}</td>
                      <td className="max-w-[220px] truncate text-secondary" title={r.name}>{r.name}</td>
                      <td className="text-secondary">{r.sector ?? <span className="text-warning">yok</span>}</td>
                      <td>
                        <Badge tone={r.outcome === "ok" && r.clean_rows > 0 ? "good" : r.outcome === "provider_error" ? "critical" : "warning"}>
                          {r.outcome === "ok" && r.clean_rows > 0 ? "ok" : r.outcome}
                        </Badge>
                        {r.is_stale && <Badge tone="warning">bayat</Badge>}
                      </td>
                      <td className="num text-right">{r.clean_rows}</td>
                      <td className="num text-right">{r.rejected_rows}</td>
                      <td className="num">{formatDate(r.first_date)}</td>
                      <td className="num">{formatDate(r.last_date)}</td>
                      <td className="num text-right">{formatPct(r.missing_ratio, 1)}</td>
                      <td>{r.dividends_available ? "var" : "yok"}</td>
                      <td className="max-w-[320px] truncate text-muted" title={[r.message, ...r.warnings].filter(Boolean).join(" · ")}>{[r.message, ...r.warnings].filter(Boolean).join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <Card title="Evreni güncelle (CSV)" subtitle="symbol,name,sector,effective_from,effective_to,source — Yahoo sembolleri .IS uzantılı olmalı. Dosya config/bist100_symbols.csv üzerine yazılır.">
        {universe.data && (
          <p className="mb-2 text-xs text-muted">
            Mevcut evren: {universe.data.count}/{universe.data.expected} sembol · geçerlilik {formatDate(universe.data.as_of)} · kaynak: {universe.data.sources.join("; ")}
          </p>
        )}
        <textarea className="num h-32 w-full text-xs" placeholder={"symbol,name,sector,effective_from,effective_to,source\nTHYAO.IS,TÜRK HAVA YOLLARI A.O.,ULAŞTIRMA VE DEPOLAMA,2026-09-19,,KAP"} value={csvText} onChange={(e) => setCsvText(e.target.value)} />
        <div className="mt-2 flex items-center gap-2">
          <button className="btn" onClick={upload} disabled={csvText.trim().length < 10}>CSV’yi doğrula ve kaydet</button>
          {uploadMessage && <span className="text-xs text-secondary">{uploadMessage}</span>}
        </div>
      </Card>
    </div>
  );
}
