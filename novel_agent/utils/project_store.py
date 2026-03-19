"""
项目元数据存储模块

使用SQLite存储项目元数据，替代JSON文件存储。
提供事务支持、索引查询和并发安全。

模块职责说明：管理项目元数据的持久化存储，支持CRUD操作。
"""

import json
import sqlite3
import logging
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager


logger = logging.getLogger(__name__)


@dataclass
class ProjectMeta:
    """项目元数据"""
    id: str
    name: str
    description: str = ""
    novel_type: str = ""
    status: str = "planning"  # planning/writing/completed/paused/failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    word_count: int = 0
    chapter_count: int = 0
    completed_chapters: int = 0
    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectMeta':
        """从字典创建"""
        return cls(**data)

    def update(self, **kwargs) -> None:
        """更新字段"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()


class ProjectStore:
    """
    项目元数据存储

    使用SQLite提供：
    - 事务支持
    - 索引查询
    - 并发安全（线程级）
    - 原子写入
    """

    # 表结构版本（用于迁移）
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        """
        初始化存储

        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

        logger.info(f"ProjectStore initialized: {db_path}")

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

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 项目元数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    novel_type TEXT DEFAULT '',
                    status TEXT DEFAULT 'planning',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    word_count INTEGER DEFAULT 0,
                    chapter_count INTEGER DEFAULT 0,
                    completed_chapters INTEGER DEFAULT 0,
                    settings TEXT DEFAULT '{}'
                )
            ''')

            # 索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_projects_status
                ON projects(status)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_projects_updated_at
                ON projects(updated_at)
            ''')

            # 元数据表（存储版本等信息）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # 记录schema版本
            cursor.execute('''
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES ('schema_version', ?)
            ''', (str(self.SCHEMA_VERSION),))

            conn.commit()

    def create(self, project: ProjectMeta) -> ProjectMeta:
        """
        创建项目

        Args:
            project: 项目元数据

        Returns:
            创建的项目
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO projects (
                    id, name, description, novel_type, status,
                    created_at, updated_at, word_count, chapter_count,
                    completed_chapters, settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project.id, project.name, project.description,
                project.novel_type, project.status, project.created_at,
                project.updated_at, project.word_count, project.chapter_count,
                project.completed_chapters, json.dumps(project.settings)
            ))
            conn.commit()

        logger.info(f"Project created: {project.id}")
        return project

    def get(self, project_id: str) -> Optional[ProjectMeta]:
        """
        获取项目

        Args:
            project_id: 项目ID

        Returns:
            项目元数据，不存在则返回None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_project(row)
            return None

    def update(self, project_id: str, **kwargs) -> Optional[ProjectMeta]:
        """
        更新项目

        Args:
            project_id: 项目ID
            **kwargs: 要更新的字段

        Returns:
            更新后的项目，不存在则返回None
        """
        project = self.get(project_id)
        if not project:
            return None

        project.update(**kwargs)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE projects SET
                    name = ?, description = ?, novel_type = ?, status = ?,
                    updated_at = ?, word_count = ?, chapter_count = ?,
                    completed_chapters = ?, settings = ?
                WHERE id = ?
            ''', (
                project.name, project.description, project.novel_type,
                project.status, project.updated_at, project.word_count,
                project.chapter_count, project.completed_chapters,
                json.dumps(project.settings), project_id
            ))
            conn.commit()

        logger.debug(f"Project updated: {project_id}")
        return project

    def delete(self, project_id: str) -> bool:
        """
        删除项目

        Args:
            project_id: 项目ID

        Returns:
            是否删除成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()
            success = cursor.rowcount > 0

        if success:
            logger.info(f"Project deleted: {project_id}")
        return success

    def list_all(self, status: Optional[str] = None) -> List[ProjectMeta]:
        """
        列出所有项目

        Args:
            status: 可选的状态过滤

        Returns:
            项目列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    'SELECT * FROM projects WHERE status = ? ORDER BY updated_at DESC',
                    (status,)
                )
            else:
                cursor.execute('SELECT * FROM projects ORDER BY updated_at DESC')

            rows = cursor.fetchall()
            return [self._row_to_project(row) for row in rows]

    def count(self, status: Optional[str] = None) -> int:
        """
        统计项目数量

        Args:
            status: 可选的状态过滤

        Returns:
            项目数量
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    'SELECT COUNT(*) FROM projects WHERE status = ?',
                    (status,)
                )
            else:
                cursor.execute('SELECT COUNT(*) FROM projects')

            return cursor.fetchone()[0]

    def _row_to_project(self, row: sqlite3.Row) -> ProjectMeta:
        """将数据库行转换为ProjectMeta"""
        settings = {}
        try:
            settings = json.loads(row['settings'])
        except (json.JSONDecodeError, TypeError):
            pass

        return ProjectMeta(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            novel_type=row['novel_type'],
            status=row['status'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            word_count=row['word_count'],
            chapter_count=row['chapter_count'],
            completed_chapters=row['completed_chapters'],
            settings=settings
        )

    def close(self) -> None:
        """关闭连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def migrate_from_json(self, json_dir: str) -> int:
        """
        从JSON文件迁移数据

        Args:
            json_dir: JSON文件目录

        Returns:
            迁移的项目数量
        """
        json_path = Path(json_dir)
        if not json_path.exists():
            return 0

        migrated = 0
        for project_file in json_path.glob("*/project.json"):
            try:
                data = json.loads(project_file.read_text(encoding="utf-8"))
                project = ProjectMeta.from_dict(data)
                self.create(project)
                migrated += 1
                logger.info(f"Migrated project: {project.id}")
            except Exception as e:
                logger.warning(f"Failed to migrate {project_file}: {e}")

        return migrated


# 全局实例
_project_store: Optional[ProjectStore] = None
_store_lock = threading.Lock()


def get_project_store(db_path: Optional[str] = None) -> ProjectStore:
    """
    获取全局项目存储实例

    Args:
        db_path: 数据库路径，默认为 data/projects.db

    Returns:
        ProjectStore实例
    """
    global _project_store

    with _store_lock:
        if _project_store is None:
            if db_path is None:
                from ..constants import PATH_DEFAULTS
                db_path = str(Path(PATH_DEFAULTS.DATA_DIR) / "projects.db")
            _project_store = ProjectStore(db_path)
        return _project_store
