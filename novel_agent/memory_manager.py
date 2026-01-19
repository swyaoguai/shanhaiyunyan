"""
小说创作记忆管理器
管理 Letta Agent 的记忆结构，针对小说创作场景优化
"""

import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from .letta_service import get_letta_service, LettaService
from .project_manager import get_project_manager
from .constants import WRITING_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class NovelMemoryBlocks:
    """小说创作记忆块结构"""
    # 核心记忆
    persona: str = ""           # Agent 人格
    project: str = ""           # 项目状态
    
    # 创作记忆
    characters: str = ""        # 角色摘要
    worldview: str = ""         # 世界观摘要
    plot_summary: str = ""      # 剧情摘要
    
    # 交互记忆
    user_preferences: str = ""  # 用户偏好
    conversation: str = ""      # 对话摘要


class MemoryManager:
    """
    记忆管理器
    同步项目数据与 Letta Agent 记忆
    """
    
    def __init__(self):
        self.letta_service: LettaService = get_letta_service()
        self.project_manager = get_project_manager()
    
    async def sync_project_to_memory(
        self, 
        agent_type: str, 
        agent_id: str
    ) -> bool:
        """
        将项目数据同步到 Agent 记忆
        
        Args:
            agent_type: Agent 类型
            agent_id: Letta Agent ID
            
        Returns:
            是否成功
        """
        if not self.letta_service.is_available:
            return False
        
        try:
            # 获取当前项目
            project = self.project_manager.get_current_project()
            if not project:
                return False
            
            # 构建项目状态摘要
            project_summary = f"""项目名称: {project.name}
项目描述: {project.description}
创建时间: {project.created_at}
章节数: {project.chapter_count}
字数: {project.word_count}"""
            
            # 更新 project 记忆块
            await self.letta_service.update_memory(
                agent_id, 
                "project", 
                project_summary
            )
            
            # 根据 Agent 类型同步相关数据
            if agent_type in ["Worldbuilder", "ChapterWriter"]:
                await self._sync_worldbuilding(agent_id)
            
            if agent_type in ["Outliner", "ChapterWriter"]:
                await self._sync_outline(agent_id)
            
            if agent_type in ["ChapterWriter", "Polisher"]:
                await self._sync_characters(agent_id)
            
            logger.info(f"Synced project data to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync project to memory: {e}")
            return False
    
    async def _sync_worldbuilding(self, agent_id: str) -> None:
        """同步世界观数据"""
        worldbuilding = self.project_manager.load_project_data("worldbuilding")
        if worldbuilding:
            summary = self._summarize_worldbuilding(worldbuilding)
            await self.letta_service.update_memory(agent_id, "worldview", summary)
    
    async def _sync_outline(self, agent_id: str) -> None:
        """同步大纲数据"""
        outline = self.project_manager.load_project_data("outline")
        if outline:
            summary = self._summarize_outline(outline)
            await self.letta_service.update_memory(agent_id, "plot_summary", summary)
    
    async def _sync_characters(self, agent_id: str) -> None:
        """同步角色数据"""
        characters = self.project_manager.load_project_data("characters")
        if characters:
            summary = self._summarize_characters(characters)
            await self.letta_service.update_memory(agent_id, "characters", summary)
    
    def _summarize_worldbuilding(self, data: List[Dict]) -> str:
        """生成世界观摘要"""
        if not data:
            return "尚无世界观设定"
        
        max_items = 5
        truncate_len = WRITING_CONFIG.HISTORY_TRUNCATE_LENGTH // 2
        lines = ["世界观设定摘要:"]
        for item in data[:max_items]:  # 限制条目数量
            name = item.get("name", "未命名")
            desc = item.get("description", "")[:truncate_len]
            lines.append(f"- {name}: {desc}")
        
        if len(data) > max_items:
            lines.append(f"... 还有 {len(data) - max_items} 项设定")
        
        return "\n".join(lines)
    
    def _summarize_outline(self, data: List[Dict]) -> str:
        """生成大纲摘要"""
        if not data:
            return "尚无大纲"
        
        lines = ["故事大纲摘要:"]
        for i, volume in enumerate(data[:3], 1):
            title = volume.get("title", f"第{i}卷")
            chapters = volume.get("chapters", [])
            lines.append(f"- {title} ({len(chapters)}章)")
        
        if len(data) > 3:
            lines.append(f"... 还有 {len(data) - 3} 卷")
        
        return "\n".join(lines)
    
    def _summarize_characters(self, data: List[Dict]) -> str:
        """生成角色摘要"""
        if not data:
            return "尚无角色设定"
        
        lines = ["主要角色:"]
        for char in data[:5]:
            name = char.get("name", "未命名")
            role = char.get("role", "")
            lines.append(f"- {name}: {role}")
        
        if len(data) > 5:
            lines.append(f"... 还有 {len(data) - 5} 个角色")
        
        return "\n".join(lines)
    
    async def export_memory_to_project(self, agent_id: str) -> Dict[str, str]:
        """
        导出 Agent 记忆到项目元数据
        
        用于持久化 Agent 在对话中学习到的信息
        """
        if not self.letta_service.is_available:
            return {}
        
        memory = await self.letta_service.get_memory(agent_id)
        
        # 可以将记忆保存到项目的元数据中
        # 这里返回原始记忆，由调用方决定如何处理
        return memory


# 全局实例
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """获取全局记忆管理器"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


# 模块职责说明：管理Letta Agent的记忆结构，同步项目数据与Agent记忆。
