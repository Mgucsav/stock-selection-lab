"""2. Gün veri sözleşmesi ve temizleme hattı testleri."""

import json

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.day02_data_pipeline import (
    REQUIRED_COLUMNS,
    build_quality_report,
    clean_prices,
    make_sample_data,
    require_columns,
    write_outputs,
)


def valid_row(**changes) -> dict:
    """Testlerde kullanılacak geçerli bir fiyat satırı üretir."""
    row = {
        "date": "2026-08-03",
        "symbol": "XYZ",
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "adj_close": 11.0,
        "volume": 100,
        "source": "demo",
        "ingested_at": "2026-08-03T18:00:00Z",
    }
    row.update(changes)
    return row


def test_missing_required_columns_fail_closed() -> None:
    with pytest.raises(ValueError, match="Zorunlu"):
        require_columns(pd.DataFrame({"date": ["2026-08-03"]}))


def test_base_sample_row_counts() -> None:
    raw = make_sample_data()
    clean, rejected, duplicates = clean_prices(raw)
    assert (len(raw), len(clean), len(rejected), len(duplicates)) == (7, 2, 4, 1)


def test_every_rejected_row_has_a_reason() -> None:
    _, rejected, _ = clean_prices(make_sample_data())
    assert rejected["rejection_reason"].str.len().gt(0).all()


def test_exact_duplicates_are_separate_from_rejections() -> None:
    _, rejected, duplicates = clean_prices(make_sample_data())
    assert len(duplicates) == 1
    assert "rejection_reason" not in duplicates.columns
    assert len(rejected) == 4


def test_symbols_are_trimmed_and_uppercased() -> None:
    clean, _, _ = clean_prices(pd.DataFrame([valid_row(symbol=" xyz ")]))
    assert clean.loc[0, "symbol"] == "XYZ"


def test_raw_input_is_unchanged() -> None:
    raw = make_sample_data()
    original = raw.copy(deep=True)
    clean_prices(raw)
    assert_frame_equal(raw, original)


def test_invalid_date_is_rejected() -> None:
    _, rejected, _ = clean_prices(pd.DataFrame([valid_row(date="bozuk")]))
    assert "invalid_date" in rejected.loc[0, "rejection_reason"]


@pytest.mark.parametrize("price", [None, "sayı-değil", np.inf, 0.0, -1.0])
def test_invalid_prices_are_rejected(price) -> None:
    _, rejected, _ = clean_prices(pd.DataFrame([valid_row(close=price)]))
    assert len(rejected) == 1
    assert "price" in rejected.loc[0, "rejection_reason"]


@pytest.mark.parametrize("volume", [-1, np.inf])
def test_negative_or_nonfinite_volume_is_rejected(volume: float) -> None:
    _, rejected, _ = clean_prices(pd.DataFrame([valid_row(volume=volume)]))
    assert "volume" in rejected.loc[0, "rejection_reason"]


def test_invalid_ohlc_relation_is_rejected() -> None:
    _, rejected, _ = clean_prices(pd.DataFrame([valid_row(high=10.0, close=11.0)]))
    assert "invalid_ohlc_relation" in rejected.loc[0, "rejection_reason"]


def test_unknown_source_has_expected_reason() -> None:
    _, rejected, _ = clean_prices(pd.DataFrame([valid_row(source="başka")]))
    assert rejected.loc[0, "rejection_reason"] == "unknown_source"


@pytest.mark.parametrize("source", ["demo", "csv", "vendor_a"])
def test_allowed_sources_are_accepted(source: str) -> None:
    clean, rejected, _ = clean_prices(pd.DataFrame([valid_row(source=source)]))
    assert len(clean) == 1
    assert rejected.empty


def test_conflicting_business_keys_reject_every_conflict() -> None:
    raw = pd.DataFrame(
        [
            valid_row(close=11.0, adj_close=11.0),
            valid_row(close=11.5, adj_close=11.5),
        ]
    )
    clean, rejected, duplicates = clean_prices(raw)
    assert clean.empty
    assert duplicates.empty
    assert len(rejected) == 2
    assert rejected["rejection_reason"].eq("conflicting_duplicate_key").all()


def test_quality_report_totals_are_consistent() -> None:
    raw = make_sample_data()
    clean, rejected, duplicates = clean_prices(raw)
    report = build_quality_report(raw, clean, rejected, duplicates)
    assert report["raw_rows"] == (
        report["clean_rows"] + report["rejected_rows"] + report["exact_duplicate_rows"]
    )
    assert report["rejection_rate"] == pytest.approx(4 / 7)


def test_quality_report_symbol_counts() -> None:
    raw = make_sample_data()
    clean, rejected, duplicates = clean_prices(raw)
    by_symbol = build_quality_report(raw, clean, rejected, duplicates)["by_symbol"]
    assert by_symbol["AAA"] == {
        "raw": 4,
        "clean": 2,
        "rejected": 1,
        "exact_duplicates": 1,
    }
    assert by_symbol["BBB"] == {
        "raw": 3,
        "clean": 0,
        "rejected": 3,
        "exact_duplicates": 0,
    }


def test_csv_and_json_outputs_are_created(tmp_path) -> None:
    raw = make_sample_data()
    clean, rejected, duplicates = clean_prices(raw)
    report = build_quality_report(raw, clean, rejected, duplicates)
    paths = write_outputs(
        clean, rejected, duplicates, report, tmp_path / "processed", tmp_path / "rejected"
    )
    assert all(path.is_file() for path in paths.values())
    saved_clean = pd.read_csv(paths["clean"])
    assert saved_clean.loc[0, "ingested_at"] == "2026-08-03T18:00:00Z"


def test_output_json_can_be_read_back(tmp_path) -> None:
    raw = make_sample_data()
    clean, rejected, duplicates = clean_prices(raw)
    report = build_quality_report(raw, clean, rejected, duplicates)
    paths = write_outputs(clean, rejected, duplicates, report, tmp_path, tmp_path)
    loaded = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert loaded == report


def test_clean_output_is_sorted_by_symbol_and_date() -> None:
    raw = pd.DataFrame(
        [
            valid_row(symbol="ZZZ", date="2026-08-04"),
            valid_row(symbol="AAA", date="2026-08-05"),
            valid_row(symbol="AAA", date="2026-08-03"),
        ],
        columns=REQUIRED_COLUMNS,
    )
    clean, _, _ = clean_prices(raw)
    observed = list(zip(clean["symbol"], clean["date"].dt.strftime("%Y-%m-%d")))
    assert observed == [
        ("AAA", "2026-08-03"),
        ("AAA", "2026-08-05"),
        ("ZZZ", "2026-08-04"),
    ]
