"""
API

API?"""

import json
import time
import re
import httpx
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..models.requests import (
    APIConfigRequest,
    FetchModelsRequest,
    TestConnectionRequest,
    GlobalAPIConfigRequest,
    AddAPIConfigRequest,
    UpdateAPIConfigRequest,
    SetActiveConfigRequest,
    AddModelRequest
)
from ..dependencies import get_coordinator, set_coordinator, get_router_agent
from ...config import config
from ...workflow import NovelCoordinator
from ...constants import TIMEOUTS, LLM_DEFAULTS, SERVER_DEFAULTS
from ...utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

router = APIRouter()


def _sync_router_coordinator(new_coordinator: NovelCoordinator) -> None:
    """Keep RouterAgent coordinator in sync."""
    router_agent = get_router_agent()
    if router_agent and hasattr(router_agent, "set_coordinator"):
        router_agent.set_coordinator(new_coordinator)


@router.get("/settings")
async def get_settings():
    """API"""
    return JSONResponse({
        "api_base": config.llm.api_base,
        "api_key": config.llm.api_key[:8] + "****" if len(config.llm.api_key) > 8 else "****",
        "api_key_set": bool(config.llm.api_key and config.llm.api_key != "your-api-key-here"),
        "model": config.llm.model,
        "max_tokens": config.llm.max_tokens,
        "temperature": config.llm.temperature
    })


@router.post("/settings")
async def save_settings(request: APIConfigRequest):
    """Save API settings to .env file."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    
    # 
    env_content = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_content[key.strip()] = value.strip()
    
    # 
    env_content["OPENAI_API_BASE"] = request.api_base
    env_content["OPENAI_API_KEY"] = request.api_key
    if request.model:
        env_content["OPENAI_MODEL"] = request.model
    
    # ?    env_content.setdefault("OPENAI_API_KEY", "")
    env_content.setdefault("OPENAI_API_BASE", "")
    env_content.setdefault("OPENAI_MODEL", "gpt-4")
    env_content.setdefault("HOST", "0.0.0.0")
    env_content.setdefault("PORT", str(SERVER_DEFAULTS.PORT))
    env_content.setdefault("DEBUG", "false")
    env_content.setdefault("MAX_TOKENS", "4096")
    env_content.setdefault("TEMPERATURE", "0.7")

    # 
    old_env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else None

    try:
        lines = [f"{k}={v}" for k, v in env_content.items()]
        atomic_write_text(env_path, "\n".join(lines), old_content=old_env_content)

        from ...config import Config
        reload_success = Config.reload()
        if not reload_success:
            # rollback when reload fails
            if old_env_content is not None:
                env_path.write_text(old_env_content, encoding="utf-8")
            return JSONResponse({
                "success": False,
                "error": "Failed to reload configuration"
            }, status_code=500)
    except (OSError, IOError, PermissionError) as e:
        logger.error(f"Failed to write .env file: {e}")
        return JSONResponse({
            "success": False,
            "error": f"Failed to save settings: {e}"
        }, status_code=500)

    from ..websocket import WebSocketProgressCallback
    ws_callback = WebSocketProgressCallback()
    new_coordinator = NovelCoordinator(
        config.paths.output_dir,
        progress_callback=ws_callback
    )
    set_coordinator(new_coordinator)
    _sync_router_coordinator(new_coordinator)
    
    return JSONResponse({"success": True, "message": "配置已保存"})


@router.post("/settings/reload")
async def reload_settings():
    """"""
    from ...config import Config
    reload_success = Config.reload()

    if not reload_success:
        return JSONResponse({
            "success": False,
            "error": "Failed to reload configuration"
        }, status_code=500)

    from ..websocket import WebSocketProgressCallback
    ws_callback = WebSocketProgressCallback()
    new_coordinator = NovelCoordinator(
        config.paths.output_dir,
        progress_callback=ws_callback
    )
    set_coordinator(new_coordinator)
    _sync_router_coordinator(new_coordinator)

    return JSONResponse({
        "success": True,
        "data": {
            "api_key": config.llm.api_key,
            "api_base": config.llm.api_base,
            "model": config.llm.model
        }
    })


@router.post("/models")
async def fetch_models(request: FetchModelsRequest):
    """Fetch available model list from API."""
    try:
        api_base = (request.api_base or "").strip()
        api_key = (request.api_key or "").strip()
        config_id = getattr(request, 'config_id', None)
        
        # 优先使用config_id查找配置
        if config_id:
            from ...agent_config import get_config_manager
            manager = get_config_manager()
            for cfg in manager.multi_config.configs:
                if cfg.id == config_id:
                    if not api_base:
                        api_base = (cfg.api_base or "").strip()
                    if not api_key:
                        api_key = (cfg.api_key or "").strip()
                    logger.info(f"Using saved config {config_id} for fetching models")
                    break
        
        # 如果API Key仍为空，尝试从已保存的配置中按api_base查找
        if not api_key and api_base:
            from ...agent_config import get_config_manager
            manager = get_config_manager()
            for cfg in manager.multi_config.configs:
                cfg_base = (cfg.api_base or "").strip()
                cfg_key = (cfg.api_key or "").strip()
                if cfg_base == api_base and cfg_key:
                    api_key = cfg_key
                    logger.info(f"Using saved API key for {api_base}")
                    break
        
        if not api_base:
            return JSONResponse({
                "success": False,
                "error": "缺少API Base URL",
                "models": []
            })
        
        if not api_key:
            return JSONResponse({
                "success": False,
                "error": "缺少API Key。请先保存配置，然后再获取模型列表",
                "models": []
            })
        
        base_url = api_base.rstrip("/")
        models_url = f"{base_url}/models"
        
        async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_SHORT) as client:
            response = await client.get(
                models_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                models = []
                
                if "data" in data:
                    for model in data["data"]:
                        model_id = model.get("id", "")
                        if model_id:
                            models.append(model_id)
                elif isinstance(data, list):
                    for model in data:
                        if isinstance(model, str):
                            models.append(model)
                        elif isinstance(model, dict) and "id" in model:
                            models.append(model["id"])
                
                if models:
                    priority_models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "deepseek-chat", "claude"]
                    def sort_key(m):
                        for i, p in enumerate(priority_models):
                            if p in m.lower():
                                return (0, i, m)
                        return (1, 0, m)
                    models.sort(key=sort_key)
                    
                    return JSONResponse({
                        "success": True,
                        "models": models
                    })
                else:
                    return JSONResponse({
                        "success": False,
                        "error": "未能解析模型列表，请手动输入模型名称",
                        "models": []
                    })
            else:
                return JSONResponse({
                    "success": False,
                    "error": f"请求失败 (HTTP {response.status_code})，该API可能不支持获取模型列表",
                    "models": []
                })
                
    except httpx.TimeoutException:
        return JSONResponse({
            "success": False,
            "error": "请求超时，请检查 API 地址是否正确",
            "models": []
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f": {str(e)}",
            "models": []
        })


@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest):
    """ API """
    try:
        api_base = (request.api_base or "").strip()
        api_key = (request.api_key or "").strip()
        test_model = (request.model or "").strip()
        config_id = (request.config_id or "").strip()

        if config_id:
            from ...agent_config import get_config_manager
            manager = get_config_manager()
            selected_config = next(
                (cfg for cfg in manager.multi_config.configs if cfg.id == config_id),
                None
            )
            if not selected_config:
                return JSONResponse({
                    "success": False,
                    "error": f"Config ID not found or changed: {config_id}. Please refresh and retry."
                })
            if not api_base:
                api_base = (selected_config.api_base or "").strip()
            if not api_key:
                api_key = (selected_config.api_key or "").strip()
            if not test_model and selected_config.models:
                test_model = str(selected_config.models[0]).strip()

        #  config_id  api_base  key
        if not api_key and api_base and not config_id:
            from ...agent_config import get_config_manager
            manager = get_config_manager()
            for cfg in manager.multi_config.configs:
                cfg_base = (cfg.api_base or "").strip()
                cfg_key = (cfg.api_key or "").strip()
                if cfg_base == api_base and cfg_key:
                    api_key = cfg_key
                    if not test_model and cfg.models:
                        test_model = str(cfg.models[0]).strip()
                    break

        if not api_base:
            return JSONResponse({
                "success": False,
                "error": "Missing API base URL."
            })

        if not api_key:
            return JSONResponse({
                "success": False,
                "error": "Missing API key. Save the config first, then test again."
            })

        base_url = api_base.rstrip("/")
        #  /v1 /v4 
        last_segment = base_url.rsplit("/", 1)[-1].lower() if base_url else ""
        if not re.fullmatch(r"v\d+(\.\d+)?", last_segment):
            base_url = base_url + "/v1" if not base_url.endswith("/") else base_url + "v1"

        if not test_model:
            test_model = "gpt-3.5-turbo"

        start_time = time.time()

        async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": test_model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                }
            )

            response_time = int((time.time() - start_time) * 1000)
            error_text = response.text[:400] if response.text else ""
            error_detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    candidate = payload.get("error", payload.get("message", payload.get("detail", "")))
                    if isinstance(candidate, dict):
                        error_detail = str(
                            candidate.get("message")
                            or candidate.get("detail")
                            or candidate.get("code")
                            or candidate
                        )
                    else:
                        error_detail = str(candidate or "")
            except Exception:
                error_detail = ""
            if not error_detail:
                error_detail = error_text
            error_detail = (error_detail or "").strip()[:200]

            if response.status_code == 200:
                return JSONResponse({
                    "success": True,
                    "message": "Connection successful.",
                    "model_tested": test_model,
                    "response_time": response_time
                })
            if response.status_code == 401:
                suffix = f": {error_detail}" if error_detail else ""
                return JSONResponse({
                    "success": False,
                    "error": f"Authentication failed (possible invalid key or account/model access issue){suffix}"
                })
            if response.status_code == 403:
                suffix = f": {error_detail}" if error_detail else ""
                return JSONResponse({
                    "success": False,
                    "error": f"Access denied (insufficient permission for this model or account){suffix}"
                })
            if response.status_code == 404:
                return JSONResponse({
                    "success": False,
                    "error": f"Model '{test_model}' not found or API endpoint is incorrect."
                })
            if response.status_code == 429:
                return JSONResponse({
                    "success": False,
                    "error": "Rate limited. Please retry later."
                })

            return JSONResponse({
                "success": False,
                "error": f"Connection failed (HTTP {response.status_code}): {error_detail or error_text[:200]}"
            })

    except httpx.TimeoutException:
        return JSONResponse({
            "success": False,
                "error": "Connection timeout. Check API base URL and network."
        })
    except httpx.ConnectError as e:
        return JSONResponse({
            "success": False,
            "error": f"Failed to connect to server: {str(e)}"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"Connection failed: {str(e)}"
        })

# ========== API?==========

@router.get("/global-config")
async def get_global_api_config():
    """API"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    cfg = manager.get_global_config()
    multi = manager.get_multi_config()
    
    return JSONResponse({
        "api_base": cfg.api_base,
        "api_key": cfg.api_key[:8] + "****" if len(cfg.api_key) > 8 else "",
        "api_key_set": bool(cfg.api_key),
        "model": cfg.model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "is_configured": cfg.is_configured(),
        "multi_config": {
            "configs": manager.list_api_configs(),
            "active_config_id": multi.active_config_id,
            "active_model": multi.active_model
        }
    })


@router.post("/global-config")
async def save_global_api_config(request: GlobalAPIConfigRequest):
    """Save global API config (legacy compatible)."""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    
    current_api_key = manager.get_global_config().api_key
    
    api_key = request.api_key
    should_keep_original = (
        api_key.endswith("****") or
        api_key == "" or
        (not api_key and current_api_key)
    )
    
    if should_keep_original:
        api_key = current_api_key
    
    manager.set_global_config(
        api_base=request.api_base,
        api_key=api_key,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    return JSONResponse({"success": True, "message": "API"})


# ===== PI =====

@router.get("/api-configs")
async def list_api_configs():
    """PI"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    multi = manager.get_multi_config()
    
    return JSONResponse({
        "configs": manager.list_api_configs(),
        "active_config_id": multi.active_config_id,
        "active_model": multi.active_model
    })


@router.post("/api-configs")
async def add_api_config(request: AddAPIConfigRequest):
    """API"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    
    cfg = manager.add_api_config(
        name=request.name,
        api_base=request.api_base,
        api_key=request.api_key,
        models=request.models,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    return JSONResponse({
        "success": True,
        "message": f"API '{request.name}' ",
        "config": cfg.to_dict()
    })


@router.put("/api-configs/{config_id}")
async def update_api_config_by_id(config_id: str, request: UpdateAPIConfigRequest):
    """PI"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()
    
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.api_base is not None:
        updates["api_base"] = request.api_base
    if request.api_key is not None and not request.api_key.endswith("****"):
        updates["api_key"] = request.api_key
    if request.models is not None:
        updates["models"] = request.models
    if request.temperature is not None:
        updates["temperature"] = request.temperature
    if request.max_tokens is not None:
        updates["max_tokens"] = request.max_tokens
    
    cfg = manager.update_api_config(config_id, **updates)
    
    if cfg:
        return JSONResponse({
            "success": True,
            "message": "API",
            "config": cfg.to_dict()
        })
    else:
        raise HTTPException(status_code=404, detail="")


@router.delete("/api-configs/{config_id}")
async def delete_api_config_by_id(config_id: str):
    """ API """
    from ...agent_config import get_config_manager
    manager = get_config_manager()

    if manager.delete_api_config(config_id):
        return JSONResponse({
            "success": True,
            "message": "API "
        })
    else:
        raise HTTPException(status_code=404, detail="")


@router.post("/api-configs/active")
async def set_active_api_config(request: SetActiveConfigRequest):
    """ API """
    from ...agent_config import get_config_manager
    manager = get_config_manager()

    if manager.set_active_config(request.config_id, request.model):
        return JSONResponse({
            "success": True,
            "message": ""
        })
    else:
        raise HTTPException(status_code=404, detail="")


@router.post("/api-configs/{config_id}/models")
async def add_model_to_api_config(config_id: str, request: AddModelRequest):
    """"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()

    if manager.add_model_to_config(config_id, request.model):
        return JSONResponse({
            "success": True,
            "message": f" '{request.model}' "
        })
    else:
        raise HTTPException(status_code=404, detail="")


@router.delete("/api-configs/{config_id}/models/{model}")
async def remove_model_from_api_config(config_id: str, model: str):
    """"""
    from ...agent_config import get_config_manager
    manager = get_config_manager()

    if manager.remove_model_from_config(config_id, model):
        return JSONResponse({
            "success": True,
            "message": f" '{model}' "
        })
    else:
        raise HTTPException(status_code=404, detail="")
