"""Parquet tabanlı yerel fiyat cache'i.

Ham ve temiz veri ayrı dosyalarda tutulur; ``(symbol, date)`` anahtarı
temiz tabloda benzersizdir. Bu sınıf ``PriceStore`` arayüzünü uygular; bulut
geçişinde aynı arayüzle Supabase Storage/PostgreSQL adaptörü yazılabilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd


class PriceStore(Protocol):
    def save_raw(self, frame: pd.DataFrame) -> None: ...
    def load_raw(self) -> pd.DataFrame | None: ...
    def save_clean(self, frame: pd.DataFrame) -> None: ...
    def load_clean(self) -> pd.DataFrame | None: ...
    def save_benchmark(self, frame: pd.DataFrame) -> None: ...
    def load_benchmark(self) -> pd.DataFrame | None: ...
    def save_fundamentals(self, frame: pd.DataFrame) -> None: ...
    def load_fundamentals(self) -> pd.DataFrame | None: ...
    def clear(self) -> None: ...


class ParquetPriceCache:
    RAW_FILE = "prices_raw.parquet"
    CLEAN_FILE = "prices_clean.parquet"
    BENCHMARK_FILE = "benchmark.parquet"
    FUNDAMENTALS_FILE = "fundamentals.parquet"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.directory / name

    def _save(self, name: str, frame: pd.DataFrame) -> None:
        frame.to_parquet(self._path(name), index=False)

    def _load(self, name: str) -> pd.DataFrame | None:
        path = self._path(name)
        if not path.exists():
            return None
        frame = pd.read_parquet(path)
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
        return frame

    def save_raw(self, frame: pd.DataFrame) -> None:
        self._save(self.RAW_FILE, frame)

    def load_raw(self) -> pd.DataFrame | None:
        return self._load(self.RAW_FILE)

    def save_clean(self, frame: pd.DataFrame) -> None:
        if frame.duplicated(subset=["symbol", "date"]).any():
            raise ValueError("Temiz tabloda (symbol, date) anahtarı benzersiz olmalıdır.")
        self._save(self.CLEAN_FILE, frame)

    def load_clean(self) -> pd.DataFrame | None:
        return self._load(self.CLEAN_FILE)

    def save_benchmark(self, frame: pd.DataFrame) -> None:
        self._save(self.BENCHMARK_FILE, frame)

    def load_benchmark(self) -> pd.DataFrame | None:
        return self._load(self.BENCHMARK_FILE)

    def save_fundamentals(self, frame: pd.DataFrame) -> None:
        self._save(self.FUNDAMENTALS_FILE, frame)

    def load_fundamentals(self) -> pd.DataFrame | None:
        return self._load(self.FUNDAMENTALS_FILE)

    def clear(self) -> None:
        for name in (self.RAW_FILE, self.CLEAN_FILE, self.BENCHMARK_FILE, self.FUNDAMENTALS_FILE):
            path = self._path(name)
            if path.exists():
                path.unlink()
