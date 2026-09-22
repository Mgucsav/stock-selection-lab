"""Ortam değişkenlerinden okunan uygulama ayarları.

Yol ayarları yalnızca yerel MVP içindir; repository ve cache arayüzlerinin
arkasında kaldıkları için Supabase/PostgreSQL geçişinde bu dosya değişir,
çekirdek kod değişmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def pick_postgres_driver() -> str:
    """psycopg yüklenebiliyorsa onu, yoksa saf Python ``pg8000``'i seçer (DLL engeli olan makineler için)."""
    try:
        import psycopg  # noqa: F401

        return "psycopg"
    except Exception:
        return "pg8000"


def normalize_database_url(value: str, driver: str | None = None) -> str:
    """Neon/Supabase/Railway'in verdiği ``postgresql://`` veya ``postgres://`` adresini kullanılabilir sürücüye bağlar."""
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            return f"postgresql+{driver or pick_postgres_driver()}://" + value[len(prefix):]
    return value


def _default_database_url() -> str:
    value = os.environ.get("SSL_DATABASE_URL")
    if not value:
        return f"sqlite:///{(PROJECT_ROOT / 'state' / 'stock_selection.db').as_posix()}"
    value = normalize_database_url(value)
    if value.startswith("sqlite:///") and not value.startswith("sqlite:////"):
        raw = value.removeprefix("sqlite:///")
        path = Path(raw)
        if raw != ":memory:" and not path.is_absolute():
            return f"sqlite:///{(PROJECT_ROOT / path).resolve().as_posix()}"
    return value


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    """Çalışma zamanı ayarları; her alan ortam değişkeniyle ezilebilir."""

    project_root: Path = PROJECT_ROOT
    universe_csv: Path = field(
        default_factory=lambda: _env_path(
            "SSL_UNIVERSE_CSV", PROJECT_ROOT / "config" / "bist100_symbols.csv"
        )
    )
    profiles_json: Path = field(
        default_factory=lambda: _env_path(
            "SSL_PROFILES_JSON", PROJECT_ROOT / "config" / "profiles.json"
        )
    )
    cache_dir: Path = field(
        default_factory=lambda: _env_path("SSL_CACHE_DIR", PROJECT_ROOT / "data" / "cache")
    )
    demo_dir: Path = field(
        default_factory=lambda: _env_path("SSL_DEMO_DIR", PROJECT_ROOT / "data" / "demo")
    )
    database_url: str = field(default_factory=_default_database_url)
    # parquet (yerel dosya) | sql (veritabanı tabloları; bulut için) | auto (PostgreSQL ise sql, değilse parquet)
    price_store: str = field(default_factory=lambda: os.environ.get("SSL_PRICE_STORE", "auto"))
    provider_name: str = field(
        default_factory=lambda: os.environ.get("SSL_DATA_PROVIDER", "yahoo")
    )
    benchmark_symbol: str = field(
        default_factory=lambda: os.environ.get("SSL_BENCHMARK_SYMBOL", "XU100.IS")
    )
    lookback_years: int = field(default_factory=lambda: _env_int("SSL_LOOKBACK_YEARS", 3))
    batch_size: int = field(default_factory=lambda: _env_int("SSL_BATCH_SIZE", 25))
    max_retries: int = field(default_factory=lambda: _env_int("SSL_MAX_RETRIES", 3))
    stale_days: int = field(default_factory=lambda: _env_int("SSL_STALE_DAYS", 7))
    # Günlük veri bu kadar saatten eskiyse (veya demo modundaysa) backend arka planda kendisi yeniler; 0 = kapalı
    auto_refresh_hours: int = field(default_factory=lambda: _env_int("SSL_AUTO_REFRESH_HOURS", 20))
    # Gecikmeli fiyat anlık görüntüsünün arka planda yenilenme sıklığı (saniye); 0 = arka plan kapalı
    quote_poll_seconds: int = field(default_factory=lambda: _env_int("SSL_QUOTE_POLL_SECONDS", 45))
    # Borsa kapalıyken daha seyrek yenile
    quote_idle_poll_seconds: int = field(default_factory=lambda: _env_int("SSL_QUOTE_IDLE_POLL_SECONDS", 600))
    # Vercel önizleme adresleri gibi değişken alan adları için düzenli ifade (örn. https://.*\.vercel\.app)
    cors_origin_regex: str | None = field(default_factory=lambda: os.environ.get("SSL_CORS_ORIGIN_REGEX") or None)
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.environ.get(
                "SSL_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",")
            if origin.strip()
        )
    )


def load_settings() -> Settings:
    """``.env`` dosyasını (varsa) yükler ve ortamdan ``Settings`` üretir."""
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    return Settings()
