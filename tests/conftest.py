"""Ortak test fixture'ları: sahte sağlayıcı, geçici cache ve SQLite."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.stock_selection.application import AppContainer, build_container
from src.stock_selection.data.providers.fake import FakeProvider
from src.stock_selection.demo import generate_demo_prices
from src.stock_selection.settings import PROJECT_ROOT, Settings

DEMO_END = date(2026, 9, 18)
SMALL_SYMBOLS = [
    "AKBNK.IS", "ASELS.IS", "BIMAS.IS", "EREGL.IS", "FROTO.IS", "GARAN.IS", "KCHOL.IS",
    "SAHOL.IS", "SISE.IS", "THYAO.IS", "TUPRS.IS", "TCELL.IS", "PGSUS.IS", "TOASO.IS",
    "ARCLK.IS", "MGROS.IS", "ENKAI.IS", "PETKM.IS", "ISCTR.IS", "YKBNK.IS",
]


def write_small_universe(path: Path, symbols: list[str] = SMALL_SYMBOLS) -> Path:
    lines = ["symbol,name,sector,effective_from,effective_to,source"]
    for i, symbol in enumerate(symbols):
        sector = "MALİ KURULUŞLAR" if i % 3 == 0 else ("İMALAT" if i % 3 == 1 else "")
        lines.append(f"{symbol},{symbol[:-3]} A.Ş.,{sector},2026-01-01,,test")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def demo_raw():
    """Sentetik ham tablo; testler kopyalayarak kullanır, yerinde değiştirmez."""
    return generate_demo_prices(SMALL_SYMBOLS, end=DEMO_END, years=2)


@pytest.fixture(scope="session")
def session_demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Temizlenmiş demo verisi oturum boyunca bir kez üretilip parquet olarak paylaşılır."""
    return tmp_path_factory.mktemp("demo")


@pytest.fixture
def test_settings(tmp_path: Path, session_demo_dir: Path) -> Settings:
    universe_csv = write_small_universe(tmp_path / "universe.csv")
    return Settings(
        project_root=PROJECT_ROOT,
        universe_csv=universe_csv,
        profiles_json=tmp_path / "profiles.json",
        cache_dir=tmp_path / "cache",
        demo_dir=session_demo_dir,
        database_url=f"sqlite:///{(tmp_path / 'state.db').as_posix()}",
        provider_name="fake",
        benchmark_symbol="XU100.IS",
        lookback_years=2,
        batch_size=5,
        max_retries=2,
        stale_days=7,
        auto_refresh_hours=0,  # testlerde arka plan yenileme kapalı
        price_store="sql",  # pyarrow'a bağımlı olmadan (SQLite tabloları)
        cors_origins=("http://localhost:3000",),
        quote_poll_seconds=0,  # testlerde arka plan fiyat yenileme kapalı
        secondary_provider="none",  # testlerde ikincil kaynak (ağ) kapalı
    )


@pytest.fixture
def container(test_settings: Settings, demo_raw) -> AppContainer:
    provider = FakeProvider(frame=demo_raw)
    return build_container(test_settings, provider=provider)
