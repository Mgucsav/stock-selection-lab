"""fpfs (fuzzy parameterized fuzzy soft) matrisi ve karar operatörleri.

Matrisin sıfırıncı satırı (``mu``) parametre önem ağırlıklarını taşır:

```text
a_0j = mu_j                (kriter j'nin önem derecesi, [0, 1])
a_ij = hisse i'nin kriter j üyeliği
```

Sütun sırası sözleşmedir: ``return, dividend, liquidity, risk``.

Operatörler (``n`` = kriter sayısı):

```text
CCE10   score_i = (1 / n) * sum_j(mu_j * a_ij)      → ana sonuç
FSS     fss_i   = (1 / n) * sum_j(a_ij)              → ağırlıksız baseline
DRF     drf_i   = sum_j(mu_j * a_ij)
DMF     C_ik    = sum_j(mu_j * (a_ij - a_kj)),  D_i = sum_k(C_ik)
```
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .membership import validate_membership_frame

CRITERIA_COLUMNS = ["return", "dividend", "liquidity", "risk"]
MU_ROW = "mu"


def validate_column_contract(columns: list[str] | pd.Index) -> None:
    """Sütun sırasının sözleşmeyle birebir aynı olduğunu doğrular."""
    actual = list(columns)
    if actual != CRITERIA_COLUMNS:
        raise ValueError(
            f"fpfs sütun sırası sözleşmesi ihlal edildi: {actual} != {CRITERIA_COLUMNS}"
        )


def _weights_vector(weights: Mapping[str, float]) -> np.ndarray:
    missing = [c for c in CRITERIA_COLUMNS if c not in weights]
    if missing:
        raise ValueError(f"Ağırlık eksik: {', '.join(missing)}")
    extra = [k for k in weights if k not in CRITERIA_COLUMNS]
    if extra:
        raise ValueError(f"Bilinmeyen ağırlık anahtarı: {', '.join(extra)}")
    vector = np.asarray([float(weights[c]) for c in CRITERIA_COLUMNS], dtype=float)
    if not np.isfinite(vector).all():
        raise ValueError("Ağırlıklar sonlu olmalıdır.")
    if (vector < 0).any() or (vector > 1).any():
        raise ValueError("Ağırlıklar [0, 1] aralığında olmalıdır.")
    return vector


def build_fpfs_matrix(memberships: pd.DataFrame, weights: Mapping[str, float]) -> pd.DataFrame:
    """Sıfırıncı satırı ``mu`` olan fpfs matrisini üretir; girdiyi değiştirmez."""
    validate_column_contract(memberships.columns)
    validate_membership_frame(memberships)
    if MU_ROW in memberships.index:
        raise ValueError("Üyelik tablosunda 'mu' adlı hisse olamaz.")
    mu = _weights_vector(weights)
    top = pd.DataFrame([mu], index=[MU_ROW], columns=CRITERIA_COLUMNS)
    body = memberships.loc[:, CRITERIA_COLUMNS].astype(float)
    return pd.concat([top, body])


def _split(matrix: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    validate_column_contract(matrix.columns)
    if MU_ROW not in matrix.index or matrix.index[0] != MU_ROW:
        raise ValueError("fpfs matrisinin sıfırıncı satırı 'mu' olmalıdır.")
    mu = matrix.loc[MU_ROW].to_numpy(dtype=float)
    body = matrix.drop(index=MU_ROW)
    if body.empty:
        raise ValueError("fpfs matrisinde hisse satırı yok.")
    validate_membership_frame(body)
    return mu, body


def cce10_scores(matrix: pd.DataFrame) -> pd.Series:
    """``score_i = (1/n) * sum_j(mu_j * a_ij)``."""
    mu, body = _split(matrix)
    n = len(CRITERIA_COLUMNS)
    return pd.Series(body.to_numpy(dtype=float) @ mu / n, index=body.index, name="cce10")


def fss_scores(matrix: pd.DataFrame) -> pd.Series:
    """Ağırlıksız baseline: ``(1/n) * sum_j(a_ij)``."""
    _, body = _split(matrix)
    n = len(CRITERIA_COLUMNS)
    return pd.Series(body.to_numpy(dtype=float).sum(axis=1) / n, index=body.index, name="fss")


def weighted_drf(matrix: pd.DataFrame) -> pd.Series:
    """``drf_i = sum_j(mu_j * a_ij)``."""
    mu, body = _split(matrix)
    return pd.Series(body.to_numpy(dtype=float) @ mu, index=body.index, name="drf")


def weighted_dmf(matrix: pd.DataFrame) -> pd.Series:
    """``D_i = sum_k sum_j mu_j (a_ij - a_kj)``."""
    mu, body = _split(matrix)
    values = body.to_numpy(dtype=float)
    weighted = values @ mu            # sum_j mu_j a_ij  (her hisse için)
    m = values.shape[0]
    # sum_k (w_i - w_k) = m * w_i - sum_k w_k
    dmf = m * weighted - weighted.sum()
    return pd.Series(dmf, index=body.index, name="dmf")


def _rank(scores: pd.Series) -> pd.Series:
    return scores.rank(ascending=False, method="min").astype(int)


@dataclass
class FpfsResult:
    matrix: pd.DataFrame
    scores: pd.DataFrame
    weights: dict[str, float]
    n_criteria: int = len(CRITERIA_COLUMNS)
    warnings: list[str] = field(default_factory=list)


def evaluate_fpfs(memberships: pd.DataFrame, weights: Mapping[str, float]) -> FpfsResult:
    """Bütün operatörleri hesaplar ve sıra tablosu üretir (CCE10 ana sıra)."""
    matrix = build_fpfs_matrix(memberships, weights)
    scores = pd.DataFrame(
        {
            "cce10": cce10_scores(matrix),
            "fss": fss_scores(matrix),
            "drf": weighted_drf(matrix),
            "dmf": weighted_dmf(matrix),
        }
    )
    scores["rank"] = _rank(scores["cce10"])
    scores["fss_rank"] = _rank(scores["fss"])
    scores["drf_rank"] = _rank(scores["drf"])
    scores["dmf_rank"] = _rank(scores["dmf"])
    scores["rank_delta_vs_fss"] = scores["fss_rank"] - scores["rank"]
    scores = scores.sort_values(["rank", "cce10"], ascending=[True, False])
    return FpfsResult(matrix=matrix, scores=scores, weights={c: float(weights[c]) for c in CRITERIA_COLUMNS})
