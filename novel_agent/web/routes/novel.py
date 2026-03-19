"""
小说创作API路由模块

包含小说创建、世界观生成、大纲生成、章节撰写等功能。
"""

import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from ..models.requests import (
    CreateNovelRequest,
    GenerateWorldRequest,
    GenerateOutlineRequest,
    WriteChapterRequest
)
from ..dependencies import get_coordinator
from ...config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/create")
async def create_novel(request: CreateNovelRequest):
    """创建小说(流式输出)"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")
    
    async def generate():
        async for progress in coordinator.create_novel(
            novel_type=request.novel_type,
            theme=request.theme,
            requirements=request.requirements,
            protagonist=request.protagonist,
            plot_idea=request.plot_idea,
            volume_count=request.volume_count,
            chapters_per_volume=request.chapters_per_volume
        ):
            yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
    
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


@router.get("/status")
async def get_status():
    """获取项目状态"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")
    
    return JSONResponse(coordinator.get_project_status())


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
