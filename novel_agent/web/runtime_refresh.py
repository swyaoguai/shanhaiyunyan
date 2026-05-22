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
    if router_agent and hasattr(router_agent, "refresh_model_config"):
        try:
            router_agent.refresh_model_config()
        except Exception as exc:
            logger.debug(f"[RuntimeRefresh] 刷新路由智能体模型配置失败: {exc}")
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


def release_runtime_for_project_delete(project_id: str) -> Dict[str, Any]:
    """删除项目前释放持有项目知识库文件句柄的运行态对象。"""
    project_id = str(project_id or "").strip()
    result: Dict[str, Any] = {
        "project_id": project_id,
        "knowledge_base_closed": False,
        "continuous_writer_cache_cleared": 0,
    }
    if not project_id:
        return result

    router_agent = get_router_agent()
    coordinator = get_coordinator()

    runtime_kbs = []
    for owner in (router_agent, coordinator):
        kb = getattr(owner, "knowledge_base", None) if owner is not None else None
        if kb is not None and getattr(kb, "project_id", "") == project_id and kb not in runtime_kbs:
            runtime_kbs.append(kb)

    if router_agent is not None and getattr(getattr(router_agent, "knowledge_base", None), "project_id", "") == project_id:
        try:
            router_agent.set_knowledge_base(None)
        except Exception as exc:
            logger.warning(f"[RuntimeRefresh] 清空路由智能体知识库失败: {exc}")

    if coordinator is not None and getattr(getattr(coordinator, "knowledge_base", None), "project_id", "") == project_id:
        try:
            coordinator.set_knowledge_base(None)
        except Exception as exc:
            logger.warning(f"[RuntimeRefresh] 清空协调器知识库失败: {exc}")

    for kb in runtime_kbs:
        close = getattr(kb, "close", None)
        if callable(close):
            try:
                close()
                result["knowledge_base_closed"] = True
            except Exception as exc:
                logger.warning(f"[RuntimeRefresh] 关闭项目知识库失败 project_id={project_id}: {exc}")

    try:
        from .routes.continuous_write import clear_project_runtime

        result["continuous_writer_cache_cleared"] = clear_project_runtime(project_id)
    except Exception as exc:
        logger.warning(f"[RuntimeRefresh] 清理删除项目运行态失败: {exc}")

    return result
