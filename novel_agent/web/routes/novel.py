"""
小说创作API路由模块

包含小说创建、世界观生成、大纲生成、章节撰写等功能。
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

from ..models.requests import (
    CollabRecoveryActionRequest,
    ConfirmCreationContractRequest,
    CreateNovelRequest,
    GenerateWorldRequest,
    GenerateOutlineRequest,
    ResumeCreationFlowRequest,
    WriteChapterRequest,
)
from ..dependencies import get_coordinator, get_router_agent
from ...agents import RouterAgent
from ...agents.chat_session_store import get_chat_session_store
from ...config import config
from ...project_manager import get_project_manager
from ...workflow.collab_run_state import COLLAB_RUN_STATE_KEY
from ...workflow.task_pool import TaskPool, TaskStatus
from .chat import (
    _apply_workflow_update,
    _clear_active_workflow,
    _normalize_creation_requirements,
    _register_active_workflow,
    _resolve_workflow_file_path,
    _sanitize_conversation_history,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_collab_runtime_state(coordinator: Any) -> Dict[str, Any]:
    if not coordinator:
        return {}
    state_store = getattr(coordinator, "collab_run_state_store", None)
    if state_store is not None and hasattr(state_store, "load_state"):
        try:
            state = state_store.load_state()
            return state if isinstance(state, dict) else {}
        except Exception as exc:
            logger.warning("[NovelRoute] failed to load collab run state from store: %s", exc)

    project_manager = getattr(coordinator, "project_manager", None)
    if project_manager is None or not hasattr(project_manager, "load_project_state"):
        return {}
    state = project_manager.load_project_state(COLLAB_RUN_STATE_KEY, default={})
    return state if isinstance(state, dict) else {}


def _task_label(task_type: str) -> str:
    labels = {
        "build_world": "世界观设定",
        "build_characters": "角色档案",
        "build_outline": "全书大纲",
        "chapter_settings": "章纲设定",
        "write_chapter": "章节正文",
        "summary_orchestrate": "阶段总结",
        "context_plan": "上下文规划",
        "content_read": "内容读取",
        "evaluate_chapter": "章节评估",
        "polish_chapter": "章节润色",
        "expand_content": "正文扩写",
    }
    key = str(task_type or "").strip()
    return labels.get(key, key or "未记录任务")


def _task_title(task: Dict[str, Any]) -> str:
    title = str((task or {}).get("title") or "").strip()
    task_type = str((task or {}).get("task_type") or "").strip()
    return title or _task_label(task_type)


def _summarize_diagnostic_task(task: Dict[str, Any]) -> Dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return {
        "task_id": str(task.get("task_id") or task.get("id") or "").strip(),
        "task_type": str(task.get("task_type") or "").strip(),
        "title": _task_title(task),
        "status": str(task.get("status") or "").strip(),
        "assigned_agent": str(task.get("assigned_agent") or "").strip(),
        "retry_count": int(task.get("retry_count") or 0),
        "reason": str(
            metadata.get("blocked_reason")
            or metadata.get("error")
            or metadata.get("review_note")
            or ""
        ).strip(),
    }


def _ready_task_summaries(tasks: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    completed_ids = {
        str(task.get("task_id") or task.get("id") or "").strip()
        for task in tasks
        if str(task.get("status") or "").strip() == "completed"
    }
    ready: list[Dict[str, Any]] = []
    for task in tasks:
        status = str(task.get("status") or "pending").strip()
        if status not in {"pending", "blocked"}:
            continue
        depends_on = [
            str(item or "").strip()
            for item in (task.get("depends_on") or [])
            if str(item or "").strip()
        ]
        if all(item in completed_ids for item in depends_on):
            ready.append(_summarize_diagnostic_task(task))
    return ready


def _diagnostic_action_label(action: str) -> str:
    labels = {
        "retry_failed_task": "重试失败任务",
        "acknowledge_review": "确认审阅并继续",
        "unblock_task": "解除阻塞",
        "resume_next_batch": "继续下一批任务",
        "resume_ready_tasks": "继续就绪任务",
    }
    key = str(action or "").strip()
    return labels.get(key, key or "未命名动作")


def _build_recovery_action(
    action: str,
    *,
    label: str = "",
    task: Optional[Dict[str, Any]] = None,
    run_after: bool = True,
    approve_chapter_settings: bool = False,
) -> Dict[str, Any]:
    task_id = str((task or {}).get("task_id") or "").strip()
    task_title = str((task or {}).get("title") or "").strip()
    payload = {
        "action": str(action or "").strip(),
        "label": label or _diagnostic_action_label(action),
        "task_id": task_id,
        "task_title": task_title,
        "run_after": bool(run_after),
        "resume_payload": {
            "max_tasks": 7,
            "max_chapter_tasks": 2,
            "approve_chapter_settings": bool(approve_chapter_settings),
        } if run_after else {},
    }
    return payload


def _build_collab_diagnostics(
    *,
    task_pool: Dict[str, Any],
    collab_run_state: Dict[str, Any],
    project_ready_execution: Dict[str, Any],
    collab_execution_trace: Dict[str, Any],
) -> Dict[str, Any]:
    tasks = [
        task
        for task in (task_pool.get("tasks", []) if isinstance(task_pool, dict) else [])
        if isinstance(task, dict)
    ]
    status_counts: Dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "pending").strip() or "pending"
        status_counts[status] = status_counts.get(status, 0) + 1

    failed_tasks = [_summarize_diagnostic_task(task) for task in tasks if str(task.get("status") or "").strip() == "failed"]
    blocked_tasks = [_summarize_diagnostic_task(task) for task in tasks if str(task.get("status") or "").strip() == "blocked"]
    review_tasks = [_summarize_diagnostic_task(task) for task in tasks if str(task.get("status") or "").strip() == "review_required"]
    running_tasks = [
        _summarize_diagnostic_task(task)
        for task in tasks
        if str(task.get("status") or "").strip() in {"running", "claimed"}
    ]
    ready_tasks = _ready_task_summaries(tasks)

    stop_reason = str((project_ready_execution or {}).get("stop_reason") or "").strip()
    stopped_on_task_type = str((project_ready_execution or {}).get("stopped_on_task_type") or "").strip()
    run_status = str((collab_run_state or {}).get("status") or "").strip()
    current_node = str((collab_run_state or {}).get("current_node") or "").strip()
    checkpoints = [
        item for item in (collab_run_state.get("checkpoints", []) if isinstance(collab_run_state, dict) else [])
        if isinstance(item, dict)
    ]
    handoffs = [
        item for item in (collab_run_state.get("handoffs", []) if isinstance(collab_run_state, dict) else [])
        if isinstance(item, dict)
    ]
    artifacts = [
        item for item in (collab_run_state.get("artifacts", []) if isinstance(collab_run_state, dict) else [])
        if isinstance(item, dict)
    ]
    memory_items = {}
    shared_memory = collab_run_state.get("shared_memory") if isinstance(collab_run_state, dict) else {}
    if isinstance(shared_memory, dict) and isinstance(shared_memory.get("items"), dict):
        memory_items = shared_memory.get("items") or {}
    events = [
        item for item in (collab_execution_trace.get("events", []) if isinstance(collab_execution_trace, dict) else [])
        if isinstance(item, dict)
    ]

    if failed_tasks:
        health = "failed"
        summary = f"{failed_tasks[0]['title']} 执行失败，需要先查看失败原因。"
        recommended_action = "review_failed_task"
        can_resume = False
    elif stop_reason == "chapter_settings_review_required" or review_tasks:
        health = "needs_review"
        summary = "章纲或阶段成果等待确认，确认后可继续正文创作。"
        recommended_action = "approve_and_resume"
        can_resume = True
    elif blocked_tasks:
        health = "blocked"
        summary = f"{blocked_tasks[0]['title']} 当前阻塞，需要补齐上下文或确认条件。"
        recommended_action = "review_blocker"
        can_resume = bool(ready_tasks)
    elif stop_reason in {"max_tasks_reached", "max_chapter_tasks_reached"}:
        health = "paused"
        summary = "本轮协作达到批量上限，可检查结果后继续下一批任务。"
        recommended_action = "resume_next_batch"
        can_resume = True
    elif running_tasks:
        health = "running"
        summary = f"{running_tasks[0]['title']} 正在执行。"
        recommended_action = "wait_or_refresh"
        can_resume = False
    elif ready_tasks:
        health = "ready"
        summary = f"{ready_tasks[0]['title']} 已就绪，可继续调度。"
        recommended_action = "resume_ready_tasks"
        can_resume = True
    elif tasks and status_counts.get("completed", 0) == len(tasks):
        health = "completed"
        summary = "当前任务池已完成。"
        recommended_action = "review_outputs"
        can_resume = False
    else:
        health = "idle"
        summary = "当前没有可诊断的协作任务。"
        recommended_action = "start_or_confirm_contract"
        can_resume = False

    if stop_reason == "task_failed" and not failed_tasks:
        health = "failed"
        summary = "最近一轮协作报告任务失败，请检查任务池和运行消息。"
        recommended_action = "review_failed_task"

    actions: list[Dict[str, Any]] = []
    if failed_tasks:
        actions.append(_build_recovery_action("retry_failed_task", task=failed_tasks[0], run_after=False))
    if health == "needs_review":
        actions.append(_build_recovery_action(
            "acknowledge_review",
            label="确认审阅并继续正文",
            task=review_tasks[0] if review_tasks else {},
            run_after=True,
            approve_chapter_settings=True,
        ))
    if health == "blocked" and blocked_tasks:
        actions.append(_build_recovery_action("unblock_task", task=blocked_tasks[0], run_after=False))
    if recommended_action in {"resume_next_batch", "resume_ready_tasks"} and can_resume:
        actions.append(_build_recovery_action(recommended_action, run_after=True))

    recovery = {
        "can_resume": can_resume,
        "requires_review": health == "needs_review",
        "recommended_action": recommended_action,
        "resume_payload": {
            "max_tasks": 7,
            "max_chapter_tasks": 2,
            "approve_chapter_settings": recommended_action == "approve_and_resume",
        } if can_resume else {},
        "actions": actions,
    }

    warnings: list[str] = []
    if run_status == "failed" or current_node == "failed":
        warnings.append("运行账本标记为失败。")
    if tasks and not checkpoints:
        warnings.append("任务池存在，但闭环检查点为空。")
    if status_counts.get("completed", 0) and not artifacts:
        warnings.append("已有完成任务，但产物登记为空。")
    if status_counts.get("completed", 0) and not handoffs:
        warnings.append("已有完成任务，但 Agent 交接记录为空。")
    if status_counts.get("completed", 0) and not memory_items:
        warnings.append("已有完成任务，但共享记忆尚未写入。")

    return {
        "health": health,
        "summary": summary,
        "status_counts": status_counts,
        "stop_reason": stop_reason,
        "stopped_on_task_type": stopped_on_task_type,
        "current_node": current_node,
        "run_status": run_status or "idle",
        "task_count": len(tasks),
        "event_count": len(events),
        "checkpoint_count": len(checkpoints),
        "handoff_count": len(handoffs),
        "artifact_count": len(artifacts),
        "memory_item_count": len(memory_items),
        "running_tasks": running_tasks[:5],
        "failed_tasks": failed_tasks[:5],
        "blocked_tasks": blocked_tasks[:5],
        "review_tasks": review_tasks[:5],
        "ready_tasks": ready_tasks[:5],
        "warnings": warnings,
        "recovery": recovery,
    }


def _compact_handoff_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _recent_dict_items(payload: Any, limit: int) -> list[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    return [
        dict(item)
        for item in payload
        if isinstance(item, dict)
    ][-max(0, int(limit or 0)):]


def _memory_handoff_items(collab_run_state: Dict[str, Any], limit: int = 6) -> list[Dict[str, Any]]:
    shared_memory = collab_run_state.get("shared_memory") if isinstance(collab_run_state, dict) else {}
    raw_items = shared_memory.get("items") if isinstance(shared_memory, dict) else {}
    if not isinstance(raw_items, dict):
        return []
    items: list[Dict[str, Any]] = []
    for key, value in raw_items.items():
        if not isinstance(value, dict):
            continue
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        value_summary = metadata.get("value_summary") if isinstance(metadata.get("value_summary"), dict) else {}
        items.append({
            "key": str(value.get("key") or key or "").strip(),
            "summary": _compact_handoff_text(
                value.get("summary")
                or value_summary.get("preview")
                or value_summary.get("type")
                or ""
            ),
            "source_task_id": str(value.get("source_task_id") or "").strip(),
            "source_task_type": str(value.get("source_task_type") or "").strip(),
            "source_agent": str(value.get("source_agent") or "").strip(),
            "updated_at": str(value.get("updated_at") or "").strip(),
        })
    return sorted(items, key=lambda item: item.get("updated_at", ""))[-limit:]


def _build_handoff_note(
    *,
    diagnostics: Dict[str, Any],
    creation_contract: Dict[str, Any],
    task_pool: Dict[str, Any],
    collab_run_state: Dict[str, Any],
    project_ready_execution: Dict[str, Any],
    memory_items: list[Dict[str, Any]],
) -> str:
    contract_id = str((creation_contract or {}).get("contract_id") or "").strip()
    project_id = str((collab_run_state or {}).get("project_id") or "").strip()
    run_id = str((collab_run_state or {}).get("run_id") or "").strip()
    recovery = diagnostics.get("recovery") if isinstance(diagnostics.get("recovery"), dict) else {}
    action = str(recovery.get("recommended_action") or "").strip()
    tasks = [
        item for item in (task_pool.get("tasks", []) if isinstance(task_pool, dict) else [])
        if isinstance(item, dict)
    ]
    status_counts = diagnostics.get("status_counts") if isinstance(diagnostics.get("status_counts"), dict) else {}
    focus_tasks = (
        diagnostics.get("failed_tasks")
        or diagnostics.get("blocked_tasks")
        or diagnostics.get("review_tasks")
        or diagnostics.get("ready_tasks")
        or []
    )
    focus_lines = [
        f"- {item.get('task_id', '')} {item.get('title', '')} [{item.get('status', '')}]"
        for item in focus_tasks[:5]
        if isinstance(item, dict)
    ]
    memory_lines = [
        f"- {item.get('key', '')}: {item.get('summary', '')}"
        for item in memory_items[:5]
        if isinstance(item, dict)
    ]
    lines = [
        "多Agent协作交接包",
        f"项目: {project_id or '未记录'} / Run: {run_id or '未记录'} / Contract: {contract_id or '未记录'}",
        f"健康状态: {diagnostics.get('health', 'idle')} - {diagnostics.get('summary', '')}",
        f"停止原因: {diagnostics.get('stop_reason') or '无'} / 卡在: {diagnostics.get('stopped_on_task_type') or '无'} / 推荐动作: {action or '无'}",
        f"任务统计: {status_counts or {}} / 总任务: {len(tasks)}",
        f"最近批次: 已执行 {project_ready_execution.get('executed_task_count', 0) if isinstance(project_ready_execution, dict) else 0} 个任务",
    ]
    if focus_lines:
        lines.append("重点任务:")
        lines.extend(focus_lines)
    if memory_lines:
        lines.append("共享记忆:")
        lines.extend(memory_lines)
    warnings = diagnostics.get("warnings") if isinstance(diagnostics.get("warnings"), list) else []
    if warnings:
        lines.append("风险提示:")
        lines.extend(f"- {item}" for item in warnings[:5])
    return "\n".join(str(line).rstrip() for line in lines if str(line).strip())


def _build_collab_handoff(
    *,
    task_pool: Dict[str, Any],
    collab_execution_trace: Dict[str, Any],
    collab_run_state: Dict[str, Any],
    collab_diagnostics: Dict[str, Any],
    creation_contract: Dict[str, Any],
    project_ready_execution: Dict[str, Any],
) -> Dict[str, Any]:
    tasks = [
        item for item in (task_pool.get("tasks", []) if isinstance(task_pool, dict) else [])
        if isinstance(item, dict)
    ]
    status_counts = collab_diagnostics.get("status_counts") if isinstance(collab_diagnostics.get("status_counts"), dict) else {}
    memory_items = _memory_handoff_items(collab_run_state)
    recent_checkpoints = _recent_dict_items((collab_run_state or {}).get("checkpoints"), 5)
    recent_messages = _recent_dict_items((collab_run_state or {}).get("messages"), 5)
    recent_handoffs = _recent_dict_items((collab_run_state or {}).get("handoffs"), 5)
    recent_artifacts = _recent_dict_items((collab_run_state or {}).get("artifacts"), 5)
    recent_events = _recent_dict_items((collab_execution_trace or {}).get("events"), 5)
    recovery = collab_diagnostics.get("recovery") if isinstance(collab_diagnostics.get("recovery"), dict) else {}

    note = _build_handoff_note(
        diagnostics=collab_diagnostics,
        creation_contract=creation_contract,
        task_pool=task_pool,
        collab_run_state=collab_run_state,
        project_ready_execution=project_ready_execution,
        memory_items=memory_items,
    )

    return {
        "handoff_id": f"handoff-{_now_iso()}",
        "generated_at": _now_iso(),
        "project_id": str((collab_run_state or {}).get("project_id") or "").strip(),
        "session_id": str((collab_run_state or {}).get("session_id") or "").strip(),
        "run_id": str((collab_run_state or {}).get("run_id") or "").strip(),
        "contract_id": str((creation_contract or {}).get("contract_id") or "").strip(),
        "health": str(collab_diagnostics.get("health") or "idle").strip(),
        "summary": str(collab_diagnostics.get("summary") or "").strip(),
        "recommended_action": str(recovery.get("recommended_action") or "").strip(),
        "resume_payload": recovery.get("resume_payload") if isinstance(recovery.get("resume_payload"), dict) else {},
        "actions": recovery.get("actions") if isinstance(recovery.get("actions"), list) else [],
        "task_count": len(tasks),
        "status_counts": status_counts,
        "stop_reason": str(collab_diagnostics.get("stop_reason") or "").strip(),
        "stopped_on_task_type": str(collab_diagnostics.get("stopped_on_task_type") or "").strip(),
        "warnings": collab_diagnostics.get("warnings") if isinstance(collab_diagnostics.get("warnings"), list) else [],
        "focus_tasks": (
            collab_diagnostics.get("failed_tasks")
            or collab_diagnostics.get("blocked_tasks")
            or collab_diagnostics.get("review_tasks")
            or collab_diagnostics.get("ready_tasks")
            or []
        )[:8],
        "recent_checkpoints": recent_checkpoints,
        "recent_messages": recent_messages,
        "recent_handoffs": recent_handoffs,
        "recent_artifacts": recent_artifacts,
        "recent_events": recent_events,
        "shared_memory": {
            "updated_at": str(((collab_run_state or {}).get("shared_memory") or {}).get("updated_at") or ""),
            "items": memory_items,
        },
        "handoff_note": note,
    }


def _build_collab_runtime_payload(coordinator: Any) -> Dict[str, Any]:
    project_manager = getattr(coordinator, "project_manager", None)
    if project_manager is None:
        return {
            "task_pool": {},
            "collab_execution_trace": {},
            "collab_run_state": {},
            "collab_diagnostics": {},
            "collab_handoff": {},
            "creation_contract": {},
            "project_ready_execution": {},
        }

    task_pool = project_manager.load_project_state("task_pool", default={})
    if not isinstance(task_pool, dict):
        task_pool = {}
    collab_execution_trace = project_manager.load_project_state("collab_execution_trace", default={})
    if not isinstance(collab_execution_trace, dict):
        collab_execution_trace = {}
    creation_contract = project_manager.load_project_state("creation_contract", default={})
    if not isinstance(creation_contract, dict):
        creation_contract = {}

    project_ready_execution = (
        task_pool.get("metadata", {}).get("project_ready_execution", {})
        if isinstance(task_pool.get("metadata"), dict)
        else {}
    )
    if not isinstance(project_ready_execution, dict):
        project_ready_execution = {}

    collab_run_state = _load_collab_runtime_state(coordinator)
    collab_diagnostics = _build_collab_diagnostics(
        task_pool=task_pool,
        collab_run_state=collab_run_state,
        project_ready_execution=project_ready_execution,
        collab_execution_trace=collab_execution_trace,
    )
    collab_handoff = _build_collab_handoff(
        task_pool=task_pool,
        collab_execution_trace=collab_execution_trace,
        collab_run_state=collab_run_state,
        collab_diagnostics=collab_diagnostics,
        creation_contract=creation_contract,
        project_ready_execution=project_ready_execution,
    )

    return {
        "task_pool": task_pool,
        "collab_execution_trace": collab_execution_trace,
        "collab_run_state": collab_run_state,
        "collab_diagnostics": collab_diagnostics,
        "collab_handoff": collab_handoff,
        "creation_contract": creation_contract,
        "project_ready_execution": project_ready_execution,
    }


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_recovery_task_pool(coordinator: Any) -> TaskPool:
    project_manager = getattr(coordinator, "project_manager", None)
    if project_manager is None or not hasattr(project_manager, "load_project_state"):
        raise HTTPException(status_code=500, detail="ProjectManager not initialized")
    payload = project_manager.load_project_state("task_pool", default={})
    if not isinstance(payload, dict) or not payload.get("tasks"):
        raise HTTPException(status_code=400, detail="当前项目没有可恢复的任务池。")
    try:
        return TaskPool.from_dict(payload)
    except Exception as exc:
        logger.warning("[NovelRoute] failed to restore task pool for recovery: %s", exc)
        raise HTTPException(status_code=400, detail="任务池状态损坏，无法执行恢复动作。") from exc


def _save_recovery_task_pool(coordinator: Any, task_pool: TaskPool) -> Dict[str, Any]:
    save_pool = getattr(coordinator, "_save_runtime_task_pool", None)
    if callable(save_pool):
        return save_pool(task_pool)
    payload = task_pool.to_dict()
    coordinator.project_manager.save_project_state("task_pool", payload)
    return payload


def _append_recovery_event(coordinator: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    append_event = getattr(coordinator, "_append_collab_execution_event", None)
    if callable(append_event):
        return append_event("recovery_action", payload)

    project_manager = getattr(coordinator, "project_manager", None)
    if project_manager is None:
        return {}
    trace = project_manager.load_project_state("collab_execution_trace", default={})
    if not isinstance(trace, dict):
        trace = {}
    events = [
        item for item in (trace.get("events") or [])
        if isinstance(item, dict)
    ]
    events.append({
        "type": "recovery_action",
        "timestamp": _now_iso(),
        **dict(payload or {}),
    })
    trace["status"] = trace.get("status") or "running"
    trace["events"] = events[-300:]
    project_manager.save_project_state("collab_execution_trace", trace)
    return trace


def _append_recovery_run_state(coordinator: Any, payload: Dict[str, Any]) -> None:
    state_store = getattr(coordinator, "collab_run_state_store", None)
    task_id = str((payload.get("task_ids") or [""])[0] or "").strip()
    task_type = str((payload.get("task_types") or [""])[0] or "").strip()
    if state_store is not None:
        if hasattr(state_store, "ensure_run"):
            state_store.ensure_run(status="running")
        if hasattr(state_store, "record_checkpoint"):
            state_store.record_checkpoint(
                node="recovery_action",
                status="completed",
                task_id=task_id,
                task_type=task_type,
                agent_name="Coordinator",
                metadata=payload,
            )
        if hasattr(state_store, "append_runtime_event"):
            state_store.append_runtime_event({
                "type": "recovery_action",
                "timestamp": _now_iso(),
                "task_id": task_id,
                "task_type": task_type,
                "agent_name": "Coordinator",
                "payload": payload,
            })
        return

    project_manager = getattr(coordinator, "project_manager", None)
    if project_manager is None:
        return
    state = project_manager.load_project_state(COLLAB_RUN_STATE_KEY, default={})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("run_id", "manual-recovery")
    state["status"] = "running"
    state["current_node"] = "recovery_action"
    state["current_task_id"] = task_id
    state["current_task_type"] = task_type
    state["updated_at"] = _now_iso()
    checkpoint = {
        "checkpoint_id": f"manual-recovery-{len(state.get('checkpoints') or []) + 1}",
        "node": "recovery_action",
        "status": "completed",
        "created_at": _now_iso(),
        "task_id": task_id,
        "task_type": task_type,
        "agent_name": "Coordinator",
        "metadata": dict(payload or {}),
    }
    message = {
        "message_id": f"manual-recovery-msg-{len(state.get('messages') or []) + 1}",
        "type": "recovery_action",
        "created_at": _now_iso(),
        "task_id": task_id,
        "task_type": task_type,
        "agent_name": "Coordinator",
        "content": dict(payload or {}),
    }
    checkpoints = [
        item for item in (state.get("checkpoints") or [])
        if isinstance(item, dict)
    ]
    messages = [
        item for item in (state.get("messages") or [])
        if isinstance(item, dict)
    ]
    state["checkpoints"] = (checkpoints + [checkpoint])[-120:]
    state["messages"] = (messages + [message])[-500:]
    state.setdefault("shared_memory", {"items": {}, "updated_at": ""})
    project_manager.save_project_state(COLLAB_RUN_STATE_KEY, state)


def _append_task_recovery_history(
    task: Any,
    *,
    action: str,
    previous_status: str,
    note: str,
) -> None:
    metadata = dict(getattr(task, "metadata", {}) or {})
    history = [
        item for item in (metadata.get("recovery_history") or [])
        if isinstance(item, dict)
    ]
    history.append({
        "action": action,
        "previous_status": previous_status,
        "note": str(note or "").strip(),
        "at": _now_iso(),
        "previous_error": str(metadata.get("error") or "").strip(),
        "previous_blocked_reason": str(metadata.get("blocked_reason") or "").strip(),
        "previous_review_note": str(metadata.get("review_note") or "").strip(),
    })
    metadata["recovery_history"] = history[-20:]
    metadata["last_recovery_action"] = action
    metadata["last_recovery_at"] = _now_iso()
    if note:
        metadata["last_recovery_note"] = str(note or "").strip()
    for key in ("error", "blocked_reason", "review_note"):
        metadata.pop(key, None)
    task.metadata = metadata


def _resolve_recovery_task_ids(request: CollabRecoveryActionRequest) -> list[str]:
    ids = []
    if request.task_id:
        ids.append(str(request.task_id or "").strip())
    ids.extend(str(item or "").strip() for item in (request.task_ids or []))
    seen = set()
    result = []
    for item in ids:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _apply_collab_recovery_action(
    *,
    task_pool: TaskPool,
    action: str,
    task_ids: list[str],
    note: str,
) -> list[Dict[str, Any]]:
    normalized_action = str(action or "").strip()
    updated_tasks = []
    if normalized_action in {"retry_failed_task", "unblock_task"} and not task_ids:
        raise HTTPException(status_code=400, detail="恢复动作需要指定 task_id。")

    for task_id in task_ids:
        task = task_pool.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        previous_status = str(task.status or "").strip()
        if normalized_action == "retry_failed_task":
            if previous_status != TaskStatus.FAILED:
                raise HTTPException(status_code=400, detail="只有失败任务可以执行重试恢复。")
            _append_task_recovery_history(
                task,
                action=normalized_action,
                previous_status=previous_status,
                note=note,
            )
            task.status = TaskStatus.PENDING
            task.assigned_agent = ""
            task.result_ref = ""
            task.touch()
        elif normalized_action == "unblock_task":
            if previous_status != TaskStatus.BLOCKED:
                raise HTTPException(status_code=400, detail="只有阻塞任务可以解除阻塞。")
            _append_task_recovery_history(
                task,
                action=normalized_action,
                previous_status=previous_status,
                note=note,
            )
            task.status = TaskStatus.PENDING
            task.touch()
        elif normalized_action == "acknowledge_review":
            if previous_status == TaskStatus.REVIEW_REQUIRED:
                _append_task_recovery_history(
                    task,
                    action=normalized_action,
                    previous_status=previous_status,
                    note=note,
                )
                task.status = TaskStatus.COMPLETED
                task.review_required = False
                task.touch()
            else:
                continue
        else:
            raise HTTPException(status_code=400, detail="不支持的恢复动作。")

        task_pool._touch()
        updated_tasks.append(task.to_dict())

    if updated_tasks:
        execution = task_pool.metadata.get("project_ready_execution")
        if not isinstance(execution, dict):
            execution = {}
        previous_stop_reason = str(execution.get("stop_reason") or "").strip()
        previous_stopped_type = str(execution.get("stopped_on_task_type") or "").strip()
        if previous_stop_reason:
            execution["recovered_from_stop_reason"] = previous_stop_reason
            execution["recovered_from_task_type"] = previous_stopped_type
            execution["stop_reason"] = ""
            execution["stopped_on_task_type"] = ""
            execution["recovery_action"] = normalized_action
            execution["recovered_at"] = _now_iso()
            task_pool.metadata["project_ready_execution"] = execution
            task_pool._touch()

    return updated_tasks


async def _execute_recovery_resume(
    coordinator: Any,
    request: CollabRecoveryActionRequest,
) -> Dict[str, Any]:
    max_tasks = max(1, int(request.max_tasks or 7))
    max_chapter_tasks = max(0, int(request.max_chapter_tasks or 0))
    if bool(request.approve_chapter_settings):
        approve_review = getattr(coordinator, "approve_chapter_settings_review", None)
        if callable(approve_review):
            approve_review()
    execute_tasks = getattr(coordinator, "execute_project_ready_tasks", None)
    if not callable(execute_tasks):
        raise HTTPException(status_code=500, detail="Coordinator does not support project-ready resume")
    return await execute_tasks(
        max_tasks=max_tasks,
        max_chapter_tasks=max_chapter_tasks,
    )


def _collab_recovery_message(action: str, updated_count: int, executed_count: int = 0) -> str:
    if action == "retry_failed_task":
        return f"已将 {updated_count} 个失败任务恢复为待处理，可继续调度重试。"
    if action == "unblock_task":
        return f"已解除 {updated_count} 个阻塞任务，可重新进入调度。"
    if action == "acknowledge_review":
        if executed_count:
            return f"已确认审阅并续跑 {executed_count} 个任务。"
        return "已确认审阅断点，可继续执行后续任务。"
    return "恢复动作已执行。"


def _request_creation_requirements(request: CreateNovelRequest) -> Dict[str, Any]:
    return {
        "novel_type": request.novel_type,
        "theme": request.theme,
        "requirements": request.requirements,
        "protagonist": request.protagonist,
        "plot_idea": request.plot_idea,
        "volume_count": request.volume_count,
        "chapters_per_volume": request.chapters_per_volume,
    }


def _load_create_session_context(request: CreateNovelRequest) -> Dict[str, Any]:
    session_id = str(request.session_id or "").strip()
    if not session_id:
        return {}

    project_id = str(getattr(get_project_manager(), "current_project_id", "") or "").strip()
    state = get_chat_session_store().load(session_id, project_id)
    if not state:
        return {}

    collected_info = dict(getattr(state, "collected_info", {}) or {})
    conversation_history = _sanitize_conversation_history(
        getattr(state, "conversation_history", None) or []
    )[-12:]

    request_requirements = _request_creation_requirements(request)
    message = (
        request_requirements.get("plot_idea")
        or request_requirements.get("requirements")
        or request_requirements.get("theme")
        or request_requirements.get("novel_type")
        or "开始创作"
    )
    normalized = _normalize_creation_requirements(
        collected_info=collected_info,
        message=str(message),
    )

    merged_requirements = dict(request_requirements)
    for key in ("novel_type", "theme", "requirements", "protagonist", "plot_idea"):
        if str(collected_info.get(key) or "").strip():
            merged_requirements[key] = normalized[key]
    for key in ("volume_count", "chapters_per_volume", "target_word_count", "target_words_per_chapter", "target_words_per_chapter_source"):
        if collected_info.get(key) not in (None, ""):
            merged_requirements[key] = normalized[key]

    context: Dict[str, Any] = {
        "session_id": session_id,
        "collected_info": collected_info,
        "creation_requirements": merged_requirements,
    }
    if conversation_history:
        context["conversation_history"] = conversation_history
    return context


def _supports_router_create_execution(router_agent: Any) -> bool:
    return bool(
        router_agent
        and callable(getattr(router_agent, "_execute_create_novel_pipeline", None))
    )


def _normalize_create_workflow_update(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        text = str(payload or "").strip()
        return {"content": text} if text else {}

    update = dict(payload)
    stage = str(update.get("stage") or "").strip()
    status = str(update.get("status") or "").strip()
    if not status:
        if stage in {"completed", "failed", "cancelled"}:
            update["status"] = stage
        elif stage:
            update["status"] = "running"
    if not update.get("content") and update.get("message"):
        update["content"] = str(update.get("message") or "").strip()
    if not update.get("output_dir") and update.get("project_dir"):
        update["output_dir"] = str(update.get("project_dir") or "").strip()
    file_path = str(update.get("file_path") or "").strip()
    if file_path and not update.get("output_dir"):
        update["output_dir"] = str(Path(file_path).parent)
    return update


@router.post("/create")
async def create_novel(request: CreateNovelRequest):
    """创建小说(流式输出)"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    session_context = _load_create_session_context(request)
    create_args = dict(session_context.get("creation_requirements") or _request_creation_requirements(request))
    session_id = str(request.session_id or "").strip()
    pm = get_project_manager()
    project_id = str(getattr(pm, "current_project_id", "") or "").strip()
    session_key = f"{project_id}::{session_id}" if session_id else ""
    router_agent = get_router_agent()
    if not _supports_router_create_execution(router_agent):
        router_agent = RouterAgent(coordinator=coordinator)
    elif getattr(router_agent, "coordinator", None) is not coordinator and hasattr(router_agent, "set_coordinator"):
        router_agent.set_coordinator(coordinator)

    async def generate():
        active_run = None
        if session_id:
            active_run = _register_active_workflow(
                session_key,
                {
                    "session_id": session_id,
                    "project_id": project_id,
                    "status": "running",
                    "command": "create",
                    "target_agent": "Coordinator",
                    "current_agent": "Coordinator",
                    "stage": "starting",
                },
            )
        if _supports_router_create_execution(router_agent):
            queue: asyncio.Queue = asyncio.Queue()
            context = dict(session_context or {})
            context["auto_execute"] = True
            context["creation_requirements"] = dict(create_args)

            async def push_progress(update: Any):
                payload = dict(update) if isinstance(update, dict) else {"message": str(update or "").strip()}
                if payload:
                    await queue.put({"type": "progress", "payload": payload})

            context["progress_callback"] = push_progress
            start_message = (
                str(create_args.get("plot_idea") or "").strip()
                or str(create_args.get("requirements") or "").strip()
                or str(create_args.get("theme") or "").strip()
                or "开始创作"
            )

            async def runner():
                try:
                    result = await router_agent._execute_create_novel_pipeline(
                        message=start_message,
                        context=context,
                    )
                    await queue.put({"type": "done", "payload": result})
                except Exception as exc:
                    await queue.put({
                        "type": "failed",
                        "payload": {
                            "stage": "failed",
                            "message": f"创建小说失败: {str(exc)}",
                            "error": str(exc),
                        },
                    })

            runner_task = asyncio.create_task(runner())
            try:
                while True:
                    event = await queue.get()
                    payload = event.get("payload") or {}
                    normalized_update = _normalize_create_workflow_update(payload)
                    if event.get("type") == "done" and "status" not in normalized_update:
                        normalized_update["status"] = "completed"
                        normalized_update["stage"] = str(normalized_update.get("stage") or "completed")
                    elif event.get("type") == "failed":
                        normalized_update["status"] = "failed"
                        normalized_update["stage"] = str(normalized_update.get("stage") or "failed")
                    if active_run and normalized_update:
                        _apply_workflow_update(active_run, normalized_update)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    if event.get("type") in {"done", "failed"}:
                        break
            finally:
                if not runner_task.done():
                    runner_task.cancel()
                    try:
                        await runner_task
                    except asyncio.CancelledError:
                        pass
                if active_run:
                    _clear_active_workflow(session_key)
            return

        try:
            async for progress in coordinator.create_novel(
                novel_type=create_args["novel_type"],
                theme=create_args["theme"],
                requirements=create_args["requirements"],
                protagonist=create_args["protagonist"],
                plot_idea=create_args["plot_idea"],
                volume_count=create_args["volume_count"],
                chapters_per_volume=create_args["chapters_per_volume"],
                session_context=session_context or None,
            ):
                normalized_update = _normalize_create_workflow_update(progress)
                if active_run and normalized_update:
                    _apply_workflow_update(active_run, normalized_update)
                yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
        except Exception as exc:
            failure_payload = {
                "stage": "failed",
                "status": "failed",
                "message": f"创建小说失败: {str(exc)}",
                "error": str(exc),
            }
            if active_run:
                _apply_workflow_update(active_run, failure_payload)
            yield f"data: {json.dumps(failure_payload, ensure_ascii=False)}\n\n"
        finally:
            if active_run:
                _clear_active_workflow(session_key)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


@router.post("/world")
async def generate_world(request: GenerateWorldRequest):
    """生成世界观"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    result = await coordinator.generate_world(
        novel_type=request.novel_type,
        theme=request.theme,
        requirements=request.requirements
    )
    return JSONResponse(result)


@router.post("/outline")
async def generate_outline(request: GenerateOutlineRequest):
    """生成大纲"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    result = await coordinator.generate_outline(
        protagonist=request.protagonist,
        plot_idea=request.plot_idea,
        volume_count=request.volume_count,
        chapters_per_volume=request.chapters_per_volume
    )
    return JSONResponse(result)


@router.post("/chapter")
async def write_chapter(request: WriteChapterRequest):
    """撰写/续写/润色章节"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    try:
        action = request.action.lower()

        if action == "continue":
            result = await coordinator.continue_chapter(
                chapter_index=request.chapter_index,
                chapter_title=request.chapter_title,
                existing_content=request.existing_content,
                target_words=request.word_count,
                enable_trends=request.enable_trends,
                trends_platforms=request.trends_platforms,
                trends_query=request.trends_query,
            )
        elif action == "polish":
            result = await coordinator.polish_content(
                content=request.existing_content,
                chapter_title=request.chapter_title
            )
        else:
            result = await coordinator.write_single_chapter(
                chapter_number=request.chapter_number,
                chapter_outline=request.chapter_outline,
                chapter_title=request.chapter_title,
                enable_trends=request.enable_trends,
                trends_platforms=request.trends_platforms,
                trends_query=request.trends_query,
            )

        return JSONResponse(result)
    except Exception as e:
        logger.error(f"[Novel] 章节处理失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "content": ""
        })


@router.post("/contract/confirm")
async def confirm_creation_contract(request: ConfirmCreationContractRequest):
    """确认创作合同并初始化正式任务池。"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    payload = dict(request.contract_payload or {})
    if not payload:
        payload = coordinator.project_manager.load_project_state("creation_contract", default={})
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="creation_contract 草案不存在")

    request_contract_id = str(request.contract_id or "").strip()
    payload_contract_id = str(payload.get("contract_id") or "").strip()
    if request_contract_id and payload_contract_id and request_contract_id != payload_contract_id:
        raise HTTPException(status_code=400, detail="contract_id 与当前草案不一致")

    if not request.approved:
        payload.setdefault("metadata", {})
        if isinstance(payload.get("metadata"), dict):
            payload["metadata"]["draft"] = True
            payload["metadata"]["rejected_at"] = payload["metadata"].get("rejected_at") or ""
        coordinator.project_manager.save_project_state("creation_contract", payload)
        return JSONResponse({
            "success": True,
            "approved": False,
            "creation_contract": payload,
            "message": "已拒绝当前合同草案",
        })

    existing_pool = coordinator.project_manager.load_project_state("task_pool", default={})
    persisted_contract = coordinator.project_manager.load_project_state("creation_contract", default={})
    pool_metadata = existing_pool.get("metadata", {}) if isinstance(existing_pool, dict) else {}
    existing_tasks = existing_pool.get("tasks", []) if isinstance(existing_pool, dict) else []
    pool_contract_id = str(pool_metadata.get("contract_id") or "").strip()
    persisted_contract_id = (
        str(persisted_contract.get("contract_id") or "").strip()
        if isinstance(persisted_contract, dict)
        else ""
    )
    already_confirmed = (
        bool(payload.get("user_confirmed"))
        or (isinstance(persisted_contract, dict) and bool(persisted_contract.get("user_confirmed")))
    )
    same_runtime_contract = bool(existing_tasks) and (
        (payload_contract_id and pool_contract_id == payload_contract_id)
        or (request_contract_id and pool_contract_id == request_contract_id)
        or (payload_contract_id and persisted_contract_id == payload_contract_id)
    )
    if same_runtime_contract and already_confirmed:
        ready_task_result = await coordinator.execute_project_ready_tasks(
            max_tasks=7,
            max_chapter_tasks=2,
        )
        runtime_payload = _build_collab_runtime_payload(coordinator)
        return JSONResponse({
            "success": True,
            "approved": True,
            "creation_contract": persisted_contract if isinstance(persisted_contract, dict) and persisted_contract else payload,
            "task_pool": ready_task_result.get("task_pool", runtime_payload["task_pool"] or existing_pool),
            "collab_execution_trace": runtime_payload["collab_execution_trace"],
            "collab_run_state": runtime_payload["collab_run_state"],
            "collab_diagnostics": runtime_payload["collab_diagnostics"],
            "collab_handoff": runtime_payload["collab_handoff"],
            "project_ready_task_execution": ready_task_result,
            "message": "合同已确认过，已沿用现有任务池继续执行。",
        })

    result = coordinator.initialize_task_pool_from_contract(payload, approved=True)
    ready_task_result = await coordinator.execute_project_ready_tasks(
        max_tasks=7,
        max_chapter_tasks=2,
    )
    runtime_payload = _build_collab_runtime_payload(coordinator)
    return JSONResponse({
        "success": True,
        "approved": True,
        "creation_contract": result.get("creation_contract", {}),
        "task_pool": ready_task_result.get("task_pool", runtime_payload["task_pool"] or result.get("task_pool", {})),
        "collab_execution_trace": runtime_payload["collab_execution_trace"],
        "collab_run_state": runtime_payload["collab_run_state"],
        "collab_diagnostics": runtime_payload["collab_diagnostics"],
        "collab_handoff": runtime_payload["collab_handoff"],
        "project_ready_task_execution": ready_task_result,
        "message": "合同已确认，正式任务池已初始化，并已尝试执行首批可执行任务",
    })


@router.post("/contract/resume")
async def resume_creation_flow(request: ResumeCreationFlowRequest):
    """
    续跑创作流程。

    适用于因 review_required 被打断（例如章纲设定生成后等用户审阅）
    或因 max_tasks/max_chapter_tasks 限额被截断后，用户审阅完成准备
    继续创作的场景。

    与 /contract/confirm 不同：本接口不会重新初始化任务池，
    直接从已有的 runtime task pool 中调度下一批 ready tasks，
    保留之前已完成任务的进度。
    """
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    contract_payload = coordinator.project_manager.load_project_state(
        "creation_contract", default={}
    )
    if not isinstance(contract_payload, dict) or not contract_payload:
        raise HTTPException(
            status_code=400,
            detail="当前项目尚未确认创作合同，无法续跑。请先通过聊天发起创作并确认合同。",
        )

    existing_pool = coordinator.project_manager.load_project_state("task_pool", default={})
    if not isinstance(existing_pool, dict) or not existing_pool.get("tasks"):
        raise HTTPException(
            status_code=400,
            detail="当前项目没有可续跑的任务池。请先通过 /contract/confirm 初始化任务池。",
        )

    max_tasks = max(1, int(request.max_tasks or 7))
    max_chapter_tasks = max(0, int(request.max_chapter_tasks or 0))

    review_state = coordinator.project_manager.load_project_state(
        "chapter_settings_review", default={}
    )
    if not isinstance(review_state, dict):
        review_state = {}
    if bool(request.approve_chapter_settings):
        approve_review = getattr(coordinator, "approve_chapter_settings_review", None)
        if callable(approve_review):
            review_state = approve_review()
        else:
            review_state.update({
                "approved": True,
                "approved_at": "",
                "status": "approved",
            })
            coordinator.project_manager.save_project_state(
                "chapter_settings_review", review_state
            )

    ready_task_result = await coordinator.execute_project_ready_tasks(
        max_tasks=max_tasks,
        max_chapter_tasks=max_chapter_tasks,
    )

    project_ready_execution = (
        ready_task_result.get("project_ready_execution") or {}
        if isinstance(ready_task_result, dict)
        else {}
    )
    stop_reason = str(project_ready_execution.get("stop_reason") or "").strip()
    executed_count = int(project_ready_execution.get("executed_task_count") or 0)

    if stop_reason == "review_required":
        message = f"已续跑 {executed_count} 个任务，仍在审阅断点上。请再次审阅后调用本接口继续。"
    elif stop_reason == "chapter_settings_review_required":
        message = "章纲设定尚未确认，已暂停正文创作，不会提前创建正文章节文件。"
    elif stop_reason in {"max_tasks_reached", "max_chapter_tasks_reached"}:
        message = f"已续跑 {executed_count} 个任务，达到本次批量上限。可再次调用本接口继续。"
    elif stop_reason == "task_failed":
        message = f"已续跑 {executed_count} 个任务，最后一个任务失败，请检查任务池状态。"
    elif stop_reason == "":
        message = f"已续跑 {executed_count} 个任务，任务池暂无新的就绪任务。"
    else:
        message = f"已续跑 {executed_count} 个任务，停止原因：{stop_reason}。"

    runtime_payload = _build_collab_runtime_payload(coordinator)
    return JSONResponse({
        "success": True,
        "creation_contract": contract_payload,
        "task_pool": ready_task_result.get("task_pool", runtime_payload["task_pool"] or existing_pool),
        "collab_execution_trace": runtime_payload["collab_execution_trace"],
        "collab_run_state": runtime_payload["collab_run_state"],
        "collab_diagnostics": runtime_payload["collab_diagnostics"],
        "collab_handoff": runtime_payload["collab_handoff"],
        "project_ready_task_execution": ready_task_result,
        "project_ready_execution": project_ready_execution,
        "stop_reason": stop_reason,
        "stopped_on_task_type": str(project_ready_execution.get("stopped_on_task_type") or "").strip(),
        "executed_task_count": executed_count,
        "chapter_settings_review": review_state,
        "message": message,
    })


@router.post("/contract/recovery-action")
async def apply_collab_recovery_action(request: CollabRecoveryActionRequest):
    """对协作诊断建议执行恢复动作，并可选择立即续跑任务池。"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    action = str(request.action or "").strip()
    if action in {"resume_next_batch", "resume_ready_tasks"}:
        ready_task_result = await _execute_recovery_resume(coordinator, request)
        runtime_payload = _build_collab_runtime_payload(coordinator)
        project_ready_execution = (
            ready_task_result.get("project_ready_execution") or {}
            if isinstance(ready_task_result, dict)
            else {}
        )
        executed_count = int(project_ready_execution.get("executed_task_count") or 0)
        event_payload = {
            "action": action,
            "task_ids": [],
            "task_types": [],
            "updated_count": 0,
            "run_after": True,
            "executed_task_count": executed_count,
            "note": str(request.note or "").strip(),
        }
        _append_recovery_event(coordinator, event_payload)
        _append_recovery_run_state(coordinator, event_payload)
        runtime_payload = _build_collab_runtime_payload(coordinator)
        return JSONResponse({
            "success": True,
            "action": action,
            "updated_tasks": [],
            "task_pool": ready_task_result.get("task_pool", runtime_payload["task_pool"]),
            "collab_execution_trace": runtime_payload["collab_execution_trace"],
            "collab_run_state": runtime_payload["collab_run_state"],
            "collab_diagnostics": runtime_payload["collab_diagnostics"],
            "collab_handoff": runtime_payload["collab_handoff"],
            "project_ready_task_execution": ready_task_result,
            "project_ready_execution": project_ready_execution,
            "executed_task_count": executed_count,
            "message": f"已续跑 {executed_count} 个任务。",
        })

    task_pool = _load_recovery_task_pool(coordinator)
    task_ids = _resolve_recovery_task_ids(request)
    updated_tasks = _apply_collab_recovery_action(
        task_pool=task_pool,
        action=action,
        task_ids=task_ids,
        note=str(request.note or "").strip(),
    )
    saved_task_pool = _save_recovery_task_pool(coordinator, task_pool)

    task_types = [
        str(item.get("task_type") or "").strip()
        for item in updated_tasks
        if isinstance(item, dict)
    ]
    event_payload = {
        "action": action,
        "task_ids": [
            str(item.get("task_id") or "").strip()
            for item in updated_tasks
            if isinstance(item, dict)
        ],
        "task_types": task_types,
        "updated_count": len(updated_tasks),
        "run_after": bool(request.run_after),
        "note": str(request.note or "").strip(),
    }
    _append_recovery_event(coordinator, event_payload)
    _append_recovery_run_state(coordinator, event_payload)

    ready_task_result: Dict[str, Any] = {}
    project_ready_execution: Dict[str, Any] = {}
    executed_count = 0
    if bool(request.run_after):
        ready_task_result = await _execute_recovery_resume(coordinator, request)
        project_ready_execution = (
            ready_task_result.get("project_ready_execution") or {}
            if isinstance(ready_task_result, dict)
            else {}
        )
        executed_count = int(project_ready_execution.get("executed_task_count") or 0)

    runtime_payload = _build_collab_runtime_payload(coordinator)
    return JSONResponse({
        "success": True,
        "action": action,
        "updated_tasks": updated_tasks,
        "task_pool": ready_task_result.get("task_pool", runtime_payload["task_pool"] or saved_task_pool),
        "collab_execution_trace": runtime_payload["collab_execution_trace"],
        "collab_run_state": runtime_payload["collab_run_state"],
        "collab_diagnostics": runtime_payload["collab_diagnostics"],
        "collab_handoff": runtime_payload["collab_handoff"],
        "project_ready_task_execution": ready_task_result,
        "project_ready_execution": project_ready_execution,
        "executed_task_count": executed_count,
        "message": _collab_recovery_message(action, len(updated_tasks), executed_count),
    })


@router.get("/status")
async def get_status():
    """获取项目状态"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    status = dict(coordinator.get_project_status() or {})
    status.update(_build_collab_runtime_payload(coordinator))
    return JSONResponse(status)


@router.get("/result-file")
async def download_collab_result_file(path: str):
    """下载协作模式产物文件。"""
    requested_path = _resolve_workflow_file_path(path)
    return FileResponse(
        path=requested_path,
        filename=requested_path.name,
        media_type="application/octet-stream",
    )


@router.get("/result-file-preview")
async def preview_collab_result_file(path: str):
    """预览协作模式产物文件。"""
    requested_path = _resolve_workflow_file_path(path)
    suffix = requested_path.suffix.lower()
    if suffix not in {".txt", ".md", ".json", ".log"}:
        raise HTTPException(status_code=400, detail="当前文件类型不支持应用内预览")

    content = requested_path.read_text(encoding="utf-8", errors="replace")
    truncated = False
    if len(content) > 120000:
        content = content[:120000]
        truncated = True

    language = {
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".log": "text",
    }.get(suffix, "text")

    return JSONResponse({
        "path": str(requested_path),
        "filename": requested_path.name,
        "language": language,
        "content": content,
        "truncated": truncated,
        "download_url": f"/api/novel/result-file?path={path}",
    })


@router.get("/memory/contract")
async def get_memory_contract():
    """获取记忆契约与同步诊断信息"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")
    return JSONResponse(coordinator.get_memory_diagnostics())


@router.get("/types")
async def get_novel_types():
    """获取支持的小说类型"""
    return JSONResponse({"types": config.novel.novel_types})
