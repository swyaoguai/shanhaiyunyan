"""Novel-to-script route regression tests."""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.web.app import create_app


def _build_projects_payload(project_id: str) -> dict:
    return {
        "projects": {
            project_id: {
                "id": project_id,
                "name": "Script Project",
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

    project_id = "script001"
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


def test_novel_to_script_import_supports_txt(client_with_project: TestClient):
    content = (
        "第1章 雨夜\n"
        "夜色压着城墙，主角听见巷子尽头有人呼救。\n"
        "第2章 追踪\n"
        "他追入旧巷，发现地上有未干的血迹。"
    )

    response = client_with_project.post(
        "/api/novel-to-script/import",
        files={"novel_file": ("sample.txt", content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["source_type"] == "file"
    assert payload["data"]["chapter_count"] >= 2
    assert payload["data"]["source_filename"] == "sample.txt"
    assert payload["data"]["analysis"]["recommended_mode"] in {"full_text", "chapterwise", "batchwise"}


def test_novel_to_script_state_roundtrip(client_with_project: TestClient):
    payload = {
        "source_text": "测试正文",
        "result": {"formatted_text": "【场景一：测试 - 夜】\n人物：甲\n环境：雨夜\n动作/旁白：测试。"},
    }

    save_resp = client_with_project.post("/api/novel-to-script/state", json={"data": payload})
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True

    get_resp = client_with_project.get("/api/novel-to-script/state")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"] == payload


def test_novel_to_script_convert_returns_formatted_text(monkeypatch, client_with_project: TestClient):
    async def fake_run_prompt(prompt, *, api_config_id="", model=""):
        assert "场景台本" in prompt["user_prompt"]
        return json.dumps(
            {
                "scenes": [
                    {
                        "scene_number": 1,
                        "scene_label": "场景一",
                        "heading": "古桥 - 夜",
                        "characters_text": "江临",
                        "environment_text": "雾气压低了桥面。",
                        "beats": [
                            {"type": "action_narration", "label": "动作/旁白", "text": "江临停在桥心。"},
                            {"type": "character_line", "speaker": "江临", "qualifier": "低声", "text": "我来晚了。"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("novel_agent.web.routes.novel_to_script._run_conversion_prompt", fake_run_prompt)

    response = client_with_project.post(
        "/api/novel-to-script/convert",
        json={
            "source_type": "paste",
            "source_text": "江临在古桥上等一个不会出现的人。",
            "config": {
                "script_style": "scene_block_webnovel_script",
                "convert_mode": "full_text",
                "scene_density": "medium",
                "dialogue_ratio": "medium",
                "keep_voice_style": True,
                "human_name_strategy": "keep_original",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["result"]["scene_count"] == 1
    assert "【场景一：古桥 - 夜】" in payload["data"]["result"]["formatted_text"]
    assert payload["data"]["conversion_plan"]["batch_count"] == 1


def test_novel_to_script_convert_batches_long_text(monkeypatch, client_with_project: TestClient):
    calls = []

    async def fake_run_prompt(prompt, *, api_config_id="", model=""):
        calls.append(prompt["user_prompt"])
        batch_label = len(calls)
        return json.dumps(
            {
                "scenes": [
                    {
                        "scene_number": 1,
                        "scene_label": "场景一",
                        "heading": f"批次{batch_label} - 夜",
                        "characters_text": "主角",
                        "environment_text": "场景环境。",
                        "beats": [
                            {"type": "action_narration", "label": "动作/旁白", "text": f"批次 {batch_label} 开始。"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("novel_agent.web.routes.novel_to_script._run_conversion_prompt", fake_run_prompt)

    long_text = "\n\n".join(
        [f"第{i}章\n" + ("内容" * 7000) for i in range(1, 7)]
    )
    response = client_with_project.post(
        "/api/novel-to-script/convert",
        json={
            "source_type": "paste",
            "source_text": long_text,
            "config": {
                "convert_mode": "auto",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["conversion_plan"]["resolved_mode"] == "batchwise"
    assert payload["conversion_plan"]["batch_count"] >= 2
    assert len(calls) == payload["conversion_plan"]["batch_count"]
    assert payload["result"]["scene_count"] == payload["conversion_plan"]["batch_count"]


def test_novel_to_script_reconvert_batch_replaces_target_batch(monkeypatch, client_with_project: TestClient):
    calls = []

    async def fake_run_prompt(prompt, *, api_config_id="", model=""):
        calls.append(prompt["user_prompt"])
        batch_label = len(calls)
        return json.dumps(
            {
                "scenes": [
                    {
                        "scene_number": 1,
                        "scene_label": "场景一",
                        "heading": f"重转批次{batch_label}",
                        "characters_text": "主角",
                        "environment_text": "场景环境。",
                        "beats": [
                            {"type": "action_narration", "label": "动作/旁白", "text": f"重转 {batch_label}。"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("novel_agent.web.routes.novel_to_script._run_conversion_prompt", fake_run_prompt)

    long_text = "\n\n".join([f"第{i}章\n" + ("内容" * 7000) for i in range(1, 5)])
    initial = client_with_project.post(
        "/api/novel-to-script/convert",
        json={
            "source_type": "paste",
            "source_text": long_text,
            "config": {"convert_mode": "auto"},
        },
    )
    assert initial.status_code == 200
    initial_payload = initial.json()["data"]
    assert initial_payload["result"]["batch_count"] >= 2

    reconvert = client_with_project.post(
        "/api/novel-to-script/reconvert-batch",
        json={
            "source_type": "paste",
            "source_text": long_text,
            "config": {"convert_mode": "auto"},
            "batch_number": 1,
            "existing_batches": initial_payload["result"]["batches"],
        },
    )
    assert reconvert.status_code == 200
    reconvert_payload = reconvert.json()["data"]
    assert reconvert_payload["batch_result"]["batch_number"] == 1
    assert reconvert_payload["result"]["batches"][0]["result"]["scenes"][0]["heading"].startswith("重转批次")


def test_novel_to_script_convert_reports_missing_api_when_not_mocked(monkeypatch, client_with_project: TestClient):
    async def fake_missing_api(prompt, *, api_config_id="", model=""):
        raise HTTPException(status_code=400, detail="未配置可用的 API，请先在设置中完成 API 配置。")

    monkeypatch.setattr("novel_agent.web.routes.novel_to_script._run_conversion_prompt", fake_missing_api)
    response = client_with_project.post(
        "/api/novel-to-script/convert",
        json={
            "source_type": "paste",
            "source_text": "测试文本",
            "config": {},
        },
    )

    assert response.status_code == 400
    assert "未配置可用的 API" in response.json()["detail"]


def test_novel_to_script_export_supports_text_and_docx(client_with_project: TestClient):
    result = {
        "formatted_text": (
            "【场景一：渡口 - 清晨】\n"
            "人物：顾迟\n"
            "环境：江面起雾。\n"
            "动作/旁白：顾迟把船推向水面。"
        )
    }

    txt_resp = client_with_project.post(
        "/api/novel-to-script/export?format=txt",
        json={"title": "渡口", "result": result},
    )
    assert txt_resp.status_code == 200
    assert txt_resp.text.startswith("渡口")
    assert "【场景一：渡口 - 清晨】" in txt_resp.text

    docx_resp = client_with_project.post(
        "/api/novel-to-script/export?format=docx",
        json={"title": "渡口", "result": result},
    )
    assert docx_resp.status_code == 200
    assert docx_resp.content[:2] == b"PK"
