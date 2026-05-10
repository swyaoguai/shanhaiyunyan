"""Helpers for turning agent/protocol output into user-visible text."""

import json
import re
from typing import Any, Callable, Iterator, Optional


Localizer = Optional[Callable[[str], str]]

_VISIBLE_TEXT_FIELDS = ("reply", "response", "content", "message", "text", "summary", "result_summary")
_PREFERRED_TEXT_FIELDS = ("reply", "response")
_NESTED_PAYLOAD_FIELDS = ("delegated_result", "result", "data", "payload", "output")
_TECHNICAL_FRAGMENT_KEYS = (
    "_id",
    "id",
    "source",
    "source_preview",
    "source_type",
    "created_at",
    "updated_at",
    "revision_notes",
    "metadata",
)


def _apply_localizer(text: str, localizer: Localizer = None) -> str:
    return localizer(text) if localizer else text


def _strip_basic_markers(text: Any) -> str:
    value = str(text or "").replace("[INFO_COMPLETE]", "").strip()
    value = re.sub(r"<\|[^|]*\|>", "", value).strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\s*```$", "", value).strip()
    return value


def _iter_json_objects(text: str) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        yield payload


def _remove_json_objects(text: str) -> str:
    decoder = json.JSONDecoder()
    chunks = []
    cursor = 0
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except ValueError:
            index += 1
            continue
        chunks.append(text[cursor:index])
        cursor = index + end
        index = cursor
    chunks.append(text[cursor:])
    return "".join(chunks).strip()


def _extract_visible_from_payload(payload: Any, depth: int = 0) -> str:
    if depth > 5:
        return ""

    if isinstance(payload, dict):
        for field in _PREFERRED_TEXT_FIELDS:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for field in _VISIBLE_TEXT_FIELDS:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for field in _NESTED_PAYLOAD_FIELDS:
            nested = payload.get(field)
            visible = _extract_visible_from_payload(nested, depth + 1)
            if visible:
                return visible
        return ""

    if isinstance(payload, list):
        parts = [_extract_visible_from_payload(item, depth + 1) for item in payload]
        return "\n".join(part for part in parts if part).strip()

    return ""


def extract_visible_text_from_jsonish(text: Any) -> str:
    value = _strip_basic_markers(text)
    if not value:
        return ""

    for payload in _iter_json_objects(value):
        visible = _extract_visible_from_payload(payload)
        if visible:
            return _strip_basic_markers(visible)
    return ""


def strip_visible_technical_markers(text: Any, localizer: Localizer = None) -> str:
    value = _strip_basic_markers(text)
    if not value:
        return ""

    if looks_like_metadata_fragment(value):
        return ""
    visible = extract_visible_text_from_jsonish(value)
    if visible:
        return _apply_localizer(visible, localizer)
    if looks_like_jsonish_prefix(value):
        return ""
    without_json = _remove_json_objects(value)
    if without_json != value:
        without_json = without_json.strip(" \t\r\n:：-—")
        if without_json in {"子助手返回", "助手返回", "返回", "结果", "输出"}:
            return ""
        return _apply_localizer(without_json, localizer)
    return _apply_localizer(value, localizer)


def looks_like_jsonish_prefix(text: Any) -> bool:
    value = _strip_basic_markers(text).lstrip()
    if not value:
        return False
    if value.startswith("data:"):
        value = value[5:].lstrip()
    return value.startswith("{") or value.startswith("[")


def looks_like_metadata_fragment(text: Any) -> bool:
    value = _strip_basic_markers(text)
    if not value:
        return False
    if re.search(r"[\u4e00-\u9fff]", value):
        return False

    lines = [line.strip().strip(",;") for line in value.splitlines() if line.strip()]
    if not lines or len(lines) > 16:
        return False
    lower_text = value.lower()
    if not any(key in lower_text for key in _TECHNICAL_FRAGMENT_KEYS):
        return False
    return all(len(line) <= 80 for line in lines)


def stream_visible_text(text: Any, localizer: Localizer = None) -> Optional[str]:
    value = _strip_basic_markers(text)
    if not value:
        return ""

    if looks_like_metadata_fragment(value):
        return ""
    visible = extract_visible_text_from_jsonish(value)
    if visible:
        return _apply_localizer(visible, localizer)
    if looks_like_jsonish_prefix(value):
        return None
    return _apply_localizer(value, localizer)
