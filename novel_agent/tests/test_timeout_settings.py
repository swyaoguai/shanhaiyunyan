"""全局超时设置测试。"""

from fastapi.testclient import TestClient

from novel_agent.agent_config import AgentModelConfig
from novel_agent.agents import base_agent as base_agent_module
from novel_agent.agents import llm_client as llm_client_module
from novel_agent.timeout_settings import (
    DEFAULT_LLM_TIMEOUTS,
    DEFAULT_SHORT_STORY_TIMEOUTS,
    get_timeout_settings,
    save_timeout_settings,
)
from novel_agent.web.app import create_app


class _DummyAgent(base_agent_module.BaseAgent):
    def _get_default_prompt(self) -> str:
        return "test"

    async def execute(self, input_data, context=None):
        return {"ok": True}


def test_timeout_settings_defaults_and_persistence(monkeypatch, tmp_path):
    settings_file = tmp_path / "timeout_settings.json"
    monkeypatch.setattr(
        "novel_agent.timeout_settings.TIMEOUT_SETTINGS_FILE",
        settings_file,
    )

    assert get_timeout_settings() == {
        "llm": DEFAULT_LLM_TIMEOUTS,
        "short_story": DEFAULT_SHORT_STORY_TIMEOUTS,
    }

    saved = save_timeout_settings(
        {
            "llm": {"read": 900, "write": 180},
            "short_story": {"quality": 480, "coherence": 420},
        }
    )

    assert saved["llm"]["read"] == 900
    assert saved["llm"]["write"] == 180
    assert saved["short_story"]["quality"] == 480
    assert saved["short_story"]["coherence"] == 420
    assert saved["short_story"]["chapter"] == DEFAULT_SHORT_STORY_TIMEOUTS["chapter"]
    assert get_timeout_settings() == saved


def test_timeout_settings_endpoint_roundtrip(monkeypatch, tmp_path):
    settings_file = tmp_path / "timeout_settings.json"
    monkeypatch.setattr(
        "novel_agent.timeout_settings.TIMEOUT_SETTINGS_FILE",
        settings_file,
    )

    app = create_app()
    client = TestClient(app)

    get_resp = client.get("/api/timeout-settings")
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert data["llm"] == DEFAULT_LLM_TIMEOUTS
    assert data["short_story"] == DEFAULT_SHORT_STORY_TIMEOUTS

    post_resp = client.post(
        "/api/timeout-settings",
        json={
            "llm": {"connect": 45, "read": 900, "write": 150, "pool": 45},
            "short_story": {"quality": 540, "coherence": 510, "chapter": 360},
        },
    )
    assert post_resp.status_code == 200
    payload = post_resp.json()["data"]
    assert payload["llm"]["read"] == 900
    assert payload["llm"]["write"] == 150
    assert payload["short_story"]["quality"] == 540
    assert payload["short_story"]["coherence"] == 510
    assert payload["short_story"]["chapter"] == 360


def test_short_story_timeout_limit_resolution_uses_global_settings(monkeypatch, tmp_path):
    from novel_agent.web.routes import short_story as short_story_routes

    settings_file = tmp_path / "timeout_settings.json"
    monkeypatch.setattr(
        "novel_agent.timeout_settings.TIMEOUT_SETTINGS_FILE",
        settings_file,
    )
    save_timeout_settings({"short_story": {"quality": 555}})

    limits = short_story_routes._get_short_story_prompt_limits("quality")

    assert limits["max_tokens_limit"] == 7000
    assert limits["timeout_seconds"] == 555


def test_llm_client_uses_global_timeout_settings(monkeypatch):
    observed = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            observed.update(kwargs)

    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(
        llm_client_module,
        "get_llm_timeout_settings",
        lambda: {"connect": 21, "read": 654, "write": 87, "pool": 43},
    )

    llm_client_module.LLMClient(
        AgentModelConfig(
            agent_name="tester",
            api_base="https://example.com/v1",
            api_key="key",
            model="demo",
        )
    )

    timeout = observed["timeout"]
    assert timeout.connect == 21
    assert timeout.read == 654
    assert timeout.write == 87
    assert timeout.pool == 43


def test_base_agent_uses_global_timeout_settings(monkeypatch):
    observed = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            observed.update(kwargs)

    monkeypatch.setattr(base_agent_module, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(
        base_agent_module,
        "get_llm_timeout_settings",
        lambda: {"connect": 12, "read": 789, "write": 34, "pool": 56},
    )

    _DummyAgent(
        name="Dummy",
        model_config=AgentModelConfig(
            agent_name="Dummy",
            api_base="https://example.com/v1",
            api_key="key",
            model="demo",
        ),
    )

    timeout = observed["timeout"]
    assert timeout.connect == 12
    assert timeout.read == 789
    assert timeout.write == 34
    assert timeout.pool == 56
