"""FastAPI endpoint testleri (sahte sağlayıcı, geçici SQLite)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from src.stock_selection.data.providers.fake import FakeProvider
from src.stock_selection.application import build_container


@pytest.fixture
def client(container):
    app = create_app(container)
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_demo_mode_and_disclaimer(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["is_demo"] is True
    assert body["data_source"] == "demo"
    assert "garanti" in body["disclaimer"]


def test_universe_endpoint_reads_config(client: TestClient) -> None:
    body = client.get("/api/v1/universe").json()
    assert body["count"] == 20 and body["is_complete"] is False
    assert body["members"][0]["symbol"].endswith(".IS")
    assert any("universe incomplete" in w for w in body["warnings"])


def test_data_status_shows_demo_and_symbol_statuses(client: TestClient) -> None:
    body = client.get("/api/v1/data/status").json()
    assert body["is_demo"] is True
    assert body["ok_count"] == 20
    assert len(body["symbol_statuses"]) == 20


def test_data_refresh_uses_provider_and_exposes_failures(container) -> None:
    provider: FakeProvider = container.data.provider
    provider.failing_symbols = {"ASELS.IS"}
    provider.missing_symbols = {"GARAN.IS"}
    with TestClient(create_app(container)) as client:
        body = client.post("/api/v1/data/refresh", json={}).json()
        assert provider.calls, "sağlayıcı çağrılmadı"
        assert body["is_demo"] is False and body["data_source"] == "fake"
        assert body["failed_count"] == 2
        assert set(body["missing_symbols"]) == {"ASELS.IS", "GARAN.IS"}
        outcomes = {s["symbol"]: s["outcome"] for s in body["symbol_statuses"]}
        assert outcomes["ASELS.IS"] == "provider_error" and outcomes["GARAN.IS"] == "no_data"
        assert body["last_success_at"] is not None
        assert client.get("/health").json()["is_demo"] is False


def test_data_refresh_total_failure_returns_503_and_keeps_demo(container) -> None:
    container.data.provider.raise_on_batch = True
    with TestClient(create_app(container)) as client:
        response = client.post("/api/v1/data/refresh", json={})
        assert response.status_code == 503
        assert "Veri alınamadı" in response.json()["detail"]
        status = client.get("/api/v1/data/status").json()
        assert status["last_error"] is not None
        assert status["is_demo"] is True


def test_ranking_run_and_latest(client: TestClient) -> None:
    run = client.post("/api/v1/rankings/run", json={"profile_id": "balanced"}).json()
    assert run["weights"] == {"return": 0.8, "dividend": 0.6, "liquidity": 0.6, "risk": 0.8}
    assert run["scored_count"] == 20
    assert run["normalization"]["return"] == "minmax_benefit"
    assert run["results"][0]["rank"] == 1
    row = run["results"][0]
    assert set(row["membership"]) == {"return", "dividend", "liquidity", "risk"}
    latest = client.get("/api/v1/rankings/latest", params={"profile_id": "balanced"}).json()
    assert latest["score_run_id"] == run["score_run_id"]


def test_ranking_custom_weights_preview_is_not_persisted(client: TestClient) -> None:
    custom = {"return": 1.0, "dividend": 0.0, "liquidity": 0.0, "risk": 0.0}
    run = client.post("/api/v1/rankings/run", json={"weights": custom, "persist": False}).json()
    assert run["persisted"] is False
    top = run["results"][0]
    assert top["membership"]["return"] == pytest.approx(1.0)
    bad = client.post("/api/v1/rankings/run", json={"weights": {**custom, "return": 1.5}})
    assert bad.status_code == 422


def test_portfolio_flow_generate_select_get_revalue(client: TestClient) -> None:
    status = client.get("/api/v1/data/status").json()
    latest = date.fromisoformat(status["date_range"]["end"])
    decision = (latest - timedelta(days=90)).isoformat()
    gen = client.post("/api/v1/portfolios/generate", json={"capital": 250000, "decision_date": decision}).json()
    assert gen["is_demo"] is True
    assert [c["profile_id"] for c in gen["candidates"]] == ["conservative", "balanced", "aggressive"]
    for c in gen["candidates"]:
        assert sum(c["weights"].values()) == pytest.approx(1.0)
        assert max(c["weights"].values()) <= c["max_weight"] + 1e-9
        assert c["stats"]["backtest_end"] <= decision
    balanced = gen["candidates"][1]
    created = client.post(f"/api/v1/portfolios/{balanced['candidate_id']}/select", json={"initial_capital": 250000})
    assert created.status_code == 201
    detail = created.json()
    assert detail["status"] == "active"
    assert detail["snapshot"]["cash"] >= 0
    assert all(p["entry_date"] > decision for p in detail["snapshot"]["positions"])
    assert detail["valuation"]["current_value"] > 0
    assert detail["benchmark_available"] is True
    assert len(detail["series"]) > 10

    listed = client.get("/api/v1/portfolios").json()["portfolios"]
    assert listed[0]["portfolio_id"] == detail["portfolio_id"]
    fetched = client.get(f"/api/v1/portfolios/{detail['portfolio_id']}").json()
    assert fetched["score_run_id"] == balanced["score_run_id"]
    revalued = client.post(f"/api/v1/portfolios/{detail['portfolio_id']}/revalue").json()
    assert revalued["valuation"]["as_of"] == status["date_range"]["end"]


def test_portfolio_selected_at_latest_date_is_pending(client: TestClient) -> None:
    gen = client.post("/api/v1/portfolios/generate", json={"capital": 100000}).json()
    detail = client.post(f"/api/v1/portfolios/{gen['candidates'][2]['candidate_id']}/select").json()
    assert detail["status"] == "pending"
    assert detail["snapshot"]["entry_pending"]
    assert detail["valuation"]["status"] == "pending"


def test_unknown_portfolio_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/portfolios/yok").status_code == 404
    assert client.post("/api/v1/portfolios/yok/select").status_code == 404


def test_decision_date_after_data_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/portfolios/generate", json={"capital": 1000, "decision_date": "2030-01-01"})
    assert response.status_code == 400
