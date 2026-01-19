"""
LLM响应缓存模块
使用SQLite存储LLM响应缓存，减少重复调用
"""

import os
import json
import time
import sqlite3
import hashlib
import threading
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from functools import wraps

from ..constants import CACHE_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: str
    model: str
    temperature: float
    tokens_in: int
    tokens_out: int
    created_at: float
    expires_at: float
    hit_count: int = 0
    last_hit_at: Optional[float] = None


class LLMResponseCache:
    """
    LLM响应缓存
    
    使用SQLite存储缓存，支持：
    - TTL过期
    - 命中率统计
    - 内存+磁盘双层缓存
    - 线程安全
    """
    
    def __init__(
        self,
        db_path: str = None,
        default_ttl: int = CACHE_CONFIG.DEFAULT_TTL,
        memory_cache_size: int = CACHE_CONFIG.MEMORY_CACHE_SIZE,
        enabled: bool = True
    ):
        """
        初始化缓存
        
        Args:
            db_path: SQLite数据库路径，None则使用内存缓存
            default_ttl: 默认缓存过期时间（秒）
            memory_cache_size: 内存缓存大小
            enabled: 是否启用缓存
        """
        self.db_path = db_path
        self.default_ttl = default_ttl
        self.memory_cache_size = memory_cache_size
        self.enabled = enabled
        
        # 内存缓存（LRU）
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._memory_access_order: List[str] = []
        
        # 统计
        self._hits = 0
        self._misses = 0
        
        # 线程安全
        self._lock = threading.RLock()
        self._local = threading.local()
        
        # 初始化数据库
        if db_path:
            self._init_db()
        
        logger.info(f"LLM缓存初始化完成: {'SQLite' if db_path else '内存'}, TTL={default_ttl}s")
    
    @contextmanager
    def _get_connection(self):
        """获取线程安全的数据库连接"""
        if not self.db_path:
            yield None
            return
            
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            if conn is None:
                return
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    model TEXT,
                    temperature REAL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    last_hit_at REAL
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_expires_at 
                ON llm_cache(expires_at)
            ''')
            
            conn.commit()
    
    @staticmethod
    def _generate_key(
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """
        生成缓存键
        
        根据请求参数生成唯一的缓存键
        """
        # 创建规范化的请求内容
        content = json.dumps({
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }, sort_keys=True, ensure_ascii=False)
        
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int
    ) -> Optional[str]:
        """
        获取缓存
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度
            max_tokens: 最大token数
            
        Returns:
            缓存的响应，或None
        """
        if not self.enabled:
            return None
        
        key = self._generate_key(messages, model, temperature, max_tokens)
        
        with self._lock:
            # 1. 先查内存缓存
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if entry.expires_at > time.time():
                    self._update_hit(key, entry)
                    self._hits += 1
                    return entry.value
                else:
                    # 过期，删除
                    del self._memory_cache[key]
                    if key in self._memory_access_order:
                        self._memory_access_order.remove(key)
            
            # 2. 查SQLite缓存
            if self.db_path:
                entry = self._get_from_db(key)
                if entry and entry.expires_at > time.time():
                    self._update_hit(key, entry)
                    self._add_to_memory(key, entry)
                    self._hits += 1
                    return entry.value
        
        self._misses += 1
        return None
    
    def set(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        response: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        ttl: Optional[int] = None
    ) -> str:
        """
        设置缓存
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度
            max_tokens: 最大token数
            response: LLM响应
            tokens_in: 输入token数
            tokens_out: 输出token数
            ttl: 过期时间（秒），None使用默认值
            
        Returns:
            缓存键
        """
        if not self.enabled:
            return ""
        
        key = self._generate_key(messages, model, temperature, max_tokens)
        ttl = ttl if ttl is not None else self.default_ttl
        now = time.time()
        
        entry = CacheEntry(
            key=key,
            value=response,
            model=model,
            temperature=temperature,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            created_at=now,
            expires_at=now + ttl
        )
        
        with self._lock:
            # 添加到内存缓存
            self._add_to_memory(key, entry)
            
            # 添加到SQLite
            if self.db_path:
                self._save_to_db(entry)
        
        return key
    
    def _add_to_memory(self, key: str, entry: CacheEntry):
        """添加到内存缓存（LRU）"""
        # 如果已存在，更新访问顺序
        if key in self._memory_cache:
            if key in self._memory_access_order:
                self._memory_access_order.remove(key)
        # 淘汰最旧的
        elif len(self._memory_cache) >= self.memory_cache_size:
            if self._memory_access_order:
                oldest_key = self._memory_access_order.pop(0)
                if oldest_key in self._memory_cache:
                    del self._memory_cache[oldest_key]
        
        self._memory_cache[key] = entry
        self._memory_access_order.append(key)
    
    def _get_from_db(self, key: str) -> Optional[CacheEntry]:
        """从数据库获取"""
        with self._get_connection() as conn:
            if conn is None:
                return None
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM llm_cache WHERE key = ?',
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return CacheEntry(
                    key=row['key'],
                    value=row['value'],
                    model=row['model'],
                    temperature=row['temperature'],
                    tokens_in=row['tokens_in'],
                    tokens_out=row['tokens_out'],
                    created_at=row['created_at'],
                    expires_at=row['expires_at'],
                    hit_count=row['hit_count'],
                    last_hit_at=row['last_hit_at']
                )
            return None
    
    def _save_to_db(self, entry: CacheEntry):
        """保存到数据库"""
        with self._get_connection() as conn:
            if conn is None:
                return
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO llm_cache
                (key, value, model, temperature, tokens_in, tokens_out, 
                 created_at, expires_at, hit_count, last_hit_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.key, entry.value, entry.model, entry.temperature,
                entry.tokens_in, entry.tokens_out, entry.created_at,
                entry.expires_at, entry.hit_count, entry.last_hit_at
            ))
            conn.commit()
    
    def _update_hit(self, key: str, entry: CacheEntry):
        """更新命中统计"""
        entry.hit_count += 1
        entry.last_hit_at = time.time()
        
        if self.db_path:
            with self._get_connection() as conn:
                if conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE llm_cache 
                        SET hit_count = hit_count + 1, last_hit_at = ?
                        WHERE key = ?
                    ''', (entry.last_hit_at, key))
                    conn.commit()
    
    def invalidate(
        self,
        messages: List[Dict[str, str]] = None,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        key: str = None
    ) -> bool:
        """
        使缓存失效
        
        可以通过key直接删除，或通过请求参数删除
        """
        if key is None and messages:
            key = self._generate_key(messages, model, temperature, max_tokens)
        
        if not key:
            return False
        
        with self._lock:
            # 从内存删除
            if key in self._memory_cache:
                del self._memory_cache[key]
                if key in self._memory_access_order:
                    self._memory_access_order.remove(key)
            
            # 从数据库删除
            if self.db_path:
                with self._get_connection() as conn:
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM llm_cache WHERE key = ?', (key,))
                        conn.commit()
                        return cursor.rowcount > 0
        
        return True
    
    def clear_expired(self) -> int:
        """
        清理过期缓存
        
        Returns:
            清理的条目数
        """
        now = time.time()
        cleared = 0
        
        with self._lock:
            # 清理内存
            expired_keys = [
                k for k, v in self._memory_cache.items()
                if v.expires_at <= now
            ]
            for key in expired_keys:
                del self._memory_cache[key]
                if key in self._memory_access_order:
                    self._memory_access_order.remove(key)
                cleared += 1
            
            # 清理数据库
            if self.db_path:
                with self._get_connection() as conn:
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            'DELETE FROM llm_cache WHERE expires_at <= ?',
                            (now,)
                        )
                        cleared += cursor.rowcount
                        conn.commit()
        
        if cleared > 0:
            logger.info(f"清理了 {cleared} 个过期缓存条目")
        
        return cleared
    
    def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            self._memory_cache.clear()
            self._memory_access_order.clear()
            
            if self.db_path:
                with self._get_connection() as conn:
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM llm_cache')
                        conn.commit()
        
        logger.warning("已清空所有LLM缓存")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计
        
        Returns:
            统计信息字典
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        db_count = 0
        db_size = 0
        if self.db_path:
            with self._get_connection() as conn:
                if conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM llm_cache WHERE expires_at > ?', (time.time(),))
                    db_count = cursor.fetchone()[0]
            if os.path.exists(self.db_path):
                db_size = os.path.getsize(self.db_path)
        
        return {
            "enabled": self.enabled,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
            "memory_entries": len(self._memory_cache),
            "memory_cache_size": self.memory_cache_size,
            "db_entries": db_count,
            "db_size_bytes": db_size,
            "default_ttl": self.default_ttl
        }
    
    def close(self):
        """关闭连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# 全局缓存实例
_global_cache: Optional[LLMResponseCache] = None
_cache_lock = threading.Lock()


def get_llm_cache(
    db_path: str = None,
    default_ttl: int = CACHE_CONFIG.DEFAULT_TTL,
    memory_cache_size: int = CACHE_CONFIG.MEMORY_CACHE_SIZE,
    enabled: bool = True
) -> LLMResponseCache:
    """
    获取全局LLM缓存实例
    
    Args:
        db_path: 数据库路径
        default_ttl: 默认TTL
        memory_cache_size: 内存缓存大小
        enabled: 是否启用
        
    Returns:
        LLMResponseCache实例
    """
    global _global_cache
    
    with _cache_lock:
        if _global_cache is None:
            _global_cache = LLMResponseCache(
                db_path=db_path,
                default_ttl=default_ttl,
                memory_cache_size=memory_cache_size,
                enabled=enabled
            )
        return _global_cache


def cached_llm_call(ttl: int = CACHE_CONFIG.LLM_CACHE_TTL):
    """
    LLM调用缓存装饰器
    
    用于装饰异步LLM调用函数
    
    Args:
        ttl: 缓存过期时间（秒），默认使用 CACHE_CONFIG.LLM_CACHE_TTL
    
    Usage:
        @cached_llm_call(ttl=CACHE_CONFIG.LLM_CACHE_TTL)
        async def call_llm(messages, model, temperature, max_tokens):
            # ... 实际LLM调用
            return response
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(
            messages: List[Dict[str, str]],
            model: str,
            temperature: float,
            max_tokens: int,
            *args,
            use_cache: bool = True,
            **kwargs
        ):
            cache = get_llm_cache()
            
            # 尝试从缓存获取
            if use_cache:
                cached = cache.get(messages, model, temperature, max_tokens)
                if cached is not None:
                    logger.debug("LLM缓存命中")
                    return cached
            
            # 调用实际函数
            result = await func(messages, model, temperature, max_tokens, *args, **kwargs)
            
            # 存入缓存
            if use_cache and result:
                cache.set(
                    messages, model, temperature, max_tokens,
                    result, ttl=ttl
                )
            
            return result
        return wrapper
    return decorator


# 模块职责说明：使用SQLite存储LLM响应缓存，支持内存+磁盘双层缓存和TTL过期机制。