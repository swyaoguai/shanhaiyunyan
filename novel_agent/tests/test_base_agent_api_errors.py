import pytest

from novel_agent.agents.base_agent import BaseAgent


class _ErrorParsingAgent:
    name = "Communicator"


class _MinimalAgent(BaseAgent):
    def _get_default_prompt(self) -> str:
        return "test"

    async def execute(self, input_data, context=None):
        return {"success": True}


class _FakeModelConfig:
    api_base = "https://api.loveatri.su/v1"


class _BlockedCompletions:
    async def create(self, **_params):
        raise Exception("Your request was blocked.")


class _BlockedChat:
    completions = _BlockedCompletions()


class _BlockedClient:
    chat = _BlockedChat()


def test_blocked_request_error_mentions_current_agent_config():
    message = BaseAgent._parse_api_error(
        _ErrorParsingAgent(),
        "PermissionDeniedError: Your request was blocked.",
        "gpt-5.4-mini",
        "https://api.loveatri.su/v1",
    )

    assert message is not None
    assert "模型服务拒绝了本次请求" in message
    assert "当前Agent：Communicator" in message
    assert "检查“Communicator”的独立模型配置" in message
    assert "不必强制所有Agent统一" in message


@pytest.mark.asyncio
async def test_stream_response_converts_blocked_request_to_friendly_error():
    agent = object.__new__(_MinimalAgent)
    agent.name = "Communicator"
    agent.model_config = _FakeModelConfig()
    agent.client = _BlockedClient()
    agent._parse_api_error = BaseAgent._parse_api_error.__get__(agent, BaseAgent)

    stream = BaseAgent._stream_response(agent, {"model": "gpt-5.4-mini"})

    with pytest.raises(Exception) as exc_info:
        async for _chunk in stream:
            pass

    assert "模型服务拒绝了本次请求" in str(exc_info.value)
    assert "当前Agent：Communicator" in str(exc_info.value)
