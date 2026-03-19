"""
辅助记忆 API 路由

提供长期辅助记忆的分类/条目 CRUD、检索、注入预览、历史回滚能力。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ...aux_memory import get_aux_memory_service
from ...project_manager import get_project_manager
from ..models.requests import (
    AuxMemoryItemBatchDeleteRequest,
    AuxMemoryItemBatchUpdateRequest,
    AuxMemoryCategoryCreateRequest,
    AuxMemoryCategoryUpdateRequest,
    AuxMemoryItemClearRequest,
    AuxMemoryConfigUpdateRequest,
    AuxMemoryInjectionPreviewRequest,
    AuxMemoryItemCreateRequest,
    AuxMemoryItemUpdateRequest,
    AuxMemoryResourceImportRequest,
    AuxMemoryRetrieveRequest,
    AuxMemoryRollbackRequest,
    AuxMemoryTraceRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_project_id() -> str:
    pm = get_project_manager()
    if not pm.current_project_id:
        raise HTTPException(status_code=400, detail="请先选择一个项目")
    return pm.current_project_id


@router.get("/aux-memory/categories")
async def list_aux_memory_categories(
    user_id: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
):
    """获取辅助记忆分类列表"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    categories = service.list_categories(project_id, user_id=user_id, enabled_only=enabled_only)
    return JSONResponse({"success": True, "categories": [category.to_dict() for category in categories]})


@router.post("/aux-memory/categories")
async def create_aux_memory_category(request: AuxMemoryCategoryCreateRequest):
    """创建辅助记忆分类"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    category = service.create_category(
        project_id=project_id,
        name=request.name,
        description=request.description,
        summary=request.summary,
        enabled=request.enabled,
        user_id=request.user_id,
    )
    return JSONResponse({"success": True, "category": category.to_dict()})


@router.patch("/aux-memory/categories/{category_id}")
async def update_aux_memory_category(category_id: str, request: AuxMemoryCategoryUpdateRequest):
    """更新辅助记忆分类"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    updates = {key: value for key, value in request.model_dump().items() if value is not None}
    category = service.update_category(project_id, category_id, updates)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    return JSONResponse({"success": True, "category": category.to_dict()})


@router.delete("/aux-memory/categories/{category_id}")
async def delete_aux_memory_category(category_id: str):
    """删除辅助记忆分类"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    deleted, removed_items = service.delete_category(project_id, category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="分类不存在")
    return JSONResponse(
        {
            "success": True,
            "message": "分类已删除",
            "removed_items": removed_items,
        }
    )


@router.get("/aux-memory/items")
async def list_aux_memory_items(
    category_id: str = Query(default=""),
    query: str = Query(default=""),
    user_id: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
    memory_type: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """获取辅助记忆条目列表"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    items = service.list_items(
        project_id=project_id,
        category_id=category_id or None,
        query=query,
        user_id=user_id,
        enabled_only=enabled_only,
        memory_type=memory_type,
    )
    total = len(items)
    paged_items = items[offset: offset + limit]
    return JSONResponse(
        {
            "success": True,
            "items": [item.to_dict() for item in paged_items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@router.post("/aux-memory/items")
async def create_aux_memory_item(request: AuxMemoryItemCreateRequest):
    """创建辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    try:
        item = service.create_item(
            project_id=project_id,
            summary=request.summary,
            details=request.details,
            category_id=request.category_id,
            memory_type=request.memory_type,
            score=request.score,
            enabled=request.enabled,
            tags=request.tags,
            user_id=request.user_id,
            source_resource_id=request.source_resource_id,
            extra=request.extra,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse({"success": True, "item": item.to_dict()})


@router.post("/aux-memory/items/batch-update")
async def batch_update_aux_memory_items(request: AuxMemoryItemBatchUpdateRequest):
    """批量更新辅助记忆条目启用状态"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    item_ids = [str(item_id).strip() for item_id in (request.item_ids or []) if str(item_id).strip()]
    if not item_ids:
        raise HTTPException(status_code=400, detail="请至少选择 1 条记忆条目")

    result = service.batch_update_items_enabled(
        project_id=project_id,
        item_ids=item_ids,
        enabled=request.enabled,
    )
    return JSONResponse({"success": True, **result})


@router.post("/aux-memory/items/batch-delete")
async def batch_delete_aux_memory_items(request: AuxMemoryItemBatchDeleteRequest):
    """批量删除辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    item_ids = [str(item_id).strip() for item_id in (request.item_ids or []) if str(item_id).strip()]
    if not item_ids:
        raise HTTPException(status_code=400, detail="请至少选择 1 条记忆条目")

    deleted_count = service.delete_items(project_id=project_id, item_ids=item_ids, action="batch_delete_items")
    return JSONResponse({"success": True, "requested": len(set(item_ids)), "deleted": deleted_count})


@router.post("/aux-memory/items/clear")
async def clear_aux_memory_items(request: AuxMemoryItemClearRequest):
    """清空当前筛选条件下的辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    result = service.clear_items(
        project_id=project_id,
        category_id=request.category_id or None,
        query=request.query,
        user_id=request.user_id,
        enabled_only=request.enabled_only,
        memory_type=request.memory_type,
    )
    return JSONResponse({"success": True, **result})


@router.patch("/aux-memory/items/{item_id}")
async def update_aux_memory_item(item_id: str, request: AuxMemoryItemUpdateRequest):
    """更新辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    updates = {key: value for key, value in request.model_dump().items() if value is not None}
    try:
        item = service.update_item(project_id, item_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    return JSONResponse({"success": True, "item": item.to_dict()})


@router.delete("/aux-memory/items/{item_id}")
async def delete_aux_memory_item(item_id: str):
    """删除辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    deleted = service.delete_item(project_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="条目不存在")
    return JSONResponse({"success": True, "message": "条目已删除"})


@router.post("/aux-memory/retrieve")
async def retrieve_aux_memory(request: AuxMemoryRetrieveRequest):
    """检索辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    mode = request.mode if request.mode in {"fast", "deep"} else "fast"

    items = service.retrieve(
        project_id=project_id,
        query=request.query,
        top_k=request.top_k,
        mode=mode,
        user_id=request.user_id or None,
        category_ids=request.category_ids,
        enabled_only=True,
        where=request.where,
    )
    return JSONResponse(
        {
            "success": True,
            "items": items,
            "count": len(items),
            "mode": mode,
        }
    )


@router.post("/aux-memory/injection-preview")
async def preview_aux_memory_injection(request: AuxMemoryInjectionPreviewRequest):
    """生成辅助记忆注入预览"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    mode = request.mode if request.mode in {"fast", "deep"} else "fast"

    preview = service.build_injection_preview(
        project_id=project_id,
        query=request.query,
        top_k=request.top_k,
        user_id=request.user_id or None,
        category_ids=request.category_ids,
        mode=mode,
        max_chars=request.max_chars,
        where=request.where,
    )
    return JSONResponse({"success": True, **preview})


@router.post("/aux-memory/resources/import")
async def import_aux_memory_resource(request: AuxMemoryResourceImportRequest):
    """导入文本资源并自动创建辅助记忆条目"""
    project_id = _require_project_id()
    service = get_aux_memory_service()

    try:
        result = service.import_resource_text(
            project_id=project_id,
            content=request.content,
            source_type=request.source_type,
            user_id=request.user_id,
            title=request.title,
            category_id=request.category_id,
            min_line_chars=request.min_line_chars,
            max_items=request.max_items,
            default_score=request.default_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "success": True,
            "resource": result.get("resource", {}),
            "items": result.get("items", []),
            "imported_count": len(result.get("items", [])),
        }
    )


@router.get("/aux-memory/history")
async def list_aux_memory_history(limit: int = Query(default=20, ge=1, le=100)):
    """获取辅助记忆历史快照列表"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    rows = service.list_history(project_id, limit=limit)
    return JSONResponse({"success": True, "history": rows})


@router.get("/aux-memory/injection-records")
async def list_aux_memory_injection_records(
    limit: int = Query(default=20, ge=1, le=100),
    source: str = Query(default=""),
):
    """获取辅助记忆注入命中记录"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    rows = service.list_injection_records(project_id=project_id, limit=limit, source=source)
    return JSONResponse({"success": True, "records": rows})


@router.post("/aux-memory/trace")
async def get_aux_memory_trace(request: AuxMemoryTraceRequest):
    """获取辅助记忆条目的来源和引用追踪"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    trace = service.get_item_trace(
        project_id=project_id,
        item_id=request.item_id,
        limit=request.limit,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="条目不存在")
    return JSONResponse({"success": True, "trace": trace})


@router.post("/aux-memory/rollback")
async def rollback_aux_memory(request: AuxMemoryRollbackRequest):
    """回滚辅助记忆到指定历史快照"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    result = service.rollback(project_id, request.history_id)
    if not result:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return JSONResponse({"success": True, "result": result})


@router.get("/aux-memory/config")
async def get_aux_memory_config():
    """获取辅助记忆配置"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    return JSONResponse({"success": True, "config": service.get_config(project_id)})


@router.patch("/aux-memory/config")
async def update_aux_memory_config(request: AuxMemoryConfigUpdateRequest):
    """更新辅助记忆配置"""
    project_id = _require_project_id()
    service = get_aux_memory_service()
    updates = {key: value for key, value in request.model_dump().items() if value is not None}
    config = service.update_config(project_id, updates)
    return JSONResponse({"success": True, "config": config})
