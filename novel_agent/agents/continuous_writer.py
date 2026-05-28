# -*- coding: utf-8 -*-
"""
无限续写 Agent。

根据用户提供的故事开头或灵感持续生成章节，并通过持久化会话、
知识库检索与一致性约束，尽量保持长程创作的连续性。
"""
from __future__ import annotations

import asyncio
import logging
import time
import re
import json
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass, field

from .base_agent import BaseAgent
from .session_store import (
    NORMAL_CHARACTER_STATUS,
    SessionState,
    get_session_store,
    normalize_character_status,
)
from ..agent_config import AgentModelConfig
from ..constants import WRITING_CONFIG

# 延迟导入剧情约束模块，避免循环依赖。
PlotConstraintStore = None
ContentValidator = None
PostGenerationProcessor = None

SUSPICIOUS_MOJIBAKE_FRAGMENTS = (
    "\u9352\u56e8\u5d32",
    "\u942d\u30e8\u7611",
    "\u7ed4\u72ba\u59ad",
    "\u93ad\u3220\ue632",
    "\u701b\u6941\u669f",
    "\u59af\u2033\u7037",
    "\u6d7c\u6c33\u763d",
)

NON_CHAPTER_RESPONSE_PATTERNS = (
    r"请告诉我",
    r"请把.+告诉我",
    r"我没有收到",
    r"目前提供的.+只有",
    r"比如[:：]",
    r"题材/类型",
    r"主角信息",
    r"世界观/背景",
    r"核心冲突/主线",
    r"开篇情境",
    r"风格偏好",
    r"基本信息",
    r"粗略的想法",
)

_CHAPTER_MARK_RE = r"第[ \t]*[\d一二三四五六七八九十百千万零〇两]+[ \t]*[章节回]"
_MARKDOWN_CHAPTER_HEADING_RE = re.compile(
    rf"^\s{{0,3}}#{{1,6}}[ \t]*(?:{_CHAPTER_MARK_RE})[ \t]*[-—:：、.． \t]*(?P<title>[^\n\r]*)[ \t]*(?:\r?\n|$)"
)
_PLAIN_CHAPTER_HEADING_RE = re.compile(
    rf"^\s{{0,3}}(?:{_CHAPTER_MARK_RE})(?:(?:[ \t]*[-—:：、.．][ \t]*|[ \t]+)(?P<title>[^\n\r]*))?[ \t]*(?:\r?\n|$)"
)
_CHAPTER_TITLE_PREFIX_RE = re.compile(
    rf"^\s*(?:#{{1,6}}[ \t]*)?(?:{_CHAPTER_MARK_RE})(?:[ \t]*[-—:：、.．][ \t]*|[ \t]+)?"
)
_BARE_CHAPTER_TITLE_RE = re.compile(rf"^\s*(?:#{{1,6}}\s*)?(?:{_CHAPTER_MARK_RE})\s*$")

_COMMON_CHINESE_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "谢邹喻柏水章云苏潘葛范彭郎鲁韦昌马苗花方俞任袁柳鲍史唐费廉岑"
    "薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄穆萧"
    "尹姚邵汪祁毛米贝明计伏成戴谈宋庞熊纪舒屈项祝董梁杜阮蓝闵季"
    "贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田胡凌霍虞万支柯管卢莫房"
    "解应宗丁宣邓杭洪包左石崔吉龚程邢裴陆荣翁荀惠曲封储靳井段富"
    "焦巴牧山谷车侯全班秋仲宫宁仇甘厉祖武符刘景龙叶司韶黎白怀蒲"
    "卓屠池乔闻党翟谭贡劳冉雍桑桂牛寿边燕浦农温庄晏柴瞿阎连习艾"
    "向古易慎廖终居衡步耿满弘匡文寇广东欧沃利蔚越师巩聂晁勾冷辛"
    "那简饶曾沙丰关查红游权益桓公"
)
_COMPOUND_CHINESE_SURNAMES = (
    "欧阳|司马|上官|诸葛|东方|皇甫|尉迟|公孙|慕容|司徒|令狐|宇文|长孙|夏侯"
)
_CHARACTER_NAME_FOLLOWERS = (
    "说|道|问|答|看|望|站|走|跑|坐|转|冲|笑|哭|喊|叫|低|抬|皱|握|捏|拉|推|"
    "抱|扶|踢|绕|探|钻|守|退|把|将|被|给|向|对|与|和|从|在|正|又|也|却|便|"
    "才|仍|还|已经|忽然|突然|没有|不是|另有|发现|决定|怀疑|盯|凝视|注视"
)
_CHARACTER_NAME_PREFIXES = (
    "看向|望向|面对|叫住|找到|遇见|追上|扶起|抱住|拉住|问|对|向|跟|和|与"
)
_NON_CHARACTER_NAMES = {
    "我们", "他们", "这里", "那里", "一个", "不是", "如果", "然后", "自己", "有人",
    "众人", "少年", "少女", "男人", "女人", "老人", "教练", "队友", "守门员", "主角",
    "配角", "反派", "角色", "人物",
}
_NON_CHARACTER_NAME_PARTS = (
    "第", "章", "回", "节", "故事", "起源", "最近", "状态", "表现", "训练", "基地",
    "空气", "草腥", "塑胶", "跑道", "味道", "足球", "点球", "热点", "小说", "方面",
    "相关", "参考", "内容", "章节", "标题", "纪元",
)

def get_plot_constraint_store(knowledge_base):
    """获取剧情约束存储实例。"""
    global PlotConstraintStore
    if PlotConstraintStore is None:
        from ..knowledge_base.logic_layer.plot_constraints import PlotConstraintStore as PCS
        PlotConstraintStore = PCS
    return PlotConstraintStore(knowledge_base)

def get_content_validator(constraint_store, knowledge_base):
    """获取内容校验器与后处理器。"""
    global ContentValidator, PostGenerationProcessor
    if ContentValidator is None:
        from .content_validator import ContentValidator as CV, PostGenerationProcessor as PGP
        ContentValidator = CV
        PostGenerationProcessor = PGP
    return ContentValidator(constraint_store, knowledge_base), PostGenerationProcessor

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """角色状态跟踪。"""
    name: str
    is_alive: bool = True
    status: str = NORMAL_CHARACTER_STATUS
    location: str = ""
    last_chapter: int = 0
    notes: List[str] = field(default_factory=list)
    learned_abilities: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = str(self.name or "").strip()
        self.status = normalize_character_status(self.status)


@dataclass
class PlotPoint:
    """剧情要点跟踪。"""
    chapter: int
    description: str
    importance: str = "normal"
    resolved: bool = False


@dataclass
class ContinuousWriteConfig:
    """无限续写配置。"""
    words_per_chapter: int = 2500
    min_words: int = 2000
    max_words: int = 4000
    auto_save_to_kb: bool = True
    check_consistency: bool = True
    context_chapters: int = 5
    kb_search_top_k: int = 5
    kb_summary_top_k: int = 3
    pause_for_user_input: bool = True
    enable_trends_search: bool = False
    trends_platforms: List[str] = field(default_factory=lambda: ["toutiao", "douyin"])
    trends_limit: int = 5


class ContinuousWriter(BaseAgent):
    """
    无限续写 Agent。

    核心职责：
    1. 根据故事开头持续生成后续章节。
    2. 在章节间保持人物、剧情和设定一致性。
    3. 通过持久化会话支持恢复与跨模型续写。
    4. 在可用时接入知识库与热点灵感增强创作。
    """
    
    def __init__(
        self,
        model_config: Optional[AgentModelConfig] = None,
        write_config: Optional[ContinuousWriteConfig] = None,
        knowledge_base = None,
        session_id: str = "default",
        project_id: str = "",
        **kwargs
    ):
        """初始化无限续写 Agent。"""
        super().__init__(
            name="ContinuousWriter",
            prompt_file="continuous_writer.md",
            model_config=model_config,
            **kwargs
        )
        
        self.write_config = write_config or ContinuousWriteConfig()
        self.knowledge_base = knowledge_base
        self._library_service = None
        
        # 会话标识
        self._session_id = session_id
        self._project_id = project_id
        self._session_store = get_session_store()
        self._session_state: Optional[SessionState] = None
        
        self._is_running = False
        self._should_stop = False
        self._waiting_for_input = False
        self._current_chapter = 0
        
        self._written_chapters: List[Dict[str, Any]] = []
        self._story_beginning: str = ""
        self._user_inspirations: List[Dict[str, Any]] = []
        self._recovered_chapters: List[Dict[str, Any]] = []  # 恢复的章节数据
        self._corrections: List[Dict[str, Any]] = []
        
        self._characters: Dict[str, CharacterState] = {}
        self._plot_points: List[PlotPoint] = []
        self._dead_characters: List[str] = []
        
        self._trends_enabled: bool = False
        self._trends_query: str = ""
        self._cached_trends: List[Dict[str, Any]] = []
        
        # 当前使用的模型名称，用于跟踪模型切换
        self._current_model: str = ""
        
        # 剧情约束存储，在设置知识库时初始化
        self._constraint_store = None
        self._character_manager = None
        
        # 内容验证器与后处理器
        self._content_validator = None
        self._post_processor = None
        
        # 验证配置
        self._enable_post_validation = True
        self._auto_fix_violations = True
        self._max_regeneration_attempts = 2
        
        # 高级检索配置
        self._use_advanced_search = True
        self._use_dynamic_weights = True
        self._use_reranking = True
        self._use_context_compression = True

        try:
            self._content_validator, _ = get_content_validator(None, None)
        except Exception as exc:
            logger.warning(f"[{self.name}] 基础内容验证器初始化失败: {exc}")
            self._content_validator = None
        
    def _get_default_prompt(self) -> str:
        """获取默认系统提示词。"""
        prompt = """# 无限续写 Agent

你负责长程连续创作，目标是在多轮续写中保持剧情推进、人物一致和设定稳定。

## 工作模式

### 模式 CW1：起章（start）
- 根据故事开头建立人物、冲突和叙事节奏，并在章末留下可续写的钩子。

### 模式 CW2：续章（continue，默认）
- 基于上一章自然推进，不重复前文，不原地打转。

### 模式 CW3：重生成（regenerate）
- 保持章节目标和关键事实不变，重写表达、节奏与推进路径。

### 模式 CW4：纠正执行（correct / inspiration）
- 下一章优先吸收用户新增灵感与剧情纠正。

## 强约束

1. 严格控制在目标字数的正负 15% 以内。
2. 已死亡角色不得以活人状态回归，回忆或闪回除外。
3. 不破坏既有世界观、角色设定、时间线和关键事实。
4. 模型切换后优先遵守历史上下文与持久化状态。

## 支线规则

- 支线推进时必须保留回到主线的连接点。
- 支线不可无限延长，到达目标后应尽快回收。
- 线程变化只能通过自然剧情、对话、场景转场和章末钩子体现，不要输出 HTML 注释、PLOT_THREAD 标记或其他机器标记。
"""
        return self._ensure_text_integrity(prompt, "默认提示词")

    @staticmethod
    def _contains_mojibake(text: str) -> bool:
        """检测常见乱码片段。"""
        if not text:
            return False
        if "\ufffd" in text:
            return True
        return any(fragment in text for fragment in SUSPICIOUS_MOJIBAKE_FRAGMENTS)

    def _ensure_text_integrity(self, text: str, label: str) -> str:
        """在关键提示词发送前阻断明显乱码。"""
        if self._contains_mojibake(text):
            logger.error(f"[{self.name}] {label} 检测到疑似乱码，请检查源码编码")
            raise ValueError(f"{label} 存在疑似乱码")
        return text
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """鎵ц缁啓浠诲姟"""
        action = input_data.get("action", "continue")
        
        if input_data.get("trends_query"):
            self._trends_enabled = True
            self._trends_query = input_data.get("trends_query", "")
        if input_data.get("trends_platforms"):
            self.write_config.trends_platforms = input_data.get("trends_platforms")
        
        if action == "start":
            return await self._start_new_story(input_data, context)
        elif action == "continue":
            return await self._continue_writing(input_data, context)
        elif action == "add_inspiration":
            return self._add_inspiration(input_data)
        elif action == "correct":
            return self._add_correction(input_data)
        elif action == "stop":
            return self._stop_writing()
        elif action == "status":
            return self._get_status()
        elif action == "get_chapter":
            return self._get_chapter(input_data.get("chapter_number", 1))
        elif action == "enable_trends":
            return self._enable_trends(input_data)
        elif action == "disable_trends":
            return self._disable_trends()
        elif action == "regenerate":
            return await self._regenerate_chapter(input_data, context)
        else:
            return {"success": False, "error": f"未知动作: {action}"}
    
    def _load_or_create_session(self, story_beginning: str = "") -> SessionState:
        """
        加载或创建持久化会话。
        
        这是确保切换模型后仍能保持续写连续性的关键。
        """
        # 先尝试从持久化存储恢复
        state = self._session_store.load(self._session_id, self._project_id)
        
        if state:
            # 恢复已有会话
            logger.info(f"[{self.name}] Recovered persisted session at chapter {state.current_chapter}")
            
            # 同步内存状态
            self._story_beginning = state.story_beginning
            self._current_chapter = state.current_chapter
            self._written_chapters = state.chapters.copy()
            self._dead_characters = state.dead_characters.copy()
            self._user_inspirations = state.inspirations.copy()
            self._corrections = state.corrections.copy()
            self._characters = {
                name: CharacterState(**payload) if isinstance(payload, dict) else CharacterState(name=name)
                for name, payload in (state.character_states or {}).items()
            }
            self._plot_points = [
                PlotPoint(**item)
                for item in (state.plot_points or [])
                if isinstance(item, dict)
            ]
            
            return state
        
        # 创建新会话
        state = SessionState(
            session_id=self._session_id,
            project_id=self._project_id,
            story_beginning=story_beginning,
            words_per_chapter=self.write_config.words_per_chapter,
            trends_enabled=self._trends_enabled,
            trends_platforms=self.write_config.trends_platforms
        )
        
        self._session_store.save(state)
        logger.info(f"[{self.name}] Created new persisted session")
        return state
    
    def _sync_to_session(self):
        """
        将当前内存状态同步到持久化会话。
        
        每次章节完成后调用，确保关键数据不会丢失。
        """
        if not self._session_state:
            return
        
        self._session_state.story_beginning = self._story_beginning
        self._session_state.current_chapter = self._current_chapter
        self._session_state.chapters = self._written_chapters.copy()
        self._session_state.dead_characters = self._dead_characters.copy()
        self._session_state.character_states = {
            name: {
                "name": state.name,
                "is_alive": state.is_alive,
                "status": state.status,
                "location": state.location,
                "last_chapter": state.last_chapter,
                "notes": list(state.notes[-5:]),
                "learned_abilities": list(state.learned_abilities[-12:]),
            }
            for name, state in self._characters.items()
        }
        self._session_state.plot_points = [
            {
                "chapter": point.chapter,
                "description": point.description,
                "importance": point.importance,
                "resolved": point.resolved,
            }
            for point in self._plot_points[-20:]
        ]
        self._session_state.inspirations = self._user_inspirations.copy()
        self._session_state.corrections = self._corrections.copy()
        self._session_state.is_running = self._is_running
        self._session_state.last_model = self._current_model
        
        self._session_store.save(self._session_state)
    
    def _get_model_switch_context(self) -> str:
        """获取模型切换时需要补充的上下文。"""
        if not self._session_state:
            return ""
        
        last_model = self._session_state.last_model
        if last_model and last_model != self._current_model:
            logger.info(f"[{self.name}] 检测到模型切换: {last_model} -> {self._current_model}")
            
            # 构建增强的模型切换上下文
            context_parts = []
            
            # 1. 基础会话摘要
            session_summary = self._session_state.get_context_summary(max_chapters=5)
            context_parts.append(session_summary)
            
            # 2. 从知识库补充关键约束
            if self.knowledge_base and self._use_advanced_search:
                try:
                    # 获取关键剧情约束
                    critical_constraints = self.knowledge_base.get_active_constraints()
                    if critical_constraints:
                        context_parts.append("\n[重要剧情约束]")
                        for c in critical_constraints[:10]:
                            context_parts.append(f"- {c.title}")
                    
                    # 获取已死亡角色
                    dead_chars = self.knowledge_base.get_dead_characters()
                    if dead_chars:
                        context_parts.append("\n[已死亡角色]")
                        context_parts.append(", ".join(dead_chars))
                        
                except Exception as e:
                    logger.warning(f"[{self.name}] 获取知识库约束失败: {e}")
            
            # 3. 提供上一章完整内容，确保续写连贯
            if self._written_chapters:
                last_ch = self._written_chapters[-1]
                last_content = last_ch.get('content', '')
                if last_content:
                    context_parts.append("\n[上一章完整内容]")
                    context_parts.append(
                        f"第{last_ch.get('chapter_number')}章 {last_ch.get('title', '')}"
                    )
                    # 保留更多正文，确保续写稳定
                    context_parts.append(last_content[-2000:] if len(last_content) > 2000 else last_content)
            
            return "\n".join(context_parts)
        
        return ""
    
    async def _start_new_story(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """开始新故事或恢复已有故事。"""
        story_beginning = input_data.get("content", "")
        if not story_beginning:
            return {"success": False, "error": "请提供故事开头或灵感"}
        
        current_chapter = input_data.get("current_chapter", 0)
        is_recovery = current_chapter > 0
        
        self._is_running = True
        self._should_stop = False
        
        # 获取当前模型名称
        if self.model_config:
            self._current_model = self.model_config.model
        
        # 优先尝试从持久化存储恢复
        self._session_state = self._load_or_create_session(story_beginning)
        
        # 若持久化会话已有数据，则优先恢复
        if self._session_state.chapters:
            logger.info(f"[{self.name}] Using persisted chapters: {len(self._session_state.chapters)}")
            is_recovery = True
            self._current_chapter = self._session_state.current_chapter
            self._story_beginning = self._session_state.story_beginning
            self._written_chapters = self._session_state.chapters.copy()
            self._dead_characters = self._session_state.dead_characters.copy()
            self._user_inspirations = self._session_state.inspirations.copy()
            self._corrections = self._session_state.corrections.copy()
            self._characters = {
                name: CharacterState(**payload) if isinstance(payload, dict) else CharacterState(name=name)
                for name, payload in (self._session_state.character_states or {}).items()
            }
            self._plot_points = [
                PlotPoint(**item)
                for item in (self._session_state.plot_points or [])
                if isinstance(item, dict)
            ]
        elif is_recovery:
            # 从前端传入的数据恢复，兼容旧逻辑
            self._current_chapter = current_chapter
            if not self._story_beginning:
                self._story_beginning = story_beginning
            
            # 恢复章节数据，确保后续章节有上下文
            recovered_chapters = input_data.get("recovered_chapters", [])
            if recovered_chapters and isinstance(recovered_chapters, list):
                self._written_chapters = []
                for ch in recovered_chapters:
                    if isinstance(ch, dict) and ch.get("content"):
                        self._written_chapters.append({
                            "chapter_number": ch.get("chapter_number", len(self._written_chapters) + 1),
                            "title": ch.get("title", f"第{ch.get('chapter_number', len(self._written_chapters) + 1)}章"),
                            "content": ch.get("content", ""),
                            "word_count": ch.get("word_count", len(ch.get("content", "")))
                        })
                logger.info(f"[{self.name}] 已从前端恢复 {len(self._written_chapters)} 章数据")
                
                # 同步到持久化存储
                self._session_state.chapters = self._written_chapters.copy()
                self._session_state.current_chapter = current_chapter
                self._session_store.save(self._session_state)
            else:
                logger.warning(f"[{self.name}] 恢复会话时缺少完整章节数据，将使用故事开头作为上下文")
            
            logger.info(f"[{self.name}] 已恢复会话，当前章节: {current_chapter}")
        else:
            self._current_chapter = 0
            self._written_chapters = []
            self._story_beginning = story_beginning
            self._user_inspirations = []
            self._corrections = []
            self._characters = {}
            self._plot_points = []
            self._dead_characters = []
            
            # 更新持久化会话
            self._session_state.story_beginning = story_beginning
            self._session_store.save(self._session_state)
            
            logger.info(f"[{self.name}] 开始新故事")
        
        return await self._write_chapter(input_data, context)
    
    async def _continue_writing(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """继续续写下一章。"""
        if not self._is_running and not self._written_chapters:
            return {"success": False, "error": "请先开始一个新故事"}
        
        self._is_running = True
        self._should_stop = False
        
        extra_inspiration = input_data.get("content", "")
        if extra_inspiration:
            self._add_inspiration({"content": extra_inspiration, "chapter": self._current_chapter + 1})
        
        return await self._write_chapter(input_data, context)
    
    async def _regenerate_chapter(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """重新生成指定章节，默认从该章开始重建。"""
        chapter_number = int(input_data.get("chapter_number", 0) or 0)
        if chapter_number <= 0:
            return {"success": False, "error": "invalid chapter number"}
        
        target_index = None
        for idx, ch in enumerate(self._written_chapters):
            if ch.get("chapter_number") == chapter_number:
                target_index = idx
                break
        
        if target_index is None:
            return {"success": False, "error": f"chapter {chapter_number} not found"}
        
        self._is_running = True
        self._should_stop = False
        
        removed = self._written_chapters[target_index:]
        removed_numbers = [ch.get("chapter_number") for ch in removed if ch.get("chapter_number")]
        
        self._written_chapters = self._written_chapters[:target_index]
        self._current_chapter = chapter_number - 1
        
        # 清理被移除章节对应的灵感与纠正
        self._user_inspirations = [i for i in self._user_inspirations if i.get("chapter", 0) < chapter_number]
        self._corrections = [c for c in self._corrections if c.get("chapter", 0) < chapter_number]
        
        # 同步删除知识库中的相关章节
        if removed_numbers and self.knowledge_base:
            for num in removed_numbers:
                try:
                    self.knowledge_base.delete_chapter(f"chapter_{num}")
                except Exception as e:
                    logger.warning(f"[{self.name}] 删除知识库章节失败: chapter_{num}, {e}")
        
        # 同步会话
        self._sync_to_session()
        
        extra_inspiration = input_data.get("content", "")
        if extra_inspiration:
            self._add_inspiration({"content": extra_inspiration, "chapter": chapter_number})
        
        return await self._write_chapter(input_data, context)
    
    async def _write_chapter(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """创作一个章节。"""
        self._current_chapter += 1
        chapter_number = self._current_chapter
        
        await self.notify_progress(f"正在创作第{chapter_number}章...", 0)
        
        # 检测模型切换，补充额外上下文
        model_switch_context = self._get_model_switch_context()
        
        await self.notify_progress("正在读取知识库...", 10)
        kb_summaries = await self._retrieve_summaries_from_knowledge_base()
        
        await self.notify_progress("正在检索相关剧情...", 20)
        kb_context = await self._retrieve_from_knowledge_base(chapter_number)
        
        trends_data = []
        if self._trends_enabled:
            await self.notify_progress("正在搜索热点...", 30)
            trends_data = await self._search_trends()
        
        recent_chapters = self._get_recent_chapters()
        chapter_inspirations = [i for i in self._user_inspirations if i.get("chapter") == chapter_number]
        chapter_corrections = [c for c in self._corrections if c.get("chapter") == chapter_number]
        
        await self.notify_progress("正在构建提示词...", 40)
        
        prompt = self._build_chapter_prompt(
            chapter_number=chapter_number,
            story_beginning=self._story_beginning if chapter_number == 1 else "",
            recent_chapters=recent_chapters,
            kb_context=kb_context,
            kb_summaries=kb_summaries,
            trends_data=trends_data,
            inspirations=chapter_inspirations,
            corrections=chapter_corrections,
            model_switch_context=model_switch_context  # 鏂板锛氭ā鍨嬪垏鎹笂涓嬫枃
        )
        
        start_time = time.time()
        
        try:
            response = await self._call_chapter_llm(prompt)
            
            chapter_data = self._parse_chapter_response(response, chapter_number)
            chapter_data["model_used"] = self._current_model
            duration = time.time() - start_time
            
            logger.info(
                f"[{self.name}] Completed chapter {chapter_number}: "
                f"{chapter_data['word_count']} words, model={self._current_model}"
            )
            
            # 后处理验证，作为提示词约束外的第二道防线
            validation_result = None
            if self._enable_post_validation and self._content_validator:
                await self.notify_progress("正在验证内容一致性...", 85)
                
                content = chapter_data["content"]
                validation_result = self._content_validator.validate(
                    content,
                    chapter_number,
                    auto_fix=self._auto_fix_violations
                )
                
                if validation_result.auto_fixed and validation_result.fixed_content:
                    # 应用自动修正
                    chapter_data["content"] = validation_result.fixed_content
                    chapter_data["word_count"] = len(re.sub(r'\s+', '', validation_result.fixed_content))
                    chapter_data["auto_fixed"] = True
                    logger.info(f"[{self.name}] 已应用自动修正")
                
                if validation_result.has_critical:
                    # 存在严重违规，记录警告
                    chapter_data["validation_warnings"] = [
                        v.description for v in validation_result.violations
                    ]
                    logger.warning(f"[{self.name}] Detected {len(validation_result.violations)} validation violations")
            
            self._update_character_states(chapter_data)
            self._written_chapters.append(chapter_data)
            
            # 同步到持久化存储，确保数据不丢失
            self._sync_to_session()

            if self.write_config.auto_save_to_kb:
                await self._save_to_knowledge_base(chapter_data)

            # 自动生成章节摘要
            try:
                from novel_agent.chapter_summary_service import (
                    get_auto_summary_enabled,
                    generate_chapter_summary,
                    save_chapter_summary_to_library,
                )
                if get_auto_summary_enabled(self._project_id):
                    summary = await generate_chapter_summary(
                        chapter_number=chapter_data["chapter_number"],
                        title=chapter_data.get("title", ""),
                        content=chapter_data.get("content", ""),
                    )
                    save_chapter_summary_to_library(
                        chapter_data["chapter_number"],
                        summary,
                        source_mode="infinite_write",
                    )
            except Exception as e:
                logger.warning(f"[ContinuousWriter] Auto chapter summary failed: {e}")

            await self.notify_progress(f"第{chapter_number}章创作完成", 100, {"chapter": chapter_data})
            
            result = {
                "success": True,
                "chapter": chapter_data,
                "waiting_for_input": self.write_config.pause_for_user_input,
                "message": "章节创作完成",
                "session_id": self._session_id,
                "persisted": True
            }
            
            # 附加验证结果
            if validation_result:
                result["validation"] = {
                    "passed": validation_result.is_valid,
                    "auto_fixed": validation_result.auto_fixed,
                    "warnings": [v.description for v in validation_result.violations] if validation_result.violations else []
                }
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 创作失败: {e}")
            self._current_chapter -= 1
            return {"success": False, "chapter_number": chapter_number, "error": str(e)}

    def _should_stream_chapter_generation(self) -> bool:
        """Use provider streaming for relay-backed long chapter generation."""
        return self._api_type in {"openai_responses", "anthropic"} or self._is_tsc5_api_base()

    async def _call_chapter_llm(self, prompt: str) -> str:
        result = await self.call_llm(
            [{"role": "user", "content": prompt}],
            stream=self._should_stream_chapter_generation(),
        )
        if hasattr(result, "__aiter__"):
            chunks: List[str] = []
            async for chunk in result:
                if chunk:
                    chunks.append(str(chunk))
            return "".join(chunks)
        return str(result or "")

    def _build_chapter_prompt(
        self,
        chapter_number: int,
        story_beginning: str,
        recent_chapters: List[Dict[str, Any]],
        kb_context: Dict[str, Any],
        kb_summaries: List[Dict[str, Any]] = None,
        trends_data: List[Dict[str, Any]] = None,
        inspirations: List[Dict[str, Any]] = None,
        corrections: List[Dict[str, Any]] = None,
        model_switch_context: str = ""
    ) -> str:
        """构建章节续写提示词。"""
        parts = []
        inspirations = inspirations or []
        corrections = corrections or []
        kb_summaries = kb_summaries or []
        trends_data = trends_data or []
        
        # 模型切换时补充完整故事上下文
        if model_switch_context:
            parts.append("[重要提示：模型已切换，请仔细阅读以下完整上下文]")
            parts.append(model_switch_context)
            parts.append("")
        
        if kb_summaries:
            parts.append("[剧情总结]")
            for s in kb_summaries:
                parts.append(f"{s.get('chapter_range', '')}: {s.get('content', '')}")
            parts.append("")
        
        if story_beginning:
            parts.append(f"[故事开头核心设定]\n{story_beginning[:600]}\n")
        
        if trends_data:
            parts.append("[热点融合要求]")
            parts.append("请从热点候选中选择 1-2 条与当前剧情最契合的内容进行改编融入。")
            parts.append("不要原样照抄热点标题，不要写成新闻播报，要转化为角色动机/冲突/事件触发。")
            parts.append("")
            parts.append("[热点候选]")
            trend_candidates = self._select_balanced_trend_candidates(trends_data, limit=5)
            for t in trend_candidates:
                title = (t.get("title") or "").strip()
                if not title:
                    continue
                platform = (t.get("platform") or "").strip()
                hot = (t.get("hot") or "").strip()
                source = f"[{platform}]" if platform else ""
                heat = f"（热度:{hot}）" if hot else ""
                parts.append(f"- {source}{title}{heat}")
            parts.append("")
        if kb_context.get("relevant_content"):
            parts.append("[知识库信息]")
            for item in kb_context["relevant_content"]:
                parts.append(f"- {item}")
            parts.append("")
        else:
            lib_ctx = self._get_library_context()
            if lib_ctx:
                parts.append(lib_ctx)
                parts.append("")
        
        # 合并知识库和内存中的死亡角色约束
        all_dead = set(self._dead_characters)
        if kb_context.get("dead_characters"):
            all_dead.update(kb_context["dead_characters"])
        
        if all_dead:
            parts.append("[已死亡角色 - 绝对禁止复活]")
            parts.append("以下角色已在之前的章节中死亡，绝对不能让他们以活人身份出现：")
            for char in sorted(all_dead):
                parts.append(f"  - {char}")
            parts.append("")
        
        # 剧情约束（从知识库检索）
        if kb_context.get("plot_constraints"):
            parts.append("[重要剧情约束]")
            for constraint in kb_context["plot_constraints"][:5]:
                doc = constraint.get("document", "")
                if doc:
                    # 只提取关键信息
                    lines = doc.split("\n")[:10]
                    for line in lines:
                        if line.strip() and not line.startswith("==="):
                            parts.append(f"  {line}")
            parts.append("")
        
        # 增强前情回顾，提供更详细的章节内容
        if recent_chapters:
            parts.append("[前情回顾]")
            for ch in recent_chapters:
                ch_num = ch.get('chapter_number')
                title = ch.get('title', '')
                summary = ch.get('summary', '')[:300]
                parts.append(f"第{ch_num}章 {title}:")
                parts.append(f"  {summary}...")
            parts.append("")
            
            # 最后一章的完整内容，确保续写连贯
            if recent_chapters:
                last_chapter = recent_chapters[-1]
                last_content = last_chapter.get('content', '')
                if last_content:
                    parts.append("[上一章结尾（请直接续写）]")
                    parts.append(last_content[-1500:])
                    parts.append("")

        if self.write_config.check_consistency:
            character_memory = self._build_character_memory_block()
            if character_memory:
                parts.append("[角色状态锚点]")
                parts.append(character_memory)
                parts.append("")

            setting_memory = self._build_setting_memory_block(story_beginning, recent_chapters)
            if setting_memory:
                parts.append("[设定与场景锚点]")
                parts.append(setting_memory)
                parts.append("")

            preflight = self._build_preflight_consistency_checklist(recent_chapters)
            if preflight:
                parts.append("[续写前检查]")
                parts.append(preflight)
                parts.append("")
        
        if inspirations:
            parts.append("[灵感]")
            for insp in inspirations:
                parts.append(f"- {insp.get('content', '')}")
            parts.append("")
        
        if corrections:
            parts.append("[纠正]")
            for corr in corrections:
                parts.append(f"- {corr.get('content', '')}")
            parts.append("")
        
        target = self.write_config.words_per_chapter
        min_w = int(target * 0.90)
        max_w = int(target * 1.10)
        
        parts.append("[写作要求]")
        parts.append("1. 先保证前文记忆、人物状态、世界设定、时间线不出错。")
        parts.append("2. 再自然承接上一章结尾，推进当前冲突或目标。")
        parts.append("3. 若使用热点，只能改写成剧情素材，不能写成新闻播报或生硬插入。")
        parts.append("4. 直接输出小说正文，不要附加章节信息、检查过程或解释。")
        parts.append("")
        parts.append("[记忆使用]")
        if all_dead:
            parts.append("已提供的前情、知识库、剧情总结、角色状态和约束就是本次可用记忆；涉及已离场角色时，以前文事实为准。")
        else:
            parts.append("已提供的前情、知识库、剧情总结、角色状态和约束就是本次可用记忆；重要设定以前文事实为准。")
        parts.append("")
        parts.append(f"[字数限制] {min_w}-{max_w}字，目标{target}字")
        parts.append(f"[任务] 请创作第{chapter_number}章")
        if all_dead:
            parts.append("[注意] 请保持与前文剧情连贯，不要重复已有内容；已离场角色只按前文允许的方式出现；不要输出正文外说明")
        else:
            parts.append("[注意] 请保持与前文剧情连贯，不要重复已有内容，不要输出正文外说明")

        mandatory_tail_marker = "[写作要求]"

        prompt_text = "\n".join(parts)
        estimated_tokens = len(prompt_text) // 2
        max_tokens = WRITING_CONFIG.MAX_CONTEXT_TOKENS

        if estimated_tokens > max_tokens:
            mandatory_tail = ""
            mt_idx = prompt_text.find(mandatory_tail_marker)
            if mt_idx != -1:
                mandatory_tail = prompt_text[mt_idx:]
                prompt_text = prompt_text[:mt_idx]

            budget_chars = max_tokens * 2 - len(mandatory_tail)
            low_priority_markers = [
                "[热点融合要求]", "[热点候选]",
                "[知识库信息]",
                "[故事开头核心设定]",
                "[设定与场景锚点]",
            ]
            for marker in low_priority_markers:
                if len(prompt_text) <= budget_chars:
                    break
                idx = prompt_text.find(marker)
                if idx == -1:
                    continue
                end = prompt_text.find("\n[", idx + len(marker))
                if end == -1:
                    prompt_text = prompt_text[:idx]
                else:
                    prompt_text = prompt_text[:idx] + prompt_text[end:]

            prompt_text = prompt_text.rstrip() + "\n" + mandatory_tail
            logger.warning(
                f"[{self.name}] 提示词超出token预算: "
                f"{estimated_tokens}>{max_tokens}, 已截断至{len(prompt_text)//2}"
            )

        return self._ensure_text_integrity(prompt_text, "章节提示词")

    def _normalize_chapter_title(self, title: str, chapter_number: int) -> str:
        """Return a display title without chapter-number or Markdown heading markers."""
        cleaned = str(title or "").strip()
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned).strip()
        cleaned = re.sub(r"[*_`~]+", "", cleaned).strip()
        cleaned = _CHAPTER_TITLE_PREFIX_RE.sub("", cleaned, count=1).strip()
        cleaned = re.sub(r"^[\-—:：、.．\s]+", "", cleaned).strip()
        if _BARE_CHAPTER_TITLE_RE.fullmatch(cleaned):
            cleaned = ""
        return cleaned or f"第{chapter_number}章"

    def _split_chapter_heading(self, response: str, chapter_number: int) -> tuple[str, str]:
        """Extract a leading chapter heading and remove it from the body."""
        text = str(response or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        for pattern in (_MARKDOWN_CHAPTER_HEADING_RE, _PLAIN_CHAPTER_HEADING_RE):
            match = pattern.match(text)
            if match:
                title = self._normalize_chapter_title(match.group("title") or "", chapter_number)
                return title, text[match.end():].strip()

        return self._normalize_chapter_title("", chapter_number), text

    def _parse_chapter_response(self, response: str, chapter_number: int) -> Dict[str, Any]:
        """解析 LLM 响应。"""
        title, content = self._split_chapter_heading(response, chapter_number)
        chapter_info = {}
        
        info_match = re.search(r'---\n.+?(.*?)(?:$|\n---)', content, re.DOTALL)
        if info_match:
            content = content[:info_match.start()].strip()

        self._ensure_chapter_like_content(content, chapter_number)
        
        word_count = len(re.sub(r'\s+', '', content))
        
        target = self.write_config.words_per_chapter
        max_w = int(target * 1.15)
        
        if word_count > max_w:
            logger.warning(f"[{self.name}] 字数超标: {word_count} > {max_w}")
            content = self._smart_truncate(content, max_w)
            word_count = len(re.sub(r'\s+', '', content))
        
        summary = content[:200] + "..." if len(content) > 200 else content
        
        return {
            "chapter_number": chapter_number,
            "title": title,
            "content": content,
            "word_count": word_count,
            "summary": summary,
            **chapter_info
        }

    def _ensure_chapter_like_content(self, content: str, chapter_number: int) -> None:
        """阻止将需求收集或说明性回复误存为章节正文。"""
        text = str(content or "").strip()
        if not text:
            raise ValueError(f"第{chapter_number}章生成失败：模型返回空正文")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        bullet_lines = [line for line in lines if re.match(r"^[-*]\s+", line)]
        question_lines = [line for line in lines if "？" in line or "?" in line]
        matched_patterns = [
            pattern for pattern in NON_CHAPTER_RESPONSE_PATTERNS
            if re.search(pattern, text)
        ]

        if len(matched_patterns) >= 2:
            raise ValueError(
                f"第{chapter_number}章生成失败：模型返回了需求收集/说明性内容，未输出小说正文"
            )

        if len(bullet_lines) >= 3 and (question_lines or "请告诉我" in text or "比如" in text):
            raise ValueError(
                f"第{chapter_number}章生成失败：模型返回了列表式说明而非章节正文"
            )
    
    def _smart_truncate(self, content: str, max_words: int) -> str:
        """鏅鸿兘鎴柇"""
        current = len(re.sub(r'\s+', '', content))
        if current <= max_words:
            return content
        
        paragraphs = content.split('\n\n')
        result = []
        total = 0
        
        for para in paragraphs:
            para_words = len(re.sub(r'\s+', '', para))
            if total + para_words <= max_words:
                result.append(para)
                total += para_words
            else:
                break

        truncated = '\n\n'.join(result).strip()
        if truncated:
            return truncated
        kept: List[str] = []
        visible_count = 0
        for char in content:
            if not char.isspace():
                visible_count += 1
            if visible_count > max_words:
                break
            kept.append(char)
        return ''.join(kept).strip()
    
    def _update_character_states(self, chapter_data: Dict[str, Any]) -> None:
        """根据最新章节更新角色状态与剧情锚点。"""
        content = str(chapter_data.get("content") or "").strip()
        chapter_number = int(chapter_data.get("chapter_number") or 0)
        if not content or chapter_number <= 0:
            return

        known_names = self._known_character_names()
        for name, note in self._extract_character_state_notes(content, known_names).items():
            state = self._characters.get(name) or CharacterState(name=name)
            state.last_chapter = chapter_number
            if note:
                state.notes.append(note)
                state.notes = state.notes[-5:]
            inferred_location = self._infer_character_location(note)
            if inferred_location:
                state.location = inferred_location
            inferred_status = self._infer_character_status(note)
            if inferred_status:
                state.status = inferred_status
                if self._character_manager and inferred_status in ("死亡", "陨落"):
                    try:
                        self._character_manager.update_character(name, {"status": "deceased"})
                    except Exception:
                        pass
            self._characters[name] = state

        for name, abilities in self._extract_character_ability_events(content).items():
            state = self._characters.get(name) or CharacterState(name=name)
            state.last_chapter = max(state.last_chapter, chapter_number)
            new_abilities = [
                ability
                for ability in abilities
                if ability and ability not in state.learned_abilities
            ]
            if not new_abilities:
                self._characters[name] = state
                continue
            state.learned_abilities.extend(new_abilities)
            state.learned_abilities = state.learned_abilities[-12:]
            state.notes.append(f"第{chapter_number}章获得/掌握：" + "、".join(new_abilities))
            state.notes = state.notes[-5:]
            self._sync_character_abilities_to_manager(name, new_abilities)
            self._characters[name] = state

        self._plot_points.extend(self._extract_plot_points(content, chapter_number))
        self._plot_points = self._plot_points[-20:]

    def _known_character_names(self) -> List[str]:
        names = set(self._characters.keys())
        manager = self._character_manager
        manager_chars = getattr(manager, "characters", None)
        if isinstance(manager_chars, dict):
            names.update(str(name).strip() for name in manager_chars.keys() if str(name).strip())
        return sorted(names, key=len, reverse=True)

    def _sync_character_abilities_to_manager(self, name: str, abilities: List[str]) -> None:
        if not self._character_manager or not name or not abilities:
            return
        try:
            character = self._character_manager.get_character(name)
            if not character:
                return
            merged = list(getattr(character, "abilities", []) or [])
            changed = False
            for ability in abilities:
                if ability and ability not in merged:
                    merged.append(ability)
                    changed = True
            if changed:
                self._character_manager.update_character(name, {"abilities": merged})
        except Exception as exc:
            logger.warning(f"[{self.name}] 同步角色能力到CharacterManager失败: {exc}")

    def _get_library_context(self) -> str:
        try:
            if self._library_service is None:
                from novel_agent.library_service import get_library_service
                self._library_service = get_library_service()
            svc = self._library_service
            if svc.is_degraded:
                return ""
            parts = []
            chars = svc.list_entries(entry_type="character")
            if chars:
                parts.append("[资料库-角色]")
                for c in chars[:10]:
                    name = c.content_structured.get("name", c.title)
                    role = c.content_structured.get("role", "")
                    parts.append(f"- {name}: {role}")
            worlds = svc.list_entries(entry_type="world")
            if worlds:
                parts.append("[资料库-世界观]")
                for w in worlds[:3]:
                    world_data = w.content_structured.get("world", {})
                    name = world_data.get("name", w.title) if isinstance(world_data, dict) else w.title
                    parts.append(f"- {name}")
            outline = svc.list_entries(entry_type="outline")
            if outline:
                chapters = outline[0].content_structured.get("chapters", [])
                if chapters:
                    parts.append(f"[资料库-大纲] 共{len(chapters)}章")
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    async def _retrieve_from_knowledge_base(self, chapter_number: int) -> Dict[str, Any]:
        """
        从知识库检索上下文（增强版）。
        
        优先使用 SeekDB 高级搜索能力：
        - 动态权重调整
        - 智能重排
        - 上下文压缩
        """
        if not self.knowledge_base:
            return {"relevant_content": [], "plot_constraints": [], "dead_characters": [], "writing_context": {}}
        
        result = {
            "relevant_content": [],
            "plot_constraints": [],
            "dead_characters": [],
            "writing_context": {}
        }
        
        try:
            # 鏋勫缓鏌ヨ
            recent = ""
            if self._written_chapters:
                recent = self._written_chapters[-1].get("content", "")[:500]
            elif self._story_beginning:
                recent = self._story_beginning[:500]
            
            if recent and self._use_advanced_search:
                # 浣跨敤楂樼骇鎼滅储锛堝弬鑰?SeekDB 浼樺寲锛?
                try:
                    # 鑾峰彇鍐欎綔涓婁笅鏂囷紙涓€绔欏紡鑾峰彇鎵€鏈夌浉鍏充俊鎭級
                    writing_context = self.knowledge_base.get_context_for_writing(
                        query=recent,
                        current_chapter=chapter_number,
                        max_tokens=2000,
                        include_constraints=True
                    )
                    result["writing_context"] = writing_context
                    
                    # 鎻愬彇鐩稿叧鍐呭
                    for item in writing_context.get("relevant_content", []):
                        content = item.get("content", "")[:200]
                        if content:
                            result["relevant_content"].append(content)
                    
                    # 鎻愬彇绾︽潫
                    for constraint in writing_context.get("constraints", []):
                        result["plot_constraints"].append({
                            "type": constraint.get("type"),
                            "description": constraint.get("description"),
                            "entities": constraint.get("entities", [])
                        })
                    
                    # 姝讳骸瑙掕壊
                    result["dead_characters"] = writing_context.get("dead_characters", [])
                    
                    logger.debug(f"[{self.name}] 高级搜索完成，token 估算: {writing_context.get('total_tokens_estimate', 0)}")
                    
                except AttributeError:
                    # 知识库不支持高级搜索，回退到基础模式
                    logger.debug(f"[{self.name}] 知识库不支持高级搜索，回退到基础模式")
                    self._use_advanced_search = False
            
            # 鍩虹鎼滅储锛堜綔涓哄悗澶囨垨楂樼骇鎼滅储涓嶅彲鐢ㄦ椂锛?
            if not self._use_advanced_search and recent:
                resp = self.knowledge_base.search(query=recent, top_k=self.write_config.kb_search_top_k)
                result["relevant_content"] = [r.document[:200] for r in resp.results if r.metadata.get("type") != "plot_constraints"]
            
            # 妫€绱㈠墽鎯呯害鏉燂紙鍏抽敭锛氶槻姝㈣鑹插娲荤瓑闂锛?
            if self._constraint_store:
                constraints = self._constraint_store.search_constraints(
                    query=recent[:200] if recent else "",
                    top_k=5
                )
                # 鍚堝苟绾︽潫
                for c in constraints:
                    if c not in result["plot_constraints"]:
                        result["plot_constraints"].append(c)
                
                # 鑾峰彇鎵€鏈夋浜¤鑹插垪琛?
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in result["dead_characters"]:
                        result["dead_characters"].append(char)
                
                # 鍚屾鍒板唴瀛樼姸鎬?
                for char in result["dead_characters"]:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                        logger.info(f"[{self.name}] 从知识库同步死亡角色: {char}")
                
        except Exception as e:
            logger.warning(f"[{self.name}] 知识库检索失败: {e}")
        
        return result
    
    async def _retrieve_summaries_from_knowledge_base(self) -> List[Dict[str, Any]]:
        """从知识库检索剧情总结。"""
        if not self.knowledge_base:
            return []
        
        try:
            resp = self.knowledge_base.search(
                query="剧情总结",
                top_k=self.write_config.kb_summary_top_k
            )
            return [{"chapter_range": "", "content": r.document[:500]} for r in resp.results]
        except Exception as e:
            logger.debug(f"[{self.name}] 检索剧情总结失败: {e}")
        
        return []

    def _select_balanced_trend_candidates(
        self,
        trends_data: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """按平台轮询挑选热点，避免单个平台占满候选位。"""
        if not trends_data or limit <= 0:
            return []

        platform_buckets: Dict[str, List[Dict[str, Any]]] = {}
        platform_order: List[str] = []

        for trend in trends_data:
            platform = (trend.get("platform") or "").strip().lower()
            if platform not in platform_buckets:
                platform_buckets[platform] = []
                platform_order.append(platform)
            platform_buckets[platform].append(trend)

        merged: List[Dict[str, Any]] = []
        cursor = {platform: 0 for platform in platform_order}
        while len(merged) < limit:
            appended = False
            for platform in platform_order:
                idx = cursor[platform]
                items = platform_buckets.get(platform, [])
                if idx >= len(items):
                    continue
                merged.append(items[idx])
                cursor[platform] = idx + 1
                appended = True
                if len(merged) >= limit:
                    break
            if not appended:
                break

        return merged

    @staticmethod
    def _extract_trend_tool_error(result: Any) -> str:
        if result is None:
            return ""
        if hasattr(result, "content") and result.content:
            first = result.content[0]
            text = getattr(first, "text", "")
            if isinstance(text, str):
                return text.strip()
        return ""

    def _build_trend_tool_candidates(self, platform: str) -> List[str]:
        normalized = (platform or "").strip().lower()
        if not normalized:
            return []

        candidates: List[str] = []

        def _add(tool_name: str) -> None:
            if tool_name and tool_name not in candidates:
                candidates.append(tool_name)

        mapped = self._get_trend_tool_name(normalized)
        _add(mapped)

        modern = f"get_{normalized}_trending"
        _add(modern)
        _add(modern.replace("_", "-"))

        if mapped:
            _add(mapped.replace("_", "-"))

        return candidates
    
    async def _search_trends(self) -> List[Dict[str, Any]]:
        """搜索热点。"""
        trends: List[Dict[str, Any]] = []

        def _extract_tag(text: str, tag: str) -> str:
            if not text:
                return ""
            match = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
            return (match.group(1).strip() if match else "")

        def _strip_xml(text: str) -> str:
            if not text:
                return ""
            return re.sub(r"<[^>]+>", "", text).strip()

        def _parse_trend_payload(payload: Any) -> List[Dict[str, str]]:
            rows: List[Dict[str, str]] = []
            if payload is None:
                return rows

            if isinstance(payload, list):
                for item in payload:
                    rows.extend(_parse_trend_payload(item))
                return rows

            if isinstance(payload, dict):
                for key in ("data", "list", "items", "result"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        rows.extend(_parse_trend_payload(value))
                        return rows

                title_val = payload.get("title") or payload.get("name") or payload.get("content") or ""
                if isinstance(title_val, (dict, list)):
                    rows.extend(_parse_trend_payload(title_val))
                    return rows

                title_text = str(title_val or "").strip()
                title = _extract_tag(title_text, "title") or _strip_xml(title_text) or title_text
                if title:
                    hot_val = payload.get("hot") or payload.get("hotValue") or payload.get("heat") or payload.get("popularity") or payload.get("score") or ""
                    url_val = payload.get("url") or payload.get("link") or ""
                    rows.append(
                        {
                            "title": str(title),
                            "hot": str(hot_val or ""),
                            "url": str(url_val or ""),
                        }
                    )
                return rows

            if isinstance(payload, str):
                text = payload.strip()
                if not text:
                    return rows
                try:
                    parsed = json.loads(text)
                    rows.extend(_parse_trend_payload(parsed))
                    return rows
                except json.JSONDecodeError:
                    title = _extract_tag(text, "title") or _strip_xml(text) or text
                    if title:
                        rows.append(
                            {
                                "title": str(title),
                                "hot": _extract_tag(text, "popularity"),
                                "url": _extract_tag(text, "link"),
                            }
                        )
                return rows

            return rows

        try:
            selected_platforms: List[str] = []
            for platform in self.write_config.trends_platforms:
                normalized = (platform or "").strip().lower()
                if normalized and normalized not in selected_platforms:
                    selected_platforms.append(normalized)

            total_limit = int(self.write_config.trends_limit or 0)
            if not selected_platforms or total_limit <= 0:
                self._cached_trends = []
                return []

            seen_titles = set()
            platform_trends: Dict[str, List[Dict[str, Any]]] = {
                platform: [] for platform in selected_platforms
            }

            for platform in selected_platforms:
                try:
                    result = None
                    tool_candidates = self._build_trend_tool_candidates(platform)
                    used_tool = ""

                    for tool_name in tool_candidates:
                        try:
                            # 优先尝试以“类方法方式”调用，兼容测试中无 self 的猴补方法签名
                            try:
                                call_impl = getattr(BaseAgent, "use_skill")  # type: ignore[name-defined]
                                call_result = call_impl("trends_search", tool_name, limit=total_limit)  # type: ignore[misc]
                            except TypeError:
                                # 回退到实例方法调用
                                call_result = self.use_skill("trends_search", tool_name, limit=total_limit)
                        except Exception as call_error:
                            logger.debug(
                                f"[{self.name}] 热点工具调用异常({platform}, {tool_name}): {call_error}"
                            )
                            continue

                        # 检查 Skill 调用结果
                        if not call_result or not call_result.get("success"):
                            error_msg = call_result.get("error", "") if call_result else "unknown error"
                            lowered_error = error_msg.lower()
                            if "not found" in lowered_error:
                                logger.debug(
                                    f"[{self.name}] 热点工具不存在，尝试下一个候选: platform={platform}, tool={tool_name}"
                                )
                                continue
                            logger.debug(
                                f"[{self.name}] 热点工具调用失败({platform}, {tool_name}): {error_msg}"
                            )
                            call_result = None

                        if call_result and call_result.get("success"):
                            result = call_result
                            used_tool = tool_name
                            break

                    if result is None:
                        logger.debug(f"[{self.name}] 未获取到平台热点({platform})，候选工具: {tool_candidates}")
                        continue

                    # 处理 Skill 返回的数据
                    if result and result.get("data"):
                        data_items = result.get("data", [])
                        for item in data_items:
                            title = (item.get("title") or "").strip()
                            if not title or title in seen_titles:
                                continue
                            seen_titles.add(title)
                            platform_trends[platform].append(
                                {
                                    "title": title,
                                    "hot": (item.get("hot") or item.get("hotValue") or item.get("热度") or ""),
                                    "url": item.get("url", ""),
                                    "platform": platform,
                                }
                            )
                            if len(platform_trends[platform]) >= total_limit:
                                break

                    logger.debug(
                        f"[{self.name}] 平台热点获取成功: platform={platform}, tool={used_tool}, count={len(platform_trends[platform])}"
                    )
                except Exception as platform_error:
                    logger.debug(f"[{self.name}] 获取平台热点失败({platform}): {platform_error}")
                    continue

            merged_candidates: List[Dict[str, Any]] = []
            for platform in selected_platforms:
                merged_candidates.extend(platform_trends.get(platform, []))
            trends = self._select_balanced_trend_candidates(merged_candidates, limit=total_limit)
            self._cached_trends = trends
        except Exception as e:
            logger.error(f"[{self.name}] 热点搜索失败: {e}")
        return trends
    
    def _get_trend_tool_name(self, platform: str) -> str:
        """获取热点工具名。"""
        platform = (platform or "").strip().lower()
        m = {
            "douban": "get_douban_rank",
            "weread": "get_weread_rank",
            "zhihu": "get_zhihu_trending",
            "gcores": "get_gcores_new",
            "toutiao": "get_toutiao_trending",
            "netease": "get_netease_news_trending",
            "tencent": "get_tencent_news_trending",
            "thepaper": "get_thepaper_trending",
            "bilibili": "get_bilibili_rank",
            "douyin": "get_douyin_trending",
            "weibo": "get_weibo_trending",
            "36kr": "get_36kr_trending",
            "sspai": "get_sspai_rank",
            "ifanr": "get_ifanr_news",
            "juejin": "get_juejin_article_rank",
            "smzdm": "get_smzdm_rank",
        }
        return m.get(platform, f"get_{platform}_trending")
    
    async def _save_to_knowledge_base(self, chapter_data: Dict[str, Any]) -> None:
        """存入知识库并自动提取剧情约束。"""
        if not self.knowledge_base:
            return
        
        try:
            from ..chapter_knowledge_sync import upsert_knowledge_base_chapter

            # 存储章节内容。使用 upsert 避免重写章节时残留旧向量分块。
            upsert_knowledge_base_chapter(
                self.knowledge_base,
                chapter_id=f"chapter_{chapter_data['chapter_number']}",
                title=chapter_data["title"],
                content=chapter_data["content"],
                chapter_number=chapter_data["chapter_number"],
                metadata={
                    "word_count": chapter_data["word_count"],
                    "model_used": self._current_model,
                    "source_mode": "infinite_write",
                    "source_type": "continuous_write",
                    "source_session_id": self._session_id,
                }
            )
            
            # 鑷姩鎻愬彇骞跺瓨鍌ㄥ墽鎯呯害鏉燂紙鍏抽敭锛氱‘淇濊鑹叉浜＄瓑淇℃伅琚褰曪級
            if self._constraint_store:
                constraints = self._constraint_store.extract_and_store(
                    content=chapter_data["content"],
                    chapter_id=f"chapter_{chapter_data['chapter_number']}",
                    chapter_number=chapter_data["chapter_number"],
                    title=chapter_data["title"]
                )
                
                # 鏇存柊鍐呭瓨涓殑姝讳骸瑙掕壊鍒楄〃
                for constraint in constraints:
                    if constraint.constraint_type == "character_death":
                        for entity in constraint.entities:
                            if entity not in self._dead_characters:
                                self._dead_characters.append(entity)
                                logger.info(f"[{self.name}] 检测到角色死亡: {entity}")
                
                if constraints:
                    logger.info(f"[{self.name}] Extracted {len(constraints)} plot constraints")
            
        except Exception as e:
            logger.error(f"[{self.name}] 存储失败: {e}")
    
    def _add_inspiration(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """娣诲姞鐏垫劅"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "灵感内容不能为空"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._user_inspirations.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {"success": True, "message": "inspiration added"}
    
    def _add_correction(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """娣诲姞绾犳"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "纠正内容不能为空"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._corrections.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {"success": True, "message": "correction added"}
    
    def _add_dead_character(self, character_name: str) -> Dict[str, Any]:
        if character_name and character_name not in self._dead_characters:
            self._dead_characters.append(character_name)
            self._sync_to_session()
            if self._character_manager:
                try:
                    self._character_manager.update_character(character_name, {"status": "deceased"})
                except Exception as e:
                    logger.warning(f"[{self.name}] 同步角色死亡到CharacterManager失败: {e}")
            logger.info(f"[{self.name}] 记录角色死亡: {character_name}")
        return {"success": True, "dead_characters": self._dead_characters}
    
    def _stop_writing(self) -> Dict[str, Any]:
        """鍋滄缁啓"""
        self._is_running = False
        self._should_stop = True
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {
            "success": True,
            "message": "continuous writing stopped",
            "total_chapters": len(self._written_chapters),
            "total_words": sum(ch.get("word_count", 0) for ch in self._written_chapters),
            "session_id": self._session_id,
            "persisted": True
        }
    
    def _get_status(self) -> Dict[str, Any]:
        """鑾峰彇鐘舵€?"""
        return {
            "success": True,
            "is_running": self._is_running,
            "current_chapter": self._current_chapter,
            "total_chapters": len(self._written_chapters),
            "total_words": sum(ch.get("word_count", 0) for ch in self._written_chapters),
            "dead_characters": self._dead_characters,
            "trends_enabled": self._trends_enabled,
            "session_id": self._session_id,
            "last_model": self._current_model,
            "persisted": self._session_state is not None
        }
    
    def _enable_trends(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """鍚敤鐑偣"""
        self._trends_enabled = True
        self._trends_query = input_data.get("query", "")
        if input_data.get("platforms"):
            self.write_config.trends_platforms = input_data.get("platforms")
        return {"success": True, "message": "trends fusion enabled"}
    
    def _disable_trends(self) -> Dict[str, Any]:
        """绂佺敤鐑偣"""
        self._trends_enabled = False
        self._trends_query = ""
        self._cached_trends = []
        return {"success": True, "message": "trends fusion disabled"}
    
    def _get_chapter(self, chapter_number: int) -> Dict[str, Any]:
        """获取指定章节。"""
        for ch in self._written_chapters:
            if ch.get("chapter_number") == chapter_number:
                return {"success": True, "chapter": ch}
        return {"success": False, "error": f"chapter {chapter_number} not found"}
    
    def _apply_client_sync(
        self,
        chapters: List[Dict[str, Any]],
        current_chapter: int,
        deleted_chapters: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """将前端章节列表同步到后端会话。"""
        normalized = [ch for ch in chapters if isinstance(ch, dict)]
        normalized.sort(key=lambda x: x.get("chapter_number", 0))
        
        self._written_chapters = normalized
        
        if current_chapter > 0:
            self._current_chapter = current_chapter
        else:
            last_num = 0
            if normalized:
                last_num = max([c.get("chapter_number", 0) for c in normalized] or [0])
            self._current_chapter = last_num

        if not normalized and self._current_chapter == 0:
            self._story_beginning = ""
            self._dead_characters = []
            self._user_inspirations = []
            self._corrections = []
            self._characters = {}
            self._plot_points = []
            if self._session_state:
                self._session_state.story_beginning = ""
                self._session_state.dead_characters = []
                self._session_state.inspirations = []
                self._session_state.corrections = []
                self._session_state.character_states = {}
                self._session_state.plot_points = []
        
        deleted_chapters = deleted_chapters or []
        if deleted_chapters and self.knowledge_base:
            for num in deleted_chapters:
                try:
                    self.knowledge_base.delete_chapter(f"chapter_{num}")
                except Exception as e:
                    logger.warning(f"[{self.name}] 删除知识库章节失败: chapter_{num}, {e}")
        
        self._user_inspirations = [
            i for i in self._user_inspirations if i.get("chapter", 0) <= self._current_chapter + 1
        ]
        self._corrections = [
            c for c in self._corrections if c.get("chapter", 0) <= self._current_chapter + 1
        ]
        
        self._sync_to_session()
        
        return {
            "success": True,
            "message": "session synchronized",
            "current_chapter": self._current_chapter,
            "total_chapters": len(self._written_chapters)
        }
    
    def _get_recent_chapters(self) -> List[Dict[str, Any]]:
        """获取最近几章。"""
        return self._written_chapters[-self.write_config.context_chapters:]

    @staticmethod
    def _extract_character_state_notes(content: str, known_names: Optional[List[str]] = None) -> Dict[str, str]:
        notes: Dict[str, str] = {}
        sentences = re.split(r"(?<=[。！？!?])", content)
        known = sorted(
            {
                str(name or "").strip()
                for name in (known_names or [])
                if ContinuousWriter._looks_like_character_name(str(name or "").strip())
            },
            key=len,
            reverse=True,
        )
        for sentence in sentences:
            cleaned = sentence.strip()
            if not cleaned or cleaned.startswith("“") or cleaned.startswith("\""):
                continue
            names = [name for name in known if name in cleaned] if known else ContinuousWriter._extract_fallback_character_names(cleaned)
            for name in names:
                if name not in notes:
                    notes[name] = cleaned[:80]
        return notes

    @staticmethod
    def _looks_like_character_name(name: str) -> bool:
        if not name or name in _NON_CHARACTER_NAMES:
            return False
        if len(name) < 2 or len(name) > 4:
            return False
        if not re.fullmatch(r"[\u4e00-\u9fa5·]+", name):
            return False
        if any(part in name for part in _NON_CHARACTER_NAME_PARTS):
            return False
        return True

    @staticmethod
    def _extract_fallback_character_names(sentence: str) -> List[str]:
        names: List[str] = []

        def add_name(value: str) -> None:
            name = str(value or "").strip("，。！？；：、（）()《》“”\"' ")
            if ContinuousWriter._looks_like_character_name(name) and name not in names:
                names.append(name)

        follower = rf"(?:{_CHARACTER_NAME_FOLLOWERS})"
        prefix = rf"(?:{_CHARACTER_NAME_PREFIXES})"
        compound_name = rf"(?:{_COMPOUND_CHINESE_SURNAMES})[\u4e00-\u9fa5]{{1,2}}"
        single_name = rf"[{_COMMON_CHINESE_SURNAMES}][\u4e00-\u9fa5]{{1,2}}"
        patterns = [
            rf"({compound_name})(?={follower})",
            rf"({single_name})(?={follower})",
            rf"{prefix}({compound_name})",
            rf"{prefix}({single_name})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, sentence):
                add_name(match.group(1))

        return names

    def _extract_character_ability_events(self, content: str) -> Dict[str, List[str]]:
        """从章节正文中抽取“角色学会/觉醒/掌握能力”的明确事件。"""
        known_names = self._known_character_names()
        if not known_names:
            return {}

        events: Dict[str, List[str]] = {}
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", str(content or "")) if item.strip()]
        trigger_pattern = re.compile(r"(学会了?|习得了?|掌握了?|领悟了?|练成了?|觉醒了?|获得了?|参透了?|突破了?)")
        for sentence in sentences:
            if not trigger_pattern.search(sentence):
                continue
            matched_names = [name for name in known_names if name and name in sentence]
            if not matched_names:
                continue
            ability = self._extract_ability_name_from_sentence(sentence)
            if not ability:
                continue
            for name in matched_names:
                events.setdefault(name, [])
                if ability not in events[name]:
                    events[name].append(ability)
        return events

    @staticmethod
    def _extract_ability_name_from_sentence(sentence: str) -> str:
        text = str(sentence or "")
        trigger = re.search(r"(?:学会了?|习得了?|掌握了?|领悟了?|练成了?|觉醒了?|获得了?|参透了?|突破了?)", text)
        if not trigger:
            return ""
        tail = text[trigger.end():]
        tail = re.sub(r"^[的了一门一种一招新的\s，,：:]+", "", tail)
        suffix_pattern = (
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,16}?"
            r"(?:剑法|刀法|枪法|拳法|掌法|心法|功法|身法|步法|阵法|符法|术法|法术|秘术|神通|天赋|能力|技能|术|诀|法|剑|刀|拳|掌|步|咒|符))"
        )
        match = re.search(suffix_pattern, tail)
        if match:
            return match.group(1).strip("，,。；;、 的了")
        fallback = re.split(r"[，,。；;、\s]", tail, maxsplit=1)[0].strip("的了")
        return fallback[:16] if len(fallback) >= 2 else ""

    @staticmethod
    def _infer_character_location(note: str) -> str:
        match = re.search(r"(?:在|回到|来到|走进|站在|留在)([\u4e00-\u9fa5]{2,8}(?:城|镇|村|宫|殿|阁|楼|院|府|山|峰|谷|林|海|岛|桥|巷|街|房|室|厅|门|营|塔))", note or "")
        return match.group(1) if match else ""

    @staticmethod
    def _infer_character_status(note: str) -> str:
        text = note or ""
        for keyword in ("受伤", "虚弱", "愤怒", "慌乱", "警惕", "犹豫", "沉默", "冷静", "紧张", "疲惫", "失控"):
            if keyword in text:
                return keyword
        return ""

    @staticmethod
    def _extract_plot_points(content: str, chapter_number: int) -> List[PlotPoint]:
        points: List[PlotPoint] = []
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", content) if item.strip()]
        for sentence in sentences[:2]:
            points.append(
                PlotPoint(
                    chapter=chapter_number,
                    description=sentence[:80],
                    importance="high" if any(token in sentence for token in ("终于", "发现", "真相", "决定", "必须", "突然")) else "normal",
                )
            )
        return points

    def _build_character_memory_block(self) -> str:
        if not self._characters:
            return ""
        ranked = sorted(self._characters.values(), key=lambda item: (item.last_chapter, len(item.notes)), reverse=True)
        lines: List[str] = []
        for state in ranked[:8]:
            fragments = [state.name]
            if state.last_chapter:
                fragments.append(f"最近出现在第{state.last_chapter}章")
            status = normalize_character_status(state.status)
            if status and status != NORMAL_CHARACTER_STATUS:
                fragments.append(f"状态：{status}")
            if state.location:
                fragments.append(f"位置：{state.location}")
            if state.learned_abilities:
                fragments.append(f"能力：{'、'.join(state.learned_abilities[-4:])}")
            if state.notes:
                fragments.append(f"最近表现：{state.notes[-1]}")
            lines.append("；".join(fragments))
        return "\n".join(lines)

    def _build_setting_memory_block(self, story_beginning: str, recent_chapters: List[Dict[str, Any]]) -> str:
        anchors: List[str] = []
        if story_beginning:
            anchors.append(f"开篇设定：{story_beginning[:120].strip()}")
        for chapter in recent_chapters[-3:]:
            title = str(chapter.get("title") or "").strip()
            summary = str(chapter.get("summary") or "").strip()
            content = str(chapter.get("content") or "").strip()
            snippet = summary or content[:120]
            if snippet:
                anchors.append(f"第{chapter.get('chapter_number')}章 {title}：{snippet[:120]}")
        return "\n".join(anchors[:4])

    def _build_preflight_consistency_checklist(self, recent_chapters: List[Dict[str, Any]]) -> str:
        checklist: List[str] = [
            "1. 先核对角色称呼、身份、立场，别把同一个人写成两个版本。",
            "2. 先核对地点、时间、场景承接，别突然换地图。",
            "3. 先核对上一章刚发生的大事，别忘掉刚立住的冲突。",
        ]
        if self._characters:
            hot_names = [state.name for state in sorted(self._characters.values(), key=lambda item: item.last_chapter, reverse=True)[:3]]
            if hot_names:
                checklist.append(f"4. 本章重点盯住这些角色：{'、'.join(hot_names)}。")
        if recent_chapters:
            last_title = str(recent_chapters[-1].get("title") or "").strip() or f"第{recent_chapters[-1].get('chapter_number')}章"
            checklist.append(f"5. 本章必须顺着上一章《{last_title}》的结尾往下写。")
        if self._plot_points:
            latest_plot = self._plot_points[-1].description.strip()
            if latest_plot:
                checklist.append(f"6. 最近刚立住的剧情点：{latest_plot[:60]}。")
        checklist.append("7. 如果拿不准，就保守续写，优先沿用已有设定，不擅自加新设定。")
        return "\n".join(checklist)
    
    def get_all_chapters(self) -> List[Dict[str, Any]]:
        """获取全部章节。"""
        return self._written_chapters.copy()
    
    def set_knowledge_base(self, kb) -> None:
        """设置知识库实例。"""
        self.knowledge_base = kb
        
        # 初始化剧情约束存储
        if kb:
            try:
                self._constraint_store = get_plot_constraint_store(kb)
                logger.info(f"[{self.name}] Knowledge base and plot constraint store initialized")
                
                # 从知识库加载已有的死亡角色约束
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                
                if self._dead_characters:
                    logger.info(f"[{self.name}] Loaded dead-character constraints: {len(self._dead_characters)}")
                
                # 初始化内容验证器
                self._content_validator, _ = get_content_validator(self._constraint_store, kb)
                self._content_validator.load_constraints()
                logger.info(f"[{self.name}] 内容验证器已配置")
                
            except Exception as e:
                logger.warning(f"[{self.name}] 剧情约束存储初始化失败: {e}")
                self._constraint_store = None
                self._content_validator = None
        else:
            self._constraint_store = None
            try:
                self._content_validator, _ = get_content_validator(None, None)
            except Exception as exc:
                logger.warning(f"[{self.name}] 基础内容验证器初始化失败: {exc}")
                self._content_validator = None
            logger.info(f"[{self.name}] 知识库已清空")

    def set_character_manager(self, cm) -> None:
        """设置角色管理器实例，用于同步角色状态。"""
        self._character_manager = cm
        if cm:
            logger.info(f"[{self.name}] CharacterManager已配置")

    def set_session_id(self, session_id: str, project_id: str = "") -> None:
        """设置会话 ID。"""
        normalized_session_id = str(session_id or "default").strip() or "default"
        normalized_project_id = str(project_id or "").strip()
        session_changed = (
            normalized_session_id != self._session_id
            or normalized_project_id != self._project_id
        )
        if session_changed and (self._session_id or self._project_id):
            self._session_state = None
            self._story_beginning = ""
            self._current_chapter = 0
            self._is_running = False
            self._should_stop = False
            self._written_chapters = []
            self._dead_characters = []
            self._user_inspirations = []
            self._corrections = []
            self._characters = {}
            self._plot_points = []
        self._session_id = normalized_session_id
        self._project_id = normalized_project_id
        logger.info(f"[{self.name}] 会话 ID 已设置: {normalized_session_id}")
    
    def set_model(self, model: str) -> None:
        """设置当前模型。"""
        if model != self._current_model:
            logger.info(f"[{self.name}] 模型切换: {self._current_model} -> {model}")
        self._current_model = model
    
    def get_session_context(self) -> Dict[str, Any]:
        """
        获取会话上下文，供外部恢复续写使用。
        
        返回保持续写连续性所需的核心状态。
        """
        if self._session_state:
            return self._session_store.get_context_for_continuation(
                self._session_id,
                self._project_id
            )
        
        return {
            "session_id": self._session_id,
            "current_chapter": self._current_chapter,
            "story_beginning": self._story_beginning,
            "dead_characters": self._dead_characters,
            "last_model": self._current_model,
            "recent_chapters": self._get_recent_chapters()
        }
    
    def configure_advanced_search(
        self,
        use_advanced: bool = True,
        use_dynamic_weights: bool = True,
        use_reranking: bool = True,
        use_context_compression: bool = True
    ) -> None:
        """
        配置高级搜索选项。
        
        Args:
            use_advanced: 是否启用高级搜索
            use_dynamic_weights: 是否启用动态权重
            use_reranking: 是否启用重排
            use_context_compression: 是否启用上下文压缩
        """
        self._use_advanced_search = use_advanced
        self._use_dynamic_weights = use_dynamic_weights
        self._use_reranking = use_reranking
        self._use_context_compression = use_context_compression
        logger.info(
            f"[{self.name}] 高级搜索配置已更新: "
            f"advanced={use_advanced}, "
            f"dynamic_weights={use_dynamic_weights}, "
            f"reranking={use_reranking}, "
            f"compression={use_context_compression}"
        )
    
    async def recover_from_model_switch(self) -> Dict[str, Any]:
        """
        在模型切换后恢复续写上下文。
        
        Returns:
            恢复结果，包含加载的上下文信息。
        """
        result = {
            "success": True,
            "model_switched": False,
            "context_loaded": False,
            "dead_characters": [],
            "constraints": [],
            "recent_chapters_count": 0
        }
        
        if not self._session_state:
            result["message"] = "未找到会话状态"
            return result
        
        last_model = self._session_state.last_model
        if not last_model or last_model == self._current_model:
            result["message"] = "未检测到模型切换"
            return result
        
        result["model_switched"] = True
        logger.info(f"[{self.name}] 检测到模型切换，开始恢复上下文: {last_model} -> {self._current_model}")
        
        try:
            # 1. 从持久化存储恢复基础状态
            self._story_beginning = self._session_state.story_beginning
            self._current_chapter = self._session_state.current_chapter
            self._written_chapters = self._session_state.chapters.copy()
            self._dead_characters = self._session_state.dead_characters.copy()
            self._user_inspirations = self._session_state.inspirations.copy()
            self._corrections = self._session_state.corrections.copy()
            self._characters = {
                name: CharacterState(**payload) if isinstance(payload, dict) else CharacterState(name=name)
                for name, payload in (self._session_state.character_states or {}).items()
            }
            self._plot_points = [
                PlotPoint(**item)
                for item in (self._session_state.plot_points or [])
                if isinstance(item, dict)
            ]
            
            result["recent_chapters_count"] = len(self._written_chapters)
            
            # 2. 从知识库补齐最新约束
            if self.knowledge_base:
                try:
                    # 获取活动约束
                    constraints = self.knowledge_base.get_active_constraints()
                    result["constraints"] = [c.title for c in constraints[:5]]
                    
                    # 同步死亡角色
                    dead_chars = self.knowledge_base.get_dead_characters()
                    for char in dead_chars:
                        if char not in self._dead_characters:
                            self._dead_characters.append(char)
                    
                    result["dead_characters"] = self._dead_characters.copy()
                    
                except Exception as e:
                    logger.warning(f"[{self.name}] 从知识库恢复约束失败: {e}")
            
            result["context_loaded"] = True
            result["message"] = f"模型切换后已恢复上下文，加载 {result['recent_chapters_count']} 章"
            
            # 更新会话中的模型信息
            self._session_state.last_model = self._current_model
            self._session_store.save(self._session_state)
            
        except Exception as e:
            logger.error(f"[{self.name}] 模型切换恢复失败: {e}")
            result["success"] = False
            result["message"] = f"恢复失败: {e}"
        
        return result


