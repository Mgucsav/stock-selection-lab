"""FastAPI uygulaması: BIST 100 fpfs sıralama ve model portföy takibi.

Bu API gerçek emir göndermez, aracı kurum hesabına bağlanmaz ve getiri
tahmini/garantisi sunmaz. Bütün çıktılar araştırma ve model portföy
simülasyonu amaçlıdır.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import sys
from pathlib import Path

# Depo kökünden ``src.*`` ve ``api.*`` içe aktarımlarının çalışması için
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.schemas import (  # noqa: E402
    CandidateOut,
    DataRefreshRequest,
    DataStatusResponse,
    DividendOut,
    HealthResponse,
    HistoryBar,
    LiveValuationResponse,
    PortfolioDetail,
    PortfolioGenerateRequest,
    PortfolioGenerateResponse,
    PortfolioListResponse,
    PortfolioSelectRequest,
    PortfolioSummary,
    ProfileOut,
    QuoteOut,
    QuotesResponse,
    RankingRunRequest,
    RankingRunResponse,
    StockHistoryResponse,
    StockSummaryResponse,
    UniverseMemberOut,
    UniverseResponse,
    UniverseUploadRequest,
)
from src.stock_selection import MODEL_VERSION  # noqa: E402
from src.stock_selection.application import (  # noqa: E402
    QUOTE_LABEL,
    AppContainer,
    DataUnavailableError,
    NotFoundError,
    build_container,
)
from src.stock_selection.data.providers.base import INTRADAY_LIMITS  # noqa: E402
from src.stock_selection.demo import DEMO_SOURCE  # noqa: E402
from src.stock_selection.features.stock_stats import compute_stock_stats  # noqa: E402
from src.stock_selection.repositories.base import PortfolioRecord, ScoreRunRecord  # noqa: E402

logger = logging.getLogger("api")

DISCLAIMER = (
    "Araştırma ve model portföy simülasyonu amaçlıdır; yatırım tavsiyesi, "
    "fiyat tahmini veya garantili getiri değildir. Gerçek emir gönderilmez."
)


def create_app(container: AppContainer | None = None) -> FastAPI:
    """Uygulama fabrikası; testlerde sahte container enjekte edilebilir."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or build_container()
        try:
            app.state.container.data.bundle()  # demo/cache ısındırma
        except Exception as error:  # pragma: no cover
            logger.warning("Veri ısındırma başarısız: %s", error)
        app.state.container.auto_refresh.start()  # günlük veriyi arka planda güncel tut (kapalıysa no-op)
        app.state.container.quotes.start_poller()  # fiyat anlık görüntüsünü arka planda tazele
        yield
        app.state.container.auto_refresh.stop()
        app.state.container.quotes.stop()

    app = FastAPI(title="Stock Selection Lab API", version=MODEL_VERSION, lifespan=lifespan)
    cors_settings = container.settings if container else _load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_settings.cors_origins),
        allow_origin_regex=cors_settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def ctx(request: Request) -> AppContainer:
        return request.app.state.container

    # ------------------------------------------------------------ errors
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(DataUnavailableError)
    async def _data_unavailable(_: Request, error: DataUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": f"Veri alınamadı: {error}"})

    @app.exception_handler(ValueError)
    async def _bad_request(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    # ------------------------------------------------------------ health
    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        c = ctx(request)
        status = c.data.status()
        return HealthResponse(
            status="ok", model_version=MODEL_VERSION, data_source=str(status.get("data_source", DEMO_SOURCE)),
            is_demo=bool(status.get("is_demo", True)), data_label=str(status.get("data_label", "Günlük/gecikmeli veri")),
            disclaimer=DISCLAIMER,
        )

    # ---------------------------------------------------------- universe
    @app.get("/api/v1/universe", response_model=UniverseResponse)
    def universe(request: Request) -> UniverseResponse:
        u = ctx(request).data.universe()
        return UniverseResponse(
            as_of=u.as_of.isoformat(), count=len(u.members), expected=100, is_complete=u.is_complete,
            sources=u.sources, warnings=list(u.warnings),
            members=[
                UniverseMemberOut(
                    symbol=m.symbol, name=m.name, sector=m.sector,
                    effective_from=m.effective_from.isoformat() if m.effective_from else None,
                    effective_to=m.effective_to.isoformat() if m.effective_to else None, source=m.source,
                )
                for m in u.members
            ],
        )

    @app.post("/api/v1/universe", response_model=UniverseResponse)
    def upload_universe(body: UniverseUploadRequest, request: Request) -> UniverseResponse:
        ctx(request).data.replace_universe(body.csv_text)
        return universe(request)

    @app.get("/api/v1/profiles", response_model=list[ProfileOut])
    def profiles(request: Request) -> list[ProfileOut]:
        return [ProfileOut(**p.to_dict()) for p in ctx(request).profiles.values()]

    # -------------------------------------------------------------- data
    @app.get("/api/v1/data/status", response_model=DataStatusResponse)
    def data_status(request: Request) -> DataStatusResponse:
        c = ctx(request)
        return DataStatusResponse(**c.data.status(), auto_refresh=dict(c.auto_refresh.state, max_age_hours=c.auto_refresh.max_age_hours))

    @app.post("/api/v1/data/refresh", response_model=DataStatusResponse)
    def data_refresh(request: Request, body: DataRefreshRequest | None = None) -> DataStatusResponse:
        c = ctx(request)
        status = c.data.refresh(lookback_years=body.lookback_years if body else None)
        return DataStatusResponse(**status)

    # ---------------------------------------------------------- rankings
    def _ranking_response(run: ScoreRunRecord) -> RankingRunResponse:
        return RankingRunResponse(
            score_run_id=run.id, created_at=run.created_at.isoformat(), profile_id=run.profile_id, weights=run.weights,
            data_as_of=run.data_as_of, window_start=run.window_start, normalization=run.normalization,
            constant_policy=run.constant_policy, model_version=run.model_version, data_source=run.data_source,
            is_demo=run.data_source == DEMO_SOURCE, universe_size=run.universe_size, scored_count=run.scored_count,
            excluded=run.excluded, warnings=run.warnings, persisted=run.persisted, results=run.results,  # type: ignore[arg-type]
        )

    @app.post("/api/v1/rankings/run", response_model=RankingRunResponse)
    def rankings_run(body: RankingRunRequest, request: Request) -> RankingRunResponse:
        c = ctx(request)
        run = c.ranking.run(
            profile_id=body.profile_id, weights=body.weights, as_of=body.as_of, persist=body.persist,
            constant_policy=body.constant_policy,
        )
        return _ranking_response(run)

    @app.get("/api/v1/rankings/latest", response_model=RankingRunResponse)
    def rankings_latest(request: Request, profile_id: str | None = None) -> RankingRunResponse:
        c = ctx(request)
        run = c.ranking.latest(profile_id)
        if run is None:
            run = c.ranking.run(profile_id=profile_id or "balanced", persist=True)
        return _ranking_response(run)

    @app.get("/api/v1/rankings/{score_run_id}", response_model=RankingRunResponse)
    def rankings_get(score_run_id: str, request: Request) -> RankingRunResponse:
        run = ctx(request).ranking.get(score_run_id)
        if run is None:
            raise NotFoundError(f"Skor çalışması bulunamadı: {score_run_id}")
        return _ranking_response(run)

    # -------------------------------------------------------- portfolios
    @app.post("/api/v1/portfolios/generate", response_model=PortfolioGenerateResponse)
    def portfolios_generate(body: PortfolioGenerateRequest, request: Request) -> PortfolioGenerateResponse:
        c = ctx(request)
        candidates = c.portfolios.generate(capital=body.capital, decision_date=body.decision_date, profile_ids=body.profile_ids)
        source = candidates[0]["data_source"] if candidates else c.data.bundle().source
        return PortfolioGenerateResponse(
            candidates=[CandidateOut(**cd) for cd in candidates], data_source=source, is_demo=source == DEMO_SOURCE,
        )

    def _summary(c: AppContainer, record: PortfolioRecord) -> PortfolioSummary:
        val = c.portfolios.latest_valuation(record.id)
        metrics = val.metrics if val else {}
        return PortfolioSummary(
            portfolio_id=record.id, name=record.name, created_at=record.created_at.isoformat(), profile_id=record.profile_id,
            status=record.status, decision_date=record.decision_date, data_as_of=record.data_as_of, data_source=record.data_source,
            initial_capital=record.initial_capital, current_value=metrics.get("current_value"),
            total_return=metrics.get("total_return"), daily_change=metrics.get("daily_change"),
            benchmark_return=metrics.get("benchmark_return"),
            position_count=len(record.snapshot.get("positions", [])) or len(record.snapshot.get("target_weights", {})),
        )

    @app.post("/api/v1/portfolios/{candidate_id}/select", response_model=PortfolioDetail, status_code=201)
    def portfolios_select(candidate_id: str, request: Request, body: PortfolioSelectRequest | None = None) -> PortfolioDetail:
        c = ctx(request)
        record = c.portfolios.select(candidate_id, initial_capital=body.initial_capital if body else None, name=body.name if body else None)
        record, val = c.portfolios.revalue(record.id)
        return _detail(record, val)

    @app.get("/api/v1/portfolios", response_model=PortfolioListResponse)
    def portfolios_list(request: Request) -> PortfolioListResponse:
        c = ctx(request)
        return PortfolioListResponse(portfolios=[_summary(c, r) for r in c.portfolios.list()])

    def _detail(record: PortfolioRecord, val) -> PortfolioDetail:
        return PortfolioDetail(
            portfolio_id=record.id, name=record.name, created_at=record.created_at.isoformat(), candidate_id=record.candidate_id,
            score_run_id=record.score_run_id, profile_id=record.profile_id, profile_weights=record.profile_weights,
            model_version=record.model_version, decision_date=record.decision_date, data_as_of=record.data_as_of,
            data_source=record.data_source, is_demo=record.data_source == DEMO_SOURCE, initial_capital=record.initial_capital,
            status=record.status, activated_at=record.activated_at.isoformat() if record.activated_at else None,
            snapshot=record.snapshot, valuation=val.metrics if val else None, series=val.series if val else [],
            contributions=val.contributions if val else [], warnings=val.warnings if val else [],
            benchmark_available=val.benchmark_available if val else False,
        )

    @app.get("/api/v1/portfolios/{portfolio_id}", response_model=PortfolioDetail)
    def portfolios_get(portfolio_id: str, request: Request) -> PortfolioDetail:
        c = ctx(request)
        record = c.portfolios.get(portfolio_id)
        val = c.portfolios.latest_valuation(portfolio_id)
        if val is None:
            record, val = c.portfolios.revalue(portfolio_id)
        return _detail(record, val)

    @app.post("/api/v1/portfolios/{portfolio_id}/revalue", response_model=PortfolioDetail)
    def portfolios_revalue(portfolio_id: str, request: Request) -> PortfolioDetail:
        record, val = ctx(request).portfolios.revalue(portfolio_id)
        return _detail(record, val)

    # ------------------------------------------------------- quotes/stocks
    def _quote_out(q, names: dict[str, str], sectors: dict[str, str | None]) -> QuoteOut:
        return QuoteOut(name=names.get(q.symbol), sector=sectors.get(q.symbol), **q.to_dict())

    def _demo_message(c: AppContainer) -> str | None:
        return None if c.quotes.enabled else "Demo modunda canlı fiyat yok; Veri Sağlığı sayfasından canlı veriyi yenileyin."

    @app.get("/api/v1/quotes", response_model=QuotesResponse)
    def quotes(request: Request, symbols: str | None = None, force: bool = False) -> QuotesResponse:
        """Gecikmeli son fiyatlar (≈15 dk). ``symbols`` verilmezse bütün evren."""
        c = ctx(request)
        u = c.data.universe()
        wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else u.symbols
        quote_list, from_cache = c.quotes.quotes(wanted, force=force)
        delays = [q.delayed_by_minutes for q in quote_list if q.delayed_by_minutes is not None]
        states = [q.market_state for q in quote_list if q.market_state]
        return QuotesResponse(
            label=QUOTE_LABEL, available=c.quotes.enabled, is_demo=c.data.bundle().source == DEMO_SOURCE,
            delayed_by_minutes=max(delays) if delays else None,
            market_state=states[0] if states else None,
            poll=dict(c.quotes.poll_state),
            fetched_at=c.quotes.last_fetch_at.isoformat() if c.quotes.last_fetch_at else None, from_cache=from_cache,
            message=_demo_message(c), quotes=[_quote_out(q, u.name_map, u.sector_map) for q in quote_list],
        )

    @app.get("/api/v1/stocks/{symbol}/history", response_model=StockHistoryResponse)
    def stock_history(symbol: str, request: Request, interval: str = "1d") -> StockHistoryResponse:
        c = ctx(request)
        symbol = symbol.upper()
        if interval != "1d" and interval not in INTRADAY_LIMITS:
            raise ValueError(f"Desteklenmeyen aralık: {interval}. İzinli: 1d, {', '.join(INTRADAY_LIMITS)}")
        frame = c.quotes.history(symbol, interval)
        warnings: list[str] = []
        if frame.empty:
            warnings.append("Bu aralık için veri bulunamadı.")
        if interval in INTRADAY_LIMITS:
            warnings.append(f"Yahoo {interval} verisi en fazla {INTRADAY_LIMITS[interval]} geriye gider ve ≈15 dk gecikmelidir.")
        bars = [
            HistoryBar(
                t=row["datetime"].isoformat(), o=_f(row.get("open")), h=_f(row.get("high")), l=_f(row.get("low")),
                c=_f(row.get("close")), v=_f(row.get("volume")), adj=_f(row.get("adj_close")), div=_f(row.get("dividends")),
            )
            for row in frame.to_dict(orient="records")
        ]
        return StockHistoryResponse(
            symbol=symbol, interval=interval, label=QUOTE_LABEL if interval != "1d" else "Günlük kapanış",
            count=len(bars), bars=bars, warnings=warnings,
        )

    @app.get("/api/v1/stocks/{symbol}", response_model=StockSummaryResponse)
    def stock_summary(symbol: str, request: Request) -> StockSummaryResponse:
        c = ctx(request)
        symbol = symbol.upper()
        u = c.data.universe()
        daily = c.quotes.history(symbol, "1d")
        if daily.empty and symbol not in u.name_map:
            raise NotFoundError(f"Sembol bulunamadı: {symbol}")
        quote = None
        if c.quotes.enabled:
            quote_list, _ = c.quotes.quotes([symbol])
            quote = _quote_out(quote_list[0], u.name_map, u.sector_map)
        last_close = float(daily["close"].iloc[-1]) if not daily.empty else None
        last_dt = daily["datetime"].iloc[-1] if not daily.empty else None
        # Değişimler için referans: canlı fiyat varsa o (ve tarihi), yoksa son günlük kapanış
        ref_price = quote.last_price if quote and quote.last_price else last_close
        ref_dt = pd.Timestamp(quote.last_time).normalize() if quote and quote.last_time else last_dt

        def change(days: int) -> float | None:
            if ref_price is None or ref_dt is None or daily.empty:
                return None
            past = daily.loc[daily["datetime"] <= ref_dt - pd.Timedelta(days=days)]
            if past.empty:
                return None
            base_price = float(past["close"].iloc[-1])
            return ref_price / base_price - 1.0 if base_price else None

        year = daily.loc[daily["datetime"] >= last_dt - pd.Timedelta(days=365)] if not daily.empty else daily
        divs = daily.loc[daily["dividends"] > 0] if not daily.empty else daily
        div_12m = float(divs.loc[divs["datetime"] >= last_dt - pd.Timedelta(days=365), "dividends"].sum()) if not divs.empty else 0.0
        stats = compute_stock_stats(daily, c.data.bundle().benchmark)
        ranking = None
        run = c.ranking.latest("balanced")
        if run:
            row = next((r for r in run.results if r["symbol"] == symbol), None)
            if row:
                ranking = dict(row, score_run_id=run.id, data_as_of=run.data_as_of, profile_id=run.profile_id)
        return StockSummaryResponse(
            symbol=symbol, name=u.name_map.get(symbol, symbol), sector=u.sector_map.get(symbol), in_universe=symbol in u.name_map,
            quote=quote, quote_label=QUOTE_LABEL,
            daily_last_date=last_dt.date().isoformat() if last_dt is not None else None,
            daily_last_close=last_close, daily_rows=int(len(daily)),
            change_1w=change(7), change_1m=change(30), change_3m=change(91), change_1y=change(365),
            high_52w=_f(year["high"].max()) if not year.empty else None, low_52w=_f(year["low"].min()) if not year.empty else None,
            dividends=[
                DividendOut(date=r["datetime"].date().isoformat(), amount=float(r["dividends"]), close=_f(r["close"]))
                for r in divs.to_dict(orient="records")
            ][::-1],
            dividend_yield_12m=(div_12m / last_close) if last_close else None,
            stats=stats,
            ranking=ranking, is_demo=c.data.bundle().source == DEMO_SOURCE,
        )

    @app.get("/api/v1/portfolios/{portfolio_id}/live", response_model=LiveValuationResponse)
    def portfolios_live(portfolio_id: str, request: Request) -> LiveValuationResponse:
        c = ctx(request)
        return LiveValuationResponse(**c.portfolios.live_valuation(portfolio_id, c.quotes))

    return app


def _f(value) -> float | None:
    """NaN/None güvenli float."""
    try:
        if value is None:
            return None
        number = float(value)
        return None if number != number else number
    except (TypeError, ValueError):
        return None


def _load_settings():
    from src.stock_selection.settings import load_settings

    return load_settings()


app = create_app()
