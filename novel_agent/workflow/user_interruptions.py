"""Helpers for pausing and annotating creative workflow runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from .user_visible_categories import category_keywords
from .workflow_context import UserInterruption


def detect_interruption_impact(message: str) -> List[str]:
    """Infer which creative categories a user correction may invalidate."""

    text = str(message or "").strip()
    affected: List[str] = []
    for category, keywords in category_keywords().items():
        if any(keyword in text for keyword in keywords):
            affected.append(category)
    if not affected and any(token in text for token in ("不对", "改成", "不是", "修改", "调整")):
        affected.extend(["characters", "outline", "chapters"])
    return affected


def build_user_interruption(message: str) -> UserInterruption:
    return UserInterruption(
        interruption_id=f"interrupt-{uuid4().hex[:10]}",
        message=str(message or "").strip(),
        affected_categories=detect_interruption_impact(message),
        created_at=datetime.now().isoformat(),
    )


def apply_interruption(run_payload: Dict[str, Any], message: str) -> Dict[str, Any]:
    """Record a user interruption in a serialized workflow run payload."""

    payload = dict(run_payload or {})
    try:
        from .creative_workflow import CreativeWorkflowRun

        run = CreativeWorkflowRun.from_dict(payload)
        run.apply_user_interruption(message)
        return run.to_dict()
    except Exception:
        interruption = build_user_interruption(message).to_dict()
        payload.setdefault("user_interruptions", []).append(interruption)
        payload.setdefault("canonical_context", {}).setdefault("user_interruptions", []).append(interruption)
        payload["status"] = "paused"
        payload["current_stage"] = "user_interruption"
        payload["updated_at"] = datetime.now().isoformat()
        return payload
