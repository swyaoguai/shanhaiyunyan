"""
Letta 集成基础测试
测试配置和服务模块

注：Letta是可选集成模块，相关模块未实现时测试将被跳过
"""

import pytest
import asyncio
from pathlib import Path


# 检测Letta模块是否可用
def _check_letta_available():
    """检查Letta模块是否可用"""
    try:
        from novel_agent.letta_config import LettaConfig
        return True
    except ImportError:
        return False

LETTA_MODULES_AVAILABLE = _check_letta_available()
skip_letta = pytest.mark.skipif(
    not LETTA_MODULES_AVAILABLE,
    reason="Letta modules not available (optional integration)"
)


@skip_letta
class TestLettaConfig:
    """测试 Letta 配置模块"""
    
    def test_import_config(self):
        """测试配置模块导入"""
        from novel_agent.letta_config import (
            LettaConfig,
            LettaConfigManager,
            get_letta_config_manager,
            get_letta_config
        )
        assert LettaConfig is not None
        assert LettaConfigManager is not None
    
    def test_default_config(self):
        """测试默认配置"""
        from novel_agent.letta_config import LettaConfig
        
        config = LettaConfig()
        assert config.api_key == ""
        assert config.base_url == ""
        assert config.default_model == "openai/gpt-4.1"
        assert config.enabled == False
    
    def test_config_is_configured(self):
        """测试配置检测"""
        from novel_agent.letta_config import LettaConfig
        
        config = LettaConfig()
        assert config.is_configured() == False
        
        config.api_key = "test-key"
        assert config.is_configured() == True


@skip_letta
class TestLettaService:
    """测试 Letta 服务模块"""
    
    def test_import_service(self):
        """测试服务模块导入"""
        from novel_agent.letta_service import (
            LettaService,
            AgentInfo,
            get_letta_service,
            reset_letta_service
        )
        assert LettaService is not None
        assert AgentInfo is not None
    
    def test_service_without_config(self):
        """测试无配置时服务状态"""
        from novel_agent.letta_service import LettaService
        from novel_agent.letta_config import LettaConfig
        
        config = LettaConfig()  # 无 API key
        service = LettaService(config)
        
        # 无配置时服务不可用
        assert service.is_available == False


@skip_letta
class TestLettaAdapter:
    """测试 Letta 适配器模块"""
    
    def test_import_adapter(self):
        """测试适配器模块导入"""
        from novel_agent.agents import LETTA_AVAILABLE
        
        # 适配器模块应该可以导入
        # 即使 letta-client 未安装
        assert isinstance(LETTA_AVAILABLE, bool)
    
    def test_adapter_factory(self):
        """测试适配器工厂函数"""
        try:
            from novel_agent.agents.letta_adapter import (
                LettaAgentAdapter,
                LettaCommunicatorAdapter,
                create_letta_adapter
            )
            
            adapter = create_letta_adapter("Communicator")
            assert adapter is not None
            assert isinstance(adapter, LettaCommunicatorAdapter)
            
            adapter = create_letta_adapter("Worldbuilder")
            assert isinstance(adapter, LettaAgentAdapter)
        except ImportError:
            pytest.skip("letta-client not installed")


@skip_letta
class TestMemoryManager:
    """测试记忆管理器模块"""
    
    def test_import_memory_manager(self):
        """测试记忆管理器导入"""
        from novel_agent.memory_manager import (
            MemoryManager,
            NovelMemoryBlocks,
            get_memory_manager
        )
        assert MemoryManager is not None
        assert NovelMemoryBlocks is not None
    
    def test_memory_blocks_structure(self):
        """测试记忆块结构"""
        from novel_agent.memory_manager import NovelMemoryBlocks
        
        blocks = NovelMemoryBlocks()
        assert hasattr(blocks, "persona")
        assert hasattr(blocks, "project")
        assert hasattr(blocks, "characters")
        assert hasattr(blocks, "worldview")
        assert hasattr(blocks, "plot_summary")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
