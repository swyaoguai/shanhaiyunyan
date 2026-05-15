"""Chapter-to-knowledge-base synchronization helpers."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from .content_sanitizer import strip_internal_author_markers

logger = logging.getLogger(__name__)

CHAPTER_KNOWLEDGE_SYNC_CONFIG_KEY = "chapter_knowledge_sync_config"
DEFAULT_CHAPTER_KNOWLEDGE_SYNC_CONFIG: Dict[str, bool] = {
    "auto_vector_sync_enabled": True,
    "sync_on_edit_enabled": True,
    "sync_on_delete_enabled": True,
}


def normalize_chapter_knowledge_sync_config(payload: Any) -> Dict[str, bool]:
    config = dict(DEFAULT_CHAPTER_KNOWLEDGE_SYNC_CONFIG)
    if isinstance(payload, dict):
        for key in config:
            if key in payload:
                config[key] = bool(payload.get(key))
    return config


def get_chapter_knowledge_sync_config(project_id: str = "") -> Dict[str, bool]:
    try:
        from .project_manager import get_project_manager

        pm = get_project_manager()
        state = pm.load_project_state(CHAPTER_KNOWLEDGE_SYNC_CONFIG_KEY, default={})
        return normalize_chapter_knowledge_sync_config(state)
    except Exception:
        return dict(DEFAULT_CHAPTER_KNOWLEDGE_SYNC_CONFIG)


def set_chapter_knowledge_sync_config(project_id: str, payload: Dict[str, Any]) -> Dict[str, bool]:
    from .project_manager import get_project_manager

    pm = get_project_manager()
    config = normalize_chapter_knowledge_sync_config(payload)
    pm.save_project_state(CHAPTER_KNOWLEDGE_SYNC_CONFIG_KEY, config)
    return config


def chapter_content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def build_chapter_id(chapter_number: int) -> str:
    return f"chapter_{int(chapter_number)}"


def upsert_knowledge_base_chapter(
    knowledge_base: Any,
    *,
    chapter_id: str,
    title: str,
    content: str,
    chapter_number: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Idempotently upsert a chapter into a KnowledgeBase instance."""

    clean_content = strip_internal_author_markers(content or "").strip()
    if not clean_content:
        return {"status": "skipped_empty", "chapter_id": chapter_id, "chapter_number": chapter_number}

    now = datetime.now().isoformat()
    content_hash = chapter_content_hash(clean_content)
    merged_metadata = {
        "source": "project_chapters",
        "sync_source": "project_chapters",
        "content_hash": content_hash,
        "chapter_number": chapter_number,
        "title": title,
        "synced_at": now,
        **(metadata or {}),
    }

    existing = None
    get_chapter = getattr(knowledge_base, "get_chapter", None)
    if callable(get_chapter):
        existing = get_chapter(chapter_id)

    existing_metadata = getattr(existing, "metadata", None) if existing is not None else None
    existing_hash = (existing_metadata or {}).get("content_hash") if isinstance(existing_metadata, dict) else None
    existing_title = getattr(existing, "title", "") if existing is not None else ""

    if existing is not None and existing_hash == content_hash:
        if existing_title != title and hasattr(knowledge_base, "update_chapter"):
            knowledge_base.update_chapter(
                chapter_id=chapter_id,
                title=title,
                chapter_number=chapter_number,
                metadata=merged_metadata,
            )
            return {"status": "metadata_updated", "chapter_id": chapter_id, "chapter_number": chapter_number}
        return {"status": "skipped_unchanged", "chapter_id": chapter_id, "chapter_number": chapter_number}

    if existing is not None and hasattr(knowledge_base, "update_chapter"):
        result = knowledge_base.update_chapter(
            chapter_id=chapter_id,
            title=title,
            content=clean_content,
            chapter_number=chapter_number,
            metadata=merged_metadata,
        )
        return {
            "status": "updated",
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "chunk_count": getattr(result, "chunk_count", 0),
            "success": getattr(result, "success", True),
            "error": getattr(result, "error", ""),
        }

    result = knowledge_base.add_chapter(
        chapter_id=chapter_id,
        title=title,
        content=clean_content,
        chapter_number=chapter_number,
        metadata=merged_metadata,
    )
    return {
        "status": "created",
        "chapter_id": chapter_id,
        "chapter_number": chapter_number,
        "chunk_count": getattr(result, "chunk_count", 0),
        "success": getattr(result, "success", True),
        "error": getattr(result, "error", ""),
    }


@dataclass
class ChapterKnowledgeSyncService:
    project_manager: Any
    knowledge_base_factory: Optional[Callable[[str], Any]] = None
    config: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.config = normalize_chapter_knowledge_sync_config(self.config or self._load_config())

    def _load_config(self) -> Dict[str, Any]:
        try:
            return self.project_manager.load_project_state(CHAPTER_KNOWLEDGE_SYNC_CONFIG_KEY, default={})
        except Exception:
            return {}

    def sync_chapters(
        self,
        chapters: Optional[Iterable[Dict[str, Any]]] = None,
        *,
        delete_missing: Optional[bool] = None,
        force: bool = False,
        trigger: str = "edit",
    ) -> Dict[str, Any]:
        if not force and not self.config.get("auto_vector_sync_enabled", True):
            return {"success": True, "status": "disabled", "synced": 0, "deleted": 0, "errors": []}
        if not force and trigger == "edit" and not self.config.get("sync_on_edit_enabled", True):
            return {"success": True, "status": "disabled_edit_sync", "synced": 0, "deleted": 0, "errors": []}

        rows = list(chapters if chapters is not None else self.project_manager.load_project_data("chapters"))
        delete_stale = self.config.get("sync_on_delete_enabled", True) if delete_missing is None else bool(delete_missing)

        kb = None
        close_after = False
        try:
            kb, close_after = self._open_knowledge_base()
        except Exception as exc:
            return {
                "success": False,
                "status": "not_ready",
                "synced": 0,
                "deleted": 0,
                "errors": [str(exc)],
            }

        results: List[Dict[str, Any]] = []
        errors: List[str] = []
        expected_ids = set()

        try:
            for index, row in enumerate(rows, start=1):
                normalized = self._normalize_chapter_row(row, index)
                if not normalized:
                    continue
                try:
                    if not str(normalized.get("content") or "").strip():
                        if self.config.get("sync_on_delete_enabled", True):
                            deleted = _delete_single_chapter(kb, normalized["chapter_id"])
                            results.append({
                                "status": "deleted_empty" if deleted else "skipped_empty",
                                "chapter_id": normalized["chapter_id"],
                                "chapter_number": normalized["chapter_number"],
                            })
                        else:
                            expected_ids.add(normalized["chapter_id"])
                            results.append({
                                "status": "skipped_empty",
                                "chapter_id": normalized["chapter_id"],
                                "chapter_number": normalized["chapter_number"],
                            })
                        continue
                    expected_ids.add(normalized["chapter_id"])
                    results.append(upsert_knowledge_base_chapter(kb, **normalized))
                except Exception as exc:
                    msg = f"{normalized['chapter_id']}: {exc}"
                    logger.warning(f"[ChapterKnowledgeSync] Upsert failed {msg}")
                    errors.append(msg)

            empty_deleted = sum(1 for item in results if item.get("status") == "deleted_empty")
            deleted = (self._delete_stale_chapters(kb, expected_ids) if delete_stale else 0) + empty_deleted
            return {
                "success": not errors,
                "status": "completed" if not errors else "partial",
                "synced": sum(1 for item in results if item.get("status") in {"created", "updated", "metadata_updated"}),
                "skipped": sum(1 for item in results if str(item.get("status", "")).startswith("skipped")),
                "deleted": deleted,
                "results": results,
                "errors": errors,
            }
        finally:
            if close_after and kb is not None:
                close = getattr(kb, "close", None)
                if callable(close):
                    close()

    def _open_knowledge_base(self):
        project_id = str(getattr(self.project_manager, "current_project_id", "") or "").strip()
        if not project_id:
            raise ValueError("请先选择或创建一个项目")

        if self.knowledge_base_factory:
            return self.knowledge_base_factory(project_id), True

        from .knowledge_runtime import create_project_knowledge_base

        return create_project_knowledge_base(project_id, data_dir=getattr(self.project_manager, "data_dir", None)), True

    def _normalize_chapter_row(self, row: Any, index: int) -> Optional[Dict[str, Any]]:
        if not isinstance(row, dict):
            return None
        chapter_number = _positive_int(row.get("chapter_number")) or index
        title = str(row.get("title") or row.get("name") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        content = strip_internal_author_markers(row.get("content") or "").strip()
        if not content:
            return {
                "chapter_id": build_chapter_id(chapter_number),
                "title": title,
                "content": "",
                "chapter_number": chapter_number,
                "metadata": {"empty_source": True},
            }
        return {
            "chapter_id": build_chapter_id(chapter_number),
            "title": title,
            "content": content,
            "chapter_number": chapter_number,
            "metadata": {
                "summary": str(row.get("summary") or "").strip(),
                "created_at": str(row.get("created_at") or "").strip(),
                "updated_at": str(row.get("updated_at") or "").strip(),
            },
        }

    def _delete_stale_chapters(self, knowledge_base: Any, expected_ids: set[str]) -> int:
        list_chapters = getattr(knowledge_base, "list_chapters", None)
        delete_chapter = getattr(knowledge_base, "delete_chapter", None)
        if not callable(list_chapters) or not callable(delete_chapter):
            return 0

        deleted = 0
        for chapter in list_chapters(limit=None):
            chapter_id = str(getattr(chapter, "chapter_id", "") or "")
            if not chapter_id or chapter_id in expected_ids:
                continue
            metadata = getattr(chapter, "metadata", None) or {}
            source = (metadata.get("sync_source") or metadata.get("source")) if isinstance(metadata, dict) else ""
            is_project_chapter = source == "project_chapters" or re.fullmatch(r"chapter_\d+", chapter_id)
            if not is_project_chapter:
                continue
            try:
                if delete_chapter(chapter_id):
                    deleted += 1
            except Exception as exc:
                logger.warning(f"[ChapterKnowledgeSync] Delete stale chapter failed {chapter_id}: {exc}")
        return deleted


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _delete_single_chapter(knowledge_base: Any, chapter_id: str) -> bool:
    delete_chapter = getattr(knowledge_base, "delete_chapter", None)
    if not callable(delete_chapter):
        return False
    try:
        return bool(delete_chapter(chapter_id))
    except Exception as exc:
        logger.warning(f"[ChapterKnowledgeSync] Delete empty chapter index failed {chapter_id}: {exc}")
        return False
