"""会话ID安全测试"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_agent.agents.chat_session_store import ChatSessionStore, ChatSessionState
from novel_agent.agents.session_store import SessionStore, SessionState, SessionStoreLoadError
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


def test_session_store_load_returns_detached_copy(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    state = SessionState(
        session_id="session1",
        project_id="project1",
        chapters=[{"chapter_number": 1, "title": "原始标题", "content": "正文", "summary": "摘要", "word_count": 2}],
        dead_characters=["沈夜"],
    )

    assert store.save(state) is True

    loaded = store.load("session1", "project1")
    assert loaded is not None
    loaded.chapters[0]["title"] = "被污染"
    loaded.dead_characters.append("新角色")

    reloaded = store.load("session1", "project1")
    assert reloaded is not None
    assert reloaded.chapters[0]["title"] == "原始标题"
    assert reloaded.dead_characters == ["沈夜"]


def test_session_store_save_does_not_fake_commit_on_atomic_write_failure(tmp_path: Path, monkeypatch):
    from novel_agent.agents import session_store as session_store_module

    store = SessionStore(storage_dir=tmp_path / "sessions")
    state = SessionState(session_id="session1", project_id="project1")
    old_updated_at = state.updated_at
    old_version = state.version

    def _raise_io_error(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(session_store_module, "atomic_write_json", _raise_io_error)

    assert store.save(state) is False
    assert state.updated_at == old_updated_at
    assert state.version == old_version
    assert store._cache == {}
    assert store.load("session1", "project1") is None


def test_session_store_delete_and_clear_project_cache_keep_lock_identity(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    lock = store._get_lock("session1", "project1")
    async_lock = store._get_async_lock("session1", "project1")

    assert store.save(SessionState(session_id="session1", project_id="project1")) is True
    assert store.delete("session1", "project1") is True
    assert store._get_lock("session1", "project1") is lock
    assert store._get_async_lock("session1", "project1") is async_lock

    assert store.save(SessionState(session_id="session1", project_id="project1")) is True
    assert store.clear_project_cache("project1") == 1
    assert store._get_lock("session1", "project1") is lock
    assert store._get_async_lock("session1", "project1") is async_lock


def test_session_store_create_or_restore_raises_on_corrupt_session_file(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    path = store._get_session_path("session1", "project1")
    path.write_text("{bad json", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    with pytest.raises(SessionStoreLoadError):
        store.create_or_restore("session1", "project1", story_beginning="新的开头")

    assert path.read_text(encoding="utf-8") == before


def test_session_store_invalidates_stale_cache_across_store_instances(tmp_path: Path):
    storage_dir = tmp_path / "sessions"
    store_a = SessionStore(storage_dir=storage_dir)
    store_b = SessionStore(storage_dir=storage_dir)

    state = SessionState(session_id="session1", project_id="project1", story_beginning="旧开头")
    assert store_a.save(state) is True

    cached = store_b.load("session1", "project1")
    assert cached is not None
    assert cached.story_beginning == "旧开头"

    updated = store_a.load("session1", "project1")
    assert updated is not None
    updated.story_beginning = "新开头"
    updated.dead_characters.append("阿九")
    assert store_a.save(updated) is True

    refreshed = store_b.load("session1", "project1")
    assert refreshed is not None
    assert refreshed.story_beginning == "新开头"
    assert refreshed.dead_characters == ["阿九"]
