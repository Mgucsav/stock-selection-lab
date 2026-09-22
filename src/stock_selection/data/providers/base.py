"""``MarketDataProvider`` sözleşmesi ve ortak sonuç türleri.

Her sağlayıcı, uzun formatta (bir satır = bir sembol-gün) ham OHLCV tablosu
döndürür. Sütunlar ``RAW_PRICE_COLUMNS`` ile sabittir; ``dividends`` sütunu
kaynak sağlamıyorsa ``NaN`` bırakılır ve bu durum sembol durumunda
``dividends_available=False`` olarak işaretlenir.

Sağlayıcı hatası (ağ, oran sınırı) ile gerçekten veri bulunmaması
(``no_data``) ayrı ``FetchOutcome`` değerleri olarak kaydedilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

import pandas as pd

RAW_PRICE_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "source",
    "ingested_at",
]


class FetchOutcome(StrEnum):
    OK = "ok"
    NO_DATA = "no_data"
    PROVIDER_ERROR = "provider_error"


@dataclass
class SymbolFetchStatus:
    symbol: str
    outcome: FetchOutcome
    rows: int = 0
    first_date: date | None = None
    last_date: date | None = None
    dividends_available: bool = False
    message: str = ""
    attempts: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "outcome": self.outcome.value,
            "rows": self.rows,
            "first_date": self.first_date.isoformat() if self.first_date else None,
            "last_date": self.last_date.isoformat() if self.last_date else None,
            "dividends_available": bool(self.dividends_available),
            "message": self.message,
            "attempts": self.attempts,
        }


INTRADAY_COLUMNS = ["datetime", "symbol", "open", "high", "low", "close", "volume"]

# Yahoo'nun BIST için sunduğu gün içi aralıklar ve geriye dönük sınırları
INTRADAY_LIMITS: dict[str, str] = {"1m": "7d", "5m": "60d", "15m": "60d", "1h": "730d"}


@dataclass
class Quote:
    """Sorgu anındaki son bilinen (gecikmeli) fiyat özeti."""

    symbol: str
    last_price: float | None
    last_time: datetime | None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    day_volume: float | None = None
    previous_close: float | None = None
    outcome: FetchOutcome = FetchOutcome.OK
    message: str = ""

    @property
    def day_change(self) -> float | None:
        if self.last_price is None or not self.previous_close:
            return None
        return self.last_price - self.previous_close

    @property
    def day_change_pct(self) -> float | None:
        if self.last_price is None or not self.previous_close:
            return None
        return self.last_price / self.previous_close - 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "last_time": self.last_time.isoformat() if self.last_time else None,
            "day_open": self.day_open,
            "day_high": self.day_high,
            "day_low": self.day_low,
            "day_volume": self.day_volume,
            "previous_close": self.previous_close,
            "day_change": self.day_change,
            "day_change_pct": self.day_change_pct,
            "outcome": self.outcome.value,
            "message": self.message,
        }


@dataclass
class ProviderBatchResult:
    provider: str
    frame: pd.DataFrame
    statuses: list[SymbolFetchStatus] = field(default_factory=list)
    fetched_at: datetime | None = None

    @property
    def ok_symbols(self) -> list[str]:
        return [s.symbol for s in self.statuses if s.outcome == FetchOutcome.OK]

    @property
    def failed_symbols(self) -> list[str]:
        return [s.symbol for s in self.statuses if s.outcome != FetchOutcome.OK]


class MarketDataProvider(Protocol):
    """Günlük OHLCV + temettü verisi indiren adaptör sözleşmesi."""

    name: str

    def fetch_daily(
        self, symbols: list[str], start: date, end: date
    ) -> ProviderBatchResult:
        """Verilen semboller için ``[start, end]`` aralığındaki günlük veriyi getirir."""
        ...

    def fetch_intraday(self, symbols: list[str], interval: str, period: str) -> pd.DataFrame:
        """``INTRADAY_COLUMNS`` sütunlu gün içi barlar (zaman damgası borsa saat dilimi, tz-naive)."""
        ...

    def fetch_quotes(self, symbols: list[str]) -> list[Quote]:
        """Son bilinen fiyat özeti; gecikmeli olabilir, tick akışı değildir."""
        ...


def empty_intraday_frame() -> pd.DataFrame:
    frame = pd.DataFrame(columns=INTRADAY_COLUMNS)
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    return frame


def empty_raw_frame() -> pd.DataFrame:
    """Sözleşmeye uygun boş bir ham tablo üretir."""
    return pd.DataFrame(columns=RAW_PRICE_COLUMNS)
