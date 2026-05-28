"""
向量存储模块

基于ChromaDB实现向量数据的存储和检索。
支持：
- 向量的增删改查
- 元数据过滤
- 持久化存储
"""

import json
import logging
import sys
import traceback
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def _sanitize_chroma_metadata_value(value: Any) -> Any:
    """Convert metadata values to scalar types accepted by Chroma."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value), ensure_ascii=False, default=str)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _sanitize_chroma_metadatas(metadatas: Optional[list[dict]]) -> list[dict]:
    if metadatas is None:
        return []
    sanitized: list[dict] = []
    for metadata in metadatas:
        if not isinstance(metadata, dict):
            sanitized.append({})
            continue
        sanitized.append({
            str(key): _sanitize_chroma_metadata_value(value)
            for key, value in metadata.items()
        })
    return sanitized

# ChromaDB导入与状态检测
CHROMA_AVAILABLE = False
CHROMA_IMPORT_ERROR = None
chromadb = None
Settings = None  # 声明 Settings 以便在导入失败时也能引用

def _init_chromadb():
    """初始化ChromaDB模块，返回导入状态"""
    global CHROMA_AVAILABLE, CHROMA_IMPORT_ERROR, chromadb, Settings
    
    try:
        import chromadb as _chromadb
        from chromadb.config import Settings as _Settings
        
        chromadb = _chromadb
        Settings = _Settings
        CHROMA_AVAILABLE = True
        
        version = getattr(chromadb, '__version__', '未知')
        logger.info(f"✓ ChromaDB导入成功: 版本 {version}")
        print(f"[VectorStore] ✓ ChromaDB导入成功: 版本 {version}", file=sys.stderr)
        return True
        
    except ImportError as e:
        CHROMA_IMPORT_ERROR = str(e)
        error_msg = f"ChromaDB导入失败 (ImportError): {e}"
        logger.error(error_msg)
        logger.error("请运行: pip install chromadb")
        print(f"[VectorStore] ✗ {error_msg}", file=sys.stderr)
        return False
        
    except Exception as e:
        CHROMA_IMPORT_ERROR = f"{type(e).__name__}: {str(e)}"
        error_msg = f"ChromaDB初始化错误 ({type(e).__name__}): {e}"
        logger.error(error_msg)
        logger.error(f"详细堆栈:\n{traceback.format_exc()}")
        print(f"[VectorStore] ✗ {error_msg}", file=sys.stderr)
        return False

# 模块加载时立即尝试初始化
_init_chromadb()

from ..config import ChromaConfig


class VectorStore:
    """
    向量存储类
    
    封装ChromaDB，提供向量存储和检索功能。
    """
    
    def __init__(self, config: ChromaConfig):
        """
        初始化向量存储
        
        Args:
            config: ChromaDB配置
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("chromadb未安装，请运行: pip install chromadb")
        
        self.config = config
        self._client: Optional[chromadb.Client] = None
        self._collection: Optional[chromadb.Collection] = None
        
        self._initialize()
    
    def _initialize(self):
        """初始化ChromaDB客户端和集合"""
        # 确保持久化目录存在
        persist_path = Path(self.config.persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)
        
        # 创建持久化客户端
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # 获取或创建集合
        # 根据距离度量选择相似度函数
        distance_fn = {
            "cosine": "cosine",
            "l2": "l2", 
            "ip": "ip"  # inner product
        }.get(self.config.distance_metric, "cosine")
        
        self._collection = self._client.get_or_create_collection(
            name=self.config.collection_name,
            metadata={"hnsw:space": distance_fn}
        )
        
        logger.info(f"向量存储初始化完成: {self.config.collection_name}, "
                   f"当前文档数: {self._collection.count()}")
    
    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: Optional[list[dict]] = None
    ) -> None:
        """
        添加向量到存储
        
        Args:
            ids: 文档ID列表
            embeddings: 向量列表
            documents: 原始文档文本列表
            metadatas: 元数据列表（可选）
        """
        if not ids:
            logger.warning("添加向量时ID列表为空")
            return
        
        # 确保元数据列表长度匹配
        if metadatas is None:
            metadatas = [{}] * len(ids)
        metadatas = _sanitize_chroma_metadatas(metadatas)
        
        try:
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.debug(f"成功添加 {len(ids)} 个向量")
        except Exception as e:
            logger.error(f"添加向量失败: {e}")
            raise
    
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: Optional[list[dict]] = None
    ) -> None:
        """
        更新或插入向量（存在则更新，不存在则插入）
        
        Args:
            ids: 文档ID列表
            embeddings: 向量列表
            documents: 原始文档文本列表
            metadatas: 元数据列表（可选）
        """
        if not ids:
            return
        
        if metadatas is None:
            metadatas = [{}] * len(ids)
        metadatas = _sanitize_chroma_metadatas(metadatas)
        
        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.debug(f"成功upsert {len(ids)} 个向量")
        except Exception as e:
            logger.error(f"upsert向量失败: {e}")
            raise
    
    def query(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
        include: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        向量相似度查询
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件
            include: 返回字段，可选 ["documents", "metadatas", "distances", "embeddings"]
        
        Returns:
            查询结果字典，包含ids, documents, metadatas, distances等
        """
        if include is None:
            include = ["documents", "metadatas", "distances"]
        
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                where_document=where_document,
                include=include
            )
            
            # 展平结果（因为我们只查询一个向量）
            return {
                "ids": results["ids"][0] if results["ids"] else [],
                "documents": results["documents"][0] if results.get("documents") else [],
                "metadatas": results["metadatas"][0] if results.get("metadatas") else [],
                "distances": results["distances"][0] if results.get("distances") else [],
            }
        except Exception as e:
            logger.error(f"向量查询失败: {e}")
            raise
    
    def get(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None,
        limit: Optional[int] = None,
        include: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        根据ID或条件获取向量
        
        Args:
            ids: 文档ID列表
            where: 元数据过滤条件
            limit: 返回数量限制
            include: 返回字段
        
        Returns:
            获取结果字典
        """
        if include is None:
            include = ["documents", "metadatas"]
        
        try:
            results = self._collection.get(
                ids=ids,
                where=where,
                limit=limit,
                include=include
            )
            return results
        except Exception as e:
            logger.error(f"获取向量失败: {e}")
            raise
    
    def delete(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None
    ) -> None:
        """
        删除向量
        
        Args:
            ids: 要删除的文档ID列表
            where: 元数据过滤条件（满足条件的将被删除）
        """
        try:
            self._collection.delete(ids=ids, where=where)
            logger.debug(f"成功删除向量: ids={ids}, where={where}")
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            raise
    
    def count(self) -> int:
        """返回存储的向量总数"""
        return self._collection.count()
    
    def clear(self) -> None:
        """清空所有向量"""
        try:
            # 删除并重新创建集合
            self._client.delete_collection(self.config.collection_name)
            self._collection = self._client.create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": self.config.distance_metric}
            )
            logger.info(f"已清空向量存储: {self.config.collection_name}")
        except Exception as e:
            logger.error(f"清空向量存储失败: {e}")
            raise
    
    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        return {
            "name": self.config.collection_name,
            "count": self.count(),
            "persist_directory": self.config.persist_directory,
            "distance_metric": self.config.distance_metric,
        }

    def close(self) -> None:
        """关闭 ChromaDB 客户端，释放 SQLite 文件句柄。"""
        self._collection = None
        if self._client is None:
            return
        try:
            identifier = getattr(self._client, "_identifier", None)
            try:
                system = getattr(self._client, "_system", None)
                stop = getattr(system, "stop", None)
                if callable(stop):
                    stop()
            except Exception as exc:
                logger.debug(f"停止 ChromaDB 系统失败: {exc}")

            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            if identifier:
                try:
                    from chromadb.api.shared_system_client import SharedSystemClient

                    SharedSystemClient._identifier_to_system.pop(identifier, None)
                except Exception as exc:
                    logger.debug(f"清理 ChromaDB 系统缓存失败: {exc}")
        finally:
            self._client = None


class MockVectorStore:
    """
    模拟向量存储类
    
    用于测试环境，不依赖ChromaDB。
    使用内存存储和简单的距离计算实现向量检索。
    """
    
    def __init__(self, config: ChromaConfig = None):
        """
        初始化模拟向量存储
        
        Args:
            config: ChromaDB配置（可选）
        """
        self.config = config or ChromaConfig()
        self._data: dict[str, dict] = {}
        logger.info("模拟向量存储初始化完成")
    
    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: Optional[list[dict]] = None
    ) -> None:
        """添加向量到存储"""
        if not ids:
            return
        
        if metadatas is None:
            metadatas = [{}] * len(ids)
        metadatas = _sanitize_chroma_metadatas(metadatas)

        for i, doc_id in enumerate(ids):
            self._data[doc_id] = {
                "embedding": embeddings[i],
                "document": documents[i],
                "metadata": metadatas[i]
            }
        logger.debug(f"Mock: 成功添加 {len(ids)} 个向量")
    
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: Optional[list[dict]] = None
    ) -> None:
        """更新或插入向量"""
        self.add(ids, embeddings, documents, metadatas)
    
    def query(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
        include: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """向量相似度查询"""
        if not self._data:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        
        # 计算余弦相似度
        results = []
        for doc_id, data in self._data.items():
            # 应用元数据过滤
            if where:
                match = True
                for key, value in where.items():
                    if data["metadata"].get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            # 计算距离（余弦距离 = 1 - 余弦相似度）
            distance = self._cosine_distance(query_embedding, data["embedding"])
            results.append((doc_id, data, distance))
        
        # 按距离排序并取top_k
        results.sort(key=lambda x: x[2])
        results = results[:top_k]
        
        return {
            "ids": [r[0] for r in results],
            "documents": [r[1]["document"] for r in results],
            "metadatas": [r[1]["metadata"] for r in results],
            "distances": [r[2] for r in results],
        }
    
    def _cosine_distance(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦距离"""
        import math
        
        if len(vec1) != len(vec2):
            return 1.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 1.0
        
        similarity = dot_product / (norm1 * norm2)
        return 1.0 - similarity
    
    def get(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None,
        limit: Optional[int] = None,
        include: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """根据ID或条件获取向量"""
        results = {"ids": [], "documents": [], "metadatas": []}
        
        for doc_id, data in self._data.items():
            if ids and doc_id not in ids:
                continue
            
            if where:
                match = True
                for key, value in where.items():
                    if data["metadata"].get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            results["ids"].append(doc_id)
            results["documents"].append(data["document"])
            results["metadatas"].append(data["metadata"])
            
            if limit and len(results["ids"]) >= limit:
                break
        
        return results
    
    def delete(
        self,
        ids: Optional[list[str]] = None,
        where: Optional[dict] = None
    ) -> None:
        """删除向量"""
        if ids:
            for doc_id in ids:
                self._data.pop(doc_id, None)
        
        if where:
            to_delete = []
            for doc_id, data in self._data.items():
                match = True
                for key, value in where.items():
                    if data["metadata"].get(key) != value:
                        match = False
                        break
                if match:
                    to_delete.append(doc_id)
            
            for doc_id in to_delete:
                del self._data[doc_id]
    
    def count(self) -> int:
        """返回存储的向量总数"""
        return len(self._data)
    
    def clear(self) -> None:
        """清空所有向量"""
        self._data.clear()
        logger.info("Mock: 已清空向量存储")
    
    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        return {
            "name": "mock_collection",
            "count": self.count(),
            "persist_directory": "memory",
            "distance_metric": "cosine",
        }

    def close(self) -> None:
        """释放模拟存储资源。"""
        self._data.clear()
