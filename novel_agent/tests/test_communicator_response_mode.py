"""
测试 Communicator 显式 response_mode 调用链
"""

import pytest
import json

from novel_agent.agents.communicator import CommunicatorAgent
from novel_agent.web.routes.chat import _infer_communicator_response_mode


class DummyCommunicator(CommunicatorAgent):
    """避免真实 LLM 调用的测试替身"""

    def __init__(self):
        super().__init__(knowledge_base=None, router_agent=None)
        self.captured_messages = None

    async def _check_auto_tool_call(self, message: str):
        return None

    async def _retrieve_knowledge_context(self, message: str):
        return []

    async def call_llm(self, messages, temperature=None, stream=False, **kwargs):
        self.captured_messages = messages
        return '{"extracted_info": {}, "reply": "测试回复", "is_complete": false}'


class IntentFallbackCommunicator(CommunicatorAgent):
    """用于测试搜索意图失败兜底。"""

    def __init__(self, llm_response: str):
        super().__init__(knowledge_base=None, router_agent=None)
        self.llm_response = llm_response

    async def call_llm(self, messages, temperature=None, stream=False, **kwargs):
        return self.llm_response


class RuntimeProgressCommunicator(CommunicatorAgent):
    """用于测试 runtime_context 注入的 progress_callback。"""

    def __init__(self):
        super().__init__(knowledge_base=None, router_agent=None)

    async def _check_auto_tool_call(self, message: str):
        return None

    async def _retrieve_knowledge_context(self, message: str):
        return []

    async def call_llm(self, messages, temperature=None, stream=False, **kwargs):
        assert self.callback_handler is not None
        await self._emit_callback_event({
            "type": "llm_chunk",
            "agent": self.name,
            "content": "流式片段",
        })
        return '{"extracted_info": {}, "reply": "最终回复", "is_complete": false}'


class StreamFallbackCommunicator(CommunicatorAgent):
    """用于测试消息总线回退链路会把事件透传给回调。"""

    def __init__(self):
        super().__init__(knowledge_base=None, router_agent=None)

    async def send_task_stream(self, receiver, task_type, task_data, context=None, timeout=0):
        yield {
            "msg_type": "task_progress",
            "payload": {
                "type": "progress_update",
                "agent": receiver,
                "message": "正在生成大纲",
                "progress": 30,
            },
        }
        yield {
            "msg_type": "task_progress",
            "payload": {
                "type": "llm_chunk",
                "agent": receiver,
                "content": "第一卷",
            },
        }
        yield {
            "msg_type": "task_completed",
            "payload": {
                "result": {
                    "outline": {"title": "测试大纲"},
                }
            },
        }


class PartialStreamFailureCommunicator(CommunicatorAgent):
    """用于测试流式中断时返回部分结果而非直接报错。"""

    def __init__(self):
        super().__init__(knowledge_base=None, router_agent=None)

    async def _check_auto_tool_call(self, message: str):
        return None

    async def _retrieve_knowledge_context(self, message: str):
        return []

    async def call_llm(self, messages, temperature=None, stream=False, **kwargs):
        async def _stream():
            yield "第一段"
            yield "第二段"
            raise Exception("stream error: stream ID 149; INTERNAL_ERROR; received from peer")

        return _stream()


class TestCommunicatorResponseModeInference:
    """测试 Communicator 回复模式推断"""

    def test_infer_confirmation_from_create_command(self):
        result = _infer_communicator_response_mode(
            processed_message="开始创作",
            targeted_command={"name": "create"},
            routing_hint={"intent": "general_chat"},
        )
        assert result == "confirmation"

    def test_infer_confirmation_from_create_intent(self):
        result = _infer_communicator_response_mode(
            processed_message="我要开始写小说",
            routing_hint={"intent": "create_novel"},
            targeted_command=None,
        )
        assert result == "confirmation"

    def test_infer_summary(self):
        result = _infer_communicator_response_mode(
            processed_message="帮我总结一下现在的设定",
            routing_hint={"intent": "general_chat"},
            targeted_command=None,
        )
        assert result == "summary"

    def test_infer_comparison(self):
        result = _infer_communicator_response_mode(
            processed_message="请对比方案A和方案B的优缺点",
            routing_hint={"intent": "general_chat"},
            targeted_command=None,
        )
        assert result == "comparison"

    def test_infer_planning(self):
        result = _infer_communicator_response_mode(
            processed_message="下一步怎么做，给我一个步骤计划",
            routing_hint={"intent": "general_chat"},
            targeted_command=None,
        )
        assert result == "planning"

    def test_infer_lightweight_by_default(self):
        result = _infer_communicator_response_mode(
            processed_message="主角名字我想再改一下",
            routing_hint={"intent": "general_chat"},
            targeted_command=None,
        )
        assert result == "lightweight"


class TestCommunicatorResponseModePropagation:
    """测试 response_mode 是否进入 Communicator 分析提示"""

    @pytest.mark.asyncio
    async def test_chat_injects_planning_mode_into_analysis_prompt(self):
        agent = DummyCommunicator()

        result = await agent.chat(
            "告诉我下一步怎么做",
            runtime_context={"response_mode": "planning"},
        )

        assert result["reply"] == "测试回复"
        assert agent.captured_messages is not None
        assert len(agent.captured_messages) >= 1

        analysis_prompt = agent.captured_messages[-1]["content"]
        assert "当前回复模式：planning" in analysis_prompt
        assert "planning：适合执行计划，优先有序列表" in analysis_prompt

    @pytest.mark.asyncio
    async def test_chat_uses_lightweight_as_default_response_mode(self):
        agent = DummyCommunicator()

        await agent.chat("随便聊聊主角设定")

        analysis_prompt = agent.captured_messages[-1]["content"]
        assert "当前回复模式：lightweight" in analysis_prompt
        assert "不要在 lightweight 模式下过度结构化" in analysis_prompt

    @pytest.mark.asyncio
    async def test_chat_installs_runtime_progress_callback_for_nested_stream_events(self):
        agent = RuntimeProgressCommunicator()
        received = []

        async def progress_callback(data):
            received.append(dict(data))

        result = await agent.chat(
            "测试一下流式回调",
            runtime_context={"progress_callback": progress_callback},
        )

        assert result["reply"] == "最终回复"
        assert received
        assert received[0]["type"] == "llm_chunk"
        assert received[0]["content"] == "流式片段"
        assert agent.callback_handler is None


class TestCommunicatorRequirementExtraction:
    """测试沟通阶段的轻量需求抽取。"""

    def test_extracts_per_chapter_words_as_discussable_requirement(self):
        info = CommunicatorAgent._extract_info_from_user_message("全书5w字左右，每章2500字，卷数我们再讨论")

        assert info["target_word_count"] == 50000
        assert info["target_words_per_chapter"] == 2500
        assert info["target_words_per_chapter_source"] == "user"

    def test_per_chapter_words_do_not_become_total_words(self):
        info = CommunicatorAgent._extract_info_from_user_message("先按每章0.3w字来规划")

        assert info["target_words_per_chapter"] == 3000
        assert "target_word_count" not in info


class TestCommunicatorSearchIntentFallback:
    """测试搜索意图判定失败时的兜底逻辑。"""

    @pytest.mark.asyncio
    async def test_detect_search_intent_uses_heuristic_when_llm_returns_empty(self):
        agent = IntentFallbackCommunicator("")

        result = await agent._detect_search_intent("帮我搜索一下足球梗和足球术语")

        assert result is not None
        assert result["need_search"] is True
        assert result["query"] == "足球梗和足球术语"
        assert result["source"] == "heuristic_fallback"

    @pytest.mark.asyncio
    async def test_detect_search_intent_does_not_false_positive_on_progress_prompt(self):
        agent = IntentFallbackCommunicator("")

        result = await agent._detect_search_intent("搜索结果出来了吗")

        assert result is None


class TestCommunicatorChatStreamRecovery:
    @pytest.mark.asyncio
    async def test_chat_stream_returns_partial_done_when_stream_breaks_after_chunks(self):
        agent = PartialStreamFailureCommunicator()

        events = []
        async for event in agent.chat_stream("继续"):
            events.append(event)

        joined = "".join(events)
        done_event = next(event for event in events if '"type": "done"' in event or '"type":"done"' in event)
        done_payload = json.loads(done_event.split("data: ", 1)[1])

        assert "第一段" in joined
        assert "第二段" in joined
        assert done_payload["reply"] == "第一段第二段"
        assert done_payload["interrupted"] is True
        assert "warning" in done_payload
        assert not any('"type": "error"' in event or '"type":"error"' in event for event in events)


class TestCommunicatorStreamingTaskFallback:
    """测试 Communicator 消息总线回退链路的流式事件转发。"""

    @pytest.mark.asyncio
    async def test_request_outline_forwards_progress_and_llm_chunks_to_callback(self):
        agent = StreamFallbackCommunicator()
        received = []

        async def progress_callback(data):
            received.append(dict(data))

        agent.set_callback_handler(progress_callback)

        result = await agent.request_outline(
            world={"world_name": "玄荒界"},
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=5,
        )

        assert result["outline"]["title"] == "测试大纲"
        assert len(received) == 2
        assert received[0]["type"] == "progress_update"
        assert received[0]["message"] == "正在生成大纲"
        assert received[0]["current_agent"] == "Outliner"
        assert received[1]["type"] == "llm_chunk"
        assert received[1]["content"] == "第一卷"
        assert received[1]["current_agent"] == "Outliner"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
