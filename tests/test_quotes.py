"""Gecikmeli fiyat servisi, hisse geçmişi ve canlı portföy değerlemesi testleri."""

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from src.stock_selection.application import QuoteService
from src.stock_selection.data.providers.base import FetchOutcome
from src.stock_selection.data.providers.yahoo import YahooFinanceProvider


@pytest.fixture
def live_client(container):
    """Sahte sağlayıcıdan canlı veri çekilmiş (demo olmayan) uygulama."""
    app = create_app(container)
    with TestClient(app) as client:
        assert client.post("/api/v1/data/refresh", json={}).status_code == 200
        yield client


def test_quotes_disabled_in_demo_mode(client_demo):
    body = client_demo.get("/api/v1/quotes", params={"symbols": "AKBNK.IS"}).json()
    assert body["available"] is False and body["is_demo"] is True
    assert body["quotes"][0]["outcome"] == "no_data"
    assert "Demo" in body["message"]


@pytest.fixture
def client_demo(container):
    with TestClient(create_app(container)) as client:
        yield client


def test_quotes_are_cached_by_ttl(container):
    times = [1000.0]
    service = QuoteService(container.data, container.data.provider, quote_ttl=60, clock=lambda: times[0])
    container.data.refresh()
    provider = container.data.provider
    q1, cached1 = service.quotes(["AKBNK.IS", "GARAN.IS"])
    q2, cached2 = service.quotes(["AKBNK.IS", "GARAN.IS"])
    assert provider.quote_calls == 1 and cached1 is False and cached2 is True
    assert q1[0].last_price == q2[0].last_price
    assert q1[0].previous_close is not None and q1[0].day_change is not None
    times[0] += 61
    service.quotes(["AKBNK.IS"])
    assert provider.quote_calls == 2


def test_quotes_endpoint_returns_universe_quotes(live_client: TestClient):
    body = live_client.get("/api/v1/quotes").json()
    assert body["available"] is True and body["is_demo"] is False
    assert len(body["quotes"]) == 20
    q = body["quotes"][0]
    assert q["last_price"] > 0 and q["last_time"] and q["name"]
    assert q["day_change_pct"] is not None


def test_stock_summary_and_history(live_client: TestClient):
    body = live_client.get("/api/v1/stocks/AKBNK.IS").json()
    assert body["in_universe"] is True
    assert body["daily_rows"] > 400
    assert body["quote"]["last_price"] > 0
    assert body["change_1m"] is not None and body["high_52w"] >= body["low_52w"]
    assert isinstance(body["dividends"], list)
    daily = live_client.get("/api/v1/stocks/AKBNK.IS/history", params={"interval": "1d"}).json()
    assert daily["count"] == body["daily_rows"] and daily["bars"][-1]["c"] > 0
    intraday = live_client.get("/api/v1/stocks/AKBNK.IS/history", params={"interval": "5m"}).json()
    assert intraday["count"] > 0 and any("15 dk" in w for w in intraday["warnings"])
    assert live_client.get("/api/v1/stocks/AKBNK.IS/history", params={"interval": "2m"}).status_code == 400
    assert live_client.get("/api/v1/stocks/YOK.IS").status_code == 404


def test_live_valuation_tracks_intraday_price_moves(live_client: TestClient, container):
    status = live_client.get("/api/v1/data/status").json()
    decision = (date.fromisoformat(status["date_range"]["end"]) - timedelta(days=60)).isoformat()
    gen = live_client.post("/api/v1/portfolios/generate", json={"capital": 500000, "decision_date": decision}).json()
    detail = live_client.post(f"/api/v1/portfolios/{gen['candidates'][2]['candidate_id']}/select").json()
    pid = detail["portfolio_id"]

    live = live_client.get(f"/api/v1/portfolios/{pid}/live").json()
    assert live["available"] is True
    base_value = live["current_value"]
    assert base_value == pytest.approx(live["cash"] + sum(p["market_value"] for p in live["positions"]))
    assert sum(p["weight"] for p in live["positions"]) == pytest.approx(1 - live["cash"] / base_value)

    # Gün içi fiyatlar %2 yükselsin: cache TTL'i aşmak için force ile yeniden çek
    container.data.provider.intraday_multiplier = 1.02
    container.quotes.quotes([p["symbol"] for p in live["positions"]], force=True)
    moved = live_client.get(f"/api/v1/portfolios/{pid}/live").json()
    assert moved["current_value"] > base_value
    assert moved["day_change"] > 0 and moved["day_change_pct"] > 0
    before = {p["symbol"]: p["last_price"] for p in live["positions"]}
    assert all(p["last_price"] == pytest.approx(before[p["symbol"]] * 1.02) for p in moved["positions"])
    assert moved["current_value"] - moved["cash"] == pytest.approx((base_value - live["cash"]) * 1.02)


def test_live_valuation_pending_portfolio(live_client: TestClient):
    gen = live_client.post("/api/v1/portfolios/generate", json={"capital": 100000}).json()
    detail = live_client.post(f"/api/v1/portfolios/{gen['candidates'][2]['candidate_id']}/select").json()
    live = live_client.get(f"/api/v1/portfolios/{detail['portfolio_id']}/live").json()
    assert live["available"] is False and live["status"] == "pending"


def test_yahoo_intraday_parsing_and_quote_derivation():
    idx = pd.date_range("2026-09-18 09:55", periods=4, freq="1min", tz="Europe/Istanbul")
    cols = pd.MultiIndex.from_product([["A.IS"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    frame = pd.DataFrame([[10, 10.5, 9.9, 10.2, 10.2, 100], [10.2, 10.6, 10.1, 10.4, 10.4, 50], [10.4, 10.4, 10.0, 10.1, 10.1, 70], [10.1, 10.3, 10.0, 10.3, 10.3, 30]], index=idx, columns=cols)
    prev_idx = pd.date_range("2026-09-17 10:30", periods=2, freq="1h", tz="Europe/Istanbul")
    hourly = pd.DataFrame([[9.5, 9.7, 9.4, 9.6, 9.6, 500], [9.6, 9.9, 9.5, 9.8, 9.8, 400]], index=prev_idx, columns=cols)

    def downloader(symbols, interval, period):
        return frame if interval == "1m" else pd.concat([hourly, frame])

    provider = YahooFinanceProvider(intraday_downloader=downloader, sleep=lambda _: None)
    bars = provider.fetch_intraday(["A.IS"], "1m", "1d")
    assert list(bars.columns) == ["datetime", "symbol", "open", "high", "low", "close", "volume"]
    assert bars["datetime"].iloc[0] == pd.Timestamp("2026-09-18 09:55")  # borsa saati, tz-naive
    quote = provider.fetch_quotes(["A.IS"])[0]
    assert quote.last_price == 10.3 and quote.day_high == 10.6 and quote.day_low == 9.9 and quote.day_volume == 250
    assert quote.previous_close == 9.8  # bir önceki günün son saatlik barı
    assert quote.day_change_pct == pytest.approx(10.3 / 9.8 - 1)
    assert quote.outcome == FetchOutcome.OK
    with pytest.raises(ValueError):
        provider.fetch_intraday(["A.IS"], "2m", "1d")
