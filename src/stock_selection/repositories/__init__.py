"""Kalıcı durum arayüzleri ve SQLite uygulaması.

Uygulama katmanı yalnızca ``base.py``'deki Protocol'leri kullanır. Yerel
MVP'de ``sqlite.py`` (SQLAlchemy) bu arayüzleri uygular; Supabase
PostgreSQL için aynı arayüzü uygulayan ikinci bir modül eklenebilir.
"""

from .base import (
    DataStatusRepository,
    PortfolioRecord,
    PortfolioRepository,
    ScoreRunRecord,
    ScoreRunRepository,
    ValuationRecord,
)
from .sqlite import SqlAlchemyUnitOfWork, create_engine_from_url

__all__ = [
    "DataStatusRepository",
    "PortfolioRecord",
    "PortfolioRepository",
    "ScoreRunRecord",
    "ScoreRunRepository",
    "SqlAlchemyUnitOfWork",
    "ValuationRecord",
    "create_engine_from_url",
]
