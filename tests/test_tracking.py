"""Lot/nakit hesabı, look-ahead engeli ve değerleme testleri."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.stock_selection.tracking import allocate_lots, resolve_entry_prices, valuation_series
from src.stock_selection.tracking.snapshot import PositionSnapshot


def _clean(symbols: list[str], start: str = "2026-06-01", periods: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    frames = []
    for i, symbol in enumerate(symbols):
        close = np.linspace(100 + 10 * i, 120 + 10 * i, periods)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates, "symbol": symbol, "open": close - 1, "high": close + 1, "low": close - 2,
                    "close": close, "adj_close": close, "volume": 1000, "dividends": 0.0,
                    "source": "demo", "ingested_at": "2026-09-01T18:00:00Z",
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_entry_price_comes_from_next_trading_day_not_decision_day() -> None:
    clean = _clean(["A.IS"])
    decision = date(2026, 6, 3)  # Çarşamba
    entries = resolve_entry_prices(clean, ["A.IS"], decision)
    entry_date, price, field = entries["A.IS"]
    assert entry_date == date(2026, 6, 4)
    assert field == "open"
    expected_open = float(clean.loc[clean["date"] == pd.Timestamp("2026-06-04"), "open"].iloc[0])
    assert price == pytest.approx(expected_open)


def test_entry_is_pending_when_no_future_trading_day_exists() -> None:
    clean = _clean(["A.IS"])
    last = clean["date"].max().date()
    assert resolve_entry_prices(clean, ["A.IS"], last)["A.IS"] is None


def test_lot_allocation_uses_floor_and_keeps_remainder_in_cash() -> None:
    entries = {"A.IS": (date(2026, 6, 4), 101.0, "open"), "B.IS": (date(2026, 6, 4), 33.0, "open")}
    positions, cash = allocate_lots(10_000.0, {"A.IS": 0.6, "B.IS": 0.4}, entries)
    by = {p.symbol: p for p in positions}
    assert by["A.IS"].quantity == int(np.floor(6000 / 101.0)) == 59
    assert by["B.IS"].quantity == int(np.floor(4000 / 33.0)) == 121
    invested = 59 * 101.0 + 121 * 33.0
    assert cash == pytest.approx(10_000.0 - invested)
    assert cash >= 0


def test_pending_position_has_zero_lots() -> None:
    positions, cash = allocate_lots(1000.0, {"A.IS": 1.0}, {"A.IS": None})
    assert positions[0].is_pending and positions[0].quantity == 0
    assert cash == 1000.0


def test_valuation_series_and_metrics() -> None:
    clean = _clean(["A.IS", "B.IS"])
    positions = [
        PositionSnapshot("A.IS", 0.5, date(2026, 6, 2), 100.0, "open", 50, 5000.0),
        PositionSnapshot("B.IS", 0.5, date(2026, 6, 2), 110.0, "open", 40, 4400.0),
    ]
    cash = 600.0
    benchmark = clean.loc[clean["symbol"] == "A.IS", ["date", "close"]].assign(symbol="XU100.IS")
    result = valuation_series(positions, cash, 10_000.0, clean, benchmark)
    assert result.benchmark_available
    last = result.series.iloc[-1]
    a_last = float(clean.loc[(clean["symbol"] == "A.IS"), "close"].iloc[-1])
    b_last = float(clean.loc[(clean["symbol"] == "B.IS"), "close"].iloc[-1])
    assert last["value"] == pytest.approx(cash + 50 * a_last + 40 * b_last)
    assert result.metrics["total_return"] == pytest.approx(last["value"] / 10_000.0 - 1)
    assert result.metrics["cash_ratio"] == pytest.approx(cash / last["value"])
    assert result.metrics["relative_return"] is not None
    assert len(result.contributions) == 2
    assert result.series["portfolio_norm"].iloc[0] == pytest.approx(100.0)


def test_missing_benchmark_does_not_break_valuation() -> None:
    clean = _clean(["A.IS"])
    positions = [PositionSnapshot("A.IS", 1.0, date(2026, 6, 2), 100.0, "open", 90, 9000.0)]
    result = valuation_series(positions, 1000.0, 10_000.0, clean, None)
    assert not result.benchmark_available
    assert result.metrics["benchmark_return"] is None
    assert any("Benchmark" in w for w in result.warnings)
    empty_bench = pd.DataFrame(columns=["date", "symbol", "close"])
    result2 = valuation_series(positions, 1000.0, 10_000.0, clean, empty_bench)
    assert not result2.benchmark_available
