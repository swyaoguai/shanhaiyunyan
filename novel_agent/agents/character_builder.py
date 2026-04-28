"""
LLM 驱动的角色构建 Agent
负责基于当前请求、最近讨论摘要、世界观和项目信息生成结构化角色卡草稿。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import AgentCapability, BaseAgent
from .structured_output import StructuredOutputValidator


class CharacterBuilderAgent(BaseAgent):
    """真正由大模型驱动的角色卡生成 Agent。"""

    PLACEHOLDER_NAMES = {
        "主角", "男主", "女主", "角色", "人物", "配角", "反派", "角色1", "人物1",
    }

    REQUIRED_TOP_FIELDS = ["status", "characters", "missing_info", "confidence"]

    def __init__(self):
        super().__init__(
            name="CharacterBuilder",
            prompt_file=None,
        )

    def _get_default_prompt(self) -> str:
        return (
            "你是专业小说策划中的 CharacterBuilder，专门把零散讨论整理成可用的角色卡草稿。\n"
            "你的职责不是写散文说明，而是输出严格可机读的 JSON。\n"
            "\n"
            "核心规则：\n"
            "1. 只能输出 JSON，不能输出 Markdown、解释、前后缀。\n"
            "2. 如果信息不足，不得用“主角/男主/女主/角色”等占位名敷衍生成。\n"
            "3. 若关键信息不足，应返回 status='missing_info'，并列出 missing_info。\n"
            "4. 角色卡以“草稿”形式生成，不默认表示已保存。\n"
            "5. 优先吸收 recent_discussion、collected_info、world_summary 中已经明确给出的事实。\n"
            "6. 不要发明与现有讨论冲突的设定；不确定的内容宁可留空或写入 notes。\n"
            "7. 输出中的 confidence 必须是 0~1 的数字。\n"
            "\n"
            "输出格式必须为：\n"
            "{\n"
            "  \"status\": \"ok\" | \"missing_info\",\n"
            "  \"confidence\": 0.0,\n"
            "  \"missing_info\": [],\n"
            "  \"characters\": [\n"
            "    {\n"
            "      \"name\": \"\",\n"
            "      \"role\": \"\",\n"
            "      \"identity\": \"\",\n"
            "      \"description\": \"\",\n"
            "      \"personality\": [],\n"
            "      \"goals\": [],\n"
            "      \"relationships\": {},\n"
            "      \"notes\": \"\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["character_planning", "story_planning"],
            accept_task_types=["build_characters"],
            required_inputs=["protagonist"],
            produced_outputs=["characters", "missing_info", "confidence"],
            priority=90,
            max_concurrency=1,
            metadata={
                "stage": "planning",
                "agent_class": self.__class__.__name__,
            },
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

    @classmethod
    def _count_effective_fields(cls, payload: Dict[str, Any]) -> int:
        keys = ["name", "role", "identity", "description", "personality", "goals", "relationships", "notes"]
        total = 0
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                total += 1
            elif isinstance(value, list) and value:
                total += 1
            elif isinstance(value, dict) and value:
                total += 1
        return total

    @classmethod
    def _normalize_character(cls, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        name = str(raw.get("name") or "").strip()
        role = str(raw.get("role") or "").strip()
        description = str(raw.get("description") or "").strip()
        identity = str(raw.get("identity") or raw.get("occupation") or "").strip()
        personality = raw.get("personality")
        goals = raw.get("goals")
        relationships = raw.get("relationships")
        notes = str(raw.get("notes") or raw.get("background") or "").strip()

        normalized = {
            "name": name,
            "role": role or "角色",
            "identity": identity,
            "occupation": identity,
            "description": description,
            "personality": personality if isinstance(personality, list) else [str(personality).strip()] if str(personality or "").strip() else [],
            "goals": goals if isinstance(goals, list) else [str(goals).strip()] if str(goals or "").strip() else [],
            "relationships": relationships if isinstance(relationships, dict) else {},
            "notes": notes,
        }
        return normalized

    @classmethod
    def _validate_payload(cls, payload: Dict[str, Any]) -> Tuple[bool, List[str], List[Dict[str, Any]], str]:
        raw_characters = payload.get("characters")
        if not isinstance(raw_characters, list):
            return False, ["characters 必须是数组"], [], "角色生成结果格式错误，未返回角色数组。"

        normalized_characters: List[Dict[str, Any]] = []
        issues: List[str] = []
        for raw_char in raw_characters:
            character = cls._normalize_character(raw_char)
            if not character:
                issues.append("存在非对象角色项")
                continue

            name = str(character.get("name") or "").strip()
            description = str(character.get("description") or "").strip()
            if not name:
                issues.append("角色缺少 name")
                continue
            if name in cls.PLACEHOLDER_NAMES:
                issues.append(f"角色名 {name} 为占位名")
                continue
            if len(description) < 6:
                issues.append(f"角色 {name} 的 description 过短")
                continue
            if cls._count_effective_fields(character) < 4:
                issues.append(f"角色 {name} 的有效字段过少")
                continue
            normalized_characters.append(character)

        if issues or not normalized_characters:
            message = "角色卡草稿质量不足，暂不保存：" + "；".join(issues[:4]) if issues else "角色卡草稿为空，暂不保存。"
            return False, issues or ["未生成有效角色卡"], normalized_characters, message
        return True, [], normalized_characters, ""

    @staticmethod
    def _build_user_prompt(input_data: Dict[str, Any]) -> str:
        request_mode = str(input_data.get("request_mode") or "draft").strip() or "draft"
        return (
            "请基于以下信息生成角色卡草稿：\n\n"
            f"## 当前请求模式\n{request_mode}\n\n"
            f"## 当前用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 角色需求摘要\n{str(input_data.get('character_request') or '').strip() or '无'}\n\n"
            f"## 角色类型提示\n{str(input_data.get('character_role') or '').strip() or '未指定'}\n\n"
            f"## 已识别姓名提示\n{str(input_data.get('character_name') or '').strip() or '未识别'}\n\n"
            f"## 最近讨论摘要\n{str(input_data.get('recent_discussion') or '').strip() or '无'}\n\n"
            f"## 当前 collected_info\n"
            f"- novel_type: {str(input_data.get('novel_type') or '').strip() or '未指定'}\n"
            f"- theme: {str(input_data.get('theme') or '').strip() or '未指定'}\n"
            f"- protagonist: {str(input_data.get('protagonist') or '').strip() or '未指定'}\n"
            f"- plot_idea: {str(input_data.get('plot_idea') or '').strip() or '未指定'}\n\n"
            f"## 世界观摘要\n{str(input_data.get('world_summary') or '').strip() or '无'}\n\n"
            f"## 已有角色摘要\n{str(input_data.get('existing_characters_summary') or '').strip() or '无'}\n\n"
            "要求：\n"
            "1. 只生成当前请求最相关的 1~2 个角色卡草稿。\n"
            "2. 若信息不足以生成可靠角色卡，返回 status='missing_info'，并明确列出缺什么。\n"
            "3. 关系字段使用对象映射，如 {\"角色A\": \"师徒\"}。\n"
            "4. 不要输出任何 JSON 以外的内容。\n"
        )

    async def _generate_once(self, input_data: Dict[str, Any], feedback: str = "") -> Tuple[Optional[Dict[str, Any]], str, List[str]]:
        user_prompt = self._build_user_prompt(input_data)
        if feedback:
            user_prompt += f"\n上一次输出存在以下问题，请严格修复后重写 JSON：\n{feedback}\n"

        response = await self.call_llm(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2200,
        )

        json_text = self._extract_json_text(response)
        validation = StructuredOutputValidator.validate_json_output(
            json_text,
            required_fields=self.REQUIRED_TOP_FIELDS,
        )
        if not validation.get("is_valid"):
            return None, response, validation.get("violations", []) or validation.get("missing_fields", [])

        try:
            payload = json.loads(json_text)
        except Exception as exc:
            return None, response, [f"JSON 解析失败: {exc}"]

        if not isinstance(payload, dict):
            return None, response, ["顶层 JSON 必须为对象"]
        return payload, response, []

    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = dict(input_data or {})
        if not str(request.get("world_summary") or "").strip() and isinstance(context, dict):
            world_payload = context.get("world")
            if isinstance(world_payload, dict):
                world_name = str(world_payload.get("name") or world_payload.get("world_name") or "").strip()
                world_type = str(world_payload.get("world_type") or "").strip()
                request["world_summary"] = "\n".join(
                    part for part in [f"世界名：{world_name}" if world_name else "", f"类型：{world_type}" if world_type else ""]
                    if part
                )
        if not str(request.get("character_request") or "").strip():
            request["character_request"] = str(request.get("protagonist") or request.get("plot_idea") or request.get("user_request") or "").strip()
        minimum_signal = any(
            str(request.get(key) or "").strip()
            for key in ("character_request", "recent_discussion", "protagonist", "plot_idea", "world_summary")
        )
        if not minimum_signal:
            return {
                "success": False,
                "agent": self.name,
                "characters": [],
                "missing_info": ["缺少可用于生成角色卡的讨论内容或创作信息"],
                "response_message": "当前信息不足，无法生成角色卡草稿。请先描述角色或继续讨论设定。",
            }

        response = ""
        payload: Optional[Dict[str, Any]] = None
        feedback = ""
        issues: List[str] = []
        for _ in range(2):
            payload, response, issues = await self._generate_once(request, feedback=feedback)
            if payload is not None:
                break
            feedback = "；".join(str(item) for item in issues if str(item).strip()) or "请输出合法且完整的 JSON"

        if payload is None:
            return {
                "success": False,
                "agent": self.name,
                "characters": [],
                "missing_info": [],
                "response_message": "角色卡生成失败，未能输出合法 JSON。",
                "raw_response": response,
                "validation_issues": issues,
            }

        status = str(payload.get("status") or "ok").strip() or "ok"
        missing_info = payload.get("missing_info")
        missing_info = missing_info if isinstance(missing_info, list) else []
        confidence = payload.get("confidence")
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0

        is_valid, business_issues, normalized_characters, message = self._validate_payload(payload)
        if status == "missing_info":
            return {
                "success": False,
                "agent": self.name,
                "characters": [],
                "missing_info": missing_info or business_issues,
                "confidence": confidence_value,
                "response_message": "当前信息不足，先补充这些信息后再生成角色卡：" + "、".join((missing_info or business_issues)[:5]),
                "raw_response": response,
            }

        if not is_valid:
            return {
                "success": False,
                "agent": self.name,
                "characters": normalized_characters,
                "missing_info": business_issues,
                "confidence": confidence_value,
                "response_message": message,
                "raw_response": response,
                "validation_issues": business_issues,
            }

        return {
            "success": True,
            "agent": self.name,
            "status": status,
            "confidence": confidence_value,
            "characters": normalized_characters,
            "missing_info": missing_info,
            "raw_response": response,
        }
