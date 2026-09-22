"""Test ve demo için ağ kullanmayan sahte sağlayıcı."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from .base import (
    INTRADAY_COLUMNS,
    FetchOutcome,
    ProviderBatchResult,
    Quote,
    SymbolFetchStatus,
    empty_intraday_frame,
    empty_raw_frame,
)


class FakeProvider:
    """Önceden verilen ham tabloyu sembol bazında döndürür.

    ``failing_symbols`` sağlayıcı hatası, ``missing_symbols`` ise
    ``no_data`` senaryosunu taklit eder. Tek sembolün başarısızlığı diğer
    sembollerin verisini etkilemez.
    """

    name = "fake"

    def __init__(
        self,
        frame: pd.DataFrame | None = None,
        failing_symbols: set[str] | None = None,
        missing_symbols: set[str] | None = None,
        raise_on_batch: bool = False,
    ) -> None:
        self.frame = frame if frame is not None else empty_raw_frame()
        self.failing_symbols = failing_symbols or set()
        self.missing_symbols = missing_symbols or set()
        self.raise_on_batch = raise_on_batch
        self.calls: list[list[str]] = []
        self.quote_calls = 0
        # Günlük tablodan türetilen "son fiyat"a uygulanacak sahte gün içi çarpan (test için)
        self.intraday_multiplier = 1.0

    def fetch_daily(self, symbols: list[str], start: date, end: date) -> ProviderBatchResult:
        self.calls.append(list(symbols))
        if self.raise_on_batch:
            raise ConnectionError("Sahte sağlayıcı ağ hatası")
        fetched_at = datetime.now(timezone.utc)
        frames: list[pd.DataFrame] = []
        statuses: list[SymbolFetchStatus] = []
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        for symbol in symbols:
            if symbol in self.failing_symbols:
                statuses.append(
                    SymbolFetchStatus(symbol, FetchOutcome.PROVIDER_ERROR, message="Sahte sağlayıcı hatası")
                )
                continue
            if symbol in self.missing_symbols or self.frame.empty:
                statuses.append(SymbolFetchStatus(symbol, FetchOutcome.NO_DATA, message="Veri yok"))
                continue
            sub = self.frame.loc[self.frame["symbol"] == symbol].copy()
            sub = sub.loc[(pd.to_datetime(sub["date"]) >= start_ts) & (pd.to_datetime(sub["date"]) <= end_ts)]
            if sub.empty:
                statuses.append(SymbolFetchStatus(symbol, FetchOutcome.NO_DATA, message="Veri yok"))
                continue
            sub["source"] = self.name if "source" not in sub.columns else sub["source"]
            sub["ingested_at"] = fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            frames.append(sub)
            dates = pd.to_datetime(sub["date"])
            statuses.append(
                SymbolFetchStatus(
                    symbol,
                    FetchOutcome.OK,
                    rows=len(sub),
                    first_date=dates.min().date(),
                    last_date=dates.max().date(),
                    dividends_available=bool("dividends" in sub.columns and sub["dividends"].notna().any()),
                )
            )
        frame = pd.concat(frames, ignore_index=True) if frames else empty_raw_frame()
        return ProviderBatchResult(provider=self.name, frame=frame, statuses=statuses, fetched_at=fetched_at)

    # ------------------------------------------------------------ intraday
    def fetch_intraday(self, symbols: list[str], interval: str, period: str | None = None) -> pd.DataFrame:
        """Günlük satırları 'gün içi bar' gibi döndürür (test için yeterli)."""
        if self.raise_on_batch:
            raise ConnectionError("Sahte sağlayıcı ağ hatası")
        frames = []
        for symbol in symbols:
            if symbol in self.failing_symbols or symbol in self.missing_symbols:
                continue
            sub = self.frame.loc[self.frame["symbol"] == symbol].sort_values("date").tail(5)
            if sub.empty:
                continue
            out = pd.DataFrame(
                {
                    "datetime": pd.to_datetime(sub["date"]) + pd.Timedelta(hours=17, minutes=59),
                    "symbol": symbol,
                    "open": sub["open"].to_numpy(),
                    "high": sub["high"].to_numpy(),
                    "low": sub["low"].to_numpy(),
                    "close": sub["close"].to_numpy() * self.intraday_multiplier,
                    "volume": sub["volume"].to_numpy(),
                }
            )
            frames.append(out.loc[:, INTRADAY_COLUMNS])
        return pd.concat(frames, ignore_index=True) if frames else empty_intraday_frame()

    def fetch_quotes(self, symbols: list[str]) -> list[Quote]:
        self.quote_calls += 1
        if self.raise_on_batch:
            return [Quote(s, None, None, outcome=FetchOutcome.PROVIDER_ERROR, message="Sahte hata") for s in symbols]
        bars = self.fetch_intraday(symbols, "1m", "1d")
        quotes = []
        for symbol in symbols:
            sub = bars.loc[bars["symbol"] == symbol] if not bars.empty else bars
            if sub.empty:
                quotes.append(Quote(symbol, None, None, outcome=FetchOutcome.NO_DATA, message="Veri yok"))
                continue
            last = sub.iloc[-1]
            prev = float(sub.iloc[-2]["close"]) / self.intraday_multiplier if len(sub) > 1 else None
            quotes.append(
                Quote(symbol, float(last["close"]), last["datetime"].to_pydatetime(), day_open=float(last["open"]),
                      day_high=float(last["high"]), day_low=float(last["low"]), day_volume=float(last["volume"]),
                      previous_close=prev)
            )
        return quotes
