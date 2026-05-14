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
async def test_chapter_setting_builder_retries_when_response_too_short(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)
    calls = 0

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '{"chapter_settings":[]}'
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": "第1章 赐婚",
                        "description": "女主接到赐婚圣旨，被迫进入权力漩涡并与男主初遇。",
                        "chapter_number": 1,
                        "chapter_goal": "建立赐婚压力与男女主初遇的关系张力",
                        "key_event": "赐婚圣旨到达苏府，女主在宫门外遇见男主",
                        "ending_hook": "男主认出女主手中旧物，暗示两家旧案有关",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "outline_rows": [{"chapter_number": 1, "title": "赐婚", "summary": "女主被赐婚。"}],
        }
    )

    assert result["success"] is True
    assert calls == 2
    assert not result.get("fallback_used")
    assert result["rows"][0]["chapter_goal"] == "建立赐婚压力与男女主初遇的关系张力"


@pytest.mark.asyncio
async def test_chapter_setting_builder_pads_partial_success_to_total_chapters(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": "第1章 旧城归来",
                        "description": "林渊回到旧城，发现宗门覆灭旧案仍有人遮掩。",
                        "chapter_number": 1,
                        "chapter_goal": "建立旧城压抑氛围和复仇目标",
                        "key_event": "林渊在旧城门口认出当年的暗号",
                        "ending_hook": "暗号背后出现新的追杀者",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 3,
            "outline_rows": [
                {"chapter_number": 1, "title": "旧城归来", "summary": "林渊回到旧城。"},
                {"chapter_number": 2, "title": "夜探宗门", "summary": "林渊夜探废弃宗门。"},
                {"chapter_number": 3, "title": "旧友成敌", "summary": "旧友站在敌对阵营。"},
            ],
        }
    )

    assert result["success"] is True
    assert result["coverage_fallback_used"] is True
    assert [row["chapter_number"] for row in result["rows"]] == [1, 2, 3]
    assert result["rows"][0]["chapter_goal"] == "建立旧城压抑氛围和复仇目标"
    assert result["rows"][1]["chapter_goal"] == "林渊夜探废弃宗门。"
    assert result["rows"][2]["key_event"] == "旧友站在敌对阵营。"


@pytest.mark.asyncio
async def test_chapter_setting_builder_generates_long_projects_in_batches(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)
    calls = 0

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        nonlocal calls
        calls += 1
        prompt = messages[-1]["content"]
        outline_json = prompt.split("## 大纲资料", 1)[1].split("## 事件线资料", 1)[0].strip()
        outline_rows = json.loads(outline_json)
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": f"第{row['chapter_number']}章",
                        "description": row["summary"],
                        "chapter_number": row["chapter_number"],
                        "chapter_goal": row["summary"],
                        "key_event": row["summary"],
                        "ending_hook": "引出下一章",
                    }
                    for row in outline_rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 12,
            "outline_rows": [
                {"chapter_number": number, "title": f"第{number}章", "summary": f"第{number}章剧情"}
                for number in range(1, 13)
            ],
        }
    )

    assert result["success"] is True
    assert calls == 3
    assert result["batch_count"] == 3
    assert [row["chapter_number"] for row in result["rows"]] == list(range(1, 13))
    assert not result.get("fallback_used")


@pytest.mark.asyncio
async def test_chapter_setting_builder_batch_prompt_includes_overview_and_characters(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)
    prompts = []

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        prompt = messages[-1]["content"]
        prompts.append(prompt)
        outline_json = prompt.split("## 大纲资料", 1)[1].split("## 事件线资料", 1)[0].strip()
        outline_rows = json.loads(outline_json)
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": row["title"],
                        "description": row["summary"],
                        "chapter_number": row["chapter_number"],
                        "chapter_goal": row["summary"],
                        "key_event": row["summary"],
                        "ending_hook": "承接下一章",
                    }
                    for row in outline_rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 6,
            "world_summary": "世界名：锦绣长安",
            "characters": [{"name": "沈清悦"}, {"name": "陆砚"}],
            "outline_overview_rows": [
                {
                    "title": "主线大纲",
                    "summary": "沈清悦与陆砚先婚后爱。",
                    "global_outline": "角色设定：沈清悦、陆砚。",
                }
            ],
            "outline_rows": [
                {"chapter_number": number, "title": f"第{number}章", "summary": f"沈清悦与陆砚剧情{number}"}
                for number in range(1, 7)
            ],
        }
    )

    assert result["success"] is True
    assert result["batch_count"] == 2
    assert len(prompts) == 2
    assert "全书/分卷概览" in prompts[0]
    assert "沈清悦" in prompts[0]
    assert "陆砚" in prompts[0]
    assert "不得重启剧情" in prompts[1]


@pytest.mark.asyncio
async def test_chapter_setting_builder_discards_out_of_batch_restart_rows(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)
    calls = 0

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        nonlocal calls
        calls += 1
        prompt = messages[-1]["content"]
        outline_json = prompt.split("## 大纲资料", 1)[1].split("## 事件线资料", 1)[0].strip()
        outline_rows = json.loads(outline_json)
        if calls == 2:
            restart_rows = [
                {
                    "name": f"错误重启第{number}章",
                    "description": f"错误重启剧情{number}",
                    "chapter_number": number,
                    "chapter_goal": f"错误目标{number}",
                    "key_event": f"错误事件{number}",
                    "ending_hook": "错误钩子",
                }
                for number in range(1, 6)
            ]
            return json.dumps({"chapter_settings": restart_rows}, ensure_ascii=False)
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": row["title"],
                        "description": row["summary"],
                        "chapter_number": row["chapter_number"],
                        "chapter_goal": row["summary"],
                        "key_event": row["summary"],
                        "ending_hook": "承接下一章",
                    }
                    for row in outline_rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 10,
            "outline_rows": [
                {"chapter_number": number, "title": f"第{number}章", "summary": f"正确剧情{number}"}
                for number in range(1, 11)
            ],
        }
    )

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert [row["chapter_number"] for row in result["rows"]] == list(range(1, 11))
    assert result["rows"][5]["name"] == "第6章"
    assert result["rows"][5]["chapter_goal"] == "正确剧情6"
    assert all("错误重启" not in row["name"] for row in result["rows"])


@pytest.mark.asyncio
async def test_chapter_setting_builder_replaces_rows_that_rename_locked_characters(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps(
            {
                "chapter_settings": [
                    {
                        "name": "第1章 新婚夜",
                        "description": "沈清婉嫁入镇南王府，发现赵恒外冷内热。",
                        "chapter_number": 1,
                        "chapter_goal": "沈清婉与赵恒在新婚夜确认婚约关系",
                        "key_event": "赵恒替沈清婉挡下嫡姐刁难",
                        "ending_hook": "沈清婉发现赵恒藏着旧信",
                    },
                    {
                        "name": "第2章 回门风波",
                        "description": "沈清婉回门，赵恒出面维护她。",
                        "chapter_number": 2,
                        "chapter_goal": "沈清婉与赵恒共同面对娘家羞辱",
                        "key_event": "赵恒当众护妻",
                        "ending_hook": "嫡姐暗中设计下一局",
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 2,
            "characters": [{"name": "沈清悦"}, {"name": "陆砚"}],
            "outline_rows": [
                {
                    "chapter_number": 1,
                    "title": "第1章 新婚夜",
                    "summary": "沈清悦嫁入镇北将军府，发现陆砚外冷内热。",
                },
                {
                    "chapter_number": 2,
                    "title": "第2章 回门风波",
                    "summary": "沈清悦回门受嫡姐刁难，陆砚出面维护。",
                },
            ],
        }
    )

    assert result["success"] is True
    assert result["character_consistency_fallback_used"] is True
    serialized = json.dumps(result["rows"], ensure_ascii=False)
    assert "沈清悦" in serialized
    assert "陆砚" in serialized
    assert "沈清婉" not in serialized
    assert "赵恒" not in serialized
    assert result["rows"][0]["chapter_goal"] == "沈清悦嫁入镇北将军府，发现陆砚外冷内热。"
    assert result["rows"][1]["key_event"] == "沈清悦回门受嫡姐刁难，陆砚出面维护。"


@pytest.mark.asyncio
async def test_chapter_setting_builder_fallback_expands_global_outline_to_total_chapters(model_config, monkeypatch):
    builder = _build_agent(ChapterSettingBuilderAgent, model_config)

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return "主线大纲正文，但不是 JSON"

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "user_request": "生成章纲",
            "total_chapters": 3,
            "outline_rows": [
                {
                    "title": "主线大纲",
                    "summary": "旧城幸存者回归，追查宗门覆灭真相。",
                    "global_outline": "旧城幸存者回归，追查宗门覆灭真相。",
                }
            ],
        }
    )

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert [row["chapter_number"] for row in result["rows"]] == [1, 2, 3]
    assert result["rows"][0]["chapter_goal"] == "旧城幸存者回归，追查宗门覆灭真相。"


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
