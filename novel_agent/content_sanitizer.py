"""Sanitizers for text that is displayed or persisted as author-facing content."""

from __future__ import annotations

import json
import re
from typing import Any, List


_INTERNAL_HTML_COMMENT_RE = re.compile(
    r"<!--\s*(?:PLOT_THREAD|THREAD_STATE|INTERNAL|SYSTEM)[\s\S]*?-->",
    flags=re.IGNORECASE,
)
_INTERNAL_AUTHOR_LINE_RE = re.compile(
    r"(?im)^\s*(?:作者|author)\s*[:：]\s*(?:AI\s*助手|AI\s*创作|人工智能助手)\s*$"
)

_STRUCTURED_LABELS = {
    "abilities": "能力",
    "continents": "大陆/区域",
    "core_concept": "核心概念",
    "cost": "代价",
    "cultivation_method": "修炼方式",
    "cultivation method": "修炼方式",
    "special_locations": "特殊地点",
    "key_locations": "关键地点",
    "environment": "环境",
    "faction_control": "势力控制",
    "factions": "势力",
    "levels": "境界层级",
    "limitations": "限制与代价",
    "locations": "地点",
    "power_system": "力量体系",
    "power_levels": "力量层级",
    "geography": "地理环境",
    "history": "历史背景",
    "items": "物品/设定条目",
    "culture": "文化习俗",
    "magic_system": "修炼体系",
    "method": "方式",
    "rules": "规则",
    "special_abilities": "特殊能力",
    "special abilities": "特殊能力",
    "taboos": "禁忌",
    "technology_level": "技术水平",
    "timeline": "时间线",
}

_STRUCTURED_LABEL_ALIASES = {
    re.sub(r"[\s_-]+", " ", key).strip().lower(): label
    for key, label in _STRUCTURED_LABELS.items()
}

_TEXT_LABEL_REPLACEMENTS = [
    (re.compile(r"(?i)(^|[；;，,\n]\s*)levels\s*[:：]\s*"), r"\1境界层级："),
    (re.compile(r"(?i)(^|[；;，,\n]\s*)cultivation\s+method\s*[:：]\s*"), r"\1修炼方式："),
    (re.compile(r"(?i)(^|[；;，,\n]\s*)special\s+abilities\s*[:：]\s*"), r"\1特殊能力："),
    (re.compile(r"(?i)(^|[；;，,\n]\s*)limitations\s*[:：]\s*"), r"\1限制与代价："),
    (re.compile(r"(?i)(^|[；;，,\n]\s*)power\s+system\s*[:：]\s*"), r"\1力量体系："),
]

def _localized_structured_label(key: Any) -> str:
    raw = str(key).strip()
    if not raw:
        return ""
    normalized = re.sub(r"[\s_-]+", " ", raw).strip().lower()
    return _STRUCTURED_LABEL_ALIASES.get(normalized) or raw.replace("_", " ")


def localize_structured_labels(text: Any) -> str:
    """Translate common generated schema labels in author-facing text."""
    value = str(text or "")
    if not value:
        return ""
    for pattern, replacement in _TEXT_LABEL_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    return value


def strip_internal_author_markers(text: Any) -> str:
    """Remove internal coordination markers from prose shown to the author."""
    value = str(text or "")
    if not value:
        return ""
    value = _INTERNAL_HTML_COMMENT_RE.sub("", value)
    value = _INTERNAL_AUTHOR_LINE_RE.sub("", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return localize_structured_labels(value.strip())


def humanize_structured_value(value: Any, *, max_items: int = 8, depth: int = 0) -> str:
    """Render dict/list payloads as readable notes instead of raw JSON blobs."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = strip_internal_author_markers(value)
        if text[:1] in {"{", "["}:
            try:
                return humanize_structured_value(
                    json.loads(text),
                    max_items=max_items,
                    depth=depth + 1,
                )
            except Exception:
                return text
        return text
    if isinstance(value, (int, float, bool)):
        return str(value)
    if depth > 2:
        return str(value)

    if isinstance(value, list):
        parts: List[str] = []
        for item in value[:max_items]:
            text = humanize_structured_value(item, max_items=max_items, depth=depth + 1)
            if text:
                parts.append(text)
        if len(value) > max_items:
            parts.append(f"等{len(value)}项")
        separator = "\n" if any("\n" in part for part in parts) else "、"
        return separator.join(parts)

    if isinstance(value, dict):
        priority_keys = (
            "name",
            "title",
            "description",
            "summary",
            "content",
            "significance",
            "environment",
            "goal",
            "leader",
            "impact",
            "details",
        )
        lines: List[str] = []

        for key in priority_keys:
            if key not in value:
                continue
            text = humanize_structured_value(value.get(key), max_items=max_items, depth=depth + 1)
            if text:
                lines.append(text)

        for key, item in value.items():
            if key in priority_keys:
                continue
            text = humanize_structured_value(item, max_items=max_items, depth=depth + 1)
            if text:
                label = _localized_structured_label(key)
                lines.append(f"{label}：{text}")
            if len(lines) >= max_items:
                break

        return "；".join(lines)

    return str(value).strip()
