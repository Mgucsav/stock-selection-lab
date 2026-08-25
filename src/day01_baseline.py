"""1. Gün: sentetik fiyatlarla getiri, risk ve hisse sıralaması."""

from collections.abc import Collection, Mapping
import sys

import numpy as np
import pandas as pd


# Sabitler
TRADING_DAYS = 252
SCORING_COLUMNS = {"return_score", "volatility_score", "drawdown_score"}
DEFAULT_WEIGHTS = {
    "return_score": 0.40,
    "volatility_score": 0.35,
    "drawdown_score": 0.25,
}


# Sentetik fiyat tablosu
prices = pd.DataFrame(
    {
        "ALFA": [100, 101, 100, 103, 104, 102, 105, 107, 106, 109],
        "BETA": [100, 99, 101, 100, 103, 105, 104, 108, 111, 110],
        "GAMA": [100, 100.5, 101, 101.5, 102, 102.2, 102.7, 103, 103.4, 104],
    },
    index=pd.date_range("2026-08-03", periods=10, freq="B"),
)


# Fiyat doğrulama ve basit getiriler
def _validated_prices(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Fiyat tablosunun sayısal, sonlu ve pozitif bir kopyasını döndürür."""
    if not isinstance(price_frame, pd.DataFrame):
        raise ValueError("Fiyat verisi bir pandas DataFrame olmalıdır.")
    if price_frame.empty or price_frame.shape[1] == 0:
        raise ValueError("Fiyat tablosu boş olamaz.")
    if price_frame.isna().any().any():
        raise ValueError("Fiyat tablosunda eksik değer bulunamaz.")

    numeric = price_frame.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("Fiyatların tamamı sayısal olmalıdır.")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Fiyatların tamamı sonlu olmalıdır.")
    if (numeric <= 0).any().any():
        raise ValueError("Fiyatların tamamı sıfırdan büyük olmalıdır.")
    return numeric


def simple_returns(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Fiyatlardan ``P[t] / P[t-1] - 1`` basit getirisini üretir."""
    validated = _validated_prices(price_frame)
    return validated.div(validated.shift(1)).sub(1.0).iloc[1:]


# Maksimum düşüş
def max_drawdown(price_series: pd.Series) -> float:
    """Zirveden en büyük oransal kaybı negatif bir sayı olarak döndürür."""
    if not isinstance(price_series, pd.Series) or price_series.empty:
        raise ValueError("Fiyat serisi boş olmayan bir pandas Series olmalıdır.")
    validated = _validated_prices(price_series.to_frame("price"))["price"]
    drawdown = validated.div(validated.cummax()).sub(1.0)
    return float(drawdown.min())


# Yıllıklaştırılmış aşağı yönlü oynaklık
def annualized_downside_volatility(
    returns: pd.Series | pd.DataFrame,
) -> float | pd.Series:
    """Negatif getirilerin anakütle standart sapmasını yıllıklaştırır.

    Bu eğitim tanımı, akademik kaynaklardaki her aşağı yönlü sapma tanımıyla
    aynı olmak zorunda değildir. Negatif getiri yoksa sonuç ``0.0`` olur.
    """

    def calculate(series: pd.Series) -> float:
        numeric = pd.to_numeric(series, errors="coerce")
        negative = numeric[(numeric < 0) & np.isfinite(numeric)]
        if negative.empty:
            return 0.0
        return float(negative.std(ddof=0) * np.sqrt(TRADING_DAYS))

    if isinstance(returns, pd.Series):
        return calculate(returns)
    if isinstance(returns, pd.DataFrame):
        return returns.apply(calculate)
    raise ValueError("Getiri verisi bir pandas Series veya DataFrame olmalıdır.")


# Özellik üretimi
def build_features(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Her hisse için getiri ve üç risk özelliği üretir."""
    validated = _validated_prices(price_frame)
    returns = simple_returns(validated)
    cumulative_return = validated.iloc[-1].div(validated.iloc[0]).sub(1.0)
    annualized_volatility = returns.std(ddof=1).mul(np.sqrt(TRADING_DAYS))
    downside = annualized_downside_volatility(returns)
    drawdown = validated.apply(max_drawdown).abs()
    return pd.DataFrame(
        {
            "return": cumulative_return,
            "volatility": annualized_volatility,
            "downside_volatility": downside,
            "max_drawdown_abs": drawdown,
        }
    )


# Fayda ve maliyet min-max normalizasyonu
def minmax_benefit(series: pd.Series) -> pd.Series:
    """Büyük değerin iyi olduğu bir kriteri 0 ile 1 arasına taşır."""
    spread = series.max() - series.min()
    if np.isclose(spread, 0.0):
        return pd.Series(0.5, index=series.index, dtype=float)
    return series.sub(series.min()).div(spread)


def minmax_cost(series: pd.Series) -> pd.Series:
    """Küçük değerin iyi olduğu bir kriteri 0 ile 1 arasına taşır."""
    spread = series.max() - series.min()
    if np.isclose(spread, 0.0):
        return pd.Series(0.5, index=series.index, dtype=float)
    return series.rsub(series.max()).div(spread)


# Ağırlık doğrulaması
def validate_weights(
    weights: Mapping[str, float], expected_columns: Collection[str]
) -> None:
    """Ağırlık anahtarlarını, sonluluğunu, işaretini ve toplamını doğrular."""
    if set(weights) != set(expected_columns):
        raise ValueError("Ağırlık anahtarları puanlama kriterleriyle aynı olmalıdır.")
    try:
        numeric_weights = np.asarray(list(weights.values()), dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Ağırlıkların tamamı sayısal olmalıdır.") from error
    if not np.isfinite(numeric_weights).all():
        raise ValueError("Ağırlıkların tamamı sonlu olmalıdır.")
    if (numeric_weights < 0).any():
        raise ValueError("Ağırlıklar negatif olamaz.")
    if not np.isclose(numeric_weights.sum(), 1.0):
        raise ValueError("Ağırlıkların toplamı yaklaşık olarak 1 olmalıdır.")


# Hisse puanlama ve sıralaması
def score_stocks(
    features: pd.DataFrame, weights: Mapping[str, float]
) -> pd.DataFrame:
    """Üç kriteri normalize edip ağırlıklı toplam puanla hisseleri sıralar."""
    required = {"return", "volatility", "max_drawdown_abs"}
    if not required.issubset(features.columns):
        raise ValueError("Özellik tablosunda gerekli puanlama sütunları eksik.")

    normalized = pd.DataFrame(index=features.index)
    normalized["return_score"] = minmax_benefit(features["return"])
    normalized["volatility_score"] = minmax_cost(features["volatility"])
    normalized["drawdown_score"] = minmax_cost(features["max_drawdown_abs"])
    validate_weights(weights, SCORING_COLUMNS)

    normalized["total_score"] = sum(
        normalized[column] * weight for column, weight in weights.items()
    )
    normalized["rank"] = (
        normalized["total_score"].rank(ascending=False, method="min").astype(int)
    )
    return normalized.sort_values(["rank", "total_score"], ascending=[True, False])


# Gösterim
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    feature_table = build_features(prices)
    ranking_table = score_stocks(feature_table, DEFAULT_WEIGHTS)

    print("ÖZELLİK TABLOSU")
    print(feature_table.round(4))
    print("\nSIRALAMA TABLOSU")
    print(ranking_table.round(4))

    invalid_weights = {
        "return_score": 0.50,
        "volatility_score": -0.10,
        "drawdown_score": 0.60,
    }
    try:
        score_stocks(feature_table, invalid_weights)
    except ValueError as error:
        print(f"\nNEGATİF AĞIRLIK BAŞARIYLA REDDEDİLDİ: {error}")

    prices_with_missing = prices.copy()
    prices_with_missing.loc[prices.index[3], "ALFA"] = np.nan
    try:
        build_features(prices_with_missing)
    except ValueError as error:
        print(f"\nEKSİK FİYAT BAŞARIYLA REDDEDİLDİ: {error}")
