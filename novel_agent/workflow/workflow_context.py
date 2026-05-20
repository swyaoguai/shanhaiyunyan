"""Structured context objects for serial creative workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class WorkflowContext:
    """Single source of truth passed between creative workflow tasks."""

    original_request: str
    confirmed_requirements: Dict[str, Any] = field(default_factory=dict)
    project_snapshot: Dict[str, Any] = field(default_factory=dict)
    knowledge_snapshot: Dict[str, Any] = field(default_factory=dict)
    previous_artifacts: Dict[str, Any] = field(default_factory=dict)
    active_artifact: Dict[str, Any] = field(default_factory=dict)
    review_feedback: List[Dict[str, Any]] = field(default_factory=list)
    frozen_facts: List[str] = field(default_factory=list)
    forbidden_changes: List[str] = field(default_factory=list)
    user_interruptions: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_conflicts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Artifact:
    """Generated creative artifact recorded by the workflow run."""

    artifact_id: str
    artifact_type: str
    task_id: str
    content: Any
    status: str = "draft"
    target_path: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentHandoff:
    """Summary handed from one specialist agent to the next."""

    artifact_id: str
    artifact_type: str
    task_id: str = ""
    agent_name: str = ""
    context_snapshot_id: str = ""
    decisions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    new_facts: List[str] = field(default_factory=list)
    changed_facts: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    next_context_summary: str = ""
    artifact_refs: List[str] = field(default_factory=list)
    context_delta_id: str = ""
    consumed_context_keys: List[str] = field(default_factory=list)
    produced_context_keys: List[str] = field(default_factory=list)
    output_validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserInterruption:
    """User correction inserted while a workflow is running."""

    interruption_id: str
    message: str
    affected_categories: List[str] = field(default_factory=list)
    affected_task_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    status: str = "recorded"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
