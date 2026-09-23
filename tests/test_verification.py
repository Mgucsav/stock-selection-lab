"""İkincil kaynakla doğrulama, eksik gün tamamlama ve gerçek devir hızı testleri."""

from datetime import date

import pandas as pd
import pytest

from src.stock_selection.data.providers.base import RAW_PRICE_COLUMNS
from src.stock_selection.data.providers.isyatirim import (
    IsYatirimProvider,
    to_source_symbol,
    to_universe_symbol,
)
from src.stock_selection.features.criteria import compute_criteria


def _row(symbol: str, day: str, close: float, aof: float | None = None, tl_volume: float = 1_000_000.0,
         adj: float | None = None, free_float: float = 5e10) -> dict:
    """İş Yatırım ucunun döndürdüğü satır biçimi."""
    aof = aof if aof is not None else close
    return {
        "HGDG_HS_KODU": symbol, "HGDG_TARIH": day, "HG_KAPANIS": close, "HGDG_KAPANIS": adj if adj else close,
        "HG_AOF": aof, "HG_MIN": close * 0.98, "HG_MAX": close * 1.02, "HGDG_HACIM": tl_volume,
        "HAO_PD": free_float, "PD": free_float * 3, "SERMAYE": 1e9,
    }


def test_symbol_mapping() -> None:
    assert to_source_symbol("THYAO.IS") == "THYAO" and to_source_symbol("THYAO") == "THYAO"
    assert to_universe_symbol("thyao") == "THYAO.IS" and to_universe_symbol("THYAO.IS") == "THYAO.IS"


def test_provider_maps_fields_and_derives_lots() -> None:
    rows = {"A": [_row("A", "2026-09-21", 100.0, aof=101.0, tl_volume=1_010_000.0, adj=95.0)]}
    provider = IsYatirimProvider(fetcher=lambda sym, s, e: rows.get(sym, []), sleep=lambda _: None)
    result = provider.fetch_daily(["A.IS"], date(2026, 9, 20), date(2026, 9, 22))
    assert list(result.frame.columns) == RAW_PRICE_COLUMNS
    row = result.frame.iloc[0]
    assert row["symbol"] == "A.IS" and row["close"] == 100.0 and row["adj_close"] == 95.0
    assert row["open"] == 101.0  # kaynakta açılış yok: ağırlıklı ortalama fiyat konur
    assert row["volume"] == pytest.approx(10_000)  # 1.010.000 TL / 101 TL
    assert pd.isna(row["dividends"]) and row["source"] == "isyatirim"
    assert row["high"] >= max(row["open"], row["close"]) and row["low"] <= min(row["open"], row["close"])


def test_provider_reports_failures_and_retries() -> None:
    calls: list[str] = []

    def flaky(symbol: str, start: date, end: date) -> list[dict]:
        calls.append(symbol)
        if symbol == "BAD":
            raise ConnectionError("zaman aşımı")
        return [_row(symbol, "2026-09-21", 10.0)]

    provider = IsYatirimProvider(fetcher=flaky, max_retries=3, sleep=lambda _: None)
    result = provider.fetch_daily(["GOOD.IS", "BAD.IS"], date(2026, 9, 20), date(2026, 9, 22))
    assert result.ok_symbols == ["GOOD.IS"] and result.failed_symbols == ["BAD.IS"]
    assert calls.count("BAD") == 3  # yeniden deneme
    assert "zaman aşımı" in [s.message for s in result.statuses if s.symbol == "BAD.IS"][0]


def test_fetch_window_returns_prices_and_free_float_in_one_pass() -> None:
    rows = {"A": [_row("A", "2026-09-21", 50.0, free_float=7e10)]}
    provider = IsYatirimProvider(fetcher=lambda sym, s, e: rows.get(sym, []), sleep=lambda _: None)
    prices, fundamentals = provider.fetch_window(["A.IS"], date(2026, 9, 20), date(2026, 9, 22))
    assert len(prices.frame) == 1
    assert fundamentals.loc[0, "free_float_market_cap"] == 7e10 and fundamentals.loc[0, "symbol"] == "A.IS"


def _clean_frame(symbol: str, closes: list[float], volume: float = 1000.0) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    return pd.DataFrame({
        "date": dates, "symbol": symbol, "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "adj_close": closes,
        "volume": volume, "dividends": 0.0, "source": "yahoo", "ingested_at": "2026-09-22T18:00:00Z",
    })


def test_liquidity_uses_real_turnover_when_free_float_available() -> None:
    frame = pd.concat([_clean_frame("A.IS", [100.0] * 200), _clean_frame("B.IS", [100.0] * 200)])
    # Aynı TL hacim, farklı dolaşım büyüklüğü → devir hızı B'de 10 kat yüksek
    result = compute_criteria(frame, min_observations=50, free_float_market_cap={"A.IS": 1e9, "B.IS": 1e8})
    assert result.liquidity_method == "turnover_free_float"
    assert result.table.loc["A.IS", "liquidity"] == pytest.approx(100 * 1000 / 1e9)
    assert result.table.loc["B.IS", "liquidity"] == pytest.approx(10 * result.table.loc["A.IS", "liquidity"])


def test_partial_free_float_falls_back_to_proxy_for_everyone() -> None:
    frame = pd.concat([_clean_frame("A.IS", [100.0] * 200), _clean_frame("B.IS", [100.0] * 200)])
    result = compute_criteria(frame, min_observations=50, free_float_market_cap={"A.IS": 1e9})
    assert result.liquidity_method == "tl_volume_proxy"
    assert result.table.loc["A.IS", "liquidity"] == pytest.approx(100 * 1000)  # bölünmedi
    assert any("proxy" in w for w in result.warnings)


def test_verification_fills_gaps_and_flags_mismatch(container) -> None:
    """Birincil kaynakta eksik gün tamamlanır, sapan kapanış raporlanır."""
    container.data.refresh()  # sahte Yahoo verisi
    clean = container.data.bundle().clean
    symbol = str(clean["symbol"].iloc[0])
    last_day = pd.to_datetime(clean["date"]).max()
    missing_day = (last_day + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    same_day = last_day.strftime("%Y-%m-%d")
    primary_close = float(
        clean.loc[(clean["symbol"] == symbol) & (pd.to_datetime(clean["date"]) == last_day), "close"].iloc[0]
    )

    def fetcher(source_symbol: str, start: date, end: date) -> list[dict]:
        if f"{source_symbol}.IS" != symbol:
            return []
        return [
            _row(source_symbol, same_day, primary_close * 1.05),  # %5 sapma → uyarı
            _row(source_symbol, missing_day, primary_close),      # eksik gün → tamamlanır
        ]

    container.data.secondary = IsYatirimProvider(fetcher=fetcher, sleep=lambda _: None)
    status = container.data.refresh()
    report = status["verification"]
    assert report["available"] is True
    assert report["filled_rows"] >= 1 and report["compared_rows"] >= 1
    assert report["mismatches"] and report["mismatches"][0]["symbol"] == symbol
    assert report["mismatches"][0]["deviation"] == pytest.approx(0.05, abs=1e-6)
    assert any("tolerans" in w for w in report["warnings"])

    refreshed = container.data.bundle().clean
    filled = refreshed.loc[(refreshed["symbol"] == symbol) & (refreshed["date"] == pd.Timestamp(missing_day))]
    assert len(filled) == 1 and filled["source"].iloc[0] == "isyatirim"
