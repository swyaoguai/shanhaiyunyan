"""Utilities for normalizing project-level outline payloads."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .content_sanitizer import humanize_structured_value, strip_internal_author_markers


PENDING_TEXT_VALUES = {"", "待生成", "待生成。"}


def parse_jsonish_text(text: Any) -> Optional[Any]:
    """Parse JSON from plain text or a fenced model response."""
    raw = str(text or "").strip()
    if not raw:
        return None

    candidates: List[str] = []
    if "```json" in raw:
        candidates.append(raw.split("```json", 1)[1].split("```", 1)[0].strip())
    if "```" in raw:
        candidates.append(raw.split("```", 1)[1].split("```", 1)[0].strip())
    candidates.append(raw)

    object_start = raw.find("{")
    object_end = raw.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw[object_start : object_end + 1])

    array_start = raw.find("[")
    array_end = raw.rfind("]")
    if array_start >= 0 and array_end > array_start:
        candidates.append(raw[array_start : array_end + 1])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def normalize_outline_payload(payload: Any) -> Any:
    """Prefer parsed raw outline JSON when an agent wrapped it as raw_content."""
    if not isinstance(payload, dict):
        return payload

    raw_content = payload.get("raw_content")
    parsed = parse_jsonish_text(raw_content)
    if isinstance(parsed, dict):
        normalized = dict(parsed)
        for key, value in payload.items():
            if key != "raw_content" and key not in normalized:
                normalized[key] = value
        return normalized
    recovered = recover_loose_outline_payload(raw_content)
    if recovered:
        for key, value in payload.items():
            if key != "raw_content" and key not in recovered:
                recovered[key] = value
        return recovered
    return payload


def is_pending_text(value: Any) -> bool:
    return str(value or "").strip() in PENDING_TEXT_VALUES


def recover_loose_outline_payload(text: Any) -> Dict[str, Any]:
    """Recover key outline fields from truncated or newline-broken JSON text."""
    raw = str(text or "")
    if not raw.strip():
        return {}

    recovered: Dict[str, Any] = {}
    for key in (
        "title",
        "novel_title",
        "author",
        "intro",
        "theme",
        "story_synopsis",
        "main_conflict",
        "ending_direction",
        "global_outline",
        "selling_points",
    ):
        value = _extract_loose_json_string(raw, key)
        if value:
            recovered[key] = value

    volumes = _extract_loose_volumes(raw)
    if volumes:
        recovered["volumes"] = volumes
    return recovered


def _extract_loose_json_string(raw: str, key: str) -> str:
    marker = f'"{key}"'
    marker_index = raw.find(marker)
    if marker_index < 0:
        return ""
    colon_index = raw.find(":", marker_index + len(marker))
    if colon_index < 0:
        return ""
    start = raw.find('"', colon_index + 1)
    if start < 0:
        return ""

    chars: List[str] = []
    escaped = False
    for index in range(start + 1, len(raw)):
        char = raw[index]
        if escaped:
            if char == "n":
                chars.append("\n")
            elif char == "t":
                chars.append("\t")
            else:
                chars.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            remainder = raw[index + 1 :].lstrip()
            if not remainder or remainder.startswith((",", "}", "]")):
                return "".join(chars).strip()
        chars.append(char)
    return "".join(chars).strip()


def _extract_loose_json_number(raw: str, key: str) -> Optional[int]:
    marker = f'"{key}"'
    marker_index = raw.find(marker)
    if marker_index < 0:
        return None
    colon_index = raw.find(":", marker_index + len(marker))
    if colon_index < 0:
        return None
    index = colon_index + 1
    while index < len(raw) and raw[index].isspace():
        index += 1
    digits: List[str] = []
    while index < len(raw) and raw[index].isdigit():
        digits.append(raw[index])
        index += 1
    return int("".join(digits)) if digits else None


def _extract_loose_volumes(raw: str) -> List[Dict[str, Any]]:
    volumes: List[Dict[str, Any]] = []
    marker = '"volume_number"'
    search_start = 0
    while True:
        start = raw.find(marker, search_start)
        if start < 0:
            break
        next_volume = raw.find(marker, start + len(marker))
        chapters_start = raw.find('"chapters"', start)
        block_end_candidates = [
            candidate for candidate in (next_volume, chapters_start)
            if candidate > start
        ]
        block_end = min(block_end_candidates) if block_end_candidates else len(raw)
        block = raw[start:block_end]
        volume: Dict[str, Any] = {}
        number = _extract_loose_json_number(block, "volume_number")
        if number is not None:
            volume["volume_number"] = number
        for key in (
            "volume_title",
            "volume_summary",
            "core_conflict",
            "protagonist_growth",
            "volume_climax",
            "foreshadowing",
        ):
            value = _extract_loose_json_string(block, key)
            if value:
                volume[key] = value
        if volume:
            volumes.append(volume)
        search_start = block_end
    return volumes


def get_outline_volumes(payload: Any) -> List[Dict[str, Any]]:
    data = normalize_outline_payload(payload)
    if isinstance(data, dict):
        volumes = data.get("volumes")
        if isinstance(volumes, list):
            return [volume for volume in volumes if isinstance(volume, dict)]
    if isinstance(data, list):
        return [
            row for row in data
            if isinstance(row, dict)
            and (
                row.get("volume_number")
                or row.get("volume_title")
                or row.get("volume_summary")
                or row.get("volume_plan")
            )
        ]
    return []


def _normalize_outline_chapter_number(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        match = None
        if value is not None:
            import re

            match = re.search(r"\d+", str(value))
        number = int(match.group(0)) if match else int(fallback or 1)
    return number if number > 0 else int(fallback or 1)


def _is_outline_overview_row(row: Dict[str, Any]) -> bool:
    title = str(row.get("title") or row.get("name") or "").strip()
    return (
        title == "主线大纲"
        or bool(row.get("global_outline"))
        or bool(row.get("volume_plan"))
        or bool(row.get("volumes"))
    )


def _chapter_summary_from_outline_entry(entry: Dict[str, Any]) -> str:
    direct = (
        entry.get("summary")
        or entry.get("description")
        or entry.get("synopsis")
        or entry.get("chapter_goal")
        or entry.get("scene_goal")
        or entry.get("goal")
        or entry.get("key_event")
        or entry.get("core_event")
        or entry.get("content")
    )
    text = humanize_structured_value(direct).strip()
    if text and not is_pending_text(text):
        return text

    parts: List[str] = []
    for label, key in (
        ("章节目标", "chapter_goal"),
        ("关键事件", "key_event"),
        ("核心事件", "core_event"),
        ("冲突", "conflict"),
        ("情绪点", "emotion_point"),
        ("章末钩子", "ending_hook"),
    ):
        value = humanize_structured_value(entry.get(key)).strip()
        if value and not is_pending_text(value):
            parts.append(f"{label}：{value}")
    return "\n".join(parts).strip()


def extract_outline_chapter_rows(payload: Any, *, timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract executable per-chapter rows from raw, overview, or legacy outlines."""
    data = normalize_outline_payload(payload)
    now = timestamp or datetime.now().isoformat()
    rows: List[Dict[str, Any]] = []

    def append_chapter(entry: Any, fallback_number: int, volume_title: str = "") -> None:
        if isinstance(entry, dict):
            number = _normalize_outline_chapter_number(
                entry.get("chapter_number") or entry.get("chapter") or entry.get("number"),
                fallback_number,
            )
            title = str(
                entry.get("title")
                or entry.get("name")
                or entry.get("chapter_title")
                or f"第{number}章"
            ).strip() or f"第{number}章"
            summary = _chapter_summary_from_outline_entry(entry)
            row = dict(entry)
            row.update({
                "chapter_number": number,
                "title": title,
                "summary": summary,
                "content": strip_internal_author_markers(entry.get("content")),
                "created_at": entry.get("created_at") or now,
                "updated_at": entry.get("updated_at") or now,
            })
            if volume_title and not row.get("volume_title"):
                row["volume_title"] = volume_title
        else:
            number = int(fallback_number or 1)
            summary = humanize_structured_value(entry).strip()
            row = {
                "chapter_number": number,
                "title": f"第{number}章",
                "summary": summary,
                "content": "",
                "created_at": now,
                "updated_at": now,
            }
        rows.append(row)

    if isinstance(data, dict):
        next_number = 1
        for volume_index, volume in enumerate(get_outline_volumes(data), start=1):
            chapters = volume.get("chapters")
            if not isinstance(chapters, list):
                continue
            volume_title = str(
                volume.get("volume_title")
                or volume.get("title")
                or volume.get("name")
                or f"第{volume_index}卷"
            ).strip()
            for chapter in chapters:
                append_chapter(chapter, next_number, volume_title=volume_title)
                next_number += 1

        direct_chapters = data.get("chapters")
        if isinstance(direct_chapters, list):
            for chapter in direct_chapters:
                append_chapter(chapter, next_number)
                next_number += 1

    elif isinstance(data, list):
        next_number = 1
        for row in data:
            if not isinstance(row, dict):
                append_chapter(row, next_number)
                next_number += 1
                continue

            nested_rows = []
            if row.get("volumes") or row.get("chapters"):
                nested_rows = extract_outline_chapter_rows(row, timestamp=now)
            if nested_rows:
                rows.extend(nested_rows)
                next_number = max(
                    next_number,
                    max(int(item.get("chapter_number") or 0) for item in nested_rows) + 1,
                )
                continue

            if _is_outline_overview_row(row):
                continue
            append_chapter(row, next_number)
            next_number += 1

    deduped: Dict[int, Dict[str, Any]] = {}
    overflow: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        number = _normalize_outline_chapter_number(row.get("chapter_number"), index)
        row["chapter_number"] = number
        if number not in deduped:
            deduped[number] = row
        else:
            overflow.append(row)

    ordered = [deduped[number] for number in sorted(deduped)]
    if overflow:
        ordered.extend(overflow)
    return ordered


def build_global_outline_text(payload: Any) -> str:
    data = normalize_outline_payload(payload)

    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            text = strip_internal_author_markers(row.get("global_outline"))
            if text:
                return text
        for row in data:
            if not isinstance(row, dict):
                continue
            text = strip_internal_author_markers(row.get("summary") or row.get("description"))
            if text and not is_pending_text(text):
                return text
        return ""

    if not isinstance(data, dict):
        return ""

    global_outline = strip_internal_author_markers(data.get("global_outline"))
    if global_outline:
        return global_outline

    sections = [
        ("书名", data.get("title") or data.get("novel_title")),
        ("作者", data.get("author")),
        ("简介", data.get("intro") or data.get("theme")),
        ("故事梗概", data.get("story_synopsis") or data.get("synopsis") or data.get("main_plot")),
        ("一、【力量体系】", data.get("power_system")),
        ("二、【世界地图】", data.get("world_map") or data.get("geography")),
        ("三、【中心思想】", data.get("central_idea") or data.get("theme_statement")),
        ("四、【矛盾冲突】", data.get("main_conflict") or data.get("conflicts")),
        ("五、【前期剧情】", data.get("early_plot")),
        ("六、【叙事节奏】", data.get("narrative_pacing") or data.get("pacing")),
        ("七、【小说卖点】", data.get("selling_points")),
        ("八、【角色设定】", data.get("protagonist") or data.get("characters")),
    ]
    parts = []
    for title, value in sections:
        text = humanize_structured_value(value).strip()
        if text and not is_pending_text(text):
            parts.append(f"{title}\n{text}")

    legacy_chapter_summary = _legacy_chapter_summary_text(data)
    if legacy_chapter_summary and not any(part.startswith("故事梗概") for part in parts):
        parts.append(f"故事梗概\n{legacy_chapter_summary}")
    return "\n\n".join(parts).strip()


def _legacy_chapter_summary_text(data: Dict[str, Any]) -> str:
    """Compress old chapter-only outline payloads into a global synopsis."""
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        return ""

    summaries: List[str] = []
    titles: List[str] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        summary = strip_internal_author_markers(
            chapter.get("summary")
            or chapter.get("description")
            or chapter.get("synopsis")
        ).strip()
        if summary and not is_pending_text(summary):
            summaries.append(summary)
            continue
        title = strip_internal_author_markers(chapter.get("title") or chapter.get("name")).strip()
        if title and not is_pending_text(title):
            titles.append(title)

    source = summaries or titles
    if not source:
        return ""
    return " ".join(source).strip()


def format_outline_volume_plan(payload: Any) -> str:
    volumes = get_outline_volumes(payload)
    if not volumes:
        data = normalize_outline_payload(payload)
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    text = strip_internal_author_markers(row.get("volume_plan"))
                    if text:
                        return text
        return ""

    lines: List[str] = ["【分卷规划】"]
    for index, volume in enumerate(volumes, start=1):
        number = volume.get("volume_number") or volume.get("number") or index
        title = str(
            volume.get("volume_title")
            or volume.get("title")
            or volume.get("name")
            or f"第{number}卷"
        ).strip()
        header = f"第{number}卷：{title}" if not title.startswith("第") else title
        lines.append(header)

        fields = [
            ("本卷概述", volume.get("volume_summary") or volume.get("summary") or volume.get("description")),
            ("核心冲突", volume.get("core_conflict") or volume.get("conflict")),
            ("主角成长", volume.get("protagonist_growth") or volume.get("character_growth")),
            ("本卷高潮", volume.get("volume_climax") or volume.get("climax")),
            ("关键事件", volume.get("key_events") or volume.get("story_beats") or volume.get("major_events")),
        ]
        for label, value in fields:
            text = humanize_structured_value(value).strip()
            if text and not is_pending_text(text):
                lines.append(f"- {label}：{text}")
        lines.append("")
    return "\n".join(lines).strip()


def extract_outline_field(payload: Any, *keys: str) -> str:
    data = normalize_outline_payload(payload)
    if isinstance(data, dict):
        for key in keys:
            text = humanize_structured_value(data.get(key)).strip()
            if text and not is_pending_text(text):
                return text
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            for key in keys:
                text = humanize_structured_value(row.get(key)).strip()
                if text and not is_pending_text(text):
                    return text
    return ""


def build_outline_overview_row(payload: Any, *, timestamp: Optional[str] = None) -> Dict[str, Any]:
    data = normalize_outline_payload(payload)
    global_outline = build_global_outline_text(data)
    volume_plan = format_outline_volume_plan(data)
    if not global_outline and not volume_plan:
        return {}

    now = timestamp or datetime.now().isoformat()
    title = extract_outline_field(data, "title", "novel_title") or "主线大纲"
    row: Dict[str, Any] = {
        "title": "主线大纲",
        "name": "主线大纲",
        "summary": global_outline or volume_plan,
        "global_outline": global_outline,
        "volume_plan": volume_plan,
        "story_synopsis": extract_outline_field(data, "story_synopsis", "synopsis", "main_plot"),
        "conflicts": extract_outline_field(data, "main_conflict", "conflicts"),
        "selling_points": extract_outline_field(data, "selling_points"),
        "novel_title": title,
        "content": "",
        "created_at": now,
        "updated_at": now,
    }

    volumes = get_outline_volumes(data)
    if volumes:
        row["volumes"] = volumes
    return row


def extract_eventlines_from_outline(payload: Any) -> List[Dict[str, Any]]:
    """Extract explicit plot/event thread rows from a global outline payload."""
    data = normalize_outline_payload(payload)
    if not isinstance(data, dict):
        return []

    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(_collect_outline_eventline_entries(data), start=1):
        row = _eventline_row_from_entry(entry, fallback_id=f"outline_thread_{index}")
        if row:
            rows.append(row)

    for index, entry in enumerate(_collect_volume_eventline_entries(data), start=len(rows) + 1):
        row = _eventline_row_from_entry(entry, fallback_id=f"volume_thread_{index}")
        if row:
            rows.append(row)

    return _dedupe_eventline_rows(rows)


def merge_eventline_rows(
    existing_rows: Any,
    generated_rows: Any,
) -> List[Dict[str, Any]]:
    """Merge outline-derived eventlines without overwriting user-authored fields."""
    existing = [dict(row) for row in existing_rows if isinstance(row, dict)] if isinstance(existing_rows, list) else []
    generated = [dict(row) for row in generated_rows if isinstance(row, dict)] if isinstance(generated_rows, list) else []
    if not existing:
        return _dedupe_eventline_rows(generated)

    merged: List[Dict[str, Any]] = [dict(row) for row in existing]
    index_by_key: Dict[str, int] = {}
    for index, row in enumerate(merged):
        for key in _eventline_merge_keys(row):
            index_by_key.setdefault(key, index)

    for row in generated:
        keys = _eventline_merge_keys(row)
        match_index = next((index_by_key[key] for key in keys if key in index_by_key), None)
        if match_index is None:
            index_by_key.update({key: len(merged) for key in keys if key not in index_by_key})
            merged.append(dict(row))
            continue

        target = merged[match_index]
        for field, value in row.items():
            if _is_empty_project_value(target.get(field)) and not _is_empty_project_value(value):
                target[field] = value
        for key in _eventline_merge_keys(target):
            index_by_key.setdefault(key, match_index)

    return _dedupe_eventline_rows(merged)


def _collect_outline_eventline_entries(data: Dict[str, Any]) -> List[Any]:
    collected: List[Any] = []
    for key in (
        "plot_threads",
        "threads",
        "eventlines",
        "event_lines",
        "storylines",
        "story_lines",
    ):
        value = data.get(key)
        if isinstance(value, list):
            collected.extend(value)
        elif isinstance(value, dict):
            for item_key, item in value.items():
                if isinstance(item, dict):
                    copied = dict(item)
                    copied.setdefault("id", item_key)
                    copied.setdefault("thread_id", item_key)
                    collected.append(copied)
                else:
                    collected.append({"id": item_key, "thread_id": item_key, "name": item})

    recurring = data.get("recurring_elements")
    if isinstance(recurring, dict):
        foreshadowing = recurring.get("foreshadowing_threads")
        if isinstance(foreshadowing, list):
            for item in foreshadowing:
                if isinstance(item, str) and item.strip():
                    collected.append(
                        {
                            "name": item.strip(),
                            "description": item.strip(),
                            "thread_type": "subplot",
                            "source_scope": "recurring_foreshadowing",
                        }
                    )
                elif isinstance(item, dict):
                    copied = dict(item)
                    copied.setdefault("source_scope", "recurring_foreshadowing")
                    collected.append(copied)
    return collected


def _collect_volume_eventline_entries(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    volumes = get_outline_volumes(data)
    for volume_index, volume in enumerate(volumes, start=1):
        number = volume.get("volume_number") or volume.get("number") or volume_index
        volume_title = str(
            volume.get("volume_title")
            or volume.get("title")
            or volume.get("name")
            or f"第{number}卷"
        ).strip()

        for key in ("eventlines", "event_lines", "plot_threads", "threads", "storylines", "story_lines"):
            value = volume.get(key)
            if isinstance(value, dict):
                entries = []
                for item_key, item in value.items():
                    if isinstance(item, dict):
                        copied = dict(item)
                        copied.setdefault("id", item_key)
                        copied.setdefault("thread_id", item_key)
                    else:
                        copied = {"id": item_key, "thread_id": item_key, "name": item}
                    entries.append(copied)
            else:
                entries = value if isinstance(value, list) else []
            for entry in entries:
                if isinstance(entry, dict):
                    copied = dict(entry)
                else:
                    copied = {"name": str(entry or "").strip(), "description": str(entry or "").strip()}
                copied.setdefault("start_volume", number)
                copied.setdefault("volume_title", volume_title)
                copied.setdefault("source_scope", "volume_eventline")
                collected.append(copied)

        foreshadowing = humanize_structured_value(volume.get("foreshadowing")).strip()
        if foreshadowing and not is_pending_text(foreshadowing):
            collected.append(
                {
                    "name": f"{volume_title}伏笔线" if volume_title else f"第{number}卷伏笔线",
                    "description": foreshadowing,
                    "conflict": foreshadowing,
                    "thread_type": "subplot",
                    "status": "planned",
                    "start_volume": number,
                    "volume_title": volume_title,
                    "source_scope": "volume_foreshadowing",
                }
            )
    return collected


def _eventline_row_from_entry(entry: Any, *, fallback_id: str) -> Dict[str, Any]:
    if isinstance(entry, str):
        text = entry.strip()
        if not text or is_pending_text(text):
            return {}
        return {
            "id": fallback_id,
            "thread_id": fallback_id,
            "name": text,
            "description": text,
            "participants": "",
            "conflict": text,
            "status": "planned",
            "thread_title": text,
            "thread_type": "subplot",
            "objective": text,
            "source": "outline",
        }

    if not isinstance(entry, dict):
        return {}

    name = _first_outline_text(entry, "name", "title", "thread_title", "id", "thread_id")
    description = _first_outline_text(
        entry,
        "description",
        "summary",
        "objective",
        "goal",
        "conflict",
        "core_conflict",
        "content",
    )
    if not name and not description:
        return {}

    thread_id = _first_outline_text(entry, "thread_id", "id", "key") or fallback_id
    thread_title = _first_outline_text(entry, "thread_title", "title", "name") or name or thread_id
    thread_type = _first_outline_text(entry, "thread_type", "type", "kind") or "subplot"
    if str(thread_id).strip() == "main":
        thread_type = "main"

    row: Dict[str, Any] = {
        "id": thread_id,
        "thread_id": thread_id,
        "name": name or thread_title,
        "description": description or name or thread_title,
        "participants": humanize_structured_value(
            entry.get("participants") or entry.get("characters") or entry.get("roles") or entry.get("actors")
        ).strip(),
        "conflict": _first_outline_text(entry, "conflict", "core_conflict", "obstacle") or description,
        "status": _first_outline_text(entry, "status") or ("active" if thread_type == "main" else "planned"),
        "thread_title": thread_title,
        "thread_type": str(thread_type).strip().lower() or "subplot",
        "objective": _first_outline_text(entry, "objective", "goal", "thread_objective") or description,
        "source": "outline",
    }

    for source_key, target_key in (
        ("start_volume", "start_volume"),
        ("volume_number", "start_volume"),
        ("volume", "start_volume"),
        ("start_chapter", "start_chapter"),
        ("chapter_start", "start_chapter"),
        ("first_chapter", "start_chapter"),
        ("entry_chapter", "start_chapter"),
        ("return_by_chapter", "target_return_chapter"),
        ("return_by", "target_return_chapter"),
        ("target_return_chapter", "target_return_chapter"),
        ("max_consecutive_chapters", "max_consecutive_chapters"),
        ("max_streak", "max_consecutive_chapters"),
    ):
        number = _to_positive_int(entry.get(source_key))
        if number:
            row[target_key] = number

    for key in ("volume_title", "source_scope"):
        value = _first_outline_text(entry, key)
        if value:
            row[key] = value

    return {key: value for key, value in row.items() if not _is_empty_project_value(value)}


def _dedupe_eventline_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    index_by_key: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = _eventline_merge_keys(row)
        match_index = next((index_by_key[key] for key in keys if key in index_by_key), None)
        if match_index is None:
            index_by_key.update({key: len(deduped) for key in keys if key not in index_by_key})
            deduped.append(dict(row))
            continue
        target = deduped[match_index]
        for field, value in row.items():
            if _is_empty_project_value(target.get(field)) and not _is_empty_project_value(value):
                target[field] = value
    return deduped


def _eventline_merge_keys(row: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for field in ("thread_id", "id", "name", "title", "thread_title"):
        value = str(row.get(field) or "").strip().lower()
        if value and value not in keys:
            keys.append(value)
    return keys


def _first_outline_text(source: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        text = humanize_structured_value(value).strip()
        if text and not is_pending_text(text):
            return text
    return ""


def _is_empty_project_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return is_pending_text(value.strip())
    if isinstance(value, (list, dict)):
        return not value
    return False


def _to_positive_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
