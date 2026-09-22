"""Seminerdeki yedi hisselik örneğin test fixture'ı.

Seminer sunumunda ham üyelik matrisi verilmediği için buradaki üyelik
değerleri, seminerde raporlanan Dengeli profil CCE10 skorlarını (±0.001) ve
hem FSS hem fpfs sıralamalarını yeniden üretecek şekilde yapılandırılmış bir
**yeniden yapılandırma**dır; seminerin orijinal ham verisi değildir.

Sütun sırası sözleşmesi: return, dividend, liquidity, risk.
"""

import pandas as pd

SEMINAR_WEIGHTS = {"return": 0.80, "dividend": 0.60, "liquidity": 0.60, "risk": 0.80}

SEMINAR_MEMBERSHIPS = pd.DataFrame(
    {
        "return":    [0.84, 0.64, 0.30, 0.39, 0.40, 0.36, 0.24],
        "dividend":  [0.33, 0.74, 0.42, 0.26, 0.60, 0.30, 0.31],
        "liquidity": [0.84, 0.44, 0.57, 0.16, 0.35, 0.29, 0.24],
        "risk":      [0.55, 0.30, 0.40, 0.63, 0.20, 0.22, 0.18],
    },
    index=["C29", "C21", "C9", "C7", "C4", "C16", "C14"],
)

EXPECTED_FSS_ORDER = ["C29", "C21", "C9", "C4", "C7", "C16", "C14"]
EXPECTED_FPFS_ORDER = ["C29", "C21", "C9", "C7", "C4", "C16", "C14"]
EXPECTED_FPFS_SCORES = {
    "C29": 0.454,
    "C21": 0.365,
    "C9": 0.288,
    "C7": 0.267,
    "C4": 0.262,
    "C16": 0.205,
    "C14": 0.167,
}
