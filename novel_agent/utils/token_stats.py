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


@dataclass
class TokenUsageRecord:
    """Token使用记录"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
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
            
            logger.info("Database tables initialized")
    
    def record(
        self,
        agent_name: str,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        success: bool = True,
        method: str = "",
        duration: float = 0.0
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
            
        Returns:
            记录ID
        """
        total_tokens = tokens_in + tokens_out
        
        with self._get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO token_usage 
                (timestamp, agent_name, model, tokens_in, tokens_out, total_tokens, success, method, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
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
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取每日统计数据
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            
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
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取每周统计数据
        
        Args:
            weeks: 统计周数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            
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
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取小时统计数据（用于24小时曲线图）
        
        Args:
            hours: 统计小时数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            
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
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取按模型分组的统计数据
        
        Args:
            days: 统计天数
            agent_name: 筛选Agent（可选）
            
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
        
        if agent_name:
            query += ' AND agent_name = ?'
            params.append(agent_name)
        
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
        model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取按Agent分组的统计数据
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            
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
        agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取统计摘要
        
        Args:
            days: 统计天数
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            
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
                    "filter_agent": agent_name
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
                "filter_agent": agent_name
            }
    
    def get_available_models(self) -> List[str]:
        """获取所有使用过的模型列表"""
        with self._get_cursor() as cursor:
            cursor.execute('''
                SELECT DISTINCT model FROM token_usage 
                WHERE model != '' 
                ORDER BY model
            ''')
            return [row["model"] for row in cursor.fetchall()]
    
    def get_available_agents(self) -> List[str]:
        """获取所有Agent列表"""
        with self._get_cursor() as cursor:
            cursor.execute('''
                SELECT DISTINCT agent_name FROM token_usage 
                ORDER BY agent_name
            ''')
            return [row["agent_name"] for row in cursor.fetchall()]
    
    def get_recent_records(
        self,
        limit: int = 100,
        model: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的记录
        
        Args:
            limit: 返回数量限制
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
            
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
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "id": row["id"],
                "timestamp": row["timestamp"],
                "agent_name": row["agent_name"],
                "model": row["model"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
                "total_tokens": row["total_tokens"],
                "success": bool(row["success"]),
                "method": row["method"],
                "duration": row["duration"]
            } for row in rows]
    
    def cleanup_old_records(self, days: int = 90) -> int:
        """
        清理旧记录
        
        Args:
            days: 保留天数
            
        Returns:
            删除的记录数
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self._get_cursor() as cursor:
            cursor.execute('DELETE FROM token_usage WHERE timestamp < ?', (cutoff_date,))
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old token usage records")
            
            return deleted_count
    
    def reset_all(self) -> int:
        """
        重置所有统计数据（清空整个表）
        
        Returns:
            删除的记录数
        """
        with self._get_cursor() as cursor:
            # 先获取记录总数
            cursor.execute('SELECT COUNT(*) FROM token_usage')
            total_count = cursor.fetchone()[0]
            
            # 删除所有记录
            cursor.execute('DELETE FROM token_usage')
            
            logger.info(f"Reset all token usage records: {total_count} records deleted")
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


def record_token_usage(
    agent_name: str,
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    success: bool = True,
    method: str = "",
    duration: float = 0.0
) -> int:
    """
    便捷函数：记录token使用
    
    Args:
        agent_name: Agent名称
        model: 模型名称
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
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        success=success,
        method=method,
        duration=duration
    )


# 模块职责说明：Token消耗统计的SQLite持久化存储，支持多维度查询和统计分析。