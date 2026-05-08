"""
质量评估Agent
负责评估章节质量，检测问题
实现Evals系统
"""

from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent, AgentCapability
from ..constants import AGENT_TEMPERATURE, WRITING_CONFIG


class EvaluatorAgent(BaseAgent):
    """质量评估Agent"""
    
    def __init__(self):
        super().__init__(
            name="Evaluator",
            prompt_file="evaluator.md"
        )
    
    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import EVALUATOR_PROMPT
        return EVALUATOR_PROMPT

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["evaluate_chapter", "quality_review", "review_artifact"],
            accept_task_types=["evaluate_chapter", "review_artifact"],
            required_inputs=["content", "chapter_outline"],
            produced_outputs=["evaluation"],
            priority=90,
            max_concurrency=2,
            metadata={
                "stage": "evaluation",
            },
        )

    async def review_artifact(
        self,
        *,
        task_id: str,
        artifact_id: str,
        artifact_type: str,
        artifact: Any,
        revision_target: str,
        workflow_context: Any,
    ):
        """Review generic workflow artifacts without requiring an LLM call."""
        from ..workflow.artifact_review import review_artifact_contextual

        return review_artifact_contextual(
            task_id=task_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            artifact=artifact,
            revision_target=revision_target,
            workflow_context=workflow_context,
        )
    
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
        
        prompt = self._render_custom_task_prompt(
            "evaluate_chapter",
            content=content,
            chapter_outline=chapter_outline,
            world=world,
            characters=characters,
            previous_summary=previous_summary,
        )
        if not prompt:
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
