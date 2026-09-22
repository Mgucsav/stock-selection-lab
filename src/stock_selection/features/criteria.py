"""Seminer modelinin dört kriteri: getiri, temettü, likidite, aşağı yönlü risk.

Formüller (``r_it`` günlük basit getiri):

```text
mean_return_i   = mean(r_it)                                  (dönemsel)
downside_risk_i = mean(max(0, mean_return_i - r_it))          (yarı-mutlak sapma, maliyet)
dividend_yield  = annual_cash_dividend / reference_price
liquidity_proxy = median(close * volume)                      (TL işlem hacmi proxy'si)
```

Getiriler ``adj_close`` üzerinden hesaplanır; böylece bedelsiz/bedelli
sermaye artırımı ve temettü kesintileri yapay getiri üretmez. Likidite
proxy'si gerçek devir hızı (turnover) değildir; ücretsiz veriyle dolaşımdaki
pay sayısı güvenilir biçimde bulunamadığı için TL hacim medyanı kullanılır.

Günlük getiriler ``src.day01_baseline.simple_returns`` ile üretilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS, simple_returns

CRITERIA_ORDER = ["return", "dividend", "liquidity", "risk"]
MIN_OBSERVATIONS = 120


def mean_return(returns: pd.Series) -> float:
    """Dönemsel (günlük) ortalama getiri."""
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        raise ValueError("Getiri serisi boş.")
    return float(values.mean())


def downside_risk(returns: pd.Series) -> float:
    """Yarı-mutlak sapma: ``mean(max(0, mean_return - r_t))``."""
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        raise ValueError("Getiri serisi boş.")
    mu = values.mean()
    return float(np.maximum(0.0, mu - values).mean())


def liquidity_proxy(close: pd.Series, volume: pd.Series) -> float:
    """TL hacim medyanı; gerçek turnover değildir."""
    tl_volume = pd.to_numeric(close, errors="coerce") * pd.to_numeric(volume, errors="coerce")
    tl_volume = tl_volume.dropna()
    if tl_volume.empty:
        raise ValueError("Hacim serisi boş.")
    return float(tl_volume.median())


@dataclass
class CriteriaResult:
    """Kriter tablosu, dışlanan semboller ve uyarılar."""

    table: pd.DataFrame
    excluded: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    as_of: date | None = None
    window_start: date | None = None
    observations: int = 0


def compute_criteria(
    clean: pd.DataFrame,
    as_of: date | None = None,
    lookback_days: int | None = None,
    dividend_window_days: int = 365,
    min_observations: int = MIN_OBSERVATIONS,
) -> CriteriaResult:
    """Temiz uzun tablodan sembol bazında kriterleri hesaplar.

    Yalnızca ``as_of`` tarihine kadar olan veri kullanılır (look-ahead yok).
    """
    if clean is None or clean.empty:
        return CriteriaResult(pd.DataFrame(columns=CRITERIA_ORDER), warnings=["Temiz veri yok."])

    frame = clean.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if as_of is not None:
        frame = frame.loc[frame["date"] <= pd.Timestamp(as_of)]
    if frame.empty:
        return CriteriaResult(pd.DataFrame(columns=CRITERIA_ORDER), warnings=["Karar tarihine kadar veri yok."])

    effective_as_of = frame["date"].max()
    if lookback_days is not None:
        frame = frame.loc[frame["date"] > effective_as_of - pd.Timedelta(days=lookback_days)]
    window_start = frame["date"].min()

    rows: dict[str, dict[str, object]] = {}
    excluded: dict[str, str] = {}
    warnings: list[str] = []
    for symbol, sub in frame.groupby("symbol", sort=True):
        sub = sub.sort_values("date")
        price = pd.to_numeric(sub["adj_close"], errors="coerce")
        price = price.where(price > 0)
        if price.dropna().shape[0] < min_observations:
            excluded[str(symbol)] = f"insufficient_data ({price.dropna().shape[0]} < {min_observations})"
            continue
        price_frame = price.dropna().to_frame(str(symbol))
        returns = simple_returns(price_frame)[str(symbol)]
        mu = mean_return(returns)
        risk = downside_risk(returns)
        liquidity = liquidity_proxy(sub["close"], sub["volume"])

        # Temettü: pencere içi nakit temettü / referans fiyat (son kapanış)
        div_series = pd.to_numeric(sub["dividends"], errors="coerce")
        reference_price = float(pd.to_numeric(sub["close"], errors="coerce").iloc[-1])
        if div_series.notna().sum() == 0:
            dividend_yield, dividend_status = 0.0, "unavailable"
        else:
            div_window = sub.loc[sub["date"] > effective_as_of - pd.Timedelta(days=dividend_window_days)]
            cash = float(pd.to_numeric(div_window["dividends"], errors="coerce").fillna(0.0).sum())
            if cash > 0 and reference_price > 0:
                dividend_yield, dividend_status = cash / reference_price, "observed"
            else:
                dividend_yield, dividend_status = 0.0, "no_dividend_observed"

        rows[str(symbol)] = {
            "return": mu,
            "dividend": dividend_yield,
            "liquidity": liquidity,
            "risk": risk,
            "annualized_return": mu * TRADING_DAYS,
            "dividend_status": dividend_status,
            "observations": int(len(returns)),
            "last_close": reference_price,
        }

    table = pd.DataFrame.from_dict(rows, orient="index")
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
        as_of=effective_as_of.date(),
        window_start=window_start.date(),
        observations=int(table["observations"].max()) if not table.empty else 0,
    )
