"""标准化本地多 Agent 运行时事件。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
import uuid


RuntimeEventType = str

WORKFLOW_START: RuntimeEventType = "workflow_start"
WORKFLOW_END: RuntimeEventType = "workflow_end"
TASK_CREATED: RuntimeEventType = "task_created"
TASK_CLAIMED: RuntimeEventType = "task_claimed"
TASK_START: RuntimeEventType = "task_start"
TASK_PROGRESS: RuntimeEventType = "task_progress"
TASK_END: RuntimeEventType = "task_end"
TASK_FAILED: RuntimeEventType = "task_failed"
TASK_BLOCKED: RuntimeEventType = "task_blocked"
ROUTE_START: RuntimeEventType = "route_start"
ROUTE_END: RuntimeEventType = "route_end"
MESSAGE_START: RuntimeEventType = "message_start"
MESSAGE_DELTA: RuntimeEventType = "message_delta"
MESSAGE_END: RuntimeEventType = "message_end"
ARTIFACT_CREATED: RuntimeEventType = "artifact_created"
ARTIFACT_UPDATED: RuntimeEventType = "artifact_updated"
HANDOFF_CREATED: RuntimeEventType = "handoff_created"
CONTEXT_DELTA_CREATED: RuntimeEventType = "context_delta_created"
VALIDATION_START: RuntimeEventType = "validation_start"
VALIDATION_END: RuntimeEventType = "validation_end"
FALLBACK_START: RuntimeEventType = "fallback_start"
FALLBACK_END: RuntimeEventType = "fallback_end"
USER_INPUT_REQUIRED: RuntimeEventType = "user_input_required"


LEGACY_EVENT_TYPE_MAP: Dict[str, RuntimeEventType] = {
    "contract_confirmation": WORKFLOW_START,
    "contract_rejection": WORKFLOW_END,
    "task_registered": TASK_CREATED,
    "task_created": TASK_CREATED,
    "task_claimed": TASK_CLAIMED,
    "task_started": TASK_START,
    "task_start": TASK_START,
    "task_completed": TASK_END,
    "task_end": TASK_END,
    "task_failed": TASK_FAILED,
    "task_rejected": TASK_FAILED,
    "task_blocked": TASK_BLOCKED,
    "task_fallback_started": FALLBACK_START,
    "fallback_start": FALLBACK_START,
    "fallback_end": FALLBACK_END,
    "route_start": ROUTE_START,
    "route_end": ROUTE_END,
    "validation_start": VALIDATION_START,
    "validation_end": VALIDATION_END,
    "artifact_created": ARTIFACT_CREATED,
    "artifact_updated": ARTIFACT_UPDATED,
    "handoff_created": HANDOFF_CREATED,
    "context_delta_created": CONTEXT_DELTA_CREATED,
}


@dataclass
class AgentRuntimeEvent:
    """可持久化、可回放的本地 Agent 运行时事件。"""

    type: RuntimeEventType
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    run_id: str = ""
    task_id: str = ""
    parent_event_id: str = ""
    trace_id: str = ""
    agent_name: str = ""
    task_type: str = ""
    status: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso(now_provider: Optional[Callable[[], datetime]] = None) -> str:
    return (now_provider or datetime.now)().isoformat()


def to_jsonable(value: Any) -> Any:
    """将事件 payload 归一化为 JSON 可序列化结构。"""
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            return to_jsonable(value.to_dict())
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalize_runtime_event_type(event_type: str) -> RuntimeEventType:
    normalized = str(event_type or "").strip() or "unknown"
    return LEGACY_EVENT_TYPE_MAP.get(normalized, normalized)


def make_runtime_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timestamp: str = "",
    run_id: str = "",
    trace_id: str = "",
    task_id: str = "",
    agent_name: str = "",
    task_type: str = "",
    status: str = "",
    parent_event_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    now_provider: Optional[Callable[[], datetime]] = None,
) -> AgentRuntimeEvent:
    """创建标准 runtime event，并从 payload 中补齐常用字段。"""
    normalized_payload = to_jsonable(dict(payload or {}))
    normalized_metadata = to_jsonable(dict(metadata or {}))

    resolved_task_id = str(task_id or normalized_payload.get("task_id") or "").strip()
    resolved_task_type = str(task_type or normalized_payload.get("task_type") or "").strip()
    resolved_agent_name = str(
        agent_name
        or normalized_payload.get("agent_name")
        or normalized_payload.get("assigned_agent")
        or normalized_payload.get("agent")
        or ""
    ).strip()
    resolved_trace_id = str(
        trace_id
        or normalized_payload.get("trace_id")
        or normalized_payload.get("context_snapshot_id")
        or resolved_task_id
        or ""
    ).strip()
    resolved_status = str(status or normalized_payload.get("status") or "").strip()
    resolved_timestamp = str(timestamp or normalized_payload.get("timestamp") or "").strip() or _now_iso(now_provider)

    return AgentRuntimeEvent(
        type=normalize_runtime_event_type(event_type),
        timestamp=resolved_timestamp,
        run_id=str(run_id or normalized_payload.get("run_id") or "").strip(),
        task_id=resolved_task_id,
        parent_event_id=str(parent_event_id or normalized_payload.get("parent_event_id") or "").strip(),
        trace_id=resolved_trace_id,
        agent_name=resolved_agent_name,
        task_type=resolved_task_type,
        status=resolved_status,
        payload=normalized_payload,
        metadata=normalized_metadata,
    )


def build_legacy_trace_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timestamp: str = "",
    run_id: str = "",
    now_provider: Optional[Callable[[], datetime]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    构建兼容旧前端的 trace event，同时附带标准 runtime_event。

    旧字段 `type` 保持原事件名，避免现有前端和测试断裂；
    标准事件放入 `runtime_event`，并把 `runtime_type/event_id/trace_id/run_id`
    摊平到顶层，便于渐进迁移。
    """
    event_timestamp = str(timestamp or "").strip() or _now_iso(now_provider)
    legacy_payload = to_jsonable(dict(payload or {}))
    legacy_payload["type"] = str(event_type or legacy_payload.get("type") or "unknown").strip() or "unknown"
    legacy_payload["timestamp"] = str(legacy_payload.get("timestamp") or event_timestamp).strip() or event_timestamp
    legacy_payload.pop("created_at", None)

    runtime_event = make_runtime_event(
        legacy_payload["type"],
        legacy_payload,
        timestamp=legacy_payload["timestamp"],
        run_id=run_id,
        metadata={"legacy_type": legacy_payload["type"]},
        now_provider=now_provider,
    ).to_dict()

    legacy_payload["event_id"] = runtime_event["event_id"]
    legacy_payload["runtime_type"] = runtime_event["type"]
    legacy_payload["trace_id"] = runtime_event["trace_id"]
    legacy_payload["run_id"] = runtime_event["run_id"]
    legacy_payload["runtime_event"] = runtime_event
    return legacy_payload, runtime_event


def normalize_legacy_trace_event(
    event: Dict[str, Any],
    *,
    now_provider: Optional[Callable[[], datetime]] = None,
) -> Dict[str, Any]:
    normalized = to_jsonable(dict(event or {}))
    normalized_timestamp = str(
        normalized.get("timestamp")
        or normalized.get("created_at")
        or ""
    ).strip() or _now_iso(now_provider)
    normalized["timestamp"] = normalized_timestamp
    normalized.pop("created_at", None)
    return normalized
