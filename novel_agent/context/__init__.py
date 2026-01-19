"""
上下文管理模块

包含：
- ContextManager: 上下文管理器
- CharacterManager: 角色管理器
- WorldManager: 世界观管理器
"""

from .context_manager import ContextManager, ContextItem, CompressionResult
from .character_manager import CharacterManager, Character
from .world_manager import WorldManager, WorldSetting

__all__ = [
    # 管理器
    "ContextManager",
    "CharacterManager",
    "WorldManager",
    # 数据类
    "ContextItem",
    "CompressionResult",
    "Character",
    "WorldSetting"
]
