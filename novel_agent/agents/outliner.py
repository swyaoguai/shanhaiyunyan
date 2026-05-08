"""
大纲规划Agent
负责规划小说的整体结构和分卷大纲
实现Prompt Chaining模式
"""

from typing import Dict, Any, Optional, List
from .base_agent import AgentCapability, BaseAgent
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

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["story_outlining", "story_planning"],
            accept_task_types=["build_outline"],
            required_inputs=["world", "protagonist"],
            produced_outputs=["outline"],
            priority=91,
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
        discussion_context = str(
            input_data.get("discussion_context")
            or input_data.get("recent_discussion")
            or ((context or {}).get("discussion_context") if isinstance(context, dict) else "")
            or ((context or {}).get("recent_discussion") if isinstance(context, dict) else "")
            or ""
        ).strip()
        
        # Prompt Chaining: 先生成总纲，再细化
        
        # Step 1: 生成总纲
        try:
            await self.notify_progress("正在读取世界观与需求，规划总体目标与规模...", 20)
        except Exception:
            pass

        outline_variables = {
            "worldbuilding": world,
            "world": world,
            "user_input": {
                "protagonist": protagonist,
                "plot_idea": plot_idea,
                "volume_count": volume_count,
                "chapters_per_volume": chapters_per_volume,
                "discussion_context": discussion_context,
            },
            "protagonist": protagonist,
            "plot_idea": plot_idea,
            "volume_count": volume_count,
            "chapters_per_volume": chapters_per_volume,
            "discussion_context": discussion_context,
        }
        custom_prompt = self._render_custom_task_prompt("create_outline", **outline_variables)
        if custom_prompt:
            response = await self.call_llm([{"role": "user", "content": custom_prompt}])
            try:
                import json
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                else:
                    json_str = response
                outline_data = json.loads(json_str.strip())
            except (json.JSONDecodeError, ValueError, IndexError):
                outline_data = {"raw_content": response}

            try:
                await self.notify_progress("大纲规划完成", 100)
            except Exception:
                pass

            return {
                "success": True,
                "agent": self.name,
                "outline": outline_data,
                "total_outline": response,
                "raw_response": response,
                "prompt_source": "custom_task_prompt",
            }
        total_prompt = f"""基于以下信息，规划小说的总体大纲：

## 世界观
{world}

## 主角设定
{protagonist if protagonist else "请自行设计一个有特色的主角"}

## 剧情构思
{plot_idea if plot_idea else "请自由发挥，创作一个精彩的故事"}

## 聊天讨论上下文（最高优先级）
{discussion_context if discussion_context else "无"}

## 要求
- 分为 {volume_count} 卷
- 全书预计规模参考：每卷约 {chapters_per_volume} 章，仅用于判断体量，不输出章节清单
- 设计清晰的主线冲突和角色成长线
- “大纲”是整部小说的全局蓝图，不要把单章列表当成大纲正文
- 默认全书大纲结构：
  书名、作者、简介、故事梗概
  一、【力量体系】
  二、【世界地图】
  三、【中心思想】
  四、【矛盾冲突】
  五、【前期剧情】
  六、【叙事节奏】
  七、【小说卖点】
  八、【角色设定】

## 重要说明
“聊天讨论上下文”和“剧情构思”字段中可能已经包含沟通助手与用户的完整讨论摘要。
你必须优先遵守这些讨论中已经确定的剧情方向、风格要求、人物关系、爽点偏好、禁忌与特殊约束，
不能因为世界观或默认套路而把这些既定要求覆盖掉。

请先输出总纲（JSON格式），包含 title、global_outline、theme、main_conflict、ending_direction："""

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
3. 本卷主线推进、核心冲突、角色成长、阶段高潮

不要展开到单章标题或单章列表；章节目标应由“章纲设定/细纲设定”单独生成。

输出完整的JSON格式大纲，必须包含：
- title：小说标题
- global_outline：按默认全书大纲结构写成的完整大纲正文
- volumes：分卷规划，每卷只包含 volume_number、volume_title、volume_summary、core_conflict、protagonist_growth、volume_climax、key_events；不要包含 chapters

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
            await self.notify_progress("正在整理分卷总纲...", 90)
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
