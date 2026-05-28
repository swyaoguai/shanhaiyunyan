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
    minimum_response_chars = 0

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
        from .enhanced_prompts import AGENT_COORDINATION_PROTOCOL, STRUCTURED_DATA_AGENT_PROTOCOL

        return (
            f"你是专业的{self.output_label}构建器。\n"
            "你只负责把输入的创作信息整理成结构化 JSON。\n"
            f"{AGENT_COORDINATION_PROTOCOL}\n"
            f"{STRUCTURED_DATA_AGENT_PROTOCOL}\n"
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
        outline_overview_rows = input_data.get("outline_overview_rows")
        eventlines = input_data.get("eventlines")
        custom_prompt = self._render_custom_task_prompt(
            f"build_{self.output_key}",
            user_request=str(input_data.get("user_request") or "").strip() or "无",
            recent_discussion=str(input_data.get("recent_discussion") or "").strip() or "无",
            world_summary=str(input_data.get("world_summary") or "").strip() or "无",
            characters_json=json.dumps(input_data.get("characters"), ensure_ascii=False, indent=2) if isinstance(input_data.get("characters"), list) else str(input_data.get("characters") or "无"),
            outline_overview_json=json.dumps(outline_overview_rows, ensure_ascii=False, indent=2) if isinstance(outline_overview_rows, list) else "[]",
            outline_rows_json=json.dumps(outline_rows, ensure_ascii=False, indent=2) if isinstance(outline_rows, list) else "[]",
            eventlines_json=json.dumps(eventlines, ensure_ascii=False, indent=2) if isinstance(eventlines, list) else "[]",
        )
        if custom_prompt:
            return custom_prompt

        return (
            f"## 当前任务\n生成{self.output_label}\n\n"
            f"## 用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 最近讨论摘要\n{str(input_data.get('recent_discussion') or '').strip() or '无'}\n\n"
            f"## 世界观摘要\n{str(input_data.get('world_summary') or '').strip() or '无'}\n\n"
            f"## 角色资料\n{json.dumps(input_data.get('characters'), ensure_ascii=False, indent=2) if isinstance(input_data.get('characters'), list) else str(input_data.get('characters') or '无')}\n\n"
            f"## 全书/分卷概览（只作一致性约束，不要当成逐章清单复制）\n{json.dumps(outline_overview_rows, ensure_ascii=False, indent=2) if isinstance(outline_overview_rows, list) else '[]'}\n\n"
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
        min_chars = max(0, int(getattr(self, "minimum_response_chars", 0) or 0))
        if min_chars and len(response_text.strip()) < min_chars:
            return None, response_text, [f"LLM 返回内容过短（{len(response_text.strip())} 字符，至少需要 {min_chars} 字符）"]

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
    minimum_response_chars = 100
    batch_size = 5
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
        result = await self._execute_in_batches(input_data, context=context) or await super().execute(input_data, context=context)
        rows = result.get("rows")
        if result.get("success") and isinstance(rows, list):
            consistent_rows, consistency_issues = self._replace_inconsistent_character_rows(rows, input_data)
            completed_rows = self._ensure_chapter_coverage(consistent_rows, input_data)
            if consistency_issues:
                result["character_consistency_fallback_used"] = True
                result["fallback_used"] = True
                result["validation_issues"] = [
                    *(result.get("validation_issues") or []),
                    *consistency_issues,
                ]
                result["response_message"] = (
                    result.get("response_message")
                    or "章纲生成器输出疑似替换已确认角色，已根据大纲种子生成一致性兜底章纲。"
                )
            if len(completed_rows) > len(rows):
                result["coverage_fallback_used"] = True
                result["response_message"] = (
                    result.get("response_message")
                    or "章纲生成器只返回了部分章节，已根据大纲补齐缺失章纲。"
                )
            outline_issues = self._check_chapter_outline_consistency(completed_rows, input_data)
            if outline_issues:
                result["validation_issues"] = [
                    *(result.get("validation_issues") or []),
                    *outline_issues,
                ]
                logger.warning(
                    "[%s] 章纲一致性检查发现问题：%s",
                    self.name, "; ".join(outline_issues),
                )
            result["rows"] = self._enrich_rows_with_eventlines(completed_rows, input_data)
        return result

    @staticmethod
    def _is_outline_overview_row(row: Dict[str, Any]) -> bool:
        title = str(row.get("title") or row.get("name") or "").strip()
        return (
            title == "主线大纲"
            or bool(row.get("global_outline"))
            or bool(row.get("volume_plan"))
            or bool(row.get("volumes"))
        )

    def _rows_for_chapter_batch(
        self,
        input_data: Dict[str, Any],
        chapter_numbers: List[int],
    ) -> List[Dict[str, Any]]:
        return [
            self._outline_source_for_chapter(input_data, chapter_number)
            for chapter_number in chapter_numbers
        ]

    async def _execute_in_batches(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        expected_numbers = self._expected_chapter_numbers([], input_data)
        batch_size = max(1, int(getattr(self, "batch_size", 5) or 5))
        if len(expected_numbers) <= batch_size:
            return None

        all_rows: List[Dict[str, Any]] = []
        validation_issues: List[str] = []
        raw_responses: List[str] = []
        fallback_used = False
        coverage_fallback_used = False
        base_request = str(input_data.get("user_request") or "生成章纲").strip()

        for start in range(0, len(expected_numbers), batch_size):
            batch_numbers = expected_numbers[start:start + batch_size]
            if not batch_numbers:
                continue
            batch_input = dict(input_data)
            batch_input["outline_rows"] = self._rows_for_chapter_batch(input_data, batch_numbers)
            batch_input["user_request"] = (
                f"{base_request}\n"
                f"本批只生成第{batch_numbers[0]}章到第{batch_numbers[-1]}章，"
                "不要输出本批范围之外的章节。"
                "必须严格围绕本批“大纲资料”中每条 chapter_number/title/summary 扩写；"
                "不得重启剧情、不得新增另一套第1章开局、不得改名替换世界观或角色。"
            )
            batch_result = await _ProjectDataBuilderAgent.execute(self, batch_input, context=context)
            rows = batch_result.get("rows") if isinstance(batch_result, dict) else []
            if not batch_result.get("success") or not isinstance(rows, list) or not rows:
                return None

            batch_number_set = set(batch_numbers)
            filtered_rows = [
                row for index, row in enumerate(rows, start=1)
                if isinstance(row, dict)
                and (
                    self._coerce_chapter_number(
                        row.get("chapter_number"),
                        batch_numbers[min(index - 1, len(batch_numbers) - 1)],
                    )
                    in batch_number_set
                )
            ]
            if filtered_rows:
                filtered_rows, consistency_issues = self._replace_inconsistent_character_rows(filtered_rows, batch_input)
                if consistency_issues:
                    fallback_used = True
                    validation_issues.extend(consistency_issues)
            if filtered_rows:
                all_rows.extend(filtered_rows)
            else:
                fallback_used = True
                issue = (
                    f"LLM 返回的章节号不在本批范围第{batch_numbers[0]}-"
                    f"{batch_numbers[-1]}章内，已丢弃越界行并用本批大纲兜底。"
                )
                validation_issues.append(issue)
                logger.warning("[%s] %s", self.name, issue)
                all_rows.extend(self._build_fallback_rows(batch_input))
            fallback_used = fallback_used or bool(batch_result.get("fallback_used"))
            validation_issues.extend(str(item) for item in batch_result.get("validation_issues") or [] if str(item).strip())
            raw_response = str(batch_result.get("raw_response") or "").strip()
            if raw_response:
                raw_responses.append(raw_response)

        normalized_rows = self._normalize_rows(all_rows)
        if not normalized_rows:
            return None
        normalized_rows, consistency_issues = self._replace_inconsistent_character_rows(normalized_rows, input_data)
        if consistency_issues:
            fallback_used = True
            validation_issues.extend(consistency_issues)
        completed_rows = self._ensure_chapter_coverage(normalized_rows, input_data)
        coverage_fallback_used = len(completed_rows) > len(normalized_rows)
        response_message = ""
        if fallback_used or coverage_fallback_used:
            response_message = "章纲生成采用分批执行，部分章节由本地兜底补齐，请审阅后再继续正文。"

        return {
            "success": True,
            "agent": self.name,
            "rows": self._enrich_rows_with_eventlines(completed_rows, input_data),
            "fallback_used": fallback_used,
            "coverage_fallback_used": coverage_fallback_used,
            "response_message": response_message,
            "validation_issues": validation_issues,
            "raw_response": "\n\n".join(raw_responses),
            "batch_count": (len(expected_numbers) + batch_size - 1) // batch_size,
        }

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
        if (
            total_chapters > len(outline_rows)
            and len(outline_rows) <= 1
            and self._is_outline_overview_row(
                outline_rows[0] if outline_rows and isinstance(outline_rows[0], dict) else {}
            )
        ):
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

    @staticmethod
    def _canonical_character_names(input_data: Dict[str, Any]) -> List[str]:
        names: List[str] = []

        def add_name(value: Any) -> None:
            name = str(value or "").strip()
            if not name or name in names:
                return
            if name in {"主角", "男主", "女主", "角色", "人物", "配角", "反派"}:
                return
            names.append(name)

        for key in ("locked_character_names", "canonical_character_names"):
            value = input_data.get(key)
            if isinstance(value, list):
                for item in value:
                    add_name(item)
            elif isinstance(value, str):
                for item in re.split(r"[,，、/\s]+", value):
                    add_name(item)

        characters = input_data.get("characters")
        if isinstance(characters, dict) and isinstance(characters.get("characters"), list):
            characters = characters.get("characters")
        if isinstance(characters, dict):
            for key, value in characters.items():
                if isinstance(value, dict):
                    add_name(value.get("name") or key)
                else:
                    add_name(key)
        elif isinstance(characters, list):
            for item in characters:
                if isinstance(item, dict):
                    add_name(item.get("name"))

        return names

    @staticmethod
    def _chapter_setting_text(row: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("name", "title", "description", "chapter_goal", "key_event", "ending_hook"):
            value = row.get(key)
            if isinstance(value, (dict, list)):
                parts.append(json.dumps(value, ensure_ascii=False))
            elif value not in (None, ""):
                parts.append(str(value))
        return "\n".join(parts)

    @staticmethod
    def _extract_referenced_person_names(text: str) -> List[str]:
        try:
            from .character_builder import CharacterBuilderAgent
            looks_like_name = CharacterBuilderAgent._looks_like_chinese_person_name
        except Exception:
            looks_like_name = lambda value: bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", str(value or "").strip()))

        names: List[str] = []

        def add_name(value: Any) -> None:
            name = str(value or "").strip()
            if name and name not in names and looks_like_name(name):
                names.append(name)

        patterns = (
            r"(?:女主|男主|主角|庶女|夫人|妻子|丈夫|将军|姑娘|世子|王爷)([\u4e00-\u9fff]{2,4})",
            r"([\u4e00-\u9fff]{2,4})(?:与|和|同)([\u4e00-\u9fff]{2,4})(?=在|因|从|于|一同|共同|新婚|回门|暗生|并肩|相守|，|。|、|$)",
            r"([\u4e00-\u9fff]{2,4})(?=被迫|替嫁|嫁入|嫁给|回门|新婚|入府|发现|暗生|携手|并肩)",
            r"(?:嫁给|嫁入|娶|护住|守护|试探)(?:冷面将军|镇北将军|世子|王爷|将军)?([\u4e00-\u9fff]{2,4})",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                for group in match.groups():
                    add_name(group)
        return names

    def _row_replaces_locked_characters(
        self,
        row: Dict[str, Any],
        locked_names: List[str],
    ) -> tuple[bool, List[str]]:
        text = self._chapter_setting_text(row)
        if not text or not locked_names:
            return False, []
        if any(name and name in text for name in locked_names):
            return False, []

        referenced_names = [
            name for name in self._extract_referenced_person_names(text)
            if name not in locked_names
        ]
        if len(referenced_names) >= 2:
            return True, referenced_names
        if referenced_names and re.search(r"(女主|男主|主角|妻子|丈夫|夫妇|夫妻|新婚|婚约)", text):
            return True, referenced_names
        return False, referenced_names

    def _replace_inconsistent_character_rows(
        self,
        rows: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        locked_names = self._canonical_character_names(input_data)
        if len(locked_names) < 2:
            return rows, []

        corrected: List[Dict[str, Any]] = []
        issues: List[str] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            chapter_number = self._coerce_chapter_number(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            should_replace, referenced_names = self._row_replaces_locked_characters(row, locked_names)
            if should_replace:
                corrected.append(
                    self._build_fallback_row(
                        self._outline_source_for_chapter(input_data, chapter_number),
                        chapter_number,
                    )
                )
                issues.append(
                    f"第{chapter_number}章疑似替换已确认角色："
                    f"{'、'.join(referenced_names)}；已按大纲种子兜底。"
                )
                continue
            corrected.append(row)
        return corrected, issues

    def _check_chapter_outline_consistency(
        self,
        rows: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        if not rows:
            return issues

        titles: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("name") or row.get("title") or "").strip()
            if title and title in titles:
                issues.append(f"章纲存在重复标题「{title}」")
            elif title:
                titles.append(title)

        locked_names = self._canonical_character_names(input_data)
        if locked_names:
            combined_text = "\n".join(self._chapter_setting_text(r) for r in rows if isinstance(r, dict))
            if not any(name in combined_text for name in locked_names):
                issues.append(
                    f"所有章纲均未提及任何已确认角色（{', '.join(locked_names[:5])}）"
                )

        outline_rows = input_data.get("outline_rows")
        if isinstance(outline_rows, list):
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or index >= len(outline_rows):
                    continue
                outline_row = outline_rows[index]
                if not isinstance(outline_row, dict):
                    continue
                outline_summary = str(outline_row.get("summary") or outline_row.get("description") or "").strip()
                if len(outline_summary) < 10:
                    continue
                keywords = [
                    w for w in re.split(r"[，。、；\s]+", outline_summary)
                    if len(w) >= 2
                ][:8]
                if not keywords:
                    continue
                setting_text = self._chapter_setting_text(row)
                if not any(kw in setting_text for kw in keywords):
                    chapter_num = self._coerce_chapter_number(
                        row.get("chapter_number") or row.get("chapter"),
                        index + 1,
                    )
                    issues.append(
                        f"第{chapter_num}章章纲与大纲关键词无重叠，可能偏离大纲"
                    )

        return issues

    def _expected_chapter_numbers(self, rows: List[Dict[str, Any]], input_data: Dict[str, Any]) -> List[int]:
        try:
            total_chapters = max(0, int(input_data.get("total_chapters") or 0))
        except (TypeError, ValueError):
            total_chapters = 0
        if total_chapters:
            return list(range(1, total_chapters + 1))

        outline_rows = input_data.get("outline_rows")
        if isinstance(outline_rows, list) and outline_rows:
            chapter_numbers = [
                self._coerce_chapter_number(
                    row.get("chapter_number") or row.get("chapter") or row.get("number"),
                    index,
                )
                for index, row in enumerate(outline_rows, start=1)
                if isinstance(row, dict)
            ]
            if chapter_numbers:
                return sorted({number for number in chapter_numbers if number > 0})

        row_numbers = [
            self._coerce_chapter_number(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            for index, row in enumerate(rows, start=1)
            if isinstance(row, dict)
        ]
        return sorted({number for number in row_numbers if number > 0})

    def _outline_source_for_chapter(
        self,
        input_data: Dict[str, Any],
        chapter_number: int,
    ) -> Dict[str, Any]:
        outline_rows = input_data.get("outline_rows")
        if not isinstance(outline_rows, list) or not outline_rows:
            return {
                "chapter_number": chapter_number,
                "title": f"第{chapter_number}章",
                "summary": f"依据全书大纲推进第{chapter_number}章剧情",
            }

        for index, row in enumerate(outline_rows, start=1):
            if not isinstance(row, dict):
                continue
            number = self._coerce_chapter_number(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            if number == chapter_number:
                return dict(row)

        if len(outline_rows) == 1 and isinstance(outline_rows[0], dict):
            source_row = dict(outline_rows[0])
        elif 0 < chapter_number <= len(outline_rows) and isinstance(outline_rows[chapter_number - 1], dict):
            source_row = dict(outline_rows[chapter_number - 1])
        else:
            source_row = {}

        return {
            **source_row,
            "chapter_number": chapter_number,
            "title": source_row.get("title") or source_row.get("name") or f"第{chapter_number}章",
            "summary": self._stringify_outline_field(
                source_row,
                "summary",
                "global_outline",
                "story_synopsis",
                "volume_plan",
                "description",
                "content",
            ) or f"依据全书大纲推进第{chapter_number}章剧情",
        }

    def _ensure_chapter_coverage(
        self,
        rows: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        normalized: Dict[int, Dict[str, Any]] = {}
        duplicate_numbers: List[int] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            copied = dict(row)
            chapter_number = self._coerce_chapter_number(
                copied.get("chapter_number") or copied.get("chapter") or copied.get("number"),
                index,
            )
            copied["chapter_number"] = chapter_number
            copied["name"] = str(copied.get("name") or copied.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
            copied["description"] = str(
                copied.get("description")
                or copied.get("chapter_goal")
                or copied.get("key_event")
                or f"{copied['name']} 待根据章节大纲细化"
            ).strip()
            if chapter_number in normalized:
                duplicate_numbers.append(chapter_number)
                existing = normalized[chapter_number]
                existing_text = " ".join(
                    str(existing.get(key) or "")
                    for key in ("description", "chapter_goal", "key_event", "ending_hook")
                )
                copied_text = " ".join(
                    str(copied.get(key) or "")
                    for key in ("description", "chapter_goal", "key_event", "ending_hook")
                )
                if len(copied_text.strip()) > len(existing_text.strip()):
                    normalized[chapter_number] = copied
                continue
            normalized[chapter_number] = copied

        if duplicate_numbers:
            logger.warning(
                "[%s] Dropped duplicate chapter setting rows for chapters: %s",
                self.name,
                sorted(set(duplicate_numbers)),
            )

        expected_numbers = self._expected_chapter_numbers(list(normalized.values()), input_data)
        for chapter_number in expected_numbers:
            if chapter_number in normalized:
                continue
            normalized[chapter_number] = self._build_fallback_row(
                self._outline_source_for_chapter(input_data, chapter_number),
                chapter_number,
            )

        return [
            normalized[number]
            for number in sorted(normalized)
            if number > 0
        ]

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
