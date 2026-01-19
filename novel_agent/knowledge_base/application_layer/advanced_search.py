# -*- coding: utf-8 -*-
"""
高级搜索模块（参考 SeekDB 设计）

增强功能：
1. 动态权重调整 - 根据查询特征自动调整向量/全文权重
2. Reranking - 使用交叉编码器重排序
3. 查询分析 - 识别查询意图
4. 上下文压缩 - 智能截取相关片段
"""

import re
import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .hybrid_search import HybridSearch, SearchResult, SearchResponse, SearchType
from ..config import RetrievalConfig

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """查询意图类型"""
    EXACT_MATCH = "exact_match"      # 精确匹配（角色名、地名等）
    SEMANTIC = "semantic"             # 语义理解（情节发展、人物关系）
    TEMPORAL = "temporal"             # 时间相关（之前、之后）
    CAUSAL = "causal"                 # 因果关系（为什么、导致）
    CONSTRAINT = "constraint"         # 约束检索（不能、必须）


@dataclass
class QueryAnalysis:
    """查询分析结果"""
    original_query: str
    cleaned_query: str
    intent: QueryIntent
    keywords: List[str]
    entities: List[str]
    is_question: bool
    suggested_vector_weight: float
    suggested_fulltext_weight: float
    expansion_terms: List[str] = field(default_factory=list)


@dataclass
class RerankResult:
    """重排序结果"""
    results: List[SearchResult]
    rerank_method: str
    original_order: List[str]  # 原始排序的ID列表


class QueryAnalyzer:
    """
    查询分析器
    
    分析查询意图，推荐最优搜索策略
    """
    
    # 精确匹配关键词
    EXACT_PATTERNS = [
        r'["「『](.+?)["」』]',  # 引号包裹
        r'第\d+章',
        r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',  # 英文名
    ]
    
    # 语义查询关键词
    SEMANTIC_KEYWORDS = [
        '怎样', '如何', '什么是', '为什么', '关系',
        '发展', '变化', '影响', '结果', '意义',
    ]
    
    # 时间相关关键词
    TEMPORAL_KEYWORDS = [
        '之前', '之后', '以前', '以后', '接着',
        '然后', '最后', '开始', '结束', '当时',
    ]
    
    # 因果关键词
    CAUSAL_KEYWORDS = [
        '为什么', '因为', '所以', '导致', '造成',
        '原因', '结果', '影响', '由于', '因此',
    ]
    
    # 约束关键词
    CONSTRAINT_KEYWORDS = [
        '不能', '必须', '禁止', '绝对', '一定',
        '永远', '从不', '规则', '设定', '死亡',
    ]
    
    # 实体识别模式
    ENTITY_PATTERNS = [
        r'([一-龥]{2,4}(?:子|儿|哥|姐|叔|婶|爷|奶|公)?)',  # 中文人名
        r'([一-龥]{2,6}(?:城|宗|门|派|山|谷|海|林|殿|阁))',  # 地名/门派
        r'([一-龥]{2,4}(?:剑|刀|枪|斧|锤|弓|杖|珠|丹|诀))',  # 物品
    ]
    
    def __init__(self):
        """初始化分析器"""
        self._exact_patterns = [re.compile(p, re.UNICODE) for p in self.EXACT_PATTERNS]
        self._entity_patterns = [re.compile(p, re.UNICODE) for p in self.ENTITY_PATTERNS]
    
    def analyze(self, query: str) -> QueryAnalysis:
        """
        分析查询
        
        Args:
            query: 原始查询
        
        Returns:
            查询分析结果
        """
        cleaned = self._clean_query(query)
        intent = self._detect_intent(cleaned)
        keywords = self._extract_keywords(cleaned)
        entities = self._extract_entities(cleaned)
        is_question = self._is_question(cleaned)
        
        # 根据意图推荐权重
        vector_weight, fulltext_weight = self._recommend_weights(
            intent, len(entities), is_question
        )
        
        # 查询扩展
        expansion_terms = self._expand_query(cleaned, intent)
        
        return QueryAnalysis(
            original_query=query,
            cleaned_query=cleaned,
            intent=intent,
            keywords=keywords,
            entities=entities,
            is_question=is_question,
            suggested_vector_weight=vector_weight,
            suggested_fulltext_weight=fulltext_weight,
            expansion_terms=expansion_terms
        )
    
    def _clean_query(self, query: str) -> str:
        """清理查询"""
        # 移除多余空白
        cleaned = re.sub(r'\s+', ' ', query.strip())
        return cleaned
    
    def _detect_intent(self, query: str) -> QueryIntent:
        """检测查询意图"""
        # 检查精确匹配
        for pattern in self._exact_patterns:
            if pattern.search(query):
                return QueryIntent.EXACT_MATCH
        
        # 检查约束（优先级较高）
        if any(kw in query for kw in self.CONSTRAINT_KEYWORDS):
            return QueryIntent.CONSTRAINT
        
        # 检查因果
        if any(kw in query for kw in self.CAUSAL_KEYWORDS):
            return QueryIntent.CAUSAL
        
        # 检查时间
        if any(kw in query for kw in self.TEMPORAL_KEYWORDS):
            return QueryIntent.TEMPORAL
        
        # 检查语义
        if any(kw in query for kw in self.SEMANTIC_KEYWORDS):
            return QueryIntent.SEMANTIC
        
        # 默认语义
        return QueryIntent.SEMANTIC
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 简单分词
        words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', query)
        # 过滤停用词
        stop_words = {'的', '了', '是', '在', '有', '和', '与', '或'}
        return [w for w in words if w not in stop_words and len(w) >= 2]
    
    def _extract_entities(self, query: str) -> List[str]:
        """提取实体"""
        entities = []
        for pattern in self._entity_patterns:
            matches = pattern.findall(query)
            entities.extend(matches)
        return list(set(entities))
    
    def _is_question(self, query: str) -> bool:
        """判断是否是问句"""
        question_markers = ['?', '？', '吗', '呢', '什么', '怎么', '为什么', '哪']
        return any(m in query for m in question_markers)
    
    def _recommend_weights(
        self,
        intent: QueryIntent,
        entity_count: int,
        is_question: bool
    ) -> Tuple[float, float]:
        """
        推荐搜索权重
        
        根据查询特征动态调整向量和全文权重
        
        Returns:
            (vector_weight, fulltext_weight)
        """
        # 基础权重
        vector_weight = 0.6
        fulltext_weight = 0.4
        
        # 根据意图调整
        if intent == QueryIntent.EXACT_MATCH:
            # 精确匹配：全文权重更高
            vector_weight = 0.3
            fulltext_weight = 0.7
        elif intent == QueryIntent.SEMANTIC:
            # 语义理解：向量权重更高
            vector_weight = 0.8
            fulltext_weight = 0.2
        elif intent == QueryIntent.CONSTRAINT:
            # 约束检索：平衡，略偏全文
            vector_weight = 0.4
            fulltext_weight = 0.6
        elif intent == QueryIntent.TEMPORAL:
            # 时间相关：平衡
            vector_weight = 0.5
            fulltext_weight = 0.5
        elif intent == QueryIntent.CAUSAL:
            # 因果关系：向量权重更高
            vector_weight = 0.7
            fulltext_weight = 0.3
        
        # 根据实体数量调整
        if entity_count >= 2:
            # 多实体查询，增加全文权重
            fulltext_weight += 0.1
            vector_weight -= 0.1
        
        # 问句倾向于语义理解
        if is_question:
            vector_weight += 0.05
            fulltext_weight -= 0.05
        
        # 归一化
        total = vector_weight + fulltext_weight
        return round(vector_weight / total, 2), round(fulltext_weight / total, 2)
    
    def _expand_query(self, query: str, intent: QueryIntent) -> List[str]:
        """查询扩展"""
        expansions = []
        
        if intent == QueryIntent.CONSTRAINT:
            # 约束查询扩展
            if '死' in query or '亡' in query:
                expansions.extend(['死亡', '阵亡', '牺牲', '丧生'])
            if '规则' in query or '设定' in query:
                expansions.extend(['法则', '禁忌', '天道'])
        
        return expansions


class Reranker:
    """
    重排序器
    
    使用多种策略对初始检索结果进行重排序
    """
    
    def __init__(self, embedding_service=None):
        """
        初始化重排序器
        
        Args:
            embedding_service: 向量化服务（用于语义重排）
        """
        self.embedding_service = embedding_service
    
    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        method: str = "semantic",
        top_k: Optional[int] = None
    ) -> RerankResult:
        """
        重排序
        
        Args:
            query: 原始查询
            results: 初始结果
            method: 重排序方法 ("semantic", "keyword", "position", "combined")
            top_k: 返回数量
        
        Returns:
            重排序结果
        """
        if not results:
            return RerankResult(results=[], rerank_method=method, original_order=[])
        
        original_order = [r.id for r in results]
        
        if method == "keyword":
            reranked = self._keyword_rerank(query, results)
        elif method == "position":
            reranked = self._position_rerank(results)
        elif method == "combined":
            reranked = self._combined_rerank(query, results)
        else:
            # 默认语义重排
            reranked = self._semantic_rerank(query, results)
        
        if top_k:
            reranked = reranked[:top_k]
        
        return RerankResult(
            results=reranked,
            rerank_method=method,
            original_order=original_order
        )
    
    def _semantic_rerank(
        self,
        query: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """语义重排序（基于向量相似度）"""
        if not self.embedding_service:
            return results
        
        try:
            # 获取查询向量
            query_vec = self.embedding_service.embed(query)
            
            # 计算每个结果与查询的相似度
            for result in results:
                doc_vec = self.embedding_service.embed(result.document[:500])
                
                # 余弦相似度
                similarity = self._cosine_similarity(query_vec, doc_vec)
                
                # 结合原始分数
                result.score = 0.7 * result.score + 0.3 * similarity
            
            # 重新排序
            results.sort(key=lambda x: x.score, reverse=True)
            
        except Exception as e:
            logger.warning(f"语义重排失败: {e}")
        
        return results
    
    def _keyword_rerank(
        self,
        query: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """关键词重排序"""
        # 提取查询关键词
        keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z]+', query.lower()))
        
        for result in results:
            doc_lower = result.document.lower()
            
            # 计算关键词命中率
            hits = sum(1 for kw in keywords if kw in doc_lower)
            hit_rate = hits / len(keywords) if keywords else 0
            
            # 位置加权（关键词出现在开头更重要）
            position_boost = 0
            for kw in keywords:
                pos = doc_lower.find(kw)
                if pos != -1:
                    # 越靠前加分越多
                    position_boost += 0.1 * (1 - pos / len(doc_lower))
            
            # 结合原始分数
            result.score = 0.6 * result.score + 0.3 * hit_rate + 0.1 * position_boost
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _position_rerank(self, results: List[SearchResult]) -> List[SearchResult]:
        """位置重排序（按章节顺序）"""
        def get_chapter_number(r: SearchResult) -> int:
            if r.metadata and 'chapter_number' in r.metadata:
                return r.metadata['chapter_number']
            # 尝试从 chapter_id 提取
            if r.chapter_id:
                match = re.search(r'\d+', r.chapter_id)
                if match:
                    return int(match.group())
            return 9999
        
        # 先按分数排序，再按章节号排序（相同分数时）
        results.sort(key=lambda x: (-x.score, get_chapter_number(x)))
        return results
    
    def _combined_rerank(
        self,
        query: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """组合重排序"""
        # 先关键词重排
        results = self._keyword_rerank(query, results)
        
        # 再位置调整
        results = self._position_rerank(results)
        
        return results
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math
        
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0
        
        return dot / (norm1 * norm2)


class ContextCompressor:
    """
    上下文压缩器
    
    从检索结果中智能提取最相关的片段
    """
    
    def __init__(self, max_context_length: int = 4000):
        """
        初始化压缩器
        
        Args:
            max_context_length: 最大上下文长度（字符数）
        """
        self.max_context_length = max_context_length
    
    def compress(
        self,
        query: str,
        results: List[SearchResult],
        method: str = "relevance"
    ) -> str:
        """
        压缩上下文
        
        Args:
            query: 查询
            results: 检索结果
            method: 压缩方法 ("relevance", "summary", "key_sentences")
        
        Returns:
            压缩后的上下文字符串
        """
        if not results:
            return ""
        
        if method == "summary":
            return self._summary_compress(results)
        elif method == "key_sentences":
            return self._key_sentences_compress(query, results)
        else:
            return self._relevance_compress(query, results)
    
    def _relevance_compress(
        self,
        query: str,
        results: List[SearchResult]
    ) -> str:
        """基于相关性压缩"""
        parts = []
        total_length = 0
        
        # 按分数排序
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        for result in sorted_results:
            # 提取相关片段
            snippet = self._extract_relevant_snippet(query, result.document)
            
            if total_length + len(snippet) > self.max_context_length:
                # 截断
                remaining = self.max_context_length - total_length
                if remaining > 100:
                    snippet = snippet[:remaining] + "..."
                else:
                    break
            
            # 添加来源标记
            chapter_info = f"[第{result.metadata.get('chapter_number', '?')}章]" if result.metadata else ""
            parts.append(f"{chapter_info}\n{snippet}")
            total_length += len(snippet) + len(chapter_info) + 2
        
        return "\n\n".join(parts)
    
    def _extract_relevant_snippet(
        self,
        query: str,
        document: str,
        window_size: int = 300
    ) -> str:
        """提取相关片段"""
        if len(document) <= window_size:
            return document
        
        # 查找查询关键词
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', query)
        
        best_pos = 0
        best_score = 0
        
        # 滑动窗口查找最相关片段
        for i in range(0, len(document) - window_size, 50):
            window = document[i:i + window_size]
            score = sum(1 for kw in keywords if kw in window)
            if score > best_score:
                best_score = score
                best_pos = i
        
        # 调整到句子边界
        start = max(0, best_pos)
        end = min(len(document), best_pos + window_size)
        
        # 向前查找句子开始
        while start > 0 and document[start] not in '。！？\n':
            start -= 1
        if start > 0:
            start += 1
        
        # 向后查找句子结束
        while end < len(document) and document[end] not in '。！？\n':
            end += 1
        if end < len(document):
            end += 1
        
        snippet = document[start:end].strip()
        
        # 添加省略号标记
        if start > 0:
            snippet = "..." + snippet
        if end < len(document):
            snippet = snippet + "..."
        
        return snippet
    
    def _summary_compress(self, results: List[SearchResult]) -> str:
        """摘要式压缩"""
        summaries = []
        
        for i, result in enumerate(results[:5]):  # 最多5条
            # 提取前200字作为摘要
            summary = result.document[:200].strip()
            if len(result.document) > 200:
                summary += "..."
            
            chapter_info = f"[{result.metadata.get('chapter_number', '?')}]" if result.metadata else ""
            summaries.append(f"{i+1}. {chapter_info} {summary}")
        
        return "\n".join(summaries)
    
    def _key_sentences_compress(
        self,
        query: str,
        results: List[SearchResult]
    ) -> str:
        """关键句提取压缩"""
        key_sentences = []
        total_length = 0
        
        for result in results:
            # 分割为句子
            sentences = re.split(r'[。！？\n]+', result.document)
            
            # 评分每个句子
            keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,}', query))
            
            scored_sentences = []
            for sent in sentences:
                if len(sent) < 10:
                    continue
                score = sum(1 for kw in keywords if kw in sent)
                if score > 0:
                    scored_sentences.append((score, sent))
            
            # 取最相关的句子
            scored_sentences.sort(key=lambda x: x[0], reverse=True)
            
            for score, sent in scored_sentences[:2]:
                if total_length + len(sent) > self.max_context_length:
                    break
                key_sentences.append(sent + "。")
                total_length += len(sent) + 1
        
        return " ".join(key_sentences)


class AdvancedSearch:
    """
    高级搜索引擎
    
    整合查询分析、动态权重、重排序和上下文压缩
    """
    
    def __init__(
        self,
        base_search: HybridSearch,
        embedding_service=None,
        config: Optional[RetrievalConfig] = None
    ):
        """
        初始化高级搜索
        
        Args:
            base_search: 基础混合搜索引擎
            embedding_service: 向量化服务
            config: 检索配置
        """
        self.base_search = base_search
        self.embedding_service = embedding_service
        self.config = config or RetrievalConfig()
        
        self.analyzer = QueryAnalyzer()
        self.reranker = Reranker(embedding_service)
        self.compressor = ContextCompressor()
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        use_dynamic_weights: bool = True,
        rerank: bool = True,
        rerank_method: str = "combined",
        chapter_filter: Optional[List[str]] = None,
        min_score: Optional[float] = None
    ) -> SearchResponse:
        """
        高级搜索
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            use_dynamic_weights: 是否使用动态权重
            rerank: 是否重排序
            rerank_method: 重排序方法
            chapter_filter: 章节过滤
            min_score: 最小分数阈值
        
        Returns:
            搜索响应
        """
        import time
        start_time = time.time()
        
        # 分析查询
        analysis = self.analyzer.analyze(query)
        logger.info(f"[AdvancedSearch] 查询意图: {analysis.intent.value}, "
                   f"权重: v={analysis.suggested_vector_weight}, f={analysis.suggested_fulltext_weight}")
        
        # 应用动态权重
        if use_dynamic_weights:
            original_vector_weight = self.config.vector_weight
            original_fulltext_weight = self.config.fulltext_weight
            
            self.config.vector_weight = analysis.suggested_vector_weight
            self.config.fulltext_weight = analysis.suggested_fulltext_weight
        
        try:
            # 执行基础搜索（多取一些用于重排）
            search_top_k = top_k * 3 if rerank else top_k
            
            response = self.base_search.search(
                query=analysis.cleaned_query,
                top_k=search_top_k,
                search_type=SearchType.HYBRID,
                chapter_filter=chapter_filter,
                min_score=min_score
            )
            
            # 重排序
            if rerank and response.results:
                rerank_result = self.reranker.rerank(
                    query=query,
                    results=response.results,
                    method=rerank_method,
                    top_k=top_k
                )
                response.results = rerank_result.results
                response.total = len(rerank_result.results)
        
        finally:
            # 恢复原始权重
            if use_dynamic_weights:
                self.config.vector_weight = original_vector_weight
                self.config.fulltext_weight = original_fulltext_weight
        
        response.took_ms = round((time.time() - start_time) * 1000, 2)
        
        return response
    
    def search_with_context(
        self,
        query: str,
        top_k: int = 5,
        max_context_length: int = 4000,
        compress_method: str = "relevance"
    ) -> Tuple[SearchResponse, str]:
        """
        搜索并返回压缩后的上下文
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            max_context_length: 最大上下文长度
            compress_method: 压缩方法
        
        Returns:
            (搜索响应, 压缩上下文)
        """
        # 执行搜索
        response = self.search(query, top_k=top_k)
        
        # 压缩上下文
        self.compressor.max_context_length = max_context_length
        compressed_context = self.compressor.compress(
            query=query,
            results=response.results,
            method=compress_method
        )
        
        return response, compressed_context
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        分析查询（公开接口）
        
        Args:
            query: 检索查询
        
        Returns:
            分析结果字典
        """
        analysis = self.analyzer.analyze(query)
        return {
            "original_query": analysis.original_query,
            "cleaned_query": analysis.cleaned_query,
            "intent": analysis.intent.value,
            "keywords": analysis.keywords,
            "entities": analysis.entities,
            "is_question": analysis.is_question,
            "suggested_weights": {
                "vector": analysis.suggested_vector_weight,
                "fulltext": analysis.suggested_fulltext_weight
            },
            "expansion_terms": analysis.expansion_terms
        }