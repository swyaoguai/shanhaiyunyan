"""
检索路由器模块

根据配置和查询类型智能选择检索策略：
- 角色/世界观等小数据：使用摘要索引检索（无向量RAG）
- 章节/情节等大数据：使用混合检索（向量+全文）

支持用户在设置中自由切换策略。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SearchStrategy(Enum):
    """检索策略枚举"""
    SUMMARY = "summary"  # 摘要索引检索（无向量RAG）
    VECTOR = "vector"  # 纯向量检索
    FULLTEXT = "fulltext"  # 纯全文检索
    HYBRID = "hybrid"  # 混合检索（向量+全文）


class DataCategory(Enum):
    """数据分类枚举"""
    CHARACTER = "character"  # 角色
    WORLD = "world"  # 世界观设定
    ITEM = "item"  # 物品道具
    LOCATION = "location"  # 地点场景
    CHAPTER = "chapter"  # 章节内容
    PLOT = "plot"  # 情节
    DIALOGUE = "dialogue"  # 对话历史


@dataclass
class RetrievalConfig:
    """检索配置"""
    # 是否启用摘要索引检索
    summary_search_enabled: bool = False
    # 使用摘要索引的分类
    summary_search_categories: List[str] = field(
        default_factory=lambda: ["character", "world", "item", "location"]
    )
    # 章节检索模式
    chapter_search_mode: str = "hybrid"  # "hybrid", "vector", "fulltext"
    # 混合检索权重
    vector_weight: float = 0.7
    fulltext_weight: float = 0.3
    # 默认返回数量
    default_top_k: int = 5
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RetrievalConfig":
        return cls(
            summary_search_enabled=data.get("summary_search_enabled", False),
            summary_search_categories=data.get("summary_search_categories", 
                                                ["character", "world", "item", "location"]),
            chapter_search_mode=data.get("chapter_search_mode", "hybrid"),
            vector_weight=data.get("vector_weight", 0.7),
            fulltext_weight=data.get("fulltext_weight", 0.3),
            default_top_k=data.get("default_top_k", 5)
        )
    
    @classmethod
    def load_from_file(cls, project_id: str) -> "RetrievalConfig":
        """从配置文件加载"""
        try:
            from ...constants import get_data_dir
            config_path = get_data_dir() / "knowledge_base_config.json"
            
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"加载检索配置失败: {e}")
        
        return cls()


@dataclass
class RetrievalResult:
    """检索结果"""
    entry_id: str
    category: str
    name: str
    content: str
    score: float
    strategy_used: SearchStrategy
    metadata: Dict = field(default_factory=dict)


class RetrievalRouter:
    """
    检索路由器
    
    根据配置和数据类型智能选择检索策略：
    - 小数据集（角色、世界观）：摘要索引检索
    - 大数据集（章节、情节）：混合/向量/全文检索
    
    使用方式：
    ```python
    router = RetrievalRouter(
        project_id="my_project",
        summary_index=my_summary_index,
        hybrid_search=my_hybrid_search,
        llm_caller=my_llm_function
    )
    
    # 自动路由检索
    results = await router.retrieve(
        query="谁是主角",
        categories=["character", "world"]
    )
    ```
    """
    
    def __init__(
        self,
        project_id: str,
        summary_index=None,  # SummaryIndex 实例
        hybrid_search=None,  # HybridSearch 实例
        vector_store=None,  # VectorStore 实例
        fulltext_store=None,  # FulltextStore 实例
        llm_caller: Callable = None,
        config: RetrievalConfig = None
    ):
        """
        初始化检索路由器
        
        Args:
            project_id: 项目ID
            summary_index: 摘要索引实例
            hybrid_search: 混合检索实例
            vector_store: 向量存储实例
            fulltext_store: 全文存储实例
            llm_caller: LLM调用函数
            config: 检索配置
        """
        self.project_id = project_id
        self.summary_index = summary_index
        self.hybrid_search = hybrid_search
        self.vector_store = vector_store
        self.fulltext_store = fulltext_store
        self.llm_caller = llm_caller
        self.config = config or RetrievalConfig.load_from_file(project_id)
        
        logger.info(f"[RetrievalRouter] 初始化完成 - 摘要检索: {self.config.summary_search_enabled}")
    
    def update_config(self, config: RetrievalConfig):
        """更新配置"""
        self.config = config
        logger.info(f"[RetrievalRouter] 配置已更新 - 摘要检索: {config.summary_search_enabled}")
    
    def _determine_strategy(self, category: str) -> SearchStrategy:
        """根据分类确定检索策略"""
        # 如果启用了摘要检索，且分类在支持列表中
        if (self.config.summary_search_enabled and 
            category in self.config.summary_search_categories and
            self.summary_index is not None):
            return SearchStrategy.SUMMARY
        
        # 章节类数据使用配置的模式
        if category in ["chapter", "plot", "dialogue"]:
            mode = self.config.chapter_search_mode
            if mode == "vector":
                return SearchStrategy.VECTOR
            elif mode == "fulltext":
                return SearchStrategy.FULLTEXT
            else:
                return SearchStrategy.HYBRID
        
        # 默认使用混合检索
        return SearchStrategy.HYBRID
    
    async def retrieve(
        self,
        query: str,
        categories: List[str] = None,
        top_k: int = None,
        force_strategy: SearchStrategy = None
    ) -> List[RetrievalResult]:
        """
        执行检索
        
        Args:
            query: 查询文本
            categories: 要检索的分类列表
            top_k: 返回结果数量
            force_strategy: 强制使用指定策略（覆盖自动路由）
            
        Returns:
            检索结果列表
        """
        top_k = top_k or self.config.default_top_k
        all_results = []
        
        # 按分类分组，确定每个分类的检索策略
        if categories is None:
            categories = list(DataCategory.__members__.keys())
            categories = [c.lower() for c in categories]
        
        # 按策略分组分类
        strategy_categories: Dict[SearchStrategy, List[str]] = {}
        for category in categories:
            if force_strategy:
                strategy = force_strategy
            else:
                strategy = self._determine_strategy(category)
            
            if strategy not in strategy_categories:
                strategy_categories[strategy] = []
            strategy_categories[strategy].append(category)
        
        # 执行各策略的检索
        for strategy, cats in strategy_categories.items():
            try:
                results = await self._execute_strategy(
                    strategy=strategy,
                    query=query,
                    categories=cats,
                    top_k=top_k
                )
                all_results.extend(results)
            except Exception as e:
                logger.error(f"[RetrievalRouter] {strategy.value} 检索失败: {e}")
        
        # 按分数排序并截断
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]
    
    async def _execute_strategy(
        self,
        strategy: SearchStrategy,
        query: str,
        categories: List[str],
        top_k: int
    ) -> List[RetrievalResult]:
        """执行特定策略的检索"""
        
        if strategy == SearchStrategy.SUMMARY:
            return await self._summary_search(query, categories, top_k)
        elif strategy == SearchStrategy.VECTOR:
            return await self._vector_search(query, categories, top_k)
        elif strategy == SearchStrategy.FULLTEXT:
            return await self._fulltext_search(query, categories, top_k)
        else:  # HYBRID
            return await self._hybrid_search(query, categories, top_k)
    
    async def _summary_search(
        self,
        query: str,
        categories: List[str],
        top_k: int
    ) -> List[RetrievalResult]:
        """摘要索引检索"""
        if not self.summary_index:
            logger.warning("[RetrievalRouter] 摘要索引未初始化，降级到混合检索")
            return await self._hybrid_search(query, categories, top_k)
        
        try:
            results = await self.summary_index.retrieve(
                query=query,
                top_k=top_k,
                categories=categories
            )
            
            return [
                RetrievalResult(
                    entry_id=r["entry_id"],
                    category=r["category"],
                    name=r["name"],
                    content=r["content"],
                    score=r["score"],
                    strategy_used=SearchStrategy.SUMMARY,
                    metadata={"summary": r.get("summary", "")}
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"[RetrievalRouter] 摘要检索失败: {e}")
            return []
    
    async def _vector_search(
        self,
        query: str,
        categories: List[str],
        top_k: int
    ) -> List[RetrievalResult]:
        """纯向量检索"""
        # 当前知识库主链路中 vector_store 不提供按 query 文本直接检索接口，
        # 这里保持兼容：若无可用适配器则返回空并由上层混合/降级策略兜底。
        if not self.vector_store or not hasattr(self.vector_store, "search"):
            logger.warning("[RetrievalRouter] 向量存储未提供 search(query, ...) 接口，跳过纯向量检索")
            return []
        
        try:
            search_fn = getattr(self.vector_store, "search")
            results = search_fn(query=query, top_k=top_k, filter_categories=categories)
            if hasattr(results, "__await__"):
                results = await results
            
            return [
                RetrievalResult(
                    entry_id=r.get("id", ""),
                    category=r.get("category", ""),
                    name=r.get("name", ""),
                    content=r.get("content", ""),
                    score=r.get("score", 0.0),
                    strategy_used=SearchStrategy.VECTOR,
                    metadata=r.get("metadata", {})
                )
                for r in (results or [])
            ]
        except Exception as e:
            logger.error(f"[RetrievalRouter] 向量检索失败: {e}")
            return []
    
    async def _fulltext_search(
        self,
        query: str,
        categories: List[str],
        top_k: int
    ) -> List[RetrievalResult]:
        """纯全文检索"""
        if not self.fulltext_store:
            logger.warning("[RetrievalRouter] 全文存储未初始化")
            return []
        
        try:
            # 兼容 FullTextStore.search(query, top_k, chapter_filter)
            raw_results = self.fulltext_store.search(
                query=query,
                top_k=top_k
            )
            
            results: List[RetrievalResult] = []
            for r in (raw_results or []):
                metadata = getattr(r, "metadata", None) or {}
                category = metadata.get("category", "")
                if categories and category and category not in categories:
                    continue
                
                results.append(
                    RetrievalResult(
                        entry_id=getattr(r, "id", ""),
                        category=category,
                        name=metadata.get("name", ""),
                        content=getattr(r, "document", ""),
                        score=getattr(r, "score", 0.0),
                        strategy_used=SearchStrategy.FULLTEXT,
                        metadata=metadata
                    )
                )
            
            return results
        except Exception as e:
            logger.error(f"[RetrievalRouter] 全文检索失败: {e}")
            return []
    
    async def _hybrid_search(
        self,
        query: str,
        categories: List[str],
        top_k: int
    ) -> List[RetrievalResult]:
        """混合检索（向量+全文）"""
        if self.hybrid_search:
            try:
                # 兼容 HybridSearch.search(...) 同步接口
                original_vw = getattr(self.hybrid_search.config, "vector_weight", self.config.vector_weight)
                original_fw = getattr(self.hybrid_search.config, "fulltext_weight", self.config.fulltext_weight)
                self.hybrid_search.config.vector_weight = self.config.vector_weight
                self.hybrid_search.config.fulltext_weight = self.config.fulltext_weight

                try:
                    response = self.hybrid_search.search(
                        query=query,
                        top_k=top_k
                    )
                finally:
                    self.hybrid_search.config.vector_weight = original_vw
                    self.hybrid_search.config.fulltext_weight = original_fw
                
                return [
                    RetrievalResult(
                        entry_id=r.id,
                        category=(r.metadata or {}).get("category", ""),
                        name=(r.metadata or {}).get("name", ""),
                        content=r.document,
                        score=r.score,
                        strategy_used=SearchStrategy.HYBRID,
                        metadata=r.metadata or {}
                    )
                    for r in getattr(response, "results", [])
                ]
            except Exception as e:
                logger.error(f"[RetrievalRouter] 混合检索失败: {e}")
        
        # 降级：分别执行向量和全文检索，然后融合
        vector_results = await self._vector_search(query, categories, top_k)
        fulltext_results = await self._fulltext_search(query, categories, top_k)
        
        # 简单的分数融合
        merged = {}
        for r in vector_results:
            merged[r.entry_id] = RetrievalResult(
                entry_id=r.entry_id,
                category=r.category,
                name=r.name,
                content=r.content,
                score=r.score * self.config.vector_weight,
                strategy_used=SearchStrategy.HYBRID,
                metadata=r.metadata
            )
        
        for r in fulltext_results:
            if r.entry_id in merged:
                merged[r.entry_id].score += r.score * self.config.fulltext_weight
            else:
                merged[r.entry_id] = RetrievalResult(
                    entry_id=r.entry_id,
                    category=r.category,
                    name=r.name,
                    content=r.content,
                    score=r.score * self.config.fulltext_weight,
                    strategy_used=SearchStrategy.HYBRID,
                    metadata=r.metadata
                )
        
        results = list(merged.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        stats = {
            "config": {
                "summary_search_enabled": self.config.summary_search_enabled,
                "summary_search_categories": self.config.summary_search_categories,
                "chapter_search_mode": self.config.chapter_search_mode,
                "vector_weight": self.config.vector_weight,
                "fulltext_weight": self.config.fulltext_weight
            },
            "components": {
                "summary_index": self.summary_index is not None,
                "hybrid_search": self.hybrid_search is not None,
                "vector_store": self.vector_store is not None,
                "fulltext_store": self.fulltext_store is not None,
                "llm_caller": self.llm_caller is not None
            }
        }
        
        if self.summary_index:
            stats["summary_index_stats"] = self.summary_index.get_stats()
        
        return stats


class UnifiedSearch:
    """
    统一检索接口
    
    封装RetrievalRouter，提供简洁的检索API。
    """
    
    def __init__(self, project_id: str, llm_caller: Callable = None):
        """初始化统一检索"""
        self.project_id = project_id
        self.llm_caller = llm_caller
        self.router = None
        self._initialized = False
    
    async def initialize(self):
        """延迟初始化"""
        if self._initialized:
            return
        
        from ..logic_layer.summary_index import SummaryIndex
        
        # 加载配置
        config = RetrievalConfig.load_from_file(self.project_id)
        
        # 初始化摘要索引
        summary_index = None
        if config.summary_search_enabled:
            summary_index = SummaryIndex(
                project_id=self.project_id,
                llm_caller=self.llm_caller
            )
        
        # 初始化路由器
        self.router = RetrievalRouter(
            project_id=self.project_id,
            summary_index=summary_index,
            llm_caller=self.llm_caller,
            config=config
        )
        
        self._initialized = True
        logger.info(f"[UnifiedSearch] 初始化完成")
    
    async def search(
        self,
        query: str,
        categories: List[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        统一检索接口
        
        Args:
            query: 查询文本
            categories: 分类过滤
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        if not self._initialized:
            await self.initialize()
        
        results = await self.router.retrieve(
            query=query,
            categories=categories,
            top_k=top_k
        )
        
        return [
            {
                "id": r.entry_id,
                "category": r.category,
                "name": r.name,
                "content": r.content,
                "score": r.score,
                "strategy": r.strategy_used.value,
                "metadata": r.metadata
            }
            for r in results
        ]
    
    async def add_entry(
        self,
        entry_id: str,
        category: str,
        name: str,
        content: str
    ):
        """添加条目（自动路由到合适的存储）"""
        if not self._initialized:
            await self.initialize()
        
        # 如果启用摘要检索且分类匹配，添加到摘要索引
        if (self.router.config.summary_search_enabled and 
            category in self.router.config.summary_search_categories and
            self.router.summary_index):
            await self.router.summary_index.add_entry(
                entry_id=entry_id,
                category=category,
                name=name,
                content=content
            )
        
        # 同时也可以添加到向量存储（如果需要的话）
        # 这里可以根据实际需求扩展
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized:
            return {"initialized": False}
        
        return self.router.get_stats()