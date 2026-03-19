"""辅助记忆模块测试"""

from pathlib import Path

import pytest

from novel_agent.aux_memory import AuxMemoryService


@pytest.fixture
def aux_service(tmp_path: Path) -> AuxMemoryService:
    return AuxMemoryService(data_dir=tmp_path)


def test_category_and_item_crud(aux_service: AuxMemoryService):
    project_id = "proj_1"

    category = aux_service.create_category(
        project_id=project_id,
        name="写作偏好",
        description="测试分类",
        enabled=True,
    )
    assert category.name == "写作偏好"

    created_item = aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="偏好短句",
        details="尽量使用短句，避免冗长描述",
        tags=["文风", "节奏"],
        score=0.7,
    )
    assert created_item.category_id == category.id

    updated_item = aux_service.update_item(
        project_id=project_id,
        item_id=created_item.id,
        updates={"enabled": False, "score": 0.2, "summary": "偏好极短句"},
    )
    assert updated_item is not None
    assert updated_item.enabled is False
    assert updated_item.score == pytest.approx(0.2)
    assert updated_item.summary == "偏好极短句"

    items = aux_service.list_items(project_id=project_id, enabled_only=False)
    assert len(items) == 1

    deleted = aux_service.delete_item(project_id=project_id, item_id=created_item.id)
    assert deleted is True
    assert aux_service.list_items(project_id=project_id) == []


def test_retrieve_and_injection_preview(aux_service: AuxMemoryService):
    project_id = "proj_2"
    category = aux_service.create_category(project_id=project_id, name="风格")

    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="战斗段落节奏快",
        details="战斗场景优先使用短句和动词",
        tags=["战斗", "节奏"],
        score=0.6,
    )
    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="对白避免口号式重复",
        details="对话尽量自然，不要反复喊设定名词",
        tags=["对白"],
        score=0.5,
    )

    rows = aux_service.retrieve(
        project_id=project_id,
        query="战斗 节奏",
        top_k=2,
        mode="fast",
    )
    assert len(rows) == 2
    assert rows[0]["summary"].startswith("战斗")
    assert "match_reason" in rows[0]

    preview = aux_service.build_injection_preview(
        project_id=project_id,
        query="战斗节奏",
        top_k=2,
        mode="fast",
    )
    assert preview["count"] == 2
    assert "辅助记忆注入建议" in preview["prompt_preview"]


def test_history_and_rollback(aux_service: AuxMemoryService):
    project_id = "proj_3"

    category = aux_service.create_category(project_id=project_id, name="禁忌词")
    item = aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="避免套路词",
        details="慎用绝世、逆天等词",
        score=0.8,
    )

    history_before = aux_service.list_history(project_id=project_id, limit=20)
    assert history_before

    aux_service.update_item(
        project_id=project_id,
        item_id=item.id,
        updates={"summary": "避免套路形容词", "score": 0.3},
    )
    changed = aux_service.get_item(project_id=project_id, item_id=item.id)
    assert changed is not None
    assert changed.summary == "避免套路形容词"

    target_history = None
    for row in aux_service.list_history(project_id=project_id, limit=20):
        if row["action"] in {"create_item", "create_category"}:
            target_history = row
            break

    assert target_history is not None
    rollback_result = aux_service.rollback(project_id=project_id, history_id=target_history["id"])
    assert rollback_result is not None


def test_import_resource_creates_items(aux_service: AuxMemoryService):
    project_id = "proj_4"
    category = aux_service.create_category(project_id=project_id, name="习惯")

    payload = aux_service.import_resource_text(
        project_id=project_id,
        source_type="manual",
        content="""
        - 偏好短句
        - 避免直白说教
        - 战斗结束后补一句情绪余波
        """,
        title="手工导入",
        category_id=category.id,
        min_line_chars=2,
        max_items=5,
    )

    assert payload["resource"]["id"].startswith("res_")
    assert len(payload["items"]) == 3


def test_auto_classify_and_category_summary(aux_service: AuxMemoryService):
    project_id = "proj_5"

    category = aux_service.create_category(
        project_id=project_id,
        name="写作偏好",
        description="偏好与习惯",
    )

    item = aux_service.create_item(
        project_id=project_id,
        summary="我的写作偏好是短句推进",
        details="偏好短句和快速节奏",
        tags=["偏好", "节奏"],
        memory_type="preference",
    )

    assert item.category_id == category.id
    refreshed_category = aux_service.get_category(project_id=project_id, category_id=category.id)
    assert refreshed_category is not None
    assert "短句" in refreshed_category.summary or "偏好" in refreshed_category.summary


def test_where_filter_and_config(aux_service: AuxMemoryService):
    project_id = "proj_6"
    category = aux_service.create_category(project_id=project_id, name="约束")

    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="避免口号式对白",
        details="对白应自然",
        score=0.2,
        user_id="u1",
    )
    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="战斗节奏要快",
        details="动词优先",
        score=0.9,
        user_id="u2",
    )

    filtered = aux_service.retrieve(
        project_id=project_id,
        query="节奏",
        where={
            "project_id": project_id,
            "user_id": "u2",
            "category_ids": [category.id],
            "min_score": 0.5,
            "enabled_only": True,
        },
    )
    assert len(filtered) == 1
    assert filtered[0]["summary"].startswith("战斗")

    config = aux_service.update_config(
        project_id=project_id,
        updates={
            "injection_enabled": False,
            "injection_top_k": 3,
            "auto_classify_enabled": False,
        },
    )
    assert config["injection_enabled"] is False
    assert config["injection_top_k"] == 3

    injection = aux_service.get_injection_for_writing(project_id=project_id, query="节奏")
    assert injection["enabled"] is False


def test_bool_coercion_for_config_and_where(aux_service: AuxMemoryService):
    project_id = "proj_6b"
    category = aux_service.create_category(project_id=project_id, name="偏好")

    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="启用条目",
        details="",
        score=0.6,
        enabled=True,
    )
    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="停用条目",
        details="",
        score=0.9,
        enabled=False,
    )

    config = aux_service.update_config(
        project_id=project_id,
        updates={
            "injection_enabled": "false",
            "auto_classify_enabled": "1",
            "auto_summary_enabled": "0",
        },
    )
    assert config["injection_enabled"] is False
    assert config["auto_classify_enabled"] is True
    assert config["auto_summary_enabled"] is False

    rows = aux_service.retrieve(
        project_id=project_id,
        query="条目",
        where={
            "enabled_only": "false",
            "category_ids": [category.id],
        },
    )
    assert len(rows) == 2

    config = aux_service.update_config(
        project_id=project_id,
        updates={
            "injection_top_k": "bad",
            "injection_max_chars": "oops",
            "auto_summary_top_items": "invalid",
        },
    )
    assert config["injection_top_k"] == 6
    assert config["injection_max_chars"] == 1200
    assert config["auto_summary_top_items"] == 5


def test_injection_records_and_preview_where(aux_service: AuxMemoryService):
    project_id = "proj_7"
    category = aux_service.create_category(project_id=project_id, name="战斗")
    aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="战斗节奏快",
        details="使用短句和动词",
        score=0.9,
        user_id="u1",
    )

    preview = aux_service.build_injection_preview(
        project_id=project_id,
        query="战斗节奏",
        where={
            "project_id": project_id,
            "user_id": "u1",
            "category_ids": [category.id],
            "min_score": 0.5,
            "enabled_only": True,
        },
    )
    assert preview["count"] == 1

    aux_service.update_config(project_id, {"injection_enabled": True, "injection_top_k": 5})
    result = aux_service.get_injection_for_writing(
        project_id=project_id,
        query="战斗",
        where={"user_id": "u1"},
    )
    assert result["enabled"] is True

    rows = aux_service.list_injection_records(project_id=project_id, limit=10)
    assert rows
    assert rows[0]["source"] == "writing"


def test_deep_retrieve_rerank_and_reference(aux_service: AuxMemoryService):
    project_id = "proj_8"
    category = aux_service.create_category(project_id=project_id, name="节奏")

    resource_payload = aux_service.import_resource_text(
        project_id=project_id,
        source_type="manual",
        content="- 战斗节奏要快\n- 对白短句推进\n- 情绪余波收束",
        title="深检索测试",
        category_id=category.id,
        min_line_chars=2,
        max_items=5,
        default_score=0.6,
    )
    assert resource_payload["items"]

    rows = aux_service.retrieve(
        project_id=project_id,
        query="战斗 节奏",
        mode="deep",
        top_k=3,
    )
    assert rows
    assert "deep_score" in rows[0]
    assert "reference" in rows[0]
    assert rows[0]["reference"]["item_id"]


def test_item_trace_contains_source_and_refs(aux_service: AuxMemoryService):
    project_id = "proj_9"
    category = aux_service.create_category(project_id=project_id, name="文风")
    imported = aux_service.import_resource_text(
        project_id=project_id,
        source_type="manual",
        content="- 偏好短句\n- 避免口号化",
        title="trace测试",
        category_id=category.id,
        min_line_chars=2,
        max_items=5,
    )

    item_id = imported["items"][0]["id"]
    aux_service.update_config(project_id, {"injection_enabled": True})
    aux_service.get_injection_for_writing(project_id=project_id, query="短句")

    trace = aux_service.get_item_trace(project_id=project_id, item_id=item_id, limit=10)
    assert trace is not None
    assert trace["item"]["id"] == item_id
    assert trace["source_resource"] is not None
    assert trace["ref_count"] >= 0


def test_batch_update_delete_and_clear_items(aux_service: AuxMemoryService):
    project_id = "proj_batch_clear"
    category = aux_service.create_category(project_id=project_id, name="batch")

    item_a = aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="A short note",
        details="",
        memory_type="preference",
        enabled=True,
    )
    item_b = aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="B short note",
        details="",
        memory_type="fact",
        enabled=True,
    )
    item_c = aux_service.create_item(
        project_id=project_id,
        category_id=category.id,
        summary="C keep me",
        details="",
        memory_type="plot",
        enabled=False,
    )

    batch_result = aux_service.batch_update_items_enabled(
        project_id=project_id,
        item_ids=[item_a.id, item_b.id],
        enabled=False,
    )
    assert batch_result["requested"] == 2
    assert batch_result["matched"] == 2
    assert batch_result["updated"] == 2

    deleted_count = aux_service.delete_items(
        project_id=project_id,
        item_ids=[item_b.id],
        action="test_batch_delete",
    )
    assert deleted_count == 1

    clear_result = aux_service.clear_items(
        project_id=project_id,
        category_id=category.id,
        query="short",
        enabled_only=False,
        memory_type="preference",
    )
    assert clear_result["matched"] == 1
    assert clear_result["deleted"] == 1

    remaining_ids = {item.id for item in aux_service.list_items(project_id=project_id, enabled_only=False)}
    assert remaining_ids == {item_c.id}
