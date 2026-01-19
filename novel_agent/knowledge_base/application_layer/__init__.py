"""
应用层模块

提供用户与知识库交互的接口：
- 混合检索（HybridSearch）
- 知识管理API（KnowledgeAPI）
- 章节导航（Navigator）
"""

from .hybrid_search import HybridSearch, SearchResult
from .knowledge_api import KnowledgeAPI
from .navigator import ChapterNavigator

__all__ = [
    "HybridSearch",
    "SearchResult",
    "KnowledgeAPI",
    "ChapterNavigator",
]