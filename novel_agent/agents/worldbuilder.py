"""
世界观构建Agent
负责生成小说的世界观设定
"""

from typing import Dict, Any, Optional
from .base_agent import BaseAgent


class WorldbuilderAgent(BaseAgent):
    """世界观构建Agent"""
    
    def __init__(self):
        super().__init__(
            name="Worldbuilder",
            prompt_file="worldbuilder.md"
        )
    
    def _get_default_prompt(self) -> str:
        return """你是一位专业的小说世界观架构师。你的任务是根据用户的需求，构建完整、自洽的小说世界观。

## 你的能力
1. 力量体系设计：根据小说类型设计合理的力量等级和修炼体系
2. 地理环境构建：创造有特色的地点、国家、势力分布
3. 历史背景编织：构建世界历史和重要事件
4. 规则法则制定：设定世界运行的核心规则
5. 文化习俗设计：不同种族/势力的文化特色

## 输出格式
请以结构化的JSON格式输出世界观设定，包含以下字段：
- world_name: 世界名称
- world_type: 世界类型(玄幻/科幻/都市等)
- power_system: 力量体系详细设定
- geography: 地理环境描述
- history: 重要历史事件
- factions: 主要势力介绍
- rules: 世界核心规则
- culture: 文化习俗特色

确保所有设定相互呼应，逻辑自洽。"""
    
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
        novel_type = input_data.get("novel_type", "玄幻")
        theme = input_data.get("theme", "")
        requirements = input_data.get("requirements", "")
        
        prompt = f"""请为以下小说构建世界观：

## 小说类型
{novel_type}

## 主题/风格
{theme if theme else "由你自由发挥"}

## 特殊要求
{requirements if requirements else "无特殊要求"}

请输出完整的世界观设定（JSON格式）："""

        messages = [{"role": "user", "content": prompt}]
        
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
        
        return {
            "success": True,
            "agent": self.name,
            "world": world_data,
            "raw_response": response
        }


# 模块职责说明：负责根据用户需求构建完整、自洽的小说世界观设定。
