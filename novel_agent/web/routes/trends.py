"""
热点搜索API路由模块

包含热点状态检查、搜索、平台列表和配置管理功能。
使用 Skill 系统替代 MCP。
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..models.requests import TrendSearchRequest, TrendsConfigRequest, TrendsVisibilityRequest
from ...utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter()

# 热点配置默认值常量
TRENDS_CONFIG_DEFAULTS = {
    "enabled": True,
    "auto_refresh": False,
    "refresh_interval": 300,
    "default_platforms": [],
    "show_in_infinite_write": True,
    "show_in_multi_agent": True
}

# 平台ID到Skill方法名称的映射
PLATFORM_METHOD_MAP = {
    "douban": "get_douban_trending",
    "weread": "get_weread_trending",
    "zhihu": "get_zhihu_trending",
    "gcores": "get_gcores_trending",
    "toutiao": "get_toutiao_trending",
    "netease": "get_netease_trending",
    "tencent": "get_tencent_trending",
    "thepaper": "get_thepaper_trending",
    "bilibili": "get_bilibili_trending",
    "douyin": "get_douyin_trending",
    "weibo": "get_weibo_trending",
    "36kr": "get_36kr_trending",
    "sspai": "get_sspai_trending",
    "ifanr": "get_ifanr_trending",
    "juejin": "get_juejin_trending",
    "smzdm": "get_smzdm_trending",
}


def _get_skill_service():
    """获取 Skill 服务实例"""
    try:
        from skills.trends_search.scripts.trends_service import get_service
        return get_service()
    except Exception as e:
        logger.error(f"Failed to load trends_search skill: {e}")
        return None


@router.get("/trends/status")
async def get_trends_status():
    """获取热点搜索服务状态"""
    try:
        service = _get_skill_service()
        if service is None:
            return JSONResponse({
                "available": False,
                "tools": [],
                "message": "热点搜索 Skill 未找到，请检查 skills/trends_search 目录"
            })
        
        # 检查 Skill 是否存在
        skill_path = Path(__file__).parent.parent.parent.parent / "skills" / "trends_search"
        is_available = skill_path.exists() and (skill_path / "SKILL.md").exists()
        
        tools = [{"name": method, "description": f"获取{platform}热点"}
                 for platform, method in PLATFORM_METHOD_MAP.items()]
        
        return JSONResponse({
            "available": is_available,
            "tools": tools,
            "server": "trends_search (Skill)",
            "message": "热点服务已连接 (Skill系统)" if is_available else "热点搜索 Skill 未找到"
        })
    except Exception as e:
        logger.warning(f"[Trends] 热点服务状态检查失败: {e}")
        return JSONResponse({
            "available": False,
            "tools": [],
            "error": str(e),
            "message": "热点搜索服务未连接"
        })


@router.post("/trends/search")
async def search_trends(request: TrendSearchRequest):
    """搜索热点/热梗"""
    try:
        service = _get_skill_service()
        if service is None:
            return JSONResponse({
                "success": False,
                "trends": [],
                "platform": request.platform,
                "error": "热点搜索 Skill 未找到"
            })
        
        # 获取方法名
        method_name = PLATFORM_METHOD_MAP.get(request.platform, f"get_{request.platform}_trending")
        
        # 检查方法是否存在
        if not hasattr(service, method_name):
            return JSONResponse({
                "success": False,
                "trends": [],
                "platform": request.platform,
                "error": f"平台 {request.platform} 不支持"
            })
        
        # 调用 Skill 方法
        result = getattr(service, method_name)(limit=request.limit or 20)
        
        if not result or not result.get("success"):
            error_msg = result.get("error", "获取热点失败") if result else "获取热点失败"
            return JSONResponse({
                "success": False,
                "trends": [],
                "platform": request.platform,
                "error": error_msg
            })
        
        # 格式化数据
        trends_data = result.get("data", [])
        normalized_trends = []
        for i, trend in enumerate(trends_data[:request.limit]):
            normalized = {
                "title": trend.get("title", f"热点 {i + 1}"),
                "hot": str(trend.get("hot", "")),
                "url": trend.get("url", ""),
                "rank": i + 1
            }
            normalized_trends.append(normalized)
        
        logger.info(f"[Trends] 平台 {request.platform} 获取到 {len(normalized_trends)} 条热点")
        
        return JSONResponse({
            "success": True,
            "trends": normalized_trends,
            "platform": request.platform,
            "count": len(normalized_trends)
        })
        
    except Exception as e:
        logger.error(f"热点搜索失败: {e}")
        return JSONResponse({
            "success": False,
            "trends": [],
            "platform": request.platform,
            "error": str(e),
            "message": f"获取{request.platform}热点失败"
        })


@router.get("/trends/platforms")
async def get_trend_platforms():
    """获取支持的热点平台列表"""
    # 只保留抖音和头条两个平台
    platforms = [
        {"id": "douyin", "name": "抖音热点", "icon": "ri-tiktok-fill", "description": "获取抖音热点视频", "category": "视频娱乐"},
        {"id": "toutiao", "name": "头条热榜", "icon": "ri-newspaper-fill", "description": "获取今日头条热门", "category": "热点资讯"},
    ]
    
    return JSONResponse({"platforms": platforms})


@router.post("/trends/multi-search")
async def multi_search_trends(platforms: Optional[List[str]] = None):
    """同时搜索多个平台的热点"""
    results = {}
    target_platforms = platforms or ["weibo", "zhihu"]
    service = _get_skill_service()
    
    if service is None:
        return JSONResponse({
            "success": False,
            "results": {},
            "error": "热点搜索 Skill 未找到"
        })
    
    for platform in target_platforms:
        try:
            method_name = PLATFORM_METHOD_MAP.get(platform, f"get_{platform}_trending")
            
            if not hasattr(service, method_name):
                results[platform] = {
                    "success": False,
                    "error": f"平台 {platform} 不支持",
                    "trends": []
                }
                continue
            
            result = getattr(service, method_name)(limit=10)
            
            if result and result.get("success"):
                results[platform] = {
                    "success": True,
                    "trends": result.get("data", [])[:10]
                }
            else:
                results[platform] = {
                    "success": False,
                    "error": result.get("error", "获取失败") if result else "获取失败",
                    "trends": []
                }
        except Exception as e:
            results[platform] = {
                "success": False,
                "error": str(e),
                "trends": []
            }
    
    return JSONResponse({
        "success": True,
        "results": results
    })


@router.get("/trends/config")
async def get_trends_config():
    """获取热点搜索配置"""
    config_path = Path(__file__).parent.parent.parent / "data" / "trends_config.json"
    
    config_data = TRENDS_CONFIG_DEFAULTS.copy()
    
    if config_path.exists():
        try:
            saved_config = json.loads(config_path.read_text(encoding="utf-8"))
            config_data.update(saved_config)
        except Exception as e:
            logger.warning(f"[Trends] 加载热点配置失败，使用默认配置: {e}")
    
    return JSONResponse(config_data)


@router.post("/trends/config")
async def save_trends_config(request: TrendsConfigRequest):
    """保存热点搜索配置"""
    config_path = Path(__file__).parent.parent.parent / "data" / "trends_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"[TrendsConfig] 收到保存请求: platforms={request.default_platforms}")
    
    config_data = {}
    
    if config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            logger.info(f"[TrendsConfig] 加载现有配置: {config_data}")
        except Exception as e:
            logger.error(f"[TrendsConfig] 加载配置失败: {e}")
    
    if request.enabled is not None:
        config_data["enabled"] = request.enabled
    if request.auto_refresh is not None:
        config_data["auto_refresh"] = request.auto_refresh
    if request.refresh_interval is not None:
        config_data["refresh_interval"] = request.refresh_interval
    if request.default_platforms is not None:
        config_data["default_platforms"] = request.default_platforms
        logger.info(f"[TrendsConfig] 正在更新 default_platforms 为: {request.default_platforms}")
    if request.show_in_infinite_write is not None:
        config_data["show_in_infinite_write"] = request.show_in_infinite_write
    if request.show_in_multi_agent is not None:
        config_data["show_in_multi_agent"] = request.show_in_multi_agent
    
    for key, default_value in TRENDS_CONFIG_DEFAULTS.items():
        if key not in config_data:
            config_data[key] = default_value
    
    try:
        old_content = config_path.read_text(encoding="utf-8") if config_path.exists() else None
        atomic_write_json(
            config_path,
            config_data,
            old_content=old_content,
            ensure_ascii=False,
            indent=2,
        )
        logger.info(f"[TrendsConfig] 配置已保存: {config_data}")
    except Exception as e:
        logger.error(f"[TrendsConfig] 保存配置失败: {e}")
        return JSONResponse({
            "success": False,
            "error": f"保存失败: {str(e)}"
        })
    
    return JSONResponse({
        "success": True,
        "message": "热点配置已保存",
        "saved_config": config_data
    })


@router.post("/trends/visibility")
async def save_trends_visibility(request: TrendsVisibilityRequest):
    """保存热点显示开关配置"""
    config_path = Path(__file__).parent.parent.parent / "data" / "trends_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    config_data = {}
    
    if config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            logger.info(f"[TrendsVisibility] 加载现有配置: {config_data}")
        except Exception as e:
            logger.error(f"[TrendsVisibility] 加载配置失败: {e}")
    
    config_data["show_in_infinite_write"] = request.show_in_infinite_write
    config_data["show_in_multi_agent"] = request.show_in_multi_agent
    
    for key, default_value in TRENDS_CONFIG_DEFAULTS.items():
        if key not in config_data:
            config_data[key] = default_value
    
    logger.info(f"[TrendsVisibility] 保存配置: {config_data}")
    old_content = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    atomic_write_json(
        config_path,
        config_data,
        old_content=old_content,
        ensure_ascii=False,
        indent=2,
    )
    
    return JSONResponse({
        "success": True,
        "message": "热点显示配置已保存"
    })