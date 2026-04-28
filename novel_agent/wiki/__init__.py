"""
Wiki 知识系统

基于 Karpathy LLM Wiki 模式，将小说创作知识从"临时检索"升级为"预编译wiki"。

核心组件：
- wiki_types: 数据模型（WikiPage, WikiGraph, Frontmatter）
- wiki_store: 页面存储服务（Markdown文件读写）
- wiki_index: index.md / overview.md / log.md 自动维护
- wiki_graph: 知识图谱（4信号相关性模型）
- wiki_ingest: 两步链式摄取管道
- wiki_lint: 质量检查系统
- wiki_migrate: 旧数据迁移
"""

from .wiki_types import (
    PageType,
    Frontmatter,
    WikiPage,
    WikiLink,
    WikiGraph,
    WikiGraphNode,
    WikiGraphEdge,
    IngestResult,
    LintIssue,
    LintReport,
    parse_frontmatter,
    now_iso,
)
from .wiki_store import WikiStore
from .wiki_index import WikiIndexManager
from .wiki_graph import WikiGraphBuilder
from .wiki_ingest import WikiIngestPipeline
from .wiki_lint import WikiLinter
from .wiki_migrate import WikiMigrator
from .wiki_retriever import WikiRetriever, BudgetAllocator, SearchResult, RetrievalResult
from .wiki_review import ReviewManager, ReviewItem
from .wiki_compat import WikiCompatLayer

__all__ = [
    # 类型
    "PageType",
    "Frontmatter",
    "WikiPage",
    "WikiLink",
    "WikiGraph",
    "WikiGraphNode",
    "WikiGraphEdge",
    "IngestResult",
    "LintIssue",
    "LintReport",
    "SearchResult",
    "RetrievalResult",
    "ReviewItem",
    # 服务
    "WikiStore",
    "WikiIndexManager",
    "WikiGraphBuilder",
    "WikiIngestPipeline",
    "WikiLinter",
    "WikiMigrator",
    "WikiRetriever",
    "BudgetAllocator",
    "ReviewManager",
    "WikiCompatLayer",
    # 工具
    "parse_frontmatter",
    "now_iso",
]