"""
Wiki 兼容层

让旧的资料库（LibraryService）和知识中心（KnowledgeBase）
可以与新的 Wiki 系统共存，并提供平滑迁移路径。

策略：
1. WikiStore 作为新的 canonical source of truth
2. LibraryService 作为只读兼容层（从 wiki 页面投影）
3. KnowledgeBase 保留向量/全文检索能力，wiki 页面自动索引
4. 提供一键迁移命令
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_types import PageType, WikiPage, Frontmatter, now_iso
from .wiki_store import WikiStore
from .wiki_index import WikiIndexManager
from .wiki_graph import WikiGraphBuilder
from .wiki_ingest import WikiIngestPipeline
from .wiki_lint import WikiLinter
from .wiki_migrate import WikiMigrator
from .wiki_retriever import WikiRetriever
from .wiki_review import ReviewManager

logger = logging.getLogger(__name__)


class WikiCompatLayer:
    """
    Wiki 兼容层
    
    提供统一接口，让旧代码可以无缝切换到新 wiki 系统。
    
    使用方式：
        compat = WikiCompatLayer(project_dir)
        compat.initialize()  # 初始化 wiki 目录
        
        # 迁移旧数据
        compat.migrate_from_library()
        
        # 使用新系统
        pages = compat.store.list_pages()
        result = await compat.retriever.retrieve("主角的身世")
    """

    def __init__(self, project_dir: Path):
        self._project_dir = project_dir
        self._wiki_dir = project_dir / "wiki"
        
        # 核心组件
        self._store = WikiStore(self._wiki_dir)
        self._index = WikiIndexManager(self._wiki_dir)
        self._graph_builder = WikiGraphBuilder()
        self._ingest: Optional[WikiIngestPipeline] = None
        self._linter: Optional[WikiLinter] = None
        self._retriever: Optional[WikiRetriever] = None
        self._review: Optional[ReviewManager] = None

    @property
    def store(self) -> WikiStore:
        return self._store

    @property
    def index(self) -> WikiIndexManager:
        return self._index

    @property
    def graph_builder(self) -> WikiGraphBuilder:
        return self._graph_builder

    @property
    def ingest(self) -> WikiIngestPipeline:
        if not self._ingest:
            self._ingest = WikiIngestPipeline(
                self._store, self._index, self._graph_builder
            )
        return self._ingest

    @property
    def linter(self) -> WikiLinter:
        if not self._linter:
            self._linter = WikiLinter(self._store, self._graph_builder)
        return self._linter

    @property
    def retriever(self) -> WikiRetriever:
        if not self._retriever:
            self._retriever = WikiRetriever(
                self._store, self._graph_builder
            )
        return self._retriever

    @property
    def review(self) -> ReviewManager:
        if not self._review:
            self._review = ReviewManager(self._project_dir)
        return self._review

    # ------------------------------------------------------------------
    #  初始化
    # ------------------------------------------------------------------

    def initialize(self, theme: str = "待补充", style: str = "网文爽文风格") -> None:
        """
        初始化 wiki 系统
        
        创建目录结构和核心文件。
        """
        self._index.initialize_wiki(theme=theme, style=style)
        self._store.ensure_dirs()
        logger.info(f"[WikiCompat] Wiki 系统初始化完成: {self._wiki_dir}")

    def is_initialized(self) -> bool:
        """检查 wiki 是否已初始化"""
        return (
            self._wiki_dir.exists()
            and (self._wiki_dir / "purpose.md").exists()
            and (self._wiki_dir / "schema.md").exists()
        )

    # ------------------------------------------------------------------
    #  迁移
    # ------------------------------------------------------------------

    def migrate_from_library(self) -> Dict[str, int]:
        """
        从旧的资料库迁移数据到 wiki
        
        Returns:
            迁移统计
        """
        migrator = WikiMigrator(self._project_dir, self._wiki_dir)
        stats = migrator.migrate_all()
        
        # 重建图谱
        pages = self._store.list_pages()
        self._graph_builder.build_from_pages(pages)
        
        logger.info(f"[WikiCompat] 迁移完成: {stats}")
        return stats

    # ------------------------------------------------------------------
    #  兼容旧接口
    # ------------------------------------------------------------------

    def get_characters(self) -> List[Dict[str, Any]]:
        """兼容旧接口：获取角色列表"""
        pages = self._store.list_pages(page_type=PageType.CHARACTER)
        return [
            {
                "name": p.title,
                "description": p.body[:200],
                "tags": p.tags,
                "sources": p.sources,
            }
            for p in pages
        ]

    def get_world_settings(self) -> List[Dict[str, Any]]:
        """兼容旧接口：获取世界观设定"""
        pages = self._store.list_pages(page_type=PageType.WORLD)
        return [
            {
                "name": p.title,
                "content": p.body,
                "tags": p.tags,
            }
            for p in pages
        ]

    def get_chapter_summaries(self) -> List[Dict[str, Any]]:
        """兼容旧接口：获取章节摘要"""
        pages = self._store.list_pages(page_type=PageType.CHAPTER)
        return [
            {
                "title": p.title,
                "summary": p.body[:500],
                "chapter_number": p.frontmatter.chapter_number,
            }
            for p in pages
        ]

    def get_constraints(self) -> List[Dict[str, Any]]:
        """兼容旧接口：获取剧情约束"""
        pages = self._store.list_pages(page_type=PageType.CONSTRAINT)
        return [
            {
                "title": p.title,
                "description": p.body,
                "constraint_type": p.frontmatter.constraint_type,
                "severity": p.frontmatter.severity,
                "entities": p.frontmatter.entities,
            }
            for p in pages
        ]

    def get_dead_characters(self) -> List[str]:
        """兼容旧接口：获取已死亡角色"""
        constraints = self._store.list_pages(page_type=PageType.CONSTRAINT)
        dead = []
        for c in constraints:
            if c.frontmatter.constraint_type == "character_death":
                dead.extend(c.frontmatter.entities)
        return list(set(dead))

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """兼容旧接口：搜索"""
        pages = self._store.search_by_text(query, top_k=top_k)
        return [
            {
                "title": p.title,
                "content": p.body[:500],
                "type": p.page_type.value,
            }
            for p in pages
        ]

    # ------------------------------------------------------------------
    #  统计
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """获取 wiki 统计信息"""
        store_stats = self._store.get_statistics()
        graph_stats = self._graph_builder.get_statistics()
        review_stats = self.review.get_statistics()
        
        return {
            "store": store_stats,
            "graph": graph_stats,
            "review": review_stats,
            "initialized": self.is_initialized(),
        }