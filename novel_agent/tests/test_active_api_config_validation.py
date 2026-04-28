import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from novel_agent.agent_config import AgentConfigManager
from novel_agent.web.app import create_app


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, url, headers=None, json=None):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _build_manager() -> AgentConfigManager:
    temp_dir = tempfile.TemporaryDirectory()
    manager = AgentConfigManager(config_dir=Path(temp_dir.name))
    manager._temp_dir = temp_dir  # prevent cleanup during test
    return manager


def test_set_active_api_config_rejects_unreachable_endpoint(monkeypatch):
    app = create_app()
    manager = _build_manager()
    good = manager.add_api_config(
        name="good",
        api_base="https://good.example/v1",
        api_key="sk-good",
        models=["gpt-5.4"],
    )
    bad = manager.add_api_config(
        name="bad",
        api_base="https://bad.example/v1",
        api_key="sk-bad",
        models=["claude-opus-4-6"],
    )
    manager.set_active_config(good.id, "gpt-5.4")

    monkeypatch.setattr("novel_agent.agent_config.get_config_manager", lambda: manager)
    monkeypatch.setattr(
        "novel_agent.web.routes.settings.httpx.AsyncClient",
        lambda timeout=None: _FakeAsyncClient([_FakeResponse(404, text="Not Found")]),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/api-configs/active", json={"config_id": bad.id, "model": "claude-opus-4-6"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "404" in payload["error"]
    assert manager.get_multi_config().active_config_id == good.id
    assert manager.get_multi_config().active_model == "gpt-5.4"


def test_set_active_api_config_rejects_model_not_in_remote_models(monkeypatch):
    app = create_app()
    manager = _build_manager()
    baseline = manager.add_api_config(
        name="baseline",
        api_base="https://baseline.example/v1",
        api_key="sk-baseline",
        models=["gpt-5.4"],
    )
    manager.set_active_config(baseline.id, "gpt-5.4")
    config = manager.add_api_config(
        name="cfg",
        api_base="https://good.example/v1",
        api_key="sk-good",
        models=["claude-opus-4-6", "gpt-5.4"],
    )

    monkeypatch.setattr("novel_agent.agent_config.get_config_manager", lambda: manager)
    monkeypatch.setattr(
        "novel_agent.web.routes.settings.httpx.AsyncClient",
        lambda timeout=None: _FakeAsyncClient([
            _FakeResponse(200, payload={"data": [{"id": "gpt-5.4"}]}, text='{"data":[{"id":"gpt-5.4"}]}'),
        ]),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/api-configs/active", json={"config_id": config.id, "model": "claude-opus-4-6"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "不在远端模型列表中" in payload["error"]
    assert manager.get_multi_config().active_config_id == baseline.id
    assert manager.get_multi_config().active_model == "gpt-5.4"


def test_set_active_api_config_auto_picks_first_remote_supported_model(monkeypatch):
    app = create_app()
    manager = _build_manager()
    config = manager.add_api_config(
        name="cfg",
        api_base="https://good.example/v1",
        api_key="sk-good",
        models=["claude-opus-4-6", "gpt-5.4", "deepseek-v3.2"],
    )

    monkeypatch.setattr("novel_agent.agent_config.get_config_manager", lambda: manager)
    monkeypatch.setattr(
        "novel_agent.web.routes.settings.httpx.AsyncClient",
        lambda timeout=None: _FakeAsyncClient([
            _FakeResponse(
                200,
                payload={"data": [{"id": "gpt-5.4"}, {"id": "deepseek-v3.2"}]},
                text='{"data":[{"id":"gpt-5.4"},{"id":"deepseek-v3.2"}]}',
            ),
        ]),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/api-configs/active", json={"config_id": config.id, "model": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["active_model"] == "gpt-5.4"
    assert manager.get_multi_config().active_config_id == config.id
    assert manager.get_multi_config().active_model == "gpt-5.4"


def test_test_connection_returns_detailed_quota_error(monkeypatch):
    app = create_app()
    manager = _build_manager()
    config = manager.add_api_config(
        name="cfg",
        api_base="https://good.example/v1",
        api_key="sk-good",
        models=["gpt-5.4"],
    )

    monkeypatch.setattr("novel_agent.agent_config.get_config_manager", lambda: manager)
    monkeypatch.setattr(
        "novel_agent.web.routes.settings.httpx.AsyncClient",
        lambda timeout=None: _FakeAsyncClient([
            _FakeResponse(429, payload={"error": {"message": "quota exceeded"}}, text='{"error":{"message":"quota exceeded"}}'),
        ]),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/test-connection", json={"config_id": config.id, "model": "gpt-5.4"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "quota_exceeded"
    assert "配额已经用完了" in payload["error"]
    assert "联系管理员补额度" in payload["solution"]
    assert payload["title"] == "配额已经用完了"


def test_test_connection_returns_detailed_model_permission_error(monkeypatch):
    app = create_app()
    manager = _build_manager()
    config = manager.add_api_config(
        name="cfg",
        api_base="https://good.example/v1",
        api_key="sk-good",
        models=["claude-opus-4-6"],
    )

    monkeypatch.setattr("novel_agent.agent_config.get_config_manager", lambda: manager)
    monkeypatch.setattr(
        "novel_agent.web.routes.settings.httpx.AsyncClient",
        lambda timeout=None: _FakeAsyncClient([
            _FakeResponse(403, payload={"error": {"message": "model_not_allowed"}}, text='{"error":{"message":"model_not_allowed"}}'),
        ]),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/test-connection", json={"config_id": config.id, "model": "claude-opus-4-6"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "model_not_allowed"
    assert "模型 claude-opus-4-6 没开权限" in payload["error"]
    assert "检查模型白名单" in payload["solution"]
    assert payload["title"] == "模型 claude-opus-4-6 没开权限"
