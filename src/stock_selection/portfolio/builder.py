"""Şeffaf model portföy oluşturucu.

fpfs algoritması hisseleri **seçer ve sıralar**; bu modül ise seçilen
hisselere **ağırlık verir**. İki katman kasıtlı olarak ayrıdır: ağırlık
şeması değişse de fpfs sıralaması değişmez.

Şemalar:

```text
inverse_downside_risk        w_i ∝ 1 / risk_i
half_score_half_inverse_risk w_i = 0.5 * score_share_i + 0.5 * inv_risk_share_i
score_proportional           w_i ∝ cce10_i
```

Ardından tek hisse tavanı uygulanır, fazla ağırlık tavana ulaşmamış
hisselere orantılı dağıtılır ve toplamın ``1.0`` olması garanti edilir.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..fuzzy.profiles import InvestorProfile
from .stats import historical_stats

WEIGHT_TOLERANCE = 1e-9
RISK_EPSILON = 1e-8


@dataclass
class PortfolioCandidate:
    profile_id: str
    profile_label: str
    weights: dict[str, float]
    holdings: list[dict[str, object]]
    average_score: float
    stats: dict[str, object]
    sector_exposure: dict[str, float] | None
    warnings: list[str] = field(default_factory=list)
    weighting_scheme: str = ""
    max_weight: float = 0.0
    profile_weights: dict[str, float] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.weights)


def apply_cap_and_redistribute(weights: Mapping[str, float], max_weight: float) -> tuple[dict[str, float], list[str]]:
    """Tavanı uygular, fazlayı yeniden dağıtır ve toplamı 1.0'a normalize eder."""
    if not weights:
        raise ValueError("Boş ağırlık kümesine tavan uygulanamaz.")
    names = list(weights)
    w = np.asarray([float(weights[n]) for n in names], dtype=float)
    if (w < 0).any() or not np.isfinite(w).all():
        raise ValueError("Ağırlıklar negatif veya sonlu olmayan değer içeremez.")
    if w.sum() <= 0:
        w = np.ones_like(w)
    w = w / w.sum()
    warnings: list[str] = []
    if len(w) * max_weight < 1.0 - WEIGHT_TOLERANCE:
        warnings.append(
            f"{len(w)} hisse ile %{max_weight*100:.0f} tavanı sağlanamaz; eşit ağırlık kullanıldı ve tavan aşıldı."
        )
        w = np.full(len(w), 1.0 / len(w))
        return {n: float(v) for n, v in zip(names, w)}, warnings

    capped = np.zeros(len(w), dtype=bool)
    for _ in range(len(w) + 1):
        over = (w > max_weight + WEIGHT_TOLERANCE) & ~capped
        if not over.any():
            break
        excess = float((w[over] - max_weight).sum())
        w[over] = max_weight
        capped |= over
        free = ~capped
        if free.any() and w[free].sum() > 0:
            w[free] += excess * (w[free] / w[free].sum())
        elif free.any():
            w[free] += excess / free.sum()
    w = w / w.sum()
    if not np.isclose(w.sum(), 1.0, atol=1e-9):
        raise ValueError("Ağırlık toplamı 1.0 olmalıdır.")
    return {n: float(v) for n, v in zip(names, w)}, warnings


def _raw_weights(scheme: str, scores: pd.Series, risks: pd.Series) -> pd.Series:
    inv_risk = 1.0 / (risks.clip(lower=0.0) + RISK_EPSILON)
    inv_share = inv_risk / inv_risk.sum()
    score_share = scores / scores.sum() if scores.sum() > 0 else pd.Series(1.0 / len(scores), index=scores.index)
    if scheme == "inverse_downside_risk":
        return inv_share
    if scheme == "half_score_half_inverse_risk":
        return 0.5 * score_share + 0.5 * inv_share
    if scheme == "score_proportional":
        return score_share
    raise ValueError(f"Bilinmeyen ağırlık şeması: {scheme}")


def build_candidate(
    profile: InvestorProfile,
    scores: pd.DataFrame,
    criteria: pd.DataFrame,
    adj_close_wide: pd.DataFrame,
    sector_map: Mapping[str, str | None] | None = None,
    name_map: Mapping[str, str] | None = None,
    as_of=None,
    lookback_days: int | None = None,
    with_stats: bool = True,
) -> PortfolioCandidate:
    """Profil sıralamasındaki ilk N uygun hisseden model portföy üretir.

    ``with_stats=False`` tarihsel volatilite/düşüş hesabını atlar; yürüyen backtest
    her karar tarihinde yalnızca ağırlıklara ihtiyaç duyar.
    """
    warnings: list[str] = []
    ranked = scores.sort_values(["rank", "cce10"], ascending=[True, False])
    eligible = [s for s in ranked.index if s in criteria.index and s in adj_close_wide.columns]
    dropped = [s for s in ranked.index if s not in eligible]
    if dropped:
        warnings.append(f"{len(dropped)} hisse yeterli veri olmadığı için portföy adayı dışında bırakıldı.")
    chosen = eligible[: profile.portfolio_size]
    if not chosen:
        raise ValueError("Portföy için uygun hisse bulunamadı.")
    if len(chosen) < profile.portfolio_size:
        warnings.append(f"Yalnızca {len(chosen)} uygun hisse bulundu (hedef {profile.portfolio_size}).")

    score_series = ranked.loc[chosen, "cce10"].astype(float)
    risk_series = criteria.loc[chosen, "risk"].astype(float)
    raw = _raw_weights(profile.weighting_scheme, score_series, risk_series)
    weights, cap_warnings = apply_cap_and_redistribute(raw.to_dict(), profile.max_weight)
    warnings.extend(cap_warnings)

    holdings = [
        {
            "symbol": s,
            "name": (name_map or {}).get(s, s),
            "weight": weights[s],
            "cce10": float(score_series[s]),
            "rank": int(ranked.loc[s, "rank"]),
            "downside_risk": float(risk_series[s]),
            "sector": (sector_map or {}).get(s),
        }
        for s in chosen
    ]

    sector_exposure: dict[str, float] | None = None
    if sector_map is not None:
        missing = [s for s in chosen if not sector_map.get(s)]
        if missing:
            warnings.append(f"Sektör bilgisi eksik: {', '.join(missing)}; sektör yoğunlaşması kısmi gösterilir.")
        exposure: dict[str, float] = {}
        for s in chosen:
            key = sector_map.get(s) or "Bilinmiyor"
            exposure[key] = exposure.get(key, 0.0) + weights[s]
        sector_exposure = {k: round(v, 6) for k, v in sorted(exposure.items(), key=lambda kv: -kv[1])}

    stats = (
        historical_stats(adj_close_wide, weights, as_of=as_of, lookback_days=lookback_days)
        if with_stats else {}
    )
    return PortfolioCandidate(
        profile_id=profile.id,
        profile_label=profile.label,
        weights=weights,
        holdings=holdings,
        average_score=float(score_series.mean()),
        stats=stats,
        sector_exposure=sector_exposure,
        warnings=warnings,
        weighting_scheme=profile.weighting_scheme,
        max_weight=profile.max_weight,
        profile_weights=dict(profile.weights),
    )


def build_model_portfolios(
    profiles: Mapping[str, InvestorProfile],
    scores_by_profile: Mapping[str, pd.DataFrame],
    criteria: pd.DataFrame,
    adj_close_wide: pd.DataFrame,
    sector_map: Mapping[str, str | None] | None = None,
    name_map: Mapping[str, str] | None = None,
    as_of=None,
    lookback_days: int | None = None,
) -> list[PortfolioCandidate]:
    """Her profil için bir aday portföy üretir."""
    return [
        build_candidate(
            profiles[pid], scores_by_profile[pid], criteria, adj_close_wide,
            sector_map=sector_map, name_map=name_map, as_of=as_of, lookback_days=lookback_days,
        )
        for pid in profiles
        if pid in scores_by_profile
    ]
