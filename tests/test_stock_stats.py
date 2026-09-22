"""Tek hisse istatistikleri testleri."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.day01_baseline import TRADING_DAYS
from src.stock_selection.features.stock_stats import compute_stock_stats


def _daily(closes: list[float], start: str = "2024-01-01", volume: float = 1000.0) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [volume] * len(closes),
        }
    )


def test_empty_or_short_input_returns_none_fields():
    assert compute_stock_stats(pd.DataFrame())["observations"] == 0
    assert compute_stock_stats(_daily([10.0, 11.0]))["volatility_1y"] is None


def test_volatility_and_mean_return_match_formulas():
    rng = np.random.default_rng(3)
    closes = list(100 * np.cumprod(1 + rng.normal(0.0005, 0.02, 300)))
    frame = _daily(closes)
    original = frame.copy(deep=True)
    stats = compute_stock_stats(frame)
    assert_frame_equal(frame, original)  # girdi değişmez

    returns = pd.Series(closes).pct_change().dropna()
    assert stats["volatility_1y"] == pytest.approx(returns.tail(TRADING_DAYS).std(ddof=1) * np.sqrt(TRADING_DAYS), rel=1e-6)
    assert stats["volatility_30d"] == pytest.approx(returns.tail(30).std(ddof=1) * np.sqrt(TRADING_DAYS), rel=1e-6)
    assert stats["mean_daily_return"] == pytest.approx(returns.mean(), rel=1e-6)
    assert stats["annualized_mean_return"] == pytest.approx(returns.mean() * TRADING_DAYS, rel=1e-6)
    assert 0 <= stats["positive_day_ratio"] <= 1
    assert stats["observations"] == 300


def test_drawdown_moving_averages_and_52w_range():
    closes = [100.0] * 10 + [120.0] * 10 + [90.0] * 10 + [110.0] * 230
    stats = compute_stock_stats(_daily(closes))
    assert stats["max_drawdown_all"] == pytest.approx(-0.25)  # 120 -> 90
    assert stats["sma20"] == pytest.approx(110.0)
    assert stats["sma50"] == pytest.approx(110.0)
    assert stats["sma200"] == pytest.approx(110.0)
    assert stats["price_vs_sma50"] == pytest.approx(0.0)
    # 52 haftalık pencere 120 TL'li dönemi de kapsar (260 iş günü ≈ 52 hafta)
    assert stats["high_52w"] == pytest.approx(120.0 * 1.01)
    assert stats["low_52w"] == pytest.approx(90.0 * 0.99)
    assert stats["from_high_52w"] < 0 and stats["from_low_52w"] > 0
    assert stats["avg_volume_30d"] == pytest.approx(1000.0)
    assert stats["avg_tl_volume_30d"] == pytest.approx(110_000.0)


def test_beta_is_one_against_identical_benchmark_and_two_when_doubled():
    rng = np.random.default_rng(7)
    market = rng.normal(0.0004, 0.012, 260)
    bench_close = 8000 * np.cumprod(1 + market)
    stock_close = 100 * np.cumprod(1 + 2 * market)  # beta = 2
    bench = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=260), "close": bench_close})
    stats = compute_stock_stats(_daily(list(stock_close)), bench)
    assert stats["beta_1y"] == pytest.approx(2.0, abs=0.05)
    assert stats["correlation_1y"] == pytest.approx(1.0, abs=1e-6)

    same = compute_stock_stats(_daily(list(bench_close)), bench)
    assert same["beta_1y"] == pytest.approx(1.0, abs=1e-6)


def test_missing_benchmark_leaves_beta_none():
    stats = compute_stock_stats(_daily([100.0 + i for i in range(100)]), None)
    assert stats["beta_1y"] is None and stats["correlation_1y"] is None
