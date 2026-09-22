"use client";

import Link from "next/link";

import { Badge, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { PROFILE_LABELS, formatDate, formatDateTime, formatPct, formatTL, signClass } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function PortfoliosPage() {
  const list = useApi(() => api.portfolios(), []);
  const rows = list.data?.portfolios ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="Portföylerim" description="Seçilip başlatılan model portföyler (değiştirilemez anlık görüntü + günlük değerleme).">
        <Link href="/builder" className="btn btn-primary">Yeni model portföy</Link>
      </PageHeader>
      {list.loading && <Loading />}
      {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
      {!list.loading && rows.length === 0 && (
        <Card><p className="text-sm text-secondary">Henüz portföy seçilmedi.</p></Card>
      )}
      {rows.length > 0 && (
        <Card>
          <table className="table-dense w-full text-xs">
            <thead>
              <tr>
                <th>Ad</th>
                <th>Profil</th>
                <th>Durum</th>
                <th>Karar tarihi</th>
                <th className="text-right">Başlangıç</th>
                <th className="text-right">Güncel değer</th>
                <th className="text-right">Toplam getiri</th>
                <th className="text-right">BIST 100</th>
                <th>Kaynak</th>
                <th>Oluşturma</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.portfolio_id}>
                  <td><Link href={`/portfolios/${p.portfolio_id}`} className="text-accent underline">{p.name}</Link></td>
                  <td>{PROFILE_LABELS[p.profile_id] ?? p.profile_id}</td>
                  <td><Badge tone={p.status === "active" ? "good" : "warning"}>{p.status === "active" ? "aktif" : "beklemede"}</Badge></td>
                  <td className="num">{formatDate(p.decision_date)}</td>
                  <td className="num text-right">{formatTL(p.initial_capital)}</td>
                  <td className="num text-right">{formatTL(p.current_value)}</td>
                  <td className={`num text-right ${signClass(p.total_return)}`}>{formatPct(p.total_return, 2, true)}</td>
                  <td className={`num text-right ${signClass(p.benchmark_return)}`}>{formatPct(p.benchmark_return, 2, true)}</td>
                  <td><Badge tone={p.data_source === "demo" ? "warning" : "neutral"}>{p.data_source}</Badge></td>
                  <td className="num text-muted">{formatDateTime(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
