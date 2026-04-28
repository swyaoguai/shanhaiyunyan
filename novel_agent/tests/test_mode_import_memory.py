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



def test_worldbuilding_get_returns_rows_and_raw_data_for_object_payload(client_with_project):
    client, manager = client_with_project
    worldbuilding_payload = {
        "world": {
            "name": "苍穹界",
            "world_type": "仙侠",
            "geography": "九州浮空，云海隔绝",
            "history": "星陨之后宗门并起",
            "factions": [
                {"name": "天衡宗", "description": "镇守天门的古老宗门"},
            ],
        },
        "locations": {
            "赤霄城": {"description": "悬于火山口的贸易城"},
        },
        "items": {
            "镇魂灯": {"description": "可压制心魔的古灯"},
        },
        "events": [
            {"title": "星陨纪元", "description": "旧王朝在流星雨中覆灭"},
        ],
    }
    manager.save_project_data("worldbuilding", worldbuilding_payload)

    response = client.get("/api/project-data/worldbuilding")
    assert response.status_code == 200
    payload = response.json()

    assert payload["raw_data"] == worldbuilding_payload
    assert isinstance(payload["data"], list)
    assert any(row["name"] == "苍穹界" and row["description"] == "仙侠" for row in payload["data"])
    assert any(row["name"] == "地理环境" and "九州浮空" in row["description"] for row in payload["data"])
    assert any(row["name"] == "天衡宗" and "镇守天门" in row["description"] for row in payload["data"])
    assert any(row["name"] == "赤霄城" and "火山口" in row["description"] for row in payload["data"])
    assert any(row["name"] == "镇魂灯" and "心魔" in row["description"] for row in payload["data"])
    assert any(row["name"] == "星陨纪元" and "旧王朝" in row["description"] for row in payload["data"])



def test_worldbuilding_post_preserves_compatible_object_shape(client_with_project):
    client, manager = client_with_project
    existing_payload = {
        "world": {
            "name": "旧世界",
            "world_type": "废土",
        },
        "locations": {
            "黑塔": {"description": "旧时代观测站"},
        },
        "items": {
            "灰烬钥匙": {"description": "通向地下档案库"},
        },
        "events": [
            {"title": "余烬之夜", "description": "天空燃烧整整一夜"},
        ],
    }
    manager.save_project_data("worldbuilding", existing_payload)

    rows = [
        {"name": "世界名称", "description": "赛博灵境"},
        {"name": "力量体系", "description": "灵网接入后可施展术式"},
        {"name": "世界规则", "description": "所有高阶术式都要备案"},
    ]
    response = client.post(
        "/api/project-data/worldbuilding",
        json={"data": rows},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    saved_payload = manager.load_project_data("worldbuilding")
    assert isinstance(saved_payload, dict)
    assert isinstance(saved_payload.get("world"), dict)
    assert saved_payload["world"]["name"] == "赛博灵境"
    assert saved_payload["world"]["world_name"] == "赛博灵境"
    assert saved_payload["world"]["power_system"] == "灵网接入后可施展术式"
    assert "所有高阶术式都要备案" in saved_payload["world"]["rules"]
    assert saved_payload["locations"] == {}
    assert saved_payload["items"] == {}
    assert saved_payload["events"] == []


def test_characters_post_preserves_structured_fields(client_with_project):
    client, manager = client_with_project
    rows = [
        {
            "name": "吴迪",
            "role": "主角",
            "identity": "合欢宗外门弟子",
            "occupation": "杂役弟子",
            "age": "17",
            "description": "抽象系修仙主角",
            "personality": ["抽象", "无厘头"],
            "abilities": ["吞器修炼"],
            "motivation": "摆脱追杀并逆袭",
            "goals": ["活着走出秘境", "在宗门站稳脚跟"],
            "relationships": "苏青禾：暧昧对象\n赵不凡：死对头",
            "tags": ["爽文", "修仙"],
        }
    ]

    response = client.post(
        "/api/project-data/characters",
        json={"data": rows},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    saved_payload = manager.load_project_data("characters")
    assert isinstance(saved_payload, dict)
    assert saved_payload["吴迪"]["identity"] == "合欢宗外门弟子"
    assert saved_payload["吴迪"]["goals"] == ["活着走出秘境", "在宗门站稳脚跟"]

    get_response = client.get("/api/project-data/characters")
    payload = get_response.json()
    assert payload["data"][0]["relationships"]["赵不凡"] == "死对头"
    assert payload["data"][0]["tags"] == ["爽文", "修仙"]


@pytest.mark.parametrize("data_type", ["eventlines", "outline_settings", "detail_settings", "chapter_settings"])
def test_generic_builtin_project_data_round_trip(client_with_project, data_type):
    client, manager = client_with_project
    rows = [
        {"name": "条目一", "description": "说明一", "chapter_number": 1},
        {"name": "条目二", "description": "说明二", "chapter_number": 2},
    ]

    response = client.post(
        f"/api/project-data/{data_type}",
        json={"data": rows},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    saved_payload = manager.load_project_data(data_type)
    assert isinstance(saved_payload, list)
    assert saved_payload[0]["name"] == "条目一"

    get_response = client.get(f"/api/project-data/{data_type}")
    assert get_response.status_code == 200
    payload = get_response.json()
    assert isinstance(payload["data"], list)
    assert payload["data"][1]["name"] == "条目二"
    assert payload["raw_data"][0]["description"] == "说明一"


def test_import_rejects_unsupported_format(client_with_project):
    client, _ = client_with_project
    response = client.post(
        "/api/continuous-write/import",
        files={"novel_file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
        data={"session_id": "sess_import_2"},
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
