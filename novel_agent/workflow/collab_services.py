"""长篇协作模式的本地服务与轻量参与者。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..agents.base_agent import AgentCapability
from ..agents.enhanced_prompts import AGENT_COORDINATION_PROTOCOL
from .context_bundle import load_confirmed_context_bundles_from_project_dir

CallbackHandler = Callable[[Dict[str, Any]], Awaitable[Optional[Any]]]


class BaseCollabService:
    """不依赖 BaseAgent 生命周期的本地协作服务。"""

    def __init__(self, name: str):
        self.name = name
        self.callback_handler: Optional[CallbackHandler] = None
        self.knowledge_base = None
        self.llm_client = None  # 13.6 新增：可选的 LLM 客户端

    def set_callback_handler(self, handler: CallbackHandler) -> None:
        self.callback_handler = handler

    def set_knowledge_base(self, knowledge_base) -> None:
        self.knowledge_base = knowledge_base

    def set_llm_client(self, llm_client) -> None:
        """13.6 新增：设置 LLM 客户端，用于智能扩写/总结等需要调用 LLM 的服务。"""
        self.llm_client = llm_client

    async def ensure_subscribed(self) -> None:
        return None


class ContextStrategyService(BaseCollabService):
    def __init__(self):
        super().__init__(name="ContextStrategy")

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


class ContentReaderService(BaseCollabService):
    def __init__(self):
        super().__init__(name="ContentReader")

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
            "context_bundles": runtime_context.get("context_bundles", []),
        }

        permanent_memory = self._load_permanent_memory(project_dir)
        permanent_loaded_keys = set(permanent_memory.get("loaded_keys") or [])
        context_bundles = load_confirmed_context_bundles_from_project_dir(project_dir)

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
            elif key == "context_bundles" and value in (None, "", [], {}):
                if context_bundles:
                    loaded["context_bundles"] = context_bundles
                    value = context_bundles
                    source = "context_bundle"

            if key in {"banned_words", "anti_ai_rules", "knowledge_base"}:
                if key in permanent_loaded_keys:
                    skipped_reason = "permanent_memory_hit"
                    source = "permanent_memory"
                    value = (permanent_memory.get("items") or {}).get(key)
                else:
                    permanent_loaded_keys.add(key)

            report.append(
                {
                    "key": key,
                    "label": item.get("label", key),
                    "loaded": value not in (None, "", [], {}),
                    "source": source,
                    "skipped_reason": skipped_reason,
                }
            )

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


class ContentExpansionService(BaseCollabService):
    """13.6 修复：调用 LLM 进行智能扩写，不保留规则降级。"""

    def __init__(self):
        super().__init__(name="ContentExpansion")

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

        if self.llm_client is None:
            raise RuntimeError(f"[{self.name}] 未配置 LLM 客户端，无法执行智能扩写")

        system_prompt = (
            "你是一位专业的小说扩写编辑。你的任务是在不改变原文结构和情节走向的前提下，"
            "对给定的章节内容进行扩写，使其达到目标字数。\n"
            f"{AGENT_COORDINATION_PROTOCOL}\n"
            "扩写要求：\n"
            "1. 保持原文的叙事风格和节奏\n"
            "2. 补充场景细节、人物心理、环境描写\n"
            "3. 增强对话的自然感和信息量\n"
            "4. 不要添加与大纲无关的新情节\n"
            "5. 不要使用省略号、破折号等标点符号过度\n"
            "6. 不要把系统进度、Agent 名称、交接字段、保存状态或错误提示写入正文\n"
            "7. 直接输出扩写后的完整章节内容，不要添加任何解释或标注"
        )
        user_prompt = (
            f"章节标题：{chapter_title}\n"
            f"章节大纲：{chapter_outline[:500]}\n"
            f"{'上一章摘要：' + previous_summary[:200] if previous_summary else ''}\n"
            f"目标字数：{target_words}字\n"
            f"当前字数：{current_nonspace}字\n\n"
            f"原文内容：\n{content}"
        )
        result = await self.llm_client.call(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=min(target_words * 3, 8000),
        )
        if not isinstance(result, str) or len(re.sub(r"\s+", "", result)) <= current_nonspace:
            raise RuntimeError(f"[{self.name}] LLM扩写结果无效或未达到目标字数")

        expanded_nonspace = len(re.sub(r"\s+", "", result))
        return {
            "success": True,
            "agent": self.name,
            "content": result,
            "expanded": True,
            "word_count": expanded_nonspace,
        }


class FileNamingService(BaseCollabService):
    def __init__(self):
        super().__init__(name="FileNaming")

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


class SummaryService(BaseCollabService):
    """13.6 修复：调用 LLM 生成真正的剧情总结，不保留规则降级。"""

    def __init__(self):
        super().__init__(name="SummaryOrchestrator")

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chapters = list(input_data.get("chapters") or [])
        start_chapter = int(input_data.get("start_chapter") or 1)
        end_chapter = int(input_data.get("end_chapter") or start_chapter)

        if self.llm_client is None:
            raise RuntimeError(f"[{self.name}] 未配置 LLM 客户端，无法执行剧情总结")

        chapter_texts = []
        chapter_items: List[Dict[str, Any]] = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            number = ch.get("chapter_number") or ch.get("number") or "?"
            title = str(ch.get("title") or ch.get("chapter_title") or f"第{number}章").strip()
            content = str(ch.get("content") or "").strip()
            if content:
                chapter_texts.append(f"【第{number}章 {title}】\n{content[:800]}")
            chapter_items.append({"chapter_number": number, "title": title, "summary": content[:120].strip() if content else ""})

        if not chapter_texts:
            raise RuntimeError(f"[{self.name}] 无有效章节内容可供总结")

        system_prompt = (
            "你是一位专业的小说剧情分析师。请对以下章节内容进行总结，生成一份简洁的剧情梗概。\n"
            f"{AGENT_COORDINATION_PROTOCOL}\n"
            "总结要求：\n"
            "1. 提炼每章的核心剧情事件和转折点\n"
            "2. 标注主要人物的行动和变化\n"
            "3. 指出伏笔、悬念和未解之谜\n"
            "4. 保持客观叙述，不添加个人评价\n"
            "5. 每章总结控制在100-200字\n"
            "6. 最后给出整体剧情走向的简要分析\n"
            "7. 只总结正文事实，不把系统进度、Agent 名称、任务日志或保存状态写成剧情"
        )
        user_prompt = (
            f"请总结第{start_chapter}章到第{end_chapter}章的剧情：\n\n"
            + "\n\n".join(chapter_texts)
        )
        result = await self.llm_client.call(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=4000,
        )
        if not isinstance(result, str) or len(result.strip()) < 50:
            raise RuntimeError(f"[{self.name}] LLM总结结果无效")

        summary = result.strip()
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


class ServiceBackedCollabParticipant(BaseCollabService):
    """将本地服务包装为可执行的轻量参与者。

    13.7 修复：不再实现 accepts_task() / estimate_cost()，
    避免被 capability_registry 误选为路由候选。
    Service 不参与路由选择，只通过 RoutingPolicy 的 preferred_agent_name 直接指定。
    """

    def __init__(self, service: BaseCollabService, capability: AgentCapability):
        super().__init__(name=service.name)
        self.service = service
        self._capability = capability

    def set_callback_handler(self, handler: CallbackHandler) -> None:
        super().set_callback_handler(handler)
        if hasattr(self.service, "set_callback_handler"):
            self.service.set_callback_handler(handler)

    def set_knowledge_base(self, knowledge_base) -> None:
        super().set_knowledge_base(knowledge_base)
        if hasattr(self.service, "set_knowledge_base"):
            self.service.set_knowledge_base(knowledge_base)

    def set_llm_client(self, llm_client) -> None:
        """13.6/13.7 修复：将 LLM 客户端传递给内部服务。"""
        super().set_llm_client(llm_client)
        if hasattr(self.service, "set_llm_client"):
            self.service.set_llm_client(llm_client)

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self._capability.agent_name,
            capabilities=list(self._capability.capabilities or []),
            accept_task_types=list(self._capability.accept_task_types or []),
            required_inputs=list(self._capability.required_inputs or []),
            produced_outputs=list(self._capability.produced_outputs or []),
            priority=int(self._capability.priority or 0),
            max_concurrency=int(self._capability.max_concurrency or 1),
            metadata=dict(self._capability.metadata or {}),
        )

    # 13.7 修复：不再实现 accepts_task() / estimate_cost()
    # Service 不参与路由选择，避免被 capability_registry 的 find_candidates() 误选

    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self.service.execute(input_data, context=context)


def build_default_collab_service_registry() -> Dict[str, BaseCollabService]:
    return {
        "context_strategy": ContextStrategyService(),
        "content_reader": ContentReaderService(),
        "content_expansion": ContentExpansionService(),
        "file_naming": FileNamingService(),
        "summary_orchestrator": SummaryService(),
    }


def resolve_chapter_market_results(
    chapter_market_results: Dict[str, Any],
    chapter_num: int,
    chapter_title: str,
) -> Dict[str, Any]:
    """
    Parse and assemble final chapter data from chapter task market results.
    Pure function - no coordinator state needed.
    """
    import re
    chapter_writer_run = chapter_market_results.get("write_chapter", {})
    chapter_result = chapter_writer_run.get("result", {}) if isinstance(chapter_writer_run, dict) else {}
    chapter_content = str(chapter_result.get("content") or "")

    evaluator_run = chapter_market_results.get("evaluate_chapter", {})
    eval_result = evaluator_run.get("result", {}) if isinstance(evaluator_run, dict) else {}
    evaluation = eval_result.get("evaluation", {}) if isinstance(eval_result, dict) else {}

    polisher_run: Dict[str, Any] = {}
    market_polish_run = chapter_market_results.get("polish_chapter", {})
    if isinstance(market_polish_run, dict) and market_polish_run:
        polisher_run = market_polish_run
        polish_result = polisher_run.get("result", {})
        chapter_content = str(polish_result.get("content") or chapter_content)

    expansion_run = chapter_market_results.get("expand_content", {})
    expanded_result = expansion_run.get("result", {}) if isinstance(expansion_run, dict) else {}
    chapter_content = str(expanded_result.get("content") or chapter_content)

    summary_run = chapter_market_results.get("summary_orchestrate", {})
    summary_result = summary_run.get("result", {}) if isinstance(summary_run, dict) else {}
    summary_payload = summary_result.get("summary_payload", {}) if isinstance(summary_result, dict) else {}

    context_strategy_run = chapter_market_results.get("context_strategy", {})
    content_reader_run = chapter_market_results.get("content_reader", {})
    reader_result = content_reader_run.get("result", {}) if isinstance(content_reader_run, dict) else {}

    autonomy_trace = {
        "chapter_task_market": chapter_market_results.get("task_pool", {}),
        "context_plan": {
            "selected_agent": context_strategy_run.get("selected_agent", ""),
            "candidate_agents": context_strategy_run.get("candidate_agents", []),
            "task_pool": context_strategy_run.get("task_pool", {}),
        },
        "content_read": {
            "selected_agent": content_reader_run.get("selected_agent", ""),
            "candidate_agents": content_reader_run.get("candidate_agents", []),
            "task_pool": content_reader_run.get("task_pool", {}),
        },
        "write_chapter": {
            "selected_agent": chapter_writer_run.get("selected_agent", ""),
            "candidate_agents": chapter_writer_run.get("candidate_agents", []),
            "task_pool": chapter_writer_run.get("task_pool", {}),
        },
        "evaluate_chapter": {
            "selected_agent": evaluator_run.get("selected_agent", ""),
            "candidate_agents": evaluator_run.get("candidate_agents", []),
            "task_pool": evaluator_run.get("task_pool", {}),
        },
        "polish_chapter": {
            "selected_agent": polisher_run.get("selected_agent", "") if polisher_run else "",
            "candidate_agents": polisher_run.get("candidate_agents", []) if polisher_run else [],
            "task_pool": polisher_run.get("task_pool", {}) if polisher_run else {},
        },
        "expand_content": {
            "selected_agent": expansion_run.get("selected_agent", ""),
            "candidate_agents": expansion_run.get("candidate_agents", []),
            "task_pool": expansion_run.get("task_pool", {}),
        },
        "summary_orchestrate": {
            "selected_agent": summary_run.get("selected_agent", "") if summary_run else "",
            "candidate_agents": summary_run.get("candidate_agents", []) if summary_run else [],
            "task_pool": summary_run.get("task_pool", {}) if summary_run else {},
        },
    }

    normalized_word_count = int(
        expanded_result.get("word_count")
        or len(re.sub(r"\s+", "", chapter_content))
        or 0
    )

    return {
        "chapter_content": chapter_content,
        "evaluation": evaluation,
        "polisher_run": polisher_run,
        "expanded_result": expanded_result,
        "summary_result": summary_result,
        "summary_payload": summary_payload,
        "reader_result": reader_result,
        "autonomy_trace": autonomy_trace,
        "normalized_word_count": normalized_word_count,
    }


def build_default_collab_participants(services: Dict[str, BaseCollabService]) -> Dict[str, ServiceBackedCollabParticipant]:
    return {
        "ContextStrategy": ServiceBackedCollabParticipant(
            services["context_strategy"],
            AgentCapability(
                agent_name="ContextStrategy",
                capabilities=["plan_context", "identify_dependencies"],
                accept_task_types=["context_plan"],
                required_inputs=["chapter_number", "chapter_title"],
                produced_outputs=["strategy"],
                priority=88,
                max_concurrency=2,
                metadata={"stage": "chapter_preparation", "runtime": "service_backed"},
            ),
        ),
        "ContentReader": ServiceBackedCollabParticipant(
            services["content_reader"],
            AgentCapability(
                agent_name="ContentReader",
                capabilities=["load_context", "resolve_context_inputs"],
                accept_task_types=["content_read"],
                required_inputs=["strategy"],
                produced_outputs=["loaded_context", "report", "permanent_memory"],
                priority=87,
                max_concurrency=2,
                metadata={"stage": "chapter_preparation", "runtime": "service_backed"},
            ),
        ),
        "ContentExpansion": ServiceBackedCollabParticipant(
            services["content_expansion"],
            AgentCapability(
                agent_name="ContentExpansion",
                capabilities=["expand_content", "enrich_chapter"],
                accept_task_types=["expand_content"],
                required_inputs=["content", "target_words"],
                produced_outputs=["content", "word_count", "expanded"],
                priority=80,
                max_concurrency=2,
                metadata={"stage": "post_processing", "runtime": "service_backed"},
            ),
        ),
        "SummaryOrchestrator": ServiceBackedCollabParticipant(
            services["summary_orchestrator"],
            AgentCapability(
                agent_name="SummaryOrchestrator",
                capabilities=["summarize_stage", "summarize_chapters"],
                accept_task_types=["summary_orchestrate"],
                required_inputs=["start_chapter", "end_chapter", "chapters"],
                produced_outputs=["summary", "summary_payload"],
                priority=70,
                max_concurrency=1,
                metadata={"stage": "stage_summary", "runtime": "service_backed"},
            ),
        ),
    }
