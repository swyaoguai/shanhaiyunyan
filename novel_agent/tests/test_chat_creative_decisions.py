import json

import pytest

from novel_agent.agents.communicator import CommunicatorAgent
from novel_agent.chat_creative_decisions import process_chat_creative_decision
from novel_agent.project_manager import ProjectManager


def test_discussion_only_chat_decision_does_not_update_project_content(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_data("worldbuilding", [])

    result = process_chat_creative_decision(
        pm,
        "先讨论一下，暂时不要落盘，世界观可以改成赛博都市方向。",
        mode="auto",
    )

    assert result is not None
    assert result["decision"]["decision_type"] == "discussion_only"
    assert result["updated_files"] == []
    assert pm.load_project_data("worldbuilding") == []

    decisions = pm.load_project_state("chat_creative_decisions", default=[])
    assert decisions[-1]["status"] == "recorded"


def test_no_archive_marker_keeps_chat_revision_discussion_only(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_data("characters", [])

    result = process_chat_creative_decision(
        pm,
        "我想补充主角人设，主角叫林渡，少年剑修，先别存档，继续帮我细化。",
        mode="auto",
    )

    assert result is not None
    assert result["decision"]["decision_type"] == "discussion_only"
    assert result["updated_files"] == []
    assert pm.load_project_data("characters") == []


def test_chat_revision_updates_contract_task_pool_without_touching_data_in_auto_mode(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_state(
        "creation_contract",
        {
            "contract_id": "contract-1",
            "scope": {"discussion_context": "旧方向"},
            "metadata": {},
        },
    )
    pm.save_project_state(
        "task_pool",
        {
            "tasks": [],
            "metadata": {"source": "contract_confirmation"},
        },
    )
    pm.save_project_data(
        "characters",
        [
            {
                "name": "林渡",
                "description": "少年剑修",
            }
        ],
    )

    result = process_chat_creative_decision(
        pm,
        "把主角林渡的动机修改为调查城市记忆污染，后续不要走宗门复仇线。",
        mode="auto",
    )

    assert result is not None
    assert result["applied"] is True
    assert {item["kind"] for item in result["updated_files"]} == {
        "creation_contract",
        "task_pool",
    }

    contract = pm.load_project_state("creation_contract", default={})
    assert "调查城市记忆污染" in contract["scope"]["discussion_context"]
    assert contract["metadata"]["chat_revision_notes"]

    task_pool = pm.load_project_state("task_pool", default={})
    assert task_pool["metadata"]["needs_replan"] is True
    assert "宗门复仇线" in task_pool["metadata"]["chat_revision_notes"][-1]

    characters = pm.load_project_data("characters")
    assert "调查城市记忆污染" not in json.dumps(characters, ensure_ascii=False)
    assert "revision_notes" not in characters[0]


def test_chat_revision_updates_target_data_only_in_execute_mode(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_data(
        "characters",
        [
            {
                "name": "林渡",
                "description": "少年剑修",
            }
        ],
    )

    result = process_chat_creative_decision(
        pm,
        "把主角林渡的动机修改为调查城市记忆污染，后续不要走宗门复仇线。",
        mode="execute",
    )

    assert result is not None
    assert {item["kind"] for item in result["updated_files"]} >= {"characters"}

    characters = pm.load_project_data("characters")
    assert "调查城市记忆污染" in json.dumps(characters, ensure_ascii=False)
    assert characters[0]["revision_notes"]


def test_chat_revision_preserves_dict_project_data_payload(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    pm.save_project_data(
        "worldbuilding",
        {
            "world_name": "旧城",
            "power_system": "剑修体系",
        },
    )

    result = process_chat_creative_decision(
        pm,
        "把世界观保存到资料库，后续强调旧城记忆污染。",
        mode="execute",
    )

    saved_world = pm.load_project_data("worldbuilding")

    assert result is not None
    assert {item["kind"] for item in result["updated_files"]} >= {"worldbuilding"}
    assert isinstance(saved_world, dict)
    assert saved_world["world_name"] == "旧城"
    assert "旧城记忆污染" in saved_world["revision_notes"][-1]


class _StreamingInfoAgent(CommunicatorAgent):
    async def _check_auto_tool_call(self, message):
        return None

    async def _retrieve_knowledge_context(self, message):
        return []

    async def call_llm(self, messages, temperature=0.7, stream=False, **kwargs):
        async def _gen():
            yield "好的，"
            yield "我会按这个方向整理。"
            yield "[INFO_COMPLETE]"

        return _gen()


@pytest.mark.asyncio
async def test_streaming_chat_extracts_structured_info_from_user_message():
    agent = _StreamingInfoAgent()

    events = []
    async for event in agent.chat_stream("主题是城市记忆污染，主角叫林渡，不要走宗门复仇线。"):
        events.append(event)

    assert agent.collected_info["theme"] == "城市记忆污染"
    assert agent.collected_info["protagonist"] == "林渡"
    assert "宗门复仇线" in agent.collected_info["requirements"]
    assert any('"type": "done"' in event for event in events)
