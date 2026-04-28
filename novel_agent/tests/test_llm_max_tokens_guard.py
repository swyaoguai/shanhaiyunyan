"""Tests for max_tokens normalization in LLM callers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from novel_agent.agent_config import AgentModelConfig
from novel_agent.agents.base_agent import BaseAgent
from novel_agent.agents.llm_client import LLMClient
from novel_agent.utils.llm_params import PROVIDER_SAFE_MAX_TOKENS, normalize_max_tokens


class _FakeCompletions:
    def __init__(self, captured: dict):
        self._captured = captured

    async def create(self, **params):
        self._captured.update(params)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


class _FakeClient:
    def __init__(self, captured: dict):
        self.chat = SimpleNamespace(completions=_FakeCompletions(captured))


class _DummyAgent(BaseAgent):
    def __init__(self, captured: dict, model_config: AgentModelConfig):
        self._captured = captured
        super().__init__(name="DummyAgent", prompt_file=None, model_config=model_config)

    def _create_client(self):
        return _FakeClient(self._captured)

    def _get_default_prompt(self) -> str:
        return "test"

    async def execute(self, input_data, context=None):
        return {"success": True}


def test_normalize_max_tokens_clamps_and_recovers_invalid_values():
    assert normalize_max_tokens(PROVIDER_SAFE_MAX_TOKENS + 500) == PROVIDER_SAFE_MAX_TOKENS
    assert normalize_max_tokens(0) == 4096
    assert normalize_max_tokens("bad-value") == 4096


def test_base_agent_caps_oversized_max_tokens_before_api_call():
    captured = {}
    agent = _DummyAgent(
        captured,
        AgentModelConfig(
            agent_name="DummyAgent",
            api_base="https://example.com/v1",
            api_key="test-key",
            model="test-model",
            max_tokens=99999,
        ),
    )

    result = asyncio.run(
        agent.call_llm(
            [{"role": "user", "content": "hello"}],
            enable_retry=False,
        )
    )

    assert result == "ok"
    assert captured["max_tokens"] == PROVIDER_SAFE_MAX_TOKENS


def test_llm_client_caps_oversized_max_tokens_before_api_call():
    captured = {}
    client = LLMClient(
        AgentModelConfig(
            agent_name="LLMClient",
            api_base="https://example.com/v1",
            api_key="test-key",
            model="test-model",
            max_tokens=65535,
        ),
        metrics_namespace="test",
    )
    client._client = _FakeClient(captured)

    result = asyncio.run(
        client.call(
            [{"role": "user", "content": "hello"}],
            enable_retry=False,
        )
    )

    assert result == "ok"
    assert captured["max_tokens"] == PROVIDER_SAFE_MAX_TOKENS
