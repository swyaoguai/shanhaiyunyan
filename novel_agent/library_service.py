"""
统一资料库服务 — 底层已替换为 Wiki 系统

本模块的 get_library_service() 现在返回 WikiLibraryAdapter，
它兼容旧 LibraryService 的所有接口。

library_types.py 和 library_mappers.py 保留为纯类型定义，无逻辑冲突。
"""

from __future__ import annotations

import logging
import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    KNOWLEDGE_NODE_TYPES,
    BUILTIN_CATEGORIES,
    SourceType,
)
from .library_mappers import LEGACY_MAPPER, LEGACY_PROJECTOR


# ------------------------------------------------------------------
#  Legacy LibraryService — compatibility for direct class imports
# ------------------------------------------------------------------

LEGACY_LIBRARY_FILES: Dict[str, str] = {
    "outline": "outline.json",
    "characters": "characters.json",
    "worldbuilding": "worldbuilding.json",
    "items": "items.json",
    "eventlines": "eventlines.json",
    "detail_settings": "detail_settings.json",
    "chapter_settings": "chapter_settings.json",
    "outline_settings": "outline_settings.json",
    "chapter_summary": "chapter_summaries.json",
}

WIKILINK_PATTERN = re.compile(r"\[\[[^\]]+\]\]")


class LibraryService:
    """
    旧版 library.json 资料库服务。

    运行时入口 get_library_service() 已切换到 WikiLibraryAdapter；这个类保留给
    仍然显式导入 LibraryService 的兼容代码和旧测试使用。
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.library_path = self.project_dir / "library.json"
        self.backup_dir = self.project_dir / ".library_backup"
        self._lock = threading.RLock()
        self._payload: Optional[LibraryPayload] = None

    @property
    def is_degraded(self) -> bool:
        return False

    def load(self) -> LibraryPayload:
        with self._lock:
            if self._payload is not None:
                return self._payload

            self.project_dir.mkdir(parents=True, exist_ok=True)
            if self.library_path.exists():
                try:
                    raw = json.loads(self.library_path.read_text(encoding="utf-8"))
                    self._payload = self._payload_from_dict(raw)
                    return self._payload
                except Exception as exc:
                    logger.warning(f"[LibraryService] 读取 library.json 失败，使用空资料库: {exc}")

            payload = LibraryPayload.empty()
            self._bootstrap_from_legacy(payload)
            self._payload = payload
            self.save(payload)
            return payload

    def save(self, payload: Optional[LibraryPayload] = None) -> None:
        with self._lock:
            if payload is not None:
                self._payload = payload
            payload = self._payload or LibraryPayload.empty()
            self.project_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self.library_path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(payload.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.library_path)

    def get_entry(self, entry_id: str) -> Optional[LibraryEntry]:
        payload = self.load()
        with self._lock:
            for entry in payload.entries:
                if entry.id == entry_id:
                    return entry
        return None

    def list_entries(
        self,
        entry_type: Optional[str] = None,
        category_key: Optional[str] = None,
    ) -> List[LibraryEntry]:
        payload = self.load()
        with self._lock:
            entries = list(payload.entries)
            if entry_type:
                entries = [entry for entry in entries if entry.entry_type == entry_type]
            if category_key:
                entries = [entry for entry in entries if entry.category_key == category_key]
            return entries

    def upsert_entry(self, entry: LibraryEntry) -> LibraryEntry:
        with self._lock:
            payload = self.load()
            normalized = self._normalize_entry(entry)
            for index, existing in enumerate(payload.entries):
                if existing.id == normalized.id:
                    payload.entries[index] = normalized
                    break
            else:
                payload.entries.append(normalized)
            self.save(payload)
            return normalized

    def upsert_entries(self, entries: List[LibraryEntry]) -> List[LibraryEntry]:
        return [self.upsert_entry(entry) for entry in entries]

    def delete_entry(self, entry_id: str) -> bool:
        with self._lock:
            payload = self.load()
            before = len(payload.entries)
            payload.entries = [entry for entry in payload.entries if entry.id != entry_id]
            deleted = len(payload.entries) != before
            if deleted:
                self.save(payload)
            return deleted

    def upsert_from_legacy(self, data_type: str, data: Any) -> List[LibraryEntry]:
        mapper = LEGACY_MAPPER.get(data_type)
        if mapper is None:
            return []
        entries = mapper(data)
        return self.upsert_entries(entries)

    def project_legacy_view(self, data_type: str) -> Any:
        projector = LEGACY_PROJECTOR.get(data_type)
        if projector is None:
            return []
        return projector(self.load().entries)

    def sync_legacy_file(self, data_type: str) -> None:
        data = self.project_legacy_view(data_type)
        file_name = LEGACY_LIBRARY_FILES.get(data_type)
        if file_name:
            (self.project_dir / file_name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def sync_all_legacy_files(self) -> None:
        for data_type in LEGACY_PROJECTOR:
            self.sync_legacy_file(data_type)

    def list_categories(self) -> List[CategoryMeta]:
        payload = self.load()
        return list(payload.categories_meta)

    def upsert_category(self, category: CategoryMeta) -> CategoryMeta:
        with self._lock:
            payload = self.load()
            for index, existing in enumerate(payload.categories_meta):
                if existing.key == category.key:
                    payload.categories_meta[index] = category
                    break
            else:
                payload.categories_meta.append(category)
            self.save(payload)
            return category

    def _bootstrap_from_legacy(self, payload: LibraryPayload) -> None:
        seen_ids = {entry.id for entry in payload.entries}
        for data_type, file_name in LEGACY_LIBRARY_FILES.items():
            legacy_path = self.project_dir / file_name
            if not legacy_path.exists():
                continue
            mapper = LEGACY_MAPPER.get(data_type)
            if mapper is None:
                continue
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
                for entry in mapper(data):
                    normalized = self._normalize_entry(entry)
                    if normalized.id not in seen_ids:
                        payload.entries.append(normalized)
                        seen_ids.add(normalized.id)
                self._backup_legacy_file(legacy_path)
            except Exception as exc:
                logger.warning(f"[LibraryService] 导入旧资料失败 {legacy_path}: {exc}")

    def _backup_legacy_file(self, legacy_path: Path) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        target = self.backup_dir / legacy_path.name
        if not target.exists():
            shutil.copy2(legacy_path, target)

    @classmethod
    def _payload_from_dict(cls, data: Dict[str, Any]) -> LibraryPayload:
        payload = LibraryPayload.empty()
        payload.version = data.get("version", CURRENT_LIBRARY_VERSION)
        payload.entries = [cls._entry_from_dict(item) for item in data.get("entries", [])]
        cats = data.get("categories_meta")
        if cats:
            payload.categories_meta = [CategoryMeta.from_dict(item) for item in cats]
        return payload

    @staticmethod
    def _entry_from_dict(data: Dict[str, Any]) -> LibraryEntry:
        if "links_out" in data or "links_in" in data or "vector_text" in data:
            known_fields = {field.name for field in KnowledgeNode.__dataclass_fields__.values()}
            filtered = {key: value for key, value in data.items() if key in known_fields}
            return KnowledgeNode(**filtered)
        return LibraryEntry.from_dict(data)

    @classmethod
    def _normalize_entry(cls, entry: LibraryEntry) -> LibraryEntry:
        if isinstance(entry, KnowledgeNode):
            node = entry
        elif entry.entry_type in KNOWLEDGE_NODE_TYPES:
            node = KnowledgeNode.from_entry(entry)
        else:
            entry.updated_at = _now_iso()
            return entry

        node.links_out = cls._merge_links(
            node.links_out,
            node.relations,
            cls._extract_links(node.summary),
            cls._extract_links(node.vector_text),
            cls._extract_links(node.content_structured),
        )
        structured_vector = node.content_structured.get("vector_text") if node.content_structured else ""
        if structured_vector and node.vector_text in ("", node.summary, node.title):
            node.vector_text = str(structured_vector)
        if not node.vector_text:
            node.vector_text = cls._build_vector_text(node)
        node.updated_at = _now_iso()
        return node

    @staticmethod
    def _merge_links(*groups: Any) -> List[str]:
        merged: List[str] = []
        seen = set()
        for group in groups:
            if not group:
                continue
            values = group if isinstance(group, list) else [group]
            for value in values:
                text = str(value).strip()
                if not text:
                    continue
                if not text.startswith("[["):
                    text = f"[[{text}]]"
                if text not in seen:
                    merged.append(text)
                    seen.add(text)
        return merged

    @classmethod
    def _extract_links(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, dict):
            links: List[str] = []
            for item in value.values():
                links.extend(cls._extract_links(item))
            return links
        if isinstance(value, list):
            links = []
            for item in value:
                links.extend(cls._extract_links(item))
            return links
        return WIKILINK_PATTERN.findall(str(value))

    @staticmethod
    def _build_vector_text(node: KnowledgeNode) -> str:
        parts = [node.title, node.summary]
        structured_text = node.content_structured.get("vector_text") if node.content_structured else ""
        if structured_text:
            parts.append(str(structured_text))
        return " ".join(part for part in parts if part).strip()


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
