import pytest
import asyncio
import json

from novel_agent.agents.router_agent import RouterAgent


@pytest.fixture(autouse=True)
def stub_router_intent_llm(monkeypatch):
    async def fake_call_llm(self, messages, temperature=None, **kwargs):
        prompt = messages[-1]["content"]
        # 新 prompt 格式：【用户消息】\n"xxx"
        try:
            message = prompt.split('【用户消息】\n"', 1)[1].split('"\n', 1)[0]
        except (IndexError, ValueError):
            # 兜底：尝试旧格式
            try:
                message = prompt.split('用户消息："', 1)[1].split('"', 1)[0]
            except (IndexError, ValueError):
                message = ""

        if "玄幻小说" in message:
            payload = {"intent": "create_novel", "confidence": 0.92, "fallback_intent": "general_chat"}
        elif any(token in message for token in ("主角档案", "人设卡", "角色卡", "角色加入资料库", "角色加入", "反派人物设定")):
            payload = {"intent": "create_character", "confidence": 0.91, "fallback_intent": "general_chat"}
        elif "事件线" in message:
            payload = {"intent": "create_eventlines", "confidence": 0.9, "fallback_intent": "general_chat"}
        elif "细纲" in message:
            payload = {"intent": "create_detail_outline", "confidence": 0.9, "fallback_intent": "general_chat"}
        elif "章纲" in message:
            payload = {"intent": "create_chapter_settings", "confidence": 0.9, "fallback_intent": "general_chat"}
        elif "继续写第10章" in message:
            payload = {"intent": "continue_write", "confidence": 0.93, "fallback_intent": "general_chat"}
        elif "润色" in message:
            payload = {"intent": "polish_content", "confidence": 0.88, "fallback_intent": "general_chat"}
        elif "唐朝的官职体系" in message:
            payload = {"intent": "search_web", "confidence": 0.9, "fallback_intent": "query_knowledge"}
        elif "热梗" in message:
            payload = {"intent": "search_trends", "confidence": 0.9, "fallback_intent": "search_web"}
        elif "主角现在是什么境界" in message:
            payload = {"intent": "query_knowledge", "confidence": 0.85, "fallback_intent": "general_chat"}
        else:
            payload = {"intent": "general_chat", "confidence": 0.5, "fallback_intent": "general_chat"}
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(RouterAgent, "call_llm", fake_call_llm)


@pytest.mark.asyncio
async def test_intent_create_novel():
    ra = RouterAgent()
    ia = await ra.analyze_intent("我想写一部玄幻小说")
    assert ia.primary_intent.value == "create_novel"
    assert ia.confidence >= 0.5


@pytest.mark.asyncio
async def test_creation_requirement_extraction_uses_model_for_ancient_romance_request(monkeypatch):
    async def fake_call_llm(self, messages, temperature=None, **kwargs):
        return json.dumps({
            "is_creation_request": True,
            "novel_type": "古代言情",
            "theme": "古代、姐弟恋、团宠",
            "requirements": "篇幅约50000字；主角姓名与人物设定由助手合理安排",
            "protagonist": "",
            "plot_idea": "",
            "volume_count": 1,
            "chapters_per_volume": 17,
            "target_word_count": 50000,
            "confidence": 0.9,
        }, ensure_ascii=False)

    monkeypatch.setattr(RouterAgent, "call_llm", fake_call_llm)

    ra = RouterAgent()
    message = "我想写一本古代的姐弟恋团宠小说，篇幅在5w字左右。主角名字什么的你帮我安排"

    info = await ra._build_creation_requirements_async({}, message)

    assert info["novel_type"] == "古代言情"
    assert info["theme"] == "古代、姐弟恋、团宠"
    assert info["target_word_count"] == 50000
    assert info["chapters_per_volume"] > 5
    assert info.get("protagonist", "") == ""
    assert info["plot_idea"] == ""
    assert "主角姓名与人物设定由助手合理安排" in info["requirements"]
    assert info["ai_autonomy_requested"] is True


@pytest.mark.asyncio
async def test_creation_requirement_extraction_marks_freeform_ai_autonomy(monkeypatch):
    async def fake_call_llm(self, messages, temperature=None, **kwargs):
        return json.dumps({
            "is_creation_request": True,
            "novel_type": "古代言情",
            "theme": "古代甜宠",
            "requirements": "篇幅约50000字",
            "protagonist": "",
            "plot_idea": "",
            "volume_count": 1,
            "chapters_per_volume": 17,
            "target_word_count": 50000,
            "ai_autonomy_requested": True,
            "confidence": 0.9,
        }, ensure_ascii=False)

    monkeypatch.setattr(RouterAgent, "call_llm", fake_call_llm)

    ra = RouterAgent()
    message = "我想写一本古代的甜宠题材小说，篇幅5W字，其他的你随便帮我安排"

    info = await ra._build_creation_requirements_async({}, message)

    assert info["ai_autonomy_requested"] is True
    assert "未指定的世界观、角色姓名、人物设定和剧情细节由助手自主创作" in info["requirements"]
    assert info["plot_idea"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "创建主角档案",
        "给主角做个人设卡",
        "把这个角色加入资料库：林渡，少年剑修，宗门遗孤",
        "设计反派人物设定：裴烬，前任圣子，已堕魔",
        "请帮我生成主角角色卡：林渡，少年剑修，宗门遗孤",
        "把角色加入资料库，林渡，少年剑修",
    ],
)
async def test_intent_create_character_variants(message):
    ra = RouterAgent()
    ia = await ra.analyze_intent(message)
    assert ia.primary_intent.value == "create_character"
    assert ia.confidence >= 0.85


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("帮我梳理一下这本书的事件线", "create_eventlines"),
        ("根据现在的设定生成细纲", "create_detail_outline"),
        ("把章纲也补出来", "create_chapter_settings"),
    ],
)
async def test_intent_detects_other_knowledge_generation_requests(message, expected_intent):
    ra = RouterAgent()
    ia = await ra.analyze_intent(message)
    assert ia.primary_intent.value == expected_intent


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
    assert ia.primary_intent.value == "query_knowledge"
    assert ia.requires_knowledge_base is True


@pytest.mark.asyncio
async def test_intent_analysis_raises_when_llm_returns_invalid_json(monkeypatch):
    """当LLM返回无效JSON时，应抛出 RuntimeError（不回退到规则）。"""
    async def invalid_call_llm(self, messages, temperature=None, **kwargs):
        return "not-json"

    monkeypatch.setattr(RouterAgent, "call_llm", invalid_call_llm)

    ra = RouterAgent()
    with pytest.raises(RuntimeError, match="LLM意图分析全部重试失败"):
        await ra.analyze_intent("继续写第10章")


@pytest.mark.asyncio
async def test_intent_analysis_uses_llm_directly(monkeypatch):
    """LLM意图识别是唯一路径，不依赖规则兜底。"""
    async def fake_call_llm(self, messages, temperature=None, **kwargs):
        return json.dumps({"intent": "create_character", "confidence": 0.97, "fallback_intent": "general_chat"}, ensure_ascii=False)

    monkeypatch.setattr(RouterAgent, "call_llm", fake_call_llm)

    ra = RouterAgent()
    ia = await ra.analyze_intent("帮我写一个玄幻小说")

    assert ia.primary_intent.value == "create_character"
    assert ia.confidence >= 0.9
