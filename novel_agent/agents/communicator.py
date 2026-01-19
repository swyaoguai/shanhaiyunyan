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
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent
from .knowledge_mixin import KnowledgeBaseMixin, SharedKnowledgeContext
from ..constants import AGENT_TEMPERATURE, WRITING_CONFIG, TIMEOUTS

logger = logging.getLogger(__name__)

# 热点平台映射（只保留能正常工作的平台）
TRENDS_PLATFORMS = {
    "toutiao": "头条热榜",
    "douyin": "抖音热点"
}

# MCP工具名称映射
MCP_TOOL_NAMES = {
    "toutiao": "get-toutiao-trending",
    "douyin": "get-douyin-trending"
}

# 自动工具调用的触发模式
AUTO_TOOL_PATTERNS = {
    "web_search": [
        r"帮我(查|搜|找).{0,10}(梗|热词|流行语|网络用语)",
        r"(什么是|解释一下).{0,20}(梗|热梗|冷梗)",
        r"(最近|现在).{0,10}(流行|火|热门).{0,10}(什么|啥)",
        r"(融入|加入|使用).{0,10}(梗|热点|热词)",
    ],
    "trends_search": [
        r"(今日|今天|最新|实时).{0,10}(热点|热搜|热榜)",
        r"(头条|抖音|微博).{0,10}(热搜|热榜|热点)",
        r"(看看|查看|获取).{0,10}(热点|热搜)",
    ]
}


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
    
    def _get_default_prompt(self) -> str:
        return """你是一位专业的小说创作顾问，负责与用户沟通，收集小说创作的需求信息。

你的任务是：
1. 友好地与用户对话，了解他们想创作什么样的小说
2. 通过提问引导用户提供更详细的信息
3. 帮助用户明确模糊的想法
4. 整理收集到的信息

你需要收集的关键信息：
- 小说类型（玄幻、都市、科幻、言情等）
- 主题风格（热血、轻松、黑暗、治愈等）
- 主角设定（性格、背景、能力）
- 剧情构思（大致故事方向）
- 篇幅规划（多少卷、每卷多少章）

沟通技巧：
- 根据用户的回答灵活调整问题
- 如果用户答案模糊，帮他们具体化
- 适时给出建议和参考
- 保持对话轻松友好

当你认为信息足够时，在回复末尾加上标记：[INFO_COMPLETE]
如果还需要更多信息，继续提问即可。"""
    
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
    
    async def chat(self, user_message: str) -> Dict[str, Any]:
        """
        处理用户消息，返回回复
        
        增强流程：
        1. 检测自动工具调用需求
        2. 知识库检索获取上下文
        3. 分析用户输入
        4. 生成响应
        
        Args:
            user_message: 用户输入
            
        Returns:
            {
                "reply": "AI回复",
                "is_complete": bool,  # 信息是否收集完成
                "collected_info": {}  # 已收集的信息
            }
        """
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        try:
            # === 步骤1: 检测自动工具调用需求 ===
            auto_tool_result = await self._check_auto_tool_call(user_message)
            
            # === 步骤2: 知识库检索 ===
            kb_context = await self._retrieve_knowledge_context(user_message)
            
            # === 步骤3: 构建增强提示 ===
            analysis_prompt = self._build_analysis_prompt(
                user_message,
                auto_tool_result,
                kb_context
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
            if auto_tool_result and auto_tool_result.get("success"):
                tool_text = self._format_auto_tool_result(auto_tool_result)
                if tool_text and tool_text not in reply:
                    reply = f"{reply}\n\n{tool_text}"
            
            # 添加AI回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": reply
            })
            
            response_data = {
                "reply": reply,
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
    
    async def _check_auto_tool_call(self, message: str) -> Optional[Dict[str, Any]]:
        """
        检测并执行自动工具调用
        
        识别用户消息中隐含的工具调用需求，自动执行
        
        Args:
            message: 用户消息
            
        Returns:
            工具调用结果，如果不需要调用则返回None
        """
        # 检查网络搜索模式
        for pattern in AUTO_TOOL_PATTERNS.get("web_search", []):
            if re.search(pattern, message):
                # 提取搜索关键词
                query = self._extract_search_query(message)
                logger.info(f"[{self.name}] 自动触发网络搜索: {query}")
                
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
        
        # 检查热点搜索模式
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
        kb_context: List[Dict[str, Any]]
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
            tool_data = auto_tool_result.get("data", [])
            if tool_data:
                tool_text = self._format_auto_tool_result(auto_tool_result)
                parts.append(f"\n【工具调用结果】\n{tool_text[:500]}...")
        
        # 指令
        parts.append("""
请：
1. 从用户的回复中提取有用的信息
2. 结合知识库内容和工具结果，给出更准确的回复
3. 判断还缺少哪些关键信息
4. 如果信息足够，在回复末尾加上 [INFO_COMPLETE]
5. 如果还需要更多信息，友好地继续提问

以JSON格式返回：
{
    "extracted_info": {"字段名": "提取的值"},
    "reply": "你的回复内容",
    "is_complete": true/false
}""")
        
        return "\n".join(parts)
    
    def _format_auto_tool_result(self, result: Dict[str, Any]) -> str:
        """格式化自动工具调用结果"""
        tool = result.get("tool", "")
        data = result.get("data", [])
        
        if not data:
            return ""
        
        if tool == "web_search":
            lines = [f"🔍 **搜索结果**: {result.get('query', '')}\n"]
            for i, item in enumerate(data[:5], 1):
                title = item.get("title", "")
                desc = item.get("description") or item.get("snippet", "")
                if title:
                    lines.append(f"**{i}. {title}**")
                    if desc:
                        lines.append(f"   {desc[:80]}...")
            return "\n".join(lines)
        
        elif tool == "trends_search":
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
            # 用户询问热点，默认搜索微博
            platform = self._detect_platform(user_message) or "weibo"
        
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
        
        # 3. 检查是否是网络搜索请求（冷门梗等）
        elif self._is_web_search_request(user_message):
            try:
                query = self._extract_search_query(user_message)
                logger.info(f"[Communicator] 执行网络搜索: {query}")
                
                results = await self.web_search(query, limit=5)
                if results:
                    search_text = self._format_web_results(results, query)
                    reply = f"{reply}\n\n{search_text}"
            except Exception as e:
                logger.error(f"[Communicator] 网络搜索失败: {e}", exc_info=True)
                reply = f"{reply}\n\n⚠️ 网络搜索失败: {str(e)}"
        
        return reply, trends_data
    
    def _is_trends_request(self, message: str) -> bool:
        """检测用户是否在询问热点"""
        keywords = ["热点", "热搜", "热榜", "热门", "热梗", "趋势", "trending", "搜索热"]
        is_match = any(kw in message for kw in keywords)
        logger.info(f"[Communicator] 热点请求检测: message='{message[:50]}...', is_match={is_match}")
        return is_match
    
    def _detect_platform(self, message: str) -> Optional[str]:
        """从用户消息中检测平台"""
        platform_keywords = {
            "weibo": ["微博", "weibo"],
            "zhihu": ["知乎", "zhihu"],
            "douyin": ["抖音", "tiktok", "douyin"],
            "bilibili": ["b站", "bilibili", "哔哩哔哩"],
            "baidu": ["百度", "baidu"],
            "toutiao": ["头条", "今日头条", "toutiao"]
        }
        message_lower = message.lower()
        for platform, keywords in platform_keywords.items():
            if any(kw in message_lower for kw in keywords):
                return platform
        return None
    
    async def search_trends(self, platform: str = "weibo", limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索热点话题
        
        Args:
            platform: 平台名称 (weibo, zhihu, douyin, bilibili, baidu, toutiao)
            limit: 返回数量限制
            
        Returns:
            热点列表
        """
        try:
            # 使用映射获取正确的工具名称
            tool_name = MCP_TOOL_NAMES.get(platform, f"get-{platform}-trending")
            logger.info(f"[Communicator] 开始调用MCP工具: trends-hub/{tool_name}")
            result = await self.use_mcp_tool("trends-hub", tool_name, {"limit": limit})
            logger.info(f"[Communicator] MCP调用返回: type={type(result)}")
            
            # 检查是否是错误响应
            if result and hasattr(result, 'isError') and result.isError:
                error_msg = "热点服务暂时不可用"
                if result.content and len(result.content) > 0:
                    if hasattr(result.content[0], 'text'):
                        error_msg = result.content[0].text
                logger.error(f"[Communicator] MCP返回错误: {error_msg}")
                raise Exception(f"{TRENDS_PLATFORMS.get(platform, platform)}: {error_msg}")
            
            # 解析MCP返回的结果
            if result and hasattr(result, 'content') and result.content:
                content_len = len(result.content)
                logger.info(f"[Communicator] 解析 result.content, 长度={content_len}")
                
                # 尝试方式1: 第一个item包含整个JSON数组
                if content_len >= 1 and hasattr(result.content[0], 'text'):
                    first_text = result.content[0].text
                    logger.info(f"[Communicator] 第一个item内容(前100字符): {first_text[:100]}")
                    try:
                        data = json.loads(first_text)
                        if isinstance(data, list):
                            logger.info(f"[Communicator] 方式1成功，返回 {len(data)} 条热点")
                            return data
                        elif isinstance(data, dict) and 'data' in data:
                            logger.info(f"[Communicator] 方式1成功(dict.data)，返回 {len(data['data'])} 条热点")
                            return data['data']
                        elif isinstance(data, dict):
                            # 可能是单个热点对象
                            logger.info(f"[Communicator] 第一个item是单个热点对象")
                    except json.JSONDecodeError:
                        logger.info(f"[Communicator] 第一个item不是JSON，尝试方式2")
                
                # 尝试方式2: 每个item是一个独立的热点(JSON或纯文本)
                trends = []
                for i, item in enumerate(result.content):
                    if hasattr(item, 'text') and item.text:
                        text = item.text.strip()
                        if not text:
                            continue
                        try:
                            # 尝试解析为JSON
                            obj = json.loads(text)
                            if isinstance(obj, dict):
                                trends.append(obj)
                        except json.JSONDecodeError:
                            # 纯文本格式，创建简单对象
                            trends.append({"title": text, "rank": i + 1})
                
                if trends:
                    logger.info(f"[Communicator] 方式2成功，返回 {len(trends)} 条热点")
                    return trends
            else:
                logger.warning(f"[Communicator] MCP返回结果为空或没有content属性")
            
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
        使用Web Search MCP搜索冷门梗或特定内容
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        try:
            logger.info(f"[Communicator] 开始网络搜索: query='{query}', limit={limit}")
            result = await self.use_mcp_tool("web-search", "search", {"query": query, "limit": limit})
            logger.info(f"[Communicator] 网络搜索返回: type={type(result)}")
            
            # 检查错误
            if result and hasattr(result, 'isError') and result.isError:
                error_msg = "搜索服务暂时不可用"
                if result.content and len(result.content) > 0:
                    if hasattr(result.content[0], 'text'):
                        error_msg = result.content[0].text
                logger.error(f"[Communicator] 网络搜索错误: {error_msg}")
                raise Exception(error_msg)
            
            # 解析结果
            search_results = []
            if result and hasattr(result, 'content') and result.content:
                for item in result.content:
                    if hasattr(item, 'text') and item.text:
                        try:
                            data = json.loads(item.text)
                            if isinstance(data, list):
                                search_results = data
                                break
                            elif isinstance(data, dict):
                                search_results.append(data)
                        except json.JSONDecodeError:
                            # 纯文本格式
                            search_results.append({"title": item.text})
            
            logger.info(f"[Communicator] 网络搜索成功，返回 {len(search_results)} 条结果")
            return search_results
        except Exception as e:
            logger.error(f"[Communicator] 网络搜索失败: {e}", exc_info=True)
            raise
    
    def _is_web_search_request(self, message: str) -> bool:
        """检测用户是否需要网络搜索（冷门梗等）"""
        keywords = ["搜索", "查一下", "查询", "找一下", "什么是", "解释", "冷门梗", "冷梗", "网络梗"]
        is_match = any(kw in message for kw in keywords)
        # 排除热点请求
        if self._is_trends_request(message):
            return False
        return is_match
    
    def _extract_search_query(self, message: str) -> str:
        """从用户消息中提取搜索关键词"""
        # 简单提取：去掉常见的前缀
        prefixes = ["搜索", "查一下", "查询", "找一下", "什么是", "解释一下", "帮我查"]
        query = message
        for prefix in prefixes:
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        return query if query else message
    
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
        请求世界观构建（通过消息总线）
        
        Args:
            novel_type: 小说类型
            theme: 主题
            requirements: 特殊要求
            
        Returns:
            世界观数据
        """
        result = await self.send_task(
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
        请求大纲生成（通过消息总线）
        
        Args:
            world: 世界观数据
            protagonist: 主角设定
            plot_idea: 剧情构思
            volume_count: 卷数
            chapters_per_volume: 每卷章节数
            
        Returns:
            大纲数据
        """
        result = await self.send_task(
            receiver="Outliner",
            task_type="create_outline",
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
        请求章节撰写（通过消息总线）
        
        Args:
            chapter_number: 章节号
            chapter_outline: 章节大纲
            chapter_title: 章节标题
            context: 上下文信息
            
        Returns:
            章节内容
        """
        result = await self.send_task(
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
        
        这个方法展示了如何通过消息总线协调多个Agent工作
        使用共享知识上下文确保各Agent间状态一致
        
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
