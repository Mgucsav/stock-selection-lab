"""İş Yatırım günlük veri adaptörü (doğruluk katmanı).

Kaynak: ``isyatirim.com.tr`` halka açık "HisseTekil" veri ucu. Resmî bir API
değildir; bu yüzden **birincil sağlayıcı olarak değil**, Yahoo verisinin
doğrulanması, eksik günlerin tamamlanması ve fiili dolaşım piyasa değerinin
alınması için kullanılır.

Kaynağın verdiği alanlar ve bizim sözleşmemize karşılığı:

```text
HG_KAPANIS    → close       (ham kapanış)
HGDG_KAPANIS  → adj_close   (kurumsal işlemlere göre düzeltilmiş kapanış)
HG_MIN/HG_MAX → low/high
HG_AOF        → open  *     (kaynakta açılış fiyatı YOKTUR; ağırlıklı ortalama fiyat konur)
HGDG_HACIM    → volume **   (kaynak TL hacim verir; lot = TL hacim / AOF ile türetilir)
HAO_PD        → fiili dolaşımdaki piyasa değeri (gerçek devir hızı için)
```

\\* Bu yüzden İş Yatırım satırları ``source="isyatirim"`` ile işaretlenir ve
giriş fiyatı (bir sonraki işlem gününün açılışı) için Yahoo tercih edilir.
\\*\\* Temettü verisi bu uçtan gelmez; ``dividends`` boş bırakılır (Yahoo sağlar).

Kütüphane (``isyatirimhisse``) yerine doğrudan istek kullanılır: kütüphane
sembolleri sıralı çekiyor (~2,4 sn/sembol) ve sık zaman aşımı veriyor; burada
sınırlı eşzamanlılık + yeniden deneme ile 100 sembol ~40 sn'de tamamlanır.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
import logging
import time
from typing import Any, Callable

import numpy as np
import pandas as pd

from .base import (
    RAW_PRICE_COLUMNS,
    FetchOutcome,
    ProviderBatchResult,
    SymbolFetchStatus,
    empty_raw_frame,
)

logger = logging.getLogger(__name__)

ENDPOINT = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil"
USER_AGENT = "Mozilla/5.0 (compatible; stock-selection-lab/1.0)"
FUNDAMENTAL_COLUMNS = ["symbol", "date", "free_float_market_cap", "market_cap", "shares"]


def to_source_symbol(symbol: str) -> str:
    """``THYAO.IS`` → ``THYAO``."""
    return symbol[:-3] if symbol.upper().endswith(".IS") else symbol.upper()


def to_universe_symbol(code: str) -> str:
    """``THYAO`` → ``THYAO.IS``."""
    code = str(code).strip().upper()
    return code if code.endswith(".IS") else f"{code}.IS"


@dataclass
class _SymbolResult:
    symbol: str
    rows: list[dict[str, Any]]
    error: str | None = None


class IsYatirimProvider:
    """İş Yatırım günlük fiyat ve dolaşım piyasa değeri adaptörü."""

    name = "isyatirim"

    def __init__(
        self,
        max_workers: int = 10,
        max_retries: int = 3,
        timeout: float = 20.0,
        backoff_seconds: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
        fetcher: Callable[[str, date, date], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.timeout = timeout
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._fetcher = fetcher

    # ------------------------------------------------------------- transport
    def _request(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        if self._fetcher is not None:
            return self._fetcher(symbol, start, end)
        import requests

        response = requests.get(
            ENDPOINT,
            params={
                "hisse": symbol,
                "startdate": start.strftime("%d-%m-%Y"),
                "enddate": end.strftime("%d-%m-%Y"),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return list(payload.get("value") or [])

    def _fetch_symbol(self, symbol: str, start: date, end: date) -> _SymbolResult:
        source_symbol = to_source_symbol(symbol)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return _SymbolResult(symbol, self._request(source_symbol, start, end))
            except Exception as error:
                last_error = error
                if attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        return _SymbolResult(symbol, [], str(last_error))

    def _fetch_all(self, symbols: list[str], start: date, end: date) -> list[_SymbolResult]:
        unique = list(dict.fromkeys(symbols))
        if not unique:
            return []
        workers = max(1, min(self.max_workers, len(unique)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="isyatirim") as pool:
            return list(pool.map(lambda s: self._fetch_symbol(s, start, end), unique))

    # ----------------------------------------------------------------- parse
    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return float("nan")
        return number if np.isfinite(number) else float("nan")

    def _rows_to_frame(self, result: _SymbolResult, ingested_at: datetime) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for row in result.rows:
            close = self._number(row.get("HG_KAPANIS"))
            adj_close = self._number(row.get("HGDG_KAPANIS"))
            aof = self._number(row.get("HG_AOF"))
            tl_volume = self._number(row.get("HGDG_HACIM"))
            if not np.isfinite(close) or close <= 0:
                continue
            open_price = aof if np.isfinite(aof) and aof > 0 else close
            lots = tl_volume / aof if np.isfinite(tl_volume) and np.isfinite(aof) and aof > 0 else float("nan")
            records.append(
                {
                    "date": pd.to_datetime(row.get("HGDG_TARIH")).normalize(),
                    "symbol": result.symbol,
                    "open": open_price,
                    "high": self._number(row.get("HG_MAX")),
                    "low": self._number(row.get("HG_MIN")),
                    "close": close,
                    "adj_close": adj_close if np.isfinite(adj_close) and adj_close > 0 else close,
                    "volume": float(np.round(lots)) if np.isfinite(lots) else float("nan"),
                    "dividends": float("nan"),  # bu uçtan temettü gelmez
                    "source": self.name,
                    "ingested_at": ingested_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
        if not records:
            return empty_raw_frame()
        frame = pd.DataFrame.from_records(records)
        # Gün içi tutarlılık: kaynak AOF'u açılış olarak kullandığımız için sınırları güvenceye al
        frame["high"] = frame[["high", "open", "close"]].max(axis=1)
        frame["low"] = frame[["low", "open", "close"]].min(axis=1)
        return frame.loc[:, RAW_PRICE_COLUMNS]

    # ---------------------------------------------------------------- public
    def fetch_window(self, symbols: list[str], start: date, end: date) -> tuple[ProviderBatchResult, pd.DataFrame]:
        """Tek çekimde hem fiyat tablosu hem dolaşım piyasa değeri (iki kez istek atmamak için)."""
        results = self._fetch_all(symbols, start, end)
        return self._to_prices(results), self._to_fundamentals(results)

    def fetch_daily(self, symbols: list[str], start: date, end: date) -> ProviderBatchResult:
        return self._to_prices(self._fetch_all(symbols, start, end))

    def fetch_fundamentals(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Fiili dolaşım piyasa değeri (HAO_PD), piyasa değeri ve pay sayısı."""
        return self._to_fundamentals(self._fetch_all(symbols, start, end))

    def _to_prices(self, results: list[_SymbolResult]) -> ProviderBatchResult:
        fetched_at = datetime.now(timezone.utc)
        frames: list[pd.DataFrame] = []
        statuses: list[SymbolFetchStatus] = []
        for result in results:
            if result.error:
                statuses.append(
                    SymbolFetchStatus(result.symbol, FetchOutcome.PROVIDER_ERROR, message=f"İş Yatırım: {result.error}")
                )
                continue
            frame = self._rows_to_frame(result, fetched_at)
            if frame.empty:
                statuses.append(SymbolFetchStatus(result.symbol, FetchOutcome.NO_DATA, message="Kaynakta satır yok"))
                continue
            frames.append(frame)
            statuses.append(
                SymbolFetchStatus(
                    result.symbol, FetchOutcome.OK, rows=len(frame),
                    first_date=frame["date"].min().date(), last_date=frame["date"].max().date(),
                    dividends_available=False,
                )
            )
        combined = pd.concat(frames, ignore_index=True) if frames else empty_raw_frame()
        return ProviderBatchResult(provider=self.name, frame=combined, statuses=statuses, fetched_at=fetched_at)

    def _to_fundamentals(self, results: list[_SymbolResult]) -> pd.DataFrame:
        """Gerçek devir hızı (TL hacim / fiili dolaşım piyasa değeri) bu tablodan hesaplanır."""
        records: list[dict[str, Any]] = []
        for result in results:
            for row in result.rows:
                free_float = self._number(row.get("HAO_PD"))
                if not np.isfinite(free_float) or free_float <= 0:
                    continue
                records.append(
                    {
                        "symbol": result.symbol,
                        "date": pd.to_datetime(row.get("HGDG_TARIH")).normalize(),
                        "free_float_market_cap": free_float,
                        "market_cap": self._number(row.get("PD")),
                        "shares": self._number(row.get("SERMAYE")),
                    }
                )
        if not records:
            return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)
        return pd.DataFrame.from_records(records).loc[:, FUNDAMENTAL_COLUMNS]
