"""
Wiki 多阶段检索管道

基于 LLM Wiki 模式的多阶段检索：
Phase 1: 分词搜索（中文双字 + 英文单词）
Phase 1.5: 向量语义搜索（可选，需外部 embedding 服务）
Phase 2: 图谱扩展（4信号相关性，2跳遍历+衰减）
Phase 3: 预算控制（按比例分配 token 预算）
Phase 4: 上下文组装（编号页面，完整内容）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Awaitable

from .wiki_types import (
    PageType,
    WikiPage,
    WikiGraph,
)
from .wiki_store import WikiStore
from .wiki_graph import WikiGraphBuilder

logger = logging.getLogger(__name__)

# 向量搜索函数类型
VectorSearchFn = Callable[[str, int], Awaitable[List[Tuple[str, float]]]]


@dataclass
class SearchResult:
    """单个搜索结果"""
    page: WikiPage
    score: float  # 综合相关性分数
    source: str  # 来源阶段：keyword / vector / graph
    matched_tokens: List[str] = field(default_factory=list)

    def to_context_entry(self, index: int) -> str:
        """转换为上下文条目（带编号）"""
        header = f"[{index}] {self.page.title} ({self.page.page_type.value})"
        body = self.page.body
        return f"{header}\n{body}"


@dataclass
class RetrievalResult:
    """检索结果"""
    results: List[SearchResult]
    total_candidates: int  # 候选总数
    budget_used: int  # 使用的 token 数
    budget_limit: int  # token 预算上限
    phases_used: List[str]  # 使用的检索阶段

    @property
    def context_text(self) -> str:
        """组装后的上下文文本"""
        parts = []
        for i, result in enumerate(self.results, 1):
            parts.append(result.to_context_entry(i))
        return "\n\n---\n\n".join(parts)

    @property
    def page_titles(self) -> List[str]:
        """返回结果页面标题列表"""
        return [r.page.title for r in self.results]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [
                {
                    "title": r.page.title,
                    "type": r.page.page_type.value,
                    "score": round(r.score, 3),
                    "source": r.source,
                }
                for r in self.results
            ],
            "total_candidates": self.total_candidates,
            "budget_used": self.budget_used,
            "budget_limit": self.budget_limit,
            "phases_used": self.phases_used,
        }


class BudgetAllocator:
    """
    Token 预算分配器
    
    按比例分配上下文窗口：
    - 60% wiki 页面
    - 20% 聊天历史
    - 5% 目录（index.md）
    - 15% 系统提示
    """

    def __init__(
        self,
        total_budget: int = 8000,
        wiki_ratio: float = 0.60,
        chat_ratio: float = 0.20,
        index_ratio: float = 0.05,
        system_ratio: float = 0.15,
    ):
        self.total_budget = total_budget
        self.wiki_budget = int(total_budget * wiki_ratio)
        self.chat_budget = int(total_budget * chat_ratio)
        self.index_budget = int(total_budget * index_ratio)
        self.system_budget = int(total_budget * system_ratio)

    def select_pages(
        self,
        candidates: List[SearchResult],
        max_pages: int = 20,
    ) -> List[SearchResult]:
        """
        按预算选择页面
        
        按分数降序选择，直到预算用完。
        """
        selected: List[SearchResult] = []
        used_budget = 0
        
        for result in candidates:
            if len(selected) >= max_pages:
                break
            
            # 估算页面 token 数（中文约 1.5 字/token）
            page_tokens = self._estimate_tokens(result.page.body)
            
            if used_budget + page_tokens > self.wiki_budget:
                # 尝试截断页面内容
                remaining = self.wiki_budget - used_budget
                if remaining > 100:
                    # 截断正文
                    truncated_body = self._truncate_to_tokens(
                        result.page.body, remaining
                    )
                    truncated_page = WikiPage(
                        frontmatter=result.page.frontmatter,
                        body=truncated_body,
                        file_path=result.page.file_path,
                    )
                    selected.append(SearchResult(
                        page=truncated_page,
                        score=result.score,
                        source=result.source,
                        matched_tokens=result.matched_tokens,
                    ))
                break
            
            selected.append(result)
            used_budget += page_tokens
        
        return selected

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算文本的 token 数"""
        # 中文约 1.5 字符/token，英文约 4 字符/token
        chinese_chars = len(re.findall(r"[\u4e00-\u9fa5]", text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数"""
        # 粗略截断
        max_chars = int(max_tokens * 2)
        if len(text) <= max_chars:
            return text
        
        # 按段落截断
        paragraphs = text.split("\n\n")
        result = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = BudgetAllocator._estimate_tokens(para)
            if current_tokens + para_tokens > max_tokens:
                break
            result.append(para)
            current_tokens += para_tokens
        
        return "\n\n".join(result)


class WikiRetriever:
    """
    Wiki 多阶段检索器
    
    使用方式：
        retriever = WikiRetriever(store, graph_builder)
        result = await retriever.retrieve("主角的身世", context_window=8000)
    """

    def __init__(
        self,
        store: WikiStore,
        graph_builder: WikiGraphBuilder,
        vector_search_fn: Optional[VectorSearchFn] = None,
    ):
        """
        初始化检索器
        
        Args:
            store: wiki 页面存储
            graph_builder: 知识图谱构建器
            vector_search_fn: 向量搜索函数（可选）
        """
        self._store = store
        self._graph_builder = graph_builder
        self._vector_search_fn = vector_search_fn

    async def retrieve(
        self,
        query: str,
        context_window: int = 8000,
        top_k: int = 10,
        include_graph: bool = True,
        include_vector: bool = True,
    ) -> RetrievalResult:
        """
        执行多阶段检索
        
        Args:
            query: 搜索查询
            context_window: 上下文窗口大小（token）
            top_k: 返回结果数量
            include_graph: 是否包含图谱扩展
            include_vector: 是否包含向量搜索
            
        Returns:
            检索结果
        """
        phases_used = []
        all_candidates: Dict[str, SearchResult] = {}
        
        # Phase 1: 分词搜索
        keyword_results = self._keyword_search(query, top_k=top_k * 2)
        for result in keyword_results:
            all_candidates[result.page.title] = result
        phases_used.append("keyword")
        
        # Phase 1.5: 向量语义搜索（可选）
        if include_vector and self._vector_search_fn:
            try:
                vector_results = await self._vector_search(query, top_k=top_k)
                for result in vector_results:
                    existing = all_candidates.get(result.page.title)
                    if existing:
                        # 合并分数
                        existing.score += result.score * 0.5
                        existing.source = "keyword+vector"
                    else:
                        all_candidates[result.page.title] = result
                phases_used.append("vector")
            except Exception as e:
                logger.warning(f"[Retriever] 向量搜索失败: {e}")
        
        # Phase 2: 图谱扩展
        if include_graph and all_candidates:
            seed_titles = [
                title for title, r in sorted(
                    all_candidates.items(),
                    key=lambda x: -x[1].score
                )[:5]
            ]
            graph_results = self._graph_expand(seed_titles, hops=2, decay=0.5)
            for result in graph_results:
                existing = all_candidates.get(result.page.title)
                if existing:
                    existing.score += result.score * 0.3
                    if "graph" not in existing.source:
                        existing.source += "+graph"
                else:
                    all_candidates[result.page.title] = result
            phases_used.append("graph")
        
        # 排序
        sorted_candidates = sorted(
            all_candidates.values(),
            key=lambda x: -x.score
        )
        
        # Phase 3: 预算控制
        budget = BudgetAllocator(total_budget=context_window)
        selected = budget.select_pages(sorted_candidates, max_pages=top_k)
        
        return RetrievalResult(
            results=selected,
            total_candidates=len(all_candidates),
            budget_used=budget._estimate_tokens(
                "\n".join(r.page.body for r in selected)
            ),
            budget_limit=budget.wiki_budget,
            phases_used=phases_used,
        )

    def _keyword_search(self, query: str, top_k: int = 20) -> List[SearchResult]:
        """Phase 1: 分词搜索"""
        pages = self._store.search_by_text(query, top_k=top_k)
        
        results = []
        query_tokens = self._tokenize(query.lower())
        
        for page in pages:
            # 计算匹配的 token
            page_tokens = set(self._tokenize(page.body.lower() + " " + page.title.lower()))
            matched = [t for t in query_tokens if t in page_tokens]
            
            score = len(matched) / max(len(query_tokens), 1)
            
            # 标题匹配加分
            if query.lower() in page.title.lower():
                score += 2.0
            
            results.append(SearchResult(
                page=page,
                score=score,
                source="keyword",
                matched_tokens=matched,
            ))
        
        results.sort(key=lambda x: -x.score)
        return results[:top_k]

    async def _vector_search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Phase 1.5: 向量语义搜索"""
        if not self._vector_search_fn:
            return []
        
        # 调用外部向量搜索
        vector_results = await self._vector_search_fn(query, top_k)
        
        results = []
        for title, score in vector_results:
            page = self._store.load_page(title)
            if page:
                results.append(SearchResult(
                    page=page,
                    score=score,
                    source="vector",
                ))
        
        return results

    def _graph_expand(
        self,
        seed_titles: List[str],
        hops: int = 2,
        decay: float = 0.5,
    ) -> List[SearchResult]:
        """Phase 2: 图谱扩展"""
        expanded = self._graph_builder.expand_from_seeds(
            seed_titles, hops=hops, decay=decay, max_results=10
        )
        
        results = []
        for title, score in expanded:
            if title in seed_titles:
                continue  # 跳过种子节点
            
            page = self._store.load_page(title)
            if page:
                results.append(SearchResult(
                    page=page,
                    score=score,
                    source="graph",
                ))
        
        return results

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """分词：中文双字 + 英文单词"""
        tokens = []
        # 英文单词
        english = re.findall(r"[a-zA-Z]+", text)
        tokens.extend(w.lower() for w in english)
        # 中文双字
        chinese = re.findall(r"[\u4e00-\u9fa5]", text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i] + chinese[i + 1])
        tokens.extend(chinese)
        return tokens