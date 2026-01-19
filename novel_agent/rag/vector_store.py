"""
向量存储模块
使用JSON文件存储，numpy进行向量计算
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import numpy as np

from .embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: str
    text: str
    score: float
    metadata: Dict[str, Any]


@dataclass 
class Document:
    """文档"""
    doc_id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any]


class SimpleVectorStore:
    """
    简单的向量存储
    使用JSON文件持久化，numpy进行相似度计算
    """
    
    def __init__(
        self, 
        store_path: Optional[Path] = None,
        embedding_provider: Optional[EmbeddingProvider] = None
    ):
        """
        初始化向量存储
        
        Args:
            store_path: 存储文件路径
            embedding_provider: Embedding提供者
        """
        self.store_path = store_path or Path(__file__).parent.parent / "data" / "vectors.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.documents: Dict[str, Document] = {}
        self._load()
        
        logger.info(f"VectorStore initialized with {len(self.documents)} documents")
    
    def _load(self) -> None:
        """从文件加载"""
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text(encoding="utf-8"))
                for doc_id, doc_data in data.items():
                    self.documents[doc_id] = Document(**doc_data)
            except Exception as e:
                logger.warning(f"Failed to load vector store: {e}")
    
    def _save(self) -> None:
        """保存到文件"""
        data = {
            doc_id: asdict(doc) 
            for doc_id, doc in self.documents.items()
        }
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8"
        )
    
    async def add(
        self, 
        doc_id: str, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加文档
        
        Args:
            doc_id: 文档ID
            text: 文档文本
            metadata: 元数据
        """
        # 生成embedding
        embeddings = await self.embedding_provider.embed([text])
        
        self.documents[doc_id] = Document(
            doc_id=doc_id,
            text=text,
            embedding=embeddings[0],
            metadata=metadata or {}
        )
        
        self._save()
        logger.debug(f"Added document: {doc_id}")
    
    def add_sync(
        self, 
        doc_id: str, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """同步添加文档"""
        embeddings = self.embedding_provider.embed_sync([text])
        
        self.documents[doc_id] = Document(
            doc_id=doc_id,
            text=text,
            embedding=embeddings[0],
            metadata=metadata or {}
        )
        
        self._save()
    
    async def add_batch(
        self, 
        documents: List[Dict[str, Any]]
    ) -> None:
        """
        批量添加文档
        
        Args:
            documents: [{"doc_id": str, "text": str, "metadata": dict}, ...]
        """
        texts = [doc["text"] for doc in documents]
        embeddings = await self.embedding_provider.embed(texts)
        
        for i, doc in enumerate(documents):
            self.documents[doc["doc_id"]] = Document(
                doc_id=doc["doc_id"],
                text=doc["text"],
                embedding=embeddings[i],
                metadata=doc.get("metadata", {})
            )
        
        self._save()
        logger.info(f"Added {len(documents)} documents")
    
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        搜索相似文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            filter_metadata: 元数据过滤条件
            
        Returns:
            搜索结果列表
        """
        if not self.documents:
            return []
        
        # 生成查询向量
        query_embedding = await self.embedding_provider.embed([query])
        query_vec = np.array(query_embedding[0])
        
        # 计算相似度
        results = []
        for doc_id, doc in self.documents.items():
            # 元数据过滤
            if filter_metadata:
                match = all(
                    doc.metadata.get(k) == v 
                    for k, v in filter_metadata.items()
                )
                if not match:
                    continue
            
            doc_vec = np.array(doc.embedding)
            # 余弦相似度
            score = np.dot(query_vec, doc_vec) / (
                np.linalg.norm(query_vec) * np.linalg.norm(doc_vec) + 1e-8
            )
            
            results.append(SearchResult(
                doc_id=doc_id,
                text=doc.text,
                score=float(score),
                metadata=doc.metadata
            ))
        
        # 排序并返回top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def search_sync(
        self, 
        query: str, 
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """同步搜索"""
        if not self.documents:
            return []
        
        query_embedding = self.embedding_provider.embed_sync([query])
        query_vec = np.array(query_embedding[0])
        
        results = []
        for doc_id, doc in self.documents.items():
            if filter_metadata:
                match = all(
                    doc.metadata.get(k) == v 
                    for k, v in filter_metadata.items()
                )
                if not match:
                    continue
            
            doc_vec = np.array(doc.embedding)
            score = np.dot(query_vec, doc_vec) / (
                np.linalg.norm(query_vec) * np.linalg.norm(doc_vec) + 1e-8
            )
            
            results.append(SearchResult(
                doc_id=doc_id,
                text=doc.text,
                score=float(score),
                metadata=doc.metadata
            ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        if doc_id in self.documents:
            del self.documents[doc_id]
            self._save()
            return True
        return False
    
    def clear(self) -> None:
        """清空所有文档"""
        self.documents = {}
        self._save()
    
    def count(self) -> int:
        """文档数量"""
        return len(self.documents)
    
    def get(self, doc_id: str) -> Optional[Document]:
        """获取文档"""
        return self.documents.get(doc_id)


# 模块职责说明：简单向量存储，使用JSON文件持久化，numpy计算相似度，支持文档的增删查改。
