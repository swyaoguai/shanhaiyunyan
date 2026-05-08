"""旧格式 ↔ LibraryEntry 双向转换"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .library_types import (
    EntryType,
    KnowledgeNode,
    LibraryEntry,
    SourceType,
    generate_entry_id,
    _now_iso,
)
from .outline_utils import build_global_outline_text, format_outline_volume_plan, get_outline_volumes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  旧 → 新  (legacy JSON → LibraryEntry list)
# ---------------------------------------------------------------------------

def outline_to_entries(data: Any) -> List[LibraryEntry]:
    global_outline = build_global_outline_text(data)
    volume_plan = format_outline_volume_plan(data)
    chapters = _extract_chapters(data)
    if global_outline or volume_plan:
        now = _now_iso()
        summary = _truncate(global_outline or volume_plan, 200)
        content_structured = {
            "global_outline": global_outline,
            "volume_plan": volume_plan,
        }
        if chapters:
            content_structured["chapters"] = chapters
        volumes = get_outline_volumes(data)
        if volumes:
            content_structured["volumes"] = volumes
        return [KnowledgeNode.from_entry(LibraryEntry(
            id=generate_entry_id("outline", 0),
            entry_type=EntryType.OUTLINE.value,
            title="主线大纲",
            summary=summary or "主线大纲",
            content_structured=content_structured,
            source_type=SourceType.IMPORTED.value,
            source_ref={"legacy_data_type": "outline"},
            category_key="outline",
            builtin=True,
            created_at=now,
            updated_at=now,
        ))]

    if not chapters:
        return []
    now = _now_iso()
    return [KnowledgeNode.from_entry(LibraryEntry(
        id=generate_entry_id("outline", 0),
        entry_type=EntryType.OUTLINE.value,
        title="主线大纲",
        summary=f"共 {len(chapters)} 章",
        content_structured={"chapters": chapters},
        source_type=SourceType.IMPORTED.value,
        source_ref={"legacy_data_type": "outline"},
        category_key="outline",
        builtin=True,
        created_at=now,
        updated_at=now,
    ))]


def characters_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data, wrapper_key="characters")
    entries: List[LibraryEntry] = []
    now = _now_iso()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("title") or f"角色_{i}"
        entries.append(KnowledgeNode.from_entry(LibraryEntry(
            id=generate_entry_id("character", i),
            entry_type=EntryType.CHARACTER.value,
            title=name,
            summary=_truncate(row.get("description") or row.get("role") or "", 200),
            content_structured=dict(row),
            source_type=SourceType.IMPORTED.value,
            source_ref={"legacy_data_type": "characters"},
            category_key="character",
            builtin=True,
            created_at=now,
            updated_at=now,
        )))
    return entries


def worldbuilding_to_entries(data: Any) -> List[LibraryEntry]:
    if not data:
        return []
    now = _now_iso()
    payload = data if isinstance(data, dict) else {}
    summary_parts = []
    if payload.get("world") and isinstance(payload["world"], dict):
        summary_parts.append(payload["world"].get("name") or "")
    return [KnowledgeNode.from_entry(LibraryEntry(
        id=generate_entry_id("world", 0),
        entry_type=EntryType.WORLD.value,
        title="世界观设定",
        summary=" ".join(summary_parts).strip() or "世界观设定",
        content_structured=payload,
        source_type=SourceType.IMPORTED.value,
        source_ref={"legacy_data_type": "worldbuilding"},
        category_key="world",
        builtin=True,
        created_at=now,
        updated_at=now,
    ))]


def items_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data, wrapper_key="items")
    return [KnowledgeNode.from_entry(entry) for entry in _named_rows_to_entries(rows, EntryType.ITEM, "items")]


def eventlines_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data)
    return [KnowledgeNode.from_entry(entry) for entry in _named_rows_to_entries(rows, EntryType.EVENTLINE, "eventlines")]


def detail_settings_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data)
    return [KnowledgeNode.from_entry(entry) for entry in _named_rows_to_entries(rows, EntryType.DETAIL_OUTLINE, "detail_settings")]


def chapter_settings_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data)
    return [KnowledgeNode.from_entry(entry) for entry in _named_rows_to_entries(rows, EntryType.CHAPTER_SETTING, "chapter_settings")]


def outline_settings_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data)
    return _named_rows_to_entries(
        rows, EntryType.CUSTOM, "outline_settings",
        category_override="outline_settings_legacy",
    )


def chapter_summaries_to_entries(data: Any) -> List[LibraryEntry]:
    rows = _extract_list(data)
    if not rows:
        return []
    now = _now_iso()
    entries = []
    for i, row in enumerate(rows):
        ch_num = row.get("chapter_number", i + 1)
        title = row.get("title") or row.get("summary_text", "") or f"第{ch_num}章摘要"
        links = _as_list(row.get("links"))
        base_entry = LibraryEntry(
            id=generate_entry_id("chapter_summary", i),
            entry_type=EntryType.CHAPTER_SUMMARY.value,
            title=_truncate(title, 60),
            summary=_truncate(row.get("summary_text", ""), 200),
            content_structured=row,
            source_type=SourceType.DERIVED.value,
            tags=["chapter_summary"],
            relations=links,
            metadata={"chapter_number": ch_num},
            created_at=now,
            updated_at=now,
        )
        entries.append(KnowledgeNode.from_entry(base_entry, links_out=links, vector_text=str(row.get("vector_text") or row.get("summary_text") or title)))
    return entries


LEGACY_MAPPER = {
    "outline": outline_to_entries,
    "characters": characters_to_entries,
    "worldbuilding": worldbuilding_to_entries,
    "items": items_to_entries,
    "eventlines": eventlines_to_entries,
    "detail_settings": detail_settings_to_entries,
    "chapter_settings": chapter_settings_to_entries,
    "outline_settings": outline_settings_to_entries,
    "chapter_summary": chapter_summaries_to_entries,
}


# ---------------------------------------------------------------------------
#  新 → 旧  (LibraryEntry list → legacy JSON)
# ---------------------------------------------------------------------------

def entries_to_outline(entries: List[LibraryEntry]) -> List[Dict]:
    for e in entries:
        if e.entry_type == EntryType.OUTLINE.value:
            return e.content_structured.get("chapters", [])
    return []


def entries_to_characters(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.CHARACTER.value]


def entries_to_worldbuilding(entries: List[LibraryEntry]) -> Dict:
    for e in entries:
        if e.entry_type == EntryType.WORLD.value:
            return e.content_structured
    return {}


def entries_to_items(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.ITEM.value]


def entries_to_eventlines(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.EVENTLINE.value]


def entries_to_detail_settings(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.DETAIL_OUTLINE.value]


def entries_to_chapter_settings(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.CHAPTER_SETTING.value]


def entries_to_outline_settings(entries: List[LibraryEntry]) -> List[Dict]:
    return [
        e.content_structured for e in entries
        if e.entry_type == EntryType.CUSTOM.value and e.category_key == "outline_settings_legacy"
    ]


def entries_to_chapter_summaries(entries: List[LibraryEntry]) -> List[Dict]:
    return [e.content_structured for e in entries if e.entry_type == EntryType.CHAPTER_SUMMARY.value]


LEGACY_PROJECTOR = {
    "outline": entries_to_outline,
    "characters": entries_to_characters,
    "worldbuilding": entries_to_worldbuilding,
    "items": entries_to_items,
    "eventlines": entries_to_eventlines,
    "detail_settings": entries_to_detail_settings,
    "chapter_settings": entries_to_chapter_settings,
    "outline_settings": entries_to_outline_settings,
    "chapter_summary": entries_to_chapter_summaries,
}


# ---------------------------------------------------------------------------
#  内部工具
# ---------------------------------------------------------------------------

def _extract_chapters(data: Any) -> List[Dict]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        ch = data.get("chapters")
        if isinstance(ch, list):
            return [r for r in ch if isinstance(r, dict)]
    return []


def _extract_list(data: Any, wrapper_key: Optional[str] = None) -> List[Dict]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and wrapper_key:
        inner = data.get(wrapper_key)
        if isinstance(inner, list):
            return [r for r in inner if isinstance(r, dict)]
    return []


def _named_rows_to_entries(
    rows: List[Dict],
    entry_type: EntryType,
    legacy_data_type: str,
    category_override: Optional[str] = None,
) -> List[LibraryEntry]:
    entries: List[LibraryEntry] = []
    now = _now_iso()
    cat_key = category_override or entry_type.value
    builtin = category_override is None
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("title") or f"{legacy_data_type}_{i}"
        summary_parts = []
        for k in ("description", "conflict", "goal", "scene_goal", "chapter_goal"):
            val = row.get(k)
            if val:
                summary_parts.append(_truncate(str(val), 100))
                break
        entries.append(LibraryEntry(
            id=generate_entry_id(entry_type.value, i),
            entry_type=entry_type.value,
            title=name,
            summary=" ".join(summary_parts),
            content_structured=dict(row),
            source_type=SourceType.IMPORTED.value,
            source_ref={"legacy_data_type": legacy_data_type},
            category_key=cat_key,
            builtin=builtin,
            created_at=now,
            updated_at=now,
        ))
    return entries


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]
