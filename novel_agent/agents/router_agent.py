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
import math
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from .base_agent import BaseAgent
from ..constants import AGENT_TEMPERATURE, TIMEOUTS
from ..utils.atomic_write import atomic_write_text
from ..content_sanitizer import strip_internal_author_markers
from ..outline_utils import (
    build_outline_overview_row,
    derive_chapter_seed_rows_from_outline,
    enrich_eventlines_with_character_participants,
    extract_outline_chapter_rows,
    extract_eventlines_from_outline,
    merge_eventline_rows,
    normalize_outline_payload,
)
from ..workflow.artifact_review import ReviewResult, review_artifact_basic
from ..workflow.creative_executor import CreativeWorkflowExecutor, TaskExecutionResult
from ..workflow.creative_workflow import CreativeWorkflowRun
from ..workflow.contracts import build_default_creation_contract, build_default_task_graph
from ..workflow.runtime_messages import make_runtime_message
from ..workflow.workflow_context import AgentHandoff, Artifact, WorkflowContext
from ..workflow.workflow_planner import BUILTIN_CATEGORY_DEFINITIONS, WorkflowTask, build_workflow_plan, detect_target_categories

logger = logging.getLogger(__name__)

_GENRE_HINTS: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("古代", "古言", "宫廷", "宅斗", "甜宠", "言情", "爱情", "恋爱", "姐弟恋", "团宠"), "古代言情"),
    (("玄幻", "修仙", "仙侠"), "玄幻"),
    (("都市", "现代"), "都市"),
    (("科幻", "星际", "未来"), "科幻"),
    (("悬疑", "推理"), "悬疑"),
    (("武侠",), "武侠"),
    (("历史",), "历史"),
    (("末世",), "末世"),
)

_THEME_HINTS: Tuple[Tuple[str, str], ...] = (
    ("古言", "古代"),
    ("古代", "古代"),
    ("姐弟恋", "姐弟恋"),
    ("团宠", "团宠"),
    ("甜宠", "甜宠"),
    ("复仇成长", "复仇成长"),
    ("复仇", "复仇"),
    ("成长", "成长"),
    ("权谋", "权谋"),
    ("宅斗", "宅斗"),
    ("宫廷", "宫廷"),
)

_AI_AUTONOMY_REQUIREMENT = "未指定的世界观、角色姓名、人物设定和剧情细节由助手自主创作"


_USER_VISIBLE_AGENT_NAME_REPLACEMENTS = {
    "Worldbuilder那边": "后续世界观设定流程这边",
    "WorldBuilder那边": "后续世界观设定流程这边",
    "WorldbuilderAgent": "世界观构建师",
    "WorldBuilderAgent": "世界观构建师",
    "Worldbuilder": "世界观构建师",
    "WorldBuilder": "世界观构建师",
    "OutlinerAgent": "大纲规划师",
    "Outliner": "大纲规划师",
    "ChapterWriterAgent": "章节写作助手",
    "ChapterWriter": "章节写作助手",
    "CharacterBuilderAgent": "角色构建师",
    "CharacterBuilder": "角色构建师",
    "EventlineBuilder": "事件线构建师",
    "DetailOutlineBuilder": "细纲构建师",
    "ChapterSettingBuilder": "章纲构建师",
    "ContinuousWriter": "续写助手",
    "PolisherAgent": "润色助手",
    "Polisher": "润色助手",
    "EvaluatorAgent": "质量评估师",
    "Evaluator": "质量评估师",
    "CommunicatorAgent": "沟通助手",
    "Communicator": "沟通助手",
    "Coordinator": "创作协调器",
    "Router": "智能路由助手",
    "WebSearch": "网络搜索助手",
    "TrendsSearch": "热点搜索助手",
}


_USER_VISIBLE_WORKFLOW_ERROR_REPLACEMENTS = {
    "missing_chapter_number": "缺少章节号：当前任务没有拿到要写第几章",
    "chapter_not_found": "未找到对应章节：请先生成或检查大纲",
    "missing_outline": "缺少大纲：需要先有章节大纲才能写正文",
    "empty_workflow_plan": "没有可执行的工作流计划",
    "task_failed": "任务执行失败",
    "unsupported_task_type": "当前任务类型还不支持自动执行",
    "max_chapter_tasks_reached": "这一轮连续写章达到上限",
    "max_tasks_reached": "这一轮任务执行达到上限",
    "fallback_triggered": "系统已触发回退处理",
    "review_required": "这一步需要先复核确认",
    "cancelled": "创作已取消",
}

_USER_VISIBLE_WORKFLOW_TASK_REPLACEMENTS = {
    "worldbuilding": "世界观设定",
    "characters": "角色档案",
    "outline": "大纲",
    "items": "道具物品",
    "eventlines": "事件线",
    "detail_settings": "细纲设定",
    "chapter_settings": "章纲设定",
    "chapter_summary": "正文摘要",
    "chapters": "正文章节",
    "write_chapter": "章节正文",
    "build_world": "世界观设定",
    "build_characters": "角色档案",
    "build_outline": "大纲",
    "summary_orchestrate": "阶段总结",
}

_CREATION_DISCUSSION_FIELD_WHITELIST = {
    "novel_type",
    "theme",
    "requirements",
    "protagonist",
    "plot_idea",
    "volume_count",
    "chapters_per_volume",
    "target_word_count",
    "target_words_per_chapter",
    "target_words_per_chapter_source",
    "ai_autonomy_requested",
    "plot_thread_preferences",
    "style",
    "forbidden",
    "constraints",
}

_NON_CREATIVE_ASSISTANT_CONTEXT_PATTERNS = (
    re.compile(r"\b(?:Worldbuilder|Outliner|ChapterWriter|Coordinator|Router|TaskPool|Dispatcher|AgentDispatcher)\b", re.IGNORECASE),
    re.compile(r"\bsub_agent_(?:started|completed)\b|\btask_(?:started|completed|failed|rejected)\b", re.IGNORECASE),
    re.compile(r"正在(?:调度任务|调用|执行)|任务执行失败|回退执行|工作流(?:停止|状态)|已通过审查|待复核|复核确认"),
    re.compile(r"^(?:返回|返回列表|大纲标题|全书大纲内容|分卷规划|故事梗概|保存|取消)$"),
)


def _sanitize_assistant_discussion_context(text: Any) -> str:
    """Keep creative assistant summaries, drop UI/progress/internal workflow chatter."""
    raw = strip_internal_author_markers(text)
    if not raw:
        return ""
    kept_lines: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(pattern.search(line) for pattern in _NON_CREATIVE_ASSISTANT_CONTEXT_PATTERNS):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def _localize_user_visible_agent_names(text: Any) -> str:
    """将用户可见文本中的内部 Agent 代号替换为自然中文显示。"""
    value = str(text or "")
    if not value:
        return ""
    for old, new in _USER_VISIBLE_AGENT_NAME_REPLACEMENTS.items():
        value = value.replace(old, new)
    value = value.replace("后续世界观设定流程这边能", "后续世界观设定会")
    value = value.replace("世界观构建师那边", "后续世界观设定流程这边")
    value = value.replace("大纲规划师那边", "后续大纲规划流程这边")
    value = value.replace("候选 Agent", "候选创作助手")
    value = value.replace("多Agent", "多助手")
    value = value.replace("子Agent", "子助手")
    return value


def _localize_workflow_error(text: Any) -> str:
    value = _localize_user_visible_agent_names(text)
    if not value:
        return ""
    for old, new in sorted(_USER_VISIBLE_WORKFLOW_ERROR_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        value = value.replace(old, new)
    return value


def _get_user_visible_workflow_task_name(task_type: Any, default: str = "当前任务") -> str:
    raw = str(task_type or "").strip()
    if not raw:
        return default
    return _USER_VISIBLE_WORKFLOW_TASK_REPLACEMENTS.get(raw, raw) or default


def _get_user_visible_agent_name(agent_name: Any, default: str = "创作助手") -> str:
    raw = str(agent_name or "").strip()
    if not raw:
        return default
    return _localize_user_visible_agent_names(raw) or default


def _format_plan_deliverable_label(value: Any) -> str:
    """将内部产物路径转换为用户可读的中文名称。"""
    raw = str(value or "").strip()
    if not raw:
        return "计划产物"
    normalized_path = raw.replace("\\", "/").lower()
    normalized = normalized_path.rsplit("/", 1)[-1]
    mapping = {
        "worldbuilding.json": "世界观设定",
        "characters.json": "角色档案",
        "outline.json": "故事大纲",
        "items.json": "道具物品",
        "eventlines.json": "事件线",
        "detail_settings.json": "细纲设定",
        "chapter_settings.json": "章纲设定",
        "chapters/*.md": "正文章节",
        "stage_summaries/*.md": "阶段总结",
    }
    if normalized in mapping:
        return mapping[normalized]
    if normalized_path.startswith("chapters/") or "/chapters/" in normalized_path:
        return "正文章节"
    if normalized_path.startswith("stage_summaries/") or "/stage_summaries/" in normalized_path:
        return "阶段总结"
    return _get_user_visible_workflow_task_name(raw, raw)


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

        # LLM意图分析配置（LLM优先；仅在接口不可用时恢复明确执行命令）
        self._llm_intent_timeout = 15.0       # 当前超时时间（秒）
        self._llm_intent_max_timeout = 60.0    # 最大超时
        self._llm_intent_max_retries = 2        # 最大重试次数
        self._last_intent_error_kind: Optional[str] = None

    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import ROUTER_AGENT_PROMPT
        return ROUTER_AGENT_PROMPT
    
    async def analyze_intent(self, message: str) -> IntentAnalysis:
        """
        分析用户意图（单意图，向后兼容）。

        LLM 优先判断；当 LLM 接口不可用时，只对明确的执行类命令使用本地恢复。
        LLM 支持动态超时重试：首次超时后自动延长重试，最多重试2次（15s -> 30s -> 60s）。
        若全部重试均失败，抛出 RuntimeError 显式报错。
        """
        # 重置超时状态（新请求从头开始）
        self._llm_intent_timeout = 15.0
        self._last_intent_error_kind = None

        llm_analysis = await self._analyze_intent_with_llm(message)
        if llm_analysis is not None:
            return self._normalize_intent_analysis(message, llm_analysis)

        recovered = self._recover_intent_after_llm_unavailable(message)
        if recovered is not None:
            return recovered

        # LLM 彻底失败后，显式报错。
        raise RuntimeError(
            f"[{self.name}] LLM意图分析全部重试失败，无法识别用户意图。请检查LLM配置。"
        )

    async def analyze_intents(self, message: str) -> List[IntentAnalysis]:
        """
        分析用户意图（支持多意图拆分）。

        当用户消息包含多个任务时，返回按依赖顺序排列的意图列表。
        如果只有一个意图，返回长度为1的列表。
        """
        # 重置超时状态
        self._llm_intent_timeout = 15.0
        self._last_intent_error_kind = None

        llm_results = await self._analyze_intents_with_llm(message)
        if llm_results:
            normalized_results = [self._normalize_intent_analysis(message, item) for item in llm_results]
            return self._sort_intents_by_dependency(normalized_results)

        # 回退到单意图分析
        single = await self.analyze_intent(message)
        return [self._normalize_intent_analysis(message, single)]

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

    def _intent_analyses_from_explicit_context(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> List[IntentAnalysis]:
        context = context if isinstance(context, dict) else {}
        if isinstance(context.get("creation_requirements"), dict):
            return [self._build_intent_analysis(message, UserIntent.CREATE_NOVEL, confidence=1.0)]

        explicit_command = context.get("explicit_command")
        if not isinstance(explicit_command, dict):
            return []
        command_name = str(explicit_command.get("name") or "").strip().lower()
        intent_by_command = {
            "create": UserIntent.CREATE_NOVEL,
            "worldbuild": UserIntent.CREATE_NOVEL,
            "outline": UserIntent.CREATE_NOVEL,
            "character": UserIntent.CREATE_CHARACTER,
            "chapter": UserIntent.CONTINUE_WRITE,
            "projectdata": UserIntent.GENERAL_CHAT,
        }
        intent = intent_by_command.get(command_name)
        if not intent:
            return []
        return [self._build_intent_analysis(message, intent, confidence=1.0)]

    def _normalize_intent_analysis(self, message: str, analysis: Any) -> IntentAnalysis:
        """兼容测试桩和旧调用方返回的简化意图对象。"""
        if isinstance(analysis, IntentAnalysis) and isinstance(analysis.primary_intent, UserIntent):
            if not isinstance(analysis.entities, dict):
                analysis.entities = self._extract_entities(message, analysis.primary_intent)
            return analysis

        raw_intent = getattr(analysis, "primary_intent", None)
        intent = raw_intent if isinstance(raw_intent, UserIntent) else self._coerce_user_intent(
            getattr(raw_intent, "value", raw_intent)
        )
        if intent is None:
            intent = UserIntent.GENERAL_CHAT

        fallback_raw = getattr(analysis, "fallback_intent", None)
        fallback_intent = fallback_raw if isinstance(fallback_raw, UserIntent) else self._coerce_user_intent(
            getattr(fallback_raw, "value", fallback_raw)
        )

        try:
            confidence = float(getattr(analysis, "confidence", 0.5) or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5

        normalized = self._build_intent_analysis(
            message,
            intent,
            confidence=confidence,
            fallback_intent=fallback_intent,
        )

        supplied_entities = getattr(analysis, "entities", None)
        if isinstance(supplied_entities, dict):
            normalized.entities.update(supplied_entities)

        for attr in ("requires_knowledge_base", "requires_tool_call", "tool_name", "tool_args"):
            if hasattr(analysis, attr):
                setattr(normalized, attr, getattr(analysis, attr))
        if not isinstance(normalized.tool_args, (dict, type(None))):
            normalized.tool_args = {}
        return normalized

    def _recover_intent_after_llm_unavailable(self, message: str) -> Optional[IntentAnalysis]:
        """LLM 连接失败时，仅恢复强执行语义，避免把讨论误判为写入操作。"""
        if self._last_intent_error_kind != "llm_unavailable":
            return None

        intent = self._detect_local_action_intent(message)
        if intent is None:
            return None

        logger.info(f"[{self.name}] LLM不可用，使用本地执行意图恢复: {intent.value}")
        return self._build_intent_analysis(
            message,
            intent,
            confidence=0.88,
            fallback_intent=UserIntent.GENERAL_CHAT,
        )

    @staticmethod
    def _detect_local_action_intent(message: str) -> Optional[UserIntent]:
        text = str(message or "").strip()
        if not text:
            return None

        soft_enrichment_markers = (
            "丰富一下", "丰富", "细化一下", "继续细化", "细化", "展开一下",
            "扩展一下", "扩展", "拓展一下", "拓展", "根据这个设定",
            "基于这个设定", "在这个设定上", "帮我想想", "帮我想",
            "补充一点", "补充一下", "完善一下",
        )
        hard_execution_markers = (
            "直接生成", "直接创建", "直接写", "开始创作", "开始写", "开始正文",
            "生成", "创建", "新建", "建立", "写入资料库", "保存到资料库",
            "同步到资料库", "加入资料库", "存到资料库", "落库", "入库",
            "执行", "续写", "继续写", "写正文", "生成正文",
        )
        if (
            any(marker in text for marker in soft_enrichment_markers)
            and not any(marker in text for marker in hard_execution_markers)
        ):
            return None

        discussion_markers = (
            "先讨论", "先聊", "聊聊", "建议", "怎么", "如何", "要不要", "是否",
            "能不能", "可不可以", "可以吗", "行不行", "合适吗", "帮我看看",
        )
        if any(marker in text for marker in discussion_markers):
            return None

        action_markers = (
            "生成", "创建", "新建", "建立", "构建", "设计", "梳理", "整理",
            "补全", "补出来", "补一下", "完善", "写", "做", "加入资料库",
            "保存到资料库", "存到资料库", "写入资料库", "同步到资料库",
        )

        if any(token in text for token in ("续写", "继续写", "接着写", "往下写", "继续正文")):
            return UserIntent.CONTINUE_WRITE
        if re.search(r"(写|创作|生成)第[0-9一二三四五六七八九十百千万两零〇]+章", text):
            return UserIntent.CONTINUE_WRITE
        if any(token in text for token in ("润色", "改写这段", "优化这段", "修改这段", "重写这段")):
            return UserIntent.POLISH_CONTENT

        has_action = any(token in text for token in action_markers)
        if has_action and any(token in text for token in ("角色卡", "人设卡", "人物卡", "角色档案", "人物设定", "主角档案", "反派人物设定")):
            return UserIntent.CREATE_CHARACTER
        if has_action and any(token in text for token in ("事件线", "剧情线", "故事线", "主线", "支线")):
            return UserIntent.CREATE_EVENTLINES
        if has_action and any(token in text for token in ("细纲", "详细大纲", "分场细纲")):
            return UserIntent.CREATE_DETAIL_OUTLINE
        if has_action and any(token in text for token in ("章纲", "章节设定", "章节规划")):
            return UserIntent.CREATE_CHAPTER_SETTINGS
        if has_action and any(token in text for token in ("世界观", "世界设定", "世界设定集")):
            return UserIntent.CREATE_NOVEL

        create_novel_markers = (
            "开始创作", "开始写", "创建小说", "开一本新书", "写一部", "写一本",
            "写个小说", "写一篇小说", "创作小说",
        )
        if any(marker in text for marker in create_novel_markers):
            return UserIntent.CREATE_NOVEL

        return None

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
                self._last_intent_error_kind = None
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
                    self._last_intent_error_kind = "llm_unavailable"
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
                self._last_intent_error_kind = "invalid_response" if isinstance(e, ValueError) else "llm_unavailable"
                return None

        self._llm_intent_timeout = 15.0  # reset
        return None

    async def _analyze_intents_with_llm(
        self,
        message: str,
    ) -> Optional[List[IntentAnalysis]]:
        """
        使用 LLM 进行多意图分析，支持超时重试。

        返回多个意图的列表，或 None（如果分析失败）。
        """
        prompt = self._build_multi_intent_analysis_prompt(message)
        current_timeout = self._llm_intent_timeout
        retries = 0

        while retries <= self._llm_intent_max_retries:
            try:
                logger.info(
                    f"[{self.name}] 开始 LLM 多意图分析"
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
                result = self._parse_multi_intent_response(response)
                if not result or not isinstance(result, list):
                    raise ValueError("invalid_multi_intent_response")

                analyses: List[IntentAnalysis] = []
                for item in result:
                    if not isinstance(item, dict) or "intent" not in item:
                        continue
                    primary_intent = self._coerce_user_intent(item.get("intent"))
                    if primary_intent is None:
                        continue
                    fallback_intent = self._coerce_user_intent(item.get("fallback_intent"))
                    confidence = float(item.get("confidence", 0.7))
                    analysis = self._build_intent_analysis(
                        str(item.get("original_text") or message),
                        primary_intent,
                        confidence=confidence,
                        fallback_intent=fallback_intent,
                    )
                    # 覆盖 entities（如果 LLM 返回了 entities 字段）
                    if isinstance(item.get("entities"), dict):
                        analysis.entities.update(item["entities"])
                    analyses.append(analysis)

                if not analyses:
                    raise ValueError("no_valid_intents_parsed")

                self._llm_intent_timeout = 15.0
                self._last_intent_error_kind = None
                logger.info(
                    f"[{self.name}] LLM 多意图分析成功: {len(analyses)} 个意图, "
                    f"intents={[a.primary_intent.value for a in analyses]}"
                )
                return analyses

            except asyncio.TimeoutError:
                retries += 1
                if retries > self._llm_intent_max_retries:
                    logger.warning(
                        f"[{self.name}] LLM 多意图分析第{retries - 1}次超时，已达最大重试次数"
                    )
                    self._llm_intent_timeout = 15.0
                    self._last_intent_error_kind = "llm_unavailable"
                    return None
                current_timeout = min(current_timeout * 2, self._llm_intent_max_timeout)
                self._llm_intent_timeout = current_timeout
                logger.warning(
                    f"[{self.name}] LLM 多意图分析超时({current_timeout / 2:.0f}s)，"
                    f"第{retries}次重试，使用timeout={current_timeout:.0f}s"
                )
                continue

            except Exception as e:
                logger.warning(f"[{self.name}] LLM 多意图分析异常: {e}")
                self._llm_intent_timeout = 15.0
                self._last_intent_error_kind = "invalid_response" if isinstance(e, ValueError) else "llm_unavailable"
                return None

        self._llm_intent_timeout = 15.0
        return None

    def _build_multi_intent_analysis_prompt(self, message: str) -> str:
        """
        构造 LLM 多意图分析提示词。

        与单意图分析类似，但要求 LLM 返回一个意图数组。
        """
        system_desc = """【系统背景】
这是一个 AI 辅助小说创作平台。平台有完整的长篇创作工作流，由多个专业创作助手分工完成：

【创作助手职责】
- 世界观构建师：构建世界观（世界设定、力量体系、地理、势力、文化等）
- 角色构建师：创建角色档案/人设卡（主角、配角、反派等人物）
- 大纲规划师：规划故事大纲（卷/章结构、主线/支线剧情）
- 章节写作助手：撰写章节正文
- 质量评估师：评估章节质量
- 润色助手：润色修订章节
- 续写助手：无限续写（对已有章节续写）

【工作流顺序】
当用户要创作一部新小说时，系统按顺序执行：
世界观 → 角色档案 → 故事大纲 → 章节正文（并行可写多章）→ 评估 → 润色

【关键区分规则】
- "写小说" + "主角叫XXX" + 要求开始创作/生成大纲/写正文 → CREATE_NOVEL（主角是小说的设定之一）
- "我想写一本..." 但只是要求"丰富/细化/展开主角人设或世界观设定" → GENERAL_CHAT，除非明确说生成、保存、写入资料库或开始创作
- "创建角色档案/人设卡/角色卡" → CREATE_CHARACTER
- "梳理/生成事件线/剧情线" → CREATE_EVENTLINES
- "续写/继续写" → CONTINUE_WRITE
- "润色/改写" → POLISH_CONTENT
- "怎么写/要不要/是否/帮我看看/先讨论" → GENERAL_CHAT 或 ASK_HELP，不要判成执行类创作意图"""

        intent_descriptions = {
            UserIntent.CREATE_NOVEL: (
                "用户要开始创作一部新小说。关键词：'写小说/创作/开始写'、指定了主角名字、"
                "提到小说类型（玄幻/都市等）、要求'搭大纲''世界观''写正文'。"
                "注意：如果用户只是要求丰富、细化、展开主角人设或世界观设定，"
                "且没有明确要求生成/保存/开始创作，判为 GENERAL_CHAT。"
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
            "请根据上述系统背景和创作助手职责，判断这条消息中包含的所有用户意图。\n"
            "用户可能在一条消息中提出多个任务，请将每个任务拆分为独立的意图。\n\n"
            "只能从以下 intent 中选择：\n"
            + "\n".join(allowed_lines)
            + "\n\n"
            "判断要求：\n"
            "1. 以用户真实意图为准，不只看单个关键词。\n"
            "2. '写小说 + 主角名 + 明确开始创作/生成大纲/写正文' → CREATE_NOVEL；"
            "'丰富/细化/展开主角人设或世界观设定' → GENERAL_CHAT，除非明确要求保存、生成或开始创作。\n"
            "3. '续写/继续写' → CONTINUE_WRITE；'润色/改写已有内容' → POLISH_CONTENT。\n"
            "4. 如果用户是在询问建议、比较方案、确认是否要做、或明确说先讨论，优先 GENERAL_CHAT/ASK_HELP，而不是执行类意图。\n"
            "5. CREATE_* 只表示用户主题属于创作任务；是否立即写入由后续执行门控判断，不要为了“可能会写”而提高置信度。\n"
            "6. 置信度：很确定用0.9+，比较确定用0.7-0.9，不确定用0.5-0.7。\n"
            "7. 如果用户只表达了一个意图，数组中只返回一个元素。\n"
            "8. original_text 是该意图对应的原始用户文本片段。\n\n"
            "只返回 JSON 数组，不要解释：\n"
            '[\n'
            '  {\n'
            '    "intent": "create_character",\n'
            '    "confidence": 0.9,\n'
            '    "original_text": "帮我写主角的角色卡",\n'
            '    "fallback_intent": "general_chat"\n'
            '  },\n'
            '  {\n'
            '    "intent": "create_character",\n'
            '    "confidence": 0.85,\n'
            '    "original_text": "十个配角的角色卡",\n'
            '    "fallback_intent": "general_chat"\n'
            '  }\n'
            ']'
        )

    def _parse_multi_intent_response(self, response: Any) -> Optional[List[Dict[str, Any]]]:
        """解析多意图分析 JSON 数组。"""
        raw_text = str(response or "").strip()
        if not raw_text:
            return None
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        # 尝试从文本中提取 JSON 数组
        json_match = re.search(r"\[[\s\S]*\]", raw_text)
        if not json_match:
            return None
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
        return None

    # 意图依赖优先级（数值越小越先执行）
    _INTENT_DEPENDENCY_ORDER: Dict[str, int] = {
        UserIntent.SEARCH_WEB.value: 0,
        UserIntent.SEARCH_TRENDS.value: 0,
        UserIntent.QUERY_KNOWLEDGE.value: 0,
        # 世界观和角色是创作基础
        "build_world": 1,
        UserIntent.CREATE_CHARACTER.value: 2,
        # 大纲依赖世界观
        UserIntent.CREATE_NOVEL.value: 3,
        UserIntent.CREATE_EVENTLINES.value: 4,
        UserIntent.CREATE_DETAIL_OUTLINE.value: 4,
        UserIntent.CREATE_CHAPTER_SETTINGS.value: 4,
        # 写作依赖大纲
        UserIntent.CONTINUE_WRITE.value: 5,
        # 润色依赖已有内容
        UserIntent.POLISH_CONTENT.value: 6,
        # 对话类无依赖
        UserIntent.GENERAL_CHAT.value: 10,
        UserIntent.ASK_HELP.value: 10,
        UserIntent.PROVIDE_FEEDBACK.value: 10,
        UserIntent.PROJECT_MANAGE.value: 10,
        UserIntent.CONFIG_SETTINGS.value: 10,
    }

    def _sort_intents_by_dependency(self, intents: List[IntentAnalysis]) -> List[IntentAnalysis]:
        """
        按依赖优先级对意图列表排序。

        排序规则：
        1. 搜索/查询类最先（无依赖）
        2. 世界观构建次之
        3. 角色创建
        4. 大纲/事件线
        5. 写作
        6. 润色
        7. 对话类最后
        """
        def _get_order(intent: IntentAnalysis) -> int:
            return self._INTENT_DEPENDENCY_ORDER.get(intent.primary_intent.value, 5)
        return sorted(intents, key=_get_order)

    def _build_intent_analysis_prompt(self, message: str) -> str:
        """
        构造 LLM 意图分析提示词。

        提示词包含：
        1. 系统工作流说明（让LLM理解这是一个小说创作平台）
        2. 所有创作助手及其职责（让LLM知道有哪些内部助手可用）
        3. 所有意图类型及其含义
        4. 判断规则（帮助LLM区分易混淆的意图）
        """
        system_desc = """【系统背景】
这是一个 AI 辅助小说创作平台。平台有完整的长篇创作工作流，由多个专业创作助手分工完成：

【创作助手职责】
- 世界观构建师：构建世界观（世界设定、力量体系、地理、势力、文化等）
- 角色构建师：创建角色档案/人设卡（主角、配角、反派等人物）
- 大纲规划师：规划故事大纲（卷/章结构、主线/支线剧情）
- 章节写作助手：撰写章节正文
- 质量评估师：评估章节质量
- 润色助手：润色修订章节
- 续写助手：无限续写（对已有章节续写）

【工作流顺序】
当用户要创作一部新小说时，系统按顺序执行：
世界观 → 角色档案 → 故事大纲 → 章节正文（并行可写多章）→ 评估 → 润色

【关键区分规则】
- "写小说" + "主角叫XXX" + 要求开始创作/生成大纲/写正文 → CREATE_NOVEL（主角是小说的设定之一）
- "我想写一本..." 但只是要求"丰富/细化/展开主角人设或世界观设定" → GENERAL_CHAT，除非明确说生成、保存、写入资料库或开始创作
- "创建角色档案/人设卡/角色卡" → CREATE_CHARACTER
- "梳理/生成事件线/剧情线" → CREATE_EVENTLINES
- "续写/继续写" → CONTINUE_WRITE
- "润色/改写" → POLISH_CONTENT
- "怎么写/要不要/是否/帮我看看/先讨论" → GENERAL_CHAT 或 ASK_HELP，不要判成执行类创作意图"""

        intent_descriptions = {
            UserIntent.CREATE_NOVEL: (
                "用户要开始创作一部新小说。关键词：'写小说/创作/开始写'、指定了主角名字、"
                "提到小说类型（玄幻/都市等）、要求'搭大纲''世界观''写正文'。"
                "注意：如果用户只是要求丰富、细化、展开主角人设或世界观设定，"
                "且没有明确要求生成/保存/开始创作，判为 GENERAL_CHAT。"
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
            "请根据上述系统背景和创作助手职责，判断这条消息最主要的用户意图，只能从以下 intent 中选择一个：\n"
            + "\n".join(allowed_lines)
            + "\n\n"
            "判断要求：\n"
            "1. 以用户真实意图为准，不只看单个关键词。\n"
            "2. '写小说 + 主角名 + 明确开始创作/生成大纲/写正文' → CREATE_NOVEL；"
            "'丰富/细化/展开主角人设或世界观设定' → GENERAL_CHAT，除非明确要求保存、生成或开始创作。\n"
            "3. '续写/继续写' → CONTINUE_WRITE；'润色/改写已有内容' → POLISH_CONTENT。\n"
            "4. 如果用户是在询问建议、比较方案、确认是否要做、或明确说先讨论，优先 GENERAL_CHAT/ASK_HELP，而不是执行类意图。\n"
            "5. CREATE_* 只表示用户主题属于创作任务；是否立即写入由后续执行门控判断，不要为了“可能会写”而提高置信度。\n"
            "6. 置信度：很确定用0.9+，比较确定用0.7-0.9，不确定用0.5-0.7。\n\n"
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
            story_memory_result = await self._try_story_memory_action(message)
            if story_memory_result:
                return story_memory_result

            # 1. 分析意图（透明化，支持多意图拆分）
            result["routing_info"]["steps"].append({
                "step": "intent_analysis",
                "status": "started",
                "message": "🔍 正在分析您的意图..."
            })
            
            intent_analyses = self._intent_analyses_from_explicit_context(message, context)
            if not intent_analyses:
                intent_analyses = await self.analyze_intents(message)
            intent_analyses = [self._normalize_intent_analysis(message, ia) for ia in intent_analyses]
            
            # 记录所有意图
            result["intent"] = {
                "type": intent_analyses[0].primary_intent.value,
                "confidence": intent_analyses[0].confidence,
                "entities": intent_analyses[0].entities,
                "multi_intent": len(intent_analyses) > 1,
                "intent_count": len(intent_analyses),
                "all_intents": [
                    {
                        "type": ia.primary_intent.value,
                        "confidence": ia.confidence,
                    }
                    for ia in intent_analyses
                ],
            }
            
            # 透明化输出
            if len(intent_analyses) > 1:
                intent_names = [self._get_intent_display_name(ia.primary_intent) for ia in intent_analyses]
                result["routing_info"]["steps"].append({
                    "step": "intent_analysis",
                    "status": "completed",
                    "message": f"🎯 识别到 {len(intent_analyses)} 个意图：{' → '.join(intent_names)}",
                    "details": "将按依赖顺序依次执行",
                })
            else:
                intent_analysis = intent_analyses[0]
                intent_emoji = self._get_intent_emoji(intent_analysis.primary_intent)
                confidence_level = "高" if intent_analysis.confidence > 0.7 else "中" if intent_analysis.confidence > 0.5 else "低"
                result["routing_info"]["steps"].append({
                    "step": "intent_analysis",
                    "status": "completed",
                    "message": f"{intent_emoji} 意图识别：{self._get_intent_display_name(intent_analysis.primary_intent)}",
                    "details": f"置信度：{confidence_level}（{intent_analysis.confidence:.0%}）"
                })
            
            logger.info(
                f"[{self.name}] 意图分析: {len(intent_analyses)} 个意图, "
                f"intents={[ia.primary_intent.value for ia in intent_analyses]}"
            )
            
            # 2. 并行执行知识库检索和工具调用（性能优化）
            import asyncio
            tasks = []
            
            # 使用第一个意图判断是否需要知识库和工具
            first_intent = intent_analyses[0]
            if first_intent.requires_knowledge_base:
                result["routing_info"]["steps"].append({
                    "step": "knowledge_retrieval",
                    "status": "started",
                    "message": "📚 正在检索知识库..."
                })
                tasks.append(("kb", self.retrieve_knowledge(message)))
            
            if first_intent.requires_tool_call and first_intent.tool_name:
                tool_display = self._get_tool_display_name(first_intent.tool_name)
                result["routing_info"]["steps"].append({
                    "step": "tool_call",
                    "status": "started",
                    "message": f"🔧 正在调用工具：{tool_display}"
                })
                tasks.append(("tool", self.call_tool(
                    first_intent.tool_name,
                    first_intent.tool_args or {}
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
            
            # 4. 根据意图分发任务给对应的智能体（支持多意图顺序执行）
            if len(intent_analyses) > 1:
                # 多意图：先显示待办任务清单，再顺序执行
                result["routing_info"]["steps"].append({
                    "step": "task_delegation",
                    "status": "started",
                    "message": f"🎯 识别到 {len(intent_analyses)} 个任务，正在按依赖顺序执行..."
                })
                
                # 构建待办任务清单（markdown checkbox 格式）
                task_checklist: List[Dict[str, Any]] = []
                for idx, ia in enumerate(intent_analyses, 1):
                    intent_name = self._get_intent_display_name(ia.primary_intent)
                    emoji = self._get_intent_emoji(ia.primary_intent)
                    task_checklist.append({
                        "index": idx,
                        "intent_name": intent_name,
                        "emoji": emoji,
                        "status": "pending",  # pending / running / completed / failed
                        "agent": "",
                        "response_text": "",
                    })
                
                # 先发送任务清单给前端（通过 progress callback）
                checklist_header = self._build_task_checklist_markdown(task_checklist)
                if context and isinstance(context, dict):
                    callback = context.get("progress_callback")
                    if callback:
                        try:
                            checklist_payload = {
                                "content": checklist_header,
                                "current_agent": "Router",
                                "stage": "multi_intent_checklist",
                                "status": "running",
                            }
                            callback_result = callback(checklist_payload)
                            if hasattr(callback_result, "__await__"):
                                await callback_result
                        except Exception:
                            pass
                
                all_responses: List[str] = []
                all_delegated_results: List[Dict[str, Any]] = []
                last_delegated_result: Optional[Dict[str, Any]] = None
                
                for idx, ia in enumerate(intent_analyses, 1):
                    intent_name = self._get_intent_display_name(ia.primary_intent)
                    emoji = self._get_intent_emoji(ia.primary_intent)
                    
                    # 更新清单状态为"执行中"
                    task_checklist[idx - 1]["status"] = "running"
                    
                    result["routing_info"]["steps"].append({
                        "step": f"task_delegation_{idx}",
                        "status": "started",
                        "message": f"🎯 [{idx}/{len(intent_analyses)}] 正在执行：{intent_name}..."
                    })
                    
                    try:
                        delegated_result = await self._delegate_to_agent(
                            intent_analysis=ia,
                            message=str(ia.entities.get("original_text") or message),
                            knowledge_results=result["knowledge_results"],
                            tool_results=result["tool_results"],
                            context=context
                        )
                        
                        if delegated_result:
                            all_delegated_results.append(delegated_result)
                            last_delegated_result = delegated_result
                            agent_name = delegated_result.get("agent_name", "未知Agent")
                            agent_display_name = _get_user_visible_agent_name(agent_name, "未知助手")
                            response_text = _localize_user_visible_agent_names(delegated_result.get("response", ""))
                            
                            task_status = self._delegated_task_status(delegated_result)
                            task_checklist[idx - 1]["status"] = task_status
                            task_checklist[idx - 1]["agent"] = agent_display_name
                            task_checklist[idx - 1]["response_text"] = response_text
                            
                            status_message = "完成" if task_status == "completed" else "需要继续确认"
                            result["routing_info"]["steps"].append({
                                "step": f"task_delegation_{idx}",
                                "status": task_status,
                                "message": f"📞 [{idx}/{len(intent_analyses)}] {intent_name} → {agent_display_name} {status_message}"
                            })
                            
                            if response_text:
                                all_responses.append(f"**【{intent_name}】**\n{response_text}")
                        else:
                            task_checklist[idx - 1]["status"] = "completed"
                            task_checklist[idx - 1]["agent"] = "智能路由助手"
                            result["routing_info"]["steps"].append({
                                "step": f"task_delegation_{idx}",
                                "status": "completed",
                                "message": f"💬 [{idx}/{len(intent_analyses)}] {intent_name} 由路由器直接处理"
                            })
                    except Exception as e:
                        logger.error(f"[{self.name}] 多意图任务 {idx} 执行失败: {e}")
                        task_checklist[idx - 1]["status"] = "failed"
                        result["routing_info"]["steps"].append({
                            "step": f"task_delegation_{idx}",
                            "status": "failed",
                            "message": f"❌ [{idx}/{len(intent_analyses)}] {intent_name} 执行失败: {str(e)[:50]}"
                        })
                        all_responses.append(f"**【{intent_name}】**\n❌ 执行失败: {str(e)[:100]}")
                
                # 聚合结果：待办清单 + 各任务详情
                if last_delegated_result:
                    aggregate_result = dict(last_delegated_result)
                    aggregate_result["is_complete"] = all(
                        task.get("status") == "completed" for task in task_checklist
                    )
                    aggregate_result["delegated_results"] = all_delegated_results
                    aggregate_result["created_files"] = self._merge_delegated_file_records(all_delegated_results, "created_files")
                    aggregate_result["updated_files"] = self._merge_delegated_file_records(all_delegated_results, "updated_files")
                    aggregate_result["reused_files"] = self._merge_delegated_file_records(all_delegated_results, "reused_files")
                    if not aggregate_result["is_complete"]:
                        aggregate_result["requires_confirmation"] = True
                    result["delegated_result"] = aggregate_result
                    result["routed_to"] = last_delegated_result.get("agent_name")
                    result["is_complete"] = aggregate_result["is_complete"]
                
                # 构建最终响应：清单 + 详情
                final_checklist = self._build_task_checklist_markdown(task_checklist, show_status=True)
                response_parts = [final_checklist]
                if all_responses:
                    response_parts.append("\n\n---\n\n")
                    response_parts.append("\n\n---\n\n".join(all_responses))
                result["response"] = "".join(response_parts)
                
                # 将任务清单结构化数据也返回给前端
                result["task_checklist"] = [
                    {
                        "index": t["index"],
                        "intent": intent_analyses[t["index"] - 1].primary_intent.value,
                        "intent_name": t["intent_name"],
                        "emoji": t["emoji"],
                        "status": t["status"],
                        "agent": t["agent"],
                    }
                    for t in task_checklist
                ]
                
                result["routing_info"]["steps"].append({
                    "step": "task_delegation",
                    "status": "completed",
                    "message": (
                        f"✅ 所有 {len(intent_analyses)} 个任务执行完成"
                        if result.get("is_complete", False)
                        else f"🟡 {len(intent_analyses)} 个任务已执行，仍有任务等待确认"
                    )
                })
            else:
                # 单意图：原有逻辑
                intent_analysis = intent_analyses[0]
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
                    agent_display_name = _get_user_visible_agent_name(agent_name, "未知助手")
                    result["routing_info"]["steps"].append({
                        "step": "task_delegation",
                        "status": "completed",
                        "message": f"📞 已分发给：{agent_display_name}"
                    })
                    
                    # 如果被委派的Agent返回了响应，使用它
                    if delegated_result.get("response"):
                        result["response"] = _localize_user_visible_agent_names(delegated_result["response"])
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
                    intent_analysis=intent_analyses[0],
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

        result["response"] = _localize_user_visible_agent_names(result.get("response", ""))
        for step in result.get("routing_info", {}).get("steps", []):
            if not isinstance(step, dict):
                continue
            for key in ("message", "details", "error"):
                if step.get(key):
                    step[key] = _localize_user_visible_agent_names(step[key])
        
        # 计算总耗时
        result["routing_info"]["duration"] = time.time() - start_time
        result["routing_info"]["steps"].append({
            "step": "completed",
            "status": "success",
            "message": f"⏱️ 处理完成（耗时 {result['routing_info']['duration']:.2f}秒）"
        })
        
        return result

    async def _try_story_memory_action(self, message: str) -> Optional[Dict[str, Any]]:
        """Handle direct story-memory lookup/backfill requests before generic routing."""
        try:
            from ..story_memory_actions import handle_story_memory_request

            return await handle_story_memory_request(self, message)
        except Exception as exc:
            logger.warning(f"[{self.name}] story memory action failed: {exc}")
            return None

    @staticmethod
    def _delegated_task_status(delegated_result: Dict[str, Any]) -> str:
        if not isinstance(delegated_result, dict):
            return "completed"
        if delegated_result.get("error"):
            return "failed"
        if "is_complete" in delegated_result and not bool(delegated_result.get("is_complete")):
            return "needs_confirmation"
        return "completed"

    @staticmethod
    def _merge_delegated_file_records(
        delegated_results: List[Dict[str, Any]],
        field_name: str,
    ) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = []
        seen_paths: set[str] = set()
        for result in delegated_results:
            if not isinstance(result, dict):
                continue
            for item in result.get(field_name, []) or []:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                key = path or json.dumps(item, ensure_ascii=False, sort_keys=True)
                if key in seen_paths:
                    continue
                merged.append(dict(item))
                seen_paths.add(key)
        return merged
    
    def _build_task_checklist_markdown(
        self,
        task_checklist: List[Dict[str, Any]],
        show_status: bool = False,
    ) -> str:
        """
        构建待办任务清单的 markdown 格式。
        
        Args:
            task_checklist: 任务清单列表
            show_status: 是否显示执行状态（完成后显示 ✅/❌）
        
        Returns:
            markdown 格式的任务清单
        """
        status_icons = {
            "pending": "⬜",
            "running": "🔄",
            "completed": "✅",
            "needs_confirmation": "🟡",
            "failed": "❌",
        }
        
        lines = ["### 📋 任务清单\n"]
        for task in task_checklist:
            idx = task["index"]
            emoji = task["emoji"]
            name = task["intent_name"]
            status = task["status"]
            agent = task.get("agent", "")
            agent_display = _get_user_visible_agent_name(agent, "") if agent else ""
            
            if show_status:
                icon = status_icons.get(status, "⬜")
                agent_hint = f" → `{agent_display}`" if agent_display and status in ("completed", "needs_confirmation", "failed") else ""
                lines.append(f"- {icon} **{idx}.** {emoji} {name}{agent_hint}")
            else:
                lines.append(f"- ⬜ **{idx}.** {emoji} {name}")
        
        completed_count = sum(1 for t in task_checklist if t["status"] == "completed")
        pending_confirmation_count = sum(1 for t in task_checklist if t["status"] == "needs_confirmation")
        failed_count = sum(1 for t in task_checklist if t["status"] == "failed")
        total = len(task_checklist)
        
        if show_status:
            if failed_count > 0:
                lines.append(f"\n> 进度：{completed_count}/{total} 完成，{failed_count} 失败")
            elif pending_confirmation_count > 0:
                lines.append(f"\n> 进度：{completed_count}/{total} 完成，{pending_confirmation_count} 个等待确认")
            elif completed_count == total:
                lines.append(f"\n> ✅ 全部 {total} 个任务已完成")
            else:
                lines.append(f"\n> 进度：{completed_count}/{total} 完成")
        
        return "\n".join(lines)

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
                if explicit_name == "create" and bool((context or {}).get("auto_execute")):
                    return await self._execute_create_novel_pipeline(message=message, context=context)
                serial_categories = self._target_categories_from_explicit_command(message, explicit_command)
                if explicit_name in {"worldbuild", "outline", "character", "projectdata", "chapter"}:
                    return await self._execute_serial_creative_workflow_pipeline(
                        message=message,
                        context=context,
                        target_categories=serial_categories,
                        action="world_and_character_setup"
                        if serial_categories == ["worldbuilding", "characters"]
                        else "creative_workflow",
                        operation=self._workflow_operation_from_message(message),
                    )

            # === 角色建档 → CharacterBuilder ===
            if intent == UserIntent.CREATE_CHARACTER:
                if not self.coordinator:
                    return await self._execute_character_creation_pipeline(message, context)
                return await self._execute_serial_creative_workflow_pipeline(
                    message=message,
                    context=context,
                    target_categories=["characters"],
                    operation=self._workflow_operation_from_message(message),
                )

            if intent == UserIntent.CREATE_EVENTLINES:
                if not self.coordinator:
                    return await self._execute_project_data_generation_pipeline(
                        message=message,
                        context=context,
                        data_type="eventlines",
                        agent_name="EventlineBuilder",
                        stage="eventlines",
                        label="事件线",
                    )
                return await self._execute_serial_creative_workflow_pipeline(
                    message=message,
                    context=context,
                    target_categories=["eventlines"],
                    operation=self._workflow_operation_from_message(message),
                )

            if intent == UserIntent.CREATE_DETAIL_OUTLINE:
                if not self.coordinator:
                    return await self._execute_project_data_generation_pipeline(
                        message=message,
                        context=context,
                        data_type="detail_settings",
                        agent_name="DetailOutlineBuilder",
                        stage="detail_outlining",
                        label="细纲",
                    )
                return await self._execute_serial_creative_workflow_pipeline(
                    message=message,
                    context=context,
                    target_categories=["detail_settings"],
                    operation=self._workflow_operation_from_message(message),
                )

            if intent == UserIntent.CREATE_CHAPTER_SETTINGS:
                if not self.coordinator:
                    return await self._execute_project_data_generation_pipeline(
                        message=message,
                        context=context,
                        data_type="chapter_settings",
                        agent_name="ChapterSettingBuilder",
                        stage="chapter_settings",
                        label="章纲设定",
                    )
                return await self._execute_serial_creative_workflow_pipeline(
                    message=message,
                    context=context,
                    target_categories=["chapter_settings"],
                    operation=self._workflow_operation_from_message(message),
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
                            "3. 系统会先识别素材并生成 3 个创意方案\n"
                            "4. 依次完成方案选择、导语、大纲、章节生成、质检、复审、取名\n\n"
                            '这个固定面板会按\u201c统一输入 -> 3个创意方案 -> 导语 -> 大纲 -> 正文 -> 质检 -> 复审 -> 书名\u201d的流程推进。'
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
                        if (
                            is_worldbuild_only
                            and self._message_requests_character_cards(message)
                            and not is_novel_creation
                        ):
                            return await self._execute_serial_creative_workflow_pipeline(
                                message=message,
                                context=context,
                                target_categories=["worldbuilding", "characters"],
                                action="world_and_character_setup",
                                operation=self._workflow_operation_from_message(message),
                            )
                        if is_worldbuild_only and not is_novel_creation:
                            return await self._execute_serial_creative_workflow_pipeline(
                                message=message,
                                context=context,
                                target_categories=["worldbuilding"],
                                operation=self._workflow_operation_from_message(message),
                            )
                        return await self._execute_create_novel_pipeline(
                            message=message,
                            context=context,
                        )

                    requirements = await self._build_creation_requirements_async(context, message)
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
    
    def _can_call_model_for_requirement_extraction(self) -> bool:
        model_name = str(getattr(self.model_config, "model", "") or "").strip().lower()
        api_base = str(getattr(self.model_config, "api_base", "") or "").strip().lower()
        if "test-model" in model_name or "example.invalid" in api_base:
            return False
        return bool(model_name)

    @staticmethod
    def _looks_like_per_chapter_count_context(text: str, start: int) -> bool:
        prefix = str(text or "")[max(0, start - 16):start]
        return any(marker in prefix for marker in ("每章", "每一章", "单章", "每章节", "章节字数", "每章正文", "单章正文"))

    @staticmethod
    def _extract_word_count_hint(message: str) -> int:
        text = str(message or "").strip()
        if not text:
            return 0
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:w|W|万)\s*(?:字|词)?", text):
            if RouterAgent._looks_like_per_chapter_count_context(text, match.start()):
                continue
            return max(0, int(float(match.group(1)) * 10000))
        for match in re.finditer(r"(\d{4,7})\s*(?:字|词)", text):
            if RouterAgent._looks_like_per_chapter_count_context(text, match.start()):
                continue
            return max(0, int(match.group(1)))
        return 0

    @staticmethod
    def _normalize_word_count_number(raw_number: Any, raw_unit: Any = "") -> int:
        try:
            value = float(str(raw_number or "").strip())
        except (TypeError, ValueError):
            return 0
        unit = str(raw_unit or "").strip().lower()
        if unit in {"w", "万"}:
            value *= 10000
        elif unit in {"k", "千"}:
            value *= 1000
        elif value < 50:
            return 0
        return max(0, int(round(value)))

    @staticmethod
    def _extract_per_chapter_word_count_hint(message: str) -> int:
        text = str(message or "").strip()
        if not text:
            return 0
        patterns = (
            r"(?:每章|每一章|单章|每章节|章节字数|每章正文|单章正文).{0,8}?(\d+(?:\.\d+)?)\s*(k|K|千|w|W|万)?\s*(?:字|词)?",
            r"(\d+(?:\.\d+)?)\s*(k|K|千|w|W|万)?\s*(?:字|词)?\s*(?:每章|每一章|单章|每章节|一章)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return RouterAgent._normalize_word_count_number(match.group(1), match.group(2) or "")
        return 0

    @staticmethod
    def _derive_chapters_for_target_words(target_word_count: int) -> int:
        if target_word_count <= 0:
            return 0
        return max(5, min(80, int(math.ceil(target_word_count / 3000))))

    @staticmethod
    def _extract_local_creation_requirement_hints(message: str) -> Dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            return {}

        hints: Dict[str, Any] = {}
        autonomy_patterns = (
            r"(?:其他|其它|剩下|其余|余下|别的|其他的|其它的|后面|后续).{0,24}(?:随便|你来|你帮我|帮我|你安排|帮我安排|自由发挥|自己安排|自行安排|完善|补充|补全|由你(?:来)?(?:补充|补全|完善|安排|设定))",
            r"(?:随便|自由发挥|自己安排|自行安排|你安排|帮我安排|你看着办|你定|你决定|都交给你|由你(?:来)?(?:补充|补全|完善|安排|设定)|你(?:来)?(?:补充|补全|完善)).{0,20}(?:创作|写|安排|完善|补全|补充|设定|构思)?",
            r"(?:不用|不想|懒得).{0,12}(?:想|填|设定|补充).{0,20}(?:你来|你帮我|随便|自由发挥|安排)",
        )
        autonomous_creation = any(re.search(pattern, text) for pattern in autonomy_patterns)
        if autonomous_creation:
            hints["ai_autonomy_requested"] = True
        for tokens, novel_type in _GENRE_HINTS:
            if any(token in text for token in tokens):
                hints["novel_type"] = novel_type
                break

        theme_parts: List[str] = []
        for token, label in _THEME_HINTS:
            if token in text and label not in theme_parts:
                theme_parts.append(label)
        if theme_parts:
            if theme_parts == ["古代", "甜宠"]:
                hints["theme"] = "古代甜宠"
            else:
                hints["theme"] = "、".join(theme_parts[:4])

        protagonist_match = re.search(r"(?<!女)(?:主角|男主角?|男主)(?:叫|是|为)\s*([^。；;，,\n]+)", text)
        if protagonist_match:
            protagonist = str(protagonist_match.group(1) or "").strip()
            if protagonist and not any(marker in protagonist for marker in ("你帮我", "帮我", "随便", "什么的", "安排")):
                hints["protagonist"] = protagonist[:120]

        plot_match = re.search(r"(?:剧情|故事|主线|走向)(?:是|为|围绕|：|:)\s*([^。；;\n]+)", text)
        if plot_match:
            plot_idea = str(plot_match.group(1) or "").strip(" ，,。；;")
            if plot_idea and plot_idea != text:
                hints["plot_idea"] = plot_idea[:500]

        target_words = RouterAgent._extract_word_count_hint(text)
        per_chapter_words = RouterAgent._extract_per_chapter_word_count_hint(text)
        if per_chapter_words:
            hints["target_words_per_chapter"] = per_chapter_words
            hints["target_words_per_chapter_source"] = "user"
        if target_words:
            hints["target_word_count"] = target_words
            if per_chapter_words:
                hints["chapters_per_volume"] = max(1, min(80, int(math.ceil(target_words / per_chapter_words))))
            else:
                hints["chapters_per_volume"] = RouterAgent._derive_chapters_for_target_words(target_words)

        requirement_parts: List[str] = []
        if target_words:
            requirement_parts.append(f"篇幅约{target_words}字")
        if per_chapter_words:
            requirement_parts.append(f"每章约{per_chapter_words}字")
        if autonomous_creation:
            requirement_parts.append(_AI_AUTONOMY_REQUIREMENT)
        if re.search(r"(?:主角名字|主角名|主角姓名|主角设定|人物设定).{0,12}(?:你帮我|帮我|随便|安排|完善|想)", text):
            requirement_parts.append("主角姓名与人物设定由助手合理安排")
        if re.search(r"(?:女主角|女主).{0,12}(?:你帮我|帮我|随便|安排|想)", text):
            requirement_parts.append("女主角由助手构思")
        if requirement_parts:
            hints["requirements"] = "；".join(requirement_parts)

        return hints

    @staticmethod
    def _looks_like_unparsed_creation_request(plot_idea: str, source_message: str) -> bool:
        plot = str(plot_idea or "").strip()
        source = str(source_message or "").strip()
        if not plot:
            return False
        if source and plot == source:
            return True
        request_markers = ("我想写", "想写", "篇幅", "题材", "小说", "主角名字", "你帮我", "帮我安排")
        return any(marker in plot for marker in request_markers) and not any(
            marker in plot for marker in ("剧情", "主线", "故事走向", "围绕", "讲述")
        )

    @staticmethod
    def _extract_json_object(response: str) -> Dict[str, Any]:
        text = str(response or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            data = json.loads(match.group())
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_model_requirement_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        allowed_text_fields = ("novel_type", "theme", "requirements", "protagonist", "plot_idea")
        normalized: Dict[str, Any] = {}
        for key in allowed_text_fields:
            value = payload.get(key)
            if isinstance(value, (str, int, float)):
                text = str(value).strip()
                if text and text not in {"未指定", "未知", "无", "null", "None"}:
                    normalized[key] = text[:1200] if key == "requirements" else text[:500]

        for key in ("volume_count", "chapters_per_volume", "target_word_count", "target_words_per_chapter"):
            try:
                value = int(payload.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                normalized[key] = value

        if payload.get("ai_autonomy_requested") is True:
            normalized["ai_autonomy_requested"] = True

        return normalized

    async def _extract_creation_requirements_with_model(
        self,
        context: Optional[Dict[str, Any]],
        message: str,
        base_requirements: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self._can_call_model_for_requirement_extraction():
            return {}

        prompt = (
            "你是小说创作需求解析器。请先判断用户这句话是在提出新小说创作需求、补充创作约束，"
            "还是普通聊天；只有明确属于创作需求时才提取字段。\n"
            "不要按固定关键词硬切，要理解中文语义：题材、时代背景、篇幅、主角名、让AI代拟的部分都要保留。\n\n"
            "字段约束：target_word_count 表示全书总字数；target_words_per_chapter 只在用户明确说“每章/单章/一章多少字”时填写，"
            "如果用户只说全书篇幅，不要自行推断单章字数，返回 0 交给后续确认讨论。\n\n"
            "自主补全约束：用户说“其他/剩下/其余都由你补充/补全/完善/安排”、"
            "“其他设定和内容由你补充”、“都交给你”等，必须把 ai_autonomy_requested 设为 true，"
            "并在 requirements 中保留“未指定部分由助手自主创作”的含义。\n\n"
            "返回严格 JSON，不要 Markdown：\n"
            "{\n"
            '  "is_creation_request": true,\n'
            '  "novel_type": "",\n'
            '  "theme": "",\n'
            '  "requirements": "",\n'
            '  "protagonist": "",\n'
            '  "plot_idea": "",\n'
            '  "volume_count": 1,\n'
            '  "chapters_per_volume": 0,\n'
            '  "target_word_count": 0,\n'
            '  "target_words_per_chapter": 0,\n'
            '  "ai_autonomy_requested": false,\n'
            '  "confidence": 0.0\n'
            "}\n\n"
            f"当前基础字段（可能不准，只作参考）：\n{json.dumps(base_requirements, ensure_ascii=False)}\n\n"
            f"完整讨论上下文：\n{self._build_discussion_context(context, message)}\n\n"
            f"当前用户消息：\n{message}"
        )
        try:
            response = await self.call_llm(
                [{"role": "user", "content": prompt}],
                temperature=AGENT_TEMPERATURE.SUMMARY_STABLE,
                max_tokens=900,
            )
        except Exception as exc:
            logger.warning(f"[{self.name}] 模型解析创作需求失败，使用本地兜底: {exc}")
            return {}

        payload = self._extract_json_object(str(response or ""))
        if not payload or payload.get("is_creation_request") is False:
            return {}
        try:
            confidence = float(payload.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence and confidence < 0.35:
            return {}
        return self._normalize_model_requirement_payload(payload)

    def _merge_creation_requirement_hints(
        self,
        base: Dict[str, Any],
        hints: Dict[str, Any],
        message: str,
    ) -> Dict[str, Any]:
        merged = dict(base or {})
        if not hints:
            return merged

        raw_message = str(message or "").strip()
        for key in ("novel_type", "theme", "requirements", "protagonist"):
            value = hints.get(key)
            if value in (None, "", [], {}):
                continue
            if key == "requirements" and str(merged.get(key) or "").strip():
                existing_parts = [
                    part.strip()
                    for part in re.split(r"[；;\n]+", str(merged.get(key) or ""))
                    if part.strip()
                ]
                for part in re.split(r"[；;\n]+", str(value)):
                    part = part.strip()
                    if part and part not in existing_parts:
                        existing_parts.append(part)
                merged[key] = "；".join(existing_parts)
            else:
                merged[key] = value

        if hints.get("ai_autonomy_requested"):
            merged["ai_autonomy_requested"] = True
            existing_requirements = str(merged.get("requirements") or "").strip()
            if _AI_AUTONOMY_REQUIREMENT not in existing_requirements:
                merged["requirements"] = (
                    f"{existing_requirements}；{_AI_AUTONOMY_REQUIREMENT}"
                    if existing_requirements
                    else _AI_AUTONOMY_REQUIREMENT
                )

        plot_hint = str(hints.get("plot_idea") or "").strip()
        if plot_hint and (
            not str(merged.get("plot_idea") or "").strip()
            or str(merged.get("plot_idea") or "").strip() == raw_message
        ):
            merged["plot_idea"] = plot_hint

        for key in ("target_word_count", "target_words_per_chapter"):
            if hints.get(key):
                merged[key] = self._normalize_positive_int(hints.get(key), 0)
                if key == "target_words_per_chapter":
                    source = str(hints.get("target_words_per_chapter_source") or "").strip()
                    merged["target_words_per_chapter_source"] = source or "user"

        for key in ("volume_count", "chapters_per_volume"):
            if not hints.get(key):
                continue
            current = self._normalize_positive_int(merged.get(key), 0)
            should_replace_default = (
                (key == "volume_count" and current <= 1)
                or (key == "chapters_per_volume" and (current <= 5 or hints.get("target_word_count")))
            )
            if should_replace_default:
                merged[key] = self._normalize_positive_int(hints.get(key), current or 1)

        target_words = self._normalize_positive_int(merged.get("target_word_count"), 0)
        total_chapters = (
            self._normalize_positive_int(merged.get("volume_count"), 1)
            * self._normalize_positive_int(merged.get("chapters_per_volume"), 5)
        )
        if target_words and total_chapters and not merged.get("target_words_per_chapter"):
            merged["target_words_per_chapter"] = max(500, int(math.ceil(target_words / total_chapters)))
            merged["target_words_per_chapter_source"] = "estimated"

        return merged

    async def _build_creation_requirements_async(
        self,
        context: Optional[Dict[str, Any]],
        message: str,
    ) -> Dict[str, Any]:
        base = self._build_creation_requirements(context, message)
        local_hints = self._extract_local_creation_requirement_hints(message)
        if local_hints:
            base = self._merge_creation_requirement_hints(base, local_hints, message)

        model_hints = await self._extract_creation_requirements_with_model(context, message, base)
        if model_hints:
            base = self._merge_creation_requirement_hints(base, model_hints, message)

        if self._looks_like_unparsed_creation_request(base.get("plot_idea", ""), str(base.get("source_message") or message)):
            base["plot_idea"] = str(local_hints.get("plot_idea") or "").strip()
        return base

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
                if role == "user":
                    role_label = "用户"
                elif role == "assistant":
                    content = _sanitize_assistant_discussion_context(content)
                    if not content:
                        continue
                    role_label = "助手"
                else:
                    continue
                lines.append(f"{role_label}：{content}")

        if isinstance(collected_info, dict) and collected_info:
            extra_items = []
            for key, value in collected_info.items():
                if str(key) not in _CREATION_DISCUSSION_FIELD_WHITELIST:
                    continue
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
        ai_autonomy_requested = bool(requirements.get("ai_autonomy_requested", False))
        context_rules = (
            "【上下文继承硬约束】\n"
            "1. 必须优先基于上方聊天讨论中用户已经确认或倾向的设定。\n"
            "2. 不得擅自更换主角、题材、核心能力、门派/世界背景。\n"
            "3. 如果聊天讨论缺少关键信息，请明确列为待确认，不要随机补成无关设定。\n"
            "4. 允许补充细节，但补充内容必须服务于已讨论方向。"
        )
        if ai_autonomy_requested:
            context_rules += (
                "\n5. 用户已明确授权“其他/未指定内容由AI安排”，"
                "这类空白不是缺失信息；请在已给定的题材、篇幅和风格方向内自主补全世界名、核心冲突、地点、势力与剧情钩子。"
            )
        if not discussion_context:
            return f"{base_requirements}\n\n{context_rules}".strip()
        if base_requirements:
            return (
                f"{base_requirements}\n\n"
                "【沟通助手完整讨论摘要】\n"
                f"{discussion_context}\n\n"
                f"{context_rules}"
            ).strip()
        return f"【沟通助手完整讨论摘要】\n{discussion_context}\n\n{context_rules}".strip()

    def _build_outline_plot_idea_text(self, requirements: Dict[str, Any]) -> str:
        plot_idea = str(requirements.get("plot_idea") or "").strip()
        discussion_context = str(requirements.get("discussion_context") or "").strip()
        autonomy_note = (
            "【AI自主创作授权】用户已明确表示未指定内容由助手安排；"
            "请在已给定的题材、篇幅、主题和角色方向内自主设计主线、角色关系、冲突与阶段爽点。"
            if bool(requirements.get("ai_autonomy_requested", False))
            else ""
        )
        base_parts = [part for part in (plot_idea, autonomy_note) if part]
        if discussion_context:
            return (
                f"{chr(10).join(base_parts)}\n\n"
                "【沟通助手完整讨论摘要】\n"
                f"{discussion_context}"
            ).strip()
        return "\n\n".join(base_parts)

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

        latest_message = str(message or "").strip()
        source_plot_idea = str(source.get("plot_idea") or "").strip()
        plot_idea = source_plot_idea or ""
        novel_type = str(source.get("novel_type") or "").strip()
        if not novel_type:
            try:
                from ..project_manager import get_project_manager

                current_project = get_project_manager().get_current_project()
                novel_type = str(getattr(current_project, "novel_type", "") or "").strip()
            except Exception:
                novel_type = ""

        return {
            "novel_type": novel_type or "",
            "theme": str(source.get("theme") or "").strip(),
            "requirements": str(source.get("requirements") or "").strip(),
            "protagonist": str(source.get("protagonist") or "").strip(),
            "plot_idea": plot_idea,
            "volume_count": self._normalize_positive_int(source.get("volume_count"), 1),
            "chapters_per_volume": self._normalize_positive_int(source.get("chapters_per_volume"), 5),
            "target_word_count": self._normalize_positive_int(source.get("target_word_count"), 0),
            "target_words_per_chapter": self._normalize_positive_int(source.get("target_words_per_chapter"), 0),
            "target_words_per_chapter_source": str(source.get("target_words_per_chapter_source") or "").strip(),
            "ai_autonomy_requested": bool(source.get("ai_autonomy_requested", False)),
            "discussion_context": discussion_context,
            "resume_existing": self._should_resume_existing_project(context, message),
            "source_message": latest_message,
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
            target_word_count=self._normalize_positive_int(requirements.get("target_word_count"), 0),
            target_words_per_chapter=self._normalize_positive_int(requirements.get("target_words_per_chapter"), 0),
            ai_autonomy_requested=bool(requirements.get("ai_autonomy_requested", False)),
            source_session_id=str((context or {}).get("session_id") or "").strip(),
            source_message=str(requirements.get("source_message") or "").strip(),
            user_confirmed=user_confirmed,
        )
        contract.scope["discussion_context"] = str(requirements.get("discussion_context") or "").strip()
        contract.scope["resume_existing"] = bool(requirements.get("resume_existing", False))
        words_per_chapter_source = str(requirements.get("target_words_per_chapter_source") or "").strip()
        if (
            not words_per_chapter_source
            and self._normalize_positive_int(contract.scope.get("target_words_per_chapter"), 0)
            and not self._normalize_positive_int(requirements.get("target_words_per_chapter"), 0)
        ):
            words_per_chapter_source = "estimated"
        if words_per_chapter_source:
            contract.scope["target_words_per_chapter_source"] = words_per_chapter_source
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
            min(max(1, total_task_count), 5),
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

        event_type = str(data.get("type") or "").strip()
        # 逐 token 的 LLM 流式增量（以及同类内部事件）不应作为"思考进度"
        # 冒泡到 chat SSE：否则每个 token 都会被前端 appendStreamWorkflowProgress
        # 当作一行新的进度文本渲染，造成"逐字成行"的展示效果。
        if event_type in {
            "llm_chunk",
            "tool_call",
            "tool_result",
            "agent_task_progress",
        }:
            return

        stage = str(data.get("stage") or data.get("task_type") or "").strip()
        current_agent = str(data.get("agent") or data.get("current_agent") or "Coordinator").strip() or "Coordinator"
        content = str(data.get("message") or data.get("content") or "").strip()
        if not content:
            return

        status = "running"
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
        elif task_type == "build_characters":
            kind = "characters"
            label = "角色档案"
        elif task_type == "build_outline":
            kind = "outline"
            label = "大纲"
        elif task_type == "chapter_settings":
            kind = "chapter_settings"
            label = "章纲设定"
        elif task_type == "detail_outlining":
            kind = "detail_settings"
            label = "细纲设定"
        elif task_type == "outline_settings":
            kind = "outline_settings"
            label = "大纲设定"
        elif task_type == "eventlines":
            kind = "eventlines"
            label = "事件线"
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
                "content": "## 创作启动\n已切换到正式多助手协作执行链。",
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
        all_chapters_complete = bool(outline_rows) and next_incomplete == 0 and len(written_chapters) >= len(outline_rows)

        current_project = pm.get_current_project()
        outline_title = str((current_project.name if current_project else "") or "未命名项目").strip() or "未命名项目"
        compiled_novel_path = ""
        if written_chapters and all_chapters_complete:
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
            "已切换到正式多助手协作执行链，当前请求会通过合同确认后的任务池执行。",
            "",
            "执行流程：合同 → 任务池 → 创作助手协作 → 项目产物落盘",
        ]
        if executed_titles:
            preview_titles = executed_titles[:8]
            response_parts.extend(["", "已执行任务："] + [f"- {title}" for title in preview_titles])

        stop_reason_value = str(project_ready_execution.get("stop_reason") or "").strip()
        stopped_on_task_type = str(project_ready_execution.get("stopped_on_task_type") or "").strip()
        is_review_break = stop_reason_value == "review_required"
        is_chapter_settings_break = is_review_break and stopped_on_task_type in {
            "chapter_settings",
            "write_chapter",  # 当章纲在上一批生成、本批立即停在 write_chapter 入口的边界场景
        }

        if stop_reason_value:
            response_parts.extend(
                ["", f"当前停止原因：{_localize_workflow_error(stop_reason_value)}"]
            )
        if outline_rows:
            response_parts.extend(["", f"大纲已就绪，共 {len(outline_rows)} 章。"])
        if written_chapters:
            response_parts.append(f"已完成章节：{len(written_chapters)} 章。")
        if is_chapter_settings_break:
            response_parts.extend(
                [
                    "",
                    "章纲设定已生成，正文创作已暂停等待你的审阅。",
                    "请到左侧资料库中查看 / 修改章纲设定，确认无误后调用 "
                    "`POST /api/v1/contract/resume` 继续生成正文。",
                ]
            )
            if next_incomplete:
                response_parts.append(f"审阅通过后将从第 {next_incomplete} 章继续。")
        elif next_incomplete:
            response_parts.append(f"下一待完成章节：第 {next_incomplete} 章。")
        elif all_chapters_complete:
            response_parts.append("当前任务池中的章节任务已全部完成。")
        elif stop_reason_value:
            response_parts.append("章节任务尚未完成：上游任务已停止，请先处理当前停止原因。")
        else:
            response_parts.append("章节任务尚未开始：尚未生成可执行大纲。")
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

        response_payload = {
            "agent_name": "Coordinator",
            "action": "create_novel",
            "response": "\n".join(response_parts),
            "is_complete": all_chapters_complete,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "output_dir": str(project_dir),
            "focus_module": "write",
            "focus_chapter": next_incomplete or (0 if all_chapters_complete else 1),
            "awaiting_user_review": is_chapter_settings_break,
            "resume_endpoint": "/api/v1/contract/resume" if is_review_break else "",
            "params": {
                **requirements,
                "persisted_paths": persisted_paths,
                "execution_agents": completed_agents,
                "creation_contract": init_result.get("creation_contract", contract_payload) if isinstance(init_result, dict) else contract_payload,
                "task_pool": task_pool,
                "collab_execution_trace": collab_execution_trace,
                "project_ready_task_execution": execute_result,
                "stop_reason": stop_reason_value,
                "stopped_on_task_type": stopped_on_task_type,
                "awaiting_user_review": is_chapter_settings_break,
            },
        }
        if stop_reason_value == "task_failed":
            response_payload["status"] = "failed"
            response_payload["error"] = "task_failed"
        elif is_review_break:
            response_payload["status"] = "needs_review"
        return response_payload

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

        task_graph_preview = self._build_contract_task_preview(task_graph)
        preview_tasks: List[str] = []
        for item in task_graph_preview[:6]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("task_type") or "").strip()
            status = str(item.get("preview_status") or "").strip()
            suffix = "（已完成，将复用）" if status == "reuse" else ""
            if title:
                preview_tasks.append(f"- {title}{suffix}")

        style_items = constraints.get("style", []) if isinstance(constraints, dict) else []
        style_text = "、".join([str(item).strip() for item in style_items if str(item).strip()]) or "未特别指定"
        quality_text = "、".join([str(item).strip() for item in quality_rules if str(item).strip()]) or "未特别指定"
        deliverables_text = (
            "\n".join([f"- {_format_plan_deliverable_label(item)}" for item in deliverables[:8]])
            if isinstance(deliverables, list) and deliverables
            else "- 暂无"
        )
        agents_text = "、".join([
            _get_user_visible_agent_name(item)
            for item in agent_candidates[:12]
            if str(item).strip()
        ]) or "待定"
        task_preview_text = "\n".join(preview_tasks) if preview_tasks else "- 暂无任务预览"
        target_word_count = self._normalize_positive_int(scope.get("target_word_count") or requirements.get("target_word_count"), 0)
        target_words_line = f"- 预计篇幅：约 {target_word_count} 字\n" if target_word_count else ""
        target_words_per_chapter = self._normalize_positive_int(
            scope.get("target_words_per_chapter") or requirements.get("target_words_per_chapter"),
            0,
        )
        words_per_chapter_source = str(
            scope.get("target_words_per_chapter_source")
            or requirements.get("target_words_per_chapter_source")
            or ""
        ).strip()
        if target_words_per_chapter:
            source_hint = "（用户已指定）" if words_per_chapter_source == "user" else "（按总篇幅和章节数估算，可继续调整）"
            words_per_chapter_line = f"- 每章目标字数：约 {target_words_per_chapter} 字{source_hint}\n"
        else:
            words_per_chapter_line = "- 每章目标字数：待确认（例如可回复“每章约3000字”）\n"

        discussion_note = (
            "还可以继续讨论的细节：每章目标字数、卷数/分卷方式、章节数量都可以在确认前修改。\n\n"
        )

        response = (
            "已根据当前讨论内容整理出一份“创作合同草案”，现在不会直接开始创作。\n\n"
            "请先确认以下方案：\n\n"
            f"- 类型：{scope.get('novel_type') or requirements.get('novel_type') or '未指定'}\n"
            f"- 主题：{scope.get('theme') or requirements.get('theme') or '未指定'}\n"
            f"- 主角：{scope.get('protagonist') or requirements.get('protagonist') or ('由助手自主设定' if requirements.get('ai_autonomy_requested') else '未指定')}\n"
            f"- 剧情构思：{scope.get('plot_idea') or requirements.get('plot_idea') or ('由助手自主构思' if requirements.get('ai_autonomy_requested') else '未指定')}\n"
            f"{target_words_line}"
            f"{words_per_chapter_line}"
            f"- 预计卷数：{scope.get('volume_count') or requirements.get('volume_count') or 1}\n"
            f"- 每卷章节数：{scope.get('chapters_per_volume') or requirements.get('chapters_per_volume') or 5}\n"
            f"- 总章节数：{scope.get('total_chapters') or '未计算'}\n"
            f"- 风格约束：{style_text}\n"
            f"- 质量规则：{quality_text}\n\n"
            f"{discussion_note}"
            "计划产物：\n"
            f"{deliverables_text}\n\n"
            "候选创作助手：\n"
            f"{agents_text}\n\n"
            "任务预览：\n"
            f"{task_preview_text}\n\n"
            "如果方案无误，请点击“确认当前任务并开始”，系统会进入正式执行阶段。"
        )

        display_contract_payload = dict(contract_payload)
        display_contract_payload["task_graph_preview"] = task_graph_preview

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
                "creation_contract": display_contract_payload,
                "contract_status": "draft",
                "task_graph_draft": task_graph_preview,
            },
        }

    def _build_contract_task_preview(self, task_graph: Any) -> List[Dict[str, Any]]:
        """Return task preview rows annotated with current project reuse status."""
        if not isinstance(task_graph, list):
            return []

        try:
            from ..project_manager import get_project_manager

            pm = get_project_manager()
        except Exception:
            pm = None

        completed_types: Set[str] = set()
        completed_chapters: Set[int] = set()

        def _has_payload(data_type: str) -> bool:
            if pm is None:
                return False
            try:
                payload = pm.load_project_data(data_type)
            except Exception:
                return False
            if isinstance(payload, list):
                return any(bool(item) for item in payload)
            if isinstance(payload, dict):
                return any(value not in ({}, [], "", None) for value in payload.values())
            return bool(payload)

        if _has_payload("worldbuilding"):
            completed_types.add("build_world")
        if _has_payload("characters"):
            completed_types.add("build_characters")
        if _has_payload("outline"):
            completed_types.add("build_outline")
        if _has_payload("chapter_settings"):
            completed_types.add("chapter_settings")

        if pm is not None:
            try:
                chapter_rows = pm.load_project_data("chapters")
            except Exception:
                chapter_rows = []
            if isinstance(chapter_rows, list):
                for index, row in enumerate(chapter_rows, start=1):
                    if not isinstance(row, dict):
                        continue
                    chapter_number = self._normalize_positive_int(
                        row.get("chapter_number") or row.get("chapter") or row.get("number"),
                        index,
                    )
                    content = strip_internal_author_markers(row.get("content"))
                    if chapter_number and content:
                        completed_chapters.add(chapter_number)

        preview_rows: List[Dict[str, Any]] = []
        for item in task_graph:
            if not isinstance(item, dict):
                continue
            task_type = str(item.get("task_type") or "").strip()
            row = dict(item)
            is_reuse = task_type in completed_types
            if task_type == "write_chapter":
                inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
                chapter_number = self._normalize_positive_int(inputs.get("chapter_number"), 0)
                if chapter_number and chapter_number not in completed_chapters:
                    existing = self._load_existing_chapter_result(chapter_number, {})
                    if existing:
                        completed_chapters.add(chapter_number)
                is_reuse = bool(chapter_number and chapter_number in completed_chapters)
            row["preview_status"] = "reuse" if is_reuse else "pending"
            preview_rows.append(row)
        return preview_rows

    def _outline_to_project_rows(self, outline_data: Any) -> List[Dict[str, Any]]:
        timestamp = datetime.now().isoformat()
        overview = build_outline_overview_row(outline_data, timestamp=timestamp)
        return [overview] if overview else []

    def _chapter_rows_from_settings(self, settings_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(settings_rows, start=1):
            if not isinstance(row, dict):
                continue
            chapter_number = self._normalize_positive_int(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            title = str(row.get("name") or row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
            summary = str(
                row.get("description")
                or row.get("writing_goal")
                or row.get("chapter_goal")
                or row.get("scene_goal")
                or row.get("key_event")
                or row.get("event")
                or ""
            ).strip()
            rows.append({
                "chapter_number": chapter_number,
                "title": title,
                "summary": summary,
                "content": "",
                "chapter_goal": row.get("chapter_goal") or row.get("writing_goal") or "",
                "writing_goal": row.get("writing_goal") or row.get("chapter_goal") or "",
                "scene_goal": row.get("scene_goal", ""),
                "key_event": row.get("key_event") or row.get("event") or "",
                "conflict": row.get("conflict", ""),
                "emotion": row.get("emotion", ""),
                "ending_hook": row.get("ending_hook") or row.get("hook") or "",
                "plot_thread": row.get("plot_thread"),
                "source": "chapter_settings",
            })
        return self._sort_chapter_rows(rows)

    def _load_project_executable_chapter_rows(self) -> List[Dict[str, Any]]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        chapter_rows = pm.load_project_data("chapters")
        chapter_rows = [row for row in chapter_rows if isinstance(row, dict)] if isinstance(chapter_rows, list) else []

        chapter_settings = pm.load_project_data("chapter_settings")
        chapter_settings_rows = (
            self._chapter_rows_from_settings([row for row in chapter_settings if isinstance(row, dict)])
            if isinstance(chapter_settings, list)
            else []
        )
        if chapter_settings_rows:
            existing_by_number: Dict[int, Dict[str, Any]] = {}
            for index, row in enumerate(chapter_rows, start=1):
                number = self._normalize_positive_int(
                    row.get("chapter_number") or row.get("chapter") or row.get("number"),
                    index,
                )
                existing_by_number[number] = row
            merged_rows: List[Dict[str, Any]] = []
            for row in chapter_settings_rows:
                number = self._normalize_positive_int(row.get("chapter_number"), len(merged_rows) + 1)
                merged = dict(row)
                existing = existing_by_number.get(number)
                if isinstance(existing, dict):
                    existing_content = strip_internal_author_markers(existing.get("content"))
                    if existing_content:
                        merged["content"] = existing_content
                    if str(existing.get("title") or "").strip() and not str(merged.get("title") or "").strip():
                        merged["title"] = str(existing.get("title")).strip()
                merged_rows.append(merged)
            return self._sort_chapter_rows(merged_rows)

        if chapter_rows:
            return self._sort_chapter_rows(chapter_rows)

        if self.coordinator is not None:
            load_rows = getattr(self.coordinator, "_load_project_chapter_rows", None)
            if callable(load_rows):
                try:
                    coordinator_rows = extract_outline_chapter_rows(load_rows())
                    if not coordinator_rows:
                        coordinator_rows = derive_chapter_seed_rows_from_outline(load_rows())
                    if coordinator_rows:
                        return self._sort_chapter_rows(coordinator_rows)
                except Exception:
                    pass

        outline_payload = pm.load_project_data("outline")
        rows = extract_outline_chapter_rows(outline_payload)
        if not rows:
            rows = derive_chapter_seed_rows_from_outline(outline_payload)
        return self._sort_chapter_rows(rows)

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
    def _sync_eventlines_from_outline(outline_data: Any) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        generated_rows = extract_eventlines_from_outline(outline_data)
        if not generated_rows:
            return {"eventline_count": 0, "status": "skipped"}

        pm = get_project_manager()
        character_rows = pm.load_project_data("characters")
        generated_rows = enrich_eventlines_with_character_participants(generated_rows, character_rows)
        existing_rows = pm.load_project_data("eventlines")
        merged_rows = merge_eventline_rows(existing_rows, generated_rows)
        merged_rows = enrich_eventlines_with_character_participants(merged_rows, character_rows)
        if merged_rows != existing_rows:
            try:
                from ..library_service import get_library_service
                svc = get_library_service()
                svc.upsert_from_legacy("eventlines", merged_rows)
            except Exception as e:
                logger.warning(f"[Router] Library eventlines write failed: {e}")
            pm.save_project_data("eventlines", merged_rows)
            return {
                "eventline_count": len(generated_rows),
                "merged_count": len(merged_rows),
                "status": "updated",
            }
        return {
            "eventline_count": len(generated_rows),
            "merged_count": len(merged_rows),
            "status": "unchanged",
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

    @staticmethod
    def _merge_named_project_rows(existing_rows: List[Dict[str, Any]], new_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = [dict(row) for row in existing_rows if isinstance(row, dict)]
        index_by_key: Dict[str, int] = {}
        for index, row in enumerate(merged):
            key = str(row.get("id") or row.get("name") or row.get("title") or "").strip().lower()
            if key and key not in index_by_key:
                index_by_key[key] = index
        for row in new_rows:
            if not isinstance(row, dict):
                continue
            row_copy = dict(row)
            key = str(row_copy.get("id") or row_copy.get("name") or row_copy.get("title") or "").strip().lower()
            if key and key in index_by_key:
                merged[index_by_key[key]].update(row_copy)
            else:
                if key:
                    index_by_key[key] = len(merged)
                merged.append(row_copy)
        return merged

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
        eventlines: List[Dict[str, Any]] = []
        if pm.current_project_id:
            try:
                world_summary = self._summarize_worldbuilding_payload(pm.load_project_data("worldbuilding"))
            except Exception:
                world_summary = ""
            try:
                eventline_payload = pm.load_project_data("eventlines")
                if isinstance(eventline_payload, list):
                    eventlines = [row for row in eventline_payload if isinstance(row, dict)]
            except Exception:
                eventlines = []
        return {
            "user_request": message,
            "recent_discussion": self._summarize_recent_discussion(context),
            "discussion_context": self._build_discussion_context(context, message),
            "world_summary": world_summary,
            "outline_rows": outline_rows,
            "eventlines": eventlines,
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
        chapters_dir = pm.get_chapters_dir()
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
        chapter_content = strip_internal_author_markers(row.get("content"))
        if not chapter_content and chapter_path:
            try:
                chapter_content = strip_internal_author_markers(
                    Path(chapter_path).read_text(encoding="utf-8")
                )
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

    @staticmethod
    def _is_global_outline_overview_row(row: Dict[str, Any]) -> bool:
        title = str(row.get("title") or row.get("name") or "").strip()
        return (
            title == "主线大纲"
            or bool(row.get("global_outline"))
            or bool(row.get("volume_plan"))
            or bool(row.get("volumes"))
        )

    @classmethod
    def _sort_chapter_rows(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            copied = dict(row)
            copied["chapter_number"] = cls._normalize_positive_int(
                copied.get("chapter_number") or copied.get("chapter") or copied.get("number"),
                index,
            )
            normalized.append(copied)
        return sorted(normalized, key=lambda item: int(item.get("chapter_number") or 0))

    @classmethod
    def _chapter_rows_with_slot(
        cls,
        rows: List[Dict[str, Any]],
        chapter_number: int,
        timestamp: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        by_number: Dict[int, Dict[str, Any]] = {}
        for row in cls._sort_chapter_rows([row for row in rows if isinstance(row, dict)]):
            number = cls._normalize_positive_int(row.get("chapter_number"), len(by_number) + 1)
            if number not in by_number:
                by_number[number] = row
                continue
            existing = by_number[number]
            if not str(existing.get("content") or "").strip() and str(row.get("content") or "").strip():
                by_number[number] = row

        target_number = max(1, int(chapter_number or 1))
        for number in range(1, target_number + 1):
            by_number.setdefault(
                number,
                {
                    "chapter_number": number,
                    "title": f"第{number}章",
                    "summary": "",
                    "content": "",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        ordered_rows = [by_number[number] for number in sorted(by_number)]
        return ordered_rows, by_number[target_number]

    async def _persist_chapter_result(self, chapter_result: Dict[str, Any], outline_rows: List[Dict[str, Any]]) -> Dict[str, str]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_path = pm.get_project_data_path("outline")
        outline_existed_before = outline_path.exists()
        chapters_path = pm.get_project_data_path("chapters")
        chapters_existed_before = chapters_path.exists()
        chapter_number = self._normalize_positive_int(
            chapter_result.get("chapter_number", chapter_result.get("number")),
            1,
        )
        chapter_title = str(
            chapter_result.get("chapter_title")
            or chapter_result.get("title")
            or f"第{chapter_number}章"
        ).strip() or f"第{chapter_number}章"
        chapter_content = strip_internal_author_markers(chapter_result.get("content"))
        timestamp = datetime.now().isoformat()

        chapter_rows = pm.load_project_data("chapters")
        if not isinstance(chapter_rows, list) or not any(isinstance(row, dict) for row in chapter_rows):
            chapter_rows = [
                dict(row) for row in outline_rows
                if isinstance(row, dict) and not self._is_global_outline_overview_row(row)
            ]
        chapter_rows, row = self._chapter_rows_with_slot(chapter_rows, chapter_number, timestamp)
        row["chapter_number"] = chapter_number
        row["title"] = chapter_title
        row["content"] = chapter_content
        row["updated_at"] = timestamp

        pm.save_project_data("chapters", chapter_rows)

        legacy_outline_rows = pm.load_project_data("outline")
        if (
            isinstance(legacy_outline_rows, list)
            and legacy_outline_rows
            and not all(
                self._is_global_outline_overview_row(row)
                for row in legacy_outline_rows
                if isinstance(row, dict)
            )
        ):
            legacy_rows, legacy_row = self._chapter_rows_with_slot(legacy_outline_rows, chapter_number, timestamp)
            legacy_row["chapter_number"] = chapter_number
            legacy_row["title"] = chapter_title
            legacy_row["content"] = chapter_content
            legacy_row["updated_at"] = timestamp
            pm.save_project_data("outline", legacy_rows)

        chapters_dir = pm.get_chapters_dir()
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
            "chapters_path": str(chapters_path),
            "chapters_status": "updated" if chapters_existed_before else "created",
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
        outline_title = outline_data.get("title") if isinstance(outline_data, dict) else ""
        row_title = outline_rows[0].get("novel_title") if outline_rows else ""
        project_title = str(outline_title or row_title or (current_project.name if current_project else "") or "未命名项目").strip() or "未命名项目"
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
        from ..worldbuilding_persistence import persist_worldbuilding_project_data

        persist_worldbuilding_project_data(payload)

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
    def _worldbuilding_missing_info(world_data: Any) -> List[str]:
        if not isinstance(world_data, dict):
            return []
        status = str(world_data.get("status") or "").strip().lower()
        missing: List[str] = []
        raw_missing = world_data.get("missing_info")
        if isinstance(raw_missing, list):
            missing.extend(str(item).strip() for item in raw_missing if str(item).strip())
        elif isinstance(raw_missing, str) and raw_missing.strip():
            missing.append(raw_missing.strip())
        if status in {"missing_info", "needs_input", "needs_confirmation", "pending_confirmation"} and not missing:
            missing.append("缺少可用于构建世界观的关键信息")
        return missing

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
        creation_requirements = dict((context or {}).get("creation_requirements") or {})

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

        if not theme:
            theme = str(creation_requirements.get("theme") or "").strip()
        if not plot_idea:
            plot_idea = str(creation_requirements.get("plot_idea") or "").strip()
        if not protagonist:
            protagonist = str(creation_requirements.get("protagonist") or "").strip() or protagonist
        if novel_type == "未分类":
            novel_type = str(creation_requirements.get("novel_type") or "").strip() or novel_type
        ai_autonomy_requested = bool(
            (context or {}).get("ai_autonomy_requested")
            or creation_requirements.get("ai_autonomy_requested")
            or collected_info.get("ai_autonomy_requested")
        )
        autonomous_brief = str(
            (context or {}).get("autonomous_brief")
            or creation_requirements.get("autonomous_brief")
            or ""
        ).strip()
        if ai_autonomy_requested and not autonomous_brief:
            autonomous_brief = (
                "用户已授权助手自主安排未指定的角色姓名、身份、人物关系和人物弧线；"
                "请在已给定题材、主题、篇幅与讨论方向内主动创作。"
            )

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

        request_mode = str(
            (context or {}).get("character_request_mode")
            or ("save" if (context or {}).get("chat_auto_save_enabled") else "draft")
        ).strip() or "draft"
        if ai_autonomy_requested and request_mode == "draft":
            request_mode = "autonomous_draft"

        return {
            "user_request": message,
            "novel_type": novel_type,
            "theme": theme,
            "plot_idea": plot_idea,
            "protagonist": protagonist,
            "character_prompt": cleaned_prompt,
            "character_request": cleaned_prompt or autonomous_brief or message,
            "character_role": character_role,
            "character_name": character_name,
            "recent_discussion": self._summarize_recent_discussion(context),
            "discussion_context": self._build_discussion_context(context, message),
            "world_summary": world_summary,
            "existing_characters_summary": existing_characters_summary,
            "request_mode": request_mode,
            "ai_autonomy_requested": ai_autonomy_requested,
            "autonomous_brief": autonomous_brief,
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

    @staticmethod
    def _message_requests_character_cards(message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        profile_keywords = (
            "角色卡",
            "人设卡",
            "人物卡",
            "角色档案",
            "人物档案",
            "角色设定",
            "人物设定",
            "主角设定",
        )
        action_keywords = ("创建", "生成", "设计", "写", "做", "补全", "完善", "看看")
        if any(keyword in text for keyword in ("创建角色", "生成角色", "设计角色", "写角色")):
            return True
        return any(keyword in text for keyword in profile_keywords) and any(keyword in text for keyword in action_keywords)

    @staticmethod
    def _review_worldbuilding_for_project_setup(world_data: Any) -> Dict[str, Any]:
        issues: List[str] = []
        if not isinstance(world_data, dict) or not world_data:
            issues.append("世界观结果为空或不是对象")
            return {"passed": False, "issues": issues}

        meaningful_keys = [
            key for key, value in world_data.items()
            if value not in (None, "", [], {})
        ]
        if len(meaningful_keys) < 3:
            issues.append("世界观有效字段过少")

        name = str(world_data.get("world_name") or world_data.get("name") or "").strip()
        if name in {"", "未命名世界", "默认世界"}:
            issues.append("世界观缺少可识别的世界名称或核心标识")

        core_text = json.dumps(world_data, ensure_ascii=False)
        if len(core_text.strip()) < 120:
            issues.append("世界观内容过短，无法支撑后续角色卡")

        return {"passed": not issues, "issues": issues}

    @staticmethod
    def _review_characters_for_project_setup(characters: Any) -> Dict[str, Any]:
        issues: List[str] = []
        if not isinstance(characters, list) or not characters:
            issues.append("角色卡结果为空")
            return {"passed": False, "issues": issues}

        placeholder_names = {"主角", "男主", "女主", "角色", "人物", "角色1", "人物1"}
        valid_count = 0
        for item in characters:
            if not isinstance(item, dict):
                issues.append("存在非对象角色项")
                continue
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not name or name in placeholder_names:
                issues.append("角色缺少明确姓名")
                continue
            if len(description) < 6:
                issues.append(f"角色 {name} 简介过短")
                continue
            valid_count += 1

        if valid_count <= 0:
            issues.append("没有通过基础审查的角色卡")
        return {"passed": valid_count > 0 and not issues, "issues": issues}

    @staticmethod
    def _build_autonomous_creation_note(requirements: Dict[str, Any]) -> str:
        if not bool((requirements or {}).get("ai_autonomy_requested", False)):
            return ""
        return (
            "用户已授权助手自主安排未指定内容；主角姓名、人物关系、剧情主线、世界观细节和爽点节奏"
            "都可由AI在已给定题材、主题、篇幅与讨论方向内主动创作。"
        )

    @staticmethod
    def _load_workflow_category_definitions() -> List[Dict[str, Any]]:
        categories = [dict(item) for item in BUILTIN_CATEGORY_DEFINITIONS]
        try:
            from ..project_manager import get_project_manager

            custom_categories = get_project_manager().load_project_state("knowledge_categories", default=[])
            if isinstance(custom_categories, list):
                for item in custom_categories:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or item.get("id") or "").strip()
                    if not key:
                        continue
                    categories.append({
                        "id": str(item.get("id") or key).strip(),
                        "key": key,
                        "name": str(item.get("name") or key).strip(),
                        "aliases": [str(alias) for alias in item.get("aliases") or [] if str(alias).strip()],
                        "builtin": bool(item.get("builtin", False)),
                    })
        except Exception as exc:
            logger.debug(f"[Router] load workflow category definitions failed: {exc}")
        return categories

    @classmethod
    def _category_definition_by_key(cls, key: str) -> Dict[str, Any]:
        normalized = str(key or "").strip()
        for item in cls._load_workflow_category_definitions():
            if str(item.get("key") or "").strip() == normalized:
                return dict(item)
        return {"key": normalized, "name": normalized, "aliases": [], "builtin": False}

    def _target_categories_from_explicit_command(
        self,
        message: str,
        explicit_command: Optional[Dict[str, Any]],
    ) -> List[str]:
        if not isinstance(explicit_command, dict):
            return []
        name = str(explicit_command.get("name") or "").strip().lower()
        if name == "worldbuild":
            categories = ["worldbuilding"]
            if self._message_requests_character_cards(message):
                categories.append("characters")
            return categories
        if name == "character":
            return ["characters"]
        if name == "outline":
            return ["outline"]
        if name == "chapter":
            return ["chapters"]
        if name == "projectdata":
            category = explicit_command.get("category")
            key = str((category or {}).get("key") or "").strip() if isinstance(category, dict) else ""
            return [key] if key else []
        return []

    def _target_categories_from_intent(
        self,
        intent: UserIntent,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> List[str]:
        if intent == UserIntent.CREATE_CHARACTER:
            return ["characters"]
        if intent == UserIntent.CREATE_EVENTLINES:
            return ["eventlines"]
        if intent == UserIntent.CREATE_DETAIL_OUTLINE:
            return ["detail_settings"]
        if intent == UserIntent.CREATE_CHAPTER_SETTINGS:
            return ["chapter_settings"]

        requested_category = (context or {}).get("requested_knowledge_category") if isinstance(context, dict) else None
        if isinstance(requested_category, dict) and requested_category.get("key"):
            return [str(requested_category.get("key")).strip()]

        return detect_target_categories(
            message,
            knowledge_categories=self._load_workflow_category_definitions(),
        )

    @staticmethod
    def _workflow_operation_from_message(message: str) -> str:
        text = str(message or "").strip()
        if any(token in text for token in ("修改", "改成", "调整", "修订", "重写", "不是", "不对")):
            return "revise"
        return "create"

    @staticmethod
    def _dedupe_workflow_categories(categories: List[str]) -> List[str]:
        normalized: List[str] = []
        for category in categories or []:
            key = str(category or "").strip()
            if key and key not in normalized:
                normalized.append(key)
        return normalized

    @staticmethod
    def _workflow_category_allowed_keys(category_definitions: List[Dict[str, Any]]) -> Set[str]:
        keys = {str(item.get("key") or "").strip() for item in category_definitions or []}
        keys.update(str(item.get("key") or "").strip() for item in BUILTIN_CATEGORY_DEFINITIONS)
        return {key for key in keys if key}

    @staticmethod
    def _normalize_workflow_operation(value: Any, fallback: str = "create") -> str:
        text = str(value or "").strip().lower()
        if text in {"revise", "revision", "modify", "rewrite", "update", "edit", "修改", "修订", "重写", "调整"}:
            return "revise"
        if text in {"create", "write", "generate", "continue", "生成", "创作", "写", "续写"}:
            return "create"
        return "revise" if str(fallback or "").strip() == "revise" else "create"

    @staticmethod
    def _message_wants_chapter_body_from_settings(message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        if any(token in text for token in ("按章纲写", "根据章纲写", "依照章纲写", "照章纲写")):
            return True
        if "正文" in text and any(token in text for token in ("章纲", "每章", "每一章", "章节", "章")):
            return True
        return False

    @staticmethod
    def _message_requests_chapter_settings_generation(message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        direct_terms = (
            "生成章纲",
            "创建章纲",
            "写章纲",
            "设计章纲",
            "补全章纲",
            "完善章纲",
            "章纲设定",
            "章节设定",
            "章节规划",
        )
        if any(token in text for token in direct_terms):
            return True
        return bool(re.search(r"(先|然后|再).{0,10}(章纲|章节设定|章节规划)", text))

    def _adjust_categories_for_chapter_body_request(
        self,
        categories: List[str],
        message: str,
        directive_payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        adjusted = self._dedupe_workflow_categories(categories)
        if not self._message_wants_chapter_body_from_settings(message):
            return adjusted

        payload = directive_payload if isinstance(directive_payload, dict) else {}
        write_source = str(payload.get("write_source") or payload.get("source") or "").strip()
        references_chapter_settings = (
            "chapter_settings" in adjusted
            or write_source == "chapter_settings"
            or "章纲" in str(message or "")
        )
        if not references_chapter_settings:
            return adjusted

        should_generate_settings = self._message_requests_chapter_settings_generation(message)
        if "chapters" not in adjusted:
            adjusted.append("chapters")
        if "chapter_settings" in adjusted and not should_generate_settings:
            adjusted = [category for category in adjusted if category != "chapter_settings"]
        return adjusted

    @staticmethod
    def _count_project_data_rows(data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            if isinstance(data.get("items"), list):
                return len(data.get("items") or [])
            if isinstance(data.get("chapters"), list):
                return len(data.get("chapters") or [])
            return 1 if data else 0
        return 0

    def _build_workflow_execution_snapshot(self, category_definitions: List[Dict[str, Any]]) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        try:
            from ..project_manager import get_project_manager

            pm = get_project_manager()
            snapshot["project_id"] = str(getattr(pm, "current_project_id", "") or "")
            for item in category_definitions or []:
                key = str(item.get("key") or "").strip()
                if not key:
                    continue
                try:
                    snapshot[f"{key}_count"] = self._count_project_data_rows(pm.load_project_data(key))
                except Exception:
                    snapshot[f"{key}_count"] = 0
        except Exception as exc:
            logger.debug(f"[{self.name}] 构建工作流执行快照失败: {exc}")
        return snapshot

    def _fallback_workflow_execution_directive(
        self,
        *,
        message: str,
        categories: List[str],
        operation: str,
        reason: str,
    ) -> Dict[str, Any]:
        adjusted_categories = self._adjust_categories_for_chapter_body_request(categories, message)
        return {
            "target_categories": adjusted_categories,
            "operation": self._normalize_workflow_operation(operation),
            "write_source": "chapter_settings" if "章纲" in str(message or "") else "",
            "chapter_scope": "all" if any(token in str(message or "") for token in ("每一章", "每章", "全部", "所有")) else "unknown",
            "chapter_number": self._chapter_number_from_message_or_context(message, None),
            "requires_confirmation": False,
            "confidence": 0.0,
            "reason": reason,
            "source": "local_rules",
        }

    def _normalize_workflow_execution_directive(
        self,
        payload: Dict[str, Any],
        *,
        message: str,
        fallback_categories: List[str],
        fallback_operation: str,
        category_definitions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        allowed_keys = self._workflow_category_allowed_keys(category_definitions)
        raw_categories = payload.get("target_categories") or payload.get("categories") or []
        if isinstance(raw_categories, str):
            raw_categories = re.split(r"[,，、\s]+", raw_categories)
        model_categories = [
            str(category or "").strip()
            for category in raw_categories
            if str(category or "").strip() in allowed_keys
        ] if isinstance(raw_categories, list) else []

        categories = self._dedupe_workflow_categories(model_categories or fallback_categories)
        categories = self._adjust_categories_for_chapter_body_request(categories, message, payload)

        try:
            confidence = float(payload.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence and confidence < 0.35:
            fallback = self._fallback_workflow_execution_directive(
                message=message,
                categories=fallback_categories,
                operation=fallback_operation,
                reason="模型判断置信度过低，已回退到本地规则",
            )
            fallback["model_confidence"] = confidence
            return fallback

        chapter_number = self._normalize_positive_int(
            payload.get("chapter_number"),
            self._chapter_number_from_message_or_context(message, None),
        )
        return {
            "target_categories": categories,
            "operation": self._normalize_workflow_operation(payload.get("operation"), fallback_operation),
            "write_source": str(payload.get("write_source") or payload.get("source") or "").strip()[:80],
            "chapter_scope": str(payload.get("chapter_scope") or payload.get("scope") or "unknown").strip()[:40],
            "chapter_number": chapter_number,
            "requires_confirmation": bool(payload.get("requires_confirmation", False)),
            "confidence": confidence,
            "reason": str(payload.get("reason") or "").strip()[:400],
            "source": "model",
        }

    async def _resolve_serial_workflow_execution_directive(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        target_categories: List[str],
        operation: str,
        category_definitions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback = self._fallback_workflow_execution_directive(
            message=message,
            categories=target_categories,
            operation=operation,
            reason="使用本地规则生成执行指令",
        )
        if not self._can_call_model_for_requirement_extraction():
            return fallback

        category_brief = [
            {
                "key": str(item.get("key") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "aliases": [str(alias) for alias in item.get("aliases") or [] if str(alias).strip()],
            }
            for item in category_definitions or []
            if str(item.get("key") or "").strip()
        ]
        prompt = (
            "你是本地小说创作执行器的语义判断层。你的任务不是写正文，而是把用户的话解释成可执行指令。\n"
            "请理解中文语义，尤其区分：\n"
            "1. “写/生成章纲”是 chapter_settings；\n"
            "2. “按章纲写正文/写每一章”是 chapters，write_source 应为 chapter_settings；\n"
            "3. “先写章纲再按章纲写正文”需要 target_categories 同时包含 chapter_settings 和 chapters；\n"
            "4. 如果用户只是引用已有章纲来写正文，不要把 chapter_settings 当作要重新生成的目标。\n\n"
            "只能返回严格 JSON，不要 Markdown，不要解释：\n"
            "{\n"
            '  "should_execute": true,\n'
            '  "target_categories": ["chapters"],\n'
            '  "operation": "create",\n'
            '  "write_source": "chapter_settings",\n'
            '  "chapter_scope": "all",\n'
            '  "chapter_number": 0,\n'
            '  "requires_confirmation": false,\n'
            '  "confidence": 0.0,\n'
            '  "reason": ""\n'
            "}\n\n"
            f"允许的 target_categories：\n{json.dumps(category_brief, ensure_ascii=False)}\n\n"
            f"本地规则初判：\n{json.dumps(fallback, ensure_ascii=False)}\n\n"
            f"项目现有资料快照：\n{json.dumps(self._build_workflow_execution_snapshot(category_definitions), ensure_ascii=False)}\n\n"
            f"完整讨论上下文：\n{self._build_discussion_context(context, message)}\n\n"
            f"当前用户消息：\n{message}"
        )
        try:
            response = await self.call_llm(
                [{"role": "user", "content": prompt}],
                temperature=AGENT_TEMPERATURE.SUMMARY_STABLE,
                max_tokens=700,
            )
        except Exception as exc:
            logger.warning(f"[{self.name}] 模型解析工作流执行意图失败，使用本地兜底: {exc}")
            return fallback

        payload = self._extract_json_object(str(response or ""))
        if not payload or payload.get("should_execute") is False:
            return fallback
        return self._normalize_workflow_execution_directive(
            payload,
            message=message,
            fallback_categories=fallback.get("target_categories") or target_categories,
            fallback_operation=fallback.get("operation") or operation,
            category_definitions=category_definitions,
        )

    @staticmethod
    def _safe_workflow_state_key(run_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(run_id or "").strip())[:80]
        return f"creative_workflow_run_{safe or 'latest'}"

    def _save_creative_workflow_run(self, run: CreativeWorkflowRun) -> None:
        try:
            from ..project_manager import get_project_manager

            pm = get_project_manager()
            if not getattr(pm, "current_project_id", ""):
                return
            payload = run.to_dict()
            pm.save_project_state(self._safe_workflow_state_key(run.run_id), payload)
            pm.save_project_state("latest_creative_workflow_run", {
                "run_id": run.run_id,
                "status": run.status,
                "updated_at": run.updated_at,
            })
        except Exception as exc:
            logger.debug(f"[Router] save creative workflow run failed: {exc}")

    async def _review_creative_workflow_artifact(
        self,
        task: WorkflowTask,
        artifact: Artifact,
        workflow_context: WorkflowContext,
        basic_review: ReviewResult,
    ) -> Optional[ReviewResult]:
        evaluator = getattr(self.coordinator, "evaluator", None) if self.coordinator else None
        if evaluator is None:
            from .evaluator import EvaluatorAgent

            evaluator = EvaluatorAgent()
        review_method = getattr(evaluator, "review_artifact", None)
        if not callable(review_method):
            return basic_review
        return await review_method(
            task_id=task.task_id,
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            artifact=artifact.content,
            revision_target=task.target_agent,
            workflow_context=workflow_context,
        )

    async def resume_creative_workflow_run(
        self,
        run_payload: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.coordinator:
            return {
                "agent_name": "Coordinator",
                "action": "creative_workflow_resume",
                "response": "协调器当前不可用，无法恢复串行创作工作流。",
                "error": "coordinator_unavailable",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        run = CreativeWorkflowRun.from_dict(run_payload)
        run.status = "running"
        run.set_current(agent="Coordinator", stage="resuming", status="running")
        self._save_creative_workflow_run(run)

        latest_interruption = ""
        if run.user_interruptions:
            latest_interruption = run.user_interruptions[-1].message
        resume_message = run.user_request
        if latest_interruption:
            resume_message = f"{run.user_request}\n\n用户最新修正：{latest_interruption}"

        async def emit_run_progress(current_run: CreativeWorkflowRun, payload: Dict[str, Any]) -> None:
            self._save_creative_workflow_run(current_run)
            await self._emit_progress(context, payload)

        executor = CreativeWorkflowExecutor(
            run=run,
            task_runner=lambda task, workflow_context: self._run_creative_workflow_task(
                task=task,
                workflow_context=workflow_context,
                message=resume_message,
                context=context,
            ),
            progress_emitter=emit_run_progress,
            pause_checker=self._check_coordinator_pause_cancel,
            review_runner=self._review_creative_workflow_artifact,
        )
        completed_run = await executor.execute()
        self._save_creative_workflow_run(completed_run)
        is_complete = completed_run.status == "completed"
        return {
            "agent_name": "Coordinator",
            "action": "creative_workflow_resume",
            "response": self._build_serial_creative_workflow_response(completed_run),
            "is_complete": is_complete,
            "error": "" if is_complete else self._last_creative_workflow_error(completed_run),
            "run_id": completed_run.run_id,
            "created_files": completed_run.created_files,
            "updated_files": completed_run.updated_files,
            "reused_files": completed_run.reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": str((completed_run.canonical_context.active_artifact or {}).get("artifact_type") or ""),
            "focus_chapter": 0,
            "params": {
                "creative_workflow_run": completed_run.to_dict(),
                "operation": completed_run.workflow_plan.operation,
            },
        }

    async def _execute_serial_creative_workflow_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        target_categories: List[str],
        action: str = "creative_workflow",
        operation: str = "create",
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        categories = [str(item or "").strip() for item in target_categories if str(item or "").strip()]
        if not self.coordinator:
            return {
                "agent_name": "Coordinator",
                "action": action,
                "response": "协调器当前不可用，无法执行串行创作工作流。",
                "error": "coordinator_unavailable",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        pm = get_project_manager()
        category_definitions = self._load_workflow_category_definitions()
        execution_directive = await self._resolve_serial_workflow_execution_directive(
            message=message,
            context=context,
            target_categories=categories,
            operation=operation,
            category_definitions=category_definitions,
        )
        categories = self._dedupe_workflow_categories(execution_directive.get("target_categories") or categories)
        operation = self._normalize_workflow_operation(execution_directive.get("operation"), operation)
        if not categories:
            return {
                "agent_name": "Coordinator",
                "action": action,
                "response": "未识别到需要执行的创作资料类别。",
                "error": "empty_workflow_plan",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "params": {
                    "execution_directive": execution_directive,
                },
            }
        workflow_plan = build_workflow_plan(
            user_request=message,
            operation=operation,
            target_categories=categories,
            knowledge_categories=category_definitions,
        )
        categories = workflow_plan.target_categories
        requirements = await self._build_creation_requirements_async(context, message)
        requirements["operation"] = operation
        requirements["execution_directive"] = execution_directive
        workflow_run = CreativeWorkflowRun.create(
            project_id=str(getattr(pm, "current_project_id", "") or ""),
            user_request=message,
            workflow_plan=workflow_plan,
            canonical_context=WorkflowContext(
                original_request=message,
                confirmed_requirements=requirements,
                project_snapshot={
                    "project_id": str(getattr(pm, "current_project_id", "") or ""),
                    "project_dir": str(getattr(self.coordinator, "project_dir", "") or ""),
                },
            ),
            run_id=self._get_run_id(context) or None,
        )

        async def emit_run_progress(run: CreativeWorkflowRun, payload: Dict[str, Any]) -> None:
            self._save_creative_workflow_run(run)
            await self._emit_progress(context, payload)

        executor = CreativeWorkflowExecutor(
            run=workflow_run,
            task_runner=lambda task, workflow_context: self._run_creative_workflow_task(
                task=task,
                workflow_context=workflow_context,
                message=message,
                context=context,
            ),
            progress_emitter=emit_run_progress,
            pause_checker=self._check_coordinator_pause_cancel,
            review_runner=self._review_creative_workflow_artifact,
        )
        completed_run = await executor.execute()
        self._save_creative_workflow_run(completed_run)
        is_complete = completed_run.status == "completed"
        response = self._build_serial_creative_workflow_response(completed_run)
        visible_tasks = [task for task in completed_run.task_queue if task.task_type != "prepare_context"]
        result_agent_name = "Coordinator"
        if action == "creative_workflow" and len(visible_tasks) == 1:
            result_agent_name = visible_tasks[0].target_agent
        return {
            "agent_name": result_agent_name,
            "action": action,
            "response": response,
            "is_complete": is_complete,
            "error": "" if is_complete else self._last_creative_workflow_error(completed_run),
            "run_id": completed_run.run_id,
            "created_files": completed_run.created_files,
            "updated_files": completed_run.updated_files,
            "reused_files": completed_run.reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": self._focus_module_for_workflow_categories(categories),
            "focus_chapter": self._chapter_number_from_message_or_context(message, context),
            "params": {
                "target_categories": categories,
                "data_type": categories[0] if len(categories) == 1 else "",
                "operation": operation,
                "execution_directive": execution_directive,
                "creative_workflow_run": completed_run.to_dict(),
                "execution_agents": [
                    task.target_agent
                    for task in completed_run.task_queue
                    if task.task_type != "prepare_context"
                ],
            },
        }

    async def _run_creative_workflow_task(
        self,
        *,
        task: WorkflowTask,
        workflow_context: WorkflowContext,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> TaskExecutionResult:
        task_context = dict(context or {})
        task_context["workflow_context"] = workflow_context.to_dict()
        task_context["review_feedback"] = list(workflow_context.review_feedback)
        task_type = str(task.task_type or "").strip()
        result: Dict[str, Any]

        if task_type == "worldbuilding":
            result = await self._execute_worldbuild_pipeline(message=message, context=task_context)
        elif task_type == "characters":
            task_context["character_request_mode"] = "save"
            world_payload = self._find_workflow_artifact_content(workflow_context, "worldbuilding")
            if isinstance(world_payload, dict):
                task_context["world"] = world_payload
            result = await self._execute_character_creation_pipeline(message=message, context=task_context)
        elif task_type == "outline":
            result = await self._execute_outline_pipeline(message=message, context=task_context)
        elif task_type == "eventlines":
            result = await self._execute_project_data_generation_pipeline(
                message=message,
                context=task_context,
                data_type="eventlines",
                agent_name="EventlineBuilder",
                stage="eventlines",
                label="事件线",
            )
        elif task_type == "detail_settings":
            result = await self._execute_project_data_generation_pipeline(
                message=message,
                context=task_context,
                data_type="detail_settings",
                agent_name="DetailOutlineBuilder",
                stage="detail_outlining",
                label="细纲",
            )
        elif task_type == "chapter_settings":
            result = await self._execute_project_data_generation_pipeline(
                message=message,
                context=task_context,
                data_type="chapter_settings",
                agent_name="ChapterSettingBuilder",
                stage="chapter_settings",
                label="章纲设定",
            )
        elif task_type == "chapters":
            chapter_num = self._chapter_number_from_message_or_context(message, context)
            if chapter_num <= 0:
                result = await self._execute_project_chapters_write(context=task_context)
            else:
                result = await self._execute_project_chapter_write(chapter_num=chapter_num, context=task_context) or {
                    "agent_name": "ChapterWriter",
                    "action": "write_chapter",
                    "response": f"第{chapter_num}章不存在，请先生成大纲。",
                    "error": "chapter_not_found",
                    "is_complete": False,
                }
        else:
            category = self._category_definition_by_key(task_type)
            result = await self._execute_generic_project_data_pipeline(
                message=message,
                context=task_context,
                data_type=task_type,
                label=str(category.get("name") or task_type),
                category=category,
            )

        return self._task_execution_result_from_router_result(task, result)

    def _task_execution_result_from_router_result(
        self,
        task: WorkflowTask,
        result: Dict[str, Any],
    ) -> TaskExecutionResult:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        result = result if isinstance(result, dict) else {}
        params = result.get("params") if isinstance(result.get("params"), dict) else {}
        task_type = str(task.task_type or "").strip()
        artifact = None
        target_path = ""

        if task_type == "worldbuilding":
            artifact = params.get("world")
        elif task_type == "characters":
            artifact = result.get("characters") or params.get("characters")
        elif task_type == "chapters":
            chapter_payloads = params.get("chapters") if isinstance(params.get("chapters"), list) else []
            if chapter_payloads:
                combined_content = "\n\n".join(
                    str(item.get("content") or "").strip()
                    for item in chapter_payloads
                    if isinstance(item, dict) and str(item.get("content") or "").strip()
                ).strip()
                first_chapter_number = self._normalize_positive_int(
                    (chapter_payloads[0] if isinstance(chapter_payloads[0], dict) else {}).get("chapter_number")
                    or (chapter_payloads[0] if isinstance(chapter_payloads[0], dict) else {}).get("number"),
                    0,
                )
                artifact = {
                    "content": combined_content,
                    "chapters": chapter_payloads,
                    "chapter_number": first_chapter_number,
                    "chapter_count": len(chapter_payloads),
                }
            else:
                combined_content = str(result.get("chapter_content") or result.get("response") or "").strip()
                artifact = {
                    "content": combined_content,
                    "chapter_number": params.get("chapter_number") or params.get("focus_chapter"),
                }
            persisted_paths = params.get("persisted_paths") if isinstance(params.get("persisted_paths"), dict) else {}
            target_path = str(persisted_paths.get("chapter_path") or "")
        else:
            try:
                artifact = pm.load_project_data(task_type)
            except Exception:
                artifact = params.get("rows") or params

        if not target_path:
            try:
                target_path = str(pm.get_project_data_path(task_type))
            except Exception:
                target_path = ""

        return TaskExecutionResult(
            success=bool(result.get("is_complete", result.get("success", False))) and not bool(result.get("error")),
            agent_name=str(result.get("agent_name") or task.target_agent),
            action=str(result.get("action") or task.task_type),
            response=str(result.get("response") or ""),
            artifact=artifact,
            artifact_type=task.output_type or task.task_type,
            target_path=target_path,
            created_files=[item for item in result.get("created_files") or [] if isinstance(item, dict)],
            updated_files=[item for item in result.get("updated_files") or [] if isinstance(item, dict)],
            reused_files=[item for item in result.get("reused_files") or [] if isinstance(item, dict)],
            focus_module=str(result.get("focus_module") or ""),
            focus_chapter=self._normalize_positive_int(result.get("focus_chapter"), 0),
            params=params,
            error=str(result.get("error") or ""),
        )

    @staticmethod
    def _find_workflow_artifact_content(workflow_context: WorkflowContext, artifact_type: str) -> Any:
        for artifact in (workflow_context.previous_artifacts or {}).values():
            if isinstance(artifact, dict) and artifact.get("artifact_type") == artifact_type:
                return artifact.get("content")
        return None

    def _chapter_number_from_message_or_context(self, message: str, context: Optional[Dict[str, Any]]) -> int:
        explicit_command = (context or {}).get("explicit_command") if isinstance(context, dict) else None
        if isinstance(explicit_command, dict):
            parsed = self._normalize_positive_int(explicit_command.get("chapter_number"), 0)
            if parsed > 0:
                return parsed
        try:
            entities = self._extract_entities(message, UserIntent.CONTINUE_WRITE)
            return self._normalize_positive_int(entities.get("chapter_number"), 0)
        except Exception:
            return 0

    @staticmethod
    def _focus_module_for_workflow_categories(categories: List[str]) -> str:
        if "chapters" in categories or "outline" in categories:
            return "write"
        if "characters" in categories:
            return "characters"
        return "world"

    @staticmethod
    def _last_creative_workflow_error(run: CreativeWorkflowRun) -> str:
        for task in reversed(run.completed_tasks):
            if task.error:
                return _localize_workflow_error(task.error)
        return ""

    @staticmethod
    def _build_serial_creative_workflow_response(run: CreativeWorkflowRun) -> str:
        completed = [task for task in run.completed_tasks if task.status == "completed" and task.task_type != "prepare_context"]
        failed = [task for task in run.completed_tasks if task.status == "failed"]
        lines = ["已按串行多助手工作流执行。", ""]
        lines.append("工作流计划：")
        for index, task in enumerate([task for task in run.task_queue if task.task_type != "prepare_context"], 1):
            status_map = {
                "pending": "等待中",
                "running": "执行中",
                "completed": "已完成",
                "failed": "失败",
                "revision_requested": "待修订",
            }
            status = status_map.get(task.status, task.status)
            lines.append(f"{index}. {task.title or task.task_type}：{status}")
        lines.append("")
        if failed:
            task_name = _get_user_visible_workflow_task_name(failed[-1].task_type)
            error_text = _localize_workflow_error(failed[-1].error) or "未通过审查"
            lines.append(f"当前停止在：{task_name}。原因：{error_text}")
        else:
            lines.append(f"已完成 {len(completed)} 个创作任务，并生成 {len(run.reviews)} 条审查记录。")
        return "\n".join(lines)

    async def _execute_world_and_character_pipeline(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """执行“世界观 + 角色卡”的自组织资料生成工作流。"""
        if not self.coordinator:
            return {
                "agent_name": "Coordinator",
                "action": "world_and_character_setup",
                "response": "协调器当前不可用，无法执行世界观与角色卡工作流。",
                "error": "coordinator_unavailable",
                "is_complete": False,
                "run_id": self._get_run_id(context),
            }

        from ..project_manager import get_project_manager

        pm = get_project_manager()
        requirements = await self._build_creation_requirements_async(context, message)
        workflow_plan = build_workflow_plan(
            user_request=message,
            operation="create",
            target_categories=["worldbuilding", "characters"],
        )
        workflow_run = CreativeWorkflowRun.create(
            project_id=str(getattr(pm, "current_project_id", "") or ""),
            user_request=message,
            workflow_plan=workflow_plan,
            canonical_context=WorkflowContext(
                original_request=message,
                confirmed_requirements=requirements,
                project_snapshot={
                    "project_id": str(getattr(pm, "current_project_id", "") or ""),
                    "project_dir": str(getattr(self.coordinator, "project_dir", "") or ""),
                },
            ),
            run_id=self._get_run_id(context) or None,
        )
        workflow_run.complete_task(
            task_id="prepare_context",
            task_type="prepare_context",
            target_agent="Coordinator",
            status="completed",
        )

        await self._emit_creative_workflow_progress(context, workflow_run, {
            "content": (
                "## 工作流计划\n"
                "已拆解为：1. 世界观构建 2. 独立审查 3. 角色卡生成 4. 独立审查 5. 写入资料库。"
            ),
            "current_agent": "Coordinator",
            "stage": "workflow_planning",
            "status": "running",
            "output_dir": str(self.coordinator.project_dir),
        })

        if await self._check_coordinator_pause_cancel():
            workflow_run.status = "cancelled"
            return {
                "agent_name": "Coordinator",
                "action": "world_and_character_setup",
                "response": "任务已取消，未继续生成世界观和角色卡。",
                "error": "cancelled",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": [],
                "updated_files": [],
                "reused_files": [],
                "output_dir": str(self.coordinator.project_dir),
                "params": {"creative_workflow_run": workflow_run.to_dict()},
            }

        world_data: Dict[str, Any] = {}
        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        reused_files: List[Dict[str, str]] = []
        world_review: Dict[str, Any] = {"passed": False, "issues": ["not_started"]}

        world_task_id = "create_worldbuilding"
        workflow_run.mark_task(world_task_id, "running")
        for attempt in range(2):
            if attempt == 0:
                world_data, world_created, world_updated, world_reused = await self._ensure_world_payload(requirements, context)
            else:
                feedback = "；".join(world_review.get("issues") or [])
                retry_requirements = dict(requirements)
                retry_requirements["requirements"] = (
                    f"{requirements.get('requirements') or ''}\n\n"
                    f"【独立审查退回意见】{feedback}\n"
                    "请重写世界观，必须严格继承聊天讨论中的题材、主角、核心能力与世界背景。"
                ).strip()
                world_result = await self.coordinator.generate_world(
                    novel_type=retry_requirements["novel_type"],
                    theme=retry_requirements["theme"],
                    requirements=self._build_worldbuilding_requirements_text(retry_requirements),
                )
                world_data = world_result.get("world", {}) if isinstance(world_result, dict) else {}
                if self._worldbuilding_missing_info(world_data):
                    world_created, world_updated, world_reused = [], [], []
                else:
                    self._persist_worldbuilding_project_data({"world": world_data} if isinstance(world_data, dict) else {})
                    world_path = self.coordinator.project_dir / "worldbuilding.json"
                    world_file = self._build_file_record(str(world_path), "worldbuilding", "世界观", "updated")
                    world_created, world_updated, world_reused = [], [world_file], []

            self._merge_file_records(created_files, world_created)
            self._merge_file_records(updated_files, world_updated)
            self._merge_file_records(reused_files, world_reused)
            workflow_run.created_files = created_files
            workflow_run.updated_files = updated_files
            world_artifact_id = f"{world_task_id}-artifact"
            workflow_run.add_artifact(
                Artifact(
                    artifact_id=world_artifact_id,
                    artifact_type="worldbuilding",
                    task_id=world_task_id,
                    content=world_data,
                    status="draft",
                    target_path=str(self.coordinator.project_dir / "worldbuilding.json"),
                    updated_at=datetime.now().isoformat(),
                )
            )
            world_review_result = review_artifact_basic(
                task_id=world_task_id,
                artifact_id=world_artifact_id,
                artifact_type="worldbuilding",
                artifact=world_data,
                revision_target="Worldbuilder",
            )
            workflow_run.add_review(world_review_result)
            workflow_run.add_handoff(self._make_artifact_handoff(
                artifact_id=world_artifact_id,
                artifact_type="worldbuilding",
                artifact=world_data,
                summary="世界观设定已生成，后续角色卡必须继承该世界规则。",
            ))
            world_review = {
                "passed": world_review_result.passed,
                "severity": world_review_result.severity,
                "issues": [issue.message for issue in world_review_result.issues],
                "revision_target": world_review_result.revision_target,
                "revision_instructions": world_review_result.revision_instructions,
                "requires_user_confirmation": world_review_result.requires_user_confirmation,
            }
            await self._emit_creative_workflow_progress(context, workflow_run, {
                "content": (
                    "### 独立审查\n世界观审查通过。"
                    if world_review["passed"]
                    else f"### 独立审查\n世界观被退回：{'；'.join(world_review.get('issues') or [])}"
                ),
                "current_agent": "Evaluator",
                "stage": "world_review",
                "status": "running",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
            if world_review["passed"]:
                workflow_run.complete_task(
                    task_id=world_task_id,
                    task_type="worldbuilding",
                    target_agent="Worldbuilder",
                    artifact_id=world_artifact_id,
                    status="completed",
                )
                break
            workflow_run.mark_task(world_task_id, "revision_requested")

        if not world_review["passed"]:
            workflow_run.status = "failed"
            workflow_run.complete_task(
                task_id=world_task_id,
                task_type="worldbuilding",
                target_agent="Worldbuilder",
                artifact_id=f"{world_task_id}-artifact",
                status="failed",
                error="world_review_failed",
            )
            return {
                "agent_name": "Coordinator",
                "action": "world_and_character_setup",
                "response": "世界观未通过独立审查，已停止后续角色卡生成：" + "；".join(world_review.get("issues") or []),
                "error": "world_review_failed",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "params": {"world_review": world_review, "world": world_data, "creative_workflow_run": workflow_run.to_dict()},
            }

        if await self._check_coordinator_pause_cancel():
            workflow_run.status = "cancelled"
            return {
                "agent_name": "Coordinator",
                "action": "world_and_character_setup",
                "response": "任务已取消，世界观已保留，角色卡尚未生成。",
                "error": "cancelled",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "params": {"world_review": world_review, "world": world_data, "creative_workflow_run": workflow_run.to_dict()},
            }

        character_task_id = "create_characters"
        workflow_run.mark_task(character_task_id, "running")
        character_context = dict(context or {})
        character_context["character_request_mode"] = (
            "autonomous_draft" if requirements.get("ai_autonomy_requested") else "save"
        )
        character_context["world"] = world_data
        autonomous_note = self._build_autonomous_creation_note(requirements)
        character_context["creation_requirements"] = {
            **requirements,
            "autonomous_brief": autonomous_note,
        }
        character_context["ai_autonomy_requested"] = bool(requirements.get("ai_autonomy_requested", False))
        character_context["autonomous_brief"] = autonomous_note
        character_result = await self._execute_character_creation_pipeline(
            message=message,
            context=character_context,
        )
        self._merge_file_records(created_files, character_result.get("created_files", []))
        self._merge_file_records(updated_files, character_result.get("updated_files", []))
        self._merge_file_records(reused_files, character_result.get("reused_files", []))

        characters = character_result.get("characters", []) if isinstance(character_result, dict) else []
        character_artifact_id = f"{character_task_id}-artifact"
        workflow_run.created_files = created_files
        workflow_run.updated_files = updated_files
        workflow_run.add_artifact(
            Artifact(
                artifact_id=character_artifact_id,
                artifact_type="characters",
                task_id=character_task_id,
                content=characters,
                status="draft",
                target_path=str(self.coordinator.project_dir / "characters.json"),
                updated_at=datetime.now().isoformat(),
            )
        )
        character_review_result = review_artifact_basic(
            task_id=character_task_id,
            artifact_id=character_artifact_id,
            artifact_type="characters",
            artifact=characters,
            revision_target="CharacterBuilder",
        )
        workflow_run.add_review(character_review_result)
        workflow_run.add_handoff(self._make_artifact_handoff(
            artifact_id=character_artifact_id,
            artifact_type="characters",
            artifact=characters,
            summary="角色卡已基于世界观生成，后续大纲和正文应继承角色动机与关系。",
        ))
        character_review = {
            "passed": character_review_result.passed,
            "severity": character_review_result.severity,
            "issues": [issue.message for issue in character_review_result.issues],
            "revision_target": character_review_result.revision_target,
            "revision_instructions": character_review_result.revision_instructions,
            "requires_user_confirmation": character_review_result.requires_user_confirmation,
        }
        await self._emit_creative_workflow_progress(context, workflow_run, {
            "content": (
                "### 独立审查\n角色卡审查通过。"
                if character_review["passed"]
                else f"### 独立审查\n角色卡被退回：{'；'.join(character_review.get('issues') or [])}"
            ),
            "current_agent": "Evaluator",
            "stage": "character_review",
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })

        if not character_review["passed"] or not character_result.get("is_complete"):
            workflow_run.status = "failed"
            workflow_run.complete_task(
                task_id=character_task_id,
                task_type="characters",
                target_agent="CharacterBuilder",
                artifact_id=character_artifact_id,
                status="failed",
                error=str(character_result.get("error") or "character_review_failed"),
            )
            return {
                "agent_name": "Coordinator",
                "action": "world_and_character_setup",
                "response": (
                    "世界观已完成，但角色卡未通过审查或未成功保存："
                    + "；".join(character_review.get("issues") or [str(character_result.get("error") or "unknown_error")])
                ),
                "error": str(character_result.get("error") or "character_review_failed"),
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "focus_module": "characters",
                "params": {
                    "world": world_data,
                    "world_review": world_review,
                    "character_review": character_review,
                    "creative_workflow_run": workflow_run.to_dict(),
                },
            }

        workflow_run.complete_task(
            task_id=character_task_id,
            task_type="characters",
            target_agent="CharacterBuilder",
            artifact_id=character_artifact_id,
            status="completed",
        )
        workflow_run.status = "completed"
        await self._emit_creative_workflow_progress(context, workflow_run, {
            "content": "### 工作流完成\n世界观和角色卡均已通过审查并写入资料库。",
            "current_agent": "Coordinator",
            "stage": "completed",
            "status": "completed",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
        })

        return {
            "agent_name": "Coordinator",
            "action": "world_and_character_setup",
            "response": (
                "已按多助手工作流完成：世界观构建 → 独立审查 → 角色卡生成 → 独立审查 → 写入资料库。\n\n"
                "世界观已同步到资料库，角色卡也已创建并保存。"
            ),
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir),
            "focus_module": "characters",
            "focus_chapter": 0,
            "params": {
                "world": world_data,
                "characters": characters,
                "world_review": world_review,
                "character_review": character_review,
                "execution_agents": ["Coordinator", "Worldbuilder", "Evaluator", "CharacterBuilder"],
                "creative_workflow_run": workflow_run.to_dict(),
            },
            "collected_info": character_result.get("collected_info", {}),
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

        if request_mode not in {"save", "autonomous_draft"}:
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
            text = _localize_workflow_error(str(message or "").strip())
            if not text:
                return
            payload = {
                "content": f"{text}\n\n",
                "runtime_message": make_runtime_message(
                    role="event",
                    message_type="workflow",
                    content={"content": f"{text}\n\n"},
                    trace_id=self._get_run_id(context),
                ).to_dict(),
            }
        elif isinstance(message, dict):
            next_payload = dict(message)
            content = _localize_workflow_error(str(next_payload.get("content") or "").strip())
            if content:
                next_payload["content"] = f"{content}\n\n"
            for key in ("message", "details", "error"):
                if next_payload.get(key):
                    next_payload[key] = _localize_workflow_error(next_payload[key])
            if not isinstance(next_payload.get("runtime_message"), dict):
                next_payload["runtime_message"] = make_runtime_message(
                    role="event",
                    message_type="workflow",
                    content={
                        key: value
                        for key, value in next_payload.items()
                        if key != "runtime_message"
                    },
                    trace_id=self._get_run_id(context),
                    agent_name=str(
                        next_payload.get("current_agent")
                        or next_payload.get("target_agent")
                        or ""
                    ).strip(),
                    metadata={
                        "stage": str(next_payload.get("stage") or "").strip(),
                        "status": str(next_payload.get("status") or "").strip(),
                    },
                ).to_dict()
            payload = next_payload
        else:
            return
        try:
            result = callback(payload)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.debug(f"[{self.name}] progress callback failed: {exc}")

    async def _emit_creative_workflow_progress(
        self,
        context: Optional[Dict[str, Any]],
        run: CreativeWorkflowRun,
        message: Dict[str, Any],
    ) -> None:
        payload = dict(message or {})
        run.set_current(
            agent=str(payload.get("current_agent") or run.current_agent),
            stage=str(payload.get("stage") or run.current_stage),
            status=str(payload.get("status") or run.status),
        )
        if "created_files" in payload:
            run.created_files = [item for item in payload.get("created_files") or [] if isinstance(item, dict)]
        if "updated_files" in payload:
            run.updated_files = [item for item in payload.get("updated_files") or [] if isinstance(item, dict)]
        snapshot = run.to_dict()
        payload.update({
            "creative_workflow": snapshot,
            "workflow_plan": snapshot.get("workflow_plan", {}),
            "task_queue": snapshot.get("task_queue", []),
            "completed_tasks": snapshot.get("completed_tasks", []),
            "reviews": snapshot.get("reviews", []),
            "handoff_notes": snapshot.get("handoff_notes", []),
        })
        await self._emit_progress(context, payload)

    @staticmethod
    def _make_artifact_handoff(
        *,
        artifact_id: str,
        artifact_type: str,
        artifact: Any,
        summary: str,
    ) -> AgentHandoff:
        new_facts: List[str] = []
        if isinstance(artifact, dict):
            for key, value in list(artifact.items())[:5]:
                if value not in (None, "", [], {}):
                    new_facts.append(f"{key}: {str(value)[:80]}")
        elif isinstance(artifact, list):
            for item in artifact[:5]:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("title") or "").strip()
                    if name:
                        new_facts.append(name)
        return AgentHandoff(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            decisions=[summary] if summary else [],
            dependencies=[],
            new_facts=new_facts,
            changed_facts=[],
            risks=[],
            next_context_summary=summary,
        )

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
        should_reuse_world = bool(requirements.get("resume_existing", False))
        if should_reuse_world and world_path.exists():
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
            requirements=self._build_worldbuilding_requirements_text(requirements),
        )
        world_data = world_result.get("world", {}) if isinstance(world_result, dict) else {}
        missing_info = self._worldbuilding_missing_info(world_data)
        if missing_info:
            await self._emit_progress(context, {
                "content": "### 世界观阶段暂停\n缺少关键信息：" + "、".join(missing_info[:5]),
                "current_agent": "Worldbuilder",
                "stage": "worldbuilding",
                "status": "failed",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
            return world_data, created_files, updated_files, reused_files
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
        requirements = await self._build_creation_requirements_async(context, message)
        world_data, created_files, updated_files, reused_files = await self._ensure_world_payload(requirements, context)
        missing_info = self._worldbuilding_missing_info(world_data)
        if missing_info:
            response = "世界观构建暂时中断，需要先补充：" + "、".join(missing_info[:5])
            return {
                "agent_name": "Worldbuilder",
                "action": "worldbuild",
                "response": response,
                "error": "missing_worldbuilding_info",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "focus_module": "world",
                "focus_chapter": 0,
                "params": {
                    "world": world_data,
                    "missing_info": missing_info,
                },
            }
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
        requirements = await self._build_creation_requirements_async(context, message)
        world_data, created_files, updated_files, reused_files = await self._ensure_world_payload(requirements, context)
        missing_info = self._worldbuilding_missing_info(world_data)
        if missing_info:
            response = "无法继续生成大纲，世界观还缺少：" + "、".join(missing_info[:5])
            return {
                "agent_name": "Worldbuilder",
                "action": "outline",
                "response": response,
                "error": "missing_worldbuilding_info",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "focus_module": "world",
                "focus_chapter": 0,
                "params": {
                    "world": world_data,
                    "missing_info": missing_info,
                },
            }
        await self._emit_progress(context, {
            "content": "### 大纲阶段\n正在生成主线大纲...",
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
            plot_idea=self._build_outline_plot_idea_text(requirements),
            volume_count=requirements["volume_count"],
            chapters_per_volume=requirements["chapters_per_volume"],
            characters=getattr(self.coordinator, "character_manager", None).export_for_llm()
            if getattr(self.coordinator, "character_manager", None) is not None
            else None,
        )
        outline_data = normalize_outline_payload(outline_result.get("outline", {}) if isinstance(outline_result, dict) else {})
        outline_rows = self._outline_to_project_rows(outline_data)
        outline_persist = self._persist_outline_rows(outline_rows)
        self._sync_eventlines_from_outline(outline_data)
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

    @staticmethod
    def _requested_category_from_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        explicit_command = context.get("explicit_command")
        if isinstance(explicit_command, dict) and isinstance(explicit_command.get("category"), dict):
            return dict(explicit_command["category"])
        category = context.get("requested_knowledge_category")
        if isinstance(category, dict):
            return dict(category)
        return {}

    async def _execute_requested_project_data_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        category = self._requested_category_from_context(context)
        data_type = str(category.get("key") or "").strip()
        label = str(category.get("name") or data_type or "资料库内容").strip()
        if not data_type:
            return {
                "agent_name": "ProjectDataBuilder",
                "action": "generate_project_data",
                "error": "未识别到目标资料库类别。",
                "response": "未识别到目标资料库类别。请说明要生成或修改哪一类资料，例如“生成道具物品 玄铁剑”。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": [],
                "updated_files": [],
                "reused_files": [],
            }

        if data_type == "worldbuilding":
            return await self._execute_worldbuild_pipeline(message=message, context=context)
        if data_type == "characters":
            character_context = dict(context or {})
            character_context["character_request_mode"] = "save"
            return await self._execute_character_creation_pipeline(message=message, context=character_context)
        if data_type == "outline":
            return await self._execute_outline_pipeline(message=message, context=context)
        if data_type == "eventlines":
            return await self._execute_project_data_generation_pipeline(
                message=message,
                context=context,
                data_type="eventlines",
                agent_name="EventlineBuilder",
                stage="eventlines",
                label=label or "事件线",
            )
        if data_type == "detail_settings":
            return await self._execute_project_data_generation_pipeline(
                message=message,
                context=context,
                data_type="detail_settings",
                agent_name="DetailOutlineBuilder",
                stage="detail_outline",
                label=label or "细纲设定",
            )
        if data_type == "chapter_settings":
            return await self._execute_project_data_generation_pipeline(
                message=message,
                context=context,
                data_type="chapter_settings",
                agent_name="ChapterSettingBuilder",
                stage="chapter_settings",
                label=label or "章纲设定",
            )
        if data_type == "chapters":
            return {
                "agent_name": "ChapterWriter",
                "action": "write_chapter",
                "error": "缺少章节号。",
                "response": "我识别到你要处理正文章节，但需要指定章节号，例如“写第3章正文”或“修改第3章正文”。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": [],
                "updated_files": [],
                "reused_files": [],
            }

        return await self._execute_generic_project_data_pipeline(
            message=message,
            context=context,
            data_type=data_type,
            label=label,
            category=category,
        )

    async def _execute_generic_project_data_pipeline(
        self,
        *,
        message: str,
        context: Optional[Dict[str, Any]],
        data_type: str,
        label: str,
        category: Dict[str, Any],
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager
        from .project_data_builders import GenericProjectDataBuilderAgent

        pm = get_project_manager()
        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        reused_files: List[Dict[str, str]] = []
        outline_rows = pm.load_project_data("outline")
        if not isinstance(outline_rows, list):
            outline_rows = []
        outline_rows = [row for row in outline_rows if isinstance(row, dict)]
        existing_rows = pm.load_project_data(data_type)
        if not isinstance(existing_rows, list):
            existing_rows = []
        existing_rows = [row for row in existing_rows if isinstance(row, dict)]
        requirements = self._build_project_data_generation_requirements(
            message=message,
            context=context,
            outline_rows=outline_rows,
        )
        requirements.update({
            "target_category": category,
            "data_type": data_type,
            "category_name": label,
            "existing_rows": existing_rows,
        })
        await self._emit_progress(context, {
            "content": f"### {label}阶段\n正在调用ProjectDataBuilder生成或更新结构化资料...",
            "current_agent": "ProjectDataBuilder",
            "stage": "project_data",
            "status": "running",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
        })
        builder = GenericProjectDataBuilderAgent(data_type=data_type, category_name=label)
        builder_result = await builder.execute(
            requirements,
            context={"project_dir": str(self.coordinator.project_dir) if self.coordinator else ""},
        )
        rows = builder_result.get("rows", []) if isinstance(builder_result, dict) else []
        if not isinstance(rows, list) or not rows:
            response_message = str((builder_result or {}).get("response_message") or "").strip() if isinstance(builder_result, dict) else ""
            return {
                "agent_name": "ProjectDataBuilder",
                "action": f"generate_{data_type}",
                "error": response_message or f"无法生成{label}，因为ProjectDataBuilder未返回有效结果。",
                "response": response_message or f"无法生成{label}，因为ProjectDataBuilder未返回有效结果。",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
            }

        merged_rows = self._merge_named_project_rows(existing_rows, [row for row in rows if isinstance(row, dict)])
        persist_result = self._persist_named_project_rows(data_type, merged_rows)
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
            "content": f"### {label}阶段完成\n已生成或更新 {len(rows)} 条{label}并同步到资料库",
            "current_agent": "ProjectDataBuilder",
            "stage": "project_data",
            "status": "completed",
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
        })
        return {
            "agent_name": "ProjectDataBuilder",
            "action": f"generate_{data_type}",
            "response": f"已完成{label}生成/更新，并写入资料库。",
            "is_complete": True,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
            "focus_module": "world",
            "params": {
                "data_type": data_type,
                "category": category,
                "count": len(rows),
            },
        }

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
        requirements = await self._build_creation_requirements_async(context, message)
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
        missing_info = self._worldbuilding_missing_info(world_data)
        if missing_info:
            return {
                "agent_name": "Worldbuilder",
                "action": "create_novel",
                "response": "创作已暂停，世界观还缺少：" + "、".join(missing_info[:5]),
                "error": "missing_worldbuilding_info",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
                "focus_module": "world",
                "focus_chapter": 0,
                "params": {
                    **requirements,
                    "world": world_data,
                    "missing_info": missing_info,
                    "creation_contract": contract_payload,
                },
            }

        outline_rows = pm.load_project_data("outline")
        outline_path = str(pm.get_project_data_path("outline"))
        outline_data: Dict[str, Any] = {}
        execution_outline_rows: List[Dict[str, Any]] = []
        if bool(requirements.get("resume_existing", False)) and isinstance(outline_rows, list) and outline_rows:
            outline_rows = [row for row in outline_rows if isinstance(row, dict)]
            outline_data = {"chapters": outline_rows}
            execution_outline_rows = extract_outline_chapter_rows(outline_rows)
            if not execution_outline_rows:
                execution_outline_rows = derive_chapter_seed_rows_from_outline(outline_rows)
            if not execution_outline_rows:
                execution_outline_rows = self._load_project_executable_chapter_rows()
            if not execution_outline_rows:
                execution_outline_rows = outline_rows
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
                "content": "### 大纲阶段\n正在生成主线大纲...",
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
                plot_idea=self._build_outline_plot_idea_text(requirements),
                volume_count=requirements["volume_count"],
                chapters_per_volume=requirements["chapters_per_volume"],
                characters=getattr(self.coordinator, "character_manager", None).export_for_llm()
                if getattr(self.coordinator, "character_manager", None) is not None
                else None,
            )
            outline_data = normalize_outline_payload(outline_result.get("outline", {}) if isinstance(outline_result, dict) else {})
            outline_rows = self._outline_to_project_rows(outline_data)
            execution_outline_rows = extract_outline_chapter_rows(outline_data)
            if not execution_outline_rows:
                execution_outline_rows = derive_chapter_seed_rows_from_outline(outline_data)
            if not execution_outline_rows:
                execution_outline_rows = outline_rows
            outline_persist = self._persist_outline_rows(outline_rows)
            self._sync_eventlines_from_outline(outline_data)
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
                "content": f"### 大纲阶段完成\n共规划 {len(execution_outline_rows)} 章，大纲已同步到资料库",
                "current_agent": "Outliner",
                "stage": "outlining",
                "status": "running",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir),
            })
        chapter_outline_rows = execution_outline_rows or outline_rows
        project_title = self._ensure_project_metadata(
            requirements=requirements,
            outline_rows=chapter_outline_rows,
            outline_data=outline_data if isinstance(outline_data, dict) else {},
        )

        written_chapters: List[Dict[str, Any]] = []
        chapter_files: List[Dict[str, str]] = []
        last_persisted_paths = {"outline_path": outline_path}
        resumed_chapter_count = 0
        for chapter_index, row in enumerate(chapter_outline_rows, start=1):
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
                    "focus_chapter": self._find_next_incomplete_chapter(chapter_outline_rows, start_at=chapter_index) or chapter_index,
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
                    "content": f"### 章节阶段\n正在创作第 {chapter_index}/{len(chapter_outline_rows)} 章：{row.get('title') or f'第{chapter_index}章'}",
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
            last_persisted_paths = await self._persist_chapter_result(chapter_result, chapter_outline_rows)
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

        outline_preview = [row.get("title", f"第{i+1}章") for i, row in enumerate(chapter_outline_rows[:5])]
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
            "执行流程：世界观 → 角色档案 → 大纲 → 正文创作",
            "",
            "生成结果：",
            "- 世界观已同步到资料库",
            f"- 大纲已生成，共 {len(chapter_outline_rows)} 章",
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
            "focus_chapter": self._find_next_incomplete_chapter(chapter_outline_rows, start_at=1),
            "params": {
                **requirements,
                "persisted_paths": persisted_paths,
                "execution_agents": ["Worldbuilder", "CharacterBuilder", "Outliner", "ChapterWriter"],
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

    async def _execute_project_chapters_write(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_rows = self._load_project_executable_chapter_rows()
        if not outline_rows:
            return {
                "agent_name": "ChapterWriter",
                "action": "write_chapters",
                "response": "还没有可用的章节大纲，无法判断每一章该写什么。请先生成或确认大纲，然后再开始写正文。",
                "error": "missing_outline",
                "is_complete": False,
                "run_id": self._get_run_id(context),
                "created_files": [],
                "updated_files": [],
                "reused_files": [],
                "focus_module": "write",
                "focus_chapter": 1,
            }

        created_files: List[Dict[str, str]] = []
        updated_files: List[Dict[str, str]] = []
        reused_files: List[Dict[str, str]] = []
        written_chapters: List[Dict[str, Any]] = []
        generated_chapters: List[Dict[str, Any]] = []
        chapter_paths: List[str] = []
        last_persisted_paths: Dict[str, str] = {
            "outline_path": str(pm.get_project_data_path("outline")),
        }

        for index, row in enumerate(outline_rows, start=1):
            if not isinstance(row, dict):
                continue
            chapter_num = self._normalize_positive_int(row.get("chapter_number"), index)
            existing_chapter = self._load_existing_chapter_result(chapter_num, row)
            if existing_chapter:
                written_chapters.append(existing_chapter)
                chapter_path = self._find_existing_chapter_file(chapter_num) or ""
                if chapter_path:
                    chapter_file = self._build_file_record(
                        chapter_path,
                        "chapter",
                        f"第 {chapter_num} 章",
                        "reused",
                    )
                    chapter_paths.append(chapter_file["path"])
                    self._append_file_record_by_status(
                        file_record=chapter_file,
                        created_files=created_files,
                        updated_files=updated_files,
                        reused_files=reused_files,
                    )
                await self._emit_progress(
                    context,
                    {
                        "content": f"### 章节阶段\n第 {chapter_num} 章已有正文，已跳过并复用。",
                        "current_agent": "ChapterWriter",
                        "stage": f"chapter_{chapter_num}",
                        "status": "running",
                        "created_files": created_files,
                        "updated_files": updated_files,
                        "reused_files": reused_files,
                        "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
                    },
                )
                continue

            if await self._check_coordinator_pause_cancel():
                return {
                    "agent_name": "ChapterWriter",
                    "action": "write_chapters",
                    "response": "章节正文写作已取消，已生成内容会保留在当前项目中。",
                    "error": "cancelled",
                    "is_complete": False,
                    "run_id": self._get_run_id(context),
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
                    "focus_module": "write",
                    "focus_chapter": chapter_num,
                    "params": {
                        "chapters": written_chapters,
                        "persisted_paths": {
                            **last_persisted_paths,
                            "chapter_paths": chapter_paths,
                        },
                    },
                }

            chapter_title = str(row.get("title") or f"第{chapter_num}章").strip() or f"第{chapter_num}章"
            chapter_outline = str(row.get("summary") or row.get("content") or chapter_title).strip() or chapter_title
            await self._emit_progress(
                context,
                {
                    "content": f"### 章节阶段\n正在按大纲创作第 {chapter_num}/{len(outline_rows)} 章：{chapter_title}",
                    "current_agent": "ChapterWriter",
                    "stage": f"chapter_{chapter_num}",
                    "status": "running",
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
                },
            )
            chapter_result = await self._write_chapter_with_coordinator(
                chapter_num=chapter_num,
                chapter_outline={
                    "title": chapter_title,
                    "summary": chapter_outline,
                },
                previous_chapters=written_chapters,
            )
            chapter_result.setdefault("number", chapter_num)
            chapter_result.setdefault("chapter_number", chapter_num)
            chapter_result.setdefault("chapter_title", chapter_title)
            written_chapters.append(chapter_result)
            generated_chapters.append(chapter_result)
            last_persisted_paths = await self._persist_chapter_result(chapter_result, outline_rows)
            chapter_path = str(last_persisted_paths.get("chapter_path") or "")
            if chapter_path:
                chapter_file = self._build_file_record(
                    chapter_path,
                    "chapter",
                    f"第 {chapter_num} 章",
                    str(last_persisted_paths.get("chapter_status") or "created"),
                )
                chapter_paths.append(chapter_file["path"])
                self._append_file_record_by_status(
                    file_record=chapter_file,
                    created_files=created_files,
                    updated_files=updated_files,
                    reused_files=reused_files,
                )
            await self._emit_progress(
                context,
                {
                    "content": f"第 {chapter_num} 章完成，已同步到章节列表。",
                    "current_agent": "ChapterWriter",
                    "stage": f"chapter_{chapter_num}",
                    "status": "running",
                    "created_files": created_files,
                    "updated_files": updated_files,
                    "reused_files": reused_files,
                    "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
                },
            )

        total_words = sum(len(re.sub(r"\s+", "", str(chapter.get("content") or ""))) for chapter in written_chapters)
        current_project = pm.get_current_project()
        project_title = str((current_project.name if current_project else "") or "未命名项目").strip() or "未命名项目"
        compiled_novel_path = ""
        compiled_novel = self._save_compiled_novel(project_title, written_chapters)
        if compiled_novel:
            compiled_novel_path = str(compiled_novel.get("path") or "")
            compiled_file = self._build_file_record(
                compiled_novel_path,
                "compiled_novel",
                "合集",
                str(compiled_novel.get("status") or "created"),
            )
            self._append_file_record_by_status(
                file_record=compiled_file,
                created_files=created_files,
                updated_files=updated_files,
                reused_files=reused_files,
            )

        persisted_paths = {
            **last_persisted_paths,
            "chapter_paths": chapter_paths,
        }
        if chapter_paths:
            persisted_paths["chapter_path"] = chapter_paths[-1]
        if compiled_novel_path:
            persisted_paths["compiled_novel_path"] = compiled_novel_path

        next_incomplete = self._find_next_incomplete_chapter(pm.load_project_data("chapters"), start_at=1)
        await self._emit_progress(
            context,
            {
                "content": f"### 章节正文完成\n已按章纲/大纲处理 {len(written_chapters)} 章，其中新写 {len(generated_chapters)} 章。",
                "current_agent": "ChapterWriter",
                "stage": "chapters",
                "status": "completed",
                "created_files": created_files,
                "updated_files": updated_files,
                "reused_files": reused_files,
                "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
            },
        )

        response_parts = [
            "已按章纲/大纲逐章执行正文写作。",
            "",
            f"- 可执行章节数：{len(outline_rows)}",
            f"- 本次新写章节：{len(generated_chapters)}",
            f"- 已有正文复用：{max(0, len(written_chapters) - len(generated_chapters))}",
            f"- 当前正文总字数约：{total_words} 字",
        ]
        if compiled_novel_path:
            response_parts.append("- 已生成或更新合集文件")
        if generated_chapters and str(generated_chapters[0].get("content") or "").strip():
            response_parts.extend([
                "",
                "以下是本次新写的第一章正文：",
                "",
                str(generated_chapters[0].get("content") or "").strip(),
            ])

        return {
            "agent_name": "ChapterWriter",
            "action": "write_chapters",
            "response": "\n".join(response_parts),
            "is_complete": next_incomplete == 0,
            "run_id": self._get_run_id(context),
            "created_files": created_files,
            "updated_files": updated_files,
            "reused_files": reused_files,
            "output_dir": str(self.coordinator.project_dir) if self.coordinator else "",
            "focus_module": "write",
            "focus_chapter": next_incomplete,
            "params": {
                "chapters": written_chapters,
                "generated_chapter_count": len(generated_chapters),
                "persisted_paths": persisted_paths,
            },
        }

    async def _execute_project_chapter_write(
        self,
        chapter_num: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from ..project_manager import get_project_manager

        pm = get_project_manager()
        outline_rows = self._load_project_executable_chapter_rows()
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
