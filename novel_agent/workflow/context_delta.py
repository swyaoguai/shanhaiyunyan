"""Context delta records for collaborative task execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List
import uuid


def _new_delta_id() -> str:
    return f"delta-{uuid.uuid4().hex[:12]}"


def _summarize_value(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"type": "NoneType", "empty": True}
    if isinstance(value, str):
        compact = value.strip().replace("\n", " ")
        return {
            "type": "str",
            "length": len(value),
            "preview": compact[:160],
        }
    if isinstance(value, (list, tuple, set)):
        return {"type": type(value).__name__, "length": len(value)}
    if isinstance(value, dict):
        return {"type": "dict", "length": len(value), "keys": list(value.keys())[:12]}
    return {"type": type(value).__name__, "repr": str(value)[:160]}


@dataclass
class ContextDelta:
    """Summary of context keys changed by one task."""

    task_id: str
    task_type: str
    agent_name: str
    delta_id: str = field(default_factory=_new_delta_id)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    added_keys: List[str] = field(default_factory=list)
    updated_keys: List[str] = field(default_factory=list)
    removed_keys: List[str] = field(default_factory=list)
    source_of_truth_patch: Dict[str, str] = field(default_factory=dict)
    overwrite_reasons: Dict[str, str] = field(default_factory=dict)
    summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_context_delta(
    *,
    before: Dict[str, Any],
    after: Dict[str, Any],
    task_id: str,
    task_type: str,
    agent_name: str,
) -> ContextDelta:
    """Build a compact delta between two context dictionaries."""
    before_payload = dict(before or {})
    after_payload = dict(after or {})
    before_sources = before_payload.get("source_of_truth") if isinstance(before_payload.get("source_of_truth"), dict) else {}
    after_sources = after_payload.get("source_of_truth") if isinstance(after_payload.get("source_of_truth"), dict) else {}

    ignored = {"source_of_truth"}
    before_keys = {key for key in before_payload.keys() if key not in ignored}
    after_keys = {key for key in after_payload.keys() if key not in ignored}
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    updated = sorted(
        key for key in (before_keys & after_keys)
        if before_payload.get(key) != after_payload.get(key)
    )

    changed_keys = added + updated
    source_patch = {
        key: str(after_sources.get(key) or "").strip()
        for key in changed_keys
        if str(after_sources.get(key) or "").strip()
    }
    overwrite_reasons = {
        key: f"{before_sources.get(key, 'unknown')} -> {after_sources.get(key, agent_name or task_type or 'unknown')}"
        for key in updated
    }
    summaries = {
        key: _summarize_value(after_payload.get(key))
        for key in changed_keys[:40]
    }

    parts: List[str] = []
    if added:
        parts.append(f"新增 {len(added)} 个上下文键")
    if updated:
        parts.append(f"更新 {len(updated)} 个上下文键")
    if removed:
        parts.append(f"移除 {len(removed)} 个上下文键")
    summary = "；".join(parts) if parts else "上下文无结构性变化"

    return ContextDelta(
        task_id=str(task_id or "").strip(),
        task_type=str(task_type or "").strip(),
        agent_name=str(agent_name or "").strip(),
        added_keys=added,
        updated_keys=updated,
        removed_keys=removed,
        source_of_truth_patch=source_patch,
        overwrite_reasons=overwrite_reasons,
        summaries=summaries,
        summary=summary,
    )
