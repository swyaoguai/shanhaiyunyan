"""Tests for trend ingestion in ContinuousWriter."""

import asyncio
import json

from novel_agent.agents.continuous_writer import ContinuousWriteConfig, ContinuousWriter
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
