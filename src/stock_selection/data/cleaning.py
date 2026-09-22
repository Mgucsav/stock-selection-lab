"""Ham sağlayıcı verisinin 2. Gün sözleşmesiyle temizlenmesi.

``src.day02_data_pipeline.clean_prices`` yeniden kullanılır: yinelenen
kayıt, eksik/negatif fiyat, negatif hacim, OHLC tutarsızlığı ve çakışan
anahtar kuralları oradan gelir. Bu modül üstüne şunları ekler:

* ``dividends`` sütununu temiz tabloya geri bağlama,
* sembol bazında satır sayısı, eksik gün oranı ve stale (bayat) kontrolü,
* hesaplama katmanına aktarılacak kalite uyarıları.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.day02_data_pipeline import REQUIRED_COLUMNS, build_quality_report, clean_prices

CLEAN_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "source",
    "ingested_at",
]


@dataclass
class SymbolQuality:
    symbol: str
    clean_rows: int
    rejected_rows: int
    first_date: date | None
    last_date: date | None
    missing_ratio: float
    is_stale: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "clean_rows": self.clean_rows,
            "rejected_rows": self.rejected_rows,
            "first_date": self.first_date.isoformat() if self.first_date else None,
            "last_date": self.last_date.isoformat() if self.last_date else None,
            "missing_ratio": round(self.missing_ratio, 4),
            "is_stale": self.is_stale,
            "warnings": list(self.warnings),
        }


@dataclass
class CleaningResult:
    clean: pd.DataFrame
    rejected: pd.DataFrame
    exact_duplicates: pd.DataFrame
    report: dict[str, object]
    symbol_quality: dict[str, SymbolQuality]
    warnings: list[str]


def _empty_clean() -> pd.DataFrame:
    frame = pd.DataFrame(columns=CLEAN_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def clean_raw_prices(
    raw: pd.DataFrame,
    reference_date: date | None = None,
    stale_days: int = 7,
    max_missing_ratio: float = 0.20,
    min_rows: int = 60,
) -> CleaningResult:
    """Ham tabloyu temizler; çağıranın tablosunu değiştirmez."""
    if raw is None or raw.empty:
        return CleaningResult(_empty_clean(), pd.DataFrame(), pd.DataFrame(), {}, {}, ["Ham veri boş."])

    working = raw.copy(deep=True)
    if "dividends" not in working.columns:
        working["dividends"] = np.nan
    working["_row_id"] = np.arange(len(working))

    clean_base, rejected, duplicates = clean_prices(working.loc[:, REQUIRED_COLUMNS])
    report = build_quality_report(working.loc[:, REQUIRED_COLUMNS], clean_base, rejected, duplicates)

    # Temettü sütununu (symbol, date) anahtarıyla geri bağla.
    dividend_lookup = working.loc[:, ["symbol", "date", "dividends"]].copy()
    dividend_lookup["symbol"] = dividend_lookup["symbol"].astype("string").str.strip().str.upper()
    dividend_lookup["date"] = pd.to_datetime(dividend_lookup["date"], errors="coerce").dt.normalize()
    dividend_lookup["dividends"] = pd.to_numeric(dividend_lookup["dividends"], errors="coerce")
    dividend_lookup = dividend_lookup.dropna(subset=["date"]).drop_duplicates(subset=["symbol", "date"], keep="first")
    clean_base = clean_base.copy()
    clean_base["symbol"] = clean_base["symbol"].astype(str)
    clean = clean_base.merge(dividend_lookup, on=["symbol", "date"], how="left")
    clean = clean.loc[:, CLEAN_COLUMNS].sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    # Sembol bazlı kalite değerlendirmesi
    reference = pd.Timestamp(reference_date) if reference_date else clean["date"].max()
    warnings: list[str] = []
    symbol_quality: dict[str, SymbolQuality] = {}
    rejected_counts = (
        rejected["symbol"].astype(str).value_counts().to_dict() if not rejected.empty else {}
    )
    all_symbols = sorted(set(clean["symbol"].unique()) | set(map(str, rejected_counts)))
    for symbol in all_symbols:
        sub = clean.loc[clean["symbol"] == symbol]
        sym_warnings: list[str] = []
        if sub.empty:
            symbol_quality[symbol] = SymbolQuality(
                symbol, 0, int(rejected_counts.get(symbol, 0)), None, None, 1.0, True,
                ["Temiz satır kalmadı; bütün kayıtlar reddedildi."],
            )
            continue
        first, last = sub["date"].min(), sub["date"].max()
        expected_days = len(pd.bdate_range(first, last))
        missing_ratio = 1.0 - len(sub) / expected_days if expected_days else 0.0
        is_stale = (reference - last).days > stale_days
        if len(sub) < min_rows:
            sym_warnings.append(f"Yetersiz gözlem: {len(sub)} satır (< {min_rows}).")
        if missing_ratio > max_missing_ratio:
            sym_warnings.append(f"Aşırı eksik gün: iş günlerinin %{missing_ratio*100:.1f}'i yok.")
        if is_stale:
            sym_warnings.append(f"Bayat veri: son gözlem {last.date().isoformat()}.")
        if rejected_counts.get(symbol):
            sym_warnings.append(f"{int(rejected_counts[symbol])} satır sözleşme kuralıyla reddedildi.")
        symbol_quality[symbol] = SymbolQuality(
            symbol, len(sub), int(rejected_counts.get(symbol, 0)), first.date(), last.date(),
            max(missing_ratio, 0.0), bool(is_stale), sym_warnings,
        )

    stale = [s for s, q in symbol_quality.items() if q.is_stale]
    if stale:
        warnings.append(f"{len(stale)} sembolde bayat veri: {', '.join(stale[:10])}{'…' if len(stale) > 10 else ''}")
    if not rejected.empty:
        warnings.append(f"{len(rejected)} ham satır ret nedeniyle dışlandı (bkz. kalite raporu).")
    if not duplicates.empty:
        warnings.append(f"{len(duplicates)} tam yinelenen satır ayıklandı.")
    return CleaningResult(clean, rejected, duplicates, report, symbol_quality, warnings)


def pivot_field(clean: pd.DataFrame, field_name: str) -> pd.DataFrame:
    """Uzun temiz tabloyu ``date x symbol`` geniş tabloya çevirir."""
    if clean.empty:
        return pd.DataFrame()
    wide = clean.pivot(index="date", columns="symbol", values=field_name).sort_index()
    wide.columns.name = None
    return wide
