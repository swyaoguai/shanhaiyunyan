"""
智能路由Agent
负责分析用户意图、优先检索知识库、自动调用工具，确保每个用户请求都有Agent响应

核心职责：
1. 意图识别：分析用户消息，判断需要哪种处理方式
2. 知识库优先：在回复前先检索知识库获取相关上下文
3. 工具调用：自动识别并调用MCP工具（如网络搜索、热点获取等）
4. 响应保证：确保每个用户请求都有明确的Agent响应
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass

from .base_agent import BaseAgent
from ..constants import AGENT_TEMPERATURE, TIMEOUTS

logger = logging.getLogger(__name__)


class UserIntent(Enum):
    """用户意图类型"""
    # 创作相关
    CREATE_NOVEL = "create_novel"           # 创建小说
    CONTINUE_WRITE = "continue_write"       # 续写
    POLISH_CONTENT = "polish_content"       # 润色
    
    # 信息查询
    SEARCH_WEB = "search_web"               # 网络搜索
    SEARCH_TRENDS = "search_trends"         # 热点搜索
    QUERY_KNOWLEDGE = "query_knowledge"     # 查询知识库
    
    # 对话交互
    GENERAL_CHAT = "general_chat"           # 普通对话
    ASK_HELP = "ask_help"                   # 寻求帮助
    PROVIDE_FEEDBACK = "provide_feedback"   # 提供反馈
    
    # 项目管理
    PROJECT_MANAGE = "project_manage"       # 项目管理
    CONFIG_SETTINGS = "config_settings"     # 配置设置


@dataclass
class IntentAnalysis:
    """意图分析结果"""
    primary_intent: UserIntent
    confidence: float
    entities: Dict[str, Any]  # 提取的实体（如搜索关键词、章节号等）
    requires_knowledge_base: bool
    requires_tool_call: bool
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    fallback_intent: Optional[UserIntent] = None


class RouterAgent(BaseAgent):
    """
    智能路由Agent
    
    作为用户请求的第一入口，负责：
    1. 分析用户意图
    2. 检索知识库获取上下文
    3. 调用必要的工具
    4. 将请求路由到正确的Agent并执行
    5. 确保每个请求都有响应
    
    API配置：
    - 使用全局API配置，无需单独配置
    - 继承自BaseAgent，自动获取全局模型设置
    
    任务分发规则：
    - 创建小说 → NovelCoordinator（世界观→大纲→章节）
    - 续写章节 → ContinuousWriter
    - 润色内容 → PolisherAgent
    - 普通对话 → CommunicatorAgent
    - 搜索热点 → 直接调用MCP工具
    """
    
    # 意图关键词映射
    INTENT_KEYWORDS = {
        UserIntent.CREATE_NOVEL: [
            "创作", "写一部", "新小说", "开始写", "创建小说", "开一本新书"
        ],
        UserIntent.CONTINUE_WRITE: [
            "续写", "继续写", "接着写", "往下写", "下一章", "继续创作"
        ],
        UserIntent.POLISH_CONTENT: [
            "润色", "优化", "修改", "改进", "完善", "调整文风"
        ],
        UserIntent.SEARCH_WEB: [
            "搜索", "查一下", "查询", "找一下", "什么是", "解释",
            "冷门梗", "冷梗", "网络梗", "梗是什么", "了解一下"
        ],
        UserIntent.SEARCH_TRENDS: [
            "热点", "热搜", "热榜", "热门", "热梗", "趋势", 
            "trending", "搜索热", "今日热点", "最新热点"
        ],
        UserIntent.QUERY_KNOWLEDGE: [
            "之前写的", "前面提到", "回顾", "查看设定", "角色状态",
            "世界观", "剧情线", "人物关系"
        ],
        UserIntent.ASK_HELP: [
            "帮助", "怎么用", "如何", "教我", "指导", "说明"
        ],
        UserIntent.PROJECT_MANAGE: [
            "项目", "保存", "加载", "导出", "删除项目", "切换项目"
        ],
        UserIntent.CONFIG_SETTINGS: [
            "设置", "配置", "API", "模型", "参数"
        ]
    }
    
    # MCP工具映射
    MCP_TOOLS = {
        "web_search": {
            "server": "web-search",
            "tool": "search",
            "description": "网络搜索"
        },
        "toutiao_trends": {
            "server": "trends-hub",
            "tool": "get-toutiao-trending",
            "description": "头条热榜"
        },
        "douyin_trends": {
            "server": "trends-hub",
            "tool": "get-douyin-trending",
            "description": "抖音热点"
        }
    }
    
    def __init__(self, knowledge_base=None, coordinator=None):
        """
        初始化路由智能体
        
        Args:
            knowledge_base: 知识库实例（可选）
            coordinator: 协调器实例（可选，用于分发创作任务）
            
        注意：使用全局API配置，无需单独配置模型
        """
        super().__init__(name="Router", prompt_file=None)
        self.knowledge_base = knowledge_base
        self.coordinator = coordinator
        
        # 延迟加载的Agent实例
        self._communicator = None
        self._polisher = None
        self._continuous_writer = None
        
    def _get_default_prompt(self) -> str:
        return """你是一个智能路由助手，负责分析用户意图并提供帮助。

你的任务是：
1. 理解用户的真实需求
2. 提供准确、有帮助的回复
3. 当需要查询信息时，主动使用可用的工具
4. 保持友好、专业的沟通风格

你可以帮助用户：
- 创作小说（世界观构建、大纲规划、章节撰写）
- 搜索网络信息和热点话题
- 查询知识库中的已有内容
- 解答使用问题"""
    
    async def analyze_intent(self, message: str) -> IntentAnalysis:
        """
        分析用户意图
        
        Args:
            message: 用户消息
            
        Returns:
            意图分析结果
        """
        message_lower = message.lower()
        
        # 第一步：关键词匹配
        matched_intents: List[Tuple[UserIntent, int]] = []
        for intent, keywords in self.INTENT_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw in message_lower)
            if match_count > 0:
                matched_intents.append((intent, match_count))
        
        # 按匹配数量排序
        matched_intents.sort(key=lambda x: x[1], reverse=True)
        
        # 确定主要意图
        if matched_intents:
            primary_intent = matched_intents[0][0]
            confidence = min(0.9, 0.5 + matched_intents[0][1] * 0.15)
            fallback = matched_intents[1][0] if len(matched_intents) > 1 else UserIntent.GENERAL_CHAT
        else:
            primary_intent = UserIntent.GENERAL_CHAT
            confidence = 0.5
            fallback = None
        
        # 提取实体
        entities = self._extract_entities(message, primary_intent)
        
        # 判断是否需要知识库
        requires_kb = primary_intent in [
            UserIntent.CONTINUE_WRITE,
            UserIntent.QUERY_KNOWLEDGE,
            UserIntent.GENERAL_CHAT  # 普通对话也先查知识库获取上下文
        ]
        
        # 判断是否需要工具调用
        requires_tool = primary_intent in [
            UserIntent.SEARCH_WEB,
            UserIntent.SEARCH_TRENDS
        ]
        
        # 确定工具
        tool_name = None
        tool_args = None
        
        if primary_intent == UserIntent.SEARCH_WEB:
            tool_name = "web_search"
            tool_args = {"query": entities.get("search_query", message)}
        elif primary_intent == UserIntent.SEARCH_TRENDS:
            platform = entities.get("platform", "toutiao")
            tool_name = f"{platform}_trends"
            tool_args = {"limit": 20}
        
        return IntentAnalysis(
            primary_intent=primary_intent,
            confidence=confidence,
            entities=entities,
            requires_knowledge_base=requires_kb,
            requires_tool_call=requires_tool,
            tool_name=tool_name,
            tool_args=tool_args,
            fallback_intent=fallback
        )
    
    def _extract_entities(self, message: str, intent: UserIntent) -> Dict[str, Any]:
        """提取消息中的实体"""
        entities = {}
        
        # 提取搜索查询
        if intent == UserIntent.SEARCH_WEB:
            # 移除常见前缀
            prefixes = ["搜索", "查一下", "查询", "找一下", "什么是", "解释一下", "帮我查"]
            query = message
            for prefix in prefixes:
                if query.startswith(prefix):
                    query = query[len(prefix):].strip()
                    break
            entities["search_query"] = query if query else message
        
        # 提取热点平台
        if intent == UserIntent.SEARCH_TRENDS:
            platform_keywords = {
                "toutiao": ["头条", "今日头条", "toutiao"],
                "douyin": ["抖音", "tiktok", "douyin"]
            }
            message_lower = message.lower()
            for platform, keywords in platform_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    entities["platform"] = platform
                    break
            if "platform" not in entities:
                entities["platform"] = "toutiao"  # 默认头条
        
        # 提取章节号
        chapter_match = re.search(r'第(\d+)章', message)
        if chapter_match:
            entities["chapter_number"] = int(chapter_match.group(1))
        
        return entities
    
    async def retrieve_knowledge(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        从知识库检索相关内容
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        if not self.knowledge_base:
            logger.info(f"[{self.name}] 知识库未配置，跳过检索")
            return []
        
        try:
            search_response = self.knowledge_base.search(
                query=query,
                top_k=top_k
            )
            
            results = []
            if hasattr(search_response, 'results'):
                for result in search_response.results:
                    results.append({
                        "content": result.content if hasattr(result, 'content') else str(result),
                        "score": result.score if hasattr(result, 'score') else 0.0,
                        "metadata": result.metadata if hasattr(result, 'metadata') else {}
                    })
            
            logger.info(f"[{self.name}] 知识库检索到 {len(results)} 条相关内容")
            return results
            
        except Exception as e:
            logger.warning(f"[{self.name}] 知识库检索失败: {e}")
            return []
    
    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            
        Returns:
            工具调用结果
        """
        if tool_name not in self.MCP_TOOLS:
            return {"error": f"未知工具: {tool_name}"}
        
        tool_config = self.MCP_TOOLS[tool_name]
        
        try:
            logger.info(f"[{self.name}] 调用MCP工具: {tool_config['server']}/{tool_config['tool']}")
            
            result = await self.use_mcp_tool(
                tool_config["server"],
                tool_config["tool"],
                args
            )
            
            # 解析结果
            parsed_result = self._parse_mcp_result(result, tool_name)
            return {
                "success": True,
                "tool": tool_name,
                "data": parsed_result
            }
            
        except Exception as e:
            logger.error(f"[{self.name}] 工具调用失败: {e}")
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e)
            }
    
    def _parse_mcp_result(self, result: Any, tool_name: str) -> Any:
        """解析MCP工具返回结果"""
        if result is None:
            return []
        
        # 检查错误
        if hasattr(result, 'isError') and result.isError:
            error_msg = "工具调用失败"
            if hasattr(result, 'content') and result.content:
                if hasattr(result.content[0], 'text'):
                    error_msg = result.content[0].text
            raise Exception(error_msg)
        
        # 解析content
        if hasattr(result, 'content') and result.content:
            for item in result.content:
                if hasattr(item, 'text') and item.text:
                    try:
                        data = json.loads(item.text)
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict):
                            return data.get('data', data)
                    except json.JSONDecodeError:
                        continue
        
        return []
    
    async def route_and_respond(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        路由用户请求并生成响应
        
        这是主入口方法，保证每个请求都有响应
        会根据意图分析结果，将任务分发给对应的智能体执行
        
        Args:
            message: 用户消息
            context: 上下文信息
            
        Returns:
            响应结果，包含：
            - response: 回复文本
            - intent: 识别的意图
            - knowledge_results: 知识库检索结果
            - tool_results: 工具调用结果
            - routed_to: 路由到的Agent
            - delegated_result: 被委派Agent的执行结果
        """
        result = {
            "response": "",
            "intent": None,
            "knowledge_results": [],
            "tool_results": None,
            "routed_to": None,
            "delegated_result": None,
            "success": True
        }
        
        try:
            # 1. 分析意图
            intent_analysis = await self.analyze_intent(message)
            result["intent"] = {
                "type": intent_analysis.primary_intent.value,
                "confidence": intent_analysis.confidence,
                "entities": intent_analysis.entities
            }
            
            logger.info(
                f"[{self.name}] 意图分析: {intent_analysis.primary_intent.value} "
                f"(置信度: {intent_analysis.confidence:.2f})"
            )
            
            # 2. 知识库检索（如果需要）
            if intent_analysis.requires_knowledge_base:
                kb_results = await self.retrieve_knowledge(message)
                result["knowledge_results"] = kb_results
            
            # 3. 工具调用（如果需要）
            if intent_analysis.requires_tool_call and intent_analysis.tool_name:
                tool_result = await self.call_tool(
                    intent_analysis.tool_name,
                    intent_analysis.tool_args or {}
                )
                result["tool_results"] = tool_result
            
            # 4. 根据意图分发任务给对应的智能体
            delegated_result = await self._delegate_to_agent(
                intent_analysis=intent_analysis,
                message=message,
                knowledge_results=result["knowledge_results"],
                tool_results=result["tool_results"],
                context=context
            )
            
            if delegated_result:
                result["delegated_result"] = delegated_result
                result["routed_to"] = delegated_result.get("agent_name")
                
                # 如果被委派的Agent返回了响应，使用它
                if delegated_result.get("response"):
                    result["response"] = delegated_result["response"]
            
            # 5. 如果没有委派响应，生成路由层响应
            if not result["response"]:
                response = await self._generate_response(
                    message=message,
                    intent_analysis=intent_analysis,
                    knowledge_results=result["knowledge_results"],
                    tool_results=result["tool_results"],
                    context=context
                )
                result["response"] = response
            
        except Exception as e:
            logger.error(f"[{self.name}] 路由处理失败: {e}")
            result["success"] = False
            result["response"] = f"抱歉，处理您的请求时遇到问题: {str(e)}。请稍后重试或换个方式描述您的需求。"
        
        # 保证有响应（双重保障）
        if not result["response"]:
            result["response"] = "我收到了您的消息，请问有什么可以帮助您的？"
        
        return result
    
    async def _delegate_to_agent(
        self,
        intent_analysis: IntentAnalysis,
        message: str,
        knowledge_results: List[Dict[str, Any]],
        tool_results: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        将任务委派给对应的智能体执行
        
        任务分发规则：
        - CREATE_NOVEL → NovelCoordinator（完整创作流程）
        - CONTINUE_WRITE → ContinuousWriter（续写）
        - POLISH_CONTENT → PolisherAgent（润色）
        - GENERAL_CHAT → CommunicatorAgent（对话）
        - 其他 → 返回None，由路由器自己处理
        
        Args:
            intent_analysis: 意图分析结果
            message: 用户消息
            knowledge_results: 知识库检索结果
            tool_results: 工具调用结果
            context: 上下文信息
            
        Returns:
            委派执行结果，如果无需委派返回None
        """
        intent = intent_analysis.primary_intent
        entities = intent_analysis.entities
        
        try:
            # === 创建小说 → 协调器 ===
            if intent == UserIntent.CREATE_NOVEL:
                if self.coordinator:
                    logger.info(f"[{self.name}] 分发创作任务到 Coordinator")
                    
                    # 从消息中提取小说参数
                    novel_type = self._extract_novel_type(message)
                    
                    # 返回引导信息，实际创作需要通过API触发
                    return {
                        "agent_name": "Coordinator",
                        "action": "create_novel",
                        "response": f"好的！我将为您创作一部{novel_type}小说。\n\n"
                                   f"🎯 **创作流程**：\n"
                                   f"1. 首先构建独特的世界观\n"
                                   f"2. 然后规划详细的故事大纲\n"
                                   f"3. 最后逐章撰写精彩内容\n\n"
                                   f"请在创作面板中点击「开始创作」，或告诉我更多关于您想要的故事细节（主角设定、剧情构思等）。",
                        "params": {
                            "novel_type": novel_type,
                            "ready_to_create": True
                        }
                    }
                else:
                    return {
                        "agent_name": "Router",
                        "response": "检测到您想创作小说，请在创作面板中配置并开始创作。"
                    }
            
            # === 续写 → 无限续写Agent ===
            elif intent == UserIntent.CONTINUE_WRITE:
                writer = self._get_continuous_writer()
                if writer:
                    logger.info(f"[{self.name}] 分发续写任务到 ContinuousWriter")
                    
                    chapter_num = entities.get("chapter_number", 0)
                    
                    return {
                        "agent_name": "ContinuousWriter",
                        "action": "continue",
                        "response": f"好的，我将为您续写{'第' + str(chapter_num) + '章' if chapter_num else '下一章'}内容。\n"
                                   f"请在无限续写面板中操作，或直接告诉我您的创作灵感。",
                        "params": {
                            "chapter_number": chapter_num
                        }
                    }
            
            # === 润色 → 润色Agent ===
            elif intent == UserIntent.POLISH_CONTENT:
                polisher = self._get_polisher()
                if polisher:
                    logger.info(f"[{self.name}] 分发润色任务到 Polisher")
                    
                    return {
                        "agent_name": "Polisher",
                        "action": "polish",
                        "response": "好的，请提供需要润色的内容，我将为您优化文字表达、丰富细节描写。"
                    }
            
            # === 普通对话 → 沟通Agent ===
            elif intent == UserIntent.GENERAL_CHAT:
                communicator = self._get_communicator()
                if communicator:
                    logger.info(f"[{self.name}] 分发对话任务到 Communicator")
                    
                    # 将知识库和工具结果传递给沟通Agent
                    chat_context = context or {}
                    if knowledge_results:
                        chat_context["knowledge"] = knowledge_results
                    if tool_results:
                        chat_context["tool_results"] = tool_results
                    
                    # 执行对话
                    chat_result = await communicator.chat(message)
                    
                    return {
                        "agent_name": "Communicator",
                        "action": "chat",
                        "response": chat_result.get("reply", ""),
                        "is_complete": chat_result.get("is_complete", False),
                        "collected_info": chat_result.get("collected_info", {})
                    }
            
            # 其他意图由路由器自己处理
            return None
            
        except Exception as e:
            logger.error(f"[{self.name}] 任务委派失败: {e}")
            return {
                "agent_name": "Router",
                "error": str(e),
                "response": f"任务分发遇到问题: {str(e)}"
            }
    
    def _extract_novel_type(self, message: str) -> str:
        """从消息中提取小说类型"""
        type_keywords = {
            "玄幻": ["玄幻", "修仙", "修真", "仙侠", "奇幻"],
            "都市": ["都市", "现代", "职场", "商战"],
            "科幻": ["科幻", "未来", "星际", "机甲", "末日"],
            "言情": ["言情", "爱情", "甜宠", "虐恋", "总裁"],
            "历史": ["历史", "穿越", "古代", "架空"],
            "悬疑": ["悬疑", "推理", "探案", "侦探"],
            "游戏": ["游戏", "电竞", "网游", "虚拟"],
            "武侠": ["武侠", "江湖", "门派"]
        }
        
        message_lower = message.lower()
        for novel_type, keywords in type_keywords.items():
            if any(kw in message_lower for kw in keywords):
                return novel_type
        
        return "玄幻"  # 默认类型
    
    def _get_communicator(self):
        """获取沟通Agent（延迟加载）"""
        if self._communicator is None:
            from .communicator import CommunicatorAgent
            self._communicator = CommunicatorAgent(
                knowledge_base=self.knowledge_base,
                router_agent=self
            )
        return self._communicator
    
    def _get_polisher(self):
        """获取润色Agent（延迟加载）"""
        if self._polisher is None:
            from .polisher import PolisherAgent
            self._polisher = PolisherAgent()
        return self._polisher
    
    def _get_continuous_writer(self):
        """获取无限续写Agent（延迟加载）"""
        if self._continuous_writer is None:
            from .continuous_writer import ContinuousWriter
            self._continuous_writer = ContinuousWriter()
            if self.knowledge_base:
                self._continuous_writer.set_knowledge_base(self.knowledge_base)
        return self._continuous_writer
    
    def set_coordinator(self, coordinator) -> None:
        """设置协调器实例"""
        self.coordinator = coordinator
        logger.info(f"[{self.name}] 协调器已配置")
    
    async def _generate_response(
        self,
        message: str,
        intent_analysis: IntentAnalysis,
        knowledge_results: List[Dict[str, Any]],
        tool_results: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """生成响应"""
        
        # 构建增强提示
        prompt_parts = []
        
        # 用户消息
        prompt_parts.append(f"用户消息：{message}")
        
        # 知识库上下文
        if knowledge_results:
            kb_context = "\n".join([
                f"- {r.get('content', '')[:200]}..." 
                for r in knowledge_results[:3]
            ])
            prompt_parts.append(f"\n相关知识库内容：\n{kb_context}")
        
        # 工具调用结果
        if tool_results and tool_results.get("success"):
            tool_data = tool_results.get("data", [])
            if isinstance(tool_data, list) and tool_data:
                # 格式化热点/搜索结果
                formatted = self._format_tool_results(tool_results)
                prompt_parts.append(f"\n工具调用结果：\n{formatted}")
        
        # 意图说明
        prompt_parts.append(f"\n识别的用户意图：{intent_analysis.primary_intent.value}")
        
        # 生成回复
        prompt = "\n".join(prompt_parts) + "\n\n请根据以上信息，生成一个友好、有帮助的回复。"
        
        try:
            response = await self.call_llm(
                [{"role": "user", "content": prompt}],
                temperature=AGENT_TEMPERATURE.CREATIVE_HIGH
            )
            return response
        except Exception as e:
            logger.error(f"[{self.name}] LLM调用失败: {e}")
            # 返回基于工具结果的默认响应
            if tool_results and tool_results.get("success"):
                return self._format_tool_results(tool_results)
            return "抱歉，我暂时无法生成回复。请稍后再试。"
    
    def _format_tool_results(self, tool_results: Dict[str, Any]) -> str:
        """格式化工具结果为文本"""
        tool_name = tool_results.get("tool", "")
        data = tool_results.get("data", [])
        
        if not data:
            return "未找到相关结果。"
        
        if "trends" in tool_name:
            # 热点格式化
            platform_names = {
                "toutiao_trends": "头条热榜",
                "douyin_trends": "抖音热点"
            }
            lines = [f"📊 **{platform_names.get(tool_name, '热点')}** (实时):\n"]
            
            for i, item in enumerate(data[:10], 1):
                title = item.get("title") or item.get("name") or str(item)
                hot = item.get("hot") or item.get("hotValue") or ""
                
                if i <= 3:
                    emoji = ["🥇", "🥈", "🥉"][i-1]
                    lines.append(f"{emoji} {title} {hot}".strip())
                else:
                    lines.append(f"{i}. {title} {hot}".strip())
            
            return "\n".join(lines)
        
        elif tool_name == "web_search":
            # 搜索结果格式化
            lines = ["🔍 **搜索结果**:\n"]
            
            for i, item in enumerate(data[:5], 1):
                title = item.get("title", "")
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
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行路由和响应（BaseAgent接口实现）
        
        Args:
            input_data: 包含 "message" 键的输入数据
            context: 上下文信息
            
        Returns:
            路由和响应结果
        """
        message = input_data.get("message", "")
        if not message:
            return {
                "success": False,
                "response": "请输入您的问题或需求。",
                "error": "Empty message"
            }
        
        return await self.route_and_respond(message, context)
    
    def set_knowledge_base(self, kb) -> None:
        """设置知识库实例"""
        self.knowledge_base = kb
        # 同步到子Agent
        if self._communicator:
            self._communicator.set_knowledge_base(kb)
        if self._continuous_writer:
            self._continuous_writer.set_knowledge_base(kb)
        logger.info(f"[{self.name}] 知识库已配置")


# 模块职责说明：智能路由智能体，负责意图识别、知识库检索、工具调用、任务分发和响应保证