"""Typed runtime messages and artifact envelopes for local agent workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import uuid

from .runtime_events import normalize_runtime_event_type, to_jsonable


RuntimeMessageRole = str
RuntimeMessageType = str
ArtifactType = str

TEXT_MESSAGE: RuntimeMessageType = "text"
WORKFLOW_MESSAGE: RuntimeMessageType = "workflow"
TASK_MESSAGE: RuntimeMessageType = "task"
ARTIFACT_MESSAGE: RuntimeMessageType = "artifact"
HANDOFF_MESSAGE: RuntimeMessageType = "handoff"
CONTEXT_DELTA_MESSAGE: RuntimeMessageType = "context_delta"
ERROR_MESSAGE: RuntimeMessageType = "error"


EVENT_MESSAGE_TYPE_MAP: Dict[str, RuntimeMessageType] = {
    "workflow_start": WORKFLOW_MESSAGE,
    "workflow_end": WORKFLOW_MESSAGE,
    "contract_confirmation": WORKFLOW_MESSAGE,
    "contract_rejection": WORKFLOW_MESSAGE,
    "route_start": TASK_MESSAGE,
    "route_end": TASK_MESSAGE,
    "task_created": TASK_MESSAGE,
    "task_registered": TASK_MESSAGE,
    "task_claimed": TASK_MESSAGE,
    "task_started": TASK_MESSAGE,
    "task_start": TASK_MESSAGE,
    "task_completed": TASK_MESSAGE,
    "task_end": TASK_MESSAGE,
    "task_progress": TASK_MESSAGE,
    "validation_start": TASK_MESSAGE,
    "validation_end": TASK_MESSAGE,
    "fallback_start": TASK_MESSAGE,
    "fallback_end": TASK_MESSAGE,
    "task_fallback_started": TASK_MESSAGE,
    "artifact_created": ARTIFACT_MESSAGE,
    "artifact_updated": ARTIFACT_MESSAGE,
    "handoff_created": HANDOFF_MESSAGE,
    "context_delta_created": CONTEXT_DELTA_MESSAGE,
    "task_failed": ERROR_MESSAGE,
    "task_rejected": ERROR_MESSAGE,
    "task_blocked": ERROR_MESSAGE,
    "user_input_required": ERROR_MESSAGE,
}


def _now_iso(now_provider: Optional[Callable[[], datetime]] = None) -> str:
    return (now_provider or datetime.now)().isoformat()


def _new_message_id() -> str:
    return f"msg-{uuid.uuid4().hex}"


def _new_artifact_id() -> str:
    return f"art-{uuid.uuid4().hex}"


def _compact_text(value: str, *, limit: int = 2000) -> Any:
    if len(value) <= limit:
        return value
    compact = value.strip().replace("\r\n", "\n").replace("\r", "\n")
    return {
        "type": "str",
        "length": len(value),
        "preview": compact[:limit],
        "truncated": True,
    }


def _compact_content(value: Any) -> Any:
    if isinstance(value, str):
        return _compact_text(value)
    if isinstance(value, dict):
        return {str(key): _compact_content(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_compact_content(item) for item in value]
    return to_jsonable(value)


def runtime_message_type_for_event(event_type: str) -> RuntimeMessageType:
    """Return the frontend renderer type for a runtime/legacy event."""
    raw_type = str(event_type or "").strip() or "unknown"
    normalized_type = normalize_runtime_event_type(raw_type)
    return EVENT_MESSAGE_TYPE_MAP.get(raw_type) or EVENT_MESSAGE_TYPE_MAP.get(normalized_type) or TEXT_MESSAGE


def runtime_message_role_for_type(message_type: str) -> RuntimeMessageRole:
    normalized = str(message_type or "").strip()
    if normalized == ARTIFACT_MESSAGE:
        return "artifact"
    if normalized in {HANDOFF_MESSAGE, CONTEXT_DELTA_MESSAGE}:
        return "agent"
    if normalized == ERROR_MESSAGE:
        return "system"
    return "event"


@dataclass
class AgentRuntimeMessage:
    """Frontend-facing typed message envelope."""

    role: RuntimeMessageRole
    type: RuntimeMessageType
    content: Any
    message_id: str = field(default_factory=_new_message_id)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    trace_id: str = ""
    task_id: str = ""
    agent_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class ArtifactEnvelope:
    """Typed artifact envelope used by runtime events and frontend renderers."""

    artifact_type: ArtifactType
    content: Any
    artifact_id: str = field(default_factory=_new_artifact_id)
    title: str = ""
    refs: List[str] = field(default_factory=list)
    created_by: str = ""
    task_id: str = ""
    trace_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


def make_runtime_message(
    *,
    role: RuntimeMessageRole,
    message_type: RuntimeMessageType,
    content: Any,
    trace_id: str = "",
    task_id: str = "",
    agent_name: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    created_at: str = "",
    now_provider: Optional[Callable[[], datetime]] = None,
) -> AgentRuntimeMessage:
    """Create a JSON-safe typed runtime message."""
    return AgentRuntimeMessage(
        role=str(role or "event").strip() or "event",
        type=str(message_type or TEXT_MESSAGE).strip() or TEXT_MESSAGE,
        content=to_jsonable(content),
        created_at=str(created_at or "").strip() or _now_iso(now_provider),
        trace_id=str(trace_id or "").strip(),
        task_id=str(task_id or "").strip(),
        agent_name=str(agent_name or "").strip(),
        metadata=to_jsonable(dict(metadata or {})),
    )


def make_artifact_envelope(
    *,
    artifact_type: ArtifactType,
    content: Any,
    refs: Optional[List[Any]] = None,
    created_by: str = "",
    task_id: str = "",
    trace_id: str = "",
    title: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    created_at: str = "",
    now_provider: Optional[Callable[[], datetime]] = None,
) -> ArtifactEnvelope:
    """Create a compact, JSON-safe artifact envelope."""
    normalized_refs = [
        str(item or "").strip()
        for item in (refs or [])
        if str(item or "").strip()
    ]
    return ArtifactEnvelope(
        artifact_type=str(artifact_type or "task_output").strip() or "task_output",
        title=str(title or "").strip(),
        content=_compact_content(content),
        refs=normalized_refs,
        created_by=str(created_by or "").strip(),
        task_id=str(task_id or "").strip(),
        trace_id=str(trace_id or "").strip(),
        created_at=str(created_at or "").strip() or _now_iso(now_provider),
        metadata=to_jsonable(dict(metadata or {})),
    )


def make_runtime_message_for_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    trace_id: str = "",
    task_id: str = "",
    agent_name: str = "",
    created_at: str = "",
    run_id: str = "",
    now_provider: Optional[Callable[[], datetime]] = None,
) -> AgentRuntimeMessage:
    """Build a typed message from a legacy/runtime event payload."""
    event_payload = to_jsonable(dict(payload or {}))
    message_type = runtime_message_type_for_event(event_type)
    resolved_task_id = str(task_id or event_payload.get("task_id") or "").strip()
    resolved_agent = str(
        agent_name
        or event_payload.get("agent_name")
        or event_payload.get("assigned_agent")
        or event_payload.get("agent")
        or event_payload.get("current_agent")
        or ""
    ).strip()
    resolved_trace_id = str(
        trace_id
        or event_payload.get("trace_id")
        or event_payload.get("context_snapshot_id")
        or resolved_task_id
        or ""
    ).strip()
    resolved_created_at = str(
        created_at
        or event_payload.get("created_at")
        or event_payload.get("timestamp")
        or ""
    ).strip()
    normalized_event_type = normalize_runtime_event_type(event_type)
    content = {
        key: value
        for key, value in event_payload.items()
        if key not in {"runtime_message"}
    }
    content.setdefault("event_type", normalized_event_type)
    return make_runtime_message(
        role=runtime_message_role_for_type(message_type),
        message_type=message_type,
        content=content,
        trace_id=resolved_trace_id,
        task_id=resolved_task_id,
        agent_name=resolved_agent,
        created_at=resolved_created_at,
        metadata={
            "event_type": normalized_event_type,
            "legacy_type": str(event_type or "").strip(),
            "run_id": str(run_id or event_payload.get("run_id") or "").strip(),
        },
        now_provider=now_provider,
    )


def attach_runtime_message(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    trace_id: str = "",
    task_id: str = "",
    agent_name: str = "",
    run_id: str = "",
    now_provider: Optional[Callable[[], datetime]] = None,
) -> Dict[str, Any]:
    """Return an event payload enriched with runtime_message and artifact envelope."""
    event_payload = to_jsonable(dict(payload or {}))
    runtime_type = normalize_runtime_event_type(event_type)
    resolved_trace_id = str(
        trace_id
        or event_payload.get("trace_id")
        or event_payload.get("context_snapshot_id")
        or event_payload.get("task_id")
        or ""
    ).strip()
    resolved_task_id = str(task_id or event_payload.get("task_id") or "").strip()
    resolved_agent = str(
        agent_name
        or event_payload.get("agent_name")
        or event_payload.get("assigned_agent")
        or event_payload.get("agent")
        or ""
    ).strip()

    if runtime_type in {"artifact_created", "artifact_updated"} and not isinstance(event_payload.get("artifact"), dict):
        refs = event_payload.get("artifact_refs")
        refs_list = refs if isinstance(refs, list) else []
        artifact_content = {
            "result_keys": event_payload.get("result_keys", []),
            "context_snapshot_id": event_payload.get("context_snapshot_id", ""),
            "fallback_used": bool(event_payload.get("fallback_used")),
        }
        event_payload["artifact"] = make_artifact_envelope(
            artifact_type=str(event_payload.get("artifact_type") or event_payload.get("task_type") or "task_output"),
            title=str(event_payload.get("title") or event_payload.get("task_type") or "任务产物"),
            content=artifact_content,
            refs=refs_list,
            created_by=resolved_agent,
            task_id=resolved_task_id,
            trace_id=resolved_trace_id,
            metadata={
                "event_type": runtime_type,
                "result_keys": event_payload.get("result_keys", []),
            },
            created_at=str(event_payload.get("created_at") or event_payload.get("timestamp") or ""),
            now_provider=now_provider,
        ).to_dict()

    if not isinstance(event_payload.get("runtime_message"), dict):
        event_payload["runtime_message"] = make_runtime_message_for_event(
            event_type,
            event_payload,
            trace_id=resolved_trace_id,
            task_id=resolved_task_id,
            agent_name=resolved_agent,
            run_id=run_id,
            now_provider=now_provider,
        ).to_dict()
    return event_payload
