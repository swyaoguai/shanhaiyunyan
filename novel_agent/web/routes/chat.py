"""
对话API路由模块

包含聊天会话管理、消息发送、用户输入处理等功能。
"""

import logging
import asyncio
import re
import json
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from ..models.requests import ChatRequest, UserInputRequest
from ..dependencies import get_coordinator, get_router_agent

logger = logging.getLogger(__name__)

router = APIRouter()

INTENT_TARGET_AGENT_MAP = {
    "create_novel": "Coordinator",
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

# 存储对话会话（内存热缓存）
chat_sessions = {}
_chat_session_locks = {}
_chat_locks_guard = asyncio.Lock()
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
        text = content.strip()
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
        _chat_session_locks.pop(session_key, None)

    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "cleared": bool(in_memory_cleared or persisted_cleared),
    })


@router.post("/chat")
async def chat(request: ChatRequest):
    """发送对话消息（增强版：集成智能路由）"""
    from ...agents import CommunicatorAgent, get_chat_session_store, ChatSessionState
    from ...prompts import check_user_input_security, get_security_response
    from ...project_manager import get_project_manager

    session_id = request.session_id
    router_agent = get_router_agent()
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()
    
    # 安全检查
    is_safe, processed_message = check_user_input_security(request.message)
    if not is_safe:
        return JSONResponse({
            "reply": get_security_response(),
            "is_complete": False
        })
    
    lock = await _get_chat_session_lock(session_key)
    async with lock:
        # 获取或创建会话（优先从内存，其次从持久化恢复）
        if session_key not in chat_sessions:
            agent = CommunicatorAgent()

            if router_agent:
                agent.set_router_agent(router_agent)
                if router_agent.knowledge_base:
                    agent.set_knowledge_base(router_agent.knowledge_base)

            saved = store.load(session_id, project_id)
            if saved:
                agent.conversation_history = saved.conversation_history
                agent.collected_info = saved.collected_info
            else:
                await agent.start_conversation()

            chat_sessions[session_key] = agent

        agent = chat_sessions[session_key]
        try:
            # 配置可能在会话期间被用户修改，这里按轮次热刷新，避免继续使用旧模型。
            if hasattr(agent, "refresh_model_config"):
                agent.refresh_model_config()
        except Exception as refresh_error:
            logger.debug(f"[Chat] refresh model config failed: {refresh_error}")

        active_model = ""
        try:
            if hasattr(agent, "_get_model_name"):
                active_model = str(agent._get_model_name() or "").strip()
        except Exception:
            active_model = ""

        routing_hint = None
        if router_agent and hasattr(router_agent, "analyze_intent"):
            try:
                intent_analysis = await router_agent.analyze_intent(processed_message)
                primary_intent = getattr(intent_analysis, "primary_intent", None)
                intent_name = getattr(primary_intent, "value", "") or str(primary_intent or "")
                intent_name = str(intent_name).strip()
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
        
        try:
            result = await agent.chat(processed_message)

            # 将底层报错转成可读提示，避免前端只看到通用兜底文案
            backend_error = str(result.get("error", "") or "").strip()
            fallback_reply = "抱歉，我遇到了一些问题。能重新告诉我你的想法吗？"
            if backend_error and (not result.get("reply") or result.get("reply") == fallback_reply):
                short_error = backend_error[:220]
                result["reply"] = (
                    f"当前请求失败：{short_error}\n\n"
                    "请检查 API Key、模型权限或账号状态。"
                )

            # 保证前端总能拿到后端路由结果，避免显示层猜测
            if routing_hint is None:
                routing_hint = {
                    "intent": "",
                    "target_agent": "Communicator",
                    "confidence": 0.0,
                }
                if active_model:
                    routing_hint["model"] = active_model
            
            if not result.get("reply") and router_agent:
                router_result = await router_agent.route_and_respond(processed_message)
                result["reply"] = router_result.get("response", "抱歉，我暂时无法理解您的需求。")
                result["routed"] = True
                if routing_hint is None:
                    routing_hint = {}
                routed_to = router_result.get("routed_to")
                if routed_to:
                    routing_hint["target_agent"] = routed_to
                    if routed_to != "Communicator":
                        routing_hint.pop("model", None)

            if routing_hint:
                result["routing"] = routing_hint

            # 每轮对话后持久化
            store.save(
                ChatSessionState(
                    session_id=session_id,
                    project_id=project_id,
                    conversation_history=agent.conversation_history,
                    collected_info=agent.collected_info
                )
            )

            return JSONResponse(result)
            
        except Exception as e:
            logger.error(f"[Chat] 处理失败: {e}")
            return JSONResponse({
                "reply": "抱歉，处理您的请求时遇到问题。请稍后重试。",
                "is_complete": False,
                "error": str(e)
            })


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话（SSE）— 实时输出AI回复"""
    from ...agents import CommunicatorAgent, get_chat_session_store, ChatSessionState
    from ...prompts import check_user_input_security, get_security_response
    from ...project_manager import get_project_manager

    session_id = request.session_id
    router_agent = get_router_agent()
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    session_key = f"{project_id}::{session_id}"
    store = get_chat_session_store()

    # 安全检查
    is_safe, processed_message = check_user_input_security(request.message)
    if not is_safe:
        error_reply = get_security_response()
        async def error_gen():
            yield f"data: {json.dumps({'type': 'chunk', 'content': error_reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'reply': error_reply, 'is_complete': False}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    lock = await _get_chat_session_lock(session_key)
    async with lock:
        # 获取或创建会话
        if session_key not in chat_sessions:
            agent = CommunicatorAgent()
            if router_agent:
                agent.set_router_agent(router_agent)
                if router_agent.knowledge_base:
                    agent.set_knowledge_base(router_agent.knowledge_base)

            saved = store.load(session_id, project_id)
            if saved:
                agent.conversation_history = saved.conversation_history
                agent.collected_info = saved.collected_info
            else:
                await agent.start_conversation()

            chat_sessions[session_key] = agent

        agent = chat_sessions[session_key]
        try:
            if hasattr(agent, "refresh_model_config"):
                agent.refresh_model_config()
        except Exception:
            pass

        # 路由分析
        active_model = ""
        try:
            if hasattr(agent, "_get_model_name"):
                active_model = str(agent._get_model_name() or "").strip()
        except Exception:
            pass

        routing_hint = None
        if router_agent and hasattr(router_agent, "analyze_intent"):
            try:
                intent_analysis = await router_agent.analyze_intent(processed_message)
                primary_intent = getattr(intent_analysis, "primary_intent", None)
                intent_name = str(getattr(primary_intent, "value", "") or str(primary_intent or "")).strip()
                confidence = float(getattr(intent_analysis, "confidence", 0.0) or 0.0)
                routing_hint = {
                    "intent": intent_name,
                    "target_agent": INTENT_TARGET_AGENT_MAP.get(intent_name, "Communicator"),
                    "confidence": confidence,
                }
                if active_model and routing_hint.get("target_agent") == "Communicator":
                    routing_hint["model"] = active_model
            except Exception:
                pass

        if routing_hint is None:
            routing_hint = {"intent": "", "target_agent": "Communicator", "confidence": 0.0}
            if active_model:
                routing_hint["model"] = active_model

    # 流式生成器（锁已释放）
    async def generate():
        try:
            async for sse_event in agent.chat_stream(processed_message):
                # 在done事件中注入routing
                if '"type": "done"' in sse_event or '"type":"done"' in sse_event:
                    try:
                        data_str = sse_event.split("data: ", 1)[1].rstrip("\n")
                        data = json.loads(data_str)
                        data["routing"] = routing_hint
                        sse_event = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass
                yield sse_event

            # 持久化会话
            store.save(
                ChatSessionState(
                    session_id=session_id,
                    project_id=project_id,
                    conversation_history=agent.conversation_history,
                    collected_info=agent.collected_info
                )
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
                if router_agent.knowledge_base:
                    agent.set_knowledge_base(router_agent.knowledge_base)
            agent.conversation_history = saved.conversation_history
            agent.collected_info = saved.collected_info
            chat_sessions[session_key] = agent

        agent = chat_sessions[session_key]
        requirements = await agent.get_structured_requirements()

        del chat_sessions[session_key]
        _chat_session_locks.pop(session_key, None)
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
        _chat_session_locks.pop(session_key, None)
        persisted_cleared = store.delete(session_id, project_id)

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
