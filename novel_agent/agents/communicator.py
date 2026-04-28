"""
沟通智能体 - 与用户进行多轮对话收集创作需求

增强功能：
- 集成智能路由：自动识别用户意图
- 知识库优先：回复前先检索知识库
- 自动工具调用：识别隐含的搜索需求
- 知识库混入：统一的知识库访问接口
- 共享上下文：支持多Agent协作时的状态共享
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, AsyncGenerator

from .base_agent import BaseAgent
from .knowledge_mixin import KnowledgeBaseMixin, SharedKnowledgeContext
from ..constants import AGENT_TEMPERATURE, WRITING_CONFIG, TIMEOUTS

logger = logging.getLogger(__name__)

# 热点平台映射（只保留能正常工作的平台）
# 热点平台映射（只保留抖音和头条）
TRENDS_PLATFORMS = {
    "douyin": "抖音热点",
    "toutiao": "头条热榜"
}

# 自动工具调用的触发模式（已废弃，改用LLM智能判断）
# 保留用于热点搜索的简单匹配
AUTO_TOOL_PATTERNS = {
    "trends_search": [
        r"(今日|今天|最新|实时).{0,10}(热点|热搜|热榜)",
        r"(头条|抖音|微博).{0,10}(热搜|热榜|热点)",
        r"(看看|查看|获取).{0,10}(热点|热搜)",
    ]
}


def _strip_technical_markers(text: str) -> str:
    """移除技术标记，并从JSON格式中提取reply字段"""
    text = str(text or "").replace("[INFO_COMPLETE]", "").strip()
    
    # 如果文本看起来像JSON，尝试提取reply字段
    if text.startswith('{') and '"reply"' in text:
        try:
            import json as _json
            # 尝试解析JSON
            json_match = __import__('re').search(r'\{[\s\S]*\}', text)
            if json_match:
                data = _json.loads(json_match.group())
                if isinstance(data, dict) and "reply" in data:
                    reply = str(data["reply"] or "").strip()
                    if reply:
                        return reply
        except (ValueError, KeyError, TypeError):
            pass
    
    return text


class CommunicatorAgent(BaseAgent, KnowledgeBaseMixin):
    """
    沟通智能体
    通过多轮对话与用户交互，收集并整理小说创作需求
    
    增强功能：
    - 自动意图识别：识别用户的隐含需求
    - 知识库检索：回复前先查询相关上下文
    - 智能工具调用：自动识别并调用MCP工具
    - 知识库混入：统一的高级搜索、约束检测
    - 共享上下文：支持多Agent协作状态传递
    """
    
    def __init__(self, knowledge_base=None, router_agent=None):
        super().__init__(name="Communicator", prompt_file="communicator.md")
        
        # 初始化知识库混入
        self.init_knowledge_mixin(knowledge_base)
        
        self.conversation_history: List[Dict[str, str]] = []
        self.collected_info: Dict[str, Any] = {}
        self.required_fields = [
            "novel_type",      # 小说类型
            "theme",           # 主题风格
            "protagonist",     # 主角设定
            "plot_idea",       # 剧情构思
            "volume_count",    # 卷数
            "chapters_per_volume"  # 每卷章节数
        ]
        
        # 路由器（用于增强响应）
        self.router_agent = router_agent
        
        # 共享知识上下文（用于多Agent协作）
        self._shared_context: Optional[SharedKnowledgeContext] = None

    def _get_runtime_progress_callback(self, runtime_context: Optional[Dict[str, Any]]) -> Optional[Any]:
        """从运行时上下文中提取临时进度回调。"""
        if not isinstance(runtime_context, dict):
            return None
        callback = runtime_context.get("progress_callback")
        return callback if callback else None

    def _install_runtime_progress_callback(self, runtime_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        将 runtime_context 中的 progress_callback 临时并入当前 callback_handler。

        返回旧 handler，供调用方在 finally 中恢复。
        """
        progress_callback = self._get_runtime_progress_callback(runtime_context)
        if not progress_callback:
            return {"installed": False, "previous_handler": self.callback_handler}

        previous_handler = self.callback_handler

        async def combined_handler(data: Dict[str, Any]) -> Optional[Any]:
            result: Optional[Any] = None
            for handler in (progress_callback, previous_handler):
                if not handler:
                    continue
                current = handler(data)
                if hasattr(current, "__await__"):
                    current = await current
                if current is not None:
                    result = current
            return result

        self.set_callback_handler(combined_handler)
        return {"installed": True, "previous_handler": previous_handler}

    def _restore_runtime_progress_callback(self, callback_state: Optional[Dict[str, Any]]) -> None:
        """恢复临时安装前的 callback_handler。"""
        if not isinstance(callback_state, dict) or not callback_state.get("installed"):
            return
        self.set_callback_handler(callback_state.get("previous_handler"))

    async def _forward_stream_task_event(self, receiver: str, payload: Optional[Dict[str, Any]]) -> None:
        """将消息总线流式任务事件转发给上游 callback。"""
        if not isinstance(payload, dict) or not payload:
            return

        forwarded = dict(payload)
        forwarded.setdefault("agent", str(payload.get("agent") or receiver).strip() or receiver)
        forwarded.setdefault("current_agent", receiver)

        if forwarded.get("type") == "llm_chunk" and not forwarded.get("content"):
            forwarded["content"] = str(forwarded.get("delta") or "")

        await self._emit_callback_event(forwarded)

    async def _run_streaming_task_fallback(
        self,
        receiver: str,
        task_type: str,
        task_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        timeout: float = TIMEOUTS.AGENT_LONG,
    ) -> Dict[str, Any]:
        """通过消息总线流式执行子任务，并把过程事件向上游透传。"""
        final_result: Optional[Dict[str, Any]] = None

        async for event in self.send_task_stream(
            receiver=receiver,
            task_type=task_type,
            task_data=task_data,
            context=context,
            timeout=timeout,
        ):
            msg_type = str(event.get("msg_type") or "").strip()
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

            if msg_type in {"task_progress", "user_input_required"}:
                await self._forward_stream_task_event(receiver, payload)
                continue

            if msg_type == "task_completed":
                result_payload = payload.get("result")
                if isinstance(result_payload, dict):
                    final_result = result_payload
                else:
                    final_result = {"result": result_payload}
                break

            if msg_type == "task_failed":
                error_text = str(
                    payload.get("error")
                    or payload.get("message")
                    or (payload.get("result") or {}).get("error")
                    or f"{receiver} 执行失败"
                ).strip()
                await self._forward_stream_task_event(receiver, {
                    "type": "agent_task_failed",
                    "agent": receiver,
                    "current_agent": receiver,
                    "message": error_text,
                    "error": error_text,
                    "content": error_text,
                })
                return {"error": error_text}

        if final_result is not None:
            return final_result
        return {"error": f"{receiver} 超时未完成"}
    
    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import COMMUNICATOR_AGENT_PROMPT
        return COMMUNICATOR_AGENT_PROMPT
    
    async def start_conversation(self) -> str:
        """开始对话，发送开场白"""
        self.conversation_history = []
        self.collected_info = {}
        
        opening = """你好！我是小说创作顾问，很高兴为你服务！🎉

在开始创作之前，我想先了解一下你的想法。

**请告诉我，你想创作什么类型的小说呢？**

比如：
- 🗡️ 玄幻/仙侠 - 修炼升级，热血战斗
- 🏙️ 都市/现代 - 贴近生活，情感故事
- 🚀 科幻/未来 - 星际冒险，科技想象
- 💕 言情/甜宠 - 浪漫爱情，甜蜜日常

或者你有其他想法也可以直接告诉我~"""
        
        self.conversation_history.append({
            "role": "assistant",
            "content": opening
        })
        
        return opening
    
    async def chat(self, user_message: str, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理用户消息，返回回复
        
        增强流程：
        1. 检测自动工具调用需求
        2. 知识库检索获取上下文
        3. 分析用户输入
        4. 生成响应
        
        Args:
            user_message: 用户输入
            runtime_context: 路由器或外部执行链注入的运行时上下文
            
        Returns:
            {
                "reply": "AI回复",
                "is_complete": bool,  # 信息是否收集完成
                "collected_info": {}  # 已收集的信息
            }
        """
        runtime_context = runtime_context or {}
        response_mode = str(runtime_context.get("response_mode") or "lightweight").strip() or "lightweight"

        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        callback_state = self._install_runtime_progress_callback(runtime_context)
        try:
            # === 步骤1: 检测自动工具调用需求 ===
            auto_tool_result = await self._check_auto_tool_call(user_message)

            external_tool_result = runtime_context.get("tool_results") if isinstance(runtime_context, dict) else None
            if (
                (not auto_tool_result or not auto_tool_result.get("success"))
                and isinstance(external_tool_result, dict)
                and external_tool_result.get("success")
            ):
                auto_tool_result = external_tool_result
            
            # === 步骤2: 知识库检索 ===
            kb_context = await self._retrieve_knowledge_context(user_message)
            external_knowledge = runtime_context.get("knowledge") if isinstance(runtime_context, dict) else None
            if isinstance(external_knowledge, list) and external_knowledge:
                merged_kb_context = []
                seen_keys = set()

                for item in list(external_knowledge) + list(kb_context):
                    if isinstance(item, dict):
                        content = str(item.get("content") or "").strip()
                        score = item.get("score", 0.0)
                        normalized_item = dict(item)
                    else:
                        content = str(item).strip()
                        score = 0.0
                        normalized_item = {"content": content, "score": score}

                    if not content:
                        continue

                    dedup_key = (content[:200], str(score))
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    merged_kb_context.append(normalized_item)

                kb_context = merged_kb_context
            
            # === 步骤3: 构建增强提示 ===
            analysis_prompt = self._build_analysis_prompt(
                user_message,
                auto_tool_result,
                kb_context,
                response_mode=response_mode,
            )
            
            messages = self.conversation_history.copy()
            messages.append({"role": "user", "content": analysis_prompt})
            
            response = await self.call_llm(messages, temperature=AGENT_TEMPERATURE.CREATIVE_HIGH)
            
            # 解析JSON响应
            result = self._parse_response(response)
            
            # 更新收集的信息
            if result.get("extracted_info"):
                self.collected_info.update(result["extracted_info"])
            
            # 获取AI回复
            reply = result.get("reply", response)
            
            # === 步骤4: 处理热点搜索（兼容旧逻辑） ===
            reply, trends_data = await self._process_trends_search(reply, user_message)
            
            # === 步骤5: 整合自动工具调用结果 ===
            # 注意：web_search结果已在_build_analysis_prompt中传递给LLM分析
            # 只有trends_search等其他工具才需要追加到回复中
            if auto_tool_result and auto_tool_result.get("success"):
                tool = auto_tool_result.get("tool", "")
                if tool != "web_search":  # web_search结果不追加，已由LLM分析
                    tool_text = self._format_auto_tool_result(auto_tool_result)
                    if tool_text and tool_text not in reply:
                        reply = f"{reply}\n\n{tool_text}"
            
            # 移除技术标记（不应该显示给用户），再写入对话历史
            reply_clean = _strip_technical_markers(reply)
            self.conversation_history.append({
                "role": "assistant",
                "content": reply_clean
            })
            
            response_data = {
                "reply": reply_clean,
                "is_complete": result.get("is_complete", False) or "[INFO_COMPLETE]" in reply,
                "collected_info": self.collected_info,
                "knowledge_used": bool(kb_context),
                "auto_tool_called": bool(auto_tool_result)
            }
            
            # 如果有热点数据，添加到响应中
            if trends_data:
                response_data["trends"] = trends_data
            
            return response_data
            
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            # 确保有响应（响应保证机制）
            return {
                "reply": "抱歉，我遇到了一些问题。能重新告诉我你的想法吗？",
                "is_complete": False,
                "collected_info": self.collected_info,
                "error": str(e)
            }
        finally:
            self._restore_runtime_progress_callback(callback_state)

    async def chat_stream(
        self,
        user_message: str,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式处理用户消息，逐块返回SSE事件

        预处理（工具调用、知识库）同步完成后，流式输出LLM回复。

        Yields:
            SSE格式字符串: data: {"type": "chunk/done/error", ...}\n\n
        """
        import json as _json

        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        callback_state = self._install_runtime_progress_callback(runtime_context)
        try:
            runtime_context = runtime_context or {}
            response_mode = str(runtime_context.get("response_mode") or "lightweight").strip() or "lightweight"

            # === 预处理（同步） ===
            auto_tool_result = await self._check_auto_tool_call(user_message)
            kb_context = await self._retrieve_knowledge_context(user_message)

            # 构建流式提示（不要求JSON格式）
            analysis_prompt = self._build_stream_prompt(
                user_message, auto_tool_result, kb_context, response_mode=response_mode
            )

            messages = self.conversation_history.copy()
            messages.append({"role": "user", "content": analysis_prompt})

            # === 流式LLM调用 ===
            logger.info(f"[{self.name}] 开始流式LLM调用...")
            stream = await self.call_llm(
                messages, temperature=AGENT_TEMPERATURE.CREATIVE_HIGH, stream=True
            )

            full_text = ""
            visible_text = ""
            chunk_count = 0
            marker = "[INFO_COMPLETE]"
            json_extracted_reply = ""
            
            async for chunk in stream:
                chunk_count += 1
                full_text += chunk

                # 检测LLM是否输出了JSON格式（而非纯文本）
                if not json_extracted_reply:
                    json_match = re.search(r'\{[\s\S]*"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', full_text)
                    if json_match:
                        json_extracted_reply = json_match.group(1).replace('\\"', '"').replace('\\n', '\n')
                        logger.info(f"[{self.name}] 检测到JSON格式输出，提取reply字段")
                
                # 如果已提取到reply，使用提取的内容
                if json_extracted_reply:
                    current_visible_text = json_extracted_reply.replace(marker, "")
                else:
                    # 正常模式：过滤技术标记
                    current_visible_text = full_text.replace(marker, "")
                    # 如果文本以JSON开头，等待更多内容再决定是否输出
                    stripped = current_visible_text.lstrip()
                    if stripped.startswith('{') and '"reply"' not in stripped[:200]:
                        visible_text = current_visible_text
                        continue
                
                visible_delta = current_visible_text[len(visible_text):]
                visible_text = current_visible_text

                if visible_delta:
                    yield f"data: {_json.dumps({'type': 'chunk', 'content': visible_delta}, ensure_ascii=False)}\n\n"
            
            # 如果从JSON中提取了reply，更新full_text
            if json_extracted_reply:
                full_text = json_extracted_reply
            
            logger.info(f"[{self.name}] 流式输出完成，共 {chunk_count} 个chunk，总长度 {len(full_text)} 字符")

            # === 后处理 ===
            # 流式模式下不需要处理热点搜索，因为：
            # 1. 热点搜索已在预处理阶段通过auto_tool_result处理
            # 2. LLM的回复已经流式输出给用户
            # 3. 不应该在流式输出后再修改回复内容
            
            reply = full_text  # 原始完整输出，仅用于完成标记判断
            reply_clean = _strip_technical_markers(reply)

            # 添加AI回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": reply_clean
            })

            # 发送完成事件
            done_data = {
                "type": "done",
                "reply": reply_clean,
                "is_complete": marker in reply,
                "collected_info": self.collected_info,
                "knowledge_used": bool(kb_context),
                "auto_tool_called": bool(auto_tool_result)
            }
            yield f"data: {_json.dumps(done_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            if visible_text:
                logger.warning(
                    f"[{self.name}] Chat stream interrupted after partial output, returning partial reply: {e}",
                    exc_info=True,
                )
                reply = full_text
                reply_clean = _strip_technical_markers(reply)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": reply_clean
                })
                done_data = {
                    "type": "done",
                    "reply": reply_clean,
                    "is_complete": marker in reply,
                    "collected_info": self.collected_info,
                    "knowledge_used": bool(kb_context),
                    "auto_tool_called": bool(auto_tool_result),
                    "interrupted": True,
                    "warning": "回复在流式传输阶段中断，已返回已生成内容。",
                }
                yield f"data: {_json.dumps(done_data, ensure_ascii=False)}\n\n"
            else:
                logger.error(f"Chat stream error: {e}", exc_info=True)
                yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            self._restore_runtime_progress_callback(callback_state)

    def _build_stream_prompt(
        self,
        user_message: str,
        auto_tool_result: Optional[Dict[str, Any]],
        kb_context: List[Dict[str, Any]],
        response_mode: str = "lightweight",
    ) -> str:
        """构建流式模式的分析提示（不要求JSON格式）"""
        parts = []

        parts.append(f"当前已收集的信息：\n{json.dumps(self.collected_info, ensure_ascii=False, indent=2)}")
        parts.append(f'\n用户刚才说："{user_message}"')

        if kb_context:
            kb_text = "\n".join([f"- {r.get('content', '')[:150]}..." for r in kb_context[:3]])
            parts.append(f"\n【知识库相关内容】\n{kb_text}")

        if auto_tool_result and auto_tool_result.get("success"):
            tool = auto_tool_result.get("tool", "")
            tool_data = auto_tool_result.get("data", [])
            
            if tool_data and tool == "web_search":
                # 网络搜索：传递原始数据供LLM分析
                query = auto_tool_result.get("query", "")
                search_content = []
                for i, item in enumerate(tool_data[:5], 1):
                    title = item.get("title", "")
                    desc = item.get("description") or item.get("snippet", "")
                    if title:
                        search_content.append(f"{i}. {title}")
                        if desc:
                            search_content.append(f"   {desc[:200]}")
                
                parts.append(f"\n【网络搜索结果】（关键词：{query}）")
                parts.append("\n".join(search_content))
                parts.append("\n**重要指令**：")
                parts.append("1. 仔细分析以上搜索结果")
                parts.append("2. 提取适合融入小说创作的元素（梗、术语、黑话、背景资料等）")
                parts.append("3. **立即回复用户**，告诉他们你找到了什么有用的内容")
                parts.append("4. 给出具体的创作建议，说明如何将这些元素融入剧情")
            
            elif tool_data:
                # 其他工具：使用原有格式化方法
                tool_text = self._format_auto_tool_result(auto_tool_result)
                if tool_text:
                    parts.append(f"\n【工具调用结果】\n{tool_text[:500]}...")

        parts.append(f"""
当前回复模式：{response_mode}

回复模式要求：
- lightweight：自然追问或轻量回应，不要过度分块
- summary：用结构化 Markdown 总结已知信息
- confirmation：用结构化 Markdown 给出确认稿与下一步
- comparison：如涉及方案对比，优先表格
- planning：如涉及执行路径，优先有序列表

**重要**：请直接用自然语言回复用户，使用Markdown格式排版（标题、列表、粗体等）。
**绝对不要**输出JSON格式、代码块、或任何技术标记。
结合知识库内容和工具结果给出准确、有条理的回复。
如果信息已经足够，在回复末尾加上 [INFO_COMPLETE]。""")

        return "\n".join(parts)

    async def _check_auto_tool_call(self, message: str) -> Optional[Dict[str, Any]]:
        """
        检测并执行自动工具调用
        
        使用LLM智能判断用户是否需要搜索，而不是简单的正则匹配
        
        Args:
            message: 用户消息
            
        Returns:
            工具调用结果，如果不需要调用则返回None
        """
        # 使用LLM判断是否需要网络搜索
        search_intent = await self._detect_search_intent(message)
        
        if search_intent and search_intent.get("need_search"):
            query = search_intent.get("query", message)
            logger.info(f"[{self.name}] LLM检测到搜索需求: {query}")
            
            try:
                results = await self.web_search(query, limit=5)
                return {
                    "success": True,
                    "tool": "web_search",
                    "query": query,
                    "data": results
                }
            except Exception as e:
                logger.warning(f"[{self.name}] 自动网络搜索失败: {e}")
                return {"success": False, "tool": "web_search", "error": str(e)}
        
        # 检查热点搜索模式（保留简单正则匹配）
        for pattern in AUTO_TOOL_PATTERNS.get("trends_search", []):
            if re.search(pattern, message):
                platform = self._detect_platform(message) or "toutiao"
                logger.info(f"[{self.name}] 自动触发热点搜索: {platform}")
                
                try:
                    trends = await self.search_trends(platform, limit=10)
                    return {
                        "success": True,
                        "tool": "trends_search",
                        "platform": platform,
                        "data": trends
                    }
                except Exception as e:
                    logger.warning(f"[{self.name}] 自动热点搜索失败: {e}")
                    return {"success": False, "tool": "trends_search", "error": str(e)}
        
        return None
    
    async def _retrieve_knowledge_context(self, message: str) -> List[Dict[str, Any]]:
        """
        从知识库检索相关上下文（使用知识库混入）
        
        Args:
            message: 用户消息
            
        Returns:
            知识库检索结果
        """
        if not self.has_knowledge_base:
            return []
        
        try:
            # 使用知识库混入的高级搜索
            search_result = await self.search_knowledge(
                query=message,
                top_k=3,
                include_constraints=True
            )
            
            results = []
            for item in search_result.get("relevant_content", []):
                if isinstance(item, dict):
                    results.append(item)
                else:
                    results.append({"content": str(item), "score": 0.0})
            
            if results:
                logger.info(f"[{self.name}] 知识库检索到 {len(results)} 条相关内容")
            
            return results
            
        except Exception as e:
            logger.warning(f"[{self.name}] 知识库检索失败: {e}")
            return []
    
    def _build_analysis_prompt(
        self,
        user_message: str,
        auto_tool_result: Optional[Dict[str, Any]],
        kb_context: List[Dict[str, Any]],
        response_mode: str = "lightweight",
    ) -> str:
        """构建增强分析提示"""
        parts = []
        
        # 基础信息
        parts.append(f"当前已收集的信息：\n{json.dumps(self.collected_info, ensure_ascii=False, indent=2)}")
        parts.append(f'\n用户刚才说："{user_message}"')
        
        # 知识库上下文
        if kb_context:
            kb_text = "\n".join([f"- {r.get('content', '')[:150]}..." for r in kb_context[:3]])
            parts.append(f"\n【知识库相关内容】\n{kb_text}")
        
        # 工具调用结果
        if auto_tool_result and auto_tool_result.get("success"):
            tool = auto_tool_result.get("tool", "")
            tool_data = auto_tool_result.get("data", [])
            
            if tool_data and tool == "web_search":
                # 网络搜索：传递原始数据供LLM分析和融入建议
                query = auto_tool_result.get("query", "")
                search_content = []
                for i, item in enumerate(tool_data[:5], 1):
                    title = item.get("title", "")
                    desc = item.get("description") or item.get("snippet", "")
                    if title:
                        search_content.append(f"{i}. {title}")
                        if desc:
                            search_content.append(f"   {desc[:200]}")
                
                parts.append(f"\n【网络搜索结果】（关键词：{query}）")
                parts.append("\n".join(search_content))
                parts.append("\n**重要指令**：")
                parts.append("1. 仔细分析以上搜索结果")
                parts.append("2. 提取适合融入小说创作的元素（梗、术语、黑话、背景资料等）")
                parts.append("3. **立即回复用户**，告诉他们你找到了什么有用的内容")
                parts.append("4. 给出具体的创作建议，说明如何将这些元素融入剧情")
            
            elif tool_data:
                # 其他工具：使用原有格式化方法
                tool_text = self._format_auto_tool_result(auto_tool_result)
                if tool_text:
                    parts.append(f"\n【工具调用结果】\n{tool_text[:500]}...")
        
        # 指令
        parts.append(f"""
当前回复模式：{response_mode}

回复模式要求：
- lightweight：自然、简洁、像聊天，不强制大段结构化
- summary：适合需求总结，使用分块与列表
- confirmation：适合定稿确认，先总结，再给下一步
- comparison：适合多方案比较，优先表格
- planning：适合执行计划，优先有序列表

请：
1. 从用户的回复中提取有用的信息
2. 结合知识库内容和工具结果，给出更准确的回复
3. 判断还缺少哪些关键信息
4. 如果信息足够，在回复末尾加上 [INFO_COMPLETE]
5. 如果还需要更多信息，友好地继续提问
6. 严格遵守当前回复模式，不要在 lightweight 模式下过度结构化

以JSON格式返回：
{{
    "extracted_info": {{"字段名": "提取的值"}},
    "reply": "你的回复内容",
    "is_complete": true/false
}}""")
        
        return "\n".join(parts)
    
    def _format_auto_tool_result(self, result: Dict[str, Any]) -> str:
        """
        格式化自动工具调用结果
        
        注意：对于web_search，不直接展示搜索结果，而是返回原始数据供LLM分析
        """
        tool = result.get("tool", "")
        data = result.get("data", [])
        
        if not data:
            return ""
        
        if tool == "web_search":
            # 不直接展示搜索结果，返回空字符串
            # 搜索结果会通过_build_analysis_prompt传递给LLM进行分析
            return ""
        
        elif tool == "trends_search":
            # 热点搜索仍然直接展示
            platform = result.get("platform", "")
            platform_name = TRENDS_PLATFORMS.get(platform, platform)
            lines = [f"📊 **{platform_name}** (实时):\n"]
            
            for i, item in enumerate(data[:10], 1):
                title = item.get("title") or item.get("name", "")
                if not title:
                    continue
                if i <= 3:
                    emoji = ["🥇", "🥈", "🥉"][i-1]
                    lines.append(f"{emoji} {title}")
                else:
                    lines.append(f"{i}. {title}")
            
            return "\n".join(lines)
        
        return json.dumps(data, ensure_ascii=False)[:500]
    
    def set_shared_context(self, ctx: SharedKnowledgeContext) -> None:
        """
        设置共享知识上下文
        
        用于多Agent协作时共享状态
        
        Args:
            ctx: 共享知识上下文
        """
        self._shared_context = ctx
        logger.info(f"[{self.name}] 共享知识上下文已配置")
    
    def get_shared_context(self) -> Optional[SharedKnowledgeContext]:
        """获取共享知识上下文"""
        return self._shared_context
    
    def set_router_agent(self, router) -> None:
        """设置路由智能体"""
        self.router_agent = router
        logger.info(f"[{self.name}] 路由智能体已配置")
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM的JSON响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 如果解析失败，返回原始回复
        return {
            "reply": response,
            "extracted_info": {},
            "is_complete": "[INFO_COMPLETE]" in response
        }
    
    async def _process_trends_search(self, reply: str, user_message: str) -> tuple:
        """
        检测并处理热点搜索请求
        
        Args:
            reply: AI的回复
            user_message: 用户消息
            
        Returns:
            (处理后的回复, 热点数据)
        """
        trends_data = None
        
        logger.info(f"[Communicator] 处理热点搜索: user_message='{user_message[:80]}...'")
        
        # 1. 检测AI回复中的搜索指令 [SEARCH_TRENDS:platform]
        search_match = re.search(r'\[SEARCH_TRENDS:(\w+)\]', reply)
        
        # 2. 如果没有指令，检查用户是否直接询问热点
        platform = None
        if search_match:
            platform = search_match.group(1).lower()
        elif self._is_trends_request(user_message):
            # 用户询问热点，默认使用当前正式支持的平台
            platform = self._detect_platform(user_message) or "toutiao"

        if platform and platform not in TRENDS_PLATFORMS:
            logger.info(f"[Communicator] 热点平台 {platform} 当前未纳入正式支持列表，回退到 toutiao")
            platform = "toutiao"
        
        if platform and platform in TRENDS_PLATFORMS:
            try:
                logger.info(f"[Communicator] 搜索热点: {platform}")
                trends = await self.search_trends(platform)
                
                if trends:
                    trends_data = {
                        "platform": platform,
                        "platform_name": TRENDS_PLATFORMS.get(platform, platform),
                        "items": trends[:10]  # 只返回前10条
                    }
                    
                    # 格式化热点结果
                    trends_text = self._format_trends(trends[:10], platform)
                    
                    # 如果回复中包含搜索指令，替换它
                    if search_match:
                        reply = reply.replace(search_match.group(0), trends_text)
                    else:
                        # 否则追加到回复末尾
                        reply = f"{reply}\n\n{trends_text}"
                        
            except Exception as e:
                logger.error(f"[Communicator] 热点搜索失败: {e}", exc_info=True)
                error_msg = f"\n\n⚠️ 热点搜索失败: {str(e)}"
                if search_match:
                    reply = reply.replace(search_match.group(0), error_msg)
                else:
                    reply = f"{reply}{error_msg}"
        
        # 注意：网络搜索已在_check_auto_tool_call中处理，不需要在这里重复处理
        # 搜索结果已通过_build_analysis_prompt传递给LLM进行分析
        
        return reply, trends_data
    
    def _is_trends_request(self, message: str) -> bool:
        """检测用户是否在询问热点"""
        keywords = ["热点", "热搜", "热榜", "热门", "热梗", "趋势", "trending", "搜索热"]
        is_match = any(kw in message for kw in keywords)
        logger.info(f"[Communicator] 热点请求检测: message='{message[:50]}...', is_match={is_match}")
        return is_match
    
    def _detect_platform(self, message: str) -> Optional[str]:
        """从用户消息中检测平台（仅返回当前正式支持的平台）。"""
        platform_keywords = {
            "douyin": ["抖音", "tiktok", "douyin"],
            "toutiao": ["头条", "今日头条", "toutiao"],
        }
        message_lower = message.lower()
        for platform, keywords in platform_keywords.items():
            if any(kw in message_lower for kw in keywords):
                return platform
        return None
    
    async def search_trends(self, platform: str = "toutiao", limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索热点话题（使用内置Skill服务）

        Args:
            platform: 平台名称 (weibo, zhihu, douyin, bilibili, toutiao, etc.)
            limit: 返回数量限制

        Returns:
            热点列表
        """
        try:
            from skills.trends_search.scripts.trends_service import get_service
            service = get_service()

            method_name = f"get_{platform}_trending"
            if not hasattr(service, method_name):
                logger.warning(f"[Communicator] 平台 {platform} 不支持")
                return []

            logger.info(f"[Communicator] 调用Skill热点服务: {method_name}")
            result = getattr(service, method_name)(limit=limit)

            if not result or not result.get("success"):
                error_msg = result.get("error", "获取热点失败") if result else "获取热点失败"
                logger.error(f"[Communicator] 热点搜索失败: {error_msg}")
                raise Exception(f"{TRENDS_PLATFORMS.get(platform, platform)}: {error_msg}")

            trends_data = result.get("data", [])
            logger.info(f"[Communicator] 获取到 {len(trends_data)} 条热点")
            return trends_data[:limit]

        except ImportError:
            logger.error("[Communicator] 热点搜索Skill未安装，请检查 skills/trends_search 目录")
            return []
        except Exception as e:
            logger.error(f"[Communicator] 热点搜索失败 ({platform}): {e}", exc_info=True)
            raise
    
    def _format_trends(self, trends: List[Dict], platform: str) -> str:
        """格式化热点结果为文本"""
        platform_name = TRENDS_PLATFORMS.get(platform, platform)
        lines = [f"📊 **{platform_name}** (实时):\n"]
        
        for i, item in enumerate(trends[:10], 1):
            # 尝试从不同字段获取标题
            title = item.get("title") or item.get("name") or item.get("content", "")
            
            # 如果标题包含XML标签，尝试提取
            if title and ("<" in title or ">" in title):
                title = self._extract_from_xml(title, "title") or title
            
            # 如果标题仍然包含XML，清理掉所有标签
            if "<" in str(title):
                import re
                title = re.sub(r'<[^>]+>', '', str(title)).strip()
            
            # 获取热度
            hot = item.get("hot") or item.get("hotValue") or item.get("heat") or item.get("popularity", "")
            if hot and ("<" in str(hot) or ">" in str(hot)):
                hot = self._extract_from_xml(str(hot), "popularity") or ""
                if hot:
                    hot = f"🔥{hot}"
            
            if not title:
                continue
            
            if i <= 3:
                # 前三名用特殊标记
                emoji = ["🥇", "🥈", "🥉"][i-1]
                lines.append(f"{emoji} {title} {hot}".strip())
            else:
                lines.append(f"{i}. {title} {hot}".strip())
        
        return "\n".join(lines)
    
    def _extract_from_xml(self, text: str, tag: str) -> str:
        """从XML文本中提取指定标签的内容"""
        import re
        pattern = rf'<{tag}[^>]*>([^<]+)</{tag}>'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    async def web_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用agent_reach技能进行网络搜索
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        try:
            logger.info(f"[Communicator] 调用agent_reach技能搜索: query='{query}', limit={limit}")
            
            # 调用agent_reach技能（use_skill是同步方法，不需要await）
            result = self.use_skill(
                skill_name="agent_reach",
                method="web_search",
                query=query,
                max_results=limit
            )
            
            if not result or not result.get("success"):
                error_msg = result.get("error", "搜索失败") if result else "搜索失败"
                logger.error(f"[Communicator] agent_reach搜索失败: {error_msg}")
                return []
            
            search_results = result.get("data", [])
            logger.info(f"[Communicator] agent_reach搜索成功，返回 {len(search_results)} 条结果")
            return search_results[:limit]
            
        except Exception as e:
            logger.error(f"[Communicator] agent_reach搜索失败: {e}", exc_info=True)
            return []
    
    def _is_web_search_request(self, message: str) -> bool:
        """检测用户是否需要网络搜索（冷门梗等）"""
        blocked_phrases = [
            "搜索结果出来了吗",
            "搜到了吗",
            "怎么样了",
            "好了吗",
            "随便",
            "你自己选",
            "快点",
        ]
        if any(phrase in message for phrase in blocked_phrases):
            return False

        keywords = ["搜索", "查一下", "查询", "找一下", "什么是", "解释", "冷门梗", "冷梗", "网络梗"]
        is_match = any(kw in message for kw in keywords)
        # 排除热点请求
        if self._is_trends_request(message):
            return False
        return is_match

    def _extract_search_query_from_message(self, message: str) -> str:
        """从用户消息中提取适合搜索的简短查询词。"""
        query = str(message or "").strip()
        prefixes = [
            "帮我搜索一下",
            "帮我查一下",
            "帮我查询一下",
            "帮我找一下",
            "搜索一下",
            "查一下",
            "查询一下",
            "找一下",
            "搜索",
            "查询",
            "解释一下",
            "解释",
            "什么是",
        ]
        for prefix in prefixes:
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        return query or str(message or "").strip()

    def _fallback_search_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """LLM 搜索意图判定失败时的保守兜底。"""
        if not self._is_web_search_request(message):
            return None
        query = self._extract_search_query_from_message(message)
        if not query:
            return None
        return {
            "need_search": True,
            "query": query,
            "source": "heuristic_fallback",
        }
    
    async def _detect_search_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        使用LLM检测用户是否需要网络搜索，并提取搜索关键词
        
        Args:
            message: 用户消息
            
        Returns:
            {"need_search": bool, "query": str} 或 None
        """
        try:
            intent_prompt = f"""用户说："{message}"

请判断用户是否需要进行网络搜索来获取资料、信息、梗、术语等内容。

判断标准：
- 用户明确提到"搜索"、"查找"、"查一下"等词，并且是首次提出搜索需求
- 用户需要了解某些梗、黑话、术语、流行语等网络内容
- 用户需要获取某个主题的相关资料或背景信息
- 用户想了解某个概念、事件、人物等

**重要**：以下情况不应触发搜索：
- 用户在询问搜索进度（"搜索结果出来了吗"、"搜到了吗"）
- 用户在等待回复（"随便"、"你自己选"、"快点"）
- 用户在追问或催促（"怎么样了"、"好了吗"）
- 用户只是在描述小说情节，没有明确要求搜索

如果需要搜索，提取核心搜索关键词（简洁、适合搜索引擎）。

以JSON格式返回：
{{
    "need_search": true/false,
    "query": "搜索关键词"（如果need_search为true）
}}

示例1：
用户："我需要你为我搜索一下网上的梗以及足球的相关资料"
返回：{{"need_search": true, "query": "足球梗 足球黑话 足球术语"}}

示例2：
用户："主角是个中场球员，右脚可以远射"
返回：{{"need_search": false}}

示例3：
用户："随便，你自己随便选一些。搜索结果出来了吗"
返回：{{"need_search": false}}

现在请判断："""

            logger.info(f"[{self.name}] 开始意图检测LLM调用...")
            response = await self.call_llm(
                [{"role": "user", "content": intent_prompt}],
                temperature=0.3,
                enable_retry=True
            )
            
            logger.info(f"[{self.name}] 意图检测响应类型: {type(response)}, 长度: {len(str(response))}")

            if not str(response or "").strip():
                raise ValueError("empty_intent_response")

            # 解析JSON响应
            result = self._parse_response(response)
            if not isinstance(result.get("need_search"), bool):
                raise ValueError(f"invalid_intent_payload: {result}")

            if result.get("need_search"):
                logger.info(f"[{self.name}] LLM判断需要搜索: {result.get('query', '')}")
                return result
            else:
                logger.info(f"[{self.name}] LLM判断不需要搜索")
                return None
            
        except Exception as e:
            logger.warning(f"[{self.name}] LLM意图检测失败: {e}", exc_info=True)
            fallback_intent = self._fallback_search_intent(message)
            if fallback_intent:
                logger.info(f"[{self.name}] 启发式兜底判定需要搜索: {fallback_intent.get('query', '')}")
            return fallback_intent
    
    def _format_web_results(self, results: List[Dict], query: str) -> str:
        """格式化网络搜索结果"""
        lines = [f"🔍 **搜索结果**: {query}\n"]
        
        for i, item in enumerate(results[:5], 1):
            title = item.get("title") or item.get("name", "")
            description = item.get("description") or item.get("snippet", "")
            url = item.get("url") or item.get("link", "")
            
            if title:
                lines.append(f"**{i}. {title}**")
                if description:
                    lines.append(f"   {description[:100]}...")
                if url:
                    lines.append(f"   🔗 {url}")
                lines.append("")
        
        return "\n".join(lines)
    
    async def get_structured_requirements(self) -> Dict[str, Any]:
        """
        获取结构化的需求信息
        用于传递给主协调器
        
        Returns:
            结构化的创作需求
        """
        # 使用LLM整理信息
        summary_prompt = f"""
请将以下对话中收集到的信息整理成结构化的小说创作需求：

对话历史：
{self._format_history()}

收集到的信息：
{json.dumps(self.collected_info, ensure_ascii=False, indent=2)}

请返回JSON格式：
{{
    "novel_type": "小说类型",
    "theme": "主题风格",
    "protagonist": "主角设定描述",
    "plot_idea": "剧情构思",
    "requirements": "其他特殊要求",
    "volume_count": 数字,
    "chapters_per_volume": 数字,
    "confidence": 0.0-1.0的置信度
}}
"""
        
        response = await self.call_llm(
            [{"role": "user", "content": summary_prompt}],
            temperature=AGENT_TEMPERATURE.SUMMARY_STABLE
        )
        
        try:
            result = self._parse_response(response)
            # 填充默认值
            result.setdefault("volume_count", 1)
            result.setdefault("chapters_per_volume", 5)
            return result
        except (json.JSONDecodeError, ValueError, KeyError):
            # 返回已收集的信息
            return self.collected_info
    
    def _format_history(self) -> str:
        """格式化对话历史"""
        lines = []
        truncate_len = WRITING_CONFIG.HISTORY_TRUNCATE_LENGTH
        for msg in self.conversation_history:
            role = "用户" if msg["role"] == "user" else "AI"
            lines.append(f"{role}: {msg['content'][:truncate_len]}...")
        return "\n".join(lines)
    
    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行对话（单轮）
        
        对于多轮对话，建议使用 start_conversation 和 chat 方法
        """
        user_message = input_data.get("message", "")
        
        if not self.conversation_history:
            await self.start_conversation()
        
        return await self.chat(user_message)
    
    # ==================== Agent协作方法 ====================
    
    async def request_worldbuilding(
        self,
        novel_type: str,
        theme: str = "",
        requirements: str = ""
    ) -> Dict[str, Any]:
        """
        请求世界观构建（优先走主协调器，回退到消息总线）
        
        Args:
            novel_type: 小说类型
            theme: 主题
            requirements: 特殊要求
            
        Returns:
            世界观数据
        """
        coordinator = getattr(self.router_agent, "coordinator", None) if self.router_agent else None
        if coordinator and hasattr(coordinator, "generate_world"):
            try:
                return await coordinator.generate_world(
                    novel_type=novel_type,
                    theme=theme,
                    requirements=requirements,
                )
            except Exception as exc:
                logger.warning(f"[{self.name}] 协调器世界观构建失败，回退消息总线: {exc}")

        result = await self._run_streaming_task_fallback(
            receiver="Worldbuilder",
            task_type="build_world",
            task_data={
                "novel_type": novel_type,
                "theme": theme,
                "requirements": requirements
            },
            timeout=TIMEOUTS.AGENT_LONG
        )
        
        if result:
            return result
        return {"error": "世界观构建超时未完成"}
    
    async def request_outline(
        self,
        world: Dict[str, Any],
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 10
    ) -> Dict[str, Any]:
        """
        请求大纲生成（优先走主协调器，回退到消息总线）
        
        Args:
            world: 世界观数据
            protagonist: 主角设定
            plot_idea: 剧情构思
            volume_count: 卷数
            chapters_per_volume: 每卷章节数
            
        Returns:
            大纲数据
        """
        coordinator = getattr(self.router_agent, "coordinator", None) if self.router_agent else None
        if coordinator and hasattr(coordinator, "generate_outline"):
            try:
                return await coordinator.generate_outline(
                    world=world,
                    protagonist=protagonist,
                    plot_idea=plot_idea,
                    volume_count=volume_count,
                    chapters_per_volume=chapters_per_volume,
                )
            except Exception as exc:
                logger.warning(f"[{self.name}] 协调器大纲生成失败，回退消息总线: {exc}")

        result = await self._run_streaming_task_fallback(
            receiver="Outliner",
            task_type="build_outline",
            task_data={
                "protagonist": protagonist,
                "plot_idea": plot_idea,
                "volume_count": volume_count,
                "chapters_per_volume": chapters_per_volume
            },
            context={"world": world},
            timeout=TIMEOUTS.AGENT_LONG
        )
        
        if result:
            return result
        return {"error": "大纲生成超时未完成"}
    
    async def request_chapter(
        self,
        chapter_number: int,
        chapter_outline: str,
        chapter_title: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        请求章节撰写（优先走主协调器，回退到消息总线）
        
        Args:
            chapter_number: 章节号
            chapter_outline: 章节大纲
            chapter_title: 章节标题
            context: 上下文信息
            
        Returns:
            章节内容
        """
        coordinator = getattr(self.router_agent, "coordinator", None) if self.router_agent else None
        if coordinator and hasattr(coordinator, "write_single_chapter"):
            try:
                return await coordinator.write_single_chapter(
                    chapter_number=chapter_number,
                    chapter_outline=chapter_outline,
                    chapter_title=chapter_title or f"第{chapter_number}章",
                )
            except Exception as exc:
                logger.warning(f"[{self.name}] 协调器章节写作失败，回退消息总线: {exc}")

        result = await self._run_streaming_task_fallback(
            receiver="ChapterWriter",
            task_type="write_chapter",
            task_data={
                "chapter_number": chapter_number,
                "chapter_outline": chapter_outline,
                "chapter_title": chapter_title or f"第{chapter_number}章"
            },
            context=context,
            timeout=TIMEOUTS.AGENT_LONG
        )
        
        if result:
            return result
        return {"error": "章节撰写超时未完成"}
    
    async def collaborate_full_creation(
        self,
        novel_type: str,
        theme: str = "",
        requirements: str = "",
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 5
    ) -> Dict[str, Any]:
        """
        协作完成完整创作流程
        
        优先复用主协调器执行链，避免形成与当前产品主路径脱节的悬空协作模式。
        若主协调器不可用，再回退到消息总线分阶段协作。
        
        Args:
            novel_type: 小说类型
            theme: 主题
            requirements: 要求
            protagonist: 主角设定
            plot_idea: 剧情构思
            volume_count: 卷数
            chapters_per_volume: 每卷章节数
            
        Returns:
            创作结果摘要
        """
        results = {
            "stages_completed": [],
            "errors": [],
            "dead_characters": [],
            "constraints": []
        }

        coordinator = getattr(self.router_agent, "coordinator", None) if self.router_agent else None
        if coordinator and hasattr(coordinator, "create_novel"):
            try:
                await self.notify_progress("正在调用主协调器执行完整创作流程...", 5)
                latest_payload: Dict[str, Any] = {}
                async for payload in coordinator.create_novel(
                    novel_type=novel_type,
                    theme=theme,
                    requirements=requirements,
                    protagonist=protagonist,
                    plot_idea=plot_idea,
                    volume_count=volume_count,
                    chapters_per_volume=chapters_per_volume,
                ):
                    if isinstance(payload, dict):
                        latest_payload = payload
                        stage = str(payload.get("stage") or "").strip()
                        if stage and stage not in results["stages_completed"] and stage not in {"init", "completed"}:
                            results["stages_completed"].append(stage)

                if latest_payload.get("stage") == "failed":
                    results["errors"].append(str(latest_payload.get("error") or latest_payload.get("message") or "协作创作失败"))
                else:
                    results["project"] = latest_payload.get("project", {})
                    results["file_path"] = latest_payload.get("file_path", "")
                    if "completed" not in results["stages_completed"]:
                        results["stages_completed"].append("completed")

                if self.has_knowledge_base:
                    try:
                        results["dead_characters"] = self.knowledge_base.get_dead_characters()
                    except Exception:
                        results["dead_characters"] = []
                    try:
                        constraints = self.knowledge_base.get_active_constraints()
                        results["constraints"] = [
                            {"type": c.constraint_type, "description": c.title, "entities": c.entities}
                            for c in constraints
                        ]
                    except Exception:
                        results["constraints"] = []

                await self.notify_progress("主协调器创作完成", 100)
                return results
            except Exception as exc:
                logger.warning(f"[{self.name}] 主协调器完整创作失败，回退消息总线协作: {exc}")
                results["errors"].append(f"主协调器回退: {exc}")
        
        # 初始化共享知识上下文
        if not self._shared_context and self.has_knowledge_base:
            self._shared_context = SharedKnowledgeContext(self.knowledge_base)
        
        # 1. 世界观构建
        await self.notify_progress("正在构建世界观...", 10)
        world_result = await self.request_worldbuilding(novel_type, theme, requirements)
        
        if "error" in world_result:
            results["errors"].append(f"世界观: {world_result['error']}")
            return results
        
        results["world"] = world_result.get("world", {})
        results["stages_completed"].append("worldbuilding")
        
        # 2. 大纲规划
        await self.notify_progress("正在规划大纲...", 30)
        outline_result = await self.request_outline(
            world=results["world"],
            protagonist=protagonist,
            plot_idea=plot_idea,
            volume_count=volume_count,
            chapters_per_volume=chapters_per_volume
        )
        
        if "error" in outline_result:
            results["errors"].append(f"大纲: {outline_result['error']}")
            return results
        
        results["outline"] = outline_result.get("outline", {})
        results["stages_completed"].append("outlining")
        
        # 3. 章节撰写（示例：只写第一章）
        await self.notify_progress("正在撰写第一章...", 50)
        
        chapters = results["outline"].get("chapters", [])
        if chapters:
            first_chapter = chapters[0] if isinstance(chapters[0], dict) else {"summary": str(chapters[0])}
            
            # 传递共享上下文
            chapter_context = {"world": results["world"]}
            if self._shared_context:
                chapter_context["shared_knowledge"] = self._shared_context.to_dict()
            
            chapter_result = await self.request_chapter(
                chapter_number=1,
                chapter_outline=first_chapter.get("summary", ""),
                chapter_title=first_chapter.get("title", "第1章"),
                context=chapter_context
            )
            
            if "error" not in chapter_result:
                results["first_chapter"] = chapter_result
                results["stages_completed"].append("first_chapter")
                
                # 更新共享上下文
                if self._shared_context:
                    # 记录死亡角色
                    dead_chars = chapter_result.get("dead_characters", [])
                    for char in dead_chars:
                        self._shared_context.record_death(char, 1)
                    
                    # 记录章节摘要
                    content = chapter_result.get("content", "")
                    if content:
                        self._shared_context.update_chapter_summary(1, content[:300])
        
        # 更新结果中的约束信息
        if self._shared_context:
            results["dead_characters"] = self._shared_context.dead_characters
            results["constraints"] = self._shared_context.active_constraints
        
        await self.notify_progress("协作创作完成", 100)
        
        return results


# 模块职责说明：沟通智能体，负责与用户多轮对话、知识库检索、自动工具调用，支持消息总线协作
