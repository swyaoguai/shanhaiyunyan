"""
润色优化Agent
负责对章节内容进行润色和优化
"""

from typing import Dict, Any, Optional
from .base_agent import BaseAgent
from ..constants import AGENT_TEMPERATURE


class PolisherAgent(BaseAgent):
    """润色优化Agent"""
    
    def __init__(self):
        super().__init__(
            name="Polisher",
            prompt_file="polisher.md"
        )
    
    def _get_default_prompt(self) -> str:
        return """你是一位专业的小说编辑和润色专家。你的任务是优化小说章节的文字质量。

## 你的能力
1. 语言润色：优化措辞，提升文采
2. 节奏调整：调整句子长短，把控阅读节奏
3. 细节补充：丰富场景描写和心理描写
4. 风格统一：保持全文风格一致
5. 错误修正：修复语法和逻辑问题

## 润色原则
1. 保持原意：不改变剧情和人物设定
2. 适度润色：不过度堆砌华丽辞藻
3. 符合风格：根据小说类型调整文风
4. 提升可读性：让文章更加流畅

## 输出格式
直接输出润色后的完整章节内容。"""
    
    async def execute(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        润色章节
        
        Args:
            input_data: 包含 content(原始内容), feedback(评估反馈)
            context: 上下文
            
        Returns:
            润色后的内容
        """
        content = input_data.get("content", "")
        feedback = input_data.get("feedback", "")
        style = input_data.get("style", "网文风格")
        
        prompt = f"""请对以下章节进行润色优化：

## 原始内容
{content}

## 评估反馈(需要改进的地方)
{feedback if feedback else "无特殊反馈，请进行常规润色"}

## 风格要求
{style}

## 润色要求
1. 保持原有剧情不变
2. 优化语言表达
3. 增强画面感和代入感
4. 根据反馈重点改进问题区域

请输出润色后的完整章节："""

        messages = [{"role": "user", "content": prompt}]
        
        response = await self.call_llm(messages, temperature=AGENT_TEMPERATURE.POLISHER_MAIN)
        
        return {
            "success": True,
            "agent": self.name,
            "original_length": len(content),
            "polished_length": len(response),
            "content": response
        }
    
    async def polish_style(
        self,
        content: str,
        target_style: str
    ) -> str:
        """
        风格转换润色
        
        Args:
            content: 原始内容
            target_style: 目标风格描述
            
        Returns:
            转换后的内容
        """
        prompt = f"""请将以下内容转换为指定风格：

## 原始内容
{content}

## 目标风格
{target_style}

保持剧情不变，只调整文字风格，输出转换后的内容："""

        messages = [{"role": "user", "content": prompt}]
        return await self.call_llm(messages, temperature=AGENT_TEMPERATURE.POLISHER_STYLE)


# 模块职责说明：负责对章节内容进行润色和优化，支持风格转换功能。
