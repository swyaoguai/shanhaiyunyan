"""Runtime endpoints for the packaged desktop app."""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...version import get_app_version

logger = logging.getLogger(__name__)

router = APIRouter()

EXPLICIT_SHUTDOWN_DELAY_SECONDS = 0.2


class BrowserWindowEvent(BaseModel):
    window_id: str = ""


class AppShutdownRequest(BaseModel):
    reason: str = "user_request"


def _window_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:120]


def _shutdown_reason(value: Any) -> str:
    text = str(value or "").strip()
    return (text or "user_request")[:120]


def _terminate_process(reason: str) -> None:
    logger.info("[Runtime] Explicit app shutdown requested: %s", reason)
    os._exit(0)


def _is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _schedule_process_exit(delay_seconds: float, reason: str) -> None:
    delay = max(float(delay_seconds or 0.0), 0.1)
    timer = threading.Timer(delay, _terminate_process, args=(reason,))
    timer.daemon = True
    timer.start()


def request_app_shutdown(reason: str = "user_request") -> Dict[str, Any]:
    if not _is_packaged_app():
        return {
            "accepted": False,
            "packaged": False,
            "reason": "not_packaged",
        }

    normalized_reason = _shutdown_reason(reason)
    _schedule_process_exit(EXPLICIT_SHUTDOWN_DELAY_SECONDS, normalized_reason)
    return {
        "accepted": True,
        "packaged": True,
        "reason": normalized_reason,
    }


def record_browser_window_heartbeat(window_id: str) -> Dict[str, Any]:
    _window_id(window_id)
    return {"enabled": False, "active_windows": 0, "scheduled_shutdown": False}


def record_browser_window_closed(window_id: str) -> Dict[str, Any]:
    _window_id(window_id)
    return {"enabled": False, "active_windows": 0, "scheduled_shutdown": False}


def _reset_browser_window_state_for_tests() -> None:
    return None


@router.get("/app/runtime")
async def runtime_info():
    packaged = _is_packaged_app()
    return {
        "app_name": "山海·云烟",
        "version": get_app_version(),
        "packaged": packaged,
        "close_shutdown_enabled": False,
        "explicit_shutdown_enabled": packaged,
    }


@router.post("/app/window-heartbeat")
async def browser_window_heartbeat(event: BrowserWindowEvent):
    return record_browser_window_heartbeat(event.window_id)


@router.post("/app/window-closed")
async def browser_window_closed(event: BrowserWindowEvent):
    return record_browser_window_closed(event.window_id)


@router.post("/app/shutdown")
async def app_shutdown(event: AppShutdownRequest):
    result = request_app_shutdown(event.reason)
    if not result["accepted"]:
        raise HTTPException(status_code=409, detail="App shutdown is only available in packaged builds")
    return result
