"""会话ID安全测试"""

from pathlib import Path

from fastapi.testclient import TestClient

from novel_agent.agents.chat_session_store import ChatSessionStore, ChatSessionState
from novel_agent.agents.session_store import SessionStore, SessionState
from novel_agent.web.app import create_app


def test_session_store_rejects_path_traversal_id(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")

    state = SessionState(session_id="..\\..\\escape", project_id="default")
    assert store.save(state) is False
    assert store.load("..\\..\\escape", "default") is None
    assert store.exists("..\\..\\escape", "default") is False
    assert store.delete("..\\..\\escape", "default") is False


def test_chat_session_store_rejects_path_traversal_id(tmp_path: Path):
    store = ChatSessionStore(storage_dir=tmp_path / "chat_sessions")

    state = ChatSessionState(session_id="..\\..\\escape", project_id="default")
    assert store.save(state) is False
    assert store.load("..\\..\\escape", "default") is None
    assert store.delete("..\\..\\escape", "default") is False


def test_chat_api_rejects_invalid_session_id():
    client = TestClient(create_app())

    response = client.post(
        "/api/chat/start",
        params={"session_id": "../escape"},
    )

    assert response.status_code == 400
    assert "session_id" in response.json().get("detail", "")


def test_chat_history_api_rejects_invalid_session_id():
    client = TestClient(create_app())

    response = client.get(
        "/api/chat/history",
        params={"session_id": "../escape"},
    )

    assert response.status_code == 400
    assert "session_id" in response.json().get("detail", "")


def test_chat_history_and_reset_api_roundtrip(tmp_path: Path, monkeypatch):
    from novel_agent.agents import chat_session_store as chat_session_store_module
    from novel_agent.project_manager import get_project_manager
    from novel_agent.web.routes import chat as chat_routes_module

    isolated_store = ChatSessionStore(storage_dir=tmp_path / "chat_sessions")
    monkeypatch.setattr(chat_session_store_module, "_chat_session_store", isolated_store, raising=False)
    chat_routes_module.chat_sessions.clear()
    chat_routes_module._chat_session_locks.clear()

    app = create_app()
    with TestClient(app) as client:
        project_id = get_project_manager().current_project_id or ""

        seeded = ChatSessionState(
            session_id="copilot",
            project_id=project_id,
            conversation_history=[
                {"role": "assistant", "content": "你好，欢迎继续创作。"},
                {"role": "user", "content": "帮我续写下一段。"},
            ],
            collected_info={},
        )
        assert isolated_store.save(seeded) is True

        history_resp = client.get("/api/chat/history", params={"session_id": "copilot"})
        assert history_resp.status_code == 200
        history_payload = history_resp.json()
        assert history_payload["session_id"] == "copilot"
        assert history_payload["count"] == 2
        assert history_payload["history"][0]["role"] == "assistant"
        assert history_payload["history"][1]["role"] == "user"

        reset_resp = client.post("/api/chat/reset", params={"session_id": "copilot"})
        assert reset_resp.status_code == 200
        reset_payload = reset_resp.json()
        assert reset_payload["success"] is True
        assert reset_payload["session_id"] == "copilot"

        history_after_reset = client.get("/api/chat/history", params={"session_id": "copilot"})
        assert history_after_reset.status_code == 200
        assert history_after_reset.json()["count"] == 0


def test_chat_sessions_list_create_delete_roundtrip(tmp_path: Path, monkeypatch):
    from novel_agent.agents import chat_session_store as chat_session_store_module
    from novel_agent.project_manager import get_project_manager
    from novel_agent.web.routes import chat as chat_routes_module

    isolated_store = ChatSessionStore(storage_dir=tmp_path / "chat_sessions")
    monkeypatch.setattr(chat_session_store_module, "_chat_session_store", isolated_store, raising=False)
    chat_routes_module.chat_sessions.clear()
    chat_routes_module._chat_session_locks.clear()

    app = create_app()
    with TestClient(app) as client:
        project_id = get_project_manager().current_project_id or ""
        state = ChatSessionState(
            session_id="copilot_demo",
            project_id=project_id,
            conversation_history=[
                {"role": "user", "content": "测试会话列表"},
                {"role": "assistant", "content": "收到"},
            ],
            collected_info={},
        )
        assert isolated_store.save(state) is True

        list_resp = client.get("/api/chat/sessions")
        assert list_resp.status_code == 200
        list_payload = list_resp.json()
        assert list_payload["count"] >= 1
        assert any(s["session_id"] == "copilot_demo" for s in list_payload["sessions"])

        create_resp = client.post("/api/chat/sessions")
        assert create_resp.status_code == 200
        created_payload = create_resp.json()
        created_id = created_payload["session_id"]
        assert created_id

        delete_resp = client.delete(f"/api/chat/sessions/{created_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["success"] is True

        list_after_delete = client.get("/api/chat/sessions")
        assert list_after_delete.status_code == 200
        assert all(s["session_id"] != created_id for s in list_after_delete.json()["sessions"])
