"""
统一资料库服务 — 底层已替换为 Wiki 系统

本模块的 get_library_service() 现在返回 WikiLibraryAdapter，
它兼容旧 LibraryService 的所有接口。

library_types.py 和 library_mappers.py 保留为纯类型定义，无逻辑冲突。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 向后兼容：重新导出旧类型
from .library_types import (
    CURRENT_LIBRARY_VERSION,
    CategoryMeta,
    EntryType,
    KnowledgeNode,
    LibraryEntry,
    LibraryPayload,
    generate_entry_id,
    _now_iso,
    LEGACY_DATA_TYPE_MAP,
    ENTRY_TYPE_TO_LEGACY,
    BUILTIN_CATEGORIES,
    SourceType,
)
from .library_mappers import LEGACY_MAPPER, LEGACY_PROJECTOR


# ------------------------------------------------------------------
#  Singleton accessor — 返回 Wiki 适配器
# ------------------------------------------------------------------

_service_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def get_library_service(project_dir: Optional[Path] = None) -> Any:
    """
    获取资料库服务（底层已替换为 Wiki 系统）
    
    返回 WikiLibraryAdapter，兼容旧 LibraryService 的所有接口。
    """
    if project_dir is None:
        from .project_manager import get_project_manager
        pm = get_project_manager()
        project_dir = pm.get_project_data_path("outline").parent

    key = str(project_dir)
    with _cache_lock:
        svc = _service_cache.get(key)
        if svc is None:
            from .wiki.wiki_adapter import WikiLibraryAdapter
            svc = WikiLibraryAdapter(project_dir)
            _service_cache[key] = svc
            logger.info(f"[LibraryService] 使用 Wiki 系统: {project_dir}")
        return svc


def clear_library_cache() -> None:
    with _cache_lock:
        _service_cache.clear()