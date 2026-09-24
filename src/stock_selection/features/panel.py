"""Aynı veri üzerinde çok sayıda karar tarihi için hızlı kriter hesabı.

``compute_criteria`` her çağrıda temiz tabloyu baştan gruplar; yürüyen backtest
36–120 karar tarihi için bunu tekrarlayınca dakikalara çıkar. ``CriteriaPanel``
sembol serilerini **bir kez** NumPy dizilerine açar, sonra her karar tarihinde
yalnızca pencereyi dilimler.

Sözleşme: ``criteria_at`` çıktısı ``compute_criteria`` ile **birebir aynıdır**
(``tests/test_panel.py`` bunu birkaç tarih için doğrular). Formül değişikliği
yapılacaksa iki yerde birden yapılmalı; referans uygulama ``criteria.py``dir.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS

from .criteria import CRITERIA_ORDER, MIN_OBSERVATIONS, CriteriaResult


@dataclass
class _SymbolSeries:
    dates: np.ndarray       # datetime64[ns], artan
    adj_close: np.ndarray   # float, geçersizler NaN
    close: np.ndarray
    volume: np.ndarray
    dividends: np.ndarray   # NaN = sağlayıcı vermedi
    has_dividend_data: bool


class CriteriaPanel:
    """Temiz uzun tablodan sembol bazlı diziler; tarih başına hızlı kriter üretir."""

    def __init__(self, clean: pd.DataFrame) -> None:
        self.symbols: list[str] = []
        self._series: dict[str, _SymbolSeries] = {}
        self.all_dates: np.ndarray = np.array([], dtype="datetime64[ns]")
        if clean is None or clean.empty:
            return
        frame = clean.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values(["symbol", "date"])
        for symbol, sub in frame.groupby("symbol", sort=True):
            adj = pd.to_numeric(sub["adj_close"], errors="coerce").to_numpy(dtype=float)
            adj = np.where(adj > 0, adj, np.nan)
            dividends = pd.to_numeric(sub["dividends"], errors="coerce").to_numpy(dtype=float)
            self._series[str(symbol)] = _SymbolSeries(
                dates=sub["date"].to_numpy(dtype="datetime64[ns]"),
                adj_close=adj,
                close=pd.to_numeric(sub["close"], errors="coerce").to_numpy(dtype=float),
                volume=pd.to_numeric(sub["volume"], errors="coerce").to_numpy(dtype=float),
                dividends=dividends,
                has_dividend_data=bool(np.isfinite(dividends).any()),
            )
        self.symbols = sorted(self._series)
        self.all_dates = np.unique(frame["date"].to_numpy(dtype="datetime64[ns]"))

    # ------------------------------------------------------------- yardımcı
    def effective_as_of(self, as_of: date | None) -> pd.Timestamp | None:
        """Karar tarihine kadar olan **en son** veri günü (compute_criteria ile aynı tanım)."""
        if self.all_dates.size == 0:
            return None
        if as_of is None:
            return pd.Timestamp(self.all_dates[-1])
        limit = np.datetime64(pd.Timestamp(as_of).normalize())
        index = int(np.searchsorted(self.all_dates, limit, side="right"))
        return pd.Timestamp(self.all_dates[index - 1]) if index else None

    def trading_days(self, start: date | None = None, end: date | None = None) -> list[pd.Timestamp]:
        dates = self.all_dates
        if start is not None:
            dates = dates[dates >= np.datetime64(pd.Timestamp(start).normalize())]
        if end is not None:
            dates = dates[dates <= np.datetime64(pd.Timestamp(end).normalize())]
        return [pd.Timestamp(d) for d in dates]

    # -------------------------------------------------------------- kriter
    def criteria_at(
        self,
        as_of: date | None = None,
        lookback_days: int | None = None,
        dividend_window_days: int = 365,
        min_observations: int = MIN_OBSERVATIONS,
        free_float_market_cap: Mapping[str, float] | None = None,
    ) -> CriteriaResult:
        """``compute_criteria`` ile aynı çıktı; pencereleme NumPy ile yapılır."""
        if not self._series:
            return CriteriaResult(pd.DataFrame(columns=CRITERIA_ORDER), warnings=["Temiz veri yok."])
        effective = self.effective_as_of(as_of)
        if effective is None:
            return CriteriaResult(pd.DataFrame(columns=CRITERIA_ORDER), warnings=["Karar tarihine kadar veri yok."])

        upper = np.datetime64(effective)
        lower = (
            np.datetime64(effective - pd.Timedelta(days=lookback_days))
            if lookback_days is not None else None
        )
        dividend_lower = np.datetime64(effective - pd.Timedelta(days=dividend_window_days))

        rows: dict[str, dict[str, object]] = {}
        excluded: dict[str, str] = {}
        warnings: list[str] = []
        window_start: pd.Timestamp | None = None

        for symbol in self.symbols:
            series = self._series[symbol]
            end = int(np.searchsorted(series.dates, upper, side="right"))
            start = int(np.searchsorted(series.dates, lower, side="right")) if lower is not None else 0
            if end <= start:
                continue
            dates = series.dates[start:end]
            if window_start is None or dates[0] < np.datetime64(window_start):
                window_start = pd.Timestamp(dates[0])

            adj = series.adj_close[start:end]
            valid = np.isfinite(adj)
            usable = int(valid.sum())
            if usable < min_observations:
                excluded[symbol] = f"insufficient_data ({usable} < {min_observations})"
                continue

            prices = adj[valid]
            returns = prices[1:] / prices[:-1] - 1.0
            mu = float(returns.mean())
            risk = float(np.maximum(0.0, mu - returns).mean())

            close = series.close[start:end]
            volume = series.volume[start:end]
            tl_volume = close * volume
            tl_volume = tl_volume[np.isfinite(tl_volume)]
            if tl_volume.size == 0:
                raise ValueError(f"{symbol}: hacim serisi boş.")
            liquidity = float(np.median(tl_volume))

            reference_price = float(close[-1])
            if not series.has_dividend_data or not np.isfinite(series.dividends[start:end]).any():
                dividend_yield, dividend_status = 0.0, "unavailable"
            else:
                div_mask = dates > dividend_lower
                cash = float(np.nansum(series.dividends[start:end][div_mask]))
                if cash > 0 and reference_price > 0:
                    dividend_yield, dividend_status = cash / reference_price, "observed"
                else:
                    dividend_yield, dividend_status = 0.0, "no_dividend_observed"

            rows[symbol] = {
                "return": mu,
                "dividend": dividend_yield,
                "liquidity": liquidity,
                "risk": risk,
                "annualized_return": mu * TRADING_DAYS,
                "dividend_status": dividend_status,
                "observations": int(returns.size),
                "last_close": reference_price,
            }

        table = pd.DataFrame.from_dict(rows, orient="index")
        liquidity_method = "tl_volume_proxy"
        if not table.empty and free_float_market_cap:
            covered = {s: float(free_float_market_cap[s]) for s in table.index
                       if s in free_float_market_cap and float(free_float_market_cap[s]) > 0}
            if len(covered) == len(table.index):
                table["liquidity"] = [table.loc[s, "liquidity"] / covered[s] for s in table.index]
                liquidity_method = "turnover_free_float"
            else:
                warnings.append(
                    f"{len(table.index) - len(covered)} sembolde fiili dolaşım piyasa değeri yok; "
                    "likidite gerçek devir hızı yerine TL hacim proxy'si ile hesaplandı."
                )
        if table.empty:
            warnings.append("Hiçbir sembol yeterli gözleme sahip değil.")
            table = pd.DataFrame(columns=CRITERIA_ORDER)
        else:
            table = table.loc[:, CRITERIA_ORDER + ["annualized_return", "dividend_status", "observations", "last_close"]]
            table.index.name = "symbol"
            unavailable = int((table["dividend_status"] == "unavailable").sum())
            if unavailable:
                warnings.append(f"{unavailable} sembolde temettü verisi sağlayıcıdan alınamadı (unavailable).")
        if excluded:
            warnings.append(f"{len(excluded)} sembol yetersiz veri nedeniyle dışlandı.")
        return CriteriaResult(
            table=table,
            excluded=excluded,
            warnings=warnings,
            as_of=effective.date(),
            window_start=(window_start or effective).date(),
            observations=int(table["observations"].max()) if not table.empty else 0,
            liquidity_method=liquidity_method,
        )
