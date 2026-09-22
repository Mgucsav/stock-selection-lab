"""fpfs matrisi, CCE10/FSS/DRF/DMF operatörleri ve seminer örneği testleri."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.stock_selection.fuzzy import (
    CRITERIA_COLUMNS,
    build_fpfs_matrix,
    cce10_scores,
    evaluate_fpfs,
    fss_scores,
    validate_column_contract,
    weighted_dmf,
    weighted_drf,
)
from tests.fixtures.seminar_example import (
    EXPECTED_FPFS_ORDER,
    EXPECTED_FPFS_SCORES,
    EXPECTED_FSS_ORDER,
    SEMINAR_MEMBERSHIPS,
    SEMINAR_WEIGHTS,
)


def test_matrix_zero_row_holds_parameter_weights() -> None:
    matrix = build_fpfs_matrix(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    assert matrix.index[0] == "mu"
    assert matrix.loc["mu"].tolist() == [0.8, 0.6, 0.6, 0.8]
    assert list(matrix.columns) == ["return", "dividend", "liquidity", "risk"]


def test_cce10_formula_by_hand() -> None:
    memberships = pd.DataFrame(
        {"return": [1.0], "dividend": [0.5], "liquidity": [0.0], "risk": [0.25]}, index=["X"]
    )
    weights = {"return": 0.5, "dividend": 1.0, "liquidity": 1.0, "risk": 0.8}
    matrix = build_fpfs_matrix(memberships, weights)
    expected = (0.5 * 1.0 + 1.0 * 0.5 + 1.0 * 0.0 + 0.8 * 0.25) / 4
    assert cce10_scores(matrix)["X"] == pytest.approx(expected)


def test_fss_baseline_ignores_weights() -> None:
    matrix = build_fpfs_matrix(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    expected = SEMINAR_MEMBERSHIPS.sum(axis=1) / 4
    assert fss_scores(matrix).to_numpy() == pytest.approx(expected.to_numpy())


def test_weighted_drf_is_n_times_cce10() -> None:
    matrix = build_fpfs_matrix(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    assert weighted_drf(matrix).to_numpy() == pytest.approx(4 * cce10_scores(matrix).to_numpy())


def test_weighted_dmf_matches_pairwise_definition() -> None:
    matrix = build_fpfs_matrix(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    mu = np.array([SEMINAR_WEIGHTS[c] for c in CRITERIA_COLUMNS])
    values = SEMINAR_MEMBERSHIPS.to_numpy()
    expected = []
    for i in range(len(values)):
        total = 0.0
        for k in range(len(values)):
            total += float(np.sum(mu * (values[i] - values[k])))
        expected.append(total)
    assert weighted_dmf(matrix).to_numpy() == pytest.approx(np.array(expected))
    assert weighted_dmf(matrix).sum() == pytest.approx(0.0)


def test_seminar_example_reproduces_fss_and_fpfs_orders() -> None:
    result = evaluate_fpfs(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    fpfs_order = result.scores.sort_values("cce10", ascending=False).index.tolist()
    fss_order = result.scores.sort_values("fss", ascending=False).index.tolist()
    assert fpfs_order == EXPECTED_FPFS_ORDER
    assert fss_order == EXPECTED_FSS_ORDER


def test_seminar_example_reproduces_scores() -> None:
    result = evaluate_fpfs(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    for stock, expected in EXPECTED_FPFS_SCORES.items():
        assert result.scores.loc[stock, "cce10"] == pytest.approx(expected, abs=1e-3)


def test_rank_delta_between_fss_and_fpfs() -> None:
    result = evaluate_fpfs(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    assert result.scores.loc["C7", "rank_delta_vs_fss"] == 1
    assert result.scores.loc["C4", "rank_delta_vs_fss"] == -1


def test_column_contract_is_enforced() -> None:
    with pytest.raises(ValueError, match="sütun sırası"):
        validate_column_contract(["return", "risk", "dividend", "liquidity"])
    shuffled = SEMINAR_MEMBERSHIPS.loc[:, ["risk", "return", "dividend", "liquidity"]]
    with pytest.raises(ValueError, match="sütun sırası"):
        build_fpfs_matrix(shuffled, SEMINAR_WEIGHTS)


def test_input_memberships_are_not_mutated() -> None:
    original = SEMINAR_MEMBERSHIPS.copy(deep=True)
    evaluate_fpfs(SEMINAR_MEMBERSHIPS, SEMINAR_WEIGHTS)
    assert_frame_equal(SEMINAR_MEMBERSHIPS, original)


@pytest.mark.parametrize("bad", [np.nan, np.inf, 1.5, -0.1])
def test_invalid_membership_values_fail_fast(bad: float) -> None:
    memberships = SEMINAR_MEMBERSHIPS.copy()
    memberships.loc["C29", "return"] = bad
    with pytest.raises(ValueError):
        build_fpfs_matrix(memberships, SEMINAR_WEIGHTS)


@pytest.mark.parametrize(
    "weights",
    [
        {"return": 1.2, "dividend": 0.5, "liquidity": 0.5, "risk": 0.5},
        {"return": -0.1, "dividend": 0.5, "liquidity": 0.5, "risk": 0.5},
        {"return": 0.5, "dividend": 0.5, "liquidity": 0.5},
    ],
)
def test_invalid_weights_are_rejected(weights: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        build_fpfs_matrix(SEMINAR_MEMBERSHIPS, weights)
