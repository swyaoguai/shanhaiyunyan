import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from novel_agent.agents.router_agent import RouterAgent, UserIntent, IntentAnalysis
from novel_agent.workflow.coordinator import NovelCoordinator, NovelProject, WorkflowState
from novel_agent.project_manager import ProjectManager
from novel_agent.web.routes import projects as project_routes
from novel_agent.web.models.requests import ChatRequest
from novel_agent.web.routes import chat as chat_routes


class _FakeChatStore:
    def __init__(self):
        self.saved_states = []

    def load(self, session_id, project_id):
        return None

    def save(self, state):
        self.saved_states.append(state)

    def delete(self, session_id, project_id):
        return True


class _PersistentChatStore(_FakeChatStore):
    def __init__(self):
        super().__init__()
        self._states = {}

    def load(self, session_id, project_id):
        return self._states.get((project_id, session_id))

    def save(self, state):
        self.saved_states.append(state)
        self._states[(state.project_id, state.session_id)] = state
        return True

    def delete(self, session_id, project_id):
        self._states.pop((project_id, session_id), None)
        return True


class _FakeProjectManager:
    current_project_id = "proj-test"


class _FakeCommunicatorAgent:
    chat_calls = 0

    def __init__(self):
        self.conversation_history = []
        self.collected_info = {
            "novel_type": "玄幻",
            "theme": "复仇成长",
            "protagonist": "林渡，少年剑修",
            "plot_idea": "宗门覆灭后复仇并重建秩序",
            "volume_count": 1,
            "chapters_per_volume": 5,
        }
        self.model_config = SimpleNamespace(
            model="gpt-4o-mini",
            api_base="https://initial.example/v1",
            api_key="initial-key",
            temperature=0.7,
            max_tokens=2048,
            use_global=True,
        )
        self.refresh_calls = 0

    def set_router_agent(self, router_agent):
        self.router_agent = router_agent

    def set_knowledge_base(self, knowledge_base):
        self.knowledge_base = knowledge_base

    def refresh_model_config(self):
        self.refresh_calls += 1
        self.model_config = SimpleNamespace(
            model="glm-4.6",
            api_base="https://updated.example/v1",
            api_key="updated-key",
            temperature=0.6,
            max_tokens=4096,
            use_global=True,
        )
        return True

    def _get_model_name(self):
        return self.model_config.model

    async def start_conversation(self):
        self.conversation_history.append({"role": "assistant", "content": "opening"})
        return "opening"

    async def chat(self, user_message):
        type(self).chat_calls += 1
        return {
            "reply": "communicator fallback",
            "is_complete": False,
            "collected_info": self.collected_info,
        }


class _FakeStreamingCommunicatorAgent(_FakeCommunicatorAgent):
    async def chat_stream(self, user_message, runtime_context=None):
        yield f"data: {json.dumps({'type': 'chunk', 'content': 'stream chunk'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'reply': 'stream done', 'is_complete': False}, ensure_ascii=False)}\n\n"


class _FakeRouterWithDynamicModel:
    def __init__(self):
        self.knowledge_base = None
        self.refresh_calls = 0
        self.conversation_history = []
        self.model_config = SimpleNamespace(
            model="gpt-5.4",
            api_base="https://router.initial/v1",
            api_key="router-initial-key",
            temperature=0.1,
            max_tokens=8192,
            use_global=True,
        )

    def refresh_model_config(self):
        self.refresh_calls += 1
        self.model_config = SimpleNamespace(
            model="glm-4.6",
            api_base="https://router.updated/v1",
            api_key="router-updated-key",
            temperature=0.2,
            max_tokens=8192,
            use_global=True,
        )
        return True

    def _get_model_name(self):
        return self.model_config.model

    def set_knowledge_base(self, knowledge_base):
        self.knowledge_base = knowledge_base

    async def route_and_respond(self, message, context=None):
        return {
            "response": "router reply",
            "routed_to": "Communicator",
            "delegated_result": {
                "agent_name": "Communicator",
                "action": "chat",
                "response": "router reply",
            },
            "routing_info": {"steps": []},
        }


class _SlowCommunicatorAgent(_FakeCommunicatorAgent):
    start_calls = 0
    chat_calls = 0

    async def start_conversation(self):
        type(self).start_calls += 1
        await asyncio.sleep(0.01)
        self.conversation_history.append({"role": "assistant", "content": "opening"})
        return "opening"

    async def chat(self, user_message, runtime_context=None):
        type(self).chat_calls += 1
        await asyncio.sleep(0.01)
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": f"echo:{user_message}"})
        return {
            "reply": f"echo:{user_message}",
            "is_complete": False,
            "collected_info": self.collected_info,
        }


class _FakeContinuousWriter:
    def __init__(self):
        self.session_id = ""
        self.project_id = ""
        self.session_loaded = False
        self.executed = []

    def set_session_id(self, session_id, project_id=""):
        self.session_id = session_id
        self.project_id = project_id

    def _load_or_create_session(self):
        self.session_loaded = True
        return object()

    async def execute(self, input_data, context=None):
        self.executed.append((input_data, context))
        return {
            "success": True,
            "chapter": {
                "chapter_number": 3,
                "content": "这是续写助手真正写出的下一章正文。",
            },
        }


class _FakePolisher:
    def __init__(self):
        self.executed = []

    async def execute(self, input_data, context=None):
        self.executed.append((input_data, context))
        return {
            "success": True,
            "content": "这是润色助手真正输出的润色结果。",
        }


class _FakeRouter:
    def __init__(self):
        self.last_context = None

    async def analyze_intent(self, message):
        return SimpleNamespace(
            primary_intent=SimpleNamespace(value="create_novel"),
            confidence=0.95,
        )

    async def route_and_respond(self, message, context=None):
        self.last_context = context or {}
        return {
            "response": "已切换到创作协调器并开始执行。",
            "routed_to": "Coordinator",
            "delegated_result": {
                "agent_name": "Coordinator",
                "action": "create_novel",
                "params": context.get("creation_requirements", {}),
            },
            "routing_info": {"steps": []},
        }


class _FakeStreamingRouter(_FakeRouter):
    async def route_and_respond(self, message, context=None):
        self.last_context = context or {}
        progress_callback = self.last_context.get("progress_callback")
        if progress_callback:
            await progress_callback("### 世界观阶段\n正在生成世界观...\n\n")
            await progress_callback("### 大纲阶段\n正在生成大纲...\n\n")
        return {
            "response": "创作完成，文件已全部写入。",
            "routed_to": "Coordinator",
            "delegated_result": {
                "agent_name": "Coordinator",
                "action": "create_novel",
            },
            "routing_info": {"steps": []},
        }


class _LockAwareRouter(_FakeRouter):
    def __init__(self, lock):
        super().__init__()
        self.lock = lock
        self.observed_unlocked = False

    async def route_and_respond(self, message, context=None):
        self.last_context = context or {}
        self.observed_unlocked = not self.lock.locked()
        if not self.observed_unlocked:
            raise AssertionError("chat lock should be released before router execution")
        return {
            "response": "已在无锁状态下执行多Agent任务。",
            "routed_to": "Coordinator",
            "delegated_result": {
                "agent_name": "Coordinator",
                "action": "create_novel",
                "params": context.get("creation_requirements", {}),
            },
            "routing_info": {"steps": []},
        }


class _FakeControlCoordinator:
    def __init__(self):
        self.pause_calls = 0
        self.resume_calls = 0
        self.cancel_calls = 0
        self.workflow_state = SimpleNamespace(value="writing")
        self.checkpoint = {"current_chapter": 2}
        self.project = {"total_chapters": 5, "completed_chapters": 1}

    def pause(self):
        self.pause_calls += 1
        self.workflow_state = SimpleNamespace(value="paused")

    def resume(self):
        self.resume_calls += 1
        self.workflow_state = SimpleNamespace(value="writing")

    def cancel(self):
        self.cancel_calls += 1
        self.workflow_state = SimpleNamespace(value="failed")

    def get_project_status(self):
        return {
            "workflow_state": self.workflow_state.value,
            "checkpoint": self.checkpoint,
            "project": self.project,
        }


@pytest.mark.parametrize(
    ("message", "expected_name", "expected_chapter", "expected_payload"),
    [
        ("/create 宗门覆灭后的复仇与重建", "create", 0, "宗门覆灭后的复仇与重建"),
        ("/worldbuild 末日废土与残存城邦", "worldbuild", 0, "末日废土与残存城邦"),
        ("/chapter 12 收束伏笔", "chapter", 12, "收束伏笔"),
        ("/chapter 5 收束伏笔", "chapter", 5, "收束伏笔"),
        ("/status", "status", 0, ""),
        ("/pause", "pause", 0, ""),
    ],
)
def test_parse_explicit_command_supports_slash_commands_only(message, expected_name, expected_chapter, expected_payload):
    payload = chat_routes._parse_explicit_command(message)

    assert payload is not None
    assert payload["name"] == expected_name
    assert payload.get("chapter_number", 0) == expected_chapter
    assert payload.get("message", "") == expected_payload


@pytest.mark.parametrize("message", ["开始创作 宗门覆灭后的复仇与重建", "生成世界观 末日废土与残存城邦", "续写章节3 血战升级", "查看进度"])
def test_parse_explicit_command_ignores_plain_chinese_inputs(message):
    assert chat_routes._parse_explicit_command(message) is None


@pytest.mark.parametrize(
    ("message", "expected_name", "expected_chapter", "expected_payload"),
    [
        ("生成世界观 末日废土与残存城邦", "worldbuild", 0, "末日废土与残存城邦"),
        ("生成大纲 宗门覆灭后的复仇与重建", "outline", 0, "宗门覆灭后的复仇与重建"),
        ("续写章节3 血战升级", "chapter", 3, "血战升级"),
        ("那就把世界观保存到资料库", "worldbuild", 0, "把世界观保存到资料库"),
        ("直接写第一章正文", "chapter", 1, ""),
        ("查看进度", "status", 0, ""),
    ],
)
def test_parse_targeted_natural_language_command(message, expected_name, expected_chapter, expected_payload):
    payload = chat_routes._parse_targeted_natural_language_command(message)

    assert payload is not None
    assert payload["name"] == expected_name
    assert payload.get("chapter_number", 0) == expected_chapter
    assert payload.get("message", "") == expected_payload


@pytest.mark.asyncio
async def test_chat_explicit_creation_uses_router_execution(monkeypatch):
    store = _FakeChatStore()
    router = _FakeRouter()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="开始创作吧", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["reply"] == "已切换到创作协调器并开始执行。"
    assert payload["routed"] is True
    assert payload["routing"]["target_agent"] == "Coordinator"
    assert router.last_context["auto_execute"] is True
    assert router.last_context["creation_requirements"]["novel_type"] == "玄幻"
    assert _FakeCommunicatorAgent.chat_calls == 0
    assert store.saved_states, "chat session should still be persisted after delegated execution"


@pytest.mark.asyncio
async def test_chat_router_execution_releases_session_lock_before_long_running_route(monkeypatch):
    store = _FakeChatStore()
    session_key = "proj-test::copilot"
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    lock = await chat_routes._get_chat_session_lock(session_key)
    router = _LockAwareRouter(lock)

    _FakeCommunicatorAgent.chat_calls = 0

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="开始创作吧", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routed"] is True
    assert router.observed_unlocked is True
    assert _FakeCommunicatorAgent.chat_calls == 0
    assert store.saved_states


@pytest.mark.asyncio
async def test_chat_stream_router_execution_emits_progress_before_done(monkeypatch):
    store = _FakeChatStore()
    router = _FakeStreamingRouter()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat_stream(ChatRequest(message="开始创作吧", session_id="copilot"))
    events = []
    async for raw in response.body_iterator:
        events.append(raw)

    joined = "".join(
        item.decode("utf-8") if isinstance(item, (bytes, bytearray)) else str(item)
        for item in events
    )

    assert "### 世界观阶段" in joined
    assert "### 大纲阶段" in joined
    assert '"type": "done"' in joined or '"type":"done"' in joined
    assert "创作完成，文件已全部写入。" in joined
    assert _FakeCommunicatorAgent.chat_calls == 0


@pytest.mark.asyncio
async def test_chat_stream_does_not_resave_session_after_reset(monkeypatch):
    store = _FakeChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeStreamingCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat_stream(ChatRequest(message="普通对话", session_id="copilot"))
    reset_response = await chat_routes.reset_chat(session_id="copilot")
    reset_payload = json.loads(reset_response.body.decode("utf-8"))
    assert reset_payload["success"] is True

    events = []
    async for raw in response.body_iterator:
        events.append(raw)

    joined = "".join(
        item.decode("utf-8") if isinstance(item, (bytes, bytearray)) else str(item)
        for item in events
    )
    assert "stream done" in joined
    assert store.saved_states == []


@pytest.mark.asyncio
async def test_reset_chat_preserves_session_lock_identity(monkeypatch):
    store = _FakeChatStore()
    session_key = "proj-test::copilot"
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    original_lock = await chat_routes._get_chat_session_lock(session_key)

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())

    response = await chat_routes.reset_chat(session_id="copilot")
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["success"] is True
    same_lock = await chat_routes._get_chat_session_lock(session_key)
    assert same_lock is original_lock


@pytest.mark.asyncio
async def test_delete_chat_session_preserves_session_lock_identity(monkeypatch):
    store = _FakeChatStore()
    session_key = "proj-test::copilot"
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes.chat_sessions[session_key] = object()

    original_lock = await chat_routes._get_chat_session_lock(session_key)

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())

    response = await chat_routes.delete_chat_session(session_id="copilot")
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["success"] is True
    same_lock = await chat_routes._get_chat_session_lock(session_key)
    assert same_lock is original_lock


@pytest.mark.asyncio
async def test_create_chat_session_burst_without_id_returns_unique_session_ids(monkeypatch):
    store = _PersistentChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())

    async def create_once():
        response = await chat_routes.create_chat_session()
        return json.loads(response.body.decode("utf-8"))

    payloads = await asyncio.gather(*[create_once() for _ in range(6)])
    session_ids = [item["session_id"] for item in payloads]

    assert len(session_ids) == len(set(session_ids))


@pytest.mark.asyncio
async def test_chat_concurrent_same_session_initializes_single_agent_instance(monkeypatch):
    store = _PersistentChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    _SlowCommunicatorAgent.start_calls = 0
    _SlowCommunicatorAgent.chat_calls = 0

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _SlowCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    async def send(message):
        response = await chat_routes.chat(ChatRequest(message=message, session_id="copilot"))
        return json.loads(response.body.decode("utf-8"))

    first, second = await asyncio.gather(send("你好"), send("继续"))

    assert first["reply"] == "echo:你好"
    assert second["reply"] == "echo:继续"
    assert _SlowCommunicatorAgent.start_calls == 1
    assert _SlowCommunicatorAgent.chat_calls == 2
    assert len(store.saved_states) == 2


@pytest.mark.asyncio
async def test_chat_workflow_control_commands_call_coordinator(monkeypatch):
    store = _FakeChatStore()
    coordinator = _FakeControlCoordinator()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS["proj-test::copilot"] = {
        "status": "running",
        "last_progress": "第 1 章完成",
    }

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    pause_resp = await chat_routes.chat(ChatRequest(message="/pause", session_id="copilot"))
    pause_payload = json.loads(pause_resp.body.decode("utf-8"))
    assert coordinator.pause_calls == 1
    assert "已发送暂停指令" in pause_payload["reply"]
    assert pause_payload["routing"]["target_agent"] == "Coordinator"

    resume_resp = await chat_routes.chat(ChatRequest(message="继续创作", session_id="copilot"))
    resume_payload = json.loads(resume_resp.body.decode("utf-8"))
    assert coordinator.resume_calls == 1
    assert "已发送恢复指令" in resume_payload["reply"]

    status_resp = await chat_routes.chat(ChatRequest(message="/status", session_id="copilot"))
    status_payload = json.loads(status_resp.body.decode("utf-8"))
    assert "当前创作状态" in status_payload["reply"]
    assert "最近进度" in status_payload["reply"]

    cancel_resp = await chat_routes.chat(ChatRequest(message="取消创作", session_id="copilot"))
    cancel_payload = json.loads(cancel_resp.body.decode("utf-8"))
    assert coordinator.cancel_calls == 1
    assert "已发送取消指令" in cancel_payload["reply"]


@pytest.mark.asyncio
async def test_chat_stream_workflow_control_commands_use_control_branch(monkeypatch):
    store = _FakeChatStore()
    coordinator = _FakeControlCoordinator()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS["proj-test::copilot"] = {
        "status": "running",
        "last_progress": "第 2 章进行中",
    }

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: _FakeProjectManager())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat_stream(ChatRequest(message="/pause", session_id="copilot"))
    events = []
    async for raw in response.body_iterator:
        events.append(raw)

    joined = "".join(
        item.decode("utf-8") if isinstance(item, (bytes, bytearray)) else str(item)
        for item in events
    )

    assert coordinator.pause_calls == 1
    assert "已发送暂停指令" in joined
    assert '"target_agent": "Coordinator"' in joined or '"target_agent":"Coordinator"' in joined
    assert '"type": "done"' in joined or '"type":"done"' in joined


@pytest.mark.asyncio
async def test_chat_explicit_create_command_persists_structured_workflow_status(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="开始创作 宗门覆灭后的复仇与重建", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "Coordinator"
    assert payload["workflow"]["status"] == "completed"
    assert payload["workflow"]["run_id"]
    assert payload["created_files"], "explicit create should return created files"
    assert payload["output_dir"] == str(project_dir)
    assert any(item["kind"] == "worldbuilding" for item in payload["created_files"] + payload["updated_files"])
    assert any(item["kind"] == "outline" for item in payload["created_files"] + payload["updated_files"])
    assert _FakeCommunicatorAgent.chat_calls == 0

    status_response = await chat_routes.get_chat_workflow_status(session_id="copilot")
    status_payload = json.loads(status_response.body.decode("utf-8"))
    assert status_payload["workflow"]["status"] == "completed"
    assert status_payload["workflow"]["run_id"] == payload["workflow"]["run_id"]
    assert status_payload["workflow"]["created_files"] or status_payload["workflow"]["updated_files"]
    assert "当前创作状态：`completed`" in status_payload["reply"]


@pytest.mark.asyncio
async def test_chat_refreshes_model_config_for_existing_session_same_conversation(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    store = _PersistentChatStore()
    router = _FakeRouterWithDynamicModel()

    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    first_response = await chat_routes.chat(ChatRequest(message="你好", session_id="copilot"))
    first_payload = json.loads(first_response.body.decode("utf-8"))

    second_response = await chat_routes.chat(ChatRequest(message="继续聊聊", session_id="copilot"))
    second_payload = json.loads(second_response.body.decode("utf-8"))

    agent = chat_routes.chat_sessions[f"{pm.current_project_id}::copilot"]

    assert first_payload["reply"] == "communicator fallback"
    assert second_payload["reply"] == "communicator fallback"
    assert agent.refresh_calls >= 2
    assert agent._get_model_name() == "glm-4.6"
    assert router.refresh_calls >= 2
    assert router._get_model_name() == "glm-4.6"
    assert first_payload["routing"]["model"] == "glm-4.6"
    assert second_payload["routing"]["model"] == "glm-4.6"


@pytest.mark.asyncio
async def test_chat_explicit_create_command_uses_formal_task_pool_when_available(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="开始创作 宗门覆灭后的复仇与重建", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    saved_task_pool = pm.load_project_state("task_pool", default={})
    saved_trace = pm.load_project_state("collab_execution_trace", default={})

    assert payload["routing"]["target_agent"] == "Coordinator"
    assert payload["workflow"]["status"] == "completed"
    assert "正式多Agent协作执行链" in payload["reply"]
    assert coordinator.last_execute_kwargs == {"max_tasks": 4, "max_chapter_tasks": 2}
    assert saved_task_pool.get("metadata", {}).get("source") == "contract_confirmation"
    assert saved_task_pool.get("metadata", {}).get("project_ready_execution", {}).get("executed_task_count") == 4
    assert any(task.get("task_type") == "build_world" and task.get("status") == "completed" for task in saved_task_pool.get("tasks", []))
    assert any(item.get("type") == "project_ready_execution_cycle" for item in saved_trace.get("events", []))
    assert any(item["kind"] == "worldbuilding" for item in payload["created_files"] + payload["updated_files"])
    assert any(item["kind"] == "outline" for item in payload["created_files"] + payload["updated_files"])


@pytest.mark.asyncio
async def test_chat_workflow_control_commands_keep_real_coordinator_statuses_consistent(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    store = _FakeChatStore()
    monkeypatch.setattr("novel_agent.workflow.coordinator.get_project_manager", lambda: pm)
    coordinator = NovelCoordinator(project_dir=tmp_path / "project")
    coordinator.project = NovelProject(
        id=pm.current_project_id,
        title="测试项目",
        novel_type="玄幻",
        status="writing",
        created_at="2026-04-10T00:00:00",
        updated_at="2026-04-10T00:00:00",
        total_chapters=5,
        completed_chapters=1,
        word_count=1000,
    )
    coordinator._update_checkpoint(state=WorkflowState.WRITING, current_chapter=2)

    session_key = f"{pm.current_project_id}::copilot"
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS[session_key] = {
        "status": "writing",
        "last_progress": "第 2 章进行中",
        "stage": "chapter_2",
        "current_agent": "ChapterWriter",
    }

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    pause_resp = await chat_routes.chat(ChatRequest(message="/pause", session_id="copilot"))
    pause_payload = json.loads(pause_resp.body.decode("utf-8"))
    assert pause_payload["workflow"]["status"] == "paused"

    resume_resp = await chat_routes.chat(ChatRequest(message="继续创作", session_id="copilot"))
    resume_payload = json.loads(resume_resp.body.decode("utf-8"))
    assert resume_payload["workflow"]["status"] == "writing"

    status_resp = await chat_routes.chat(ChatRequest(message="/status", session_id="copilot"))
    status_payload = json.loads(status_resp.body.decode("utf-8"))
    assert "当前创作状态：`writing`" in status_payload["reply"]

    cancel_resp = await chat_routes.chat(ChatRequest(message="取消创作", session_id="copilot"))
    cancel_payload = json.loads(cancel_resp.body.decode("utf-8"))
    assert cancel_payload["workflow"]["status"] == "cancelled"

    final_status_resp = await chat_routes.chat(ChatRequest(message="/status", session_id="copilot"))
    final_status_payload = json.loads(final_status_resp.body.decode("utf-8"))
    assert "当前创作状态：`cancelled`" in final_status_payload["reply"]


def test_router_formal_execution_limits_cap_large_projects():
    router = RouterAgent(coordinator=None)
    max_tasks, max_chapter_tasks = router._compute_formal_execution_limits(
        requirements={"volume_count": 3, "chapters_per_volume": 10},
        task_pool_payload={"tasks": [{} for _ in range(28)]},
    )

    assert max_tasks == 4
    assert max_chapter_tasks == 2


@pytest.mark.asyncio
async def test_chat_pause_rejects_cancelled_real_coordinator_without_active_run(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    store = _FakeChatStore()
    monkeypatch.setattr("novel_agent.workflow.coordinator.get_project_manager", lambda: pm)
    coordinator = NovelCoordinator(project_dir=tmp_path / "project")
    coordinator.project = NovelProject(
        id=pm.current_project_id,
        title="测试项目",
        novel_type="玄幻",
        status="writing",
        created_at="2026-04-10T00:00:00",
        updated_at="2026-04-10T00:00:00",
        total_chapters=5,
        completed_chapters=1,
        word_count=1000,
    )
    coordinator._update_checkpoint(state=WorkflowState.WRITING, current_chapter=2)
    coordinator.cancel()

    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: None)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="/pause", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["reply"] == "当前没有正在执行的创作任务，无法暂停。"


@pytest.mark.asyncio
async def test_get_chat_workflow_status_prefers_session_snapshot_over_real_coordinator_idle(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    monkeypatch.setattr("novel_agent.workflow.coordinator.get_project_manager", lambda: pm)
    coordinator = NovelCoordinator(project_dir=tmp_path / "project")

    session_key = f"{pm.current_project_id}::copilot"
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS[session_key] = {
        "run_id": "run-123",
        "session_id": "copilot",
        "project_id": pm.current_project_id,
        "status": "completed",
        "current_agent": "Coordinator",
        "target_agent": "Coordinator",
        "stage": "completed",
        "last_progress": "全部任务已完成",
        "created_files": [],
        "updated_files": [],
    }

    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)

    response = await chat_routes.get_chat_workflow_status(session_id="copilot")
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["workflow"]["status"] == "completed"
    assert payload["workflow"]["run_id"] == "run-123"
    assert "当前创作状态：`completed`" in payload["reply"]


def test_real_coordinator_resume_and_cancel_keep_runtime_state_consistent():
    coordinator = NovelCoordinator()
    coordinator.project = NovelProject(
        id="proj-test",
        title="测试项目",
        novel_type="玄幻",
        status="writing",
        created_at="2026-04-10T00:00:00",
        updated_at="2026-04-10T00:00:00",
        total_chapters=5,
        completed_chapters=1,
        word_count=1000,
    )
    coordinator._update_checkpoint(state=WorkflowState.WRITING, current_chapter=2)

    coordinator.pause()
    assert coordinator.workflow_state == WorkflowState.PAUSED
    assert coordinator.checkpoint is not None
    assert coordinator.checkpoint.state == WorkflowState.PAUSED

    coordinator.resume()
    assert coordinator.workflow_state == WorkflowState.WRITING
    assert coordinator.checkpoint is not None
    assert coordinator.checkpoint.state == WorkflowState.WRITING
    assert coordinator.get_project_status()["workflow_state"] == "writing"

    coordinator.pause()
    coordinator.cancel()
    assert coordinator._cancelled is True
    assert coordinator._paused is False
    assert coordinator.workflow_state == WorkflowState.WRITING
    assert coordinator.checkpoint is not None
    assert coordinator.checkpoint.state == WorkflowState.WRITING
    assert coordinator.get_project_status()["workflow_state"] == "cancelled"


@pytest.mark.asyncio
async def test_chat_explicit_worldbuild_command_writes_world_file_only(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="生成世界观 末日废土与残存城邦", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "Worldbuilder"
    assert payload["workflow"]["current_agent"] == "Worldbuilder"
    assert any(item["kind"] == "worldbuilding" for item in payload["created_files"] + payload["updated_files"])
    assert not any(item["kind"] == "chapter" for item in payload["created_files"] + payload["updated_files"])
    assert (project_dir / "worldbuilding.json").exists()
    saved_world = pm.load_project_data("worldbuilding")
    assert isinstance(saved_world, dict)
    assert saved_world.get("world", {}).get("world_name") == "玄幻世界"
    normalized_world = project_routes._normalize_builtin_project_data("worldbuilding", saved_world)
    assert any(item.get("name") == "玄幻世界" for item in normalized_world.get("data", []))


@pytest.mark.asyncio
async def test_chat_prefixed_worldbuild_save_request_executes_and_persists_project_worldbuilding(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="那就把世界观保存到资料库", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "Worldbuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "worldbuilding" for item in payload["created_files"] + payload["updated_files"])
    saved_world = pm.load_project_data("worldbuilding")
    assert isinstance(saved_world, dict)
    assert saved_world.get("world", {}).get("world_name") == "玄幻世界"
    normalized_world = project_routes._normalize_builtin_project_data("worldbuilding", saved_world)
    assert any(item.get("name") == "玄幻世界" for item in normalized_world.get("data", []))


@pytest.mark.asyncio
async def test_chat_character_creation_request_routes_to_character_builder_and_persists_characters(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _FakeChatStore()

    async def _fake_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "CharacterBuilder",
            "characters": [
                {
                    "name": "林渡",
                    "role": "主角",
                    "identity": "宗门遗孤",
                    "occupation": "宗门遗孤",
                    "description": "少年剑修，宗门覆灭后踏上复仇之路。",
                    "personality": ["克制", "执拗"],
                    "goals": ["复仇", "重建秩序"],
                    "relationships": {"苏晚": "旧识"},
                    "notes": "保存测试",
                }
            ],
            "confidence": 0.95,
            "missing_info": [],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.character_builder.CharacterBuilderAgent.execute", _fake_execute)

    response = await chat_routes.chat(ChatRequest(message="把这个主角加入资料库：林渡，少年剑修，宗门遗孤", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "characters" for item in payload["created_files"] + payload["updated_files"])
    assert _FakeCommunicatorAgent.chat_calls == 0

    saved_characters = pm.load_project_data("characters")
    normalized = project_routes._normalize_builtin_project_data("characters", saved_characters)
    assert any(item.get("name") == "林渡" for item in normalized.get("data", []))


@pytest.mark.asyncio
async def test_chat_character_card_request_routes_to_builder_draft_without_persisting(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _PersistentChatStore()

    async def _fake_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "CharacterBuilder",
            "characters": [
                {
                    "name": "林渡",
                    "role": "主角",
                    "identity": "宗门遗孤",
                    "occupation": "宗门遗孤",
                    "description": "少年剑修，背负宗门覆灭之仇。",
                    "personality": ["克制", "执拗"],
                    "goals": ["复仇", "重建秩序"],
                    "relationships": {"师姐苏晚": "旧识"},
                    "notes": "草稿",
                }
            ],
            "confidence": 0.92,
            "missing_info": [],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.character_builder.CharacterBuilderAgent.execute", _fake_execute)

    response = await chat_routes.chat(ChatRequest(message="请帮我生成主角角色卡：林渡，少年剑修，宗门遗孤", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert payload["is_complete"] is False
    assert "已生成角色卡草稿" in payload["reply"]
    assert payload["delegated_result"]["characters"][0]["name"] == "林渡"
    assert pm.load_project_data("characters") == []

    save_response = await chat_routes.chat(ChatRequest(message="把这个角色卡保存到资料库", session_id="copilot"))
    save_payload = json.loads(save_response.body.decode("utf-8"))
    saved_characters = pm.load_project_data("characters")
    normalized = project_routes._normalize_builtin_project_data("characters", saved_characters)

    assert save_payload["routing"]["target_agent"] == "CharacterBuilder"
    assert any(item["kind"] == "characters" for item in save_payload["created_files"] + save_payload["updated_files"])
    assert any(item.get("name") == "林渡" for item in normalized.get("data", []))


@pytest.mark.asyncio
async def test_chat_character_card_auto_saves_when_chat_toggle_enabled(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_state("copilot_chat_auto_save", {"enabled": True})
    router = RouterAgent()
    store = _FakeChatStore()

    async def _fake_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "CharacterBuilder",
            "characters": [
                {
                    "name": "林渡",
                    "role": "主角",
                    "identity": "宗门遗孤",
                    "occupation": "宗门遗孤",
                    "description": "少年剑修，背负宗门覆灭之仇。",
                    "personality": ["克制", "执拗"],
                    "goals": ["复仇", "重建秩序"],
                    "relationships": {"师姐苏晚": "旧识"},
                    "notes": "自动保存",
                }
            ],
            "confidence": 0.92,
            "missing_info": [],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.character_builder.CharacterBuilderAgent.execute", _fake_execute)

    response = await chat_routes.chat(ChatRequest(message="请帮我生成主角角色卡：林渡，少年剑修，宗门遗孤", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert payload["is_complete"] is True
    assert any(item["kind"] == "characters" for item in payload["created_files"] + payload["updated_files"])
    saved_characters = pm.load_project_data("characters")
    normalized = project_routes._normalize_builtin_project_data("characters", saved_characters)
    assert any(item.get("name") == "林渡" for item in normalized.get("data", []))


@pytest.mark.asyncio
async def test_chat_character_card_custom_category_requires_manual_selection_even_with_toggle(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_state("copilot_chat_auto_save", {"enabled": True})
    pm.save_project_state("knowledge_categories", [
        {"id": "db-custom-faction", "key": "custom_faction", "name": "势力档案", "builtin": False}
    ])
    router = RouterAgent()
    store = _FakeChatStore()

    async def _fake_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "CharacterBuilder",
            "characters": [
                {
                    "name": "林渡",
                    "role": "主角",
                    "identity": "宗门遗孤",
                    "occupation": "宗门遗孤",
                    "description": "少年剑修，背负宗门覆灭之仇。",
                    "personality": ["克制", "执拗"],
                    "goals": ["复仇", "重建秩序"],
                    "relationships": {"师姐苏晚": "旧识"},
                    "notes": "自定义分类",
                }
            ],
            "confidence": 0.92,
            "missing_info": [],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.character_builder.CharacterBuilderAgent.execute", _fake_execute)

    response = await chat_routes.chat(ChatRequest(message="请帮我生成主角角色卡并保存到势力档案", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert payload["is_complete"] is False
    assert "不会自动写入该分类" in payload["reply"]
    assert pm.load_project_data("characters") == []


@pytest.mark.asyncio
async def test_chat_character_discussion_without_save_phrase_stays_in_communicator(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _FakeChatStore()

    _SlowCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _SlowCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")

    response = await chat_routes.chat(ChatRequest(message="我想补充主角人设，主角叫林渡，少年剑修，先别存档，继续帮我细化", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["reply"].startswith("echo:")
    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload.get("routed") is not True
    assert _SlowCommunicatorAgent.chat_calls == 1
    assert pm.load_project_data("characters") == []


@pytest.mark.asyncio
async def test_chat_character_creation_request_routes_to_builder_even_without_explicit_save_phrase(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _FakeChatStore()

    async def _fake_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "CharacterBuilder",
            "characters": [
                {
                    "name": "林渡",
                    "role": "主角",
                    "identity": "宗门遗孤",
                    "occupation": "宗门遗孤",
                    "description": "少年剑修，背负宗门覆灭之仇。",
                    "personality": ["克制", "执拗"],
                    "goals": ["复仇", "重建秩序"],
                    "relationships": {"师姐苏晚": "旧识"},
                    "notes": "回归测试",
                }
            ],
            "confidence": 0.92,
            "missing_info": [],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.character_builder.CharacterBuilderAgent.execute", _fake_execute)

    response = await chat_routes.chat(ChatRequest(message="请帮我生成主角角色卡：林渡，少年剑修，宗门遗孤", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["target_agent"] == "CharacterBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "characters" for item in payload["created_files"] + payload["updated_files"])
    assert _FakeCommunicatorAgent.chat_calls == 0


@pytest.mark.asyncio
async def test_chat_continue_write_request_executes_continuous_writer(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _FakeChatStore()
    fake_writer = _FakeContinuousWriter()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr(router, "_get_continuous_writer", lambda: fake_writer)
    monkeypatch.setattr(
        router,
        "analyze_intent",
        AsyncMock(return_value=IntentAnalysis(
            primary_intent=UserIntent.CONTINUE_WRITE,
            confidence=0.95,
            entities={},
            requires_knowledge_base=False,
            requires_tool_call=False,
        ))
    )

    response = await chat_routes.chat(ChatRequest(message="继续写，主角刚刚得知仇人下落，现在立刻推进冲突", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "ContinuousWriter"
    assert payload["workflow"]["status"] == "completed"
    assert payload["is_complete"] is True
    assert "真正写出的下一章正文" in payload["reply"]
    assert fake_writer.session_id == "copilot"
    assert fake_writer.session_loaded is True
    assert fake_writer.executed


@pytest.mark.asyncio
async def test_chat_polish_request_executes_polisher_when_content_present(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    router = RouterAgent()
    store = _FakeChatStore()
    fake_polisher = _FakePolisher()

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr(router, "_get_polisher", lambda: fake_polisher)
    monkeypatch.setattr(
        router,
        "analyze_intent",
        AsyncMock(return_value=IntentAnalysis(
            primary_intent=UserIntent.POLISH_CONTENT,
            confidence=0.95,
            entities={},
            requires_knowledge_base=False,
            requires_tool_call=False,
        ))
    )

    response = await chat_routes.chat(ChatRequest(message="请帮我润色：他推门进去，看见屋里没有灯，气氛很压抑。", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "Polisher"
    assert payload["workflow"]["status"] == "completed"
    assert payload["is_complete"] is True
    assert "真正输出的润色结果" in payload["reply"]
    assert fake_polisher.executed


@pytest.mark.asyncio
async def test_chat_eventline_request_auto_generates_and_persists_without_explicit_save_phrase(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    async def _fake_eventline_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "EventlineBuilder",
            "rows": [
                {
                    "name": "第1章 事件线",
                    "description": "主角接到复仇目标并踏上旅程",
                    "participants": ["林渡"],
                    "conflict": "复仇与生存压力",
                    "status": "推进中",
                }
            ],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.project_data_builders.EventlineBuilderAgent.execute", _fake_eventline_execute)

    response = await chat_routes.chat(ChatRequest(message="帮我梳理一下这本书的事件线", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "EventlineBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "eventlines" for item in payload["created_files"] + payload["updated_files"])
    saved_rows = pm.load_project_data("eventlines")
    assert isinstance(saved_rows, list) and saved_rows
    assert any("事件线" in str(item.get("name") or "") for item in saved_rows if isinstance(item, dict))


@pytest.mark.asyncio
async def test_chat_detail_outline_request_auto_generates_and_persists(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    async def _fake_detail_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "DetailOutlineBuilder",
            "rows": [
                {
                    "name": "第1章",
                    "description": "主角确认目标并与同伴会合",
                    "chapter_number": 1,
                    "scene_goal": "建立本章行动目标",
                    "conflict": "目标与现实条件不匹配",
                    "notes": "需埋下后续伏笔",
                }
            ],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.project_data_builders.DetailOutlineBuilderAgent.execute", _fake_detail_execute)

    response = await chat_routes.chat(ChatRequest(message="根据当前设定生成细纲", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "DetailOutlineBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "detail_settings" for item in payload["created_files"] + payload["updated_files"])
    saved_rows = pm.load_project_data("detail_settings")
    assert isinstance(saved_rows, list) and saved_rows
    assert any(item.get("chapter_number") == 1 for item in saved_rows if isinstance(item, dict))


@pytest.mark.asyncio
async def test_chat_chapter_setting_request_auto_generates_and_persists(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)
    store = _FakeChatStore()

    async def _fake_chapter_setting_execute(self, input_data, context=None):
        return {
            "success": True,
            "agent": "ChapterSettingBuilder",
            "rows": [
                {
                    "name": "第1章",
                    "description": "主角踏上复仇旅程的开端",
                    "chapter_number": 1,
                    "chapter_goal": "建立行动目标",
                    "key_event": "得知仇人线索",
                    "ending_hook": "发现更大阴谋",
                }
            ],
        }

    _FakeCommunicatorAgent.chat_calls = 0
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    monkeypatch.setattr("novel_agent.agents.CommunicatorAgent", _FakeCommunicatorAgent)
    monkeypatch.setattr("novel_agent.agents.get_chat_session_store", lambda: store)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.prompts.check_user_input_security", lambda message: (True, message))
    monkeypatch.setattr("novel_agent.prompts.get_security_response", lambda: "blocked")
    monkeypatch.setattr("novel_agent.agents.project_data_builders.ChapterSettingBuilderAgent.execute", _fake_chapter_setting_execute)

    response = await chat_routes.chat(ChatRequest(message="把章纲也补出来", session_id="copilot"))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["routing"]["target_agent"] == "ChapterSettingBuilder"
    assert payload["workflow"]["status"] == "completed"
    assert any(item["kind"] == "chapter_settings" for item in payload["created_files"] + payload["updated_files"])
    saved_rows = pm.load_project_data("chapter_settings")
    assert isinstance(saved_rows, list) and saved_rows
    assert any(item.get("chapter_number") == 1 for item in saved_rows if isinstance(item, dict))


class _FakeCoordinator:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.project = None
        self._paused = False
        self._cancelled = False

    async def generate_world(self, novel_type: str, theme: str = "", requirements: str = ""):
        payload = {
            "world_name": f"{novel_type}世界",
            "theme": theme,
            "requirements": requirements,
        }
        (self.project_dir / "worldbuilding.json").write_text(
            json.dumps({"world": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"world": payload}

    async def generate_outline(
        self,
        world=None,
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 5,
    ):
        return {
            "outline": {
                "chapters": [
                    {"title": "第1章 旧城归来", "summary": f"{protagonist}踏入旧城，故事由此开始。"},
                    {"title": "第2章 血债", "summary": f"{plot_idea}进一步升级。"},
                ]
            }
        }

    async def _write_single_chapter_internal(self, chapter_num: int, chapter_outline, previous_chapters):
        chapter_title = chapter_outline.get("title") or f"第{chapter_num}章"
        chapter_summary = chapter_outline.get("summary") or ""
        return {
            "number": chapter_num,
            "chapter_title": chapter_title,
            "title": chapter_title,
            "content": f"{chapter_title}\n{chapter_summary}\n真正的正文已经写入文件。",
        }

    async def _check_pause_cancel(self):
        return self._cancelled

    def _extract_chapters(self, outline_data):
        return outline_data.get("chapters", [])

    def _save_novel(self, file_path: Path, chapters):
        content = "\n\n".join(str(chapter.get("content") or "") for chapter in chapters)
        file_path.write_text(content, encoding="utf-8")


class _FakeFormalCoordinator:
    def __init__(self, pm: ProjectManager, project_dir: Path):
        self.project_manager = pm
        self.project_dir = project_dir
        self.progress_callback = None
        self.project = None
        self.last_execute_kwargs = {}

    def initialize_task_pool_from_contract(self, contract_payload, approved=True):
        task_pool = {
            "metadata": {
                "contract_id": contract_payload.get("contract_id", "contract-1"),
                "source": "contract_confirmation",
            },
            "tasks": [
                {"task_id": "world-1", "task_type": "build_world", "title": "生成世界观", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {}},
                {"task_id": "outline-1", "task_type": "build_outline", "title": "生成大纲", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {}},
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
                {"task_id": "chapter-2", "task_type": "write_chapter", "title": "创作第2章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 2}},
            ],
        }
        self.project_manager.save_project_state("creation_contract", contract_payload)
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state(
            "collab_execution_trace",
            {"status": "initialized", "events": [{"type": "contract_confirmation"}]},
        )
        return {"creation_contract": contract_payload, "task_pool": task_pool}

    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        if self.progress_callback:
            await self.progress_callback(
                {
                    "type": "sub_agent_dispatching",
                    "stage": "project_dispatch",
                    "agent": "Coordinator",
                    "task_type": "build_world",
                    "title": "生成世界观",
                    "message": "正在调度任务: 生成世界观",
                }
            )

        (self.project_dir / "worldbuilding.json").write_text(
            json.dumps({"world": {"world_name": "玄幻世界"}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outline_rows = [
            {"chapter_number": 1, "title": "第1章 旧城归来", "summary": "林渡回到旧城。", "content": "第1章正文"},
            {"chapter_number": 2, "title": "第2章 血债", "summary": "复仇升级。", "content": "第2章正文"},
        ]
        self.project_manager.save_project_data("outline", outline_rows)
        chapters_dir = self.project_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapter_one = chapters_dir / "001_第1章_旧城归来.md"
        chapter_two = chapters_dir / "002_第2章_血债.md"
        chapter_one.write_text("第1章正文", encoding="utf-8")
        chapter_two.write_text("第2章正文", encoding="utf-8")

        task_pool = self.project_manager.load_project_state("task_pool", default={})
        for task in task_pool.get("tasks", []):
            task_type = task.get("task_type")
            task["status"] = "completed"
            if task_type == "build_world":
                task["assigned_agent"] = "Worldbuilder"
                task["result_ref"] = "worldbuilding.json"
            elif task_type == "build_outline":
                task["assigned_agent"] = "Outliner"
                task["result_ref"] = "outline.json"
            elif task_type == "write_chapter" and task.get("inputs", {}).get("chapter_number") == 1:
                task["assigned_agent"] = "ChapterWriter"
                task["result_ref"] = str(chapter_one)
            elif task_type == "write_chapter":
                task["assigned_agent"] = "ChapterWriter"
                task["result_ref"] = str(chapter_two)
        task_pool["metadata"]["project_ready_execution"] = {
            "executed_task_count": 4,
            "chapter_tasks_executed": 2,
            "stop_reason": "",
            "stopped_on_task_type": "",
        }
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state(
            "collab_execution_trace",
            {
                "status": "initialized",
                "events": [
                    {"type": "contract_confirmation"},
                    {"type": "task_started"},
                    {"type": "task_completed"},
                    {"type": "project_ready_execution_cycle"},
                ],
            },
        )
        return {
            "task_pool": task_pool,
            "executed_tasks": [
                {"task_id": "world-1", "task_type": "build_world", "title": "生成世界观", "selected_agent": "Worldbuilder", "result_ref": "worldbuilding.json"},
                {"task_id": "outline-1", "task_type": "build_outline", "title": "生成大纲", "selected_agent": "Outliner", "result_ref": "outline.json"},
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "selected_agent": "ChapterWriter", "result_ref": str(chapter_one)},
                {"task_id": "chapter-2", "task_type": "write_chapter", "title": "创作第2章", "selected_agent": "ChapterWriter", "result_ref": str(chapter_two)},
            ],
            "project_ready_execution": task_pool["metadata"]["project_ready_execution"],
            "stop_reason": "",
            "stopped_on_task_type": "",
        }

    def _save_novel(self, file_path: Path, chapters):
        content = "\n\n".join(str(chapter.get("content") or "") for chapter in chapters)
        file_path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_router_create_pipeline_persists_outline_and_chapter_files(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    result = await router.route_and_respond(
        "开始创作",
        context={
            "auto_execute": True,
            "creation_requirements": {
                "novel_type": "玄幻",
                "theme": "宗门复仇",
                "protagonist": "林渡",
                "plot_idea": "宗门覆灭后的复仇与重建",
                "volume_count": 1,
                "chapters_per_volume": 2,
            },
        },
    )

    outline_path = project_dir / "outline.json"
    world_path = project_dir / "worldbuilding.json"
    chapter_dir = project_dir / "chapters"
    chapter_files = list(chapter_dir.glob("*.md"))
    compiled_files = list(project_dir.glob("*.txt"))
    outline_rows = json.loads(outline_path.read_text(encoding="utf-8"))

    assert result["routed_to"] == "Coordinator"
    assert "已切换到创作执行链" in result["response"]
    assert world_path.exists()
    assert outline_path.exists()
    assert outline_rows[0]["title"] == "第1章 旧城归来"
    assert "真正的正文已经写入文件。" in outline_rows[0]["content"]
    assert len(chapter_files) == 2, "all generated chapter files should be created in project chapters directory"
    assert compiled_files, "compiled novel txt should be created"
    assert "真正的正文已经写入文件。" in chapter_files[0].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_router_create_pipeline_resumes_from_existing_outline_and_chapters(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeCoordinator(project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    outline_rows = [
        {
            "chapter_number": 1,
            "title": "第1章 旧城归来",
            "summary": "林渡踏入旧城，故事由此开始。",
            "content": "第1章 旧城归来\n这是一段已经写好的正文。",
            "created_at": "2026-03-24T00:00:00",
            "updated_at": "2026-03-24T00:00:00",
        },
        {
            "chapter_number": 2,
            "title": "第2章 血债",
            "summary": "宗门覆灭后的复仇与重建进一步升级。",
            "content": "",
            "created_at": "2026-03-24T00:00:00",
            "updated_at": "2026-03-24T00:00:00",
        },
    ]
    pm.save_project_data("outline", outline_rows)
    (project_dir / "worldbuilding.json").write_text(
        json.dumps({"world": {"world_name": "玄幻世界"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    chapter_dir = project_dir / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "001_第1章_旧城归来.md").write_text("第1章 旧城归来\n这是一段已经写好的正文。", encoding="utf-8")

    result = await router.route_and_respond(
        "/create 继续完成这部小说",
        context={
            "auto_execute": True,
            "explicit_command": {
                "name": "create",
                "message": "继续完成这部小说",
                "raw_args": "继续完成这部小说",
                "display": "/create",
            },
            "creation_requirements": {
                "novel_type": "玄幻",
                "theme": "宗门复仇",
                "protagonist": "林渡",
                "plot_idea": "宗门覆灭后的复仇与重建",
                "volume_count": 1,
                "chapters_per_volume": 2,
            },
        },
    )

    chapter_files = sorted((project_dir / "chapters").glob("*.md"))
    compiled_files = list(project_dir.glob("*.txt"))
    updated_outline = json.loads((project_dir / "outline.json").read_text(encoding="utf-8"))

    assert result["routed_to"] == "Coordinator"
    assert "断点续作" in result["response"]
    assert len(chapter_files) == 2
    assert "这是一段已经写好的正文。" in chapter_files[0].read_text(encoding="utf-8")
    assert "真正的正文已经写入文件。" in chapter_files[1].read_text(encoding="utf-8")
    assert "真正的正文已经写入文件。" in updated_outline[1]["content"]
    assert compiled_files
    assert any(item["kind"] == "worldbuilding" and item["status"] == "reused" for item in result["delegated_result"].get("reused_files", []))
    assert any(item["kind"] == "outline" and item["status"] == "reused" for item in result["delegated_result"].get("reused_files", []))
    assert any(item["kind"] == "chapter" and item["status"] == "reused" for item in result["delegated_result"].get("reused_files", []))
    assert not any(item["path"].endswith("001_第1章_旧城归来.md") for item in result["delegated_result"].get("updated_files", []))


@pytest.mark.asyncio
async def test_get_chat_workflow_status_reports_reused_file_counts(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    session_key = f"{pm.current_project_id}::copilot"
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS[session_key] = {
        "run_id": "run-reuse",
        "session_id": "copilot",
        "project_id": pm.current_project_id,
        "status": "completed",
        "current_agent": "Coordinator",
        "target_agent": "Coordinator",
        "stage": "completed",
        "last_progress": "断点续作完成",
        "created_files": [{"path": "chapters/002.md", "kind": "chapter", "label": "第 2 章", "status": "created"}],
        "updated_files": [],
        "reused_files": [{"path": "chapters/001.md", "kind": "chapter", "label": "第 1 章", "status": "reused"}],
    }

    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: None)

    response = await chat_routes.get_chat_workflow_status(session_id="copilot")
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["workflow"]["reused_files"]
    assert "内容同步情况：新增 1 项，更新 0 项，复用 1 项" in payload["reply"]


def test_router_build_creation_requirements_preserves_discussion_context_and_resume_signal():
    router = RouterAgent(coordinator=None)
    context = {
        "explicit_command": {
            "name": "create",
            "message": "继续完成这部小说",
            "raw_args": "继续完成这部小说",
        },
        "collected_info": {
            "novel_type": "玄幻",
            "theme": "黑暗复仇",
            "protagonist": "林渡",
            "plot_idea": "宗门覆灭后的复仇与重建",
        },
        "conversation_history": [
            {"role": "user", "content": "我要偏黑暗修仙，带合欢宗元素，但不要低俗。"},
            {"role": "assistant", "content": "明白，重点保留危险感、诱惑感和权力斗争。"},
            {"role": "user", "content": "前期不要升级太快，先压抑后爆发。"},
        ],
    }

    requirements = router._build_creation_requirements(context, "继续完成这部小说")

    assert requirements["resume_existing"] is True
    assert "偏黑暗修仙" in requirements["discussion_context"]
    assert "不要低俗" in requirements["discussion_context"]
    assert "前期不要升级太快" in requirements["discussion_context"]


@pytest.mark.asyncio
async def test_chat_workflow_file_download_rejects_paths_outside_project(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    with pytest.raises(Exception) as exc_info:
        await chat_routes.download_chat_workflow_file(path="C:/Windows/system32/drivers/etc/hosts", session_id="copilot")

    assert getattr(exc_info.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_chat_workflow_file_preview_returns_text_content(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    target_file = project_dir / "outline.json"
    target_file.write_text('{"title":"测试大纲"}', encoding="utf-8")
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    response = await chat_routes.preview_chat_workflow_file(path=str(target_file), session_id="copilot")
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["filename"] == "outline.json"
    assert payload["language"] == "json"
    assert "测试大纲" in payload["content"]
