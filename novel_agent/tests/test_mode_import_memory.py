"""Tests for isolated import/memory pipelines of collab and infinite-write modes."""

import json
from pathlib import Path

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
                "name": "Import Project",
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

    project_id = "import001"
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
        yield client, manager
    finally:
        project_manager_module._project_manager = old_manager


def test_collab_import_creates_collab_memory(client_with_project):
    client, manager = client_with_project
    content = (
        "第1章 初遇\n"
        "林风在城门口遇见了失踪多年的师兄，决定连夜调查。\n"
        "第2章 追查\n"
        "两人沿着旧地图进入地窟，发现了与王城相关的秘密。"
    )

    response = client.post(
        "/api/projects/import-novel",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
        data={"merge_mode": "replace"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode"] == "collab_write"
    assert payload["imported_chapters"] >= 2

    collab_memory_path = (
        Path(manager.data_dir)
        / "projects"
        / manager.current_project_id
        / "mode_memory"
        / "collab_write"
        / "memory.json"
    )
    assert collab_memory_path.exists()
    memory_payload = json.loads(collab_memory_path.read_text(encoding="utf-8"))
    assert memory_payload["mode"] == "collab_write"
    assert len(memory_payload.get("chapter_cards", [])) >= 2


def test_infinite_import_creates_isolated_memory(client_with_project):
    client, manager = client_with_project
    content = (
        "第1章 雾夜\n"
        "大雾笼罩古镇，主角在钟楼听见了不该出现的名字。\n"
        "第2章 回声\n"
        "他追着回声走进废弃礼堂，却看见了十年前的自己。"
    )

    response = client.post(
        "/api/continuous-write/import",
        files={"novel_file": ("sample.md", content.encode("utf-8"), "text/markdown")},
        data={"session_id": "sess_import_1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode"] == "infinite_write"
    assert payload["session_id"] == "sess_import_1"
    assert payload["imported_chapters"] >= 2
    assert isinstance(payload.get("chapters"), list)

    infinite_memory_path = (
        Path(manager.data_dir)
        / "projects"
        / manager.current_project_id
        / "mode_memory"
        / "infinite_write"
        / "sess_import_1.json"
    )
    assert infinite_memory_path.exists()
    memory_payload = json.loads(infinite_memory_path.read_text(encoding="utf-8"))
    assert memory_payload["mode"] == "infinite_write"
    assert memory_payload["session_id"] == "sess_import_1"
    assert len(memory_payload.get("chapter_memory", [])) >= 2


def test_outline_save_auto_refreshes_collab_memory(client_with_project):
    client, manager = client_with_project
    outline_payload = [
        {
            "title": "第1章 测试",
            "summary": "角色相遇并提出计划",
            "content": "主角与同伴在港口会合，决定明早出发前往北境。",
        }
    ]

    response = client.post(
        "/api/project-data/outline",
        json={"data": outline_payload},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    collab_memory_path = (
        Path(manager.data_dir)
        / "projects"
        / manager.current_project_id
        / "mode_memory"
        / "collab_write"
        / "memory.json"
    )
    assert collab_memory_path.exists()
    memory_payload = json.loads(collab_memory_path.read_text(encoding="utf-8"))
    assert memory_payload["mode"] == "collab_write"
    assert memory_payload["chapter_count"] == 1


def test_import_rejects_unsupported_format(client_with_project):
    client, _ = client_with_project
    response = client.post(
        "/api/continuous-write/import",
        files={"novel_file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
        data={"session_id": "sess_import_2"},
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
