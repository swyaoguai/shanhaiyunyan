"""Novel cover generation APIs."""

from __future__ import annotations

import logging

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


def _ok(data: dict) -> JSONResponse:
    return JSONResponse({"success": True, **data})


def _require_current_project():
    pm = get_project_manager()
    if not getattr(pm, "current_project_id", ""):
        raise HTTPException(status_code=400, detail="请先选择小说项目。")
    return pm


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
    pm = _require_current_project()
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请先生成或填写封面提示词。")

    payload = request.model_dump()
    payload["prompt"] = prompt
    payload["project_dir"] = str(pm.get_current_project_dir())
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
