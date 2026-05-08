"""Recovery helpers for project-scoped writing data."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def has_project_payload(payload: Any) -> bool:
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        return bool(payload)
    if isinstance(payload, str):
        return bool(payload.strip())
    return payload is not None


def load_context_value(project_dir: Path, key: str, default: Any = None) -> Any:
    context_file = Path(project_dir) / "context.json"
    if not context_file.exists():
        return default
    try:
        data = json.loads(context_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[ProjectDataRecovery] Failed to read context.json: {exc}")
        return default
    contexts = data.get("contexts") if isinstance(data, dict) else {}
    item = contexts.get(key) if isinstance(contexts, dict) else {}
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return default


def load_context_chapter_values(project_dir: Path) -> Dict[int, Dict[str, str]]:
    context_file = Path(project_dir) / "context.json"
    if not context_file.exists():
        return {}
    try:
        data = json.loads(context_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    contexts = data.get("contexts") if isinstance(data, dict) else {}
    if not isinstance(contexts, dict):
        return {}

    chapters: Dict[int, Dict[str, str]] = {}
    pattern = re.compile(r"^chapter_(\d+)_(content|summary)$")
    for key, item in contexts.items():
        match = pattern.match(str(key))
        if not match or not isinstance(item, dict):
            continue
        chapter_number = int(match.group(1))
        field = match.group(2)
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        chapters.setdefault(chapter_number, {})[field] = value
    return chapters


def outline_payload_to_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]

    chapters: List[Any] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("chapters"), list):
            chapters = payload["chapters"]
        elif isinstance(payload.get("volumes"), list):
            for volume in payload["volumes"]:
                if isinstance(volume, dict) and isinstance(volume.get("chapters"), list):
                    chapters.extend(volume["chapters"])

    rows: List[Dict[str, Any]] = []
    now = datetime.now().isoformat()
    for index, chapter in enumerate(chapters, start=1):
        if isinstance(chapter, dict):
            title = str(chapter.get("title") or f"第{index}章").strip() or f"第{index}章"
            summary = str(chapter.get("summary") or chapter.get("description") or chapter.get("content") or "").strip()
            content = str(chapter.get("content") or "").strip()
        else:
            title = f"第{index}章"
            summary = str(chapter or "").strip()
            content = ""
        rows.append({
            "chapter_number": int(chapter.get("chapter_number") or index) if isinstance(chapter, dict) else index,
            "title": title,
            "summary": summary,
            "content": content,
            "created_at": str(chapter.get("created_at") or now) if isinstance(chapter, dict) else now,
            "updated_at": str(chapter.get("updated_at") or now) if isinstance(chapter, dict) else now,
        })
    return rows


def _chapter_number_from_file(path: Path, fallback: int) -> int:
    match = re.search(r"(\d+)", path.stem)
    if not match:
        return fallback
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return fallback


def _title_from_file(path: Path, chapter_number: int) -> str:
    title = re.sub(r"^\d+[_\-\s]*", "", path.stem).strip()
    return title or f"第{chapter_number}章"


def merge_outline_with_chapter_files(project_manager: Any, payload: Any) -> Optional[List[Dict[str, Any]]]:
    rows = outline_payload_to_rows(payload)
    project_dir = project_manager.get_current_project_dir()
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        return rows if rows else None

    chapter_files = sorted(chapters_dir.glob("*.md"))
    if not chapter_files:
        return rows if rows else None

    changed = False
    now = datetime.now().isoformat()
    for fallback_index, chapter_file in enumerate(chapter_files, start=1):
        chapter_number = _chapter_number_from_file(chapter_file, fallback_index)
        try:
            content = chapter_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not content:
            continue

        while len(rows) < chapter_number:
            row_number = len(rows) + 1
            rows.append({
                "chapter_number": row_number,
                "title": f"第{row_number}章",
                "summary": "",
                "content": "",
                "created_at": now,
                "updated_at": now,
            })
            changed = True

        row = rows[chapter_number - 1]
        if not str(row.get("title") or "").strip() or row.get("title") == f"第{chapter_number}章":
            row["title"] = _title_from_file(chapter_file, chapter_number)
            changed = True
        if not str(row.get("content") or "").strip():
            row["content"] = content
            row["updated_at"] = now
            changed = True

    if changed:
        project_manager.save_project_data("outline", rows)
    return rows if rows else None


def recover_project_data(data_type: str, project_manager: Any, existing_payload: Any = None) -> Any:
    project_dir = project_manager.get_current_project_dir()

    if data_type == "worldbuilding":
        from .worldbuilding_persistence import recover_worldbuilding_from_context

        return recover_worldbuilding_from_context(project_manager=project_manager)

    if data_type == "outline":
        merged = merge_outline_with_chapter_files(project_manager, existing_payload)
        if has_project_payload(merged):
            return merged

        context_outline = load_context_value(project_dir, "outline", default=None)
        rows = outline_payload_to_rows(context_outline)
        chapter_values = load_context_chapter_values(project_dir)
        if chapter_values:
            now = datetime.now().isoformat()
            for chapter_number, values in sorted(chapter_values.items()):
                while len(rows) < chapter_number:
                    row_number = len(rows) + 1
                    rows.append({
                        "chapter_number": row_number,
                        "title": f"第{row_number}章",
                        "summary": "",
                        "content": "",
                        "created_at": now,
                        "updated_at": now,
                    })
                row = rows[chapter_number - 1]
                row["summary"] = row.get("summary") or values.get("summary", "")
                row["content"] = row.get("content") or values.get("content", "")
                row["updated_at"] = now
        if rows:
            project_manager.save_project_data("outline", rows)
            return rows

    if data_type == "characters":
        characters = load_context_value(project_dir, "characters", default=None)
        if has_project_payload(characters):
            project_manager.save_project_data("characters", characters)
            return characters

    if data_type == "chapter_summary":
        chapter_values = load_context_chapter_values(project_dir)
        rows = []
        for chapter_number, values in sorted(chapter_values.items()):
            summary = values.get("summary", "")
            if summary:
                rows.append({
                    "chapter_number": chapter_number,
                    "title": f"第{chapter_number}章摘要",
                    "summary_text": summary,
                })
        if rows:
            project_manager.save_project_data("chapter_summary", rows)
            return rows

    return None


def persist_project_data(data_type: str, data: Any, *, project_manager: Any = None) -> Any:
    if project_manager is None:
        from .project_manager import get_project_manager

        project_manager = get_project_manager()
    if not getattr(project_manager, "current_project_id", None):
        return data

    project_manager.save_project_data(data_type, data)
    try:
        from .library_service import get_library_service

        svc = get_library_service(project_manager.get_current_project_dir())
        svc.upsert_from_legacy(data_type, data)
    except Exception as exc:
        logger.debug(f"[ProjectDataRecovery] Library sync failed for {data_type}: {exc}")
    return data
