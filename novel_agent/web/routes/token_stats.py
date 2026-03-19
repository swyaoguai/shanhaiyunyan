"""
Token统计API路由模块

包含Token使用量的统计、查询和清理功能。
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/token-stats/summary")
async def get_token_stats_summary(
    days: int = 30,
    model: str = None,
    agent_name: str = None
):
    """获取Token统计摘要"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    summary = store.get_summary(days=days, model=model, agent_name=agent_name)
    
    return JSONResponse(summary)


@router.get("/token-stats/daily")
async def get_token_stats_daily(
    days: int = 7,
    model: str = None,
    agent_name: str = None
):
    """获取每日Token统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_daily_stats(days=days, model=model, agent_name=agent_name)
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/weekly")
async def get_token_stats_weekly(
    weeks: int = 4,
    model: str = None,
    agent_name: str = None
):
    """获取每周Token统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_weekly_stats(weeks=weeks, model=model, agent_name=agent_name)
    
    return JSONResponse({
        "period": f"{weeks} weeks",
        "data": stats
    })


@router.get("/token-stats/hourly")
async def get_token_stats_hourly(
    hours: int = 24,
    model: str = None,
    agent_name: str = None
):
    """获取小时统计（24小时曲线图数据）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_hourly_stats(hours=hours, model=model, agent_name=agent_name)
    
    return JSONResponse({
        "period": f"{hours} hours",
        "data": stats
    })


@router.get("/token-stats/by-model")
async def get_token_stats_by_model(
    days: int = 30,
    agent_name: str = None
):
    """获取按模型分组的统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_model_stats(days=days, agent_name=agent_name)
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/by-agent")
async def get_token_stats_by_agent(
    days: int = 30,
    model: str = None
):
    """获取按Agent分组的统计"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    stats = store.get_agent_stats(days=days, model=model)
    
    return JSONResponse({
        "period": f"{days} days",
        "data": stats
    })


@router.get("/token-stats/filters")
async def get_token_stats_filters():
    """获取可用的筛选选项（模型列表、Agent列表）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    
    return JSONResponse({
        "models": store.get_available_models(),
        "agents": store.get_available_agents()
    })


@router.get("/token-stats/recent")
async def get_token_stats_recent(
    limit: int = 100,
    model: str = None,
    agent_name: str = None
):
    """获取最近的Token使用记录"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    records = store.get_recent_records(limit=limit, model=model, agent_name=agent_name)
    
    return JSONResponse({
        "total": len(records),
        "records": records
    })


@router.post("/token-stats/cleanup")
async def cleanup_token_stats(days: int = 90):
    """清理旧的Token统计记录"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    deleted_count = store.cleanup_old_records(days=days)
    
    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已删除 {deleted_count} 条 {days} 天前的记录"
    })


@router.post("/token-stats/reset")
async def reset_token_stats():
    """重置所有Token统计数据（清空整个表）"""
    from ...utils.token_stats import get_token_stats_store
    
    store = get_token_stats_store()
    deleted_count = store.reset_all()
    
    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count,
        "message": f"已重置所有统计数据，共删除 {deleted_count} 条记录"
    })