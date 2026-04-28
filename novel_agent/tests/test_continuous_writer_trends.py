"""Tests for trend ingestion in ContinuousWriter."""

import asyncio
import json

from novel_agent.agents.continuous_writer import CharacterState, ContinuousWriteConfig, ContinuousWriter
from novel_agent.agents.base_agent import BaseAgent


class _FakeText:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, content=None, is_error: bool = False):
        self.content = content or []
        self.isError = is_error


def test_continuous_writer_search_trends_parses_xml(monkeypatch):
    def fake_use_skill(skill_name: str, method: str, **kwargs):
        assert method == "get_toutiao_trending"
        return {
            "success": True,
            "platform": "toutiao",
            "data": [
                {"title": "测试热点C", "hot": "777", "url": "https://example.com/c"}
            ]
        }

    monkeypatch.setattr(BaseAgent, "use_skill", fake_use_skill)

    writer = ContinuousWriter(write_config=ContinuousWriteConfig(trends_platforms=["toutiao"], trends_limit=5))
    trends = asyncio.run(writer._search_trends())

    assert len(trends) == 1
    assert trends[0]["title"] == "测试热点C"
    assert trends[0]["hot"] == "777"
    assert trends[0]["url"] == "https://example.com/c"
    assert trends[0]["platform"] == "toutiao"


def test_continuous_writer_prompt_contains_trend_fusion_instructions():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    prompt = writer._build_chapter_prompt(
        chapter_number=2,
        story_beginning="",
        recent_chapters=[],
        kb_context={},
        kb_summaries=[],
        trends_data=[{"title": "测试热点D", "platform": "weibo", "hot": "66"}],
        inspirations=[],
        corrections=[],
        model_switch_context="",
    )

    assert "热点融合要求" in prompt
    assert "热点候选" in prompt
    assert "测试热点D" in prompt
    assert "执行优先级" in prompt
    assert "只能改写成剧情素材" in prompt
    assert "不要附加章节信息、自检结果或解释" in prompt
    assert "已提供的前情、知识库、剧情总结、死亡角色和约束就是本次可用记忆" in prompt


def test_continuous_writer_prompt_includes_character_and_setting_anchors():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    writer._characters = {
        "周岚": CharacterState(
            name="周岚",
            status="警惕",
            location="旧城",
            last_chapter=4,
            notes=["周岚站在旧城桥头，怀疑顾原另有隐情。"],
        )
    }
    prompt = writer._build_chapter_prompt(
        chapter_number=5,
        story_beginning="周岚带着旧相机回到旧城，准备查清失约真相。",
        recent_chapters=[
            {
                "chapter_number": 4,
                "title": "桥头",
                "summary": "周岚在旧城桥头继续追查。",
                "content": "周岚站在旧城桥头，风很冷，她终于决定继续查下去。"
            }
        ],
        kb_context={},
        kb_summaries=[],
        trends_data=[],
        inspirations=[],
        corrections=[],
        model_switch_context="",
    )

    assert "[角色状态锚点]" in prompt
    assert "周岚；最近出现在第4章；状态：警惕；位置：旧城" in prompt
    assert "[设定与场景锚点]" in prompt
    assert "开篇设定：周岚带着旧相机回到旧城" in prompt
    assert "第4章 桥头：周岚在旧城桥头继续追查。" in prompt
    assert "[续写前快速自检]" in prompt
    assert "本章重点盯住这些角色：周岚。" in prompt
    assert "本章必须顺着上一章《桥头》的结尾往下写。" in prompt


def test_continuous_writer_uses_five_recent_chapters_by_default():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    writer._written_chapters = [
        {"chapter_number": idx, "title": f"第{idx}章", "summary": f"摘要{idx}", "content": f"正文{idx}"}
        for idx in range(1, 8)
    ]

    recent = writer._get_recent_chapters()

    assert [item["chapter_number"] for item in recent] == [3, 4, 5, 6, 7]


def test_continuous_writer_search_trends_balances_multi_platforms(monkeypatch):
    def fake_use_skill(skill_name: str, method: str, **kwargs):
        if method == "get_toutiao_trending":
            return {
                "success": True,
                "platform": "toutiao",
                "data": [
                    {"title": "T1", "hotValue": 101, "url": "https://example.com/t1"},
                    {"title": "T2", "hotValue": 102, "url": "https://example.com/t2"},
                    {"title": "T3", "hotValue": 103, "url": "https://example.com/t3"},
                ]
            }
        if method == "get_weibo_trending":
            return {
                "success": True,
                "platform": "weibo",
                "data": [
                    {"title": "W1", "hotValue": 201, "url": "https://example.com/w1"},
                    {"title": "W2", "hotValue": 202, "url": "https://example.com/w2"},
                ]
            }
        raise AssertionError(f"Unexpected method: {method}")

    monkeypatch.setattr(BaseAgent, "use_skill", fake_use_skill)

    writer = ContinuousWriter(
        write_config=ContinuousWriteConfig(trends_platforms=["toutiao", "weibo"], trends_limit=3)
    )
    trends = asyncio.run(writer._search_trends())

    assert [t["title"] for t in trends] == ["T1", "W1", "T2"]
    assert [t["platform"] for t in trends] == ["toutiao", "weibo", "toutiao"]


def test_continuous_writer_search_trends_fallbacks_to_legacy_tool_name(monkeypatch):
    called_methods = []

    def fake_use_skill(skill_name: str, method: str, **kwargs):
        called_methods.append(method)
        if method == "get_customsource_trending":
            return {"success": False, "error": f"Method not found: {method}"}
        if method == "get-customsource-trending":
            return {
                "success": True,
                "platform": "customsource",
                "data": [{"title": "LegacyTrend", "hot": "88"}]
            }
        raise AssertionError(f"Unexpected method: {method}")

    monkeypatch.setattr(BaseAgent, "use_skill", fake_use_skill)

    writer = ContinuousWriter(
        write_config=ContinuousWriteConfig(trends_platforms=["customsource"], trends_limit=2)
    )
    trends = asyncio.run(writer._search_trends())

    assert called_methods[:2] == ["get_customsource_trending", "get-customsource-trending"]
    assert len(trends) == 1
    assert trends[0]["title"] == "LegacyTrend"
    assert trends[0]["platform"] == "customsource"


def test_continuous_writer_prompt_balances_trend_candidates():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    prompt = writer._build_chapter_prompt(
        chapter_number=3,
        story_beginning="",
        recent_chapters=[],
        kb_context={},
        kb_summaries=[],
        trends_data=[
            {"title": "T1", "platform": "toutiao"},
            {"title": "T2", "platform": "toutiao"},
            {"title": "T3", "platform": "toutiao"},
            {"title": "T4", "platform": "toutiao"},
            {"title": "W1", "platform": "weibo"},
            {"title": "W2", "platform": "weibo"},
        ],
        inspirations=[],
        corrections=[],
        model_switch_context="",
    )

    assert "W1" in prompt
    assert prompt.index("W1") < prompt.index("T2")


def test_continuous_writer_default_prompt_has_no_mojibake():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())

    prompt = writer._get_default_prompt()

    assert "乱码" not in prompt
    assert not writer._contains_mojibake(prompt)


def test_continuous_writer_initializes_basic_validator_without_knowledge_base():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())

    assert writer._content_validator is not None


def test_continuous_writer_system_prompt_prioritizes_memory_and_natural_trend_adaptation():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())

    prompt = writer.system_prompt

    assert "守住前文记忆" in prompt
    assert "系统已经检索好的记忆快照" in prompt
    assert "热点融入规则" in prompt
    assert "只选与当前剧情最贴合的 1 到 2 条" in prompt
    assert "不要原样照抄热点标题" in prompt
    assert "不得输出创作说明、自检报告、章节信息清单" in prompt
    assert "高频套路词" in prompt
    assert "机械情绪反应模板" in prompt
    assert "四字词" in prompt
    assert "短距离里反复使用同一词语" in prompt
    assert "对称排比句" in prompt
    assert "同样的起手节奏" in prompt
    assert "标准格式" not in prompt
    assert "林枫" not in prompt


def test_continuous_writer_rejects_mojibake_prompt():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    broken_text = "这是损坏文本：" + "\u59af\u2033\u7037"

    try:
        writer._ensure_text_integrity(broken_text, "测试提示词")
        raised = False
    except ValueError:
        raised = True

    assert raised is True


def test_continuous_writer_rejects_requirement_collection_reply():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    response = (
        "你好！看起来你想让我开始创作一部小说，但目前提供的故事开头只有\"你好\"两个字，我没有收到具体的故事设定信息，比如：\n\n"
        "- **题材/类型**：玄幻、都市、科幻、悬疑。\n"
        "- **主角信息**：名字、身份、性格。\n"
        "- **世界观/背景**：故事发生在什么世界。\n"
        "- **核心冲突/主线**：主角要面对什么问题。\n\n"
        "请把你想写的故事基本信息告诉我。"
    )

    try:
        writer._parse_chapter_response(response, chapter_number=1)
        raised = False
    except ValueError as exc:
        raised = True
        assert "未输出小说正文" in str(exc) or "列表式说明" in str(exc)

    assert raised is True


def test_continuous_writer_accepts_normal_chapter_response():
    writer = ContinuousWriter(write_config=ContinuousWriteConfig())
    response = (
        "夜雨敲窗，旧城区的路灯在水雾里晕成昏黄的圈。"
        "林渡把湿透的外套搭在椅背上，听见门外传来第三次敲门声。"
        "他没有立刻应声，只把桌角那封没有署名的信按得更紧。"
    )

    chapter = writer._parse_chapter_response(response, chapter_number=1)

    assert chapter["chapter_number"] == 1
    assert "夜雨敲窗" in chapter["content"]
    assert chapter["word_count"] > 0
