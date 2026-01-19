"""
章节导航模块

提供章节浏览和导航功能。
支持：
- 章节列表浏览
- 章节跳转
- 上下文导航
"""

import logging
from typing import Optional
from dataclasses import dataclass

from ..data_layer.metadata_store import MetadataStore, ChapterInfo

logger = logging.getLogger(__name__)


@dataclass
class NavigationContext:
    """导航上下文"""
    current_chapter: Optional[ChapterInfo]
    previous_chapter: Optional[ChapterInfo]
    next_chapter: Optional[ChapterInfo]
    total_chapters: int
    current_position: int  # 当前章节在列表中的位置（从1开始）


class ChapterNavigator:
    """
    章节导航器
    
    提供章节浏览和导航功能。
    """
    
    def __init__(self, metadata_store: MetadataStore):
        """
        初始化导航器
        
        Args:
            metadata_store: 元数据存储
        """
        self.metadata_store = metadata_store
        self._cached_chapters: Optional[list[ChapterInfo]] = None
    
    def get_navigation_context(
        self,
        chapter_id: str
    ) -> Optional[NavigationContext]:
        """
        获取章节的导航上下文
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            导航上下文
        """
        chapters = self._get_ordered_chapters()
        
        if not chapters:
            return None
        
        # 查找当前章节
        current_idx = None
        for i, chapter in enumerate(chapters):
            if chapter.chapter_id == chapter_id:
                current_idx = i
                break
        
        if current_idx is None:
            return None
        
        return NavigationContext(
            current_chapter=chapters[current_idx],
            previous_chapter=chapters[current_idx - 1] if current_idx > 0 else None,
            next_chapter=chapters[current_idx + 1] if current_idx < len(chapters) - 1 else None,
            total_chapters=len(chapters),
            current_position=current_idx + 1
        )
    
    def go_to_chapter(
        self,
        chapter_number: int
    ) -> Optional[ChapterInfo]:
        """
        跳转到指定章节号
        
        Args:
            chapter_number: 章节序号
        
        Returns:
            章节信息
        """
        return self.metadata_store.get_chapter_by_number(chapter_number)
    
    def get_first_chapter(self) -> Optional[ChapterInfo]:
        """获取第一章"""
        chapters = self._get_ordered_chapters()
        return chapters[0] if chapters else None
    
    def get_last_chapter(self) -> Optional[ChapterInfo]:
        """获取最后一章"""
        chapters = self._get_ordered_chapters()
        return chapters[-1] if chapters else None
    
    def get_chapter_by_id(self, chapter_id: str) -> Optional[ChapterInfo]:
        """根据ID获取章节"""
        return self.metadata_store.get_chapter(chapter_id)
    
    def get_previous_chapter(
        self,
        chapter_id: str
    ) -> Optional[ChapterInfo]:
        """
        获取上一章
        
        Args:
            chapter_id: 当前章节ID
        
        Returns:
            上一章信息
        """
        context = self.get_navigation_context(chapter_id)
        return context.previous_chapter if context else None
    
    def get_next_chapter(
        self,
        chapter_id: str
    ) -> Optional[ChapterInfo]:
        """
        获取下一章
        
        Args:
            chapter_id: 当前章节ID
        
        Returns:
            下一章信息
        """
        context = self.get_navigation_context(chapter_id)
        return context.next_chapter if context else None
    
    def get_chapters_in_range(
        self,
        start_number: int,
        end_number: int
    ) -> list[ChapterInfo]:
        """
        获取范围内的章节
        
        Args:
            start_number: 起始章节号（包含）
            end_number: 结束章节号（包含）
        
        Returns:
            章节列表
        """
        chapters = self._get_ordered_chapters()
        return [
            c for c in chapters
            if c.chapter_number and start_number <= c.chapter_number <= end_number
        ]
    
    def get_recent_chapters(self, count: int = 5) -> list[ChapterInfo]:
        """
        获取最近的章节
        
        Args:
            count: 返回数量
        
        Returns:
            章节列表（按更新时间倒序）
        """
        return self.metadata_store.list_chapters(
            order_by="updated_at",
            ascending=False,
            limit=count
        )
    
    def get_table_of_contents(self) -> list[dict]:
        """
        获取目录
        
        Returns:
            目录列表
        """
        chapters = self._get_ordered_chapters()
        
        return [
            {
                "chapter_id": c.chapter_id,
                "chapter_number": c.chapter_number,
                "title": c.title,
                "word_count": c.word_count,
            }
            for c in chapters
        ]
    
    def search_chapters_by_title(
        self,
        keyword: str
    ) -> list[ChapterInfo]:
        """
        按标题搜索章节
        
        Args:
            keyword: 搜索关键词
        
        Returns:
            匹配的章节列表
        """
        chapters = self._get_ordered_chapters()
        keyword_lower = keyword.lower()
        
        return [
            c for c in chapters
            if keyword_lower in c.title.lower()
        ]
    
    def get_progress_info(self) -> dict:
        """
        获取进度信息
        
        Returns:
            进度信息
        """
        stats = self.metadata_store.get_statistics()
        chapters = self._get_ordered_chapters()
        
        return {
            "total_chapters": stats["chapter_count"],
            "total_words": stats["total_words"],
            "average_words_per_chapter": (
                stats["total_words"] // stats["chapter_count"]
                if stats["chapter_count"] > 0 else 0
            ),
            "latest_chapter": chapters[-1].to_dict() if chapters else None,
        }
    
    def invalidate_cache(self):
        """使缓存失效"""
        self._cached_chapters = None
    
    def _get_ordered_chapters(self) -> list[ChapterInfo]:
        """获取排序后的章节列表（带缓存）"""
        if self._cached_chapters is None:
            self._cached_chapters = self.metadata_store.list_chapters(
                order_by="chapter_number",
                ascending=True
            )
        return self._cached_chapters