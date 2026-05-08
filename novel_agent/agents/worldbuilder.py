"""
世界观构建Agent
负责生成小说的世界观设定
"""

from typing import Dict, Any, Optional
from .base_agent import AgentCapability, BaseAgent


class WorldbuilderAgent(BaseAgent):
    """世界观构建Agent"""
    
    def __init__(self):
        super().__init__(
            name="Worldbuilder",
            prompt_file="worldbuilder.md"
        )
    
    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import WORLDBUILDER_PROMPT
        return WORLDBUILDER_PROMPT

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["worldbuilding", "story_planning"],
            accept_task_types=["build_world"],
            required_inputs=["novel_type"],
            produced_outputs=["world"],
            priority=92,
            max_concurrency=1,
            metadata={
                "stage": "planning",
                "prompt_file": self.prompt_file or "",
                "agent_class": self.__class__.__name__,
            },
        )
    
    async def execute(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建世界观
        
        Args:
            input_data: 包含 novel_type(小说类型), theme(主题), requirements(特殊要求)
            context: 上下文信息
            
        Returns:
            世界观设定字典
        """
        novel_type = input_data.get("novel_type") or ""
        theme = input_data.get("theme", "")
        requirements = input_data.get("requirements", "")
        discussion_context = str(
            input_data.get("discussion_context")
            or input_data.get("recent_discussion")
            or ((context or {}).get("discussion_context") if isinstance(context, dict) else "")
            or ((context or {}).get("recent_discussion") if isinstance(context, dict) else "")
            or ""
        ).strip()

        # 进度：读取需求/确认风格
        try:
            await self.notify_progress("正在读取需求并确认风格...", 10)
        except Exception:
            pass

        novel_type_section = f"## 小说类型\n{novel_type}" if novel_type else "## 小说类型\n请告诉我小说类型（玄幻、都市、科幻、言情、武侠等）"

        prompt = self._render_custom_task_prompt(
            "build_world",
            user_input={
                "novel_type": novel_type,
                "theme": theme,
                "requirements": requirements,
                "discussion_context": discussion_context,
            },
            novel_type=novel_type,
            theme=theme,
            requirements=requirements,
            discussion_context=discussion_context,
        )
        if not prompt:
            prompt = f"""请为以下小说构建世界观：

{novel_type_section}

## 主题/风格
{theme if theme else "由你自由发挥"}

## 特殊要求
{requirements if requirements else "无特殊要求"}

## 聊天讨论上下文（最高优先级）
{discussion_context if discussion_context else "无"}

请严格继承聊天讨论中用户已经确认或明显倾向的设定；不要用默认套路覆盖主角、题材、能力体系、世界背景、禁忌或风格要求。
如果关键创作信息不足以可靠构建世界观，请输出 {{"status":"missing_info","missing_info":[...]}}，不要擅自补成无关设定。

请输出完整的世界观设定（JSON格式）："""

        messages = [{"role": "user", "content": prompt}]
        
        # 进度：开始生成世界观骨架
        try:
            await self.notify_progress("正在生成世界观骨架（力量体系/地理/历史）...", 40)
        except Exception:
            pass

        response = await self.call_llm(messages)
        
        # 尝试解析JSON
        try:
            import json
            # 提取JSON部分
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            world_data = json.loads(json_str.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            # 解析失败则返回原始文本
            world_data = {"raw_content": response}

        # 进度：补齐钩子与叙事约束 -> 完成
        try:
            await self.notify_progress("正在补齐剧情钩子与叙事约束...", 90)
            await self.notify_progress("世界观构建完成", 100)
        except Exception:
            pass
        
        return {
            "success": True,
            "agent": self.name,
            "world": world_data,
            "raw_response": response
        }


# 模块职责说明：负责根据用户需求构建完整、自洽的小说世界观设定。
