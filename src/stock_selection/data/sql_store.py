"""Veritabanı tabanlı fiyat deposu (``PriceStore`` arayüzü).

Yerel MVP Parquet dosyası kullanır; bulutta (Supabase PostgreSQL) kalıcı disk
olmadığı için ham/temiz/benchmark tabloları veritabanında tutulur. SQLAlchemy
ile yazıldığı için SQLite üzerinde de çalışır (testler bunu kullanır).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

RAW_TABLE = "prices_raw"
CLEAN_TABLE = "prices_clean"
BENCHMARK_TABLE = "prices_benchmark"
FUNDAMENTALS_TABLE = "fundamentals"


class SqlPriceStore:
    """Fiyat tablolarını ``prices_raw``, ``prices_clean``, ``prices_benchmark`` tablolarında saklar."""

    def __init__(self, engine: Engine, chunksize: int = 2000) -> None:
        self.engine = engine
        self.chunksize = chunksize

    def _save(self, table: str, frame: pd.DataFrame) -> None:
        out = frame.copy()
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"])
        # Tam değiştirme: eski veri ile yeni veri karışmaz (yenileme bütün pencereyi getirir).
        if self.engine.dialect.name == "postgresql":
            self._save_postgres_copy(table, out)
            return
        with self.engine.begin() as connection:
            out.to_sql(table, connection, if_exists="replace", index=False, chunksize=self.chunksize)

    def _save_postgres_copy(self, table: str, out: pd.DataFrame) -> None:
        """PostgreSQL'de satır satır INSERT yerine COPY: uzak veritabanında dakikalar yerine saniyeler."""
        import io

        with self.engine.begin() as connection:
            out.head(0).to_sql(table, connection, if_exists="replace", index=False)  # yalnızca şema
        csv_bytes = out.to_csv(index=False, header=True, date_format="%Y-%m-%d %H:%M:%S").encode("utf-8")
        columns = ", ".join(f'"{c}"' for c in out.columns)
        sql = f'COPY "{table}" ({columns}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)'
        raw = self.engine.raw_connection()
        try:
            cursor = raw.cursor()
            driver = self.engine.dialect.driver
            if driver == "pg8000":
                cursor.execute(sql, stream=io.BytesIO(csv_bytes))
            else:  # psycopg 3
                with cursor.copy(sql) as copy:
                    copy.write(csv_bytes)
            raw.commit()
        finally:
            raw.close()

    def _load(self, table: str) -> pd.DataFrame | None:
        with self.engine.connect() as connection:
            exists = connection.dialect.has_table(connection, table)
            if not exists:
                return None
            frame = pd.read_sql_table(table, connection)
        if frame.empty:
            return None
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
        return frame

    def save_raw(self, frame: pd.DataFrame) -> None:
        self._save(RAW_TABLE, frame)

    def load_raw(self) -> pd.DataFrame | None:
        return self._load(RAW_TABLE)

    def save_clean(self, frame: pd.DataFrame) -> None:
        if frame.duplicated(subset=["symbol", "date"]).any():
            raise ValueError("Temiz tabloda (symbol, date) anahtarı benzersiz olmalıdır.")
        self._save(CLEAN_TABLE, frame)

    def load_clean(self) -> pd.DataFrame | None:
        return self._load(CLEAN_TABLE)

    def save_benchmark(self, frame: pd.DataFrame) -> None:
        self._save(BENCHMARK_TABLE, frame)

    def load_benchmark(self) -> pd.DataFrame | None:
        return self._load(BENCHMARK_TABLE)

    def save_fundamentals(self, frame: pd.DataFrame) -> None:
        self._save(FUNDAMENTALS_TABLE, frame)

    def load_fundamentals(self) -> pd.DataFrame | None:
        return self._load(FUNDAMENTALS_TABLE)

    def clear(self) -> None:
        with self.engine.begin() as connection:
            for table in (RAW_TABLE, CLEAN_TABLE, BENCHMARK_TABLE, FUNDAMENTALS_TABLE):
                connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
