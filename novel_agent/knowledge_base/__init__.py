"""
知识库系统 (Knowledge Base System)

基于分层架构的知识库实现，支持：
- 向量检索（ChromaDB + 硅基流动 bge-m3）
- 全文搜索（SQLite FTS5）
- 章节标记与管理
- 摘要索引检索（无向量RAG）

使用示例:
    from novel_agent.knowledge_base import KnowledgeBase
    
    kb = KnowledgeBase(project_id="my_novel")
    kb.add_chapter("chapter_1", "第一章", "内容...")
    results = kb.search("查询内容", top_k=5)
    
无向量RAG使用示例:
    from novel_agent.knowledge_base import SummaryIndex, UnifiedSearch
    
    # 方式1: 直接使用摘要索引
    index = SummaryIndex(project_id="my_novel", llm_caller=my_llm)
    await index.add_entry("char_001", "character", "李逍遥", "主角信息...")
    results = await index.retrieve("谁是主角")
    
    # 方式2: 使用统一检索（自动路由）
    search = UnifiedSearch(project_id="my_novel", llm_caller=my_llm)
    results = await search.search("谁是主角", categories=["character"])
"""

from .config import KnowledgeBaseConfig, SummarySearchConfig
from .knowledge_base import KnowledgeBase
from .logic_layer.summary_index import SummaryIndex, SummaryEntry
from .application_layer.retrieval_router import (
    RetrievalRouter,
    RetrievalConfig,
    UnifiedSearch,
    SearchStrategy,
)

__all__ = [
    # 核心类
    "KnowledgeBase",
    "KnowledgeBaseConfig",
    # 摘要索引（无向量RAG）
    "SummaryIndex",
    "SummaryEntry",
    "SummarySearchConfig",
    # 检索路由
    "RetrievalRouter",
    "RetrievalConfig",
    "UnifiedSearch",
    "SearchStrategy",
]

__version__ = "1.1.0"