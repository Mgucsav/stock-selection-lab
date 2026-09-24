"""Yürüyen backtest motoru testleri: look-ahead engeli, maliyet, lot ve nakit tutarlılığı."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.stock_selection.backtest.engine import (
    BacktestConfig,
    equal_weight_strategy,
    rebalance_dates,
    run_backtest,
)
from src.stock_selection.features.panel import CriteriaPanel
from src.stock_selection.fuzzy.profiles import DEFAULT_PROFILES


def _market(symbols: dict[str, float], days: int = 500, start: str = "2024-01-01", seed: int = 5) -> pd.DataFrame:
    """Her sembol için sabit günlük sürüklenmeli sentetik seri (deterministik)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=days)
    frames = []
    for symbol, drift in symbols.items():
        noise = rng.normal(0, 0.004, days)
        close = 100 * np.cumprod(1 + drift + noise)
        frames.append(pd.DataFrame({
            "date": dates, "symbol": symbol, "open": close * 0.999, "high": close * 1.01,
            "low": close * 0.99, "close": close, "adj_close": close, "volume": 100_000.0,
            "dividends": 0.0, "source": "fake", "ingested_at": "2026-01-01T00:00:00Z",
        }))
    return pd.concat(frames, ignore_index=True)


def _benchmark(days: int = 500, start: str = "2024-01-01", drift: float = 0.0004) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=days)
    return pd.DataFrame({"date": dates, "symbol": "XU100.IS", "close": 8000 * np.cumprod(np.full(days, 1 + drift))})


@pytest.fixture
def market() -> pd.DataFrame:
    # A en güçlü, D en zayıf: momentum kriteri A'yı seçmeli
    return _market({"A.IS": 0.0012, "B.IS": 0.0008, "C.IS": 0.0004, "D.IS": -0.0002})


def test_rebalance_schedule_is_monthly_and_starts_on_trading_days(market: pd.DataFrame) -> None:
    panel = CriteriaPanel(market)
    config = BacktestConfig(start=date(2024, 6, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    schedule = rebalance_dates(panel, config)
    assert len(schedule) == 13
    assert all(d in set(panel.trading_days()) for d in schedule)
    assert schedule == sorted(schedule)


def test_backtest_respects_lookahead_barrier(market: pd.DataFrame) -> None:
    """Karar tarihinden sonra veri eklemek o tarihe kadarki kararları değiştirmemeli."""
    panel_full = CriteriaPanel(market)
    cutoff = pd.Timestamp("2025-06-30")
    truncated = market.loc[pd.to_datetime(market["date"]) <= cutoff]
    panel_short = CriteriaPanel(truncated)
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)

    full = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config, panel=panel_full)
    short = run_backtest(truncated, None, DEFAULT_PROFILES["balanced"], config, panel=panel_short)
    picks_full = [(r["date"], tuple(r["symbols"])) for r in full.rebalances]
    picks_short = [(r["date"], tuple(r["symbols"])) for r in short.rebalances]
    assert picks_full == picks_short


def test_trades_execute_after_the_decision_day(market: pd.DataFrame) -> None:
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    panel = CriteriaPanel(market)
    result = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config, panel=panel)
    schedule = {d.date().isoformat() for d in rebalance_dates(panel, config)}
    # İşlem günleri karar günlerinin kendisi değil, sonrasındaki ilk işlem günüdür
    assert all(r["date"] not in schedule for r in result.rebalances)


def test_costs_reduce_return_and_are_reported(market: pd.DataFrame) -> None:
    panel = CriteriaPanel(market)
    base = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365, cost_bps=0.0)
    free = run_backtest(market, None, DEFAULT_PROFILES["aggressive"], base, panel=panel)
    costly = run_backtest(market, None, DEFAULT_PROFILES["aggressive"], replace(base, cost_bps=50.0), panel=panel)
    assert free.metrics["total_cost"] == 0
    assert costly.metrics["total_cost"] > 0
    assert costly.metrics["total_return"] < free.metrics["total_return"]


def test_cash_and_lots_stay_valid(market: pd.DataFrame) -> None:
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365, cost_bps=25.0)
    result = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config)
    assert (result.equity["cash"] >= -1e-6).all()
    assert (result.equity["value"] > 0).all()
    assert all(0 <= r["turnover"] <= 2 for r in result.rebalances if r["turnover"] is not None)


def test_momentum_criterion_selects_the_strongest_symbol(market: pd.DataFrame) -> None:
    """Getiri kriteri tek başına ağırlıklandığında en güçlü seriyi seçmeli (motor doğru bağlanmış mı)."""
    from src.stock_selection.fuzzy.profiles import InvestorProfile

    profile = InvestorProfile(
        id="momentum", label="momentum", description="",
        weights={"return": 1.0, "dividend": 0.0, "liquidity": 0.0, "risk": 0.0},
        portfolio_size=1, max_weight=1.0, weighting_scheme="score_proportional",
    )
    # Sürüklenme farkı gürültüyü açıkça aşsın ki seçim deterministik olsun
    strong = _market({"A.IS": 0.004, "B.IS": 0.001, "C.IS": 0.0005, "D.IS": -0.001})
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    result = run_backtest(strong, None, profile, config)
    assert all(r["symbols"] == ["A.IS"] for r in result.rebalances)


def test_dividends_are_credited_to_cash() -> None:
    frame = _market({"A.IS": 0.0005, "B.IS": 0.0004}, days=400)
    pay_day = pd.Timestamp(sorted(frame["date"].unique())[300])
    mask = (frame["symbol"] == "A.IS") & (frame["date"] == pay_day)
    frame.loc[mask, "dividends"] = 5.0
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 7, 1), min_observations=60, lookback_days=365, cost_bps=0.0)
    with_dividend = run_backtest(frame, None, DEFAULT_PROFILES["balanced"], config)
    frame_zero = frame.copy()
    frame_zero["dividends"] = 0.0
    without = run_backtest(frame_zero, None, DEFAULT_PROFILES["balanced"], config)
    assert with_dividend.metrics["total_dividends"] > 0
    assert without.metrics["total_dividends"] == 0
    assert with_dividend.metrics["final_value"] > without.metrics["final_value"]


def test_benchmark_comparison_and_missing_benchmark(market: pd.DataFrame) -> None:
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    with_bench = run_backtest(market, _benchmark(), DEFAULT_PROFILES["balanced"], config)
    assert with_bench.metrics["benchmark_return"] is not None
    assert with_bench.metrics["excess_return"] is not None
    assert with_bench.equity["benchmark_norm"].notna().any()

    without = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config)
    assert without.metrics["benchmark_return"] is None
    assert any("BIST 100" in w for w in without.warnings)


def test_equal_weight_control_strategy(market: pd.DataFrame) -> None:
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    result = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config,
                          strategy=equal_weight_strategy(), label="eşit_ağırlık")
    assert result.profile_id == "eşit_ağırlık"
    assert all(len(r["symbols"]) == 4 for r in result.rebalances)  # evrenin tamamı


def test_survivorship_and_cost_limits_are_declared(market: pd.DataFrame) -> None:
    config = BacktestConfig(start=date(2024, 7, 1), end=date(2025, 6, 30), min_observations=60, lookback_days=365)
    result = run_backtest(market, None, DEFAULT_PROFILES["balanced"], config)
    text = " ".join(result.warnings)
    assert "survivorship" in text.lower() and "stopaj" in text.lower()
