"""辅助记忆 API 集成测试"""

import pytest
from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.project_manager import get_project_manager


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def ensure_project():
    pm = get_project_manager()
    if not pm.current_project_id:
        project = pm.create_project("测试项目", "辅助记忆测试")
        pm.switch_project(project.id)
    return pm.current_project_id


def test_aux_memory_category_item_api(client: TestClient):
    ensure_project()

    create_cat = client.post(
        "/api/aux-memory/categories",
        json={
            "name": "测试分类",
            "description": "desc",
            "summary": "sum",
            "enabled": True,
            "user_id": "",
        },
    )
    assert create_cat.status_code == 200
    category_id = create_cat.json()["category"]["id"]

    list_cat = client.get("/api/aux-memory/categories")
    assert list_cat.status_code == 200
    assert any(row["id"] == category_id for row in list_cat.json().get("categories", []))

    create_item = client.post(
        "/api/aux-memory/items",
        json={
            "category_id": category_id,
            "summary": "偏好短句",
            "details": "尽量短句",
            "memory_type": "preference",
            "score": 0.7,
            "enabled": True,
            "tags": ["文风"],
            "user_id": "",
            "source_resource_id": "",
            "extra": {},
        },
    )
    assert create_item.status_code == 200
    item_id = create_item.json()["item"]["id"]

    retrieve = client.post(
        "/api/aux-memory/retrieve",
        json={
            "query": "短句",
            "mode": "fast",
            "top_k": 5,
            "user_id": "",
            "category_ids": [category_id],
        },
    )
    assert retrieve.status_code == 200
    assert retrieve.json()["count"] >= 1

    preview = client.post(
        "/api/aux-memory/injection-preview",
        json={
            "query": "短句",
            "mode": "fast",
            "top_k": 5,
            "user_id": "",
            "category_ids": [category_id],
            "max_chars": 800,
        },
    )
    assert preview.status_code == 200
    assert "prompt_preview" in preview.json()

    patch_item = client.patch(
        f"/api/aux-memory/items/{item_id}",
        json={"enabled": False, "score": 0.2},
    )
    assert patch_item.status_code == 200

    delete_item = client.delete(f"/api/aux-memory/items/{item_id}")
    assert delete_item.status_code == 200

    delete_cat = client.delete(f"/api/aux-memory/categories/{category_id}")
    assert delete_cat.status_code == 200


def test_aux_memory_import_and_history_api(client: TestClient):
    ensure_project()

    create_cat = client.post(
        "/api/aux-memory/categories",
        json={
            "name": "导入分类",
            "description": "",
            "summary": "",
            "enabled": True,
            "user_id": "",
        },
    )
    category_id = create_cat.json()["category"]["id"]

    imported = client.post(
        "/api/aux-memory/resources/import",
        json={
            "content": "- 偏好短句\n- 避免口号化\n- 对白保留潜台词",
            "source_type": "manual",
            "title": "测试导入",
            "user_id": "",
            "category_id": category_id,
            "min_line_chars": 2,
            "max_items": 10,
            "default_score": 0.6,
        },
    )
    assert imported.status_code == 200
    assert imported.json()["imported_count"] >= 2

    history = client.get("/api/aux-memory/history?limit=10")
    assert history.status_code == 200
    rows = history.json().get("history", [])
    assert rows

    rollback = client.post(
        "/api/aux-memory/rollback",
        json={"history_id": rows[-1]["id"]},
    )
    assert rollback.status_code == 200


def test_aux_memory_config_and_where_api(client: TestClient):
    ensure_project()

    cat_res = client.post(
        "/api/aux-memory/categories",
        json={
            "name": "where分类",
            "description": "",
            "summary": "",
            "enabled": True,
            "user_id": "",
        },
    )
    category_id = cat_res.json()["category"]["id"]

    client.post(
        "/api/aux-memory/items",
        json={
            "category_id": category_id,
            "summary": "A用户偏好短句",
            "details": "",
            "memory_type": "preference",
            "score": 0.3,
            "enabled": True,
            "tags": ["短句"],
            "user_id": "uA",
            "source_resource_id": "",
            "extra": {},
        },
    )
    client.post(
        "/api/aux-memory/items",
        json={
            "category_id": category_id,
            "summary": "B用户偏好快节奏",
            "details": "",
            "memory_type": "preference",
            "score": 0.9,
            "enabled": True,
            "tags": ["节奏"],
            "user_id": "uB",
            "source_resource_id": "",
            "extra": {},
        },
    )

    retrieve = client.post(
        "/api/aux-memory/retrieve",
        json={
            "query": "节奏",
            "mode": "fast",
            "top_k": 10,
            "user_id": "",
            "category_ids": [],
            "where": {
                "project_id": ensure_project(),
                "user_id": "uB",
                "category_ids": [category_id],
                "min_score": 0.5,
                "enabled_only": True,
            },
        },
    )
    assert retrieve.status_code == 200
    assert retrieve.json()["count"] >= 1

    get_config = client.get("/api/aux-memory/config")
    assert get_config.status_code == 200
    assert "config" in get_config.json()

    patch_config = client.patch(
        "/api/aux-memory/config",
        json={
            "injection_enabled": False,
            "injection_mode": "fast",
            "injection_top_k": 4,
            "auto_classify_enabled": True,
            "auto_summary_enabled": True,
            "auto_summary_top_items": 6,
        },
    )
    assert patch_config.status_code == 200
    assert patch_config.json()["config"]["injection_enabled"] is False


def test_aux_memory_injection_records_api(client: TestClient):
    project_id = ensure_project()

    cat_res = client.post(
        "/api/aux-memory/categories",
        json={"name": "记录分类", "description": "", "summary": "", "enabled": True, "user_id": ""},
    )
    category_id = cat_res.json()["category"]["id"]

    client.post(
        "/api/aux-memory/items",
        json={
            "category_id": category_id,
            "summary": "命中记录测试",
            "details": "",
            "memory_type": "preference",
            "score": 0.9,
            "enabled": True,
            "tags": ["记录"],
            "user_id": "",
            "source_resource_id": "",
            "extra": {},
        },
    )

    client.patch(
        "/api/aux-memory/config",
        json={"injection_enabled": True, "injection_top_k": 5},
    )

    preview = client.post(
        "/api/aux-memory/injection-preview",
        json={
            "query": "命中",
            "mode": "fast",
            "top_k": 5,
            "user_id": "",
            "category_ids": [category_id],
            "max_chars": 600,
            "where": {"project_id": project_id},
        },
    )
    assert preview.status_code == 200

    # 真正触发写作注入记录：通过 service 写入（API 无单独写入接口）
    from novel_agent.aux_memory import get_aux_memory_service
    service = get_aux_memory_service()
    service.get_injection_for_writing(project_id=project_id, query="命中测试")

    records = client.get("/api/aux-memory/injection-records?limit=10")
    assert records.status_code == 200
    assert len(records.json().get("records", [])) >= 1


def test_aux_memory_deep_and_trace_api(client: TestClient):
    project_id = ensure_project()

    cat_res = client.post(
        "/api/aux-memory/categories",
        json={"name": "trace分类", "description": "", "summary": "", "enabled": True, "user_id": ""},
    )
    category_id = cat_res.json()["category"]["id"]

    imported = client.post(
        "/api/aux-memory/resources/import",
        json={
            "content": "- 战斗节奏要快\n- 对白短句推进",
            "source_type": "manual",
            "title": "trace导入",
            "user_id": "",
            "category_id": category_id,
            "min_line_chars": 2,
            "max_items": 10,
            "default_score": 0.7,
        },
    )
    assert imported.status_code == 200
    items = imported.json().get("items", [])
    assert items
    item_id = items[0]["id"]

    deep = client.post(
        "/api/aux-memory/retrieve",
        json={
            "query": "战斗 节奏",
            "mode": "deep",
            "top_k": 5,
            "user_id": "",
            "category_ids": [category_id],
            "where": {"project_id": project_id},
        },
    )
    assert deep.status_code == 200
    assert deep.json().get("count", 0) >= 1

    from novel_agent.aux_memory import get_aux_memory_service
    service = get_aux_memory_service()
    service.update_config(project_id=project_id, updates={"injection_enabled": True})
    service.get_injection_for_writing(project_id=project_id, query="战斗节奏")

    trace = client.post(
        "/api/aux-memory/trace",
        json={"item_id": item_id, "limit": 20},
    )
    assert trace.status_code == 200
    trace_data = trace.json().get("trace", {})
    assert trace_data.get("item", {}).get("id") == item_id
    assert "injection_refs" in trace_data


def test_aux_memory_batch_clear_and_limit_api(client: TestClient):
    ensure_project()

    cat_res = client.post(
        "/api/aux-memory/categories",
        json={"name": "batch-clear", "description": "", "summary": "", "enabled": True, "user_id": ""},
    )
    assert cat_res.status_code == 200
    category_id = cat_res.json()["category"]["id"]

    created_ids = []
    for idx in range(3):
        created = client.post(
            "/api/aux-memory/items",
            json={
                "category_id": category_id,
                "summary": f"batch item {idx}",
                "details": "",
                "memory_type": "preference" if idx < 2 else "plot",
                "score": 0.6,
                "enabled": True,
                "tags": ["batch"],
                "user_id": "",
                "source_resource_id": "",
                "extra": {},
            },
        )
        assert created.status_code == 200
        created_ids.append(created.json()["item"]["id"])

    list_res = client.get("/api/aux-memory/items?limit=1&offset=0")
    assert list_res.status_code == 200
    payload = list_res.json()
    assert payload["limit"] == 1
    assert payload["total"] >= 3
    assert len(payload["items"]) == 1

    batch_disable = client.post(
        "/api/aux-memory/items/batch-update",
        json={"item_ids": created_ids[:2], "enabled": False},
    )
    assert batch_disable.status_code == 200
    batch_body = batch_disable.json()
    assert batch_body["updated"] == 2
    assert batch_body["matched"] == 2

    batch_delete = client.post(
        "/api/aux-memory/items/batch-delete",
        json={"item_ids": [created_ids[1]]},
    )
    assert batch_delete.status_code == 200
    assert batch_delete.json()["deleted"] == 1

    clear_res = client.post(
        "/api/aux-memory/items/clear",
        json={
            "category_id": category_id,
            "query": "batch item",
            "user_id": None,
            "enabled_only": False,
            "memory_type": "preference",
        },
    )
    assert clear_res.status_code == 200
    clear_body = clear_res.json()
    assert clear_body["matched"] >= 1
    assert clear_body["deleted"] >= 1
