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
from ...agents.visible_text import strip_visible_technical_markers
from ...route_targets import get_default_intent_route_target
from ...workflow.user_interruptions import apply_interruption
from ...workflow.runtime_messages import make_runtime_message

logger = logging.getLogger(__name__)

router = APIRouter()

def _target_agent_for_intent(intent_name: str) -> str:
    target = get_default_intent_route_target(intent_name)
    return str(getattr(target, "id", "") or "Communicator").strip() or "Communicator"


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


def _normalize_project_chapters_for_chat(pm: Any) -> List[Dict[str, Any]]:
    """Load saved project chapters for lightweight chat answers."""
    if pm is None:
        return []
    try:
        payload = pm.load_project_data("chapters")
    except Exception as exc:
        logger.debug(f"[Chat] load project chapters for direct answer failed: {exc}")
        return []
    if isinstance(payload, dict):
        rows = payload.get("chapters")
    else:
        rows = payload
    if not isinstance(rows, list):
        return []

    chapters: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        content = str(row.get("content") or "").strip()
        summary = str(row.get("summary") or row.get("description") or "").strip()
        title = str(row.get("title") or row.get("name") or "").strip()
        if source == "chapter_settings" and not content:
            continue
        if not (title or content or summary):
            continue
        try:
            chapter_number = int(row.get("chapter_number") or row.get("number") or row.get("chapter") or index)
        except (TypeError, ValueError):
            chapter_number = index
        if chapter_number <= 0:
            chapter_number = index
        chapters.append({
            "chapter_number": chapter_number,
            "title": title or f"第{chapter_number}章",
            "content": content,
            "summary": summary,
            "word_count": int(row.get("word_count") or len(re.sub(r"\s+", "", content)) or 0),
        })
    return sorted(chapters, key=lambda item: item["chapter_number"])


def _project_chapter_chat_payload(pm: Any, message: str) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip()
    if not text or text.startswith("/"):
        return None
    compact = re.sub(r"\s+", "", text)
    asks_count = any(token in compact for token in ("几章", "多少章", "有几章", "章节列表", "有哪些章节"))
    asks_current = any(token in compact for token in ("现在第几章", "当前第几章", "目前第几章", "现在有几章", "目前有几章"))
    chapter_match = re.search(r"第\s*(\d+)\s*章", text)
    asks_specific = bool(chapter_match and any(token in compact for token in ("内容", "正文", "写了什么", "看看", "检查", "保存了没", "有没有")))
    if not (asks_count or asks_current or asks_specific):
        return None
    if chapter_match and any(token in compact for token in ("写第", "生成第", "创作第", "续写第", "润色第")) and not asks_specific:
        return None

    chapters = _normalize_project_chapters_for_chat(pm)
    routing = {
        "intent": "query_project_chapters",
        "target_agent": "ProjectChapters",
        "display": "正文章节",
        "confidence": 1.0,
    }
    if not chapters:
        return {
            "reply": "当前项目还没有保存的正文章节。左侧如果显示了章节标题，请先打开章节并确认正文已保存。",
            "is_complete": False,
            "routed": True,
            "routing": routing,
            "project_chapters": {"total": 0, "written": 0, "chapters": []},
        }

    if asks_specific and chapter_match:
        target_number = int(chapter_match.group(1))
        chapter = next((item for item in chapters if item["chapter_number"] == target_number), None)
        if not chapter:
            available = "、".join(f"第{item['chapter_number']}章" for item in chapters[:12])
            return {
                "reply": f"当前项目没有找到第{target_number}章。已保存章节：{available}。",
                "is_complete": False,
                "routed": True,
                "routing": routing,
                "project_chapters": {"total": len(chapters), "written": sum(1 for item in chapters if item["content"]), "chapters": chapters},
            }
        body = chapter["content"] or chapter["summary"] or "这一章目前只有标题，还没有保存正文内容。"
        if len(body) > 1200:
            body = body[:1200].rstrip() + "..."
        reply = f"找到了第{chapter['chapter_number']}章《{chapter['title']}》。\n\n{body}"
        return {
            "reply": reply,
            "is_complete": False,
            "routed": True,
            "routing": routing,
            "project_chapters": {"total": len(chapters), "written": sum(1 for item in chapters if item["content"]), "chapters": chapters},
        }

    written = sum(1 for item in chapters if item["content"])
    lines = [f"- 第{item['chapter_number']}章《{item['title']}》" + ("（有正文）" if item["content"] else "（仅标题/摘要）") for item in chapters[:20]]
    more = "\n..." if len(chapters) > 20 else ""
    reply = f"当前项目已保存 {len(chapters)} 章，其中 {written} 章有正文内容。\n" + "\n".join(lines) + more
    return {
        "reply": reply,
        "is_complete": False,
        "routed": True,
        "routing": routing,
        "project_chapters": {"total": len(chapters), "written": written, "chapters": chapters},
    }

# 存储对话会话（内存热缓存）
chat_sessions = {}
_chat_session_locks = {}
_chat_locks_guard = asyncio.Lock()
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ACTIVE_WORKFLOW_RUNS: Dict[str, Dict[str, Any]] = {}
_ROUTER_EXECUTION_INTENTS = {
    "create_novel",
    "create_character",
    "create_eventlines",
    "create_detail_outline",
    "create_chapter_settings",
    "create_project_data",
    "continue_write",
    "polish_content",
    "search_web",
    "search_trends",
}
_ROUTER_COMMAND_NAMES: set[str] = set()
_WORKFLOW_CONTROL_COMMAND_NAMES: set[str] = {"status", "pause", "resume", "cancel"}
_CONTRACT_RESUME_STOP_REASONS: set[str] = {
    "review_required",
    "chapter_settings_review_required",
    "max_tasks_reached",
    "max_chapter_tasks_reached",
}
_CONTRACT_RESUME_CONFIRMATION_MARKERS = (
    "继续",
    "继续创作",
    "继续正文",
    "继续生成",
    "开始创作",
    "开始正文",
    "开始写",
    "写正文",
    "生成正文",
    "创作正文",
    "写第一章",
    "创作第一章",
    "生成第一章",
    "写第1章",
    "创作第1章",
    "生成第1章",
    "写吧",
    "可以写",
    "确认",
    "同意",
    "通过",
    "批准",
)
_CONTRACT_RESUME_SHORT_CONFIRMATIONS = {
    "创作",
    "继续",
    "开始",
    "写",
    "写吧",
    "可以",
    "可以了",
    "好",
    "好的",
    "行",
    "行吧",
    "确认",
    "同意",
    "通过",
}
_CONTRACT_RESUME_NEGATION_MARKERS = (
    "不",
    "别",
    "不要",
    "先别",
    "暂停",
    "停止",
    "取消",
    "修改",
    "调整",
    "重写",
    "等等",
)
CHAT_AUTO_SAVE_STATE_KEY = "copilot_chat_auto_save"
CHAT_CREATIVE_MODE_STATE_KEY = "copilot_creative_mode"
CHAT_CREATIVE_MODES = {"auto", "discussion", "plan", "execute"}
CHAT_PLAN_ROUTER_INTENTS = {"create_novel", "create_character"}
KNOWLEDGE_CATEGORIES_STATE_KEY = "knowledge_categories"
BUILTIN_KNOWLEDGE_CATEGORIES = [
    {"id": "db-outline-main", "key": "outline", "name": "大纲", "builtin": True, "aliases": ["故事大纲", "章节大纲", "总纲"]},
    {"id": "db-char", "key": "characters", "name": "角色档案", "builtin": True, "aliases": ["角色卡", "人设卡", "人物卡", "人物档案", "角色设定", "人物设定"]},
    {"id": "db-world", "key": "worldbuilding", "name": "世界观设定", "builtin": True, "aliases": ["世界观", "世界设定", "世界设定集"]},
    {"id": "db-item", "key": "items", "name": "道具物品", "builtin": True, "aliases": ["道具", "物品", "装备", "法宝", "线索物"]},
    {"id": "db-event", "key": "eventlines", "name": "事件线", "builtin": True, "aliases": ["剧情线", "主线", "支线", "事件链"]},
    {"id": "db-detail", "key": "detail_settings", "name": "细纲设定", "builtin": True, "aliases": ["细纲", "详细大纲", "分场细纲"]},
    {"id": "db-chapter", "key": "chapter_settings", "name": "章纲设定", "builtin": True, "aliases": ["章纲", "章节设定", "章节规划"]},
    {"id": "db-chsummary", "key": "chapter_summary", "name": "正文摘要", "builtin": True, "aliases": ["章节摘要", "正文总结", "剧情摘要"]},
    {"id": "db-chapters", "key": "chapters", "name": "正文章节", "builtin": True, "aliases": ["正文", "章节正文", "章节"]},
]
PROJECT_DATA_ACTION_KEYWORDS = (
    "生成", "创建", "新建", "建立", "写", "设计", "整理", "梳理", "补全", "完善",
    "修改", "更新", "改写", "扩写", "追加", "添加", "加入", "保存", "同步", "写入",
    "补出来", "补一下", "做出来",
)
AUTO_EXECUTION_CONFIDENCE_FLOOR = 0.72
DISCUSSION_OR_PLANNING_MARKERS = (
    "先讨论", "先聊", "聊聊", "讨论一下", "先看看", "看看", "评估", "分析",
    "建议", "推荐", "灵感", "想法", "思路", "还有什么", "其他设定",
    "觉得", "怎么", "如何", "要不要", "是否", "能不能", "可不可以",
    "可以吗", "行不行", "合适吗", "有必要吗", "方案", "计划", "步骤", "流程",
    "路线", "下一步", "先别保存", "不要保存", "别落库", "不要落库", "别写入",
    "先别存档", "不要存档", "别存档", "先别入库", "不要入库", "别入库",
    "这句话", "这句", "换一句", "换掉", "其他不改", "其余不改", "刚才", "上一条",
)
SOFT_CREATIVE_ENRICHMENT_MARKERS = (
    "丰富一下", "丰富", "细化一下", "继续细化", "细化", "展开一下",
    "扩展一下", "扩展", "拓展一下", "拓展", "根据这个设定",
    "基于这个设定", "在这个设定上", "帮我想想", "帮我想",
    "补充一点", "补充一下", "完善一下",
)
SOFT_CREATIVE_TARGET_MARKERS = (
    "主角", "角色", "人物", "人设", "角色设定", "人物设定",
    "世界观", "世界设定", "设定",
)
HARD_CREATIVE_EXECUTION_MARKERS = (
    "直接生成", "直接创建", "直接写", "开始创作", "开始写", "开始正文",
    "生成", "创建", "新建", "建立", "写入资料库", "保存到资料库",
    "同步到资料库", "加入资料库", "存到资料库", "落库", "入库",
    "执行", "续写", "继续写", "写正文", "生成正文",
)
CONTINUE_WRITE_ACTION_MARKERS = (
    "续写", "继续写", "接着写", "往下写", "下一章", "继续正文", "继续创作",
    "写第", "创作第", "生成第",
)
POLISH_ACTION_MARKERS = (
    "润色", "改写", "优化这段", "修改这段", "调整文风", "修一下", "重写这段",
)
PROJECT_DATA_OBJECT_MARKERS = (
    "事件线", "剧情线", "故事线", "主线", "支线", "细纲", "详细大纲", "章纲",
    "章节设定", "章节规划", "资料库", "世界观", "角色卡", "人设卡", "大纲",
)
_EXPLICIT_COMMAND_DEFINITIONS: Dict[str, Dict[str, Any]] = {}

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


_USER_VISIBLE_AGENT_NAME_REPLACEMENTS = {
    "Worldbuilder那边": "后续世界观设定流程这边",
    "WorldBuilder那边": "后续世界观设定流程这边",
    "WorldbuilderAgent": "世界观构建师",
    "WorldBuilderAgent": "世界观构建师",
    "Worldbuilder": "世界观构建师",
    "WorldBuilder": "世界观构建师",
    "OutlinerAgent": "大纲规划师",
    "Outliner": "大纲规划师",
    "ChapterWriter": "章节写作助手",
    "Communicator": "沟通助手",
    "Coordinator": "创作协调器",
    "Router": "智能路由",
    "CharacterBuilder": "角色构建师",
    "EventlineBuilder": "事件线构建师",
    "DetailOutlineBuilder": "细纲构建师",
    "ChapterSettingBuilder": "章纲构建师",
    "ContinuousWriter": "续写助手",
    "Polisher": "润色助手",
    "Evaluator": "质量评估师",
    "SummaryOrchestrator": "摘要编排助手",
    "ContextStrategy": "上下文策略助手",
    "ContentReader": "内容读取助手",
    "ContentExpansion": "内容扩展助手",
    "FileNaming": "文件命名助手",
    "WebSearch": "网络搜索助手",
    "TrendsSearch": "热点搜索助手",
}


def _localize_user_visible_agent_names(text: Any) -> str:
    """将用户可见文本中的内部 Agent 代号替换成自然中文显示。"""
    value = str(text or "")
    if not value:
        return ""
    for old, new in _USER_VISIBLE_AGENT_NAME_REPLACEMENTS.items():
        value = value.replace(old, new)
    value = value.replace("后续世界观设定流程这边能", "后续世界观设定会")
    value = value.replace("世界观构建师那边", "后续世界观设定流程这边")
    value = value.replace("大纲规划师那边", "后续大纲规划流程这边")
    value = value.replace("候选 Agent", "候选创作助手")
    value = value.replace("多Agent", "多助手")
    value = value.replace("子Agent", "子助手")
    return value


def _strip_visible_technical_markers(text: Any) -> str:
    """移除技术标记，并从JSON格式中提取reply字段"""
    return strip_visible_technical_markers(text, _localize_user_visible_agent_names)


def _is_internal_stream_progress(update: Any) -> bool:
    if not isinstance(update, dict):
        return False
    event_type = str(update.get("type") or "").strip()
    return event_type in {
        "llm_chunk",
        "tool_call",
        "tool_result",
        "agent_task_progress",
        "agent_task_completed",
        "agent_task_failed",
    }


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
    model_label = str(
        payload.get("current_model")
        or payload.get("model")
        or payload.get("active_model")
        or payload.get("model_used")
        or payload.get("last_model")
        or ""
    ).strip()
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
        "model": model_label,
        "current_model": model_label,
        "active_model": model_label,
        "model_used": model_label,
        "started_at": str(payload.get("started_at") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
        "created_files": _merge_file_entries([], payload.get("created_files"), default_status="created"),
        "updated_files": _merge_file_entries([], payload.get("updated_files"), default_status="updated"),
        "reused_files": _merge_file_entries([], payload.get("reused_files"), default_status="reused"),
        "creative_workflow": payload.get("creative_workflow") if isinstance(payload.get("creative_workflow"), dict) else None,
        "workflow_plan": payload.get("workflow_plan") if isinstance(payload.get("workflow_plan"), dict) else {},
        "task_queue": payload.get("task_queue") if isinstance(payload.get("task_queue"), list) else [],
        "completed_tasks": payload.get("completed_tasks") if isinstance(payload.get("completed_tasks"), list) else [],
        "reviews": payload.get("reviews") if isinstance(payload.get("reviews"), list) else [],
        "handoff_notes": payload.get("handoff_notes") if isinstance(payload.get("handoff_notes"), list) else [],
        "user_interruptions": payload.get("user_interruptions") if isinstance(payload.get("user_interruptions"), list) else [],
        "stop_reason": str(payload.get("stop_reason") or "").strip(),
        "stopped_on_task_type": str(payload.get("stopped_on_task_type") or "").strip(),
        "awaiting_user_review": bool(payload.get("awaiting_user_review", False)),
        "resume_endpoint": str(payload.get("resume_endpoint") or "").strip(),
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

    content = ""
    if not _is_internal_stream_progress(update_payload):
        content = _strip_visible_technical_markers(update_payload.get("content") or update_payload.get("message") or "")
    if content:
        active_run["last_progress"] = content
    for field in ("status", "target_agent", "current_agent", "stage", "output_dir", "last_error", "command", "run_id", "focus_module", "model", "current_model", "active_model", "model_used", "last_model", "stop_reason", "stopped_on_task_type", "resume_endpoint"):
        value = update_payload.get(field)
        if value not in (None, ""):
            active_run[field] = str(value).strip()
    if "awaiting_user_review" in update_payload:
        active_run["awaiting_user_review"] = bool(update_payload.get("awaiting_user_review"))
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
    for field in ("creative_workflow", "workflow_plan"):
        value = update_payload.get(field)
        if isinstance(value, dict):
            active_run[field] = value
    for field in ("task_queue", "completed_tasks", "reviews", "handoff_notes", "user_interruptions"):
        value = update_payload.get(field)
        if isinstance(value, list):
            active_run[field] = value

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
        routed_model = _resolve_agent_effective_model(routed_to, _extract_model_label(router_result))
        if routed_model:
            active_run["model"] = routed_model
            active_run["current_model"] = routed_model
            active_run["active_model"] = routed_model
            active_run["model_used"] = routed_model
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
    delegated_params = delegated_result.get("params") if isinstance(delegated_result.get("params"), dict) else {}
    creative_workflow = delegated_params.get("creative_workflow_run")
    if isinstance(creative_workflow, dict):
        active_run["creative_workflow"] = creative_workflow
        workflow_plan = creative_workflow.get("workflow_plan")
        if isinstance(workflow_plan, dict):
            active_run["workflow_plan"] = workflow_plan
        for field in ("task_queue", "completed_tasks", "reviews", "handoff_notes"):
            value = creative_workflow.get(field)
            if isinstance(value, list):
                active_run[field] = value
        interruptions = creative_workflow.get("user_interruptions")
        if isinstance(interruptions, list):
            active_run["user_interruptions"] = interruptions

    stop_reason = _project_ready_stop_reason_from_delegated(delegated_result)
    if stop_reason:
        active_run["stop_reason"] = stop_reason
    stopped_on_task_type = str(delegated_params.get("stopped_on_task_type") or "").strip()
    if not stopped_on_task_type:
        project_ready_task_execution = (
            delegated_params.get("project_ready_task_execution")
            if isinstance(delegated_params.get("project_ready_task_execution"), dict)
            else {}
        )
        project_ready_execution = (
            project_ready_task_execution.get("project_ready_execution")
            if isinstance(project_ready_task_execution.get("project_ready_execution"), dict)
            else project_ready_task_execution
        )
        stopped_on_task_type = str(project_ready_execution.get("stopped_on_task_type") or "").strip()
    if stopped_on_task_type:
        active_run["stopped_on_task_type"] = stopped_on_task_type
    if delegated_result.get("resume_endpoint"):
        active_run["resume_endpoint"] = str(delegated_result.get("resume_endpoint") or "").strip()
    elif stop_reason in {"review_required", "chapter_settings_review_required"}:
        active_run["resume_endpoint"] = "/api/v1/contract/resume"
    if delegated_params.get("awaiting_user_review") not in (None, ""):
        active_run["awaiting_user_review"] = bool(delegated_params.get("awaiting_user_review"))
    if stop_reason == "task_failed":
        active_run["status"] = "failed"
        active_run["last_error"] = str(delegated_params.get("stopped_on_task_type") or stop_reason).strip()
    elif stop_reason in {"review_required", "chapter_settings_review_required"}:
        active_run["status"] = "needs_confirmation"
        active_run["stage"] = "awaiting_confirmation"
    elif isinstance(router_result, dict) and not router_result.get("success", True):
        active_run["status"] = "failed"
        active_run["last_error"] = str((router_result.get("error") or delegated_result.get("error") or "")).strip()
    elif delegated_result.get("error"):
        active_run["status"] = "failed"
        active_run["last_error"] = str(delegated_result.get("error") or "").strip()
    else:
        active_run["status"] = str(active_run.get("status") or "completed")

    _sync_workflow_snapshot(active_run)
    return _workflow_public_snapshot(active_run)


def _is_workflow_interruption_message(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text) and any(token in text for token in ("不对", "不是", "改成", "修改", "调整", "重写"))


def _copy_creative_workflow_to_active_run(active_run: Dict[str, Any], creative_workflow: Dict[str, Any]) -> None:
    active_run["creative_workflow"] = creative_workflow
    active_run["run_id"] = str(creative_workflow.get("run_id") or active_run.get("run_id") or "").strip()
    active_run["status"] = str(creative_workflow.get("status") or active_run.get("status") or "paused").strip()
    active_run["current_agent"] = str(creative_workflow.get("current_agent") or active_run.get("current_agent") or "Coordinator").strip()
    active_run["stage"] = str(creative_workflow.get("current_stage") or active_run.get("stage") or "user_interruption").strip()
    for field in ("task_queue", "completed_tasks", "reviews", "handoff_notes", "user_interruptions", "created_files", "updated_files", "reused_files"):
        value = creative_workflow.get(field)
        if isinstance(value, list):
            active_run[field] = value
    workflow_plan = creative_workflow.get("workflow_plan")
    if isinstance(workflow_plan, dict):
        active_run["workflow_plan"] = workflow_plan


def _record_workflow_interruption(
    *,
    session_key: str,
    session_id: str,
    message: str,
    coordinator: Any,
) -> Optional[Dict[str, Any]]:
    active_run = _get_workflow_record(session_key, session_id)
    creative_workflow = active_run.get("creative_workflow") if isinstance(active_run, dict) else None
    if not isinstance(active_run, dict) or not isinstance(creative_workflow, dict):
        return None
    workflow_status = str(creative_workflow.get("status") or active_run.get("status") or "").strip()
    if workflow_status in {"failed", "cancelled"}:
        return None
    updated_workflow = apply_interruption(creative_workflow, message)
    if not isinstance(updated_workflow, dict):
        return None
    if coordinator is not None:
        try:
            coordinator.pause()
        except Exception:
            pass
    _copy_creative_workflow_to_active_run(active_run, updated_workflow)
    _apply_workflow_update(active_run, {
        "status": "paused",
        "stage": "user_interruption",
        "current_agent": "Coordinator",
        "content": "已记录用户插入的修改意见，并重新规划受影响任务。",
    })
    workflow = _workflow_public_snapshot(active_run)
    affected = []
    interruptions = updated_workflow.get("user_interruptions") if isinstance(updated_workflow.get("user_interruptions"), list) else []
    if interruptions:
        affected = interruptions[-1].get("affected_categories", []) if isinstance(interruptions[-1], dict) else []
    return {
        "reply": "已记录这条修改意见，并会从受影响的创作阶段继续修订。",
        "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
        "workflow": workflow,
        "resume_workflow": True,
        "affected_categories": affected,
        "handled": True,
    }


def _project_ready_stop_reason_from_delegated(delegated_result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(delegated_result, dict):
        return ""
    params = delegated_result.get("params") if isinstance(delegated_result.get("params"), dict) else {}
    candidates = [
        params,
        params.get("project_ready_execution") if isinstance(params.get("project_ready_execution"), dict) else {},
    ]
    project_ready_task_execution = (
        params.get("project_ready_task_execution")
        if isinstance(params.get("project_ready_task_execution"), dict)
        else {}
    )
    if project_ready_task_execution:
        candidates.append(project_ready_task_execution)
        nested = project_ready_task_execution.get("project_ready_execution")
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        stop_reason = str(candidate.get("stop_reason") or "").strip()
        if stop_reason:
            return stop_reason
    return ""


def _load_project_ready_execution_from_coordinator(coordinator: Any) -> Dict[str, Any]:
    if coordinator is None:
        return {}
    project_manager = getattr(coordinator, "project_manager", None)
    load_state = getattr(project_manager, "load_project_state", None)
    if not callable(load_state):
        return {}
    try:
        task_pool = load_state("task_pool", default={})
    except Exception as exc:
        logger.debug(f"[Chat] load task pool for resume detection failed: {exc}")
        return {}
    if not isinstance(task_pool, dict):
        return {}
    metadata = task_pool.get("metadata") if isinstance(task_pool.get("metadata"), dict) else {}
    execution = metadata.get("project_ready_execution") if isinstance(metadata.get("project_ready_execution"), dict) else {}
    return dict(execution or {})


def _has_contract_resume_checkpoint(coordinator: Any) -> bool:
    execution = _load_project_ready_execution_from_coordinator(coordinator)
    stop_reason = str(execution.get("stop_reason") or "").strip()
    if stop_reason in _CONTRACT_RESUME_STOP_REASONS:
        return True
    stopped_on_task_type = str(execution.get("stopped_on_task_type") or "").strip()
    return stopped_on_task_type in {"chapter_settings", "write_chapter"} and stop_reason in {
        "review_required",
        "chapter_settings_review_required",
    }


def _is_contract_resume_confirmation_message(message: str, coordinator: Any) -> bool:
    if not _has_contract_resume_checkpoint(coordinator):
        return False
    text = str(message or "").strip()
    if not text or text.startswith("/"):
        return False
    normalized = re.sub(r"\s+", "", text.lower())
    if not normalized:
        return False
    if any(marker in normalized for marker in _CONTRACT_RESUME_NEGATION_MARKERS):
        return False
    if normalized in _CONTRACT_RESUME_SHORT_CONFIRMATIONS:
        return True
    return any(marker in normalized for marker in _CONTRACT_RESUME_CONFIRMATION_MARKERS)


def _router_result_terminal_workflow_update(router_result: Optional[Dict[str, Any]]) -> Dict[str, str]:
    delegated_result = (
        router_result.get("delegated_result")
        if isinstance(router_result, dict) and isinstance(router_result.get("delegated_result"), dict)
        else {}
    )
    stop_reason = _project_ready_stop_reason_from_delegated(delegated_result)
    if stop_reason == "task_failed":
        return {"status": "failed", "stage": "failed"}
    if stop_reason in {"review_required", "chapter_settings_review_required"}:
        return {"status": "needs_confirmation", "stage": "awaiting_confirmation"}
    if delegated_result.get("error") or (isinstance(router_result, dict) and not router_result.get("success", True)):
        return {"status": "failed", "stage": "failed"}
    if "is_complete" in delegated_result and not bool(delegated_result.get("is_complete")):
        return {"status": "needs_confirmation", "stage": "awaiting_confirmation"}
    return {"status": "completed", "stage": "completed"}


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
    return None


def _parse_workflow_control_command(message: str) -> str:
    text = str(message or "").strip().lower()
    if not text.startswith("/"):
        return ""
    command = text[1:].split(maxsplit=1)[0].strip()
    return command if command in _WORKFLOW_CONTROL_COMMAND_NAMES else ""


def _normalize_category_match_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _category_aliases(category: Dict[str, Any]) -> List[str]:
    aliases = []
    for value in (
        category.get("name"),
        category.get("key"),
        category.get("id"),
        *(category.get("aliases") or [] if isinstance(category.get("aliases"), list) else []),
    ):
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


def _get_all_project_knowledge_categories() -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {
        str(item["key"]): dict(item) for item in BUILTIN_KNOWLEDGE_CATEGORIES
    }
    for item in _load_project_knowledge_categories():
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        merged[key] = {**merged.get(key, {}), **dict(item)}
    return list(merged.values())


def _message_has_project_data_action(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(keyword in text for keyword in PROJECT_DATA_ACTION_KEYWORDS)


def _extract_target_project_data_category(message: str) -> Optional[Dict[str, Any]]:
    normalized_message = _normalize_category_match_text(message)
    if not normalized_message:
        return None

    matched: Optional[Dict[str, Any]] = None
    matched_len = -1
    builtin_targets = _get_builtin_chat_auto_save_targets()
    for category in _get_all_project_knowledge_categories():
        candidates = [_normalize_category_match_text(alias) for alias in _category_aliases(category)]
        candidates = [candidate for candidate in candidates if candidate]
        if not candidates:
            continue
        if not any(candidate in normalized_message for candidate in candidates):
            continue
        score = max(len(candidate) for candidate in candidates if candidate in normalized_message)
        if score <= matched_len:
            continue
        matched = dict(category)
        key = str(matched.get("key") or "").strip()
        matched["builtin"] = bool(matched.get("builtin")) or key in builtin_targets
        matched_len = score
    return matched


def _project_data_target_agent_for_category(category: Optional[Dict[str, Any]]) -> str:
    key = str((category or {}).get("key") or "").strip()
    return {
        "worldbuilding": "Worldbuilder",
        "characters": "CharacterBuilder",
        "outline": "Outliner",
        "eventlines": "EventlineBuilder",
        "detail_settings": "DetailOutlineBuilder",
        "chapter_settings": "ChapterSettingBuilder",
        "chapters": "ChapterWriter",
    }.get(key, "ProjectDataBuilder")


def _parse_targeted_natural_language_command(message: str) -> Optional[Dict[str, Any]]:
    """Legacy hook kept for callers; natural language routing is LLM-only."""
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
    elif command_name == "character":
        intent_name = "create_character"
        target_agent = "CharacterBuilder"
        confidence = 1.0
    elif command_name == "projectdata":
        intent_name = "create_project_data"
        category = command.get("category") if isinstance(command.get("category"), dict) else {}
        target_agent = _project_data_target_agent_for_category(category)
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


def _is_discussion_or_planning_request(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    if any(marker in text for marker in DISCUSSION_OR_PLANNING_MARKERS):
        return True
    if _is_soft_creative_enrichment_request(text):
        return True
    return "?" in text or "？" in text


def _is_soft_creative_enrichment_request(text: str) -> bool:
    """“丰富/细化设定”通常是在让助手出想法，不应在智能模式下直接落入生成链。"""
    if not any(marker in text for marker in SOFT_CREATIVE_ENRICHMENT_MARKERS):
        return False
    if any(marker in text for marker in HARD_CREATIVE_EXECUTION_MARKERS):
        return False
    return any(marker in text for marker in SOFT_CREATIVE_TARGET_MARKERS)


def _is_conversational_revision_request(message: str) -> bool:
    """用户在改聊天里刚讨论过的一句话，不等同于执行正文润色。"""
    text = str(message or "").strip()
    if not text:
        return False
    revision_markers = ("这句话", "这句", "换一句", "换掉", "其他不改", "其余不改", "上一条", "刚才")
    if not any(marker in text for marker in revision_markers):
        return False
    explicit_artifact_markers = ("第", "章", "正文", "章节正文", "角色档案", "世界观", "大纲", "资料库")
    return not any(marker in text for marker in explicit_artifact_markers)


def _is_explicit_character_save_trigger(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    patterns = (
        "加入资料库", "保存到资料库", "同步到资料库", "存到资料库", "写入资料库",
        "保存这个角色卡", "把角色卡保存", "确认保存角色卡",
    )
    return any(pattern in text for pattern in patterns)


def _is_revision_request(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text) and any(token in text for token in ("修改", "改成", "调整", "修订", "重写", "不是", "不对"))


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


def _is_project_data_generation_trigger(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return (
        any(action in text for action in PROJECT_DATA_ACTION_KEYWORDS)
        and any(marker in text for marker in PROJECT_DATA_OBJECT_MARKERS)
    )


def _target_categories_from_message(message: str, intent_name: str = "") -> List[str]:
    text = str(message or "").strip().lower()
    categories: List[str] = []
    category_extra_aliases = {
        "characters": ("人设", "主角设定", "主角人设", "人物人设"),
        "worldbuilding": ("世界观设定",),
    }
    for category in BUILTIN_KNOWLEDGE_CATEGORIES:
        key = str(category.get("key") or "").strip()
        aliases = [
            str(category.get("name") or "").strip(),
            *[str(item or "").strip() for item in category.get("aliases") or []],
            *category_extra_aliases.get(key, ()),
        ]
        if key and any(alias and alias.lower() in text for alias in aliases):
            categories.append(key)

    intent_defaults = {
        "create_character": "characters",
        "create_eventlines": "eventlines",
        "create_detail_outline": "detail_settings",
        "create_chapter_settings": "chapter_settings",
    }
    default_category = intent_defaults.get(str(intent_name or "").strip())
    if default_category and default_category not in categories:
        categories.append(default_category)
    return categories


def _infer_router_operation(
    intent_name: str,
    message: str,
    explicit_command: Optional[Dict[str, Any]] = None,
) -> str:
    """Separate the creative topic from whether the app may execute side effects."""
    intent = str(intent_name or "").strip()
    text = str(message or "").strip()

    if explicit_command and explicit_command.get("name") in _ROUTER_COMMAND_NAMES:
        return "execute"
    if intent in {"search_web", "search_trends"}:
        return "query"
    if intent in {"continue_write", "polish_content"}:
        return "execute"
    if any(token in text for token in ("保存到资料库", "写入资料库", "同步到资料库", "加入资料库", "存到资料库", "落库", "入库")):
        return "save"
    if _is_revision_request(text):
        return "revise"
    if _is_discussion_or_planning_request(text):
        return "discuss"
    if any(token in text for token in HARD_CREATIVE_EXECUTION_MARKERS):
        return "execute"
    if intent in {
        "create_novel",
        "create_character",
        "create_eventlines",
        "create_detail_outline",
        "create_chapter_settings",
        "create_project_data",
    }:
        return "execute"
    return "discuss"


def _build_router_execution_decision(
    intent_name: str,
    message: str,
    explicit_command: Optional[Dict[str, Any]] = None,
    confidence: float = 1.0,
    creative_mode: str = "auto",
) -> Dict[str, Any]:
    """Deterministic execution gate; works the same with or without local ONNX."""
    intent = str(intent_name or "").strip()
    mode = _normalize_chat_creative_mode(creative_mode)
    try:
        confidence_value = float(confidence or 0.0)
    except (TypeError, ValueError):
        confidence_value = 0.0

    operation = _infer_router_operation(intent, message, explicit_command)
    target_categories = _target_categories_from_message(message, intent)
    side_effect_allowed = operation in {"execute", "save", "revise"}

    execution_allowed = False
    if mode == "discussion":
        side_effect_allowed = False
    elif mode == "plan":
        execution_allowed = intent in CHAT_PLAN_ROUTER_INTENTS
        side_effect_allowed = False
        if execution_allowed:
            operation = "plan"
    elif mode == "execute":
        execution_allowed = intent in _ROUTER_EXECUTION_INTENTS
        side_effect_allowed = execution_allowed and operation != "query"
        if execution_allowed and operation == "discuss":
            operation = "execute"
    elif intent in _ROUTER_EXECUTION_INTENTS and confidence_value >= AUTO_EXECUTION_CONFIDENCE_FLOOR:
        execution_allowed = operation in {"execute", "save", "revise", "query"}
        if operation == "query":
            side_effect_allowed = False

    if explicit_command and explicit_command.get("name") in _ROUTER_COMMAND_NAMES:
        execution_allowed = mode != "discussion"
        if mode == "plan":
            operation = "plan"
            side_effect_allowed = False
        else:
            side_effect_allowed = execution_allowed and operation != "query"

    return {
        "intent": intent,
        "operation": operation,
        "target_categories": target_categories,
        "side_effect_allowed": bool(side_effect_allowed),
        "execution_allowed": bool(execution_allowed),
        "confidence": confidence_value,
        "creative_mode": mode,
    }


def _is_continue_write_trigger(message: str) -> bool:
    text = str(message or "").strip()
    return bool(text) and any(marker in text for marker in CONTINUE_WRITE_ACTION_MARKERS)


def _is_polish_trigger(message: str) -> bool:
    text = str(message or "").strip()
    if not text or _is_conversational_revision_request(text):
        return False
    return any(marker in text for marker in POLISH_ACTION_MARKERS)


def _normalize_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _fallback_creation_requirement_hints(message: str, router_agent: Any = None) -> Dict[str, Any]:
    extractor = getattr(router_agent, "_extract_local_creation_requirement_hints", None)
    if not callable(extractor):
        return {}
    try:
        hints = extractor(message)
    except Exception:
        return {}
    return dict(hints) if isinstance(hints, dict) else {}


def _normalize_creation_requirements(
    collected_info: Optional[Dict[str, Any]],
    message: str,
    router_agent: Any = None,
) -> Dict[str, Any]:
    info = dict(collected_info or {})
    hints = _fallback_creation_requirement_hints(message, router_agent)

    novel_type = str(info.get("novel_type") or "").strip()
    if not novel_type:
        novel_type = str(hints.get("novel_type") or "").strip()
    if not novel_type:
        try:
            from ...project_manager import get_project_manager

            current_project = get_project_manager().get_current_project()
            novel_type = str(getattr(current_project, "novel_type", "") or "").strip()
        except Exception:
            novel_type = ""

    target_word_count = _normalize_positive_int(info.get("target_word_count") or hints.get("target_word_count"), 0)
    target_words_per_chapter = _normalize_positive_int(
        info.get("target_words_per_chapter") or hints.get("target_words_per_chapter"),
        0,
    )
    target_words_per_chapter_source = str(
        info.get("target_words_per_chapter_source")
        or hints.get("target_words_per_chapter_source")
        or ("user" if target_words_per_chapter else "")
    ).strip()
    chapters_per_volume = _normalize_positive_int(info.get("chapters_per_volume") or hints.get("chapters_per_volume"), 5)
    if target_word_count and chapters_per_volume <= 5:
        if target_words_per_chapter:
            chapters_per_volume = max(1, min(80, (target_word_count + target_words_per_chapter - 1) // target_words_per_chapter))
        else:
            chapters_per_volume = max(5, min(80, (target_word_count + 2999) // 3000))
            target_words_per_chapter = max(500, (target_word_count + chapters_per_volume - 1) // chapters_per_volume)
            target_words_per_chapter_source = "estimated"

    plot_idea = str(info.get("plot_idea") or hints.get("plot_idea") or "").strip()

    return {
        "novel_type": novel_type or "",
        "theme": str(info.get("theme") or hints.get("theme") or "").strip(),
        "requirements": str(info.get("requirements") or hints.get("requirements") or "").strip(),
        "protagonist": str(info.get("protagonist") or hints.get("protagonist") or "").strip(),
        "plot_idea": plot_idea,
        "volume_count": _normalize_positive_int(info.get("volume_count"), 1),
        "chapters_per_volume": chapters_per_volume,
        "target_word_count": target_word_count,
        "target_words_per_chapter": target_words_per_chapter,
        "target_words_per_chapter_source": target_words_per_chapter_source,
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


def _normalize_chat_creative_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in CHAT_CREATIVE_MODES else "auto"


def _load_chat_creative_mode(requested_mode: Any = None) -> str:
    mode = _normalize_chat_creative_mode(requested_mode)
    return mode if mode != "auto" else "auto"


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


def _clear_default_empty_project_files_for_plan_mode(pm: Any) -> None:
    """Plan mode may persist a contract draft, but it must not leave content files behind."""
    project_id = str(getattr(pm, "current_project_id", "") or "").strip()
    if not project_id:
        return
    try:
        project_dir = pm._get_project_dir(project_id)
    except Exception as exc:
        logger.debug(f"[Chat] resolve project dir for plan cleanup failed: {exc}")
        return

    for filename in (
        "outline.json",
        "chapters.json",
        "characters.json",
        "worldbuilding.json",
        "items.json",
        "eventlines.json",
        "outline_settings.json",
        "detail_settings.json",
        "chapter_settings.json",
    ):
        path = project_dir / filename
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload == []:
            try:
                path.unlink()
            except Exception as exc:
                logger.debug(f"[Chat] remove empty plan-mode placeholder failed for {path}: {exc}")


def _extract_requested_knowledge_category(message: str) -> Optional[Dict[str, Any]]:
    text = str(message or "").strip().lower()
    if not text:
        return None

    matched: Optional[Dict[str, Any]] = None
    matched_len = -1
    builtin_targets = _get_builtin_chat_auto_save_targets()
    for category in _get_all_project_knowledge_categories():
        key = str(category.get("key") or "").strip()
        candidates = [_normalize_category_match_text(alias) for alias in _category_aliases(category)]
        candidates = [candidate for candidate in candidates if candidate]
        if not candidates:
            continue
        normalized_text = _normalize_category_match_text(text)
        if not any(candidate in normalized_text for candidate in candidates):
            continue
        score = max(len(candidate) for candidate in candidates if candidate in normalized_text)
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
    confidence: float = 1.0,
) -> bool:
    decision = _build_router_execution_decision(
        intent_name=intent_name,
        message=message,
        explicit_command=explicit_command,
        confidence=confidence,
        creative_mode="auto",
    )
    return bool(decision.get("execution_allowed"))


def _downgrade_discussion_routing_hint(
    routing_hint: Optional[Dict[str, Any]],
    processed_message: str,
    targeted_command: Optional[Dict[str, Any]],
    active_model: str,
) -> Optional[Dict[str, Any]]:
    """Route advice/planning phrasing to chat even if the model spots creative keywords."""
    if not isinstance(routing_hint, dict) or not routing_hint:
        return routing_hint
    if targeted_command and targeted_command.get("name") in _ROUTER_COMMAND_NAMES:
        return routing_hint

    intent = str(routing_hint.get("intent") or "").strip()
    if intent not in _ROUTER_EXECUTION_INTENTS:
        return routing_hint
    try:
        previous_confidence = float(routing_hint.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        previous_confidence = 0.0
    decision = _build_router_execution_decision(
        intent_name=intent,
        message=processed_message,
        explicit_command=targeted_command,
        confidence=previous_confidence,
        creative_mode=str(routing_hint.get("creative_mode") or "auto"),
    )
    if decision.get("execution_allowed") or decision.get("operation") != "discuss":
        return routing_hint

    downgraded = dict(routing_hint)
    downgraded["intent"] = "general_chat"
    downgraded["target_agent"] = "Communicator"
    downgraded["fallback_intent"] = intent
    downgraded["confidence"] = max(previous_confidence, 0.9)
    downgraded["execution_decision"] = decision
    downgraded["operation"] = decision.get("operation")
    downgraded["side_effect_allowed"] = False
    if active_model:
        downgraded["model"] = active_model
        downgraded["current_model"] = active_model
        downgraded["active_model"] = active_model
        downgraded["model_used"] = active_model
    return downgraded


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
        "create_project_data",
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
    creative_mode: str = "auto",
) -> Dict[str, Any]:
    collected_info = getattr(agent, "collected_info", {}) or {}
    effective_mode = _normalize_chat_creative_mode(creative_mode)
    context: Dict[str, Any] = {
        "session_id": session_id,
        "collected_info": dict(collected_info),
        "chat_auto_save_enabled": _load_chat_auto_save_enabled(),
        "chat_auto_save_builtin_targets": sorted(_get_builtin_chat_auto_save_targets()),
        "creative_mode": effective_mode,
    }
    history = getattr(agent, "conversation_history", None) or []
    if history:
        context["conversation_history"] = _sanitize_conversation_history(history)

    if isinstance(explicit_command, dict):
        context["explicit_command"] = dict(explicit_command)

    routing_decision = _build_router_execution_decision(
        intent_name=intent_name,
        message=message,
        explicit_command=explicit_command,
        confidence=1.0,
        creative_mode=effective_mode,
    )
    context["routing_decision"] = routing_decision
    context["operation"] = routing_decision.get("operation")
    context["side_effect_allowed"] = routing_decision.get("side_effect_allowed")
    context["intent"] = intent_name

    if intent_name == "create_novel":
        should_auto_execute = bool(routing_decision.get("execution_allowed") and routing_decision.get("side_effect_allowed"))
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
            (routing_decision.get("execution_allowed") and routing_decision.get("side_effect_allowed"))
            or (context.get("chat_auto_save_enabled") and not requires_manual_category_selection)
        )
        if effective_mode in {"discussion", "plan"}:
            should_auto_execute = False
        context["auto_execute"] = should_auto_execute
        context["requires_confirmation"] = False
        context["requested_knowledge_category"] = requested_category
        context["requires_manual_category_selection"] = requires_manual_category_selection
        if requires_manual_category_selection:
            context["character_request_mode"] = "manual_category"
        else:
            context["character_request_mode"] = "save" if (effective_mode == "execute" or is_save_request or context.get("chat_auto_save_enabled")) else "draft"
    elif intent_name in {"create_eventlines", "create_detail_outline", "create_chapter_settings"}:
        context["auto_execute"] = bool(routing_decision.get("execution_allowed") and routing_decision.get("side_effect_allowed"))
        context["requires_confirmation"] = False
    elif intent_name == "create_project_data":
        explicit_category = (
            explicit_command.get("category")
            if isinstance(explicit_command, dict) and isinstance(explicit_command.get("category"), dict)
            else None
        )
        requested_category = explicit_category or _extract_target_project_data_category(message)
        context["auto_execute"] = bool(routing_decision.get("execution_allowed") and routing_decision.get("side_effect_allowed"))
        context["requires_confirmation"] = False
        context["requested_knowledge_category"] = requested_category
    elif intent_name == "continue_write":
        context["auto_execute"] = bool(routing_decision.get("execution_allowed"))

    return context


async def _call_agent_chat(agent: Any, message: str, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call Communicator chat while preserving compatibility with older agent shims."""
    try:
        return await agent.chat(message, runtime_context=runtime_context)
    except TypeError as exc:
        if "runtime_context" not in str(exc):
            raise
        return await agent.chat(message)


async def _iterate_agent_chat_stream(agent: Any, message: str, runtime_context: Optional[Dict[str, Any]] = None):
    try:
        stream = agent.chat_stream(message, runtime_context=runtime_context)
    except TypeError as exc:
        if "runtime_context" not in str(exc):
            raise
        stream = agent.chat_stream(message)
    async for item in stream:
        yield item


def _extract_model_label(router_result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(router_result, dict):
        return ""
    delegated = router_result.get("delegated_result") if isinstance(router_result.get("delegated_result"), dict) else {}
    routing_info = router_result.get("routing_info") if isinstance(router_result.get("routing_info"), dict) else {}
    for bucket in (router_result, delegated, routing_info):
        for key in ("model", "current_model", "model_used", "active_model", "last_model"):
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
    action = str(router_result.get("action") or delegated.get("action") or "").strip()
    routed_to = (
        str(router_result.get("routed_to") or "").strip()
        or str(delegated.get("agent_name") or "").strip()
    )
    if action == "manual_category_selection_required":
        routed_to = "Communicator"
        routing_hint["manual_category_selection_required"] = True
    if routed_to:
        routing_hint["target_agent"] = routed_to

    model_label = _extract_model_label(router_result) or _resolve_agent_effective_model(routed_to, "")
    if model_label:
        routing_hint["model"] = model_label
        routing_hint["current_model"] = model_label
        routing_hint["active_model"] = model_label
        routing_hint["model_used"] = model_label
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
    status_labels = {
        "idle": "空闲",
        "running": "执行中",
        "starting": "准备中",
        "completed": "已完成",
        "needs_confirmation": "待确认",
        "failed": "执行失败",
        "paused": "已暂停",
        "cancelled": "已取消",
        "writing": "写作中",
        "worldbuilding": "世界观构建中",
        "outlining": "大纲生成中",
    }
    status_label = status_labels.get(status, status or "空闲")
    lines = [
        f"当前创作状态：{status_label}",
        f"已完成章节：{completed_chapters}/{total_chapters}" if total_chapters else f"当前章节进度：{current_chapter}",
    ]
    if run_id:
        lines.append(f"运行编号：{run_id}")
    if current_agent:
        lines.append(f"当前执行助手：{_localize_user_visible_agent_names(current_agent)}")
    if stage:
        lines.append(f"当前阶段：{_localize_user_visible_agent_names(stage)}")
    if last_progress:
        lines.extend(["", "最近进度：", _localize_user_visible_agent_names(last_progress.strip())])
    if created_files or updated_files or reused_files:
        lines.extend([
            "",
            f"内容同步情况：新增 {len(created_files)} 项，更新 {len(updated_files)} 项，复用 {len(reused_files)} 项",
        ])
    if last_error:
        lines.extend(["", "最近错误：", _localize_user_visible_agent_names(last_error)])
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
        if _has_contract_resume_checkpoint(coordinator):
            return {
                "reply": "正在继续执行已确认的创作任务池。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "workflow": _workflow_public_snapshot(active_run),
                "resume_contract_flow": True,
                "handled": True,
            }
        if active_run is None and current_state != "paused":
            return {
                "reply": "当前没有处于暂停中的活动创作任务，无法直接恢复。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "handled": True,
            }
        if isinstance(active_run, dict) and isinstance(active_run.get("creative_workflow"), dict):
            workflow_status = str(active_run["creative_workflow"].get("status") or active_run.get("status") or "").strip()
            if workflow_status == "paused":
                coordinator.resume()
                _apply_workflow_update(active_run, {
                    "status": "running",
                    "stage": "resuming",
                    "content": "已恢复串行创作工作流。",
                })
                return {
                    "reply": "已恢复串行创作工作流。",
                    "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                    "workflow": _workflow_public_snapshot(active_run),
                    "resume_workflow": True,
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

    _refresh_runtime_model_configs(agent, router_agent, get_coordinator())
    return agent


def _refresh_runtime_model_configs(agent: Any, router_agent: Any = None, coordinator: Any = None) -> str:
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

    try:
        if coordinator is not None and hasattr(coordinator, "refresh_model_configs"):
            coordinator.refresh_model_configs()
    except Exception as refresh_error:
        logger.debug(f"[Chat] refresh coordinator model configs failed: {refresh_error}")

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
    creative_mode: str = "auto",
) -> Optional[Dict[str, Any]]:
    routing_hint = None
    if targeted_command and targeted_command.get("name") in _ROUTER_COMMAND_NAMES:
        routing_hint = _routing_hint_from_explicit_command(targeted_command, active_model)
    elif router_agent and hasattr(router_agent, "analyze_intent"):
        try:
            intent_analysis = await router_agent.analyze_intent(processed_message)
            intent_name = _extract_intent_name(intent_analysis)
            confidence = float(getattr(intent_analysis, "confidence", 0.0) or 0.0)
            fallback_intent = getattr(intent_analysis, "fallback_intent", None)
            fallback_name = str(getattr(fallback_intent, "value", "") or fallback_intent or "").strip()
            routing_hint = {
                "intent": intent_name,
                "target_agent": _target_agent_for_intent(intent_name),
                "confidence": confidence,
            }
            if fallback_name and fallback_name.lower() != "none":
                routing_hint["fallback_intent"] = fallback_name
            if active_model and routing_hint.get("target_agent") == "Communicator":
                routing_hint["model"] = active_model
        except Exception as analyze_error:
            logger.debug(f"[Chat] intent analysis failed: {analyze_error}")
    if routing_hint:
        routing_hint["creative_mode"] = _normalize_chat_creative_mode(creative_mode)
        decision = _build_router_execution_decision(
            intent_name=str(routing_hint.get("intent") or ""),
            message=processed_message,
            explicit_command=targeted_command,
            confidence=float(routing_hint.get("confidence", 0.0) or 0.0),
            creative_mode=creative_mode,
        )
        routing_hint["operation"] = decision.get("operation")
        routing_hint["target_categories"] = decision.get("target_categories")
        routing_hint["side_effect_allowed"] = decision.get("side_effect_allowed")
        routing_hint["execution_allowed"] = decision.get("execution_allowed")
        routing_hint["execution_decision"] = decision
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

    if _is_workflow_interruption_message(processed_message):
        interrupted = _record_workflow_interruption(
            session_key=session_key,
            session_id=session_id,
            message=processed_message,
            coordinator=coordinator,
        )
        if interrupted:
            return {
                "ok": True,
                "security_reply": "",
                "processed_message": processed_message,
                "targeted_command": None,
                "handled_control": interrupted,
            }

    if _is_contract_resume_confirmation_message(processed_message, coordinator):
        return {
            "ok": True,
            "security_reply": "",
            "processed_message": processed_message,
            "targeted_command": None,
            "handled_control": {
                "reply": "正在继续执行已确认的创作任务池。",
                "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
                "resume_contract_flow": True,
                "handled": True,
            },
        }

    targeted_command = _parse_explicit_command(processed_message)
    workflow_control = _parse_workflow_control_command(processed_message)
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
    model_label = str(hint.get("model") or "").strip()
    if model_label:
        hint.setdefault("current_model", model_label)
        hint.setdefault("active_model", model_label)
        hint.setdefault("model_used", model_label)
    return hint


def _should_execute_router_request(
    router_agent: Any,
    routing_hint: Optional[Dict[str, Any]],
    targeted_command: Optional[Dict[str, Any]],
    processed_message: str,
    agent: Any,
    creative_mode: str = "auto",
) -> bool:
    mode = _normalize_chat_creative_mode(creative_mode)
    intent = str((routing_hint or {}).get("intent") or "").strip()
    if not router_agent or not routing_hint:
        return False
    decision = _build_router_execution_decision(
        intent_name=intent,
        message=processed_message,
        explicit_command=targeted_command,
        confidence=float(routing_hint.get("confidence", 0.0) or 0.0),
        creative_mode=mode,
    )
    routing_hint["operation"] = decision.get("operation")
    routing_hint["target_categories"] = decision.get("target_categories")
    routing_hint["side_effect_allowed"] = decision.get("side_effect_allowed")
    routing_hint["execution_allowed"] = decision.get("execution_allowed")
    routing_hint["execution_decision"] = decision
    return bool(decision.get("execution_allowed"))


def _register_router_workflow_run(
    session_key: str,
    session_id: str,
    project_id: str,
    routing_hint: Dict[str, Any],
    targeted_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    target_agent = str(routing_hint.get("target_agent") or "Coordinator").strip() or "Coordinator"
    model_label = str(routing_hint.get("current_model") or routing_hint.get("model") or "").strip()
    if not model_label:
        model_label = _resolve_agent_effective_model(target_agent)
    return _register_active_workflow(session_key, {
        "status": "running",
        "session_id": session_id,
        "project_id": project_id,
        "last_progress": "",
        "command": str((targeted_command or {}).get("name") or routing_hint.get("intent") or "").strip(),
        "target_agent": target_agent,
        "current_agent": target_agent,
        "stage": "starting",
        "model": model_label,
        "current_model": model_label,
        "active_model": model_label,
        "model_used": model_label,
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
    creative_mode: str = "auto",
) -> tuple[str, Dict[str, Any]]:
    router_message = str((targeted_command or {}).get("message") or processed_message).strip() or processed_message
    router_context = _build_router_context(
        agent=agent,
        session_id=session_id,
        message=router_message,
        intent_name=routing_hint.get("intent", ""),
        router_agent=router_agent,
        explicit_command=targeted_command,
        creative_mode=creative_mode,
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


def _extract_runtime_messages_from_trace(trace: Any, limit: int = 12) -> List[Dict[str, Any]]:
    if not isinstance(trace, dict):
        return []
    messages: List[Dict[str, Any]] = []
    for event in trace.get("events", []) or []:
        if isinstance(event, dict) and isinstance(event.get("runtime_message"), dict):
            messages.append(event["runtime_message"])
    for runtime_event in trace.get("runtime_events", []) or []:
        if not isinstance(runtime_event, dict):
            continue
        payload = runtime_event.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("runtime_message"), dict):
            message = payload["runtime_message"]
            message_id = str(message.get("message_id") or "").strip()
            if not message_id or not any(str(item.get("message_id") or "").strip() == message_id for item in messages):
                messages.append(message)
    return messages[-max(1, int(limit or 12)):]


def _merge_delegated_runtime_payload(target: Dict[str, Any], delegated_result: Optional[Dict[str, Any]]) -> None:
    if not isinstance(target, dict) or not isinstance(delegated_result, dict):
        return
    params = delegated_result.get("params") if isinstance(delegated_result.get("params"), dict) else {}
    for key in ("creation_contract", "task_pool", "collab_execution_trace"):
        value = params.get(key)
        if isinstance(value, dict) and value:
            target[key] = value
            if key == "collab_execution_trace":
                runtime_messages = _extract_runtime_messages_from_trace(value)
                if runtime_messages:
                    target["runtime_messages"] = runtime_messages
                    target["runtime_message"] = runtime_messages[-1]
    project_ready_task_execution = params.get("project_ready_task_execution")
    if isinstance(project_ready_task_execution, dict) and project_ready_task_execution:
        target["project_ready_task_execution"] = project_ready_task_execution
        nested = project_ready_task_execution.get("project_ready_execution")
        target["project_ready_execution"] = nested if isinstance(nested, dict) else project_ready_task_execution
    for key in ("stop_reason", "stopped_on_task_type", "awaiting_user_review"):
        value = params.get(key)
        if value not in (None, "", [], {}):
            target[key] = value


def _process_chat_creative_decision(pm: Any, message: str, creative_mode: str) -> Optional[Dict[str, Any]]:
    """Persist/apply chat-driven creative decisions without breaking chat flow."""
    try:
        if not pm or not getattr(pm, "current_project_id", ""):
            return None
        from ...chat_creative_decisions import process_chat_creative_decision

        return process_chat_creative_decision(pm, message, mode=creative_mode)
    except Exception as exc:
        logger.warning(f"[Chat] 处理聊天创作决策失败: {exc}")
        return None


def _process_assistant_auto_save(
    pm: Any,
    assistant_text: str,
    creative_mode: str,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """Persist assistant-generated project artifacts from direct execution chat replies."""
    try:
        if not pm or not getattr(pm, "current_project_id", ""):
            return None
        from ...chat_auto_save import process_assistant_auto_save

        return process_assistant_auto_save(
            pm,
            assistant_text,
            mode=creative_mode,
            auto_save_enabled=_load_chat_auto_save_enabled(),
            categories=_get_all_project_knowledge_categories(),
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning(f"[Chat] 自动同步助手回复失败: {exc}")
        return None


def _router_result_allows_assistant_auto_save(
    router_result: Optional[Dict[str, Any]],
    delegated_result: Optional[Dict[str, Any]],
    workflow_snapshot: Optional[Dict[str, Any]],
) -> bool:
    """失败或取消的路由执行结果不应触发资料库自动同步。"""
    if isinstance(router_result, dict) and not router_result.get("success", True):
        return False
    if isinstance(delegated_result, dict):
        if _project_ready_stop_reason_from_delegated(delegated_result) == "task_failed":
            return False
        if delegated_result.get("error"):
            return False
        status = str(delegated_result.get("status") or "").strip().lower()
        if status in {"failed", "cancelled"}:
            return False
    if isinstance(workflow_snapshot, dict):
        status = str(workflow_snapshot.get("status") or workflow_snapshot.get("stage") or "").strip().lower()
        if status in {"failed", "cancelled"}:
            return False
    return True


_CREATIVE_DECISION_PLANNING_KINDS = {"creation_contract", "task_pool", "chat_creative_decisions"}
_ROUTED_EXECUTION_SKIP_CREATIVE_DECISION = {
    "continue_write",
    "polish_content",
}
_ROUTED_AGENT_SKIP_CREATIVE_DECISION = {
    "ContinuousWriter",
    "Polisher",
    "PolisherAgent",
}


def _creative_decision_touched_project_content(updated_files: List[Dict[str, Any]]) -> bool:
    for item in updated_files:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind and kind not in _CREATIVE_DECISION_PLANNING_KINDS:
            return True
    return False


def _should_process_creative_decision_after_router(
    routing_hint: Optional[Dict[str, Any]],
    delegated_result: Optional[Dict[str, Any]],
) -> bool:
    intent = str((routing_hint or {}).get("intent") or "").strip()
    if intent in _ROUTED_EXECUTION_SKIP_CREATIVE_DECISION:
        return False
    agent_name = str((delegated_result or {}).get("agent_name") or "").strip()
    if agent_name in _ROUTED_AGENT_SKIP_CREATIVE_DECISION:
        return False
    return True


def _merge_creative_decision_result(result: Dict[str, Any], decision_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach creative decision data to a chat response payload."""
    if not isinstance(decision_result, dict):
        return result
    updated_files = decision_result.get("updated_files") if isinstance(decision_result.get("updated_files"), list) else []
    if updated_files:
        result["updated_files"] = _merge_file_entries(
            result.get("updated_files"),
            updated_files,
            default_status="updated",
        )
    result["creative_decision"] = decision_result.get("decision")
    if decision_result.get("applied") and result.get("reply"):
        if _creative_decision_touched_project_content(updated_files):
            note = "已根据这轮讨论更新创作决策，并同步到相关项目内容。"
        else:
            note = (
                "已根据这轮讨论记录创作决策，并更新创作规划；本次没有创建资料库文件。"
                "如需落到角色、世界观、大纲或章节正文，请切换为执行模式，或明确说“保存到资料库”。"
            )
        result["reply"] = (
            f"{str(result.get('reply') or '').rstrip()}\n\n"
            f"{note}"
        )
    return result


def _merge_assistant_auto_save_result(
    result: Dict[str, Any],
    auto_save_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach assistant reply auto-save data to a chat response payload."""
    if not isinstance(auto_save_result, dict):
        return result

    result["assistant_auto_save"] = auto_save_result
    created_files = auto_save_result.get("created_files") if isinstance(auto_save_result.get("created_files"), list) else []
    updated_files = auto_save_result.get("updated_files") if isinstance(auto_save_result.get("updated_files"), list) else []
    if created_files:
        result["created_files"] = _merge_file_entries(
            result.get("created_files"),
            created_files,
            default_status="created",
        )
    if updated_files:
        result["updated_files"] = _merge_file_entries(
            result.get("updated_files"),
            updated_files,
            default_status="updated",
        )
    if auto_save_result.get("applied") and result.get("reply") and auto_save_result.get("summary"):
        summary = str(auto_save_result.get("summary") or "").strip()
        reply_text = str(result.get("reply") or "").rstrip()
        if summary and summary not in reply_text:
            result["reply"] = f"{reply_text}\n\n{summary}"
    return result


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


async def _resume_creative_workflow_response(
    *,
    session_key: str,
    session_id: str,
    project_id: str,
    store: Any,
    router_agent: Any,
    coordinator: Any,
    active_run: Optional[Dict[str, Any]],
) -> JSONResponse:
    if not router_agent or not hasattr(router_agent, "resume_creative_workflow_run"):
        return JSONResponse({
            "reply": "当前路由器不支持恢复串行创作工作流。",
            "is_complete": False,
            "workflow": _workflow_public_snapshot(active_run),
        })
    if not isinstance(active_run, dict) or not isinstance(active_run.get("creative_workflow"), dict):
        return JSONResponse({
            "reply": "没有找到可恢复的串行创作工作流快照。",
            "is_complete": False,
            "workflow": _workflow_public_snapshot(active_run),
        })
    if coordinator is not None:
        try:
            if _get_coordinator_workflow_state(coordinator, "idle") == "paused":
                coordinator.resume()
        except Exception:
            pass

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        agent = await _ensure_chat_agent(session_key, session_id, project_id, store, router_agent)

    async def capture_progress(update: Any):
        _apply_workflow_update(active_run, update)

    router_context = {
        "progress_callback": capture_progress,
        "run_id": str(active_run.get("run_id") or "").strip(),
    }
    delegated_result = await router_agent.resume_creative_workflow_run(
        active_run["creative_workflow"],
        context=router_context,
    )
    router_result = {
        "success": not bool(delegated_result.get("error")),
        "response": delegated_result.get("response") or "",
        "routed_to": delegated_result.get("agent_name") or "Coordinator",
        "delegated_result": delegated_result,
    }
    workflow_snapshot = _apply_router_result_to_workflow(active_run, router_result)
    if isinstance(active_run, dict) and active_run.get("status") not in {"failed", "cancelled"}:
        _apply_workflow_update(active_run, _router_result_terminal_workflow_update(router_result))
        workflow_snapshot = _workflow_public_snapshot(active_run)

    delegated_result = _merge_router_delegated_info(agent, router_result)
    reply_text = _strip_visible_technical_markers(str(router_result.get("response") or "已恢复串行创作工作流。").strip())
    _append_agent_history(agent, "user", "继续创作")
    _append_agent_history(agent, "assistant", reply_text)
    _persist_chat_session(store, session_id, project_id, agent)
    response_payload = {
        "reply": reply_text,
        "is_complete": bool(delegated_result.get("is_complete", False)),
        "collected_info": getattr(agent, "collected_info", {}) or {},
        "routed": True,
        "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
        "delegated_result": delegated_result,
        "routed_to": router_result.get("routed_to"),
        "workflow": workflow_snapshot,
        "created_files": (workflow_snapshot or {}).get("created_files", []),
        "updated_files": (workflow_snapshot or {}).get("updated_files", []),
        "reused_files": (workflow_snapshot or {}).get("reused_files", []),
        "output_dir": (workflow_snapshot or {}).get("output_dir", ""),
    }
    _merge_delegated_runtime_payload(response_payload, delegated_result)
    return JSONResponse(response_payload)


def _build_contract_resume_reply(executed_count: int, stop_reason: str) -> str:
    if stop_reason == "review_required":
        return f"已续跑 {executed_count} 个任务，仍停在审阅断点。请审阅后再继续。"
    if stop_reason == "chapter_settings_review_required":
        return "章纲设定尚未确认，已暂停正文创作，不会提前创建正文章节文件。"
    if stop_reason in {"max_tasks_reached", "max_chapter_tasks_reached"}:
        return f"已续跑 {executed_count} 个任务，达到本次批量上限。可以继续发送“继续创作”接着写。"
    if stop_reason == "task_failed":
        return f"已续跑 {executed_count} 个任务，最后一个任务失败，请检查任务池状态。"
    if not stop_reason:
        return f"已续跑 {executed_count} 个任务，任务池暂无新的就绪任务。"
    return f"已续跑 {executed_count} 个任务，停止原因：{stop_reason}。"


def _contract_resume_status_from_stop_reason(stop_reason: str) -> str:
    if stop_reason == "task_failed":
        return "failed"
    if stop_reason in _CONTRACT_RESUME_STOP_REASONS:
        return "needs_confirmation"
    return "completed"


def _contract_resume_stage_from_stop_reason(stop_reason: str) -> str:
    if stop_reason == "task_failed":
        return "failed"
    if stop_reason in {"review_required", "chapter_settings_review_required"}:
        return "awaiting_confirmation"
    if stop_reason in {"max_tasks_reached", "max_chapter_tasks_reached"}:
        return "awaiting_continue"
    return "completed"


async def _resume_contract_workflow_response(
    *,
    session_key: str,
    session_id: str,
    project_id: str,
    store: Any,
    coordinator: Any,
    active_run: Optional[Dict[str, Any]],
) -> JSONResponse:
    if coordinator is None:
        return JSONResponse({
            "reply": "当前协调器不可用，无法继续创作任务池。",
            "is_complete": False,
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
        })
    project_manager = getattr(coordinator, "project_manager", None)
    load_state = getattr(project_manager, "load_project_state", None)
    if not callable(load_state):
        return JSONResponse({
            "reply": "当前项目没有可续跑的任务池。",
            "is_complete": False,
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
        })

    contract_payload = load_state("creation_contract", default={})
    existing_pool = load_state("task_pool", default={})
    if not isinstance(contract_payload, dict) or not contract_payload or not isinstance(existing_pool, dict) or not existing_pool.get("tasks"):
        return JSONResponse({
            "reply": "当前项目没有可续跑的创作合同或任务池，请先发起并确认创作合同。",
            "is_complete": False,
            "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
            "workflow": _workflow_public_snapshot(active_run),
        })

    if not isinstance(active_run, dict):
        active_run = _register_active_workflow(session_key, {
            "session_id": session_id,
            "project_id": project_id,
            "command": "contract_resume",
            "target_agent": "Coordinator",
            "current_agent": "Coordinator",
        })
    _apply_workflow_update(active_run, {
        "status": "running",
        "stage": "contract_resume",
        "current_agent": "Coordinator",
        "content": "正在沿用已确认合同和现有任务池继续创作。",
    })

    review_state = load_state("chapter_settings_review", default={})
    approve_review = getattr(coordinator, "approve_chapter_settings_review", None)
    if callable(approve_review):
        try:
            review_state = approve_review()
        except Exception as exc:
            logger.debug(f"[Chat] approve chapter settings review skipped: {exc}")
    elif isinstance(review_state, dict):
        review_state.update({
            "approved": True,
            "approved_at": _now_iso(),
            "status": "approved",
        })
        save_state = getattr(project_manager, "save_project_state", None)
        if callable(save_state):
            save_state("chapter_settings_review", review_state)

    ready_task_result = await coordinator.execute_project_ready_tasks(
        max_tasks=7,
        max_chapter_tasks=2,
    )
    if not isinstance(ready_task_result, dict):
        ready_task_result = {}
    task_pool = ready_task_result.get("task_pool") if isinstance(ready_task_result.get("task_pool"), dict) else existing_pool
    collab_execution_trace = load_state("collab_execution_trace", default={})
    project_ready_execution = ready_task_result.get("project_ready_execution")
    if not isinstance(project_ready_execution, dict):
        project_ready_execution = (
            task_pool.get("metadata", {}).get("project_ready_execution", {})
            if isinstance(task_pool, dict) and isinstance(task_pool.get("metadata"), dict)
            else {}
        )
    if not isinstance(project_ready_execution, dict):
        project_ready_execution = {}
    stop_reason = str(project_ready_execution.get("stop_reason") or ready_task_result.get("stop_reason") or "").strip()
    stopped_on_task_type = str(project_ready_execution.get("stopped_on_task_type") or ready_task_result.get("stopped_on_task_type") or "").strip()
    executed_count = int(project_ready_execution.get("executed_task_count") or ready_task_result.get("executed_task_count") or 0)
    reply_text = _build_contract_resume_reply(executed_count, stop_reason)
    status = _contract_resume_status_from_stop_reason(stop_reason)
    stage = _contract_resume_stage_from_stop_reason(stop_reason)

    _apply_workflow_update(active_run, {
        "status": status,
        "stage": stage,
        "current_agent": "Coordinator",
        "stop_reason": stop_reason,
        "stopped_on_task_type": stopped_on_task_type,
        "awaiting_user_review": stop_reason in {"review_required", "chapter_settings_review_required"},
        "resume_endpoint": "/api/v1/contract/resume" if stop_reason in _CONTRACT_RESUME_STOP_REASONS else "",
        "content": reply_text,
    })
    workflow_snapshot = _workflow_public_snapshot(active_run)
    delegated_result = {
        "agent_name": "Coordinator",
        "action": "contract_resume",
        "response": reply_text,
        "is_complete": status == "completed",
        "params": {
            "creation_contract": contract_payload,
            "task_pool": task_pool,
            "collab_execution_trace": collab_execution_trace,
            "project_ready_task_execution": ready_task_result,
            "project_ready_execution": project_ready_execution,
            "stop_reason": stop_reason,
            "stopped_on_task_type": stopped_on_task_type,
            "awaiting_user_review": stop_reason in {"review_required", "chapter_settings_review_required"},
        },
    }

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        agent = await _ensure_chat_agent(session_key, session_id, project_id, store, None)
        _append_agent_history(agent, "user", "继续创作")
        _append_agent_history(agent, "assistant", reply_text)
        _persist_chat_session(store, session_id, project_id, agent)

    response_payload = {
        "reply": reply_text,
        "is_complete": status == "completed",
        "routed": True,
        "routing": {"intent": "project_manage", "target_agent": "Coordinator", "confidence": 1.0},
        "delegated_result": delegated_result,
        "routed_to": "Coordinator",
        "workflow": workflow_snapshot,
        "created_files": (workflow_snapshot or {}).get("created_files", []),
        "updated_files": (workflow_snapshot or {}).get("updated_files", []),
        "reused_files": (workflow_snapshot or {}).get("reused_files", []),
        "output_dir": (workflow_snapshot or {}).get("output_dir", ""),
    }
    _merge_delegated_runtime_payload(response_payload, delegated_result)
    return JSONResponse(response_payload)


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
        "model": "",
        "current_model": "",
        "active_model": "",
        "model_used": "",
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
    creative_mode = _load_chat_creative_mode(getattr(request, "creative_mode", "auto"))
    chapter_answer = _project_chapter_chat_payload(pm, processed_message)
    if chapter_answer:
        return JSONResponse(chapter_answer)
    try:
        from ...story_memory_actions import handle_story_memory_request

        story_memory_result = await handle_story_memory_request(router_agent, processed_message)
        if story_memory_result:
            return JSONResponse({
                "reply": _strip_visible_technical_markers(str(story_memory_result.get("response") or "")),
                "is_complete": False,
                "routed": True,
                "routing_info": story_memory_result.get("routing_info"),
                "delegated_result": story_memory_result.get("delegated_result"),
                "routed_to": story_memory_result.get("routed_to"),
                "routing": {
                    "intent": "query_knowledge",
                    "target_agent": "StoryMemory",
                    "display": "故事记忆",
                    "confidence": 0.98,
                },
            })
    except Exception as exc:
        logger.warning(f"[Chat] story memory action skipped: {exc}")
    if handled_control:
        if handled_control.get("resume_contract_flow"):
            return await _resume_contract_workflow_response(
                session_key=session_key,
                session_id=session_id,
                project_id=project_id,
                store=store,
                coordinator=coordinator,
                active_run=_get_workflow_record(session_key, session_id),
            )
        if handled_control.get("resume_workflow"):
            return await _resume_creative_workflow_response(
                session_key=session_key,
                session_id=session_id,
                project_id=project_id,
                store=store,
                router_agent=router_agent,
                coordinator=coordinator,
                active_run=_get_workflow_record(session_key, session_id),
            )
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
            creative_mode = _load_chat_creative_mode(getattr(request, "creative_mode", "auto"))
            routing_hint = await _build_chat_routing_hint(
                processed_message=processed_message,
                targeted_command=targeted_command,
                router_agent=router_agent,
                active_model=active_model,
                creative_mode=creative_mode,
            )
            routing_hint = _downgrade_discussion_routing_hint(
                routing_hint,
                processed_message,
                targeted_command,
                active_model,
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
                creative_mode=creative_mode,
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
                    creative_mode=creative_mode,
                )
            else:
                result = await _call_agent_chat(
                    agent,
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

                decision_result = _process_chat_creative_decision(pm, processed_message, creative_mode)
                _merge_creative_decision_result(result, decision_result)
                auto_save_result = _process_assistant_auto_save(
                    pm,
                    str(result.get("reply") or ""),
                    creative_mode,
                    session_id,
                )
                _merge_assistant_auto_save_result(result, auto_save_result)

                _persist_chat_session(store, session_id, project_id, agent)
                return JSONResponse(result)

        router_result = None
        try:
            router_result = await router_agent.route_and_respond(router_message, context=router_context)
        finally:
            _clear_active_workflow(session_key)
        if creative_mode == "plan":
            _clear_default_empty_project_files_for_plan_mode(pm)

        async with lock:
            active_agent = chat_sessions.get(session_key) or agent
            raw_reply_text = str((router_result or {}).get("response") or "抱歉，我暂时无法理解您的需求。").strip()
            reply_text = _strip_visible_technical_markers(raw_reply_text)

            _append_agent_history(active_agent, "user", processed_message)
            _append_agent_history(active_agent, "assistant", reply_text)

            delegated_result = _merge_router_delegated_info(active_agent, router_result or {})
            workflow_snapshot = _apply_router_result_to_workflow(active_run, router_result or {})
            if isinstance(active_run, dict) and active_run.get("status") not in {"failed", "cancelled"}:
                _apply_workflow_update(active_run, _router_result_terminal_workflow_update(router_result or {}))
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
            _merge_delegated_runtime_payload(result, delegated_result)
            if routing_hint:
                result["routing"] = routing_hint
            decision_result = None
            if (
                str(delegated_result.get("action") or "") != "manual_category_selection_required"
                and _should_process_creative_decision_after_router(routing_hint, delegated_result)
            ):
                decision_result = _process_chat_creative_decision(pm, processed_message, creative_mode)
                _merge_creative_decision_result(result, decision_result)
            auto_save_result = None
            if _router_result_allows_assistant_auto_save(router_result or {}, delegated_result, workflow_snapshot):
                auto_save_result = _process_assistant_auto_save(
                    pm,
                    str(result.get("reply") or ""),
                    creative_mode,
                    session_id,
                )
            _merge_assistant_auto_save_result(result, auto_save_result)
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
            if handled_control.get("resume_contract_flow"):
                response = await _resume_contract_workflow_response(
                    session_key=session_key,
                    session_id=session_id,
                    project_id=project_id,
                    store=store,
                    coordinator=coordinator,
                    active_run=_get_workflow_record(session_key, session_id),
                )
                payload = json.loads(response.body.decode("utf-8"))
                if payload.get("reply"):
                    yield f"data: {json.dumps({'type': 'chunk', 'content': payload['reply']}, ensure_ascii=False)}\n\n"
                if payload.get("workflow"):
                    yield f"data: {json.dumps({'type': 'workflow', 'workflow': payload['workflow']}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', **payload}, ensure_ascii=False)}\n\n"
                return
            if handled_control.get("resume_workflow"):
                response = await _resume_creative_workflow_response(
                    session_key=session_key,
                    session_id=session_id,
                    project_id=project_id,
                    store=store,
                    router_agent=router_agent,
                    coordinator=coordinator,
                    active_run=_get_workflow_record(session_key, session_id),
                )
                payload = json.loads(response.body.decode("utf-8"))
                if payload.get("workflow"):
                    yield f"data: {json.dumps({'type': 'workflow', 'workflow': payload['workflow']}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', **payload}, ensure_ascii=False)}\n\n"
                return
            reply = handled_control["reply"]
            yield f"data: {json.dumps({'type': 'chunk', 'content': reply}, ensure_ascii=False)}\n\n"
            if handled_control.get("workflow"):
                yield f"data: {json.dumps({'type': 'workflow', 'workflow': handled_control['workflow']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'reply': reply, 'is_complete': False, 'routing': handled_control['routing'], 'workflow': handled_control.get('workflow')}, ensure_ascii=False)}\n\n"
        return StreamingResponse(control_gen(), media_type="text/event-stream")

    chapter_answer = _project_chapter_chat_payload(pm, processed_message)
    if chapter_answer:
        async def chapter_answer_gen():
            reply = str(chapter_answer.get("reply") or "")
            yield f"data: {json.dumps({'type': 'chunk', 'content': reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', **chapter_answer}, ensure_ascii=False)}\n\n"
        return StreamingResponse(chapter_answer_gen(), media_type="text/event-stream")

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        agent = await _ensure_chat_agent(session_key, session_id, project_id, store, router_agent)
        active_model = _refresh_runtime_model_configs(agent, router_agent)
        creative_mode = _load_chat_creative_mode(getattr(request, "creative_mode", "auto"))
        routing_hint = await _build_chat_routing_hint(
            processed_message=processed_message,
            targeted_command=targeted_command,
            router_agent=router_agent,
            active_model=active_model,
            creative_mode=creative_mode,
        )
        routing_hint = _downgrade_discussion_routing_hint(
            routing_hint,
            processed_message,
            targeted_command,
            active_model,
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
        creative_mode=creative_mode,
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
                _apply_workflow_update(active_run, update)
                workflow_snapshot = _workflow_public_snapshot(active_run)
                if workflow_snapshot:
                    runtime_message = update.get("runtime_message") if isinstance(update, dict) else None
                    if not isinstance(runtime_message, dict):
                        runtime_message = make_runtime_message(
                            role="event",
                            message_type="workflow",
                            content={"workflow": workflow_snapshot},
                            trace_id=str(workflow_snapshot.get("run_id") or "").strip(),
                            agent_name=str(
                                workflow_snapshot.get("current_agent")
                                or workflow_snapshot.get("target_agent")
                                or ""
                            ).strip(),
                            metadata={
                                "stage": str(workflow_snapshot.get("stage") or "").strip(),
                                "status": str(workflow_snapshot.get("status") or "").strip(),
                            },
                        ).to_dict()
                    await queue.put({
                        "type": "workflow",
                        "workflow": workflow_snapshot,
                        "runtime_message": runtime_message,
                    })

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
                        creative_mode=creative_mode,
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
                        chunk_text = _localize_user_visible_agent_names(event.get("content") or "")
                        if chunk_text:
                            full_text += chunk_text
                            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_text}, ensure_ascii=False)}\n\n"
                        continue

                    if event_type == "workflow":
                        workflow_payload = event.get("workflow")
                        if workflow_payload:
                            workflow_event = {"type": "workflow", "workflow": workflow_payload}
                            if isinstance(event.get("runtime_message"), dict):
                                workflow_event["runtime_message"] = event["runtime_message"]
                            yield f"data: {json.dumps(workflow_event, ensure_ascii=False)}\n\n"
                        continue

                    if event_type == "router_done":
                        router_result = event.get("router_result") or {}
                        if creative_mode == "plan":
                            _clear_default_empty_project_files_for_plan_mode(pm)
                        workflow_snapshot = _apply_router_result_to_workflow(active_run, router_result)
                        if isinstance(active_run, dict) and active_run.get("status") not in {"failed", "cancelled"}:
                            _apply_workflow_update(active_run, _router_result_terminal_workflow_update(router_result))
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
                        _merge_delegated_runtime_payload(done_payload, delegated_result)
                        if not isinstance(done_payload.get("runtime_message"), dict) and workflow_snapshot:
                            done_payload["runtime_message"] = make_runtime_message(
                                role="event",
                                message_type="workflow",
                                content={"workflow": workflow_snapshot},
                                trace_id=str((workflow_snapshot or {}).get("run_id") or "").strip(),
                                agent_name=str(
                                    (workflow_snapshot or {}).get("current_agent")
                                    or (workflow_snapshot or {}).get("target_agent")
                                    or ""
                                ).strip(),
                                metadata={
                                    "stage": str((workflow_snapshot or {}).get("stage") or "").strip(),
                                    "status": str((workflow_snapshot or {}).get("status") or "").strip(),
                                },
                            ).to_dict()
                        if _should_process_creative_decision_after_router(routing, delegated_result):
                            decision_result = _process_chat_creative_decision(pm, processed_message, creative_mode)
                            _merge_creative_decision_result(done_payload, decision_result)
                        auto_save_result = None
                        if _router_result_allows_assistant_auto_save(router_result, delegated_result, workflow_snapshot):
                            auto_save_result = _process_assistant_auto_save(
                                pm,
                                str(done_payload.get("reply") or full_text or reply_text or ""),
                                creative_mode,
                                session_id,
                            )
                        _merge_assistant_auto_save_result(done_payload, auto_save_result)
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
                        runtime_message = make_runtime_message(
                            role="system",
                            message_type="error",
                            content={
                                "message": event.get("message", ""),
                                "workflow": workflow_snapshot,
                            },
                            trace_id=str((workflow_snapshot or {}).get("run_id") or "").strip(),
                            agent_name=str((workflow_snapshot or {}).get("current_agent") or "").strip(),
                        ).to_dict()
                        yield f"data: {json.dumps({'type': 'workflow', 'workflow': workflow_snapshot, 'runtime_message': runtime_message}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'error', 'message': event.get('message', ''), 'workflow': workflow_snapshot, 'runtime_message': runtime_message}, ensure_ascii=False)}\n\n"
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
                runtime_message = make_runtime_message(
                    role="system",
                    message_type="error",
                    content={
                        "message": str(e),
                        "workflow": workflow_snapshot,
                    },
                    trace_id=str((workflow_snapshot or {}).get("run_id") or "").strip(),
                    agent_name=str((workflow_snapshot or {}).get("current_agent") or "").strip(),
                ).to_dict()
                yield f"data: {json.dumps({'type': 'workflow', 'workflow': workflow_snapshot, 'runtime_message': runtime_message}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'workflow': workflow_snapshot, 'runtime_message': runtime_message}, ensure_ascii=False)}\n\n"
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
            async for sse_event in _iterate_agent_chat_stream(
                agent,
                processed_message,
                runtime_context={"response_mode": communicator_response_mode},
            ):
                # 在done事件中注入routing
                if '"type": "done"' in sse_event or '"type":"done"' in sse_event:
                    try:
                        data_str = sse_event.split("data: ", 1)[1].rstrip("\n")
                        data = json.loads(data_str)
                        data["routing"] = routing_hint
                        workflow = _workflow_public_snapshot(_get_active_workflow(session_key))
                        if workflow:
                            data["workflow"] = workflow
                        decision_result = _process_chat_creative_decision(pm, processed_message, creative_mode)
                        _merge_creative_decision_result(data, decision_result)
                        auto_save_result = _process_assistant_auto_save(
                            pm,
                            str(data.get("reply") or data.get("content") or ""),
                            creative_mode,
                            session_id,
                        )
                        _merge_assistant_auto_save_result(data, auto_save_result)
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
