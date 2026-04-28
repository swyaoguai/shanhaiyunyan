"""
对话API路由模块

包含聊天会话管理、消息发送、用户输入处理等功能。
"""

import logging
import asyncio
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

from ..models.requests import ChatRequest, UserInputRequest
from ..dependencies import get_coordinator, get_router_agent

logger = logging.getLogger(__name__)

router = APIRouter()

INTENT_TARGET_AGENT_MAP = {
    "create_novel": "Coordinator",
    "create_character": "CharacterBuilder",
    "create_eventlines": "EventlineBuilder",
    "create_detail_outline": "DetailOutlineBuilder",
    "create_chapter_settings": "ChapterSettingBuilder",
    "continue_write": "ContinuousWriter",
    "polish_content": "Polisher",
    "search_web": "WebSearch",
    "search_trends": "TrendsSearch",
    "query_knowledge": "Communicator",
    "general_chat": "Communicator",
    "ask_help": "Communicator",
    "provide_feedback": "Communicator",
    "project_manage": "ProjectManager",
    # 当前并无独立 SettingsAssistant Agent，配置类问题统一由 Communicator 承接
    "config_settings": "Communicator",
}


def _resolve_agent_effective_model(agent_name: str, fallback_model: str = "") -> str:
    target_agent = str(agent_name or "").strip()
    if not target_agent:
        return str(fallback_model or "").strip()
    try:
        from ...agent_config import get_config_manager
        cfg = get_config_manager().get_effective_config(target_agent)
        model_name = str(getattr(cfg, "model", "") or "").strip()
        if model_name:
            return model_name
    except Exception as exc:
        logger.debug(f"[Chat] resolve effective model failed for {target_agent}: {exc}")
    return str(fallback_model or "").strip()

# 存储对话会话（内存热缓存）
chat_sessions = {}
_chat_session_locks = {}
_chat_locks_guard = asyncio.Lock()
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ACTIVE_WORKFLOW_RUNS: Dict[str, Dict[str, Any]] = {}
_CREATE_START_PATTERNS = (
    "开始创作",
    "开始写",
    "开始生成",
    "开始吧",
    "直接开写",
    "直接写",
    "马上开始",
    "开始第一章",
    # 世界观创建触发
    "写世界观", "建世界观", "创建世界观", "构建世界观", "生成世界观",
    "设定世界观", "建立世界观", "先写世界观", "帮我写世界观",
    # 大纲创建触发
    "写大纲", "创建大纲", "生成大纲", "建大纲", "做大纲",
    "设计大纲", "规划大纲", "先写大纲", "帮我写大纲",
    # 角色创建触发
    "创建角色", "设计角色", "写角色", "建角色",
    # 正文创作触发
    "写正文", "创作正文", "开始正文", "生成正文",
)
_ROUTER_EXECUTION_INTENTS = {
    "create_novel",
    "create_character",
    "create_eventlines",
    "create_detail_outline",
    "create_chapter_settings",
    "continue_write",
    "polish_content",
    "search_web",
    "search_trends",
}
_ROUTER_COMMAND_NAMES = {"create", "worldbuild", "outline", "chapter"}
_WORKFLOW_CONTROL_COMMAND_NAMES = {"pause", "resume", "status", "cancel"}
CHAT_AUTO_SAVE_STATE_KEY = "copilot_chat_auto_save"
KNOWLEDGE_CATEGORIES_STATE_KEY = "knowledge_categories"
_EXPLICIT_COMMAND_DEFINITIONS = {
    "create": {
        "display": "开始创作",
        "aliases": ("create",),
    },
    "worldbuild": {
        "display": "生成世界观",
        "aliases": ("worldbuild",),
    },
    "outline": {
        "display": "生成大纲",
        "aliases": ("outline",),
    },
    "chapter": {
        "display": "续写章节",
        "aliases": ("chapter",),
    },
    "pause": {
        "display": "暂停创作",
        "aliases": ("pause",),
    },
    "resume": {
        "display": "继续创作",
        "aliases": ("resume",),
    },
    "status": {
        "display": "查看进度",
        "aliases": ("status",),
    },
    "cancel": {
        "display": "取消创作",
        "aliases": ("cancel",),
    },
}

_NATURAL_LANGUAGE_COMMAND_PATTERNS = {
    "worldbuild": (
        "生成世界观",
        "构建世界观",
        "补全世界观",
        "完善世界观",
        "世界观设定",
        "保存世界观",
        "同步世界观",
        "把世界观保存到资料库",
        "把世界观同步到资料库",
        "世界观保存到资料库",
        "世界观同步到资料库",
        # 更多自然表达
        "写世界观",
        "创建世界观",
        "建世界观",
        "建立世界观",
        "设定世界观",
        "做世界观",
    ),
    "outline": (
        "生成大纲",
        "创建大纲",
        "规划大纲",
        "补全大纲",
        "完善大纲",
        # 更多自然表达
        "写大纲",
        "建大纲",
        "做大纲",
        "设计大纲",
    ),
    "pause": (
        "暂停创作",
        "先暂停",
        "暂停一下",
        "停一下",
        "暂停写作",
    ),
    "resume": (
        "继续创作",
        "恢复创作",
        "继续写作",
        "恢复写作",
        "继续生成",
        "恢复生成",
    ),
    "status": (
        "创作状态",
        "查看进度",
        "当前进度",
        "进度如何",
        "现在写到哪",
        "写到哪了",
    ),
    "cancel": (
        "取消创作",
        "停止创作",
        "终止创作",
        "取消写作",
        "停止写作",
    ),
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _normalize_session_id(session_id: str) -> str:
    value = (session_id or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="session_id 不能为空")
    if not _SESSION_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=400, detail="session_id 包含非法字符")
    return value


async def _get_chat_session_lock(session_key: str) -> asyncio.Lock:
    async with _chat_locks_guard:
        lock = _chat_session_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            _chat_session_locks[session_key] = lock
        return lock


def _strip_visible_technical_markers(text: Any) -> str:
    """移除技术标记，并从JSON格式中提取reply字段"""
    if not isinstance(text, str):
        return ""
    text = text.replace("[INFO_COMPLETE]", "").strip()
    
    # 如果文本看起来像JSON，尝试提取reply字段
    if text.startswith('{') and '"reply"' in text:
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, dict) and "reply" in data:
                    reply = str(data["reply"] or "").strip()
                    if reply:
                        return reply
        except (ValueError, KeyError, TypeError):
            pass
    
    return text


def _sanitize_conversation_history(history):
    """Normalize history payload for frontend rendering."""
    normalized = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = item.get("content", "")
        if role not in {"user", "assistant", "system"}:
            continue
        if not isinstance(content, str):
            continue
        text = _strip_visible_technical_markers(content)
        if not text:
            continue
        normalized.append({
            "role": role,
            "content": text,
        })
    return normalized


def _session_preview_from_history(history):
    normalized = _sanitize_conversation_history(history)
    if not normalized:
        return {
            "message_count": 0,
            "last_message_preview": "",
        }
    preview = normalized[-1]["content"][:120]
    return {
        "message_count": len(normalized),
        "last_message_preview": preview,
    }


def _extract_intent_name(intent_analysis: Any) -> str:
    primary_intent = getattr(intent_analysis, "primary_intent", None)
    intent_name = getattr(primary_intent, "value", "") or str(primary_intent or "")
    return str(intent_name).strip()


def _workflow_state_key(session_id: str) -> str:
    safe_session = re.sub(r"[^A-Za-z0-9_-]+", "_", str(session_id or "").strip()) or "copilot"
    return f"copilot_workflow_{safe_session}"


def _normalize_file_entry(item: Any, default_status: str = "created") -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        path = item.strip()
        if not path:
            return None
        return {
            "path": path,
            "label": path.split("\\")[-1].split("/")[-1],
            "kind": "file",
            "status": default_status,
        }
    if not isinstance(item, dict):
        return None
    path = str(item.get("path") or item.get("file") or "").strip()
    if not path:
        return None
    label = str(item.get("label") or item.get("name") or "").strip()
    kind = str(item.get("kind") or "file").strip() or "file"
    status = str(item.get("status") or default_status).strip() or default_status
    return {
        "path": path,
        "label": label or path.split("\\")[-1].split("/")[-1],
        "kind": kind,
        "status": status,
    }


def _merge_file_entries(existing: Any, incoming: Any, default_status: str = "created") -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for bucket in (existing or [], incoming or []):
        if isinstance(bucket, list):
            for item in bucket:
                normalized = _normalize_file_entry(item, default_status=default_status)
                if normalized:
                    merged[normalized["path"]] = normalized
        else:
            normalized = _normalize_file_entry(bucket, default_status=default_status)
            if normalized:
                merged[normalized["path"]] = normalized
    return list(merged.values())


def _workflow_public_snapshot(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    return {
        "run_id": str(payload.get("run_id") or "").strip(),
        "session_id": str(payload.get("session_id") or "").strip(),
        "project_id": str(payload.get("project_id") or "").strip(),
        "command": str(payload.get("command") or "").strip(),
        "status": str(payload.get("status") or "idle").strip() or "idle",
        "target_agent": str(payload.get("target_agent") or "").strip(),
        "current_agent": str(payload.get("current_agent") or "").strip(),
        "stage": str(payload.get("stage") or "").strip(),
        "last_progress": str(payload.get("last_progress") or "").strip(),
        "last_error": str(payload.get("last_error") or "").strip(),
        "output_dir": str(payload.get("output_dir") or "").strip(),
        "focus_module": str(payload.get("focus_module") or "").strip(),
        "focus_chapter": _normalize_positive_int(payload.get("focus_chapter"), 0),
        "started_at": str(payload.get("started_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
        "created_files": _merge_file_entries([], payload.get("created_files"), default_status="created"),
        "updated_files": _merge_file_entries([], payload.get("updated_files"), default_status="updated"),
        "reused_files": _merge_file_entries([], payload.get("reused_files"), default_status="reused"),
    }


def _save_workflow_snapshot(session_id: str, payload: Optional[Dict[str, Any]]) -> None:
    if not session_id:
        return
    snapshot = _workflow_public_snapshot(payload)
    if snapshot is None:
        return
    try:
        from ...project_manager import get_project_manager

        get_project_manager().save_project_state(_workflow_state_key(session_id), snapshot)
    except Exception as exc:
        logger.debug(f"[Chat] save workflow snapshot failed: {exc}")


def _load_workflow_snapshot(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    try:
        from ...project_manager import get_project_manager

        payload = get_project_manager().load_project_state(_workflow_state_key(session_id), default=None)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.debug(f"[Chat] load workflow snapshot failed: {exc}")
        return None


def _delete_workflow_snapshot(session_id: str) -> None:
    if not session_id:
        return
    try:
        from ...project_manager import get_project_manager

        get_project_manager().delete_project_state(_workflow_state_key(session_id))
    except Exception as exc:
        logger.debug(f"[Chat] delete workflow snapshot failed: {exc}")


def _sync_workflow_snapshot(payload: Optional[Dict[str, Any]]) -> None:
    if not isinstance(payload, dict):
        return
    payload["updated_at"] = _now_iso()
    _save_workflow_snapshot(str(payload.get("session_id") or "").strip(), payload)


def _apply_workflow_update(active_run: Optional[Dict[str, Any]], update: Any) -> str:
    if not isinstance(active_run, dict):
        return ""
    if isinstance(update, str):
        update_payload = {"content": update}
    elif isinstance(update, dict):
        update_payload = dict(update)
    else:
        return ""

    content = str(update_payload.get("content") or update_payload.get("message") or "").strip()
    if content:
        active_run["last_progress"] = content
    for field in ("status", "target_agent", "current_agent", "stage", "output_dir", "last_error", "command", "run_id", "focus_module"):
        value = update_payload.get(field)
        if value not in (None, ""):
            active_run[field] = str(value).strip()
    if "focus_chapter" in update_payload:
        active_run["focus_chapter"] = _normalize_positive_int(update_payload.get("focus_chapter"), 0)

    if "created_files" in update_payload:
        active_run["created_files"] = _merge_file_entries(
            active_run.get("created_files"),
            update_payload.get("created_files"),
            default_status="created",
        )
    if "updated_files" in update_payload:
        active_run["updated_files"] = _merge_file_entries(
            active_run.get("updated_files"),
            update_payload.get("updated_files"),
            default_status="updated",
        )
    if "reused_files" in update_payload:
        active_run["reused_files"] = _merge_file_entries(
            active_run.get("reused_files"),
            update_payload.get("reused_files"),
            default_status="reused",
        )

    _sync_workflow_snapshot(active_run)
    return content


def _apply_router_result_to_workflow(active_run: Optional[Dict[str, Any]], router_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(active_run, dict):
        return None
    delegated_result = router_result.get("delegated_result") if isinstance(router_result, dict) and isinstance(router_result.get("delegated_result"), dict) else {}
    routed_to = str((router_result or {}).get("routed_to") or delegated_result.get("agent_name") or "").strip()
    if routed_to:
        active_run["target_agent"] = routed_to
        active_run["current_agent"] = routed_to
    if delegated_result.get("run_id"):
        active_run["run_id"] = str(delegated_result.get("run_id")).strip()
    if delegated_result.get("output_dir"):
        active_run["output_dir"] = str(delegated_result.get("output_dir")).strip()
    if delegated_result.get("focus_module"):
        active_run["focus_module"] = str(delegated_result.get("focus_module")).strip()
    if delegated_result.get("focus_chapter") is not None:
        active_run["focus_chapter"] = _normalize_positive_int(delegated_result.get("focus_chapter"), 0)
    active_run["created_files"] = _merge_file_entries(
        active_run.get("created_files"),
        delegated_result.get("created_files"),
        default_status="created",
    )
    active_run["updated_files"] = _merge_file_entries(
        active_run.get("updated_files"),
        delegated_result.get("updated_files"),
        default_status="updated",
    )
    active_run["reused_files"] = _merge_file_entries(
        active_run.get("reused_files"),
        delegated_result.get("reused_files"),
        default_status="reused",
    )

    if isinstance(router_result, dict) and not router_result.get("success", True):
        active_run["status"] = "failed"
        active_run["last_error"] = str((router_result.get("error") or delegated_result.get("error") or "")).strip()
    elif delegated_result.get("error"):
        active_run["status"] = "failed"
        active_run["last_error"] = str(delegated_result.get("error") or "").strip()
    else:
        active_run["status"] = str(active_run.get("status") or "completed")

    _sync_workflow_snapshot(active_run)
    return _workflow_public_snapshot(active_run)


def _get_workflow_record(session_key: str, session_id: str) -> Optional[Dict[str, Any]]:
    active_run = _get_active_workflow(session_key)
    if active_run:
        return active_run
    return _load_workflow_snapshot(session_id)


def _resolve_workflow_file_path(raw_path: str) -> Path:
    from ...project_manager import get_project_manager

    path_value = str(raw_path or "").strip()
    if not path_value:
        raise HTTPException(status_code=400, detail="path 不能为空")

    pm = get_project_manager()
    if not pm.current_project_id:
        raise HTTPException(status_code=400, detail="当前没有活动项目")

    project_dir = pm._get_project_dir(pm.current_project_id).resolve()
    requested_path = Path(path_value).expanduser()
    if not requested_path.is_absolute():
        requested_path = (project_dir / requested_path).resolve()
    else:
        requested_path = requested_path.resolve()

    try:
        requested_path.relative_to(project_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="只允许访问当前项目目录内的文件") from exc

    if not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    return requested_path


def _match_command_alias(message: str, aliases: tuple[str, ...], allow_compact_number: bool = False) -> Optional[str]:
    text = str(message or "").strip()
    if not text:
        return None
    if not text.startswith("/"):
        return None
    normalized = text[1:].lstrip()
    if not normalized:
        return None
    for alias in aliases:
        raw_alias = str(alias or "").strip()
        if not raw_alias:
            continue
        candidate = normalized.lower() if raw_alias.isascii() else normalized
        alias_value = raw_alias.lower() if raw_alias.isascii() else raw_alias
        if not candidate.startswith(alias_value):
            continue
        remainder = normalized[len(raw_alias):]
        if not remainder:
            return ""
        if remainder[:1].isspace():
            return remainder.strip()
        if allow_compact_number and remainder[:1].isdigit():
            return remainder.strip()
    return None


def _parse_explicit_command(message: str) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip()
    if not text.startswith("/"):
        return None

    chapter_definition = _EXPLICIT_COMMAND_DEFINITIONS["chapter"]
    chapter_args = _match_command_alias(
        message,
        tuple(chapter_definition.get("aliases") or ()),
        allow_compact_number=True,
    )
    if chapter_args is not None:
        raw_args = str(chapter_args or "").strip()
        chapter_match = re.match(r"^(\d+)(?:\s+(.*))?$", raw_args)
        payload: Dict[str, Any] = {
            "name": "chapter",
            "raw_args": raw_args,
            "display": str(chapter_definition.get("display") or "续写章节"),
            "chapter_number": int(chapter_match.group(1)) if chapter_match else 0,
            "message": str(chapter_match.group(2) or "").strip() if chapter_match else raw_args,
        }
        return payload

    for command_name, definition in _EXPLICIT_COMMAND_DEFINITIONS.items():
        if command_name == "chapter":
            continue
        raw_args = _match_command_alias(message, tuple(definition.get("aliases") or ()))
        if raw_args is None:
            continue
        raw_args = str(raw_args or "").strip()
        payload: Dict[str, Any] = {
            "name": command_name,
            "raw_args": raw_args,
            "display": str(definition.get("display") or command_name),
        }
        payload["message"] = raw_args
        return payload

    return None


def _parse_targeted_natural_language_command(message: str) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip()
    if not text or text.startswith("/"):
        return None

    normalized_text = re.sub(
        r"^(?:好(?:的|吧)?|那(?:就|先|直接)?|请|帮我|麻烦你|现在|直接|马上|先|先帮我|开始|然后|接着)+",
        "",
        text,
    ).strip()
    candidate_text = normalized_text or text

    chapter_match = re.match(
        r"^(?:续写章节\s*|(?:写|生成|创作)第)([0-9一二三四五六七八九十百千万两零〇]+)(?:章)?(?:正文)?(?:\s+(.*))?$",
        candidate_text,
    )
    if chapter_match:
        raw_args = str(chapter_match.group(2) or "").strip()
        chapter_number = 0
        try:
            number_text = str(chapter_match.group(1) or "").strip()
            if number_text.isdigit():
                chapter_number = int(number_text)
            else:
                digit_map = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
                unit_map = {"十": 10, "百": 100, "千": 1000, "万": 10000}
                total = 0
                current = 0
                for char in number_text:
                    if char in digit_map:
                        current = digit_map[char]
                        continue
                    if char in unit_map:
                        unit_value = unit_map[char]
                        if current == 0:
                            current = 1
                        if unit_value >= 10000:
                            total = (total + current) * unit_value
                        else:
                            total += current * unit_value
                        current = 0
                        continue
                    current = 0
                    total = 0
                    break
                chapter_number = total + current
        except Exception:
            chapter_number = 0
        return {
            "name": "chapter",
            "raw_args": raw_args,
            "display": "续写章节",
            "chapter_number": chapter_number,
            "message": raw_args,
        }

    for command_name, patterns in _NATURAL_LANGUAGE_COMMAND_PATTERNS.items():
        matched = next((pattern for pattern in patterns if candidate_text.startswith(pattern)), "")
        if not matched:
            continue
        raw_args = candidate_text[len(matched):].strip()
        payload_message = raw_args
        if command_name == "worldbuild" and any(token in candidate_text for token in ("保存", "同步", "资料库")):
            payload_message = candidate_text
        return {
            "name": command_name,
            "raw_args": raw_args,
            "display": str(_EXPLICIT_COMMAND_DEFINITIONS.get(command_name, {}).get("display") or matched),
            "message": payload_message,
        }

    return None


def _routing_hint_from_explicit_command(command: Dict[str, Any], active_model: str = "") -> Optional[Dict[str, Any]]:
    command_name = str((command or {}).get("name") or "").strip()
    if not command_name:
        return None

    intent_name = ""
    target_agent = "Communicator"
    confidence = 0.0

    if command_name == "chapter":
        intent_name = "continue_write"
        target_agent = "ChapterWriter"
        confidence = 1.0
    elif command_name == "worldbuild":
        intent_name = "create_novel"
        target_agent = "Worldbuilder"
        confidence = 1.0
    elif command_name == "outline":
        intent_name = "create_novel"
        target_agent = "Outliner"
        confidence = 1.0
    elif command_name == "create":
        intent_name = "create_novel"
        target_agent = "Coordinator"
        confidence = 1.0
    elif command_name in _WORKFLOW_CONTROL_COMMAND_NAMES:
        intent_name = "project_manage"
        target_agent = "Coordinator"
        confidence = 1.0

    hint = {
        "intent": intent_name,
        "target_agent": target_agent,
        "confidence": confidence,
    }
    resolved_model = _resolve_agent_effective_model(target_agent, active_model)
    if resolved_model:
        hint["model"] = resolved_model
    return hint


def _is_explicit_creation_trigger(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in _CREATE_START_PATTERNS)


def _is_explicit_character_save_trigger(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    patterns = (
        "加入资料库", "保存到资料库", "同步到资料库", "存到资料库", "写入资料库",
        "保存这个角色卡", "把角色卡保存", "确认保存角色卡",
    )
    return any(pattern in text for pattern in patterns)


def _is_explicit_character_draft_trigger(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    profile_keywords = ("角色档案", "人物档案", "角色卡", "人物卡", "人设卡", "角色设定", "人物设定", "主角设定")
    action_keywords = ("创建", "生成", "设计", "新建", "做", "写", "补全", "完善", "整理")
    if any(token in text for token in ("先别存档", "不要保存", "继续细化", "先讨论")):
        return False
    if any(keyword in text for keyword in ("创建角色", "生成角色", "设计角色", "创建主角", "生成主角", "设计主角")):
        return True
    return any(token in text for token in profile_keywords) and any(token in text for token in action_keywords)


def _normalize_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_creation_requirements(
    collected_info: Optional[Dict[str, Any]],
    message: str,
    router_agent: Any = None,
) -> Dict[str, Any]:
    info = dict(collected_info or {})
    novel_type = str(info.get("novel_type") or "").strip()
    if not novel_type and router_agent and hasattr(router_agent, "_extract_novel_type"):
        try:
            novel_type = str(router_agent._extract_novel_type(message) or "").strip()
        except Exception:
            novel_type = ""

    return {
        "novel_type": novel_type or "",
        "theme": str(info.get("theme") or "").strip(),
        "requirements": str(info.get("requirements") or "").strip(),
        "protagonist": str(info.get("protagonist") or "").strip(),
        "plot_idea": str(info.get("plot_idea") or message).strip(),
        "volume_count": _normalize_positive_int(info.get("volume_count"), 1),
        "chapters_per_volume": _normalize_positive_int(info.get("chapters_per_volume"), 5),
    }


def _get_builtin_chat_auto_save_targets() -> set[str]:
    from .projects import BUILTIN_PROJECT_DATA_TYPES

    return set(BUILTIN_PROJECT_DATA_TYPES) | {"chapters"}


def _load_chat_auto_save_enabled() -> bool:
    from ...project_manager import get_project_manager

    try:
        pm = get_project_manager()
        if not pm.current_project_id:
            return False
        payload = pm.load_project_state(CHAT_AUTO_SAVE_STATE_KEY, default={})
        if isinstance(payload, dict):
            return bool(payload.get("enabled"))
        return bool(payload)
    except Exception as exc:
        logger.debug(f"[Chat] load chat auto-save state failed: {exc}")
        return False


def _load_project_knowledge_categories() -> List[Dict[str, Any]]:
    from ...project_manager import get_project_manager

    try:
        pm = get_project_manager()
        if not pm.current_project_id:
            return []
        payload = pm.load_project_state(KNOWLEDGE_CATEGORIES_STATE_KEY, default=[])
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]
    except Exception as exc:
        logger.debug(f"[Chat] load knowledge categories state failed: {exc}")
        return []


def _extract_requested_knowledge_category(message: str) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip().lower()
    if not text:
        return None

    matched: Optional[Dict[str, Any]] = None
    matched_len = -1
    builtin_targets = _get_builtin_chat_auto_save_targets()
    for category in _load_project_knowledge_categories():
        name = str(category.get("name") or "").strip()
        key = str(category.get("key") or "").strip()
        candidates = [candidate.lower() for candidate in (name, key) if candidate]
        if not candidates:
            continue
        if not any(candidate in text for candidate in candidates):
            continue
        score = max(len(candidate) for candidate in candidates)
        if score <= matched_len:
            continue
        matched = dict(category)
        matched["builtin"] = bool(category.get("builtin")) or key in builtin_targets
        matched_len = score
    return matched


def _should_execute_via_router(
    intent_name: str,
    message: str,
    agent: Any,
    explicit_command: Optional[Dict[str, Any]] = None,
) -> bool:
    intent = str(intent_name or "").strip()
    if intent not in _ROUTER_EXECUTION_INTENTS:
        return False
    if intent == "create_character":
        return True
    if intent != "create_novel":
        return True
    return _is_explicit_creation_trigger(message)


def _infer_communicator_response_mode(
    processed_message: str,
    routing_hint: Optional[Dict[str, Any]] = None,
    targeted_command: Optional[Dict[str, Any]] = None,
) -> str:
    command_name = str((targeted_command or {}).get("name") or "").strip()
    intent_name = str((routing_hint or {}).get("intent") or "").strip()

    if command_name in {"create", "worldbuild", "outline"} or intent_name in {
        "create_novel",
        "create_character",
        "create_eventlines",
        "create_detail_outline",
        "create_chapter_settings",
    }:
        return "confirmation"

    text = str(processed_message or "").strip()
    if any(token in text for token in ("总结", "整理", "归纳", "梳理")):
        return "summary"
    if any(token in text for token in ("对比", "区别", "方案A", "方案B", "优缺点")):
        return "comparison"
    if any(token in text for token in ("计划", "步骤", "怎么做", "流程", "下一步")):
        return "planning"
    return "lightweight"


def _build_router_context(
    agent: Any,
    session_id: str,
    message: str,
    intent_name: str,
    router_agent: Any = None,
    explicit_command: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    collected_info = getattr(agent, "collected_info", {}) or {}
    context: Dict[str, Any] = {
        "session_id": session_id,
        "collected_info": dict(collected_info),
        "chat_auto_save_enabled": _load_chat_auto_save_enabled(),
        "chat_auto_save_builtin_targets": sorted(_get_builtin_chat_auto_save_targets()),
    }
    history = getattr(agent, "conversation_history", None) or []
    if history:
        context["conversation_history"] = _sanitize_conversation_history(history)

    if isinstance(explicit_command, dict):
        context["explicit_command"] = dict(explicit_command)

    if intent_name == "create_novel":
        should_auto_execute = bool(
            (isinstance(explicit_command, dict) and str(explicit_command.get("name") or "").strip() in _ROUTER_COMMAND_NAMES)
            or _is_explicit_creation_trigger(message)
            or context.get("chat_auto_save_enabled")
        )
        context["auto_execute"] = should_auto_execute
        context["requires_confirmation"] = not should_auto_execute
        context["creation_requirements"] = _normalize_creation_requirements(
            collected_info=collected_info,
            message=message,
            router_agent=router_agent,
        )
    elif intent_name == "create_character":
        is_save_request = _is_explicit_character_save_trigger(message)
        requested_category = _extract_requested_knowledge_category(message)
        requires_manual_category_selection = bool(requested_category and not requested_category.get("builtin"))
        should_auto_execute = bool(
            (isinstance(explicit_command, dict) and str(explicit_command.get("name") or "").strip() in _ROUTER_COMMAND_NAMES)
            or is_save_request
            or (context.get("chat_auto_save_enabled") and not requires_manual_category_selection)
        )
        context["auto_execute"] = should_auto_execute
        context["requires_confirmation"] = False
        context["requested_knowledge_category"] = requested_category
        context["requires_manual_category_selection"] = requires_manual_category_selection
        if requires_manual_category_selection:
            context["character_request_mode"] = "manual_category"
        else:
            context["character_request_mode"] = "save" if (is_save_request or context.get("chat_auto_save_enabled")) else "draft"
    elif intent_name in {"create_eventlines", "create_detail_outline", "create_chapter_settings"}:
        context["auto_execute"] = True
        context["requires_confirmation"] = False
    elif intent_name == "continue_write":
        context["auto_execute"] = True

    return context


def _extract_model_label(router_result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(router_result, dict):
        return ""
    delegated = router_result.get("delegated_result") if isinstance(router_result.get("delegated_result"), dict) else {}
    routing_info = router_result.get("routing_info") if isinstance(router_result.get("routing_info"), dict) else {}
    for bucket in (router_result, delegated, routing_info):
        for key in ("model", "model_used", "active_model"):
            value = str(bucket.get(key) or "").strip()
            if value:
                return value
    return ""


def _apply_router_result_to_routing_hint(
    routing_hint: Optional[Dict[str, Any]],
    router_result: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if routing_hint is None:
        routing_hint = {"intent": "", "target_agent": "Communicator", "confidence": 0.0}

    if not isinstance(router_result, dict):
        return routing_hint

    delegated = router_result.get("delegated_result") if isinstance(router_result.get("delegated_result"), dict) else {}
    routed_to = (
        str(router_result.get("routed_to") or "").strip()
        or str(delegated.get("agent_name") or "").strip()
    )
    if routed_to:
        routing_hint["target_agent"] = routed_to

    model_label = _extract_model_label(router_result)
    if model_label:
        routing_hint["model"] = model_label
    elif routed_to != "Communicator":
        routing_hint.pop("model", None)

    return routing_hint


def _append_agent_history(agent: Any, role: str, content: str) -> None:
    if not hasattr(agent, "conversation_history") or not isinstance(content, str):
        return
    text = content.strip()
    if not text:
        return
    agent.conversation_history.append({
        "role": role,
        "content": text,
    })


def _register_active_workflow(session_key: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("run_id", uuid4().hex[:12])
    payload.setdefault("status", "running")
    payload.setdefault("stage", "starting")
    payload.setdefault("current_agent", payload.get("target_agent", "Coordinator"))
    payload.setdefault("last_progress", "")
    payload.setdefault("last_error", "")
    payload.setdefault("output_dir", "")
    payload.setdefault("created_files", [])
    payload.setdefault("updated_files", [])
    payload.setdefault("reused_files", [])
    payload.setdefault("started_at", _now_iso())
    payload.setdefault("updated_at", payload["started_at"])
    _ACTIVE_WORKFLOW_RUNS[session_key] = payload
    _sync_workflow_snapshot(payload)
    return payload


def _get_active_workflow(session_key: str) -> Optional[Dict[str, Any]]:
    payload = _ACTIVE_WORKFLOW_RUNS.get(session_key)
    if not isinstance(payload, dict):
        return None
    task = payload.get("task")
    if task is not None and getattr(task, "done", lambda: False)():
        _ACTIVE_WORKFLOW_RUNS.pop(session_key, None)
        return None
    return payload


def _clear_active_workflow(session_key: str) -> None:
    _ACTIVE_WORKFLOW_RUNS.pop(session_key, None)


def _format_workflow_status(coordinator: Any, active_run: Optional[Dict[str, Any]]) -> str:
    workflow = _workflow_public_snapshot(active_run) if isinstance(active_run, dict) else active_run
    status = str((workflow or {}).get("status") or "").strip()
    checkpoint = None
    project = None
    if not status and coordinator and hasattr(coordinator, "get_project_status"):
        try:
            payload = coordinator.get_project_status() or {}
            status = str(payload.get("workflow_state") or "idle")
            checkpoint = payload.get("checkpoint")
            project = payload.get("project")
        except Exception:
            status = str(getattr(getattr(coordinator, "workflow_state", None), "value", "idle") or "idle")
    elif coordinator and hasattr(coordinator, "get_project_status"):
        try:
            payload = coordinator.get_project_status() or {}
            checkpoint = payload.get("checkpoint")
            project = payload.get("project")
        except Exception:
            checkpoint = None
            project = None
    if not status:
        status = "idle"
    current_chapter = checkpoint.get("current_chapter", 0) if isinstance(checkpoint, dict) else 0
    total_chapters = project.get("total_chapters", 0) if isinstance(project, dict) else 0
    completed_chapters = project.get("completed_chapters", 0) if isinstance(project, dict) else 0
    last_progress = (workflow or {}).get("last_progress", "")
    current_agent = str((workflow or {}).get("current_agent") or "").strip()
    stage = str((workflow or {}).get("stage") or "").strip()
    run_id = str((workflow or {}).get("run_id") or "").strip()
    created_files = (workflow or {}).get("created_files") or []
    updated_files = (workflow or {}).get("updated_files") or []
    reused_files = (workflow or {}).get("reused_files") or []
    last_error = str((workflow or {}).get("last_error") or "").strip()
    lines = [
        f"当前创作状态：`{status}`",
        f"已完成章节：{completed_chapters}/{total_chapters}" if total_chapters else f"当前章节进度：{current_chapter}",
    ]
    if run_id:
        lines.append(f"运行ID：`{run_id}`")
    if current_agent:
        lines.append(f"当前执行Agent：`{current_agent}`")
    if stage:
        lines.append(f"当前阶段：`{stage}`")
    if last_progress:
        lines.extend(["", "最近进度：", last_progress.strip()])
    if created_files or updated_files or reused_files:
        lines.extend([
            "",
            f"内容同步情况：新增 {len(created_files)} 项，更新 {len(updated_files)} 项，复用 {len(reused_files)} 项",
        ])
    if last_error:
        lines.extend(["", "最近错误：", last_error])
    return "\n".join(lines)


def _get_coordinator_workflow_state(coordinator: Any, default: str = "idle") -> str:
    state = str(default or "idle").strip() or "idle"
    if coordinator and hasattr(coordinator, "get_project_status"):
        try:
            payload = coordinator.get_project_status() or {}
            next_state = str(payload.get("workflow_state") or "").strip()
            if next_state:
                return next_state
        except Exception:
            pass
    return str(getattr(getattr(coordinator, "workflow_state", None), "value", state) or state).strip() or state


def _handle_workflow_control(
    action: str,
    session_key: str,
    session_id: str,
    coordinator: Any,
) -> Optional[Dict[str, Any]]:
    if not action or coordinator is None:
        return None

    active_run = _get_workflow_record(session_key, session_id)
    current_state = _get_coordinator_workflow_state(coordinator, "idle")

    if action == "status":
        return {
            "reply": _format_workflow_status(coordinator, active_run),
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
            "handled": True,
        }

    if action == "pause":
        if not active_run and current_state not in {"writing", "worldbuilding", "outlining", "paused"}:
            return {
                "reply": "当前没有正在执行的创作任务，无法暂停。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "handled": True,
            }
        coordinator.pause()
        paused_state = _get_coordinator_workflow_state(coordinator, "paused")
        if isinstance(active_run, dict):
            _apply_workflow_update(active_run, {
                "status": paused_state,
                "stage": active_run.get("stage") or paused_state,
                "current_agent": active_run.get("current_agent") or active_run.get("target_agent") or "Coordinator",
                "content": "已发送暂停指令。",
            })
        return {
            "reply": "已发送暂停指令。当前创作会在下一个可中断检查点暂停。",
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
            "handled": True,
        }

    if action == "resume":
        if active_run is None and current_state != "paused":
            return {
                "reply": "当前没有处于暂停中的活动创作任务，无法直接恢复。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "handled": True,
            }
        coordinator.resume()
        resumed_state = _get_coordinator_workflow_state(coordinator, "writing")
        if isinstance(active_run, dict):
            _apply_workflow_update(active_run, {
                "status": resumed_state,
                "content": "已发送恢复指令。",
            })
        return {
            "reply": "已发送恢复指令，创作会继续执行。",
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
            "handled": True,
        }

    if action == "cancel":
        if not active_run and current_state not in {"writing", "worldbuilding", "outlining", "paused"}:
            return {
                "reply": "当前没有正在执行的创作任务，无法取消。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "handled": True,
            }
        coordinator.cancel()
        cancelled_state = _get_coordinator_workflow_state(coordinator, "cancelled")
        if isinstance(active_run, dict):
            _apply_workflow_update(active_run, {
                "status": cancelled_state,
                "stage": "cancelled",
                "content": "已发送取消指令。",
            })
        return {
            "reply": "已发送取消指令。当前创作会尽快停止。",
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
            "handled": True,
        }

    return None


def _get_chat_runtime_context(session_id: str) -> Dict[str, Any]:
    from ...project_manager import get_project_manager
    from ...agents import get_chat_session_store

    router_agent = get_router_agent()
    coordinator = get_coordinator()
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()
    return {
        "router_agent": router_agent,
        "coordinator": coordinator,
        "pm": pm,
        "project_id": project_id,
        "session_key": session_key,
        "store": store,
    }


async def _ensure_chat_agent(session_key: str, session_id: str, project_id: str, store: Any, router_agent: Any):
    from ...agents import CommunicatorAgent

    agent = chat_sessions.get(session_key)
    if agent is None:
        agent = CommunicatorAgent()
        saved = store.load(session_id, project_id)
        if saved:
            agent.conversation_history = saved.conversation_history
            agent.collected_info = saved.collected_info
        else:
            await agent.start_conversation()
        chat_sessions[session_key] = agent

    if router_agent:
        agent.set_router_agent(router_agent)
        router_kb = getattr(router_agent, "knowledge_base", None)
        if router_kb:
            agent.set_knowledge_base(router_kb)

    _refresh_runtime_model_configs(agent, router_agent)
    return agent


def _refresh_runtime_model_configs(agent: Any, router_agent: Any = None) -> str:
    refreshed_agents = []

    def _refresh_one(target: Any) -> None:
        if not target or target in refreshed_agents:
            return
        refreshed_agents.append(target)
        try:
            if hasattr(target, "refresh_model_config"):
                target.refresh_model_config()
        except Exception as refresh_error:
            logger.debug(f"[Chat] refresh model config failed for {getattr(target, 'name', type(target).__name__)}: {refresh_error}")

    _refresh_one(agent)
    _refresh_one(router_agent)

    if router_agent:
        for attr_name in ("_communicator", "_polisher", "_continuous_writer"):
            _refresh_one(getattr(router_agent, attr_name, None))

    active_model = ""
    try:
        if hasattr(agent, "_get_model_name"):
            active_model = str(agent._get_model_name() or "").strip()
    except Exception:
        active_model = ""
    return active_model


async def _build_chat_routing_hint(
    processed_message: str,
    targeted_command: Optional[Dict[str, Any]],
    router_agent: Any,
    active_model: str,
) -> Optional[Dict[str, Any]]:
    routing_hint = None
    if targeted_command and targeted_command.get("name") in _ROUTER_COMMAND_NAMES:
        routing_hint = _routing_hint_from_explicit_command(targeted_command, active_model)
    elif router_agent and hasattr(router_agent, "analyze_intent"):
        try:
            intent_analysis = await router_agent.analyze_intent(processed_message)
            intent_name = _extract_intent_name(intent_analysis)
            confidence = float(getattr(intent_analysis, "confidence", 0.0) or 0.0)
            routing_hint = {
                "intent": intent_name,
                "target_agent": INTENT_TARGET_AGENT_MAP.get(intent_name, "Communicator"),
                "confidence": confidence,
            }
            if active_model and routing_hint.get("target_agent") == "Communicator":
                routing_hint["model"] = active_model
        except Exception as analyze_error:
            logger.debug(f"[Chat] intent analysis failed: {analyze_error}")
    return routing_hint


def _prepare_chat_request(
    raw_message: str,
    session_key: str,
    session_id: str,
    coordinator: Any,
):
    from ...prompts import check_user_input_security, get_security_response

    is_safe, processed_message = check_user_input_security(raw_message)
    if not is_safe:
        return {
            "ok": False,
            "security_reply": get_security_response(),
            "processed_message": "",
            "targeted_command": None,
            "handled_control": None,
        }

    explicit_command = _parse_explicit_command(processed_message)
    targeted_command = explicit_command or _parse_targeted_natural_language_command(processed_message)
    workflow_control = (
        str(targeted_command.get("name") or "")
        if targeted_command and targeted_command.get("name") in _WORKFLOW_CONTROL_COMMAND_NAMES
        else ""
    )
    handled_control = _handle_workflow_control(workflow_control, session_key, session_id, coordinator)

    return {
        "ok": True,
        "security_reply": "",
        "processed_message": processed_message,
        "targeted_command": targeted_command,
        "handled_control": handled_control,
    }


def _ensure_default_routing_hint(
    routing_hint: Optional[Dict[str, Any]],
    active_model: str,
) -> Dict[str, Any]:
    hint = dict(routing_hint or {})
    if not hint:
        hint = {
            "intent": "",
            "target_agent": "Communicator",
            "confidence": 0.0,
        }
    if active_model and hint.get("target_agent") == "Communicator":
        hint.setdefault("model", active_model)
    return hint


def _should_execute_router_request(
    router_agent: Any,
    routing_hint: Optional[Dict[str, Any]],
    targeted_command: Optional[Dict[str, Any]],
    processed_message: str,
    agent: Any,
) -> bool:
    return bool(
        router_agent
        and routing_hint
        and (
            (targeted_command and targeted_command.get("name") in _ROUTER_COMMAND_NAMES)
            or _should_execute_via_router(
                routing_hint.get("intent", ""),
                processed_message,
                agent,
                explicit_command=targeted_command,
            )
        )
    )


def _register_router_workflow_run(
    session_key: str,
    session_id: str,
    project_id: str,
    routing_hint: Dict[str, Any],
    targeted_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    target_agent = str(routing_hint.get("target_agent") or "Coordinator").strip() or "Coordinator"
    return _register_active_workflow(session_key, {
        "status": "running",
        "session_id": session_id,
        "project_id": project_id,
        "last_progress": "",
        "command": str((targeted_command or {}).get("name") or routing_hint.get("intent") or "").strip(),
        "target_agent": target_agent,
        "current_agent": target_agent,
        "stage": "starting",
    })


def _build_router_message_and_context(
    agent: Any,
    session_id: str,
    processed_message: str,
    routing_hint: Dict[str, Any],
    router_agent: Any,
    targeted_command: Optional[Dict[str, Any]],
    progress_callback: Any,
    run_id: str,
) -> tuple[str, Dict[str, Any]]:
    router_message = str((targeted_command or {}).get("message") or processed_message).strip() or processed_message
    router_context = _build_router_context(
        agent=agent,
        session_id=session_id,
        message=router_message,
        intent_name=routing_hint.get("intent", ""),
        router_agent=router_agent,
        explicit_command=targeted_command,
    )
    router_context["progress_callback"] = progress_callback
    router_context["run_id"] = run_id
    return router_message, router_context


def _merge_router_delegated_info(agent: Any, router_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    delegated_result = router_result.get("delegated_result") if isinstance(router_result, dict) and isinstance(router_result.get("delegated_result"), dict) else {}
    delegated_info = delegated_result.get("collected_info")
    if isinstance(delegated_info, dict) and delegated_info:
        current_info = getattr(agent, "collected_info", {}) or {}
        current_info.update(delegated_info)
        agent.collected_info = current_info
    return delegated_result


def _persist_chat_session(store: Any, session_id: str, project_id: str, agent: Any) -> None:
    from ...agents import ChatSessionState

    store.save(
        ChatSessionState(
            session_id=session_id,
            project_id=project_id,
            conversation_history=getattr(agent, "conversation_history", []) or [],
            collected_info=getattr(agent, "collected_info", {}) or {},
        )
    )


async def _persist_chat_session_if_active(
    *,
    session_key: str,
    session_id: str,
    project_id: str,
    store: Any,
    agent: Any,
) -> bool:
    lock = await _get_chat_session_lock(session_key)
    async with lock:
        current_agent = chat_sessions.get(session_key)
        if current_agent is None:
            return False
        if current_agent is not agent:
            agent = current_agent
        _persist_chat_session(store, session_id, project_id, agent)
        return True


@router.post("/chat/start")
async def start_chat(session_id: str = "default"):
    """开始新对话"""
    from ...agents import CommunicatorAgent, get_chat_session_store, ChatSessionState
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    store = get_chat_session_store()

    session_key = f"{project_id}::{session_id}"
    lock = await _get_chat_session_lock(session_key)
    async with lock:
        # 如果存在可恢复会话，直接恢复
        saved = store.load(session_id, project_id)
        agent = CommunicatorAgent()

        router_agent = get_router_agent()
        if router_agent:
            agent.set_router_agent(router_agent)
            if router_agent.knowledge_base:
                agent.set_knowledge_base(router_agent.knowledge_base)

        if saved:
            agent.conversation_history = saved.conversation_history
            agent.collected_info = saved.collected_info
            chat_sessions[session_key] = agent
            return JSONResponse({
                "session_id": session_id,
                "reply": "已恢复上次对话，会话继续。",
                "is_complete": False,
                "restored": True
            })

        opening = await agent.start_conversation()
        chat_sessions[session_key] = agent

        store.save(
            ChatSessionState(
                session_id=session_id,
                project_id=project_id,
                conversation_history=agent.conversation_history,
                collected_info=agent.collected_info
            )
        )

        return JSONResponse({
            "session_id": session_id,
            "reply": opening,
            "is_complete": False,
            "restored": False
        })


@router.get("/chat/history")
async def get_chat_history(session_id: str = "default"):
    """Get current session history for frontend restore after refresh."""
    from ...agents import get_chat_session_store
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        history = []
        agent = chat_sessions.get(session_key)
        if agent is not None:
            history = getattr(agent, "conversation_history", []) or []
        else:
            saved = store.load(session_id, project_id)
            if saved:
                history = saved.conversation_history

        normalized = _sanitize_conversation_history(history)
        return JSONResponse({
            "session_id": session_id,
            "history": normalized,
            "count": len(normalized),
            "restored": bool(normalized),
        })


@router.get("/chat/sessions")
async def list_chat_sessions():
    """List chat sessions for current project scope."""
    from ...agents import get_chat_session_store
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    store = get_chat_session_store()
    now_ts = int(time.time())
    scope = project_id or "default"
    session_dir = store.storage_dir / scope

    session_map = {}
    if session_dir.exists():
        for file_path in session_dir.glob("*.json"):
            session_id = file_path.stem
            if not _SESSION_ID_PATTERN.fullmatch(session_id):
                continue
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            expires_at = int(payload.get("expires_at", 0) or 0)
            if expires_at and now_ts >= expires_at:
                try:
                    file_path.unlink()
                except Exception:
                    pass
                continue

            history = payload.get("conversation_history", [])
            preview_meta = _session_preview_from_history(history)
            session_map[session_id] = {
                "session_id": session_id,
                "created_at": payload.get("created_at", ""),
                "updated_at": payload.get("updated_at", ""),
                "message_count": preview_meta["message_count"],
                "last_message_preview": preview_meta["last_message_preview"],
            }

    # Merge in-memory sessions in case they are newer than disk snapshot
    for session_key, agent in chat_sessions.items():
        key_project_id, _, key_session_id = session_key.partition("::")
        if key_project_id != project_id or not key_session_id:
            continue
        history = getattr(agent, "conversation_history", []) or []
        preview_meta = _session_preview_from_history(history)
        current = session_map.get(key_session_id, {
            "session_id": key_session_id,
            "created_at": "",
            "updated_at": "",
            "message_count": 0,
            "last_message_preview": "",
        })
        current["message_count"] = max(current["message_count"], preview_meta["message_count"])
        if preview_meta["last_message_preview"]:
            current["last_message_preview"] = preview_meta["last_message_preview"]
        session_map[key_session_id] = current

    sessions = list(session_map.values())
    sessions.sort(key=lambda item: (item.get("updated_at", ""), item.get("session_id", "")), reverse=True)

    return JSONResponse({
        "project_id": project_id,
        "sessions": sessions,
        "count": len(sessions),
    })


@router.post("/chat/sessions")
async def create_chat_session(session_id: str = ""):
    """Create an empty chat session for manual session management."""
    from ...agents import get_chat_session_store, ChatSessionState
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    store = get_chat_session_store()

    requested = (session_id or "").strip()
    if requested:
        target_session_id = _normalize_session_id(requested)
    else:
        base_ts = int(time.time() * 1000)
        nonce = 0
        while True:
            target_session_id = f"copilot_{base_ts}" if nonce == 0 else f"copilot_{base_ts}_{nonce}"
            session_key = f"{project_id}::{target_session_id}"
            if session_key in chat_sessions or store.load(target_session_id, project_id):
                nonce += 1
                continue
            break

    session_key = f"{project_id}::{target_session_id}"
    lock = await _get_chat_session_lock(session_key)
    async with lock:
        existing = store.load(target_session_id, project_id)
        created = False
        if not existing:
            created = store.save(
                ChatSessionState(
                    session_id=target_session_id,
                    project_id=project_id,
                    conversation_history=[],
                    collected_info={},
                )
            )

    return JSONResponse({
        "session_id": target_session_id,
        "project_id": project_id,
        "created": bool(created),
    })


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete one chat session by id."""
    from ...agents import get_chat_session_store
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    store = get_chat_session_store()
    session_key = f"{project_id}::{session_id}"

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        in_memory_cleared = chat_sessions.pop(session_key, None) is not None
        persisted_cleared = store.delete(session_id, project_id)
        _clear_active_workflow(session_key)
        _delete_workflow_snapshot(session_id)

    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "cleared": bool(in_memory_cleared or persisted_cleared),
    })


@router.get("/chat/workflow-status")
async def get_chat_workflow_status(session_id: str = "copilot"):
    """Return the latest observable workflow state for the current Copilot session."""
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    coordinator = get_coordinator()
    workflow = _get_workflow_record(session_key, session_id)
    snapshot = _workflow_public_snapshot(workflow) or {
        "run_id": "",
        "session_id": session_id,
        "project_id": project_id,
        "command": "",
        "status": "idle",
        "target_agent": "",
        "current_agent": "",
        "stage": "",
        "last_progress": "",
        "last_error": "",
        "output_dir": "",
        "focus_module": "",
        "focus_chapter": 0,
        "started_at": "",
        "updated_at": "",
        "created_files": [],
        "updated_files": [],
        "reused_files": [],
    }
    return JSONResponse({
        "workflow": snapshot,
        "reply": _format_workflow_status(coordinator, snapshot),
    })


@router.get("/chat/workflow-file")
async def download_chat_workflow_file(path: str, session_id: str = "copilot"):
    """Safely download a workflow-produced file within the current project directory."""
    session_id = _normalize_session_id(session_id)
    requested_path = _resolve_workflow_file_path(path)
    return FileResponse(
        path=requested_path,
        filename=requested_path.name,
        media_type="application/octet-stream",
    )


@router.get("/chat/workflow-file-preview")
async def preview_chat_workflow_file(path: str, session_id: str = "copilot"):
    """Return a text preview for workflow-produced files within the current project directory."""
    session_id = _normalize_session_id(session_id)
    requested_path = _resolve_workflow_file_path(path)
    suffix = requested_path.suffix.lower()
    if suffix not in {".txt", ".md", ".json", ".log"}:
        raise HTTPException(status_code=400, detail="当前文件类型不支持应用内预览")

    content = requested_path.read_text(encoding="utf-8", errors="replace")
    truncated = False
    if len(content) > 120000:
        content = content[:120000]
        truncated = True

    language = {
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".log": "text",
    }.get(suffix, "text")

    return JSONResponse({
        "path": str(requested_path),
        "filename": requested_path.name,
        "language": language,
        "content": content,
        "truncated": truncated,
        "download_url": f"/api/v1/chat/workflow-file?session_id={session_id}&path={path}",
    })


@router.post("/chat")
async def chat(request: ChatRequest):
    """发送对话消息（增强版：集成智能路由）"""
    from ...agents import ChatSessionState

    session_id = _normalize_session_id(request.session_id)
    runtime = _get_chat_runtime_context(session_id)
    router_agent = runtime["router_agent"]
    coordinator = runtime["coordinator"]
    pm = runtime["pm"]
    project_id = runtime["project_id"]
    session_key = runtime["session_key"]
    store = runtime["store"]

    prepared = _prepare_chat_request(request.message, session_key, session_id, coordinator)
    if not prepared["ok"]:
        return JSONResponse({
            "reply": prepared["security_reply"],
            "is_complete": False
        })

    processed_message = prepared["processed_message"]
    targeted_command = prepared["targeted_command"]
    handled_control = prepared["handled_control"]
    if handled_control:
        return JSONResponse({
            "reply": handled_control["reply"],
            "is_complete": False,
            "routing": handled_control["routing"],
            "workflow": handled_control.get("workflow"),
        })
    
    lock = await _get_chat_session_lock(session_key)
    try:
        async with lock:
            agent = await _ensure_chat_agent(session_key, session_id, project_id, store, router_agent)
            active_model = _refresh_runtime_model_configs(agent, router_agent)
            routing_hint = await _build_chat_routing_hint(
                processed_message=processed_message,
                targeted_command=targeted_command,
                router_agent=router_agent,
                active_model=active_model,
            )
            communicator_response_mode = _infer_communicator_response_mode(
                processed_message=processed_message,
                routing_hint=routing_hint,
                targeted_command=targeted_command,
            )
            execute_via_router = _should_execute_router_request(
                router_agent=router_agent,
                routing_hint=routing_hint,
                targeted_command=targeted_command,
                processed_message=processed_message,
                agent=agent,
            )

            active_run = None
            router_message = ""
            router_context: Dict[str, Any] = {}
            if execute_via_router:
                active_run = _register_router_workflow_run(
                    session_key=session_key,
                    session_id=session_id,
                    project_id=project_id,
                    routing_hint=routing_hint,
                    targeted_command=targeted_command,
                )

                async def capture_progress(update: Any):
                    _apply_workflow_update(active_run, update)

                router_message, router_context = _build_router_message_and_context(
                    agent=agent,
                    session_id=session_id,
                    processed_message=processed_message,
                    routing_hint=routing_hint,
                    router_agent=router_agent,
                    targeted_command=targeted_command,
                    progress_callback=capture_progress,
                    run_id=active_run["run_id"],
                )
            else:
                result = await agent.chat(
                    processed_message,
                    runtime_context={"response_mode": communicator_response_mode},
                )

                backend_error = str(result.get("error", "") or "").strip()
                fallback_reply = "抱歉，我遇到了一些问题。能重新告诉我你的想法吗？"
                if backend_error and (not result.get("reply") or result.get("reply") == fallback_reply):
                    short_error = backend_error[:220]
                    result["reply"] = (
                        f"当前请求失败：{short_error}\n\n"
                        "请检查 API Key、模型权限或账号状态。"
                    )

                routing_hint = _ensure_default_routing_hint(routing_hint, active_model)

                if not result.get("reply") and router_agent:
                    router_result = await router_agent.route_and_respond(processed_message)
                    raw_reply_text = str(router_result.get("response") or "抱歉，我暂时无法理解您的需求。").strip()
                    result["reply"] = _strip_visible_technical_markers(raw_reply_text)
                    result["routed"] = True
                    routing_hint = _apply_router_result_to_routing_hint(routing_hint, router_result)

                if routing_hint:
                    result["routing"] = routing_hint

                _persist_chat_session(store, session_id, project_id, agent)
                return JSONResponse(result)

        router_result = None
        try:
            router_result = await router_agent.route_and_respond(router_message, context=router_context)
        finally:
            _clear_active_workflow(session_key)

        async with lock:
            active_agent = chat_sessions.get(session_key) or agent
            raw_reply_text = str((router_result or {}).get("response") or "抱歉，我暂时无法理解您的需求。").strip()
            reply_text = _strip_visible_technical_markers(raw_reply_text)

            _append_agent_history(active_agent, "user", processed_message)
            _append_agent_history(active_agent, "assistant", reply_text)

            delegated_result = _merge_router_delegated_info(active_agent, router_result or {})
            workflow_snapshot = _apply_router_result_to_workflow(active_run, router_result or {})
            if isinstance(active_run, dict) and active_run.get("status") not in {"failed", "cancelled"}:
                _apply_workflow_update(active_run, {"status": "completed", "stage": "completed"})
                workflow_snapshot = _workflow_public_snapshot(active_run)

            routing_hint = _apply_router_result_to_routing_hint(routing_hint, router_result or {})
            result = {
                "reply": reply_text,
                "is_complete": bool(delegated_result.get("is_complete", False)),
                "collected_info": getattr(active_agent, "collected_info", {}) or {},
                "routed": True,
                "routing_info": (router_result or {}).get("routing_info"),
                "delegated_result": delegated_result or None,
                "routed_to": (router_result or {}).get("routed_to"),
                "workflow": workflow_snapshot,
                "created_files": (workflow_snapshot or {}).get("created_files", []),
                "updated_files": (workflow_snapshot or {}).get("updated_files", []),
                "reused_files": (workflow_snapshot or {}).get("reused_files", []),
                "output_dir": (workflow_snapshot or {}).get("output_dir", ""),
            }
            if routing_hint:
                result["routing"] = routing_hint
            if session_key in chat_sessions:
                _persist_chat_session(store, session_id, project_id, active_agent)
            return JSONResponse(result)

    except Exception as e:
        logger.error(f"[Chat] 处理失败: {e}")
        workflow = _get_workflow_record(session_key, session_id)
        if isinstance(workflow, dict):
            _apply_workflow_update(workflow, {
                "status": "failed",
                "stage": "failed",
                "last_error": str(e),
                "content": f"执行失败：{str(e)}",
            })
            _clear_active_workflow(session_key)
        return JSONResponse({
            "reply": "抱歉，处理您的请求时遇到问题。请稍后重试。",
            "is_complete": False,
            "error": str(e),
            "workflow": _workflow_public_snapshot(workflow),
        })


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话（SSE）— 实时输出AI回复"""
    from ...agents import ChatSessionState

    session_id = _normalize_session_id(request.session_id)
    runtime = _get_chat_runtime_context(session_id)
    router_agent = runtime["router_agent"]
    coordinator = runtime["coordinator"]
    pm = runtime["pm"]
    project_id = runtime["project_id"]
    session_key = runtime["session_key"]
    store = runtime["store"]

    prepared = _prepare_chat_request(request.message, session_key, session_id, coordinator)
    if not prepared["ok"]:
        error_reply = prepared["security_reply"]
        async def error_gen():
            yield f"data: {json.dumps({'type': 'chunk', 'content': error_reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'reply': error_reply, 'is_complete': False}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    processed_message = prepared["processed_message"]
    targeted_command = prepared["targeted_command"]
    handled_control = prepared["handled_control"]
    if handled_control:
        async def control_gen():
            reply = handled_control["reply"]
            yield f"data: {json.dumps({'type': 'chunk', 'content': reply}, ensure_ascii=False)}\n\n"
            if handled_control.get("workflow"):
                yield f"data: {json.dumps({'type': 'workflow', 'workflow': handled_control['workflow']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'reply': reply, 'is_complete': False, 'routing': handled_control['routing'], 'workflow': handled_control.get('workflow')}, ensure_ascii=False)}\n\n"
        return StreamingResponse(control_gen(), media_type="text/event-stream")

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        agent = await _ensure_chat_agent(session_key, session_id, project_id, store, router_agent)
        active_model = _refresh_runtime_model_configs(agent, router_agent)
        routing_hint = await _build_chat_routing_hint(
            processed_message=processed_message,
            targeted_command=targeted_command,
            router_agent=router_agent,
            active_model=active_model,
        )
        communicator_response_mode = _infer_communicator_response_mode(
            processed_message=processed_message,
            routing_hint=routing_hint,
            targeted_command=targeted_command,
        )

        routing_hint = _ensure_default_routing_hint(routing_hint, active_model)

    execute_via_router = _should_execute_router_request(
        router_agent=router_agent,
        routing_hint=routing_hint,
        targeted_command=targeted_command,
        processed_message=processed_message,
        agent=agent,
    )

    if execute_via_router:
        async def routed_generate():
            queue: asyncio.Queue = asyncio.Queue()
            full_text = ""
            active_run = _register_router_workflow_run(
                session_key=session_key,
                session_id=session_id,
                project_id=project_id,
                routing_hint=routing_hint,
                targeted_command=targeted_command,
            )

            async def push_progress_chunk(update: Any):
                chunk_text = _apply_workflow_update(active_run, update)
                workflow_snapshot = _workflow_public_snapshot(active_run)
                if chunk_text:
                    await queue.put({"type": "chunk", "content": chunk_text})
                if workflow_snapshot:
                    await queue.put({"type": "workflow", "workflow": workflow_snapshot})

            async def runner():
                try:
                    router_message, router_context = _build_router_message_and_context(
                        agent=agent,
                        session_id=session_id,
                        processed_message=processed_message,
                        routing_hint=routing_hint,
                        router_agent=router_agent,
                        targeted_command=targeted_command,
                        progress_callback=push_progress_chunk,
                        run_id=active_run["run_id"],
                    )
                    router_result = await router_agent.route_and_respond(router_message, context=router_context)
                    await queue.put({"type": "router_done", "router_result": router_result})
                except Exception as exc:
                    await queue.put({"type": "error", "message": str(exc)})

            runner_task = asyncio.create_task(runner())
            active_run["task"] = runner_task
            try:
                while True:
                    event = await queue.get()
                    event_type = event.get("type")

                    if event_type == "chunk":
                        chunk_text = str(event.get("content") or "")
                        if chunk_text:
                            full_text += chunk_text
                            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_text}, ensure_ascii=False)}\n\n"
                        continue

                    if event_type == "workflow":
                        workflow_payload = event.get("workflow")
                        if workflow_payload:
                            yield f"data: {json.dumps({'type': 'workflow', 'workflow': workflow_payload}, ensure_ascii=False)}\n\n"
                        continue

                    if event_type == "router_done":
                        router_result = event.get("router_result") or {}
                        workflow_snapshot = _apply_router_result_to_workflow(active_run, router_result)
                        if isinstance(active_run, dict) and active_run.get("status") not in {"failed", "cancelled"}:
                            _apply_workflow_update(active_run, {"status": "completed", "stage": "completed"})
                            workflow_snapshot = _workflow_public_snapshot(active_run)
                        routing = _apply_router_result_to_routing_hint(dict(routing_hint), router_result) or routing_hint
                        raw_reply_text = str(router_result.get("response") or "抱歉，我暂时无法理解您的需求。").strip()
                        reply_text = _strip_visible_technical_markers(raw_reply_text)

                        history_agent = agent
                        lock = await _get_chat_session_lock(session_key)
                        async with lock:
                            active_agent = chat_sessions.get(session_key)
                            if active_agent is not None:
                                history_agent = active_agent
                                _append_agent_history(history_agent, "user", processed_message)
                                _append_agent_history(history_agent, "assistant", reply_text)

                        delegated_result = _merge_router_delegated_info(history_agent, router_result)

                        if reply_text:
                            final_chunk = reply_text if not full_text.strip() else f"\n\n{reply_text}"
                            full_text += final_chunk
                            yield f"data: {json.dumps({'type': 'chunk', 'content': final_chunk}, ensure_ascii=False)}\n\n"

                        done_payload = {
                            "type": "done",
                            "reply": _strip_visible_technical_markers(full_text or reply_text),
                            "is_complete": bool(delegated_result.get("is_complete", False)),
                            "collected_info": getattr(history_agent, "collected_info", {}) or {},
                            "routing": routing,
                            "delegated_result": delegated_result or None,
                            "routed_to": router_result.get("routed_to"),
                            "workflow": workflow_snapshot,
                            "created_files": (workflow_snapshot or {}).get("created_files", []),
                            "updated_files": (workflow_snapshot or {}).get("updated_files", []),
                            "reused_files": (workflow_snapshot or {}).get("reused_files", []),
                            "output_dir": (workflow_snapshot or {}).get("output_dir", ""),
                        }
                        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

                        await _persist_chat_session_if_active(
                            session_key=session_key,
                            session_id=session_id,
                            project_id=project_id,
                            store=store,
                            agent=history_agent,
                        )
                        break

                    if event_type == "error":
                        logger.error(f"[Chat Stream Routed] error: {event.get('message')}")
                        _apply_workflow_update(active_run, {
                            "status": "failed",
                            "stage": "failed",
                            "last_error": str(event.get("message") or ""),
                            "content": f"执行失败：{str(event.get('message') or '')}",
                        })
                        workflow_snapshot = _workflow_public_snapshot(active_run)
                        yield f"data: {json.dumps({'type': 'workflow', 'workflow': workflow_snapshot}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'error', 'message': event.get('message', ''), 'workflow': workflow_snapshot}, ensure_ascii=False)}\n\n"
                        break
            except Exception as e:
                logger.error(f"[Chat Stream Routed] error: {e}")
                _apply_workflow_update(active_run, {
                    "status": "failed",
                    "stage": "failed",
                    "last_error": str(e),
                    "content": f"执行失败：{str(e)}",
                })
                workflow_snapshot = _workflow_public_snapshot(active_run)
                yield f"data: {json.dumps({'type': 'workflow', 'workflow': workflow_snapshot}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'workflow': workflow_snapshot}, ensure_ascii=False)}\n\n"
            finally:
                if not runner_task.done():
                    runner_task.cancel()
                    try:
                        await runner_task
                    except asyncio.CancelledError:
                        pass
                _clear_active_workflow(session_key)

        return StreamingResponse(routed_generate(), media_type="text/event-stream")

    # 流式生成器（锁已释放）
    async def generate():
        try:
            async for sse_event in agent.chat_stream(
                processed_message,
                runtime_context={"response_mode": communicator_response_mode},
            ):
                # 在done事件中注入routing
                if '"type": "done"' in sse_event or '"type":"done"' in sse_event:
                    try:
                        data_str = sse_event.split("data: ", 1)[1].rstrip("\n")
                        data = json.loads(data_str)
                        data["routing"] = routing_hint
                        workflow = _workflow_public_snapshot(_get_workflow_record(session_key, session_id))
                        if workflow:
                            data["workflow"] = workflow
                        sse_event = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass
                yield sse_event

            await _persist_chat_session_if_active(
                session_key=session_key,
                session_id=session_id,
                project_id=project_id,
                store=store,
                agent=agent,
            )
        except Exception as e:
            logger.error(f"[Chat Stream] error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat/complete")
async def complete_chat(session_id: str = "default"):
    """完成对话，获取结构化需求"""
    from ...agents import CommunicatorAgent, get_chat_session_store
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        if session_key not in chat_sessions:
            saved = store.load(session_id, project_id)
            if not saved:
                raise HTTPException(status_code=404, detail="Session not found")

            agent = CommunicatorAgent()
            router_agent = get_router_agent()
            if router_agent:
                agent.set_router_agent(router_agent)
                router_kb = getattr(router_agent, "knowledge_base", None)
                if router_kb:
                    agent.set_knowledge_base(router_kb)
            agent.conversation_history = saved.conversation_history
            agent.collected_info = saved.collected_info
            chat_sessions[session_key] = agent

        agent = chat_sessions[session_key]
        requirements = await agent.get_structured_requirements()

        del chat_sessions[session_key]
        store.delete(session_id, project_id)

        return JSONResponse({
            "success": True,
            "requirements": requirements
        })


@router.post("/chat/reset")
async def reset_chat(session_id: str = "default"):
    """Reset chat session without extracting requirements."""
    from ...agents import get_chat_session_store
    from ...project_manager import get_project_manager

    session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        in_memory_cleared = chat_sessions.pop(session_key, None) is not None
        persisted_cleared = store.delete(session_id, project_id)
        _clear_active_workflow(session_key)
        _delete_workflow_snapshot(session_id)

    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "cleared": bool(in_memory_cleared or persisted_cleared),
    })


@router.post("/user-input")
async def submit_user_input(request: UserInputRequest):
    """提交用户输入（响应Agent的输入请求）"""
    coordinator = get_coordinator()
    if not coordinator:
        raise HTTPException(status_code=500, detail="Coordinator not initialized")
    
    try:
        await coordinator.submit_user_input(request.request_id, request.user_input)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@router.get("/message-bus/stats")
async def get_message_bus_stats():
    """获取消息总线统计"""
    from ...agents.message_bus import get_message_bus
    bus = get_message_bus()
    return JSONResponse(bus.get_stats())


@router.get("/message-bus/dead-letters")
async def get_dead_letters():
    """获取死信队列"""
    from ...agents.message_bus import get_message_bus
    bus = get_message_bus()
    dead_letters = bus.get_dead_letters()
    return JSONResponse({
        "count": len(dead_letters),
        "messages": [msg.to_dict() for msg in dead_letters[:50]]
    })
