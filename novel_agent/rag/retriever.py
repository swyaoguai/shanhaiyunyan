"""
小说检索器
用于在创作过程中检索相关的角色、情节、设定信息
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from .vector_store import SimpleVectorStore, SearchResult
from ..constants import WRITING_CONFIG

logger = logging.getLogger(__name__)


class NovelRetriever:
    """
    小说内容检索器
    管理多个向量存储：角色、情节、世界观
    """
    
    def __init__(self, project_dir: Optional[Path] = None):
        """
        初始化检索器
        
        Args:
            project_dir: 项目目录
        """
        self.project_dir = project_dir or Path(__file__).parent.parent / "data"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化各类向量存储
        self.character_store = SimpleVectorStore(
            self.project_dir / "vectors_characters.json"
        )
        self.plot_store = SimpleVectorStore(
            self.project_dir / "vectors_plot.json"
        )
        self.world_store = SimpleVectorStore(
            self.project_dir / "vectors_world.json"
        )
        
        logger.info("NovelRetriever initialized")
    
    # ========== 角色相关 ==========
    
    async def add_character(
        self,
        character_id: str,
        profile: str,
        name: str = "",
        traits: Optional[List[str]] = None
    ) -> None:
        """
        添加角色档案
        
        Args:
            character_id: 角色ID
            profile: 角色详细描述
            name: 角色名称
            traits: 性格特征标签
        """
        await self.character_store.add(
            doc_id=character_id,
            text=profile,
            metadata={
                "type": "character",
                "name": name,
                "traits": traits or []
            }
        )
    
    async def search_characters(
        self, 
        query: str, 
        top_k: int = 3
    ) -> List[SearchResult]:
        """
        搜索相关角色
        
        Args:
            query: 查询（可以是场景描述、对话等）
            top_k: 返回数量
            
        Returns:
            相关角色列表
        """
        return await self.character_store.search(query, top_k)
    
    # ========== 情节相关 ==========
    
    async def add_plot_point(
        self,
        plot_id: str,
        content: str,
        chapter: int = 0,
        importance: str = "normal"
    ) -> None:
        """
        添加情节点
        
        Args:
            plot_id: 情节点ID
            content: 情节内容描述
            chapter: 所属章节
            importance: 重要性(high/normal/low)
        """
        await self.plot_store.add(
            doc_id=plot_id,
            text=content,
            metadata={
                "type": "plot",
                "chapter": chapter,
                "importance": importance
            }
        )
    
    async def search_plot(
        self, 
        query: str, 
        top_k: int = 5,
        max_chapter: Optional[int] = None
    ) -> List[SearchResult]:
        """
        搜索相关情节
        
        Args:
            query: 查询
            top_k: 返回数量
            max_chapter: 最大章节限制（避免剧透）
            
        Returns:
            相关情节列表
        """
        results = await self.plot_store.search(query, top_k * 2)
        
        # 过滤章节
        if max_chapter is not None:
            results = [
                r for r in results 
                if r.metadata.get("chapter", 0) <= max_chapter
            ]
        
        return results[:top_k]
    
    # ========== 世界观相关 ==========
    
    async def add_world_setting(
        self,
        setting_id: str,
        content: str,
        category: str = "general"
    ) -> None:
        """
        添加世界观设定
        
        Args:
            setting_id: 设定ID
            content: 设定内容
            category: 分类(power/geography/history/culture)
        """
        await self.world_store.add(
            doc_id=setting_id,
            text=content,
            metadata={
                "type": "world",
                "category": category
            }
        )
    
    async def search_world(
        self, 
        query: str, 
        top_k: int = 3,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """
        搜索世界观设定
        
        Args:
            query: 查询
            top_k: 返回数量
            category: 限定分类
            
        Returns:
            相关设定列表
        """
        filter_meta = {"category": category} if category else None
        return await self.world_store.search(query, top_k, filter_meta)
    
    # ========== 综合检索 ==========
    
    async def retrieve_context(
        self,
        query: str,
        current_chapter: int = 0,
        include_characters: bool = True,
        include_plot: bool = True,
        include_world: bool = True
    ) -> Dict[str, List[SearchResult]]:
        """
        综合检索所有相关上下文
        
        Args:
            query: 查询（通常是当前要写的章节大纲）
            current_chapter: 当前章节号
            include_characters: 是否检索角色
            include_plot: 是否检索情节
            include_world: 是否检索世界观
            
        Returns:
            分类的检索结果
        """
        results = {}
        
        if include_characters:
            results["characters"] = await self.search_characters(query, 3)
        
        if include_plot:
            results["plot"] = await self.search_plot(query, 5, current_chapter)
        
        if include_world:
            results["world"] = await self.search_world(query, 3)
        
        return results
    
    def format_context_for_prompt(
        self, 
        results: Dict[str, List[SearchResult]]
    ) -> str:
        """
        将检索结果格式化为提示词
        
        Args:
            results: retrieve_context的返回值
            
        Returns:
            格式化的上下文字符串
        """
        parts = []
        
        truncate_len = WRITING_CONFIG.HISTORY_TRUNCATE_LENGTH
        if results.get("characters"):
            parts.append("【相关角色】")
            for r in results["characters"]:
                name = r.metadata.get("name", r.doc_id)
                parts.append(f"- {name}: {r.text[:truncate_len]}...")
        
        if results.get("plot"):
            parts.append("\n【前文情节】")
            for r in results["plot"]:
                ch = r.metadata.get("chapter", "?")
                parts.append(f"- [第{ch}章] {r.text[:truncate_len]}...")
        
        if results.get("world"):
            parts.append("\n【世界设定】")
            for r in results["world"]:
                parts.append(f"- {r.text[:truncate_len]}...")
        
        return "\n".join(parts) if parts else ""
    
    # ========== 批量导入 ==========
    
    async def import_from_world_manager(self, world_data: Dict[str, Any]) -> int:
        """
        从世界观管理器导入数据
        
        Args:
            world_data: 世界观数据
            
        Returns:
            导入的条目数
        """
        count = 0
        
        # 导入力量体系
        if "power_system" in world_data:
            ps = world_data["power_system"]
            await self.add_world_setting(
                "power_system",
                f"力量体系: {ps.get('name', '')}. 等级: {', '.join(ps.get('levels', []))}. "
                f"修炼方式: {ps.get('cultivation_method', '')}",
                category="power"
            )
            count += 1
        
        # 导入地理
        if "geography" in world_data:
            geo = world_data["geography"]
            for i, loc in enumerate(geo.get("special_locations", [])):
                await self.add_world_setting(
                    f"location_{i}",
                    f"特殊地点: {loc}",
                    category="geography"
                )
                count += 1
        
        # 导入势力
        if "factions" in world_data:
            for i, faction in enumerate(world_data["factions"]):
                await self.add_world_setting(
                    f"faction_{i}",
                    f"势力: {faction.get('name', '')}. {faction.get('description', '')}",
                    category="faction"
                )
                count += 1
        
        logger.info(f"Imported {count} world settings")
        return count
    
    async def import_from_character_manager(self, characters: List[Dict[str, Any]]) -> int:
        """
        从角色管理器导入数据
        
        Args:
            characters: 角色列表
            
        Returns:
            导入的角色数
        """
        for char in characters:
            profile_parts = [
                f"姓名: {char.get('name', '')}",
                f"身份: {char.get('identity', '')}",
                f"性格: {', '.join(char.get('personality', []))}",
                f"背景: {char.get('background', '')}",
            ]
            await self.add_character(
                character_id=char.get("id", char.get("name", "")),
                profile=". ".join(profile_parts),
                name=char.get("name", ""),
                traits=char.get("personality", [])
            )
        
        logger.info(f"Imported {len(characters)} characters")
        return len(characters)
    
    def clear_all(self) -> None:
        """清空所有向量存储"""
        self.character_store.clear()
        self.plot_store.clear()
        self.world_store.clear()
        logger.info("Cleared all vector stores")


# 模块职责说明：管理小说相关的多个向量存储，提供角色、情节、世界观的语义检索功能。
