"""Repository sözleşmeleri (veritabanından bağımsız)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class ScoreRunRecord:
    id: str
    created_at: datetime
    profile_id: str
    weights: dict[str, float]
    data_as_of: str | None
    window_start: str | None
    normalization: dict[str, str]
    constant_policy: str
    model_version: str
    data_source: str
    universe_size: int
    scored_count: int
    excluded: dict[str, str]
    results: list[dict[str, Any]]
    warnings: list[str]
    persisted: bool = True


@dataclass
class CandidateRecord:
    id: str
    created_at: datetime
    score_run_id: str
    profile_id: str
    decision_date: str
    data_as_of: str | None
    payload: dict[str, Any]


@dataclass
class PortfolioRecord:
    id: str
    created_at: datetime
    name: str
    candidate_id: str
    score_run_id: str
    profile_id: str
    profile_weights: dict[str, float]
    model_version: str
    decision_date: str
    data_as_of: str | None
    data_source: str
    initial_capital: float
    status: str
    snapshot: dict[str, Any]
    activated_at: datetime | None = None


@dataclass
class ValuationRecord:
    id: str
    portfolio_id: str
    computed_at: datetime
    as_of: str | None
    metrics: dict[str, Any]
    series: list[dict[str, Any]]
    contributions: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    benchmark_available: bool = False


class DataStatusRepository(Protocol):
    def get(self) -> dict[str, Any] | None: ...
    def save(self, status: dict[str, Any]) -> None: ...


class ScoreRunRepository(Protocol):
    def add(self, record: ScoreRunRecord) -> None: ...
    def get(self, run_id: str) -> ScoreRunRecord | None: ...
    def latest(self, profile_id: str | None = None) -> ScoreRunRecord | None: ...
    def list(self, limit: int = 20) -> list[ScoreRunRecord]: ...


class CandidateRepository(Protocol):
    def add(self, record: CandidateRecord) -> None: ...
    def get(self, candidate_id: str) -> CandidateRecord | None: ...


class PortfolioRepository(Protocol):
    def add(self, record: PortfolioRecord) -> None: ...
    def get(self, portfolio_id: str) -> PortfolioRecord | None: ...
    def list(self) -> list[PortfolioRecord]: ...
    def update_status(self, portfolio_id: str, status: str, snapshot: dict[str, Any], activated_at: datetime | None) -> None: ...


class ValuationRepository(Protocol):
    def add(self, record: ValuationRecord) -> None: ...
    def latest(self, portfolio_id: str) -> ValuationRecord | None: ...


class UnitOfWork(Protocol):
    data_status: DataStatusRepository
    score_runs: ScoreRunRepository
    candidates: CandidateRepository
    portfolios: PortfolioRepository
    valuations: ValuationRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *args: object) -> None: ...
    def commit(self) -> None: ...
