import pytest

from novel_agent.agent_config import APIKeyEntry, AgentModelConfig
from novel_agent.agents import llm_client as llm_client_module
from novel_agent.agents.api_key_rotation import get_api_key_rotation_service


class _StatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _Usage:
    prompt_tokens = 3
    completion_tokens = 4


class _Message:
    content = "rotation-ok"


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]
    usage = _Usage()


@pytest.mark.asyncio
async def test_llm_client_rotates_from_failed_key_to_next(monkeypatch):
    get_api_key_rotation_service().reset()
    monkeypatch.setenv("ENABLE_API_KEY_ROTATION", "true")
    observed_keys = []

    class FakeCompletions:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def create(self, **kwargs):
            observed_keys.append(self.api_key)
            if self.api_key == "bad-key":
                raise _StatusError(401)
            return _Response()

    class FakeChat:
        def __init__(self, api_key: str):
            self.completions = FakeCompletions(api_key)

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat(kwargs["api_key"])

    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", FakeAsyncOpenAI)

    client = llm_client_module.LLMClient(
        AgentModelConfig(
            agent_name="tester",
            api_config_id="cfg",
            api_base="https://example.com/v1",
            api_key="bad-key",
            api_keys=[
                APIKeyEntry(id="bad", key="bad-key"),
                APIKeyEntry(id="good", key="good-key"),
            ],
            model="demo",
        ),
        metrics_namespace="test",
    )

    result = await client.call(
        messages=[{"role": "user", "content": "hello"}],
        enable_retry=False,
    )

    assert result == "rotation-ok"
    assert observed_keys == ["bad-key", "good-key"]


@pytest.mark.asyncio
async def test_llm_client_single_key_keeps_existing_behavior_when_disabled(monkeypatch):
    get_api_key_rotation_service().reset()
    monkeypatch.setenv("ENABLE_API_KEY_ROTATION", "false")
    observed_keys = []

    class FakeCompletions:
        async def create(self, **kwargs):
            return _Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            observed_keys.append(kwargs["api_key"])
            self.chat = FakeChat()

    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", FakeAsyncOpenAI)

    client = llm_client_module.LLMClient(
        AgentModelConfig(
            agent_name="tester",
            api_base="https://example.com/v1",
            api_key="only-key",
            model="demo",
        ),
        metrics_namespace="test",
    )

    assert await client.call([{"role": "user", "content": "hello"}], enable_retry=False) == "rotation-ok"
    assert observed_keys == ["only-key"]
