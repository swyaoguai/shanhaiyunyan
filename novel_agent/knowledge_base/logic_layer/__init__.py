"""
逻辑层模块

负责知识内容的加工和组织：
- 文本分块（Chunker）
- 向量化服务（Embeddings）
- 章节标记管理（ChapterMarker）
- 剧情约束管理（PlotConstraints）
- 摘要索引（SummaryIndex）- 无向量RAG核心实现
"""

from .chunker import TextChunker
from .embeddings import EmbeddingService
from .chapter_marker import ChapterMarker
from .plot_constraints import (
    PlotConstraint,
    PlotConstraintExtractor,
    PlotConstraintStore,
    ConstraintType
)
from .summary_index import SummaryIndex, SummaryEntry

__all__ = [
    "TextChunker",
    "EmbeddingService",
    "ChapterMarker",
    "PlotConstraint",
    "PlotConstraintExtractor",
    "PlotConstraintStore",
    "ConstraintType",
    "SummaryIndex",
    "SummaryEntry",
]