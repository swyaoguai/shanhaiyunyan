"""Tests for collaborative-mode trends injection in NovelCoordinator."""

import asyncio
import json
from unittest.mock import AsyncMock

from novel_agent.web.models.requests import WriteChapterRequest
from novel_agent.web.routes import novel as novel_routes
from novel_agent.workflow.coordinator import NovelCoordinator
from novel_agent.agents.base_agent import BaseAgent


class _FakeText:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, content=None, is_error: bool = False):
        self.content = content or []
        self.isError = is_error


def test_coordinator_search_trends_balances_multi_platforms(monkeypatch):
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

    coordinator = NovelCoordinator()
    trends = asyncio.run(coordinator._search_trends_for_collab(["toutiao", "weibo"], limit=3))

    assert [t["title"] for t in trends] == ["T1", "W1", "T2"]
    assert [t["platform"] for t in trends] == ["toutiao", "weibo", "toutiao"]


def test_coordinator_search_trends_fallbacks_to_legacy_tool_name(monkeypatch):
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

    coordinator = NovelCoordinator()
    trends = asyncio.run(coordinator._search_trends_for_collab(["customsource"], limit=2))

    assert called_methods[:2] == ["get_customsource_trending", "get-customsource-trending"]
    assert len(trends) == 1
    assert trends[0]["title"] == "LegacyTrend"
    assert trends[0]["platform"] == "customsource"


def test_coordinator_continue_chapter_includes_balanced_trends(monkeypatch):
    coordinator = NovelCoordinator()

    async def fake_search(_platforms, limit=5):
        assert limit == 5
        return [
            {"title": "T1", "platform": "toutiao"},
            {"title": "T2", "platform": "toutiao"},
            {"title": "T3", "platform": "toutiao"},
            {"title": "W1", "platform": "weibo"},
            {"title": "W2", "platform": "weibo"},
        ]

    captured_messages = {}

    async def fake_call_llm(messages, **_kwargs):
        captured_messages["messages"] = messages
        return "续写片段"

    monkeypatch.setattr(coordinator, "_search_trends_for_collab", fake_search)
    monkeypatch.setattr(coordinator.chapter_writer, "call_llm", fake_call_llm)

    result = asyncio.run(
        coordinator.continue_chapter(
            chapter_index=0,
            chapter_title="测试章",
            existing_content="已有内容",
            target_words=200,
            enable_trends=True,
            trends_platforms=["toutiao", "weibo"],
            trends_query="测试",
        )
    )

    assert result["success"] is True
    prompt = captured_messages["messages"][1]["content"]
    assert "[热点候选]" in prompt
    assert "W1" in prompt
    assert prompt.index("W1") < prompt.index("T2")


def test_novel_write_chapter_route_passes_trend_args_to_coordinator(monkeypatch):
    fake_coordinator = AsyncMock()
    fake_coordinator.continue_chapter.return_value = {"success": True, "content": "ok"}

    monkeypatch.setattr(novel_routes, "get_coordinator", lambda: fake_coordinator)

    request = WriteChapterRequest(
        action="continue",
        chapter_index=1,
        chapter_title="章节A",
        existing_content="内容A",
        word_count=300,
        enable_trends=True,
        trends_platforms=["weibo", "toutiao"],
        trends_query="关键词",
    )

    response = asyncio.run(novel_routes.write_chapter(request))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["success"] is True
    fake_coordinator.continue_chapter.assert_awaited_once_with(
        chapter_index=1,
        chapter_title="章节A",
        existing_content="内容A",
        target_words=300,
        enable_trends=True,
        trends_platforms=["weibo", "toutiao"],
        trends_query="关键词",
    )
