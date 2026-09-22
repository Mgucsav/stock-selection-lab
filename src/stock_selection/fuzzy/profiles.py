"""Yatırımcı profilleri (parametre önem ağırlıkları).

Üç profil yalnızca başlangıç/demo parametresidir; akademik olarak
doğrulanmış evrensel yatırımcı profilleri değildir. ``Dengeli`` profil
seminerdeki ağırlıkları birebir kullanır. Kullanıcı ağırlıkları ``[0, 1]``
aralığında değiştirebilir; ``config/profiles.json`` varsa varsayılanlar
oradan okunur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from .fpfs import CRITERIA_COLUMNS


@dataclass(frozen=True)
class InvestorProfile:
    id: str
    label: str
    description: str
    weights: dict[str, float]
    portfolio_size: int
    max_weight: float
    weighting_scheme: str
    is_default: bool = True
    disclaimer: str = field(
        default="Başlangıç/demo parametresi; akademik olarak doğrulanmış evrensel bir profil değildir."
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "weights": dict(self.weights),
            "portfolio_size": self.portfolio_size,
            "max_weight": self.max_weight,
            "weighting_scheme": self.weighting_scheme,
            "is_default": self.is_default,
            "disclaimer": self.disclaimer,
        }


DEFAULT_PROFILES: dict[str, InvestorProfile] = {
    "conservative": InvestorProfile(
        id="conservative",
        label="Muhafazakâr",
        description="Aşağı yönlü riske ve likiditeye en yüksek önem; ilk 15 hisse, ters-risk ağırlık, tek hisse en çok %10.",
        weights={"return": 0.55, "dividend": 0.75, "liquidity": 0.80, "risk": 1.00},
        portfolio_size=15,
        max_weight=0.10,
        weighting_scheme="inverse_downside_risk",
    ),
    "balanced": InvestorProfile(
        id="balanced",
        label="Dengeli",
        description="Seminerdeki ağırlıklar; ilk 10 hisse, %50 fpfs skor payı + %50 ters-risk payı, tek hisse en çok %15.",
        weights={"return": 0.80, "dividend": 0.60, "liquidity": 0.60, "risk": 0.80},
        portfolio_size=10,
        max_weight=0.15,
        weighting_scheme="half_score_half_inverse_risk",
    ),
    "aggressive": InvestorProfile(
        id="aggressive",
        label="Agresif",
        description="Getiriye tam önem; ilk 7 hisse, fpfs skoruyla orantılı ağırlık, tek hisse en çok %20.",
        weights={"return": 1.00, "dividend": 0.35, "liquidity": 0.55, "risk": 0.55},
        portfolio_size=7,
        max_weight=0.20,
        weighting_scheme="score_proportional",
    ),
}


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """Ağırlıkların dört kriteri kapsadığını ve ``[0, 1]`` içinde olduğunu doğrular."""
    missing = [c for c in CRITERIA_COLUMNS if c not in weights]
    if missing:
        raise ValueError(f"Ağırlık eksik: {', '.join(missing)}")
    clean: dict[str, float] = {}
    for column in CRITERIA_COLUMNS:
        value = float(weights[column])
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"'{column}' ağırlığı [0, 1] aralığında olmalıdır.")
        clean[column] = value
    return clean


def load_profiles(path: str | Path | None = None) -> dict[str, InvestorProfile]:
    """``profiles.json`` varsa varsayılanları onunla ezer; yoksa varsayılanı döndürür."""
    profiles = dict(DEFAULT_PROFILES)
    if path is None or not Path(path).exists():
        return profiles
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for item in payload.get("profiles", []):
        base = profiles.get(item["id"])
        weights = validate_weights(item.get("weights", base.weights if base else {}))
        profiles[item["id"]] = InvestorProfile(
            id=item["id"],
            label=item.get("label", base.label if base else item["id"]),
            description=item.get("description", base.description if base else ""),
            weights=weights,
            portfolio_size=int(item.get("portfolio_size", base.portfolio_size if base else 10)),
            max_weight=float(item.get("max_weight", base.max_weight if base else 0.15)),
            weighting_scheme=item.get("weighting_scheme", base.weighting_scheme if base else "score_proportional"),
            is_default=bool(base and base.weights == weights),
        )
    return profiles
