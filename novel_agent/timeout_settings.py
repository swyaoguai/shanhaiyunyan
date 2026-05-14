"""全局超时设置。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Mapping, MutableMapping

from .utils.atomic_write import atomic_write_json
from .constants import get_data_dir

logger = logging.getLogger(__name__)

LLM_TIMEOUT_RANGES: Dict[str, Dict[str, int]] = {
    "connect": {"min": 5, "max": 300},
    "read": {"min": 30, "max": 3600},
    "write": {"min": 10, "max": 600},
    "pool": {"min": 5, "max": 300},
}

DEFAULT_LLM_TIMEOUTS: Dict[str, int] = {
    "connect": 60,
    "read": 600,
    "write": 120,
    "pool": 60,
}

SHORT_STORY_TIMEOUT_MIN = 30
SHORT_STORY_TIMEOUT_MAX = 3600  # 增加最大超时限制到1小时
SHORT_STORY_TIMEOUT_RANGE: Dict[str, int] = {
    "min": SHORT_STORY_TIMEOUT_MIN,
    "max": SHORT_STORY_TIMEOUT_MAX,
}

DEFAULT_SHORT_STORY_TIMEOUTS: Dict[str, int] = {
    "input_analysis": 120,
    "fusion": 180,
    "synopsis": 120,
    "outline": 180,
    "chapter": 300,
    "quality": 1800,  # 增加质量检查超时到30分钟
    "coherence": 1800,  # 增加复审超时到30分钟
    "title": 120,
    "tags": 120,
}

DEFAULT_TIMEOUT_SETTINGS: Dict[str, Dict[str, int]] = {
    "llm": DEFAULT_LLM_TIMEOUTS,
    "short_story": DEFAULT_SHORT_STORY_TIMEOUTS,
}

TIMEOUT_SETTINGS_FILE: Path | None = None


def get_timeout_settings_file() -> Path:
    """Return the writable timeout settings path for the current runtime root."""
    if TIMEOUT_SETTINGS_FILE is not None:
        return Path(TIMEOUT_SETTINGS_FILE)
    return get_data_dir() / "timeout_settings.json"


def _coerce_llm_timeout(key: str, value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"LLM 超时“{key}”必须是整数秒。") from exc

    min_value = LLM_TIMEOUT_RANGES[key]["min"]
    max_value = LLM_TIMEOUT_RANGES[key]["max"]
    if timeout < min_value or timeout > max_value:
        raise ValueError(f"LLM 超时“{key}”必须在 {min_value}~{max_value} 秒之间。")
    return timeout


def _coerce_short_story_timeout(step: str, value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"步骤“{step}”的超时必须是整数秒。") from exc

    if timeout < SHORT_STORY_TIMEOUT_MIN or timeout > SHORT_STORY_TIMEOUT_MAX:
        raise ValueError(
            f"步骤“{step}”的超时必须在 {SHORT_STORY_TIMEOUT_MIN}~{SHORT_STORY_TIMEOUT_MAX} 秒之间。"
        )
    return timeout


def _normalize_llm_timeouts(payload: Mapping[str, object] | None) -> Dict[str, int]:
    source = payload or {}
    normalized: Dict[str, int] = {}
    for key, default_timeout in DEFAULT_LLM_TIMEOUTS.items():
        try:
            normalized[key] = _coerce_llm_timeout(key, source.get(key, default_timeout))
        except ValueError as exc:
            logger.warning("Invalid LLM timeout for %s: %s", key, exc)
            normalized[key] = default_timeout
    return normalized


def _normalize_short_story_timeouts(payload: Mapping[str, object] | None) -> Dict[str, int]:
    source = payload or {}
    normalized: Dict[str, int] = {}
    for step, default_timeout in DEFAULT_SHORT_STORY_TIMEOUTS.items():
        try:
            normalized[step] = _coerce_short_story_timeout(step, source.get(step, default_timeout))
        except ValueError as exc:
            logger.warning("Invalid short story timeout for %s: %s", step, exc)
            normalized[step] = default_timeout
    return normalized


def get_timeout_settings() -> Dict[str, Dict[str, int]]:
    payload = {}
    settings_file = get_timeout_settings_file()
    if settings_file.exists():
        try:
            payload = json.loads(settings_file.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Failed to load timeout settings: %s", exc)

    return {
        "llm": _normalize_llm_timeouts(payload.get("llm")),
        "short_story": _normalize_short_story_timeouts(payload.get("short_story")),
    }


def get_timeout_setting_ranges() -> Dict[str, Dict[str, Dict[str, int]] | Dict[str, int]]:
    return {
        "llm": LLM_TIMEOUT_RANGES,
        "short_story": SHORT_STORY_TIMEOUT_RANGE,
    }


def get_llm_timeout_settings() -> Dict[str, int]:
    return get_timeout_settings()["llm"]


def get_short_story_timeout_settings() -> Dict[str, int]:
    return get_timeout_settings()["short_story"]


def save_timeout_settings(updates: Mapping[str, Mapping[str, object]]) -> Dict[str, Dict[str, int]]:
    current = get_timeout_settings()
    next_settings: MutableMapping[str, Dict[str, int]] = {
        "llm": dict(current["llm"]),
        "short_story": dict(current["short_story"]),
    }

    llm_updates = updates.get("llm") or {}
    for key in DEFAULT_LLM_TIMEOUTS:
        if key in llm_updates and llm_updates[key] is not None:
            next_settings["llm"][key] = _coerce_llm_timeout(key, llm_updates[key])

    short_story_updates = updates.get("short_story") or {}
    for step in DEFAULT_SHORT_STORY_TIMEOUTS:
        if step in short_story_updates and short_story_updates[step] is not None:
            next_settings["short_story"][step] = _coerce_short_story_timeout(step, short_story_updates[step])

    settings_file = get_timeout_settings_file()
    old_content = (
        settings_file.read_text(encoding="utf-8")
        if settings_file.exists()
        else None
    )
    atomic_write_json(
        settings_file,
        next_settings,
        old_content=old_content,
        ensure_ascii=False,
        indent=2,
    )
    return dict(next_settings)
