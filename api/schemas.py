"""Pydantic istek/yanıt modelleri (API sözleşmesi)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str
    model_version: str
    data_source: str
    is_demo: bool
    data_label: str
    disclaimer: str


class UniverseMemberOut(BaseModel):
    symbol: str
    name: str
    sector: str | None
    effective_from: str | None
    effective_to: str | None
    source: str


class UniverseResponse(BaseModel):
    as_of: str
    count: int
    expected: int
    is_complete: bool
    sources: list[str]
    warnings: list[str]
    members: list[UniverseMemberOut]


class UniverseUploadRequest(BaseModel):
    csv_text: str = Field(min_length=10)


class DataRefreshRequest(BaseModel):
    lookback_years: int | None = Field(default=None, ge=1, le=10)


class DataStatusResponse(BaseModel):
    data_source: str
    is_demo: bool
    provider: str
    data_label: str
    last_refresh_at: str | None
    last_success_at: str | None
    last_error: str | None
    universe_size: int
    universe_complete: bool | None = None
    universe_as_of: str | None = None
    universe_sources: list[str] = []
    ok_count: int
    failed_count: int
    stale_symbols: list[str] = []
    missing_symbols: list[str] = []
    benchmark_symbol: str | None = None
    benchmark_available: bool | None = None
    symbol_statuses: list[dict[str, Any]] = []
    date_range: dict[str, str | None] | None = None
    quality_report: dict[str, Any] = {}
    warnings: list[str] = []
    auto_refresh: dict[str, Any] | None = None


class ProfileOut(BaseModel):
    id: str
    label: str
    description: str
    weights: dict[str, float]
    portfolio_size: int
    max_weight: float
    weighting_scheme: str
    is_default: bool
    disclaimer: str


class RankingRunRequest(BaseModel):
    profile_id: str | None = None
    weights: dict[str, float] | None = None
    as_of: date | None = None
    persist: bool = True
    constant_policy: str = "neutral"

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        for key, weight in value.items():
            if not 0.0 <= float(weight) <= 1.0:
                raise ValueError(f"'{key}' ağırlığı 0 ile 1 arasında olmalıdır.")
        return value


class RankingRow(BaseModel):
    symbol: str
    name: str
    sector: str | None
    rank: int
    cce10: float
    fss: float
    fss_rank: int
    drf: float
    drf_rank: int
    dmf: float
    dmf_rank: int
    rank_delta_vs_fss: int
    membership: dict[str, float]
    criteria: dict[str, Any]


class RankingRunResponse(BaseModel):
    score_run_id: str
    created_at: str
    profile_id: str
    weights: dict[str, float]
    data_as_of: str | None
    window_start: str | None
    normalization: dict[str, str]
    constant_policy: str
    model_version: str
    data_source: str
    is_demo: bool
    universe_size: int
    scored_count: int
    excluded: dict[str, str]
    warnings: list[str]
    persisted: bool
    results: list[RankingRow]


class PortfolioGenerateRequest(BaseModel):
    capital: float = Field(gt=0)
    decision_date: date | None = None
    profile_ids: list[str] | None = None


class CandidateOut(BaseModel):
    candidate_id: str
    score_run_id: str
    profile_id: str
    profile_label: str
    profile_weights: dict[str, float]
    weighting_scheme: str
    max_weight: float
    size: int
    holdings: list[dict[str, Any]]
    weights: dict[str, float]
    average_score: float
    stats: dict[str, Any]
    sector_exposure: dict[str, float] | None
    warnings: list[str]
    capital: float
    decision_date: str
    data_as_of: str | None
    data_source: str
    model_version: str


class PortfolioGenerateResponse(BaseModel):
    candidates: list[CandidateOut]
    data_source: str
    is_demo: bool


class PortfolioSelectRequest(BaseModel):
    initial_capital: float | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, max_length=128)


class PortfolioSummary(BaseModel):
    portfolio_id: str
    name: str
    created_at: str
    profile_id: str
    status: str
    decision_date: str
    data_as_of: str | None
    data_source: str
    initial_capital: float
    current_value: float | None = None
    total_return: float | None = None
    daily_change: float | None = None
    benchmark_return: float | None = None
    position_count: int


class PortfolioDetail(BaseModel):
    portfolio_id: str
    name: str
    created_at: str
    candidate_id: str
    score_run_id: str
    profile_id: str
    profile_weights: dict[str, float]
    model_version: str
    decision_date: str
    data_as_of: str | None
    data_source: str
    is_demo: bool
    initial_capital: float
    status: str
    activated_at: str | None
    snapshot: dict[str, Any]
    valuation: dict[str, Any] | None
    series: list[dict[str, Any]]
    contributions: list[dict[str, Any]]
    warnings: list[str]
    benchmark_available: bool


class PortfolioListResponse(BaseModel):
    portfolios: list[PortfolioSummary]


class ErrorResponse(BaseModel):
    detail: str


class QuoteOut(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    last_price: float | None
    last_time: str | None
    day_open: float | None
    day_high: float | None
    day_low: float | None
    day_volume: float | None
    previous_close: float | None
    day_change: float | None
    day_change_pct: float | None
    outcome: str
    message: str


class QuotesResponse(BaseModel):
    label: str
    available: bool
    is_demo: bool
    fetched_at: str | None
    from_cache: bool
    message: str | None = None
    quotes: list[QuoteOut]


class HistoryBar(BaseModel):
    t: str
    o: float | None
    h: float | None
    l: float | None
    c: float | None
    v: float | None
    adj: float | None = None
    div: float | None = None


class StockHistoryResponse(BaseModel):
    symbol: str
    interval: str
    label: str
    count: int
    bars: list[HistoryBar]
    warnings: list[str] = []


class DividendOut(BaseModel):
    date: str
    amount: float
    close: float | None


class StockSummaryResponse(BaseModel):
    symbol: str
    name: str
    sector: str | None
    in_universe: bool
    quote: QuoteOut | None
    quote_label: str
    daily_last_date: str | None
    daily_last_close: float | None
    daily_rows: int
    change_1w: float | None
    change_1m: float | None
    change_3m: float | None
    change_1y: float | None
    high_52w: float | None
    low_52w: float | None
    dividends: list[DividendOut]
    dividend_yield_12m: float | None
    ranking: dict[str, Any] | None
    is_demo: bool


class LivePositionOut(BaseModel):
    symbol: str
    quantity: int
    entry_price: float
    last_price: float
    last_time: str | None
    previous_close: float | None
    market_value: float
    pnl: float
    return_pct: float
    day_change: float
    day_change_pct: float | None
    weight: float
    fallback: bool


class LiveValuationResponse(BaseModel):
    portfolio_id: str
    status: str
    label: str
    is_demo: bool
    available: bool
    message: str | None = None
    as_of: str | None = None
    from_cache: bool | None = None
    fetched_at: str | None = None
    initial_capital: float | None = None
    cash: float | None = None
    current_value: float | None = None
    total_pnl: float | None = None
    total_return: float | None = None
    day_change: float | None = None
    day_change_pct: float | None = None
    positions: list[LivePositionOut] = []
    warnings: list[str] = []
