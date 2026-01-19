# -*- coding: utf-8 -*-
"""
统一数据模型（参考 SeekDB 设计）

将不同类型的数据（章节、约束、角色、设定）统一到一个模型中，
提供统一的存储和检索接口。

数据类型：
- chapter: 章节内容
- constraint: 剧情约束（角色死亡、能力变化等）
- character: 角色信息
- worldbuilding: 世界观设定
- item: 重要物品
- timeline: 时间线事件
"""

import re
import logging
import json
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """数据类型"""
    CHAPTER = "chapter"
    CONSTRAINT = "constraint"
    CHARACTER = "character"
    WORLDBUILDING = "worldbuilding"
    ITEM = "item"
    TIMELINE = "timeline"
    SUMMARY = "summary"
    CUSTOM = "custom"


class ConstraintSeverity(str, Enum):
    """约束严重性"""
    CRITICAL = "critical"  # 必须遵守，如角色死亡
    HIGH = "high"          # 高优先级
    MEDIUM = "medium"      # 中等优先级
    LOW = "low"            # 低优先级


@dataclass
class UnifiedDocument:
    """
    统一文档模型
    
    所有类型的数据都使用这个统一的模型存储和检索
    """
    # 基础字段
    doc_id: str
    doc_type: DataType
    title: str
    content: str
    
    # 来源信息
    source_chapter: Optional[str] = None
    chapter_number: Optional[int] = None
    
    # 相关实体
    entities: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # 约束特有字段
    constraint_type: Optional[str] = None
    severity: ConstraintSeverity = ConstraintSeverity.MEDIUM
    is_active: bool = True  # 约束是否仍然有效
    
    # 时间信息
    created_at: str = ""
    updated_at: str = ""
    
    # 扩展元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 向量化状态
    is_embedded: bool = False
    embedding_model: Optional[str] = None
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["doc_type"] = self.doc_type.value
        data["severity"] = self.severity.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedDocument":
        """从字典创建"""
        if "doc_type" in data and isinstance(data["doc_type"], str):
            data["doc_type"] = DataType(data["doc_type"])
        if "severity" in data and isinstance(data["severity"], str):
            data["severity"] = ConstraintSeverity(data["severity"])
        return cls(**data)
    
    def get_searchable_text(self) -> str:
        """获取可搜索的文本（用于全文索引）"""
        parts = [self.title, self.content]
        
        if self.entities:
            parts.append(" ".join(self.entities))
        
        if self.tags:
            parts.append(" ".join(self.tags))
        
        return " ".join(parts)
    
    def get_embedding_text(self) -> str:
        """获取用于向量化的文本"""
        # 根据文档类型构建不同的向量化文本
        if self.doc_type == DataType.CONSTRAINT:
            # 约束：强调约束内容和实体
            parts = [
                f"[约束] {self.constraint_type or ''}",
                self.title,
                self.content[:500],
                f"涉及: {', '.join(self.entities)}" if self.entities else ""
            ]
        elif self.doc_type == DataType.CHARACTER:
            # 角色：名字和描述
            parts = [
                f"[角色] {self.title}",
                self.content[:500],
                f"标签: {', '.join(self.tags)}" if self.tags else ""
            ]
        else:
            # 默认：标题和内容
            parts = [self.title, self.content[:500]]
        
        return " ".join(filter(None, parts))


@dataclass
class UnifiedSearchResult:
    """统一搜索结果"""
    document: UnifiedDocument
    score: float
    highlight: Optional[str] = None
    explain: Optional[Dict[str, Any]] = None


class UnifiedStore:
    """
    统一存储接口
    
    整合向量存储和全文存储，提供统一的数据管理
    """
    
    def __init__(
        self,
        vector_store,
        fulltext_store,
        metadata_store,
        embedding_service
    ):
        """
        初始化统一存储
        
        Args:
            vector_store: 向量存储
            fulltext_store: 全文存储
            metadata_store: 元数据存储
            embedding_service: 向量化服务
        """
        self.vector_store = vector_store
        self.fulltext_store = fulltext_store
        self.metadata_store = metadata_store
        self.embedding_service = embedding_service
        
        # 内存缓存
        self._doc_cache: Dict[str, UnifiedDocument] = {}
        
        # 类型索引
        self._type_index: Dict[DataType, List[str]] = {t: [] for t in DataType}
        
        # 实体索引
        self._entity_index: Dict[str, List[str]] = {}
    
    def add(self, doc: UnifiedDocument) -> bool:
        """
        添加文档
        
        Args:
            doc: 统一文档
        
        Returns:
            是否成功
        """
        try:
            # 向量化
            embedding_text = doc.get_embedding_text()
            embedding = self.embedding_service.embed(embedding_text)
            
            # 存储到向量库
            self.vector_store.add(
                ids=[doc.doc_id],
                embeddings=[embedding],
                documents=[doc.content],
                metadatas=[{
                    "doc_type": doc.doc_type.value,
                    "title": doc.title,
                    "chapter_id": doc.source_chapter or "",
                    "chapter_number": doc.chapter_number or 0,
                    "entities": json.dumps(doc.entities, ensure_ascii=False),
                    "tags": json.dumps(doc.tags, ensure_ascii=False),
                    "constraint_type": doc.constraint_type or "",
                    "severity": doc.severity.value,
                    "is_active": doc.is_active,
                }]
            )
            
            doc.is_embedded = True
            doc.embedding_model = getattr(self.embedding_service, 'model', 'unknown')
            
            # 存储到全文索引
            self.fulltext_store.add(
                id=doc.doc_id,
                content=doc.get_searchable_text(),
                metadata={
                    "doc_type": doc.doc_type.value,
                    "chapter_id": doc.source_chapter,
                }
            )
            
            # 更新缓存和索引
            self._doc_cache[doc.doc_id] = doc
            self._type_index[doc.doc_type].append(doc.doc_id)
            
            for entity in doc.entities:
                if entity not in self._entity_index:
                    self._entity_index[entity] = []
                self._entity_index[entity].append(doc.doc_id)
            
            logger.debug(f"[UnifiedStore] 添加文档: {doc.doc_id} ({doc.doc_type.value})")
            return True
            
        except Exception as e:
            logger.error(f"[UnifiedStore] 添加文档失败: {e}")
            return False
    
    def add_batch(self, docs: List[UnifiedDocument]) -> int:
        """批量添加文档"""
        success_count = 0
        for doc in docs:
            if self.add(doc):
                success_count += 1
        return success_count
    
    def get(self, doc_id: str) -> Optional[UnifiedDocument]:
        """获取文档"""
        if doc_id in self._doc_cache:
            return self._doc_cache[doc_id]
        return None
    
    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        try:
            # 从向量库删除
            self.vector_store.delete(ids=[doc_id])
            
            # 从全文索引删除
            self.fulltext_store.delete(doc_id)
            
            # 更新缓存和索引
            if doc_id in self._doc_cache:
                doc = self._doc_cache[doc_id]
                
                # 从类型索引删除
                if doc_id in self._type_index[doc.doc_type]:
                    self._type_index[doc.doc_type].remove(doc_id)
                
                # 从实体索引删除
                for entity in doc.entities:
                    if entity in self._entity_index and doc_id in self._entity_index[entity]:
                        self._entity_index[entity].remove(doc_id)
                
                del self._doc_cache[doc_id]
            
            return True
            
        except Exception as e:
            logger.error(f"[UnifiedStore] 删除文档失败: {e}")
            return False
    
    def search(
        self,
        query: str,
        doc_types: Optional[List[DataType]] = None,
        entities: Optional[List[str]] = None,
        top_k: int = 10,
        min_score: float = 0.0,
        search_type: str = "hybrid"
    ) -> List[UnifiedSearchResult]:
        """
        统一搜索
        
        Args:
            query: 查询
            doc_types: 文档类型过滤
            entities: 实体过滤
            top_k: 返回数量
            min_score: 最小分数
            search_type: 搜索类型 ("vector", "fulltext", "hybrid")
        
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 构建过滤条件
            where = {}
            if doc_types:
                where["doc_type"] = {"$in": [t.value for t in doc_types]}
            
            if search_type in ("vector", "hybrid"):
                # 向量搜索
                query_embedding = self.embedding_service.embed(query)
                
                vector_results = self.vector_store.query(
                    query_embedding=query_embedding,
                    top_k=top_k * 2,
                    where=where if where else None
                )
                
                for i, doc_id in enumerate(vector_results.get("ids", [])):
                    distance = vector_results.get("distances", [0])[i]
                    score = 1 - distance
                    
                    if score >= min_score:
                        doc = self.get(doc_id)
                        if doc:
                            # 实体过滤
                            if entities and not any(e in doc.entities for e in entities):
                                continue
                            
                            results.append(UnifiedSearchResult(
                                document=doc,
                                score=score
                            ))
            
            if search_type in ("fulltext", "hybrid"):
                # 全文搜索
                fulltext_results = self.fulltext_store.search(
                    query=query,
                    top_k=top_k * 2
                )
                
                # 合并结果
                existing_ids = {r.document.doc_id for r in results}
                
                for ft_result in fulltext_results:
                    doc_id = ft_result.id
                    
                    if doc_id in existing_ids:
                        # 更新分数
                        for r in results:
                            if r.document.doc_id == doc_id:
                                r.score = (r.score + ft_result.score) / 2
                                break
                    else:
                        doc = self.get(doc_id)
                        if doc:
                            # 类型过滤
                            if doc_types and doc.doc_type not in doc_types:
                                continue
                            
                            # 实体过滤
                            if entities and not any(e in doc.entities for e in entities):
                                continue
                            
                            if ft_result.score >= min_score:
                                results.append(UnifiedSearchResult(
                                    document=doc,
                                    score=ft_result.score,
                                    highlight=ft_result.highlight
                                ))
            
            # 排序
            results.sort(key=lambda x: x.score, reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"[UnifiedStore] 搜索失败: {e}")
            return []
    
    def get_by_type(self, doc_type: DataType) -> List[UnifiedDocument]:
        """按类型获取文档"""
        doc_ids = self._type_index.get(doc_type, [])
        return [self._doc_cache[id] for id in doc_ids if id in self._doc_cache]
    
    def get_by_entity(self, entity: str) -> List[UnifiedDocument]:
        """按实体获取文档"""
        doc_ids = self._entity_index.get(entity, [])
        return [self._doc_cache[id] for id in doc_ids if id in self._doc_cache]
    
    def get_active_constraints(
        self,
        constraint_types: Optional[List[str]] = None,
        severity: Optional[ConstraintSeverity] = None
    ) -> List[UnifiedDocument]:
        """
        获取活跃的约束
        
        Args:
            constraint_types: 约束类型过滤
            severity: 严重性过滤
        
        Returns:
            约束文档列表
        """
        constraints = self.get_by_type(DataType.CONSTRAINT)
        
        # 过滤活跃约束
        active = [c for c in constraints if c.is_active]
        
        # 类型过滤
        if constraint_types:
            active = [c for c in active if c.constraint_type in constraint_types]
        
        # 严重性过滤
        if severity:
            active = [c for c in active if c.severity == severity]
        
        return active
    
    def get_dead_characters(self) -> List[str]:
        """获取死亡角色列表"""
        death_constraints = self.get_active_constraints(
            constraint_types=["character_death"]
        )
        
        dead_chars = set()
        for constraint in death_constraints:
            dead_chars.update(constraint.entities)
        
        return list(dead_chars)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_documents": len(self._doc_cache),
            "by_type": {},
            "total_entities": len(self._entity_index),
            "constraints": {
                "total": 0,
                "active": 0,
                "by_severity": {}
            }
        }
        
        for doc_type in DataType:
            count = len(self._type_index.get(doc_type, []))
            stats["by_type"][doc_type.value] = count
        
        constraints = self.get_by_type(DataType.CONSTRAINT)
        stats["constraints"]["total"] = len(constraints)
        stats["constraints"]["active"] = len([c for c in constraints if c.is_active])
        
        for severity in ConstraintSeverity:
            count = len([c for c in constraints if c.severity == severity])
            stats["constraints"]["by_severity"][severity.value] = count
        
        return stats


class DocumentFactory:
    """
    文档工厂
    
    从不同来源创建 UnifiedDocument
    """
    
    @staticmethod
    def create_chapter(
        chapter_id: str,
        title: str,
        content: str,
        chapter_number: int,
        metadata: Optional[Dict] = None
    ) -> UnifiedDocument:
        """创建章节文档"""
        return UnifiedDocument(
            doc_id=f"chapter_{chapter_id}",
            doc_type=DataType.CHAPTER,
            title=title,
            content=content,
            source_chapter=chapter_id,
            chapter_number=chapter_number,
            metadata=metadata or {}
        )
    
    @staticmethod
    def create_constraint(
        constraint_id: str,
        constraint_type: str,
        description: str,
        entities: List[str],
        source_chapter: str,
        chapter_number: int,
        context: str = "",
        severity: ConstraintSeverity = ConstraintSeverity.HIGH
    ) -> UnifiedDocument:
        """创建约束文档"""
        return UnifiedDocument(
            doc_id=f"constraint_{constraint_id}",
            doc_type=DataType.CONSTRAINT,
            title=description,
            content=context or description,
            source_chapter=source_chapter,
            chapter_number=chapter_number,
            entities=entities,
            constraint_type=constraint_type,
            severity=severity
        )
    
    @staticmethod
    def create_character(
        character_id: str,
        name: str,
        description: str,
        traits: Optional[List[str]] = None,
        status: str = "active"
    ) -> UnifiedDocument:
        """创建角色文档"""
        return UnifiedDocument(
            doc_id=f"character_{character_id}",
            doc_type=DataType.CHARACTER,
            title=name,
            content=description,
            entities=[name],
            tags=traits or [],
            metadata={"status": status}
        )
    
    @staticmethod
    def create_worldbuilding(
        setting_id: str,
        category: str,
        name: str,
        description: str,
        tags: Optional[List[str]] = None
    ) -> UnifiedDocument:
        """创建世界观设定文档"""
        return UnifiedDocument(
            doc_id=f"world_{setting_id}",
            doc_type=DataType.WORLDBUILDING,
            title=f"[{category}] {name}",
            content=description,
            tags=tags or [],
            metadata={"category": category}
        )
    
    @staticmethod
    def create_summary(
        summary_id: str,
        chapter_range: str,
        summary: str,
        key_events: Optional[List[str]] = None
    ) -> UnifiedDocument:
        """创建章节摘要文档"""
        return UnifiedDocument(
            doc_id=f"summary_{summary_id}",
            doc_type=DataType.SUMMARY,
            title=f"剧情摘要 {chapter_range}",
            content=summary,
            tags=key_events or [],
            metadata={"chapter_range": chapter_range}
        )
    
    @staticmethod
    def create_timeline_event(
        event_id: str,
        event_name: str,
        description: str,
        chapter_number: int,
        involved_characters: Optional[List[str]] = None
    ) -> UnifiedDocument:
        """创建时间线事件文档"""
        return UnifiedDocument(
            doc_id=f"timeline_{event_id}",
            doc_type=DataType.TIMELINE,
            title=event_name,
            content=description,
            chapter_number=chapter_number,
            entities=involved_characters or []
        )