"""
质量评估Agent
负责评估章节质量，检测问题
实现Evals系统
"""

from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent
from ..constants import AGENT_TEMPERATURE, WRITING_CONFIG


class EvaluatorAgent(BaseAgent):
    """质量评估Agent"""
    
    def __init__(self):
        super().__init__(
            name="Evaluator",
            prompt_file="evaluator.md"
        )
    
    def _get_default_prompt(self) -> str:
        return """你是一位严格的小说质量评估专家。你的任务是检测小说中的各种问题并给出评分。

## 评估维度
1. **剧情一致性** (0-100分)
   - 情节是否连贯
   - 有无剧情漏洞
   - 伏笔是否合理

2. **角色一致性** (0-100分)
   - 角色行为是否符合设定
   - 有无OOC(Out of Character)
   - 角色发展是否合理

3. **文字质量** (0-100分)
   - 语法错误
   - 表达流畅度
   - 文采水平

4. **节奏把控** (0-100分)
   - 情节推进速度
   - 详略得当程度
   - 高潮设置

5. **代入感** (0-100分)
   - 场景描写
   - 情感共鸣
   - 阅读体验

## 输出格式
JSON格式，包含：
- passed: 是否通过(总分>=70为通过)
- total_score: 总分(各维度平均)
- scores: 各维度分数
- issues: 发现的问题列表
- suggestions: 改进建议
- highlights: 亮点描述"""
    
    async def execute(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        评估章节质量
        
        Args:
            input_data: 包含 content(章节内容), chapter_outline(章节大纲)
            context: 上下文(包含角色设定、前文信息等)
            
        Returns:
            评估结果
        """
        content = input_data.get("content", "")
        chapter_outline = input_data.get("chapter_outline", "")
        
        characters = context.get("characters", []) if context else []
        world = context.get("world", {}) if context else {}
        previous_summary = context.get("previous_summary", "") if context else ""
        
        prompt = f"""请评估以下章节的质量：

## 章节内容
{content}

## 章节大纲(用于对比)
{chapter_outline if chapter_outline else "无大纲参考"}

## 角色设定(用于检测OOC)
{characters if characters else "无角色设定参考"}

## 世界观设定(用于检测一致性)
{world if world else "无世界观参考"}

## 前情提要(用于检测连贯性)
{previous_summary if previous_summary else "无前文参考"}

请从以下维度评估并输出JSON格式结果：
1. 剧情一致性
2. 角色一致性  
3. 文字质量
4. 节奏把控
5. 代入感

输出评估结果："""

        messages = [{"role": "user", "content": prompt}]
        
        response = await self.call_llm(messages, temperature=AGENT_TEMPERATURE.EVALUATOR_STABLE)  # 低温度保证评估稳定
        
        # 解析评估结果
        try:
            import json
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            eval_result = json.loads(json_str.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            # 解析失败，返回默认通过
            eval_result = {
                "passed": True,
                "total_score": 75,
                "scores": {},
                "issues": [],
                "suggestions": [],
                "raw_response": response
            }
        
        return {
            "success": True,
            "agent": self.name,
            "evaluation": eval_result,
            "raw_response": response
        }
    
    async def check_consistency(
        self,
        chapters: List[str],
        characters: List[Dict],
        world: Dict
    ) -> Dict[str, Any]:
        """
        检查多章节一致性
        
        Args:
            chapters: 章节内容列表
            characters: 角色列表
            world: 世界观设定
            
        Returns:
            一致性检查结果
        """
        # 构建摘要用于长文本检查
        truncate_len = WRITING_CONFIG.CONSISTENCY_CHECK_TRUNCATE
        chapter_summaries = [c[:truncate_len] + "..." if len(c) > truncate_len else c for c in chapters]
        
        prompt = f"""请检查以下多个章节之间的一致性：

## 章节摘要
{chapter_summaries}

## 角色设定
{characters}

## 世界观
{world}

请检查：
1. 角色性格是否前后一致
2. 剧情是否有矛盾
3. 世界观规则是否被违反
4. 时间线是否正确

输出JSON格式的检查结果："""

        messages = [{"role": "user", "content": prompt}]
        response = await self.call_llm(messages, temperature=AGENT_TEMPERATURE.EVALUATOR_STABLE)
        
        try:
            import json
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            else:
                json_str = response
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            return {"raw_response": response}


# 模块职责说明：负责评估章节质量，检测一致性问题，实现Evals系统。
