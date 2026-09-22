"""Seans kapanmadan bugünün yarım satırının dışlanması."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.stock_selection.application import MarketDataService


def _frame(dates):
    return pd.DataFrame({"date": pd.to_datetime(dates), "symbol": "A.IS", "close": 10.0})


def test_open_session_row_is_dropped_before_close():
    now = datetime(2026, 9, 22, 14, 0, tzinfo=ZoneInfo("Europe/Istanbul"))
    out, warnings = MarketDataService._drop_open_session(_frame(["2026-09-21", "2026-09-22"]), now=now)
    assert out["date"].dt.date.astype(str).tolist() == ["2026-09-21"]
    assert warnings and "Seans sürüyor" in warnings[0]


def test_today_row_is_kept_after_close():
    now = datetime(2026, 9, 22, 18, 45, tzinfo=ZoneInfo("Europe/Istanbul"))
    out, warnings = MarketDataService._drop_open_session(_frame(["2026-09-21", "2026-09-22"]), now=now)
    assert len(out) == 2 and warnings == []
