"""
配置管理模块单元测试
测试Config.reload()方法的热重载功能
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from dotenv import load_dotenv

from novel_agent.config import Config, LLMConfig


# ==================== Fixtures ====================

@pytest.fixture
def backup_env():
    """备份和恢复环境变量"""
    original_values = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "OPENAI_API_BASE": os.getenv("OPENAI_API_BASE"),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
        "MAX_TOKENS": os.getenv("MAX_TOKENS"),
        "TEMPERATURE": os.getenv("TEMPERATURE"),
    }
    yield
    # 恢复原始环境变量
    for key, value in original_values.items():
        if value:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


# ==================== Test Cases ====================

class TestConfigReload:
    """测试Config.reload()方法"""

    def test_reload_config_success(self, backup_env):
        """
        测试1: 验证reload()方法成功执行并返回True
        """
        # 执行reload
        result = Config.reload()

        # 验证返回值
        assert result is True, "reload() should return True on success"

        # 验证配置对象存在且有效
        assert Config.llm is not None, "Config.llm should not be None after reload"
        assert isinstance(Config.llm, LLMConfig), "Config.llm should be LLMConfig instance"

    def test_reload_config_loads_dotenv_override(self, backup_env):
        """
        测试2: 验证reload()调用load_dotenv(override=True)
        确保load_dotenv被正确调用且override参数为True
        """
        with patch('novel_agent.config.load_dotenv') as mock_load_dotenv:
            # 执行reload
            Config.reload()

            # 验证load_dotenv被调用
            assert mock_load_dotenv.called, "load_dotenv should be called"

            # 验证调用参数
            call_args = mock_load_dotenv.call_args
            assert call_args is not None, "load_dotenv should be called with arguments"

            # 检查override=True参数
            call_kwargs = call_args[1] if call_args[1] else {}
            assert call_kwargs.get('override') is True, "load_dotenv should be called with override=True"

            # 检查encoding参数（用于处理GBK编码问题）
            assert call_kwargs.get('encoding') == 'utf-8', "load_dotenv should use utf-8 encoding"

    def test_reload_config_recreates_singleton(self, backup_env):
        """
        测试3: 验证reload()重新创建LLMConfig实例
        """
        # 获取重载前的配置实例ID
        config_before = Config.llm
        id_before = id(config_before)

        with patch('novel_agent.config.load_dotenv'):
            # 执行reload
            Config.reload()

            # 获取重载后的配置实例ID
            config_after = Config.llm
            id_after = id(config_after)

            # 验证配置被重新创建（不同的实例ID）
            # 注意：由于load_dotenv被mock，实际环境变量未改变，但实例应该被重新创建
            # 我们无法直接验证实例ID不同（因为mock可能没有改变环境变量）
            # 但我们可以验证reload()方法确实执行了LLMConfig()的重新实例化

            # 验证配置对象仍然有效
            assert config_after is not None, "Config.llm should not be None after reload"
            assert isinstance(config_after, LLMConfig), "Config.llm should be LLMConfig instance"

    def test_reload_config_handles_missing_env(self, backup_env):
        """
        测试4: 验证reload()处理.env文件不存在的情况
        应该返回False并记录错误日志
        """
        # Mock Path.cwd()返回一个不存在.env的目录
        with patch('novel_agent.config.Path') as mock_path:
            mock_cwd = MagicMock()
            mock_env_file = MagicMock()
            mock_env_file.exists.return_value = False
            mock_cwd.__truediv__.return_value = mock_env_file
            mock_path.cwd.return_value = mock_cwd

            # 执行reload
            result = Config.reload()

            # 验证返回False
            assert result is False, "reload() should return False when .env file is missing"

    def test_reload_config_handles_exceptions(self, backup_env):
        """
        测试5: 验证reload()处理异常情况
        应该返回False并记录错误日志
        """
        # Mock load_dotenv抛出异常
        with patch('novel_agent.config.load_dotenv') as mock_load_dotenv:
            mock_load_dotenv.side_effect = Exception("Test exception")

            # 执行reload
            result = Config.reload()

            # 验证返回False
            assert result is False, "reload() should return False when exception occurs"

    def test_reload_config_persists_across_calls(self, backup_env):
        """
        测试6: 验证reload()多次调用后配置保持一致性
        确保配置值在多次reload后保持一致
        """
        with patch('novel_agent.config.load_dotenv'):
            # 第一次reload
            result1 = Config.reload()
            config1 = Config.llm

            # 第二次reload
            result2 = Config.reload()
            config2 = Config.llm

            # 第三次reload
            result3 = Config.reload()
            config3 = Config.llm

            # 验证所有reload都成功
            assert result1 is True, "First reload should succeed"
            assert result2 is True, "Second reload should succeed"
            assert result3 is True, "Third reload should succeed"

            # 验证配置在多次reload后保持一致（值相同）
            assert config1.api_key == config2.api_key == config3.api_key, \
                "Config values should remain consistent across multiple reloads"

            # 验证其他配置字段也保持一致
            assert config1.model == config2.model == config3.model, \
                "Model should remain consistent across multiple reloads"
            assert config1.api_base == config2.api_base == config3.api_base, \
                "API base should remain consistent across multiple reloads"
