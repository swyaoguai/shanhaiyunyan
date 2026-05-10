"""
LLM 驱动的项目资料构建 Agents
用于生成事件线、细纲设定、章纲设定等结构化项目数据。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base_agent import AgentCapability, BaseAgent
from .structured_output import StructuredOutputValidator


logger = logging.getLogger(__name__)


class _ProjectDataBuilderAgent(BaseAgent):
    """项目资料构建 Agent 基类。"""

    output_label = "项目资料"
    output_key = "rows"
    extra_rules = ""
    llm_max_tokens = 3600
    generation_attempts = 2

    def __init__(self, name: str):
        super().__init__(name=name, prompt_file=None)

    def get_capabilities(self) -> AgentCapability:
        """Expose project-data builders to the formal task router."""
        task_type = str(self.output_key or "").strip()
        return AgentCapability(
            agent_name=self.name,
            capabilities=[task_type, f"build_{task_type}"] if task_type else [],
            accept_task_types=[task_type] if task_type else [],
            required_inputs=["outline_rows"],
            produced_outputs=[task_type, "rows"] if task_type else ["rows"],
            priority=90,
            max_concurrency=1,
            metadata={
                "agent_class": self.__class__.__name__,
                "data_type": task_type,
            },
        )

    def _get_default_prompt(self) -> str:
        return (
            f"你是专业的{self.output_label}构建器。\n"
            "你只负责把输入的创作信息整理成结构化 JSON。\n"
            "严禁输出 Markdown、解释、前后缀说明。\n"
            f"输出顶层必须是对象，且包含 `{self.output_key}` 数组字段。\n"
            "如果信息不足，也要基于现有大纲给出最小可用结构，而不是返回空数组。\n"
            f"{self.extra_rules}\n"
        )

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        text = str(raw_text or "").strip()
        if "```json" in text:
            return text.split("```json", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            fenced = text.split("```", 1)[1]
            if "```" in fenced:
                return fenced.split("```", 1)[0].strip()
        return text

    def _build_prompt(self, input_data: Dict[str, Any]) -> str:
        outline_rows = input_data.get("outline_rows")
        eventlines = input_data.get("eventlines")
        return (
            f"## 当前任务\n生成{self.output_label}\n\n"
            f"## 用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 最近讨论摘要\n{str(input_data.get('recent_discussion') or '').strip() or '无'}\n\n"
            f"## 世界观摘要\n{str(input_data.get('world_summary') or '').strip() or '无'}\n\n"
            f"## 大纲资料\n{json.dumps(outline_rows, ensure_ascii=False, indent=2) if isinstance(outline_rows, list) else '[]'}\n\n"
            f"## 事件线资料\n{json.dumps(eventlines, ensure_ascii=False, indent=2) if isinstance(eventlines, list) else '[]'}\n\n"
            f"请输出 JSON，对象格式为：{{\"{self.output_key}\": [...]}}"
        )

    @staticmethod
    def _stringify_outline_field(row: Dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if isinstance(value, (dict, list)):
                text = json.dumps(value, ensure_ascii=False)
            else:
                text = str(value or "")
            text = text.strip()
            if text:
                return text
        return ""

    @staticmethod
    def _coerce_chapter_number(value: Any, fallback: int) -> int:
        try:
            number = int(value)
            return number if number > 0 else fallback
        except (TypeError, ValueError):
            return fallback

    def _build_fallback_row(self, row: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        title = self._stringify_outline_field(row, "title", "name") or f"第{chapter_number}章"
        summary = self._stringify_outline_field(
            row,
            "summary",
            "description",
            "outline",
            "content",
            "chapter_outline",
        )
        return {
            "name": title,
            "description": summary or f"{title} 待根据章节大纲细化",
            "chapter_number": chapter_number,
        }

    def _build_fallback_rows(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        outline_rows = input_data.get("outline_rows")
        if not isinstance(outline_rows, list):
            return []

        fallback_rows: List[Dict[str, Any]] = []
        for index, item in enumerate(outline_rows, start=1):
            if not isinstance(item, dict):
                continue
            chapter_number = self._coerce_chapter_number(
                item.get("chapter_number") or item.get("chapter") or item.get("number"),
                index,
            )
            fallback_rows.append(self._build_fallback_row(item, chapter_number))
        return self._normalize_rows(fallback_rows)

    def _normalize_rows(self, rows: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(rows, list):
            return normalized
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not name:
                continue
            row = dict(item)
            row["name"] = name
            row["description"] = description
            normalized.append(row)
        return normalized

    async def _generate_once(
        self,
        prompt: str,
        feedback: str = "",
    ) -> tuple[Optional[Dict[str, Any]], str, List[str]]:
        user_prompt = prompt
        if feedback:
            user_prompt += f"\n\n上一次输出存在以下问题，请修复后只重写合法 JSON：\n{feedback}"

        response = await self.call_llm(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=self.llm_max_tokens,
        )
        response_text = str(response or "")
        if not response_text.strip():
            return None, response_text, ["LLM 返回空内容"]

        json_text = self._extract_json_text(response_text)
        validation = StructuredOutputValidator.validate_json_output(json_text, required_fields=[self.output_key])
        if not validation.get("is_valid"):
            return None, response_text, validation.get("violations", []) or validation.get("missing_fields", [])

        try:
            payload = json.loads(json_text)
        except Exception as exc:
            return None, response_text, [f"JSON 解析失败: {exc}"]

        if not isinstance(payload, dict):
            return None, response_text, ["顶层 JSON 必须为对象"]
        return payload, response_text, []

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = dict(input_data or {})
        prompt = self._build_prompt(request)
        response = ""
        payload: Optional[Dict[str, Any]] = None
        issues: List[str] = []
        feedback = ""

        for attempt in range(max(1, int(self.generation_attempts))):
            payload, response, issues = await self._generate_once(prompt, feedback=feedback)
            if payload is not None:
                break
            feedback = "；".join(str(item) for item in issues if str(item).strip()) or "请输出合法且完整的 JSON"
            logger.warning(
                "[%s] %s JSON generation failed on attempt %s/%s: %s",
                self.name,
                self.output_label,
                attempt + 1,
                self.generation_attempts,
                feedback,
            )

        if payload is None:
            fallback_rows = self._build_fallback_rows(request)
            if fallback_rows:
                logger.warning(
                    "[%s] Using local fallback for %s after JSON generation failure: %s rows",
                    self.name,
                    self.output_label,
                    len(fallback_rows),
                )
                return {
                    "success": True,
                    "agent": self.name,
                    "rows": fallback_rows,
                    "fallback_used": True,
                    "response_message": f"{self.output_label}生成器未返回合法 JSON，已根据现有大纲生成最小可用结构。",
                    "validation_issues": issues,
                    "raw_response": response,
                }
            return {
                "success": False,
                "agent": self.name,
                "rows": [],
                "response_message": f"{self.output_label}生成失败，未输出合法 JSON。",
                "validation_issues": issues,
                "raw_response": response,
            }

        rows = self._normalize_rows(payload.get(self.output_key))
        if not rows:
            fallback_rows = self._build_fallback_rows(request)
            if fallback_rows:
                logger.warning(
                    "[%s] Using local fallback for %s because normalized rows were empty: %s rows",
                    self.name,
                    self.output_label,
                    len(fallback_rows),
                )
                return {
                    "success": True,
                    "agent": self.name,
                    "rows": fallback_rows,
                    "fallback_used": True,
                    "response_message": f"{self.output_label}未生成有效条目，已根据现有大纲生成最小可用结构。",
                    "raw_response": response,
                }
            return {
                "success": False,
                "agent": self.name,
                "rows": [],
                "response_message": f"{self.output_label}生成失败，未生成有效条目。",
                "raw_response": response,
            }

        return {
            "success": True,
            "agent": self.name,
            "rows": rows,
            "raw_response": response,
        }


class EventlineBuilderAgent(_ProjectDataBuilderAgent):
    output_label = "事件线"
    output_key = "eventlines"
    extra_rules = (
        "每条事件线至少包含：name、description、participants、conflict、status。\n"
        "优先提炼主线/支线/人物线，禁止只把章节摘要机械复制成空洞条目。"
    )

    def __init__(self):
        super().__init__(name="EventlineBuilder")

    def _build_fallback_row(self, row: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        base = super()._build_fallback_row(row, chapter_number)
        summary = base["description"]
        return {
            "name": f"第{chapter_number}章事件线：{base['name']}",
            "description": summary,
            "participants": self._stringify_outline_field(row, "characters", "participants", "roles") or "待补充",
            "conflict": self._stringify_outline_field(row, "conflict", "core_conflict", "turning_point") or summary,
            "status": "planned",
        }


class DetailOutlineBuilderAgent(_ProjectDataBuilderAgent):
    output_label = "细纲设定"
    output_key = "detail_settings"
    extra_rules = (
        "每条细纲至少包含：name、description、chapter_number、scene_goal、conflict、notes。\n"
        "细纲应体现每章的场景目标与冲突，而不是仅复述标题。"
    )

    def __init__(self):
        super().__init__(name="DetailOutlineBuilder")

    def _build_fallback_row(self, row: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        base = super()._build_fallback_row(row, chapter_number)
        summary = base["description"]
        conflict = self._stringify_outline_field(row, "conflict", "core_conflict", "turning_point") or "围绕本章目标制造阻力并推动剧情转折"
        return {
            "name": base["name"],
            "description": summary,
            "chapter_number": chapter_number,
            "scene_goal": self._stringify_outline_field(row, "scene_goal", "chapter_goal", "goal") or summary,
            "conflict": conflict,
            "notes": self._stringify_outline_field(row, "notes", "hook", "ending_hook") or "本条由本地兜底生成，建议后续补充更细场景节拍。",
        }


class ChapterSettingBuilderAgent(_ProjectDataBuilderAgent):
    output_label = "章纲设定"
    output_key = "chapter_settings"
    extra_rules = (
        "每条章纲至少包含：name、description、chapter_number、chapter_goal、key_event、ending_hook。\n"
        "章纲应体现可执行写作目标、关键事件和章末钩子。\n"
        "如果本章承接事件线资料，必须增加 plot_thread 对象，字段包含 thread_id、thread_title、"
        "switch_to、return_by_chapter、max_consecutive_chapters、objective；"
        "需要回主线时设置 return_to_main=true。"
    )

    def __init__(self):
        super().__init__(name="ChapterSettingBuilder")

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = await super().execute(input_data, context=context)
        rows = result.get("rows")
        if result.get("success") and isinstance(rows, list):
            result["rows"] = self._enrich_rows_with_eventlines(rows, input_data)
        return result

    def _build_fallback_row(self, row: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        base = super()._build_fallback_row(row, chapter_number)
        summary = base["description"]
        key_event = self._stringify_outline_field(row, "key_event", "event", "core_event", "summary") or summary
        return {
            "name": base["name"],
            "description": summary,
            "chapter_number": chapter_number,
            "chapter_goal": self._stringify_outline_field(row, "chapter_goal", "goal", "scene_goal") or summary,
            "key_event": key_event,
            "ending_hook": self._stringify_outline_field(row, "ending_hook", "hook", "cliffhanger") or "以新的线索、危机或选择引出下一章。",
        }

    def _build_fallback_rows(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        outline_rows = input_data.get("outline_rows")
        if not isinstance(outline_rows, list):
            return []

        try:
            total_chapters = max(0, int(input_data.get("total_chapters") or 0))
        except (TypeError, ValueError):
            total_chapters = 0
        if total_chapters > len(outline_rows) and len(outline_rows) <= 1:
            source_row = outline_rows[0] if outline_rows and isinstance(outline_rows[0], dict) else {}
            overview = self._stringify_outline_field(
                source_row,
                "summary",
                "global_outline",
                "story_synopsis",
                "volume_plan",
                "description",
                "content",
            )
            expanded_rows: List[Dict[str, Any]] = []
            for chapter_number in range(1, total_chapters + 1):
                expanded_rows.append(
                    self._build_fallback_row(
                        {
                            **source_row,
                            "chapter_number": chapter_number,
                            "title": f"第{chapter_number}章",
                            "summary": overview or f"依据主线大纲推进第{chapter_number}章剧情",
                        },
                        chapter_number,
                    )
                )
            return self._enrich_rows_with_eventlines(
                self._normalize_rows(expanded_rows),
                input_data,
            )

        fallback_rows: List[Dict[str, Any]] = []
        for index, item in enumerate(outline_rows, start=1):
            if not isinstance(item, dict):
                continue
            chapter_number = self._coerce_chapter_number(
                item.get("chapter_number") or item.get("chapter") or item.get("number"),
                index,
            )
            fallback_rows.append(self._build_fallback_row(item, chapter_number))
        return self._enrich_rows_with_eventlines(self._normalize_rows(fallback_rows), input_data)

    def _enrich_rows_with_eventlines(
        self,
        rows: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        eventlines = [
            row for row in input_data.get("eventlines", [])
            if isinstance(row, dict)
        ]
        if not eventlines:
            return rows

        enriched: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            copied = dict(row)
            if isinstance(copied.get("plot_thread"), dict) and copied.get("plot_thread"):
                enriched.append(copied)
                continue
            chapter_number = self._coerce_chapter_number(
                copied.get("chapter_number") or copied.get("chapter") or copied.get("number"),
                index,
            )
            thread = self._select_eventline_for_chapter(eventlines, chapter_number)
            if thread:
                copied["plot_thread"] = self._build_plot_thread_directive(thread, chapter_number)
            enriched.append(copied)
        return enriched

    @classmethod
    def _select_eventline_for_chapter(
        cls,
        eventlines: List[Dict[str, Any]],
        chapter_number: int,
    ) -> Optional[Dict[str, Any]]:
        first_range_match: Optional[Dict[str, Any]] = None
        for row in eventlines:
            start_chapter = cls._coerce_chapter_number(row.get("start_chapter"), 0)
            if not start_chapter:
                continue
            return_by = cls._coerce_chapter_number(
                row.get("target_return_chapter") or row.get("return_by_chapter") or row.get("return_by"),
                0,
            )
            if start_chapter == chapter_number:
                return row
            if return_by and start_chapter < chapter_number <= return_by and first_range_match is None:
                first_range_match = row
        return first_range_match

    @classmethod
    def _build_plot_thread_directive(
        cls,
        row: Dict[str, Any],
        chapter_number: int,
    ) -> Dict[str, Any]:
        thread_id = str(row.get("thread_id") or row.get("id") or row.get("name") or "").strip()
        thread_title = str(row.get("thread_title") or row.get("name") or row.get("title") or thread_id).strip()
        thread_type = str(row.get("thread_type") or "subplot").strip().lower()
        start_chapter = cls._coerce_chapter_number(row.get("start_chapter"), 0)
        return_by = cls._coerce_chapter_number(
            row.get("target_return_chapter") or row.get("return_by_chapter") or row.get("return_by"),
            0,
        )
        max_consecutive = cls._coerce_chapter_number(row.get("max_consecutive_chapters") or row.get("max_streak"), 0)
        directive: Dict[str, Any] = {
            "thread_id": thread_id,
            "thread_title": thread_title,
            "objective": str(row.get("objective") or row.get("description") or "").strip(),
        }
        if thread_type == "main":
            directive["return_to_main"] = True
        elif start_chapter == chapter_number:
            directive["switch_to"] = thread_id
        if return_by:
            directive["return_by_chapter"] = return_by
        if max_consecutive:
            directive["max_consecutive_chapters"] = max_consecutive
        return {key: value for key, value in directive.items() if value not in ("", None)}


class GenericProjectDataBuilderAgent(_ProjectDataBuilderAgent):
    """通用资料库构建 Agent，用于道具、摘要和用户自定义资料库。"""

    output_key = "rows"
    llm_max_tokens = 3200

    def __init__(self, *, data_type: str, category_name: str):
        self.data_type = str(data_type or "custom").strip() or "custom"
        self.output_label = str(category_name or "项目资料").strip() or "项目资料"
        self.extra_rules = (
            "每条资料至少包含：name、description、details、tags。\n"
            "name 必须是可在资料库列表中显示的条目名；description 是一句话摘要；"
            "details 保存更完整的设定、用途、约束或修改说明；tags 是字符串数组。\n"
            "如果用户表达的是修改/更新，应在 description 或 details 中体现更新后的最终版本。"
        )
        super().__init__(name="ProjectDataBuilder")

    def _build_prompt(self, input_data: Dict[str, Any]) -> str:
        existing_rows = input_data.get("existing_rows")
        outline_rows = input_data.get("outline_rows")
        return (
            f"## 当前任务\n生成或更新资料库「{self.output_label}」中的条目\n\n"
            f"## 资料库键\n{self.data_type}\n\n"
            f"## 用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 最近讨论摘要\n{str(input_data.get('recent_discussion') or '').strip() or '无'}\n\n"
            f"## 世界观摘要\n{str(input_data.get('world_summary') or '').strip() or '无'}\n\n"
            f"## 已有同类资料\n{json.dumps(existing_rows, ensure_ascii=False, indent=2) if isinstance(existing_rows, list) else '[]'}\n\n"
            f"## 可参考章节大纲\n{json.dumps(outline_rows, ensure_ascii=False, indent=2) if isinstance(outline_rows, list) else '[]'}\n\n"
            "请只输出 JSON：{\"rows\": [...]}"
        )

    def _build_fallback_rows(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        user_request = str(input_data.get("user_request") or "").strip()
        if user_request:
            return self._normalize_rows([
                {
                    "name": self.output_label,
                    "description": user_request[:160],
                    "details": user_request,
                    "tags": [self.output_label],
                }
            ])
        return super()._build_fallback_rows(input_data)

    def _normalize_rows(self, rows: Any) -> List[Dict[str, Any]]:
        normalized = super()._normalize_rows(rows)
        for row in normalized:
            row.setdefault("details", row.get("description", ""))
            tags = row.get("tags")
            if isinstance(tags, str):
                row["tags"] = [item.strip() for item in re.split(r"[,，\n]+", tags) if item.strip()]
            elif not isinstance(tags, list):
                row["tags"] = []
        return normalized
