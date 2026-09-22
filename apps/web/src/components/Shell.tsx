"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { Badge } from "./ui";

const NAV = [
  { href: "/", label: "Panel", icon: "▤" },
  { href: "/market", label: "Piyasa", icon: "◈" },
  { href: "/rankings", label: "Hisse Sıralaması", icon: "≡" },
  { href: "/builder", label: "Portföy Oluşturucu", icon: "◫" },
  { href: "/portfolios", label: "Portföylerim", icon: "◔" },
  { href: "/methodology", label: "Metodoloji", icon: "∑" },
  { href: "/data-health", label: "Veri Sağlığı", icon: "♥" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const status = useApi(() => api.dataStatus(), []);
  const s = status.data;

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-surface-1 md:flex">
        <div className="border-b border-border px-4 py-4">
          <div className="text-sm font-bold tracking-wide">BIST 100 · fpfs Lab</div>
          <div className="text-[11px] text-muted">Model portföy simülasyonu</div>
        </div>
        <nav className="flex-1 py-2">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href) || (item.href === "/market" && pathname.startsWith("/stocks"));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-4 py-2 text-sm ${active ? "bg-surface-2 text-primary" : "text-secondary hover:bg-surface-2 hover:text-primary"}`}
              >
                <span className="w-4 text-center text-muted">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border px-4 py-3 text-[11px] text-muted">
          Araştırma amaçlıdır; yatırım tavsiyesi değildir. Gerçek emir gönderilmez.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-1 px-4 py-2">
          <nav className="flex gap-2 overflow-x-auto md:hidden">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="whitespace-nowrap text-xs text-secondary">
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
            {status.error && <Badge tone="critical">Backend yok</Badge>}
            {s && (
              <>
                <Badge tone={s.is_demo ? "warning" : "good"}>{s.is_demo ? "Demo veri" : `Kaynak: ${s.provider}`}</Badge>
                <Badge>{s.data_label}</Badge>
                <span className="text-muted">
                  Veri tarihi: <span className="num text-secondary">{s.date_range?.end ?? "—"}</span>
                  {s.last_success_at && <> · Güncelleme: <span className="num text-secondary">{formatDateTime(s.last_success_at)}</span></>}
                </span>
              </>
            )}
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
