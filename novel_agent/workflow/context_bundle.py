"""Explicit local context-bundle migration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import re
import uuid

from .context_delta import build_context_delta
from .workflow_context import AgentHandoff


CONTEXT_BUNDLE_STATE_KEY = "collab_context_bundles"
CONTEXT_BUNDLE_HANDOFF_AGENT = "ContextBundleMigrator"


@dataclass
class ContextBundle:
    """A user-confirmed bridge from another local mode into ContentReader."""

    bundle_id: str
    source_mode: str
    source_file: str
    summary: str
    suggested_target: str = "ContentReader.context_bundles"
    suggested_write_location: str = "ContentReader.context_bundles"
    source_label: str = ""
    payload: Any = None
    content_preview: str = ""
    content_hash: str = ""
    status: str = "draft"
    created_at: str = ""
    confirmed_at: str = ""
    confirmed_by: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    handoff: Dict[str, Any] = field(default_factory=dict)
    context_delta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ContextBundle":
        data = dict(payload or {})
        return cls(
            bundle_id=str(data.get("bundle_id") or "").strip(),
            source_mode=str(data.get("source_mode") or "").strip(),
            source_file=str(data.get("source_file") or "").strip(),
            summary=str(data.get("summary") or "").strip(),
            suggested_target=str(data.get("suggested_target") or "ContentReader.context_bundles").strip(),
            suggested_write_location=str(
                data.get("suggested_write_location")
                or data.get("suggested_target")
                or "ContentReader.context_bundles"
            ).strip(),
            source_label=str(data.get("source_label") or "").strip(),
            payload=data.get("payload"),
            content_preview=str(data.get("content_preview") or "").strip(),
            content_hash=str(data.get("content_hash") or "").strip(),
            status=str(data.get("status") or "draft").strip() or "draft",
            created_at=str(data.get("created_at") or "").strip(),
            confirmed_at=str(data.get("confirmed_at") or "").strip(),
            confirmed_by=str(data.get("confirmed_by") or "").strip(),
            metadata=dict(data.get("metadata") or {}),
            handoff=dict(data.get("handoff") or {}),
            context_delta=dict(data.get("context_delta") or {}),
        )


def _now_iso() -> str:
    return datetime.now().isoformat()


def _compact_text(value: Any, limit: int) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(payload or "")


def _payload_hash(payload: Any) -> str:
    return hashlib.sha256(_payload_text(payload).encode("utf-8")).hexdigest()


def _normalize_store(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        items = [dict(item) for item in raw.get("items", []) if isinstance(item, dict)]
        return {
            "items": items,
            "updated_at": str(raw.get("updated_at") or "").strip(),
        }
    if isinstance(raw, list):
        return {"items": [dict(item) for item in raw if isinstance(item, dict)], "updated_at": ""}
    return {"items": [], "updated_at": ""}


def _load_store(project_manager: Any) -> Dict[str, Any]:
    raw = project_manager.load_project_state(CONTEXT_BUNDLE_STATE_KEY, default={})
    return _normalize_store(raw)


def _save_store(project_manager: Any, store: Dict[str, Any]) -> Dict[str, Any]:
    store = _normalize_store(store)
    store["updated_at"] = _now_iso()
    project_manager.save_project_state(CONTEXT_BUNDLE_STATE_KEY, store)
    return store


def _append_state_item(project_manager: Any, state_key: str, item: Dict[str, Any], max_items: int = 200) -> None:
    raw = project_manager.load_project_state(state_key, default={})
    store = _normalize_store(raw)
    items = store.get("items", [])
    items.append(dict(item or {}))
    if len(items) > max_items:
        items = items[-max_items:]
    store = {"items": items, "updated_at": _now_iso()}
    project_manager.save_project_state(state_key, store)


def create_context_bundle(
    project_manager: Any,
    *,
    source_mode: str,
    source_file: str,
    payload: Any,
    summary: str = "",
    suggested_target: str = "ContentReader.context_bundles",
    source_label: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a draft migration bundle without touching core project data."""
    normalized_source_mode = str(source_mode or "").strip()
    normalized_source_file = str(source_file or "").strip()
    if not normalized_source_mode:
        raise ValueError("source_mode is required")
    if not normalized_source_file:
        raise ValueError("source_file is required")

    payload_text = _payload_text(payload)
    bundle = ContextBundle(
        bundle_id=f"ctxb-{uuid.uuid4().hex[:12]}",
        source_mode=normalized_source_mode,
        source_file=normalized_source_file,
        source_label=str(source_label or "").strip(),
        summary=str(summary or "").strip() or _compact_text(payload_text, 240),
        suggested_target=str(suggested_target or "ContentReader.context_bundles").strip(),
        suggested_write_location=str(suggested_target or "ContentReader.context_bundles").strip(),
        payload=payload,
        content_preview=_compact_text(payload_text, 800),
        content_hash=_payload_hash(payload),
        status="draft",
        created_at=_now_iso(),
        metadata=dict(metadata or {}),
    )

    store = _load_store(project_manager)
    items = store.get("items", [])
    items.append(bundle.to_dict())
    _save_store(project_manager, {"items": items})
    return bundle.to_dict()


def _confirmed_bundle_summaries(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "bundle_id": str(item.get("bundle_id") or "").strip(),
            "source_mode": str(item.get("source_mode") or "").strip(),
            "source_file": str(item.get("source_file") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "suggested_target": str(item.get("suggested_target") or "").strip(),
            "content_hash": str(item.get("content_hash") or "").strip(),
        }
        for item in items
        if isinstance(item, dict) and str(item.get("status") or "").strip() == "confirmed"
    ]


def confirm_context_bundle(
    project_manager: Any,
    bundle_id: str,
    *,
    confirmed_by: str = "user",
) -> Dict[str, Any]:
    """Confirm a draft bundle and expose it to ContentReader as reference material."""
    normalized_bundle_id = str(bundle_id or "").strip()
    if not normalized_bundle_id:
        raise ValueError("bundle_id is required")

    store = _load_store(project_manager)
    items = store.get("items", [])
    before_confirmed = _confirmed_bundle_summaries(items)
    matched_index = next(
        (
            index for index, item in enumerate(items)
            if str(item.get("bundle_id") or "").strip() == normalized_bundle_id
        ),
        None,
    )
    if matched_index is None:
        raise ValueError(f"context bundle not found: {normalized_bundle_id}")

    bundle = ContextBundle.from_dict(items[matched_index])
    bundle.status = "confirmed"
    bundle.confirmed_at = _now_iso()
    bundle.confirmed_by = str(confirmed_by or "user").strip() or "user"

    after_items = [dict(item) for item in items]
    after_items[matched_index] = bundle.to_dict()
    after_confirmed = _confirmed_bundle_summaries(after_items)
    task_id = f"context-bundle:{bundle.bundle_id}"
    context_delta = build_context_delta(
        before={"context_bundles": before_confirmed},
        after={"context_bundles": after_confirmed},
        task_id=task_id,
        task_type="context_bundle_confirm",
        agent_name=CONTEXT_BUNDLE_HANDOFF_AGENT,
    ).to_dict()
    handoff = AgentHandoff(
        artifact_id=bundle.bundle_id,
        artifact_type="context_bundle",
        task_id=task_id,
        agent_name=CONTEXT_BUNDLE_HANDOFF_AGENT,
        context_snapshot_id="",
        decisions=[f"已确认来自 {bundle.source_mode} 的上下文迁移包"],
        dependencies=[bundle.source_file],
        new_facts=[bundle.summary] if bundle.summary else [],
        changed_facts=[],
        risks=[],
        next_context_summary=f"ContextReader 可按需读取迁移包：{bundle.summary}",
        artifact_refs=[bundle.source_file],
        context_delta_id=context_delta.get("delta_id", ""),
        consumed_context_keys=[bundle.source_mode],
        produced_context_keys=["context_bundles"],
        output_validation={"passed": True, "expected_outputs": ["context_bundles"]},
    ).to_dict()

    bundle.handoff = handoff
    bundle.context_delta = context_delta
    after_items[matched_index] = bundle.to_dict()
    _save_store(project_manager, {"items": after_items})
    _append_state_item(project_manager, "collab_context_deltas", context_delta)
    _append_state_item(project_manager, "collab_handoffs", handoff)
    return bundle.to_dict()


def load_confirmed_context_bundles_from_project_dir(project_dir: Optional[Path]) -> List[Dict[str, Any]]:
    """Load confirmed bundles from a project client_state directory."""
    if not project_dir:
        return []
    path = Path(project_dir) / "client_state" / f"{CONTEXT_BUNDLE_STATE_KEY}.json"
    if not path.exists():
        return []
    try:
        store = _normalize_store(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return []
    return [
        dict(item)
        for item in store.get("items", [])
        if isinstance(item, dict) and str(item.get("status") or "").strip() == "confirmed"
    ]
