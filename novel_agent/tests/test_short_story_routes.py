"""Tests for short-story routes and router guidance."""

import asyncio
import io
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from novel_agent.agents.router_agent import RouterAgent, UserIntent
from novel_agent.web.app import create_app
from novel_agent.web.routes import short_story as short_story_routes


def _fake_prompt_output(prompt: str, api_config_id: str = "", model: str = "") -> str:
    if "短篇小说创作输入分析师" in prompt:
        return """{
  "summary": "输入包含词条与悬疑创作意图，适合先生成不同故事路数的融合方案。",
  "confidence": 0.93,
  "detected_material_types": ["keywords", "inspiration"],
  "keywords": ["旧相机", "失约", "雨夜"],
  "genre_hint": "悬疑惊悚",
  "borrowed_highlights": ["雨夜钩子", "照片反转"],
  "constraints": [],
  "warnings": []
}"""
    if "生成 3 个“不同故事路数”的融合方案" in prompt:
        return """【方案一】
标题：暗房追索
路数：悬疑追查
钩子：失约的人藏进最后一张照片里。
借鉴骨架：雨夜回城→线索浮现→照片反转
内容换新：摄影师与旧城调查线全部换新
故事梗概：周岚回城后在旧相机底片里看到失约真相。

【方案二】
标题：迟来赴约
路数：情感反转
钩子：她等来的人没出现，却等来了一卷会说话的底片。
借鉴骨架：重逢未成→误会加深→真相和解
内容换新：人物关系与矛盾来源换新
故事梗概：旧底片把多年误会拉回雨夜。

【方案三】
标题：雨夜旧案
路数：暗黑揭秘
钩子：每按下一次快门，都逼近一段被掩埋的旧案。
借鉴骨架：回城→追查→揭秘
内容换新：案件背景和关键事件换新
故事梗概：相机成为旧案线索的入口。"""
    if "生成 5 条风格各异的故事导语" in prompt:
        if "更偏悬疑" in prompt:
            return """【导语一】（悬疑向）
更偏悬疑的第一条。

【导语二】（悬疑向）
更偏悬疑的第二条。

【导语三】（悬疑向）
更偏悬疑的第三条。

【导语四】（悬疑向）
更偏悬疑的第四条。

【导语五】（悬疑向）
更偏悬疑的第五条。"""
        return """【导语一】（悬疑向）
雨夜里，周岚带着旧相机回城，发现顾原再度失约。

【导语二】（温情向）
她在车站等了很多年，只等来一卷过期底片。

【导语三】（反转向）
失约的人从未离开，只是藏进了相机的最后一张照片里。

【导语四】（暗黑向）
那台旧相机每拍一次，都会逼近一段被掩埋的旧案。

【导语五】（治愈向）
雨停后，周岚终于明白，那次失约是另一种守护。"""
    if "生成一份详细的短篇小说章节大纲" in prompt:
        return """## 角色表
周岚 | 摄影师 | 顾原的旧友
顾原 | 记者 | 周岚多年未见的朋友

## 时间线
故事发生在同一场雨夜到次日清晨。

## 章节大纲
### 1. 归城
- 摘要：周岚带着旧相机回到旧城。
- 出场角色：周岚
- 核心事件：她回到约定地点。
- 叙事功能：铺垫

### 2. 失约
- 摘要：她发现顾原未赴约另有隐情。
- 出场角色：周岚、顾原
- 核心事件：旧照片出现关键线索。
- 叙事功能：推进

### 3. 转场
- 摘要：周岚顺着旧照片转入更深的追查。
- 出场角色：周岚
- 核心事件：她锁定新的线索方向。
- 叙事功能：推进

### 4. 逼近
- 摘要：真相逐渐浮出水面。
- 出场角色：周岚、顾原
- 核心事件：她拼起失约背后的完整脉络。
- 叙事功能：推进

### 5. 冲洗
- 摘要：真相随着底片浮现。
- 出场角色：周岚
- 核心事件：她冲洗出最后一张照片。
- 叙事功能：高潮
"""
    if ("摘要：周岚带着旧相机回到旧城。" in prompt or "核心事件：她回到约定地点。" in prompt) and "请直接输出本章正文" in prompt:
        return "周岚拖着行李走进雨夜的旧城，怀里那台旧相机像一块沉默的石头。"
    if ("摘要：她发现顾原未赴约另有隐情。" in prompt or "核心事件：旧照片出现关键线索。" in prompt) and "请直接输出本章正文" in prompt:
        return "第二章内容，周岚开始追查失约背后的缘由。"
    if ("摘要：周岚顺着旧照片转入更深的追查。" in prompt or "核心事件：她锁定新的线索方向。" in prompt) and "请直接输出本章正文" in prompt:
        return "第三章内容，周岚顺着旧照片继续追查。"
    if ("摘要：真相逐渐浮出水面。" in prompt or "核心事件：她拼起失约背后的完整脉络。" in prompt) and "请直接输出本章正文" in prompt:
        return "第四章内容，真相在她的追索中愈发清晰。"
    if ("摘要：真相随着底片浮现。" in prompt or "核心事件：她冲洗出最后一张照片。" in prompt) and "请直接输出本章正文" in prompt:
        return "第五章内容，旧照片中浮现关键真相，故事也在这一章完成收束。"
    if "请对以上短篇小说进行全面质量检查" in prompt:
        return "✅ 质量检查通过，无需修改。"
    if "请快速检查这批章节的核心问题" in prompt:
        return "✅ 本批次质量检查通过，无需修改。"
    if "请进行通篇复审" in prompt:
        return "✅ 复审通过，正文定稿。"
    if "请快速进行通篇复审" in prompt:
        return "✅ 本批次复审通过。"
    if "请为这篇短篇小说生成 5 个候选书名" in prompt:
        return """1. 《雨夜失约》—— 类型：直白点题 | 释义：直接点出核心冲突
2. 《暗房回声》—— 类型：意象隐喻 | 释义：保留旧相机与回声感
3. 《谁没有赴约》—— 类型：悬念引导 | 释义：留下追问
4. 《迟来的照片》—— 类型：情感共鸣 | 释义：突出情感延迟
5. 《雨落成像》—— 类型：诗意文艺 | 释义：更偏文学气质"""
    if "需要为作品确定平台分类和内容标签" in prompt:
        return """{
  "main_category": "悬疑惊悚",
  "plot_tags": ["推理", "民间奇闻"],
  "role_tags": ["医生"],
  "emotion_tags": ["惊悚"],
  "background_tags": ["现代", "家庭"]
}"""
    raise AssertionError(f"Unexpected prompt: {prompt[:120]}")


def _start_short_story_workflow(client: TestClient):
    return client.post(
        "/api/short-story/workflow/start",
        json={"source_input": "旧相机、失约、雨夜", "target_total_words": 4200, "category": "悬疑惊悚"},
    ).json()["data"]["workflow"]


def _prepare_workflow_for_synopsis(client: TestClient):
    workflow = _start_short_story_workflow(client)
    workflow = client.post(
        "/api/short-story/input/analyze",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/fusion-options/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/fusion-options/select",
        json={"workflow": workflow, "selection": 1},
    ).json()["data"]["workflow"]
    return workflow


def _prepare_workflow_for_outline(client: TestClient):
    workflow = _prepare_workflow_for_synopsis(client)
    workflow = client.post(
        "/api/short-story/synopsis/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/synopsis/select",
        json={"workflow": workflow, "selection": 3},
    ).json()["data"]["workflow"]
    return workflow


def _prepare_workflow_for_writing(client: TestClient):
    workflow = _prepare_workflow_for_outline(client)
    workflow = client.post(
        "/api/short-story/outline/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/outline/confirm",
        json={"workflow": workflow, "approved": True, "feedback": ""},
    ).json()["data"]["workflow"]
    return workflow


def test_short_story_routes_complete_workflow(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    started = client.post(
        "/api/short-story/workflow/start",
        json={"source_input": "旧相机、失约、雨夜", "target_total_words": 4200, "category": "悬疑惊悚"},
    )
    workflow = started.json()["data"]["workflow"]
    assert workflow["state"] == "analyzing_source_input"
    assert workflow["planned_chapters"] == 5

    analysis = client.post(
        "/api/short-story/input/analyze",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = analysis["workflow"]
    assert workflow["state"] == "generating_fusion_options"
    assert workflow["keywords"] == ["旧相机", "失约", "雨夜"]

    fusion = client.post(
        "/api/short-story/fusion-options/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = fusion["workflow"]
    assert workflow["state"] == "awaiting_fusion_selection"
    assert len(workflow["fusion_candidates"]) == 3

    selected_fusion = client.post(
        "/api/short-story/fusion-options/select",
        json={"workflow": workflow, "selection": 2},
    ).json()["data"]
    workflow = selected_fusion["workflow"]
    assert workflow["state"] == "generating_synopsis"
    assert workflow["selected_fusion_index"] == 2

    synopsis = client.post(
        "/api/short-story/synopsis/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = synopsis["workflow"]
    assert workflow["state"] == "awaiting_synopsis_selection"
    assert len(workflow["synopsis_candidates"]) == 5

    selected = client.post(
        "/api/short-story/synopsis/select",
        json={"workflow": workflow, "selection": 3},
    ).json()["data"]
    workflow = selected["workflow"]
    assert workflow["state"] == "generating_outline"

    outline = client.post(
        "/api/short-story/outline/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = outline["workflow"]
    assert workflow["state"] == "awaiting_outline_confirm"
    assert len(workflow["chapter_blueprints"]) == 5

    confirmed = client.post(
        "/api/short-story/outline/confirm",
        json={"workflow": workflow, "approved": True, "feedback": ""},
    ).json()["data"]
    workflow = confirmed["workflow"]
    assert workflow["state"] == "writing_content"

    chapter = client.post(
        "/api/short-story/chapter/generate-all",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = chapter["workflow"]
    assert len(workflow["chapters"]) == 5
    assert workflow["state"] == "quality_checking"

    quality = client.post(
        "/api/short-story/quality-check/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    assert quality["passed"] is True

    quality_commit = client.post(
        "/api/short-story/quality-check/commit",
        json={"workflow": workflow, "report": quality["report"], "passed": True, "chapters": workflow["chapters"]},
    ).json()["data"]
    workflow = quality_commit["workflow"]
    assert workflow["state"] == "coherence_reviewing"

    coherence = client.post(
        "/api/short-story/coherence-review/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    assert coherence["passed"] is True

    coherence_commit = client.post(
        "/api/short-story/coherence-review/commit",
        json={"workflow": workflow, "report": coherence["report"], "passed": True, "chapters": workflow["chapters"]},
    ).json()["data"]
    workflow = coherence_commit["workflow"]
    assert workflow["state"] == "generating_titles"

    titles = client.post(
        "/api/short-story/title/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    workflow = titles["workflow"]
    assert len(workflow["title_candidates"]) == 5

    workflow = client.post(
        "/api/short-story/title/select",
        json={"workflow": workflow, "selection": 2},
    ).json()["data"]["workflow"]
    assert workflow["state"] == "assembling_output"

    assembled = client.post(
        "/api/short-story/assemble",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]
    assert assembled["workflow"]["state"] == "completed"
    assert "暗房回声" in assembled["final_work"]
    assert "悬疑惊悚" in assembled["final_work"]
    assert "推理" in assembled["final_work"]

    export_txt = client.post(
        "/api/short-story/export?format=txt",
        json={"workflow": assembled["workflow"]},
    )
    assert export_txt.status_code == 200
    assert "attachment;" in export_txt.headers["content-disposition"]
    assert export_txt.text.startswith("暗房回声")
    assert "标签：悬疑惊悚、推理、民间奇闻、医生、惊悚、现代、家庭" in export_txt.text
    assert "导语：失约的人从未离开，只是藏进了相机的最后一张照片里。" in export_txt.text
    assert "\n1.\n" in export_txt.text
    assert "1. 归城" not in export_txt.text
    assert "《暗房回声》" not in export_txt.text
    assert "词条标签" not in export_txt.text

    export_md = client.post(
        "/api/short-story/export?format=md",
        json={"workflow": assembled["workflow"]},
    )
    assert export_md.status_code == 200
    assert export_md.text.startswith("暗房回声")
    assert "# 《暗房回声》" not in export_md.text
    assert "## 导语" not in export_md.text
    assert "1. 归城" not in export_md.text

    export_docx = client.post(
        "/api/short-story/export?format=docx",
        json={"workflow": assembled["workflow"]},
    )
    assert export_docx.status_code == 200
    assert export_docx.content.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(export_docx.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "暗房回声" in document_xml
    assert "标签：悬疑惊悚、推理、民间奇闻、医生、惊悚、现代、家庭" in document_xml
    assert "《暗房回声》" not in document_xml
    assert "1. 归城" not in document_xml


def test_short_story_route_allows_reselecting_synopsis_after_initial_choice(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _prepare_workflow_for_synopsis(client)
    workflow = client.post(
        "/api/short-story/synopsis/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/synopsis/select",
        json={"workflow": workflow, "selection": 1},
    ).json()["data"]["workflow"]

    workflow["outline_text"] = "旧大纲"
    workflow["chapter_blueprints"] = [
        {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"}
    ]
    workflow["chapters"] = [{"chapter_number": 1, "title": "第1章", "content": "旧正文"}]

    response = client.post(
        "/api/short-story/synopsis/select",
        json={"workflow": workflow, "selection": 3},
    )

    assert response.status_code == 200
    payload = response.json()["data"]["workflow"]
    assert payload["state"] == "generating_outline"
    assert payload["selected_synopsis_index"] == 3
    assert payload["outline_text"] == ""
    assert payload["chapter_blueprints"] == []
    assert payload["chapters"] == []


def test_short_story_route_accepts_custom_chapter_word_target():
    app = create_app()
    client = TestClient(app)

    started = client.post(
        "/api/short-story/workflow/start",
        json={
            "source_input": "旧相机、失约、雨夜",
            "keywords": ["旧相机", "失约", "雨夜"],
            "target_total_words": 9000,
            "chapter_word_target": 1500,
            "category": "悬疑惊悚",
        },
    )

    workflow = started.json()["data"]["workflow"]
    assert started.status_code == 200
    assert workflow["planned_chapters"] == 6
    assert workflow["chapter_word_target"] == 1500
    assert workflow["chapter_word_min"] == 1400
    assert workflow["chapter_word_max"] == 1600
    assert workflow["custom_chapter_word_target"] == 1500


def test_short_story_generate_all_keeps_partial_progress_when_later_chapter_fails(monkeypatch):
    app = create_app()
    client = TestClient(app)
    chapter_call_count = {"value": 0}

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        if (
            "短篇小说创作输入分析师" in prompt
            or "生成 3 个“不同故事路数”的融合方案" in prompt
            or "生成 5 条风格各异的故事导语" in prompt
            or "生成一份详细的短篇小说章节大纲" in prompt
        ):
            return _fake_prompt_output(prompt, api_config_id, model)
        chapter_call_count["value"] += 1
        if chapter_call_count["value"] == 1:
            return "第一章内容。"
        raise short_story_routes.HTTPException(status_code=502, detail="无法连接到API服务器。")

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _prepare_workflow_for_writing(client)

    payload = client.post(
        "/api/short-story/chapter/generate-all",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    )

    data = payload.json()["data"]
    assert payload.status_code == 200
    assert data["partial"] is True
    assert data["failed_chapter"] == 2
    assert data["error"] == "无法连接到API服务器。"
    assert len(data["generated_chapters"]) == 1
    assert data["workflow"]["chapters"][0]["content"] == "第一章内容。"


def test_short_story_route_allows_regenerating_chapter_after_quality(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _prepare_workflow_for_writing(client)
    workflow = client.post(
        "/api/short-story/chapter/generate-all",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]

    assert workflow["state"] == "quality_checking"

    regenerated = client.post(
        "/api/short-story/chapter/generate",
        json={"workflow": workflow, "chapter_number": 2, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]

    assert regenerated["state"] == "quality_checking"
    assert any(int(item["chapter_number"]) == 2 for item in regenerated["chapters"])


def test_short_story_synopsis_feedback_is_forwarded(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = client.post(
        "/api/short-story/workflow/start",
        json={"source_input": "旧相机、失约、雨夜", "target_total_words": 4200, "category": "悬疑惊悚"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/input/analyze",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/fusion-options/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/fusion-options/select",
        json={"workflow": workflow, "selection": 1},
    ).json()["data"]["workflow"]

    payload = client.post(
        "/api/short-story/synopsis/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo", "feedback": "更偏悬疑"},
    ).json()["data"]

    assert payload["candidates"][0]["content"] == "更偏悬疑的第一条。"


def test_short_story_fusion_options_can_be_regenerated(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _start_short_story_workflow(client)
    workflow = client.post(
        "/api/short-story/input/analyze",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]
    workflow = client.post(
        "/api/short-story/fusion-options/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]

    assert workflow["state"] == "awaiting_fusion_selection"
    assert len(workflow["fusion_candidates"]) == 3

    regenerated = client.post(
        "/api/short-story/fusion-options/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    )

    assert regenerated.status_code == 200
    payload = regenerated.json()["data"]["workflow"]
    assert payload["state"] == "awaiting_fusion_selection"
    assert payload["selected_fusion"] == {}
    assert payload["selected_fusion_index"] is None
    assert len(payload["fusion_candidates"]) == 3


def test_short_story_quality_check_rejects_incomplete_chapters(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _prepare_workflow_for_writing(client)

    for chapter_number in range(1, 5):
        workflow = client.post(
            "/api/short-story/chapter/generate",
            json={"workflow": workflow, "chapter_number": chapter_number, "api_config_id": "cfg", "model": "demo"},
        ).json()["data"]["workflow"]

    workflow["state"] = "quality_checking"
    response = client.post(
        "/api/short-story/quality-check/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    )

    assert response.status_code == 400
    assert "暂时无法执行质量检查" in response.json()["detail"]


def test_short_story_quality_check_rejects_placeholder_blueprints(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return _fake_prompt_output(prompt, api_config_id, model)

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _prepare_workflow_for_writing(client)
    workflow = client.post(
        "/api/short-story/chapter/generate-all",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    ).json()["data"]["workflow"]

    workflow["chapter_blueprints"][-1] = {
        "chapter_number": workflow["chapter_blueprints"][-1]["chapter_number"],
        "title": workflow["chapter_blueprints"][-1]["title"],
        "summary": "",
        "characters": "",
        "core_event": "",
        "narrative_function": "",
        "emotion_point": "",
    }
    workflow["state"] = "quality_checking"
    response = client.post(
        "/api/short-story/quality-check/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    )

    assert response.status_code == 400
    assert "缺少有效章节蓝图" in response.json()["detail"]


def test_short_story_can_apply_simple_quality_fixes():
    app = create_app()
    client = TestClient(app)

    workflow = _start_short_story_workflow(client)
    workflow["state"] = "quality_checking"
    workflow["character_table"] = "沈青：主角\n陈浩：丈夫"
    workflow["planned_chapters"] = 6
    workflow["chapter_blueprints"] = [
        {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "沈青、陈浩", "core_event": "事件1", "narrative_function": "铺垫"},
        {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "沈青", "core_event": "事件2", "narrative_function": "推进"},
        {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "沈青", "core_event": "事件3", "narrative_function": "推进"},
        {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "沈青", "core_event": "事件4", "narrative_function": "推进"},
        {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "沈青", "core_event": "事件5", "narrative_function": "推进"},
        {"chapter_number": 6, "title": "第6章", "summary": "摘要6", "characters": "沈青", "core_event": "事件6", "narrative_function": "收束"},
    ]
    workflow["chapters"] = [
        {"chapter_number": 1, "title": "第1章", "content": "陈哲在门口拦住她，陈哲还想解释。"},
        {"chapter_number": 2, "title": "第2章", "content": "第二章"},
        {"chapter_number": 3, "title": "第3章", "content": "第三章"},
        {"chapter_number": 4, "title": "第4章", "content": "第四章"},
        {"chapter_number": 5, "title": "第5章", "content": "第五章"},
        {"chapter_number": 6, "title": "第6章", "content": "第六章"},
    ]

    response = client.post(
        "/api/short-story/quality-check/apply-simple-fixes",
        json={
                "workflow": workflow,
                "report": "第1章：角色一致性 - 丈夫名字“陈哲”与角色表“陈浩”不符",
                "chapters": workflow["chapters"],
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["fixed_count"] == 1
    assert payload["replacement_count"] == 2
    assert payload["revised_chapters"][0]["content"] == "陈浩在门口拦住她，陈浩还想解释。"
    assert payload["workflow"]["state"] == "quality_checking"


def test_short_story_quality_check_generate_returns_simple_fixes_for_common_name_patterns(monkeypatch):
    app = create_app()
    client = TestClient(app)

    async def fake_run_prompt(prompt: str, api_config_id: str = "", model: str = "", **kwargs) -> str:
        return """# 分批质检报告

## 批次 1（第1-3章）
第1章：逻辑合理性 - 角色“陈浩”在正文中被写作“陈哲”。
第2章：逻辑合理性 - 王桂芬名字前后不一致（王秀兰）
第3章：角色一致性 - 章节内丈夫名字从“陈哲”变更为“陈浩”，与角色表不符。

## 批次 2（第4-6章）
第4章：角色一致性 - 丈夫名字混用（陈哲/陈浩）
第5章：逻辑合理性 - 陈浩父亲名字前后不一致（陈哲）
第6章：逻辑合理性 - 赵姐称呼与大纲（赵姐）不符"""

    monkeypatch.setattr("novel_agent.web.routes.short_story._run_prompt", fake_run_prompt)
    monkeypatch.setattr(
        "novel_agent.web.routes.short_story._resolve_model_config",
        lambda api_config_id="", model="": object(),
    )

    workflow = _start_short_story_workflow(client)
    workflow["state"] = "quality_checking"
    workflow["character_table"] = "沈青：主角\n陈浩：丈夫\n王桂芬：婆婆"
    workflow["outline_text"] = "## 章节大纲\n..."
    workflow["planned_chapters"] = 6
    workflow["chapter_blueprints"] = [
        {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "沈青、陈浩", "core_event": "事件1", "narrative_function": "铺垫"},
        {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "沈青、王桂芬", "core_event": "事件2", "narrative_function": "推进"},
        {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "沈青", "core_event": "事件3", "narrative_function": "推进"},
        {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "沈青", "core_event": "事件4", "narrative_function": "推进"},
        {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "沈青", "core_event": "事件5", "narrative_function": "推进"},
        {"chapter_number": 6, "title": "第6章", "summary": "摘要6", "characters": "沈青", "core_event": "事件6", "narrative_function": "收束"},
    ]
    workflow["chapters"] = [
        {"chapter_number": 1, "title": "第1章", "content": "陈哲在门口拦住她。"},
        {"chapter_number": 2, "title": "第2章", "content": "王秀兰突然冲进门。"},
        {"chapter_number": 3, "title": "第3章", "content": "第三章。"},
        {"chapter_number": 4, "title": "第4章", "content": "第四章。"},
        {"chapter_number": 5, "title": "第5章", "content": "第五章。"},
        {"chapter_number": 6, "title": "第6章", "content": "第六章。"},
    ]

    response = client.post(
        "/api/short-story/quality-check/generate",
        json={"workflow": workflow, "api_config_id": "cfg", "model": "demo"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert [item["chapter_number"] for item in payload["simple_fixes"]] == [1, 2, 3, 4]
    assert [item["from_name"] for item in payload["simple_fixes"]] == ["陈哲", "王秀兰", "陈哲", "陈哲"]
    assert [item["to_name"] for item in payload["simple_fixes"]] == ["陈浩", "王桂芬", "陈浩", "陈浩"]


def test_short_story_can_rollback_placeholder_blueprints():
    app = create_app()
    client = TestClient(app)

    workflow = _start_short_story_workflow(client)
    workflow["state"] = "quality_checking"
    workflow["planned_chapters"] = 5
    workflow["chapter_blueprints"] = [
        {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
        {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
        {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
        {"chapter_number": 4, "title": "第4章", "summary": "", "characters": "", "core_event": "", "narrative_function": "", "emotion_point": ""},
        {"chapter_number": 5, "title": "第5章", "summary": "", "characters": "", "core_event": "", "narrative_function": "", "emotion_point": ""},
    ]
    workflow["chapters"] = [
        {"chapter_number": 1, "title": "第1章", "content": "第一章"},
        {"chapter_number": 2, "title": "第2章", "content": "第二章"},
        {"chapter_number": 3, "title": "第3章", "content": "第三章"},
        {"chapter_number": 4, "title": "第4章", "content": "第四章"},
        {"chapter_number": 5, "title": "第5章", "content": "第五章"},
    ]

    response = client.post(
        "/api/short-story/outline/repair-placeholders",
        json={"workflow": workflow, "feedback": "请把异常章节重新规划。"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["next_step"] == "revise_outline"
    assert payload["workflow"]["state"] == "awaiting_outline_confirm"
    assert payload["workflow"]["planned_chapters"] == 3
    assert len(payload["workflow"]["chapters"]) == 3
    assert payload["workflow"]["repair_placeholder_numbers"] == [4, 5]
    assert payload["workflow"]["manual_intervention_required"] is True


def test_short_story_confirm_outline_rejects_unresolved_repair_placeholders():
    app = create_app()
    client = TestClient(app)

    workflow = client.post(
        "/api/short-story/workflow/start",
        json={"keywords": ["旧相机", "失约", "雨夜"], "target_total_words": 4200, "category": "悬疑惊悚"},
    ).json()["data"]["workflow"]
    workflow["state"] = "awaiting_outline_confirm"
    workflow["outline_confirmed"] = False
    workflow["planned_chapters"] = 3
    workflow["repair_placeholder_numbers"] = [4, 5]
    workflow["outline_text"] = """### 1. 第1章
- 摘要：摘要1
- 出场角色：甲
- 核心事件：事件1
- 叙事功能：铺垫

### 2. 第2章
- 摘要：摘要2
- 出场角色：乙
- 核心事件：事件2
- 叙事功能：推进

### 3. 第3章
- 摘要：摘要3
- 出场角色：丙
- 核心事件：事件3
- 叙事功能：推进

### 4. 第4章
"""
    workflow["chapter_blueprints"] = [
        {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
        {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
        {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
    ]

    response = client.post(
        "/api/short-story/outline/confirm",
        json={"workflow": workflow, "approved": True, "feedback": ""},
    )

    assert response.status_code == 400
    assert "第 4、5 章" in response.json()["detail"]


def test_short_story_run_prompt_applies_timeout_and_token_cap(monkeypatch):
    observed = {}

    class FakeLLMClient:
        def __init__(self, model_config, metrics_namespace="default"):
            self.model_config = model_config

        async def call(self, **kwargs):
            observed.update(kwargs)
            return "ok"

    monkeypatch.setattr(
        short_story_routes,
        "_resolve_model_config",
        lambda api_config_id="", model="": type(
            "Cfg",
            (),
            {
                "temperature": 0.7,
                "max_tokens": 18888,
                "model": "demo-model",
                "api_key": "k",
                "api_base": "https://example.com/v1",
            },
        )(),
    )
    monkeypatch.setattr(short_story_routes, "LLMClient", FakeLLMClient)

    result = asyncio.run(
        short_story_routes._run_prompt(
            "hello",
            "cfg",
            "demo",
            max_tokens_limit=2500,
            timeout_seconds=3,
        )
    )

    assert result == "ok"
    assert observed["max_tokens"] == 2500
    assert observed["enable_retry"] is True


def test_short_story_run_prompt_timeout_raises_http_504(monkeypatch):
    class FakeLLMClient:
        def __init__(self, model_config, metrics_namespace="default"):
            self.model_config = model_config

        async def call(self, **kwargs):
            await asyncio.sleep(0.05)
            return "never"

    monkeypatch.setattr(
        short_story_routes,
        "_resolve_model_config",
        lambda api_config_id="", model="": type(
            "Cfg",
            (),
            {
                "temperature": 0.7,
                "max_tokens": 18888,
                "model": "demo-model",
                "api_key": "k",
                "api_base": "https://example.com/v1",
            },
        )(),
    )
    monkeypatch.setattr(short_story_routes, "LLMClient", FakeLLMClient)

    with patch("novel_agent.web.routes.short_story.logger.warning"):
        try:
            asyncio.run(
                short_story_routes._run_prompt(
                    "hello",
                    "cfg",
                    "demo",
                    max_tokens_limit=2500,
                    timeout_seconds=0.01,
                )
            )
            raise AssertionError("expected timeout")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 504
            assert "模型响应超时" in str(getattr(exc, "detail", exc))


def test_short_story_run_prompt_connection_error_raises_http_502(monkeypatch):
    class FakeLLMClient:
        def __init__(self, model_config, metrics_namespace="default"):
            self.model_config = model_config

        async def call(self, **kwargs):
            raise Exception("无法连接到API服务器。\nAPI地址: https://example.com/v1")

    monkeypatch.setattr(
        short_story_routes,
        "_resolve_model_config",
        lambda api_config_id="", model="": type(
            "Cfg",
            (),
            {
                "temperature": 0.7,
                "max_tokens": 18888,
                "model": "demo-model",
                "api_key": "k",
                "api_base": "https://example.com/v1",
            },
        )(),
    )
    monkeypatch.setattr(short_story_routes, "LLMClient", FakeLLMClient)

    try:
        asyncio.run(
            short_story_routes._run_prompt(
                "hello",
                "cfg",
                "demo",
                max_tokens_limit=2500,
                timeout_seconds=3,
            )
        )
        raise AssertionError("expected http 502")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 502
        assert "无法连接到API服务器" in str(getattr(exc, "detail", exc))


def test_router_guides_short_story_requests_to_fixed_panel():
    router = RouterAgent(coordinator=None)
    message = "我想写个短篇，灵感是雨夜重逢，参考旧相机和失约这个钩子"

    intent = asyncio.run(router.analyze_intent(message))
    delegated = asyncio.run(router._delegate_to_agent(intent, message, [], None, None))

    assert intent.primary_intent == UserIntent.CREATE_NOVEL
    assert intent.entities["short_story_requested"] is True
    assert delegated is not None
    assert delegated["action"] == "open_short_story_panel"
    assert delegated["params"]["module"] == "short-story"
    assert "固定入口" in delegated["response"]
    assert "3 个融合方案" in delegated["response"]
