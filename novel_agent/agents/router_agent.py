"""
智能路由Agent
负责分析用户意图、优先检索知识库、自动调用工具，确保每个用户请求都有Agent响应

核心职责：
1. 意图识别：分析用户消息，判断需要哪种处理方式
2. 知识库优先：在回复前先检索知识库获取相关上下文
3. 工具调用：自动识别并调用Skill工具（如网络搜索、热点获取等）
4. 响应保证：确保每个用户请求都有明确的Agent响应
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from .base_agent import BaseAgent
from ..constants import AGENT_TEMPERATURE, TIMEOUTS
from ..utils.atomic_write import atomic_write_text
from ..workflow.contracts import build_default_creation_contract, build_default_task_graph

logger = logging.getLogger(__name__)


class UserIntent(Enum):
    """用户意图类型"""
    # 创作相关
    CREATE_NOVEL = "create_novel"           # 创建小说
    CREATE_CHARACTER = "create_character"   # 创建角色档案
    CREATE_EVENTLINES = "create_eventlines" # 创建事件线
    CREATE_DETAIL_OUTLINE = "create_detail_outline"  # 创建细纲
    CREATE_CHAPTER_SETTINGS = "create_chapter_settings"  # 创建章纲设定
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
    - 搜索热点 → 直接调用Skill工具
    """
    
    # 意图关键词映射
    INTENT_KEYWORDS = {
        UserIntent.CREATE_NOVEL: [
            "创作", "写一部", "新小说", "开始写", "创建小说", "开一本新书",
            "写一本", "写个", "写篇", "短篇", "短故事", "微小说", "词条写", "关键词写",
            # 大纲相关
            "写大纲", "创建大纲", "生成大纲", "建大纲", "做大纲",
            "设计大纲", "规划大纲", "先写大纲", "帮我写大纲",
            # 正文/章节创作
            "写正文", "创作正文", "开始正文", "生成正文",
        ],
        UserIntent.CREATE_CHARACTER: [
            "创建角色", "设计角色", "写角色", "建角色",
            "角色档案", "人物档案", "主角档案", "角色卡", "人物卡", "人设卡",
            "人设", "角色设定", "人物设定", "主角设定", "主角档案",
            "加入资料库", "保存到资料库", "同步到资料库", "角色加入资料库", "角色加入",
        ],
        UserIntent.CREATE_EVENTLINES: [
            "事件线", "剧情线", "故事线", "主线支线", "主线和支线",
            "梳理事件", "整理事件线", "生成事件线",
        ],
        UserIntent.CREATE_DETAIL_OUTLINE: [
            "细纲", "详细大纲", "章节细纲", "生成细纲", "补全细纲", "完善细纲",
        ],
        UserIntent.CREATE_CHAPTER_SETTINGS: [
            "章纲", "章纲设定", "章节设定", "章节规划", "章节卡", "章节大纲卡",
        ],
        UserIntent.CONTINUE_WRITE: [
            "续写", "继续写", "接着写", "往下写", "下一章", "继续创作",
            "写第", "创作第", "生成第"
        ],
        UserIntent.POLISH_CONTENT: [
            "润色", "优化", "修改", "改进", "完善", "调整文风"
        ],
        UserIntent.SEARCH_WEB: [
            "搜索", "查一下", "查询", "找一下", "什么是", "解释",
            "冷门梗", "冷梗", "网络梗", "梗是什么", "了解一下",
            "相关资料", "事件经过", "历史事件", "融合创作", "素材",
        ],
        UserIntent.SEARCH_TRENDS: [
            "今日热点", "最新热点", "实时热搜",
            "热搜榜", "热榜", "看看热搜", "查看热点",
            "热梗", "流行梗"
        ],
        UserIntent.QUERY_KNOWLEDGE: [
            "之前写的", "前面提到", "回顾", "查看设定", "角色状态",
            "查看世界观", "查看大纲", "剧情线", "人物关系"
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
    
    # Skill 工具映射
    SKILLS = {
        "web_search": {
            "skill": "web_search",
            "method": "search",
            "description": "网络搜索（搜索任意内容、资料、事件、梗）"
        },
        "web_search_memes": {
            "skill": "web_search",
            "method": "search_memes",
            "description": "搜索网络热梗"
        },
        "web_search_events": {
            "skill": "web_search",
            "method": "search_events",
            "description": "搜索事件经过"
        },
        "web_search_material": {
            "skill": "web_search",
            "method": "search_creative_material",
            "description": "搜索创作素材"
        },
        "web_read_url": {
            "skill": "web_search",
            "method": "read_url",
            "description": "阅读网页内容"
        },
        "toutiao_trends": {
            "skill": "trends_search",
            "method": "get_toutiao_trending",
            "description": "头条热榜"
        },
        "douyin_trends": {
            "skill": "trends_search",
            "method": "get_douyin_trending",
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

        # LLM意图分析配置（强制使用LLM，不使用规则兜底）
        self._llm_intent_timeout = 15.0       # 当前超时时间（秒）
        self._llm_intent_max_timeout = 60.0    # 最大超时
        self._llm_intent_max_retries = 2        # 最大重试次数

    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import ROUTER_AGENT_PROMPT
        return ROUTER_AGENT_PROMPT
    
    async def analyze_intent(self, message: str) -> IntentAnalysis:
        """
        分析用户意图。

        完全基于 LLM 判断，不使用规则兜底。
        LLM 支持动态超时重试：首次超时后自动延长重试，最多重试2次（15s -> 30s -> 60s）。
        若全部重试均失败，抛出 RuntimeError 显式报错。
        """
        # 重置超时状态（新请求从头开始）
        self._llm_intent_timeout = 15.0

        llm_analysis = await self._analyze_intent_with_llm(message)
        if llm_analysis is not None:
            return llm_analysis

        # LLM 彻底失败后，显式报错（不回退到规则匹配）
        raise RuntimeError(
            f"[{self.name}] LLM意图分析全部重试失败，无法识别用户意图。请检查LLM配置。"
        )

    def _build_intent_analysis(
        self,
        message: str,
        primary_intent: UserIntent,
        *,
        confidence: float,
        fallback_intent: Optional[UserIntent] = None,
    ) -> IntentAnalysis:
        """根据意图枚举统一生成 IntentAnalysis。"""
        entities = self._extract_entities(message, primary_intent)

        requires_kb = primary_intent in [
            UserIntent.CONTINUE_WRITE,
            UserIntent.QUERY_KNOWLEDGE,
            UserIntent.GENERAL_CHAT  # 普通对话也先查知识库获取上下文
        ]

        requires_tool = primary_intent in [
            UserIntent.SEARCH_WEB,
            UserIntent.SEARCH_TRENDS
        ]

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
            confidence=max(0.0, min(float(confidence or 0.0), 1.0)),
            entities=entities,
            requires_knowledge_base=requires_kb,
            requires_tool_call=requires_tool,
            tool_name=tool_name,
            tool_args=tool_args,
            fallback_intent=fallback_intent
        )

    async def _analyze_intent_with_llm(
        self,
        message: str,
    ) -> Optional[IntentAnalysis]:
        """
        使用 LLM 进行意图识别，支持超时重试。

        首次调用超时后自动延长超时时间重试：
        - 第1次：15s
        - 第2次：30s
        - 第3次：60s（最大）
        最多重试2次。
        若全部重试失败，返回 None。
        """
        prompt = self._build_intent_analysis_prompt(message)
        current_timeout = self._llm_intent_timeout
        retries = 0

        while retries <= self._llm_intent_max_retries:
            try:
                logger.info(
                    f"[{self.name}] 开始 LLM 意图分析"
                    + (f"（第{retries}次重试, timeout={current_timeout:.0f}s）" if retries > 0 else "")
                )
                response = await asyncio.wait_for(
                    self.call_llm(
                        [{"role": "user", "content": prompt}],
                        temperature=0.1,
                        enable_retry=False,
                    ),
                    timeout=current_timeout,
                )
                result = self._parse_intent_analysis_response(response)
                if not result or "intent" not in result:
                    raise ValueError("invalid_intent_response")

                primary_intent = self._coerce_user_intent(result.get("intent"))
                if primary_intent is None:
                    raise ValueError(f"unknown_intent: {result.get('intent')}")

                fallback_intent = self._coerce_user_intent(result.get("fallback_intent"))

                llm_confidence = float(result.get("confidence", 0.5))

                analysis = self._build_intent_analysis(
                    message,
                    primary_intent,
                    confidence=llm_confidence,
                    fallback_intent=fallback_intent,
                )
                # 成功，reset 超时状态
                self._llm_intent_timeout = 15.0
                logger.info(
                    f"[{self.name}] LLM意图分析成功: {analysis.primary_intent.value} "
                    f"(confidence={analysis.confidence:.2f})"
                )
                return analysis

            except asyncio.TimeoutError:
                # 超时：延长超时重试
                retries += 1
                if retries > self._llm_intent_max_retries:
                    logger.warning(
                        f"[{self.name}] LLM意图分析第{retries - 1}次超时，已达最大重试次数"
                    )
                    self._llm_intent_timeout = 15.0  # reset 供下次使用
                    return None
                current_timeout = min(current_timeout * 2, self._llm_intent_max_timeout)
                self._llm_intent_timeout = current_timeout
                logger.warning(
                    f"[{self.name}] LLM意图分析超时({current_timeout / 2:.0f}s)，"
                    f"第{retries}次重试，使用timeout={current_timeout:.0f}s"
                )
                continue

            except Exception as e:
                logger.warning(f"[{self.name}] LLM意图分析异常: {e}")
                self._llm_intent_timeout = 15.0  # reset 供下次使用
                return None

        self._llm_intent_timeout = 15.0  # reset
        return None

    def _build_intent_analysis_prompt(self, message: str) -> str:
        """
        构造 LLM 意图分析提示词。

        提示词包含：
        1. 系统工作流说明（让LLM理解这是一个小说创作平台）
        2. 所有Agent及其职责（让LLM知道有哪些子Agent可用）
        3. 所有意图类型及其含义
        4. 判断规则（帮助LLM区分易混淆的意图）
        """
        system_desc = """【系统背景】
这是一个 AI 辅助小说创作平台。平台有完整的长篇创作工作流，由多个专业 Agent 分工完成：

【Agent 职责】
- WorldbuilderAgent：构建世界观（世界设定、力量体系、地理、势力、文化等）
- CharacterBuilderAgent：创建角色档案/人设卡（主角、配角、反派等人物）
- OutlinerAgent：规划故事大纲（卷/章结构、主线/支线剧情）
- ChapterWriterAgent：撰写章节正文
- EvaluatorAgent：评估章节质量
- PolisherAgent：润色修订章节
- ContinuousWriter：无限续写（对已有章节续写）

【工作流顺序】
当用户要创作一部新小说时，系统按顺序执行：
世界观 → 角色档案 → 故事大纲 → 章节正文（并行可写多章）→ 评估 → 润色

【关键区分规则】
- "写小说" + "主角叫XXX" → CREATE_NOVEL（主角是小说的设定之一）
- "创建角色档案/人设卡/角色卡" → CREATE_CHARACTER
- "梳理/生成事件线/剧情线" → CREATE_EVENTLINES
- "续写/继续写" → CONTINUE_WRITE
- "润色/改写" → POLISH_CONTENT"""

        intent_descriptions = {
            UserIntent.CREATE_NOVEL: (
                "用户要开始创作一部新小说。关键词：'写小说/创作/开始写'、指定了主角名字、"
                "提到小说类型（玄幻/都市等）、要求'搭大纲''世界观''写正文'。"
                "注意：只要表达了'写一个故事/小说'的意愿，即便同时提到主角名字，"
                "也用 CREATE_NOVEL，而不是 CREATE_CHARACTER。"
            ),
            UserIntent.CREATE_CHARACTER: (
                "用户要创建角色档案、人设卡，或把角色加入资料库。"
                "注意：同时提到'写小说'时，CREATE_NOVEL 优先。"
            ),
            UserIntent.CREATE_EVENTLINES: "用户要梳理、生成、规划事件线/剧情线/主线/支线",
            UserIntent.CREATE_DETAIL_OUTLINE: "用户要生成、补全、完善章节细纲/详细大纲",
            UserIntent.CREATE_CHAPTER_SETTINGS: "用户要生成章纲、章节设定或章节规划",
            UserIntent.CONTINUE_WRITE: "用户要对已有章节进行续写、继续写、接着写下一章",
            UserIntent.POLISH_CONTENT: "用户要润色、改写、优化已有的章节内容/段落/文字",
            UserIntent.SEARCH_WEB: "用户要联网搜索资料、术语、背景信息、历史事件",
            UserIntent.SEARCH_TRENDS: "用户要查询最新热点、热搜、热梗、流行趋势",
            UserIntent.QUERY_KNOWLEDGE: "用户要查询项目内已有的设定、人物状态、剧情进展、前文内容",
            UserIntent.GENERAL_CHAT: "普通闲聊、问候、无明确执行意图的对话",
            UserIntent.ASK_HELP: "用户询问如何使用本平台的功能或操作指引",
            UserIntent.PROVIDE_FEEDBACK: "用户评价、反馈、纠正已有的创作结果",
            UserIntent.PROJECT_MANAGE: "用户要保存/加载/切换/导出/删除项目",
            UserIntent.CONFIG_SETTINGS: "用户要调整API、模型、参数等系统配置",
        }

        allowed_lines = [
            f'- "{intent.value}": {intent_descriptions[intent]}' for intent in UserIntent
        ]

        return (
            f"{system_desc}\n\n"
            "【用户消息】\n"
            f'"{message}"\n\n'
            "请根据上述系统背景和Agent职责，判断这条消息最主要的用户意图，只能从以下 intent 中选择一个：\n"
            + "\n".join(allowed_lines)
            + "\n\n"
            "判断要求：\n"
            "1. 以用户真实意图为准，不只看单个关键词。\n"
            "2. '写小说 + 主角名' → CREATE_NOVEL；'主角叫XXX'单独出现才考虑 CREATE_CHARACTER。\n"
            "3. '续写/继续写' → CONTINUE_WRITE；'润色/改写已有内容' → POLISH_CONTENT。\n"
            "4. 置信度：很确定用0.9+，比较确定用0.7-0.9，不确定用0.5-0.7。\n\n"
            "只返回 JSON，不要解释：\n"
            '{\n'
            '  "intent": "create_novel",\n'
            '  "confidence": 0.85,\n'
            '  "fallback_intent": "general_chat"\n'
            '}'
        )

    def _parse_intent_analysis_response(self, response: Any) -> Optional[Dict[str, Any]]:
        """解析意图分析 JSON。"""
        raw_text = str(response or "").strip()
        if not raw_text:
            return None
        try:
            return json.loads(raw_text)
        except Exception:
            pass

        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if not json_match:
            return None
        try:
            return json.loads(json_match.group())
        except Exception:
            return None

    @staticmethod
    def _coerce_user_intent(value: Any) -> Optional[UserIntent]:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
        try:
            return UserIntent(raw)
        except ValueError:
            return None
    
    def _extract_entities(self, message: str, intent: UserIntent) -> Dict[str, Any]:
        """提取消息中的实体"""
        entities = {}
        message_lower = message.lower()

        def _parse_chinese_number(text: str) -> Optional[int]:
            raw = str(text or "").strip()
            if not raw:
                return None
            if raw.isdigit():
                try:
                    return int(raw)
                except ValueError:
                    return None

            digits = {
                "零": 0,
                "〇": 0,
                "一": 1,
                "二": 2,
                "两": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
                "九": 9,
            }
            units = {
                "十": 10,
                "百": 100,
                "千": 1000,
                "万": 10000,
            }

            total = 0
            current = 0
            last_unit = 1
            for ch in raw:
                if ch in digits:
                    current = digits[ch]
                    continue
                if ch in units:
                    unit_val = units[ch]
                    if current == 0:
                        current = 1
                    if unit_val >= 10000:
                        total = (total + current) * unit_val
                        current = 0
                        last_unit = unit_val
                        continue
                    total += current * unit_val
                    current = 0
                    last_unit = unit_val
                    continue
                return None
            value = total + current
            if value <= 0:
                return None
            return value

        if any(keyword in message for keyword in ["短篇", "短故事", "微小说"]):
            entities["short_story_requested"] = True

        if any(keyword in message for keyword in ["词条", "关键词", "关键字"]):
            entities["keyword_driven_story"] = True
            keyword_match = re.search(r"(?:词条|关键词|关键字)[：:\s]+(.+)$", message)
            if keyword_match is None:
                keyword_match = re.search(r"[：:]\s*(.+)$", message)
            if keyword_match:
                raw_keywords = keyword_match.group(1)
                parsed_keywords = [
                    item.strip()
                    for item in re.split(r"[,，、;；|/]+", raw_keywords)
                    if item.strip()
                ]
                if parsed_keywords:
                    entities["story_keywords"] = parsed_keywords
        
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
            for platform, keywords in platform_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    entities["platform"] = platform
                    break
            if "platform" not in entities:
                entities["platform"] = "toutiao"  # 默认头条
        
        # 提取章节号
        chapter_match = re.search(r"第([0-9一二三四五六七八九十百千万两零〇]+)章", message)
        if chapter_match:
            parsed = _parse_chinese_number(chapter_match.group(1))
            if parsed:
                entities["chapter_number"] = parsed
        
        # 检测是否是章节创作请求
        if intent in [UserIntent.CREATE_NOVEL, UserIntent.CONTINUE_WRITE]:
            # 检查是否明确要求写某一章
            if re.search(r"(写|创作|生成)第([0-9一二三四五六七八九十百千万两零〇]+)章", message):
                entities["explicit_chapter_request"] = True
                if "chapter_number" not in entities:
                    match = re.search(r"第([0-9一二三四五六七八九十百千万两零〇]+)章", message)
                    if match:
                        parsed = _parse_chinese_number(match.group(1))
                        if parsed:
                            entities["chapter_number"] = parsed

        if intent == UserIntent.CREATE_CHARACTER:
            character_role = self._detect_character_role(message)
            if character_role:
                entities["character_role"] = character_role
            cleaned_prompt = self._clean_character_request_message(message)
            if cleaned_prompt:
                entities["character_prompt"] = cleaned_prompt
            name_match = re.search(r"(?:叫|名叫|名字是|姓名是)\s*([A-Za-z0-9\u4e00-\u9fa5·]{2,24})", message)
            if name_match:
                entities["character_name"] = name_match.group(1).strip()
            entities["save_to_library"] = any(token in message for token in ("资料库", "保存", "存到", "同步"))

        if intent == UserIntent.CREATE_EVENTLINES:
            entities["project_data_type"] = "eventlines"

        if intent == UserIntent.CREATE_DETAIL_OUTLINE:
            entities["project_data_type"] = "detail_settings"

        if intent == UserIntent.CREATE_CHAPTER_SETTINGS:
            entities["project_data_type"] = "chapter_settings"
        
        return entities

    @staticmethod
    def _detect_character_role(message: str) -> str:
        text = str(message or "").strip()
        role_map = {
            "主角": ("主角", "男主", "女主"),
            "反派": ("反派", "boss", "boss", "恶役"),
            "配角": ("配角", "伙伴", "队友"),
        }
        for normalized, aliases in role_map.items():
            if any(alias in text for alias in aliases):
                return normalized
        if any(token in text for token in ("角色", "人物")):
            return "角色"
        return "主角"

    @staticmethod
    def _clean_character_request_message(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return ""

        patterns = [
            r"^(?:请|帮我|麻烦|给我|给)?(?:直接|现在|先)?(?:创建|建立|生成|设计|写|做|补全|完善|添加|增加|加入|保存|同步)(?:一[份个张条]?|个)?(?:主角|角色|人物|配角|反派|男主|女主)?(?:档案|资料|资料卡|角色卡|人物卡|人设卡|人设|设定|到资料库|进资料库)?[\s：:，,]*",
            r"^(?:请|帮我|麻烦|给我|给)?(?:把)?(?:主角|角色|人物|配角|反派|男主|女主)(?:做|建|写|补全|完善|生成|创建|设计|添加|增加|加入|保存|同步)(?:一[份个张条]?|个)?(?:档案|资料|资料卡|角色卡|人物卡|人设卡|人设|设定|到资料库|进资料库)?[\s：:，,]*",
            r"^(?:请|帮我|麻烦|给我|给)?(?:把)?(?:这个|该)?(?:主角|角色|人物)(?:加入|保存|同步)(?:到|进)?资料库[\s：:，,]*",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, count=1)

        cleaned = re.sub(r"^(?:主角|角色|人物|配角|反派)[\s：:，,]*", "", cleaned, count=1)
        cleaned = cleaned.strip("：:，, \n\t")
        return cleaned or text

    def _is_character_creation_request(self, message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False

        if any(token in text for token in ("查看角色", "角色状态", "人物关系", "主角现在", "查询角色", "检索角色")):
            return False

        # 如果用户在说"写小说/创作小说/写故事"等明确的小说创作意图，
        # 则"主角"是指已有小说中的主角，不是"创建角色档案"
        novel_context_keywords = (
            "小说", "创作", "写书", "写故事", "故事线", "剧情",
            "大纲", "世界观", "长篇", "短篇", "写一部", "开一本",
            "新书", "新故事", "主角是", "主角叫", "主角名字",
        )
        has_novel_context = any(kw in text for kw in novel_context_keywords)

        action_keywords = ("创建", "建立", "生成", "设计", "做", "补全", "完善", "添加", "增加", "加入", "保存", "同步")
        target_keywords = ("主角", "角色", "人物", "配角", "反派", "男主", "女主")
        profile_keywords = ("档案", "资料", "资料库", "角色卡", "人物卡", "人设", "设定")

        has_action = any(token in text for token in action_keywords)
        has_target = any(token in text for token in target_keywords)
        has_profile = any(token in text for token in profile_keywords)

        # 有小说创作上下文时，"主角"不触发独立角色创建
        if has_novel_context and has_target and not has_profile and not has_action:
            return False

        if has_action and has_target and has_profile:
            return True
        if has_action and has_target and re.search(r"(?:创建|建立|生成|设计|写|做).{0,8}(?:主角|角色|人物|配角|反派|男主|女主)", text):
            return True
        if has_target and has_profile and re.search(r"(?:主角|角色|人物|配角|反派|男主|女主).{0,8}(?:档案|角色卡|人物卡|人设|设定|资料库)", text):
            return True
        if has_target and any(token in text for token in ("加入资料库", "保存到资料库", "同步到资料库", "存到资料库")):
            return True
        return False

    def _detect_knowledge_generation_intent(self, message: str) -> Optional[UserIntent]:
        text = str(message or "").strip()
        if not text:
            return None

        action_keywords = ("生成", "创建", "整理", "梳理", "补全", "完善", "规划", "做", "写", "列出")
        has_action = any(keyword in text for keyword in action_keywords)

        if any(token in text for token in ("事件线", "剧情线", "故事线")):
            if has_action or any(token in text for token in ("主线", "支线", "脉络")):
                return UserIntent.CREATE_EVENTLINES

        if any(token in text for token in ("细纲", "详细大纲", "章节细纲")):
            if has_action or "第" in text:
                return UserIntent.CREATE_DETAIL_OUTLINE

        if any(token in text for token in ("章纲", "章纲设定", "章节设定", "章节规划", "章节卡")):
            if has_action or "第" in text:
                return UserIntent.CREATE_CHAPTER_SETTINGS

        return None
    
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
                        "content": result.document if hasattr(result, 'document') else str(result),
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
        调用 Skill 工具
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            
        Returns:
            工具调用结果
        """
        if tool_name not in self.SKILLS:
            return {"error": f"未知工具: {tool_name}"}
        
        skill_config = self.SKILLS[tool_name]
        
        try:
            logger.info(f"[{self.name}] 调用 Skill: {skill_config['skill']}/{skill_config['method']}")
            
            result = self.use_skill(
                skill_config["skill"],
                skill_config["method"],
                **args
            )
            
            # 检查结果
            if not result or not result.get("success"):
                error_msg = result.get("error", "工具调用失败") if result else "工具调用失败"
                raise Exception(error_msg)
            
            return {
                "success": True,
                "tool": tool_name,
                "data": result.get("data", [])
            }
            
        except Exception as e:
            logger.error(f"[{self.name}] 工具调用失败: {e}")
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e)
            }
    
    
    async def route_and_respond(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        路由用户请求并生成响应（增强透明化版本）
        
        这是主入口方法，保证每个请求都有响应
        会根据意图分析结果，将任务分发给对应的智能体执行
        
        改进：
        - 透明化输出：清晰展示决策过程
        - 友好错误提示：用户可理解的错误信息
        - 性能优化：并行执行知识库和工具调用
        
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
            - routing_info: 路由决策信息（透明化）
        """
        import time
        start_time = time.time()
        
        result = {
            "response": "",
            "intent": None,
            "knowledge_results": [],
            "tool_results": None,
            "routed_to": None,
            "delegated_result": None,
            "success": True,
            "routing_info": {
                "steps": [],
                "duration": 0
            }
        }
        
        try:
            # 1. 分析意图（透明化）
            result["routing_info"]["steps"].append({
                "step": "intent_analysis",
                "status": "started",
                "message": "🔍 正在分析您的意图..."
            })
            
            intent_analysis = await self.analyze_intent(message)
            result["intent"] = {
                "type": intent_analysis.primary_intent.value,
                "confidence": intent_analysis.confidence,
                "entities": intent_analysis.entities
            }
            
            # 透明化输出
            intent_emoji = self._get_intent_emoji(intent_analysis.primary_intent)
            confidence_level = "高" if intent_analysis.confidence > 0.7 else "中" if intent_analysis.confidence > 0.5 else "低"
            
            result["routing_info"]["steps"].append({
                "step": "intent_analysis",
                "status": "completed",
                "message": f"{intent_emoji} 意图识别：{self._get_intent_display_name(intent_analysis.primary_intent)}",
                "details": f"置信度：{confidence_level}（{intent_analysis.confidence:.0%}）"
            })
            
            logger.info(
                f"[{self.name}] 意图分析: {intent_analysis.primary_intent.value} "
                f"(置信度: {intent_analysis.confidence:.2f})"
            )
            
            # 2. 并行执行知识库检索和工具调用（性能优化）
            import asyncio
            tasks = []
            
            if intent_analysis.requires_knowledge_base:
                result["routing_info"]["steps"].append({
                    "step": "knowledge_retrieval",
                    "status": "started",
                    "message": "📚 正在检索知识库..."
                })
                tasks.append(("kb", self.retrieve_knowledge(message)))
            
            if intent_analysis.requires_tool_call and intent_analysis.tool_name:
                tool_display = self._get_tool_display_name(intent_analysis.tool_name)
                result["routing_info"]["steps"].append({
                    "step": "tool_call",
                    "status": "started",
                    "message": f"🔧 正在调用工具：{tool_display}"
                })
                tasks.append(("tool", self.call_tool(
                    intent_analysis.tool_name,
                    intent_analysis.tool_args or {}
                )))
            
            # 并行执行
            if tasks:
                task_results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
                for i, (task_type, task_result) in enumerate(zip([t[0] for t in tasks], task_results)):
                    if isinstance(task_result, Exception):
                        logger.error(f"[{self.name}] {task_type} 执行失败: {task_result}")
                        result["routing_info"]["steps"].append({
                            "step": task_type,
                            "status": "failed",
                            "message": f"❌ {task_type} 执行失败",
                            "error": str(task_result)
                        })
                    else:
                        if task_type == "kb":
                            result["knowledge_results"] = task_result
                            kb_count = len(task_result) if isinstance(task_result, list) else 0
                            result["routing_info"]["steps"].append({
                                "step": "knowledge_retrieval",
                                "status": "completed",
                                "message": f"✅ 知识库检索完成：找到 {kb_count} 条相关内容"
                            })
                        elif task_type == "tool":
                            result["tool_results"] = task_result
                            if task_result and task_result.get("success"):
                                data_count = len(task_result.get("data", []))
                                result["routing_info"]["steps"].append({
                                    "step": "tool_call",
                                    "status": "completed",
                                    "message": f"✅ 工具调用成功：获取 {data_count} 条结果"
                                })
                            else:
                                result["routing_info"]["steps"].append({
                                    "step": "tool_call",
                                    "status": "failed",
                                    "message": "⚠️ 工具调用失败",
                                    "error": task_result.get("error") if task_result else "未知错误"
                                })
            
            # 4. 根据意图分发任务给对应的智能体（透明化）
            result["routing_info"]["steps"].append({
                "step": "task_delegation",
                "status": "started",
                "message": "🎯 正在分发任务..."
            })
            
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
                
                agent_name = delegated_result.get("agent_name", "未知Agent")
                result["routing_info"]["steps"].append({
                    "step": "task_delegation",
                    "status": "completed",
                    "message": f"📞 已分发给：{agent_name}"
                })
                
                # 如果被委派的Agent返回了响应，使用它
                if delegated_result.get("response"):
                    result["response"] = delegated_result["response"]
            else:
                result["routing_info"]["steps"].append({
                    "step": "task_delegation",
                    "status": "completed",
                    "message": "💬 由路由器直接处理"
                })
            
            # 5. 如果没有委派响应，生成路由层响应
            if not result["response"]:
                result["routing_info"]["steps"].append({
                    "step": "response_generation",
                    "status": "started",
                    "message": "✍️ 正在生成回复..."
                })
                
                response = await self._generate_response(
                    message=message,
                    intent_analysis=intent_analysis,
                    knowledge_results=result["knowledge_results"],
                    tool_results=result["tool_results"],
                    context=context
                )
                result["response"] = response
                
                result["routing_info"]["steps"].append({
                    "step": "response_generation",
                    "status": "completed",
                    "message": "✅ 回复生成完成"
                })
            
        except Exception as e:
            logger.error(f"[{self.name}] 路由处理失败: {e}", exc_info=True)
            result["success"] = False
            
            # 友好的错误提示
            error_message = self._format_friendly_error(e, intent_analysis if 'intent_analysis' in locals() else None)
            result["response"] = error_message
            
            result["routing_info"]["steps"].append({
                "step": "error",
                "status": "failed",
                "message": "❌ 处理失败",
                "error": str(e)
            })
        
        # 保证有响应（双重保障）
        if not result["response"]:
            result["response"] = "我收到了您的消息，请问有什么可以帮助您的？"
        
        # 计算总耗时
        result["routing_info"]["duration"] = time.time() - start_time
        result["routing_info"]["steps"].append({
            "step": "completed",
            "status": "success",
            "message": f"⏱️ 处理完成（耗时 {result['routing_info']['duration']:.2f}秒）"
        })
        
        return result
    
    def _get_intent_emoji(self, intent: UserIntent) -> str:
        """获取意图对应的emoji"""
        emoji_map = {
            UserIntent.CREATE_NOVEL: "✍️",
            UserIntent.CREATE_CHARACTER: "👤",
            UserIntent.CREATE_EVENTLINES: "🧭",
            UserIntent.CREATE_DETAIL_OUTLINE: "🗂️",
            UserIntent.CREATE_CHAPTER_SETTINGS: "📑",
            UserIntent.CONTINUE_WRITE: "📝",
            UserIntent.POLISH_CONTENT: "✨",
            UserIntent.SEARCH_WEB: "🔍",
            UserIntent.SEARCH_TRENDS: "📊",
            UserIntent.QUERY_KNOWLEDGE: "📚",
            UserIntent.GENERAL_CHAT: "💬",
            UserIntent.ASK_HELP: "❓",
            UserIntent.PROJECT_MANAGE: "📁",
            UserIntent.CONFIG_SETTINGS: "⚙️"
        }
        return emoji_map.get(intent, "🤔")
    
    def _get_intent_display_name(self, intent: UserIntent) -> str:
        """获取意图的显示名称"""
        name_map = {
            UserIntent.CREATE_NOVEL: "创作小说",
            UserIntent.CREATE_CHARACTER: "创建角色档案",
            UserIntent.CREATE_EVENTLINES: "生成事件线",
            UserIntent.CREATE_DETAIL_OUTLINE: "生成细纲",
            UserIntent.CREATE_CHAPTER_SETTINGS: "生成章纲设定",
            UserIntent.CONTINUE_WRITE: "续写内容",
            UserIntent.POLISH_CONTENT: "润色文字",
            UserIntent.SEARCH_WEB: "网络搜索",
            UserIntent.SEARCH_TRENDS: "热点查询",
            UserIntent.QUERY_KNOWLEDGE: "知识库查询",
            UserIntent.GENERAL_CHAT: "普通对话",
            UserIntent.ASK_HELP: "寻求帮助",
            UserIntent.PROJECT_MANAGE: "项目管理",
            UserIntent.CONFIG_SETTINGS: "配置设置"
        }
        return name_map.get(intent, intent.value)
    
    def _get_tool_display_name(self, tool_name: str) -> str:
        """获取工具的显示名称"""
        name_map = {
            "web_search": "网络搜索",
            "toutiao_trends": "头条热榜",
            "douyin_trends": "抖音热点",
            "knowledge_base": "知识库"
        }
        return name_map.get(tool_name, tool_name)
    
    def _format_friendly_error(self, error: Exception, intent_analysis: Optional[IntentAnalysis] = None) -> str:
        """
        格式化用户友好的错误提示
        
        Args:
            error: 异常对象
            intent_analysis: 意图分析结果
            
        Returns:
            友好的错误消息
        """
        error_str = str(error).lower()
        
        # 网络相关错误
        if "connection" in error_str or "timeout" in error_str:
            return (
                "😔 抱歉，网络连接出现问题。\n\n"
                "可能的原因：\n"
                "• 网络不稳定或断开\n"
                "• API服务器响应超时\n"
                "• 代理服务器未启动\n\n"
                "💡 建议：请检查网络连接后重试"
            )
        
        # API相关错误
        if "api" in error_str or "401" in error_str or "403" in error_str:
            return (
                "🔑 抱歉，API认证出现问题。\n\n"
                "可能的原因：\n"
                "• API密钥未配置或已过期\n"
                "• API配额已用完\n"
                "• 服务暂时不可用\n\n"
                "💡 建议：请在设置中检查API配置"
            )
        
        # 模型相关错误
        if "model" in error_str or "404" in error_str:
            return (
                "🤖 抱歉，AI模型调用失败。\n\n"
                "可能的原因：\n"
                "• 模型名称不正确\n"
                "• 模型暂时不可用\n"
                "• 代理服务器配置问题\n\n"
                "💡 建议：请尝试切换到其他模型"
            )
        
        # 知识库相关错误
        if "knowledge" in error_str or "search" in error_str:
            return (
                "📚 抱歉，知识库查询出现问题。\n\n"
                "💡 建议：我将尝试不使用知识库来回答您的问题"
            )
        
        # 通用错误
        intent_hint = ""
        if intent_analysis:
            intent_name = self._get_intent_display_name(intent_analysis.primary_intent)
            intent_hint = f"\n\n您想要：{intent_name}"
        
        return (
            f"😔 抱歉，处理您的请求时遇到了问题。{intent_hint}\n\n"
            f"错误详情：{str(error)[:100]}\n\n"
            "💡 建议：\n"
            "• 请尝试换个方式描述您的需求\n"
            "• 或稍后再试\n"
            "• 如果问题持续，请联系技术支持"
        )
    
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
            explicit_command = (context or {}).get("explicit_command") if isinstance(context, dict) else None
            explicit_name = str((explicit_command or {}).get("name") or "").strip().lower()
            if explicit_name and self.coordinator:
                if explicit_name == "create":
                    return await self._execute_create_novel_pipeline(message=message, context=context)
                if explicit_name == "worldbuild":
                    return await self._execute_worldbuild_pipeline(message=message, context=context)
                if explicit_name == "outline":
                    return await self._execute_outline_pipeline(message=message, context=context)
                if explicit_name == "chapter":
                    chapter_num = self._normalize_positive_int((explicit_command or {}).get("chapter_number"), 0)
                    if chapter_num <= 0:
                        return {
                            "agent_name": "ChapterWriter",
                            "action": "write_chapter",
                            "error": "章节号无效，请使用“续写章节 3”这样的格式。",
                            "response": "章节号无效，请使用“续写章节 3”这样的格式。",
                            "is_complete": False,
                            "run_id": self._get_run_id(context),
                        }
                    executed = await self._execute_project_chapter_write(chapter_num=chapter_num, context=context)
                    if executed:
                        return executed
                    return {
                        "agent_name": "ChapterWriter",
                        "action": "write_chapter",
                        "error": f"第{chapter_num}章不存在，请先生成大纲。",
                        "response": f"第{chapter_num}章不存在，请先生成大纲后再执行“续写章节 {chapter_num}”。",
                        "is_complete": False,
                        "run_id": self._get_run_id(context),
                    }

            # === 角色建档 → CharacterBuilder ===
            if intent == UserIntent.CREATE_CHARACTER:
                return await self._execute_character_creation_pipeline(
                    message=message,
                    context=context,
                )

            if intent == UserIntent.CREATE_EVENTLINES:
                return await self._execute_project_data_generation_pipeline(
                    message=message,
                    context=context,
                    data_type="eventlines",
                    agent_name="EventlineBuilder",
                    stage="eventlines",
                    label="事件线",
                )

            if intent == UserIntent.CREATE_DETAIL_OUTLINE:
                return await self._execute_project_data_generation_pipeline(
                    message=message,
                    context=context,
                    data_type="detail_settings",
                    agent_name="DetailOutlineBuilder",
                    stage="detail_outlining",
                    label="细纲",
                )

            if intent == UserIntent.CREATE_CHAPTER_SETTINGS:
                return await self._execute_project_data_generation_pipeline(
                    message=message,
                    context=context,
                    data_type="chapter_settings",
                    agent_name="ChapterSettingBuilder",
                    stage="chapter_settings",
                    label="章纲设定",
                )

            # === 创建小说 → 协调器 ===
            if intent == UserIntent.CREATE_NOVEL:
                if entities.get("short_story_requested") or entities.get("keyword_driven_story"):
                    keyword_list = entities.get("story_keywords") or []
                    keyword_hint = f"\n已识别词条：{', '.join(keyword_list)}" if keyword_list else ""
                    return {
                        "agent_name": "Router",
                        "action": "open_short_story_panel",
                        "response": (
                            "检测到您要进行短篇创作，请直接使用左侧固定入口「短篇创作」。"
                            f"{keyword_hint}\n\n"
                            "固定面板流程：\n"
                            "1. 进入左侧「短篇创作」模块\n"
                            "2. 直接粘贴灵感、例文、题材或词条等素材\n"
                            "3. 系统会先识别素材并生成 3 个融合方案\n"
                            "4. 依次完成方案选择、导语、大纲、章节生成、质检、复审、取名\n\n"
                            "这个固定面板会按“统一输入 -> 3个融合方案 -> 导语 -> 大纲 -> 正文 -> 质检 -> 复审 -> 书名”的流程推进。"
                        ),
                        "params": {
                            "module": "short-story",
                            "keywords": keyword_list,
                        }
                    }

                auto_execute = bool((context or {}).get("auto_execute"))
                if self.coordinator:
                    if auto_execute:
                        # Detect worldbuilding-only requests - route to worldbuild pipeline
                        worldbuild_keywords = (
                            "写世界观", "建世界观", "创建世界观", "构建世界观", "生成世界观",
                            "设定世界观", "建立世界观", "先写世界观", "帮我写世界观",
                        )
                        novel_creation_keywords = (
                            "创作", "写一部", "新小说", "开始写", "创建小说", "开一本新书",
                            "写一本", "写个", "写篇", "正文",
                        )
                        msg_lower = message.lower()
                        is_worldbuild_only = any(kw in msg_lower for kw in worldbuild_keywords)
                        is_novel_creation = any(kw in msg_lower for kw in novel_creation_keywords)
                        if is_worldbuild_only and not is_novel_creation:
                            return await self._execute_worldbuild_pipeline(
                                message=message,
                                context=context,
                            )
                        return await self._execute_create_novel_pipeline(
                            message=message,
                            context=context,
                        )

                    requirements = self._build_creation_requirements(context, message)
                    contract_payload = self._persist_creation_contract_payload(
                        self._build_creation_contract_payload(
                            requirements,
                            context,
                            user_confirmed=False,
                        )
                    )
                    logger.info(f"[{self.name}] 已生成待确认创作合同草案")
                    return self._build_contract_confirmation_response(
                        requirements=requirements,
                        contract_payload=contract_payload,
                        context=context,
                    )
                else:
                    return {
                        "agent_name": "Router",
                        "response": "检测到您想创作小说，请在创作面板中配置并开始创作。"
                    }
            
            # === 续写 → 无限续写Agent ===
            elif intent == UserIntent.CONTINUE_WRITE:
                chapter_num = entities.get("chapter_number", 0)
                explicit_request = entities.get("explicit_chapter_request", False)
                auto_execute = bool((context or {}).get("auto_execute"))
                
                # 如果用户明确要求写某一章，引导使用正确的创作流程
                if explicit_request and chapter_num:
                    if auto_execute and self.coordinator:
                        executed = await self._execute_project_chapter_write(
                            chapter_num=chapter_num,
                            context=context,
                        )
                        if executed:
                            return executed

                    return {
                        "agent_name": "Router",
                        "action": "guide_to_creation",
                        "response": f"我理解您想创作第{chapter_num}章。\n\n"
                                   f"📝 **创作章节的正确方式**：\n"
                                   f"1. 如果是新项目，请先在「创作面板」完成世界观和大纲设置\n"
                                   f"2. 然后在「章节列表」中找到第{chapter_num}章，点击「生成」按钮\n"
                                   f"3. 或者使用「无限续写」功能逐章创作\n\n"
                                   f"💡 如果您想在对话中讨论第{chapter_num}章的创作思路，我很乐意帮助您！",
                        "params": {
                            "chapter_number": chapter_num,
                            "needs_setup": True
                        }
                    }
                logger.info(f"[{self.name}] 分发续写任务到 ContinuousWriter")
                return await self._execute_continuous_write_pipeline(
                    message=message,
                    context=context,
                    chapter_num=chapter_num,
                )
            
            # === 润色 → 润色Agent ===
            elif intent == UserIntent.POLISH_CONTENT:
                logger.info(f"[{self.name}] 分发润色任务到 Polisher")
                return await self._execute_polish_pipeline(
                    message=message,
                    context=context,
                )
            
            # === 普通对话 → 沟通Agent ===
            elif intent == UserIntent.GENERAL_CHAT:
                communicator = self._get_communicator()
                if communicator:
                    logger.info(f"[{self.name}] 分发对话任务到 Communicator")
                    
                    # 将知识库和工具结果传递给沟通Agent
                    chat_context = dict(context or {})
                    if knowledge_results:
                        chat_context["knowledge"] = knowledge_results
                    if tool_results:
                        chat_context["tool_results"] = tool_results
                    
                    # 执行对话
                    chat_result = await communicator.chat(message, runtime_context=chat_context)
                    
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
        
        return ""  # 默认类型

    @staticmethod
    def _normalize_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def _build_discussion_context(
        self,
        context: Optional[Dict[str, Any]],
        message: str,
    ) -> str:
        if not isinstance(context, dict):
            return str(message or "").strip()

        history = context.get("conversation_history")
        collected_info = context.get("collected_info")
        lines: List[str] = []

        if isinstance(history, list):
            for item in history:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip().lower()
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                role_label = "用户" if role == "user" else "助手" if role == "assistant" else "系统"
                lines.append(f"{role_label}：{content}")

        if isinstance(collected_info, dict) and collected_info:
            extra_items = []
            for key, value in collected_info.items():
                if value in (None, "", [], {}):
                    continue
                extra_items.append(f"{key}: {value}")
            if extra_items:
                lines.append("已提炼需求：")
                lines.extend(extra_items)

        latest_message = str(message or "").strip()
        if latest_message:
            lines.append(f"当前触发消息：{latest_message}")

        merged = "\n".join(lines).strip()
        if not merged:
            merged = latest_message
        return merged[:6000]

    def _build_worldbuilding_requirements_text(self, requirements: Dict[str, Any]) -> str:
        base_requirements = str(requirements.get("requirements") or "").strip()
        discussion_context = str(requirements.get("discussion_context") or "").strip()
        if not discussion_context:
            return base_requirements
        if base_requirements:
            return (
                f"{base_requirements}\n\n"
                "【沟通助手完整讨论摘要】\n"
                f"{discussion_context}"
            ).strip()
        return f"【沟通助手完整讨论摘要】\n{discussion_context}".strip()

    def _build_outline_plot_idea_text(self, requirements: Dict[str, Any]) -> str:
        plot_idea = str(requirements.get("plot_idea") or "").strip()
        discussion_context = str(requirements.get("discussion_context") or "").strip()
        if discussion_context:
            return (
                f"{plot_idea}\n\n"
                "【沟通助手完整讨论摘要】\n"
                f"{discussion_context}"
            ).strip()
        return plot_idea

    def _should_resume_existing_project(
        self,
        context: Optional[Dict[str, Any]],
        message: str,
    ) -> bool:
        explicit_command = (context or {}).get("explicit_command") if isinstance(context, dict) else None
        explicit_name = str((explicit_command or {}).get("name") or "").strip().lower()
        if explicit_name != "create":
            return False
        raw = " ".join([
            str((explicit_command or {}).get("message") or "").strip(),
            str((explicit_command or {}).get("raw_args") or "").strip(),
            str(message or "").strip(),
        ]).strip()
        if not raw:
            return False
        resume_keywords = ("继续", "续写", "接着", "断点", "续作", "完成这部", "继续完成")
        return any(keyword in raw for keyword in resume_keywords)

    def _build_creation_requirements(
        self,
        context: Optional[Dict[str, Any]],
        message: str,
    ) -> Dict[str, Any]:
        source = {}
        if isinstance(context, dict):
            if isinstance(context.get("creation_requirements"), dict):
                source = dict(context["creation_requirements"])
            elif isinstance(context.get("collected_info"), dict):
                source = dict(context["collected_info"])

        discussion_context = self._build_discussion_context(context, message)

        return {
            "novel_type": str(source.get("novel_type") or self._extract_novel_type(message) or "").strip() or "",
            "theme": str(source.get("theme") or "").strip(),
            "requirements": str(source.get("requirements") or "").strip(),
            "protagonist": str(source.get("protagonist") or "").strip(),
            "plot_idea": str(source.get("plot_idea") or message).strip(),
            "volume_count": self._normalize_positive_int(source.get("volume_count"), 1),
            "chapters_per_volume": self._normalize_positive_int(source.get("chapters_per_volume"), 5),
            "discussion_context": discussion_context,
            "resume_existing": self._should_resume_existing_project(context, message),
            "source_message": str(message or "").strip(),
        }

    def _build_creation_contract_payload(
        self,
        requirements: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        *,
        user_confirmed: bool,
    ) -> Dict[str, Any]:
        """基于当前需求构建创作合同与任务图草案。"""
        contract = build_default_creation_contract(
            novel_type=str(requirements.get("novel_type") or "").strip(),
            theme=str(requirements.get("theme") or "").strip(),
            requirements=str(requirements.get("requirements") or "").strip(),
            protagonist=str(requirements.get("protagonist") or "").strip(),
            plot_idea=str(requirements.get("plot_idea") or "").strip(),
            volume_count=self._normalize_positive_int(requirements.get("volume_count"), 1),
            chapters_per_volume=self._normalize_positive_int(requirements.get("chapters_per_volume"), 5),
            source_session_id=str((context or {}).get("session_id") or "").strip(),
            source_message=str(requirements.get("source_message") or "").strip(),
            user_confirmed=user_confirmed,
        )
        contract.scope["discussion_context"] = str(requirements.get("discussion_context") or "").strip()
        contract.scope["resume_existing"] = bool(requirements.get("resume_existing", False))
        contract.task_graph = build_default_task_graph(contract)
        contract.metadata.update({
            "generated_by": self.name,
            "stage": "router_pipeline",
        })
        return contract.to_dict()

    def _persist_creation_contract_payload(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """保存创作合同与任务图草案到项目状态。"""
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        if not pm.current_project_id:
            return payload

        pm.save_project_state("creation_contract", payload)
        pm.save_project_state("task_graph_draft", payload.get("task_graph", []))
        return payload

    def _supports_formal_collab_execution(self) -> bool:
        if not self.coordinator:
            return False
        return bool(
            callable(getattr(self.coordinator, "initialize_task_pool_from_contract", None))
            and callable(getattr(self.coordinator, "execute_project_ready_tasks", None))
        )

    def _compute_formal_execution_limits(
        self,
        *,
        requirements: Dict[str, Any],
        task_pool_payload: Optional[Dict[str, Any]],
    ) -> Tuple[int, int]:
        total_task_count = len((task_pool_payload or {}).get("tasks", [])) if isinstance(task_pool_payload, dict) else 0
        total_chapters = max(
            1,
            self._normalize_positive_int(requirements.get("volume_count"), 1)
            * self._normalize_positive_int(requirements.get("chapters_per_volume"), 5),
        )
        return (
            min(max(1, total_task_count), 4),
            min(total_chapters, 2),
        )

    async def _fanout_coordinator_progress(
        self,
        context: Optional[Dict[str, Any]],
        data: Any,
        existing_callback: Any,
    ) -> None:
        if existing_callback:
            try:
                existing_result = existing_callback(data)
                if hasattr(existing_result, "__await__"):
                    await existing_result
            except Exception as exc:
                logger.debug(f"[{self.name}] 旧进度回调执行失败: {exc}")

        if not isinstance(data, dict):
            return

        stage = str(data.get("stage") or data.get("task_type") or "").strip()
        current_agent = str(data.get("agent") or data.get("current_agent") or "Coordinator").strip() or "Coordinator"
        content = str(data.get("message") or data.get("content") or "").strip()
        if not content:
            return

        status = "running"
        event_type = str(data.get("type") or "").strip()
        if event_type in {"sub_agent_failed"}:
            status = "failed"
        elif event_type in {"sub_agent_completed"}:
            status = "running"

        await self._emit_progress(
            context,
            {
                "content": content,
                "current_agent": current_agent,
                "stage": stage,
                "status": status,
                "output_dir": str(self.coordinator.project_dir),
            },
        )

    @staticmethod
    def _resolve_result_ref_path(project_dir: Path, result_ref: str) -> Optional[Path]:
        raw = str(result_ref or "").strip()
        if not raw:
            return None
        resolved = Path(raw).expanduser()
        if not resolved.is_absolute():
            resolved = (project_dir / resolved).resolve()
        else:
            resolved = resolved.resolve()
        return resolved

    def _build_formal_task_file_record(
        self,
        *,
        task: Dict[str, Any],
        project_dir: Path,
        existing_paths: Set[str],
    ) -> Optional[Dict[str, str]]:
        if not isinstance(task, dict):
            return None

        result_ref = str(task.get("result_ref") or "").strip()
        resolved_path = self._resolve_result_ref_path(project_dir, result_ref)
        if resolved_path is None or not resolved_path.exists():
            return None

        task_type = str(task.get("task_type") or "").strip()
        kind = "file"
        label = resolved_path.name
        if task_type == "build_world":
            kind = "worldbuilding"
            label = "世界观"
        elif task_type == "build_outline":
            kind = "outline"
            label = "大纲"
        elif task_type == "write_chapter":
            kind = "chapter"
            chapter_number = self._normalize_positive_int(
                ((task.get("inputs") or {}) if isinstance(task.get("inputs"), dict) else {}).get("chapter_number"),
                0,
            )
            label = f"第 {chapter_number} 章" if chapter_number else "章节正文"
        elif task_type == "summary_orchestrate":
            kind = "stage_summary"
            label = str(task.get("title") or "阶段总结").strip() or "阶段总结"

        status = "updated" if str(resolved_path) in existing_paths else "created"
        return self._build_file_record(str(resolved_path), kind, label, status=status)

    async def _execute_create_novel_pipeline_formal(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        requirements: Dict[str, Any],
        contract_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        project_dir = Path(self.coordinator.project_dir).resolve()
        existing_paths = {
            str(path.resolve())
            for path in project_dir.rglob("*")
            if path.is_file()
        }

        await self._emit_progress(
            context,
            {
                "content": "## 创作启动\n已切换到正式多Agent协作执行链。",
                "current_agent": "Coordinator",
                "stage": "starting",
                "status": "running",
                "output_dir": str(project_dir),
            },
        )

        existing_progress_callback = getattr(self.coordinator, "progress_callback", None)
        init_result: Dict[str, Any] = {}
        execute_result: Dict[str, Any] = {}
        try:
            self.coordinator.progress_callback = (
                lambda data: self._fanout_coordinator_progress(context, data, existing_progress_callback)
            )
            init_result = self.coordinator.initialize_task_pool_from_contract(contract_payload, approved=True)
            task_pool_payload = init_result.get("task_pool", {}) if isinstance(init_result, dict) else {}
            max_tasks, max_chapter_tasks = self._compute_formal_execution_limits(
                requirements=requirements,
                task_pool_payload=task_pool_payload,
            )
            execute_result = await self.coordinator.execute_project_ready_tasks(
                max_tasks=max_tasks,
                max_chapter_tasks=max_chapter_tasks,
            )
        finally:
            self.coordinator.progress_callback = existing_progress_callback

        task_pool = execute_result.get("task_pool") if isinstance(execute_result, dict) else None
        if not isinstance(task_pool, dict):
            task_pool = init_result.get("task_pool", {}) if isinstance(init_result, dict) else {}

        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        for task in task_pool.get("tasks", []) if isinstance(task_pool, dict) else []:
            if not isinstance(task, dict):
                continue
            if str(task.get("status") or "").strip().lower() != "completed":
                continue
            file_record = self._build_formal_task_file_record(
                task=task,
                project_dir=project_dir,
                existing_paths=existing_paths,
            )
            if not file_record:
                continue
            if file_record.get("status") == "created":
                self._merge_file_records(created_files, [file_record])
            else:
                self._merge_file_records(updated_files, [file_record])

        outline_rows = pm.load_project_data("outline")
        if not isinstance(outline_rows, list):
            outline_rows = []
        outline_rows = [row for row in outline_rows if isinstance(row, dict)]
        next_incomplete = self._find_next_incomplete_chapter(outline_rows, start_at=1)

        written_chapters: List[Dict[str, Any]] = []
        for index, row in enumerate(outline_rows, start=1):
            chapter_result = self._load_existing_chapter_result(index, row)
            if chapter_result:
                written_chapters.append(chapter_result)

        current_project = pm.get_current_project()
        outline_title = str((current_project.name if current_project else "") or "未命名项目").strip() or "未命名项目"
        compiled_novel_path = ""
        if written_chapters and next_incomplete == 0:
            self._ensure_project_metadata(
                requirements=requirements,
                outline_rows=outline_rows,
                outline_data={"title": outline_title},
            )
            compiled_novel = self._save_compiled_novel(outline_title, written_chapters)
            compiled_novel_path = str((compiled_novel or {}).get("path") or "")
            if compiled_novel_path:
                compiled_file = self._build_file_record(
                    compiled_novel_path,
                    "compiled_novel",
                    "合集",
                    status="updated" if compiled_novel_path in existing_paths else "created",
                )
                if compiled_file["status"] == "created":
                    self._merge_file_records(created_files, [compiled_file])
                else:
                    self._merge_file_records(updated_files, [compiled_file])

        project_ready_execution = {}
        if isinstance(task_pool, dict):
            project_ready_execution = dict(task_pool.get("metadata", {}).get("project_ready_execution", {}) or {})
        if not project_ready_execution and isinstance(execute_result, dict):
            project_ready_execution = dict(execute_result.get("project_ready_execution") or {})

        collab_execution_trace = self.coordinator.project_manager.load_project_state(
            "collab_execution_trace",
            default={},
        )
        executed_tasks = execute_result.get("executed_tasks", []) if isinstance(execute_result, dict) else []
        completed_agents = sorted(
            {
                str(task.get("assigned_agent") or "").strip()
                for task in (task_pool.get("tasks", []) if isinstance(task_pool, dict) else [])
                if isinstance(task, dict)
                and str(task.get("status") or "").strip().lower() == "completed"
                and str(task.get("assigned_agent") or "").strip()
            }
        )

        executed_titles = [
            str(item.get("title") or item.get("task_type") or "").strip()
            for item in executed_tasks
            if isinstance(item, dict) and str(item.get("title") or item.get("task_type") or "").strip()
        ]
        response_parts = [
            "已切换到正式多Agent协作执行链，当前请求会通过合同确认后的任务池执行。",
            "",
            "执行流程：合同 → 任务池 → 子Agent协作 → 项目产物落盘",
        ]
        if executed_titles:
            preview_titles = executed_titles[:8]
            response_parts.extend(["", "已执行任务："] + [f"- {title}" for title in preview_titles])
        if project_ready_execution.get("stop_reason"):
            response_parts.extend(["", f"当前停止原因：{project_ready_execution.get('stop_reason')}"])
        if outline_rows:
            response_parts.extend(["", f"大纲已就绪，共 {len(outline_rows)} 章。"])
        if written_chapters:
            response_parts.append(f"已完成章节：{len(written_chapters)} 章。")
        if next_incomplete:
            response_parts.append(f"下一待完成章节：第 {next_incomplete} 章。")
        else:
            response_parts.append("当前任务池中的章节任务已全部完成。")
        if written_chapters and written_chapters[0].get("content"):
            response_parts.extend([
                "",
                "以下是已落盘的第一章正文：",
                "",
                str(written_chapters[0]["content"]),
            ])

        persisted_paths = {
            "outline_path": str(pm.get_project_data_path("outline")),
            "chapter_paths": [item["path"] for item in created_files + updated_files if item.get("kind") == "chapter"],
        }
        if compiled_novel_path:
            persisted_paths["compiled_novel_path"] = compiled_novel_path

        return {
            "agent_name": "Coordinator",
            "action": "create_novel",
            "response": "\n".join(response_parts),
            "is_complete": next_incomplete == 0,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "output_dir": str(project_dir),
            "focus_module": "write",
            "focus_chapter": next_incomplete or 0,
            "params": {
                **requirements,
                "persisted_paths": persisted_paths,
                "execution_agents": completed_agents,
                "creation_contract": init_result.get("creation_contract", contract_payload) if isinstance(init_result, dict) else contract_payload,
                "task_pool": task_pool,
                "collab_execution_trace": collab_execution_trace,
                "project_ready_task_execution": execute_result,
            },
        }

    def _build_contract_confirmation_response(
        self,
        *,
        requirements: Dict[str, Any],
        contract_payload: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建“先确认合同、再开始执行”的响应。"""
        scope = contract_payload.get("scope", {}) if isinstance(contract_payload, dict) else {}
        constraints = contract_payload.get("constraints", {}) if isinstance(contract_payload, dict) else {}
        quality_rules = constraints.get("quality_rules", []) if isinstance(constraints, dict) else []
        deliverables = contract_payload.get("deliverables", []) if isinstance(contract_payload, dict) else []
        agent_candidates = contract_payload.get("agent_candidates", []) if isinstance(contract_payload, dict) else []
        task_graph = contract_payload.get("task_graph", []) if isinstance(contract_payload, dict) else []

        preview_tasks: List[str] = []
        for item in task_graph[:6]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("task_type") or "").strip()
            if title:
                preview_tasks.append(f"- {title}")

        style_items = constraints.get("style", []) if isinstance(constraints, dict) else []
        style_text = "、".join([str(item).strip() for item in style_items if str(item).strip()]) or "未特别指定"
        quality_text = "、".join([str(item).strip() for item in quality_rules if str(item).strip()]) or "未特别指定"
        deliverables_text = "\n".join([f"- {item}" for item in deliverables[:8]]) if isinstance(deliverables, list) and deliverables else "- 暂无"
        agents_text = "、".join([str(item).strip() for item in agent_candidates[:12] if str(item).strip()]) or "待定"
        task_preview_text = "\n".join(preview_tasks) if preview_tasks else "- 暂无任务预览"

        response = (
            "已根据当前讨论内容整理出一份“创作合同草案”，现在不会直接开始创作。\n\n"
            "请先确认以下方案：\n\n"
            f"- 类型：{scope.get('novel_type') or requirements.get('novel_type') or '未指定'}\n"
            f"- 主题：{scope.get('theme') or requirements.get('theme') or '未指定'}\n"
            f"- 主角：{scope.get('protagonist') or requirements.get('protagonist') or '未指定'}\n"
            f"- 剧情构思：{scope.get('plot_idea') or requirements.get('plot_idea') or '未指定'}\n"
            f"- 预计卷数：{scope.get('volume_count') or requirements.get('volume_count') or 1}\n"
            f"- 每卷章节数：{scope.get('chapters_per_volume') or requirements.get('chapters_per_volume') or 5}\n"
            f"- 总章节数：{scope.get('total_chapters') or '未计算'}\n"
            f"- 风格约束：{style_text}\n"
            f"- 质量规则：{quality_text}\n\n"
            "计划产物：\n"
            f"{deliverables_text}\n\n"
            "候选 Agent：\n"
            f"{agents_text}\n\n"
            "任务预览：\n"
            f"{task_preview_text}\n\n"
            "如果方案无误，请点击“确认当前任务并开始”，系统会进入正式执行阶段。"
        )

        return {
            "agent_name": "Coordinator",
            "action": "confirm_creation_contract",
            "response": response,
            "is_complete": False,
            "requires_confirmation": True,
            "run_id": self._get_run_id(context),
            "focus_module": "write",
            "focus_chapter": 1,
            "params": {
                **requirements,
                "creation_contract": contract_payload,
                "contract_status": "draft",
                "task_graph_draft": contract_payload.get("task_graph", []),
            },
        }

    def _outline_to_project_rows(self, outline_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        chapters: List[Dict[str, Any]] = []
        if self.coordinator:
            extract_method = getattr(self.coordinator, "extract_outline_chapters", None)
            if not callable(extract_method):
                extract_method = getattr(self.coordinator, "_extract_chapters", None)
            if callable(extract_method):
                try:
                    chapters = extract_method(outline_data) or []
                except Exception as exc:
                    logger.warning(f"[{self.name}] 提取大纲章节失败，回退为空列表: {exc}")
                    chapters = []
        timestamp = datetime.now().isoformat()
        rows: List[Dict[str, Any]] = []
        for index, chapter in enumerate(chapters, start=1):
            summary = ""
            title = f"第{index}章"
            if isinstance(chapter, dict):
                title = str(chapter.get("title") or title).strip() or title
                summary = str(
                    chapter.get("summary")
                    or chapter.get("outline")
                    or chapter.get("description")
                    or chapter.get("content")
                    or ""
                ).strip()
            elif chapter is not None:
                summary = str(chapter).strip()

            rows.append({
                "chapter_number": index,
                "title": title,
                "summary": summary,
                "content": "",
                "created_at": timestamp,
                "updated_at": timestamp,
            })
        return rows

    def _persist_outline_rows(self, outline_rows: List[Dict[str, Any]]) -> Dict[str, str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_path = pm.get_project_data_path("outline")
        existed_before = outline_path.exists()
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy("outline", outline_rows)
        except Exception as e:
            logger.warning(f"[Router] Library outline write failed: {e}")
        pm.save_project_data("outline", outline_rows)
        return {
            "outline_path": str(outline_path),
            "outline_status": "updated" if existed_before else "created",
        }

    @staticmethod
    def _persist_characters_project_data(characters: List[Dict[str, Any]]) -> Dict[str, str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        characters_path = pm.get_project_data_path("characters")
        existed_before = characters_path.exists()
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy("characters", characters)
        except Exception as e:
            logger.warning(f"[Router] Library characters write failed: {e}")
        pm.save_project_data("characters", characters)
        return {
            "characters_path": str(characters_path),
            "characters_status": "updated" if existed_before else "created",
        }

    @staticmethod
    def _persist_named_project_rows(data_type: str, rows: List[Dict[str, Any]]) -> Dict[str, str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        data_path = pm.get_project_data_path(data_type)
        existed_before = data_path.exists()
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy(data_type, rows)
        except Exception as e:
            logger.warning(f"[Router] Library {data_type} write failed: {e}")
        pm.save_project_data(data_type, rows)
        return {
            "path": str(data_path),
            "status": "updated" if existed_before else "created",
        }

    @staticmethod
    def _merge_file_records(target: List[Dict[str, str]], incoming: List[Dict[str, str]]) -> None:
        existing_paths = {str(item.get("path") or "").strip() for item in target if isinstance(item, dict)}
        for item in incoming:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path and path not in existing_paths:
                target.append(item)
                existing_paths.add(path)

    @classmethod
    def _append_file_record_by_status(
        cls,
        *,
        file_record: Optional[Dict[str, str]],
        created_files: List[Dict[str, str]],
        updated_files: List[Dict[str, str]],
        reused_files: List[Dict[str, str]],
    ) -> None:
        if not isinstance(file_record, dict):
            return
        status = str(file_record.get("status") or "").strip().lower()
        if status == "created":
            cls._merge_file_records(created_files, [file_record])
        elif status == "reused":
            cls._merge_file_records(reused_files, [file_record])
        else:
            cls._merge_file_records(updated_files, [file_record])

    @staticmethod
    def _build_eventline_rows_from_outline(outline_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(outline_rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or f"第{index}章").strip() or f"第{index}章"
            summary = str(row.get("summary") or row.get("content") or "").strip()
            if not summary:
                continue
            rows.append({
                "name": f"{title} 事件线",
                "description": summary,
                "chapter_number": index,
                "kind": "chapter_event",
            })
        return rows

    @staticmethod
    def _build_detail_rows_from_outline(outline_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(outline_rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or f"第{index}章").strip() or f"第{index}章"
            summary = str(row.get("summary") or row.get("content") or "").strip()
            rows.append({
                "name": title,
                "description": summary or f"{title} 细纲待补充",
                "chapter_number": index,
                "scene_goal": summary[:120] if summary else "待补充",
                "conflict": "待补充",
                "emotion": "待补充",
                "foreshadowing": "待补充",
            })
        return rows

    @staticmethod
    def _build_chapter_setting_rows_from_outline(outline_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(outline_rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or f"第{index}章").strip() or f"第{index}章"
            summary = str(row.get("summary") or row.get("content") or "").strip()
            rows.append({
                "name": title,
                "description": summary or f"{title} 章纲待补充",
                "chapter_number": index,
                "writing_goal": summary[:120] if summary else "待补充",
                "characters": "",
                "location": "",
                "hook": "",
            })
        return rows

    def _build_project_data_generation_requirements(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        outline_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        world_summary = ""
        if pm.current_project_id:
            try:
                world_summary = self._summarize_worldbuilding_payload(pm.load_project_data("worldbuilding"))
            except Exception:
                world_summary = ""
        return {
            "user_request": message,
            "recent_discussion": self._summarize_recent_discussion(context),
            "world_summary": world_summary,
            "outline_rows": outline_rows,
        }

    @staticmethod
    def _safe_filename_fragment(value: str, fallback: str) -> str:
        fragment = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "").strip())
        fragment = re.sub(r"\s+", "_", fragment)
        fragment = fragment.strip("._")
        return (fragment[:48] or fallback)

    def _find_existing_chapter_file(self, chapter_number: int) -> Optional[str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        chapters_dir = pm.get_project_data_path("chapters")
        if not chapters_dir.exists():
            return None

        preferred_patterns = [
            f"{chapter_number:03d}_*.md",
            f"第{chapter_number}章-*.md",
        ]
        for pattern in preferred_patterns:
            matches = sorted(chapters_dir.glob(pattern))
            if matches:
                return str(matches[0])

        for file_path in sorted(chapters_dir.glob("*.md")):
            name = file_path.name
            if re.search(rf"(^|_)0*{chapter_number}(?:_|\.|章)", name) or f"第{chapter_number}章" in name:
                return str(file_path)
        return None

    def _load_existing_chapter_result(
        self,
        chapter_number: int,
        row: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        chapter_path = self._find_existing_chapter_file(chapter_number)
        chapter_content = str(row.get("content") or "").strip()
        if not chapter_content and chapter_path:
            try:
                chapter_content = Path(chapter_path).read_text(encoding="utf-8").strip()
            except Exception:
                chapter_content = ""
        if not chapter_content:
            return None
        chapter_title = str(row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        return {
            "number": chapter_number,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "title": chapter_title,
            "content": chapter_content,
        }

    @staticmethod
    def _find_next_incomplete_chapter(outline_rows: List[Dict[str, Any]], start_at: int = 1) -> int:
        if not isinstance(outline_rows, list):
            return 0
        start_index = max(1, int(start_at or 1))
        for index, row in enumerate(outline_rows, start=1):
            if index < start_index or not isinstance(row, dict):
                continue
            content = str(row.get("content") or "").strip()
            if not content:
                return index
        return 0

    async def _persist_chapter_result(self, chapter_result: Dict[str, Any], outline_rows: List[Dict[str, Any]]) -> Dict[str, str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_path = pm.get_project_data_path("outline")
        outline_existed_before = outline_path.exists()
        chapter_number = self._normalize_positive_int(
            chapter_result.get("chapter_number", chapter_result.get("number")),
            1,
        )
        chapter_title = str(
            chapter_result.get("chapter_title")
            or chapter_result.get("title")
            or f"第{chapter_number}章"
        ).strip() or f"第{chapter_number}章"
        chapter_content = str(chapter_result.get("content") or "").strip()
        timestamp = datetime.now().isoformat()

        while len(outline_rows) < chapter_number:
            placeholder_num = len(outline_rows) + 1
            outline_rows.append({
                "chapter_number": placeholder_num,
                "title": f"第{placeholder_num}章",
                "summary": "",
                "content": "",
                "created_at": timestamp,
                "updated_at": timestamp,
            })

        row = outline_rows[chapter_number - 1]
        row["chapter_number"] = chapter_number
        row["title"] = chapter_title
        row["content"] = chapter_content
        row["updated_at"] = timestamp

        pm.save_project_data("outline", outline_rows)

        chapters_dir = pm.get_project_data_path("chapters")
        chapters_dir.mkdir(parents=True, exist_ok=True)
        suggested_filename = str(chapter_result.get("suggested_filename") or "").strip()
        if suggested_filename:
            safe_filename = re.sub(r'[\\/:*?"<>|]+', "_", suggested_filename).strip()
            if not safe_filename.lower().endswith(".md"):
                safe_filename = f"{safe_filename}.md"
            chapter_file = chapters_dir / safe_filename
        else:
            safe_title = self._safe_filename_fragment(chapter_title, f"chapter_{chapter_number}")
            chapter_file = chapters_dir / f"{chapter_number:03d}_{safe_title}.md"

        existing_file_path = self._find_existing_chapter_file(chapter_number)
        if existing_file_path and Path(existing_file_path).resolve() != chapter_file.resolve():
            try:
                Path(existing_file_path).unlink()
            except Exception:
                logger.debug(f"[{self.name}] 删除旧章节文件失败: {existing_file_path}")

        chapter_existed_before = chapter_file.exists()
        old_content = chapter_file.read_text(encoding="utf-8") if chapter_file.exists() else None
        atomic_write_text(chapter_file, chapter_content, old_content=old_content)

        # 自动生成章节摘要
        try:
            from novel_agent.chapter_summary_service import (
                get_auto_summary_enabled,
                generate_chapter_summary,
                save_chapter_summary_to_library,
                index_chapter_summary_vector,
            )
            if get_auto_summary_enabled(pm.current_project_id):
                summary = await generate_chapter_summary(
                    chapter_number=chapter_number,
                    title=chapter_title,
                    content=chapter_content,
                )
                save_chapter_summary_to_library(chapter_number, summary, project_dir=pm.get_project_data_path("outline").parent)
                try:
                    await index_chapter_summary_vector(pm.get_project_data_path("outline").parent, summary)
                except Exception as vector_exc:
                    logger.warning(f"[RouterAgent] chapter summary vector index failed: {vector_exc}")
        except Exception as e:
            logger.warning(f"[RouterAgent] Auto chapter summary failed: {e}")

        return {
            "outline_path": str(outline_path),
            "outline_status": "updated" if outline_existed_before else "created",
            "chapter_path": str(chapter_file),
            "chapter_status": "updated" if chapter_existed_before else "created",
        }

    def _ensure_project_metadata(
        self,
        requirements: Dict[str, Any],
        outline_rows: List[Dict[str, Any]],
        outline_data: Dict[str, Any],
    ) -> str:
        from ..project_manager import get_project_manager
        from ..workflow.coordinator import NovelProject

        pm = get_project_manager()
        current_project = pm.get_current_project()
        now = datetime.now().isoformat()
        project_title = str(outline_data.get("title") or (current_project.name if current_project else "") or "未命名项目").strip() or "未命名项目"
        project_id = pm.current_project_id or (current_project.id if current_project else "default")
        created_at = current_project.created_at if current_project else now
        updated_at = current_project.updated_at if current_project else now

        self.coordinator.project = NovelProject(
            id=project_id,
            title=project_title,
            novel_type=requirements["novel_type"],
            status="writing",
            created_at=created_at,
            updated_at=updated_at,
            total_chapters=len(outline_rows),
            completed_chapters=0,
            word_count=0,
        )
        return project_title

    def _save_compiled_novel(self, project_title: str, chapters: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
        if not chapters or not self.coordinator:
            return None
        safe_title = self._safe_filename_fragment(project_title, "novel")
        novel_path = self.coordinator.project_dir / f"{safe_title}.txt"
        existed_before = novel_path.exists()
        save_method = getattr(self.coordinator, "save_compiled_novel", None)
        if not callable(save_method):
            save_method = getattr(self.coordinator, "_save_novel", None)
        if not callable(save_method):
            logger.warning(f"[{self.name}] 协调器缺少合集保存接口，跳过合集保存")
            return None
        save_method(novel_path, chapters)
        return {
            "path": str(novel_path),
            "status": "updated" if existed_before else "created",
        }

    @staticmethod
    def _build_file_record(path: str, kind: str, label: str, status: str = "created") -> Dict[str, str]:
        return {
            "path": str(path or "").strip(),
            "kind": kind,
            "label": label,
            "status": status or "created",
        }

    @staticmethod
    def _persist_worldbuilding_project_data(payload: Any) -> None:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        if not pm.current_project_id:
            return

        world_payload: Dict[str, Any] = {}
        if isinstance(payload, dict) and isinstance(payload.get("world"), dict):
            world_payload = dict(payload)
        elif isinstance(payload, dict):
            world_payload = {"world": dict(payload)}

        if not isinstance(world_payload.get("world"), dict) or not world_payload.get("world"):
            return

        existing_payload = pm.load_project_data("worldbuilding")
        merged_payload: Dict[str, Any] = dict(existing_payload) if isinstance(existing_payload, dict) else {}
        merged_payload.update(world_payload)
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy("worldbuilding", merged_payload)
        except Exception as e:
            logger.warning(f"[Router] Library worldbuilding write failed: {e}")
        pm.save_project_data("worldbuilding", merged_payload)

    @staticmethod
    def _summarize_recent_discussion(context: Optional[Dict[str, Any]], max_turns: int = 8) -> str:
        history = (context or {}).get("conversation_history") if isinstance(context, dict) else None
        if not isinstance(history, list):
            return ""
        lines: List[str] = []
        for item in history[-max_turns:]:
            if not isinstance(item, dict):
                continue
            role = "用户" if str(item.get("role") or "").strip() == "user" else "助手"
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"{role}：{content[:220]}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_worldbuilding_payload(payload: Any) -> str:
        if isinstance(payload, dict):
            world = payload.get("world", payload)
            if isinstance(world, dict):
                parts = []
                name = str(world.get("name") or world.get("world_name") or "").strip()
                world_type = str(world.get("world_type") or "").strip()
                if name:
                    parts.append(f"世界名：{name}")
                if world_type:
                    parts.append(f"类型：{world_type}")
                rules = world.get("rules") if isinstance(world.get("rules"), list) else []
                if rules:
                    parts.append("规则：" + "；".join(str(rule).strip() for rule in rules[:3] if str(rule).strip()))
                factions = world.get("factions") if isinstance(world.get("factions"), list) else []
                if factions:
                    faction_parts = []
                    for faction in factions[:2]:
                        if not isinstance(faction, dict):
                            continue
                        faction_name = str(faction.get("name") or "").strip()
                        faction_desc = str(faction.get("description") or "").strip()
                        if faction_name:
                            faction_parts.append(f"{faction_name}：{faction_desc}" if faction_desc else faction_name)
                    if faction_parts:
                        parts.append("势力：" + "；".join(faction_parts))
                return "\n".join(parts)
        if isinstance(payload, list):
            rows = []
            for item in payload[:3]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                desc = str(item.get("description") or "").strip()
                if name or desc:
                    rows.append(f"{name}：{desc}".strip("："))
            return "\n".join(rows)
        return ""

    @staticmethod
    def _summarize_character_rows(rows: List[Dict[str, Any]], limit: int = 4) -> str:
        lines: List[str] = []
        for item in rows[:limit]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "").strip()
            desc = str(item.get("description") or "").strip()
            if name:
                parts = [part for part in [role, desc[:60] if desc else ""] if part]
                lines.append(f"{name}" + (f"：{'｜'.join(parts)}" if parts else ""))
        return "\n".join(lines)

    def _build_character_requirements(self, message: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        collected_info = dict((context or {}).get("collected_info") or {})
        protagonist = str(collected_info.get("protagonist") or "").strip()
        theme = str(collected_info.get("theme") or "").strip()
        plot_idea = str(collected_info.get("plot_idea") or "").strip()
        novel_type = str(collected_info.get("novel_type") or "").strip() or "未分类"

        cleaned_prompt = self._clean_character_request_message(message)
        character_role = self._detect_character_role(message)
        character_name = ""
        name_match = re.search(r"(?:叫|名叫|名字是|姓名是)\s*([A-Za-z0-9\u4e00-\u9fa5·]{2,24})", message)
        if name_match:
            character_name = name_match.group(1).strip()

        if not protagonist:
            protagonist = cleaned_prompt

        if not plot_idea and cleaned_prompt and cleaned_prompt != protagonist:
            plot_idea = cleaned_prompt

        from ..project_manager import get_project_manager
        pm = get_project_manager()
        world_summary = ""
        existing_characters_summary = ""
        if pm.current_project_id:
            try:
                world_summary = self._summarize_worldbuilding_payload(pm.load_project_data("worldbuilding"))
            except Exception:
                world_summary = ""
            try:
                from ..context.character_manager import CharacterManager
                manager = CharacterManager(pm.get_project_data_path("characters").parent)
                existing_characters_summary = self._summarize_character_rows(manager.export_for_llm())
            except Exception:
                existing_characters_summary = ""

        return {
            "user_request": message,
            "novel_type": novel_type,
            "theme": theme,
            "plot_idea": plot_idea,
            "protagonist": protagonist,
            "character_prompt": cleaned_prompt,
            "character_request": cleaned_prompt or message,
            "character_role": character_role,
            "character_name": character_name,
            "recent_discussion": self._summarize_recent_discussion(context),
            "world_summary": world_summary,
            "existing_characters_summary": existing_characters_summary,
            "request_mode": str((context or {}).get("character_request_mode") or "draft").strip() or "draft",
            "pending_character_draft": collected_info.get("pending_character_draft"),
            "requested_knowledge_category": dict((context or {}).get("requested_knowledge_category") or {}),
            "requires_manual_category_selection": bool((context or {}).get("requires_manual_category_selection")),
            "chat_auto_save_enabled": bool((context or {}).get("chat_auto_save_enabled")),
        }

    @staticmethod
    def _format_character_draft_response(characters: List[Dict[str, Any]], *, saved: bool) -> str:
        lines = [
            "已生成角色卡草稿。" if not saved else "角色卡已生成并写入资料库。",
        ]
        for item in characters[:2]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "未命名角色").strip()
            role = str(item.get("role") or "角色").strip()
            identity = str(item.get("identity") or item.get("occupation") or "").strip()
            description = str(item.get("description") or "").strip()
            goals = item.get("goals") if isinstance(item.get("goals"), list) else []
            lines.append(f"\n【{name}】")
            lines.append(f"- 定位：{role}")
            if identity:
                lines.append(f"- 身份：{identity}")
            if description:
                lines.append(f"- 简介：{description}")
            if goals:
                lines.append(f"- 目标：{'、'.join(str(goal).strip() for goal in goals[:2] if str(goal).strip())}")
        if not saved:
            lines.append("\n如需写入资料库，请回复“把这个角色卡保存到资料库”。")
        return "\n".join(lines)

    @staticmethod
    def _extract_polish_request_content(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return ""
        patterns = [
            r"^(?:请|帮我|麻烦|给我|给)?(?:直接|现在)?(?:润色|优化|修改|改进|完善)(?:这段|下面这段|以下这段|以下内容|这篇|这章|这段文字|这段正文)?[\s：:，,]*",
            r"^(?:请|帮我|麻烦|给我|给)?(?:把)?(?:这段|下面这段|以下这段|以下内容|这篇|这章|这段文字|这段正文)(?:进行)?(?:润色|优化|修改|改进|完善)[\s：:，,]*",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, count=1)
        cleaned = cleaned.strip("：:，, \n\t")
        return cleaned if len(cleaned) >= 12 else ""

    async def _execute_polish_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        polisher = self._get_polisher()
        if polisher is None:
            return {
                "agent_name": "Polisher",
                "action": "polish",
                "response": "润色器当前不可用。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        content = self._extract_polish_request_content(message)
        if not content:
            return {
                "agent_name": "Polisher",
                "action": "polish",
                "response": "好的，请把需要润色的正文直接贴给我，我会立即交给润色助手处理。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        await self._emit_progress(context, {
            "current_agent": "Polisher",
            "stage": "polishing",
            "content": "正在调用润色助手处理文本",
        })
        result = await polisher.execute({
            "content": content,
            "feedback": "",
            "style": "网文风格",
        })
        polished = str((result or {}).get("content") or "").strip()
        if not result.get("success") or not polished:
            return {
                "agent_name": "Polisher",
                "action": "polish",
                "response": "润色助手执行失败，请稍后重试。",
                "error": str((result or {}).get("error") or "polish_failed"),
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        return {
            "agent_name": "Polisher",
            "action": "polish",
            "response": polished,
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "collected_info": {},
        }

    async def _execute_continuous_write_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        chapter_num: int = 0,
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        writer = self._get_continuous_writer()
        if writer is None:
            return {
                "agent_name": "ContinuousWriter",
                "action": "continue",
                "response": "续写助手当前不可用。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        session_id = str((context or {}).get("session_id") or "copilot").strip() or "copilot"
        writer.set_session_id(session_id, project_id)
        if getattr(writer, "_session_state", None) is None:
            try:
                writer._session_state = writer._load_or_create_session()
            except Exception:
                writer._session_state = None

        await self._emit_progress(context, {
            "current_agent": "ContinuousWriter",
            "stage": "writing",
            "content": f"正在调用续写助手{'续写第' + str(chapter_num) + '章' if chapter_num else '生成下一章'}",
        })

        execute_params = {
            "action": "continue",
            "content": message,
        }
        result = await writer.execute(execute_params)
        if result.get("success"):
            chapter = result.get("chapter") if isinstance(result.get("chapter"), dict) else {}
            chapter_number = chapter.get("chapter_number") or chapter.get("number") or chapter_num or 0
            content = str(chapter.get("content") or "").strip()
            return {
                "agent_name": "ContinuousWriter",
                "action": "continue",
                "response": content or f"续写助手已完成第{chapter_number}章。",
                "is_complete": True,
                "run_id": self._get_run_id(context),
                "focus_chapter": int(chapter_number or 0),
                "params": {"chapter_number": int(chapter_number or 0)},
                "collected_info": {},
            }

        error = str(result.get("error") or "").strip()
        friendly = "请先开始一个新故事" if "请先开始一个新故事" in error else ""
        return {
            "agent_name": "ContinuousWriter",
            "action": "continue",
            "response": friendly or "续写助手暂时无法继续当前故事，请先确认已有故事上下文或重新开始。",
            "error": error or "continue_failed",
            "is_complete": False,
            "run_id": self._get_run_id(context),
        }

    async def _execute_character_creation_pipeline(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from ..context.character_manager import CharacterManager
        from ..project_manager import get_project_manager
        from .character_builder import CharacterBuilderAgent

        pm = get_project_manager()
        if not pm.current_project_id:
            return {
                "agent_name": "CharacterBuilder",
                "action": "create_character",
                "error": "当前没有活动项目，无法保存角色档案。",
                "response": "当前没有活动项目，无法保存角色档案。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        project_dir = pm.get_project_data_path("characters").parent
        requirements = self._build_character_requirements(message, context)
        request_mode = str(requirements.get("request_mode") or "draft").strip() or "draft"
        pending_draft = requirements.get("pending_character_draft")
        builder = getattr(self.coordinator, "character_builder", None) if self.coordinator else None
        if builder is None:
            builder = CharacterBuilderAgent()

        await self._emit_progress(context, {
            "current_agent": "CharacterBuilder",
            "stage": "character_building",
            "content": "正在解析角色需求并创建角色档案",
        })

        built_characters: List[Dict[str, Any]] = []
        result: Dict[str, Any]
        if request_mode in {"save", "manual_category"} and isinstance(pending_draft, list) and pending_draft:
            result = {
                "success": True,
                "agent": "CharacterBuilder",
                "characters": pending_draft,
                "confidence": 1.0,
                "missing_info": [],
            }
            built_characters = [dict(item) for item in pending_draft if isinstance(item, dict)]
        else:
            result = await builder.execute(requirements, context={"project_dir": str(project_dir)})
            built_characters = result.get("characters", []) if isinstance(result, dict) else []
            if not isinstance(built_characters, list):
                built_characters = []

        if not result.get("success") or not built_characters:
            response_message = str(result.get("response_message") or "").strip()
            return {
                "agent_name": "CharacterBuilder",
                "action": "create_character",
                "error": response_message or "角色构建结果为空，未能创建角色档案。",
                "response": response_message or "角色构建结果为空，未能创建角色档案。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "characters": built_characters,
                "missing_info": result.get("missing_info", []) if isinstance(result, dict) else [],
            }

        if request_mode == "manual_category":
            requested_category = requirements.get("requested_knowledge_category") or {}
            category_name = str(requested_category.get("name") or requested_category.get("key") or "自定义资料库").strip() or "自定义资料库"
            draft_response = self._format_character_draft_response(built_characters, saved=False)
            draft_response = (
                f"{draft_response}\n\n"
                f"检测到目标分类「{category_name}」不是内置资料库，系统不会自动写入该分类。"
                "请先手动选择分类，再执行保存。"
            )
            return {
                "agent_name": "CharacterBuilder",
                "action": "manual_category_selection_required",
                "response": draft_response,
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "output_dir": str(project_dir),
                "focus_module": "characters",
                "requires_confirmation": True,
                "requested_knowledge_category": requested_category,
                "characters": built_characters,
                "collected_info": {
                    "protagonist": str(built_characters[0].get("name") or requirements.get("protagonist") or "").strip(),
                    "pending_character_draft": built_characters,
                },
            }

        if request_mode != "save":
            draft_response = self._format_character_draft_response(built_characters, saved=False)
            return {
                "agent_name": "CharacterBuilder",
                "action": "draft_character_card",
                "response": draft_response,
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "output_dir": str(project_dir),
                "focus_module": "characters",
                "characters": built_characters,
                "collected_info": {
                    "protagonist": str(built_characters[0].get("name") or requirements.get("protagonist") or "").strip(),
                    "pending_character_draft": built_characters,
                },
            }

        manager = CharacterManager(project_dir)
        existing_names = {char.name for char in manager.get_all_characters()}
        merged_by_name = {item.get("name"): item for item in manager.export_for_llm() if isinstance(item, dict) and item.get("name")}
        saved_names: List[str] = []

        for raw_char in built_characters:
            if not isinstance(raw_char, dict):
                continue
            name = str(raw_char.get("name") or "").strip()
            if not name:
                continue
            merged_by_name[name] = dict(raw_char)
            saved_names.append(name)

        normalized_characters = list(merged_by_name.values())
        persist_result = self._persist_characters_project_data(normalized_characters)
        saved_count = len(saved_names)
        updated_existing = [name for name in saved_names if name in existing_names]
        created_new = [name for name in saved_names if name not in existing_names]
        status = str(persist_result.get("characters_status") or "updated")

        await self._emit_progress(context, {
            "current_agent": "CharacterBuilder",
            "stage": "character_building",
            "content": f"角色档案已保存到资料库，共处理 {saved_count} 个角色",
        })

        response_lines = [self._format_character_draft_response([normalized_characters[0]] if normalized_characters else [], saved=True)]
        response_lines.append(f"\n已将 {saved_count} 个角色档案写入资料库。")
        if created_new:
            response_lines.append(f"新建角色：{', '.join(created_new)}")
        if updated_existing:
            response_lines.append(f"更新角色：{', '.join(updated_existing)}")

        return {
            "agent_name": "CharacterBuilder",
            "action": "create_character",
            "response": "\n".join(response_lines),
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "output_dir": str(project_dir),
            "focus_module": "characters",
            "created_files": [
                self._build_file_record(
                    str(persist_result.get("characters_path") or ""),
                    "characters",
                    "角色档案",
                    status=status,
                )
            ] if status == "created" else [],
            "updated_files": [
                self._build_file_record(
                    str(persist_result.get("characters_path") or ""),
                    "characters",
                    "角色档案",
                    status=status,
                )
            ] if status != "created" else [],
            "characters": normalized_characters,
            "collected_info": {
                "protagonist": str(normalized_characters[0].get("name") or requirements.get("protagonist") or "").strip() if normalized_characters else (requirements.get("protagonist") or ""),
                "pending_character_draft": [],
            },
        }

    @staticmethod
    def _get_run_id(context: Optional[Dict[str, Any]]) -> str:
        return str((context or {}).get("run_id") or "").strip()

    async def _emit_progress(self, context: Optional[Dict[str, Any]], message: Any) -> None:
        if not isinstance(context, dict):
            return
        callback = context.get("progress_callback")
        if not callback:
            return
        payload = message
        if isinstance(message, str):
            text = str(message or "").strip()
            if not text:
                return
            payload = {"content": f"{text}\n\n"}
        elif isinstance(message, dict):
            next_payload = dict(message)
            content = str(next_payload.get("content") or "").strip()
            if content:
                next_payload["content"] = f"{content}\n\n"
            payload = next_payload
        else:
            return
        try:
            result = callback(payload)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.debug(f"[{self.name}] progress callback failed: {exc}")

    async def _check_coordinator_pause_cancel(self) -> bool:
        if not self.coordinator:
            return False
        public_method = getattr(self.coordinator, "check_pause_cancel", None)
        if callable(public_method):
            result = public_method()
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        private_method = getattr(self.coordinator, "_check_pause_cancel", None)
        if callable(private_method):
            result = private_method()
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        return False

    async def _ensure_world_payload(
        self,
        requirements: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        world_path = self.coordinator.project_dir / "worldbuilding.json"
        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        reused_files: List[Dict[str, str]] = []
        world_data: Dict[str, Any] = {}
        if world_path.exists():
            try:
                payload = json.loads(world_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    candidate = payload.get("world", payload)
                    if isinstance(candidate, dict) and candidate:
                        world_data = candidate
                        self._persist_worldbuilding_project_data(payload)
            except Exception:
                world_data = {}

        if world_data:
            existing_world_file = self._build_file_record(str(world_path), "worldbuilding", "世界观", "reused")
            reused_files.append(existing_world_file)
            await self._emit_progress(context, {
                "content": "### 世界观阶段\n复用已有世界观设定",
                "current_agent": "Worldbuilder",
                "stage": "worldbuilding",
                "status": "running",
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
            return world_data, created_files, updated_files, reused_files

        await self._emit_progress(context, {
            "content": "### 世界观阶段\n正在生成世界观设定...",
            "current_agent": "Worldbuilder",
            "stage": "worldbuilding",
            "status": "running",
            "output_dir": str(self.coordinator.project_dir),
        })
        existed_before = world_path.exists()
        world_result = await self.coordinator.generate_world(
            novel_type=requirements["novel_type"],
            theme=requirements["theme"],
            requirements=requirements["requirements"],
        )
        world_data = world_result.get("world", {}) if isinstance(world_result, dict) else {}
        self._persist_worldbuilding_project_data({"world": world_data} if isinstance(world_data, dict) else {})
        world_file = self._build_file_record(
            str(world_path),
            "worldbuilding",
            "世界观",
            "updated" if existed_before else "created",
        )
        if world_file["status"] == "created":
            created_files.append(world_file)
        else:
            updated_files.append(world_file)
        await self._emit_progress(context, {
            "content": "### 世界观阶段完成\n世界观已生成并同步到资料库",
            "current_agent": "Worldbuilder",
            "stage": "worldbuilding",
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })
        return world_data, created_files, updated_files, reused_files

    async def _execute_worldbuild_pipeline(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        # 立即通知前端：正在转交给世界观构建师
        await self._emit_progress(context, {
            "content": "正在转交给世界观构建师...",
            "current_agent": "Worldbuilder",
            "stage": "worldbuilding",
            "status": "running",
        })
        requirements = self._build_creation_requirements(context, message)
        world_data, created_files, updated_files, reused_files = await self._ensure_world_payload(requirements, context)
        response = (
            "已切换到世界观构建执行链，并完成世界观生成。\n\n"
            "世界观已同步到资料库"
        )
        return {
            "agent_name": "Worldbuilder",
            "action": "worldbuild",
            "response": response,
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": "world",
            "focus_chapter": 0,
            "params": {
                "world": world_data,
            },
        }

    async def _execute_outline_pipeline(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        # 立即通知前端：正在转交给大纲规划师
        await self._emit_progress(context, {
            "content": "正在转交给大纲规划师...",
            "current_agent": "Outliner",
            "stage": "outlining",
            "status": "running",
        })
        requirements = self._build_creation_requirements(context, message)
        world_data, created_files, updated_files, reused_files = await self._ensure_world_payload(requirements, context)
        await self._emit_progress(context, {
            "content": "### 大纲阶段\n正在生成章节大纲...",
            "current_agent": "Outliner",
            "stage": "outlining",
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })
        outline_result = await self.coordinator.generate_outline(
            world=world_data if isinstance(world_data, dict) else {},
            protagonist=requirements["protagonist"],
            plot_idea=requirements["plot_idea"],
            volume_count=requirements["volume_count"],
            chapters_per_volume=requirements["chapters_per_volume"],
        )
        outline_data = outline_result.get("outline", {}) if isinstance(outline_result, dict) else {}
        outline_rows = self._outline_to_project_rows(outline_data if isinstance(outline_data, dict) else {})
        outline_persist = self._persist_outline_rows(outline_rows)
        outline_path = str(outline_persist.get("outline_path") or "")
        outline_file = self._build_file_record(
            outline_path,
            "outline",
            "大纲",
            str(outline_persist.get("outline_status") or "created"),
        )
        self._append_file_record_by_status(
            file_record=outline_file,
            created_files=created_files,
            updated_files=updated_files,
            reused_files=reused_files,
        )
        project_title = self._ensure_project_metadata(
            requirements=requirements,
            outline_rows=outline_rows,
            outline_data=outline_data if isinstance(outline_data, dict) else {},
        )
        await self._emit_progress(context, {
            "content": f"### 大纲阶段完成\n共规划 {len(outline_rows)} 章，大纲已同步到资料库",
            "current_agent": "Outliner",
            "stage": "outlining",
            "status": "completed",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })
        return {
            "agent_name": "Outliner",
            "action": "outline",
            "response": (
                "已切换到大纲规划执行链，并完成大纲生成。\n\n"
                f"项目：`{project_title}`\n"
                f"章节数：{len(outline_rows)}\n"
                "大纲已同步到资料库"
            ),
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": "write",
            "focus_chapter": self._find_next_incomplete_chapter(outline_rows, start_at=1) or 1,
            "params": {
                "outline_path": outline_path,
                "chapter_count": len(outline_rows),
            },
        }

    async def _load_outline_rows_with_auto_generation(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], Optional[Dict[str, Any]]]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        reused_files: List[Dict[str, str]] = []
        outline_rows = pm.load_project_data("outline")
        if isinstance(outline_rows, list) and any(isinstance(row, dict) for row in outline_rows):
            return [row for row in outline_rows if isinstance(row, dict)], created_files, updated_files, reused_files, None

        outline_result = await self._execute_outline_pipeline(message=message, context=context)
        self._merge_file_records(created_files, outline_result.get("created_files") or [])
        self._merge_file_records(updated_files, outline_result.get("updated_files") or [])
        self._merge_file_records(reused_files, outline_result.get("reused_files") or [])
        outline_rows = pm.load_project_data("outline")
        if not isinstance(outline_rows, list):
            outline_rows = []
        outline_rows = [row for row in outline_rows if isinstance(row, dict)]
        return outline_rows, created_files, updated_files, reused_files, outline_result

    async def _execute_project_data_generation_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        data_type: str,
        agent_name: str,
        stage: str,
        label: str,
    ) -> Dict[str, Any]:
        outline_rows, created_files, updated_files, reused_files, outline_result = await self._load_outline_rows_with_auto_generation(
            message=message,
            context=context,
        )
        if not outline_rows:
            return {
                "agent_name": agent_name,
                "action": f"generate_{data_type}",
                "error": f"无法生成{label}，因为当前项目缺少可用大纲。",
                "response": f"无法生成{label}，因为当前项目缺少可用大纲。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
            }

        from .project_data_builders import (
            EventlineBuilderAgent,
            DetailOutlineBuilderAgent,
            ChapterSettingBuilderAgent,
        )

        builder_map = {
            "eventlines": EventlineBuilderAgent,
            "detail_settings": DetailOutlineBuilderAgent,
            "chapter_settings": ChapterSettingBuilderAgent,
        }
        builder_cls = builder_map[data_type]
        builder = builder_cls()
        requirements = self._build_project_data_generation_requirements(
            message=message,
            context=context,
            outline_rows=outline_rows,
        )
        await self._emit_progress(context, {
            "content": f"### {label}阶段\n正在调用{agent_name}生成结构化{label}...",
            "current_agent": agent_name,
            "stage": stage,
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
        })
        builder_result = await builder.execute(requirements, context={"project_dir": str(self.coordinator.project_dir) if self.coordinator else ""})
        rows = builder_result.get("rows", []) if isinstance(builder_result, dict) else []
        if not isinstance(rows, list) or not rows:
            response_message = str((builder_result or {}).get("response_message") or "").strip() if isinstance(builder_result, dict) else ""
            return {
                "agent_name": agent_name,
                "action": f"generate_{data_type}",
                "error": response_message or f"无法生成{label}，因为{agent_name}未返回有效结果。",
                "response": response_message or f"无法生成{label}，因为{agent_name}未返回有效结果。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
            }
        persist_result = self._persist_named_project_rows(data_type, rows)
        file_record = self._build_file_record(
            str(persist_result.get("path") or ""),
            data_type,
            label,
            str(persist_result.get("status") or "created"),
        )
        self._append_file_record_by_status(
            file_record=file_record,
            created_files=created_files,
            updated_files=updated_files,
            reused_files=reused_files,
        )

        await self._emit_progress(context, {
            "content": f"### {label}阶段完成\n已生成 {len(rows)} 条{label}并同步到资料库",
            "current_agent": agent_name,
            "stage": stage,
            "status": "completed",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
        })

        prerequisite_text = ""
        if isinstance(outline_result, dict) and (outline_result.get("created_files") or outline_result.get("updated_files")):
            prerequisite_text = "已自动补齐前置大纲，并"

        return {
            "agent_name": agent_name,
            "action": f"generate_{data_type}",
            "response": f"{prerequisite_text}已完成{label}生成，并写入资料库。",
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
            "focus_module": "world",
            "params": {
                "data_type": data_type,
                "count": len(rows),
            },
        }

    async def _execute_create_novel_pipeline(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        requirements = self._build_creation_requirements(context, message)
        contract_payload = self._persist_creation_contract_payload(
            self._build_creation_contract_payload(
                requirements,
                context,
                user_confirmed=True,
            )
        )
        logger.info(f"[{self.name}] 自动执行创作流程: {requirements['novel_type']}")
        if self._supports_formal_collab_execution() and not bool(requirements.get("resume_existing", False)):
            return await self._execute_create_novel_pipeline_formal(
                message=message,
                context=context,
                requirements=requirements,
                contract_payload=contract_payload,
            )
        await self._emit_progress(context, {
            "content": "## 创作启动\n已进入真实创作执行链。",
            "current_agent": "Coordinator",
            "stage": "starting",
            "status": "running",
            "output_dir": str(self.coordinator.project_dir),
        })
        if await self._check_coordinator_pause_cancel():
                return {
                    "agent_name": "Coordinator",
                    "action": "create_novel",
                    "response": "创作已取消，未继续执行。",
                    "is_complete": False,
                    "run_id": self._get_run_id(context),
                    "created_files": [],
                    "updated_files": [],
                    "reused_files": [],
                    "output_dir": str(self.coordinator.project_dir),
                    "focus_module": "write",
                    "focus_chapter": 1,
                    "error": "cancelled",
                }
        world_data, created_files, updated_files, reused_files = await self._ensure_world_payload(requirements, context)

        outline_rows = pm.load_project_data("outline")
        outline_path = str(pm.get_project_data_path("outline"))
        outline_data: Dict[str, Any] = {}
        if isinstance(outline_rows, list) and outline_rows:
            outline_rows = [row for row in outline_rows if isinstance(row, dict)]
            outline_data = {"chapters": outline_rows}
            outline_file = self._build_file_record(outline_path, "outline", "大纲", "reused")
            self._append_file_record_by_status(
                file_record=outline_file,
                created_files=created_files,
                updated_files=updated_files,
                reused_files=reused_files,
            )
            await self._emit_progress(context, {
                "content": f"### 大纲阶段\n复用已有大纲，共 {len(outline_rows)} 章。",
                "current_agent": "Outliner",
                "stage": "outlining",
                "status": "running",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
        else:
            await self._emit_progress(context, {
                "content": "### 大纲阶段\n正在生成章节大纲...",
                "current_agent": "Outliner",
                "stage": "outlining",
                "status": "running",
                "created_files": created_files,
                "updated_files": updated_files,
                "output_dir": str(self.coordinator.project_dir),
            })
            if await self._check_coordinator_pause_cancel():
                return {
                    "agent_name": "Coordinator",
                    "action": "create_novel",
                    "response": "创作已取消，未继续执行。",
                    "is_complete": False,
                    "run_id": self._get_run_id(context),
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir),
                    "focus_module": "write",
                    "focus_chapter": self._find_next_incomplete_chapter(outline_rows, start_at=1) or 1,
                    "error": "cancelled",
                }
            outline_result = await self.coordinator.generate_outline(
                world=world_data if isinstance(world_data, dict) else {},
                protagonist=requirements["protagonist"],
                plot_idea=requirements["plot_idea"],
                volume_count=requirements["volume_count"],
                chapters_per_volume=requirements["chapters_per_volume"],
            )
            outline_data = outline_result.get("outline", {}) if isinstance(outline_result, dict) else {}
            outline_rows = self._outline_to_project_rows(outline_data if isinstance(outline_data, dict) else {})
            outline_persist = self._persist_outline_rows(outline_rows)
            outline_path = str(outline_persist.get("outline_path") or "")
            outline_file = self._build_file_record(
                outline_path,
                "outline",
                "大纲",
                str(outline_persist.get("outline_status") or "created"),
            )
            self._append_file_record_by_status(
                file_record=outline_file,
                created_files=created_files,
                updated_files=updated_files,
                reused_files=reused_files,
            )
            await self._emit_progress(context, {
                "content": f"### 大纲阶段完成\n共规划 {len(outline_rows)} 章，大纲已同步到资料库",
                "current_agent": "Outliner",
                "stage": "outlining",
                "status": "running",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
        project_title = self._ensure_project_metadata(
            requirements=requirements,
            outline_rows=outline_rows,
            outline_data=outline_data if isinstance(outline_data, dict) else {},
        )

        written_chapters: List[Dict[str, Any]] = []
        chapter_files: List[Dict[str, str]] = []
        last_persisted_paths = {"outline_path": outline_path}
        resumed_chapter_count = 0
        for chapter_index, row in enumerate(outline_rows, start=1):
            if await self._check_coordinator_pause_cancel():
                return {
                    "agent_name": "Coordinator",
                    "action": "create_novel",
                    "response": "创作已取消，可稍后继续，已生成文件会被保留。",
                    "is_complete": False,
                    "run_id": self._get_run_id(context),
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir),
                    "focus_module": "write",
                    "focus_chapter": self._find_next_incomplete_chapter(outline_rows, start_at=chapter_index) or chapter_index,
                    "params": {
                        "persisted_paths": {
                            "outline_path": outline_path,
                            "chapter_paths": [item["path"] for item in chapter_files],
                        },
                    },
                    "error": "cancelled",
                }
            existing_chapter = self._load_existing_chapter_result(chapter_index, row)
            if existing_chapter:
                written_chapters.append(existing_chapter)
                resumed_chapter_count += 1
                chapter_path = self._find_existing_chapter_file(chapter_index) or ""
                if chapter_path:
                    chapter_file = self._build_file_record(
                        chapter_path,
                        "chapter",
                        f"第 {chapter_index} 章",
                        "reused",
                    )
                    chapter_files.append(chapter_file)
                    self._append_file_record_by_status(
                        file_record=chapter_file,
                        created_files=created_files,
                        updated_files=updated_files,
                        reused_files=reused_files,
                    )
                await self._emit_progress(
                    context,
                    {
                        "content": f"### 章节阶段\n跳过已完成的第 {chapter_index} 章，复用现有内容。",
                        "current_agent": "ChapterWriter",
                        "stage": f"chapter_{chapter_index}",
                        "status": "running",
                        "created_files": created_files,
                        "updated_files": updated_files,
                        "reused_files": reused_files,
                        "output_dir": str(self.coordinator.project_dir),
                    },
                )
                continue
            await self._emit_progress(
                context,
                {
                    "content": f"### 章节阶段\n正在创作第 {chapter_index}/{len(outline_rows)} 章：{row.get('title') or f'第{chapter_index}章'}",
                    "current_agent": "ChapterWriter",
                    "stage": f"chapter_{chapter_index}",
                    "status": "running",
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir),
                },
            )
            chapter_outline = {
                "title": row.get("title") or f"第{chapter_index}章",
                "summary": row.get("summary") or requirements["plot_idea"],
            }
            chapter_result = await self._write_chapter_with_coordinator(
                chapter_num=chapter_index,
                chapter_outline=chapter_outline,
                previous_chapters=written_chapters,
            )
            written_chapters.append(chapter_result)
            last_persisted_paths = await self._persist_chapter_result(chapter_result, outline_rows)
            if last_persisted_paths.get("chapter_path"):
                chapter_file = self._build_file_record(
                    str(last_persisted_paths["chapter_path"]),
                    "chapter",
                    f"第 {chapter_index} 章",
                    str(last_persisted_paths.get("chapter_status") or "created"),
                )
                chapter_files.append(chapter_file)
                self._append_file_record_by_status(
                    file_record=chapter_file,
                    created_files=created_files,
                    updated_files=updated_files,
                    reused_files=reused_files,
                )
            await self._emit_progress(
                context,
                {
                    "content": f"第 {chapter_index} 章完成，已同步到章节列表",
                    "current_agent": "ChapterWriter",
                    "stage": f"chapter_{chapter_index}",
                    "status": "running",
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir),
                },
            )

        # 修复：使用去空白字符统计中文字数
        total_words = sum(len(re.sub(r"\s+", "", str(ch.get("content") or ""))) for ch in written_chapters)
        if self.coordinator.project:
            self.coordinator.project.status = "completed"
            self.coordinator.project.completed_chapters = len(written_chapters)
            self.coordinator.project.word_count = total_words
            self.coordinator.project.updated_at = datetime.now().isoformat()

        await self._emit_progress(context, {
            "content": "### 整理输出\n正在生成合集文件...",
            "current_agent": "Coordinator",
            "stage": "packaging",
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })
        compiled_novel = self._save_compiled_novel(project_title, written_chapters)
        compiled_novel_path = str((compiled_novel or {}).get("path") or "")
        if compiled_novel_path:
            compiled_file = self._build_file_record(
                compiled_novel_path,
                "compiled_novel",
                "合集",
                str((compiled_novel or {}).get("status") or "created"),
            )
            self._append_file_record_by_status(
                file_record=compiled_file,
                created_files=created_files,
                updated_files=updated_files,
                reused_files=reused_files,
            )
        persisted_paths = {
            "outline_path": outline_path,
            "chapter_paths": [item["path"] for item in chapter_files],
        }
        if chapter_files:
            persisted_paths["chapter_path"] = chapter_files[0]["path"]
        if compiled_novel_path:
            persisted_paths["compiled_novel_path"] = compiled_novel_path
        await self._emit_progress(
            context,
            {
                "content": f"### 创作完成\n已完成 {len(written_chapters)} 章，总字数约 {total_words} 字。",
                "current_agent": "Coordinator",
                "stage": "completed",
                "status": "completed",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            },
        )

        outline_preview = [row.get("title", f"第{i+1}章") for i, row in enumerate(outline_rows[:5])]
        world_preview = ""
        if isinstance(world_data, dict):
            world_preview = (
                str(world_data.get("world_name") or "")
                or str(world_data.get("name") or "")
                or str(world_data.get("raw_content") or "")
            ).strip()
        response_parts = [
            "已切换到创作执行链，当前不是沟通助手在口头回复，而是已经开始调用创作能力并写入项目内容。",
            "",
            "执行流程：世界观 → 大纲 → 正文创作",
            "",
            "生成结果：",
            "- 世界观已同步到资料库",
            f"- 大纲已生成，共 {len(outline_rows)} 章",
        ]
        if resumed_chapter_count:
            response_parts.extend(["", f"断点续作：已复用 {resumed_chapter_count} 个已完成章节，仅补写缺失内容。"])
        if chapter_files:
            response_parts.append(f"- 已生成 {len(chapter_files)} 章正文，可在左侧章节列表查看")
        if compiled_novel_path:
            response_parts.append("- 已生成合集")
        if world_preview:
            response_parts.extend(["", f"世界观主题：{world_preview}"])
        if outline_preview:
            response_parts.extend(["", "前 5 章规划："] + [f"{idx + 1}. {title}" for idx, title in enumerate(outline_preview)])
        if written_chapters and written_chapters[0].get("content"):
            response_parts.extend([
                "",
                f"已完成章节：{len(written_chapters)} 章，共约 {total_words} 字。",
                "",
                "以下是已经实际生成并落盘的第一章正文：",
                "",
                written_chapters[0]["content"],
            ])

        return {
            "agent_name": "Coordinator",
            "action": "create_novel",
            "response": "\n".join(response_parts),
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": "write",
            "focus_chapter": self._find_next_incomplete_chapter(outline_rows, start_at=1),
            "params": {
                **requirements,
                "persisted_paths": persisted_paths,
                "execution_agents": ["Worldbuilder", "Outliner", "ChapterWriter"],
                "creation_contract": contract_payload,
            },
        }

    async def _write_chapter_with_coordinator(
        self,
        chapter_num: int,
        chapter_outline: Dict[str, Any],
        previous_chapters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not self.coordinator:
            raise RuntimeError("协调器未配置，无法执行章节创作。")

        write_from_context = getattr(self.coordinator, "write_chapter_from_context", None)
        if callable(write_from_context):
            return await write_from_context(
                chapter_number=chapter_num,
                chapter_outline=chapter_outline,
                previous_chapters=previous_chapters or [],
            )

        write_internal = getattr(self.coordinator, "_write_single_chapter_internal", None)
        if callable(write_internal):
            return await write_internal(
                chapter_num=chapter_num,
                chapter_outline=chapter_outline,
                previous_chapters=previous_chapters or [],
            )

        write_single = getattr(self.coordinator, "write_single_chapter", None)
        if callable(write_single):
            outline_summary = str(
                chapter_outline.get("summary")
                or chapter_outline.get("outline")
                or chapter_outline.get("description")
                or chapter_outline.get("content")
                or chapter_outline.get("title")
                or f"第{chapter_num}章"
            ).strip()
            chapter_title = str(chapter_outline.get("title") or f"第{chapter_num}章").strip() or f"第{chapter_num}章"
            return await write_single(
                chapter_number=chapter_num,
                chapter_outline=outline_summary,
                chapter_title=chapter_title,
            )

        raise AttributeError("协调器缺少可用的章节写作接口")

    async def _execute_project_chapter_write(
        self,
        chapter_num: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_rows = pm.load_project_data("outline")
        if not isinstance(outline_rows, list) or chapter_num <= 0 or chapter_num > len(outline_rows):
            return None

        row = outline_rows[chapter_num - 1] if isinstance(outline_rows[chapter_num - 1], dict) else {}
        chapter_title = str(row.get("title") or f"第{chapter_num}章").strip() or f"第{chapter_num}章"
        chapter_outline = str(row.get("summary") or row.get("content") or "").strip()
        if not chapter_outline:
            chapter_outline = chapter_title

        await self._emit_progress(context, {
            "content": f"### 章节阶段\n正在创作第 {chapter_num} 章：{chapter_title}",
            "current_agent": "ChapterWriter",
            "stage": f"chapter_{chapter_num}",
            "status": "running",
            "output_dir": str(self.coordinator.project_dir),
        })
        result = await self._write_chapter_with_coordinator(
            chapter_num=chapter_num,
            chapter_outline={
                "title": chapter_title,
                "summary": chapter_outline,
            },
            previous_chapters=[],
        )
        persisted_paths = await self._persist_chapter_result(result, outline_rows)
        chapter_file = self._build_file_record(
            str(persisted_paths.get("chapter_path") or ""),
            "chapter",
            f"第 {chapter_num} 章",
            str(persisted_paths.get("chapter_status") or "created"),
        )
        outline_file = self._build_file_record(
            str(persisted_paths.get("outline_path") or ""),
            "outline",
            "大纲",
            str(persisted_paths.get("outline_status") or "updated"),
        )
        created_files = [item for item in [chapter_file, outline_file] if item.get("status") == "created"]
        updated_files = [item for item in [chapter_file, outline_file] if item.get("status") != "created"]
        await self._emit_progress(context, {
            "content": f"第 {chapter_num} 章完成，已同步到章节列表",
            "current_agent": "ChapterWriter",
            "stage": f"chapter_{chapter_num}",
            "status": "completed",
            "created_files": created_files,
            "updated_files": updated_files,
            "output_dir": str(self.coordinator.project_dir),
        })
        content = str(result.get("content") or "").strip()
        response = (
            f"已切换到章节写作执行链，并完成第{chapter_num}章创作。\n\n"
            f"第{chapter_num}章已同步到左侧章节列表\n\n"
            f"{content}"
        ).strip()
        return {
            "agent_name": "ChapterWriter",
            "action": "write_chapter",
            "response": response,
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": "write",
            "focus_chapter": self._find_next_incomplete_chapter(outline_rows, start_at=chapter_num + 1),
            "params": {
                "chapter_number": chapter_num,
                "persisted_paths": persisted_paths,
            },
        }
    
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
            if self.coordinator and hasattr(self.coordinator, 'character_manager'):
                self._continuous_writer.set_character_manager(self.coordinator.character_manager)
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


# 模块职责说明：智能路由智能体，负责意图识别、知识库检索、Skill工具调用、任务分发和响应保证
