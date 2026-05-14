"""上下文管理器兼容旧数据格式的回归测试。"""

import json
import logging

from novel_agent.context.character_manager import CharacterManager
from novel_agent.context.world_manager import WorldManager


def test_character_manager_loads_list_payload_without_warning(tmp_path, caplog):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "characters.json").write_text(
        json.dumps(
            [
                {"name": "林舟", "description": "冷静的调查员", "personality": "理性,克制"},
                {"name": "白璃", "description": "情报贩子", "role": "配角"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)
    manager = CharacterManager(project_dir)

    assert manager.get_character("林舟") is not None
    assert manager.get_character("林舟").personality == ["理性", "克制"]
    assert manager.get_character("白璃").role == "配角"
    assert "Failed to load characters" not in caplog.text


def test_character_manager_loads_structured_character_fields(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "characters.json").write_text(
        json.dumps(
            [
                {
                    "name": "吴迪",
                    "role": "主角",
                    "identity": "合欢宗外门弟子",
                    "occupation": "杂役弟子",
                    "age": "17",
                    "gender": "男",
                    "personality": ["抽象", "无厘头"],
                    "skills": "吞器修炼、御风术",
                    "item_refs": ["玄铁令"],
                    "growth_history": [{"chapter_number": 3, "title": "初入秘境", "description": "第一次独立破局"}],
                    "goals": ["摆脱追杀", "提升境界"],
                    "relationships": "苏青禾：暧昧对象\n赵不凡：死对头",
                    "motivation": "想要活下去并逆袭",
                    "notes": "常用谐音梗回怼别人",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = CharacterManager(project_dir)
    character = manager.get_character("吴迪")

    assert character is not None
    assert character.identity == "合欢宗外门弟子"
    assert character.occupation == "杂役弟子"
    assert character.age == "17"
    assert character.personality == ["抽象", "无厘头"]
    assert character.abilities == ["吞器修炼", "御风术"]
    assert character.inventory == ["玄铁令"]
    assert character.development_history[0]["title"] == "初入秘境"
    assert character.goals == ["摆脱追杀", "提升境界"]
    assert character.relationships["苏青禾"] == "暧昧对象"
    assert character.notes == "常用谐音梗回怼别人"


def test_character_manager_syncs_learned_abilities_from_chapter_text(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "characters.json").write_text(
        json.dumps(
            [{"name": "天齐", "role": "主角", "description": "少年主角", "abilities": ["轻功"]}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = CharacterManager(project_dir)
    updates = manager.sync_development_from_text(
        "天齐在雨夜里终于领悟了御风术，带着女主越过宫墙。",
        chapter_number=4,
    )
    reloaded = CharacterManager(project_dir)
    character = reloaded.get_character("天齐")

    assert updates == {"天齐": ["御风术"]}
    assert character is not None
    assert character.abilities == ["轻功", "御风术"]
    assert character.development_history[-1]["title"] == "御风术"
    assert character.development_history[-1]["chapter_number"] == 4
    assert "第4章获得/掌握：御风术" in character.notes


def test_character_manager_syncs_inventory_from_chapter_text(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "characters.json").write_text(
        json.dumps(
            [{"name": "天齐", "role": "主角", "description": "少年主角"}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = CharacterManager(project_dir)
    updates = manager.sync_development_from_text("天齐从密室拿到了玄铁令，决定连夜出城。", chapter_number=5)
    reloaded = CharacterManager(project_dir)
    character = reloaded.get_character("天齐")

    assert updates == {}
    assert character is not None
    assert character.inventory == ["玄铁令"]
    assert character.development_history[-1]["event_type"] == "item"
    assert character.development_history[-1]["title"] == "玄铁令"


def test_world_manager_loads_list_payload_without_warning(tmp_path, caplog):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "worldbuilding.json").write_text(
        json.dumps(
            [
                {"name": "北境雪原", "description": "终年暴雪，交通依赖冰轨列车"},
                {"name": "灵能律法", "description": "普通人禁止私自使用军用级灵能装置"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)
    manager = WorldManager(project_dir)

    assert manager.world is not None
    assert manager.world.world_type == "条目式设定"
    assert "北境雪原：终年暴雪，交通依赖冰轨列车" in manager.world.rules
    assert "灵能律法" in manager.get_world_context()
    assert "Failed to load world" not in caplog.text


def test_world_manager_compact_context_stays_short_and_structured(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "worldbuilding.json").write_text(
        json.dumps(
            {
                "world": {
                    "name": "玄荒天域",
                    "world_type": "修仙",
                    "power_system": "吞器炼体，灵器可化作修为",
                    "geography": "宗门林立，秘境遍布",
                    "factions": [
                        {"name": "合欢宗", "description": "表面风月，内里吃人"},
                        {"name": "天衡宗", "description": "自诩正道魁首"},
                    ],
                    "rules": [
                        "资源决定修为",
                        "高阶法器必须登记",
                        "秘境开启伴随伤亡",
                    ],
                    "culture": {"note": "这里不该出现在紧凑上下文里"},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = WorldManager(project_dir)
    context = manager.get_world_context()

    assert "【世界】玄荒天域" in context
    assert "- 类型：修仙" in context
    assert "- 核心规则：" in context
    assert "合欢宗" in context
    assert "文化习俗" not in context
