"""Helpers for refreshing runtime state after config reload."""

import logging
from typing import Any, Dict

from ..config import config
from ..workflow import NovelCoordinator
from ..agents import get_chat_session_store, get_session_store
from .dependencies import get_coordinator, get_router_agent, set_coordinator
from .websocket import WebSocketProgressCallback


logger = logging.getLogger(__name__)


def create_runtime_coordinator() -> NovelCoordinator:
    """Create a coordinator with the standard websocket progress callback."""
    ws_callback = WebSocketProgressCallback()
    return NovelCoordinator(
        config.paths.output_dir,
        progress_callback=ws_callback,
    )



def refresh_runtime_after_config_reload() -> NovelCoordinator:
    """Recreate coordinator and sync the existing router to the new instance."""
    new_coordinator = create_runtime_coordinator()
    set_coordinator(new_coordinator)

    router_agent = get_router_agent()
    if router_agent and hasattr(router_agent, "set_coordinator"):
        router_agent.set_coordinator(new_coordinator)

    return new_coordinator


def refresh_runtime_after_project_switch(previous_project_id: str, current_project_id: str) -> Dict[str, Any]:
    """同步项目切换后的运行态，并清理旧项目的内存缓存。"""
    previous_project_id = str(previous_project_id or "").strip()
    current_project_id = str(current_project_id or "").strip()

    chat_cache_cleared = 0
    session_cache_cleared = 0
    continuous_writer_cache_cleared = 0
    coordinator_switched = False

    if previous_project_id and previous_project_id != current_project_id:
        try:
            chat_cache_cleared = get_chat_session_store().clear_project_cache(previous_project_id)
        except Exception as exc:
            logger.warning(f"[RuntimeRefresh] 清理聊天会话缓存失败: {exc}")

        try:
            session_cache_cleared = get_session_store().clear_project_cache(previous_project_id)
        except Exception as exc:
            logger.warning(f"[RuntimeRefresh] 清理续写会话缓存失败: {exc}")

        try:
            from .routes.continuous_write import clear_project_runtime

            continuous_writer_cache_cleared = clear_project_runtime(previous_project_id)
        except Exception as exc:
            logger.warning(f"[RuntimeRefresh] 清理续写运行态失败: {exc}")

    coordinator = get_coordinator()
    if coordinator and hasattr(coordinator, "switch_to_project"):
        coordinator_switched = bool(coordinator.switch_to_project(current_project_id))

    router_agent = get_router_agent()
    if router_agent and hasattr(router_agent, "_continuous_writer"):
        router_agent._continuous_writer = None

    return {
        "previous_project_id": previous_project_id,
        "current_project_id": current_project_id,
        "chat_cache_cleared": chat_cache_cleared,
        "session_cache_cleared": session_cache_cleared,
        "continuous_writer_cache_cleared": continuous_writer_cache_cleared,
        "coordinator_switched": coordinator_switched,
    }
