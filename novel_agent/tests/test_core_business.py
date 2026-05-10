"""
核心业务逻辑测试

覆盖关键功能：
- LLM客户端调用
- 项目存储CRUD
- 频率限制
- 日志净化

模块职责说明：确保核心业务逻辑正确性和稳定性。
"""

import pytest
import asyncio
import tempfile
import os
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock


# ========================================
# LLM客户端测试
# ========================================

class TestLLMClient:
    """LLM客户端测试"""

    def test_llm_client_init(self):
        """测试LLM客户端初始化"""
        from novel_agent.agents.llm_client import LLMClient, RetryConfig
        from novel_agent.agent_config import AgentModelConfig

        config = AgentModelConfig(
            model="gpt-4",
            temperature=0.7,
            max_tokens=4096
        )

        client = LLMClient(config, metrics_namespace="test")
        assert client.model_name == "gpt-4"
        assert client.temperature == 0.7
        assert client.max_tokens == 4096

    def test_retry_config_defaults(self):
        """测试重试配置默认值"""
        from novel_agent.agents.llm_client import RetryConfig
        from novel_agent.constants import RETRY_DEFAULTS

        config = RetryConfig()
        assert config.max_retries == RETRY_DEFAULTS.MAX_RETRIES
        assert config.delay == RETRY_DEFAULTS.INITIAL_DELAY
        assert config.backoff == RETRY_DEFAULTS.BACKOFF_MULTIPLIER

    @pytest.mark.asyncio
    async def test_llm_call_with_mock(self):
        """测试LLM调用（模拟）"""
        from novel_agent.agents.llm_client import LLMClient
        from novel_agent.agent_config import AgentModelConfig

        config = AgentModelConfig(
            model="gpt-4",
            temperature=0.7,
            max_tokens=100,
            api_key="test-key",
            api_base="https://api.test.com/v1"
        )

        client = LLMClient(config, metrics_namespace="test")

        # 模拟API响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            result = await client.call(
                [{"role": "user", "content": "Hello"}],
                enable_retry=False
            )

            assert result == "Test response"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_call_estimates_tokens_when_provider_omits_usage(self):
        """兼容不返回 usage 字段的 OpenAI 兼容 API。"""
        from novel_agent.agents.llm_client import LLMClient
        from novel_agent.agent_config import AgentModelConfig

        config = AgentModelConfig(
            model="compat-model",
            temperature=0.7,
            max_tokens=100,
            api_key="test-key",
            api_base="https://api.test.com/v1"
        )
        client = LLMClient(config, metrics_namespace="test")
        captured = {}

        def capture_metrics(tokens_in, tokens_out, duration, success, error=None):
            captured.update({
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "success": success,
            })

        client._record_metrics = capture_metrics

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这是一段兼容接口返回的内容"
        mock_response.usage = None

        with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            result = await client.call(
                [{"role": "user", "content": "请写一段中文内容"}],
                enable_retry=False
            )

        assert result == "这是一段兼容接口返回的内容"
        assert captured["success"] is True
        assert captured["tokens_in"] > 0
        assert captured["tokens_out"] > 0

    @pytest.mark.asyncio
    async def test_llm_call_accepts_dict_usage_payload(self):
        """兼容以 dict 返回 usage 的 OpenAI 兼容 API。"""
        from novel_agent.agents.llm_client import LLMClient
        from novel_agent.agent_config import AgentModelConfig

        config = AgentModelConfig(
            model="compat-model",
            temperature=0.7,
            max_tokens=100,
            api_key="test-key",
            api_base="https://api.test.com/v1"
        )
        client = LLMClient(config, metrics_namespace="test")
        captured = {}

        def capture_metrics(tokens_in, tokens_out, duration, success, error=None):
            captured.update({
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "success": success,
            })

        client._record_metrics = capture_metrics

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = {"prompt_tokens": 31, "completion_tokens": 17, "total_tokens": 48}

        with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            result = await client.call(
                [{"role": "user", "content": "Hello"}],
                enable_retry=False
            )

        assert result == "Test response"
        assert captured == {
            "tokens_in": 31,
            "tokens_out": 17,
            "success": True,
        }

    @pytest.mark.asyncio
    async def test_openai_responses_usage_payload_is_recorded(self):
        """Responses API 的 input/output usage 会进入统计。"""
        from novel_agent.agents.llm_client import LLMClient
        from novel_agent.agent_config import AgentModelConfig

        config = AgentModelConfig(
            model="gpt-4.1",
            temperature=0.7,
            max_tokens=100,
            api_key="test-key",
            api_base="https://api.test.com/v1",
            api_type="openai_responses",
        )
        client = LLMClient(config, metrics_namespace="test")
        captured = {}

        def capture_metrics(tokens_in, tokens_out, duration, success, error=None):
            captured.update({
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "success": success,
            })

        client._record_metrics = capture_metrics

        mock_response = SimpleNamespace(
            output_text="Responses result",
            output=[],
            usage=SimpleNamespace(input_tokens=44, output_tokens=22),
        )

        with patch.object(client._client.responses, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            result = await client.call(
                [{"role": "user", "content": "Hello"}],
                enable_retry=False,
            )

        assert result == "Responses result"
        assert captured == {
            "tokens_in": 44,
            "tokens_out": 22,
            "success": True,
        }

    @pytest.mark.asyncio
    async def test_anthropic_usage_payload_is_recorded(self):
        """Anthropic API 的 input/output usage 会进入统计。"""
        from novel_agent.agents.llm_client import LLMClient
        from novel_agent.agent_config import AgentModelConfig

        async def fake_create(**params):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Anthropic result")],
                usage=SimpleNamespace(input_tokens=55, output_tokens=33),
            )

        client = object.__new__(LLMClient)
        client.model_config = AgentModelConfig(
            model="claude-3-5-sonnet",
            temperature=0.7,
            max_tokens=100,
            api_key="test-key",
            api_base="https://api.anthropic.com",
            api_type="anthropic",
        )
        client.metrics_namespace = "test"
        client._api_type = "anthropic"
        client._client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
        captured = {}

        def capture_metrics(tokens_in, tokens_out, duration, success, error=None):
            captured.update({
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "success": success,
            })

        client._record_metrics = capture_metrics

        result = await client._call_anthropic(
            [{"role": "user", "content": "Hello"}],
            temperature=None,
            max_tokens=None,
            system_prompt=None,
            stream=False,
        )

        assert result == "Anthropic result"
        assert captured == {
            "tokens_in": 55,
            "tokens_out": 33,
            "success": True,
        }

    def test_anthropic_base_url_strips_v1_suffix(self):
        """测试 Anthropic base_url 以根地址传给 SDK，避免 /v1/v1/messages。"""
        from novel_agent.agents.llm_client import LLMClient

        assert LLMClient._normalize_anthropic_base_url("https://api.anthropic.com/v1") == "https://api.anthropic.com"
        assert LLMClient._normalize_anthropic_base_url("https://proxy.example/anthropic/v1/") == "https://proxy.example/anthropic"
        assert LLMClient._normalize_anthropic_base_url("https://proxy.example/anthropic") == "https://proxy.example/anthropic"

    def test_anthropic_message_builder_preserves_tool_result_blocks(self):
        """测试 Anthropic 多轮工具结果按 user content block 续传。"""
        from novel_agent.agents.llm_client import LLMClient

        client = object.__new__(LLMClient)
        messages, system_prompt = client._build_anthropic_messages(
            [
                {"role": "system", "content": "system A"},
                {"role": "user", "content": "调用工具"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "我将调用工具"},
                        {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {"q": "Claude"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "结果"},
                    ],
                },
            ],
            "system B",
        )

        assert system_prompt == "system A\n\nsystem B"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"][1]["type"] == "tool_use"
        assert messages[2]["content"][0]["tool_use_id"] == "toolu_1"

    @pytest.mark.asyncio
    async def test_anthropic_stream_parses_content_block_tool_input_after_stop(self, caplog):
        """测试 Anthropic 流式工具参数只拼接到 content_block_stop 后解析。"""
        from novel_agent.agents.llm_client import LLMClient

        caplog.set_level("INFO", logger="novel_agent.agents.llm_client")

        class FakeAnthropicStream:
            def __init__(self, events):
                self._events = events

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def __aiter__(self):
                self._iter = iter(self._events)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        class FakeMessages:
            def stream(self, **params):
                return FakeAnthropicStream([
                    SimpleNamespace(
                        type="content_block_delta",
                        index=0,
                        delta=SimpleNamespace(type="text_delta", text="先查"),
                    ),
                    SimpleNamespace(
                        type="content_block_start",
                        index=1,
                        content_block=SimpleNamespace(type="tool_use", id="toolu_1", name="search", input={}),
                    ),
                    SimpleNamespace(
                        type="content_block_delta",
                        index=1,
                        delta=SimpleNamespace(type="input_json_delta", partial_json='{"query":'),
                    ),
                    SimpleNamespace(
                        type="content_block_delta",
                        index=1,
                        delta=SimpleNamespace(type="input_json_delta", partial_json='"Claude"}'),
                    ),
                    SimpleNamespace(type="content_block_stop", index=1),
                    SimpleNamespace(
                        type="message_delta",
                        delta=SimpleNamespace(stop_reason="tool_use"),
                        usage=SimpleNamespace(output_tokens=12),
                    ),
                ])

        client = object.__new__(LLMClient)
        client._client = SimpleNamespace(messages=FakeMessages())
        client.metrics_namespace = "test"

        usage_collector = {}
        chunks = []
        async for chunk in client._stream_anthropic({"model": "claude-test"}, usage_collector=usage_collector):
            chunks.append(chunk)

        assert "".join(chunks) == "先查"
        assert usage_collector["usage"].output_tokens == 12
        assert "Anthropic tool_use parsed" in caplog.text
        assert "search" in caplog.text

    def test_anthropic_non_stream_tool_use_returns_json_when_no_text(self):
        """测试非流式 Anthropic tool_use 响应没有文本时返回可解析 JSON。"""
        from novel_agent.agents.llm_client import LLMClient

        client = object.__new__(LLMClient)
        response = SimpleNamespace(
            content=[
                SimpleNamespace(type="tool_use", id="toolu_1", name="search", input={"query": "Claude"}),
            ]
        )

        content, tool_uses = client._extract_anthropic_content(response)
        assert content == ""
        assert tool_uses == [{"id": "toolu_1", "name": "search", "input": {"query": "Claude"}}]
        assert json.loads(json.dumps({"tool_calls": tool_uses}, ensure_ascii=False))["tool_calls"][0]["id"] == "toolu_1"


# ========================================
# 项目存储测试
# ========================================

class TestProjectStore:
    """项目存储测试"""

    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        os.unlink(f.name)

    def test_project_store_init(self, temp_db):
        """测试项目存储初始化"""
        from novel_agent.utils.project_store import ProjectStore

        store = ProjectStore(temp_db)
        assert Path(temp_db).exists()
        store.close()

    def test_create_and_get_project(self, temp_db):
        """测试创建和获取项目"""
        from novel_agent.utils.project_store import ProjectStore, ProjectMeta

        store = ProjectStore(temp_db)

        project = ProjectMeta(
            id="test-001",
            name="测试小说",
            description="这是一个测试项目",
            novel_type="玄幻"
        )

        # 创建
        created = store.create(project)
        assert created.id == "test-001"
        assert created.name == "测试小说"

        # 获取
        retrieved = store.get("test-001")
        assert retrieved is not None
        assert retrieved.name == "测试小说"

        store.close()

    def test_update_project(self, temp_db):
        """测试更新项目"""
        from novel_agent.utils.project_store import ProjectStore, ProjectMeta

        store = ProjectStore(temp_db)

        project = ProjectMeta(id="test-002", name="原始名称")
        store.create(project)

        # 更新
        updated = store.update("test-002", name="新名称", word_count=1000)
        assert updated is not None
        assert updated.name == "新名称"
        assert updated.word_count == 1000

        store.close()

    def test_delete_project(self, temp_db):
        """测试删除项目"""
        from novel_agent.utils.project_store import ProjectStore, ProjectMeta

        store = ProjectStore(temp_db)

        project = ProjectMeta(id="test-003", name="待删除")
        store.create(project)

        # 删除
        success = store.delete("test-003")
        assert success is True

        # 确认删除
        retrieved = store.get("test-003")
        assert retrieved is None

        store.close()

    def test_list_projects(self, temp_db):
        """测试列出项目"""
        from novel_agent.utils.project_store import ProjectStore, ProjectMeta

        store = ProjectStore(temp_db)

        # 创建多个项目
        for i in range(3):
            store.create(ProjectMeta(
                id=f"test-{i}",
                name=f"项目{i}",
                status="planning" if i < 2 else "completed"
            ))

        # 列出所有
        all_projects = store.list_all()
        assert len(all_projects) == 3

        # 按状态过滤
        planning_projects = store.list_all(status="planning")
        assert len(planning_projects) == 2

        store.close()


# ========================================
# 频率限制测试
# ========================================

class TestRateLimit:
    """频率限制测试"""

    def test_rate_limit_config(self):
        """测试频率限制配置"""
        from novel_agent.web.middleware.rate_limit import RateLimitConfig
        from novel_agent.constants import RATE_LIMIT_DEFAULTS

        config = RateLimitConfig()
        assert config.requests_per_minute == RATE_LIMIT_DEFAULTS.REQUESTS_PER_MINUTE
        assert config.requests_per_hour == RATE_LIMIT_DEFAULTS.REQUESTS_PER_HOUR

    def test_rate_limiter_allows_requests(self):
        """测试频率限制允许正常请求"""
        from novel_agent.web.middleware.rate_limit import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=10,
            burst_limit=5
        )
        limiter = RateLimiter(config)

        # 模拟请求
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # 前10次应该都允许
        for _ in range(10):
            is_allowed, _, _ = limiter.check(mock_request)
            assert is_allowed is True

    def test_rate_limiter_blocks_excess(self):
        """测试频率限制阻止超量请求"""
        from novel_agent.web.middleware.rate_limit import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=5,
            burst_limit=3,
            cooldown_seconds=1
        )
        limiter = RateLimiter(config)

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # 5次允许
        for _ in range(5):
            is_allowed, _, _ = limiter.check(mock_request)
            assert is_allowed is True

        # 第6次应该被阻止
        is_allowed, error_msg, retry_after = limiter.check(mock_request)
        assert is_allowed is False
        assert error_msg is not None
        assert retry_after > 0


# ========================================
# 日志净化测试
# ========================================

class TestLogSanitizer:
    """日志净化测试"""

    def test_sanitize_api_key(self):
        """测试净化API密钥"""
        from novel_agent.utils.log_sanitizer import sanitize_for_log

        data = {
            "api_key": "sk-1234567890abcdef",
            "model": "gpt-4"
        }

        sanitized = sanitize_for_log(data)

        assert sanitized["api_key"] == "***"
        assert sanitized["model"] == "gpt-4"

    def test_sanitize_nested_dict(self):
        """测试净化嵌套字典"""
        from novel_agent.utils.log_sanitizer import sanitize_for_log

        data = {
            "config": {
                "api_key": "secret-key",
                "password": "my-password"
            },
            "name": "test"
        }

        sanitized = sanitize_for_log(data)

        assert sanitized["config"]["api_key"] == "***"
        assert sanitized["config"]["password"] == "***"
        assert sanitized["name"] == "test"

    def test_sanitize_string_patterns(self):
        """测试净化字符串中的敏感模式"""
        from novel_agent.utils.log_sanitizer import sanitize_for_log

        text = "API Key: sk-proj-abcdefghijklmnopqrstuvwxyz123456"

        sanitized = sanitize_for_log(text)

        assert "sk-proj-" not in sanitized
        assert "API Key:" in sanitized  # 保留非敏感部分


# ========================================
# 运行测试
# ========================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
