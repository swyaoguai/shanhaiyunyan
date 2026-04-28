"""
提示词管理API路由模块

包含Agent提示词的查询、保存、删除和重载功能。
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..models.requests import SavePromptRequest

router = APIRouter()


def _ensure_prompt_agent_visible(pm, agent_type: str, *, include_advanced: bool = False) -> None:
    normalized = str(agent_type or "").strip()
    is_visible = pm.is_user_visible_agent(normalized) or (include_advanced and pm.is_advanced_agent(normalized))
    if not normalized or normalized.startswith('_') or not is_visible:
        raise HTTPException(status_code=404, detail=f"普通设置中不可访问的Agent类型: {agent_type}")


@router.get("/prompts")
async def list_prompts(include_advanced: bool = Query(False)):
    """列出所有Agent类型及其可用的任务提示词"""
    try:
        from ...prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        agents = pm.list_agents(include_advanced=include_advanced)
        
        return JSONResponse({
            "success": True,
            "agents": agents
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"加载Agent列表失败: {str(e)}",
            "agents": []
        })


@router.get("/prompts/{agent_type}")
async def get_agent_prompts(agent_type: str, include_advanced: bool = Query(False)):
    """获取指定Agent的所有提示词"""
    try:
        from ...prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
        
        system_prompt = pm.get_system_prompt_raw(agent_type)
        tasks = pm.list_tasks(agent_type)
        
        has_custom = {}
        for task in tasks:
            has_custom[task["name"]] = task.get("is_custom", False)
        
        return JSONResponse({
            "success": True,
            "agent_type": agent_type,
            "system_prompt": system_prompt,
            "tasks": tasks,
            "has_custom": has_custom
        })
    except ValueError as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"加载提示词失败: {str(e)}"
        })


@router.get("/prompts/{agent_type}/{task_name}")
async def get_task_prompt(agent_type: str, task_name: str, include_advanced: bool = Query(False)):
    """获取指定任务的提示词"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
    
    try:
        prompt = pm.get_task_prompt(agent_type, task_name)
        is_custom = pm.has_custom_prompt(agent_type, task_name)
        
        result = {
            "success": True,
            "agent_type": agent_type,
            "task_name": task_name,
            "prompt": prompt,
            "is_custom": is_custom
        }
        
        if is_custom:
            default_prompt = pm.get_default_prompt(agent_type, task_name)
            result["default_prompt"] = default_prompt
        
        return JSONResponse(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/prompts/{agent_type}/{task_name}")
async def save_custom_prompt(agent_type: str, task_name: str, request: SavePromptRequest, include_advanced: bool = Query(False)):
    """保存自定义提示词"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
    
    try:
        pm.save_custom_prompt(agent_type, task_name, request.content)
        return JSONResponse({
            "success": True,
            "message": f"已保存 {agent_type}/{task_name} 的自定义提示词"
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/prompts/{agent_type}/{task_name}")
async def delete_custom_prompt(agent_type: str, task_name: str, include_advanced: bool = Query(False)):
    """删除自定义提示词，恢复使用默认提示词"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
    
    try:
        pm.delete_custom_prompt(agent_type, task_name)
        return JSONResponse({
            "success": True,
            "message": f"已删除 {agent_type}/{task_name} 的自定义提示词，将使用默认提示词"
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/prompts/reload")
async def reload_prompts():
    """重新加载所有提示词配置"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    pm.reload()
    
    return JSONResponse({
        "success": True,
        "message": "提示词配置已重新加载"
    })


@router.post("/prompts/{agent_type}/system")
async def save_system_prompt(agent_type: str, request: SavePromptRequest, include_advanced: bool = Query(False)):
    """保存自定义系统提示词"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
    
    try:
        pm.save_custom_prompt(agent_type, "system", request.content)
        return JSONResponse({
            "success": True,
            "message": f"已保存 {agent_type} 的自定义系统提示词"
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/prompts/{agent_type}/system")
async def delete_system_prompt(agent_type: str, include_advanced: bool = Query(False)):
    """删除自定义系统提示词"""
    from ...prompts.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    _ensure_prompt_agent_visible(pm, agent_type, include_advanced=include_advanced)
    
    try:
        pm.delete_custom_prompt(agent_type, "system")
        return JSONResponse({
            "success": True,
            "message": f"已删除 {agent_type} 的自定义系统提示词"
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
