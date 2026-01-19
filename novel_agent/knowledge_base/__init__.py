"""
知识库系统 (Knowledge Base System)

基于分层架构的知识库实现，支持：
- 向量检索（ChromaDB + 硅基流动 bge-m3）
- 全文搜索（SQLite FTS5）
- 章节标记与管理

使用示例:
    from novel_agent.knowledge_base import KnowledgeBase
    
    kb = KnowledgeBase(project_id="my_novel")
    kb.add_chapter("chapter_1", "第一章", "内容...")
    results = kb.search("查询内容", top_k=5)
"""

from .config import KnowledgeBaseConfig
from .knowledge_base import KnowledgeBase

__all__ = [
    "KnowledgeBase",
    "KnowledgeBaseConfig",
]

__version__ = "1.0.0"