"""Üyelik (normalizasyon) testleri."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.stock_selection.fuzzy import ConstantColumnPolicy, build_memberships, max_division_benefit


def make_criteria() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "return": [0.002, -0.001, 0.0005],
            "dividend": [0.05, 0.0, 0.02],
            "liquidity": [1e9, 2e8, 5e8],
            "risk": [0.010, 0.020, 0.015],
        },
        index=["A", "B", "C"],
    )


def test_return_uses_minmax_benefit_and_handles_negative_values() -> None:
    result = build_memberships(make_criteria())
    assert result.frame["return"].tolist() == pytest.approx([1.0, 0.0, 0.5])
    assert result.methods["return"] == "minmax_benefit"


def test_risk_uses_minmax_cost() -> None:
    result = build_memberships(make_criteria())
    assert result.frame["risk"].tolist() == pytest.approx([1.0, 0.0, 0.5])
    assert result.methods["risk"] == "minmax_cost"


def test_dividend_and_liquidity_use_max_division() -> None:
    result = build_memberships(make_criteria())
    assert result.frame["dividend"].tolist() == pytest.approx([1.0, 0.0, 0.4])
    assert result.frame["liquidity"].tolist() == pytest.approx([1.0, 0.2, 0.5])


def test_all_negative_returns_still_normalize_to_unit_interval() -> None:
    criteria = make_criteria()
    criteria["return"] = [-0.01, -0.02, -0.03]
    result = build_memberships(criteria)
    assert result.frame["return"].tolist() == pytest.approx([1.0, 0.5, 0.0])


def test_constant_column_neutral_policy_warns() -> None:
    criteria = make_criteria()
    criteria["risk"] = 0.01
    result = build_memberships(criteria, constant_policy=ConstantColumnPolicy.NEUTRAL)
    assert result.frame["risk"].tolist() == [0.5, 0.5, 0.5]
    assert any("sabit" in w for w in result.warnings)


def test_constant_column_raise_policy() -> None:
    criteria = make_criteria()
    criteria["return"] = 0.001
    with pytest.raises(ValueError, match="sabit"):
        build_memberships(criteria, constant_policy="raise")


def test_zero_dividend_everywhere_gives_zero_membership_with_warning() -> None:
    criteria = make_criteria()
    criteria["dividend"] = 0.0
    result = build_memberships(criteria)
    assert result.frame["dividend"].tolist() == [0.0, 0.0, 0.0]
    assert any("dividend" in w for w in result.warnings)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nonfinite_criteria_fail_fast(bad: float) -> None:
    criteria = make_criteria()
    criteria.loc["A", "liquidity"] = bad
    with pytest.raises(ValueError):
        build_memberships(criteria)


def test_negative_value_in_max_division_column_is_rejected() -> None:
    with pytest.raises(ValueError):
        max_division_benefit(pd.Series([1.0, -1.0]))


def test_input_criteria_frame_is_not_mutated() -> None:
    criteria = make_criteria()
    original = criteria.copy(deep=True)
    build_memberships(criteria)
    assert_frame_equal(criteria, original)


def test_membership_values_are_within_unit_interval() -> None:
    frame = build_memberships(make_criteria()).frame
    assert ((frame >= 0) & (frame <= 1)).all().all()
