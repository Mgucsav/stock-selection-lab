import type { ReactNode } from "react";

import { signClass } from "@/lib/format";

export function Card({ title, subtitle, actions, children, className = "" }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-4 ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, hint, delta, tone }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  delta?: number | null;
  tone?: "neutral" | "signed";
}) {
  const cls = tone === "signed" ? signClass(delta) : "";
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className={`num mt-1 text-2xl font-semibold ${cls}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-secondary">{hint}</div>}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warning" | "critical" | "accent" }) {
  const tones: Record<string, string> = {
    neutral: "border-border-strong text-secondary",
    good: "border-good text-good",
    warning: "border-warning text-warning",
    critical: "border-critical text-critical",
    accent: "border-accent text-accent",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function WarningList({ warnings, title = "Uyarılar" }: { warnings: string[] | undefined; title?: string }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="rounded border border-warning/40 bg-warning/5 p-3 text-xs text-secondary">
      <div className="mb-1 flex items-center gap-1 font-semibold text-warning">
        <span aria-hidden>⚠</span> {title}
      </div>
      <ul className="list-disc space-y-0.5 pl-4">
        {warnings.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded border border-critical/50 bg-critical/10 p-4 text-sm">
      <div className="mb-1 font-semibold text-critical">✖ Hata</div>
      <p className="text-secondary">{message}</p>
      {onRetry && (
        <button className="btn mt-3" onClick={onRetry}>
          Yeniden dene
        </button>
      )}
    </div>
  );
}

export function Loading({ label = "Yükleniyor…" }: { label?: string }) {
  return <div className="p-6 text-sm text-muted">{label}</div>;
}

export function DemoBanner({ isDemo, dataLabel }: { isDemo: boolean; dataLabel?: string }) {
  if (!isDemo) return null;
  return (
    <div className="rounded border border-warning/50 bg-warning/10 px-3 py-2 text-xs text-secondary">
      <strong className="text-warning">DEMO MODU:</strong> Gösterilen veri sentetik ve deterministiktir; canlı piyasa verisi
      değildir. Canlı veri için Veri Sağlığı sayfasından yenileme yapın. {dataLabel && <span>({dataLabel})</span>}
    </div>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-secondary">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function KeyValue({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="num text-primary">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
