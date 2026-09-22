"""Portföy ağırlıklandırma, tavan ve dağıtım testleri."""

import numpy as np
import pandas as pd
import pytest

from src.stock_selection.fuzzy import DEFAULT_PROFILES
from src.stock_selection.portfolio import apply_cap_and_redistribute, build_candidate


def test_cap_redistributes_and_sums_to_one() -> None:
    weights = {"A": 0.6, "B": 0.2, "C": 0.1, "D": 0.1}
    capped, warnings = apply_cap_and_redistribute(weights, 0.3)
    assert sum(capped.values()) == pytest.approx(1.0)
    assert max(capped.values()) <= 0.3 + 1e-9
    assert capped["A"] == pytest.approx(0.3)
    assert warnings == []


def test_cap_impossible_falls_back_with_warning() -> None:
    capped, warnings = apply_cap_and_redistribute({"A": 0.5, "B": 0.5}, 0.3)
    assert sum(capped.values()) == pytest.approx(1.0)
    assert warnings and "tavan" in warnings[0]


def test_negative_weights_rejected() -> None:
    with pytest.raises(ValueError):
        apply_cap_and_redistribute({"A": -0.1, "B": 1.1}, 0.5)


def _scores_and_criteria(n: int = 20):
    symbols = [f"S{i:02d}.IS" for i in range(n)]
    rng = np.random.default_rng(1)
    cce10 = np.sort(rng.uniform(0.2, 0.8, n))[::-1]
    scores = pd.DataFrame({"cce10": cce10, "rank": np.arange(1, n + 1)}, index=symbols)
    criteria = pd.DataFrame(
        {
            "return": rng.normal(0.001, 0.001, n),
            "dividend": rng.uniform(0, 0.05, n),
            "liquidity": rng.uniform(1e7, 1e9, n),
            "risk": rng.uniform(0.005, 0.02, n),
        },
        index=symbols,
    )
    dates = pd.bdate_range("2025-01-01", periods=300)
    prices = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, (300, n)), axis=0), index=dates, columns=symbols)
    return scores, criteria, prices


@pytest.mark.parametrize("profile_id,size,cap", [("conservative", 15, 0.10), ("balanced", 10, 0.15), ("aggressive", 7, 0.20)])
def test_model_portfolios_respect_size_and_cap(profile_id: str, size: int, cap: float) -> None:
    scores, criteria, prices = _scores_and_criteria()
    candidate = build_candidate(DEFAULT_PROFILES[profile_id], scores, criteria, prices)
    assert candidate.size == size
    assert sum(candidate.weights.values()) == pytest.approx(1.0)
    assert max(candidate.weights.values()) <= cap + 1e-9
    assert candidate.stats["volatility"] is not None
    assert candidate.stats["max_drawdown"] <= 0
    assert [h["symbol"] for h in candidate.holdings] == scores.index[:size].tolist()


def test_inverse_risk_scheme_prefers_lower_risk() -> None:
    scores, criteria, prices = _scores_and_criteria()
    candidate = build_candidate(DEFAULT_PROFILES["conservative"], scores, criteria, prices)
    chosen = list(candidate.weights)
    lowest = criteria.loc[chosen, "risk"].idxmin()
    highest = criteria.loc[chosen, "risk"].idxmax()
    assert candidate.weights[lowest] >= candidate.weights[highest]


def test_symbols_without_prices_are_dropped_with_warning() -> None:
    scores, criteria, prices = _scores_and_criteria()
    prices = prices.drop(columns=[scores.index[0]])
    candidate = build_candidate(DEFAULT_PROFILES["aggressive"], scores, criteria, prices)
    assert scores.index[0] not in candidate.weights
    assert any("yeterli veri" in w for w in candidate.warnings)


def test_missing_sector_yields_warning_not_fake_limit() -> None:
    scores, criteria, prices = _scores_and_criteria()
    sector_map = {s: ("Bankacılık" if i % 2 else None) for i, s in enumerate(scores.index)}
    candidate = build_candidate(DEFAULT_PROFILES["balanced"], scores, criteria, prices, sector_map=sector_map)
    assert candidate.sector_exposure is not None
    assert "Bilinmiyor" in candidate.sector_exposure
    assert any("Sektör bilgisi eksik" in w for w in candidate.warnings)
