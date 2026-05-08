"""Generic serial executor for creative workflow runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .artifact_review import ReviewIssue, ReviewResult, review_artifact_basic
from .creative_workflow import CreativeWorkflowRun
from .workflow_context import AgentHandoff, Artifact, WorkflowContext
from .workflow_planner import WorkflowTask


TaskRunner = Callable[[WorkflowTask, WorkflowContext], Awaitable["TaskExecutionResult"]]
ProgressEmitter = Callable[[CreativeWorkflowRun, Dict[str, Any]], Awaitable[None]]
PauseChecker = Callable[[], Awaitable[bool]]
ReviewRunner = Callable[[WorkflowTask, Artifact, WorkflowContext, ReviewResult], Awaitable[Optional[ReviewResult]]]


@dataclass
class TaskExecutionResult:
    success: bool
    agent_name: str
    action: str
    response: str = ""
    artifact: Any = None
    artifact_type: str = ""
    target_path: str = ""
    created_files: List[Dict[str, Any]] = field(default_factory=list)
    updated_files: List[Dict[str, Any]] = field(default_factory=list)
    reused_files: List[Dict[str, Any]] = field(default_factory=list)
    focus_module: str = ""
    focus_chapter: int = 0
    params: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


def _merge_file_records(target: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> None:
    existing_paths = {str(item.get("path") or "").strip() for item in target if isinstance(item, dict)}
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if path and path not in existing_paths:
            target.append(item)
            existing_paths.add(path)


def _handoff_from_artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    artifact: Any,
    summary: str,
) -> AgentHandoff:
    new_facts: List[str] = []
    if isinstance(artifact, dict):
        for key, value in list(artifact.items())[:5]:
            if value not in (None, "", [], {}):
                new_facts.append(f"{key}: {str(value)[:80]}")
    elif isinstance(artifact, list):
        for item in artifact[:5]:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or "").strip()
                if name:
                    new_facts.append(name)

    return AgentHandoff(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        decisions=[summary] if summary else [],
        new_facts=new_facts,
        next_context_summary=summary,
    )


class CreativeWorkflowExecutor:
    """Run workflow tasks one after another with review and handoff."""

    def __init__(
        self,
        *,
        run: CreativeWorkflowRun,
        task_runner: TaskRunner,
        progress_emitter: Optional[ProgressEmitter] = None,
        pause_checker: Optional[PauseChecker] = None,
        review_runner: Optional[ReviewRunner] = None,
    ):
        self.run = run
        self.task_runner = task_runner
        self.progress_emitter = progress_emitter
        self.pause_checker = pause_checker
        self.review_runner = review_runner

    async def execute(self) -> CreativeWorkflowRun:
        await self._emit({
            "content": self._format_plan_message(),
            "current_agent": "Coordinator",
            "stage": "workflow_planning",
            "status": "running",
        })

        for task in self.run.task_queue:
            if task.status == "completed":
                continue
            if task.task_type == "prepare_context":
                self.run.complete_task(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    target_agent=task.target_agent,
                    status="completed",
                )
                continue

            if await self._should_pause_or_cancel():
                self.run.status = "paused"
                self.run.mark_task(task.task_id, "pending")
                await self._emit({
                    "content": "### 工作流暂停\n已在当前任务前暂停，等待继续或修改意见。",
                    "current_agent": "Coordinator",
                    "stage": "paused",
                    "status": "paused",
                })
                return self.run

            await self._run_single_task(task)
            if self.run.status in {"failed", "cancelled", "paused"}:
                return self.run

        self.run.status = "completed"
        self.run.set_current(agent="Coordinator", stage="completed", status="completed")
        await self._emit({
            "content": "### 工作流完成\n全部任务已按串行顺序执行、审查并完成交接。",
            "current_agent": "Coordinator",
            "stage": "completed",
            "status": "completed",
        })
        return self.run

    async def _run_single_task(self, task: WorkflowTask) -> None:
        while True:
            self.run.mark_task(task.task_id, "running")
            self.run.set_current(agent=task.target_agent, stage=task.task_type, status="running")
            await self._emit({
                "content": f"### {task.title or task.task_type}\n正在调用{task.target_agent}处理当前任务。",
                "current_agent": task.target_agent,
                "stage": task.task_type,
                "status": "running",
            })

            try:
                result = await self.task_runner(task, self.run.canonical_context)
            except Exception as exc:
                artifact_id = f"{task.task_id}-artifact-{len(self.run.artifacts) + 1}"
                artifact = Artifact(
                    artifact_id=artifact_id,
                    artifact_type=task.output_type or task.task_type,
                    task_id=task.task_id,
                    content={"error": str(exc)},
                    status="failed",
                    updated_at=datetime.now().isoformat(),
                )
                self.run.add_artifact(artifact)
                error = str(exc) or "task_exception"
                if await self._retry_task(task, artifact, error):
                    continue
                await self._fail_task(task, artifact_id, error)
                return

            _merge_file_records(self.run.created_files, result.created_files)
            _merge_file_records(self.run.updated_files, result.updated_files)
            _merge_file_records(self.run.reused_files, result.reused_files)

            artifact_id = f"{task.task_id}-artifact-{len(self.run.artifacts) + 1}"
            artifact_type = result.artifact_type or task.output_type or task.task_type
            artifact = Artifact(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                task_id=task.task_id,
                content=result.artifact,
                status="draft",
                target_path=result.target_path,
                updated_at=datetime.now().isoformat(),
            )
            self.run.add_artifact(artifact)

            if not result.success:
                error = result.error or result.response or "task_failed"
                if await self._retry_task(task, artifact, error):
                    continue
                await self._fail_task(task, artifact_id, error)
                return

            if task.review_required:
                review = review_artifact_basic(
                    task_id=task.task_id,
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    artifact=result.artifact,
                    revision_target=task.target_agent,
                )
                if review.passed and self.review_runner:
                    try:
                        deep_review = await self.review_runner(task, artifact, self.run.canonical_context, review)
                        if deep_review is not None:
                            review = deep_review
                    except Exception as exc:
                        review = ReviewResult(
                            task_id=task.task_id,
                            artifact_id=artifact_id,
                            artifact_type=artifact_type,
                            passed=False,
                            severity="major",
                            issues=[ReviewIssue(type="evaluator_error", message=str(exc) or "Evaluator review failed.")],
                            revision_target=task.target_agent,
                            revision_instructions=str(exc) or "Evaluator review failed.",
                        )
                self.run.add_review(review)
                await self._emit({
                    "content": (
                        "### 独立审查\n审查通过。"
                        if review.passed
                        else f"### 独立审查\n审查退回：{'；'.join(issue.message for issue in review.issues)}"
                    ),
                    "current_agent": "Evaluator",
                    "stage": f"{task.task_type}_review",
                    "status": "running",
                })
                if not review.passed:
                    error = review.revision_instructions or "review_failed"
                    if await self._retry_task(task, artifact, error):
                        continue
                    await self._fail_task(task, artifact_id, error)
                    return

            artifact.status = "committed"
            artifact.updated_at = datetime.now().isoformat()
            self._sync_artifact_snapshot(artifact)
            self.run.add_handoff(
                _handoff_from_artifact(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    artifact=result.artifact,
                    summary=result.response or f"{task.title or task.task_type}已完成。",
                )
            )
            self.run.complete_task(
                task_id=task.task_id,
                task_type=task.task_type,
                target_agent=task.target_agent,
                artifact_id=artifact_id,
                status="completed",
            )
            await self._emit({
                "content": f"### {task.title or task.task_type}完成\n已通过审查并完成交接。",
                "current_agent": task.target_agent,
                "stage": task.task_type,
                "status": "running",
                "focus_module": result.focus_module,
                "focus_chapter": result.focus_chapter,
            })
            return

    async def _retry_task(self, task: WorkflowTask, artifact: Artifact, reason: str) -> bool:
        if task.retry_count >= task.max_retries:
            return False
        task.retry_count += 1
        artifact.status = "revision_requested"
        artifact.updated_at = datetime.now().isoformat()
        self._sync_artifact_snapshot(artifact)
        self.run.mark_task(task.task_id, "revision_requested")
        await self._emit({
            "content": f"### 打回修改\n{task.target_agent}将根据审查意见重试：{reason}",
            "current_agent": task.target_agent,
            "stage": f"{task.task_type}_revision",
            "status": "running",
            "revision_reason": reason,
        })
        return True

    def _sync_artifact_snapshot(self, artifact: Artifact) -> None:
        snapshot = artifact.to_dict()
        self.run.canonical_context.previous_artifacts[artifact.artifact_id] = snapshot
        if self.run.canonical_context.active_artifact.get("artifact_id") == artifact.artifact_id:
            self.run.canonical_context.active_artifact = snapshot

    async def _fail_task(self, task: WorkflowTask, artifact_id: str, error: str) -> None:
        self.run.status = "failed"
        artifact = self.run.artifacts.get(artifact_id)
        if artifact:
            artifact.status = "failed"
            artifact.updated_at = datetime.now().isoformat()
            self._sync_artifact_snapshot(artifact)
        self.run.complete_task(
            task_id=task.task_id,
            task_type=task.task_type,
            target_agent=task.target_agent,
            artifact_id=artifact_id,
            status="failed",
            error=error,
        )
        await self._emit({
            "content": f"### 工作流停止\n{task.title or task.task_type}未通过：{error}",
            "current_agent": task.target_agent,
            "stage": task.task_type,
            "status": "failed",
            "last_error": error,
        })

    async def _should_pause_or_cancel(self) -> bool:
        if not self.pause_checker:
            return False
        return bool(await self.pause_checker())

    async def _emit(self, payload: Dict[str, Any]) -> None:
        self.run.set_current(
            agent=str(payload.get("current_agent") or self.run.current_agent),
            stage=str(payload.get("stage") or self.run.current_stage),
            status=str(payload.get("status") or self.run.status),
        )
        payload = {
            **payload,
            "created_files": self.run.created_files,
            "updated_files": self.run.updated_files,
            "reused_files": self.run.reused_files,
            "creative_workflow": self.run.to_dict(),
            "workflow_plan": self.run.workflow_plan.to_dict(),
            "task_queue": [task.to_dict() for task in self.run.task_queue],
            "completed_tasks": [task.to_dict() for task in self.run.completed_tasks],
            "reviews": [review.to_dict() for review in self.run.reviews],
            "handoff_notes": [handoff.to_dict() for handoff in self.run.handoff_notes],
        }
        if self.progress_emitter:
            await self.progress_emitter(self.run, payload)

    def _format_plan_message(self) -> str:
        lines = ["## 工作流计划"]
        visible_tasks = [task for task in self.run.task_queue if task.task_type != "prepare_context"]
        for index, task in enumerate(visible_tasks, 1):
            suffix = " -> 独立审查" if task.review_required else ""
            lines.append(f"{index}. {task.title or task.task_type}{suffix}")
        return "\n".join(lines)
