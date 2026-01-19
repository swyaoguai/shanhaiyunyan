# -*- coding: utf-8 -*-
"""
无限续写Agent
用于根据用户提供的故事开头或灵感进行续写创作
每章完成后自动存入知识库，防止剧情重复和设定冲突

增强功能：
- 会话持久化：服务重启后可恢复续写
- 模型切换保持连贯：换模型后自动传递完整上下文
- 章节连贯性保证：通过持久化的剧情摘要确保一致性
- SeekDB 优化：动态搜索权重、智能重排序、上下文压缩
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
from .session_store import get_session_store, SessionState
from ..agent_config import AgentModelConfig

# 延迟导入剧情约束模块，避免循环依赖
PlotConstraintStore = None
ContentValidator = None
PostGenerationProcessor = None

def get_plot_constraint_store(knowledge_base):
    """获取剧情约束存储实例"""
    global PlotConstraintStore
    if PlotConstraintStore is None:
        from ..knowledge_base.logic_layer.plot_constraints import PlotConstraintStore as PCS
        PlotConstraintStore = PCS
    return PlotConstraintStore(knowledge_base)

def get_content_validator(constraint_store, knowledge_base):
    """获取内容验证器实例"""
    global ContentValidator, PostGenerationProcessor
    if ContentValidator is None:
        from .content_validator import ContentValidator as CV, PostGenerationProcessor as PGP
        ContentValidator = CV
        PostGenerationProcessor = PGP
    return ContentValidator(constraint_store, knowledge_base), PostGenerationProcessor

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """角色状态追踪"""
    name: str
    is_alive: bool = True
    status: str = "正常"
    location: str = ""
    last_chapter: int = 0
    notes: List[str] = field(default_factory=list)


@dataclass
class PlotPoint:
    """剧情要点追踪"""
    chapter: int
    description: str
    importance: str = "normal"
    resolved: bool = False


@dataclass
class ContinuousWriteConfig:
    """无限续写配置"""
    words_per_chapter: int = 2500
    min_words: int = 2000
    max_words: int = 4000
    auto_save_to_kb: bool = True
    check_consistency: bool = True
    context_chapters: int = 3
    kb_search_top_k: int = 5
    kb_summary_top_k: int = 3
    pause_for_user_input: bool = True
    enable_trends_search: bool = False
    trends_platforms: List[str] = field(default_factory=lambda: ["zhihu", "douban"])
    trends_limit: int = 5


class ContinuousWriter(BaseAgent):
    """
    无限续写Agent
    
    核心功能：
    1. 根据用户提供的故事开头或灵感进行续写
    2. 每章基于前一章内容继续续写
    3. 每完成一章自动向量化存入知识库
    4. 通过知识库检索防止剧情重复和设定冲突
    5. 支持用户随时加入灵感和纠正剧情
    
    增强功能：
    6. 会话持久化 - 服务重启后自动恢复
    7. 模型切换连贯性 - 换模型时自动传递完整上下文
    8. 跨章节一致性 - 通过持久化状态确保剧情连贯
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
        """初始化无限续写Agent"""
        super().__init__(
            name="ContinuousWriter",
            prompt_file="continuous_writer.md",
            model_config=model_config,
            **kwargs
        )
        
        self.write_config = write_config or ContinuousWriteConfig()
        self.knowledge_base = knowledge_base
        
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
        
        # 当前使用的模型名称（用于追踪模型切换）
        self._current_model: str = ""
        
        # 剧情约束存储（在设置知识库时初始化）
        self._constraint_store = None
        
        # 内容验证器（后处理验证）
        self._content_validator = None
        self._post_processor = None
        
        # 验证配置
        self._enable_post_validation = True  # 是否启用后处理验证
        self._auto_fix_violations = True  # 是否自动修正违规
        self._max_regeneration_attempts = 2  # 最大重新生成次数
        
        # 高级检索配置
        self._use_advanced_search = True  # 使用增强的知识库搜索
        self._use_dynamic_weights = True  # 动态调整搜索权重
        self._use_reranking = True  # 启用结果重排序
        self._use_context_compression = True  # 启用上下文压缩
        
    def _get_default_prompt(self) -> str:
        """获取默认系统提示词"""
        return """# 无限续写Agent

你是一位专业的网络小说续写专家。

## 字数控制规则（最高优先级）

1. 严格控制在目标字数的正负15%范围内
2. 实时统计字数，确保不超标
3. 接近目标字数时立即收束剧情
4. 禁止以情节需要为由超出字数限制

## 核心原则

1. 剧情连贯性 - 遵循已有剧情，不让死亡角色复活
2. 用户灵感融入 - 自然地将灵感融入剧情
3. 用户纠正执行 - 立即根据纠正调整方向

## 禁止事项

1. 绝对禁止让死亡角色复活
2. 禁止无视用户纠正
3. 禁止创造矛盾设定
4. 禁止超出字数上限
"""
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行续写任务"""
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
        else:
            return {"success": False, "error": f"未知动作: {action}"}
    
    def _load_or_create_session(self, story_beginning: str = "") -> SessionState:
        """
        加载或创建持久化会话
        
        这是确保换模型后保持连贯性的关键
        """
        # 尝试从持久化存储加载
        state = self._session_store.load(self._session_id, self._project_id)
        
        if state:
            # 恢复已有会话
            logger.info(f"[{self.name}] 从持久化存储恢复会话，当前第 {state.current_chapter} 章")
            
            # 同步内存状态
            self._story_beginning = state.story_beginning
            self._current_chapter = state.current_chapter
            self._written_chapters = state.chapters.copy()
            self._dead_characters = state.dead_characters.copy()
            self._user_inspirations = state.inspirations.copy()
            self._corrections = state.corrections.copy()
            
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
        logger.info(f"[{self.name}] 创建新的持久化会话")
        return state
    
    def _sync_to_session(self):
        """
        将内存状态同步到持久化会话
        
        每次章节完成后调用，确保数据不丢失
        """
        if not self._session_state:
            return
        
        self._session_state.story_beginning = self._story_beginning
        self._session_state.current_chapter = self._current_chapter
        self._session_state.chapters = self._written_chapters.copy()
        self._session_state.dead_characters = self._dead_characters.copy()
        self._session_state.inspirations = self._user_inspirations.copy()
        self._session_state.corrections = self._corrections.copy()
        self._session_state.is_running = self._is_running
        self._session_state.last_model = self._current_model
        
        self._session_store.save(self._session_state)
    
    def _get_model_switch_context(self) -> str:
        """
        获取模型切换时的额外上下文
        
        当检测到模型切换时，提供更详细的上下文以确保连贯性
        """
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
            
            # 2. 从知识库获取关键约束（使用高级搜索）
            if self.knowledge_base and self._use_advanced_search:
                try:
                    # 获取所有活跃的严重约束
                    critical_constraints = self.knowledge_base.get_active_constraints()
                    if critical_constraints:
                        context_parts.append("\n[重要剧情约束]")
                        for c in critical_constraints[:10]:
                            context_parts.append(f"- {c.title}")
                    
                    # 获取死亡角色
                    dead_chars = self.knowledge_base.get_dead_characters()
                    if dead_chars:
                        context_parts.append("\n[已死亡角色]")
                        context_parts.append(", ".join(dead_chars))
                        
                except Exception as e:
                    logger.warning(f"[{self.name}] 获取知识库约束失败: {e}")
            
            # 3. 最后一章的完整内容（确保续写连贯）
            if self._written_chapters:
                last_ch = self._written_chapters[-1]
                last_content = last_ch.get('content', '')
                if last_content:
                    context_parts.append("\n[上一章完整内容]")
                    context_parts.append(f"第{last_ch.get('chapter_number')}章 {last_ch.get('title', '')}")
                    # 提供更多内容以确保连贯
                    context_parts.append(last_content[-2000:] if len(last_content) > 2000 else last_content)
            
            return "\n".join(context_parts)
        
        return ""
    
    async def _start_new_story(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """开始新故事或恢复已有故事"""
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
        
        # 尝试从持久化存储恢复（优先级最高）
        self._session_state = self._load_or_create_session(story_beginning)
        
        # 如果持久化会话有数据，优先使用
        if self._session_state.chapters:
            logger.info(f"[{self.name}] 使用持久化会话数据，已有 {len(self._session_state.chapters)} 章")
            is_recovery = True
            self._current_chapter = self._session_state.current_chapter
            self._story_beginning = self._session_state.story_beginning
            self._written_chapters = self._session_state.chapters.copy()
            self._dead_characters = self._session_state.dead_characters.copy()
            self._user_inspirations = self._session_state.inspirations.copy()
            self._corrections = self._session_state.corrections.copy()
        elif is_recovery:
            # 从前端传入的数据恢复（兼容旧逻辑）
            self._current_chapter = current_chapter
            if not self._story_beginning:
                self._story_beginning = story_beginning
            
            # 恢复章节数据 - 关键修复：确保后续章节有上下文
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
                logger.info(f"[{self.name}] 从前端恢复 {len(self._written_chapters)} 章节数据")
                
                # 同步到持久化存储
                self._session_state.chapters = self._written_chapters.copy()
                self._session_state.current_chapter = current_chapter
                self._session_store.save(self._session_state)
            else:
                # 如果没有完整章节数据，将 story_beginning 作为虚拟的第一章
                logger.warning(f"[{self.name}] 恢复会话但无完整章节数据，使用开头文本作为上下文")
            
            logger.info(f"[{self.name}] 恢复会话：当前章节 {current_chapter}")
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
        """继续续写下一章"""
        if not self._is_running and not self._written_chapters:
            return {"success": False, "error": "请先开始一个新故事"}
        
        self._is_running = True
        self._should_stop = False
        
        extra_inspiration = input_data.get("content", "")
        if extra_inspiration:
            self._add_inspiration({"content": extra_inspiration, "chapter": self._current_chapter + 1})
        
        return await self._write_chapter(input_data, context)
    
    async def _write_chapter(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """写一个章节"""
        self._current_chapter += 1
        chapter_number = self._current_chapter
        
        await self.notify_progress(f"正在创作第{chapter_number}章...", 0)
        
        # 检测模型切换，获取额外上下文
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
        
        await self.notify_progress("正在构建提示...", 40)
        
        prompt = self._build_chapter_prompt(
            chapter_number=chapter_number,
            story_beginning=self._story_beginning if chapter_number == 1 else "",
            recent_chapters=recent_chapters,
            kb_context=kb_context,
            kb_summaries=kb_summaries,
            trends_data=trends_data,
            inspirations=chapter_inspirations,
            corrections=chapter_corrections,
            model_switch_context=model_switch_context  # 新增：模型切换上下文
        )
        
        start_time = time.time()
        
        try:
            response = await self.call_llm([
                {"role": "user", "content": prompt}
            ])
            
            chapter_data = self._parse_chapter_response(response, chapter_number)
            chapter_data["model_used"] = self._current_model  # 记录使用的模型
            duration = time.time() - start_time
            
            logger.info(f"[{self.name}] 完成第{chapter_number}章: {chapter_data['word_count']}字, 模型: {self._current_model}")
            
            # 后处理验证（除提示词约束外的第二道防线）
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
                    logger.info(f"[{self.name}] 应用自动修正")
                
                if validation_result.has_critical:
                    # 存在严重违规，记录警告
                    chapter_data["validation_warnings"] = [
                        v.description for v in validation_result.violations
                    ]
                    logger.warning(f"[{self.name}] 检测到 {len(validation_result.violations)} 个违规")
            
            self._update_character_states(chapter_data)
            self._written_chapters.append(chapter_data)
            
            # 同步到持久化存储（关键：确保数据不丢失）
            self._sync_to_session()
            
            if self.write_config.auto_save_to_kb:
                await self._save_to_knowledge_base(chapter_data)
            
            await self.notify_progress(f"第{chapter_number}章创作完成", 100, {"chapter": chapter_data})
            
            result = {
                "success": True,
                "chapter": chapter_data,
                "waiting_for_input": self.write_config.pause_for_user_input,
                "message": "章节创作完成",
                "session_id": self._session_id,
                "persisted": True  # 标记已持久化
            }
            
            # 添加验证结果
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
        model_switch_context: str = ""  # 新增：模型切换时的额外上下文
    ) -> str:
        """构建章节续写提示词"""
        parts = []
        inspirations = inspirations or []
        corrections = corrections or []
        kb_summaries = kb_summaries or []
        trends_data = trends_data or []
        
        # 模型切换时，添加完整的故事上下文
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
            parts.append(f"[故事开头]\n{story_beginning}\n")
        
        if trends_data:
            parts.append("[热点]")
            for t in trends_data[:5]:
                if t.get("title"):
                    parts.append(f"- {t['title']}")
            parts.append("")
        
        if kb_context.get("relevant_content"):
            parts.append("[知识库信息]")
            for item in kb_context["relevant_content"]:
                parts.append(f"- {item}")
            parts.append("")
        
        # 已死亡角色（从知识库和内存中合并）
        all_dead = set(self._dead_characters)
        if kb_context.get("dead_characters"):
            all_dead.update(kb_context["dead_characters"])
        
        if all_dead:
            parts.append("[已死亡角色 - 绝对禁止复活！]")
            parts.append("以下角色已在之前的章节中死亡，绝对不能让他们以活人身份出现：")
            for char in sorted(all_dead):
                parts.append(f"  ❌ {char}")
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
        
        # 增强前情回顾：提供更详细的章节内容
        if recent_chapters:
            parts.append("[前情回顾]")
            for ch in recent_chapters:
                ch_num = ch.get('chapter_number')
                title = ch.get('title', '')
                summary = ch.get('summary', '')[:300]  # 增加摘要长度
                parts.append(f"第{ch_num}章 {title}:")
                parts.append(f"  {summary}...")
            parts.append("")
            
            # 最后一章的完整内容（确保续写连贯）
            if recent_chapters:
                last_chapter = recent_chapters[-1]
                last_content = last_chapter.get('content', '')
                if last_content:
                    # 提供最后1000字作为直接上下文
                    parts.append("[上一章结尾（请直接续写）]")
                    parts.append(last_content[-1000:])
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
        
        parts.append(f"[字数限制] {min_w}-{max_w}字，目标{target}字")
        parts.append(f"[任务] 请创作第{chapter_number}章")
        parts.append("[注意] 请确保与前文剧情连贯，不要重复已有内容，不要让死亡角色复活")
        
        return "\n".join(parts)
    
    def _parse_chapter_response(self, response: str, chapter_number: int) -> Dict[str, Any]:
        """解析LLM响应"""
        title_match = re.search(r'#\s*第\d+章\s*(.+?)(?:\n|$)', response)
        title = title_match.group(1).strip() if title_match else f"第{chapter_number}章"
        
        content = response
        chapter_info = {}
        
        info_match = re.search(r'---\n.+?(.*?)(?:$|\n---)', response, re.DOTALL)
        if info_match:
            content = response[:info_match.start()].strip()
        
        if title_match:
            content = content[title_match.end():].strip()
        
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
    
    def _smart_truncate(self, content: str, max_words: int) -> str:
        """智能截断"""
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
        
        return '\n\n'.join(result).strip() or content[:max_words * 2]
    
    def _update_character_states(self, chapter_data: Dict[str, Any]) -> None:
        """更新角色状态"""
        pass
    
    async def _retrieve_from_knowledge_base(self, chapter_number: int) -> Dict[str, Any]:
        """
        从知识库检索（增强版）
        
        使用 SeekDB 优化的高级搜索功能：
        - 动态权重调整
        - 智能重排序
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
            # 构建查询
            recent = ""
            if self._written_chapters:
                recent = self._written_chapters[-1].get("content", "")[:500]
            elif self._story_beginning:
                recent = self._story_beginning[:500]
            
            if recent and self._use_advanced_search:
                # 使用高级搜索（参考 SeekDB 优化）
                try:
                    # 获取写作上下文（一站式获取所有相关信息）
                    writing_context = self.knowledge_base.get_context_for_writing(
                        query=recent,
                        current_chapter=chapter_number,
                        max_tokens=2000,
                        include_constraints=True
                    )
                    result["writing_context"] = writing_context
                    
                    # 提取相关内容
                    for item in writing_context.get("relevant_content", []):
                        content = item.get("content", "")[:200]
                        if content:
                            result["relevant_content"].append(content)
                    
                    # 提取约束
                    for constraint in writing_context.get("constraints", []):
                        result["plot_constraints"].append({
                            "type": constraint.get("type"),
                            "description": constraint.get("description"),
                            "entities": constraint.get("entities", [])
                        })
                    
                    # 死亡角色
                    result["dead_characters"] = writing_context.get("dead_characters", [])
                    
                    logger.debug(f"[{self.name}] 高级搜索完成，token估计: {writing_context.get('total_tokens_estimate', 0)}")
                    
                except AttributeError:
                    # 知识库不支持高级搜索，使用基础搜索
                    logger.debug(f"[{self.name}] 知识库不支持高级搜索，回退到基础模式")
                    self._use_advanced_search = False
            
            # 基础搜索（作为后备或高级搜索不可用时）
            if not self._use_advanced_search and recent:
                resp = self.knowledge_base.search(query=recent, top_k=self.write_config.kb_search_top_k)
                result["relevant_content"] = [r.document[:200] for r in resp.results if r.metadata.get("type") != "plot_constraints"]
            
            # 检索剧情约束（关键：防止角色复活等问题）
            if self._constraint_store:
                constraints = self._constraint_store.search_constraints(
                    query=recent[:200] if recent else "",
                    top_k=5
                )
                # 合并约束
                for c in constraints:
                    if c not in result["plot_constraints"]:
                        result["plot_constraints"].append(c)
                
                # 获取所有死亡角色列表
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in result["dead_characters"]:
                        result["dead_characters"].append(char)
                
                # 同步到内存状态
                for char in result["dead_characters"]:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                        logger.info(f"[{self.name}] 从知识库同步死亡角色: {char}")
                
        except Exception as e:
            logger.warning(f"[{self.name}] 知识库检索失败: {e}")
        
        return result
    
    async def _retrieve_summaries_from_knowledge_base(self) -> List[Dict[str, Any]]:
        """从知识库检索总结"""
        if not self.knowledge_base:
            return []
        
        try:
            resp = self.knowledge_base.search(
                query="剧情总结",
                top_k=self.write_config.kb_summary_top_k
            )
            return [{"chapter_range": "", "content": r.document[:500]} for r in resp.results]
        except:
            pass
        
        return []
    
    async def _search_trends(self) -> List[Dict[str, Any]]:
        """搜索热点"""
        trends = []
        try:
            from ..utils.mcp_manager import mcp_manager
            await mcp_manager.initialize()
            
            for platform in self.write_config.trends_platforms:
                try:
                    tool = self._get_trend_tool_name(platform)
                    result = await mcp_manager.call_tool("trends-hub", tool, {"limit": self.write_config.trends_limit})
                    if result and hasattr(result, 'content'):
                        for item in result.content:
                            if hasattr(item, 'text'):
                                try:
                                    data = json.loads(item.text)
                                    if isinstance(data, list):
                                        for t in data[:self.write_config.trends_limit]:
                                            if isinstance(t, dict):
                                                trends.append({"title": t.get("title", ""), "platform": platform})
                                except:
                                    pass
                except:
                    continue
            self._cached_trends = trends
        except Exception as e:
            logger.error(f"[{self.name}] 热点搜索失败: {e}")
        return trends
    
    def _get_trend_tool_name(self, platform: str) -> str:
        """获取热点工具名"""
        m = {
            "douban": "get-douban-rank",
            "zhihu": "get-zhihu-trending",
            "bilibili": "get-bilibili-rank",
        }
        return m.get(platform, f"get-{platform}-trending")
    
    async def _save_to_knowledge_base(self, chapter_data: Dict[str, Any]) -> None:
        """存入知识库并自动提取剧情约束"""
        if not self.knowledge_base:
            return
        
        try:
            # 存储章节内容
            self.knowledge_base.add_chapter(
                chapter_id=f"chapter_{chapter_data['chapter_number']}",
                title=chapter_data["title"],
                content=chapter_data["content"],
                chapter_number=chapter_data["chapter_number"],
                metadata={
                    "word_count": chapter_data["word_count"],
                    "model_used": self._current_model
                }
            )
            
            # 自动提取并存储剧情约束（关键：确保角色死亡等信息被记录）
            if self._constraint_store:
                constraints = self._constraint_store.extract_and_store(
                    content=chapter_data["content"],
                    chapter_id=f"chapter_{chapter_data['chapter_number']}",
                    chapter_number=chapter_data["chapter_number"],
                    title=chapter_data["title"]
                )
                
                # 更新内存中的死亡角色列表
                for constraint in constraints:
                    if constraint.constraint_type == "character_death":
                        for entity in constraint.entities:
                            if entity not in self._dead_characters:
                                self._dead_characters.append(entity)
                                logger.info(f"[{self.name}] 检测到角色死亡: {entity}")
                
                if constraints:
                    logger.info(f"[{self.name}] 提取了 {len(constraints)} 个剧情约束")
            
        except Exception as e:
            logger.error(f"[{self.name}] 存储失败: {e}")
    
    def _add_inspiration(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加灵感"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "灵感内容不能为空"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._user_inspirations.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 同步到持久化存储
        self._sync_to_session()
        
        return {"success": True, "message": f"灵感已添加"}
    
    def _add_correction(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加纠正"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "纠正内容不能为空"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._corrections.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 同步到持久化存储
        self._sync_to_session()
        
        return {"success": True, "message": f"纠正已记录"}
    
    def _add_dead_character(self, character_name: str) -> Dict[str, Any]:
        """添加死亡角色"""
        if character_name and character_name not in self._dead_characters:
            self._dead_characters.append(character_name)
            self._sync_to_session()
            logger.info(f"[{self.name}] 记录角色死亡: {character_name}")
        return {"success": True, "dead_characters": self._dead_characters}
    
    def _stop_writing(self) -> Dict[str, Any]:
        """停止续写"""
        self._is_running = False
        self._should_stop = True
        
        # 同步到持久化存储
        self._sync_to_session()
        
        return {
            "success": True,
            "message": "续写已停止",
            "total_chapters": len(self._written_chapters),
            "total_words": sum(ch.get("word_count", 0) for ch in self._written_chapters),
            "session_id": self._session_id,
            "persisted": True
        }
    
    def _get_status(self) -> Dict[str, Any]:
        """获取状态"""
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
        """启用热点"""
        self._trends_enabled = True
        self._trends_query = input_data.get("query", "")
        if input_data.get("platforms"):
            self.write_config.trends_platforms = input_data.get("platforms")
        return {"success": True, "message": "热点融合已启用"}
    
    def _disable_trends(self) -> Dict[str, Any]:
        """禁用热点"""
        self._trends_enabled = False
        self._trends_query = ""
        self._cached_trends = []
        return {"success": True, "message": "热点融合已禁用"}
    
    def _get_chapter(self, chapter_number: int) -> Dict[str, Any]:
        """获取章节"""
        for ch in self._written_chapters:
            if ch.get("chapter_number") == chapter_number:
                return {"success": True, "chapter": ch}
        return {"success": False, "error": f"章节{chapter_number}不存在"}
    
    def _get_recent_chapters(self) -> List[Dict[str, Any]]:
        """获取最近章节"""
        return self._written_chapters[-self.write_config.context_chapters:]
    
    def get_all_chapters(self) -> List[Dict[str, Any]]:
        """获取所有章节"""
        return self._written_chapters.copy()
    
    def set_knowledge_base(self, kb) -> None:
        """设置知识库"""
        self.knowledge_base = kb
        
        # 初始化剧情约束存储
        if kb:
            try:
                self._constraint_store = get_plot_constraint_store(kb)
                logger.info(f"[{self.name}] 知识库和剧情约束存储已配置")
                
                # 从知识库加载已有的死亡角色
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                
                if self._dead_characters:
                    logger.info(f"[{self.name}] 从知识库加载了 {len(self._dead_characters)} 个死亡角色")
                
                # 初始化内容验证器（后处理验证）
                self._content_validator, _ = get_content_validator(self._constraint_store, kb)
                self._content_validator.load_constraints()
                logger.info(f"[{self.name}] 内容验证器已配置")
                
            except Exception as e:
                logger.warning(f"[{self.name}] 剧情约束存储初始化失败: {e}")
                self._constraint_store = None
                self._content_validator = None
        else:
            self._constraint_store = None
            self._content_validator = None
            logger.info(f"[{self.name}] 知识库已配置")
    
    def set_session_id(self, session_id: str, project_id: str = "") -> None:
        """设置会话ID（用于持久化）"""
        self._session_id = session_id
        self._project_id = project_id
        logger.info(f"[{self.name}] 会话ID设置为: {session_id}")
    
    def set_model(self, model: str) -> None:
        """设置当前模型（用于追踪模型切换）"""
        if model != self._current_model:
            logger.info(f"[{self.name}] 模型切换: {self._current_model} -> {model}")
        self._current_model = model
    
    def get_session_context(self) -> Dict[str, Any]:
        """
        获取会话上下文（供外部使用）
        
        返回确保连贯性所需的所有信息
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
        配置高级搜索选项
        
        Args:
            use_advanced: 是否使用高级搜索
            use_dynamic_weights: 是否使用动态权重
            use_reranking: 是否使用重排序
            use_context_compression: 是否使用上下文压缩
        """
        self._use_advanced_search = use_advanced
        self._use_dynamic_weights = use_dynamic_weights
        self._use_reranking = use_reranking
        self._use_context_compression = use_context_compression
        logger.info(
            f"[{self.name}] 高级搜索配置更新: "
            f"advanced={use_advanced}, "
            f"dynamic_weights={use_dynamic_weights}, "
            f"reranking={use_reranking}, "
            f"compression={use_context_compression}"
        )
    
    async def recover_from_model_switch(self) -> Dict[str, Any]:
        """
        从模型切换中恢复
        
        当检测到模型切换时，主动加载完整上下文以确保连贯性
        
        Returns:
            恢复结果，包含加载的上下文信息
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
            result["message"] = "无会话状态"
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
            
            result["recent_chapters_count"] = len(self._written_chapters)
            
            # 2. 从知识库同步最新约束
            if self.knowledge_base:
                try:
                    # 获取活跃约束
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
            result["message"] = f"成功从模型切换中恢复，加载了 {result['recent_chapters_count']} 章内容"
            
            # 更新会话中的模型信息
            self._session_state.last_model = self._current_model
            self._session_store.save(self._session_state)
            
        except Exception as e:
            logger.error(f"[{self.name}] 模型切换恢复失败: {e}")
            result["success"] = False
            result["message"] = f"恢复失败: {e}"
        
        return result
