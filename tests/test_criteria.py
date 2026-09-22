"""Kriter hesaplama testleri: getiri, aşağı yönlü risk, temettü, likidite."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.stock_selection.features import compute_criteria, downside_risk, liquidity_proxy, mean_return


def test_mean_return_is_periodic_mean() -> None:
    returns = pd.Series([0.01, -0.02, 0.03])
    assert mean_return(returns) == pytest.approx((0.01 - 0.02 + 0.03) / 3)


def test_downside_risk_is_semi_absolute_deviation() -> None:
    returns = pd.Series([0.01, -0.02, 0.03])
    mu = returns.mean()
    expected = np.mean([max(0.0, mu - r) for r in returns])
    assert downside_risk(returns) == pytest.approx(expected)
    assert downside_risk(returns) >= 0


def test_downside_risk_is_zero_for_constant_returns() -> None:
    assert downside_risk(pd.Series([0.01, 0.01, 0.01])) == pytest.approx(0.0)


def test_liquidity_proxy_is_median_tl_volume() -> None:
    close = pd.Series([10.0, 20.0, 30.0])
    volume = pd.Series([100, 100, 100])
    assert liquidity_proxy(close, volume) == pytest.approx(2000.0)


def _long_frame(symbol: str, closes: list[float], start: str = "2026-01-01", dividends: list[float] | None = None) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": symbol,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [1000] * len(closes),
            "dividends": dividends if dividends is not None else [np.nan] * len(closes),
            "source": "demo",
            "ingested_at": "2026-09-01T18:00:00Z",
        }
    )


def test_compute_criteria_respects_as_of_and_marks_dividend_status() -> None:
    closes = list(np.linspace(100, 130, 200))
    dividends = [0.0] * 200
    dividends[150] = 5.0
    frame = pd.concat(
        [
            _long_frame("AAA.IS", closes, dividends=dividends),
            _long_frame("BBB.IS", closes, dividends=[0.0] * 200),
            _long_frame("CCC.IS", closes),  # temettü sütunu tamamen NaN → unavailable
        ]
    )
    original = frame.copy(deep=True)
    as_of = frame["date"].max().date()
    result = compute_criteria(frame, as_of=as_of, min_observations=50)
    assert_frame_equal(frame, original)
    assert result.table.loc["AAA.IS", "dividend_status"] == "observed"
    assert result.table.loc["AAA.IS", "dividend"] == pytest.approx(5.0 / closes[-1])
    assert result.table.loc["BBB.IS", "dividend_status"] == "no_dividend_observed"
    assert result.table.loc["BBB.IS", "dividend"] == 0.0
    assert result.table.loc["CCC.IS", "dividend_status"] == "unavailable"

    earlier = compute_criteria(frame, as_of=date(2026, 3, 1), min_observations=20)
    assert earlier.as_of <= date(2026, 3, 1)
    assert earlier.table.loc["AAA.IS", "observations"] < result.table.loc["AAA.IS", "observations"]


def test_insufficient_data_symbols_are_excluded_not_silently_scored() -> None:
    frame = pd.concat([_long_frame("AAA.IS", list(np.linspace(100, 110, 200))), _long_frame("SHORT.IS", [10, 11, 12, 13])])
    result = compute_criteria(frame, min_observations=100)
    assert "SHORT.IS" in result.excluded
    assert "SHORT.IS" not in result.table.index
    assert list(result.table.columns[:4]) == ["return", "dividend", "liquidity", "risk"]
