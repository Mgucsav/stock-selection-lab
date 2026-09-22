"""Yahoo Finance (yfinance) sağlayıcı adaptörü.

* Semboller sınırlı boyutlu batch'ler hâlinde indirilir.
* Her batch için retry + üstel geri çekilme uygulanır.
* Tek sembolün başarısız olması bütün işlemi durdurmaz; sembol
  ``provider_error`` veya ``no_data`` olarak işaretlenir.
* ``auto_adjust=False`` ile ham ``close`` ve ``adj_close`` birlikte alınır;
  ``actions=True`` ile temettü sütunu istenir.

Veri günlük ve gecikmelidir; bu adaptör gerçek zamanlı veri sağlamaz.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
import logging
import time

import pandas as pd

from .base import (
    INTRADAY_COLUMNS,
    INTRADAY_LIMITS,
    RAW_PRICE_COLUMNS,
    FetchOutcome,
    ProviderBatchResult,
    Quote,
    SymbolFetchStatus,
    empty_intraday_frame,
    empty_raw_frame,
)

logger = logging.getLogger(__name__)

_YF_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
    "Dividends": "dividends",
}


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), max(size, 1))]


class YahooFinanceProvider:
    """yfinance üzerinden günlük OHLCV + temettü verisi indirir."""

    name = "yahoo"

    def __init__(
        self,
        batch_size: int = 25,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        downloader: Callable[..., pd.DataFrame] | None = None,
        intraday_downloader: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._downloader = downloader
        self._intraday_downloader = intraday_downloader

    # ----------------------------------------------------------------- yfinance
    def _download(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        if self._downloader is not None:
            return self._downloader(symbols, start, end)
        import yfinance as yf  # yalnızca gerçek çağrıda içe aktarılır

        return yf.download(
            tickers=symbols,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            group_by="ticker",
            threads=False,
            progress=False,
        )

    @staticmethod
    def _yf_error_messages() -> dict[str, str]:
        try:
            from yfinance import shared  # type: ignore

            errors = getattr(shared, "_ERRORS", {}) or {}
            return {str(k): str(v) for k, v in errors.items()}
        except Exception:  # pragma: no cover - savunma amaçlı
            return {}

    # ------------------------------------------------------------------ parse
    @staticmethod
    def _extract_symbol(frame: pd.DataFrame, symbol: str, single: bool) -> pd.DataFrame | None:
        if frame is None or frame.empty:
            return None
        if single:
            sub = frame
            if isinstance(sub.columns, pd.MultiIndex):
                level0 = sub.columns.get_level_values(0)
                if symbol in level0:
                    sub = sub[symbol]
                else:
                    sub = sub.droplevel(-1, axis=1) if sub.columns.nlevels > 1 else sub
        else:
            if not isinstance(frame.columns, pd.MultiIndex):
                return None
            if symbol not in frame.columns.get_level_values(0):
                return None
            sub = frame[symbol]
        sub = sub.rename(columns=_YF_COLUMN_MAP)
        keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume", "dividends"] if c in sub.columns]
        sub = sub.loc[:, keep].copy()
        sub = sub.dropna(how="all", subset=[c for c in ["open", "high", "low", "close"] if c in sub.columns])
        if sub.empty:
            return None
        sub.index = pd.to_datetime(sub.index).tz_localize(None).normalize()
        sub.index.name = "date"
        return sub.reset_index()

    def _normalize(self, sub: pd.DataFrame, symbol: str, ingested_at: datetime) -> pd.DataFrame:
        out = pd.DataFrame(
            {
                "date": sub["date"],
                "symbol": symbol,
                "open": sub.get("open"),
                "high": sub.get("high"),
                "low": sub.get("low"),
                "close": sub.get("close"),
                "adj_close": sub.get("adj_close", sub.get("close")),
                "volume": sub.get("volume"),
                "dividends": sub.get("dividends", pd.Series(float("nan"), index=sub.index)),
                "source": self.name,
                "ingested_at": ingested_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        return out.loc[:, RAW_PRICE_COLUMNS]

    # ------------------------------------------------------------------ public
    def fetch_daily(self, symbols: list[str], start: date, end: date) -> ProviderBatchResult:
        fetched_at = datetime.now(timezone.utc)
        frames: list[pd.DataFrame] = []
        statuses: list[SymbolFetchStatus] = []

        for batch in _chunks(list(dict.fromkeys(symbols)), self.batch_size):
            raw: pd.DataFrame | None = None
            last_error: Exception | None = None
            attempts = 0
            for attempt in range(1, self.max_retries + 1):
                attempts = attempt
                try:
                    raw = self._download(batch, start, end)
                    last_error = None
                    break
                except Exception as error:  # ağ/oran sınırı vb.
                    last_error = error
                    logger.warning("Yahoo batch hatası (%s/%s): %s", attempt, self.max_retries, error)
                    if attempt < self.max_retries:
                        self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))

            if last_error is not None:
                for symbol in batch:
                    statuses.append(
                        SymbolFetchStatus(
                            symbol=symbol,
                            outcome=FetchOutcome.PROVIDER_ERROR,
                            message=f"Sağlayıcı hatası: {last_error}",
                            attempts=attempts,
                        )
                    )
                continue

            yf_errors = self._yf_error_messages()
            single = len(batch) == 1
            for symbol in batch:
                try:
                    sub = self._extract_symbol(raw, symbol, single) if raw is not None else None
                except Exception as error:  # beklenmeyen şekil
                    statuses.append(
                        SymbolFetchStatus(
                            symbol=symbol,
                            outcome=FetchOutcome.PROVIDER_ERROR,
                            message=f"Yanıt ayrıştırılamadı: {error}",
                            attempts=attempts,
                        )
                    )
                    continue
                if sub is None or sub.empty:
                    message = yf_errors.get(symbol, "Kaynakta veri bulunamadı.")
                    lowered = message.lower()
                    outcome = (
                        FetchOutcome.NO_DATA
                        if ("no data" in lowered or "not found" in lowered or "delisted" in lowered or "bulunamadı" in lowered)
                        else FetchOutcome.PROVIDER_ERROR
                    )
                    statuses.append(
                        SymbolFetchStatus(symbol=symbol, outcome=outcome, message=message, attempts=attempts)
                    )
                    continue
                normalized = self._normalize(sub, symbol, fetched_at)
                frames.append(normalized)
                statuses.append(
                    SymbolFetchStatus(
                        symbol=symbol,
                        outcome=FetchOutcome.OK,
                        rows=len(normalized),
                        first_date=normalized["date"].min().date(),
                        last_date=normalized["date"].max().date(),
                        dividends_available="dividends" in sub.columns,
                        attempts=attempts,
                    )
                )

        frame = pd.concat(frames, ignore_index=True) if frames else empty_raw_frame()
        return ProviderBatchResult(provider=self.name, frame=frame, statuses=statuses, fetched_at=fetched_at)

    # --------------------------------------------------------------- intraday
    def _download_intraday(self, symbols: list[str], interval: str, period: str) -> pd.DataFrame:
        if self._intraday_downloader is not None:
            return self._intraday_downloader(symbols, interval, period)
        import yfinance as yf

        return yf.download(
            tickers=symbols, interval=interval, period=period, auto_adjust=False,
            actions=False, group_by="ticker", threads=False, progress=False, prepost=False,
        )

    @staticmethod
    def _select_symbol_frame(frame: pd.DataFrame, symbol: str, single: bool) -> pd.DataFrame | None:
        """yfinance çıktısından bir sembolün sütun bloğunu (ham indeksle) seçer."""
        if frame is None or frame.empty:
            return None
        if isinstance(frame.columns, pd.MultiIndex):
            level0 = frame.columns.get_level_values(0)
            if symbol in level0:
                return frame[symbol]
            if single and frame.columns.nlevels > 1:
                return frame.droplevel(-1, axis=1)
            return None
        return frame if single else None

    @staticmethod
    def _to_exchange_naive(index: pd.Index) -> pd.DatetimeIndex:
        """Yahoo gün içi damgaları borsa saat dilimindedir (Europe/Istanbul); tz bilgisini düşür."""
        idx = pd.to_datetime(index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert("Europe/Istanbul").tz_localize(None)
        return idx

    def fetch_intraday(self, symbols: list[str], interval: str, period: str | None = None) -> pd.DataFrame:
        if interval not in INTRADAY_LIMITS:
            raise ValueError(f"Desteklenmeyen gün içi aralık: {interval} (izinli: {', '.join(INTRADAY_LIMITS)})")
        period = period or INTRADAY_LIMITS[interval]
        frames: list[pd.DataFrame] = []
        for batch in _chunks(list(dict.fromkeys(symbols)), self.batch_size):
            raw: pd.DataFrame | None = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    raw = self._download_intraday(batch, interval, period)
                    break
                except Exception as error:
                    logger.warning("Yahoo gün içi hatası (%s/%s): %s", attempt, self.max_retries, error)
                    if attempt < self.max_retries:
                        self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            if raw is None or raw.empty:
                continue
            single = len(batch) == 1
            for symbol in batch:
                src = self._select_symbol_frame(raw, symbol, single)
                if src is None:
                    continue
                src = src.rename(columns=_YF_COLUMN_MAP)
                if "close" not in src.columns:
                    continue
                src = src.dropna(subset=["close"])
                if src.empty:
                    continue
                out = pd.DataFrame({"datetime": self._to_exchange_naive(src.index), "symbol": symbol})
                for column in ["open", "high", "low", "close", "volume"]:
                    out[column] = src[column].to_numpy() if column in src.columns else float("nan")
                frames.append(out.loc[:, INTRADAY_COLUMNS])
        if not frames:
            return empty_intraday_frame()
        return pd.concat(frames, ignore_index=True).sort_values(["symbol", "datetime"]).reset_index(drop=True)

    def fetch_quotes(self, symbols: list[str]) -> list[Quote]:
        """Son günün 1 dk barlarından son fiyat, son 5 günün saatlik barlarından önceki kapanış.

        Önceki kapanış günlük seriden alınmaz: Yahoo günlük seride son günleri
        eksik/NaN verebilir; gün içi barlar bu konuda daha güvenilirdir.
        """
        quotes: dict[str, Quote] = {}
        try:
            bars = self.fetch_intraday(symbols, "1m", "1d")
        except Exception as error:
            return [Quote(s, None, None, outcome=FetchOutcome.PROVIDER_ERROR, message=str(error)) for s in symbols]
        try:
            hourly = self.fetch_intraday(symbols, "1h", "5d")
        except Exception as error:  # önceki kapanış olmadan devam et
            logger.warning("Saatlik bar alınamadı, önceki kapanış boş kalacak: %s", error)
            hourly = empty_intraday_frame()
        for symbol in symbols:
            sub = bars.loc[bars["symbol"] == symbol] if not bars.empty else bars
            if sub.empty:
                quotes[symbol] = Quote(symbol, None, None, outcome=FetchOutcome.NO_DATA, message="Gün içi veri yok")
                continue
            last_day = sub["datetime"].max().normalize()
            day = sub.loc[sub["datetime"] >= last_day]
            last = day.iloc[-1]
            previous_close: float | None = None
            if not hourly.empty:
                prior = hourly.loc[(hourly["symbol"] == symbol) & (hourly["datetime"] < last_day)]
                if not prior.empty:
                    previous_close = float(prior.sort_values("datetime")["close"].iloc[-1])
            quotes[symbol] = Quote(
                symbol=symbol,
                last_price=float(last["close"]),
                last_time=last["datetime"].to_pydatetime(),
                day_open=float(day["open"].dropna().iloc[0]) if day["open"].notna().any() else None,
                day_high=float(day["high"].max()) if day["high"].notna().any() else None,
                day_low=float(day["low"].min()) if day["low"].notna().any() else None,
                day_volume=float(day["volume"].fillna(0).sum()),
                previous_close=previous_close,
            )
        return [quotes[s] for s in symbols]
