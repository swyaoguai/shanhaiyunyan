"""Serial creative workflow run model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .artifact_review import ReviewIssue, ReviewResult
from .user_interruptions import build_user_interruption
from .workflow_context import AgentHandoff, Artifact, UserInterruption, WorkflowContext
from .workflow_planner import WorkflowPlan, WorkflowTask


@dataclass
class WorkflowTaskResult:
    task_id: str
    task_type: str
    target_agent: str
    status: str
    artifact_id: str = ""
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CreativeWorkflowRun:
    run_id: str
    project_id: str
    status: str
    user_request: str
    workflow_plan: WorkflowPlan
    canonical_context: WorkflowContext
    task_queue: List[WorkflowTask] = field(default_factory=list)
    completed_tasks: List[WorkflowTaskResult] = field(default_factory=list)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    reviews: List[ReviewResult] = field(default_factory=list)
    handoff_notes: List[AgentHandoff] = field(default_factory=list)
    user_interruptions: List[UserInterruption] = field(default_factory=list)
    created_files: List[Dict[str, Any]] = field(default_factory=list)
    updated_files: List[Dict[str, Any]] = field(default_factory=list)
    reused_files: List[Dict[str, Any]] = field(default_factory=list)
    current_agent: str = "Coordinator"
    current_stage: str = "starting"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        user_request: str,
        workflow_plan: WorkflowPlan,
        canonical_context: WorkflowContext,
        run_id: Optional[str] = None,
    ) -> "CreativeWorkflowRun":
        return cls(
            run_id=run_id or f"creative-{uuid4().hex[:12]}",
            project_id=str(project_id or "").strip(),
            status="running",
            user_request=str(user_request or "").strip(),
            workflow_plan=workflow_plan,
            canonical_context=canonical_context,
            task_queue=[task for task in workflow_plan.tasks],
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CreativeWorkflowRun":
        payload = payload if isinstance(payload, dict) else {}
        workflow_plan = _workflow_plan_from_dict(payload.get("workflow_plan"))
        canonical_context = _workflow_context_from_dict(payload.get("canonical_context"))
        run = cls(
            run_id=str(payload.get("run_id") or f"creative-{uuid4().hex[:12]}").strip(),
            project_id=str(payload.get("project_id") or "").strip(),
            status=str(payload.get("status") or "running").strip() or "running",
            user_request=str(payload.get("user_request") or "").strip(),
            workflow_plan=workflow_plan,
            canonical_context=canonical_context,
            task_queue=[_workflow_task_from_dict(item) for item in payload.get("task_queue") or workflow_plan.tasks],
            completed_tasks=[
                _workflow_task_result_from_dict(item)
                for item in payload.get("completed_tasks") or []
                if isinstance(item, dict)
            ],
            artifacts={
                str(key): _artifact_from_dict(value)
                for key, value in (payload.get("artifacts") or {}).items()
                if isinstance(value, dict)
            },
            reviews=[
                _review_result_from_dict(item)
                for item in payload.get("reviews") or []
                if isinstance(item, dict)
            ],
            handoff_notes=[
                _agent_handoff_from_dict(item)
                for item in payload.get("handoff_notes") or []
                if isinstance(item, dict)
            ],
            user_interruptions=[
                _user_interruption_from_dict(item)
                for item in payload.get("user_interruptions") or []
                if isinstance(item, dict)
            ],
            created_files=[dict(item) for item in payload.get("created_files") or [] if isinstance(item, dict)],
            updated_files=[dict(item) for item in payload.get("updated_files") or [] if isinstance(item, dict)],
            reused_files=[dict(item) for item in payload.get("reused_files") or [] if isinstance(item, dict)],
            current_agent=str(payload.get("current_agent") or "Coordinator").strip() or "Coordinator",
            current_stage=str(payload.get("current_stage") or "starting").strip() or "starting",
            started_at=str(payload.get("started_at") or datetime.now().isoformat()).strip(),
            updated_at=str(payload.get("updated_at") or datetime.now().isoformat()).strip(),
        )
        for artifact in run.artifacts.values():
            run.canonical_context.previous_artifacts[artifact.artifact_id] = artifact.to_dict()
        if run.artifacts and not run.canonical_context.active_artifact:
            run.canonical_context.active_artifact = list(run.artifacts.values())[-1].to_dict()
        return run

    def apply_user_interruption(self, message: str) -> UserInterruption:
        interruption = build_user_interruption(message)
        affected = set(interruption.affected_categories)
        first_affected_index: Optional[int] = None
        for index, task in enumerate(self.task_queue):
            if task.task_type in affected:
                first_affected_index = index
                break

        affected_task_ids: List[str] = []
        if first_affected_index is not None:
            for task in self.task_queue[first_affected_index:]:
                if task.task_type == "prepare_context":
                    continue
                task.status = "pending"
                task.retry_count = 0
                affected_task_ids.append(task.task_id)
            affected_types = {task.task_type for task in self.task_queue[first_affected_index:]}
        else:
            affected_types = affected

        for artifact in self.artifacts.values():
            if artifact.artifact_type in affected_types and artifact.status == "committed":
                artifact.status = "revision_requested"
                artifact.updated_at = datetime.now().isoformat()
                self.canonical_context.previous_artifacts[artifact.artifact_id] = artifact.to_dict()

        interruption.affected_task_ids = affected_task_ids
        self.user_interruptions.append(interruption)
        self.canonical_context.user_interruptions.append(interruption.to_dict())
        self.canonical_context.review_feedback.append({
            "type": "user_interruption",
            "message": interruption.message,
            "affected_categories": interruption.affected_categories,
            "affected_task_ids": affected_task_ids,
            "created_at": interruption.created_at,
        })
        self.status = "paused"
        self.current_agent = "Coordinator"
        self.current_stage = "user_interruption"
        self.updated_at = datetime.now().isoformat()
        return interruption

    def mark_task(self, task_id: str, status: str) -> None:
        for task in self.task_queue:
            if task.task_id == task_id:
                task.status = status
                break
        self.updated_at = datetime.now().isoformat()

    def complete_task(
        self,
        *,
        task_id: str,
        task_type: str,
        target_agent: str,
        artifact_id: str = "",
        status: str = "completed",
        error: str = "",
    ) -> None:
        self.mark_task(task_id, status)
        self.completed_tasks.append(
            WorkflowTaskResult(
                task_id=task_id,
                task_type=task_type,
                target_agent=target_agent,
                status=status,
                artifact_id=artifact_id,
                error=error,
                completed_at=datetime.now().isoformat(),
            )
        )

    def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts[artifact.artifact_id] = artifact
        self.canonical_context.previous_artifacts[artifact.artifact_id] = artifact.to_dict()
        self.canonical_context.active_artifact = artifact.to_dict()
        self.updated_at = datetime.now().isoformat()

    def add_review(self, review: ReviewResult) -> None:
        self.reviews.append(review)
        self.canonical_context.review_feedback.append(review.to_dict())
        self.updated_at = datetime.now().isoformat()

    def add_handoff(self, handoff: AgentHandoff) -> None:
        self.handoff_notes.append(handoff)
        self.updated_at = datetime.now().isoformat()

    def set_current(self, *, agent: str, stage: str, status: Optional[str] = None) -> None:
        self.current_agent = str(agent or self.current_agent).strip() or self.current_agent
        self.current_stage = str(stage or self.current_stage).strip() or self.current_stage
        if status:
            self.status = str(status).strip()
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status,
            "user_request": self.user_request,
            "workflow_plan": self.workflow_plan.to_dict(),
            "canonical_context": self.canonical_context.to_dict(),
            "task_queue": [task.to_dict() for task in self.task_queue],
            "completed_tasks": [task.to_dict() for task in self.completed_tasks],
            "artifacts": {key: artifact.to_dict() for key, artifact in self.artifacts.items()},
            "reviews": [review.to_dict() for review in self.reviews],
            "handoff_notes": [handoff.to_dict() for handoff in self.handoff_notes],
            "user_interruptions": [item.to_dict() for item in self.user_interruptions],
            "created_files": self.created_files,
            "updated_files": self.updated_files,
            "reused_files": self.reused_files,
            "current_agent": self.current_agent,
            "current_stage": self.current_stage,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


def _workflow_task_from_dict(payload: Any) -> WorkflowTask:
    if isinstance(payload, WorkflowTask):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return WorkflowTask(
        task_id=str(payload.get("task_id") or "").strip(),
        task_type=str(payload.get("task_type") or "").strip(),
        target_agent=str(payload.get("target_agent") or "").strip(),
        input_refs=[str(item) for item in payload.get("input_refs") or []],
        output_type=str(payload.get("output_type") or "").strip(),
        status=str(payload.get("status") or "pending").strip() or "pending",
        retry_count=int(payload.get("retry_count") or 0),
        max_retries=int(payload.get("max_retries") or 1),
        review_required=bool(payload.get("review_required", True)),
        user_confirmation_required=bool(payload.get("user_confirmation_required", False)),
        title=str(payload.get("title") or "").strip(),
    )


def _workflow_plan_from_dict(payload: Any) -> WorkflowPlan:
    if isinstance(payload, WorkflowPlan):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    tasks = [_workflow_task_from_dict(item) for item in payload.get("tasks") or [] if isinstance(item, dict)]
    return WorkflowPlan(
        plan_id=str(payload.get("plan_id") or "plan-creative-serial").strip(),
        operation=str(payload.get("operation") or "create").strip() or "create",
        target_categories=[str(item) for item in payload.get("target_categories") or [] if str(item).strip()],
        tasks=tasks,
    )


def _workflow_context_from_dict(payload: Any) -> WorkflowContext:
    if isinstance(payload, WorkflowContext):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return WorkflowContext(
        original_request=str(payload.get("original_request") or "").strip(),
        confirmed_requirements=dict(payload.get("confirmed_requirements") or {}),
        project_snapshot=dict(payload.get("project_snapshot") or {}),
        knowledge_snapshot=dict(payload.get("knowledge_snapshot") or {}),
        previous_artifacts=dict(payload.get("previous_artifacts") or {}),
        active_artifact=dict(payload.get("active_artifact") or {}),
        review_feedback=[dict(item) for item in payload.get("review_feedback") or [] if isinstance(item, dict)],
        frozen_facts=[str(item) for item in payload.get("frozen_facts") or []],
        forbidden_changes=[str(item) for item in payload.get("forbidden_changes") or []],
        user_interruptions=[dict(item) for item in payload.get("user_interruptions") or [] if isinstance(item, dict)],
        unresolved_conflicts=[dict(item) for item in payload.get("unresolved_conflicts") or [] if isinstance(item, dict)],
    )


def _artifact_from_dict(payload: Any) -> Artifact:
    if isinstance(payload, Artifact):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return Artifact(
        artifact_id=str(payload.get("artifact_id") or "").strip(),
        artifact_type=str(payload.get("artifact_type") or "").strip(),
        task_id=str(payload.get("task_id") or "").strip(),
        content=payload.get("content"),
        status=str(payload.get("status") or "draft").strip() or "draft",
        target_path=str(payload.get("target_path") or "").strip(),
        created_at=str(payload.get("created_at") or "").strip(),
        updated_at=str(payload.get("updated_at") or "").strip(),
    )


def _review_result_from_dict(payload: Any) -> ReviewResult:
    if isinstance(payload, ReviewResult):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return ReviewResult(
        task_id=str(payload.get("task_id") or "").strip(),
        artifact_id=str(payload.get("artifact_id") or "").strip(),
        artifact_type=str(payload.get("artifact_type") or "").strip(),
        passed=bool(payload.get("passed")),
        severity=str(payload.get("severity") or "none").strip() or "none",
        issues=[
            ReviewIssue(type=str(item.get("type") or "").strip(), message=str(item.get("message") or "").strip())
            for item in payload.get("issues") or []
            if isinstance(item, dict)
        ],
        conflicts=[dict(item) for item in payload.get("conflicts") or [] if isinstance(item, dict)],
        missing_info=[str(item) for item in payload.get("missing_info") or []],
        revision_target=str(payload.get("revision_target") or "").strip(),
        revision_instructions=str(payload.get("revision_instructions") or "").strip(),
        requires_user_confirmation=bool(payload.get("requires_user_confirmation", False)),
    )


def _agent_handoff_from_dict(payload: Any) -> AgentHandoff:
    if isinstance(payload, AgentHandoff):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return AgentHandoff(
        artifact_id=str(payload.get("artifact_id") or "").strip(),
        artifact_type=str(payload.get("artifact_type") or "").strip(),
        decisions=[str(item) for item in payload.get("decisions") or []],
        dependencies=[str(item) for item in payload.get("dependencies") or []],
        new_facts=[str(item) for item in payload.get("new_facts") or []],
        changed_facts=[str(item) for item in payload.get("changed_facts") or []],
        risks=[str(item) for item in payload.get("risks") or []],
        next_context_summary=str(payload.get("next_context_summary") or "").strip(),
    )


def _user_interruption_from_dict(payload: Any) -> UserInterruption:
    if isinstance(payload, UserInterruption):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return UserInterruption(
        interruption_id=str(payload.get("interruption_id") or "").strip(),
        message=str(payload.get("message") or "").strip(),
        affected_categories=[str(item) for item in payload.get("affected_categories") or []],
        affected_task_ids=[str(item) for item in payload.get("affected_task_ids") or []],
        created_at=str(payload.get("created_at") or "").strip(),
        status=str(payload.get("status") or "recorded").strip() or "recorded",
    )


def _workflow_task_result_from_dict(payload: Any) -> WorkflowTaskResult:
    if isinstance(payload, WorkflowTaskResult):
        return payload
    payload = payload if isinstance(payload, dict) else {}
    return WorkflowTaskResult(
        task_id=str(payload.get("task_id") or "").strip(),
        task_type=str(payload.get("task_type") or "").strip(),
        target_agent=str(payload.get("target_agent") or "").strip(),
        status=str(payload.get("status") or "").strip(),
        artifact_id=str(payload.get("artifact_id") or "").strip(),
        error=str(payload.get("error") or "").strip(),
        started_at=str(payload.get("started_at") or "").strip(),
        completed_at=str(payload.get("completed_at") or "").strip(),
    )
