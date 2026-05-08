"""
知识库主入口模块

整合数据层、逻辑层和应用层，提供统一的知识库接口。

参考 SeekDB 设计优化：
- 动态混合搜索权重
- 统一数据模型
- 智能重排序
- 上下文压缩
"""

import logging
from typing import Optional, Any, List, Dict

from .config import KnowledgeBaseConfig, SiliconFlowConfig
from .data_layer.vector_store import VectorStore, MockVectorStore, CHROMA_AVAILABLE
from .data_layer.fulltext_store import FullTextStore
from .data_layer.metadata_store import MetadataStore, ChapterInfo
from .logic_layer.chunker import TextChunker
from .logic_layer.embeddings import (
    EmbeddingService,
    LocalOnnxEmbeddingService,
    MockEmbeddingService,
    NVIDIAEmbeddingService,
)
from .logic_layer.chapter_marker import ChapterMarker
from .application_layer.hybrid_search import HybridSearch, SearchResponse, SearchType
from .application_layer.knowledge_api import KnowledgeAPI, AddChapterResult
from .application_layer.navigator import ChapterNavigator
from .application_layer.advanced_search import AdvancedSearch, QueryIntent
from .application_layer.unified_model import (
    UnifiedStore, UnifiedDocument, UnifiedSearchResult,
    DataType, ConstraintSeverity, DocumentFactory
)

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    知识库主类
    
    整合所有组件，提供统一的知识库操作接口。
    
    使用示例:
        kb = KnowledgeBase(project_id="my_novel")
        
        # 添加章节
        kb.add_chapter("chapter_1", "第一章 开端", "这是第一章的内容...")
        
        # 搜索
        results = kb.search("主角的身世")
        
        # 导航
        chapters = kb.list_chapters()
    """
    
    def __init__(
        self,
        project_id: str = "default",
        config: Optional[KnowledgeBaseConfig] = None,
        use_mock_embeddings: bool = False
    ):
        """
        初始化知识库
        
        Args:
            project_id: 项目ID
            config: 知识库配置（可选，默认从环境变量加载）
            use_mock_embeddings: 是否使用模拟向量服务（用于测试）
        """
        # 加载配置
        if config:
            self.config = config
        else:
            self.config = KnowledgeBaseConfig.from_env(project_id)
        
        self.project_id = project_id
        
        # 验证配置
        if use_mock_embeddings:
            # 仅在用户明确要求测试时才允许使用模拟
            logger.warning(
                "⚠️ 知识库正在使用模拟向量化服务！这仅应用于测试目的！"
                "生产环境请配置 SILICONFLOW_API_KEY 环境变量或在设置中配置。"
            )
        else:
            errors = self.config.validate()
            if errors:
                # 配置有问题时抛出异常，而非仅警告
                raise ValueError(
                    f"知识库配置错误: {'; '.join(errors)}。"
                    "请在设置中配置SiliconFlow API Key，或设置SILICONFLOW_API_KEY环境变量。"
                )
        
        # 初始化各层组件
        self._init_components(use_mock_embeddings)
        
        logger.info(f"知识库初始化完成: project_id={project_id}")
    
    def _init_components(self, use_mock_embeddings: bool):
        """初始化各层组件"""
        # 数据层 - 向量存储
        # 优先使用真实的ChromaDB，仅在明确要求使用mock时才降级
        logger.info(f"[KnowledgeBase] 初始化组件: use_mock_embeddings={use_mock_embeddings}, CHROMA_AVAILABLE={CHROMA_AVAILABLE}")
        
        if use_mock_embeddings:
            logger.warning("⚠️ 使用模拟向量存储（用户明确要求 use_mock_embeddings=True）")
            self._vector_store = MockVectorStore(self.config.chroma)
        elif not CHROMA_AVAILABLE:
            # ChromaDB不可用，这是一个严重问题
            from .data_layer.vector_store import CHROMA_IMPORT_ERROR
            error_msg = f"ChromaDB不可用，无法初始化真实向量存储。错误: {CHROMA_IMPORT_ERROR}"
            logger.error(f"✗ {error_msg}")
            logger.error("请运行: pip install chromadb")
            raise ImportError(error_msg)
        else:
            # 使用真实的ChromaDB
            logger.info(f"✓ 初始化ChromaDB向量存储: {self.config.chroma.persist_directory}")
            try:
                self._vector_store = VectorStore(self.config.chroma)
                logger.info(f"✓ ChromaDB向量存储初始化成功，当前文档数: {self._vector_store.count()}")
            except Exception as e:
                logger.error(f"✗ ChromaDB向量存储初始化失败: {e}")
                raise
        
        self._fulltext_store = FullTextStore(self.config.sqlite)
        self._metadata_store = MetadataStore(self.config.sqlite)
        
        # 逻辑层
        self._chunker = TextChunker(self.config.chunking)
        self._chapter_marker = ChapterMarker()
        
        provider = str(self.config.embedding_provider or "").strip().lower()
        if use_mock_embeddings:
            self._embedding_service = MockEmbeddingService(
                embedding_dim=self.config.siliconflow.embedding_dim
            )
        elif provider == "nvidia":
            self._embedding_service = NVIDIAEmbeddingService(self.config.nvidia)
        elif provider in {"local", "local_onnx"}:
            self._embedding_service = LocalOnnxEmbeddingService(self.config.local_onnx)
        else:
            self._embedding_service = EmbeddingService(self.config.siliconflow)
        
        # 应用层
        self._search = HybridSearch(
            vector_store=self._vector_store,
            fulltext_store=self._fulltext_store,
            embedding_service=self._embedding_service,
            config=self.config.retrieval
        )
        
        self._api = KnowledgeAPI(
            vector_store=self._vector_store,
            fulltext_store=self._fulltext_store,
            metadata_store=self._metadata_store,
            embedding_service=self._embedding_service,
            chunker=self._chunker,
            chapter_marker=self._chapter_marker
        )
        
        self._navigator = ChapterNavigator(self._metadata_store)
        
        # 高级搜索（参考 SeekDB）
        self._advanced_search = AdvancedSearch(
            base_search=self._search,
            embedding_service=self._embedding_service
        )
        
        # 统一存储（参考 SeekDB）
        self._unified_store = UnifiedStore(
            vector_store=self._vector_store,
            fulltext_store=self._fulltext_store,
            metadata_store=self._metadata_store,
            embedding_service=self._embedding_service
        )
    
    # ==================== 章节管理 ====================
    
    def add_chapter(
        self,
        chapter_id: Optional[str],
        title: str,
        content: str,
        chapter_number: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> AddChapterResult:
        """
        添加章节
        
        Args:
            chapter_id: 章节ID（可选，自动生成）
            title: 章节标题
            content: 章节内容
            chapter_number: 章节序号
            metadata: 其他元数据
        
        Returns:
            添加结果
        """
        result = self._api.add_chapter(
            chapter_id=chapter_id,
            title=title,
            content=content,
            chapter_number=chapter_number,
            metadata=metadata
        )
        
        # 使导航缓存失效
        self._navigator.invalidate_cache()
        
        return result
    
    def update_chapter(
        self,
        chapter_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        chapter_number: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> AddChapterResult:
        """
        更新章节
        
        Args:
            chapter_id: 章节ID
            title: 新标题
            content: 新内容
            chapter_number: 新序号
            metadata: 新元数据
        
        Returns:
            更新结果
        """
        result = self._api.update_chapter(
            chapter_id=chapter_id,
            title=title,
            content=content,
            chapter_number=chapter_number,
            metadata=metadata
        )
        
        self._navigator.invalidate_cache()
        return result
    
    def delete_chapter(self, chapter_id: str) -> bool:
        """
        删除章节
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            是否删除成功
        """
        result = self._api.delete_chapter(chapter_id)
        self._navigator.invalidate_cache()
        return result
    
    def get_chapter(self, chapter_id: str) -> Optional[ChapterInfo]:
        """
        获取章节信息
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节信息
        """
        return self._api.get_chapter(chapter_id)
    
    def get_chapter_content(self, chapter_id: str) -> Optional[str]:
        """
        获取章节完整内容
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节内容
        """
        return self._api.get_chapter_content(chapter_id)
    
    def list_chapters(
        self,
        order_by: str = "chapter_number",
        ascending: bool = True,
        limit: Optional[int] = None
    ) -> list[ChapterInfo]:
        """
        列出所有章节
        
        Args:
            order_by: 排序字段
            ascending: 是否升序
            limit: 返回数量限制
        
        Returns:
            章节列表
        """
        return self._api.list_chapters(
            order_by=order_by,
            ascending=ascending,
            limit=limit
        )
    
    def import_document(
        self,
        content: str,
        auto_detect_chapters: bool = True,
        default_title: str = "未命名文档"
    ) -> list[AddChapterResult]:
        """
        导入文档
        
        自动检测章节结构并添加到知识库
        
        Args:
            content: 文档内容
            auto_detect_chapters: 是否自动检测章节
            default_title: 默认标题
        
        Returns:
            添加结果列表
        """
        results = self._api.import_document(
            content=content,
            auto_detect_chapters=auto_detect_chapters,
            default_title=default_title
        )
        
        self._navigator.invalidate_cache()
        return results
    
    # ==================== 检索 ====================
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        search_type: str = "hybrid",
        chapter_filter: Optional[list[str]] = None,
        min_score: Optional[float] = None
    ) -> SearchResponse:
        """
        检索知识库
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            search_type: 检索类型 ("vector", "fulltext", "hybrid")
            chapter_filter: 章节过滤
            min_score: 最小分数阈值
        
        Returns:
            检索响应
        """
        search_type_enum = SearchType(search_type)
        
        return self._search.search(
            query=query,
            top_k=top_k,
            search_type=search_type_enum,
            chapter_filter=chapter_filter,
            min_score=min_score
        )
    
    def vector_search(
        self,
        query: str,
        top_k: int = 5,
        chapter_filter: Optional[list[str]] = None
    ) -> SearchResponse:
        """向量语义检索"""
        return self.search(
            query=query,
            top_k=top_k,
            search_type="vector",
            chapter_filter=chapter_filter
        )
    
    def fulltext_search(
        self,
        query: str,
        top_k: int = 5,
        chapter_filter: Optional[list[str]] = None
    ) -> SearchResponse:
        """全文关键词检索"""
        return self.search(
            query=query,
            top_k=top_k,
            search_type="fulltext",
            chapter_filter=chapter_filter
        )
    
    def advanced_search(
        self,
        query: str,
        top_k: int = 5,
        use_dynamic_weights: bool = True,
        rerank: bool = True,
        compress_context: bool = False,
        chapter_filter: Optional[list[str]] = None
    ) -> SearchResponse:
        """
        高级搜索（参考 SeekDB 优化）
        
        特性：
        - 动态权重：根据查询意图自动调整向量/全文权重
        - 重排序：使用多策略对结果重新排序
        - 上下文压缩：智能压缩结果以节省 token
        
        Args:
            query: 检索查询
            top_k: 返回结果数量
            use_dynamic_weights: 是否使用动态权重
            rerank: 是否进行重排序
            compress_context: 是否压缩上下文
            chapter_filter: 章节过滤
        
        Returns:
            检索响应
        """
        return self._advanced_search.search(
            query=query,
            top_k=top_k,
            use_dynamic_weights=use_dynamic_weights,
            rerank=rerank,
            compress_context=compress_context,
            chapter_filter=chapter_filter
        )
    
    def search_constraints(
        self,
        query: str,
        constraint_types: Optional[List[str]] = None,
        top_k: int = 10
    ) -> List[UnifiedSearchResult]:
        """
        搜索剧情约束
        
        Args:
            query: 搜索查询
            constraint_types: 约束类型过滤
            top_k: 返回数量
        
        Returns:
            约束搜索结果
        """
        results = self._unified_store.search(
            query=query,
            doc_types=[DataType.CONSTRAINT],
            top_k=top_k
        )
        
        if constraint_types:
            results = [
                r for r in results
                if r.document.constraint_type in constraint_types
            ]
        
        return results
    
    def get_active_constraints(
        self,
        constraint_types: Optional[List[str]] = None,
        severity: Optional[ConstraintSeverity] = None
    ) -> List[UnifiedDocument]:
        """
        获取活跃的剧情约束
        
        Args:
            constraint_types: 约束类型过滤
            severity: 严重性过滤
        
        Returns:
            约束列表
        """
        return self._unified_store.get_active_constraints(
            constraint_types=constraint_types,
            severity=severity
        )
    
    def get_dead_characters(self) -> List[str]:
        """获取已死亡角色列表"""
        return self._unified_store.get_dead_characters()
    
    def add_constraint(
        self,
        constraint_type: str,
        description: str,
        entities: List[str],
        source_chapter: str,
        chapter_number: int,
        context: str = "",
        severity: ConstraintSeverity = ConstraintSeverity.HIGH
    ) -> bool:
        """
        添加剧情约束
        
        Args:
            constraint_type: 约束类型（如 character_death, ability_change）
            description: 约束描述
            entities: 涉及的实体
            source_chapter: 来源章节ID
            chapter_number: 章节序号
            context: 上下文
            severity: 严重性
        
        Returns:
            是否成功
        """
        import uuid
        
        doc = DocumentFactory.create_constraint(
            constraint_id=str(uuid.uuid4())[:8],
            constraint_type=constraint_type,
            description=description,
            entities=entities,
            source_chapter=source_chapter,
            chapter_number=chapter_number,
            context=context,
            severity=severity
        )
        
        return self._unified_store.add(doc)
    
    def search_by_entity(
        self,
        entity: str,
        doc_types: Optional[List[DataType]] = None,
        top_k: int = 10
    ) -> List[UnifiedSearchResult]:
        """
        按实体搜索（如角色名、地点名）
        
        Args:
            entity: 实体名称
            doc_types: 文档类型过滤
            top_k: 返回数量
        
        Returns:
            搜索结果
        """
        return self._unified_store.search(
            query=entity,
            doc_types=doc_types,
            entities=[entity],
            top_k=top_k
        )
    
    def get_context_for_writing(
        self,
        query: str,
        current_chapter: int,
        max_tokens: int = 2000,
        include_constraints: bool = True
    ) -> Dict[str, Any]:
        """
        获取写作上下文
        
        智能收集与当前写作相关的所有信息：
        - 相关章节内容
        - 活跃的剧情约束
        - 角色状态
        
        Args:
            query: 当前写作相关的查询
            current_chapter: 当前章节号
            max_tokens: 最大 token 数
            include_constraints: 是否包含约束
        
        Returns:
            写作上下文字典
        """
        context = {
            "relevant_content": [],
            "constraints": [],
            "dead_characters": [],
            "character_states": [],
            "total_tokens_estimate": 0
        }
        
        # 1. 搜索相关内容
        search_results = self.advanced_search(
            query=query,
            top_k=5,
            use_dynamic_weights=True,
            rerank=True,
            compress_context=True
        )
        
        for result in search_results.results:
            context["relevant_content"].append({
                "content": result.document if hasattr(result, "document") else str(result),
                "chapter": result.metadata.get("chapter_id") if result.metadata else None,
                "score": result.score
            })
        
        # 2. 获取约束
        if include_constraints:
            constraints = self.get_active_constraints(
                severity=ConstraintSeverity.CRITICAL
            )
            for c in constraints:
                context["constraints"].append({
                    "type": c.constraint_type,
                    "description": c.title,
                    "entities": c.entities
                })
            
            # 死亡角色
            context["dead_characters"] = self.get_dead_characters()
        
        # 估算 token
        import json
        context["total_tokens_estimate"] = len(
            json.dumps(context, ensure_ascii=False)
        ) // 4
        
        return context
    
    # ==================== 导航 ====================
    
    def get_table_of_contents(self) -> list[dict]:
        """获取目录"""
        return self._navigator.get_table_of_contents()
    
    def go_to_chapter(self, chapter_number: int) -> Optional[ChapterInfo]:
        """跳转到指定章节"""
        return self._navigator.go_to_chapter(chapter_number)
    
    def get_next_chapter(self, chapter_id: str) -> Optional[ChapterInfo]:
        """获取下一章"""
        return self._navigator.get_next_chapter(chapter_id)
    
    def get_previous_chapter(self, chapter_id: str) -> Optional[ChapterInfo]:
        """获取上一章"""
        return self._navigator.get_previous_chapter(chapter_id)
    
    # ==================== 统计与管理 ====================
    
    def get_statistics(self) -> dict[str, Any]:
        """获取知识库统计信息"""
        return self._api.get_statistics()
    
    def clear(self) -> bool:
        """清空知识库"""
        result = self._api.clear_all()
        self._navigator.invalidate_cache()
        return result
    
    def close(self):
        """关闭知识库，释放资源"""
        self._embedding_service.close()
        self._fulltext_store.close()
        self._metadata_store.close()
        logger.info(f"知识库已关闭: project_id={self.project_id}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # ==================== 属性访问 ====================
    
    @property
    def search_engine(self) -> HybridSearch:
        """获取底层搜索引擎"""
        return self._search
    
    @property
    def knowledge_api(self) -> KnowledgeAPI:
        """获取底层知识API"""
        return self._api
    
    @property
    def navigator(self) -> ChapterNavigator:
        """获取底层导航器"""
        return self._navigator
    
    @property
    def advanced_search_engine(self) -> AdvancedSearch:
        """获取高级搜索引擎"""
        return self._advanced_search
    
    @property
    def unified_store(self) -> UnifiedStore:
        """获取统一存储"""
        return self._unified_store
