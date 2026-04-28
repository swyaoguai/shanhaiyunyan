"""Project-ready task execution subsystem."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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
            "build_outline": self._execute_build_outline,
            "write_chapter": self._execute_write_chapter,
            "summary_orchestrate": self._execute_summary_orchestrate,
        }

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
        input_data = dict(current_task.inputs or {})
        task_context = {"project_dir": str(self.coordinator.project_dir)}
        run_result = await self.coordinator._run_autonomous_task(
            task_type="build_world",
            input_data=input_data,
            context=task_context,
            fallback_agent=self.coordinator.worldbuilder,
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = run_result.get("result", {})
        result_ref = ""
        if isinstance(result_payload, dict):
            world_data = result_payload.get("world", {})
            if isinstance(world_data, dict) and world_data:
                self.coordinator.context_manager.save("world", world_data, "world")
            result_ref = "worldbuilding.json"

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_build_outline(self, current_task: Any) -> Dict[str, Any]:
        """Execute build_outline task."""
        input_data = dict(current_task.inputs or {})
        input_data["world"] = self.coordinator.context_manager.get("world", {})
        task_context = {"project_dir": str(self.coordinator.project_dir)}
        run_result = await self.coordinator._run_autonomous_task(
            task_type="build_outline",
            input_data=input_data,
            context=task_context,
            fallback_agent=self.coordinator.outliner,
            stage="project_ready",
            title=current_task.title,
            description=current_task.description,
            expected_outputs=current_task.expected_outputs,
            review_required=bool(current_task.review_required),
        )

        result_payload = run_result.get("result", {})
        result_ref = ""
        if isinstance(result_payload, dict):
            outline_data = result_payload.get("outline", {})
            if isinstance(outline_data, dict) and outline_data:
                self.coordinator.context_manager.save("outline", outline_data, "plot")
                outline_rows = self.coordinator._extract_chapters(outline_data)
                if outline_rows:
                    timestamp = datetime.now().isoformat()
                    project_rows = []
                    for index, chapter in enumerate(outline_rows, start=1):
                        title = str(chapter.get("title") or f"第{index}章").strip() if isinstance(chapter, dict) else f"第{index}章"
                        summary = str(chapter.get("summary") or "").strip() if isinstance(chapter, dict) else str(chapter or "").strip()
                        project_rows.append({
                            "chapter_number": index,
                            "title": title,
                            "summary": summary,
                            "content": "",
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        })
                    self.coordinator.project_manager.save_project_data("outline", project_rows)
                    self.coordinator._sync_outline_to_library(project_rows)
            result_ref = "outline.json"

        metadata_patch = self.coordinator._build_metadata_patch(run_result)
        return {
            "run_result": run_result,
            "result_ref": result_ref,
            "metadata_patch": metadata_patch,
            "chapter_task_executed": False,
        }

    async def _execute_write_chapter(self, current_task: Any) -> Dict[str, Any]:
        """Execute write_chapter task."""
        from .task_pool import TaskStatus
        input_data = dict(current_task.inputs or {})
        chapter_number = int(input_data.get("chapter_number") or 1)
        outline_rows = self.coordinator._load_project_outline_rows()
        row = outline_rows[chapter_number - 1] if 0 < chapter_number <= len(outline_rows) else {}
        chapter_title = str(row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        chapter_outline = str(
            row.get("summary")
            or row.get("content")
            or current_task.title
            or chapter_title
        ).strip() or chapter_title
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
        input_data = dict(current_task.inputs or {})
        task_context = {"project_dir": str(self.coordinator.project_dir)}
        task_context["world"] = self.coordinator.world_manager.get_world_context()
        task_context["characters"] = self.coordinator.character_manager.get_character_context()

        outline_rows = self.coordinator.project_manager.load_project_data("outline")
        task_context["chapters"] = outline_rows if outline_rows else []

        run_result = await self.coordinator._run_autonomous_task(
            task_type="summary_orchestrate",
            input_data=input_data,
            context=task_context,
            fallback_agent=self.coordinator.summary_orchestrator,
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

            task_execution = await task_handler(current_task)
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
