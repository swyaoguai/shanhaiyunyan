import json
from unittest.mock import patch

import pytest

from novel_agent.agent_config import AgentModelConfig
from novel_agent.agents.project_data_builders import (
    ChapterSettingBuilderAgent,
    DetailOutlineBuilderAgent,
)


@pytest.fixture
def model_config():
    return AgentModelConfig(
        agent_name="DetailOutlineBuilder",
        model="gpt-5.4",
        api_key="test-key",
        api_base="https://example.invalid/v1",
        temperature=0.3,
        max_tokens=4096,
        api_type="openai_chat",
    )


def _build_agent(agent_cls, model_config):
    with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = model_config
        return agent_cls()


@pytest.mark.asyncio
async def test_detail_outline_builder_retries_after_empty_response(model_config, monkeypatch):
    builder = _build_agent(DetailOutlineBuilderAgent, model_config)
    calls = 0

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ""
        return json.dumps(
            {
                "detail_settings": [
                    {
                        "name": "第1章",
                        "description": "主角确认目标并遭遇阻力",
                        "chapter_number": 1,
                        "scene_goal": "建立行动目标",
                        "conflict": "线索缺失导致计划受阻",
                        "notes": "章末露出新线索",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成细纲",
            "outline_rows": [{"chapter_number": 1, "title": "第1章", "summary": "主角确认目标"}],
        }
    )

    assert result["success"] is True
    assert calls == 2
    assert result["rows"][0]["scene_goal"] == "建立行动目标"
    assert not result.get("fallback_used")


@pytest.mark.asyncio
async def test_detail_outline_builder_falls_back_to_outline_rows_when_json_invalid(model_config, monkeypatch):
    builder = _build_agent(DetailOutlineBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return "### 细纲\n不是 JSON"

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成细纲",
            "outline_rows": [
                {
                    "chapter_number": 2,
                    "title": "暗巷追踪",
                    "summary": "主角追踪线索，发现幕后势力。",
                    "conflict": "追踪过程被反向设伏",
                }
            ],
        }
    )

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["rows"][0]["chapter_number"] == 2
    assert result["rows"][0]["scene_goal"] == "主角追踪线索，发现幕后势力。"
    assert result["rows"][0]["conflict"] == "追踪过程被反向设伏"


@pytest.mark.asyncio
async def test_chapter_setting_builder_fallback_adds_required_fields(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return ""

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "outline_rows": [
                {
                    "chapter": 3,
                    "name": "雨夜摊牌",
                    "description": "主角在雨夜逼问同盟，关系出现裂痕。",
                    "hook": "同盟说出另一个名字",
                }
            ],
        }
    )

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["rows"][0]["chapter_number"] == 3
    assert result["rows"][0]["chapter_goal"] == "主角在雨夜逼问同盟，关系出现裂痕。"
    assert result["rows"][0]["key_event"] == "主角在雨夜逼问同盟，关系出现裂痕。"
    assert result["rows"][0]["ending_hook"] == "同盟说出另一个名字"


@pytest.mark.asyncio
async def test_chapter_setting_builder_fallback_adds_plot_thread_from_eventline(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return ""

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "outline_rows": [
                {"chapter_number": 2, "title": "拍卖会", "summary": "主角进入拍卖会。"}
            ],
            "eventlines": [
                {
                    "thread_id": "auction_line",
                    "name": "拍卖会支线",
                    "description": "拿到玄铁令",
                    "start_chapter": 2,
                    "target_return_chapter": 4,
                    "max_consecutive_chapters": 2,
                }
            ],
        }
    )

    plot_thread = result["rows"][0]["plot_thread"]
    assert plot_thread["thread_id"] == "auction_line"
    assert plot_thread["switch_to"] == "auction_line"
    assert plot_thread["return_by_chapter"] == 4
    assert plot_thread["max_consecutive_chapters"] == 2


@pytest.mark.asyncio
async def test_chapter_setting_builder_enriches_successful_rows_with_eventline(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": "拍卖会",
                        "description": "主角进入拍卖会。",
                        "chapter_number": 2,
                        "chapter_goal": "拿到玄铁令",
                        "key_event": "竞拍失控",
                        "ending_hook": "黑衣人现身",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "outline_rows": [
                {"chapter_number": 2, "title": "拍卖会", "summary": "主角进入拍卖会。"}
            ],
            "eventlines": [
                {
                    "thread_id": "auction_line",
                    "name": "拍卖会支线",
                    "description": "拿到玄铁令",
                    "start_chapter": 2,
                    "target_return_chapter": 4,
                }
            ],
        }
    )

    assert result["success"] is True
    assert not result.get("fallback_used")
    assert result["rows"][0]["plot_thread"]["thread_id"] == "auction_line"
    assert result["rows"][0]["plot_thread"]["switch_to"] == "auction_line"


@pytest.mark.asyncio
async def test_detail_outline_builder_falls_back_when_json_rows_empty(model_config, monkeypatch):
    builder = _build_agent(DetailOutlineBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps({"detail_settings": []}, ensure_ascii=False)

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成细纲",
            "outline_rows": [{"number": 4, "title": "断桥重逢", "summary": "旧友带来关键证据。"}],
        }
    )

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["rows"][0]["chapter_number"] == 4
    assert result["rows"][0]["name"] == "断桥重逢"
