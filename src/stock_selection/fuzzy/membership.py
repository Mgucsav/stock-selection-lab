"""Kriter değerlerinin ``[0, 1]`` üyelik derecelerine dönüştürülmesi.

* ``return``  → min-max benefit (negatif değer içerebildiği için).
* ``risk``    → min-max cost (düşük iyi).
* ``dividend``, ``liquidity`` → seminer uyumlu maksimuma bölme (benefit,
  negatif olmayan kriterler).

Min-max dönüşümleri ``src.day01_baseline.minmax_benefit/minmax_cost``
fonksiyonlarını yeniden kullanır. 1. Gün kodu sabit sütunda sessizce
``0.5`` döndürür; burada sabit sütun önce açık politika ile ele alınır ve
kalite uyarısı üretilir. NaN, sonsuz ve aralık dışı üyelikte fail-fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd

from src.day01_baseline import minmax_benefit, minmax_cost

from ..features.criteria import CRITERIA_ORDER


class ConstantColumnPolicy(StrEnum):
    """Bir kriter sütunundaki bütün değerler eşitse ne yapılacağı."""

    NEUTRAL = "neutral"  # herkese 0.5 (benefit/cost) — uyarı ile
    ZERO = "zero"        # herkese 0.0 — uyarı ile
    RAISE = "raise"      # hata fırlat


METHODS = {
    "return": "minmax_benefit",
    "dividend": "max_division_benefit",
    "liquidity": "max_division_benefit",
    "risk": "minmax_cost",
}


@dataclass
class MembershipResult:
    frame: pd.DataFrame
    methods: dict[str, str]
    constant_policy: str
    warnings: list[str] = field(default_factory=list)


def _is_constant(series: pd.Series) -> bool:
    values = series.to_numpy(dtype=float)
    return bool(np.isclose(values.max() - values.min(), 0.0))


def _apply_policy(series: pd.Series, column: str, policy: ConstantColumnPolicy, warnings: list[str]) -> pd.Series:
    if policy == ConstantColumnPolicy.RAISE:
        raise ValueError(f"'{column}' kriteri bütün hisselerde sabit; normalizasyon tanımsız.")
    value = 0.5 if policy == ConstantColumnPolicy.NEUTRAL else 0.0
    warnings.append(
        f"'{column}' kriteri bütün hisselerde sabit; '{policy.value}' politikasıyla {value} atandı."
    )
    return pd.Series(value, index=series.index, dtype=float)


def max_division_benefit(series: pd.Series) -> pd.Series:
    """``x / max(x)``; negatif olmayan benefit kriterleri için seminer yaklaşımı."""
    values = pd.to_numeric(series, errors="coerce")
    if (values < 0).any():
        raise ValueError("Maksimuma bölme yalnızca negatif olmayan kriterlerde kullanılabilir.")
    maximum = values.max()
    if not np.isfinite(maximum) or np.isclose(maximum, 0.0):
        raise ZeroDivisionError("Kriter sütununun maksimumu sıfır; maksimuma bölme tanımsız.")
    return values.div(maximum)


def validate_membership_frame(frame: pd.DataFrame) -> None:
    """NaN, sonsuz ve ``[0, 1]`` dışındaki üyeliklerde hata fırlatır."""
    values = frame.to_numpy(dtype=float)
    if np.isnan(values).any():
        raise ValueError("Üyelik matrisinde NaN bulunamaz.")
    if not np.isfinite(values).all():
        raise ValueError("Üyelik matrisinde sonsuz değer bulunamaz.")
    if (values < -1e-12).any() or (values > 1 + 1e-12).any():
        raise ValueError("Üyelik değerleri [0, 1] aralığında olmalıdır.")


def build_memberships(
    criteria: pd.DataFrame,
    constant_policy: ConstantColumnPolicy | str = ConstantColumnPolicy.NEUTRAL,
) -> MembershipResult:
    """Kriter tablosunu üyelik matrisine dönüştürür; girdiyi değiştirmez."""
    policy = ConstantColumnPolicy(constant_policy)
    missing = [c for c in CRITERIA_ORDER if c not in criteria.columns]
    if missing:
        raise ValueError(f"Kriter tablosunda sütun eksik: {', '.join(missing)}")
    if criteria.empty:
        raise ValueError("Kriter tablosu boş; üyelik üretilemez.")

    source = criteria.loc[:, CRITERIA_ORDER].apply(pd.to_numeric, errors="coerce")
    if source.isna().any().any() or not np.isfinite(source.to_numpy(dtype=float)).all():
        bad = source.columns[source.isna().any() | ~np.isfinite(source).all()].tolist()
        raise ValueError(f"Kriter değerleri NaN/sonsuz olamaz: {', '.join(map(str, bad))}")

    warnings: list[str] = []
    out = pd.DataFrame(index=source.index)
    for column in CRITERIA_ORDER:
        series = source[column].astype(float)
        method = METHODS[column]
        if method == "minmax_benefit":
            out[column] = _apply_policy(series, column, policy, warnings) if _is_constant(series) else minmax_benefit(series)
        elif method == "minmax_cost":
            out[column] = _apply_policy(series, column, policy, warnings) if _is_constant(series) else minmax_cost(series)
        else:  # max_division_benefit
            if (series < 0).any():
                raise ValueError(f"'{column}' negatif değer içeriyor; maksimuma bölme uygulanamaz.")
            if np.isclose(series.max(), 0.0):
                # Hiç temettü/hacim gözlenmemişse 0 doğru bilgidir; sessiz bölme yapılmaz.
                warnings.append(f"'{column}' kriteri bütün hisselerde 0; üyelik 0 atandı (maksimuma bölme atlandı).")
                out[column] = pd.Series(0.0, index=series.index, dtype=float)
            else:
                out[column] = max_division_benefit(series)
                if _is_constant(series):
                    warnings.append(f"'{column}' kriteri bütün hisselerde sabit; maksimuma bölme herkese 1.0 verdi.")
    out = out.loc[:, CRITERIA_ORDER].astype(float)
    validate_membership_frame(out)
    return MembershipResult(frame=out, methods=dict(METHODS), constant_policy=policy.value, warnings=warnings)
