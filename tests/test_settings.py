"""Veritabanı adresi normalizasyonu (Neon/Supabase/Railway adresleri olduğu gibi yapıştırılabilir)."""

from src.stock_selection.settings import normalize_database_url


def test_postgres_urls_are_bound_to_psycopg_driver():
    assert normalize_database_url("postgresql://u:p@ep-x-pooler.neon.tech/neondb?sslmode=require", driver="psycopg") ==         "postgresql+psycopg://u:p@ep-x-pooler.neon.tech/neondb?sslmode=require"
    assert normalize_database_url("postgres://u:p@host/db", driver="pg8000").startswith("postgresql+pg8000://")
    assert normalize_database_url("postgres://u:p@host/db").split("://")[0] in ("postgresql+psycopg", "postgresql+pg8000")
    assert normalize_database_url("postgresql+psycopg://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
