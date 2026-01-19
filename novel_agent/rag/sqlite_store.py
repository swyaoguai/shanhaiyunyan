"""
SQLite向量存储模块
使用SQLite优化向量持久化存储
"""

import os
import json
import sqlite3
import hashlib
import threading
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

import numpy as np

from ..constants import EMBEDDING_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    """向量条目"""
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]
    content_hash: str


class SQLiteVectorStore:
    """
    SQLite向量存储
    
    使用SQLite存储向量和元数据，支持：
    - 持久化存储
    - 并发访问（线程安全）
    - 高效的向量相似度搜索
    - 内容去重
    - 批量操作
    """
    
    def __init__(self, db_path: str, dimension: int = EMBEDDING_CONFIG.DEFAULT_DIMENSION):
        """
        初始化SQLite向量存储
        
        Args:
            db_path: 数据库文件路径
            dimension: 向量维度，默认1536（OpenAI ada-002）
        """
        self.db_path = db_path
        self.dimension = dimension
        self._local = threading.local()
        
        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"SQLite向量存储初始化完成: {db_path}")
    
    @contextmanager
    def _get_connection(self):
        """获取线程安全的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise
    
    def _init_db(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建向量表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT,
                    content_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_content_hash 
                ON vectors(content_hash)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON vectors(created_at)
            ''')
            
            # 创建元数据表（用于快速过滤）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata_index (
                    vector_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY (vector_id) REFERENCES vectors(id) ON DELETE CASCADE,
                    PRIMARY KEY (vector_id, key)
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_metadata_key_value 
                ON metadata_index(key, value)
            ''')
            
            conn.commit()
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    @staticmethod
    def _serialize_embedding(embedding: List[float]) -> bytes:
        """序列化向量为二进制"""
        return np.array(embedding, dtype=np.float32).tobytes()
    
    @staticmethod
    def _deserialize_embedding(data: bytes) -> List[float]:
        """反序列化二进制为向量"""
        return np.frombuffer(data, dtype=np.float32).tolist()
    
    def add(
        self, 
        content: str, 
        embedding: List[float], 
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None
    ) -> str:
        """
        添加向量
        
        Args:
            content: 文本内容
            embedding: 向量
            metadata: 元数据
            id: 可选的ID，如果不提供则自动生成
            
        Returns:
            向量ID
        """
        content_hash = self._compute_hash(content)
        vector_id = id or f"vec_{content_hash}"
        metadata = metadata or {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 插入或更新向量
            cursor.execute('''
                INSERT OR REPLACE INTO vectors 
                (id, content, embedding, metadata, content_hash, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                vector_id,
                content,
                self._serialize_embedding(embedding),
                json.dumps(metadata, ensure_ascii=False),
                content_hash
            ))
            
            # 更新元数据索引
            cursor.execute('DELETE FROM metadata_index WHERE vector_id = ?', (vector_id,))
            for key, value in metadata.items():
                if value is not None:
                    cursor.execute('''
                        INSERT INTO metadata_index (vector_id, key, value)
                        VALUES (?, ?, ?)
                    ''', (vector_id, key, str(value)))
            
            conn.commit()
        
        return vector_id
    
    def add_batch(
        self, 
        items: List[Tuple[str, List[float], Optional[Dict[str, Any]]]]
    ) -> List[str]:
        """
        批量添加向量
        
        Args:
            items: 列表，每个元素为(content, embedding, metadata)元组
            
        Returns:
            向量ID列表
        """
        ids = []
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for content, embedding, metadata in items:
                content_hash = self._compute_hash(content)
                vector_id = f"vec_{content_hash}"
                metadata = metadata or {}
                
                cursor.execute('''
                    INSERT OR REPLACE INTO vectors 
                    (id, content, embedding, metadata, content_hash, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    vector_id,
                    content,
                    self._serialize_embedding(embedding),
                    json.dumps(metadata, ensure_ascii=False),
                    content_hash
                ))
                
                cursor.execute('DELETE FROM metadata_index WHERE vector_id = ?', (vector_id,))
                for key, value in metadata.items():
                    if value is not None:
                        cursor.execute('''
                            INSERT INTO metadata_index (vector_id, key, value)
                            VALUES (?, ?, ?)
                        ''', (vector_id, key, str(value)))
                
                ids.append(vector_id)
            
            conn.commit()
        
        logger.info(f"批量添加 {len(ids)} 个向量")
        return ids
    
    def get(self, vector_id: str) -> Optional[VectorEntry]:
        """
        获取向量
        
        Args:
            vector_id: 向量ID
            
        Returns:
            VectorEntry或None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, content, embedding, metadata, content_hash
                FROM vectors WHERE id = ?
            ''', (vector_id,))
            
            row = cursor.fetchone()
            if row:
                return VectorEntry(
                    id=row['id'],
                    content=row['content'],
                    embedding=self._deserialize_embedding(row['embedding']),
                    metadata=json.loads(row['metadata'] or '{}'),
                    content_hash=row['content_hash']
                )
            return None
    
    def delete(self, vector_id: str) -> bool:
        """
        删除向量
        
        Args:
            vector_id: 向量ID
            
        Returns:
            是否删除成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM vectors WHERE id = ?', (vector_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.0
    ) -> List[Tuple[VectorEntry, float]]:
        """
        向量相似度搜索
        
        Args:
            query_embedding: 查询向量
            top_k: 返回最相似的K个结果
            filter_metadata: 元数据过滤条件
            similarity_threshold: 相似度阈值
            
        Returns:
            列表，每个元素为(VectorEntry, similarity_score)元组
        """
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        
        if query_norm == 0:
            return []
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 构建查询
            if filter_metadata:
                # 有过滤条件时，先过滤再计算
                filter_conditions = []
                filter_values = []
                for key, value in filter_metadata.items():
                    filter_conditions.append('''
                        id IN (SELECT vector_id FROM metadata_index 
                               WHERE key = ? AND value = ?)
                    ''')
                    filter_values.extend([key, str(value)])
                
                where_clause = ' AND '.join(filter_conditions)
                cursor.execute(f'''
                    SELECT id, content, embedding, metadata, content_hash
                    FROM vectors WHERE {where_clause}
                ''', filter_values)
            else:
                cursor.execute('''
                    SELECT id, content, embedding, metadata, content_hash
                    FROM vectors
                ''')
            
            results = []
            for row in cursor.fetchall():
                embedding = self._deserialize_embedding(row['embedding'])
                vec = np.array(embedding, dtype=np.float32)
                vec_norm = np.linalg.norm(vec)
                
                if vec_norm == 0:
                    continue
                
                # 计算余弦相似度
                similarity = float(np.dot(query_vec, vec) / (query_norm * vec_norm))
                
                if similarity >= similarity_threshold:
                    entry = VectorEntry(
                        id=row['id'],
                        content=row['content'],
                        embedding=embedding,
                        metadata=json.loads(row['metadata'] or '{}'),
                        content_hash=row['content_hash']
                    )
                    results.append((entry, similarity))
            
            # 排序并返回top_k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
    
    def search_by_content_hash(self, content_hash: str) -> Optional[VectorEntry]:
        """
        通过内容哈希查找向量（用于去重）
        
        Args:
            content_hash: 内容哈希
            
        Returns:
            VectorEntry或None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, content, embedding, metadata, content_hash
                FROM vectors WHERE content_hash = ?
            ''', (content_hash,))
            
            row = cursor.fetchone()
            if row:
                return VectorEntry(
                    id=row['id'],
                    content=row['content'],
                    embedding=self._deserialize_embedding(row['embedding']),
                    metadata=json.loads(row['metadata'] or '{}'),
                    content_hash=row['content_hash']
                )
            return None
    
    def exists(self, content: str) -> bool:
        """
        检查内容是否已存在
        
        Args:
            content: 文本内容
            
        Returns:
            是否存在
        """
        content_hash = self._compute_hash(content)
        return self.search_by_content_hash(content_hash) is not None
    
    def count(self, filter_metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        统计向量数量
        
        Args:
            filter_metadata: 可选的元数据过滤条件
            
        Returns:
            向量数量
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if filter_metadata:
                filter_conditions = []
                filter_values = []
                for key, value in filter_metadata.items():
                    filter_conditions.append('''
                        id IN (SELECT vector_id FROM metadata_index 
                               WHERE key = ? AND value = ?)
                    ''')
                    filter_values.extend([key, str(value)])
                
                where_clause = ' AND '.join(filter_conditions)
                cursor.execute(
                    f'SELECT COUNT(*) FROM vectors WHERE {where_clause}',
                    filter_values
                )
            else:
                cursor.execute('SELECT COUNT(*) FROM vectors')
            
            return cursor.fetchone()[0]
    
    def list_all(
        self, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[VectorEntry]:
        """
        列出所有向量
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            VectorEntry列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, content, embedding, metadata, content_hash
                FROM vectors ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                results.append(VectorEntry(
                    id=row['id'],
                    content=row['content'],
                    embedding=self._deserialize_embedding(row['embedding']),
                    metadata=json.loads(row['metadata'] or '{}'),
                    content_hash=row['content_hash']
                ))
            return results
    
    def clear(self):
        """清空所有向量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM metadata_index')
            cursor.execute('DELETE FROM vectors')
            conn.commit()
        logger.warning("已清空所有向量")
    
    def vacuum(self):
        """压缩数据库"""
        with self._get_connection() as conn:
            conn.execute('VACUUM')
        logger.info("数据库压缩完成")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            统计信息字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 向量数量
            cursor.execute('SELECT COUNT(*) FROM vectors')
            vector_count = cursor.fetchone()[0]
            
            # 数据库文件大小
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            # 唯一元数据键
            cursor.execute('SELECT DISTINCT key FROM metadata_index')
            metadata_keys = [row[0] for row in cursor.fetchall()]
            
            return {
                "vector_count": vector_count,
                "dimension": self.dimension,
                "db_path": self.db_path,
                "db_size_bytes": db_size,
                "db_size_mb": round(db_size / (1024 * 1024), 2),
                "metadata_keys": metadata_keys
            }
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class SQLiteVectorStoreManager:
    """
    SQLite向量存储管理器
    管理多个项目的向量存储
    """
    
    def __init__(self, base_dir: str):
        """
        初始化管理器
        
        Args:
            base_dir: 基础目录
        """
        self.base_dir = base_dir
        self._stores: Dict[str, SQLiteVectorStore] = {}
        self._lock = threading.Lock()
    
    def get_store(
        self, 
        project_id: str,
        dimension: int = EMBEDDING_CONFIG.DEFAULT_DIMENSION
    ) -> SQLiteVectorStore:
        """
        获取项目的向量存储
        
        Args:
            project_id: 项目ID
            dimension: 向量维度
            
        Returns:
            SQLiteVectorStore实例
        """
        with self._lock:
            if project_id not in self._stores:
                db_path = os.path.join(
                    self.base_dir, 
                    project_id, 
                    "vectors.db"
                )
                self._stores[project_id] = SQLiteVectorStore(db_path, dimension)
            return self._stores[project_id]
    
    def close_store(self, project_id: str):
        """
        关闭项目的向量存储
        
        Args:
            project_id: 项目ID
        """
        with self._lock:
            if project_id in self._stores:
                self._stores[project_id].close()
                del self._stores[project_id]
    
    def close_all(self):
        """关闭所有存储"""
        with self._lock:
            for store in self._stores.values():
                store.close()
            self._stores.clear()


# 模块职责说明：使用SQLite实现高效的向量持久化存储，支持并发访问、内容去重和批量操作。