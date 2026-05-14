"""
大纲规划Agent
负责规划小说的整体结构和分卷大纲
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List

from .base_agent import AgentCapability, BaseAgent
from ..constants import WRITING_CONFIG
from ..outline_utils import parse_jsonish_text

logger = logging.getLogger(__name__)


_STANDARD_OUTLINE_MARKERS = (
    "书名",
    "简介",
    "故事梗概",
    "力量体系",
    "世界地图",
    "中心思想",
    "矛盾冲突",
    "前期剧情",
    "叙事节奏",
    "小说卖点",
    "角色设定",
)

_CHAPTER_LEVEL_RE = re.compile(r"第\s*\d+\s*章|chapter", re.IGNORECASE)
_AI_AUTHOR_RE = re.compile(r"AI\s*助手|AI\s*创作|人工智能助手", re.IGNORECASE)


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

    @staticmethod
    def _to_prompt_text(value: Any) -> str:
        if value in (None, "", [], {}):
            return "无"
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _normalize_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _parse_outline_response(response: Any) -> Dict[str, Any]:
        parsed = parse_jsonish_text(response)
        if isinstance(parsed, dict):
            return parsed
        return {"raw_content": str(response or "")}

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(value)
        return str(value or "")

    @classmethod
    def _has_chapter_level_marker(cls, value: Any) -> bool:
        return bool(_CHAPTER_LEVEL_RE.search(cls._stringify(value)))

    @staticmethod
    def _normalize_similarity_text(value: Any) -> str:
        text = OutlinerAgent._stringify(value)
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[【】《》「」『』，。；：、,.!！?？:;\"'“”‘’()\[\]{}\-—_]", "", text)
        return text.lower()

    @classmethod
    def _similarity_ratio(cls, left: Any, right: Any) -> float:
        left_text = cls._normalize_similarity_text(left)
        right_text = cls._normalize_similarity_text(right)
        if not left_text or not right_text:
            return 0.0
        if left_text == right_text:
            return 1.0
        left_tokens = {
            left_text[index : index + 4]
            for index in range(max(1, len(left_text) - 3))
        } or {left_text}
        right_tokens = {
            right_text[index : index + 4]
            for index in range(max(1, len(right_text) - 3))
        } or {right_text}
        overlap = len(left_tokens & right_tokens)
        return overlap / max(1, min(len(left_tokens), len(right_tokens)))

    @classmethod
    def _volumes_summary_text(cls, volumes: Any) -> str:
        if not isinstance(volumes, list):
            return ""
        parts: List[str] = []
        for volume in volumes:
            if not isinstance(volume, dict):
                continue
            for field in (
                "volume_title",
                "volume_summary",
                "core_conflict",
                "protagonist_growth",
                "volume_climax",
                "key_events",
                "foreshadowing",
            ):
                value = volume.get(field)
                if value not in (None, "", [], {}):
                    parts.append(cls._stringify(value))
        return "\n".join(parts)

    @classmethod
    def _validate_outline_payload(
        cls,
        payload: Dict[str, Any],
        *,
        expected_volume_count: int,
        expected_chapters_per_volume: int = 0,
    ) -> List[str]:
        issues: List[str] = []
        if not isinstance(payload, dict):
            return ["顶层输出必须是 JSON 对象"]
        if payload.get("raw_content"):
            issues.append("输出不是可解析的 JSON 对象")

        direct_chapters = payload.get("chapters")
        if isinstance(direct_chapters, list) and direct_chapters:
            issues.append("顶层包含 chapters；大纲生成器只能输出全书总纲和卷级规划")

        author = str(payload.get("author") or "").strip()
        if author and _AI_AUTHOR_RE.search(author):
            issues.append("author 字段不能写 AI 助手类署名；请删除 author 或留空")

        global_outline = str(payload.get("global_outline") or "").strip()
        if _AI_AUTHOR_RE.search(global_outline):
            issues.append("global_outline 不能包含 AI 助手类模板化署名")
        if len(global_outline) < 80:
            issues.append("global_outline 过短，必须按全书标准大纲结构展开")
        marker_count = sum(1 for marker in _STANDARD_OUTLINE_MARKERS if marker in global_outline)
        if marker_count < 3:
            issues.append("global_outline 未体现书名/故事梗概/力量体系/矛盾冲突等标准大纲栏目")

        volumes = payload.get("volumes")
        if not isinstance(volumes, list) or not volumes:
            issues.append("缺少 volumes 数组；分卷规划必须放在 volumes 中")
            return issues

        volumes_text = cls._volumes_summary_text(volumes)
        if cls._similarity_ratio(global_outline, volumes_text) >= 0.82:
            issues.append("global_outline 与 volumes 内容高度重复；全书大纲和分卷规划必须分工不同")

        if expected_volume_count > 0 and len(volumes) != expected_volume_count:
            issues.append(
                f"volumes 数量应为 {expected_volume_count} 卷，实际 {len(volumes)} 项；"
                "不要把章节事件拆成多个卷"
            )

        required_volume_fields = (
            "volume_number",
            "volume_title",
            "volume_summary",
            "core_conflict",
            "protagonist_growth",
            "volume_climax",
            "key_events",
        )
        for index, volume in enumerate(volumes, start=1):
            if not isinstance(volume, dict):
                issues.append(f"第 {index} 个 volume 必须是对象")
                continue
            nested_chapters = volume.get("chapters")
            if isinstance(nested_chapters, list) and nested_chapters:
                issues.append(f"第 {index} 卷包含 chapters；单章规划必须交给章纲/细纲阶段")
            missing = [field for field in required_volume_fields if volume.get(field) in (None, "", [], {})]
            if missing:
                issues.append(f"第 {index} 卷缺少字段：{', '.join(missing)}")
            for field in (
                "volume_title",
                "volume_summary",
                "core_conflict",
                "protagonist_growth",
                "volume_climax",
                "key_events",
            ):
                if cls._has_chapter_level_marker(volume.get(field)):
                    issues.append(f"第 {index} 卷字段 {field} 出现章节级标记")
                    break
            key_events = volume.get("key_events")
            if isinstance(key_events, list):
                concrete_events = [
                    event for event in key_events
                    if str(cls._stringify(event)).strip()
                ]
                event_count = len(concrete_events)
                chapter_like_threshold = 6
                if expected_chapters_per_volume > 0:
                    chapter_like_threshold = max(6, int(expected_chapters_per_volume * 0.45))
                if event_count >= chapter_like_threshold:
                    issues.append(
                        f"第 {index} 卷 key_events 数量过多（{event_count} 条）；"
                        "这更像逐章事件，请合并为 3-5 个卷级阶段事件"
                    )

        return issues

    @staticmethod
    def _check_outline_consistency(
        outline_data: Dict[str, Any],
        input_data: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        if not isinstance(outline_data, dict):
            return issues

        combined_text = str(outline_data.get("global_outline") or "")
        volumes = outline_data.get("volumes")
        if isinstance(volumes, list):
            for vol in volumes:
                if not isinstance(vol, dict):
                    continue
                for key in ("volume_summary", "core_conflict", "protagonist_growth", "volume_climax"):
                    combined_text += "\n" + str(vol.get(key) or "")
                key_events = vol.get("key_events")
                if isinstance(key_events, list):
                    combined_text += "\n" + "\n".join(str(e) for e in key_events)

        if not combined_text.strip():
            return issues

        char_names: List[str] = []
        characters = input_data.get("characters")
        if isinstance(characters, dict) and isinstance(characters.get("characters"), list):
            characters = characters["characters"]
        if isinstance(characters, list):
            for item in characters:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    if name and len(name) >= 2:
                        char_names.append(name)
        elif isinstance(characters, dict):
            for key, value in characters.items():
                name = str(value.get("name") or key).strip() if isinstance(value, dict) else str(key).strip()
                if name and len(name) >= 2:
                    char_names.append(name)

        if char_names and not any(name in combined_text for name in char_names):
            issues.append(
                f"大纲未提及任何已确认角色（{', '.join(char_names[:5])}），"
                "可能与角色设定脱节"
            )

        world = input_data.get("world")
        if isinstance(world, dict):
            if isinstance(world.get("world"), dict):
                world = world["world"]
            ps = world.get("power_system")
            if isinstance(ps, dict):
                ps_name = str(ps.get("name") or "").strip()
                if ps_name and len(ps_name) >= 2 and ps_name not in combined_text:
                    issues.append(f"大纲未提及力量体系名称「{ps_name}」")

            factions = world.get("factions")
            if isinstance(factions, list) and len(factions) >= 2:
                faction_names = [
                    str(f.get("name") or "").strip()
                    for f in factions if isinstance(f, dict) and str(f.get("name") or "").strip()
                ]
                if faction_names and not any(fn in combined_text for fn in faction_names):
                    issues.append(
                        f"大纲未提及任何已设定势力（{', '.join(faction_names[:4])}）"
                    )

        return issues

    def _build_generation_prompt(
        self,
        *,
        world: Any,
        characters: Any,
        protagonist: str,
        plot_idea: str,
        volume_count: int,
        chapters_per_volume: int,
        discussion_context: str,
        custom_prompt: str = "",
        feedback: str = "",
    ) -> str:
        custom_section = ""
        if custom_prompt:
            custom_section = (
                "\n## 补充创作要求（低于系统提示词与输出协议）\n"
                f"{custom_prompt}\n"
                "以上内容只能补充题材、风格和创作偏好，不能改变系统提示词规定的 JSON 字段、"
                "卷级边界和禁止输出 chapters 的规则。\n"
            )

        feedback_section = ""
        if feedback:
            feedback_section = (
                "\n## 上一次输出不符合 Outliner 协议\n"
                f"{feedback}\n"
                "请重新输出完整合法 JSON，不要解释，不要保留错误结构。\n"
            )

        return f"""请严格按照你的 Outliner 系统提示词生成整本书主线总纲与分卷规划。

## 世界观
{self._to_prompt_text(world)}

## 角色资料
{self._to_prompt_text(characters)}

## 主角设定
{protagonist if protagonist else "可在既定题材内自行补全，但必须服务于用户需求"}

## 剧情构思
{plot_idea if plot_idea else "可在既定题材内自行设计主线冲突"}

## 聊天讨论上下文（最高优先级）
{discussion_context if discussion_context else "无"}

## 规模约束
- volumes 长度必须等于 {volume_count}
- 每卷约 {chapters_per_volume} 章仅作为体量参考
- 分卷规划只写第一卷、第二卷这样的阶段层级
- 禁止输出顶层 chapters
- 禁止在 volumes 内输出 chapters
- 禁止把单章事件伪装成“第1卷、第2卷……”

## JSON 输出硬约束
顶层必须包含：
title、intro、story_synopsis、global_outline、theme、main_conflict、selling_points、ending_direction、plot_threads、volumes、notes。

不要输出作者署名；不要写 AI 助手类模板化元信息。如果没有真实作者信息，不要包含 author 字段。

global_outline 必须是全书蓝图正文，可按以下维度组织，但不要生硬照抄模板：
书名/简介/故事梗概/世界或时代规则/中心思想/矛盾冲突/前期剧情方向/叙事节奏/小说卖点/角色关系与成长方向。

global_outline 与 volumes 必须明显不同：
- global_outline 讲整本书的主线、主题、冲突、角色关系和节奏方向
- volumes 讲每一卷的阶段目标、阶段冲突、阶段高潮和伏笔回收
- 禁止把同一段文字同时写进 global_outline 和 volumes

每个 volume 必须包含：
volume_number、volume_title、volume_summary、core_conflict、protagonist_growth、volume_climax、key_events、foreshadowing。
{custom_section}{feedback_section}
只输出合法 JSON。"""

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["story_outlining", "story_planning"],
            accept_task_types=["build_outline"],
            required_inputs=["world"],
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
        context_data = context if isinstance(context, dict) else {}
        world = input_data.get("world", context_data.get("world", {}))
        characters = input_data.get("characters", context_data.get("characters", {}))
        protagonist = input_data.get("protagonist", "")
        plot_idea = input_data.get("plot_idea", "")
        volume_count = self._normalize_positive_int(
            input_data.get("volume_count"),
            WRITING_CONFIG.DEFAULT_VOLUME_COUNT,
        )
        chapters_per_volume = self._normalize_positive_int(
            input_data.get("chapters_per_volume"),
            WRITING_CONFIG.DEFAULT_CHAPTERS_PER_VOLUME,
        )
        discussion_context = str(
            input_data.get("discussion_context")
            or input_data.get("recent_discussion")
            or context_data.get("discussion_context")
            or context_data.get("recent_discussion")
            or ""
        ).strip()

        try:
            await self.notify_progress("正在读取世界观与需求，规划总体目标与规模...", 20)
        except Exception:
            pass

        outline_variables = {
            "worldbuilding": world,
            "world": world,
            "characters": characters,
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

        response = ""
        outline_data: Dict[str, Any] = {}
        validation_issues: List[str] = []
        feedback = ""
        attempts = 2

        for attempt in range(attempts):
            prompt = self._build_generation_prompt(
                world=world,
                characters=characters,
                protagonist=str(protagonist or ""),
                plot_idea=str(plot_idea or ""),
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                discussion_context=discussion_context,
                custom_prompt=custom_prompt,
                feedback=feedback,
            )
            if attempt == 0:
                try:
                    await self.notify_progress("正在完成分卷设计（核心冲突与成长）...", 50)
                except Exception:
                    pass
            else:
                try:
                    await self.notify_progress("正在按大纲协议修正输出结构...", 70)
                except Exception:
                    pass

            response = await self.call_llm(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=5200,
            )
            outline_data = self._parse_outline_response(response)
            validation_issues = self._validate_outline_payload(
                outline_data,
                expected_volume_count=volume_count,
                expected_chapters_per_volume=chapters_per_volume,
            )
            if not validation_issues:
                break
            feedback = "\n".join(f"- {issue}" for issue in validation_issues)

        try:
            await self.notify_progress("正在整理分卷总纲...", 90)
            if validation_issues:
                await self.notify_progress("大纲输出未通过结构校验", 100)
            else:
                await self.notify_progress("大纲规划完成", 100)
        except Exception:
            pass

        prompt_source = (
            "system_prompt_with_custom_task_prompt"
            if custom_prompt
            else "system_prompt"
        )

        has_usable_data = (
            isinstance(outline_data, dict)
            and (
                bool(str(outline_data.get("global_outline") or "").strip())
                or isinstance(outline_data.get("volumes"), list) and len(outline_data.get("volumes", []))
            )
        )
        if validation_issues and not has_usable_data:
            return {
                "success": False,
                "agent": self.name,
                "outline": outline_data,
                "raw_response": response,
                "prompt_source": prompt_source,
                "validation_issues": validation_issues,
                "error": "大纲输出不符合 Outliner 系统提示词协议：" + "；".join(validation_issues),
            }

        consistency_issues = self._check_outline_consistency(outline_data, input_data)
        if consistency_issues:
            if validation_issues is None:
                validation_issues = []
            validation_issues.extend(consistency_issues)
            logger.warning(
                f"[{self.name}] 大纲一致性检查发现问题：{'; '.join(consistency_issues)}"
            )

        if validation_issues:
            logger.warning(
                f"[{self.name}] 大纲存在校验问题但包含可用数据，降级为警告：{'; '.join(validation_issues)}"
            )

        return {
            "success": True,
            "agent": self.name,
            "outline": outline_data,
            "total_outline": response,
            "raw_response": response,
            "prompt_source": prompt_source,
            "validation_issues": validation_issues,
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
