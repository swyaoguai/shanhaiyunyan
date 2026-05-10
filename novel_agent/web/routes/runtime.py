"""Runtime lifecycle endpoints for the packaged desktop app."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

BROWSER_HEARTBEAT_INTERVAL_SECONDS = 5.0
BROWSER_STALE_AFTER_SECONDS = 20.0
BROWSER_CLOSE_GRACE_SECONDS = 8.0

_active_browser_windows: Dict[str, float] = {}
_state_lock = threading.RLock()
_shutdown_timer: Optional[threading.Timer] = None


class BrowserWindowEvent(BaseModel):
    window_id: str = ""


def _browser_close_shutdown_enabled() -> bool:
    """Only auto-close the process in packaged desktop builds unless explicitly enabled."""
    if os.getenv("SHANHAI_DISABLE_BROWSER_CLOSE_SHUTDOWN", "").strip() == "1":
        return False
    if os.getenv("SHANHAI_ENABLE_BROWSER_CLOSE_SHUTDOWN", "").strip() == "1":
        return True
    return bool(getattr(sys, "frozen", False))


def _window_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:120]


def _prune_stale_windows_locked(now: Optional[float] = None) -> None:
    current = time.monotonic() if now is None else now
    stale_before = current - BROWSER_STALE_AFTER_SECONDS
    for window_id, last_seen in list(_active_browser_windows.items()):
        if last_seen < stale_before:
            _active_browser_windows.pop(window_id, None)


def _cancel_shutdown_timer_locked() -> None:
    global _shutdown_timer
    if _shutdown_timer is not None:
        _shutdown_timer.cancel()
        _shutdown_timer = None


def _terminate_process(reason: str) -> None:
    logger.info("[Runtime] Browser window closed, exiting packaged app: %s", reason)
    os._exit(0)


def _shutdown_if_no_active_windows(reason: str) -> None:
    if not _browser_close_shutdown_enabled():
        return
    with _state_lock:
        _prune_stale_windows_locked()
        if _active_browser_windows:
            return
    _terminate_process(reason)


def _schedule_shutdown_check(delay_seconds: float, reason: str) -> bool:
    if not _browser_close_shutdown_enabled():
        return False
    delay = max(float(delay_seconds or 0.0), 0.1)
    with _state_lock:
        _cancel_shutdown_timer_locked()
        timer = threading.Timer(delay, _shutdown_if_no_active_windows, args=(reason,))
        timer.daemon = True
        globals()["_shutdown_timer"] = timer
        timer.start()
    return True


def record_browser_window_heartbeat(window_id: str) -> Dict[str, Any]:
    normalized_id = _window_id(window_id)
    enabled = _browser_close_shutdown_enabled()
    if not enabled:
        return {"enabled": False, "active_windows": 0, "scheduled_shutdown": False}
    if not normalized_id:
        return {"enabled": True, "active_windows": len(_active_browser_windows), "scheduled_shutdown": False}

    with _state_lock:
        _active_browser_windows[normalized_id] = time.monotonic()
        active_count = len(_active_browser_windows)
    scheduled = _schedule_shutdown_check(
        BROWSER_STALE_AFTER_SECONDS + BROWSER_CLOSE_GRACE_SECONDS,
        "browser_heartbeat_expired",
    )
    return {"enabled": True, "active_windows": active_count, "scheduled_shutdown": scheduled}


def record_browser_window_closed(window_id: str) -> Dict[str, Any]:
    normalized_id = _window_id(window_id)
    enabled = _browser_close_shutdown_enabled()
    if not enabled:
        return {"enabled": False, "active_windows": 0, "scheduled_shutdown": False}

    with _state_lock:
        if normalized_id:
            _active_browser_windows.pop(normalized_id, None)
        _prune_stale_windows_locked()
        active_count = len(_active_browser_windows)

    scheduled = False
    if active_count == 0:
        scheduled = _schedule_shutdown_check(BROWSER_CLOSE_GRACE_SECONDS, "browser_window_closed")
    return {"enabled": True, "active_windows": active_count, "scheduled_shutdown": scheduled}


def _reset_browser_window_state_for_tests() -> None:
    with _state_lock:
        _active_browser_windows.clear()
        _cancel_shutdown_timer_locked()


@router.get("/app/runtime")
async def runtime_info():
    enabled = _browser_close_shutdown_enabled()
    return {
        "packaged": bool(getattr(sys, "frozen", False)),
        "close_shutdown_enabled": enabled,
        "heartbeat_interval_ms": int(BROWSER_HEARTBEAT_INTERVAL_SECONDS * 1000),
        "stale_after_ms": int(BROWSER_STALE_AFTER_SECONDS * 1000),
        "close_grace_ms": int(BROWSER_CLOSE_GRACE_SECONDS * 1000),
    }


@router.post("/app/window-heartbeat")
async def browser_window_heartbeat(event: BrowserWindowEvent):
    return record_browser_window_heartbeat(event.window_id)


@router.post("/app/window-closed")
async def browser_window_closed(event: BrowserWindowEvent):
    return record_browser_window_closed(event.window_id)
