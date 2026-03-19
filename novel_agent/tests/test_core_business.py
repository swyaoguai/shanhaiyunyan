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
from pathlib import Path
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
