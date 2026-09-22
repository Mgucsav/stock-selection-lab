"""Sağlayıcı, temizleme, cache ve evren testleri (ağ yok)."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.stock_selection.data.cache import ParquetPriceCache
from src.stock_selection.data.cleaning import clean_raw_prices
from src.stock_selection.data.providers import FetchOutcome
from src.stock_selection.data.providers.fake import FakeProvider
from src.stock_selection.data.providers.yahoo import YahooFinanceProvider
from src.stock_selection.demo import generate_demo_prices
from src.stock_selection.universe import load_universe, parse_universe_csv_text
from tests.conftest import SMALL_SYMBOLS, write_small_universe


def test_demo_data_is_deterministic() -> None:
    a = generate_demo_prices(["A.IS", "B.IS"], end=date(2026, 9, 18), years=1)
    b = generate_demo_prices(["A.IS", "B.IS"], end=date(2026, 9, 18), years=1)
    pd.testing.assert_frame_equal(a, b)
    assert (a["source"] == "demo").all()


def test_single_symbol_failure_does_not_stop_batch(demo_raw) -> None:
    provider = FakeProvider(frame=demo_raw, failing_symbols={"ASELS.IS"}, missing_symbols={"GARAN.IS"})
    result = provider.fetch_daily(SMALL_SYMBOLS, date(2025, 1, 1), date(2026, 9, 18))
    by = {s.symbol: s for s in result.statuses}
    assert by["ASELS.IS"].outcome == FetchOutcome.PROVIDER_ERROR
    assert by["GARAN.IS"].outcome == FetchOutcome.NO_DATA
    assert by["AKBNK.IS"].outcome == FetchOutcome.OK
    assert len(result.ok_symbols) == len(SMALL_SYMBOLS) - 2
    assert "ASELS.IS" not in set(result.frame["symbol"])


def test_yahoo_adapter_retries_then_marks_batch_as_provider_error() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def downloader(symbols, start, end):
        calls.append(len(symbols))
        raise ConnectionError("rate limited")

    provider = YahooFinanceProvider(batch_size=2, max_retries=3, backoff_seconds=1.0, sleep=sleeps.append, downloader=downloader)
    result = provider.fetch_daily(["A.IS", "B.IS", "C.IS"], date(2026, 1, 1), date(2026, 2, 1))
    assert len(calls) == 6  # 2 batch x 3 deneme
    assert sleeps == [1.0, 2.0, 1.0, 2.0]  # üstel geri çekilme
    assert all(s.outcome == FetchOutcome.PROVIDER_ERROR for s in result.statuses)
    assert result.frame.empty


def test_yahoo_adapter_parses_multiindex_frame_and_separates_no_data() -> None:
    dates = pd.date_range("2026-01-05", periods=3)
    columns = pd.MultiIndex.from_product([["A.IS", "Z.IS"], ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends"]])
    data = np.full((3, 14), np.nan)
    data[:, 0:7] = [[10, 11, 9, 10.5, 10.5, 100, 0], [10.5, 11, 10, 10.8, 10.8, 120, 0], [10.8, 12, 10, 11.5, 11.5, 90, 0.5]]
    frame = pd.DataFrame(data, index=dates, columns=columns)
    provider = YahooFinanceProvider(downloader=lambda s, a, b: frame, sleep=lambda _: None)
    result = provider.fetch_daily(["A.IS", "Z.IS"], date(2026, 1, 1), date(2026, 1, 10))
    by = {s.symbol: s for s in result.statuses}
    assert by["A.IS"].outcome == FetchOutcome.OK and by["A.IS"].rows == 3 and by["A.IS"].dividends_available
    assert by["Z.IS"].outcome == FetchOutcome.NO_DATA
    assert list(result.frame.columns) == [
        "date", "symbol", "open", "high", "low", "close", "adj_close", "volume", "dividends", "source", "ingested_at"
    ]
    assert result.frame["dividends"].iloc[-1] == 0.5


def test_cleaning_rejects_bad_rows_and_keeps_dividends(demo_raw) -> None:
    raw = demo_raw.copy()
    raw.loc[raw.index[0], "close"] = -1.0          # negatif fiyat
    raw.loc[raw.index[1], "volume"] = -5           # negatif hacim
    raw = pd.concat([raw, raw.iloc[[2]]])          # tam yinelenen
    raw.loc[raw.index[3], "dividends"] = 2.5
    result = clean_raw_prices(raw, reference_date=date(2026, 9, 19))
    assert len(result.rejected) == 2
    assert len(result.exact_duplicates) == 1
    assert not result.clean.duplicated(subset=["symbol", "date"]).any()
    key = raw.iloc[3]
    row = result.clean.loc[(result.clean["symbol"] == key["symbol"]) & (result.clean["date"] == pd.Timestamp(key["date"]))]
    assert row["dividends"].iloc[0] == 2.5
    assert any("ret nedeniyle" in w for w in result.warnings)


def test_cleaning_flags_stale_symbols(demo_raw) -> None:
    result = clean_raw_prices(demo_raw, reference_date=date(2026, 12, 1), stale_days=7)
    assert all(q.is_stale for q in result.symbol_quality.values())
    assert any("bayat" in w.lower() for w in result.warnings)


def test_parquet_cache_roundtrip_and_key_uniqueness(tmp_path: Path, demo_raw) -> None:
    pytest.importorskip("pyarrow", reason="pyarrow bu ortamda yüklenemiyor (Parquet isteğe bağlı)", exc_type=ImportError)
    cache = ParquetPriceCache(tmp_path / "cache")
    cleaned = clean_raw_prices(demo_raw, reference_date=date(2026, 9, 19)).clean
    cache.save_raw(demo_raw)
    cache.save_clean(cleaned)
    loaded = cache.load_clean()
    assert loaded is not None and len(loaded) == len(cleaned)
    with pytest.raises(ValueError):
        cache.save_clean(pd.concat([cleaned, cleaned.iloc[[0]]]))
    cache.clear()
    assert cache.load_clean() is None


def test_universe_loads_from_config_and_flags_incomplete(tmp_path: Path) -> None:
    universe = load_universe(write_small_universe(tmp_path / "u.csv"))
    assert len(universe.members) == len(SMALL_SYMBOLS)
    assert not universe.is_complete
    assert any("universe incomplete" in w for w in universe.warnings)
    assert universe.effective_from == date(2026, 1, 1)


def test_repo_universe_csv_has_100_dot_is_symbols() -> None:
    universe = load_universe(Path("config/bist100_symbols.csv"))
    assert universe.is_complete
    assert all(s.endswith(".IS") for s in universe.symbols)
    assert len(set(universe.symbols)) == 100


def test_universe_effective_dates_and_bad_symbols() -> None:
    text = (
        "symbol,name,sector,effective_from,effective_to,source\n"
        "AAA.IS,A,Sektör,2026-01-01,,kaynak\n"
        "BBB.IS,B,,2026-01-01,2026-06-01,kaynak\n"
        "CCC,C,,2026-01-01,,kaynak\n"
    )
    universe = parse_universe_csv_text(text, as_of=date(2026, 9, 1))
    assert universe.symbols == ["AAA.IS"]
    assert any("CCC" in w for w in universe.warnings)
