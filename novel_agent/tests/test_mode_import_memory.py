"""Tests for isolated import/memory pipelines of collab and infinite-write modes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.web.app import create_app
from novel_agent.worldbuilding_persistence import persist_worldbuilding_project_data
from novel_agent.library_service import get_library_service


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


def test_collab_import_replace_preserves_source_chapter_numbers(client_with_project):
    client, manager = client_with_project
    manager.save_project_data(
        "chapters",
        [{"chapter_number": index, "title": f"旧第{index}章", "content": "旧正文"} for index in range(1, 124)],
    )
    content = (
        "第123章 雨夜\n"
        "林风在雨夜遇见旧友，决定连夜进城。\n"
        "第124章 异象\n"
        "城门口突然出现异光，所有人都停下脚步。"
    )

    response = client.post(
        "/api/projects/import-novel",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
        data={"merge_mode": "replace"},
    )

    assert response.status_code == 200
    saved = manager.load_project_data("chapters")
    assert [chapter["chapter_number"] for chapter in saved] == [123, 124]
    assert [chapter["title"] for chapter in saved] == ["雨夜", "异象"]


def test_collab_import_append_offsets_colliding_chapter_numbers(client_with_project):
    client, manager = client_with_project
    manager.save_project_data(
        "chapters",
        [
            {"chapter_number": 1, "title": "旧第1章", "content": "旧正文"},
            {"chapter_number": 2, "title": "旧第2章", "content": "旧正文"},
        ],
    )
    content = (
        "第1章 雨夜\n"
        "林风在雨夜遇见旧友，决定连夜进城。\n"
        "第2章 异象\n"
        "城门口突然出现异光，所有人都停下脚步。"
    )

    response = client.post(
        "/api/projects/import-novel",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
        data={"merge_mode": "append"},
    )

    assert response.status_code == 200
    saved = manager.load_project_data("chapters")
    assert [chapter["chapter_number"] for chapter in saved] == [1, 2, 3, 4]
    assert [chapter["title"] for chapter in saved[-2:]] == ["雨夜", "异象"]


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


def test_infinite_import_preserves_source_chapter_numbers(client_with_project):
    client, _manager = client_with_project
    content = (
        "第123章 雨夜\n"
        "林风在雨夜遇见旧友，决定连夜进城。\n"
        "第124章 异象\n"
        "城门口突然出现异光，所有人都停下脚步。"
    )

    response = client.post(
        "/api/continuous-write/import",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
        data={"session_id": "sess_import_123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [chapter["chapter_number"] for chapter in payload["chapters"]] == [123, 124]
    assert payload["current_chapter"] == 124


def test_infinite_import_does_not_double_chapter_prefixed_body_lines(client_with_project):
    client, _manager = client_with_project
    content = "\n".join(
        f"第{index}章 标题{index}\n"
        f"第{index}章正文里主角继续调查，并发现新的线索。\n"
        "后续正文继续展开。"
        for index in range(1, 124)
    )

    response = client.post(
        "/api/continuous-write/import",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
        data={"session_id": "sess_import_no_double"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported_chapters"] == 123
    assert payload["current_chapter"] == 123
    assert payload["chapters"][-1]["chapter_number"] == 123
    assert payload["chapters"][-1]["title"] == "标题123"


def test_chapters_save_auto_refreshes_collab_memory(client_with_project):
    client, manager = client_with_project
    outline_payload = [
        {
            "title": "第1章 测试",
            "summary": "角色相遇并提出计划",
            "content": "主角与同伴在港口会合，决定明早出发前往北境。",
        }
    ]

    response = client.post(
        "/api/project-data/chapters",
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


def test_worldbuilding_get_recovers_from_context_when_project_file_missing(client_with_project):
    client, manager = client_with_project
    manager.save_project_data("worldbuilding", [])
    manager.get_project_data_path("worldbuilding").unlink(missing_ok=True)
    project_dir = manager.get_current_project_dir()
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "context.json").write_text(
        json.dumps(
            {
                "contexts": {
                    "world": {
                        "key": "world",
                        "value": {
                            "world_name": "玄源大陆",
                            "world_type": "东方玄幻",
                            "core_concept": "废柴少年觉醒禁忌血脉。",
                        },
                        "category": "world",
                    }
                },
                "history": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    response = client.get("/api/project-data/worldbuilding")
    assert response.status_code == 200
    payload = response.json()

    assert any(row["name"] == "玄源大陆" and row["description"] == "东方玄幻" for row in payload["data"])
    saved_payload = manager.load_project_data("worldbuilding")
    assert saved_payload["world"]["name"] == "玄源大陆"
    assert saved_payload["world"]["world_name"] == "玄源大陆"
    assert saved_payload["world"]["core_concept"] == "废柴少年觉醒禁忌血脉。"


def test_worldbuilding_persistence_normalizes_and_preserves_extra_fields(client_with_project):
    _client, manager = client_with_project
    manager.save_project_data(
        "worldbuilding",
        {
            "world": {"name": "旧世界", "world_type": "废土"},
            "locations": {"黑塔": {"description": "旧时代观测站"}},
        },
    )

    saved_payload = persist_worldbuilding_project_data(
        {
            "world": {
                "world_name": "玄源大陆",
                "core_concept": "禁忌血脉重塑秩序。",
            }
        },
        project_manager=manager,
    )

    assert saved_payload["world"]["name"] == "玄源大陆"
    assert saved_payload["world"]["world_name"] == "玄源大陆"
    assert saved_payload["world"]["world_type"] == "废土"
    assert saved_payload["world"]["core_concept"] == "禁忌血脉重塑秩序。"
    assert saved_payload["locations"]["黑塔"]["description"] == "旧时代观测站"


def test_worldbuilding_persistence_recovers_name_from_raw_content(client_with_project):
    _client, manager = client_with_project

    saved_payload = persist_worldbuilding_project_data(
        {
            "world": {
                "raw_content": "```json\n{\"world_name\": \"合欢宗秘境\", \"world_type\": \"玄幻修仙\", \"rules\": [\"器物可被吸收\"]}\n```"
            }
        },
        project_manager=manager,
    )

    assert saved_payload["world"]["name"] == "合欢宗秘境"
    assert saved_payload["world"]["world_name"] == "合欢宗秘境"
    assert saved_payload["world"]["world_type"] == "玄幻修仙"


def test_worldbuilding_persistence_tolerates_fullwidth_json_commas(client_with_project):
    _client, manager = client_with_project

    saved_payload = persist_worldbuilding_project_data(
        {
            "world": {
                "raw_content": (
                    '{"world_name": "玄天大陆", "world_type": "玄幻", '
                    '"culture": {"languages": ["大陆通用语"，"合欢宗暗语"]}}'
                )
            }
        },
        project_manager=manager,
    )

    assert saved_payload["world"]["name"] == "玄天大陆"
    assert saved_payload["world"]["world_type"] == "玄幻"
    assert "requirements" not in saved_payload["world"]


def test_worldbuilding_get_suppresses_embedded_json_requirements_row(client_with_project):
    client, manager = client_with_project
    manager.save_project_data(
        "worldbuilding",
        {
            "world": {
                "name": "玄天大陆",
                "world_type": "玄幻",
                "requirements": '{"world_name": "玄天大陆", "power_system": {"name": "噬器魔功"}}',
                "power_system": {"name": "噬器魔功"},
            }
        },
    )

    response = client.get("/api/project-data/worldbuilding")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert any(row["name"] == "玄天大陆" for row in rows)
    assert not any(row["name"] == "创作要求" for row in rows)


def test_worldbuilding_get_shows_raw_content_as_named_row(client_with_project):
    client, manager = client_with_project
    manager.save_project_data(
        "worldbuilding",
        {"world": {"raw_content": "未解析但可展示的世界观正文"}},
    )

    response = client.get("/api/project-data/worldbuilding")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert rows[0]["name"] == "世界观设定"
    assert rows[0]["kind"] == "raw_content"


def test_builtin_project_data_prefers_json_file_over_wiki_projection(client_with_project):
    client, manager = client_with_project
    manager.save_project_data(
        "characters",
        [{"name": "文件角色", "role": "主角", "description": "来自 characters.json"}],
    )
    get_library_service(manager.get_current_project_dir()).upsert_from_legacy(
        "characters",
        [{"name": "Wiki角色", "role": "配角", "description": "来自 wiki"}],
    )

    response = client.get("/api/project-data/characters")
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]]
    assert "文件角色" in names
    assert "Wiki角色" not in names


@pytest.mark.parametrize(
    "data_type",
    [
        "outline",
        "chapters",
        "worldbuilding",
        "characters",
        "items",
        "eventlines",
        "outline_settings",
        "detail_settings",
        "chapter_settings",
        "chapter_summary",
    ],
)
def test_empty_builtin_project_data_file_prevents_recovery_and_wiki_fallback(client_with_project, data_type):
    client, manager = client_with_project
    project_dir = manager.get_current_project_dir()
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "context.json").write_text(
        json.dumps(
            {
                "contexts": {
                    "world": {
                        "key": "world",
                        "value": {
                            "world_name": "旧世界",
                            "world_type": "旧类型",
                        },
                        "category": "world",
                    },
                    "outline": {
                        "key": "outline",
                        "value": {
                            "chapters": [
                                {"title": "旧大纲", "summary": "应被删除态屏蔽。"}
                            ]
                        },
                        "category": "plot",
                    },
                    "characters": {
                        "key": "characters",
                        "value": [{"name": "旧角色", "description": "应被删除态屏蔽。"}],
                        "category": "character",
                    },
                    "chapter_1_summary": {
                        "key": "chapter_1_summary",
                        "value": "旧正文摘要应被删除态屏蔽。",
                        "category": "chapter",
                    },
                },
                "history": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "001_旧正文.md").write_text("旧正文内容应被删除态屏蔽。", encoding="utf-8")
    svc = get_library_service(project_dir)
    svc.upsert_from_legacy("outline", [{"title": "Wiki大纲", "summary": "应被屏蔽"}])
    svc.upsert_from_legacy("characters", [{"name": "Wiki角色", "description": "应被屏蔽"}])
    svc.upsert_from_legacy("worldbuilding", {"world": {"name": "Wiki世界观", "content": "应被屏蔽"}})
    manager.save_project_data(data_type, [])

    response = client.get(f"/api/project-data/{data_type}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["data"] == []
    assert manager.load_project_data(data_type) == []


def test_outline_get_recovers_from_context_when_project_file_missing(client_with_project):
    client, manager = client_with_project
    manager.save_project_data("outline", [])
    manager.get_project_data_path("outline").unlink(missing_ok=True)
    project_dir = manager.get_current_project_dir()
    (project_dir / "context.json").write_text(
        json.dumps(
            {
                "contexts": {
                    "outline": {
                        "key": "outline",
                        "value": {
                            "title": "旧城录",
                            "chapters": [
                                {"title": "第一章 归来", "summary": "主角回到旧城。"}
                            ],
                        },
                        "category": "plot",
                    }
                },
                "history": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    response = client.get("/api/project-data/outline")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["title"] == "第一章 归来"
    assert "旧城" in data[0]["summary"]
    assert manager.load_project_data("outline")[0]["title"] == "第一章 归来"


def test_chapters_get_recovers_chapter_files_as_body_content(client_with_project):
    client, manager = client_with_project
    manager.save_project_data("chapters", [])
    (manager.get_project_data_path("chapters")).unlink(missing_ok=True)
    chapters_dir = manager.get_current_project_dir() / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "001_第一章_归来.md").write_text("第一章正文内容", encoding="utf-8")

    response = client.get("/api/project-data/chapters")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["title"] == "第一章_归来"
    assert data[0]["content"] == "第一章正文内容"
    assert manager.load_project_data("chapters")[0]["content"] == "第一章正文内容"



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
            "inventory": ["玄铁令"],
            "development_history": [{"chapter_number": 2, "event_type": "ability", "title": "吞器入门", "description": "开始掌握吞器修炼"}],
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
    assert saved_payload["吴迪"]["inventory"] == ["玄铁令"]
    assert saved_payload["吴迪"]["development_history"][0]["title"] == "吞器入门"

    get_response = client.get("/api/project-data/characters")
    payload = get_response.json()
    assert payload["data"][0]["relationships"]["赵不凡"] == "死对头"
    assert payload["data"][0]["tags"] == ["爽文", "修仙"]
    assert payload["data"][0]["inventory"] == ["玄铁令"]


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
