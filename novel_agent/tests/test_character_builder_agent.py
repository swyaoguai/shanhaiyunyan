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
