from fastapi.testclient import TestClient

from novel_agent.utils.token_stats import TokenStatsStore
from novel_agent.web.app import create_app


class _Project:
    current_project_id = "project-a"
    projects = {"project-a": object()}


def test_token_stats_routes_default_to_all_scope_and_can_filter_current(monkeypatch, tmp_path):
    store = TokenStatsStore(db_path=str(tmp_path / "token_stats.db"))
    store.record("AgentA", "model-a", project_id="project-a", tokens_in=100, tokens_out=20)
    store.record("AgentB", "model-b", project_id="project-b", tokens_in=30, tokens_out=10)

    monkeypatch.setattr("novel_agent.utils.token_stats.get_token_stats_store", lambda: store)
    monkeypatch.setattr("novel_agent.web.routes.token_stats._get_project_manager_safe", lambda: _Project(), raising=False)

    client = TestClient(create_app())
    all_summary = client.get("/api/token-stats/summary?days=7").json()
    current_summary = client.get("/api/token-stats/summary?days=7&scope=current").json()
    filters = client.get("/api/token-stats/filters").json()

    assert all_summary["total_tokens"] == 160
    assert all_summary["filter_project_id"] is None
    assert current_summary["total_tokens"] == 120
    assert current_summary["filter_project_id"] == "project-a"
    assert filters["scope"] == "all"
    assert filters["current_project_id"] == "project-a"
    assert filters["models"] == ["model-a", "model-b"]

    store.close()


def test_token_stats_cleanup_orphans_uses_project_registry(monkeypatch, tmp_path):
    store = TokenStatsStore(db_path=str(tmp_path / "token_stats.db"))
    store.record("AgentA", "model-a", project_id="project-a", tokens_in=100, tokens_out=20)
    store.record("AgentB", "model-b", project_id="deleted-project", tokens_in=30, tokens_out=10)

    monkeypatch.setattr("novel_agent.utils.token_stats.get_token_stats_store", lambda: store)
    monkeypatch.setattr("novel_agent.web.routes.token_stats._get_project_manager_safe", lambda: _Project(), raising=False)

    client = TestClient(create_app())
    response = client.post("/api/token-stats/cleanup-orphans")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert store.get_summary(days=7)["total_tokens"] == 120

    store.close()
