"""
Token消耗统计模块

提供SQLite持久化存储，支持按时间、模型等维度查询token消耗数据。
包含每日/每周统计、24小时曲线图数据、模型筛选等功能。
"""

import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

from ..constants import PATH_DEFAULTS

logger = logging.getLogger(__name__)


def estimate_tokens_from_text(value: Any) -> int:
    """Best-effort token estimate for providers that omit usage metadata."""
    text = str(value or "")
    if not text.strip():
        return 0

    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = max(0, len(text) - cjk_chars)
    estimated = int((cjk_chars * 0.8) + (other_chars / 4))
    return max(1, estimated)


def estimate_tokens_from_messages(messages: Any) -> int:
    """Estimate token count from OpenAI-style message payloads."""
    if not isinstance(messages, list):
        return estimate_tokens_from_text(messages)

    total = 0
    for message in messages:
        if isinstance(message, dict):
            total += estimate_tokens_from_text(message.get("role"))
            total += estimate_tokens_from_text(message.get("content"))
            total += 4
        else:
            total += estimate_tokens_from_text(message)
    return total


def _coerce_token_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _usage_to_dict(usage: Any) -> Dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        try:
            dumped = usage.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(usage, "dict"):
        try:
            dumped = usage.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {}


def _usage_field(usage: Any, *names: str) -> int:
    usage_dict = _usage_to_dict(usage)
    for name in names:
        value = usage_dict.get(name) if usage_dict else None
        if value is None and usage is not None:
            value = getattr(usage, name, None)
        parsed = _coerce_token_int(value)
        if parsed:
            return parsed
    return 0


def extract_token_usage(
    usage: Any,
    *,
    fallback_tokens_in: int = 0,
    fallback_tokens_out: int = 0,
) -> tuple[int, int]:
    """
    Extract provider-reported token usage with a safe estimate fallback.

    OpenAI-compatible providers are inconsistent here: some return SDK objects,
    some return plain dicts, Chat uses prompt/completion fields, Responses and
    Anthropic use input/output fields, and a few only expose total_tokens.
    """
    fallback_in = _coerce_token_int(fallback_tokens_in)
    fallback_out = _coerce_token_int(fallback_tokens_out)

    reported_tokens_in = _usage_field(usage, "prompt_tokens", "input_tokens", "input")
    reported_tokens_out = _usage_field(usage, "completion_tokens", "output_tokens", "output")
    tokens_in = reported_tokens_in
    tokens_out = reported_tokens_out
    total_tokens = _usage_field(usage, "total_tokens", "total")

    if not tokens_in:
        tokens_in = fallback_in
    if not tokens_out:
        tokens_out = fallback_out

    if total_tokens and not (reported_tokens_in and reported_tokens_out):
        if reported_tokens_in and total_tokens >= reported_tokens_in:
            tokens_out = total_tokens - reported_tokens_in
        elif reported_tokens_out and total_tokens >= reported_tokens_out:
            tokens_in = total_tokens - reported_tokens_out
        elif fallback_in and total_tokens >= fallback_in:
            tokens_in = fallback_in
            tokens_out = total_tokens - fallback_in
        elif fallback_out and total_tokens >= fallback_out:
            tokens_in = total_tokens - fallback_out
            tokens_out = fallback_out
        else:
            tokens_in = total_tokens
            tokens_out = 0

    return tokens_in, tokens_out


@dataclass
class TokenUsageRecord:
    """Token使用记录"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    project_id: str = ""
    agent_name: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0
    success: bool = True
    method: str = ""
    duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "project_id": self.project_id,
            "agent_name": self.agent_name,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
            "success": self.success,
            "method": self.method,
            "duration": self.duration
        }


class TokenStatsStore:
    """
    Token统计存储
    
    使用SQLite持久化存储token消耗数据，支持多维度查询。
    线程安全设计，支持并发访问。
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化Token统计存储
        
        Args:
            db_path: 数据库文件路径，默认使用 PATH_DEFAULTS.STATS_DIR/token_stats.db
        """
        if db_path is None:
            stats_dir = Path(PATH_DEFAULTS.STATS_DIR)
            stats_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(stats_dir / "token_stats.db")
        
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
        
        logger.info(f"TokenStatsStore initialized: {db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地的数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def _get_cursor(self):
        """获取数据库游标的上下文管理器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_cursor() as cursor:
            # 创建token使用记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    project_id TEXT NOT NULL DEFAULT '',
                    agent_name TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    method TEXT DEFAULT '',
                    duration REAL DEFAULT 0.0
                )
            ''')

            cursor.execute('PRAGMA table_info(token_usage)')
            columns = {row["name"] for row in cursor.fetchall()}
            if "project_id" not in columns:
                cursor.execute(
                    "ALTER TABLE token_usage "
                    "ADD COLUMN project_id TEXT NOT NULL DEFAULT ''"
                )
                current_project_id = _get_current_project_id()
                if current_project_id:
                    cursor.execute(
                        "UPDATE token_usage SET project_id = ? WHERE project_id = ''",
                        (current_project_id,),
                    )
                    logger.info(
                        "Backfilled legacy token usage records to project_id=%s",
                        current_project_id,
                    )
            
            # 创建索引以加速查询
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp 
                ON token_usage(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_token_usage_model 
                ON token_usage(model)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_token_usage_agent 
                ON token_usage(agent_name)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_token_usage_project
                ON token_usage(project_id)
            ''')
            
            logger.info("Database tables initialized")
    
    def record(
        self,
        agent_name: str,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        success: bool = True,
        method: str = "",
        duration: float = 0.0,
        project_id: str = ""
    ) -> int:
        """
        记录一次token使用
        
        Args:
            agent_name: Agent名称
            model: 模型名称
            tokens_in: 输入token数
            tokens_out: 输出token数
            success: 是否成功
            method: 调用方法
            duration: 耗时(秒)
            project_id: 项目ID
            
        Returns:
            记录ID
        """
        total_tokens = tokens_in + tokens_out
        
        with self._get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO token_usage 
                (timestamp, project_id, agent_name, model, tokens_in, tokens_out, total_tokens, success, method, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                project_id or "",
                agent_name,
                model,
                tokens_in,
                tokens_out,
                total_tokens,
                1 if success else 0,
                method,
                duration
            ))
            
            record_id = cursor.lastrowid
            logger.debug(f"Recorded token usage: {agent_name}, {model}, {total_tokens} tokens")
            return record_id
    
    def get_daily_stats(
        self,
        days: int = 7,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取每日统计数据
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            每日统计列表
        """
        start_date = datetime.now() - timedelta(days=days)
        
        query = '''
            SELECT 
                DATE(timestamp) as date,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(duration) as avg_duration
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_date]
        
        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += ' GROUP BY DATE(timestamp) ORDER BY date DESC'
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "date": row["date"],
                "tokens_in": row["total_tokens_in"] or 0,
                "tokens_out": row["total_tokens_out"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "call_count": row["call_count"] or 0,
                "success_count": row["success_count"] or 0,
                "success_rate": (row["success_count"] / row["call_count"] * 100) if row["call_count"] > 0 else 0,
                "avg_duration": round(row["avg_duration"] or 0, 2)
            } for row in rows]
    
    def get_weekly_stats(
        self,
        weeks: int = 4,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取每周统计数据
        
        Args:
            weeks: 统计周数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            每周统计列表
        """
        start_date = datetime.now() - timedelta(weeks=weeks)
        
        query = '''
            SELECT 
                strftime('%Y-W%W', timestamp) as week,
                MIN(DATE(timestamp)) as week_start,
                MAX(DATE(timestamp)) as week_end,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(duration) as avg_duration
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_date]
        
        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += " GROUP BY strftime('%Y-W%W', timestamp) ORDER BY week DESC"
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "week": row["week"],
                "week_start": row["week_start"],
                "week_end": row["week_end"],
                "tokens_in": row["total_tokens_in"] or 0,
                "tokens_out": row["total_tokens_out"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "call_count": row["call_count"] or 0,
                "success_count": row["success_count"] or 0,
                "success_rate": (row["success_count"] / row["call_count"] * 100) if row["call_count"] > 0 else 0,
                "avg_duration": round(row["avg_duration"] or 0, 2)
            } for row in rows]
    
    def get_hourly_stats(
        self,
        hours: int = 24,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取小时统计数据（用于24小时曲线图）
        
        Args:
            hours: 统计小时数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            每小时统计列表
        """
        start_time = datetime.now() - timedelta(hours=hours)
        
        query = '''
            SELECT 
                strftime('%Y-%m-%d %H:00', timestamp) as hour,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_time]
        
        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += " GROUP BY strftime('%Y-%m-%d %H', timestamp) ORDER BY hour ASC"
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 填充缺失的小时数据
            result = []
            existing_hours = {row["hour"]: row for row in rows}
            
            current = start_time.replace(minute=0, second=0, microsecond=0)
            end = datetime.now().replace(minute=0, second=0, microsecond=0)
            
            while current <= end:
                hour_key = current.strftime('%Y-%m-%d %H:00')
                if hour_key in existing_hours:
                    row = existing_hours[hour_key]
                    result.append({
                        "hour": hour_key,
                        "tokens_in": row["total_tokens_in"] or 0,
                        "tokens_out": row["total_tokens_out"] or 0,
                        "total_tokens": row["total_tokens"] or 0,
                        "call_count": row["call_count"] or 0,
                        "success_count": row["success_count"] or 0
                    })
                else:
                    result.append({
                        "hour": hour_key,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "total_tokens": 0,
                        "call_count": 0,
                        "success_count": 0
                    })
                current += timedelta(hours=1)
            
            return result
    
    def get_model_stats(
        self,
        days: int = 30,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取按模型分组的统计数据
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            模型统计列表
        """
        start_date = datetime.now() - timedelta(days=days)
        
        query = '''
            SELECT 
                model,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(duration) as avg_duration,
                MIN(timestamp) as first_used,
                MAX(timestamp) as last_used
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_date]

        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += ' GROUP BY model ORDER BY total_tokens DESC'
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "model": row["model"] or "(未知)",
                "tokens_in": row["total_tokens_in"] or 0,
                "tokens_out": row["total_tokens_out"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "call_count": row["call_count"] or 0,
                "success_count": row["success_count"] or 0,
                "success_rate": (row["success_count"] / row["call_count"] * 100) if row["call_count"] > 0 else 0,
                "avg_duration": round(row["avg_duration"] or 0, 2),
                "first_used": row["first_used"],
                "last_used": row["last_used"]
            } for row in rows]
    
    def get_agent_stats(
        self,
        days: int = 30,
        model: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取按Agent分组的统计数据
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            Agent统计列表
        """
        start_date = datetime.now() - timedelta(days=days)
        
        query = '''
            SELECT 
                agent_name,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(duration) as avg_duration
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_date]
        
        if model:
            query += ' AND model = ?'
            params.append(model)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += ' GROUP BY agent_name ORDER BY total_tokens DESC'
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "agent_name": row["agent_name"],
                "tokens_in": row["total_tokens_in"] or 0,
                "tokens_out": row["total_tokens_out"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "call_count": row["call_count"] or 0,
                "success_count": row["success_count"] or 0,
                "success_rate": (row["success_count"] / row["call_count"] * 100) if row["call_count"] > 0 else 0,
                "avg_duration": round(row["avg_duration"] or 0, 2)
            } for row in rows]
    
    def get_summary(
        self,
        days: int = 30,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取统计摘要
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            统计摘要
        """
        start_date = datetime.now() - timedelta(days=days)
        
        query = '''
            SELECT 
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as call_count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(duration) as avg_duration,
                COUNT(DISTINCT model) as model_count,
                COUNT(DISTINCT agent_name) as agent_count,
                MIN(timestamp) as first_record,
                MAX(timestamp) as last_record
            FROM token_usage
            WHERE timestamp >= ?
        '''
        params = [start_date]
        
        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            
            if row:
                call_count = row["call_count"] or 0
                return {
                    "period_days": days,
                    "tokens_in": row["total_tokens_in"] or 0,
                    "tokens_out": row["total_tokens_out"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "call_count": call_count,
                    "success_count": row["success_count"] or 0,
                    "success_rate": (row["success_count"] / call_count * 100) if call_count > 0 else 0,
                    "avg_duration": round(row["avg_duration"] or 0, 2),
                    "avg_tokens_per_call": round((row["total_tokens"] or 0) / call_count, 2) if call_count > 0 else 0,
                    "model_count": row["model_count"] or 0,
                    "agent_count": row["agent_count"] or 0,
                    "first_record": row["first_record"],
                    "last_record": row["last_record"],
                    "filter_model": model,
                    "filter_agent": agent_name,
                    "filter_project_id": project_id
                }
            
            return {
                "period_days": days,
                "tokens_in": 0,
                "tokens_out": 0,
                "total_tokens": 0,
                "call_count": 0,
                "success_count": 0,
                "success_rate": 0,
                "avg_duration": 0,
                "avg_tokens_per_call": 0,
                "model_count": 0,
                "agent_count": 0,
                "first_record": None,
                "last_record": None,
                "filter_model": model,
                "filter_agent": agent_name,
                "filter_project_id": project_id
            }
    
    def get_available_models(self, project_id: Optional[str] = None) -> List[str]:
        """获取所有使用过的模型列表"""
        query = '''
            SELECT DISTINCT model FROM token_usage
            WHERE model != ''
        '''
        params = []
        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        query += ' ORDER BY model'

        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return [row["model"] for row in cursor.fetchall()]
    
    def get_available_agents(self, project_id: Optional[str] = None) -> List[str]:
        """获取所有Agent列表"""
        query = '''
            SELECT DISTINCT agent_name FROM token_usage
            WHERE 1=1
        '''
        params = []
        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        query += ' ORDER BY agent_name'

        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return [row["agent_name"] for row in cursor.fetchall()]
    
    def get_recent_records(
        self,
        limit: int = 100,
        model: Optional[str] = None,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的记录
        
        Args:
            limit: 返回数量限制
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            project_id: 筛选项目（可选）
            
        Returns:
            记录列表
        """
        query = 'SELECT * FROM token_usage WHERE 1=1'
        params = []
        
        if model:
            query += ' AND model = ?'
            params.append(model)
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)

        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "id": row["id"],
                "timestamp": row["timestamp"],
                "project_id": row["project_id"],
                "agent_name": row["agent_name"],
                "model": row["model"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
                "total_tokens": row["total_tokens"],
                "success": bool(row["success"]),
                "method": row["method"],
                "duration": row["duration"]
            } for row in rows]
    
    def cleanup_old_records(self, days: int = 90, project_id: Optional[str] = None) -> int:
        """
        清理旧记录
        
        Args:
            days: 保留天数
            project_id: 筛选项目（可选）
            
        Returns:
            删除的记录数
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self._get_cursor() as cursor:
            query = 'DELETE FROM token_usage WHERE timestamp < ?'
            params = [cutoff_date]
            if project_id is not None:
                query += ' AND project_id = ?'
                params.append(project_id)
            cursor.execute(query, params)
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old token usage records")
            
            return deleted_count
    
    def reset_all(self, project_id: Optional[str] = None) -> int:
        """
        重置统计数据。

        project_id 为 None 时清空整个表；传入项目ID时只清空该项目。
        
        Returns:
            删除的记录数
        """
        with self._get_cursor() as cursor:
            # 先获取记录总数
            count_query = 'SELECT COUNT(*) FROM token_usage'
            count_params = []
            if project_id is not None:
                count_query += ' WHERE project_id = ?'
                count_params.append(project_id)
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            
            # 删除记录
            delete_query = 'DELETE FROM token_usage'
            delete_params = []
            if project_id is not None:
                delete_query += ' WHERE project_id = ?'
                delete_params.append(project_id)
            cursor.execute(delete_query, delete_params)
            
            logger.info(
                "Reset token usage records: project_id=%s, %s records deleted",
                project_id,
                total_count,
            )
            return total_count
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


# 全局实例
_token_stats_store: Optional[TokenStatsStore] = None


def get_token_stats_store() -> TokenStatsStore:
    """获取全局TokenStatsStore实例"""
    global _token_stats_store
    if _token_stats_store is None:
        _token_stats_store = TokenStatsStore()
    return _token_stats_store


def _get_current_project_id() -> str:
    """Best-effort current project id for token records."""
    try:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        return str(getattr(pm, "current_project_id", "") or "")
    except Exception as exc:
        logger.debug("Unable to resolve current project for token stats: %s", exc)
        return ""


def record_token_usage(
    agent_name: str,
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    success: bool = True,
    method: str = "",
    duration: float = 0.0,
    project_id: Optional[str] = None
) -> int:
    """
    便捷函数：记录token使用
    
    Args:
        agent_name: Agent名称
        model: 模型名称
        project_id: 项目ID，默认自动使用当前项目
        tokens_in: 输入token数
        tokens_out: 输出token数
        success: 是否成功
        method: 调用方法
        duration: 耗时(秒)
        
    Returns:
        记录ID
    """
    store = get_token_stats_store()
    return store.record(
        agent_name=agent_name,
        model=model,
        project_id=_get_current_project_id() if project_id is None else project_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        success=success,
        method=method,
        duration=duration
    )


# 模块职责说明：Token消耗统计的SQLite持久化存储，支持多维度查询和统计分析。
