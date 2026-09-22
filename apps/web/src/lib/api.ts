/** Backend'e tipli erişim. Adres NEXT_PUBLIC_API_BASE_URL ile belirlenir. */

import type {
  DataStatus,
  GenerateResponse,
  HealthResponse,
  HistoryInterval,
  LiveValuation,
  PortfolioDetail,
  PortfolioSummary,
  Profile,
  QuotesResponse,
  RankingRun,
  StockHistoryResponse,
  StockSummary,
  UniverseResponse,
  Weights,
} from "./types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Sunucu hata gövdesini kullanıcıya gösterilebilir Türkçe mesaja çevirir. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return `Backend'e ulaşılamadı (${API_BASE_URL}). Servisin çalıştığından emin olun (.\\scripts\\dev.ps1).`;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Bilinmeyen hata.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Ağ hatası", 0);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)))
          .join("; ");
      }
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  universe: () => request<UniverseResponse>("/api/v1/universe"),
  uploadUniverse: (csvText: string) =>
    request<UniverseResponse>("/api/v1/universe", { method: "POST", body: JSON.stringify({ csv_text: csvText }) }),
  profiles: () => request<Profile[]>("/api/v1/profiles"),
  dataStatus: () => request<DataStatus>("/api/v1/data/status"),
  dataRefresh: (lookbackYears?: number) =>
    request<DataStatus>("/api/v1/data/refresh", {
      method: "POST",
      body: JSON.stringify(lookbackYears ? { lookback_years: lookbackYears } : {}),
    }),
  rankingsRun: (body: { profile_id?: string; weights?: Weights; as_of?: string; persist?: boolean }) =>
    request<RankingRun>("/api/v1/rankings/run", { method: "POST", body: JSON.stringify(body) }),
  rankingsLatest: (profileId?: string) =>
    request<RankingRun>(`/api/v1/rankings/latest${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ""}`),
  generatePortfolios: (body: { capital: number; decision_date?: string }) =>
    request<GenerateResponse>("/api/v1/portfolios/generate", { method: "POST", body: JSON.stringify(body) }),
  selectPortfolio: (candidateId: string, body: { initial_capital?: number; name?: string }) =>
    request<PortfolioDetail>(`/api/v1/portfolios/${candidateId}/select`, { method: "POST", body: JSON.stringify(body) }),
  portfolios: () => request<{ portfolios: PortfolioSummary[] }>("/api/v1/portfolios"),
  portfolio: (id: string) => request<PortfolioDetail>(`/api/v1/portfolios/${id}`),
  revalue: (id: string) => request<PortfolioDetail>(`/api/v1/portfolios/${id}/revalue`, { method: "POST" }),
  live: (id: string) => request<LiveValuation>(`/api/v1/portfolios/${id}/live`),
  quotes: (symbols?: string[], force = false) =>
    request<QuotesResponse>(
      `/api/v1/quotes?${symbols && symbols.length ? `symbols=${encodeURIComponent(symbols.join(","))}&` : ""}force=${force}`,
    ),
  stock: (symbol: string) => request<StockSummary>(`/api/v1/stocks/${encodeURIComponent(symbol)}`),
  stockHistory: (symbol: string, interval: HistoryInterval) =>
    request<StockHistoryResponse>(`/api/v1/stocks/${encodeURIComponent(symbol)}/history?interval=${interval}`),
};
