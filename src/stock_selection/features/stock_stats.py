"""Tek hisse için temel istatistikler (gözlenen geçmişten; tahmin değildir).

Hesaplananlar: dönem getirileri, yıllıklandırılmış volatilite (30/90/252 gün),
aşağı yönlü risk, maksimum düşüş, hareketli ortalamalar, 52 hafta aralığı,
ortalama hacim, pozitif gün oranı, en iyi/en kötü gün ve BIST 100'e göre beta.

Volatilite ve maksimum düşüş ``src.day01_baseline`` fonksiyonlarını, aşağı yönlü
risk ``features.criteria`` tanımını yeniden kullanır; böylece arayüzdeki sayı ile
modeldeki sayı aynı formülden gelir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS, max_drawdown, simple_returns

from .criteria import downside_risk

SMA_WINDOWS = (20, 50, 200)
VOLATILITY_WINDOWS = {"volatility_30d": 30, "volatility_90d": 90, "volatility_1y": TRADING_DAYS}


def _float(value: Any) -> float | None:
    """NaN/inf güvenli float dönüşümü."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _annualized_volatility(returns: pd.Series, window: int) -> float | None:
    tail = returns.tail(window)
    if len(tail) < 5:
        return None
    return _float(tail.std(ddof=1) * np.sqrt(TRADING_DAYS))


def compute_stock_stats(daily: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> dict[str, Any]:
    """``datetime, open, high, low, close, volume`` sütunlu günlük tablodan istatistikleri üretir.

    Girdi tablosu değiştirilmez. Yetersiz gözlemde ilgili alan ``None`` döner.
    """
    empty: dict[str, Any] = {
        "observations": 0, "first_date": None, "last_date": None, "last_close": None,
        "volatility_30d": None, "volatility_90d": None, "volatility_1y": None,
        "downside_risk": None, "max_drawdown_1y": None, "max_drawdown_all": None,
        "sma20": None, "sma50": None, "sma200": None, "price_vs_sma50": None, "price_vs_sma200": None,
        "high_52w": None, "low_52w": None, "from_high_52w": None, "from_low_52w": None,
        "avg_volume_30d": None, "avg_tl_volume_30d": None, "positive_day_ratio": None,
        "best_day": None, "best_day_date": None, "worst_day": None, "worst_day_date": None,
        "beta_1y": None, "correlation_1y": None, "mean_daily_return": None, "annualized_mean_return": None,
    }
    if daily is None or daily.empty or "close" not in daily.columns:
        return empty

    frame = daily.loc[:, [c for c in ["datetime", "open", "high", "low", "close", "volume"] if c in daily.columns]].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    frame = frame.sort_values("datetime")
    close = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.loc[close > 0]
    if len(frame) < 3:
        return empty
    close = pd.to_numeric(frame["close"], errors="coerce")
    close.index = frame["datetime"]

    returns = simple_returns(close.to_frame("close"))["close"]
    last_date = frame["datetime"].iloc[-1]
    year_mask = frame["datetime"] >= last_date - pd.Timedelta(days=365)
    year = frame.loc[year_mask]
    year_returns = returns.loc[returns.index >= last_date - pd.Timedelta(days=365)]

    stats = dict(empty)
    stats.update(
        observations=int(len(frame)),
        first_date=frame["datetime"].iloc[0].date().isoformat(),
        last_date=last_date.date().isoformat(),
        last_close=_float(close.iloc[-1]),
        downside_risk=_float(downside_risk(year_returns)) if len(year_returns) > 5 else None,
        max_drawdown_all=_float(max_drawdown(close)),
        max_drawdown_1y=_float(max_drawdown(close.loc[close.index >= last_date - pd.Timedelta(days=365)]))
        if year_mask.sum() > 2 else None,
        mean_daily_return=_float(returns.mean()),
        annualized_mean_return=_float(returns.mean() * TRADING_DAYS),
    )
    for key, window in VOLATILITY_WINDOWS.items():
        stats[key] = _annualized_volatility(returns, window)
    for window in SMA_WINDOWS:
        stats[f"sma{window}"] = _float(close.tail(window).mean()) if len(close) >= window else None
    for window in (50, 200):
        sma = stats[f"sma{window}"]
        stats[f"price_vs_sma{window}"] = _float(close.iloc[-1] / sma - 1.0) if sma else None

    if not year.empty:
        high = pd.to_numeric(year.get("high", year["close"]), errors="coerce").max()
        low = pd.to_numeric(year.get("low", year["close"]), errors="coerce").min()
        stats["high_52w"], stats["low_52w"] = _float(high), _float(low)
        stats["from_high_52w"] = _float(close.iloc[-1] / high - 1.0) if high else None
        stats["from_low_52w"] = _float(close.iloc[-1] / low - 1.0) if low else None
        if "volume" in year.columns:
            volume = pd.to_numeric(year["volume"], errors="coerce").tail(30)
            stats["avg_volume_30d"] = _float(volume.mean())
            stats["avg_tl_volume_30d"] = _float((volume * pd.to_numeric(year["close"], errors="coerce").tail(30)).mean())

    if len(year_returns) > 5:
        stats["positive_day_ratio"] = _float((year_returns > 0).mean())
        stats["best_day"] = _float(year_returns.max())
        stats["worst_day"] = _float(year_returns.min())
        stats["best_day_date"] = year_returns.idxmax().date().isoformat()
        stats["worst_day_date"] = year_returns.idxmin().date().isoformat()

    if benchmark is not None and not benchmark.empty:
        bench = benchmark.copy()
        column = "datetime" if "datetime" in bench.columns else "date"
        bench[column] = pd.to_datetime(bench[column])
        bench_close = pd.to_numeric(bench["close"], errors="coerce")
        bench_close.index = bench[column]
        bench_close = bench_close.loc[bench_close > 0].sort_index()
        if len(bench_close) > 5:
            bench_returns = simple_returns(bench_close.to_frame("close"))["close"]
            joined = pd.concat([year_returns.rename("stock"), bench_returns.rename("bench")], axis=1).dropna()
            if len(joined) > 20 and joined["bench"].var(ddof=1) > 0:
                covariance = joined["stock"].cov(joined["bench"])
                stats["beta_1y"] = _float(covariance / joined["bench"].var(ddof=1))
                stats["correlation_1y"] = _float(joined["stock"].corr(joined["bench"]))
    return stats
