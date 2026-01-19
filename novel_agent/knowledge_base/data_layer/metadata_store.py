"""
元数据存储模块

基于SQLite存储章节和文档的元数据信息。
支持：
- 章节信息管理
- 时间戳记录
- 版本控制（基础）
"""

import sqlite3
import logging
import json
from typing import Optional, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

from ..config import SQLiteConfig

logger = logging.getLogger(__name__)


@dataclass
class ChapterInfo:
    """章节信息"""
    chapter_id: str
    title: str
    chapter_number: Optional[int] = None
    word_count: int = 0
    chunk_count: int = 0
    summary: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class MetadataStore:
    """
    元数据存储类
    
    管理章节和文档的元数据信息。
    """
    
    CHAPTERS_TABLE = "chapters"
    CHUNKS_TABLE = "chunks"
    
    def __init__(self, config: SQLiteConfig):
        """
        初始化元数据存储
        
        Args:
            config: SQLite配置
        """
        self.config = config
        self._conn: Optional[sqlite3.Connection] = None
        
        self._initialize()
    
    def _initialize(self):
        """初始化数据库表"""
        # 确保数据库目录存在
        db_path = Path(self.config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 连接数据库
        self._conn = sqlite3.connect(
            self.config.db_path,
            check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        
        # 创建章节表
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CHAPTERS_TABLE} (
                chapter_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                chapter_number INTEGER,
                word_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                summary TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建分块元数据表
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.CHUNKS_TABLE} (
                chunk_id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_pos INTEGER,
                end_pos INTEGER,
                word_count INTEGER DEFAULT 0,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chapter_id) REFERENCES {self.CHAPTERS_TABLE}(chapter_id)
                    ON DELETE CASCADE
            )
        """)
        
        # 创建索引
        self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_chunks_chapter
            ON {self.CHUNKS_TABLE}(chapter_id)
        """)
        
        self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_chapters_number
            ON {self.CHAPTERS_TABLE}(chapter_number)
        """)
        
        self._conn.commit()
        logger.info(f"元数据存储初始化完成: {self.config.db_path}")
    
    # ==================== 章节管理 ====================
    
    def add_chapter(
        self,
        chapter_id: str,
        title: str,
        chapter_number: Optional[int] = None,
        word_count: int = 0,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> ChapterInfo:
        """
        添加章节
        
        Args:
            chapter_id: 章节ID
            title: 章节标题
            chapter_number: 章节序号
            word_count: 字数
            summary: 摘要
            metadata: 其他元数据
        
        Returns:
            章节信息
        """
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        now = datetime.now().isoformat()
        
        try:
            self._conn.execute(f"""
                INSERT INTO {self.CHAPTERS_TABLE} 
                (chapter_id, title, chapter_number, word_count, summary, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (chapter_id, title, chapter_number, word_count, summary, metadata_json, now, now))
            self._conn.commit()
            
            return ChapterInfo(
                chapter_id=chapter_id,
                title=title,
                chapter_number=chapter_number,
                word_count=word_count,
                chunk_count=0,
                summary=summary,
                created_at=now,
                updated_at=now,
                metadata=metadata
            )
        except sqlite3.IntegrityError:
            # 已存在则更新
            return self.update_chapter(
                chapter_id, title, chapter_number, word_count, summary, metadata
            )
    
    def update_chapter(
        self,
        chapter_id: str,
        title: Optional[str] = None,
        chapter_number: Optional[int] = None,
        word_count: Optional[int] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Optional[ChapterInfo]:
        """
        更新章节信息
        
        Args:
            chapter_id: 章节ID
            title: 章节标题
            chapter_number: 章节序号
            word_count: 字数
            summary: 摘要
            metadata: 其他元数据
        
        Returns:
            更新后的章节信息，不存在则返回None
        """
        # 先获取现有数据
        existing = self.get_chapter(chapter_id)
        if not existing:
            return None
        
        # 合并更新
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if chapter_number is not None:
            updates.append("chapter_number = ?")
            params.append(chapter_number)
        if word_count is not None:
            updates.append("word_count = ?")
            params.append(word_count)
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(chapter_id)
        
        try:
            self._conn.execute(f"""
                UPDATE {self.CHAPTERS_TABLE}
                SET {", ".join(updates)}
                WHERE chapter_id = ?
            """, params)
            self._conn.commit()
            
            return self.get_chapter(chapter_id)
        except Exception as e:
            logger.error(f"更新章节失败: {e}")
            self._conn.rollback()
            raise
    
    def get_chapter(self, chapter_id: str) -> Optional[ChapterInfo]:
        """
        获取章节信息
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节信息，不存在则返回None
        """
        cursor = self._conn.execute(f"""
            SELECT * FROM {self.CHAPTERS_TABLE} WHERE chapter_id = ?
        """, (chapter_id,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_chapter(row)
        return None
    
    def get_chapter_by_number(self, chapter_number: int) -> Optional[ChapterInfo]:
        """
        根据章节序号获取章节
        
        Args:
            chapter_number: 章节序号
        
        Returns:
            章节信息
        """
        cursor = self._conn.execute(f"""
            SELECT * FROM {self.CHAPTERS_TABLE} WHERE chapter_number = ?
        """, (chapter_number,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_chapter(row)
        return None
    
    def list_chapters(
        self,
        order_by: str = "chapter_number",
        ascending: bool = True,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[ChapterInfo]:
        """
        列出所有章节
        
        Args:
            order_by: 排序字段
            ascending: 是否升序
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            章节列表
        """
        order = "ASC" if ascending else "DESC"
        
        sql = f"""
            SELECT * FROM {self.CHAPTERS_TABLE}
            ORDER BY {order_by} {order}
        """
        
        if limit:
            sql += f" LIMIT {limit} OFFSET {offset}"
        
        cursor = self._conn.execute(sql)
        return [self._row_to_chapter(row) for row in cursor]
    
    def delete_chapter(self, chapter_id: str) -> bool:
        """
        删除章节
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            是否删除成功
        """
        try:
            cursor = self._conn.execute(f"""
                DELETE FROM {self.CHAPTERS_TABLE} WHERE chapter_id = ?
            """, (chapter_id,))
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除章节失败: {e}")
            self._conn.rollback()
            raise
    
    def count_chapters(self) -> int:
        """返回章节总数"""
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {self.CHAPTERS_TABLE}")
        return cursor.fetchone()[0]
    
    def _row_to_chapter(self, row: sqlite3.Row) -> ChapterInfo:
        """将数据库行转换为ChapterInfo"""
        metadata = json.loads(row["metadata"]) if row["metadata"] else None
        return ChapterInfo(
            chapter_id=row["chapter_id"],
            title=row["title"],
            chapter_number=row["chapter_number"],
            word_count=row["word_count"],
            chunk_count=row["chunk_count"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata
        )
    
    # ==================== 分块管理 ====================
    
    def add_chunk(
        self,
        chunk_id: str,
        chapter_id: str,
        chunk_index: int,
        start_pos: Optional[int] = None,
        end_pos: Optional[int] = None,
        word_count: int = 0,
        metadata: Optional[dict] = None
    ) -> None:
        """
        添加分块元数据
        
        Args:
            chunk_id: 分块ID
            chapter_id: 所属章节ID
            chunk_index: 分块索引
            start_pos: 在原文中的起始位置
            end_pos: 在原文中的结束位置
            word_count: 字数
            metadata: 其他元数据
        """
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        try:
            self._conn.execute(f"""
                INSERT OR REPLACE INTO {self.CHUNKS_TABLE}
                (chunk_id, chapter_id, chunk_index, start_pos, end_pos, word_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (chunk_id, chapter_id, chunk_index, start_pos, end_pos, word_count, metadata_json))
            self._conn.commit()
        except Exception as e:
            logger.error(f"添加分块元数据失败: {e}")
            self._conn.rollback()
            raise
    
    def add_chunks_batch(
        self,
        chunks: list[dict]
    ) -> None:
        """
        批量添加分块元数据
        
        Args:
            chunks: 分块信息列表，每个字典包含 chunk_id, chapter_id, chunk_index 等字段
        """
        data = []
        for chunk in chunks:
            metadata_json = json.dumps(chunk.get("metadata"), ensure_ascii=False) if chunk.get("metadata") else None
            data.append((
                chunk["chunk_id"],
                chunk["chapter_id"],
                chunk["chunk_index"],
                chunk.get("start_pos"),
                chunk.get("end_pos"),
                chunk.get("word_count", 0),
                metadata_json
            ))
        
        try:
            self._conn.executemany(f"""
                INSERT OR REPLACE INTO {self.CHUNKS_TABLE}
                (chunk_id, chapter_id, chunk_index, start_pos, end_pos, word_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, data)
            self._conn.commit()
        except Exception as e:
            logger.error(f"批量添加分块元数据失败: {e}")
            self._conn.rollback()
            raise
    
    def get_chunks_by_chapter(self, chapter_id: str) -> list[dict]:
        """
        获取章节的所有分块
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            分块信息列表
        """
        cursor = self._conn.execute(f"""
            SELECT * FROM {self.CHUNKS_TABLE}
            WHERE chapter_id = ?
            ORDER BY chunk_index
        """, (chapter_id,))
        
        results = []
        for row in cursor:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
            results.append({
                "chunk_id": row["chunk_id"],
                "chapter_id": row["chapter_id"],
                "chunk_index": row["chunk_index"],
                "start_pos": row["start_pos"],
                "end_pos": row["end_pos"],
                "word_count": row["word_count"],
                "metadata": metadata,
                "created_at": row["created_at"],
            })
        return results
    
    def delete_chunks_by_chapter(self, chapter_id: str) -> int:
        """
        删除章节的所有分块
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            删除的分块数量
        """
        try:
            cursor = self._conn.execute(f"""
                DELETE FROM {self.CHUNKS_TABLE} WHERE chapter_id = ?
            """, (chapter_id,))
            self._conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"删除分块失败: {e}")
            self._conn.rollback()
            raise
    
    def update_chapter_chunk_count(self, chapter_id: str, chunk_count: int) -> None:
        """
        更新章节的分块数量
        
        Args:
            chapter_id: 章节ID
            chunk_count: 分块数量
        """
        try:
            self._conn.execute(f"""
                UPDATE {self.CHAPTERS_TABLE}
                SET chunk_count = ?, updated_at = ?
                WHERE chapter_id = ?
            """, (chunk_count, datetime.now().isoformat(), chapter_id))
            self._conn.commit()
        except Exception as e:
            logger.error(f"更新章节分块数量失败: {e}")
            self._conn.rollback()
            raise
    
    # ==================== 统计与工具 ====================
    
    def get_statistics(self) -> dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        chapter_count = self.count_chapters()
        
        # 总字数
        cursor = self._conn.execute(f"""
            SELECT COALESCE(SUM(word_count), 0) FROM {self.CHAPTERS_TABLE}
        """)
        total_words = cursor.fetchone()[0]
        
        # 总分块数
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {self.CHUNKS_TABLE}")
        total_chunks = cursor.fetchone()[0]
        
        return {
            "chapter_count": chapter_count,
            "total_words": total_words,
            "total_chunks": total_chunks,
        }
    
    def clear(self) -> None:
        """清空所有数据"""
        try:
            self._conn.execute(f"DELETE FROM {self.CHUNKS_TABLE}")
            self._conn.execute(f"DELETE FROM {self.CHAPTERS_TABLE}")
            self._conn.commit()
            logger.info("已清空元数据存储")
        except Exception as e:
            logger.error(f"清空元数据存储失败: {e}")
            self._conn.rollback()
            raise
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __del__(self):
        self.close()