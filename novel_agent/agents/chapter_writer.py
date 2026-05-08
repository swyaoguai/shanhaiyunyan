"""
章节撰写Agent
负责根据大纲生成具体的章节内容
支持并行生成(Sectioning模式)

增强功能：
- 知识库集成：自动检索相关上下文
- 剧情约束：防止角色复活等错误
- 模型切换连贯：支持换模型后保持一致性
"""

import os
import re
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent, AgentCapability
from .knowledge_mixin import KnowledgeBaseMixin
from ..content_sanitizer import strip_internal_author_markers
from ..constants import WRITING_CONFIG, AGENT_TEMPERATURE, AGENT_TOKEN_CONFIG

import logging
logger = logging.getLogger(__name__)


class ChapterWriterAgent(BaseAgent, KnowledgeBaseMixin):
    """
    章节撰写Agent
    
    增强功能：
    - 知识库混入：自动获取写作上下文
    - 约束检测：防止剧情矛盾
    - 死亡角色追踪：确保不复活已死角色
    """
    
    def __init__(self, knowledge_base=None):
        super().__init__(
            name="ChapterWriter",
            prompt_file="chapter_writer.md"
        )
        
        # 初始化知识库混入
        self.init_knowledge_mixin(knowledge_base)
    
    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import CHAPTER_WRITER_PROMPT
        return CHAPTER_WRITER_PROMPT

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["write_chapter", "draft_chapter"],
            accept_task_types=["write_chapter"],
            required_inputs=["chapter_number", "chapter_title", "chapter_outline"],
            produced_outputs=["content", "word_count", "dead_characters"],
            priority=95,
            max_concurrency=1,
            metadata={
                "stage": "chapter_writing",
                "supports_kb": True,
            },
        )
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        撰写单个章节
        
        Args:
            input_data: 包含 chapter_outline(章节大纲), chapter_title(章节标题)
            context: 上下文(世界观、角色档案、前文摘要等)
            
        Returns:
            章节内容
        """
        chapter_outline = input_data.get("chapter_outline", "")
        chapter_title = input_data.get("chapter_title", "")
        chapter_number = input_data.get("chapter_number", 1)
        word_count = input_data.get("word_count", WRITING_CONFIG.CHAPTER_DEFAULT_WORDS)

        # 从上下文提取相关信息
        world = context.get("world", {}) if context else {}
        characters = context.get("characters", []) if context else []
        eventlines = context.get("eventlines", "") if context else ""
        previous_summary = context.get("previous_summary", "") if context else ""
        style = context.get("style", "") if context else ""
        aux_memory = context.get("aux_memory", {}) if context else {}
        plot_thread = context.get("plot_thread", {}) if context else {}
        chapter_planning = str(context.get("chapter_planning", "") or "").strip() if context else ""
        trends_data = context.get("trends_data", []) if context else []
        discussion_context = str(
            input_data.get("discussion_context")
            or input_data.get("recent_discussion")
            or ((context or {}).get("discussion_context") if isinstance(context, dict) else "")
            or ((context or {}).get("recent_discussion") if isinstance(context, dict) else "")
            or ""
        ).strip()
        
        # 进度：开始
        try:
            await self.notify_progress(f"正在创作第{chapter_number}章...", 0)
        except Exception:
            pass

        # 从知识库获取写作上下文
        kb_context = await self._get_kb_context(chapter_outline, chapter_number)
        semantic_recall_context: Dict[str, Any] = {}
        if self._semantic_recall_enabled():
            recall_query = self.build_semantic_recall_query(
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                chapter_planning=chapter_planning,
                characters=characters,
                plot_thread=plot_thread,
                eventlines=eventlines,
                world=world,
                discussion_context=discussion_context,
            )
            semantic_recall_context = await self._get_semantic_recall_context(
                query=recall_query,
                chapter_number=chapter_number,
            )

        # 构建约束提示词
        constraint_prompt = self.build_constraint_prompt()

        aux_memory_prompt = aux_memory.get("prompt_preview", "") if isinstance(aux_memory, dict) else ""
        if not aux_memory_prompt:
            aux_memory_prompt = "未启用辅助记忆或无匹配"

        plot_thread_prompt = ""
        if isinstance(plot_thread, dict):
            plot_thread_prompt = str(plot_thread.get("writer_guidance", "") or "").strip()
            active_thread_id = str(plot_thread.get("active_thread_id", "") or "").strip()
            if not plot_thread_prompt and active_thread_id and active_thread_id != "main":
                plot_thread_prompt = f"当前章节处于支线[{active_thread_id}]，请在章末制造回主线钩子。"
        if not plot_thread_prompt:
            plot_thread_prompt = "当前章节默认推进主线。"

        # 进度：整合上下文与约束
        try:
            await self.notify_progress("正在整合上下文与写作约束...", 20)
        except Exception:
            pass

        trends_prompt = self._format_trends_context(trends_data)
        
        prompt = self._render_custom_task_prompt(
            "write_chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            chapter_outline=chapter_outline,
            context={
                "world": world,
                "characters": characters,
                "eventlines": eventlines,
                "style": style,
                "discussion_context": discussion_context,
                "aux_memory": aux_memory,
                "plot_thread": plot_thread,
                "chapter_planning": chapter_planning,
            },
            previous_summary=previous_summary,
            word_count=word_count,
            world=world,
            characters=characters,
            eventlines=eventlines,
            style=style,
            discussion_context=discussion_context,
            chapter_planning=chapter_planning,
            plot_thread_state=plot_thread_prompt,
            semantic_recall=self._format_semantic_recall_context(semantic_recall_context),
        )
        semantic_recall_block = self._format_semantic_recall_context(semantic_recall_context)
        if prompt and semantic_recall_block:
            prompt = f"{prompt}\n\n{semantic_recall_block}"
        if not prompt:
            prompt = f"""请撰写以下章节：

## 章节信息
- 章节号：第{chapter_number}章
- 标题：{chapter_title}
- 目标字数：约{word_count}字

## 章节大纲
{chapter_outline}

## 章纲/细纲约束
{chapter_planning if chapter_planning else "无"}

## 聊天讨论上下文（最高优先级）
{discussion_context if discussion_context else "无"}

## 世界观背景
{world if world else "通用现代/玄幻背景"}

## 相关角色
{characters if characters else "根据大纲自行把握"}

## 事件线参考
{eventlines if eventlines else "暂无事件线"}

## 前情提要
{previous_summary if previous_summary else "这是开篇章节"}

## 写作风格要求
{style if style else "网文爽文风格，节奏明快"}

## 剧情线程状态（高优先级）
{plot_thread_prompt}
如果本章完成支线目标，请用自然语言在剧情中制造回归主线的钩子，不要输出 HTML 注释或机器标记。

{trends_prompt}

## 辅助记忆约束（低优先级）
{aux_memory_prompt}

{constraint_prompt}

{semantic_recall_block}

{self._format_kb_context(kb_context)}

请直接开始撰写章节正文："""

        messages = [{"role": "user", "content": prompt}]

        # 进度：生成正文
        try:
            await self.notify_progress("正在生成章节正文...", 50)
        except Exception:
            pass
        
        response = await self.call_llm(
            messages,
            temperature=AGENT_TEMPERATURE.CREATIVE_HIGH,  # 略高温度增加创意
            max_tokens=AGENT_TOKEN_CONFIG.CHAPTER_WRITER_MAX_TOKENS  # 确保足够字数
        )
        response = strip_internal_author_markers(response)
        
        # 保存到知识库
        if self.has_knowledge_base:
            await self.save_chapter_to_knowledge_base(
                chapter_id=f"chapter_{chapter_number}",
                title=chapter_title,
                content=response,
                chapter_number=chapter_number
            )
        # 统计字数（字符与非空白字符）
        total_chars = len(response)
        nonspace_chars = sum(1 for c in response if not c.isspace())

        # 进度：完成
        try:
            await self.notify_progress(
                f"第{chapter_number}章创作完成",
                100,
                {"chapter": {"number": chapter_number, "title": chapter_title, "chars": total_chars, "nonspace": nonspace_chars}}
            )
        except Exception:
            pass

        return {
            "success": True,
            "agent": self.name,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "content": response,
            "word_count": nonspace_chars,  # 问题12修复：使用去空白字符数作为 word_count
            "stats": {"chars": total_chars, "nonspace_chars": nonspace_chars},
            "dead_characters": self.get_dead_characters()
        }

    @staticmethod
    def _semantic_recall_enabled() -> bool:
        value = os.getenv("ENABLE_CHAPTER_SEMANTIC_RECALL", "false").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def build_semantic_recall_query(
        self,
        *,
        chapter_number: int,
        chapter_title: str,
        chapter_outline: Any,
        chapter_planning: Any = "",
        characters: Any = None,
        plot_thread: Any = None,
        eventlines: Any = None,
        world: Any = None,
        discussion_context: str = "",
    ) -> str:
        """构造章节写作前的语义召回查询。"""
        sections: List[str] = [f"当前章节：第{chapter_number}章 {chapter_title}".strip()]

        def append(label: str, value: Any, limit: int = 700) -> None:
            text = self._semantic_recall_text(value)
            if text:
                sections.append(f"{label}：{text[:limit]}")

        append("当前章节目标和章纲", chapter_outline, 1000)
        append("章纲/细纲约束", chapter_planning, 800)
        append("出场角色", characters, 700)
        append("剧情线程/伏笔冲突", plot_thread, 900)
        append("事件线", eventlines, 900)
        append("世界规则", world, 900)
        append("用户明确要求", discussion_context, 700)

        query = "\n".join(part for part in sections if str(part).strip())
        return query[:3000]

    def _semantic_recall_text(self, value: Any) -> str:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, str):
            return re.sub(r"\s+", " ", value).strip()
        if isinstance(value, dict):
            preferred_keys = [
                "title", "summary", "goal", "objective", "conflict", "foreshadowing",
                "writer_guidance", "active_thread_id", "rules", "events", "name",
            ]
            parts: List[str] = []
            for key in preferred_keys:
                if key in value:
                    text = self._semantic_recall_text(value.get(key))
                    if text:
                        parts.append(f"{key}:{text}")
            if not parts:
                for key, item in list(value.items())[:12]:
                    text = self._semantic_recall_text(item)
                    if text:
                        parts.append(f"{key}:{text}")
            return "；".join(parts)
        if isinstance(value, list):
            parts = [self._semantic_recall_text(item) for item in value[:12]]
            return "；".join(part for part in parts if part)
        return re.sub(r"\s+", " ", str(value)).strip()

    async def _get_semantic_recall_context(self, query: str, chapter_number: int) -> Dict[str, Any]:
        if not query or not self.has_knowledge_base:
            return {"query": query, "results": []}
        try:
            search_resp = self._knowledge_base.search(
                query=query,
                top_k=8,
                search_type="hybrid",
                min_score=0.3,
            )
            results: List[Dict[str, Any]] = []
            for item in getattr(search_resp, "results", []) or []:
                metadata = getattr(item, "metadata", None) or {}
                if self._is_current_chapter_recall(metadata, chapter_number):
                    continue
                document = getattr(item, "document", "") or str(item)
                score = float(getattr(item, "score", 0.0) or 0.0)
                if not document.strip():
                    continue
                results.append({
                    "content": document[:500],
                    "score": score,
                    "source": getattr(item, "source", "knowledge_base"),
                    "chapter_id": metadata.get("chapter_id"),
                    "chapter_number": metadata.get("chapter_number"),
                })
                if len(results) >= 5:
                    break
            return {"query": query, "results": results}
        except Exception as e:
            logger.warning(f"[{self.name}] 语义召回失败，继续使用当前上下文: {e}")
            return {"query": query, "results": [], "error": str(e)}

    @staticmethod
    def _is_current_chapter_recall(metadata: Dict[str, Any], chapter_number: int) -> bool:
        if not isinstance(metadata, dict):
            return False
        chapter_id = str(metadata.get("chapter_id") or "").strip().lower()
        number = metadata.get("chapter_number")
        if str(number or "").strip() == str(chapter_number):
            return True
        return chapter_id in {f"chapter_{chapter_number}", str(chapter_number)}

    def _format_semantic_recall_context(self, recall_context: Dict[str, Any]) -> str:
        results = recall_context.get("results", []) if isinstance(recall_context, dict) else []
        if not results:
            return ""
        parts = ['<context_block source="semantic_recall">']
        total_chars = 0
        for idx, item in enumerate(results[:5], 1):
            content = str(item.get("content", "") if isinstance(item, dict) else item).strip()
            if not content:
                continue
            score = item.get("score", 0) if isinstance(item, dict) else 0
            source = item.get("source", "knowledge_base") if isinstance(item, dict) else "knowledge_base"
            chapter = item.get("chapter_id") or item.get("chapter_number") if isinstance(item, dict) else ""
            header = f"片段 {idx} score={float(score or 0):.2f} source={source}"
            if chapter:
                header += f" chapter={chapter}"
            snippet = content[:450]
            total_chars += len(snippet)
            if total_chars > 2200:
                break
            parts.append(header)
            parts.append(snippet)
        parts.append("</context_block>")
        return "\n".join(parts)

    async def _get_kb_context(self, query: str, chapter_number: int) -> Dict[str, Any]:
        """从知识库获取上下文"""
        if not self.has_knowledge_base:
            return {}
        
        try:
            return await self.get_writing_context(
                query=query[:500],
                current_chapter=chapter_number,
                max_tokens=1500
            )
        except Exception as e:
            logger.warning(f"[{self.name}] 获取知识库上下文失败: {e}")
            return {}
    
    def _format_kb_context(self, kb_context: Dict[str, Any]) -> str:
        """格式化知识库上下文"""
        if not kb_context:
            return ""
        
        parts = []
        
        # 相关内容
        relevant = kb_context.get("relevant_content", [])
        if relevant:
            parts.append("## 知识库相关内容")
            for item in relevant[:3]:
                content = item.get("content", "") if isinstance(item, dict) else str(item)
                parts.append(f"- {content[:200]}...")
            parts.append("")
        
        return "\n".join(parts)

    def _select_balanced_trend_candidates(
        self,
        trends_data: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """按平台轮询挑选热点，避免单个平台占满候选位。"""
        if not trends_data or limit <= 0:
            return []

        platform_buckets: Dict[str, List[Dict[str, Any]]] = {}
        platform_order: List[str] = []

        for trend in trends_data:
            platform = str(trend.get("platform", "")).strip().lower()
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

    def _format_trends_context(self, trends_data: List[Dict[str, Any]]) -> str:
        if not trends_data:
            return ""

        parts: List[str] = []
        parts.append("## 热点融合要求")
        parts.append("请从热点候选中选择 1-2 条与当前章节最契合的内容进行改编融入。")
        parts.append("不要照抄热点标题，不要写成新闻播报，要转化为角色动机/冲突/事件触发。")
        parts.append("")
        parts.append("## 热点候选")

        for trend in self._select_balanced_trend_candidates(trends_data, limit=5):
            title = str(trend.get("title", "")).strip()
            if not title:
                continue
            platform = str(trend.get("platform", "")).strip()
            hot = str(trend.get("hot", "")).strip()
            source = f"[{platform}]" if platform else ""
            heat = f"（热度:{hot}）" if hot else ""
            parts.append(f"- {source}{title}{heat}")

        parts.append("")
        return "\n".join(parts)
    
    async def write_chapters_batch(
        self,
        chapters: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        批量撰写多个章节(Sectioning并行模式)
        
        注意：这里的并行需要谨慎，因为后续章节可能依赖前面内容
        建议分批处理，每批3-5章
        
        Args:
            chapters: 章节列表
            context: 共享上下文
            
        Returns:
            章节内容列表
        """
        import asyncio
        
        results = []
        # 为保持连贯性，按顺序处理，但可以预先规划
        for chapter in chapters:
            result = await self.execute(chapter, context)
            results.append(result)
            
            # 更新上下文：添加前一章的摘要
            if context:
                context["previous_summary"] = self._summarize_chapter(result["content"])
        
        return results
    
    def _summarize_chapter(self, content: str, max_length: int = WRITING_CONFIG.CHAPTER_SUMMARY_MAX_LENGTH) -> str:
        """问题13修复：按段落提取关键内容，而非纯截断。"""
        if not content or not content.strip():
            return ""
        clean = re.sub(r"\s+", "", content)
        if len(clean) <= max_length:
            return content.strip()
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        summary_parts: List[str] = []
        current_len = 0
        for para in paragraphs:
            para_clean_len = len(re.sub(r"\s+", "", para))
            if current_len + para_clean_len > max_length:
                remaining = max_length - current_len
                if remaining > 20:
                    summary_parts.append(para[:remaining])
                break
            summary_parts.append(para)
            current_len += para_clean_len
        return "\n".join(summary_parts) if summary_parts else clean[:max_length]


# 模块职责说明：负责根据大纲生成具体的章节内容，支持批量生成和摘要功能。
