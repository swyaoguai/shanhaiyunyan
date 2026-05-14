"""
Token统计API路由模块

包含Token使用量的统计、查询和清理功能。
"""

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


def _get_project_manager_safe():
    try:
        from ...project_manager import get_project_manager

        return get_project_manager()
    except Exception:
        return None


def _get_current_project_id() -> str:
    """Resolve the active project scope for token statistics."""
    pm = _get_project_manager_safe()
    if pm is not None:
        return str(getattr(pm, "current_project_id", "") or "")
    return ""


def _resolve_project_scope(scope: str = "all") -> Optional[str]:
    """
    Resolve token-stat query scope.

    The page defaults to all records so users can still see historical usage
    after deleting/switching projects. Passing scope=current keeps the previous
    current-project view.
    """
    normalized = str(scope or "all").strip().lower()
    if normalized == "current":
        return _get_current_project_id()
    return None


def _cleanup_orphan_project_records() -> int:
    pm = _get_project_manager_safe()
    if pm is None:
        return 0
    valid_project_ids = list(getattr(pm, "projects", {}).keys())
    if not valid_project_ids:
        return 0

    from ...utils.token_stats import get_token_stats_store

    return get_token_stats_store().cleanup_project_records_not_in(valid_project_ids)


@router.get("/token-stats/summary")
async def get_token_stats_summary(
    days: int = 30,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取Token统计摘要"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    summary = store.get_summary(
        days=days,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse(summary)


@router.get("/token-stats/daily")
async def get_token_stats_daily(
    days: int = 7,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取每日Token统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_daily_stats(
        days=days,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/weekly")
async def get_token_stats_weekly(
    weeks: int = 4,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取每周Token统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_weekly_stats(
        weeks=weeks,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "period": f"{weeks} weeks",
        "data": stats
    })


@router.get("/token-stats/hourly")
async def get_token_stats_hourly(
    hours: int = 24,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取小时统计（24小时曲线图数据）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_hourly_stats(
        hours=hours,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "period": f"{hours} hours",
        "data": stats
    })


@router.get("/token-stats/by-model")
async def get_token_stats_by_model(
    days: int = 30,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取按模型分组的统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_model_stats(
        days=days,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/by-agent")
async def get_token_stats_by_agent(
    days: int = 30,
    model: str = None,
    scope: str = "all",
):
    """获取按Agent分组的统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_agent_stats(
        days=days,
        model=model,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/filters")
async def get_token_stats_filters(scope: str = "all"):
    """获取可用的筛选选项（模型列表、Agent列表）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    project_id = _resolve_project_scope(scope)
    
    return JSONResponse({
        "models": store.get_available_models(project_id=project_id),
        "current_project_id": _get_current_project_id(),
        "scope": "current" if project_id is not None else "all",
        "agents": []
    })


@router.get("/token-stats/recent")
async def get_token_stats_recent(
    limit: int = 100,
    model: str = None,
    agent_name: str = None,
    scope: str = "all",
):
    """获取最近的Token使用记录"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    records = store.get_recent_records(
        limit=limit,
        model=model,
        agent_name=agent_name,
        project_id=_resolve_project_scope(scope),
    )
    
    return JSONResponse({
        "total": len(records),
        "records": records
    })


@router.post("/token-stats/cleanup")
async def cleanup_token_stats(days: int = 90):
    """清理旧的Token统计记录"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    deleted_count = store.cleanup_old_records(
        days=days,
        project_id=None,
    )
    deleted_orphan_count = _cleanup_orphan_project_records()
    
    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count + deleted_orphan_count,
        "old_record_count": deleted_count,
        "orphan_record_count": deleted_orphan_count,
        "message": f"已删除 {deleted_count} 条 {days} 天前的记录，并清理 {deleted_orphan_count} 条已删除项目记录"
    })


@router.post("/token-stats/reset")
async def reset_token_stats():
    """重置所有Token统计数据（清空整个表）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    deleted_count = store.reset_all(project_id=None)
    
    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已重置全部统计数据，共删除 {deleted_count} 条记录"
    })


@router.post("/token-stats/cleanup-orphans")
async def cleanup_orphan_token_stats():
    """清理已经不存在项目的Token统计记录。"""
    deleted_count = _cleanup_orphan_project_records()

    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已清理 {deleted_count} 条已删除项目的统计记录"
    })
