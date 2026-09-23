/** Backend API sözleşmesinin TypeScript karşılıkları (api/schemas.py ile eşleşir). */

export type CriterionKey = "return" | "dividend" | "liquidity" | "risk";
export type Weights = Record<CriterionKey, number>;

export const CRITERIA_ORDER: CriterionKey[] = ["return", "dividend", "liquidity", "risk"];

export interface HealthResponse {
  status: string;
  model_version: string;
  data_source: string;
  is_demo: boolean;
  data_label: string;
  disclaimer: string;
}

export interface UniverseMember {
  symbol: string;
  name: string;
  sector: string | null;
  effective_from: string | null;
  effective_to: string | null;
  source: string;
}

export interface UniverseResponse {
  as_of: string;
  count: number;
  expected: number;
  is_complete: boolean;
  sources: string[];
  warnings: string[];
  members: UniverseMember[];
}

export interface SymbolStatus {
  symbol: string;
  name: string;
  sector: string | null;
  outcome: "ok" | "no_data" | "provider_error" | string;
  message: string;
  clean_rows: number;
  rejected_rows: number;
  first_date: string | null;
  last_date: string | null;
  is_stale: boolean;
  missing_ratio: number | null;
  dividends_available: boolean;
  warnings: string[];
}

export interface DataStatus {
  data_source: string;
  is_demo: boolean;
  provider: string;
  data_label: string;
  last_refresh_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  universe_size: number;
  universe_complete: boolean | null;
  universe_as_of: string | null;
  universe_sources: string[];
  ok_count: number;
  failed_count: number;
  stale_symbols: string[];
  missing_symbols: string[];
  benchmark_symbol: string | null;
  benchmark_available: boolean | null;
  symbol_statuses: SymbolStatus[];
  date_range: { start: string | null; end: string | null } | null;
  quality_report: Record<string, unknown>;
  warnings: string[];
  verification?: {
    available: boolean;
    provider: string | null;
    message?: string;
    checked_at?: string;
    window?: { start: string | null; end: string | null };
    compared_rows?: number;
    compared_symbols?: number;
    max_deviation?: number | null;
    median_deviation?: number | null;
    filled_rows?: number;
    tolerance?: number;
    mismatches?: Array<{ symbol: string; date: string; primary_close: number; reference_close: number; deviation: number }>;
    reference_failures?: string[];
    warnings?: string[];
  } | null;
  auto_refresh?: {
    enabled: boolean;
    running: boolean;
    last_check_at: string | null;
    last_result: string | null;
    last_error: string | null;
    max_age_hours: number;
  } | null;
}

export interface Profile {
  id: string;
  label: string;
  description: string;
  weights: Weights;
  portfolio_size: number;
  max_weight: number;
  weighting_scheme: string;
  is_default: boolean;
  disclaimer: string;
}

export interface RankingRow {
  symbol: string;
  name: string;
  sector: string | null;
  rank: number;
  cce10: number;
  fss: number;
  fss_rank: number;
  drf: number;
  drf_rank: number;
  dmf: number;
  dmf_rank: number;
  rank_delta_vs_fss: number;
  membership: Weights;
  criteria: {
    return: number;
    annualized_return: number;
    dividend: number;
    dividend_status: string;
    liquidity: number;
    risk: number;
    observations: number;
    last_close: number;
  };
}

export interface RankingRun {
  score_run_id: string;
  created_at: string;
  profile_id: string;
  weights: Weights;
  data_as_of: string | null;
  window_start: string | null;
  normalization: Record<string, string>;
  constant_policy: string;
  model_version: string;
  data_source: string;
  is_demo: boolean;
  universe_size: number;
  scored_count: number;
  excluded: Record<string, string>;
  warnings: string[];
  persisted: boolean;
  results: RankingRow[];
}

export interface Holding {
  symbol: string;
  name: string;
  weight: number;
  cce10: number;
  rank: number;
  downside_risk: number;
  sector: string | null;
}

export interface CandidateStats {
  volatility: number | null;
  max_drawdown: number | null;
  backtest_start: string | null;
  backtest_end: string | null;
  observations: number;
}

export interface Candidate {
  candidate_id: string;
  score_run_id: string;
  profile_id: string;
  profile_label: string;
  profile_weights: Weights;
  weighting_scheme: string;
  max_weight: number;
  size: number;
  holdings: Holding[];
  weights: Record<string, number>;
  average_score: number;
  stats: CandidateStats;
  sector_exposure: Record<string, number> | null;
  warnings: string[];
  capital: number;
  decision_date: string;
  data_as_of: string | null;
  data_source: string;
  model_version: string;
}

export interface GenerateResponse {
  candidates: Candidate[];
  data_source: string;
  is_demo: boolean;
}

export interface Position {
  symbol: string;
  target_weight: number;
  entry_date: string | null;
  entry_price: number | null;
  price_field: string | null;
  quantity: number;
  cost: number;
}

export interface PortfolioSnapshot {
  target_weights: Record<string, number>;
  holdings: Holding[];
  positions: Position[];
  cash: number;
  entry_pending: string[];
  source_mismatch?: string;
  invested?: number;
  entry_date?: string;
  run_warnings?: string[];
}

export interface ValuationMetrics {
  status: "active" | "pending" | string;
  as_of?: string;
  start_date?: string;
  initial_capital?: number;
  current_value?: number;
  daily_change?: number;
  daily_return?: number;
  total_pnl?: number;
  total_return?: number;
  benchmark_return?: number | null;
  relative_return?: number | null;
  volatility?: number | null;
  max_drawdown?: number;
  cash?: number;
  cash_ratio?: number | null;
  observations?: number;
}

export interface SeriesPoint {
  date: string;
  value: number;
  total_return: number;
  portfolio_norm: number;
  daily_change: number;
  daily_return: number;
  benchmark_value: number | null;
  benchmark_norm: number | null;
}

export interface Contribution {
  symbol: string;
  quantity: number;
  entry_price: number;
  last_price: number;
  market_value: number;
  pnl: number;
  return_pct: number;
  contribution_pct: number;
  current_weight: number;
  target_weight: number;
}

export interface PortfolioSummary {
  portfolio_id: string;
  name: string;
  created_at: string;
  profile_id: string;
  status: string;
  decision_date: string;
  data_as_of: string | null;
  data_source: string;
  initial_capital: number;
  current_value: number | null;
  total_return: number | null;
  daily_change: number | null;
  benchmark_return: number | null;
  position_count: number;
}

export interface PortfolioDetail {
  portfolio_id: string;
  name: string;
  created_at: string;
  candidate_id: string;
  score_run_id: string;
  profile_id: string;
  profile_weights: Weights;
  model_version: string;
  decision_date: string;
  data_as_of: string | null;
  data_source: string;
  is_demo: boolean;
  initial_capital: number;
  status: string;
  activated_at: string | null;
  snapshot: PortfolioSnapshot;
  valuation: ValuationMetrics | null;
  series: SeriesPoint[];
  contributions: Contribution[];
  warnings: string[];
  benchmark_available: boolean;
}

export interface Quote {
  symbol: string;
  market_state: string | null;
  delayed_by_minutes: number | null;
  name: string | null;
  sector: string | null;
  last_price: number | null;
  last_time: string | null;
  day_open: number | null;
  day_high: number | null;
  day_low: number | null;
  day_volume: number | null;
  previous_close: number | null;
  day_change: number | null;
  day_change_pct: number | null;
  outcome: string;
  message: string;
}

export interface QuotesResponse {
  label: string;
  available: boolean;
  is_demo: boolean;
  fetched_at: string | null;
  from_cache: boolean;
  delayed_by_minutes: number | null;
  market_state: string | null;
  poll: { enabled: boolean; last_run_at: string | null; last_duration: number | null; last_error: string | null; symbols: number; market_open: boolean | null } | null;
  message: string | null;
  quotes: Quote[];
}

export type HistoryInterval = "1d" | "1h" | "15m" | "5m" | "1m";

export interface HistoryBar {
  t: string;
  o: number | null;
  h: number | null;
  l: number | null;
  c: number | null;
  v: number | null;
  adj: number | null;
  div: number | null;
}

export interface StockHistoryResponse {
  symbol: string;
  interval: HistoryInterval;
  label: string;
  count: number;
  bars: HistoryBar[];
  warnings: string[];
}

export interface DividendEvent {
  date: string;
  amount: number;
  close: number | null;
}

export interface StockSummary {
  symbol: string;
  name: string;
  sector: string | null;
  in_universe: boolean;
  quote: Quote | null;
  quote_label: string;
  daily_last_date: string | null;
  daily_last_close: number | null;
  daily_rows: number;
  change_1w: number | null;
  change_1m: number | null;
  change_3m: number | null;
  change_1y: number | null;
  high_52w: number | null;
  low_52w: number | null;
  dividends: DividendEvent[];
  dividend_yield_12m: number | null;
  stats: StockStats;
  ranking: (RankingRow & { score_run_id: string; data_as_of: string | null; profile_id: string }) | null;
  is_demo: boolean;
}

export interface StockStats {
  observations: number;
  first_date: string | null;
  last_date: string | null;
  last_close: number | null;
  volatility_30d: number | null;
  volatility_90d: number | null;
  volatility_1y: number | null;
  downside_risk: number | null;
  max_drawdown_1y: number | null;
  max_drawdown_all: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  price_vs_sma50: number | null;
  price_vs_sma200: number | null;
  high_52w: number | null;
  low_52w: number | null;
  from_high_52w: number | null;
  from_low_52w: number | null;
  avg_volume_30d: number | null;
  avg_tl_volume_30d: number | null;
  positive_day_ratio: number | null;
  best_day: number | null;
  best_day_date: string | null;
  worst_day: number | null;
  worst_day_date: string | null;
  beta_1y: number | null;
  correlation_1y: number | null;
  mean_daily_return: number | null;
  annualized_mean_return: number | null;
}

export interface LivePosition {
  symbol: string;
  quantity: number;
  entry_price: number;
  last_price: number;
  last_time: string | null;
  previous_close: number | null;
  market_value: number;
  pnl: number;
  return_pct: number;
  day_change: number;
  day_change_pct: number | null;
  weight: number;
  fallback: boolean;
}

export interface LiveValuation {
  portfolio_id: string;
  status: string;
  label: string;
  is_demo: boolean;
  available: boolean;
  message: string | null;
  as_of: string | null;
  from_cache: boolean | null;
  fetched_at: string | null;
  initial_capital: number | null;
  cash: number | null;
  current_value: number | null;
  total_pnl: number | null;
  total_return: number | null;
  day_change: number | null;
  day_change_pct: number | null;
  positions: LivePosition[];
  warnings: string[];
}
