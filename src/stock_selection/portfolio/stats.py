"""Portföy tarihsel istatistikleri (tahmin değil, geçmiş gözlem).

Yıllık oynaklık ve maksimum düşüş ``src.day01_baseline`` fonksiyonlarıyla
hesaplanır. Sabit ağırlıklı, günlük yeniden dengelenen bir portföy
varsayımı kullanılır; bu, model portföyün geçmişte nasıl davranacağına dair
basitleştirilmiş bir backtest özetidir.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS, max_drawdown, simple_returns


def historical_stats(
    adj_close_wide: pd.DataFrame,
    weights: dict[str, float],
    as_of: date | None = None,
    lookback_days: int | None = None,
) -> dict[str, object]:
    """Ağırlıklı portföyün tarihsel volatilite ve maksimum düşüşünü döndürür."""
    symbols = [s for s in weights if s in adj_close_wide.columns]
    if not symbols:
        return {"volatility": None, "max_drawdown": None, "backtest_start": None, "backtest_end": None, "observations": 0}
    prices = adj_close_wide.loc[:, symbols].copy()
    prices.index = pd.to_datetime(prices.index)
    if as_of is not None:
        prices = prices.loc[prices.index <= pd.Timestamp(as_of)]
    if lookback_days is not None and not prices.empty:
        prices = prices.loc[prices.index > prices.index.max() - pd.Timedelta(days=lookback_days)]
    prices = prices.dropna(how="any")
    prices = prices.loc[:, (prices > 0).all(axis=0)]
    if len(prices) < 3 or prices.shape[1] == 0:
        return {"volatility": None, "max_drawdown": None, "backtest_start": None, "backtest_end": None, "observations": int(len(prices))}

    w = np.asarray([weights[s] for s in prices.columns], dtype=float)
    w = w / w.sum()
    returns = simple_returns(prices)
    portfolio_returns = returns.to_numpy(dtype=float) @ w
    growth = pd.Series(np.cumprod(1.0 + portfolio_returns), index=returns.index)
    volatility = float(np.std(portfolio_returns, ddof=1) * np.sqrt(TRADING_DAYS)) if len(portfolio_returns) > 1 else None
    mdd = float(max_drawdown(growth))
    return {
        "volatility": volatility,
        "max_drawdown": mdd,
        "backtest_start": prices.index.min().date().isoformat(),
        "backtest_end": prices.index.max().date().isoformat(),
        "observations": int(len(prices)),
    }
