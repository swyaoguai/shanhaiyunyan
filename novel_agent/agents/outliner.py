"""
大纲规划Agent
负责规划小说的整体结构和章节大纲
实现Prompt Chaining模式
"""

from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
from ..constants import WRITING_CONFIG


class OutlinerAgent(BaseAgent):
    """大纲规划Agent"""
    
    def __init__(self):
        super().__init__(
            name="Outliner",
            prompt_file="outliner.md"
        )
    
    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import OUTLINER_PROMPT
        return OUTLINER_PROMPT
    
    async def execute(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        规划小说大纲
        
        Args:
            input_data: 包含 world(世界观), protagonist(主角), plot_idea(剧情想法)
            context: 上下文信息(包含世界观等)
            
        Returns:
            大纲结构字典
        """
        world = input_data.get("world", context.get("world", {}) if context else {})
        protagonist = input_data.get("protagonist", "")
        plot_idea = input_data.get("plot_idea", "")
        volume_count = input_data.get("volume_count", WRITING_CONFIG.DEFAULT_VOLUME_COUNT)
        chapters_per_volume = input_data.get("chapters_per_volume", WRITING_CONFIG.DEFAULT_CHAPTERS_PER_VOLUME)
        
        # Prompt Chaining: 先生成总纲，再细化
        
        # Step 1: 生成总纲
        try:
            await self.notify_progress("正在读取世界观与需求，规划总体目标与规模...", 20)
        except Exception:
            pass
        total_prompt = f"""基于以下信息，规划小说的总体大纲：

## 世界观
{world}

## 主角设定
{protagonist if protagonist else "请自行设计一个有特色的主角"}

## 剧情构思
{plot_idea if plot_idea else "请自由发挥，创作一个精彩的故事"}

## 要求
- 分为 {volume_count} 卷
- 每卷约 {chapters_per_volume} 章
- 设计清晰的主线冲突和角色成长线

请先输出总纲（JSON格式），包含标题、主题、主要冲突、结局走向："""

        messages = [{"role": "user", "content": total_prompt}]
        total_response = await self.call_llm(messages)
        
        # Step 2: 细化各卷大纲
        try:
            await self.notify_progress("正在完成分卷设计（核心冲突与成长）...", 50)
        except Exception:
            pass
        detail_prompt = f"""基于上面的总纲，请详细规划每一卷的内容：

{total_response}

请为每卷输出：
1. 卷标题
2. 本卷核心事件
3. 各章节的标题和简要内容（每章2-3句话描述）

输出完整的JSON格式大纲："""

        messages.append({"role": "assistant", "content": total_response})
        messages.append({"role": "user", "content": detail_prompt})
        
        detail_response = await self.call_llm(messages)
        
        # 解析结果
        try:
            import json
            if "```json" in detail_response:
                json_str = detail_response.split("```json")[1].split("```")[0]
            elif "```" in detail_response:
                json_str = detail_response.split("```")[1].split("```")[0]
            else:
                json_str = detail_response
            
            outline_data = json.loads(json_str.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            outline_data = {"raw_content": detail_response}

        try:
            await self.notify_progress("正在补齐章节详情雏形...", 90)
            await self.notify_progress("大纲规划完成", 100)
        except Exception:
            pass
        
        return {
            "success": True,
            "agent": self.name,
            "outline": outline_data,
            "total_outline": total_response,
            "raw_response": detail_response
        }
    
    async def generate_chapter_outline(
        self,
        volume_outline: Dict[str, Any],
        chapter_index: int,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成单章详细大纲
        
        Args:
            volume_outline: 所属卷的大纲
            chapter_index: 章节索引
            context: 上下文
            
        Returns:
            章节详细大纲
        """
        prompt = f"""请为以下章节生成详细写作大纲：

## 所属卷信息
{volume_outline}

## 章节索引
第 {chapter_index + 1} 章

## 要求
详细列出：
1. 场景描写要点
2. 对话要点
3. 情节推进
4. 情感氛围
5. 伏笔/回收

输出JSON格式："""

        messages = [{"role": "user", "content": prompt}]
        response = await self.call_llm(messages)
        
        try:
            import json
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            else:
                json_str = response
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            return {"raw_content": response}


# 模块职责说明：负责规划小说的整体结构和章节大纲，实现Prompt Chaining模式。
