"""
全文搜索模块

基于SQLite FTS5实现全文搜索功能。
支持：
- 中文分词
- BM25排序
- 关键词高亮
"""

import sqlite3
import logging
import re
from typing import Optional, Any
from pathlib import Path
from dataclasses import dataclass

from ..config import SQLiteConfig

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    document: str
    score: float
    highlight: Optional[str] = None
    metadata: Optional[dict] = None


class FullTextStore:
    """
    全文搜索存储类
    
    基于SQLite FTS5实现，支持中文全文检索。
    """
    
    # FTS5表结构
    FTS_TABLE = "documents_fts"
    CONTENT_TABLE = "documents"
    
    def __init__(self, config: SQLiteConfig):
        """
        初始化全文搜索存储
        
        Args:
            config: SQLite配置
        """
        self.config = config
        self._conn: Optional[sqlite3.Connection] = None
        
        self._initialize()
    
    def _initialize(self):
        """初始化数据库和FTS5表"""
        # 确保数据库目录存在
        db_path = Path(self.config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 连接数据库
        self._conn = sqlite3.connect(
            self.config.db_path,
            check_same_thread=False  # 允许多线程访问
        )
        self._conn.row_factory = sqlite3.Row
        
        # 创建内容表（存储原始文档）
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CONTENT_TABLE} (
                id TEXT PRIMARY KEY,
                document TEXT NOT NULL,
                chapter_id TEXT,
                chunk_index INTEGER,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建FTS5虚拟表
        # 使用unicode61分词器，支持中文
        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.FTS_TABLE}
            USING fts5(
                id,
                document,
                chapter_id,
                content={self.CONTENT_TABLE},
                content_rowid=rowid,
                tokenize='{self.config.fts_tokenizer}'
            )
        """)
        
        # 创建触发器以保持FTS索引同步
        self._create_sync_triggers()
        
        # 创建索引
        self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_documents_chapter 
            ON {self.CONTENT_TABLE}(chapter_id)
        """)
        
        self._conn.commit()
        logger.info(f"全文搜索存储初始化完成: {self.config.db_path}")
    
    def _create_sync_triggers(self):
        """创建同步触发器，保持FTS索引与内容表同步"""
        # 插入触发器
        self._conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {self.CONTENT_TABLE}_ai 
            AFTER INSERT ON {self.CONTENT_TABLE}
            BEGIN
                INSERT INTO {self.FTS_TABLE}(rowid, id, document, chapter_id)
                VALUES (NEW.rowid, NEW.id, NEW.document, NEW.chapter_id);
            END
        """)
        
        # 删除触发器
        self._conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {self.CONTENT_TABLE}_ad
            AFTER DELETE ON {self.CONTENT_TABLE}
            BEGIN
                INSERT INTO {self.FTS_TABLE}({self.FTS_TABLE}, rowid, id, document, chapter_id)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.document, OLD.chapter_id);
            END
        """)
        
        # 更新触发器
        self._conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {self.CONTENT_TABLE}_au
            AFTER UPDATE ON {self.CONTENT_TABLE}
            BEGIN
                INSERT INTO {self.FTS_TABLE}({self.FTS_TABLE}, rowid, id, document, chapter_id)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.document, OLD.chapter_id);
                INSERT INTO {self.FTS_TABLE}(rowid, id, document, chapter_id)
                VALUES (NEW.rowid, NEW.id, NEW.document, NEW.chapter_id);
            END
        """)
    
    def add(
        self,
        id: str,
        document: str,
        chapter_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """
        添加文档到全文索引
        
        Args:
            id: 文档ID
            document: 文档内容
            chapter_id: 章节ID
            chunk_index: 分块索引
            metadata: 元数据
        """
        import json
        
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        try:
            self._conn.execute(f"""
                INSERT INTO {self.CONTENT_TABLE} (id, document, chapter_id, chunk_index, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (id, document, chapter_id, chunk_index, metadata_json))
            self._conn.commit()
            logger.debug(f"成功添加文档到全文索引: {id}")
        except sqlite3.IntegrityError:
            # ID已存在，执行更新
            self.update(id, document, chapter_id, chunk_index, metadata)
    
    def add_batch(
        self,
        ids: list[str],
        documents: list[str],
        chapter_ids: Optional[list[str]] = None,
        chunk_indices: Optional[list[int]] = None,
        metadatas: Optional[list[dict]] = None
    ) -> None:
        """
        批量添加文档
        
        Args:
            ids: 文档ID列表
            documents: 文档内容列表
            chapter_ids: 章节ID列表
            chunk_indices: 分块索引列表
            metadatas: 元数据列表
        """
        import json
        
        if not ids:
            return
        
        # 填充默认值
        n = len(ids)
        chapter_ids = chapter_ids or [None] * n
        chunk_indices = chunk_indices or [None] * n
        metadatas = metadatas or [None] * n
        
        data = []
        for i in range(n):
            metadata_json = json.dumps(metadatas[i], ensure_ascii=False) if metadatas[i] else None
            data.append((ids[i], documents[i], chapter_ids[i], chunk_indices[i], metadata_json))
        
        try:
            self._conn.executemany(f"""
                INSERT OR REPLACE INTO {self.CONTENT_TABLE} 
                (id, document, chapter_id, chunk_index, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, data)
            self._conn.commit()
            logger.debug(f"成功批量添加 {n} 个文档到全文索引")
        except Exception as e:
            logger.error(f"批量添加文档失败: {e}")
            self._conn.rollback()
            raise
    
    def update(
        self,
        id: str,
        document: str,
        chapter_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> bool:
        """
        更新文档
        
        Args:
            id: 文档ID
            document: 新的文档内容
            chapter_id: 章节ID
            chunk_index: 分块索引
            metadata: 元数据
        
        Returns:
            是否更新成功
        """
        import json
        
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        try:
            cursor = self._conn.execute(f"""
                UPDATE {self.CONTENT_TABLE}
                SET document = ?, chapter_id = ?, chunk_index = ?, 
                    metadata = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (document, chapter_id, chunk_index, metadata_json, id))
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            self._conn.rollback()
            raise
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        chapter_filter: Optional[list[str]] = None,
        highlight: bool = False
    ) -> list[SearchResult]:
        """
        全文搜索
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            chapter_filter: 章节过滤（只搜索指定章节）
            highlight: 是否返回高亮片段
        
        Returns:
            搜索结果列表
        """
        import json
        
        # 检查是否包含中文
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
        
        if has_chinese:
            # 对于中文，使用LIKE查询（FTS5 unicode61分词器对中文支持不好）
            return self._search_like(query, top_k, chapter_filter)
        
        # 预处理查询：转义特殊字符并添加通配符
        processed_query = self._preprocess_query(query)
        
        # 构建SQL查询
        if chapter_filter:
            placeholders = ",".join(["?"] * len(chapter_filter))
            filter_clause = f"AND c.chapter_id IN ({placeholders})"
            params = [processed_query] + chapter_filter + [top_k]
        else:
            filter_clause = ""
            params = [processed_query, top_k]
        
        # 使用BM25排序
        if highlight:
            sql = f"""
                SELECT
                    c.id,
                    c.document,
                    c.chapter_id,
                    c.metadata,
                    bm25({self.FTS_TABLE}) as score,
                    snippet({self.FTS_TABLE}, 1, '<mark>', '</mark>', '...', 32) as highlight
                FROM {self.FTS_TABLE} f
                JOIN {self.CONTENT_TABLE} c ON f.rowid = c.rowid
                WHERE {self.FTS_TABLE} MATCH ?
                {filter_clause}
                ORDER BY score
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT
                    c.id,
                    c.document,
                    c.chapter_id,
                    c.metadata,
                    bm25({self.FTS_TABLE}) as score
                FROM {self.FTS_TABLE} f
                JOIN {self.CONTENT_TABLE} c ON f.rowid = c.rowid
                WHERE {self.FTS_TABLE} MATCH ?
                {filter_clause}
                ORDER BY score
                LIMIT ?
            """
        
        try:
            cursor = self._conn.execute(sql, params)
            results = []
            
            for row in cursor:
                metadata = json.loads(row["metadata"]) if row["metadata"] else None
                result = SearchResult(
                    id=row["id"],
                    document=row["document"],
                    score=abs(row["score"]),  # BM25返回负数，取绝对值
                    highlight=row["highlight"] if highlight else None,
                    metadata=metadata
                )
                results.append(result)
            
            return results
        except sqlite3.OperationalError as e:
            # 查询语法错误时返回空结果
            logger.warning(f"全文搜索查询失败: {e}, query={query}")
            return []
    
    def _search_like(
        self,
        query: str,
        top_k: int = 5,
        chapter_filter: Optional[list[str]] = None
    ) -> list[SearchResult]:
        """
        使用LIKE进行中文搜索
        
        FTS5 unicode61分词器对中文支持不好，对中文查询使用LIKE作为备选
        """
        import json
        
        # 构建LIKE查询
        like_pattern = f"%{query}%"
        
        if chapter_filter:
            placeholders = ",".join(["?"] * len(chapter_filter))
            filter_clause = f"AND chapter_id IN ({placeholders})"
            params = [like_pattern] + chapter_filter + [top_k]
        else:
            filter_clause = ""
            params = [like_pattern, top_k]
        
        sql = f"""
            SELECT
                id,
                document,
                chapter_id,
                metadata,
                1.0 as score
            FROM {self.CONTENT_TABLE}
            WHERE document LIKE ?
            {filter_clause}
            LIMIT ?
        """
        
        try:
            cursor = self._conn.execute(sql, params)
            results = []
            
            for row in cursor:
                metadata = json.loads(row["metadata"]) if row["metadata"] else None
                result = SearchResult(
                    id=row["id"],
                    document=row["document"],
                    score=row["score"],
                    highlight=None,
                    metadata=metadata
                )
                results.append(result)
            
            return results
        except Exception as e:
            logger.warning(f"LIKE搜索失败: {e}, query={query}")
            return []
    
    def _preprocess_query(self, query: str) -> str:
        """
        预处理搜索查询
        
        将自然语言查询转换为FTS5查询语法
        """
        # 移除FTS5特殊字符
        special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+", "~"]
        processed = query
        for char in special_chars:
            processed = processed.replace(char, " ")
        
        # 去除多余空格
        processed = ' '.join(processed.split())
        
        if not processed:
            return '""'  # 空查询
        
        # FTS5 unicode61分词器会将中文按字符分词
        # 我们需要对查询中的每个字符进行搜索
        
        # 检查是否包含中文
        chinese_chars = [c for c in processed if '\u4e00' <= c <= '\u9fff']
        
        if chinese_chars:
            # 中文查询：搜索每个字符，用AND连接（要求全部匹配）
            # 使用 document: 前缀指定在document列搜索
            terms = [f'document:{c}' for c in chinese_chars]
            # 使用AND确保所有字符都匹配
            return " AND ".join(terms)
        else:
            # 英文查询：按空格分词
            words = processed.split()
            if not words:
                return f'"{processed}"'
            
            if len(words) == 1:
                return f'document:{words[0]}'
            
            terms = [f'document:{w}' for w in words if w.strip()]
            return " OR ".join(terms) if terms else f'"{processed}"'
    
    def delete(self, id: str) -> bool:
        """
        删除文档
        
        Args:
            id: 文档ID
        
        Returns:
            是否删除成功
        """
        try:
            cursor = self._conn.execute(f"""
                DELETE FROM {self.CONTENT_TABLE} WHERE id = ?
            """, (id,))
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            self._conn.rollback()
            raise
    
    def delete_by_chapter(self, chapter_id: str) -> int:
        """
        删除指定章节的所有文档
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            删除的文档数量
        """
        try:
            cursor = self._conn.execute(f"""
                DELETE FROM {self.CONTENT_TABLE} WHERE chapter_id = ?
            """, (chapter_id,))
            self._conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"删除章节文档失败: {e}")
            self._conn.rollback()
            raise
    
    def get(self, id: str) -> Optional[dict]:
        """
        根据ID获取文档
        
        Args:
            id: 文档ID
        
        Returns:
            文档信息字典，不存在则返回None
        """
        import json
        
        cursor = self._conn.execute(f"""
            SELECT * FROM {self.CONTENT_TABLE} WHERE id = ?
        """, (id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row["id"],
                "document": row["document"],
                "chapter_id": row["chapter_id"],
                "chunk_index": row["chunk_index"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None
    
    def count(self) -> int:
        """返回文档总数"""
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {self.CONTENT_TABLE}")
        return cursor.fetchone()[0]
    
    def count_by_chapter(self, chapter_id: str) -> int:
        """返回指定章节的文档数"""
        cursor = self._conn.execute(f"""
            SELECT COUNT(*) FROM {self.CONTENT_TABLE} WHERE chapter_id = ?
        """, (chapter_id,))
        return cursor.fetchone()[0]
    
    def clear(self) -> None:
        """清空所有文档"""
        try:
            self._conn.execute(f"DELETE FROM {self.CONTENT_TABLE}")
            self._conn.commit()
            logger.info("已清空全文索引")
        except Exception as e:
            logger.error(f"清空全文索引失败: {e}")
            self._conn.rollback()
            raise
    
    def rebuild_index(self) -> None:
        """重建FTS索引"""
        try:
            self._conn.execute(f"INSERT INTO {self.FTS_TABLE}({self.FTS_TABLE}) VALUES('rebuild')")
            self._conn.commit()
            logger.info("FTS索引重建完成")
        except Exception as e:
            logger.error(f"重建FTS索引失败: {e}")
            raise
    
    def optimize(self) -> None:
        """优化FTS索引"""
        try:
            self._conn.execute(f"INSERT INTO {self.FTS_TABLE}({self.FTS_TABLE}) VALUES('optimize')")
            self._conn.commit()
            logger.info("FTS索引优化完成")
        except Exception as e:
            logger.error(f"优化FTS索引失败: {e}")
            raise
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __del__(self):
        self.close()