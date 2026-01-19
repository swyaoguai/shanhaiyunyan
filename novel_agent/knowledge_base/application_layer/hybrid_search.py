"""
混合检索模块

融合向量检索和全文检索，提供统一的检索接口。
支持：
- 向量语义检索
- 全文关键词检索
- 混合检索（加权融合）
- 结果去重排序
"""

import logging
from typing import Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

from ..config import RetrievalConfig
from ..data_layer.vector_store import VectorStore
from ..data_layer.fulltext_store import FullTextStore
from ..logic_layer.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class SearchType(str, Enum):
    """检索类型"""
    VECTOR = "vector"
    FULLTEXT = "fulltext"
    HYBRID = "hybrid"


@dataclass
class SearchResult:
    """检索结果"""
    id: str
    document: str
    score: float
    chapter_id: Optional[str] = None
    chunk_index: Optional[int] = None
    metadata: Optional[dict] = None
    source: str = "unknown"  # "vector", "fulltext", "hybrid"
    highlight: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document": self.document,
            "score": self.score,
            "chapter_id": self.chapter_id,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
            "source": self.source,
            "highlight": self.highlight,
        }


@dataclass
class SearchResponse:
    """检索响应"""
    results: list[SearchResult]
    total: int
    search_type: str
    query: str
    took_ms: float = 0
    
    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "search_type": self.search_type,
            "query": self.query,
            "took_ms": self.took_ms,
        }


class HybridSearch:
    """
    混合检索类
    
    融合向量检索和全文检索结果。
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        fulltext_store: FullTextStore,
        embedding_service: EmbeddingService,
        config: Optional[RetrievalConfig] = None
    ):
        """
        初始化混合检索
        
        Args:
            vector_store: 向量存储
            fulltext_store: 全文存储
            embedding_service: 向量化服务
            config: 检索配置
        """
        self.vector_store = vector_store
        self.fulltext_store = fulltext_store
        self.embedding_service = embedding_service
        self.config = config or RetrievalConfig()
    
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        search_type: SearchType = SearchType.HYBRID,
        chapter_filter: Optional[list[str]] = None,
        min_score: Optional[float] = None
    ) -> SearchResponse:
        """
        执行检索
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            search_type: 检索类型
            chapter_filter: 章节过滤
            min_score: 最小分数阈值
        
        Returns:
            检索响应
        """
        import time
        start_time = time.time()
        
        top_k = min(top_k or self.config.default_top_k, self.config.max_top_k)
        min_score = min_score or self.config.min_score_threshold
        
        if search_type == SearchType.VECTOR:
            results = self._vector_search(query, top_k, chapter_filter)
        elif search_type == SearchType.FULLTEXT:
            results = self._fulltext_search(query, top_k, chapter_filter)
        else:
            results = self._hybrid_search(query, top_k, chapter_filter)
        
        # 过滤低分结果
        results = [r for r in results if r.score >= min_score]
        
        took_ms = (time.time() - start_time) * 1000
        
        return SearchResponse(
            results=results,
            total=len(results),
            search_type=search_type.value,
            query=query,
            took_ms=round(took_ms, 2)
        )
    
    def _vector_search(
        self,
        query: str,
        top_k: int,
        chapter_filter: Optional[list[str]] = None
    ) -> list[SearchResult]:
        """
        向量检索
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            chapter_filter: 章节过滤
        
        Returns:
            检索结果列表
        """
        # 将查询转换为向量
        query_embedding = self.embedding_service.embed(query)
        
        # 构建过滤条件
        where = None
        if chapter_filter:
            where = {"chapter_id": {"$in": chapter_filter}}
        
        # 执行向量检索
        raw_results = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where
        )
        
        # 转换结果
        results = []
        for i, doc_id in enumerate(raw_results["ids"]):
            # 将距离转换为相似度分数（余弦距离转相似度）
            distance = raw_results["distances"][i] if raw_results["distances"] else 0
            score = 1 - distance  # 余弦距离转相似度
            
            metadata = raw_results["metadatas"][i] if raw_results["metadatas"] else {}
            
            result = SearchResult(
                id=doc_id,
                document=raw_results["documents"][i] if raw_results["documents"] else "",
                score=score,
                chapter_id=metadata.get("chapter_id"),
                chunk_index=metadata.get("chunk_index"),
                metadata=metadata,
                source="vector"
            )
            results.append(result)
        
        logger.debug(f"向量检索完成: query={query[:50]}..., 返回{len(results)}条结果")
        return results
    
    def _fulltext_search(
        self,
        query: str,
        top_k: int,
        chapter_filter: Optional[list[str]] = None
    ) -> list[SearchResult]:
        """
        全文检索
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            chapter_filter: 章节过滤
        
        Returns:
            检索结果列表
        """
        # 执行全文检索
        raw_results = self.fulltext_store.search(
            query=query,
            top_k=top_k,
            chapter_filter=chapter_filter,
            highlight=True
        )
        
        # 转换结果
        results = []
        max_score = max((r.score for r in raw_results), default=1) or 1
        
        for raw in raw_results:
            # 归一化分数到0-1范围
            score = raw.score / max_score
            
            result = SearchResult(
                id=raw.id,
                document=raw.document,
                score=score,
                chapter_id=raw.metadata.get("chapter_id") if raw.metadata else None,
                chunk_index=raw.metadata.get("chunk_index") if raw.metadata else None,
                metadata=raw.metadata,
                source="fulltext",
                highlight=raw.highlight
            )
            results.append(result)
        
        logger.debug(f"全文检索完成: query={query[:50]}..., 返回{len(results)}条结果")
        return results
    
    def _hybrid_search(
        self,
        query: str,
        top_k: int,
        chapter_filter: Optional[list[str]] = None
    ) -> list[SearchResult]:
        """
        混合检索
        
        融合向量检索和全文检索结果
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            chapter_filter: 章节过滤
        
        Returns:
            检索结果列表
        """
        # 分别执行两种检索
        vector_results = self._vector_search(query, top_k * 2, chapter_filter)
        fulltext_results = self._fulltext_search(query, top_k * 2, chapter_filter)
        
        # 融合结果
        merged = self._merge_results(
            vector_results,
            fulltext_results,
            self.config.vector_weight,
            self.config.fulltext_weight
        )
        
        # 返回top_k结果
        return merged[:top_k]
    
    def _merge_results(
        self,
        vector_results: list[SearchResult],
        fulltext_results: list[SearchResult],
        vector_weight: float,
        fulltext_weight: float
    ) -> list[SearchResult]:
        """
        融合两种检索结果
        
        使用加权融合策略
        
        Args:
            vector_results: 向量检索结果
            fulltext_results: 全文检索结果
            vector_weight: 向量权重
            fulltext_weight: 全文权重
        
        Returns:
            融合后的结果列表
        """
        # 按ID合并结果
        result_map: dict[str, dict] = {}
        
        # 处理向量结果
        for result in vector_results:
            result_map[result.id] = {
                "result": result,
                "vector_score": result.score,
                "fulltext_score": 0,
            }
        
        # 处理全文结果
        for result in fulltext_results:
            if result.id in result_map:
                result_map[result.id]["fulltext_score"] = result.score
                # 保留高亮信息
                if result.highlight:
                    result_map[result.id]["result"].highlight = result.highlight
            else:
                result_map[result.id] = {
                    "result": result,
                    "vector_score": 0,
                    "fulltext_score": result.score,
                }
        
        # 计算加权分数并排序
        merged_results = []
        for doc_id, data in result_map.items():
            weighted_score = (
                data["vector_score"] * vector_weight +
                data["fulltext_score"] * fulltext_weight
            )
            
            result = data["result"]
            result.score = weighted_score
            result.source = "hybrid"
            
            # 在metadata中保存原始分数
            if result.metadata is None:
                result.metadata = {}
            result.metadata["_vector_score"] = data["vector_score"]
            result.metadata["_fulltext_score"] = data["fulltext_score"]
            
            merged_results.append(result)
        
        # 按加权分数降序排序
        merged_results.sort(key=lambda x: x.score, reverse=True)
        
        logger.debug(f"混合检索融合完成: 向量{len(vector_results)}条 + "
                    f"全文{len(fulltext_results)}条 = {len(merged_results)}条")
        
        return merged_results
    
    def explain_search(
        self,
        query: str,
        doc_id: str
    ) -> dict:
        """
        解释某个文档的检索得分
        
        Args:
            query: 检索查询
            doc_id: 文档ID
        
        Returns:
            得分解释
        """
        # 执行混合检索
        response = self.search(query, top_k=100, search_type=SearchType.HYBRID)
        
        # 查找目标文档
        for result in response.results:
            if result.id == doc_id:
                return {
                    "doc_id": doc_id,
                    "final_score": result.score,
                    "vector_score": result.metadata.get("_vector_score", 0),
                    "fulltext_score": result.metadata.get("_fulltext_score", 0),
                    "vector_weight": self.config.vector_weight,
                    "fulltext_weight": self.config.fulltext_weight,
                    "rank": response.results.index(result) + 1,
                }
        
        return {
            "doc_id": doc_id,
            "error": "文档未在检索结果中找到",
        }