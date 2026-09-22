"""Uygulama servisleri: veri, sıralama, portföy ve takip akışları.

FastAPI katmanı yalnızca bu modüldeki servisleri çağırır. Servisler
repository/cache arayüzlerine bağlıdır; SQLite ve yerel dosya sistemi
ayrıntıları burada görünmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
import threading
import time
from typing import Any, Callable
import uuid

import pandas as pd

from . import MODEL_VERSION
from .data.cache import ParquetPriceCache, PriceStore
from .data.sql_store import SqlPriceStore
from .data.cleaning import CleaningResult, clean_raw_prices, pivot_field
from .data.providers.base import INTRADAY_LIMITS, FetchOutcome, MarketDataProvider, Quote
from .data.providers.fake import FakeProvider
from .data.providers.yahoo import YahooFinanceProvider
from .demo import DEMO_SOURCE, generate_demo_prices
from .features.criteria import CriteriaResult, compute_criteria
from .fuzzy.fpfs import CRITERIA_COLUMNS, evaluate_fpfs
from .fuzzy.membership import ConstantColumnPolicy, build_memberships
from .fuzzy.profiles import InvestorProfile, load_profiles, validate_weights
from .portfolio.builder import PortfolioCandidate, build_candidate
from .repositories.base import CandidateRecord, PortfolioRecord, ScoreRunRecord, ValuationRecord
from .repositories.sqlite import SqlAlchemyUnitOfWork, create_engine_from_url
from .settings import Settings, load_settings
from .tracking.snapshot import PositionSnapshot, allocate_lots, resolve_entry_prices
from .tracking.valuation import valuation_series
from .universe import Universe, load_universe, save_universe_csv_text

logger = logging.getLogger(__name__)

DATA_LABEL = "Günlük/gecikmeli veri"
QUOTE_LABEL = "Gecikmeli fiyat (≈15 dk, Yahoo Finance)"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class NotFoundError(LookupError):
    pass


class DataUnavailableError(RuntimeError):
    pass


def _cleaning_from_clean(clean: pd.DataFrame, reference_date: date, stale_days: int) -> CleaningResult:
    """Önceden temizlenmiş (ret içermeyen) tablo için hafif kalite özeti üretir."""
    from .data.cleaning import SymbolQuality

    quality: dict[str, SymbolQuality] = {}
    reference = pd.Timestamp(reference_date)
    for symbol, sub in clean.groupby("symbol"):
        first, last = sub["date"].min(), sub["date"].max()
        expected = len(pd.bdate_range(first, last))
        missing_ratio = max(0.0, 1.0 - len(sub) / expected) if expected else 0.0
        quality[str(symbol)] = SymbolQuality(str(symbol), len(sub), 0, first.date(), last.date(), missing_ratio,
                                             bool((reference - last).days > stale_days), [])
    report = {"raw_rows": len(clean), "clean_rows": len(clean), "rejected_rows": 0, "exact_duplicate_rows": 0,
              "rejection_rate": 0.0, "reasons": {}}
    return CleaningResult(clean, pd.DataFrame(), pd.DataFrame(), report, quality, [])


# ================================================================== data
@dataclass
class DataBundle:
    clean: pd.DataFrame
    benchmark: pd.DataFrame | None
    source: str
    status: dict[str, Any]


class MarketDataService:
    """Ham veri indirme, temizleme, cache ve durum kaydı."""

    def __init__(
        self,
        settings: Settings,
        universe_loader: Callable[[], Universe],
        provider: MarketDataProvider,
        store: PriceStore,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    ) -> None:
        self.settings = settings
        self._universe_loader = universe_loader
        self.provider = provider
        self.store = store
        self.uow_factory = uow_factory
        self._bundle: DataBundle | None = None

    # ----------------------------------------------------------- universe
    def universe(self) -> Universe:
        return self._universe_loader()

    # ------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        """Kayıtlı durum yalnızca yüklü verinin kaynağıyla eşleşiyorsa geçerlidir; aksi hâlde gerçek durum."""
        bundle = self.bundle()
        with self.uow_factory() as uow:
            saved = uow.data_status.get()
        if saved and saved.get("data_source") == bundle.source:
            return saved
        return bundle.status

    def _demo_status_placeholder(self) -> dict[str, Any]:
        return {
            "data_source": DEMO_SOURCE,
            "is_demo": True,
            "provider": self.provider.name,
            "data_label": DATA_LABEL,
            "last_refresh_at": None,
            "last_success_at": None,
            "last_error": None,
            "universe_size": 0,
            "ok_count": 0,
            "failed_count": 0,
            "symbol_statuses": [],
            "date_range": None,
            "warnings": ["Cache boş; deterministik demo verisi kullanılıyor."],
        }

    def _save_status(self, status: dict[str, Any]) -> None:
        with self.uow_factory() as uow:
            uow.data_status.save(status)
            uow.commit()

    # --------------------------------------------------------------- load
    def bundle(self) -> DataBundle:
        if self._bundle is not None:
            return self._bundle
        clean = self.store.load_clean()
        if clean is not None and not clean.empty:
            benchmark = self.store.load_benchmark()
            with self.uow_factory() as uow:
                saved = uow.data_status.get()
            source = str(clean["source"].iloc[0])
            status = saved or dict(self._demo_status_placeholder(), data_source=source, is_demo=source == DEMO_SOURCE,
                                   warnings=["Cache dolu ancak durum kaydı yok; veriyi yenileyin."])
            self._bundle = DataBundle(clean, benchmark, str(status.get("data_source", source)), status)
            return self._bundle
        return self._load_demo()

    def _load_demo(self) -> DataBundle:
        universe = self.universe()
        end = date.today() - timedelta(days=1)
        cleaned = self._demo_cleaned(universe.symbols, end)
        benchmark = cleaned.clean.loc[cleaned.clean["symbol"] == self.settings.benchmark_symbol].copy()
        clean = cleaned.clean.loc[cleaned.clean["symbol"] != self.settings.benchmark_symbol].copy()
        status = self._build_status(universe, cleaned, DEMO_SOURCE, ok=universe.symbols, failed=[], benchmark_ok=not benchmark.empty,
                                    error=None, refreshed_at=None, success_at=None,
                                    extra_warnings=["Demo modu: sentetik, deterministik veri. Canlı veri değildir."])
        self._bundle = DataBundle(clean, benchmark, DEMO_SOURCE, status)
        return self._bundle

    def _demo_cleaned(self, symbols: list[str], end: date) -> CleaningResult:
        """Demo verisini üretir ve temizler; sonuç günlük anahtarla data/demo altında önbelleklenir."""
        import hashlib

        key = hashlib.sha1(
            f"{','.join(symbols)}|{end.isoformat()}|{self.settings.lookback_years}|{self.settings.benchmark_symbol}".encode()
        ).hexdigest()[:12]
        demo_dir = self.settings.demo_dir
        cache_file = demo_dir / f"demo_clean_{key}.pkl"
        if cache_file.exists():
            try:
                cached = pd.read_pickle(cache_file)
                cached["date"] = pd.to_datetime(cached["date"])
                return _cleaning_from_clean(cached, date.today(), self.settings.stale_days)
            except Exception as error:  # bozuk cache → yeniden üret
                logger.warning("Demo cache okunamadı, yeniden üretiliyor: %s", error)
        raw = generate_demo_prices(symbols, end=end, years=self.settings.lookback_years,
                                   benchmark_symbol=self.settings.benchmark_symbol)
        cleaned = clean_raw_prices(raw, reference_date=date.today(), stale_days=self.settings.stale_days)
        try:
            demo_dir.mkdir(parents=True, exist_ok=True)
            for stale in demo_dir.glob("demo_clean_*"):
                stale.unlink(missing_ok=True)
            cleaned.clean.to_pickle(cache_file)
        except Exception as error:  # cache yazılamazsa çalışmaya devam et
            logger.warning("Demo cache yazılamadı: %s", error)
        return cleaned

    def _build_status(
        self, universe: Universe, cleaned: CleaningResult, source: str, ok: list[str], failed: list[dict[str, Any]] | list[str],
        benchmark_ok: bool, error: str | None, refreshed_at: datetime | None, success_at: datetime | None,
        extra_warnings: list[str] | None = None, provider_statuses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        clean = cleaned.clean
        stock_clean = clean.loc[clean["symbol"] != self.settings.benchmark_symbol] if not clean.empty else clean
        date_range = None
        coverage_warnings: list[str] = []
        if not stock_clean.empty:
            last_date = stock_clean["date"].max()
            date_range = {"start": _iso(stock_clean["date"].min()), "end": _iso(last_date)}
            # Son işlem günü kısmi olabilir (sağlayıcı bazı sembolleri geç/eksik verir); gizleme, uyar.
            last_count = int((stock_clean["date"] == last_date).sum())
            symbol_count = int(stock_clean["symbol"].nunique())
            if symbol_count and last_count < 0.8 * symbol_count:
                coverage_warnings.append(
                    f"Son veri günü ({_iso(last_date)}) kısmi: {last_count}/{symbol_count} sembolde geçerli kapanış var; "
                    "diğer semboller için son geçerli gün kullanılır."
                )
        quality = {s: q.to_dict() for s, q in cleaned.symbol_quality.items()}
        symbol_statuses: list[dict[str, Any]] = []
        provider_map = {s["symbol"]: s for s in (provider_statuses or [])}
        for member in universe.members:
            ps = provider_map.get(member.symbol)
            q = quality.get(member.symbol)
            outcome = ps["outcome"] if ps else ("ok" if q else "no_data")
            symbol_statuses.append(
                {
                    "symbol": member.symbol,
                    "name": member.name,
                    "sector": member.sector,
                    "outcome": outcome,
                    "message": ps["message"] if ps else "",
                    "clean_rows": q["clean_rows"] if q else 0,
                    "rejected_rows": q["rejected_rows"] if q else 0,
                    "first_date": q["first_date"] if q else None,
                    "last_date": q["last_date"] if q else None,
                    "is_stale": q["is_stale"] if q else False,
                    "missing_ratio": q["missing_ratio"] if q else None,
                    "dividends_available": ps["dividends_available"] if ps else (source == DEMO_SOURCE),
                    "warnings": q["warnings"] if q else [],
                }
            )
        ok_count = sum(1 for s in symbol_statuses if s["outcome"] == "ok" and s["clean_rows"] > 0)
        failed_count = len(symbol_statuses) - ok_count
        warnings = list(universe.warnings) + list(cleaned.warnings) + coverage_warnings + list(extra_warnings or [])
        if not benchmark_ok:
            warnings.append(f"Benchmark {self.settings.benchmark_symbol} verisi bulunamadı; BIST 100 karşılaştırması devre dışı.")
        return {
            "data_source": source,
            "is_demo": source == DEMO_SOURCE,
            "provider": self.provider.name,
            "data_label": DATA_LABEL,
            "last_refresh_at": refreshed_at.isoformat() if refreshed_at else None,
            "last_success_at": success_at.isoformat() if success_at else None,
            "last_error": error,
            "universe_size": len(universe.members),
            "universe_complete": universe.is_complete,
            "universe_as_of": _iso(universe.effective_from),
            "universe_sources": universe.sources,
            "ok_count": ok_count,
            "failed_count": failed_count,
            "stale_symbols": [s["symbol"] for s in symbol_statuses if s["is_stale"]],
            "missing_symbols": [s["symbol"] for s in symbol_statuses if s["outcome"] != "ok" or s["clean_rows"] == 0],
            "benchmark_symbol": self.settings.benchmark_symbol,
            "benchmark_available": benchmark_ok,
            "symbol_statuses": symbol_statuses,
            "date_range": date_range,
            "quality_report": {k: v for k, v in cleaned.report.items() if k != "by_symbol"},
            "warnings": warnings,
        }

    # ------------------------------------------------------------ refresh
    def refresh(self, lookback_years: int | None = None) -> dict[str, Any]:
        """Sağlayıcıdan veri çeker; başarısızlık gizlenmez, demo veri sessizce kullanılmaz."""
        universe = self.universe()
        years = lookback_years or self.settings.lookback_years
        end = date.today()
        start = end - timedelta(days=365 * years + 7)
        refreshed_at = _now()
        symbols = universe.symbols + [self.settings.benchmark_symbol]
        try:
            result = self.provider.fetch_daily(symbols, start, end)
        except Exception as error:  # sağlayıcı bütünüyle çöktü
            previous = self.status()
            previous.update({"last_refresh_at": refreshed_at.isoformat(), "last_error": f"Sağlayıcı hatası: {error}"})
            previous.setdefault("warnings", []).append("Canlı veri yenileme başarısız oldu; mevcut veri korunuyor.")
            self._save_status(previous)
            raise DataUnavailableError(str(error)) from error

        provider_statuses = [s.to_dict() for s in result.statuses]
        ok_stock = [s.symbol for s in result.statuses if s.outcome == FetchOutcome.OK and s.symbol != self.settings.benchmark_symbol]
        if not ok_stock:
            previous = self.status()
            message = "Hiçbir sembol için veri alınamadı."
            previous.update({"last_refresh_at": refreshed_at.isoformat(), "last_error": message,
                             "symbol_statuses_provider": provider_statuses})
            previous.setdefault("warnings", []).append("Canlı veri yenileme başarısız oldu; mevcut veri korunuyor.")
            self._save_status(previous)
            raise DataUnavailableError(message)

        raw_frame, session_warnings = self._drop_open_session(result.frame)
        raw_frame, backfill_warnings = self._backfill_recent_days(raw_frame)
        backfill_warnings = session_warnings + backfill_warnings
        cleaned = clean_raw_prices(raw_frame, reference_date=end, stale_days=self.settings.stale_days)
        benchmark = cleaned.clean.loc[cleaned.clean["symbol"] == self.settings.benchmark_symbol].copy()
        clean = cleaned.clean.loc[cleaned.clean["symbol"] != self.settings.benchmark_symbol].copy()
        self.store.save_raw(raw_frame)
        self.store.save_clean(clean)
        self.store.save_benchmark(benchmark)

        status = self._build_status(
            universe, cleaned, result.provider, ok=ok_stock, failed=[], benchmark_ok=not benchmark.empty,
            error=None, refreshed_at=refreshed_at, success_at=refreshed_at, provider_statuses=provider_statuses,
            extra_warnings=backfill_warnings,
        )
        self._save_status(status)
        self._bundle = DataBundle(clean, benchmark, result.provider, status)
        return status

    @staticmethod
    def _drop_open_session(raw: pd.DataFrame, now: datetime | None = None) -> tuple[pd.DataFrame, list[str]]:
        """Seans kapanmadan (İstanbul 18:30 öncesi) bugünün satırını dışlar: yarım gün kapanış sayılmaz."""
        if raw is None or raw.empty:
            return raw, []
        from zoneinfo import ZoneInfo

        local_now = now or datetime.now(ZoneInfo("Europe/Istanbul"))
        if local_now.hour > 18 or (local_now.hour == 18 and local_now.minute >= 30):
            return raw, []
        today = pd.Timestamp(local_now.date())
        dates = pd.to_datetime(raw["date"]).dt.normalize()
        mask = dates >= today
        if not mask.any():
            return raw, []
        return raw.loc[~mask].copy(), [
            f"Seans sürüyor: {today.date().isoformat()} tarihli {int(mask.sum())} tamamlanmamış günlük satır dışlandı; "
            "gün sonu kapanışı 18:30'dan sonraki yenilemede alınır (gün içi fiyatlar ayrıca akar)."
        ]

    def _backfill_recent_days(self, raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Yahoo günlük seride son günleri NaN/eksik verdiğinde saatlik barlardan günlük OHLCV türetir.

        Yalnızca son 5 işlem günü penceresinde eksik olan (symbol, date) çiftleri
        doldurulur; ``adj_close = close`` alınır (o günler için kurumsal
        işlem düzeltmesi zaten yoktur), temettü sütunu boş bırakılır.
        """
        if raw is None or raw.empty or not hasattr(self.provider, "fetch_intraday"):
            return raw, []
        frame = raw.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        valid = frame.loc[pd.to_numeric(frame["close"], errors="coerce") > 0]
        if valid.empty:
            return raw, []
        latest = valid["date"].max().normalize()
        last_valid = valid.groupby("symbol")["date"].max()
        valid_keys = set(zip(valid["symbol"], valid["date"].dt.normalize()))
        window_start = latest - pd.Timedelta(days=7)
        recent_days = sorted(valid.loc[valid["date"] >= window_start, "date"].dt.normalize().unique())
        # Son 5 işlem günü penceresinde herhangi bir günü eksik olan semboller
        lagging = sorted({s for s in last_valid.index for d in recent_days if (s, d) not in valid_keys})
        if not lagging:
            return raw, []
        try:
            hourly = self.provider.fetch_intraday(lagging, "1h", "5d")
        except Exception as error:
            return raw, [f"Eksik son günler saatlik veriyle tamamlanamadı: {error}"]
        if hourly.empty:
            return raw, ["Eksik son günler için saatlik veri alınamadı."]
        hourly = hourly.copy()
        hourly["day"] = hourly["datetime"].dt.normalize()
        grouped = hourly.groupby(["symbol", "day"]).agg(
            open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")
        ).reset_index()
        ingested = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        for r in grouped.itertuples(index=False):
            if (r.symbol, r.day) in valid_keys or r.day > latest or r.day < window_start:
                continue
            if not (r.close and r.close > 0):
                continue
            rows.append({
                "date": r.day, "symbol": r.symbol, "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                "adj_close": r.close, "volume": r.volume, "dividends": float("nan"), "source": self.provider.name,
                "ingested_at": ingested,
            })
        if not rows:
            return raw, []
        filled = pd.DataFrame(rows)
        keys = set(zip(filled["symbol"], filled["date"]))
        # Aynı (symbol, date) için NaN'lı günlük satır varsa onu düşür; doldurulan satır yerine geçer
        drop_mask = [(sym, dt) in keys for sym, dt in zip(frame["symbol"], frame["date"])]
        frame = frame.loc[[not m for m in drop_mask]]
        merged = pd.concat([frame, filled], ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
        merged = merged.loc[:, raw.columns]
        return merged, [f"{len(filled)} sembol-gün Yahoo günlük seride eksikti; saatlik barlardan günlük OHLCV türetildi."]

    def replace_universe(self, csv_text: str) -> Universe:
        universe = save_universe_csv_text(csv_text, self.settings.universe_csv)
        self._bundle = None
        return universe


# ================================================================ ranking
class RankingService:
    def __init__(self, data: MarketDataService, profiles: dict[str, InvestorProfile], uow_factory, settings: Settings) -> None:
        self.data = data
        self.profiles = profiles
        self.uow_factory = uow_factory
        self.settings = settings

    def _criteria(self, as_of: date | None) -> CriteriaResult:
        bundle = self.data.bundle()
        return compute_criteria(bundle.clean, as_of=as_of, lookback_days=365 * self.settings.lookback_years)

    def run(
        self,
        profile_id: str | None = None,
        weights: dict[str, float] | None = None,
        as_of: date | None = None,
        persist: bool = True,
        constant_policy: str = ConstantColumnPolicy.NEUTRAL.value,
    ) -> ScoreRunRecord:
        if weights is None:
            if profile_id is None or profile_id not in self.profiles:
                raise ValueError("Geçerli bir profil ya da ağırlık kümesi verilmelidir.")
            weights = dict(self.profiles[profile_id].weights)
            effective_profile = profile_id
        else:
            weights = validate_weights(weights)
            effective_profile = profile_id or "custom"

        bundle = self.data.bundle()
        universe = self.data.universe()
        criteria = self._criteria(as_of)
        if criteria.table.empty:
            raise DataUnavailableError("Sıralama için yeterli veri yok. " + " ".join(criteria.warnings))
        membership = build_memberships(criteria.table, constant_policy=constant_policy)
        fpfs = evaluate_fpfs(membership.frame, weights)

        names = universe.name_map
        sectors = universe.sector_map
        results: list[dict[str, Any]] = []
        for symbol, row in fpfs.scores.iterrows():
            crit = criteria.table.loc[symbol]
            mem = membership.frame.loc[symbol]
            results.append(
                {
                    "symbol": symbol,
                    "name": names.get(symbol, symbol),
                    "sector": sectors.get(symbol),
                    "rank": int(row["rank"]),
                    "cce10": float(row["cce10"]),
                    "fss": float(row["fss"]),
                    "fss_rank": int(row["fss_rank"]),
                    "drf": float(row["drf"]),
                    "drf_rank": int(row["drf_rank"]),
                    "dmf": float(row["dmf"]),
                    "dmf_rank": int(row["dmf_rank"]),
                    "rank_delta_vs_fss": int(row["rank_delta_vs_fss"]),
                    "membership": {c: float(mem[c]) for c in CRITERIA_COLUMNS},
                    "criteria": {
                        "return": float(crit["return"]),
                        "annualized_return": float(crit["annualized_return"]),
                        "dividend": float(crit["dividend"]),
                        "dividend_status": str(crit["dividend_status"]),
                        "liquidity": float(crit["liquidity"]),
                        "risk": float(crit["risk"]),
                        "observations": int(crit["observations"]),
                        "last_close": float(crit["last_close"]),
                    },
                }
            )
        record = ScoreRunRecord(
            id=str(uuid.uuid4()),
            created_at=_now(),
            profile_id=effective_profile,
            weights=weights,
            data_as_of=_iso(criteria.as_of),
            window_start=_iso(criteria.window_start),
            normalization=dict(membership.methods),
            constant_policy=membership.constant_policy,
            model_version=MODEL_VERSION,
            data_source=bundle.source,
            universe_size=len(universe.members),
            scored_count=len(results),
            excluded=dict(criteria.excluded),
            results=results,
            warnings=list(criteria.warnings) + list(membership.warnings) + list(fpfs.warnings),
            persisted=persist,
        )
        if persist:
            with self.uow_factory() as uow:
                uow.score_runs.add(record)
                uow.commit()
        return record

    def latest(self, profile_id: str | None = None) -> ScoreRunRecord | None:
        with self.uow_factory() as uow:
            return uow.score_runs.latest(profile_id)

    def get(self, run_id: str) -> ScoreRunRecord | None:
        with self.uow_factory() as uow:
            return uow.score_runs.get(run_id)


# ============================================================== portfolio
class PortfolioService:
    def __init__(self, data: MarketDataService, ranking: RankingService, profiles: dict[str, InvestorProfile], uow_factory, settings: Settings) -> None:
        self.data = data
        self.ranking = ranking
        self.profiles = profiles
        self.uow_factory = uow_factory
        self.settings = settings

    def generate(self, capital: float, decision_date: date | None = None, profile_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Her profil için sıralama çalıştırır ve aday portföyleri kaydeder."""
        if capital <= 0:
            raise ValueError("Sermaye pozitif olmalıdır.")
        bundle = self.data.bundle()
        universe = self.data.universe()
        clean = bundle.clean
        latest_date = pd.to_datetime(clean["date"]).max().date()
        decision = decision_date or latest_date
        if decision > latest_date:
            raise ValueError(f"Karar tarihi veri tarihinden ({latest_date.isoformat()}) sonra olamaz.")
        criteria = self.ranking._criteria(decision)
        if criteria.table.empty:
            raise DataUnavailableError("Portföy için yeterli veri yok.")
        adj_wide = pivot_field(clean.loc[pd.to_datetime(clean["date"]) <= pd.Timestamp(decision)], "adj_close")

        outputs: list[dict[str, Any]] = []
        ids = profile_ids or list(self.profiles)
        with self.uow_factory() as uow:
            for pid in ids:
                profile = self.profiles[pid]
                run = self.ranking.run(profile_id=pid, as_of=decision, persist=True)
                scores = pd.DataFrame(run.results).set_index("symbol")
                candidate = build_candidate(
                    profile, scores, criteria.table, adj_wide, sector_map=universe.sector_map,
                    name_map=universe.name_map, as_of=decision, lookback_days=365 * self.settings.lookback_years,
                )
                payload = self._candidate_payload(candidate, run, capital, decision)
                record = CandidateRecord(
                    id=str(uuid.uuid4()), created_at=_now(), score_run_id=run.id, profile_id=pid,
                    decision_date=decision.isoformat(), data_as_of=run.data_as_of, payload=payload,
                )
                uow.candidates.add(record)
                payload = dict(payload, candidate_id=record.id, score_run_id=run.id)
                outputs.append(payload)
            uow.commit()
        return outputs

    @staticmethod
    def _candidate_payload(candidate: PortfolioCandidate, run: ScoreRunRecord, capital: float, decision: date) -> dict[str, Any]:
        return {
            "profile_id": candidate.profile_id,
            "profile_label": candidate.profile_label,
            "profile_weights": candidate.profile_weights,
            "weighting_scheme": candidate.weighting_scheme,
            "max_weight": candidate.max_weight,
            "size": candidate.size,
            "holdings": candidate.holdings,
            "weights": candidate.weights,
            "average_score": candidate.average_score,
            "stats": candidate.stats,
            "sector_exposure": candidate.sector_exposure,
            "warnings": candidate.warnings,
            "capital": capital,
            "decision_date": decision.isoformat(),
            "data_as_of": run.data_as_of,
            "data_source": run.data_source,
            "model_version": run.model_version,
        }

    def select(self, candidate_id: str, initial_capital: float | None = None, name: str | None = None) -> PortfolioRecord:
        with self.uow_factory() as uow:
            candidate = uow.candidates.get(candidate_id)
            if candidate is None:
                raise NotFoundError(f"Aday portföy bulunamadı: {candidate_id}")
            run = uow.score_runs.get(candidate.score_run_id)
        payload = candidate.payload
        capital = float(initial_capital or payload["capital"])
        if capital <= 0:
            raise ValueError("Başlangıç sermayesi pozitif olmalıdır.")
        decision = date.fromisoformat(candidate.decision_date)
        record = PortfolioRecord(
            id=str(uuid.uuid4()),
            created_at=_now(),
            name=name or f"{payload['profile_label']} model portföy",
            candidate_id=candidate.id,
            score_run_id=candidate.score_run_id,
            profile_id=candidate.profile_id,
            profile_weights=dict(payload["profile_weights"]),
            model_version=payload["model_version"],
            decision_date=candidate.decision_date,
            data_as_of=candidate.data_as_of,
            data_source=payload["data_source"],
            initial_capital=capital,
            status="pending",
            snapshot={
                "target_weights": payload["weights"],
                "holdings": payload["holdings"],
                "positions": [],
                "cash": capital,
                "entry_pending": list(payload["weights"]),
                "run_warnings": run.warnings if run else [],
            },
        )
        record = self._try_activate(record)
        with self.uow_factory() as uow:
            uow.portfolios.add(record)
            uow.commit()
        return record

    def _try_activate(self, record: PortfolioRecord) -> PortfolioRecord:
        """Karar tarihinden sonraki ilk işlem günü oluşmuşsa giriş fiyatlarını kilitler."""
        if record.status == "active":
            return record
        bundle = self.data.bundle()
        if record.data_source != bundle.source:
            # Demo veriyle kurulan portföy canlı veriyle (veya tersi) aktive edilmez; kaynaklar karışmaz.
            record.snapshot = dict(
                record.snapshot,
                source_mismatch=f"Portföy '{record.data_source}' verisiyle oluşturuldu; mevcut veri kaynağı '{bundle.source}'. "
                "Kaynaklar karıştırılmadı; canlı veriyle yeni bir model portföy oluşturun.",
            )
            return record
        weights: dict[str, float] = dict(record.snapshot["target_weights"])
        entries = resolve_entry_prices(bundle.clean, list(weights), date.fromisoformat(record.decision_date))
        pending = [s for s, e in entries.items() if e is None]
        if pending:
            record.snapshot = dict(record.snapshot, entry_pending=pending, positions=[], cash=record.initial_capital)
            record.status = "pending"
            return record
        positions, cash = allocate_lots(record.initial_capital, weights, entries)
        record.snapshot = dict(
            record.snapshot,
            positions=[p.to_dict() for p in positions],
            cash=cash,
            entry_pending=[],
            invested=record.initial_capital - cash,
            entry_date=max(p.entry_date for p in positions if p.entry_date).isoformat(),
        )
        record.status = "active"
        record.activated_at = _now()
        return record

    def list(self) -> list[PortfolioRecord]:
        with self.uow_factory() as uow:
            return uow.portfolios.list()

    def get(self, portfolio_id: str) -> PortfolioRecord:
        with self.uow_factory() as uow:
            record = uow.portfolios.get(portfolio_id)
        if record is None:
            raise NotFoundError(f"Portföy bulunamadı: {portfolio_id}")
        return record

    def latest_valuation(self, portfolio_id: str) -> ValuationRecord | None:
        with self.uow_factory() as uow:
            return uow.valuations.latest(portfolio_id)

    def live_valuation(self, portfolio_id: str, quotes: "QuoteService") -> dict[str, Any]:
        """Gecikmeli son fiyatlarla anlık portföy değeri; resmi (gün sonu) değerlemeden ayrıdır."""
        record = self.get(portfolio_id)
        base = {"portfolio_id": record.id, "status": record.status, "label": QUOTE_LABEL,
                "is_demo": record.data_source == DEMO_SOURCE}
        if record.status != "active":
            return dict(base, available=False, message="Portföy beklemede; giriş fiyatı oluşmadan canlı değer hesaplanamaz.", positions=[], warnings=[])
        if not quotes.enabled:
            return dict(base, available=False, message="Demo modunda canlı fiyat yok; Veri Sağlığı'ndan canlı veriyi yenileyin.", positions=[], warnings=[])
        if record.data_source != self.data.bundle().source:
            return dict(base, available=False, message="Portföy demo veriyle oluşturuldu; canlı fiyatla değerlenmez. Canlı veriyle yeni portföy oluşturun.", positions=[], warnings=[])
        positions = record.snapshot.get("positions", [])
        symbols = [p["symbol"] for p in positions]
        quote_list, from_cache = quotes.quotes(symbols)
        by_symbol = {q.symbol: q for q in quote_list}
        cash = float(record.snapshot.get("cash", 0.0))
        rows: list[dict[str, Any]] = []
        value = cash
        day_change = 0.0
        warnings: list[str] = []
        latest_time: datetime | None = None
        for p in positions:
            q = by_symbol.get(p["symbol"])
            fallback = False
            price = q.last_price if q and q.last_price is not None else None
            if price is None:
                price = quotes.previous_close(p["symbol"], None)
                fallback = True
                warnings.append(f"{p['symbol']}: canlı fiyat alınamadı, son günlük kapanış kullanıldı.")
            if price is None:
                price = float(p["entry_price"])
                warnings.append(f"{p['symbol']}: fiyat yok, giriş fiyatı kullanıldı.")
            qty = int(p["quantity"])
            market_value = qty * price
            value += market_value
            prev_close = q.previous_close if q else None
            pos_day = qty * (price - prev_close) if prev_close else 0.0
            day_change += pos_day
            if q and q.last_time and (latest_time is None or q.last_time > latest_time):
                latest_time = q.last_time
            rows.append(
                {
                    "symbol": p["symbol"], "quantity": qty, "entry_price": p["entry_price"], "last_price": price,
                    "last_time": q.last_time.isoformat() if q and q.last_time else None, "previous_close": prev_close,
                    "market_value": market_value, "pnl": market_value - float(p["cost"]),
                    "return_pct": (price / float(p["entry_price"]) - 1.0) if p["entry_price"] else 0.0,
                    "day_change": pos_day, "day_change_pct": (price / prev_close - 1.0) if prev_close else None,
                    "weight": 0.0, "fallback": fallback,
                }
            )
        for r in rows:
            r["weight"] = r["market_value"] / value if value else 0.0
        prev_value = value - day_change
        return dict(
            base, available=True, as_of=latest_time.isoformat() if latest_time else None, from_cache=from_cache,
            fetched_at=quotes.last_fetch_at.isoformat() if quotes.last_fetch_at else None,
            initial_capital=record.initial_capital, cash=cash, current_value=value,
            total_pnl=value - record.initial_capital, total_return=value / record.initial_capital - 1.0,
            day_change=day_change, day_change_pct=(day_change / prev_value) if prev_value else None,
            positions=rows, warnings=warnings,
        )

    def revalue(self, portfolio_id: str, persist: bool = True) -> tuple[PortfolioRecord, ValuationRecord]:
        record = self.get(portfolio_id)
        if record.status != "active":
            record = self._try_activate(record)
            with self.uow_factory() as uow:
                uow.portfolios.update_status(record.id, record.status, record.snapshot, record.activated_at)
                uow.commit()
        bundle = self.data.bundle()
        positions = [
            PositionSnapshot(
                symbol=p["symbol"], target_weight=p["target_weight"],
                entry_date=date.fromisoformat(p["entry_date"]) if p["entry_date"] else None,
                entry_price=p["entry_price"], price_field=p["price_field"], quantity=int(p["quantity"]), cost=float(p["cost"]),
            )
            for p in record.snapshot.get("positions", [])
        ]
        valuation = valuation_series(positions, float(record.snapshot.get("cash", record.initial_capital)),
                                     record.initial_capital, bundle.clean, bundle.benchmark)
        if record.data_source != bundle.source:
            valuation.warnings.append(
                f"Portföy '{record.data_source}' verisiyle oluşturuldu; mevcut kaynak '{bundle.source}'. "
                "Değerleme farklı kaynakla yapılmaz; canlı veriyle yeni portföy oluşturun."
            )
            if record.status == "active":
                valuation.metrics["status"] = "source_mismatch"
        series = [
            {k: (_iso(v) if k == "date" else (None if pd.isna(v) else float(v))) for k, v in row.items()}
            for row in valuation.series.to_dict(orient="records")
        ] if not valuation.series.empty else []
        metrics = dict(valuation.metrics)
        if record.status != "active":
            metrics["status"] = "pending"
        val = ValuationRecord(
            id=str(uuid.uuid4()), portfolio_id=record.id, computed_at=_now(),
            as_of=metrics.get("as_of"), metrics=metrics, series=series, contributions=valuation.contributions,
            warnings=valuation.warnings, benchmark_available=valuation.benchmark_available,
        )
        if persist:
            with self.uow_factory() as uow:
                uow.valuations.add(val)
                uow.commit()
        return record, val



# ================================================================= quotes
class QuoteService:
    """Gecikmeli son fiyat ve gün içi bar servisi (TTL cache'li).

    Yahoo fiyatları ≈15 dakika gecikmelidir; bu servis tick akışı değil,
    sorgu anındaki son bilinen fiyatı verir. Demo modunda (sentetik veri)
    canlı fiyat devre dışıdır: sentetik pozisyonlarla gerçek fiyat karışmaz.
    """

    def __init__(self, data: MarketDataService, provider: MarketDataProvider,
                 quote_ttl: float = 60.0, history_ttl: float = 300.0, clock: Callable[[], float] = time.time,
                 poll_seconds: int = 0, idle_poll_seconds: int = 600) -> None:
        self.data = data
        self.provider = provider
        self.quote_ttl = quote_ttl
        self.history_ttl = history_ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._quotes: dict[str, tuple[float, Quote]] = {}
        self._history: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
        self.last_fetch_at: datetime | None = None
        self.poll_seconds = poll_seconds
        self.idle_poll_seconds = idle_poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._refreshing: set[str] = set()
        self.poll_state: dict[str, Any] = {"enabled": poll_seconds > 0, "last_run_at": None, "last_duration": None,
                                           "last_error": None, "symbols": 0, "market_open": None}

    # ------------------------------------------------------ arka plan yenileme
    @staticmethod
    def market_is_open(now: datetime | None = None) -> bool:
        """BIST pay piyasası saatleri (TSİ 09:55–18:15, hafta içi); tatiller hariç tutulmaz."""
        from zoneinfo import ZoneInfo

        local = now or datetime.now(ZoneInfo("Europe/Istanbul"))
        if local.weekday() >= 5:
            return False
        minutes = local.hour * 60 + local.minute
        return 9 * 60 + 55 <= minutes <= 18 * 60 + 15

    def refresh_snapshot(self) -> None:
        """Bütün evrenin fiyatlarını tek turda tazeler (istek beklemeden)."""
        symbols = self.data.universe().symbols + [self.data.settings.benchmark_symbol]
        started = self._clock()
        try:
            self.quotes(symbols, force=True)
            self.poll_state.update(last_error=None, symbols=len(symbols))
        except Exception as error:  # ağ/oran sınırı: mevcut anlık görüntü korunur
            self.poll_state["last_error"] = str(error)
            logger.warning("Fiyat anlık görüntüsü yenilenemedi: %s", error)
        finally:
            self.poll_state.update(last_run_at=_now().isoformat(), last_duration=round(self._clock() - started, 2),
                                   market_open=self.market_is_open())

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.enabled:
                self.refresh_snapshot()
            wait = self.poll_seconds if self.market_is_open() else self.idle_poll_seconds
            self._stop.wait(max(wait, 5))

    def start_poller(self) -> None:
        if self.poll_seconds <= 0 or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="quote-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def enabled(self) -> bool:
        return self.data.bundle().source != DEMO_SOURCE

    def previous_close(self, symbol: str, before: date | None) -> float | None:
        """Günlük temiz tablodan ``before`` tarihinden önceki son kapanış."""
        clean = self.data.bundle().clean
        sub = clean.loc[clean["symbol"] == symbol]
        if before is not None:
            sub = sub.loc[pd.to_datetime(sub["date"]).dt.date < before]
        if sub.empty:
            return None
        return float(sub.sort_values("date")["close"].iloc[-1])

    def quotes(self, symbols: list[str], force: bool = False) -> tuple[list[Quote], bool]:
        """Semboller için son fiyat; ikinci değer tamamen cache'ten geldiğini söyler."""
        if not self.enabled:
            return [Quote(s, None, None, outcome=FetchOutcome.NO_DATA, message="Demo modunda canlı fiyat yok") for s in symbols], True
        now = self._clock()
        with self._lock:
            stale = [s for s in symbols if s in self._quotes and now - self._quotes[s][0] > self.quote_ttl]
            absent = [s for s in symbols if s not in self._quotes]
        # Elde hiç fiyat yoksa beklenir; sadece bayatsa önce cache verilir, tazeleme arka planda yapılır.
        must_fetch = absent if not force else list(dict.fromkeys(symbols))
        if must_fetch:
            self._fetch_into_cache(must_fetch)
        elif stale:
            self._refresh_async(stale)
        with self._lock:
            result = [self._quotes[s][1] for s in symbols if s in self._quotes]
            missing = [s for s in symbols if s not in self._quotes]
        for symbol in missing:
            result.append(Quote(symbol, None, None, outcome=FetchOutcome.NO_DATA, message="Fiyat alınamadı"))
        order = {q.symbol: q for q in result}
        return [order[s] for s in symbols if s in order], not must_fetch

    def _fetch_into_cache(self, symbols: list[str]) -> None:
        fetched = self.provider.fetch_quotes(symbols)
        now = self._clock()
        with self._lock:
            for q in fetched:
                if q.previous_close is None:  # sağlayıcı veremediyse günlük tablodan (daha eski olabilir)
                    q.previous_close = self.previous_close(q.symbol, q.last_time.date() if q.last_time else None)
                self._quotes[q.symbol] = (now, q)
            self.last_fetch_at = _now()

    def _refresh_async(self, symbols: list[str]) -> None:
        """Bayat fiyatları arka planda tazeler; aynı semboller için tek iş çalışır."""
        with self._lock:
            pending = [s for s in symbols if s not in self._refreshing]
            self._refreshing.update(pending)
        if not pending:
            return

        def run() -> None:
            try:
                self._fetch_into_cache(pending)
            except Exception as error:
                logger.warning("Arka plan fiyat tazeleme başarısız: %s", error)
            finally:
                with self._lock:
                    self._refreshing.difference_update(pending)

        threading.Thread(target=run, name="quote-refresh", daemon=True).start()

    def history(self, symbol: str, interval: str) -> pd.DataFrame:
        """``1d`` günlük cache'ten; diğer aralıklar sağlayıcıdan (TTL ile)."""
        if interval == "1d":
            clean = self.data.bundle().clean
            sub = clean.loc[clean["symbol"] == symbol].sort_values("date")
            out = pd.DataFrame({"datetime": pd.to_datetime(sub["date"]), "symbol": symbol})
            for column in ["open", "high", "low", "close", "volume"]:
                out[column] = sub[column].to_numpy()
            out["adj_close"] = sub["adj_close"].to_numpy()
            out["dividends"] = sub["dividends"].fillna(0.0).to_numpy()
            return out.reset_index(drop=True)
        if interval not in INTRADAY_LIMITS:
            raise ValueError(f"Desteklenmeyen aralık: {interval}")
        if not self.enabled:
            raise DataUnavailableError("Demo modunda gün içi veri yok; önce canlı veriyi yenileyin.")
        now = self._clock()
        key = (symbol, interval)
        with self._lock:
            cached = self._history.get(key)
            if cached and now - cached[0] <= self.history_ttl:
                return cached[1]
        frame = self.provider.fetch_intraday([symbol], interval, INTRADAY_LIMITS[interval])
        with self._lock:
            self._history[key] = (now, frame)
        return frame

# =========================================================== auto-refresh
class AutoRefresher:
    """Günlük veriyi arka planda güncel tutar.

    Açılışta ve sonra her ``check_interval`` saniyede bir bakar: veri demo ise ya da son
    başarılı güncelleme ``max_age_hours``'dan eskiyse ``MarketDataService.refresh`` çalıştırır.
    Hata gizlenmez; durum ``data/status`` içinde ``auto_refresh`` alanında görünür.
    """

    def __init__(self, data: MarketDataService, max_age_hours: int, check_interval: float = 3600.0) -> None:
        self.data = data
        self.max_age_hours = max_age_hours
        self.check_interval = check_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.state: dict[str, Any] = {"enabled": max_age_hours > 0, "running": False, "last_check_at": None,
                                      "last_result": None, "last_error": None}

    @property
    def enabled(self) -> bool:
        return self.max_age_hours > 0

    def needs_refresh(self) -> bool:
        status = self.data.status()
        if status.get("is_demo", True):
            return True
        last = status.get("last_success_at")
        if not last:
            return True
        try:
            age = _now() - datetime.fromisoformat(str(last).replace("Z", ""))
        except ValueError:
            return True
        return age > timedelta(hours=self.max_age_hours)

    def run_once(self) -> bool:
        self.state["last_check_at"] = _now().isoformat()
        if not self.needs_refresh():
            self.state["last_result"] = "güncel"
            return False
        self.state["running"] = True
        try:
            self.data.refresh()
            self.state["last_result"] = "yenilendi"
            self.state["last_error"] = None
            return True
        except Exception as error:  # ağ vb. — mevcut veri korunur
            self.state["last_result"] = "hata"
            self.state["last_error"] = str(error)
            logger.warning("Otomatik veri yenileme başarısız: %s", error)
            return False
        finally:
            self.state["running"] = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.check_interval)

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="auto-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


# ============================================================== container
@dataclass
class AppContainer:
    settings: Settings
    data: MarketDataService
    ranking: RankingService
    portfolios: PortfolioService
    profiles: dict[str, InvestorProfile]
    quotes: QuoteService
    auto_refresh: AutoRefresher


def _parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except Exception:  # ImportError veya işletim sistemi DLL engeli
        return False


def _select_price_store(settings: Settings, engine) -> PriceStore:
    """``sql`` / ``parquet`` / ``auto``: auto → PostgreSQL ise ya da pyarrow yüklenemiyorsa SQL, aksi hâlde Parquet."""
    choice = settings.price_store
    if choice == "parquet":
        return ParquetPriceCache(settings.cache_dir)
    if choice == "sql":
        return SqlPriceStore(engine)
    if settings.database_url.startswith("postgresql") or not _parquet_available():
        if not settings.database_url.startswith("postgresql"):
            logger.warning("pyarrow kullanılamıyor; fiyat deposu olarak SQLite tabloları kullanılacak.")
        return SqlPriceStore(engine)
    return ParquetPriceCache(settings.cache_dir)


def build_container(settings: Settings | None = None, provider: MarketDataProvider | None = None) -> AppContainer:
    settings = settings or load_settings()
    engine = create_engine_from_url(settings.database_url)
    uow_factory = lambda: SqlAlchemyUnitOfWork(engine)  # noqa: E731
    if provider is None:
        provider = (
            YahooFinanceProvider(batch_size=settings.batch_size, max_retries=settings.max_retries)
            if settings.provider_name == "yahoo"
            else FakeProvider()
        )
    store: PriceStore = _select_price_store(settings, engine)
    universe_loader = lambda: load_universe(settings.universe_csv)  # noqa: E731
    profiles = load_profiles(settings.profiles_json)
    data = MarketDataService(settings, universe_loader, provider, store, uow_factory)
    ranking = RankingService(data, profiles, uow_factory, settings)
    portfolios = PortfolioService(data, ranking, profiles, uow_factory, settings)
    quotes = QuoteService(data, provider, poll_seconds=settings.quote_poll_seconds,
                          idle_poll_seconds=settings.quote_idle_poll_seconds)
    auto_refresh = AutoRefresher(data, settings.auto_refresh_hours)
    return AppContainer(settings=settings, data=data, ranking=ranking, portfolios=portfolios, profiles=profiles,
                        quotes=quotes, auto_refresh=auto_refresh)
