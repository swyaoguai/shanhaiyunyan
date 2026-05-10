from novel_agent.chat_auto_save import process_assistant_auto_save
from novel_agent.project_manager import ProjectManager


def test_assistant_auto_save_requires_execute_mode_and_toggle(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    sample = "## 世界观\n这里是一条不应该落库的设定。"

    disabled = process_assistant_auto_save(
        pm,
        sample,
        mode="execute",
        auto_save_enabled=False,
    )
    plan_mode = process_assistant_auto_save(
        pm,
        sample,
        mode="plan",
        auto_save_enabled=True,
    )

    assert disabled is None
    assert plan_mode is None
    assert pm.load_project_data("worldbuilding") == []


def test_assistant_auto_save_extracts_builtin_sections_and_chapter(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    chapter_text = (
        "林渡推开雨夜里的档案馆铁门，潮湿的霓虹在地面碎成一片片蓝色鱼鳞。"
        "他记得自己昨晚已经来过这里，却在门口登记簿上看见了三种不同笔迹写下的名字。"
        "馆长递给他一枚空白硬币，说这座城会把每个人最想保留的记忆铸成货币，"
        "而今晚开始，所有硬币都在同时失效。林渡意识到，污染不是从某个案发现场开始的，"
        "而是从所有人默认遗忘的那一秒开始的。"
    )
    assistant_text = f"""
## 世界观基础设定
城市会将居民记忆铸成硬币，硬币失效时对应记忆会被污染。

## 核心人设
主角：林渡
少年调查员，目标是找出记忆污染的源头。

## 后续创作计划
第一卷围绕档案馆、硬币失效和城市集体失忆展开。

## 第1章 正文
{chapter_text}
"""

    result = process_assistant_auto_save(
        pm,
        assistant_text,
        mode="execute",
        auto_save_enabled=True,
        session_id="copilot",
    )

    assert result is not None
    assert result["applied"] is True
    assert {item["data_type"] for item in result["artifacts"]} >= {
        "worldbuilding",
        "characters",
        "outline",
        "chapters",
    }
    assert pm.load_project_data("worldbuilding")[0]["details"].startswith("城市会将居民记忆")
    assert pm.load_project_data("characters")[0]["name"] == "林渡"
    assert "档案馆" in pm.load_project_data("outline")[0]["summary"]
    chapters = pm.load_project_data("chapters")
    assert chapters[0]["chapter_number"] == 1
    assert "所有硬币都在同时失效" in chapters[0]["content"]
    assert "已自动同步到资料库" in result["summary"]


def test_assistant_auto_save_supports_custom_category(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    categories = [
        {
            "id": "db-custom-lore",
            "key": "custom_lore",
            "name": "灵感库",
            "builtin": False,
            "aliases": ["灵感"],
        }
    ]

    result = process_assistant_auto_save(
        pm,
        "## 灵感库\n记忆硬币可以作为城市黑市交易的核心意象。",
        mode="execute",
        auto_save_enabled=True,
        categories=categories,
    )

    assert result is not None
    assert result["applied"] is True
    assert result["artifacts"][0]["data_type"] == "custom_lore"
    rows = pm.load_project_data("custom_lore")
    assert rows[0]["name"] == "灵感库"
    assert "记忆硬币" in rows[0]["content"]


def test_assistant_auto_save_ignores_failed_character_sections(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    assistant_text = """
## 生成角色档案：失败
角色构建结果为空，未能创建角色档案。

## 错误
当前请求失败：模型返回为空。
"""

    result = process_assistant_auto_save(
        pm,
        assistant_text,
        mode="execute",
        auto_save_enabled=True,
    )

    assert result is None
    assert pm.load_project_data("characters") == []


def test_assistant_auto_save_ignores_chatty_discussion_sections(tmp_path):
    pm = ProjectManager(data_dir=tmp_path / "data")
    assistant_text = """
## 我帮你设计了一个4集为一组的小结构
这里先聊角色节奏：第一集负责拉关系，第二集制造误会，后面再看要不要落到角色档案。

## 聊天生成角色
好啦，那我拍板了，这一等一集女主撞见误会之后的响咕咕，用这句，其他的不改动。
"""

    result = process_assistant_auto_save(
        pm,
        assistant_text,
        mode="execute",
        auto_save_enabled=True,
    )

    assert result is None
    assert pm.load_project_data("characters") == []
    assert pm.load_project_data("chapters") == []
