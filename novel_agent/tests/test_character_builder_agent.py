import json
from unittest.mock import patch

import pytest

from novel_agent.agents.character_builder import CharacterBuilderAgent
from novel_agent.agent_config import AgentModelConfig


@pytest.fixture
def builder():
    config = AgentModelConfig(
        agent_name="CharacterBuilder",
        model="gpt-5.4",
        api_key="test-key",
        api_base="https://example.invalid/v1",
        temperature=0.3,
        max_tokens=4096,
    )
    with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = config
        return CharacterBuilderAgent()


@pytest.mark.asyncio
async def test_character_builder_accepts_valid_json_output(builder, monkeypatch):
    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps(
            {
                "status": "ok",
                "confidence": 0.91,
                "missing_info": [],
                "characters": [
                    {
                        "name": "吴迪",
                        "role": "主角",
                        "identity": "合欢宗外门杂役弟子",
                        "description": "抽象系修仙爽文男主，靠嘴炮和吞器修炼逆袭。",
                        "personality": ["抽象", "嘴硬"],
                        "goals": ["摆脱追杀", "在宗门站稳脚跟"],
                        "relationships": {"苏青禾": "暧昧对象"},
                        "notes": "草稿",
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "character_request": "生成主角角色卡",
            "recent_discussion": "主角叫吴迪，是合欢宗外门杂役弟子，被追杀后误入秘境。",
            "world_summary": "修仙世界，邪宗林立。",
            "request_mode": "draft",
        }
    )

    assert result["success"] is True
    assert result["characters"][0]["name"] == "吴迪"
    assert result["characters"][0]["role"] == "主角"


@pytest.mark.asyncio
async def test_character_builder_rejects_placeholder_name(builder, monkeypatch):
    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        return json.dumps(
            {
                "status": "ok",
                "confidence": 0.5,
                "missing_info": [],
                "characters": [
                    {
                        "name": "主角",
                        "role": "主角",
                        "identity": "",
                        "description": "很厉害。",
                        "personality": [],
                        "goals": [],
                        "relationships": {},
                        "notes": "",
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "character_request": "生成主角角色卡",
            "recent_discussion": "想写一个修仙主角。",
            "request_mode": "draft",
        }
    )

    assert result["success"] is False
    assert any("占位名" in issue for issue in result["missing_info"])


@pytest.mark.asyncio
async def test_character_builder_autonomous_mode_prompts_model_to_fill_blanks(builder, monkeypatch):
    captured = {}

    async def _fake_call_llm(messages, temperature=None, max_tokens=None, stream=False, enable_retry=True):
        captured["prompt"] = messages[-1]["content"]
        return json.dumps(
            {
                "status": "ok",
                "confidence": 0.87,
                "missing_info": [],
                "characters": [
                    {
                        "name": "沈知棠",
                        "role": "女主",
                        "identity": "没落侯府养女",
                        "description": "古代甜宠故事女主，外柔内韧，擅长在家族夹缝中护住亲近之人。",
                        "personality": ["聪慧", "清醒"],
                        "goals": ["重建安全感", "守住真实心意"],
                        "relationships": {"谢临舟": "姐弟恋对象"},
                        "notes": "由助手自主补全的角色草稿",
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(builder, "call_llm", _fake_call_llm)
    result = await builder.execute(
        {
            "novel_type": "古代言情",
            "theme": "古代甜宠",
            "character_request": "",
            "recent_discussion": "用户想写古代甜宠，篇幅5w字，其他由AI安排。",
            "request_mode": "autonomous_draft",
            "ai_autonomy_requested": True,
        }
    )

    assert result["success"] is True
    assert result["characters"][0]["name"] == "沈知棠"
    assert "不要因为姓名/身份/剧情细节未给出而返回 missing_info" in captured["prompt"]
