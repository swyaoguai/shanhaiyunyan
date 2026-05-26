"""Helpers for tagging project knowledge by product mode/source."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

SOURCE_TAG_PREFIX = "source:"

SOURCE_MODE_LABELS: Dict[str, str] = {
    "multi_agent": "多Agent",
    "infinite_write": "无限续写",
    "manual": "手动创建",
    "manual_import": "手动导入",
    "unknown": "未标记",
}

_SOURCE_MODE_ALIASES = {
    "multi-agent": "multi_agent",
    "multiagent": "multi_agent",
    "copilot": "multi_agent",
    "copilot_chat": "multi_agent",
    "chat": "multi_agent",
    "agent": "multi_agent",
    "infinite-write": "infinite_write",
    "infinite": "infinite_write",
    "continuous_write": "infinite_write",
    "continuous-write": "infinite_write",
    "iw": "infinite_write",
    "import": "manual_import",
    "manual-import": "manual_import",
    "file_import": "manual_import",
    "file-import": "manual_import",
    "user": "manual",
}


def normalize_source_mode(value: Any, default: str = "") -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if not raw:
        return default
    raw = _SOURCE_MODE_ALIASES.get(raw, raw)
    return raw if raw in SOURCE_MODE_LABELS and raw != "unknown" else default


def source_mode_tag(source_mode: Any) -> str:
    normalized = normalize_source_mode(source_mode)
    return f"{SOURCE_TAG_PREFIX}{normalized}" if normalized else ""


def normalize_tags(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []
    normalized: List[str] = []
    seen = set()
    for tag in tags:
        text = str(tag or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def source_mode_from_tags(tags: Any) -> str:
    for tag in normalize_tags(tags):
        text = tag.strip()
        if text.lower().startswith(SOURCE_TAG_PREFIX):
            return normalize_source_mode(text[len(SOURCE_TAG_PREFIX):])
    return ""


def source_mode_from_record(record: Any, default: str = "") -> str:
    if not isinstance(record, dict):
        return default
    direct = normalize_source_mode(record.get("source_mode"))
    if direct:
        return direct
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        nested = normalize_source_mode(metadata.get("source_mode"))
        if nested:
            return nested
    tagged = source_mode_from_tags(record.get("tags"))
    if tagged:
        return tagged
    source = str(record.get("source") or record.get("source_type") or "").strip().lower()
    if source in {"copilot_auto_save", "copilot_chat", "contract_confirmation"}:
        return "multi_agent"
    if source == "infinite_write":
        return "infinite_write"
    if record.get("source_file"):
        return "manual_import"
    return default


def ensure_source_tag(tags: Any, source_mode: Any) -> List[str]:
    normalized_tags = normalize_tags(tags)
    normalized_mode = normalize_source_mode(source_mode)
    if not normalized_mode:
        return normalized_tags
    wanted = source_mode_tag(normalized_mode)
    if not any(tag.lower().startswith(SOURCE_TAG_PREFIX) for tag in normalized_tags):
        normalized_tags.append(wanted)
    return normalized_tags


def ensure_record_source_mode(
    record: Any,
    source_mode: Any,
    *,
    source_type: Optional[str] = None,
    source_session_id: Optional[str] = None,
    source_file: Optional[str] = None,
    overwrite: bool = False,
) -> Any:
    """Return a copy of a dict record with source_mode and source tag filled."""

    if not isinstance(record, dict):
        return record
    row = dict(record)
    normalized = normalize_source_mode(source_mode)
    existing = source_mode_from_record(row)
    effective = normalized if overwrite or not existing else existing
    if effective and (overwrite or not row.get("source_mode")):
        row["source_mode"] = effective
    if source_type and (overwrite or not row.get("source_type")):
        row["source_type"] = source_type
    if source_session_id and (overwrite or not row.get("source_session_id")):
        row["source_session_id"] = source_session_id
    if source_file and (overwrite or not row.get("source_file")):
        row["source_file"] = source_file
    if effective:
        row["tags"] = ensure_source_tag(row.get("tags"), effective)
    return row


def annotate_payload_source(
    payload: Any,
    source_mode: Any,
    *,
    source_type: Optional[str] = None,
    overwrite: bool = False,
) -> Any:
    """Tag common project-data payload shapes while preserving their structure."""

    normalized = normalize_source_mode(source_mode)
    if not normalized:
        return payload
    if isinstance(payload, list):
        return [
            ensure_record_source_mode(item, normalized, source_type=source_type, overwrite=overwrite)
            if isinstance(item, dict)
            else item
            for item in payload
        ]
    if not isinstance(payload, dict):
        return payload

    result = ensure_record_source_mode(payload, normalized, source_type=source_type, overwrite=overwrite)
    for key in ("world",):
        if isinstance(result.get(key), dict):
            result[key] = ensure_record_source_mode(
                result[key],
                normalized,
                source_type=source_type,
                overwrite=overwrite,
            )
    for key in ("characters", "items", "locations"):
        value = result.get(key)
        if isinstance(value, dict):
            result[key] = {
                name: ensure_record_source_mode(item, normalized, source_type=source_type, overwrite=overwrite)
                if isinstance(item, dict)
                else item
                for name, item in value.items()
            }
        elif isinstance(value, list):
            result[key] = annotate_payload_source(value, normalized, source_type=source_type, overwrite=overwrite)
    for key in ("chapters", "events", "factions"):
        if isinstance(result.get(key), list):
            result[key] = annotate_payload_source(result[key], normalized, source_type=source_type, overwrite=overwrite)
    return result
