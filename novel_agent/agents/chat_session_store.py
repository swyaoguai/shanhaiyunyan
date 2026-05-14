# -*- coding: utf-8 -*-
"""
聊天会话持久化存储
用于避免服务重启后聊天上下文丢失，并支持TTL自动清理
"""

import json
import copy
import logging
import os
import time
import re
from dataclasses import dataclass, asdict, field, fields as dc_fields
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import threading

from ..constants import get_data_dir

logger = logging.getLogger(__name__)

_PATH_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_CONVERSATION_HISTORY = 200


@dataclass
class ChatSessionState:
    """聊天会话状态"""
    session_id: str
    project_id: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    collected_info: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    expires_at: int = 0  # Unix时间戳（秒）
    version: int = 0     # 会话版本戳（每次持久化+1）

    def __post_init__(self):
        now_iso = datetime.now().isoformat()
        now_ts = int(time.time())

        if not self.created_at:
            self.created_at = now_iso
        self.updated_at = now_iso

        # 默认TTL：7天（可通过环境变量覆盖）
        if not self.expires_at:
            ttl = int(os.getenv("CHAT_SESSION_TTL_SECONDS", "604800"))
            self.expires_at = now_ts + ttl

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSessionState":
        known = {f.name for f in dc_fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def is_expired(self) -> bool:
        return int(time.time()) >= self.expires_at

    def refresh_ttl(self) -> None:
        ttl = int(os.getenv("CHAT_SESSION_TTL_SECONDS", "604800"))
        self.updated_at = datetime.now().isoformat()
        self.expires_at = int(time.time()) + ttl


class ChatSessionStore:
    """聊天会话存储"""

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            storage_dir = get_data_dir() / "chat_sessions"

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, ChatSessionState] = {}
        self._locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._MAX_LOCK_POOL_SIZE = 500

        logger.info(f"[ChatSessionStore] 初始化完成，目录: {self.storage_dir}")

    def _get_lock(self, session_id: str, project_id: str = ""):
        key = self._cache_key(session_id, project_id)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                if len(self._locks) >= self._MAX_LOCK_POOL_SIZE:
                    evicted = False
                    for candidate_key in list(self._locks):
                        candidate = self._locks[candidate_key]
                        if candidate.acquire(blocking=False):
                            candidate.release()
                            del self._locks[candidate_key]
                            evicted = True
                            break
                    if not evicted:
                        logger.warning(
                            f"[ChatSessionStore] 锁池已满({self._MAX_LOCK_POOL_SIZE})且全部活跃，允许临时超出"
                        )
                lock = threading.RLock()
                self._locks[key] = lock
            return lock

    def _cache_key(self, session_id: str, project_id: str = "") -> str:
        safe_session_id = self._validate_path_component(session_id, "session_id")
        safe_project_id = self._validate_path_component(project_id, "project_id", allow_empty=True)
        scope = safe_project_id or "default"
        return f"{scope}::{safe_session_id}"

    @staticmethod
    def _validate_path_component(value: str, field_name: str, allow_empty: bool = False) -> str:
        text = (value or "").strip()
        if not text and allow_empty:
            return ""
        if not text:
            raise ValueError(f"{field_name} 不能为空")
        if not _PATH_COMPONENT_PATTERN.fullmatch(text):
            raise ValueError(f"{field_name} 包含非法字符")
        return text

    @staticmethod
    def _ensure_in_directory(target_path: Path, base_dir: Path) -> Path:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        try:
            is_inside = resolved_target.is_relative_to(resolved_base)
        except AttributeError:
            is_inside = str(resolved_target).startswith(str(resolved_base))
        if not is_inside:
            raise ValueError("非法会话文件路径")
        return resolved_target

    def _get_session_path(self, session_id: str, project_id: str = "") -> Path:
        safe_session_id = self._validate_path_component(session_id, "session_id")
        safe_project_id = self._validate_path_component(project_id, "project_id", allow_empty=True)
        base_dir = self.storage_dir / (safe_project_id or "default")
        base_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = base_dir / f"{safe_session_id}.json"
        return self._ensure_in_directory(candidate_path, base_dir)

    def save(self, state: ChatSessionState) -> bool:
        try:
            self._validate_path_component(state.session_id, "session_id")
            self._validate_path_component(state.project_id, "project_id", allow_empty=True)
            lock = self._get_lock(state.session_id, state.project_id)
            with lock:
                state.refresh_ttl()
                state.version = max(0, int(getattr(state, "version", 0))) + 1
                if len(state.conversation_history) > MAX_CONVERSATION_HISTORY:
                    state.conversation_history = state.conversation_history[-MAX_CONVERSATION_HISTORY:]
                key = self._cache_key(state.session_id, state.project_id)
                self._cache[key] = copy.deepcopy(state)

                path = self._get_session_path(state.session_id, state.project_id)
                temp = path.with_suffix(f".tmp.{int(time.time() * 1000)}")
                temp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
                temp.replace(path)
                return True
        except ValueError as e:
            logger.warning(f"[ChatSessionStore] 非法会话标识，保存拒绝: {e}")
            return False
        except Exception as e:
            logger.error(f"[ChatSessionStore] 保存失败: {e}")
            return False

    def load(self, session_id: str, project_id: str = "") -> Optional[ChatSessionState]:
        try:
            self._validate_path_component(session_id, "session_id")
            self._validate_path_component(project_id, "project_id", allow_empty=True)
        except ValueError as e:
            logger.warning(f"[ChatSessionStore] 非法会话标识，加载拒绝: {e}")
            return None

        lock = self._get_lock(session_id, project_id)
        with lock:
            key = self._cache_key(session_id, project_id)
            if key in self._cache:
                state = self._cache[key]
                if state.is_expired():
                    self.delete(session_id, project_id)
                    return None
                return copy.deepcopy(state)

            path = self._get_session_path(session_id, project_id)
            if not path.exists():
                return None

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                state = ChatSessionState.from_dict(data)
                if state.is_expired():
                    self.delete(session_id, project_id)
                    return None

                self._cache[key] = state
                return copy.deepcopy(state)
            except Exception as e:
                logger.error(f"[ChatSessionStore] 加载失败: {e}")
                return None

    def delete(self, session_id: str, project_id: str = "") -> bool:
        try:
            self._validate_path_component(session_id, "session_id")
            self._validate_path_component(project_id, "project_id", allow_empty=True)
            lock = self._get_lock(session_id, project_id)
            with lock:
                key = self._cache_key(session_id, project_id)
                if key in self._cache:
                    del self._cache[key]

                path = self._get_session_path(session_id, project_id)
                if path.exists():
                    path.unlink()

                return True
        except ValueError as e:
            logger.warning(f"[ChatSessionStore] 非法会话标识，删除拒绝: {e}")
            return False
        except Exception as e:
            logger.error(f"[ChatSessionStore] 删除失败: {e}")
            return False

    def cleanup_expired(self) -> int:
        """清理过期会话，返回清理数量"""
        deleted = 0

        # 清理缓存
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            del self._cache[key]
            deleted += 1

        # 清理文件
        for p in self.storage_dir.rglob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                expires_at = int(data.get("expires_at", 0))
                if expires_at and int(time.time()) >= expires_at:
                    p.unlink()
                    deleted += 1
            except Exception as e:
                # 非法文件不影响主流程
                logger.warning(f"[ChatSessionStore] 跳过异常会话文件: {p}, err={e}")
                continue

        return deleted


    def clear_project_cache(self, project_id: str = "") -> int:
        """仅清理指定项目作用域的内存缓存与锁，不删除磁盘文件。"""
        try:
            safe_project_id = self._validate_path_component(project_id, "project_id", allow_empty=True)
        except ValueError as e:
            logger.warning(f"[ChatSessionStore] 非法项目标识，清理缓存拒绝: {e}")
            return 0

        scope = safe_project_id or "default"
        prefix = f"{scope}::"
        removed = 0

        for key in list(self._cache.keys()):
            if key.startswith(prefix):
                self._cache.pop(key, None)
                removed += 1

        with self._locks_guard:
            for key in list(self._locks.keys()):
                if key.startswith(prefix):
                    self._locks.pop(key, None)

        logger.info(f"[ChatSessionStore] 已清理项目缓存: project_id={safe_project_id}, removed={removed}")
        return removed


_chat_session_store: Optional[ChatSessionStore] = None


def get_chat_session_store() -> ChatSessionStore:
    global _chat_session_store
    if _chat_session_store is None:
        _chat_session_store = ChatSessionStore()
    return _chat_session_store
