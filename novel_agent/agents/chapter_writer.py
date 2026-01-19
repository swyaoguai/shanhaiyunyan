"""
章节撰写Agent
负责根据大纲生成具体的章节内容
支持并行生成(Sectioning模式)

增强功能：
- 知识库集成：自动检索相关上下文
- 剧情约束：防止角色复活等错误
- 模型切换连贯：支持换模型后保持一致性
"""

from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
from .knowledge_mixin import KnowledgeBaseMixin
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
        return """你是一位才华横溢的网络小说作家。你擅长写出引人入胜、感染力强的小说章节。

## 你的写作风格
1. 文笔流畅，节奏明快
2. 对话生动，符合角色性格
3. 描写细腻，画面感强
4. 情节紧凑，扣人心弦
5. 善于设置悬念和爽点

## 网文写作要点
1. 开篇吸引：每章开头要有吸引力
2. 节奏把控：张弛有度，高潮迭起
3. 角色塑造：通过言行展现性格
4. 场景描写：适度且有代入感
5. 章末钩子：留下悬念吸引继续阅读

## 字数要求
每章 2000-4000 字，根据内容需要灵活调整

## 输出格式
直接输出章节正文内容，不需要额外格式包装。"""
    
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
        previous_summary = context.get("previous_summary", "") if context else ""
        style = context.get("style", "") if context else ""
        
        # 从知识库获取写作上下文
        kb_context = await self._get_kb_context(chapter_outline, chapter_number)
        
        # 构建约束提示词
        constraint_prompt = self.build_constraint_prompt()
        
        prompt = f"""请撰写以下章节：

## 章节信息
- 章节号：第{chapter_number}章
- 标题：{chapter_title}
- 目标字数：约{word_count}字

## 章节大纲
{chapter_outline}

## 世界观背景
{world if world else "通用现代/玄幻背景"}

## 相关角色
{characters if characters else "根据大纲自行把握"}

## 前情提要
{previous_summary if previous_summary else "这是开篇章节"}

## 写作风格要求
{style if style else "网文爽文风格，节奏明快"}

{constraint_prompt}

{self._format_kb_context(kb_context)}

请直接开始撰写章节正文："""

        messages = [{"role": "user", "content": prompt}]
        
        response = await self.call_llm(
            messages,
            temperature=AGENT_TEMPERATURE.CREATIVE_HIGH,  # 略高温度增加创意
            max_tokens=AGENT_TOKEN_CONFIG.CHAPTER_WRITER_MAX_TOKENS  # 确保足够字数
        )
        
        # 保存到知识库
        if self.has_knowledge_base:
            await self.save_chapter_to_knowledge_base(
                chapter_id=f"chapter_{chapter_number}",
                title=chapter_title,
                content=response,
                chapter_number=chapter_number
            )
        
        return {
            "success": True,
            "agent": self.name,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "content": response,
            "word_count": len(response),
            "dead_characters": self.get_dead_characters()
        }
    
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
        """简单摘要章节内容"""
        # 简单实现：取前N个字符
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."


# 模块职责说明：负责根据大纲生成具体的章节内容，支持批量生成和摘要功能。
