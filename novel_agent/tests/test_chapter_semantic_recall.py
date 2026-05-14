from types import SimpleNamespace

import pytest

from novel_agent.agents import base_agent as base_agent_module
from novel_agent.agents.chapter_writer import ChapterWriterAgent
from novel_agent.wiki.wiki_compat import WikiCompatLayer
from novel_agent.wiki.wiki_types import Frontmatter, PageType, WikiPage


class _FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=None))


def test_semantic_recall_query_uses_available_story_fields(monkeypatch):
    monkeypatch.setattr(base_agent_module, "AsyncOpenAI", _FakeAsyncOpenAI)
    agent = ChapterWriterAgent()

    query = agent.build_semantic_recall_query(
        chapter_number=7,
        chapter_title="夜入皇城",
        chapter_outline={"summary": "主角潜入皇城寻找旧案卷宗", "conflict": "禁军封锁"},
        chapter_planning="结尾留下叛徒线索",
        characters=[{"name": "秦川", "goal": "救师父"}],
        plot_thread={"writer_guidance": "推进旧案伏笔"},
        eventlines=[{"title": "皇城旧案"}],
        world={"rules": ["禁军不可私离内城"]},
        discussion_context="用户要求保持悬疑节奏",
    )

    assert "夜入皇城" in query
    assert "旧案伏笔" in query
    assert "秦川" in query
    assert "禁军不可私离内城" in query


@pytest.mark.asyncio
async def test_chapter_prompt_includes_semantic_recall_block(monkeypatch):
    monkeypatch.setattr(base_agent_module, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setenv("ENABLE_CHAPTER_SEMANTIC_RECALL", "true")
    captured = {}

    class FakeSearchResult:
        def __init__(self, document, score, metadata):
            self.document = document
            self.score = score
            self.metadata = metadata
            self.source = "hybrid"

    class FakeKB:
        def search(self, **kwargs):
            return SimpleNamespace(
                results=[
                    FakeSearchResult("上一章秦川得到青铜钥匙。", 0.82, {"chapter_id": "chapter_1", "chapter_number": 1}),
                    FakeSearchResult("当前章节草稿不应注入。", 0.91, {"chapter_id": "chapter_2", "chapter_number": 2}),
                ]
            )

        def add_chapter(self, **kwargs):
            return SimpleNamespace(success=True)

    agent = ChapterWriterAgent(knowledge_base=FakeKB())

    async def fake_call_llm(messages, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return "正文"

    monkeypatch.setattr(agent, "call_llm", fake_call_llm)
    async def fake_kb_context(*args, **kwargs):
        return {}

    monkeypatch.setattr(agent, "_get_kb_context", fake_kb_context)

    result = await agent.execute(
        {
            "chapter_number": 2,
            "chapter_title": "潜入内城",
            "chapter_outline": "秦川利用钥匙进入内城。",
            "word_count": 800,
        },
        context={
            "world": {"rules": ["内城戒严"]},
            "characters": [{"name": "秦川"}],
            "eventlines": [{"title": "旧案"}],
            "plot_thread": {"writer_guidance": "延续钥匙伏笔"},
        },
    )

    assert result["success"] is True
    assert '<context_block source="semantic_recall">' in captured["prompt"]
    assert "上一章秦川得到青铜钥匙" in captured["prompt"]
    assert "当前章节草稿不应注入" not in captured["prompt"]


@pytest.mark.asyncio
async def test_wiki_context_retrieves_previous_chapter_summaries(monkeypatch, tmp_path):
    monkeypatch.setattr(base_agent_module, "AsyncOpenAI", _FakeAsyncOpenAI)
    compat = WikiCompatLayer(tmp_path)
    compat.store.ensure_dirs()
    compat.store.save_page(WikiPage(
        frontmatter=Frontmatter(
            page_type=PageType.CHAPTER,
            title="第1章摘要",
            tags=["chapter_summary"],
            chapter_number=1,
        ),
        body="# 第1章摘要\n秦川得到青铜钥匙，并得知内城戒严。",
    ))
    compat.store.save_page(WikiPage(
        frontmatter=Frontmatter(
            page_type=PageType.CHAPTER,
            title="第2章摘要",
            tags=["chapter_summary"],
            chapter_number=2,
        ),
        body="# 第2章摘要\n当前章节摘要不应注入。",
    ))

    agent = ChapterWriterAgent()
    context = await agent._get_wiki_context("秦川 青铜钥匙 内城", chapter_number=2, project_dir=tmp_path)
    block = agent._format_wiki_context(context)

    assert "秦川得到青铜钥匙" in block
    assert "当前章节摘要不应注入" not in block
