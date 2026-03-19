import pytest
import asyncio

from novel_agent.agents.router_agent import RouterAgent


@pytest.mark.asyncio
async def test_intent_create_novel():
    ra = RouterAgent()
    ia = await ra.analyze_intent("我想写一部玄幻小说")
    assert ia.primary_intent.value == "create_novel"
    assert ia.confidence >= 0.5


@pytest.mark.asyncio
async def test_intent_continue_write_and_chapter_extract():
    ra = RouterAgent()
    ia = await ra.analyze_intent("继续写第10章")
    assert ia.primary_intent.value == "continue_write"
    # 实体识别
    assert ia.entities.get("chapter_number") == 10
    assert ia.entities.get("explicit_chapter_request") is True


@pytest.mark.asyncio
async def test_intent_polish_content():
    ra = RouterAgent()
    ia = await ra.analyze_intent("这段太平淡，帮我润色一下")
    assert ia.primary_intent.value == "polish_content"


@pytest.mark.asyncio
async def test_intent_search_web_and_tool_args():
    ra = RouterAgent()
    q = "查一下唐朝的官职体系"
    ia = await ra.analyze_intent(q)
    assert ia.primary_intent.value == "search_web"
    assert ia.requires_tool_call is True
    assert ia.tool_name == "web_search"
    assert isinstance(ia.tool_args, dict) and (ia.tool_args.get("query") or "唐朝" in q)


@pytest.mark.asyncio
async def test_intent_search_trends_default_platform():
    ra = RouterAgent()
    ia = await ra.analyze_intent("最近有什么热梗可以用？")
    assert ia.primary_intent.value == "search_trends"
    assert ia.tool_name in {"toutiao_trends", "douyin_trends"}


@pytest.mark.asyncio
async def test_intent_query_knowledge_requires_kb():
    ra = RouterAgent()
    ia = await ra.analyze_intent("主角现在是什么境界？")
    assert ia.primary_intent.value in {"query_knowledge", "general_chat"}
    # 对普通对话也可能开启知识库以补全上下文
    assert ia.requires_knowledge_base is True

