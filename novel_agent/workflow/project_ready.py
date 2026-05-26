"""Project-ready task execution subsystem."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..outline_utils import derive_chapter_seed_rows_from_outline

logger = logging.getLogger(__name__)


class ProjectReadyTaskExecutor:
    """
    Executes project-ready tasks from a CreationContract task graph.
    Delegates to coordinator for task execution and state management.
    """

    def __init__(self, coordinator: Any):
        self.coordinator = coordinator
        self._task_handlers: Dict[str, Callable] = {
            "build_world": self._execute_build_world,
            "build_characters": self._execute_build_characters,
            "build_outline": self._execute_build_outline,
            "chapter_settings": self._execute_chapter_settings,
            "write_chapter": self._execute_write_chapter,
            "summary_orchestrate": self._execute_summary_orchestrate,
        }

    def _registered_fallback_agent(self, task_type: str, fallback_agent: Any) -> Any:
        """Return fallback only when the active registry declares it for this task."""
        if fallback_agent is None:
            return None
        fallback_name = str(getattr(fallback_agent, "name", "") or "").strip()
        if not fallback_name:
            return None

        registry = getattr(self.coordinator, "collab_agent_registry", None)
        if registry is None:
            registry = getattr(self.coordinator, "capability_registry", None)
        if registry is None or not hasattr(registry, "find_candidates"):
            return fallback_agent

        try:
            candidates = registry.find_candidates({"task_type": str(task_type or "").strip()}) or []
        except Exception as exc:
            logger.debug(f"[ProjectReady] fallback candidate check failed for {task_type}: {exc}")
            return None

        candidate_names = {
            str(item.get("agent_name") or "").strip()
            for item in candidates
            if isinstance(item, dict)
        }
        if fallback_name not in candidate_names:
            return None
        return fallback_agent

    def _load_creation_contract_scope(self) -> Dict[str, Any]:
        project_manager = getattr(self.coordinator, "project_manager", None)
        if project_manager is None or not hasattr(project_manager, "load_project_state"):
            return {}
        try:
            payload = project_manager.load_project_state("creation_contract", default={})
        except Exception as exc:
            logger.debug(f"[ProjectReady] load creation contract failed: {exc}")
            return {}
        if not isinstance(payload, dict):
            return {}
        scope = payload.get("scope")
        return dict(scope) if isinstance(scope, dict) else {}

    def _enrich_input_with_creation_contract(
        self,
        task_type: str,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Backfill formal task inputs from the saved creation contract."""
        data = dict(input_data or {})
        scope = self._load_creation_contract_scope()
        if not scope:
            return data

        common_keys = (
            "novel_type",
            "theme",
            "requirements",
            "protagonist",
            "plot_idea",
            "volume_count",
            "chapters_per_volume",
            "total_chapters",
            "target_word_count",
            "target_words_per_chapter",
            "ai_autonomy_requested",
        )
        for key in common_keys:
            if data.get(key) in (None, "", [], {}) and scope.get(key) not in (None, "", [], {}):
                data[key] = scope.get(key)

        discussion_context = str(scope.get("discussion_context") or "").strip()
        if discussion_context:
            data.setdefault("discussion_context", discussion_context)
            data.setdefault("recent_discussion", discussion_context)

        if task_type == "build_characters":
            autonomous_brief = str(scope.get("autonomous_brief") or "").strip()
            if not autonomous_brief and bool(scope.get("ai_autonomy_requested", False)):
                autonomous_brief = (
                    "用户已授权助手自主安排未指定的角色姓名、人物设定和剧情细节；"
                    "请在已给定题材、主题、篇幅与讨论方向内主动补全。"
                )
            if autonomous_brief:
                data.setdefault("autonomous_brief", autonomous_brief)
                data.setdefault("character_request", data.get("protagonist") or data.get("plot_idea") or autonomous_brief)
                data.setdefault("request_mode", "autonomous_draft")
            else:
                data.setdefault("character_request", data.get("protagonist") or data.get("plot_idea") or "")
                data.setdefault("request_mode", "draft")

        return data

    def _chapter_settings_review_state(self) -> Dict[str, Any]:
        project_manager = getattr(self.coordinator, "project_manager", None)
        if project_manager is None or not hasattr(project_manager, "load_project_state"):
            return {}
        try:
            state = project_manager.load_project_state("chapter_settings_review", default={})
        except Exception as exc:
            logger.debug(f"[ProjectReady] load chapter settings review state failed: {exc}")
            return {}
        return dict(state) if isinstance(state, dict) else {}

    def _save_chapter_settings_review_state(self, state: Dict[str, Any]) -> None:
        project_manager = getattr(self.coordinator, "project_manager", None)
        if project_manager is None or not hasattr(project_manager, "save_project_state"):
            return
        try:
            project_manager.save_project_state("chapter_settings_review", dict(state or {}))
        except Exception as exc:
            logger.warning(f"[ProjectReady] 保存章纲审阅状态失败: {exc}")

    def _is_chapter_settings_review_approved(self) -> bool:
        state = self._chapter_settings_review_state()
        return bool(state.get("approved"))

    def approve_chapter_settings_review(self) -> Dict[str, Any]:
        state = self._chapter_settings_review_state()
        state.update({
            "approved": True,
            "approved_at": datetime.now().isoformat(),
            "status": "approved",
        })
        self._save_chapter_settings_review_state(state)
        return state

    @staticmethod
    def _has_payload_value(value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return any(ProjectReadyTaskExecutor._has_payload_value(item) for item in value)
        if isinstance(value, dict):
            return any(ProjectReadyTaskExecutor._has_payload_value(item) for item in value.values())
        return True

    @classmethod
    def _is_meaningful_world_data(cls, world_data: Any) -> bool:
        if not isinstance(world_data, dict) or not world_data:
            return False
        status = str(world_data.get("status") or "").strip().lower()
        if status in {"missing_info", "failed", "error"}:
            return False

        world_name = str(world_data.get("world_name") or world_data.get("name") or "").strip()
        if world_name and world_name not in {"未命名世界", "未命名", "世界"}:
            return True

        raw_content = str(world_data.get("raw_content") or "").strip()
        if len(raw_content) >= 40:
            return True

        for key in (
            "core_concept",
            "background",
            "history",
            "power_system",
            "geography",
            "factions",
            "rules",
            "culture",
            "locations",
            "events",
        ):
            if cls._has_payload_value(world_data.get(key)):
                return True
        return False

    @staticmethod
    def _agent_failure_message(result_payload: Any, fallback: str) -> str:
        if not isinstance(result_payload, dict):
            return fallback
        primary = str(
            result_payload.get("error")
            or result_payload.get("message")
            or result_payload.get("response_message")
            or fallback
        ).strip() or fallback
        details: List[str] = []
        for key in ("missing_info", "validation_issues", "issues", "violations"):
            value = result_payload.get(key)
            if isinstance(value, list):
                details.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                details.append(value.strip())
        if details:
            detail_text = "；".join(dict.fromkeys(details[:4]))
            if detail_text and detail_text not in primary:
                primary = f"{primary}：{detail_text}"
        return primary

    @classmethod
    def _assert_successful_result(cls, run_result: Dict[str, Any], fallback: str) -> Dict[str, Any]:
        result_payload = run_result.get("result", {}) if isinstance(run_result, dict) else {}
        if not isinstance(result_payload, dict):
            raise RuntimeError(fallback)
        if result_payload.get("success") is False:
            raise RuntimeError(cls._agent_failure_message(result_payload, fallback))
        return result_payload

    # --- Public API ---

    def initialize_from_contract(
        self,
        contract_payload: Dict[str, Any],
        approved: bool = True,
    ) -> Dict[str, Any]:
        """Initialize task pool from a creation contract."""
        return self.coordinator.initialize_task_pool_from_contract(contract_payload, approved)

    async def execute_next_batch(
        self,
        max_tasks: int = 2,
        max_chapter_tasks: Optional[int] = 1,
    ) -> Dict[str, Any]:
        """Execute next batch of ready tasks."""
        return await self._execute_project_ready_batch(
            max_tasks=max_tasks,
            max_chapter_tasks=max_chapter_tasks,
        )

    # --- Task handlers (coordinator delegates to these) ---

    async def _execute_build_world(self, current_task: Any) -> Dict[str, Any]:
        """Execute build_world task."""
        input_data = self._enrich_input_with_creation_contract(
            "build_world",
            dict(current_task.inputs or {}),
        )
        task_context = {"project_dir": str(self.coordinator.project_dir)}
        run_result = await self.coordinator._run_autonomous_task(
            task_type="build_world",
            input_data=input_data,
            context=task_context,
            fallback_agent=self._registered_fallback_agent("build_world", self.coordinator.worldbuilder),
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = self._assert_successful_result(
            run_result,
            "世界观生成未成功",
        )
        result_ref = ""
        world_data = result_payload.get("world", {})
        if not self._is_meaningful_world_data(world_data):
            raise RuntimeError(
                self._agent_failure_message(
                    world_data if isinstance(world_data, dict) else result_payload,
                    "世界观生成未产出有效设定",
                )
            )

        self.coordinator.context_manager.save("world", world_data, "world")
        from ..worldbuilding_persistence import persist_worldbuilding_project_data
        from ..context.world_manager import WorldSetting

        # 关键：将新生成的世界观同步到 coordinator.world_manager 的内存态，
        # 否则后续 ChapterWriter 通过 world_manager.get_world_context() 拿到的
        # 依旧是"暂无世界观设定"，导致章节正文与世界观脱钩。
        try:
            world_type_value = str(
                input_data.get("novel_type")
                or world_data.get("world_type")
                or "通用"
            ).strip() or "通用"
            world_setting = WorldSetting(
                name=str(world_data.get("world_name") or world_data.get("name") or "未命名世界").strip() or "未命名世界",
                world_type=world_type_value,
                power_system=world_data.get("power_system", {}) or {},
                geography=world_data.get("geography", {}) or {},
                factions=world_data.get("factions", []) or [],
                rules=world_data.get("rules", []) or [],
                culture=world_data.get("culture", {}) or {},
            )
            self.coordinator.world_manager.set_world(world_setting)
        except Exception as exc:
            logger.warning(f"[ProjectReady] world_manager 同步失败，后续章节可能拿不到世界观: {exc}")

        persisted_world = persist_worldbuilding_project_data(
            {"world": world_data},
            project_manager=self.coordinator.project_manager,
            source_mode="multi_agent",
            source_type="multi_agent_worldbuilding",
        )
        if not persisted_world:
            raise RuntimeError("世界观生成结果未成功写入 worldbuilding.json")
        result_ref = "worldbuilding.json"

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_build_characters(self, current_task: Any) -> Dict[str, Any]:
        """Execute build_characters task."""
        from ..context.character_manager import Character
        from ..project_data_recovery import persist_project_data

        input_data = self._enrich_input_with_creation_contract(
            "build_characters",
            dict(current_task.inputs or {}),
        )
        world = self.coordinator.context_manager.get("world", {})
        if isinstance(world, dict) and isinstance(world.get("world"), dict):
            world_payload = world.get("world")
        else:
            world_payload = world
        input_data["world"] = world
        if not str(input_data.get("world_summary") or "").strip():
            build_world_summary = getattr(self.coordinator.character_builder, "_build_world_summary", None)
            if callable(build_world_summary):
                input_data["world_summary"] = build_world_summary(world_payload)
        input_data.setdefault(
            "request_mode",
            "autonomous_draft" if input_data.get("ai_autonomy_requested") else "draft",
        )
        input_data.setdefault(
            "character_request",
            input_data.get("protagonist")
            or input_data.get("plot_idea")
            or input_data.get("autonomous_brief")
            or input_data.get("user_request")
            or "",
        )
        task_context = {
            "project_dir": str(self.coordinator.project_dir),
            "world": world,
        }

        run_result = await self.coordinator._run_autonomous_task(
            task_type="build_characters",
            input_data=input_data,
            context=task_context,
            fallback_agent=self._registered_fallback_agent("build_characters", self.coordinator.character_builder),
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = self._assert_successful_result(
            run_result,
            "角色档案生成未成功",
        )
        result_ref = ""
        characters = result_payload.get("characters") or []
        if not isinstance(characters, list) or not characters:
            raise RuntimeError("角色档案生成未产出有效角色")
        normalized = self.coordinator.character_manager._normalize_character_payload(characters)
        if not normalized:
            raise RuntimeError("角色档案生成结果无法规范化为有效角色")
        self.coordinator.character_manager.characters.clear()
        for _name, char_data in normalized.items():
            self.coordinator.character_manager.characters[_name] = Character(**char_data)
        exported = self.coordinator.character_manager.export_for_llm()
        self.coordinator.context_manager.save("characters", exported, "character")
        persist_project_data(
            "characters",
            exported,
            project_manager=self.coordinator.project_manager,
            source_mode="multi_agent",
            source_type="multi_agent_characters",
        )
        result_ref = "characters.json"

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_build_outline(self, current_task: Any) -> Dict[str, Any]:
        """Execute build_outline task."""
        input_data = self._enrich_input_with_creation_contract(
            "build_outline",
            dict(current_task.inputs or {}),
        )
        world = self.coordinator.context_manager.get("world", {})
        characters = self.coordinator.character_manager.export_for_llm()
        input_data["world"] = world
        input_data["characters"] = characters
        task_context = {
            "project_dir": str(self.coordinator.project_dir),
            "world": world,
            "characters": characters,
        }
        run_result = await self.coordinator._run_autonomous_task(
            task_type="build_outline",
            input_data=input_data,
            context=task_context,
            fallback_agent=self._registered_fallback_agent("build_outline", self.coordinator.outliner),
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = self._assert_successful_result(
            run_result,
            "大纲生成未成功",
        )
        result_ref = ""
        outline_data = result_payload.get("outline", {})
        if not isinstance(outline_data, dict) or not outline_data:
            raise RuntimeError("大纲生成未产出有效结构")
        self.coordinator.context_manager.save("outline", outline_data, "plot")
        outline_rows = self.coordinator._outline_to_project_rows(outline_data)
        if not outline_rows:
            raise RuntimeError("大纲生成结果未包含可落盘的全书总纲或分卷规划")
        self.coordinator._persist_outline_rows(outline_rows)
        self.coordinator._sync_eventlines_from_outline(outline_data)
        result_ref = "outline.json"

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_chapter_settings(self, current_task: Any) -> Dict[str, Any]:
        """Execute chapter_settings task and persist rows before chapter writing."""
        input_data = self._enrich_input_with_creation_contract(
            "chapter_settings",
            dict(current_task.inputs or {}),
        )
        outline_rows = self.coordinator._load_project_outline_rows()
        try:
            outline_payload = self.coordinator.context_manager.get("outline", {})
        except Exception:
            outline_payload = {}
        outline_seed_rows = derive_chapter_seed_rows_from_outline(outline_payload or outline_rows)
        if not outline_seed_rows:
            outline_seed_rows = derive_chapter_seed_rows_from_outline(outline_rows)
        eventlines = self.coordinator.project_manager.load_project_data("eventlines")
        if not isinstance(eventlines, list):
            eventlines = []
        world = self.coordinator.world_manager.get_world_context()
        characters = self.coordinator.character_manager.export_for_llm()

        input_data["outline_rows"] = outline_seed_rows or outline_rows
        input_data["outline_overview_rows"] = outline_rows
        input_data["eventlines"] = [row for row in eventlines if isinstance(row, dict)]
        input_data["characters"] = characters
        input_data.setdefault("world_summary", str(world or ""))
        input_data.setdefault(
            "user_request",
            current_task.description or current_task.title or "生成章纲设定",
        )
        task_context = {
            "project_dir": str(self.coordinator.project_dir),
            "outline_rows": input_data["outline_rows"],
            "outline_overview_rows": outline_rows,
            "eventlines": input_data["eventlines"],
            "world": world,
            "characters": characters,
        }

        run_result = await self.coordinator._run_autonomous_task(
            task_type="chapter_settings",
            input_data=input_data,
            context=task_context,
            fallback_agent=self._registered_fallback_agent(
                "chapter_settings",
                self.coordinator.chapter_setting_builder,
            ),
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = self._assert_successful_result(
            run_result,
            "章纲设定生成未成功",
        )
        rows: List[Dict[str, Any]] = []
        raw_rows = result_payload.get("chapter_settings") or result_payload.get("rows") or []
        if isinstance(raw_rows, list):
            rows = [dict(row) for row in raw_rows if isinstance(row, dict)]

        result_ref = ""
        if rows:
            from ..source_modes import ensure_record_source_mode

            rows = [
                ensure_record_source_mode(row, "multi_agent", source_type="multi_agent_chapter_settings")
                for row in rows
            ]
            self.coordinator.project_manager.save_project_data("chapter_settings", rows)
            self.coordinator._sync_chapter_settings_to_library(rows)
            result_ref = "chapter_settings.json"
        else:
            raise RuntimeError("章纲设定生成未产出有效条目")

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        review_state = {
            "approved": not bool(current_task.metadata.get("stop_on_review_required", False)),
            "status": (
                "approved"
                if not bool(current_task.metadata.get("stop_on_review_required", False))
                else "pending_review"
            ),
            "updated_at": datetime.now().isoformat(),
            "result_ref": result_ref,
            "row_count": len(rows),
            "task_id": str(getattr(current_task, "task_id", "") or "").strip(),
        }
        self._save_chapter_settings_review_state(review_state)
        metadata_patch["chapter_settings_review"] = review_state["status"]
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_write_chapter(self, current_task: Any) -> Dict[str, Any]:
        """Execute write_chapter task."""
        from .task_pool import TaskStatus
        if not self._is_chapter_settings_review_approved():
            raise PermissionError("章纲设定尚未确认，已阻止提前创建正文章节文件")

        input_data = self._enrich_input_with_creation_contract(
            "write_chapter",
            dict(current_task.inputs or {}),
        )
        chapter_number = int(input_data.get("chapter_number") or 1)
        outline_rows = self.coordinator._load_project_chapter_rows()
        row = next(
            (
                item for item in self.coordinator._sort_chapter_rows(outline_rows)
                if int(item.get("chapter_number") or 0) == chapter_number
            ),
            {},
        )
        chapter_title = str(row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        chapter_outline = str(
            row.get("summary")
            or row.get("content")
            or current_task.title
            or chapter_title
        ).strip() or chapter_title
        discussion_context = str(
            input_data.get("discussion_context")
            or input_data.get("recent_discussion")
            or ""
        ).strip()
        if discussion_context and discussion_context not in chapter_outline:
            chapter_outline = (
                f"{chapter_outline}\n\n"
                "【全局聊天讨论约束】\n"
                f"{discussion_context}"
            ).strip()
        previous_chapters = self.coordinator._load_project_previous_chapters(chapter_number, outline_rows)

        chapter_result = await self.coordinator.write_chapter_from_context(
            chapter_number=chapter_number,
            chapter_outline={
                "title": chapter_title,
                "summary": chapter_outline,
            },
            previous_chapters=previous_chapters,
        )
        persist_result = await self.coordinator._persist_project_ready_chapter_result(chapter_result, outline_rows)
        result_ref = str(persist_result.get("chapter_path") or "")

        metadata_patch = {
            "project_task_execution": "ready_task_loop",
            "selected_agent": "ChapterWriter",
            "execution_mode": "project_ready_chapter",
            "fallback_used": False,
            "outline_path": persist_result.get("outline_path", ""),
        }
        run_result = {
            "selected_agent": "ChapterWriter",
            "execution_mode": "project_ready_chapter",
            "fallback_used": False,
            "result": chapter_result,
        }
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": True,
        }

    async def _execute_summary_orchestrate(self, current_task: Any) -> Dict[str, Any]:
        """Execute summary_orchestrate task."""
        input_data = self._enrich_input_with_creation_contract(
            "summary_orchestrate",
            dict(current_task.inputs or {}),
        )
        task_context = {"project_dir": str(self.coordinator.project_dir)}
        task_context["world"] = self.coordinator.world_manager.get_world_context()
        task_context["characters"] = self.coordinator.character_manager.get_character_context()

        outline_rows = self.coordinator._load_project_chapter_rows()
        task_context["chapters"] = outline_rows if outline_rows else []

        run_result = await self.coordinator._run_autonomous_task(
            task_type="summary_orchestrate",
            input_data=input_data,
            context=task_context,
            fallback_agent=self._registered_fallback_agent("summary_orchestrate", self.coordinator.summary_orchestrator),
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_ref = ""
        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        persist_result = self.coordinator._persist_project_stage_summary_result(
            run_result.get("result", {}),
        )
        if persist_result:
            result_ref = str(persist_result.get("summary_path") or "")

        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    # --- Batch execution loop ---

    async def _execute_project_ready_batch(
        self,
        *,
        max_tasks: int = 2,
        max_chapter_tasks: Optional[int] = 1,
    ) -> Dict[str, Any]:
        """Execute a batch of ready tasks from the project-ready task pool.

        问题14修复：只在循环开始和结束时各加载/保存一次任务池，
        循环内直接操作内存中的 runtime_pool 对象，避免每个任务 2 次磁盘 IO。
        """
        from .task_pool import TaskStatus

        # 循环开始时加载一次
        runtime_pool = self.coordinator._load_runtime_task_pool()
        executed_tasks: List[Dict[str, Any]] = []
        stopped_on_task_type = ""
        stop_reason = ""
        loop_guard = 0
        chapter_tasks_executed = 0
        max_task_limit = max(1, int(max_tasks or 1))
        chapter_task_limit = None if max_chapter_tasks is None else max(0, int(max_chapter_tasks))

        while loop_guard < max_task_limit:
            ready_tasks = runtime_pool.get_ready_tasks()
            if not ready_tasks:
                break

            current_task = ready_tasks[0]
            task_type = str(current_task.task_type or "").strip()
            task_handler = self._task_handlers.get(task_type)
            if task_handler is None:
                stopped_on_task_type = task_type
                stop_reason = "unsupported_task_type"
                break

            if task_type == "write_chapter" and not self._is_chapter_settings_review_approved():
                runtime_pool.block_task(
                    current_task.task_id,
                    reason="章纲设定尚未确认，已阻止提前创建正文章节文件",
                )
                stopped_on_task_type = task_type
                stop_reason = "chapter_settings_review_required"
                break

            if (
                task_type == "write_chapter"
                and chapter_task_limit is not None
                and chapter_tasks_executed >= chapter_task_limit
            ):
                stopped_on_task_type = task_type
                stop_reason = "max_chapter_tasks_reached"
                break

            await self.coordinator._notify_progress({
                "type": "sub_agent_dispatching",
                "stage": "project_dispatch",
                "agent": "Coordinator",
                "task_type": task_type,
                "title": str(current_task.title or task_type).strip(),
                "message": f"正在调度任务: {current_task.title or task_type}",
            })

            try:
                task_execution = await task_handler(current_task)
            except Exception as exc:
                error_message = str(exc)
                runtime_pool.fail_task(current_task.task_id, error=error_message)
                stopped_on_task_type = task_type
                stop_reason = "task_failed"
                await self.coordinator._notify_progress({
                    "type": "sub_agent_failed",
                    "stage": "project_dispatch",
                    "agent": str(current_task.assigned_agent or "Coordinator").strip() or "Coordinator",
                    "task_type": task_type,
                    "title": str(current_task.title or task_type).strip(),
                    "error": error_message,
                    "message": f"任务执行失败: {current_task.title or task_type}",
                })
                break
            run_result = dict(task_execution.get("run_result") or {})
            result_ref = str(task_execution.get("result_ref") or "")
            metadata_patch = dict(task_execution.get("metadata_patch") or {})
            if bool(task_execution.get("chapter_task_executed", False)):
                chapter_tasks_executed += 1

            # 问题14修复：直接操作内存中的 runtime_pool，不从磁盘重载
            persisted_task = runtime_pool.get_task(current_task.task_id)
            if persisted_task is not None:
                runtime_pool.update_task_status(
                    current_task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent=str(run_result.get("selected_agent") or persisted_task.assigned_agent or "").strip(),
                    result_ref=result_ref,
                    metadata_patch=metadata_patch,
                )

            executed_tasks.append({
                "task_id": current_task.task_id,
                "task_type": task_type,
                "title": current_task.title,
                "selected_agent": run_result.get("selected_agent", ""),
                "result_ref": result_ref,
            })
            loop_guard += 1

            if bool(run_result.get("fallback_used", False)):
                stopped_on_task_type = task_type
                stop_reason = "fallback_triggered"
                break

            if (
                bool(current_task.review_required)
                and bool(current_task.metadata.get("stop_on_review_required", False))
            ):
                stopped_on_task_type = task_type
                stop_reason = "review_required"
                break

        # 检查剩余任务状态
        remaining_ready_tasks = runtime_pool.get_ready_tasks()
        if not stop_reason:
            if loop_guard >= max_task_limit and remaining_ready_tasks:
                stop_reason = "max_tasks_reached"
            elif remaining_ready_tasks:
                next_task_type = str(remaining_ready_tasks[0].task_type or "").strip()
                if next_task_type not in self._task_handlers:
                    stopped_on_task_type = next_task_type
                    stop_reason = "unsupported_task_type"
                elif (
                    next_task_type == "write_chapter"
                    and chapter_task_limit is not None
                    and chapter_tasks_executed >= chapter_task_limit
                ):
                    stopped_on_task_type = next_task_type
                    stop_reason = "max_chapter_tasks_reached"

        project_ready_execution = {
            "updated_at": datetime.now().isoformat(),
            "executed_task_count": len(executed_tasks),
            "chapter_tasks_executed": chapter_tasks_executed,
            "stopped_on_task_type": stopped_on_task_type,
            "stop_reason": stop_reason,
            "max_tasks": max_task_limit,
            "max_chapter_tasks": chapter_task_limit,
        }
        runtime_pool.metadata["project_ready_execution"] = project_ready_execution
        # 循环结束后统一保存一次
        self.coordinator._save_runtime_task_pool(runtime_pool)
        self.coordinator._append_collab_execution_event(
            "project_ready_execution_cycle",
            {
                "executed_task_count": len(executed_tasks),
                "chapter_tasks_executed": chapter_tasks_executed,
                "stopped_on_task_type": stopped_on_task_type,
                "stop_reason": stop_reason,
            },
        )

        return {
            "task_pool": runtime_pool.to_dict(),
            "executed_tasks": executed_tasks,
            "chapter_tasks_executed": chapter_tasks_executed,
            "stopped_on_task_type": stopped_on_task_type,
            "stop_reason": stop_reason,
            "project_ready_execution": project_ready_execution,
        }
