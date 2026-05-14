import json
from unittest.mock import patch

import pytest

from novel_agent.agent_config import AgentModelConfig
from novel_agent.agents.character_builder import CharacterBuilderAgent
from novel_agent.agents.outliner import OutlinerAgent


@pytest.fixture
def outliner():
    config = AgentModelConfig(
        agent_name="Outliner",
        model="gpt-5.4",
        api_key="test-key",
        api_base="https://example.invalid/v1",
        temperature=0.3,
        max_tokens=4096,
    )
    with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = config
        return OutlinerAgent()


@pytest.fixture
def character_builder():
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


class TestOutlineConsistency:
    def test_no_issues_when_characters_mentioned(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：林逸在天玄大陆通过灵气修炼体系修炼。",
            "volumes": [
                {
                    "volume_summary": "林逸加入青云门，与苏婉展开冒险。",
                    "core_conflict": "林逸对抗暗影阁势力",
                    "protagonist_growth": "林逸从菜鸟成长为强者",
                    "volume_climax": "林逸击败大Boss",
                }
            ],
        }
        input_data = {
            "characters": [
                {"name": "林逸", "role": "主角"},
                {"name": "苏婉", "role": "女主"},
            ],
            "world": {
                "power_system": {"name": "灵气修炼体系"},
                "factions": [{"name": "青云门"}, {"name": "暗影阁"}],
            },
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, input_data)
        assert not issues

    def test_flags_missing_characters(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：一个无名之人踏上旅途。",
            "volumes": [
                {
                    "volume_summary": "无名之人探索大陆。",
                    "core_conflict": "黑暗降临",
                }
            ],
        }
        input_data = {
            "characters": [
                {"name": "林逸", "role": "主角"},
                {"name": "苏婉", "role": "女主"},
            ],
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, input_data)
        assert any("角色" in issue for issue in issues)

    def test_flags_missing_power_system(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：林逸在大陆修炼。",
            "volumes": [],
        }
        input_data = {
            "characters": [{"name": "林逸"}],
            "world": {"power_system": {"name": "灵气修炼体系"}},
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, input_data)
        assert any("力量体系" in issue for issue in issues)

    def test_flags_missing_factions(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：林逸修炼。",
            "volumes": [],
        }
        input_data = {
            "characters": [{"name": "林逸"}],
            "world": {
                "factions": [{"name": "青云门"}, {"name": "暗影阁"}],
            },
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, input_data)
        assert any("势力" in issue for issue in issues)

    def test_no_issues_when_no_input_data(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：角色修炼。",
            "volumes": [],
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, {})
        assert not issues

    def test_characters_in_dict_format(self):
        outline_data = {
            "global_outline": "书名：测试\n故事梗概：张三在都市奋斗。",
            "volumes": [],
        }
        input_data = {
            "characters": {
                "characters": [
                    {"name": "张三", "role": "主角"},
                ]
            },
        }
        issues = OutlinerAgent._check_outline_consistency(outline_data, input_data)
        assert not issues


class TestChapterOutlineConsistency:
    def _make_builder(self):
        from novel_agent.agents.project_data_builders import ChapterSettingBuilderAgent
        config = AgentModelConfig(
            agent_name="ChapterSettingBuilder",
            model="gpt-5.4",
            api_key="test-key",
            api_base="https://example.invalid/v1",
            temperature=0.3,
            max_tokens=4096,
        )
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = config
            return ChapterSettingBuilderAgent()

    def test_detects_duplicate_titles(self):
        builder = self._make_builder()
        rows = [
            {"name": "秘境初探", "chapter_number": 1, "description": "林逸进入秘境"},
            {"name": "秘境初探", "chapter_number": 2, "description": "林逸继续探索"},
        ]
        issues = builder._check_chapter_outline_consistency(rows, {})
        assert any("重复标题" in issue for issue in issues)

    def test_no_duplicate_when_titles_differ(self):
        builder = self._make_builder()
        rows = [
            {"name": "秘境初探", "chapter_number": 1, "description": "林逸进入"},
            {"name": "暗夜潜行", "chapter_number": 2, "description": "苏婉出场"},
        ]
        issues = builder._check_chapter_outline_consistency(rows, {})
        assert not any("重复标题" in issue for issue in issues)

    def test_flags_missing_character_coverage(self):
        builder = self._make_builder()
        rows = [
            {"name": "第1章", "chapter_number": 1, "description": "无名之人探索大陆"},
        ]
        input_data = {
            "locked_character_names": ["林逸", "苏婉"],
        }
        issues = builder._check_chapter_outline_consistency(rows, input_data)
        assert any("角色" in issue for issue in issues)

    def test_no_character_issue_when_names_present(self):
        builder = self._make_builder()
        rows = [
            {"name": "第1章", "chapter_number": 1, "description": "林逸进入秘境"},
        ]
        input_data = {
            "locked_character_names": ["林逸", "苏婉"],
        }
        issues = builder._check_chapter_outline_consistency(rows, input_data)
        assert not any("角色" in issue for issue in issues)

    def test_flags_outline_keyword_mismatch(self):
        builder = self._make_builder()
        rows = [
            {"name": "第1章", "chapter_number": 1, "description": "完全无关的内容主题"},
        ]
        input_data = {
            "outline_rows": [
                {"chapter_number": 1, "summary": "林逸进入秘境，获得噬器能力，对抗邪魔"},
            ],
        }
        issues = builder._check_chapter_outline_consistency(rows, input_data)
        assert any("偏离大纲" in issue for issue in issues)

    def test_no_keyword_issue_when_overlap_exists(self):
        builder = self._make_builder()
        rows = [
            {"name": "第1章", "chapter_number": 1, "description": "林逸进入秘境获得能力"},
        ]
        input_data = {
            "outline_rows": [
                {"chapter_number": 1, "summary": "林逸进入秘境，获得噬器能力"},
            ],
        }
        issues = builder._check_chapter_outline_consistency(rows, input_data)
        assert not any("偏离大纲" in issue for issue in issues)


class TestCharacterWorldConsistency:
    def test_no_issues_when_world_terms_referenced(self):
        characters = [
            {
                "name": "林逸",
                "background": "出身青云门外门弟子，修炼灵气体系。",
                "personality": "坚韧不拔",
                "abilities": "灵气操控",
            }
        ]
        input_data = {
            "world": {
                "power_system": {"name": "灵气体系"},
                "factions": [{"name": "青云门"}, {"name": "暗影阁"}],
            },
        }
        issues = CharacterBuilderAgent._check_character_world_consistency(characters, input_data)
        assert not issues

    def test_flags_character_missing_world_references(self):
        characters = [
            {
                "name": "林逸",
                "background": "出身一个普通的小村庄。",
                "personality": "善良正直",
                "abilities": "剑法",
            }
        ]
        input_data = {
            "world": {
                "power_system": {"name": "灵气修炼"},
                "factions": [{"name": "青云门"}, {"name": "暗影阁"}],
            },
        }
        issues = CharacterBuilderAgent._check_character_world_consistency(characters, input_data)
        assert any("林逸" in issue for issue in issues)

    def test_no_check_when_few_world_terms(self):
        characters = [
            {
                "name": "林逸",
                "background": "普通人。",
            }
        ]
        input_data = {
            "world": {
                "power_system": {"name": "灵"},
            },
        }
        issues = CharacterBuilderAgent._check_character_world_consistency(characters, input_data)
        assert not issues

    def test_no_check_when_no_world(self):
        characters = [{"name": "林逸", "background": "普通人。"}]
        issues = CharacterBuilderAgent._check_character_world_consistency(characters, {})
        assert not issues

    def test_nested_world_dict(self):
        characters = [
            {
                "name": "林逸",
                "background": "青云门弟子，修炼灵气。",
            }
        ]
        input_data = {
            "world": {
                "world": {
                    "power_system": {"name": "灵气修炼"},
                    "factions": [{"name": "青云门"}, {"name": "暗影阁"}],
                },
            },
        }
        issues = CharacterBuilderAgent._check_character_world_consistency(characters, input_data)
        assert not issues
