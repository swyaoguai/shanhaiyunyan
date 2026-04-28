"""
LLM 驱动的项目资料构建 Agents
用于生成事件线、细纲设定、章纲设定等结构化项目数据。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .structured_output import StructuredOutputValidator


class _ProjectDataBuilderAgent(BaseAgent):
    """项目资料构建 Agent 基类。"""

    output_label = "项目资料"
    output_key = "rows"
    extra_rules = ""

    def __init__(self, name: str):
        super().__init__(name=name, prompt_file=None)

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
        return (
            f"## 当前任务\n生成{self.output_label}\n\n"
            f"## 用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 最近讨论摘要\n{str(input_data.get('recent_discussion') or '').strip() or '无'}\n\n"
            f"## 世界观摘要\n{str(input_data.get('world_summary') or '').strip() or '无'}\n\n"
            f"## 章节大纲\n{json.dumps(outline_rows, ensure_ascii=False, indent=2) if isinstance(outline_rows, list) else '[]'}\n\n"
            f"请输出 JSON，对象格式为：{{\"{self.output_key}\": [...]}}"
        )

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

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt = self._build_prompt(dict(input_data or {}))
        response = await self.call_llm(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=2400,
        )
        json_text = self._extract_json_text(response)
        validation = StructuredOutputValidator.validate_json_output(json_text, required_fields=[self.output_key])
        if not validation.get("is_valid"):
            return {
                "success": False,
                "agent": self.name,
                "rows": [],
                "response_message": f"{self.output_label}生成失败，未输出合法 JSON。",
                "validation_issues": validation.get("violations", []),
                "raw_response": response,
            }

        try:
            payload = json.loads(json_text)
        except Exception as exc:
            return {
                "success": False,
                "agent": self.name,
                "rows": [],
                "response_message": f"{self.output_label}生成失败，JSON 解析异常：{exc}",
                "raw_response": response,
            }

        rows = self._normalize_rows(payload.get(self.output_key))
        if not rows:
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


class DetailOutlineBuilderAgent(_ProjectDataBuilderAgent):
    output_label = "细纲设定"
    output_key = "detail_settings"
    extra_rules = (
        "每条细纲至少包含：name、description、chapter_number、scene_goal、conflict、notes。\n"
        "细纲应体现每章的场景目标与冲突，而不是仅复述标题。"
    )

    def __init__(self):
        super().__init__(name="DetailOutlineBuilder")


class ChapterSettingBuilderAgent(_ProjectDataBuilderAgent):
    output_label = "章纲设定"
    output_key = "chapter_settings"
    extra_rules = (
        "每条章纲至少包含：name、description、chapter_number、chapter_goal、key_event、ending_hook。\n"
        "章纲应体现可执行写作目标、关键事件和章末钩子。"
    )

    def __init__(self):
        super().__init__(name="ChapterSettingBuilder")

