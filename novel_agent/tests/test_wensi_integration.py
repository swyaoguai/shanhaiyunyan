"""
Wensi 集成基础测试
测试配置和服务模块

注：Wensi是可选集成模块，相关模块未实现时测试将被跳过
"""

import pytest
import asyncio
from pathlib import Path


# 检测Wensi模块是否可用
def _check_wensi_available():
    """检查Wensi模块是否可用"""
    try:
        from novel_agent.wensi_config import WensiConfig
        return True
    except ImportError:
        return False

WENSI_MODULES_AVAILABLE = _check_wensi_available()
skip_wensi = pytest.mark.skipif(
    not WENSI_MODULES_AVAILABLE,
    reason="Wensi modules not available (optional integration)"
)


@skip_wensi
class TestWensiConfig:
    """测试 Wensi 配置模块"""
    
    def test_import_config(self):
        """测试配置模块导入"""
        from novel_agent.wensi_config import (
            WensiConfig,
            WensiConfigManager,
            get_wensi_config_manager,
            get_wensi_config
        )
        assert WensiConfig is not None
        assert WensiConfigManager is not None
    
    def test_default_config(self):
        """测试默认配置"""
        from novel_agent.wensi_config import WensiConfig
        
        config = WensiConfig()
        assert config.api_key == ""
        assert config.base_url == ""
        assert config.default_model == "openai/gpt-4.1"
        assert config.enabled == False
    
    def test_config_is_configured(self):
        """测试配置检测"""
        from novel_agent.wensi_config import WensiConfig
        
        config = WensiConfig()
        assert config.is_configured() == False
        
        config.api_key = "test-key"
        assert config.is_configured() == True


@skip_wensi
class TestWensiService:
    """测试 Wensi 服务模块"""
    
    def test_import_service(self):
        """测试服务模块导入"""
        from novel_agent.wensi_service import (
            WensiService,
            get_wensi_service,
            reset_wensi_service
        )
        assert WensiService is not None
    
    def test_service_without_config(self):
        """测试无配置时服务状态"""
        from novel_agent.wensi_service import WensiService
        
        service = WensiService(base_url="", api_key="")
        
        # 无配置时服务不可用
        assert service.is_available == False


@skip_wensi
class TestWensiAdapter:
    """测试 Wensi 适配器模块"""
    
    def test_import_adapter(self):
        """测试适配器模块导入"""
        from novel_agent.agents import WENSI_AVAILABLE
        
        # 适配器模块应该可以导入
        # 即使 wensi-client 未安装
        assert isinstance(WENSI_AVAILABLE, bool)
    
    def test_adapter_factory(self):
        """测试适配器工厂函数"""
        try:
            from novel_agent.agents.wensi_adapter import (
                WensiAgentAdapter,
                WensiCommunicatorAdapter,
                create_wensi_adapter
            )
            
            adapter = create_wensi_adapter("Communicator")
            assert adapter is not None
            assert isinstance(adapter, WensiCommunicatorAdapter)
            
            adapter = create_wensi_adapter("Worldbuilder")
            assert isinstance(adapter, WensiAgentAdapter)
        except ImportError:
            pytest.skip("wensi-client not installed")


@skip_wensi
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
