"""
API

API?"""

import json
import asyncio
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
    TimeoutSettingsRequest,
    AddAPIConfigRequest,
    UpdateAPIConfigRequest,
    SetActiveConfigRequest,
    AddModelRequest
)
from ..runtime_refresh import refresh_runtime_after_config_reload
from ...config import config
from ...constants import TIMEOUTS, LLM_DEFAULTS, SERVER_DEFAULTS, get_app_root
from ...cover_image_service import CoverImageService
from ...timeout_settings import get_timeout_setting_ranges, get_timeout_settings, save_timeout_settings
from ...utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

router = APIRouter()

_IMAGE_TEST_TIMEOUT_SECONDS = 120.0
_IMAGE_TEST_RETRY_TIMEOUT_SECONDS = 180.0
_IMAGE_TEST_CONNECT_TIMEOUT_SECONDS = 30.0
_IMAGE_TEST_GATEWAY_RETRY_DELAY_SECONDS = 3.0
_IMAGE_TEST_GATEWAY_RETRY_STATUS = {503, 504, 524}


def _normalize_openai_base_url(api_base: str) -> str:
    base_url = str(api_base or "").strip().rstrip("/")
    if not base_url:
        return ""
    last_segment = base_url.rsplit("/", 1)[-1].lower() if base_url else ""
    if not re.fullmatch(r"v\d+(\.\d+)?", last_segment):
        base_url = f"{base_url}/v1"
    return base_url


def _normalize_anthropic_base_url(api_base: str) -> str:
    """Return Anthropic root base URL; callers append /v1/* explicitly."""
    base_url = str(api_base or "").strip().rstrip("/")
    if not base_url:
        return ""

    # Anthropic SDK/raw HTTP endpoints use root base + /v1/messages or /v1/models.
    # Users and OpenAI-compatible UIs may save a /v1 suffix, so strip it to avoid
    # accidental /v1/v1/* requests.
    last_segment = base_url.rsplit("/", 1)[-1].lower()
    if re.fullmatch(r"v\d+(\.\d+)?", last_segment):
        base_url = base_url.rsplit("/", 1)[0].rstrip("/")
    return base_url


def _is_mimo_api_base(api_base: str) -> bool:
    """Return True for Xiaomi MiMo API bases that document api-key auth."""
    return "xiaomimimo.com" in str(api_base or "").lower()


def _is_tsc5_api_base(api_base: str) -> bool:
    return "tsc5.top" in str(api_base or "").lower()


def _build_openai_compatible_headers(api_key: str, api_base: str) -> dict[str, str]:
    """Build headers for OpenAI-compatible providers.

    Xiaomi MiMo documents both api-key and Bearer auth, with api-key shown in
    curl examples. Keep standard Bearer auth for other OpenAI-compatible APIs.
    """
    headers = {"Content-Type": "application/json"}
    if _is_mimo_api_base(api_base):
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_anthropic_headers(api_key: str, api_base: str) -> dict[str, str]:
    """Build headers for Anthropic-compatible providers.

    Official Anthropic uses x-api-key + anthropic-version. Xiaomi MiMo's
    Anthropic-compatible endpoint documents api-key auth under /anthropic/v1.
    New API-compatible relays such as TSC5 document Bearer auth for
    /v1/messages, so use the same header shape in tests and runtime calls.
    """
    headers = {"Content-Type": "application/json"}
    if _is_mimo_api_base(api_base):
        headers["api-key"] = api_key
    elif _is_tsc5_api_base(api_base) or "anthropic.com" not in str(api_base or "").lower():
        headers["Authorization"] = f"Bearer {api_key}"
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    return headers


def _mimo_openai_models_url_from_anthropic_base(api_base: str) -> str:
    """Map MiMo Anthropic-compatible base to the same host's OpenAI models endpoint.

    MiMo documents Anthropic chat at /anthropic/v1/messages, but the model list
    endpoint is exposed by the OpenAI-compatible /v1/models path on the same
    host. This still returns real remote models; it is not a built-in fallback.
    """
    base_url = _normalize_anthropic_base_url(api_base)
    if not base_url:
        return ""

    anthropic_suffix = "/anthropic"
    if base_url.lower().endswith(anthropic_suffix):
        base_url = base_url[: -len(anthropic_suffix)].rstrip("/")
    return f"{base_url}/v1/models"


def _extract_model_ids(payload: object) -> list[str]:
    models: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        source = payload.get("data", [])
    elif isinstance(payload, list):
        source = payload
    else:
        source = []

    for item in source:
        if isinstance(item, str) and item.strip():
            models.append(item.strip())
        elif isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
            if model_id:
                models.append(model_id)
    return models


async def _fetch_remote_models(api_base: str, api_key: str, api_type: str = "openai_chat") -> tuple[int, list[str], str]:
    """获取远端模型列表，支持不同API类型"""
    if api_type == "anthropic":
        return await _fetch_anthropic_models(api_key, api_base)
    else:
        return await _fetch_openai_models(api_base, api_key)


async def _fetch_openai_models(api_base: str, api_key: str) -> tuple[int, list[str], str]:
    """获取 OpenAI 兼容 API 的模型列表"""
    base_url = _normalize_openai_base_url(api_base)
    async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
        response = await client.get(
            f"{base_url}/models",
            headers=_build_openai_compatible_headers(api_key, api_base)
        )
    body_preview = (response.text or "")[:200]
    if response.status_code != 200:
        return response.status_code, [], body_preview
    try:
        payload = response.json()
    except Exception:
        return response.status_code, [], body_preview
    return response.status_code, _extract_model_ids(payload), body_preview


async def _fetch_anthropic_models(api_key: str, api_base: str = "") -> tuple[int, list[str], str]:
    """获取 Anthropic 真实模型列表。

    按 Anthropic 官方示例请求 GET /v1/models。该函数不使用默认 API Base，
    也不返回内置 Claude 列表；只有远端真实返回模型时才视为成功。
    """
    base_url = _normalize_anthropic_base_url(api_base)
    if not base_url:
        return 0, [], "缺少 Anthropic API Base URL"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
            response = await client.get(
                f"{base_url}/v1/models",
                headers=_build_anthropic_headers(api_key, api_base),
            )
            if response.status_code == 404 and _is_mimo_api_base(api_base):
                fallback_url = _mimo_openai_models_url_from_anthropic_base(api_base)
                if fallback_url:
                    logger.info(
                        "MiMo Anthropic models endpoint returned 404; trying real OpenAI-compatible models endpoint: %s",
                        fallback_url,
                    )
                    response = await client.get(
                        fallback_url,
                        headers=_build_openai_compatible_headers(api_key, api_base),
                    )
    except Exception as e:
        return 0, [], str(e)

    body_preview = (response.text or "")[:200]
    if response.status_code in (401, 403):
        return response.status_code, [], "Anthropic API Key 无效"
    if response.status_code != 200:
        return response.status_code, [], body_preview

    try:
        models = _extract_model_ids(response.json())
    except Exception:
        return response.status_code, [], body_preview

    if not models:
        return response.status_code, [], body_preview or "Anthropic /v1/models 未返回任何模型"
    return response.status_code, models, body_preview


TEST_CONNECTION_ERROR_RULES = {
    401: [
        {
            "match": ("missing_api_key", "missing api key", "authorization"),
            "error_code": "missing_api_key",
            "title": "没带 Key",
            "solution": "添加 Authorization 头，或者先把 API Key 保存进去。",
        },
        {
            "match": ("expired", "api_key_expired"),
            "error_code": "api_key_expired",
            "title": "Key 已过期",
            "solution": "联系管理员续期，或者换一把还有效的 Key。",
        },
        {
            "match": (),
            "error_code": "invalid_api_key",
            "title": "Key 不对",
            "solution": "检查 Key 是否正确，有没有多空格，必要时重新生成。",
        },
    ],
    403: [
        {
            "match": ("disabled", "api_key_disabled"),
            "error_code": "api_key_disabled",
            "title": "Key 被禁用了",
            "solution": "联系管理员启用，或者换一把可用的 Key。",
        },
        {
            "match": (),
            "error_code": "model_not_allowed",
            "title": f"模型 {{model}} 没开权限",
            "solution": "检查模型白名单，或者换成这个接口已授权的模型。",
        },
    ],
    429: [
        {
            "match": ("quota", "额度", "insufficient_quota", "quota exceeded"),
            "error_code": "quota_exceeded",
            "title": "配额已经用完了",
            "solution": "联系管理员补额度，或者等额度重置。",
        },
        {
            "match": ("rpd", "per day", "daily"),
            "error_code": "rate_limit_rpd",
            "title": "今天的调用次数用完了",
            "solution": "等第二天重置。",
        },
        {
            "match": ("concurrent", "并发"),
            "error_code": "concurrent_limit",
            "title": "同时请求太多了",
            "solution": "减少同时请求数，再试一次。",
        },
        {
            "match": (),
            "error_code": "rate_limit_rpm",
            "title": "请求太快了",
            "solution": "降低请求频率，稍等一会儿再试。",
        },
    ],
    400: [
        {
            "match": ("max_tokens", "maximum context", "too many tokens"),
            "error_code": "max_tokens_exceeded",
            "title": "单次 Token 设得太大了",
            "solution": "把 max_tokens 调低一点再试。",
        },
        {
            "match": (),
            "error_code": "bad_request",
            "title": "请求参数不对",
            "solution": "检查模型名、API 地址和请求参数格式。",
        },
    ],
    404: [
        {
            "match": (),
            "error_code": "model_or_endpoint_not_found",
            "title": "模型名或接口地址不对",
            "solution": "先确认 API Base 对不对，再确认模型名是否真实存在。",
        },
    ],
    503: [
        {
            "match": (),
            "error_code": "no_available_accounts",
            "title": "服务暂时不可用",
            "solution": "稍后重试；如果一直这样，联系管理员检查上游服务。",
        },
    ],
}


def _render_test_connection_mapping(rule: dict, test_model: str) -> dict:
    return {
        "error_code": str(rule["error_code"]),
        "title": str(rule["title"]).replace("{model}", test_model or "当前模型"),
        "solution": str(rule["solution"]).replace("{model}", test_model or "当前模型"),
    }


def _map_test_connection_error(status_code: int, error_detail: str, test_model: str) -> dict:
    detail = str(error_detail or "").strip()
    lower = detail.lower()
    for rule in TEST_CONNECTION_ERROR_RULES.get(status_code, []):
        needles = tuple(str(item).lower() for item in rule.get("match", ()) if str(item).strip())
        if not needles or any(needle in lower for needle in needles):
            return _render_test_connection_mapping(rule, test_model)
    return {
        "error_code": "unknown_error",
        "title": f"接口返回了 {status_code}",
        "solution": "先看返回详情，再确认 API 地址、模型和账户权限。",
    }


def _build_test_connection_response(
    *,
    success: bool,
    error_code: str = "",
    title: str = "",
    solution: str = "",
    error: str = "",
    detail: str = "",
    status_code: int | None = None,
    model_tested: str = "",
    response_time: int | None = None,
) -> JSONResponse:
    payload = {
        "success": success,
        "error_code": error_code,
        "title": title,
        "solution": solution,
        "error": error,
    }
    if detail:
        payload["detail"] = detail
    if status_code is not None:
        payload["status_code"] = status_code
    if model_tested:
        payload["model_tested"] = model_tested
    if response_time is not None:
        payload["response_time"] = response_time
    return JSONResponse(payload)


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
    env_path = get_app_root() / ".env"
    
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

        refresh_runtime_after_config_reload()
    except (OSError, IOError, PermissionError) as e:
        logger.error(f"Failed to write .env file: {e}")
        return JSONResponse({
            "success": False,
            "error": f"Failed to save settings: {e}"
        }, status_code=500)

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

    refresh_runtime_after_config_reload()

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
        api_type = (getattr(request, 'api_type', '') or "openai_chat").strip()
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
                    if api_type == "openai_chat" and getattr(cfg, 'api_type', ''):
                        api_type = cfg.api_type
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
                    if api_type == "openai_chat" and getattr(cfg, 'api_type', ''):
                        api_type = cfg.api_type
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
        
        # Anthropic 模型列表
        if api_type == "anthropic":
            status_code, models, body_preview = await _fetch_anthropic_models(api_key, api_base)
            if status_code == 200 and models:
                return JSONResponse({
                    "success": True,
                    "models": models
                })
            else:
                return JSONResponse({
                    "success": False,
                    "error": body_preview or "无法获取 Anthropic 真实模型列表",
                    "models": []
                })
        
        # OpenAI 兼容 API
        base_url = _normalize_openai_base_url(api_base)
        models_url = f"{base_url}/models"
        
        async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_SHORT) as client:
            response = await client.get(
                models_url,
                headers=_build_openai_compatible_headers(api_key, api_base)
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
        api_type = (getattr(request, 'api_type', '') or "openai_chat").strip()

        if config_id:
            from ...agent_config import DEFAULT_API_PRESET_ID, get_config_manager
            manager = get_config_manager()
            selected_config = next(
                (cfg for cfg in manager.multi_config.configs if cfg.id == config_id),
                None
            )
            if not selected_config:
                return JSONResponse({
                    "success": False,
                    "error": f"Config ID not found: {config_id}. Please refresh the settings page."
                })
            if selected_config.id == DEFAULT_API_PRESET_ID and not selected_config.is_configured():
                return JSONResponse({
                    "success": False,
                    "error_code": "preset_requires_selection",
                    "title": "请先选择可用配置",
                    "solution": "探索仓API只是占位入口。请新建或选择一套已填写 Key 和模型的 API 配置后再测试。",
                    "error": "请先选择可用配置。探索仓API不能直接测试连接。",
                })
            if not api_base:
                api_base = (selected_config.api_base or "").strip()
            if not api_key:
                api_key = (selected_config.api_key or "").strip()
            if not test_model and selected_config.models:
                test_model = str(selected_config.models[0]).strip()
            if api_type == "openai_chat" and getattr(selected_config, 'api_type', ''):
                api_type = selected_config.api_type

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
                    if api_type == "openai_chat" and getattr(cfg, 'api_type', ''):
                        api_type = cfg.api_type
                    break

        if not api_base:
            return JSONResponse({
                "success": False,
                "error": "Missing API base URL."
            })

        if not api_key:
            return JSONResponse({
                "success": False,
                "error": "Missing API key. Save the config before testing."
            })

        # Anthropic 测试连接
        if api_type == "anthropic":
            return await _test_anthropic_connection(api_key, test_model, api_base)
        if api_type == "openai_responses":
            return await _test_openai_responses_connection(api_base, api_key, test_model)

        # OpenAI 兼容 API 测试连接
        return await _test_openai_connection(api_base, api_key, test_model)

    except httpx.TimeoutException:
        return _build_test_connection_response(
            success=False,
            error_code="timeout",
            title="连接超时",
            solution="检查 API 地址、代理、网络和防火墙设置。",
            error="连超时了。先看看 API 地址对不对、网络通不通。",
        )
    except httpx.ConnectError as e:
        return _build_test_connection_response(
            success=False,
            error_code="connect_error",
            title="服务器连不上",
            solution="检查 API Base、网络出口、代理和防火墙。",
            error="根本没连上目标服务器。",
            detail=str(e),
        )
    except Exception as e:
        return _build_test_connection_response(
            success=False,
            error_code="unexpected_error",
            title="测试失败",
            solution="根据详细报错继续排查 API 地址、模型、权限或网络。",
            error="测试没跑通，先看看详细报错。",
            detail=str(e),
        )


@router.post("/test-image-connection")
async def test_image_connection(request: TestConnectionRequest):
    """Test the actual image-generation endpoint for a saved API config."""
    try:
        api_base = (request.api_base or "").strip()
        api_key = (request.api_key or "").strip()
        test_model = (request.model or "").strip()
        config_id = (request.config_id or "").strip()
        image_api_format = (getattr(request, "image_api_format", "") or "auto").strip()

        if config_id:
            from ...agent_config import DEFAULT_API_PRESET_ID, get_config_manager
            manager = get_config_manager()
            selected_config = next(
                (cfg for cfg in manager.multi_config.configs if cfg.id == config_id),
                None
            )
            if not selected_config:
                return _build_test_connection_response(
                    success=False,
                    error_code="config_not_found",
                    title="配置不存在",
                    solution="刷新设置页后重新选择 API 配置。",
                    error=f"Config ID not found: {config_id}",
                )
            if selected_config.id == DEFAULT_API_PRESET_ID and not selected_config.is_configured():
                return _build_test_connection_response(
                    success=False,
                    error_code="preset_requires_selection",
                    title="请先选择可用配置",
                    solution="探索仓API只是占位入口。请新建或选择一套已填写 Key 和图片模型的 API 配置后再测试。",
                    error="请先选择可用配置。探索仓API不能直接测试图片接口。",
                )
            if not api_base:
                api_base = (selected_config.api_base or "").strip()
            if not api_key:
                api_key = (selected_config.get_primary_key() or "").strip()
            if not test_model and selected_config.models:
                test_model = str(selected_config.models[0]).strip()
            if not image_api_format or image_api_format == "auto":
                image_api_format = getattr(selected_config, "image_api_format", "auto") or "auto"

        if not api_key and api_base and not config_id:
            from ...agent_config import get_config_manager
            manager = get_config_manager()
            for cfg in manager.multi_config.configs:
                cfg_base = (cfg.api_base or "").strip()
                cfg_key = (cfg.get_primary_key() or "").strip()
                if cfg_base == api_base and cfg_key:
                    api_key = cfg_key
                    if not test_model and cfg.models:
                        test_model = str(cfg.models[0]).strip()
                    if not image_api_format or image_api_format == "auto":
                        image_api_format = getattr(cfg, "image_api_format", "auto") or "auto"
                    break

        if not api_base:
            return _build_test_connection_response(
                success=False,
                error_code="missing_api_base",
                title="缺少 API 地址",
                solution="先填写并保存 API Base URL。",
                error="Missing API base URL.",
            )
        if not api_key:
            return _build_test_connection_response(
                success=False,
                error_code="missing_api_key",
                title="缺少 API Key",
                solution="先保存配置里的 API Key，再测试图片接口。",
                error="Missing API key. Save the config before testing.",
            )
        if not test_model:
            return _build_test_connection_response(
                success=False,
                error_code="missing_image_model",
                title="缺少图像模型",
                solution="在当前配置里添加 image、imagen、dall-e、flux 等图像模型后再测试。",
                error="Missing image model.",
            )
        if not CoverImageService._is_likely_image_model(test_model):
            return _build_test_connection_response(
                success=False,
                error_code="not_image_model",
                title="当前模型不像图片模型",
                solution="请选择图片模型；文本模型通过测试不代表封面生成可用。",
                error=f"{test_model} 不像图片生成模型。",
                model_tested=test_model,
            )

        return await _test_image_generation_connection(api_base, api_key, test_model, image_api_format)
    except httpx.TimeoutException:
        return _build_test_connection_response(
            success=False,
            error_code="image_timeout",
            title="图片接口超时",
            solution="这通常是上游图片服务处理过慢或网关超时。稍后重试，或切换图片模型/渠道。",
            error="图片接口连接或生成超时。",
            model_tested=(request.model or "").strip(),
        )
    except httpx.ConnectError as e:
        return _build_test_connection_response(
            success=False,
            error_code="connect_error",
            title="图片接口连不上",
            solution="检查 API Base、网络出口、代理和防火墙。",
            error="根本没连上目标图片接口。",
            detail=str(e),
            model_tested=(request.model or "").strip(),
        )
    except Exception as e:
        return _build_test_connection_response(
            success=False,
            error_code="unexpected_error",
            title="图片测试失败",
            solution="根据详细报错继续排查 API 地址、图片模型、图片格式或账户权限。",
            error="图片接口测试没跑通，先看看详细报错。",
            detail=str(e),
            model_tested=(request.model or "").strip(),
        )


async def _test_image_generation_connection(
    api_base: str,
    api_key: str,
    test_model: str,
    image_api_format: str,
) -> JSONResponse:
    """Send a tiny real image-generation request and report endpoint compatibility."""
    start_time = time.time()
    provider_size = CoverImageService._provider_size_for_model(test_model, "1024x1024")
    format_tried: list[str] = []
    endpoint_tried: list[str] = []
    http_errors: list[str] = []
    last_status: int | None = None
    last_detail = ""

    async with httpx.AsyncClient(timeout=_image_test_timeout(0)) as client:
        for mode in CoverImageService._iter_image_api_formats(image_api_format):
            endpoint = CoverImageService._endpoint_label(mode, test_model)
            url = CoverImageService._build_url(api_base=api_base, mode=mode, model=test_model)
            payload = CoverImageService._build_payload(
                mode=mode,
                model=test_model,
                prompt="A simple clean book cover test image, no text.",
                size=provider_size,
            )
            format_tried.append(mode)
            endpoint_tried.append(endpoint)

            for attempt in range(2):
                try:
                    response = await client.post(
                        url,
                        headers=_build_openai_compatible_headers(api_key, api_base),
                        json=payload,
                        timeout=_image_test_timeout(attempt),
                    )
                except httpx.TimeoutException as exc:
                    last_detail = str(exc)
                    http_errors.append(
                        f"{mode} {endpoint} 客户端超时（{_image_test_timeout_seconds(attempt):.0f}s）"
                    )
                    if attempt == 0:
                        continue
                    if image_api_format == "auto":
                        break
                    raise

                response_time = int((time.time() - start_time) * 1000)
                last_status = response.status_code
                body_preview = (response.text or "")[:400]

                if response.status_code in _IMAGE_TEST_GATEWAY_RETRY_STATUS and attempt == 0:
                    last_detail = body_preview
                    http_errors.append(f"{mode} {endpoint} HTTP {response.status_code}: {body_preview[:160]}，已加时重试")
                    await asyncio.sleep(_IMAGE_TEST_GATEWAY_RETRY_DELAY_SECONDS)
                    continue

                if response.status_code >= 400:
                    last_detail = body_preview
                    http_errors.append(f"{mode} {endpoint} HTTP {response.status_code}: {body_preview[:160]}")
                    if CoverImageService._should_try_next_format(image_api_format, response.status_code):
                        break
                    mapped = _map_image_connection_error(response.status_code, body_preview, test_model)
                    return _build_test_connection_response(
                        success=False,
                        error_code=mapped["error_code"],
                        title=mapped["title"],
                        solution=mapped["solution"],
                        error=f"{mapped['title']}。{mapped['solution']}",
                        detail=_format_image_test_detail(format_tried, endpoint_tried, http_errors, body_preview),
                        status_code=response.status_code,
                        model_tested=test_model,
                        response_time=response_time,
                    )

                try:
                    image_base64, image_url = CoverImageService._extract_image_payload(response.json())
                except Exception as exc:
                    last_detail = str(exc)
                    image_base64, image_url = "", ""

                if image_base64 or image_url:
                    return _build_test_connection_response(
                        success=True,
                        title="图片接口可以正常用",
                        solution="这套配置已经通过真实图片接口测试，可以用于封面生成。",
                        error="图片接口连通，并返回了图片数据。",
                        detail=_format_image_test_detail(format_tried, endpoint_tried, http_errors, "已返回图片数据"),
                        status_code=response.status_code,
                        model_tested=test_model,
                        response_time=response_time,
                    )

                last_detail = body_preview or "响应成功，但没有找到图片 URL 或 base64 数据。"
                http_errors.append(f"{mode} {endpoint} 未返回图片数据")
                if image_api_format == "auto":
                    break
                return _build_test_connection_response(
                    success=False,
                    error_code="image_payload_missing",
                    title="图片接口没有返回图片",
                    solution="确认模型是否支持当前图片 API 格式，或切换图片 API 格式后再试。",
                    error="接口成功响应，但没有图片 URL 或 base64。",
                    detail=_format_image_test_detail(format_tried, endpoint_tried, http_errors, last_detail),
                    status_code=response.status_code,
                    model_tested=test_model,
                    response_time=response_time,
                )

    mapped = _map_image_connection_error(last_status or 0, last_detail, test_model)
    return _build_test_connection_response(
        success=False,
        error_code=mapped["error_code"],
        title=mapped["title"],
        solution=mapped["solution"],
        error=f"{mapped['title']}。{mapped['solution']}",
        detail=_format_image_test_detail(format_tried, endpoint_tried, http_errors, last_detail),
        status_code=last_status,
        model_tested=test_model,
        response_time=int((time.time() - start_time) * 1000),
    )


def _image_test_timeout_seconds(attempt: int) -> float:
    return _IMAGE_TEST_RETRY_TIMEOUT_SECONDS if attempt > 0 else _IMAGE_TEST_TIMEOUT_SECONDS


def _image_test_timeout(attempt: int) -> httpx.Timeout:
    return httpx.Timeout(
        _image_test_timeout_seconds(attempt),
        connect=_IMAGE_TEST_CONNECT_TIMEOUT_SECONDS,
    )


def _map_image_connection_error(status_code: int, error_detail: str, test_model: str) -> dict:
    if status_code in {503, 504, 524}:
        solution = "文本接口可用不代表图片接口可用；请稍后重试，或换图片模型/渠道/API 格式。"
        if status_code == 524:
            solution = (
                "524 表示代理已连到图片源站，但源站在 120 秒左右没有返回完整响应。"
                "本地继续加等待时间通常无效；请稍后重试，或换图片模型/渠道/API 格式。"
            )
        return {
            "error_code": "image_gateway_timeout",
            "title": "图片上游超时",
            "solution": solution,
        }
    if status_code == 429:
        return {
            "error_code": "image_rate_limited",
            "title": "图片接口被限流",
            "solution": "稍后再试，或切换到额度更充足的图片模型/渠道。",
        }
    return _map_test_connection_error(status_code, error_detail, test_model)


def _format_image_test_detail(
    format_tried: list[str],
    endpoint_tried: list[str],
    http_errors: list[str],
    last_detail: str,
) -> str:
    parts = [
        f"已尝试格式：{', '.join(format_tried) or '无'}",
        f"已尝试端点：{', '.join(endpoint_tried) or '无'}",
    ]
    if http_errors:
        parts.append("错误摘要：" + " | ".join(http_errors[-3:]))
    if last_detail:
        parts.append(f"最后返回：{last_detail[:240]}")
    return "\n".join(parts)


async def _test_openai_connection(api_base: str, api_key: str, test_model: str) -> JSONResponse:
    """测试 OpenAI 兼容 API 连接"""
    base_url = api_base.rstrip("/")
    last_segment = base_url.rsplit("/", 1)[-1].lower() if base_url else ""
    if not re.fullmatch(r"v\d+(\.\d+)?", last_segment):
        base_url = base_url + "/v1" if not base_url.endswith("/") else base_url + "v1"

    if not test_model:
        test_model = "gpt-3.5-turbo"

    start_time = time.time()

    async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
        request_body = {
            "model": test_model,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        if not _is_tsc5_api_base(api_base):
            request_body["max_tokens"] = 5
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=_build_openai_compatible_headers(api_key, api_base),
            json=request_body,
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
            return _build_test_connection_response(
                success=True,
                title="可以正常用",
                solution="这套配置已经通过测试，可以直接拿来创作。",
                error="连通，模型也能正常回话。",
                model_tested=test_model,
                response_time=response_time,
                status_code=response.status_code,
            )
        mapped = _map_test_connection_error(response.status_code, error_detail, test_model)
        return _build_test_connection_response(
            success=False,
            error_code=mapped["error_code"],
            title=mapped["title"],
            solution=mapped["solution"],
            error=f"{mapped['title']}。{mapped['solution']}",
            detail=error_detail or error_text[:200],
            status_code=response.status_code,
            model_tested=test_model,
        )


async def _test_openai_responses_connection(api_base: str, api_key: str, test_model: str) -> JSONResponse:
    """测试 OpenAI Responses API 连接。"""
    base_url = _normalize_openai_base_url(api_base)

    if not test_model:
        test_model = "gpt-5.4-mini"

    start_time = time.time()
    request_body = {
        "model": test_model,
        "input": "Hi" if _is_tsc5_api_base(api_base) else [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hi"}],
            }
        ],
        "max_output_tokens": 5,
    }

    async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
        response = await client.post(
            f"{base_url}/responses",
            headers=_build_openai_compatible_headers(api_key, api_base),
            json=request_body,
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
            return _build_test_connection_response(
                success=True,
                title="可以正常用",
                solution="这套 Responses API 配置已经通过测试，可以直接拿来创作。",
                error="连通，模型也能正常回话。",
                model_tested=test_model,
                response_time=response_time,
                status_code=response.status_code,
            )
        if response.status_code == 404 and (
            "bad_response_status_code" in error_detail.lower()
            or "openai_error" in error_detail.lower()
            or "bad_response_status_code" in error_text.lower()
            or "openai_error" in error_text.lower()
        ):
            chat_request_body = {
                "model": test_model,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            if not _is_tsc5_api_base(api_base):
                chat_request_body["max_tokens"] = 5
            try:
                chat_response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=_build_openai_compatible_headers(api_key, api_base),
                    json=chat_request_body,
                )
                if chat_response.status_code == 200:
                    return _build_test_connection_response(
                        success=True,
                        error_code="responses_fallback_chat_available",
                        title="Responses 不通，Chat 降级可用",
                        solution="当前模型的 /v1/responses 上游不可用，但 /v1/chat/completions 已通过；运行时会自动降级到 Chat Completions。若需要原生 Responses，请在后台切换支持 Responses 的渠道。",
                        error="Responses 上游返回 404，Chat Completions 可用。",
                        detail=error_detail or error_text[:200],
                        status_code=response.status_code,
                        model_tested=test_model,
                        response_time=int((time.time() - start_time) * 1000),
                    )
            except Exception:
                pass
            return _build_test_connection_response(
                success=False,
                error_code="responses_upstream_not_found",
                title="当前模型没有可用 Responses 通道",
                solution="探索仓入口已响应，但当前 Key/模型转发到上游后返回 404。运行时会优先尝试 Chat Completions 降级；如需原生 Responses，请在后台换成支持 /v1/responses 的模型或渠道。",
                error="Responses 端点存在，但这个模型的上游不支持 Responses。",
                detail=error_detail or error_text[:200],
                status_code=response.status_code,
                model_tested=test_model,
            )
        mapped = _map_test_connection_error(response.status_code, error_detail, test_model)
        return _build_test_connection_response(
            success=False,
            error_code=mapped["error_code"],
            title=mapped["title"],
            solution=mapped["solution"],
            error=f"{mapped['title']}。{mapped['solution']}",
            detail=error_detail or error_text[:200],
            status_code=response.status_code,
            model_tested=test_model,
        )


async def _test_anthropic_connection(api_key: str, test_model: str, api_base: str = "") -> JSONResponse:
    """测试 Anthropic API 连接"""
    if not test_model:
        test_model = "claude-3-5-haiku-20241022"

    base_url = _normalize_anthropic_base_url(api_base)
    messages_url = f"{base_url}/v1/messages"

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
            response = await client.post(
                messages_url,
                headers=_build_anthropic_headers(api_key, api_base),
                json={
                    "model": test_model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
            )

            response_time = int((time.time() - start_time) * 1000)
            error_text = response.text[:400] if response.text else ""
            error_detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    error_obj = payload.get("error", {})
                    if isinstance(error_obj, dict):
                        error_detail = error_obj.get("message", "")
                    else:
                        error_detail = str(error_obj)
            except Exception:
                error_detail = ""
            if not error_detail:
                error_detail = error_text
            error_detail = (error_detail or "").strip()[:200]

            if response.status_code == 200:
                return _build_test_connection_response(
                    success=True,
                    title="Anthropic 连接正常",
                    solution="Anthropic API 已通过测试，可以直接拿来创作。",
                    error="连通，Claude 模型能正常回话。",
                    model_tested=test_model,
                    response_time=response_time,
                    status_code=response.status_code,
                )

            # Anthropic 特定错误映射
            anthropic_error_map = {
                401: ("invalid_api_key", "Anthropic API Key 无效", "检查 API Key 是否正确，是否已过期。"),
                403: ("api_key_disabled", "Anthropic API Key 被禁用", "联系 Anthropic 管理员或检查账户状态。"),
                429: ("rate_limit", "Anthropic API 请求频率超限", "降低请求频率，稍等一会儿再试。"),
                529: ("overloaded", "Anthropic API 过载", "Anthropic 服务暂时过载，请稍后重试。"),
                404: ("model_not_found", f"模型 {test_model} 不可用", "检查模型名称是否正确。"),
            }

            if response.status_code in anthropic_error_map:
                error_code, title, solution = anthropic_error_map[response.status_code]
                return _build_test_connection_response(
                    success=False,
                    error_code=error_code,
                    title=title,
                    solution=solution,
                    error=f"{title}。{solution}",
                    detail=error_detail,
                    model_tested=test_model,
                    status_code=response.status_code,
                )

            return _build_test_connection_response(
                success=False,
                error_code="anthropic_error",
                title=f"Anthropic 返回 {response.status_code}",
                solution="查看错误详情，检查 API Key 和模型配置。",
                error=f"Anthropic API 返回了 {response.status_code}",
                detail=error_detail,
                model_tested=test_model,
                status_code=response.status_code,
            )

    except httpx.TimeoutException:
        return _build_test_connection_response(
            success=False,
            error_code="timeout",
            title="Anthropic 连接超时",
            solution="检查网络连接，Anthropic API 可能需要代理访问。",
            error="连接 Anthropic API 超时。",
        )
    except httpx.ConnectError as e:
        return _build_test_connection_response(
            success=False,
            error_code="connect_error",
            title="无法连接 Anthropic",
            solution="检查网络连接，可能需要配置代理才能访问 Anthropic API。",
            detail=str(e),
        )

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


@router.get("/timeout-settings")
async def get_global_timeout_settings():
    return JSONResponse(
        {
            "success": True,
            "data": {
                **get_timeout_settings(),
                "ranges": get_timeout_setting_ranges(),
            },
        }
    )


@router.post("/timeout-settings")
async def save_global_timeout_settings(request: TimeoutSettingsRequest):
    try:
        payload = request.model_dump(exclude_none=True)
        settings = save_timeout_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "success": True,
            "message": "超时设置已保存",
            "data": {
                **settings,
                "ranges": get_timeout_setting_ranges(),
            },
        }
    )


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
        api_keys=[entry.model_dump() for entry in request.api_keys],
        models=request.models,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        api_type=getattr(request, 'api_type', 'openai_chat') or 'openai_chat',
        image_api_format=getattr(request, 'image_api_format', 'auto') or 'auto'
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
    if request.api_keys is not None:
        updates["api_keys"] = [entry.model_dump() for entry in request.api_keys]
    if request.models is not None:
        updates["models"] = request.models
    if request.temperature is not None:
        updates["temperature"] = request.temperature
    if request.max_tokens is not None:
        updates["max_tokens"] = request.max_tokens
    if getattr(request, 'api_type', None) is not None:
        updates["api_type"] = request.api_type
    if getattr(request, 'image_api_format', None) is not None:
        updates["image_api_format"] = request.image_api_format
    
    old_active_model = manager.get_global_config().model
    was_active = config_id == manager.get_multi_config().active_config_id
    cfg = manager.update_api_config(config_id, **updates)

    if cfg:
        runtime_refreshed = False
        if was_active and updates:
            refresh_runtime_after_config_reload()
            runtime_refreshed = True
        active_model = manager.get_global_config().model
        return JSONResponse({
            "success": True,
            "message": "API 配置已更新",
            "config": cfg.to_dict(),
            "active_model": active_model,
            "active_model_changed": active_model != old_active_model,
            "runtime_refreshed": runtime_refreshed,
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
    target_config = next(
        (cfg for cfg in manager.get_multi_config().configs if cfg.id == request.config_id),
        None,
    )
    if target_config is None:
        raise HTTPException(status_code=404, detail="")

    api_base = str(target_config.api_base or "").strip()
    api_key = str(target_config.api_key or "").strip()
    if not api_base or not api_key:
        return JSONResponse({
            "success": False,
            "error": "所选 API 配置缺少 api_base 或 api_key，无法激活。",
        }, status_code=400)

    api_type = getattr(target_config, 'api_type', 'openai_chat') or 'openai_chat'
    try:
        status_code, remote_models, body_preview = await _fetch_remote_models(api_base, api_key, api_type)
    except httpx.TimeoutException:
        return JSONResponse({
            "success": False,
            "error": "目标 API 连接超时，无法激活该配置。",
        }, status_code=400)
    except Exception as exc:
        return JSONResponse({
            "success": False,
            "error": f"目标 API 不可达，无法激活该配置: {exc}",
        }, status_code=400)

    if status_code != 200:
        return JSONResponse({
            "success": False,
            "error": f"目标 API 模型验证返回 {status_code}，无法激活该配置。",
            "body_preview": body_preview,
        }, status_code=400)

    requested_model = str(request.model or "").strip()
    chosen_model = requested_model
    if not chosen_model:
        config_models = [str(item).strip() for item in (target_config.models or []) if str(item).strip()]
        chosen_model = next((model for model in config_models if model in remote_models), "")

    if not chosen_model:
        return JSONResponse({
            "success": False,
            "error": "目标 API 可达，但当前配置中没有任何模型与远端模型列表匹配，无法激活。",
            "remote_model_count": len(remote_models),
        }, status_code=400)

    if chosen_model not in remote_models:
        return JSONResponse({
            "success": False,
            "error": f"模型 '{chosen_model}' 不在远端模型列表中，无法激活。",
            "remote_model_count": len(remote_models),
        }, status_code=400)

    if manager.set_active_config(request.config_id, chosen_model):
        refresh_runtime_after_config_reload()
        return JSONResponse({
            "success": True,
            "message": "当前模型配置已应用",
            "active_model": chosen_model,
            "active_config_id": request.config_id,
            "remote_model_count": len(remote_models),
        })
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
