"""Novel cover generation APIs."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ...cover_image_service import CoverImageService
from ...cover_prompt_enhancer import CoverPromptEnhancer
from ...cover_prompt_builder import CoverPromptBuilder, get_cover_templates
from ...project_manager import get_project_manager
from ..models.cover_image import CoverBatchDeleteRequest, CoverGenerateRequest, CoverPromptDraftRequest

router = APIRouter()
logger = logging.getLogger(__name__)

_prompt_builder = CoverPromptBuilder()
_prompt_enhancer = CoverPromptEnhancer(builder=_prompt_builder)
_image_service = CoverImageService()
_JOB_POLL_INTERVAL_MS = 2000
_JOB_CACHE_TTL = timedelta(hours=6)
_JOB_CACHE_LIMIT = 50
_TERMINAL_JOB_STATUSES = {"completed", "failed"}
_cover_image_job_tasks: set[asyncio.Task] = set()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CoverImageJobStore:
    """Small in-memory job store for packaged/local cover generation."""

    def __init__(self, *, ttl: timedelta = _JOB_CACHE_TTL, limit: int = _JOB_CACHE_LIMIT) -> None:
        self._jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = RLock()
        self._ttl = ttl
        self._limit = max(1, int(limit))

    def create(self) -> dict[str, Any]:
        task_id = f"cover-job-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        now = _now_iso()
        job = {
            "task_id": task_id,
            "status": "queued",
            "message": "封面生成任务已提交，正在等待执行。",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": "",
        }
        with self._lock:
            self._prune_locked()
            self._jobs[task_id] = job
        return self._public(job)

    def mark_running(self, task_id: str) -> None:
        self._update(
            task_id,
            status="running",
            message="封面正在生成中，图片接口可能需要较长时间。",
            error="",
        )

    def complete(self, task_id: str, result: Mapping[str, Any]) -> None:
        self._update(
            task_id,
            status="completed",
            message="封面已生成。",
            result=dict(result),
            error="",
        )

    def fail(self, task_id: str, error: str) -> None:
        self._update(
            task_id,
            status="failed",
            message="封面生成失败。",
            result=None,
            error=str(error or "封面生成失败，请检查图像模型配置。"),
        )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(task_id)
            if not job:
                return None
            self._jobs.move_to_end(task_id)
            return self._public(job)

    def _update(self, task_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(task_id)
            if not job:
                return
            job.update(updates)
            job["updated_at"] = _now_iso()
            self._jobs.move_to_end(task_id)

    def _prune_locked(self) -> None:
        cutoff = datetime.now() - self._ttl
        for task_id, job in list(self._jobs.items()):
            if str(job.get("status")) not in _TERMINAL_JOB_STATUSES:
                continue
            updated_at = self._parse_time(job.get("updated_at"))
            if updated_at and updated_at < cutoff:
                self._jobs.pop(task_id, None)

        while len(self._jobs) > self._limit:
            terminal_id = next(
                (
                    task_id
                    for task_id, job in self._jobs.items()
                    if str(job.get("status")) in _TERMINAL_JOB_STATUSES
                ),
                None,
            )
            if terminal_id:
                self._jobs.pop(terminal_id, None)
            else:
                self._jobs.popitem(last=False)

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    @staticmethod
    def _public(job: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(job.get("task_id") or ""),
            "status": str(job.get("status") or "queued"),
            "message": str(job.get("message") or ""),
            "created_at": str(job.get("created_at") or ""),
            "updated_at": str(job.get("updated_at") or ""),
            "result": job.get("result"),
            "error": str(job.get("error") or ""),
        }


_image_job_store = CoverImageJobStore()


def _ok(data: dict) -> JSONResponse:
    return JSONResponse({"success": True, **data})


def _require_current_project():
    pm = get_project_manager()
    if not getattr(pm, "current_project_id", ""):
        raise HTTPException(status_code=400, detail="请先选择小说项目。")
    return pm


def _prepare_generation_payload(request: CoverGenerateRequest) -> dict[str, Any]:
    pm = _require_current_project()
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请先生成或填写封面提示词。")

    payload = request.model_dump()
    payload["prompt"] = prompt
    payload["project_dir"] = str(pm.get_current_project_dir())
    return payload


async def _run_cover_generation_job(task_id: str, payload: Mapping[str, Any]) -> None:
    _image_job_store.mark_running(task_id)
    try:
        result = await _image_service.generate(payload)
    except ValueError as exc:
        _image_job_store.fail(task_id, str(exc))
    except RuntimeError as exc:
        logger.warning("[CoverImages] async generation failed: %s", exc)
        _image_job_store.fail(task_id, str(exc))
    except Exception as exc:
        logger.exception("[CoverImages] unexpected async generation failure")
        _image_job_store.fail(task_id, "封面生成失败，请检查图像模型配置。")
    else:
        _image_job_store.complete(task_id, result)


def _start_cover_generation_job(task_id: str, payload: Mapping[str, Any]) -> None:
    task = asyncio.create_task(_run_cover_generation_job(task_id, payload))
    _cover_image_job_tasks.add(task)
    task.add_done_callback(_cover_image_job_tasks.discard)


@router.get("/cover-images/templates")
async def list_cover_templates():
    return _ok({"templates": get_cover_templates()})


@router.post("/cover-images/prompt-draft")
async def build_cover_prompt_draft(request: CoverPromptDraftRequest):
    pm = _require_current_project()
    try:
        draft = _prompt_builder.build_prompt(
            project_manager=pm,
            template_id=request.template_id,
            source_mode=request.source_mode,
            title=request.title,
            author=request.author,
            custom_elements=request.custom_elements,
        )
        if request.prompt_api_config_id or request.prompt_model:
            try:
                draft = await _prompt_enhancer.enhance(
                    draft,
                    api_config_id=request.prompt_api_config_id,
                    model=request.prompt_model,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:
                logger.warning("[CoverImages] prompt enhancement failed: %s", exc)
                draft["prompt_model_warning"] = (
                    "文本模型补全失败，已改用本地推断和模板补全。"
                    "可以更换文本模型，或在创作想法和四项元素中补充内容后重试。"
                )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ok({"data": draft})


@router.post("/cover-images/generate")
async def generate_cover_image(request: CoverGenerateRequest):
    payload = _prepare_generation_payload(request)
    try:
        result = await _image_service.generate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("[CoverImages] generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[CoverImages] unexpected generation failure")
        raise HTTPException(status_code=502, detail="封面生成失败，请检查图像模型配置。") from exc
    return _ok({"data": result})


@router.post("/cover-images/generate-jobs")
async def create_cover_image_generation_job(request: CoverGenerateRequest):
    payload = _prepare_generation_payload(request)
    job = _image_job_store.create()
    _start_cover_generation_job(job["task_id"], payload)
    return _ok({
        "task_id": job["task_id"],
        "data": job,
        "poll_interval_ms": _JOB_POLL_INTERVAL_MS,
    })


@router.get("/cover-images/generate-jobs/{task_id}")
async def get_cover_image_generation_job(task_id: str):
    job = _image_job_store.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="封面生成任务不存在或已过期。")
    return _ok({"data": job})


@router.get("/cover-images/history")
async def list_cover_history():
    pm = _require_current_project()
    return _ok({"covers": list(_image_service.list_history(pm.get_current_project_dir()))})


@router.delete("/cover-images/history/{cover_id}")
async def delete_cover_history(cover_id: str):
    pm = _require_current_project()
    try:
        deleted = _image_service.delete_cover(pm.get_current_project_dir(), cover_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ok({"deleted": deleted})


@router.post("/cover-images/history/delete-batch")
async def delete_cover_history_batch(request: CoverBatchDeleteRequest):
    pm = _require_current_project()
    cover_ids = [str(cover_id or "").strip() for cover_id in request.cover_ids if str(cover_id or "").strip()]
    if not cover_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的历史封面。")
    result = _image_service.delete_covers(pm.get_current_project_dir(), cover_ids)
    return _ok(result)


@router.get("/cover-images/file/{cover_id}")
async def get_cover_image_file(cover_id: str):
    pm = _require_current_project()
    try:
        image_path = _image_service.get_image_path(pm.get_current_project_dir(), cover_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not image_path:
        raise HTTPException(status_code=404, detail="封面图片不存在。")
    return FileResponse(image_path)


@router.get("/cover-images/thumbnail/{cover_id}")
async def get_cover_image_thumbnail(cover_id: str):
    pm = _require_current_project()
    try:
        image_path = _image_service.get_thumbnail_path(pm.get_current_project_dir(), cover_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not image_path:
        raise HTTPException(status_code=404, detail="封面缩略图不存在。")
    return FileResponse(image_path, media_type="image/jpeg")
