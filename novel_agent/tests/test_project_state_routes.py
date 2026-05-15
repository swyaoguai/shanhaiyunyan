"""Project state route regression tests."""

import json

import pytest
from fastapi.testclient import TestClient

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.web.app import create_app


def _build_projects_payload(project_id: str) -> dict:
    return {
        "projects": {
            project_id: {
                "id": project_id,
                "name": "State Project",
                "description": "",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "word_count": 0,
                "chapter_count": 0,
            }
        },
        "current_project_id": project_id,
    }


@pytest.fixture()
def client_with_project(tmp_path):
    app = create_app()
    client = TestClient(app)

    project_id = "state001"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "projects.json").write_text(
        json.dumps(_build_projects_payload(project_id), ensure_ascii=False),
        encoding="utf-8",
    )

    manager = ProjectManager(data_dir=data_dir)
    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        yield client
    finally:
        project_manager_module._project_manager = old_manager


def test_project_state_crud(client_with_project: TestClient):
    payload = [
        {"id": "db-custom-1", "key": "custom_world", "name": "自定义设定", "icon": "ri-folder-line", "builtin": False}
    ]

    save_resp = client_with_project.post(
        "/api/project-state/knowledge_categories",
        json={"data": payload},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True

    get_resp = client_with_project.get("/api/project-state/knowledge_categories")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"] == payload

    delete_resp = client_with_project.delete("/api/project-state/knowledge_categories")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    get_after_delete = client_with_project.get("/api/project-state/knowledge_categories")
    assert get_after_delete.status_code == 200
    assert get_after_delete.json()["data"] is None


def test_create_project_api_accepts_custom_novel_type(client_with_project: TestClient):
    response = client_with_project.post(
        "/api/projects",
        json={
            "name": "自定义分类项目",
            "description": "分类名称会进入项目元数据",
            "novel_type": "修仙副本爽文",
        },
    )

    assert response.status_code == 200
    project = response.json()["project"]
    assert project["name"] == "自定义分类项目"
    assert project["novel_type"] == "修仙副本爽文"

    list_response = client_with_project.get("/api/projects")
    assert list_response.status_code == 200
    projects = list_response.json()["projects"]
    assert any(item["novel_type"] == "修仙副本爽文" for item in projects)


def test_project_state_chat_auto_save_toggle_crud(client_with_project: TestClient):
    payload = {"enabled": True}

    save_resp = client_with_project.post(
        "/api/project-state/copilot_chat_auto_save",
        json={"data": payload},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True

    get_resp = client_with_project.get("/api/project-state/copilot_chat_auto_save")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"] == payload


def test_chapter_summary_config_roundtrip(client_with_project: TestClient):
    initial_resp = client_with_project.get("/api/chapter-summary-config")
    assert initial_resp.status_code == 200
    assert initial_resp.json()["auto_summary_enabled"] is False

    save_resp = client_with_project.post(
        "/api/chapter-summary-config",
        json={"auto_summary_enabled": True},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True
    assert save_resp.json()["auto_summary_enabled"] is True

    get_resp = client_with_project.get("/api/chapter-summary-config")
    assert get_resp.status_code == 200
    assert get_resp.json()["auto_summary_enabled"] is True


def test_chapter_knowledge_sync_config_roundtrip(client_with_project: TestClient):
    initial_resp = client_with_project.get("/api/chapter-knowledge-sync-config")
    assert initial_resp.status_code == 200
    assert initial_resp.json()["auto_vector_sync_enabled"] is True

    save_resp = client_with_project.post(
        "/api/chapter-knowledge-sync-config",
        json={
            "auto_vector_sync_enabled": False,
            "sync_on_edit_enabled": False,
            "sync_on_delete_enabled": True,
        },
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True
    assert save_resp.json()["auto_vector_sync_enabled"] is False
    assert save_resp.json()["sync_on_edit_enabled"] is False

    get_resp = client_with_project.get("/api/chapter-knowledge-sync-config")
    assert get_resp.status_code == 200
    assert get_resp.json()["sync_on_delete_enabled"] is True


def test_project_state_batch_set_and_get(client_with_project: TestClient):
    states = {
        "knowledge_data_eventlines": [{"id": "1", "name": "事件A"}],
        "copilot_chat": {"messages": [{"role": "user", "content": "hello"}], "lastUpdated": 123},
    }

    batch_set_resp = client_with_project.post(
        "/api/project-state/batch-set",
        json={"states": states},
    )
    assert batch_set_resp.status_code == 200
    assert set(batch_set_resp.json()["saved_keys"]) == set(states.keys())

    batch_get_resp = client_with_project.post(
        "/api/project-state/batch-get",
        json={"keys": list(states.keys())},
    )
    assert batch_get_resp.status_code == 200
    assert batch_get_resp.json()["states"] == states


def test_project_state_rejects_invalid_key(client_with_project: TestClient):
    single_resp = client_with_project.post(
        "/api/project-state/invalid.key",
        json={"data": {"x": 1}},
    )
    assert single_resp.status_code == 400
    assert "Invalid project state key" in single_resp.json()["error"]

    batch_get_resp = client_with_project.post(
        "/api/project-state/batch-get",
        json={"keys": ["invalid.key"]},
    )
    assert batch_get_resp.status_code == 400
    assert "Invalid project state key" in batch_get_resp.json()["error"]

    batch_set_resp = client_with_project.post(
        "/api/project-state/batch-set",
        json={"states": {"invalid.key": {"x": 1}}},
    )
    assert batch_set_resp.status_code == 400
    assert "Invalid project state key" in batch_set_resp.json()["error"]
