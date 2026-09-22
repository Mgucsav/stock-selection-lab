"""2. Gün: denetlenebilir sentetik fiyat verisi temizleme hattı."""

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "ingested_at",
]
PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close"]
ALLOWED_SOURCES = {"demo", "csv", "vendor_a", "yahoo", "fake"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_REJECTED_DIR = PROJECT_ROOT / "data" / "rejected"


def make_sample_data() -> pd.DataFrame:
    """İki temiz, dört hatalı ve bir yinelenen satırlık örnek üretir."""
    rows = [
        {
            "date": "2026-08-03",
            "symbol": " aaa ",
            "open": 100,
            "high": 103,
            "low": 99,
            "close": 102,
            "adj_close": 102,
            "volume": 1_000,
            "source": "demo",
            "ingested_at": "2026-08-03T18:00:00Z",
        },
        {
            "date": "2026-08-04",
            "symbol": "AAA",
            "open": 102,
            "high": 105,
            "low": 101,
            "close": 104,
            "adj_close": 104,
            "volume": 1_200,
            "source": "demo",
            "ingested_at": "2026-08-04T18:00:00Z",
        },
        {
            "date": "2026-08-04",
            "symbol": "AAA",
            "open": 102,
            "high": 105,
            "low": 101,
            "close": 104,
            "adj_close": 104,
            "volume": 1_200,
            "source": "demo",
            "ingested_at": "2026-08-04T18:00:00Z",
        },
        {
            "date": "2026-08-05",
            "symbol": "AAA",
            "open": 104,
            "high": 106,
            "low": 103,
            "close": 0,
            "adj_close": 105,
            "volume": 900,
            "source": "demo",
            "ingested_at": "2026-08-05T18:00:00Z",
        },
        {
            "date": "geçersiz-tarih",
            "symbol": "BBB",
            "open": 50,
            "high": 52,
            "low": 49,
            "close": 51,
            "adj_close": 51,
            "volume": 700,
            "source": "csv",
            "ingested_at": "2026-08-03T18:05:00Z",
        },
        {
            "date": "2026-08-04",
            "symbol": "BBB",
            "open": 51,
            "high": 53,
            "low": 50,
            "close": 52,
            "adj_close": 52,
            "volume": -5,
            "source": "vendor_a",
            "ingested_at": "2026-08-04T18:05:00Z",
        },
        {
            "date": "2026-08-05",
            "symbol": "BBB",
            "open": 52,
            "high": 51,
            "low": 53,
            "close": 52,
            "adj_close": 52,
            "volume": 800,
            "source": "demo",
            "ingested_at": "2026-08-05T18:05:00Z",
        },
    ]
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def require_columns(frame: pd.DataFrame) -> None:
    """Zorunlu sütunlar eksikse işlemi kapalı biçimde durdurur."""
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Zorunlu sütunlar eksik: {', '.join(missing)}")


def coerce_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Ham tabloyu değiştirmeden metin, tarih ve sayı türlerini dönüştürür."""
    require_columns(frame)
    converted = frame.loc[:, REQUIRED_COLUMNS].copy(deep=True)
    converted["symbol"] = converted["symbol"].astype("string").str.strip().str.upper()
    converted["source"] = converted["source"].astype("string").str.strip()
    converted["date"] = pd.to_datetime(
        converted["date"], errors="coerce", format="mixed"
    ).dt.normalize()
    converted["ingested_at"] = pd.to_datetime(
        converted["ingested_at"], errors="coerce", utc=True, format="mixed"
    )
    for column in [*PRICE_COLUMNS, "volume"]:
        converted[column] = pd.to_numeric(converted[column], errors="coerce")
    return converted


def _is_missing_or_infinite(value: Any) -> bool:
    """Bir değerin eksik ya da sonsuz olup olmadığını güvenle sınar."""
    if pd.isna(value):
        return True
    try:
        return not bool(np.isfinite(value))
    except TypeError:
        return True


def rejection_reason(row: pd.Series) -> str:
    """Bir dönüştürülmüş satır için sıralı ret nedenlerini birleştirir."""
    reasons: list[str] = []
    if pd.isna(row["date"]):
        reasons.append("invalid_date")
    if pd.isna(row["symbol"]) or str(row["symbol"]).strip() == "":
        reasons.append("missing_symbol")
    if pd.isna(row["ingested_at"]):
        reasons.append("invalid_ingested_at")

    invalid_prices = any(_is_missing_or_infinite(row[column]) for column in PRICE_COLUMNS)
    if invalid_prices:
        reasons.append("invalid_price")
    elif any(float(row[column]) <= 0 for column in PRICE_COLUMNS):
        reasons.append("non_positive_price")

    if _is_missing_or_infinite(row["volume"]):
        reasons.append("invalid_volume")
    elif float(row["volume"]) < 0:
        reasons.append("negative_volume")

    if not invalid_prices:
        low = float(row["low"])
        high = float(row["high"])
        open_price = float(row["open"])
        close = float(row["close"])
        if low > min(open_price, close) or high < max(open_price, close) or low > high:
            reasons.append("invalid_ohlc_relation")

    if pd.isna(row["source"]) or str(row["source"]).strip() == "":
        reasons.append("missing_source")
    elif row["source"] not in ALLOWED_SOURCES:
        reasons.append("unknown_source")
    return "|".join(reasons)


def _use_nullable_integer(frame: pd.DataFrame) -> pd.DataFrame:
    """Uygunsa hacim sütununu pandas nullable tamsayısına dönüştürür."""
    result = frame.copy()
    non_missing = result["volume"].dropna()
    if non_missing.empty or np.isclose(non_missing % 1, 0).all():
        result["volume"] = result["volume"].astype("Int64")
    return result


def clean_prices(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Ham fiyatları temiz, reddedilen ve tam yinelenen tablolara ayırır."""
    working = coerce_types(raw)

    duplicate_mask = working.duplicated(subset=REQUIRED_COLUMNS, keep="first")
    exact_duplicates = working.loc[duplicate_mask].copy()
    candidates = working.loc[~duplicate_mask].copy()
    candidates["rejection_reason"] = candidates.apply(rejection_reason, axis=1)

    rule_rejected_mask = candidates["rejection_reason"].ne("")
    rejected = candidates.loc[rule_rejected_mask].copy()
    valid = candidates.loc[~rule_rejected_mask].copy()

    conflict_mask = valid.duplicated(subset=["symbol", "date"], keep=False)
    if conflict_mask.any():
        conflicts = valid.loc[conflict_mask].copy()
        conflicts["rejection_reason"] = "conflicting_duplicate_key"
        rejected = pd.concat([rejected, conflicts], ignore_index=True)
        valid = valid.loc[~conflict_mask].copy()

    clean = valid.drop(columns="rejection_reason").sort_values(
        ["symbol", "date"], kind="stable"
    )
    rejected = rejected.sort_index(kind="stable")
    clean = _use_nullable_integer(clean).reset_index(drop=True)
    rejected = _use_nullable_integer(rejected).reset_index(drop=True)
    exact_duplicates = _use_nullable_integer(exact_duplicates).reset_index(drop=True)
    return clean, rejected, exact_duplicates


def _symbol_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Eksik sembolleri de görünür kılan adet sözlüğü üretir."""
    labels = frame["symbol"].astype("string").fillna("<EKSİK>")
    labels = labels.mask(labels.str.strip().eq(""), "<EKSİK>")
    return {str(key): int(value) for key, value in labels.value_counts().items()}


def build_quality_report(
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    rejected: pd.DataFrame,
    exact_duplicates: pd.DataFrame,
) -> dict[str, Any]:
    """Satır, ret nedeni ve sembol bazında denetim özeti üretir."""
    normalized_raw = coerce_types(raw)
    reason_counts: dict[str, int] = {}
    if not rejected.empty:
        exploded = rejected["rejection_reason"].str.split("|").explode()
        reason_counts = {
            str(key): int(value) for key, value in exploded.value_counts().items()
        }

    raw_counts = _symbol_counts(normalized_raw)
    clean_counts = _symbol_counts(clean)
    rejected_counts = _symbol_counts(rejected)
    duplicate_counts = _symbol_counts(exact_duplicates)
    symbols = sorted(set(raw_counts) | set(clean_counts) | set(rejected_counts) | set(duplicate_counts))
    by_symbol = {
        symbol: {
            "raw": raw_counts.get(symbol, 0),
            "clean": clean_counts.get(symbol, 0),
            "rejected": rejected_counts.get(symbol, 0),
            "exact_duplicates": duplicate_counts.get(symbol, 0),
        }
        for symbol in symbols
    }
    raw_rows = len(raw)
    return {
        "raw_rows": raw_rows,
        "clean_rows": len(clean),
        "rejected_rows": len(rejected),
        "exact_duplicate_rows": len(exact_duplicates),
        "rejection_rate": len(rejected) / raw_rows if raw_rows else 0.0,
        "reasons": reason_counts,
        "by_symbol": by_symbol,
    }


def _prepare_csv_output(frame: pd.DataFrame) -> pd.DataFrame:
    """Tarih ile UTC alım zamanını kayıpsız ve okunabilir biçime getirir."""
    output = frame.copy()
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output["ingested_at"] = output["ingested_at"].dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return output


def write_outputs(
    clean: pd.DataFrame,
    rejected: pd.DataFrame,
    exact_duplicates: pd.DataFrame,
    report: dict[str, Any],
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    rejected_dir: str | Path = DEFAULT_REJECTED_DIR,
) -> dict[str, Path]:
    """CSV ve JSON çıktılarını verilen proje göreli dizinlere yazar."""
    processed_path = Path(processed_dir)
    rejected_path = Path(rejected_dir)
    processed_path.mkdir(parents=True, exist_ok=True)
    rejected_path.mkdir(parents=True, exist_ok=True)

    paths = {
        "clean": processed_path / "prices_clean.csv",
        "rejected": rejected_path / "prices_rejected.csv",
        "exact_duplicates": rejected_path / "prices_exact_duplicates.csv",
        "report": processed_path / "quality_report.json",
    }
    _prepare_csv_output(clean).to_csv(paths["clean"], index=False)
    _prepare_csv_output(rejected).to_csv(paths["rejected"], index=False)
    _prepare_csv_output(exact_duplicates).to_csv(
        paths["exact_duplicates"], index=False
    )
    paths["report"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw_table = make_sample_data()
    clean_table, rejected_table, duplicate_table = clean_prices(raw_table)
    quality_report = build_quality_report(
        raw_table, clean_table, rejected_table, duplicate_table
    )
    output_paths = write_outputs(
        clean_table, rejected_table, duplicate_table, quality_report
    )

    print("TEMİZ TABLO")
    print(clean_table.to_string(index=False))
    print("\nREDDEDİLEN TABLO VE NEDENLERİ")
    print(rejected_table.to_string(index=False))
    print("\nTAM YİNELENENLER")
    print(duplicate_table.to_string(index=False))
    print("\nKALİTE RAPORU")
    print(json.dumps(quality_report, ensure_ascii=False, indent=2))
    print("\nOLUŞTURULAN ÇIKTILAR")
    for label, path in output_paths.items():
        print(f"{label}: {path.relative_to(PROJECT_ROOT)}")
