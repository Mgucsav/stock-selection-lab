"""Arka plan günlük veri yenileme testleri (ağ yok)."""

from src.stock_selection.application import AutoRefresher


def test_auto_refresh_runs_when_demo_then_skips_when_fresh(container):
    refresher = AutoRefresher(container.data, max_age_hours=20)
    assert refresher.needs_refresh() is True  # demo modunda
    assert refresher.run_once() is True
    assert refresher.state["last_result"] == "yenilendi"
    assert container.data.status()["is_demo"] is False
    assert refresher.needs_refresh() is False  # az önce yenilendi
    assert refresher.run_once() is False
    assert refresher.state["last_result"] == "güncel"


def test_auto_refresh_disabled_when_zero_hours(container):
    refresher = AutoRefresher(container.data, max_age_hours=0)
    assert refresher.enabled is False
    refresher.start()
    assert refresher._thread is None


def test_auto_refresh_reports_error_and_keeps_data(container):
    container.data.provider.raise_on_batch = True
    refresher = AutoRefresher(container.data, max_age_hours=20)
    assert refresher.run_once() is False
    assert refresher.state["last_result"] == "hata" and refresher.state["last_error"]
    assert container.data.status()["is_demo"] is True
