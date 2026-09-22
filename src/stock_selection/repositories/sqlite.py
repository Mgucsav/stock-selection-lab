"""SQLAlchemy tabanlı repository uygulaması (SQLite MVP; PostgreSQL uyumlu).

JSON sütunları hem SQLite hem PostgreSQL'de çalışır; SQLite'a özgü hiçbir
özellik kullanılmaz. ``database_url`` değiştirilerek Supabase PostgreSQL'e
bağlanılabilir.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .base import CandidateRecord, PortfolioRecord, ScoreRunRecord, ValuationRecord


class Base(DeclarativeBase):
    pass


class DataStatusRow(Base):
    __tablename__ = "data_status"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ScoreRunRow(Base):
    __tablename__ = "score_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON)
    data_as_of: Mapped[str | None] = mapped_column(String(10), nullable=True)
    window_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    normalization: Mapped[dict[str, Any]] = mapped_column(JSON)
    constant_policy: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(64))
    data_source: Mapped[str] = mapped_column(String(32))
    universe_size: Mapped[int] = mapped_column(Integer)
    scored_count: Mapped[int] = mapped_column(Integer)
    excluded: Mapped[dict[str, Any]] = mapped_column(JSON)
    results: Mapped[list[Any]] = mapped_column(JSON)
    warnings: Mapped[list[Any]] = mapped_column(JSON)


class CandidateRow(Base):
    __tablename__ = "portfolio_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    score_run_id: Mapped[str] = mapped_column(String(36), index=True)
    profile_id: Mapped[str] = mapped_column(String(64))
    decision_date: Mapped[str] = mapped_column(String(10))
    data_as_of: Mapped[str | None] = mapped_column(String(10), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class PortfolioRow(Base):
    __tablename__ = "portfolios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    name: Mapped[str] = mapped_column(String(128))
    candidate_id: Mapped[str] = mapped_column(String(36))
    score_run_id: Mapped[str] = mapped_column(String(36))
    profile_id: Mapped[str] = mapped_column(String(64))
    profile_weights: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(64))
    decision_date: Mapped[str] = mapped_column(String(10))
    data_as_of: Mapped[str | None] = mapped_column(String(10), nullable=True)
    data_source: Mapped[str] = mapped_column(String(32))
    initial_capital: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ValuationRow(Base):
    __tablename__ = "portfolio_valuations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(String(36), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    as_of: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    series: Mapped[list[Any]] = mapped_column(JSON)
    contributions: Mapped[list[Any]] = mapped_column(JSON)
    warnings: Mapped[list[Any]] = mapped_column(JSON)
    benchmark_available: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


def _json_default(value: Any) -> Any:
    """numpy/pandas/tarih türlerini JSON'a çevirir; JSON sütunları için ortak kural."""
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return None if np.isnan(number) else number
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"JSON'a çevrilemeyen tür: {type(value).__name__}")


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def create_engine_from_url(database_url: str) -> Engine:
    """Motoru oluşturur, SQLite ise dosya dizinini hazırlar ve tabloları kurar."""
    if database_url.startswith("sqlite:///"):
        path = database_url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    connect_args: dict[str, Any] = {}
    url_no_query = database_url.split("?", 1)[0]
    if database_url.startswith("postgresql+pg8000"):
        import ssl

        # pg8000 ``sslmode`` sorgu parametresini tanımaz; TLS bağlamı açıkça verilir (Supabase/Neon TLS ister).
        # Supabase veritabanı kendi kök CA'sını kullanır: SSL_DB_CA_CERT ya da config/supabase-ca-2021.crt varsa
        # onunla doğrulanır (OpenSSL 3 katı modunda bu CA reddedildiği için strict kapatılır).
        import os

        ca_file = os.environ.get("SSL_DB_CA_CERT") or str(Path(__file__).resolve().parents[3] / "config" / "supabase-ca-2021.crt")
        if Path(ca_file).exists():
            context = ssl.create_default_context(cafile=ca_file)
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        else:
            context = ssl.create_default_context()
        connect_args["ssl_context"] = context
        database_url = url_no_query
    engine = create_engine(database_url, future=True, json_serializer=json_dumps, connect_args=connect_args,
                           pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine


# ------------------------------------------------------------- repositories
class _DataStatusRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> dict[str, Any] | None:
        row = self.session.get(DataStatusRow, "current")
        return dict(row.payload) if row else None

    def save(self, status: dict[str, Any]) -> None:
        row = self.session.get(DataStatusRow, "current")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if row is None:
            self.session.add(DataStatusRow(key="current", payload=status, updated_at=now))
        else:
            row.payload = status
            row.updated_at = now


class _ScoreRunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_record(row: ScoreRunRow) -> ScoreRunRecord:
        return ScoreRunRecord(
            id=row.id, created_at=row.created_at, profile_id=row.profile_id, weights=dict(row.weights),
            data_as_of=row.data_as_of, window_start=row.window_start, normalization=dict(row.normalization),
            constant_policy=row.constant_policy, model_version=row.model_version, data_source=row.data_source,
            universe_size=row.universe_size, scored_count=row.scored_count, excluded=dict(row.excluded),
            results=list(row.results), warnings=list(row.warnings),
        )

    def add(self, record: ScoreRunRecord) -> None:
        self.session.add(
            ScoreRunRow(
                id=record.id, created_at=record.created_at, profile_id=record.profile_id, weights=record.weights,
                data_as_of=record.data_as_of, window_start=record.window_start, normalization=record.normalization,
                constant_policy=record.constant_policy, model_version=record.model_version,
                data_source=record.data_source, universe_size=record.universe_size, scored_count=record.scored_count,
                excluded=record.excluded, results=record.results, warnings=record.warnings,
            )
        )

    def get(self, run_id: str) -> ScoreRunRecord | None:
        row = self.session.get(ScoreRunRow, run_id)
        return self._to_record(row) if row else None

    def latest(self, profile_id: str | None = None) -> ScoreRunRecord | None:
        stmt = select(ScoreRunRow).order_by(ScoreRunRow.created_at.desc())
        if profile_id:
            stmt = stmt.where(ScoreRunRow.profile_id == profile_id)
        row = self.session.scalars(stmt.limit(1)).first()
        return self._to_record(row) if row else None

    def list(self, limit: int = 20) -> list[ScoreRunRecord]:
        rows = self.session.scalars(select(ScoreRunRow).order_by(ScoreRunRow.created_at.desc()).limit(limit)).all()
        return [self._to_record(r) for r in rows]


class _CandidateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: CandidateRecord) -> None:
        self.session.add(
            CandidateRow(
                id=record.id, created_at=record.created_at, score_run_id=record.score_run_id,
                profile_id=record.profile_id, decision_date=record.decision_date, data_as_of=record.data_as_of,
                payload=record.payload,
            )
        )

    def get(self, candidate_id: str) -> CandidateRecord | None:
        row = self.session.get(CandidateRow, candidate_id)
        if row is None:
            return None
        return CandidateRecord(
            id=row.id, created_at=row.created_at, score_run_id=row.score_run_id, profile_id=row.profile_id,
            decision_date=row.decision_date, data_as_of=row.data_as_of, payload=dict(row.payload),
        )


class _PortfolioRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_record(row: PortfolioRow) -> PortfolioRecord:
        return PortfolioRecord(
            id=row.id, created_at=row.created_at, name=row.name, candidate_id=row.candidate_id,
            score_run_id=row.score_run_id, profile_id=row.profile_id, profile_weights=dict(row.profile_weights),
            model_version=row.model_version, decision_date=row.decision_date, data_as_of=row.data_as_of,
            data_source=row.data_source, initial_capital=row.initial_capital, status=row.status,
            snapshot=dict(row.snapshot), activated_at=row.activated_at,
        )

    def add(self, record: PortfolioRecord) -> None:
        self.session.add(
            PortfolioRow(
                id=record.id, created_at=record.created_at, name=record.name, candidate_id=record.candidate_id,
                score_run_id=record.score_run_id, profile_id=record.profile_id, profile_weights=record.profile_weights,
                model_version=record.model_version, decision_date=record.decision_date, data_as_of=record.data_as_of,
                data_source=record.data_source, initial_capital=record.initial_capital, status=record.status,
                snapshot=record.snapshot, activated_at=record.activated_at,
            )
        )

    def get(self, portfolio_id: str) -> PortfolioRecord | None:
        row = self.session.get(PortfolioRow, portfolio_id)
        return self._to_record(row) if row else None

    def list(self) -> list[PortfolioRecord]:
        rows = self.session.scalars(select(PortfolioRow).order_by(PortfolioRow.created_at.desc())).all()
        return [self._to_record(r) for r in rows]

    def update_status(self, portfolio_id: str, status: str, snapshot: dict[str, Any], activated_at: datetime | None) -> None:
        row = self.session.get(PortfolioRow, portfolio_id)
        if row is None:
            raise KeyError(portfolio_id)
        row.status = status
        row.snapshot = snapshot
        row.activated_at = activated_at


class _ValuationRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: ValuationRecord) -> None:
        self.session.add(
            ValuationRow(
                id=record.id, portfolio_id=record.portfolio_id, computed_at=record.computed_at, as_of=record.as_of,
                metrics=record.metrics, series=record.series, contributions=record.contributions,
                warnings=record.warnings, benchmark_available=record.benchmark_available,
            )
        )

    def latest(self, portfolio_id: str) -> ValuationRecord | None:
        row = self.session.scalars(
            select(ValuationRow).where(ValuationRow.portfolio_id == portfolio_id)
            .order_by(ValuationRow.computed_at.desc()).limit(1)
        ).first()
        if row is None:
            return None
        return ValuationRecord(
            id=row.id, portfolio_id=row.portfolio_id, computed_at=row.computed_at, as_of=row.as_of,
            metrics=dict(row.metrics), series=list(row.series), contributions=list(row.contributions),
            warnings=list(row.warnings), benchmark_available=bool(row.benchmark_available),
        )


class SqlAlchemyUnitOfWork:
    """Tek oturumda bütün repository'leri sunan iş birimi."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = Session(self.engine, expire_on_commit=False)
        self.data_status = _DataStatusRepo(self.session)
        self.score_runs = _ScoreRunRepo(self.session)
        self.candidates = _CandidateRepo(self.session)
        self.portfolios = _PortfolioRepo(self.session)
        self.valuations = _ValuationRepo(self.session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        if exc_type is not None:
            self.session.rollback()
        self.session.close()
        self.session = None

    def commit(self) -> None:
        assert self.session is not None
        self.session.commit()
