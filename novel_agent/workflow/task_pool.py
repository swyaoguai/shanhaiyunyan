"""任务池与任务状态流转管理。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .contracts import TaskDefinition


def _now_iso() -> str:
    """返回当前 ISO8601 时间。"""
    return datetime.now().isoformat()


@dataclass(frozen=True)
class TaskStatus:
    """任务状态常量。"""

    PENDING: str = "pending"
    CLAIMED: str = "claimed"
    RUNNING: str = "running"
    BLOCKED: str = "blocked"
    REVIEW_REQUIRED: str = "review_required"
    COMPLETED: str = "completed"
    FAILED: str = "failed"
    ABORTED: str = "aborted"


VALID_TASK_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.CLAIMED,
    TaskStatus.RUNNING,
    TaskStatus.BLOCKED,
    TaskStatus.REVIEW_REQUIRED,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.ABORTED,
}


@dataclass
class TaskPoolSnapshot:
    """任务池快照。"""

    tasks: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tasks": list(self.tasks),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


class TaskPool:
    """监督式自组织任务池。"""

    def __init__(self, tasks: Optional[List[TaskDefinition]] = None) -> None:
        self._tasks: Dict[str, TaskDefinition] = {}
        self.created_at = _now_iso()
        self.updated_at = self.created_at
        self.metadata: Dict[str, Any] = {}
        self.status = TaskStatus()
        for task in tasks or []:
            self.add_task(task)

    def _touch(self) -> None:
        """刷新更新时间。"""
        self.updated_at = _now_iso()

    def add_task(self, task: TaskDefinition) -> TaskDefinition:
        """加入单个任务。"""
        if not isinstance(task, TaskDefinition):
            raise TypeError("task must be a TaskDefinition")
        task.touch()
        self._tasks[task.task_id] = task
        self._touch()
        return task

    def add_tasks(self, tasks: List[TaskDefinition]) -> List[TaskDefinition]:
        """批量加入任务。"""
        added: List[TaskDefinition] = []
        for task in tasks or []:
            added.append(self.add_task(task))
        return added

    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        """获取任务。"""
        return self._tasks.get(str(task_id or "").strip())

    def list_tasks(self) -> List[TaskDefinition]:
        """列出全部任务。"""
        return sorted(
            self._tasks.values(),
            key=lambda item: (-int(item.priority or 0), item.created_at, item.task_id),
        )

    def list_task_dicts(self) -> List[Dict[str, Any]]:
        """以字典形式列出全部任务。"""
        return [task.to_dict() for task in self.list_tasks()]

    def create_task(
        self,
        *,
        task_type: str,
        title: str = "",
        description: str = "",
        status: str = TaskStatus.PENDING,
        priority: int = 50,
        depends_on: Optional[List[str]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        expected_outputs: Optional[List[str]] = None,
        candidate_agents: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        review_required: bool = False,
    ) -> TaskDefinition:
        """快捷创建任务。"""
        task = TaskDefinition(
            task_type=str(task_type or "").strip(),
            title=str(title or "").strip(),
            description=str(description or "").strip(),
            status=self._normalize_status(status),
            priority=int(priority or 0),
            depends_on=[
                str(item).strip()
                for item in (depends_on or [])
                if str(item).strip()
            ],
            inputs=dict(inputs or {}),
            expected_outputs=[
                str(item).strip()
                for item in (expected_outputs or [])
                if str(item).strip()
            ],
            candidate_agents=[
                str(item).strip()
                for item in (candidate_agents or [])
                if str(item).strip()
            ],
            metadata=dict(metadata or {}),
            review_required=bool(review_required),
        )
        return self.add_task(task)

    def _normalize_status(self, status: str) -> str:
        normalized = str(status or "").strip()
        if normalized not in VALID_TASK_STATUSES:
            raise ValueError(f"Invalid task status: {status}")
        return normalized

    def update_task_status(
        self,
        task_id: str,
        status: str,
        *,
        assigned_agent: Optional[str] = None,
        result_ref: Optional[str] = None,
        metadata_patch: Optional[Dict[str, Any]] = None,
    ) -> TaskDefinition:
        """更新任务状态。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        task.status = self._normalize_status(status)
        if assigned_agent is not None:
            task.assigned_agent = str(assigned_agent or "").strip()
        if result_ref is not None:
            task.result_ref = str(result_ref or "").strip()
        if metadata_patch:
            task.metadata.update(dict(metadata_patch))
        task.touch()
        self._touch()
        return task

    def claim_task(self, task_id: str, agent_name: str) -> TaskDefinition:
        """认领任务。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        if task.status not in {self.status.PENDING, self.status.BLOCKED}:
            raise ValueError(f"Task cannot be claimed from status: {task.status}")
        return self.update_task_status(
            task_id,
            self.status.CLAIMED,
            assigned_agent=str(agent_name or "").strip(),
        )

    def start_task(self, task_id: str, agent_name: Optional[str] = None) -> TaskDefinition:
        """开始执行任务。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        if task.status not in {self.status.CLAIMED, self.status.PENDING}:
            raise ValueError(f"Task cannot start from status: {task.status}")
        return self.update_task_status(
            task_id,
            self.status.RUNNING,
            assigned_agent=agent_name if agent_name is not None else task.assigned_agent,
        )

    def complete_task(self, task_id: str, result_ref: str = "") -> TaskDefinition:
        """完成任务。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        return self.update_task_status(
            task_id,
            self.status.COMPLETED,
            result_ref=result_ref,
        )

    def block_task(self, task_id: str, reason: str = "") -> TaskDefinition:
        """阻塞任务。"""
        return self.update_task_status(
            task_id,
            self.status.BLOCKED,
            metadata_patch={"blocked_reason": str(reason or "").strip()},
        )

    def fail_task(self, task_id: str, error: str = "") -> TaskDefinition:
        """标记任务失败并累加重试次数。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        task.retry_count = int(task.retry_count or 0) + 1
        return self.update_task_status(
            task_id,
            self.status.FAILED,
            metadata_patch={"error": str(error or "").strip()},
        )

    def abort_task(self, task_id: str, reason: str = "") -> TaskDefinition:
        """中止任务。"""
        return self.update_task_status(
            task_id,
            self.status.ABORTED,
            metadata_patch={"abort_reason": str(reason or "").strip()},
        )

    def mark_review_required(self, task_id: str, note: str = "") -> TaskDefinition:
        """标记任务需要评审。"""
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        task.review_required = True
        return self.update_task_status(
            task_id,
            self.status.REVIEW_REQUIRED,
            metadata_patch={"review_note": str(note or "").strip()},
        )

    def get_ready_tasks(self) -> List[TaskDefinition]:
        """获取依赖已满足、可进入执行的任务。"""
        completed_ids = {
            task.task_id
            for task in self._tasks.values()
            if task.status == self.status.COMPLETED
        }

        ready: List[TaskDefinition] = []
        for task in self.list_tasks():
            if task.status not in {self.status.PENDING, self.status.BLOCKED}:
                continue
            dependencies_met = all(dep_id in completed_ids for dep_id in (task.depends_on or []))
            if dependencies_met:
                ready.append(task)
        return ready

    def get_blocked_tasks(self) -> List[TaskDefinition]:
        """获取阻塞任务。"""
        return [task for task in self.list_tasks() if task.status == self.status.BLOCKED]

    def get_tasks_by_status(self, status: str) -> List[TaskDefinition]:
        """按状态筛选任务。"""
        normalized_status = self._normalize_status(status)
        return [task for task in self.list_tasks() if task.status == normalized_status]

    def dependency_graph(self) -> Dict[str, List[str]]:
        """返回简化依赖图。"""
        return {
            task.task_id: list(task.depends_on or [])
            for task in self.list_tasks()
        }

    def to_snapshot(self) -> TaskPoolSnapshot:
        """导出任务池快照。"""
        return TaskPoolSnapshot(
            tasks=self.list_task_dicts(),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return self.to_snapshot().to_dict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPool":
        """从字典恢复任务池。"""
        tasks = [
            TaskDefinition.from_dict(item)
            for item in (data.get("tasks") or [])
            if isinstance(item, dict)
        ]
        pool = cls(tasks=tasks)
        pool.created_at = str(data.get("created_at") or pool.created_at).strip()
        pool.updated_at = str(data.get("updated_at") or pool.updated_at).strip()
        pool.metadata = dict(data.get("metadata") or {})
        return pool