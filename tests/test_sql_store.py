"""Veritabanı tabanlı fiyat deposu testleri (SQLite üzerinde; PostgreSQL ile aynı kod)."""

from datetime import date

import pandas as pd
from sqlalchemy import create_engine

from src.stock_selection.application import build_container
from src.stock_selection.data.cleaning import clean_raw_prices
from src.stock_selection.data.providers.fake import FakeProvider
from src.stock_selection.data.sql_store import SqlPriceStore


def test_sql_store_roundtrip(tmp_path, demo_raw):
    engine = create_engine(f"sqlite:///{(tmp_path / 'prices.db').as_posix()}")
    store = SqlPriceStore(engine)
    assert store.load_clean() is None
    clean = clean_raw_prices(demo_raw, reference_date=date(2026, 9, 19)).clean
    store.save_raw(demo_raw)
    store.save_clean(clean)
    loaded = store.load_clean()
    assert loaded is not None and len(loaded) == len(clean)
    assert pd.api.types.is_datetime64_any_dtype(loaded["date"])
    store.save_clean(clean.iloc[:100])  # tam değiştirme
    assert len(store.load_clean()) == 100
    store.clear()
    assert store.load_clean() is None


def test_container_uses_sql_store_when_requested(test_settings, demo_raw):
    from dataclasses import replace

    settings = replace(test_settings, price_store="sql")
    assert settings.price_store == "sql"
    container = build_container(settings, provider=FakeProvider(frame=demo_raw))
    assert isinstance(container.data.store, SqlPriceStore)
    container.data.refresh()
    assert container.data.status()["data_source"] == "fake"
    # Yeni container aynı veritabanından okur (kalıcılık)
    again = build_container(settings, provider=FakeProvider(frame=demo_raw))
    assert again.data.bundle().source == "fake"
