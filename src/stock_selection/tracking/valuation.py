"""Günlük portföy değerlemesi ve BIST 100 karşılaştırması.

```text
portfolio_value_t = cash + sum_i(quantity_i * price_i_t)
total_return_t    = portfolio_value_t / initial_capital - 1
```

Bir pozisyon henüz giriş tarihine ulaşmamışsa o gün için maliyeti nakit
gibi sayılır (henüz alınmamıştır). Fiyatı olmayan günlerde son bilinen
kapanış ileri taşınır ve bu durum uyarı olarak raporlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS, max_drawdown

from .snapshot import PositionSnapshot


@dataclass
class ValuationResult:
    series: pd.DataFrame  # date, value, total_return, benchmark_value, benchmark_norm, portfolio_norm
    metrics: dict[str, object]
    contributions: list[dict[str, object]]
    warnings: list[str] = field(default_factory=list)
    benchmark_available: bool = False


def _close_wide(clean: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    frame = clean.loc[clean["symbol"].isin(symbols), ["date", "symbol", "close"]].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["date"])
    wide = frame.pivot(index="date", columns="symbol", values="close").sort_index()
    wide.columns.name = None
    return wide


def valuation_series(
    positions: list[PositionSnapshot],
    cash: float,
    initial_capital: float,
    clean: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    as_of: date | None = None,
) -> ValuationResult:
    """Aktif pozisyonlardan günlük değer serisi ve metrikler üretir."""
    warnings: list[str] = []
    active = [p for p in positions if not p.is_pending]
    if not active:
        return ValuationResult(pd.DataFrame(), {"status": "pending"}, [], ["Bütün pozisyonlar beklemede; değerleme yapılamadı."], False)

    symbols = [p.symbol for p in active]
    wide = _close_wide(clean, symbols)
    start = min(p.entry_date for p in active if p.entry_date)
    wide = wide.loc[wide.index >= pd.Timestamp(start)]
    if as_of is not None:
        wide = wide.loc[wide.index <= pd.Timestamp(as_of)]
    if wide.empty:
        return ValuationResult(pd.DataFrame(), {"status": "no_prices"}, [], ["Giriş tarihinden sonra fiyat verisi yok."], False)

    missing_days = int(wide.isna().sum().sum())
    if missing_days:
        warnings.append(f"{missing_days} sembol-gün için fiyat yok; son kapanış ileri taşındı.")
    filled = wide.ffill()

    value = pd.Series(float(cash), index=filled.index)
    for p in active:
        if p.symbol not in filled.columns:
            warnings.append(f"{p.symbol}: fiyat serisi yok; maliyet üzerinden sabit tutuldu.")
            value += p.cost
            continue
        held = filled.index >= pd.Timestamp(p.entry_date)
        price = filled[p.symbol].fillna(p.entry_price)
        value += np.where(held, p.quantity * price, p.cost)

    series = pd.DataFrame({"value": value})
    series["total_return"] = series["value"] / initial_capital - 1.0
    series["portfolio_norm"] = 100.0 * series["value"] / series["value"].iloc[0]
    series["daily_change"] = series["value"].diff().fillna(0.0)
    series["daily_return"] = series["value"].pct_change().fillna(0.0)

    benchmark_available = False
    if benchmark is not None and not benchmark.empty:
        bench = benchmark.copy()
        bench["date"] = pd.to_datetime(bench["date"])
        bench = bench.set_index("date")["close"].sort_index()
        bench = bench.reindex(series.index).ffill()
        if bench.notna().sum() >= 2 and bench.iloc[0] > 0:
            series["benchmark_value"] = bench
            series["benchmark_norm"] = 100.0 * bench / bench.iloc[0]
            benchmark_available = True
        else:
            warnings.append("Benchmark serisi karşılaştırma dönemi için yetersiz; BIST 100 grafiği gösterilemiyor.")
    else:
        warnings.append("Benchmark (XU100.IS) verisi bulunamadı; BIST 100 karşılaştırması yapılamıyor.")
    if not benchmark_available:
        series["benchmark_value"] = np.nan
        series["benchmark_norm"] = np.nan

    last_value = float(series["value"].iloc[-1])
    daily_returns = series["daily_return"].to_numpy(dtype=float)
    volatility = float(np.std(daily_returns[1:], ddof=1) * np.sqrt(TRADING_DAYS)) if len(daily_returns) > 2 else None
    total_return = last_value / initial_capital - 1.0
    benchmark_return = (
        float(series["benchmark_value"].iloc[-1] / series["benchmark_value"].iloc[0] - 1.0)
        if benchmark_available else None
    )

    contributions: list[dict[str, object]] = []
    for p in active:
        last_price = float(filled[p.symbol].iloc[-1]) if p.symbol in filled.columns else p.entry_price
        pnl = p.quantity * (last_price - p.entry_price)
        contributions.append(
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "last_price": last_price,
                "market_value": p.quantity * last_price,
                "pnl": pnl,
                "return_pct": (last_price / p.entry_price - 1.0) if p.entry_price else 0.0,
                "contribution_pct": pnl / initial_capital,
                "current_weight": (p.quantity * last_price) / last_value if last_value else 0.0,
                "target_weight": p.target_weight,
            }
        )

    metrics = {
        "status": "active",
        "as_of": series.index[-1].date().isoformat(),
        "start_date": series.index[0].date().isoformat(),
        "initial_capital": initial_capital,
        "current_value": last_value,
        "daily_change": float(series["daily_change"].iloc[-1]),
        "daily_return": float(series["daily_return"].iloc[-1]),
        "total_pnl": last_value - initial_capital,
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "relative_return": (total_return - benchmark_return) if benchmark_return is not None else None,
        "volatility": volatility,
        "max_drawdown": float(max_drawdown(series["value"])),
        "cash": float(cash),
        "cash_ratio": float(cash) / last_value if last_value else None,
        "observations": int(len(series)),
    }
    series = series.reset_index().rename(columns={"index": "date"})
    return ValuationResult(series, metrics, contributions, warnings, benchmark_available)
