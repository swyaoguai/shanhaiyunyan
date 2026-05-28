"""Persistent local collaborative run state.

This module provides a small LangGraph-like run ledger for the existing local
multi-agent workflow. It is intentionally dependency-free and stores state in
the current project's client_state directory through ProjectManager.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
import re
import uuid

from .runtime_events import to_jsonable


COLLAB_RUN_STATE_KEY = "collab_run_state"
MAX_RUN_MESSAGES = 500
MAX_RUN_CHECKPOINTS = 120
MAX_RUN_HANDOFFS = 300
MAX_RUN_ARTIFACTS = 300
MAX_MEMORY_ITEMS = 300


def _now_iso() -> str:
    return datetime.now().isoformat()


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _new_checkpoint_id() -> str:
    return f"ckpt-{uuid.uuid4().hex[:12]}"


def _compact_text(value: Any, limit: int = 800) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _summarize_value(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"type": "NoneType", "empty": True}
    if isinstance(value, str):
        return {
            "type": "str",
            "length": len(value),
            "preview": _compact_text(value, 240),
        }
    if isinstance(value, (list, tuple, set)):
        return {"type": type(value).__name__, "length": len(value)}
    if isinstance(value, dict):
        return {
            "type": "dict",
            "length": len(value),
            "keys": [str(key) for key in list(value.keys())[:12]],
        }
    return {"type": type(value).__name__, "preview": _compact_text(value, 240)}


def _compact_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(context or {})
    compact: Dict[str, Any] = {}
    for key in (
        "stage",
        "chapter_outline",
        "previous_summary",
        "context_strategy",
        "loaded_context",
        "permanent_memory",
        "aux_memory",
        "latest_chapter_content",
        "latest_polished_content",
        "latest_expanded_content",
        "latest_summary",
    ):
        if key in payload:
            compact[key] = _summarize_value(payload.get(key))
    if "source_of_truth" in payload and isinstance(payload.get("source_of_truth"), dict):
        compact["source_of_truth"] = dict(payload.get("source_of_truth") or {})
    return compact


def _append_limited(items: List[Dict[str, Any]], item: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    next_items = [dict(existing) for existing in items if isinstance(existing, dict)]
    next_items.append(dict(item or {}))
    if len(next_items) > limit:
        next_items = next_items[-limit:]
    return next_items


@dataclass
class CollabRunCheckpoint:
    """A recoverable node checkpoint in the local collaboration graph."""

    node: str
    status: str
    checkpoint_id: str = field(default_factory=_new_checkpoint_id)
    created_at: str = field(default_factory=_now_iso)
    task_id: str = ""
    task_type: str = ""
    agent_name: str = ""
    context_summary: Dict[str, Any] = field(default_factory=dict)
    task_pool_summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class CollabMemoryItem:
    """A structured memory item shared across tasks in one local project run."""

    key: str
    value: Any
    source_task_id: str = ""
    source_task_type: str = ""
    source_agent: str = ""
    scope: str = "project"
    summary: str = ""
    updated_at: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class CollabRunState:
    """Serializable local collaboration state for one project."""

    run_id: str = field(default_factory=_new_run_id)
    project_id: str = ""
    session_id: str = ""
    status: str = "idle"
    current_node: str = ""
    current_task_id: str = ""
    current_task_type: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    handoffs: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    shared_memory: Dict[str, Any] = field(default_factory=lambda: {"items": {}, "updated_at": ""})
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CollabRunState":
        data = dict(payload or {})
        state = cls(
            run_id=str(data.get("run_id") or _new_run_id()).strip(),
            project_id=str(data.get("project_id") or "").strip(),
            session_id=str(data.get("session_id") or "").strip(),
            status=str(data.get("status") or "idle").strip() or "idle",
            current_node=str(data.get("current_node") or "").strip(),
            current_task_id=str(data.get("current_task_id") or "").strip(),
            current_task_type=str(data.get("current_task_type") or "").strip(),
            created_at=str(data.get("created_at") or _now_iso()).strip(),
            updated_at=str(data.get("updated_at") or _now_iso()).strip(),
            checkpoints=[dict(item) for item in data.get("checkpoints", []) if isinstance(item, dict)],
            messages=[dict(item) for item in data.get("messages", []) if isinstance(item, dict)],
            handoffs=[dict(item) for item in data.get("handoffs", []) if isinstance(item, dict)],
            artifacts=[dict(item) for item in data.get("artifacts", []) if isinstance(item, dict)],
            shared_memory=dict(data.get("shared_memory") or {"items": {}, "updated_at": ""}),
            metadata=dict(data.get("metadata") or {}),
        )
        if not isinstance(state.shared_memory.get("items"), dict):
            state.shared_memory["items"] = {}
        return state


class CollabRunStateStore:
    """Project-scoped collaboration run ledger and shared memory store."""

    def __init__(
        self,
        *,
        project_manager_provider: Callable[[], Any],
        project_dir_provider: Callable[[], Path],
    ) -> None:
        self.project_manager_provider = project_manager_provider
        self.project_dir_provider = project_dir_provider

    def _get_project_manager(self) -> Any:
        return self.project_manager_provider()

    def _get_project_id(self) -> str:
        manager = self._get_project_manager()
        return str(getattr(manager, "current_project_id", "") or "").strip()

    def _load(self) -> CollabRunState:
        manager = self._get_project_manager()
        payload = manager.load_project_state(COLLAB_RUN_STATE_KEY, default={})
        if isinstance(payload, dict) and payload:
            return CollabRunState.from_dict(payload)
        return CollabRunState(project_id=self._get_project_id())

    def _save(self, state: CollabRunState) -> Dict[str, Any]:
        state.updated_at = _now_iso()
        payload = state.to_dict()
        self._get_project_manager().save_project_state(COLLAB_RUN_STATE_KEY, payload)
        return payload

    def ensure_run(
        self,
        *,
        run_id: str = "",
        session_id: str = "",
        status: str = "running",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self._load()
        if run_id and state.run_id != run_id:
            state = CollabRunState(
                run_id=str(run_id).strip(),
                project_id=self._get_project_id(),
                session_id=str(session_id or "").strip(),
                status=str(status or "running").strip() or "running",
            )
        if not state.project_id:
            state.project_id = self._get_project_id()
        if session_id:
            state.session_id = str(session_id or "").strip()
        if status:
            state.status = str(status or "").strip()
        if isinstance(metadata, dict) and metadata:
            state.metadata.update(to_jsonable(metadata))
        return self._save(state)

    def load_state(self) -> Dict[str, Any]:
        return self._load().to_dict()

    def build_context_overlay(self) -> Dict[str, Any]:
        state = self._load()
        memory_items = state.shared_memory.get("items") if isinstance(state.shared_memory, dict) else {}
        return {
            "collab_run": {
                "run_id": state.run_id,
                "status": state.status,
                "current_node": state.current_node,
                "current_task_id": state.current_task_id,
                "recent_handoffs": state.handoffs[-5:],
                "recent_artifacts": state.artifacts[-5:],
            },
            "shared_memory": {
                "items": dict(memory_items or {}),
                "updated_at": str((state.shared_memory or {}).get("updated_at") or ""),
            },
        }

    def merge_context_overlay(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(context or {})
        overlay = self.build_context_overlay()
        payload.setdefault("collab_run", overlay["collab_run"])
        payload.setdefault("shared_memory", overlay["shared_memory"])
        return payload

    def record_checkpoint(
        self,
        *,
        node: str,
        status: str,
        task_id: str = "",
        task_type: str = "",
        agent_name: str = "",
        context: Optional[Dict[str, Any]] = None,
        task_pool: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self._load()
        if status == "failed":
            state.status = "failed"
        elif str(node or "").strip() in {"workflow_end", "completed"} and status == "completed":
            state.status = "completed"
        elif state.status not in {"failed", "completed"}:
            state.status = "running"
        state.current_node = str(node or "").strip()
        state.current_task_id = str(task_id or "").strip()
        state.current_task_type = str(task_type or "").strip()

        tasks = []
        if isinstance(task_pool, dict):
            tasks = [
                {
                    "task_id": str(item.get("task_id") or "").strip(),
                    "task_type": str(item.get("task_type") or "").strip(),
                    "status": str(item.get("status") or "").strip(),
                    "assigned_agent": str(item.get("assigned_agent") or "").strip(),
                }
                for item in task_pool.get("tasks", [])
                if isinstance(item, dict)
            ]
        checkpoint = CollabRunCheckpoint(
            node=str(node or "").strip(),
            status=str(status or "").strip(),
            task_id=str(task_id or "").strip(),
            task_type=str(task_type or "").strip(),
            agent_name=str(agent_name or "").strip(),
            context_summary=_compact_context(context),
            task_pool_summary={"task_count": len(tasks), "tasks": tasks[-20:]},
            metadata=to_jsonable(dict(metadata or {})),
        ).to_dict()
        state.checkpoints = _append_limited(state.checkpoints, checkpoint, MAX_RUN_CHECKPOINTS)
        self._save(state)
        return checkpoint

    def append_runtime_event(self, event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        state = self._load()
        message = {
            "message_id": str(event.get("event_id") or f"msg-{uuid.uuid4().hex[:12]}"),
            "type": str(event.get("type") or "").strip(),
            "created_at": str(event.get("timestamp") or _now_iso()).strip(),
            "task_id": str(event.get("task_id") or "").strip(),
            "task_type": str(event.get("task_type") or "").strip(),
            "agent_name": str(event.get("agent_name") or "").strip(),
            "trace_id": str(event.get("trace_id") or "").strip(),
            "content": to_jsonable(event.get("payload", {})),
        }
        state.messages = _append_limited(state.messages, message, MAX_RUN_MESSAGES)
        if message["type"]:
            state.current_node = message["type"]
        if message["task_id"]:
            state.current_task_id = message["task_id"]
        if message["task_type"]:
            state.current_task_type = message["task_type"]
        self._save(state)

    def append_runtime_events(self, events: Iterable[Dict[str, Any]]) -> None:
        for event in events:
            self.append_runtime_event(event)

    def append_handoff(self, handoff: Dict[str, Any]) -> None:
        if not isinstance(handoff, dict) or not handoff.get("task_id"):
            return
        state = self._load()
        state.handoffs = _append_limited(state.handoffs, to_jsonable(handoff), MAX_RUN_HANDOFFS)
        self._save(state)

    def append_artifact(
        self,
        *,
        task_id: str,
        task_type: str,
        agent_name: str,
        artifact_refs: List[str],
        result_keys: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not task_id and not artifact_refs:
            return
        state = self._load()
        artifact = {
            "artifact_id": f"art-{uuid.uuid4().hex[:12]}",
            "task_id": str(task_id or "").strip(),
            "task_type": str(task_type or "").strip(),
            "agent_name": str(agent_name or "").strip(),
            "artifact_refs": [str(item) for item in artifact_refs if str(item or "").strip()],
            "result_keys": [str(item) for item in (result_keys or []) if str(item or "").strip()],
            "created_at": _now_iso(),
            "metadata": to_jsonable(dict(metadata or {})),
        }
        state.artifacts = _append_limited(state.artifacts, artifact, MAX_RUN_ARTIFACTS)
        self._save(state)

    def upsert_memory_from_context(
        self,
        *,
        context: Dict[str, Any],
        task_id: str,
        task_type: str,
        agent_name: str,
        context_delta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self._load()
        memory_items = dict((state.shared_memory or {}).get("items") or {})
        context_payload = dict(context or {})
        changed_keys = []
        if isinstance(context_delta, dict):
            changed_keys = list(context_delta.get("added_keys") or []) + list(context_delta.get("updated_keys") or [])
        candidate_keys = [
            "permanent_memory",
            "aux_memory",
            "loaded_context",
            "context_strategy",
            "latest_chapter_content",
            "latest_word_count",
            "latest_polished_content",
            "latest_expanded_content",
            "latest_summary",
            "latest_summary_payload",
            "latest_evaluation",
        ]
        for key in candidate_keys:
            if key not in context_payload or context_payload.get(key) in (None, "", [], {}):
                continue
            if changed_keys and key not in changed_keys and key not in {"permanent_memory", "aux_memory"}:
                continue
            value = context_payload.get(key)
            memory_item = CollabMemoryItem(
                key=key,
                value=to_jsonable(value),
                source_task_id=str(task_id or "").strip(),
                source_task_type=str(task_type or "").strip(),
                source_agent=str(agent_name or "").strip(),
                summary=str((_summarize_value(value)).get("preview") or _summarize_value(value).get("type") or ""),
                metadata={
                    "context_delta_id": str((context_delta or {}).get("delta_id") or "").strip(),
                    "value_summary": _summarize_value(value),
                },
            ).to_dict()
            memory_items[key] = memory_item

        if len(memory_items) > MAX_MEMORY_ITEMS:
            ordered = sorted(
                memory_items.items(),
                key=lambda item: str((item[1] or {}).get("updated_at") or ""),
            )
            memory_items = dict(ordered[-MAX_MEMORY_ITEMS:])
        state.shared_memory = {"items": memory_items, "updated_at": _now_iso()}
        self._save(state)
        return state.shared_memory

    def mark_completed(self) -> Dict[str, Any]:
        state = self._load()
        state.status = "completed"
        state.current_node = "completed"
        return self._save(state)

    def mark_failed(self, error: str = "") -> Dict[str, Any]:
        state = self._load()
        state.status = "failed"
        state.current_node = "failed"
        if error:
            state.metadata["error"] = str(error)
        return self._save(state)
