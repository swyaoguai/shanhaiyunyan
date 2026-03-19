"""
应用层模块

提供用户与知识库交互的接口：
- 混合检索（HybridSearch）
- 知识管理API（KnowledgeAPI）
- 章节导航（Navigator）
- 检索路由器（RetrievalRouter）- 智能选择检索策略
- 统一检索（UnifiedSearch）- 封装检索路由
"""

from .hybrid_search import HybridSearch, SearchResult
from .knowledge_api import KnowledgeAPI
from .navigator import ChapterNavigator
from .retrieval_router import (
    RetrievalRouter,
    RetrievalConfig,
    RetrievalResult,
    SearchStrategy,
    DataCategory,
    UnifiedSearch,
)

__all__ = [
    "HybridSearch",
    "SearchResult",
    "KnowledgeAPI",
    "ChapterNavigator",
    "RetrievalRouter",
    "RetrievalConfig",
    "RetrievalResult",
    "SearchStrategy",
    "DataCategory",
    "UnifiedSearch",
]