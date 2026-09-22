"""Deterministik çevrimdışı demo verisi.

Uygulama ilk açılışta cache boşsa bu sentetik veriyle çalışır. Veri
``source="demo"`` olarak etiketlenir, hiçbir zaman canlı veri gibi
sunulmaz ve canlı yenileme başarısız olduğunda sessizce yerine geçmez.
Aynı tohum aynı tabloyu üretir; testler bu özelliğe dayanır.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .data.providers.base import RAW_PRICE_COLUMNS

DEMO_SEED = 20260919
DEMO_SOURCE = "demo"


def generate_demo_prices(
    symbols: list[str],
    end: date,
    years: int = 3,
    benchmark_symbol: str = "XU100.IS",
    seed: int = DEMO_SEED,
) -> pd.DataFrame:
    """Evren sembolleri ve benchmark için sentetik günlük OHLCV + temettü üretir."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=int(252 * years))
    n = len(dates)
    ingested = pd.Timestamp(end).strftime("%Y-%m-%dT18:00:00Z")

    market = rng.normal(0.0008, 0.014, size=n)  # ortak piyasa faktörü
    frames: list[pd.DataFrame] = []

    def build(symbol: str, drift: float, vol: float, beta: float, base: float, div_yield: float) -> pd.DataFrame:
        idio = rng.normal(0.0, vol, size=n)
        returns = drift + beta * market + idio
        close = base * np.cumprod(1.0 + returns)
        close = np.maximum(close, 0.5)
        spread = np.abs(rng.normal(0.0, 0.01, size=n))
        open_ = close * (1.0 + rng.normal(0.0, 0.006, size=n))
        high = np.maximum(open_, close) * (1.0 + spread)
        low = np.minimum(open_, close) * (1.0 - spread)
        low = np.minimum(low, np.minimum(open_, close))
        volume = rng.lognormal(mean=np.log(base * 2_000_000 / max(base, 1.0)), sigma=0.5, size=n).astype(int)
        dividends = np.zeros(n)
        if div_yield > 0:
            # yılda bir temettü: her ~252 günde bir, fiyata oranla
            for k in range(60, n, 252):
                dividends[k] = round(close[k] * div_yield, 4)
        # adj_close: temettü düzeltmesi (geriye dönük, basitleştirilmiş)
        adj_factor = np.ones(n)
        for k in range(n):
            if dividends[k] > 0 and close[k - 1] > 0:
                adj_factor[:k] *= 1.0 - dividends[k] / close[k - 1]
        adj_close = close * adj_factor
        return pd.DataFrame(
            {
                "date": dates,
                "symbol": symbol,
                "open": np.round(open_, 4),
                "high": np.round(high, 4),
                "low": np.round(low, 4),
                "close": np.round(close, 4),
                "adj_close": np.round(adj_close, 4),
                "volume": volume,
                "dividends": dividends,
                "source": DEMO_SOURCE,
                "ingested_at": ingested,
            }
        )

    for symbol in symbols:
        drift = rng.normal(0.0004, 0.0006)
        vol = rng.uniform(0.010, 0.035)
        beta = rng.uniform(0.5, 1.4)
        base = float(rng.uniform(5, 400))
        div_yield = float(rng.choice([0.0, 0.0, 0.01, 0.02, 0.04, 0.06]))
        frames.append(build(symbol, drift, vol, beta, base, div_yield))

    bench_close = 8000.0 * np.cumprod(1.0 + market)
    bench = pd.DataFrame(
        {
            "date": dates,
            "symbol": benchmark_symbol,
            "open": np.round(bench_close * (1 + rng.normal(0, 0.003, n)), 2),
            "high": np.round(bench_close * 1.006, 2),
            "low": np.round(bench_close * 0.994, 2),
            "close": np.round(bench_close, 2),
            "adj_close": np.round(bench_close, 2),
            "volume": rng.integers(1_000_000_000, 5_000_000_000, n),
            "dividends": 0.0,
            "source": DEMO_SOURCE,
            "ingested_at": ingested,
        }
    )
    bench["high"] = np.maximum(bench["high"], np.maximum(bench["open"], bench["close"]))
    bench["low"] = np.minimum(bench["low"], np.minimum(bench["open"], bench["close"]))
    frames.append(bench)
    return pd.concat(frames, ignore_index=True).loc[:, RAW_PRICE_COLUMNS]
