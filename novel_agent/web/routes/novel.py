"""
小说创作API路由模块

包含小说创建、世界观生成、大纲生成、章节撰写等功能。
"""

import asyncio
import json
import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

from ..models.requests import (
    ConfirmCreationContractRequest,
    CreateNovelRequest,
    GenerateWorldRequest,
    GenerateOutlineRequest,
    WriteChapterRequest
)
from ..dependencies import get_coordinator, get_router_agent
from ...agents import RouterAgent
from ...agents.chat_session_store import get_chat_session_store
from ...config import config
from ...project_manager import get_project_manager
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
    for key in ("volume_count", "chapters_per_volume"):
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

    result = coordinator.initialize_task_pool_from_contract(payload, approved=True)
    ready_task_result = await coordinator.execute_project_ready_tasks(
        max_tasks=4,
        max_chapter_tasks=2,
    )
    return JSONResponse({
        "success": True,
        "approved": True,
        "creation_contract": result.get("creation_contract", {}),
        "task_pool": ready_task_result.get("task_pool", result.get("task_pool", {})),
        "collab_execution_trace": coordinator.project_manager.load_project_state("collab_execution_trace", default={}),
        "project_ready_task_execution": ready_task_result,
        "message": "合同已确认，正式任务池已初始化，并已尝试执行首批任务与连续章节试点",
    })


@router.get("/status")
async def get_status():
    """获取项目状态"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")

    status = dict(coordinator.get_project_status() or {})
    task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
    collab_execution_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
    status["task_pool"] = task_pool
    status["collab_execution_trace"] = collab_execution_trace
    status["creation_contract"] = coordinator.project_manager.load_project_state("creation_contract", default={})
    status["project_ready_execution"] = (
        task_pool.get("metadata", {}).get("project_ready_execution", {})
        if isinstance(task_pool, dict)
        else {}
    )
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
