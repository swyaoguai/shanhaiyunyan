"""
世界观构建Agent
负责生成小说的世界观设定
"""

from typing import Dict, Any, Optional
from .base_agent import AgentCapability, BaseAgent


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "是", "已授权", "授权", "自主"}


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
        ai_autonomy_requested = _is_truthy(
            input_data.get("ai_autonomy_requested")
            or ((context or {}).get("ai_autonomy_requested") if isinstance(context, dict) else False)
        )
        autonomous_brief = str(
            input_data.get("autonomous_brief")
            or ((context or {}).get("autonomous_brief") if isinstance(context, dict) else "")
            or ""
        ).strip()
        if ai_autonomy_requested and not autonomous_brief:
            autonomous_brief = (
                "用户已授权助手自主补全未指定的时代背景、地域、角色关系、冲突钩子和世界细节；"
                "请在已给定题材、主题、篇幅和讨论方向内主动创作。"
            )
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
                "ai_autonomy_requested": ai_autonomy_requested,
                "autonomous_brief": autonomous_brief,
            },
            novel_type=novel_type,
            theme=theme,
            requirements=requirements,
            discussion_context=discussion_context,
            ai_autonomy_requested=ai_autonomy_requested,
            autonomous_brief=autonomous_brief,
        )
        if not prompt:
            missing_info_instruction = (
                "用户已授权你自主补全未指定设定。除非小说类型完全缺失，否则不要输出 missing_info；"
                "必须基于已知题材、主题、篇幅和聊天上下文主动生成完整世界观。"
                if ai_autonomy_requested
                else '如果关键创作信息不足以可靠构建世界观，请输出 {"status":"missing_info","missing_info":[...]}，不要擅自补成无关设定。'
            )
            prompt = f"""请为以下小说构建世界观：

{novel_type_section}

## 主题/风格
{theme if theme else "由你自由发挥"}

## 特殊要求
{requirements if requirements else "无特殊要求"}

## 聊天讨论上下文（最高优先级）
{discussion_context if discussion_context else "无"}

## 用户自主补全授权
{autonomous_brief if ai_autonomy_requested else "未授权；关键缺失时可以要求用户补充"}

请严格继承聊天讨论中用户已经确认或明显倾向的设定；不要用默认套路覆盖主角、题材、能力体系、世界背景、禁忌或风格要求。
{missing_info_instruction}

请输出完整的世界观设定（JSON格式）："""
        elif ai_autonomy_requested:
            prompt += (
                "\n\n## 用户自主补全授权（强制）\n"
                f"{autonomous_brief}\n"
                "不要因为主角、时代、地域、关系模式或剧情细节尚未指定而返回 missing_info；"
                "请在既有题材、主题、篇幅和聊天上下文内主动补全，并输出完整世界观 JSON。"
            )

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

        if isinstance(world_data, dict) and str(world_data.get("status") or "").strip().lower() == "missing_info":
            missing_items = world_data.get("missing_info")
            if isinstance(missing_items, list):
                error_text = "；".join(str(item).strip() for item in missing_items if str(item).strip())
            else:
                error_text = str(missing_items or "").strip()
            return {
                "success": False,
                "agent": self.name,
                "error": f"世界观关键信息不足：{error_text}" if error_text else "世界观关键信息不足",
                "world": world_data,
                "raw_response": response,
            }

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
