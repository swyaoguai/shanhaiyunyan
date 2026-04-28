"""
协作扩展辅助节点集合

警告：本文件已弃用！
所有实现已迁移到 `workflow/collab_services.py`。
本文件仅作向后兼容保留，请勿在新代码中使用。

- 本文件中的大多数对象是"内部辅助节点 / helper"，不是面向用户的独立 AI 子 Agent
- 它们主要承担：规则规划、上下文读取、命名、简单拼装、阶段总结等轻量职责
- 只有真正会独立调用大模型并产出可校验结果的对象，才应被视作"真子Agent"
- 旧版 CharacterBuilderAgent 仅保留为兼容性的规则回退节点，不再用于主流程
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent, AgentCapability


def _deprecated(cls):
    original_init = cls.__init__
    def __init__(self, *args, **kwargs):
        warnings.warn(
            f"{cls.__name__} is deprecated. "
            f"Use services from novel_agent.workflow.collab_services instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        original_init(self, *args, **kwargs)
    cls.__init__ = __init__
    return cls


class _SimpleAgent(BaseAgent):
    """最小化内部辅助节点基类，默认不依赖外部提示词文件。"""

    def __init__(self, name: str):
        self._agent_prompt_name = name
        super().__init__(name=name, prompt_file=None)

    def _get_default_prompt(self) -> str:
        return f"你是{self._agent_prompt_name}。"


@_deprecated
class CharacterBuilderAgent(_SimpleAgent):
    """已弃用的角色规则回退节点：仅做兼容保留，不应用于主流程角色卡生成。"""

    def __init__(self):
        super().__init__(name="CharacterBuilder")

    def _get_default_prompt(self) -> str:
        return "你是内部规则回退节点，仅在兼容场景下做基础角色字段提取，不负责正式角色卡生成。"

    @staticmethod
    def _normalize_role(raw_role: str) -> str:
        text = str(raw_role or "").strip()
        if any(token in text for token in ("主角", "男主", "女主")):
            return "主角"
        if "反派" in text:
            return "反派"
        if "配角" in text:
            return "配角"
        return text or "角色"

    @staticmethod
    def _extract_name(description: str, fallback: str) -> str:
        text = str(description or "").strip()
        if not text:
            return fallback
        match = re.search(r"(?:叫|名叫|名字是|姓名是)\s*([A-Za-z0-9\u4e00-\u9fa5·]{2,24})", text)
        if match:
            return match.group(1).strip()

        first_chunk = re.split(r"[，,：:\s\n]+", text, maxsplit=1)[0].strip()
        if 1 <= len(first_chunk) <= 24 and not re.search(r"(创建|生成|设计|档案|资料|设定|角色|人物|主角)", first_chunk):
            return first_chunk
        return fallback

    @staticmethod
    def _extract_age(description: str) -> str:
        text = str(description or "").strip()
        if not text:
            return ""
        match = re.search(r"([0-9]{1,3})\s*岁", text)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_gender(description: str) -> str:
        text = str(description or "").strip()
        if any(token in text for token in ("女主", "少女", "女孩", "女性", "女生", "她")):
            return "女"
        if any(token in text for token in ("男主", "少年", "男孩", "男性", "男生", "他")):
            return "男"
        return ""

    @staticmethod
    def _extract_identity(description: str) -> str:
        text = str(description or "").strip()
        if not text:
            return ""
        patterns = [
            r"(?:是|作为|身份是)([^，。；;\n]{2,30})",
            r"((?:宗主|峰主|掌门|弟子|杂役|护法|长老|宗门遗孤|调查员|医生|警察|老师|学生|老板|刺客|杀手|商人|公主|皇子|王爷|将军|修士|剑修)[^，。；;\n]{0,18})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip("：:，,。；; ")
        return ""

    @staticmethod
    def _extract_personality(description: str) -> List[str]:
        text = str(description or "").strip()
        if not text:
            return ["待补充"]
        candidates = [
            "抽象", "无厘头", "冷静", "理性", "克制", "腹黑", "热血", "善良", "执着",
            "谨慎", "机敏", "幽默", "毒舌", "温柔", "偏执", "坚韧", "乐观", "悲观",
            "孤僻", "张扬", "风骚", "疯批", "沉稳", "果断",
        ]
        detected = [token for token in candidates if token in text]
        return detected[:6] or ["待补充"]

    @staticmethod
    def _extract_goal_list(description: str, plot_idea: str) -> List[str]:
        text = " ".join(part for part in [str(description or "").strip(), str(plot_idea or "").strip()] if part).strip()
        goals: List[str] = []
        heuristics = [
            ("追杀", "摆脱追杀"),
            ("复仇", "完成复仇"),
            ("变强", "快速提升实力"),
            ("提升境界", "突破当前境界"),
            ("秘境", "活着走出秘境"),
            ("调查", "查清真相"),
            ("宗门", "在宗门中站稳脚跟"),
            ("副本", "征服关键副本"),
        ]
        for keyword, goal in heuristics:
            if keyword in text and goal not in goals:
                goals.append(goal)
        return goals[:4]

    @staticmethod
    def _extract_motivation(description: str, plot_idea: str, theme: str) -> str:
        text = str(description or "").strip()
        if "因为" in text:
            tail = text.split("因为", 1)[1].strip()
            return tail[:80]
        if any(token in text for token in ("追杀", "欠钱")):
            return "摆脱生存危机，并借此改变命运"
        if plot_idea:
            return plot_idea[:80]
        return theme[:80] if theme else ""

    @staticmethod
    def _extract_tags(character_role: str, novel_type: str, theme: str, description: str) -> List[str]:
        tags: List[str] = []
        for value in [character_role, novel_type, theme]:
            cleaned = str(value or "").strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        text = str(description or "")
        for token in ("修仙", "爽文", "悬疑", "校园", "科幻", "抽象", "合欢宗", "副本"):
            if token in text and token not in tags:
                tags.append(token)
        return tags[:6]

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        requirements = dict(input_data or {})
        protagonist = str(requirements.get("protagonist") or "").strip()
        character_prompt = str(requirements.get("character_prompt") or "").strip()
        character_role = self._normalize_role(str(requirements.get("character_role") or "").strip())
        character_name = str(requirements.get("character_name") or "").strip()
        theme = str(requirements.get("theme") or "").strip()
        plot_idea = str(requirements.get("plot_idea") or "").strip()
        novel_type = str(requirements.get("novel_type") or "未分类").strip() or "未分类"

        characters: List[Dict[str, Any]] = []

        if character_prompt or character_name:
            description = character_prompt or protagonist or f"{character_role}待补充设定"
            normalized_name = character_name or self._extract_name(description, fallback=character_role)
            identity = self._extract_identity(description)
            age = self._extract_age(description)
            gender = self._extract_gender(description)
            personality = self._extract_personality(description)
            goals = self._extract_goal_list(description, plot_idea)
            motivation = self._extract_motivation(description, plot_idea, theme)
            characters.append({
                "name": normalized_name,
                "role": character_role,
                "description": description,
                "age": age,
                "gender": gender,
                "identity": identity or character_role,
                "occupation": identity,
                "appearance": "",
                "personality": personality,
                "abilities": [],
                "background": theme or plot_idea or novel_type,
                "motivation": motivation,
                "goals": goals,
                "habits": [],
                "speaking_style": "",
                "relationships": {},
                "arc": "待补充",
                "notes": "",
                "tags": self._extract_tags(character_role, novel_type, theme, description),
                "first_appearance": 1,
                "status": "active",
            })
            return {
                "success": True,
                "agent": self.name,
                "characters": characters,
            }

        if protagonist:
            main_name = protagonist.split("，", 1)[0].split(",", 1)[0].strip() or "主角"
            identity = self._extract_identity(protagonist)
            characters.append({
                "name": main_name,
                "role": "主角",
                "description": protagonist,
                "age": self._extract_age(protagonist),
                "gender": self._extract_gender(protagonist),
                "identity": identity or "主角",
                "occupation": identity,
                "appearance": "",
                "personality": self._extract_personality(protagonist),
                "abilities": [],
                "background": theme or plot_idea,
                "motivation": self._extract_motivation(protagonist, plot_idea, theme),
                "goals": self._extract_goal_list(protagonist, plot_idea),
                "habits": [],
                "speaking_style": "",
                "relationships": {},
                "arc": "从困境中成长并推动主线",
                "notes": "",
                "tags": self._extract_tags("主角", novel_type, theme, protagonist),
                "first_appearance": 1,
                "status": "active",
            })

        if plot_idea:
            characters.append({
                "name": "关键对手",
                "role": "反派",
                "description": f"围绕{plot_idea[:80]}形成的主要阻力角色",
                "age": "",
                "gender": "",
                "identity": "关键对手",
                "occupation": "",
                "appearance": "",
                "personality": ["制造冲突", "推动升级"],
                "abilities": [],
                "background": novel_type,
                "motivation": "阻止主角达成关键目标",
                "goals": ["对主角形成持续压制"],
                "habits": [],
                "speaking_style": "",
                "relationships": {},
                "arc": "与主角形成持续对抗",
                "notes": "",
                "tags": self._extract_tags("反派", novel_type, theme, plot_idea),
                "first_appearance": 1,
                "status": "active",
            })

        if not characters:
            characters.append({
                "name": "主角",
                "role": "主角",
                "description": f"{novel_type}题材默认主角",
                "age": "",
                "gender": "",
                "identity": "主角",
                "occupation": "",
                "appearance": "",
                "personality": ["待补充"],
                "abilities": [],
                "background": theme or "待补充",
                "motivation": "",
                "goals": [],
                "habits": [],
                "speaking_style": "",
                "relationships": {},
                "arc": "待补充",
                "notes": "",
                "tags": self._extract_tags("主角", novel_type, theme, ""),
                "first_appearance": 1,
                "status": "active",
            })

        return {
            "success": True,
            "agent": self.name,
            "characters": characters,
        }


@_deprecated
class ContextStrategyAgent(_SimpleAgent):
    """内部辅助节点：决定每章需要读取哪些上下文。"""

    def __init__(self):
        super().__init__(name="ContextStrategy")

    def _get_default_prompt(self) -> str:
        return "你是内部上下文策略辅助节点，负责制定章节写作前的上下文读取计划。"

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["plan_context", "identify_dependencies"],
            accept_task_types=["context_plan"],
            required_inputs=["chapter_number", "chapter_title"],
            produced_outputs=["strategy"],
            priority=88,
            max_concurrency=2,
            metadata={"stage": "chapter_preparation"},
        )

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chapter_number = int(input_data.get("chapter_number") or 1)
        chapter_title = str(input_data.get("chapter_title") or f"第{chapter_number}章").strip()
        previous_available = bool(input_data.get("previous_summary"))
        has_characters = bool(input_data.get("characters"))
        has_world = bool(input_data.get("world"))

        read_plan = [
            {"key": "world", "label": "世界观", "priority": "P0", "required": has_world},
            {"key": "characters", "label": "角色档案", "priority": "P0", "required": has_characters},
            {"key": "chapter_outline", "label": "当前章节大纲", "priority": "P0", "required": True},
            {"key": "previous_summary", "label": "上一章摘要", "priority": "P1", "required": previous_available},
        ]

        return {
            "success": True,
            "agent": self.name,
            "strategy": {
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "read_plan": read_plan,
                "summary": f"第{chapter_number}章优先读取世界观、角色档案、当前大纲"
                           f"{'，并补充上一章摘要' if previous_available else ''}。",
            },
        }


@_deprecated
class ContentReaderAgent(_SimpleAgent):
    """内部辅助节点：将计划中的上下文整合为写作输入。"""

    def __init__(self):
        super().__init__(name="ContentReader")

    def _get_default_prompt(self) -> str:
        return "你是内部内容读取辅助节点，负责将上下文策略转化为实际写作上下文。"

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["load_context", "resolve_context_inputs"],
            accept_task_types=["content_read"],
            required_inputs=["strategy"],
            produced_outputs=["loaded_context", "report", "permanent_memory"],
            priority=87,
            max_concurrency=2,
            metadata={"stage": "chapter_preparation"},
        )

    @staticmethod
    def _safe_load_json(path: Path) -> Any:
        if not path.exists() or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _normalize_world_payload(payload: Any) -> Any:
        if isinstance(payload, dict):
            return payload.get("world", payload)
        return payload

    @staticmethod
    def _normalize_characters_payload(payload: Any) -> Any:
        if isinstance(payload, dict) and "characters" in payload:
            return payload.get("characters")
        return payload

    @staticmethod
    def _load_permanent_memory(project_dir: Optional[Path]) -> Dict[str, Any]:
        if not project_dir:
            return {"loaded_keys": [], "items": {}}
        memory_path = project_dir / "client_state" / "collab_permanent_memory.json"
        if not memory_path.exists():
            return {"loaded_keys": [], "items": {}}
        try:
            payload = json.loads(memory_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {
                    "loaded_keys": list(payload.get("loaded_keys") or []),
                    "items": dict(payload.get("items") or {}),
                }
        except Exception:
            pass
        return {"loaded_keys": [], "items": {}}

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime_context = dict(context or {})
        strategy = dict(input_data.get("strategy") or {})
        read_plan = strategy.get("read_plan") or []
        project_dir_raw = runtime_context.get("project_dir")
        project_dir = Path(project_dir_raw) if project_dir_raw else None

        loaded = {
            "world": runtime_context.get("world", {}),
            "characters": runtime_context.get("characters", ""),
            "previous_summary": runtime_context.get("previous_summary", ""),
            "chapter_outline": runtime_context.get("chapter_outline", ""),
            "plot_thread": runtime_context.get("plot_thread", {}),
            "aux_memory": runtime_context.get("aux_memory", {}),
            "trends_data": runtime_context.get("trends_data", []),
        }

        permanent_memory = self._load_permanent_memory(project_dir)
        permanent_loaded_keys = set(permanent_memory.get("loaded_keys") or [])

        file_payloads: Dict[str, Any] = {}
        if project_dir:
            file_payloads = {
                "world": self._normalize_world_payload(self._safe_load_json(project_dir / "worldbuilding.json")),
                "characters": self._normalize_characters_payload(self._safe_load_json(project_dir / "characters.json")),
                "outline": self._safe_load_json(project_dir / "outline.json"),
            }

        report = []
        for item in read_plan:
            key = str(item.get("key") or "").strip()
            if not key:
                continue

            source = "runtime"
            skipped_reason = ""
            value = loaded.get(key)

            if key == "world" and value in (None, "", [], {}):
                candidate = file_payloads.get("world")
                if candidate not in (None, "", [], {}):
                    loaded["world"] = candidate
                    value = candidate
                    source = "project_file"
            elif key == "characters" and value in (None, "", [], {}):
                candidate = file_payloads.get("characters")
                if candidate not in (None, "", [], {}):
                    loaded["characters"] = candidate
                    value = candidate
                    source = "project_file"
            elif key == "chapter_outline" and value in (None, "", [], {}):
                candidate = runtime_context.get("chapter_outline") or input_data.get("chapter_outline") or ""
                if candidate not in (None, "", [], {}):
                    loaded["chapter_outline"] = candidate
                    value = candidate
            elif key == "previous_summary" and value in (None, "", [], {}):
                candidate = runtime_context.get("previous_summary", "")
                if candidate not in (None, "", [], {}):
                    loaded["previous_summary"] = candidate
                    value = candidate

            if key in {"banned_words", "anti_ai_rules", "knowledge_base"}:
                if key in permanent_loaded_keys:
                    skipped_reason = "permanent_memory_hit"
                    source = "permanent_memory"
                    value = (permanent_memory.get("items") or {}).get(key)
                else:
                    permanent_loaded_keys.add(key)

            report.append({
                "key": key,
                "label": item.get("label", key),
                "loaded": value not in (None, "", [], {}),
                "source": source,
                "skipped_reason": skipped_reason,
            })

        merged_permanent_items = dict(permanent_memory.get("items") or {})
        for key in permanent_loaded_keys:
            merged_permanent_items.setdefault(key, (permanent_memory.get("items") or {}).get(key))

        return {
            "success": True,
            "agent": self.name,
            "loaded_context": loaded,
            "report": report,
            "permanent_memory": {
                "loaded_keys": sorted(permanent_loaded_keys),
                "items": merged_permanent_items,
            },
        }


@_deprecated
class ContentExpansionAgent(_SimpleAgent):
    """内部辅助节点：当章节过短时补足内容。"""

    def __init__(self):
        super().__init__(name="ContentExpansion")

    def _get_default_prompt(self) -> str:
        return "你是内部内容扩展辅助节点，负责在不破坏原意的前提下补足章节内容。"

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["expand_content", "enrich_chapter"],
            accept_task_types=["expand_content"],
            required_inputs=["content", "target_words"],
            produced_outputs=["content", "word_count", "expanded"],
            priority=80,
            max_concurrency=2,
            metadata={"stage": "post_processing"},
        )

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = str(input_data.get("content") or "").strip()
        target_words = int(input_data.get("target_words") or 2000)
        chapter_title = str(input_data.get("chapter_title") or "").strip()
        chapter_outline = str(input_data.get("chapter_outline") or "").strip()
        previous_summary = str((context or {}).get("previous_summary") or "").strip()

        current_nonspace = len(re.sub(r"\s+", "", content))
        if current_nonspace >= target_words or not content:
            return {
                "success": True,
                "agent": self.name,
                "content": content,
                "expanded": False,
                "word_count": current_nonspace,
            }

        supplements: List[str] = []
        if chapter_outline:
            outline_snippet = str(chapter_outline[:120]) if chapter_outline else ""
            supplements.append(
                f"{chapter_title or '本章'}的主线继续向前推进，围绕「{outline_snippet}」补足承接过程，让冲突的起因、转折与落点更完整。"
            )
        if previous_summary:
            supplements.append(
                "前文留下的局面在这一段里得到延续，人物会根据上一章形成的压力继续行动，避免情节突然跳段。"
            )
        supplements.append(
            "补充现场反应、人物动作与局势变化，让场景转换更顺，信息交代更清楚。"
        )

        expanded_content = content.rstrip() + "\n\n" + "\n".join(supplements)
        expanded_nonspace = len(re.sub(r"\s+", "", expanded_content))

        return {
            "success": True,
            "agent": self.name,
            "content": expanded_content,
            "expanded": True,
            "word_count": expanded_nonspace,
        }


@_deprecated
class FileNamingAgent(_SimpleAgent):
    """内部辅助节点：生成统一章节文件名。"""

    def __init__(self):
        super().__init__(name="FileNaming")

    def _get_default_prompt(self) -> str:
        return "你是内部文件命名辅助节点，负责生成标准化章节文件名。"

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chapter_number = int(input_data.get("chapter_number") or 1)
        chapter_title = str(input_data.get("chapter_title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        content = str(input_data.get("content") or "").strip()
        word_count = int(input_data.get("word_count") or len(re.sub(r"\s+", "", content)) or 0)

        normalized_title = re.sub(r"^第[\s\d一二三四五六七八九十百千万零〇]+章[\s\-_:：]*", "", chapter_title).strip()
        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", normalized_title)
        safe_title = re.sub(r"\s+", "_", safe_title).strip("._")
        filename = f"第{chapter_number}章-{safe_title + '-' if safe_title else ''}{word_count}字.md"

        return {
            "success": True,
            "agent": self.name,
            "filename": filename,
            "word_count": word_count,
        }


@_deprecated
class SummaryOrchestratorAgent(_SimpleAgent):
    """内部辅助节点：为一组章节生成阶段总结。"""

    def __init__(self):
        super().__init__(name="SummaryOrchestrator")

    def _get_default_prompt(self) -> str:
        return "你是内部摘要编排辅助节点，负责在阶段节点生成章节总结。"

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["summarize_stage", "summarize_chapters"],
            accept_task_types=["summary_orchestrate"],
            required_inputs=["start_chapter", "end_chapter", "chapters"],
            produced_outputs=["summary", "summary_payload"],
            priority=70,
            max_concurrency=1,
            metadata={"stage": "stage_summary"},
        )

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chapters = list(input_data.get("chapters") or [])
        start_chapter = int(input_data.get("start_chapter") or 1)
        end_chapter = int(input_data.get("end_chapter") or start_chapter)

        lines = [f"第{start_chapter}-{end_chapter}章剧情总结"]
        chapter_items: List[Dict[str, Any]] = []
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            number = chapter.get("chapter_number") or chapter.get("number") or "?"
            title = str(chapter.get("title") or chapter.get("chapter_title") or f"第{number}章").strip()
            content = str(chapter.get("content") or "").strip()
            snippet = content[:120].strip() if content else str(chapter.get("summary") or "").strip()
            lines.append(f"- 第{number}章《{title}》：{snippet}")
            chapter_items.append({
                "chapter_number": number,
                "title": title,
                "summary": snippet,
            })

        summary = "\n".join(lines).strip()
        return {
            "success": True,
            "agent": self.name,
            "summary": summary,
            "summary_payload": {
                "start_chapter": start_chapter,
                "end_chapter": end_chapter,
                "chapter_count": len(chapter_items),
                "chapters": chapter_items,
                "summary": summary,
            },
        }
