"""Portföy başlatma anlık görüntüsü: giriş fiyatı ve tam lot hesabı.

Look-ahead kuralı: karar tarihi ``decision_date`` ise giriş fiyatı, her
sembol için ``decision_date``'ten **sonraki** ilk uygun işlem gününün
açılış fiyatıdır (açılış yoksa kapanış). Böyle bir gün henüz oluşmamışsa
pozisyon ``pending`` kalır.

Lot hesabı (BIST tam lot):

```text
quantity_i = floor(capital * weight_i / entry_price_i)
cash       = capital - sum(quantity_i * entry_price_i)
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import math

import pandas as pd


@dataclass
class PositionSnapshot:
    symbol: str
    target_weight: float
    entry_date: date | None
    entry_price: float | None
    price_field: str | None
    quantity: int
    cost: float

    @property
    def is_pending(self) -> bool:
        return self.entry_price is None

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "target_weight": self.target_weight,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_price": self.entry_price,
            "price_field": self.price_field,
            "quantity": self.quantity,
            "cost": self.cost,
        }


def resolve_entry_prices(
    clean: pd.DataFrame,
    symbols: list[str],
    decision_date: date,
) -> dict[str, tuple[date, float, str] | None]:
    """Her sembol için karar tarihinden sonraki ilk uygun işlem gününü bulur."""
    frame = clean.loc[clean["symbol"].isin(symbols)].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    after = frame.loc[frame["date"] > pd.Timestamp(decision_date)].sort_values("date")
    result: dict[str, tuple[date, float, str] | None] = {}
    for symbol in symbols:
        sub = after.loc[after["symbol"] == symbol]
        result[symbol] = None
        for _, row in sub.iterrows():
            open_price = pd.to_numeric(row.get("open"), errors="coerce")
            close_price = pd.to_numeric(row.get("close"), errors="coerce")
            if pd.notna(open_price) and float(open_price) > 0:
                result[symbol] = (row["date"].date(), float(open_price), "open")
                break
            if pd.notna(close_price) and float(close_price) > 0:
                result[symbol] = (row["date"].date(), float(close_price), "close")
                break
    return result


def allocate_lots(
    capital: float,
    weights: dict[str, float],
    entry_prices: dict[str, tuple[date, float, str] | None],
) -> tuple[list[PositionSnapshot], float]:
    """Tam lot dağılımı; artan tutar nakitte kalır. Bekleyen pozisyon için lot 0."""
    if capital <= 0:
        raise ValueError("Başlangıç sermayesi pozitif olmalıdır.")
    positions: list[PositionSnapshot] = []
    invested = 0.0
    for symbol, weight in weights.items():
        entry = entry_prices.get(symbol)
        if entry is None:
            positions.append(PositionSnapshot(symbol, float(weight), None, None, None, 0, 0.0))
            continue
        entry_date, price, price_field = entry
        quantity = int(math.floor(capital * weight / price))
        cost = quantity * price
        invested += cost
        positions.append(PositionSnapshot(symbol, float(weight), entry_date, price, price_field, quantity, cost))
    cash = capital - invested
    if cash < -1e-6:
        raise ValueError("Nakit negatif olamaz; lot hesabı hatalı.")
    return positions, float(cash)
