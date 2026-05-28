"""
LLM 驱动的角色构建 Agent
负责基于当前请求、最近讨论摘要、世界观和项目信息生成结构化角色卡草稿。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import AgentCapability, BaseAgent
from .structured_output import StructuredOutputValidator


class CharacterBuilderAgent(BaseAgent):
    """真正由大模型驱动的角色卡生成 Agent。"""

    PLACEHOLDER_NAMES = {
        "主角", "男主", "女主", "角色", "人物", "配角", "反派", "角色1", "人物1",
    }
    _COMMON_CHINESE_SURNAMES = set(
        "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹姚邵湛汪祁毛狄米贝明臧成戴宋庞熊纪舒屈项祝董梁杜阮蓝闵季贾路江童颜郭梅盛林钟徐邱骆高夏蔡田胡凌霍虞万支柯管卢莫房解应宗丁宣邓杭洪包左石崔吉龚程邢裴陆荣翁荀惠曲封靳井段焦侯全班仰秋仲伊宫宁仇甘厉祖武符刘景詹龙叶司韶黎薄白蒲从索卓蔺池乔翟谭姬申冉桂牛寿边燕尚农温庄柴阎慕连习鱼容向古易廖终居步耿满弘匡文寇广东欧利蔚隆师巩聂晁勾融冷辛阚简饶曾沙养鞠丰关查荆游权盖益桓"
    )
    _NON_NAME_SUFFIXES = {
        "府", "家", "党", "城", "朝", "国", "帝", "妃", "军", "将", "门", "线",
        "章", "卷", "夜", "宴", "街", "池", "庙", "市", "集", "相", "女",
        "郎", "人", "们", "被",
    }

    REQUIRED_TOP_FIELDS = ["status", "characters", "missing_info", "confidence"]

    def __init__(self):
        super().__init__(
            name="CharacterBuilder",
            prompt_file=None,
        )

    def _get_default_prompt(self) -> str:
        from .enhanced_prompts import AGENT_COORDINATION_PROTOCOL, STRUCTURED_DATA_AGENT_PROTOCOL

        return (
            "你是专业小说策划中的 CharacterBuilder，专门把零散讨论整理成可用的角色卡草稿。\n"
            "你的职责不是写散文说明，而是输出严格可机读的 JSON。\n"
            "\n"
            f"{AGENT_COORDINATION_PROTOCOL}\n"
            f"{STRUCTURED_DATA_AGENT_PROTOCOL}\n"
            "\n"
            "核心规则：\n"
            "1. 只能输出 JSON，不能输出 Markdown、解释、前后缀。\n"
            "2. 如果信息不足，不得用“主角/男主/女主/角色”等占位名敷衍生成。\n"
            "3. 若关键信息不足，应返回 status='missing_info'，并列出 missing_info。\n"
            "4. 角色卡以“草稿”形式生成，不默认表示已保存。\n"
            "5. 优先吸收 recent_discussion、collected_info、world_summary 中已经明确给出的事实。\n"
            "6. 不要发明与现有讨论冲突的设定；不确定的内容宁可留空或写入 notes。\n"
            "7. 如果当前请求包含“那、这个、刚才、按上面”等上下文指代，必须以 discussion_context / recent_discussion 为准。\n"
            "8. 不得擅自更换主角名、题材、核心能力、门派/世界背景；信息不足则 missing_info，不要随机补成无关设定。\n"
            "9. 输出中的 confidence 必须是 0~1 的数字。\n"
            "10. 如果请求模式是 autonomous_draft，或输入声明 ai_autonomy_requested=true，表示用户已经授权助手自主安排未指定内容；"
            "此时姓名、身份、关系、动机等空白不是缺失信息，必须在既有题材与讨论方向内主动创作可用角色卡。\n"
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
            required_inputs=[],
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
    def _validate_payload(
        cls,
        payload: Dict[str, Any],
        required_names: Optional[List[str]] = None,
    ) -> Tuple[bool, List[str], List[Dict[str, Any]], str]:
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

        locked_names = [
            str(name or "").strip()
            for name in (required_names or [])
            if str(name or "").strip()
        ]
        if locked_names:
            generated_names = {str(item.get("name") or "").strip() for item in normalized_characters}
            missing_locked_names = [name for name in locked_names if name not in generated_names]
            if missing_locked_names:
                issues.append("缺少已确认角色名：" + "、".join(missing_locked_names))

        if issues or not normalized_characters:
            message = "角色卡草稿质量不足，暂不保存：" + "；".join(issues[:4]) if issues else "角色卡草稿为空，暂不保存。"
            return False, issues or ["未生成有效角色卡"], normalized_characters, message
        return True, [], normalized_characters, ""

    @staticmethod
    def _check_character_world_consistency(
        characters: List[Dict[str, Any]],
        input_data: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        world = input_data.get("world")
        if not isinstance(world, dict) or not characters:
            return issues
        if isinstance(world.get("world"), dict):
            world = world["world"]

        world_terms: List[str] = []
        ps = world.get("power_system")
        if isinstance(ps, dict):
            ps_name = str(ps.get("name") or "").strip()
            if ps_name and len(ps_name) >= 2:
                world_terms.append(ps_name)
        factions = world.get("factions")
        if isinstance(factions, list):
            for f in factions:
                if isinstance(f, dict):
                    fn = str(f.get("name") or "").strip()
                    if fn and len(fn) >= 2:
                        world_terms.append(fn)
        geo = world.get("geography")
        if isinstance(geo, dict):
            for key in ("name", "capital", "continent"):
                gn = str(geo.get(key) or "").strip()
                if gn and len(gn) >= 2:
                    world_terms.append(gn)

        if len(world_terms) < 2:
            return issues

        for char in characters:
            if not isinstance(char, dict):
                continue
            name = str(char.get("name") or "").strip()
            text_parts: List[str] = []
            for key in ("background", "personality", "abilities", "description", "role"):
                value = char.get(key)
                if isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, (dict, list)):
                    text_parts.append(json.dumps(value, ensure_ascii=False))
            combined = "\n".join(text_parts)
            if combined and not any(term in combined for term in world_terms):
                issues.append(
                    f"角色「{name}」的背景描述未提及任何已设定世界元素"
                    f"（{', '.join(world_terms[:4])}）"
                )
        return issues

    @staticmethod
    def _stringify_for_prompt(value: Any, max_chars: int = 3000) -> str:
        if value in (None, "", [], {}):
            return ""
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            text = str(value or "")
        text = text.strip()
        return text[:max_chars]

    @classmethod
    def _build_world_summary(cls, world_payload: Any) -> str:
        if isinstance(world_payload, dict) and isinstance(world_payload.get("world"), dict):
            world_payload = world_payload.get("world")
        if not isinstance(world_payload, dict):
            return str(world_payload or "").strip()

        parts: List[str] = []
        for label, key in (
            ("世界名", "name"),
            ("世界名", "world_name"),
            ("类型", "world_type"),
            ("核心概念", "core_concept"),
            ("时间线", "timeline"),
        ):
            value = cls._stringify_for_prompt(world_payload.get(key), max_chars=1200)
            if value:
                parts.append(f"{label}：{value}")

        for label, key in (
            ("叙事硬约束", "narrative_constraints"),
            ("故事钩子", "story_hooks"),
            ("支线种子", "thread_seed_hooks"),
            ("世界规则", "rules"),
            ("势力", "factions"),
            ("地理/地点", "geography"),
        ):
            value = cls._stringify_for_prompt(world_payload.get(key), max_chars=1800)
            if value:
                parts.append(f"【{label}】\n{value}")

        return "\n".join(parts).strip()

    @classmethod
    def _looks_like_chinese_person_name(cls, name: str) -> bool:
        text = str(name or "").strip()
        if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
            return False
        if text in cls.PLACEHOLDER_NAMES:
            return False
        if text[0] not in cls._COMMON_CHINESE_SURNAMES:
            return False
        if text[-1] in cls._NON_NAME_SUFFIXES:
            return False
        if any(token in text for token in ("相国", "将军", "皇帝", "夫人", "嫡姐", "旧部", "二皇子")):
            return False
        return True

    @classmethod
    def _append_locked_name(cls, names: List[str], candidate: str, limit: int = 2) -> None:
        name = str(candidate or "").strip()
        if len(names) >= limit or name in names:
            return
        if cls._looks_like_chinese_person_name(name):
            names.append(name)

    @classmethod
    def _extract_main_names_from_text(cls, text: Any, limit: int = 2) -> List[str]:
        source = str(text or "")
        names: List[str] = []
        patterns = (
            r"(?:女主|庶女|夫人|妻子|姑娘)([\u4e00-\u9fff]{2,4}?)(?=被|嫁|与|和|，|。|、|$)",
            r"(?:男主|丈夫)([\u4e00-\u9fff]{2,4}?)(?=被|娶|与|和|，|。|、|$)",
            r"([\u4e00-\u9fff]{2,4}?)(?=被迫)",
            r"嫁给(?:冷面将军|镇北将军|战功赫赫的)?([\u4e00-\u9fff]{2,4}?)(?=，|。|、|$)",
            r"([\u4e00-\u9fff]{2,4}?)与([\u4e00-\u9fff]{2,4}?)(?=从|在|因|，|。|、|$)",
            r"([\u4e00-\u9fff]{2,4}?)和([\u4e00-\u9fff]{2,4}?)(?=从|在|因|，|。|、|$)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                for group in match.groups():
                    cls._append_locked_name(names, group, limit=limit)
                    if len(names) >= limit:
                        return names
        return names

    @classmethod
    def _extract_locked_character_names(
        cls,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        limit: int = 2,
    ) -> List[str]:
        data = dict(input_data or {})
        context_data = context if isinstance(context, dict) else {}
        names: List[str] = []

        for key in ("locked_character_names", "canonical_character_names"):
            value = data.get(key) or context_data.get(key)
            if isinstance(value, list):
                for item in value:
                    cls._append_locked_name(names, str(item), limit=limit)
            elif isinstance(value, str):
                for item in re.split(r"[,，、/\s]+", value):
                    cls._append_locked_name(names, item, limit=limit)

        for key in ("character_name", "protagonist"):
            value = str(data.get(key) or context_data.get(key) or "").strip()
            if value and value not in {"未指定", "无"}:
                for item in cls._extract_main_names_from_text(value, limit=limit):
                    cls._append_locked_name(names, item, limit=limit)
                cls._append_locked_name(names, value, limit=limit)

        world_payload = data.get("world") or context_data.get("world")
        if isinstance(world_payload, dict) and isinstance(world_payload.get("world"), dict):
            world_payload = world_payload.get("world")
        if isinstance(world_payload, dict):
            main_text_parts: List[str] = []
            for key in ("story_hooks", "core_concept", "thread_seed_hooks"):
                value = world_payload.get(key)
                if isinstance(value, list):
                    main_text_parts.extend(cls._stringify_for_prompt(item, max_chars=1000) for item in value)
                else:
                    main_text_parts.append(cls._stringify_for_prompt(value, max_chars=1000))
            for name in cls._extract_main_names_from_text("\n".join(main_text_parts), limit=limit):
                cls._append_locked_name(names, name, limit=limit)

        return names[:limit]

    def _build_user_prompt(self, input_data: Dict[str, Any]) -> str:
        request_mode = str(input_data.get("request_mode") or "draft").strip() or "draft"
        ai_autonomy_requested = bool(input_data.get("ai_autonomy_requested")) or request_mode == "autonomous_draft"
        autonomy_note = (
            "用户已明确表示未指定内容由AI自由发挥或助手安排；请你主动命名、设计身份、关系和人物弧线，"
            "不要因为姓名/身份/剧情细节未给出而返回 missing_info。"
            if ai_autonomy_requested
            else "未授权，缺少关键角色信息时应返回 missing_info。"
        )
        locked_names = input_data.get("locked_character_names")
        if isinstance(locked_names, list):
            locked_character_names_text = "、".join(str(name or "").strip() for name in locked_names if str(name or "").strip()) or "无"
        else:
            locked_character_names_text = CharacterBuilderAgent._stringify_for_prompt(locked_names, max_chars=500) or "无"
        custom_prompt = self._render_custom_task_prompt(
            "build_characters",
            request_mode=request_mode,
            ai_autonomy_note=autonomy_note,
            autonomous_brief=str(input_data.get("autonomous_brief") or "").strip() or "无",
            user_request=str(input_data.get("user_request") or "").strip() or "无",
            character_request=str(input_data.get("character_request") or "").strip() or "无",
            character_role=str(input_data.get("character_role") or "").strip() or "未指定",
            character_name=str(input_data.get("character_name") or "").strip() or "未识别",
            locked_character_names=locked_character_names_text,
            discussion_context=str(input_data.get("discussion_context") or "").strip() or "无",
            recent_discussion=str(input_data.get("recent_discussion") or "").strip() or "无",
            novel_type=str(input_data.get("novel_type") or "").strip() or "未指定",
            theme=str(input_data.get("theme") or "").strip() or "未指定",
            protagonist=str(input_data.get("protagonist") or "").strip() or "未指定",
            plot_idea=str(input_data.get("plot_idea") or "").strip() or "未指定",
            world_summary=str(input_data.get("world_summary") or "").strip() or "无",
            existing_characters_summary=str(input_data.get("existing_characters_summary") or "").strip() or "无",
        )
        if custom_prompt:
            return custom_prompt

        return (
            "请基于以下信息生成角色卡草稿：\n\n"
            f"## 当前请求模式\n{request_mode}\n\n"
            f"## AI自主创作授权\n{autonomy_note}\n\n"
            f"## 自主创作说明\n{str(input_data.get('autonomous_brief') or '').strip() or '无'}\n\n"
            f"## 当前用户请求\n{str(input_data.get('user_request') or '').strip() or '无'}\n\n"
            f"## 角色需求摘要\n{str(input_data.get('character_request') or '').strip() or '无'}\n\n"
            f"## 角色类型提示\n{str(input_data.get('character_role') or '').strip() or '未指定'}\n\n"
            f"## 已识别姓名提示\n{str(input_data.get('character_name') or '').strip() or '未识别'}\n\n"
            f"## 已确认角色名锁定\n{CharacterBuilderAgent._stringify_for_prompt(input_data.get('locked_character_names'), max_chars=500) or '无'}\n\n"
            f"## 完整讨论上下文基准\n{str(input_data.get('discussion_context') or '').strip() or '无'}\n\n"
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
            "4. 必须沿用完整讨论上下文基准中的已确认设定；缺失则 missing_info，不得随机换题。\n"
            "5. 如果“已确认角色名锁定”列出姓名，主角/男女主必须使用这些姓名，不得改名、替换或另起同定位角色。\n"
            "6. 不要输出任何 JSON 以外的内容。\n"
            "7. 当 AI自主创作授权 为已授权时，第2条和第4条中的“信息不足”只指题材/篇幅/风格完全缺失；"
            "角色姓名、身份、人物关系和剧情细节未指定时，应由你主动补全。\n"
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
        if not request.get("world") and isinstance(context, dict) and context.get("world"):
            request["world"] = context.get("world")
        if not str(request.get("world_summary") or "").strip() and isinstance(context, dict):
            world_payload = context.get("world")
            world_summary = self._build_world_summary(world_payload)
            if world_summary:
                request["world_summary"] = world_summary
        elif request.get("world") and not str(request.get("world_summary") or "").strip():
            world_summary = self._build_world_summary(request.get("world"))
            if world_summary:
                request["world_summary"] = world_summary
        locked_names = self._extract_locked_character_names(request, context)
        if locked_names:
            request["locked_character_names"] = locked_names
        ai_autonomy_requested = bool(request.get("ai_autonomy_requested")) or str(request.get("request_mode") or "").strip() == "autonomous_draft"
        if not str(request.get("character_request") or "").strip():
            request["character_request"] = str(request.get("protagonist") or request.get("plot_idea") or request.get("user_request") or "").strip()
        if ai_autonomy_requested and not str(request.get("character_request") or "").strip():
            request["character_request"] = "用户已授权助手自主安排角色姓名、身份、人物关系和人物弧线。"
        minimum_signal = any(
            str(request.get(key) or "").strip()
            for key in ("character_request", "recent_discussion", "protagonist", "plot_idea", "world_summary", "autonomous_brief")
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
        is_valid = False
        business_issues: List[str] = []
        normalized_characters: List[Dict[str, Any]] = []
        message = ""
        for _ in range(2):
            payload, response, issues = await self._generate_once(request, feedback=feedback)
            if payload is None:
                feedback = "；".join(str(item) for item in issues if str(item).strip()) or "请输出合法且完整的 JSON"
                continue
            status_for_validation = str(payload.get("status") or "ok").strip() or "ok"
            if status_for_validation == "missing_info":
                break
            is_valid, business_issues, normalized_characters, message = self._validate_payload(
                payload,
                required_names=locked_names,
            )
            if is_valid:
                break
            feedback = "；".join(str(item) for item in business_issues if str(item).strip()) or "角色卡草稿质量不足"
            if locked_names:
                feedback += "；必须使用已确认角色名：" + "、".join(locked_names)

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

        if status != "missing_info" and not is_valid:
            is_valid, business_issues, normalized_characters, message = self._validate_payload(
                payload,
                required_names=locked_names,
            )
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

        consistency_warnings = self._check_character_world_consistency(
            normalized_characters, input_data,
        )

        return {
            "success": True,
            "agent": self.name,
            "status": status,
            "confidence": confidence_value,
            "characters": normalized_characters,
            "missing_info": missing_info,
            "raw_response": response,
            "consistency_warnings": consistency_warnings,
        }
