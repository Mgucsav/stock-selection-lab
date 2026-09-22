/** Biçimlendirme ve küçük saf yardımcılar (Vitest ile test edilir). */

import { CRITERIA_ORDER, type CriterionKey, type Weights } from "./types";

const TL = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const TL_PRECISE = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NUMBER = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });

export function formatTL(value: number | null | undefined, precise = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return (precise ? TL_PRECISE : TL).format(value);
}

export function formatPct(value: number | null | undefined, digits = 2, signed = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const pct = value * 100;
  const text = `${pct.toFixed(digits).replace(".", ",")} %`;
  return signed && pct > 0 ? `+${text}` : text;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("tr-TR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${NUMBER.format(value / 1e9)} mlr`;
  if (abs >= 1e6) return `${NUMBER.format(value / 1e6)} mn`;
  if (abs >= 1e3) return `${NUMBER.format(value / 1e3)} bin`;
  return NUMBER.format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-");
  if (!y || !m || !d) return value;
  return `${d}.${m}.${y}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

/** İşarete göre CSS sınıfı: pozitif yeşil, negatif kırmızı. */
export function signClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0) return "";
  return value > 0 ? "pos" : "neg";
}

/** Ağırlıkları [0, 1] aralığına sıkıştırır ve dört kriteri garanti eder. */
export function clampWeights(weights: Partial<Record<CriterionKey, number>>): Weights {
  const out = {} as Weights;
  for (const key of CRITERIA_ORDER) {
    const raw = weights[key];
    const value = typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
    out[key] = Math.min(1, Math.max(0, Math.round(value * 100) / 100));
  }
  return out;
}

export function weightsEqual(a: Weights, b: Weights, tolerance = 1e-9): boolean {
  return CRITERIA_ORDER.every((key) => Math.abs(a[key] - b[key]) <= tolerance);
}

/** CCE10: (1/n) * Σ mu_j * a_ij — arayüzde önizleme için aynı formül. */
export function cce10(membership: Weights, weights: Weights): number {
  const n = CRITERIA_ORDER.length;
  return CRITERIA_ORDER.reduce((sum, key) => sum + weights[key] * membership[key], 0) / n;
}

/** Tam lot: floor(capital * weight / price). */
export function lotQuantity(capital: number, weight: number, price: number): number {
  if (price <= 0 || capital <= 0 || weight <= 0) return 0;
  return Math.floor((capital * weight) / price);
}

export function rankDeltaLabel(delta: number): string {
  if (delta === 0) return "=";
  return delta > 0 ? `▲${delta}` : `▼${Math.abs(delta)}`;
}

export const CRITERIA_LABELS: Record<CriterionKey, string> = {
  return: "Getiri",
  dividend: "Temettü",
  liquidity: "Likidite",
  risk: "Aşağı yönlü risk",
};

export const PROFILE_LABELS: Record<string, string> = {
  conservative: "Muhafazakâr",
  balanced: "Dengeli",
  aggressive: "Agresif",
  custom: "Özel",
};
