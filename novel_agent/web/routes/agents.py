"""
Agent配置API路由模块

包含Agent列表、Agent配置管理、模型获取等功能。
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..models.requests import AgentConfigUpdateRequest, FetchModelsRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/agents")
async def list_agents(include_advanced: bool = Query(False)):
    """获取所有Agent及其配置状态"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    global_config = manager.get_global_config()
    return JSONResponse({
        "agents": manager.list_agents(include_advanced=include_advanced),
        "global_configured": global_config.is_configured(),
        "global_model": global_config.model or "(未配置)"
    })


@router.get("/agents/{agent_name}")
async def get_agent_config(agent_name: str):
    """获取单个Agent的配置"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    cfg = manager.get_config(agent_name)
    global_config = manager.get_global_config()
    return JSONResponse({
        "name": cfg.agent_name,
        "api_config_id": cfg.api_config_id,
        "api_base": cfg.api_base,
        "api_key": cfg.api_key[:8] + "****" if len(cfg.api_key) > 8 else "",
        "model": cfg.model,
        "api_type": cfg.api_type,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "description": cfg.description,
        "is_configured": cfg.is_configured(),
        "use_global": cfg.use_global,
        "global_configured": global_config.is_configured(),
        "global_model": global_config.model
    })


@router.post("/agents/{agent_name}")
async def update_agent_config(agent_name: str, request: AgentConfigUpdateRequest):
    """更新Agent配置"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    
    updates = {}
    selected_api_config = None
    if request.api_config_id is not None:
        updates['api_config_id'] = request.api_config_id
        if request.api_config_id:
            selected_api_config = next(
                (cfg for cfg in manager.multi_config.configs if cfg.id == request.api_config_id),
                None
            )
            if selected_api_config:
                updates['api_base'] = selected_api_config.api_base
                updates['api_key'] = selected_api_config.api_key
                updates['api_type'] = getattr(selected_api_config, 'api_type', 'openai_chat') or 'openai_chat'
                if selected_api_config.models:
                    updates['model'] = selected_api_config.models[0]

    if request.api_base is not None:
        updates['api_base'] = request.api_base
    # 避免前端误传空字符串覆盖已保存的 Key
    if request.api_key is not None and request.api_key != "" and not request.api_key.endswith("****"):
        updates['api_key'] = request.api_key
    if request.model is not None:
        updates['model'] = request.model
    if request.api_type is not None:
        updates['api_type'] = request.api_type
    if request.temperature is not None:
        updates['temperature'] = request.temperature
    if request.max_tokens is not None:
        updates['max_tokens'] = request.max_tokens
    if request.use_global is not None:
        updates['use_global'] = request.use_global

    # 兼容旧前端：未传 api_config_id 时，按 api_base+model 反推配置ID，避免刷新回显错乱
    if (
        request.api_config_id is None and
        updates.get('use_global') is False and
        (request.api_base or request.model)
    ):
        target_base = str((request.api_base or "").strip())
        target_model = str((request.model or "").strip())
        matched = None
        for cfg in manager.multi_config.configs:
            if target_base and cfg.api_base != target_base:
                continue
            if target_model and target_model not in (cfg.models or []):
                continue
            matched = cfg
            break
        if matched:
            updates.setdefault('api_config_id', matched.id)
            updates.setdefault('api_base', matched.api_base)
            updates.setdefault('api_key', matched.api_key)
            updates.setdefault('api_type', getattr(matched, 'api_type', 'openai_chat') or 'openai_chat')
    
    if updates:
        manager.update_config(agent_name, **updates)
        logger.info(f"[AgentConfig] 更新 {agent_name} 配置: {updates}")
    
    return JSONResponse({"success": True, "message": f"{agent_name} 配置已更新"})


@router.post("/agents/copy-to-all")
async def copy_config_to_all(source: str):
    """将一个Agent的配置复制到所有Agent"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    manager.copy_config_to_all(source)
    return JSONResponse({"success": True, "message": "配置已复制到所有Agent"})


@router.post("/fetch-models")
async def fetch_models_v2(request: FetchModelsRequest):
    """从API获取可用模型列表（兼容OpenAI v1接口格式）"""
    from .settings import fetch_models

    return await fetch_models(request)
