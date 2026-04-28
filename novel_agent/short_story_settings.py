"""短篇超时设置兼容层。"""

from __future__ import annotations

from typing import Dict, Mapping

from .timeout_settings import (
    DEFAULT_SHORT_STORY_TIMEOUTS,
    SHORT_STORY_TIMEOUT_MAX,
    SHORT_STORY_TIMEOUT_MIN,
    get_short_story_timeout_settings,
    save_timeout_settings,
)


def save_short_story_timeout_settings(updates: Mapping[str, object]) -> Dict[str, int]:
    return save_timeout_settings({"short_story": updates})["short_story"]
