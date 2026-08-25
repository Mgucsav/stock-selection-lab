"""1. Gün getiri, risk ve sıralama testleri."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from src.day01_baseline import (
    DEFAULT_WEIGHTS,
    TRADING_DAYS,
    annualized_downside_volatility,
    build_features,
    max_drawdown,
    minmax_benefit,
    minmax_cost,
    prices,
    score_stocks,
    simple_returns,
    validate_weights,
)


def test_simple_returns_calculation() -> None:
    frame = pd.DataFrame({"X": [100.0, 110.0, 99.0]})
    result = simple_returns(frame)
    assert result["X"].to_numpy() == pytest.approx([0.10, -0.10])


def test_missing_prices_are_rejected() -> None:
    frame = pd.DataFrame({"X": [100.0, np.nan]})
    with pytest.raises(ValueError, match="eksik"):
        simple_returns(frame)


@pytest.mark.parametrize("invalid_price", [0.0, -1.0])
def test_zero_and_negative_prices_are_rejected(invalid_price: float) -> None:
    with pytest.raises(ValueError):
        simple_returns(pd.DataFrame({"X": [100.0, invalid_price]}))


def test_infinite_prices_are_rejected() -> None:
    with pytest.raises(ValueError, match="sonlu"):
        simple_returns(pd.DataFrame({"X": [100.0, np.inf]}))


def test_nonnumeric_prices_are_rejected() -> None:
    with pytest.raises(ValueError, match="sayısal"):
        simple_returns(pd.DataFrame({"X": [100.0, "hatalı"]}))


def test_input_frame_is_not_mutated() -> None:
    original = prices.copy(deep=True)
    simple_returns(prices)
    assert_frame_equal(prices, original)


def test_max_drawdown_calculation() -> None:
    series = pd.Series([100.0, 120.0, 90.0, 110.0])
    assert max_drawdown(series) == pytest.approx(-0.25)


def test_downside_volatility_with_known_negative_returns() -> None:
    returns = pd.Series([-0.01, 0.02, -0.03])
    expected = 0.01 * np.sqrt(TRADING_DAYS)
    assert annualized_downside_volatility(returns) == pytest.approx(expected)


def test_downside_volatility_is_zero_without_negative_return() -> None:
    assert annualized_downside_volatility(pd.Series([0.0, 0.01])) == 0.0


def test_feature_columns_are_exact() -> None:
    assert list(build_features(prices).columns) == [
        "return",
        "volatility",
        "downside_volatility",
        "max_drawdown_abs",
    ]


def test_feature_values_match_expected_values() -> None:
    result = build_features(prices)
    expected = {
        "ALFA": [0.09, 0.2979, 0.0720, 0.0192],
        "BETA": [0.10, 0.3200, 0.0062, 0.0100],
        "GAMA": [0.04, 0.0193, 0.0000, 0.0000],
    }
    for symbol, values in expected.items():
        assert result.loc[symbol].to_numpy() == pytest.approx(values, abs=5e-4)


def test_benefit_normalization() -> None:
    result = minmax_benefit(pd.Series([2.0, 4.0, 6.0]))
    assert result.to_numpy() == pytest.approx([0.0, 0.5, 1.0])


def test_cost_normalization() -> None:
    result = minmax_cost(pd.Series([2.0, 4.0, 6.0]))
    assert result.to_numpy() == pytest.approx([1.0, 0.5, 0.0])


@pytest.mark.parametrize("normalizer", [minmax_benefit, minmax_cost])
def test_constant_normalization_returns_half(normalizer) -> None:
    series = pd.Series([3.0, 3.0], index=["A", "B"])
    assert_series_equal(normalizer(series), pd.Series([0.5, 0.5], index=series.index))


def test_negative_weights_are_rejected() -> None:
    weights = {"return_score": 0.5, "volatility_score": -0.1, "drawdown_score": 0.6}
    with pytest.raises(ValueError, match="negatif"):
        validate_weights(weights, set(weights))


@pytest.mark.parametrize(
    "weights",
    [
        {"return_score": 0.5, "volatility_score": 0.5},
        {
            "return_score": 0.4,
            "volatility_score": 0.3,
            "drawdown_score": 0.2,
            "extra": 0.1,
        },
    ],
)
def test_missing_or_extra_weight_keys_are_rejected(weights: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="anahtarları"):
        validate_weights(weights, {"return_score", "volatility_score", "drawdown_score"})


@pytest.mark.parametrize("invalid_weight", [np.nan, np.inf])
def test_nonfinite_weights_are_rejected(invalid_weight: float) -> None:
    weights = {
        "return_score": invalid_weight,
        "volatility_score": 0.35,
        "drawdown_score": 0.25,
    }
    with pytest.raises(ValueError, match="sonlu"):
        validate_weights(weights, set(weights))


def test_weight_sum_other_than_one_is_rejected() -> None:
    weights = {"return_score": 0.4, "volatility_score": 0.3, "drawdown_score": 0.2}
    with pytest.raises(ValueError, match="toplamı"):
        validate_weights(weights, set(weights))


def test_expected_ranking() -> None:
    ranking = score_stocks(build_features(prices), DEFAULT_WEIGHTS)
    assert ranking.index.tolist() == ["GAMA", "BETA", "ALFA"]
    assert ranking["total_score"].to_numpy() == pytest.approx(
        [0.6000, 0.5198, 0.3586], abs=5e-4
    )
