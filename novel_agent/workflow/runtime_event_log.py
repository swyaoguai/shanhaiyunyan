"""Append-only runtime event JSONL storage."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime
import hashlib
import uuid

from .runtime_events import to_jsonable


logger = logging.getLogger(__name__)


class RuntimeEventLog:
    """项目级运行时事件日志。

    日志只追加标准 runtime_event，一行一个 JSON。读取时会跳过损坏行，
    以便进程中断或半行写入不会阻塞历史回放。
    """

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.log_dir = self.project_dir / "runtime_events"
        self.current_path = self.log_dir / "current.jsonl"
        self.branch_index_path = self.log_dir / "branches.json"

    def append_event(self, event: Dict[str, Any]) -> None:
        payload = to_jsonable(dict(event or {}))
        branch_id = self._extract_branch_id(payload)
        if branch_id and not payload.get("branch_id"):
            payload["branch_id"] = branch_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.current_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")

    def append_events(self, events: Iterable[Dict[str, Any]]) -> None:
        normalized_events = [to_jsonable(dict(event or {})) for event in events if isinstance(event, dict)]
        if not normalized_events:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self.current_path.open("a", encoding="utf-8", newline="\n") as handle:
            for event in normalized_events:
                branch_id = self._extract_branch_id(event)
                if branch_id and not event.get("branch_id"):
                    event["branch_id"] = branch_id
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")

    def safe_append_event(self, event: Dict[str, Any]) -> bool:
        try:
            self.append_event(event)
            return True
        except Exception as exc:
            logger.warning(f"[RuntimeEventLog] failed to append event: {exc}")
            return False

    def safe_append_events(self, events: Iterable[Dict[str, Any]]) -> bool:
        try:
            self.append_events(events)
            return True
        except Exception as exc:
            logger.warning(f"[RuntimeEventLog] failed to append events: {exc}")
            return False

    def read_events(
        self,
        *,
        trace_id: str = "",
        task_id: str = "",
        branch_id: str = "",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not self.current_path.exists():
            return []

        normalized_trace_id = str(trace_id or "").strip()
        normalized_task_id = str(task_id or "").strip()
        normalized_branch_id = str(branch_id or "").strip()
        events: List[Dict[str, Any]] = []

        with self.current_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if normalized_trace_id and str(event.get("trace_id") or "").strip() != normalized_trace_id:
                    continue
                if normalized_task_id and str(event.get("task_id") or "").strip() != normalized_task_id:
                    continue
                if normalized_branch_id and self._extract_branch_id(event) != normalized_branch_id:
                    continue
                events.append(event)

        if limit is not None and limit >= 0:
            return events[-int(limit):]
        return events

    @staticmethod
    def _extract_branch_id(event: Dict[str, Any]) -> str:
        if not isinstance(event, dict):
            return ""
        for source in (
            event,
            event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
            event.get("payload") if isinstance(event.get("payload"), dict) else {},
        ):
            value = str((source or {}).get("branch_id") or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _compact_text(value: Any, limit: int = 600) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def _load_branch_index(self) -> Dict[str, Any]:
        if not self.branch_index_path.exists():
            return {"branches": {}, "updated_at": ""}
        try:
            payload = json.loads(self.branch_index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"branches": {}, "updated_at": ""}
        if not isinstance(payload, dict):
            return {"branches": {}, "updated_at": ""}
        branches = payload.get("branches")
        if not isinstance(branches, dict):
            branches = {}
        return {"branches": branches, "updated_at": str(payload.get("updated_at") or "")}

    def _save_branch_index(self, index: Dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "branches": dict(index.get("branches") or {}),
            "updated_at": self._now_iso(),
        }
        self.branch_index_path.write_text(
            json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert_branch_summary(
        self,
        *,
        branch_id: str,
        summary: str,
        parent_branch_id: str = "",
        active_leaf_event_id: str = "",
        compaction_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update a lightweight branch/compaction summary."""
        normalized_branch_id = str(branch_id or "").strip()
        if not normalized_branch_id:
            raise ValueError("branch_id is required")

        index = self._load_branch_index()
        existing = dict(index.get("branches", {}).get(normalized_branch_id) or {})
        created_at = existing.get("created_at") or self._now_iso()
        branch = {
            "branch_id": normalized_branch_id,
            "parent_branch_id": str(parent_branch_id or existing.get("parent_branch_id") or "").strip(),
            "active_leaf_event_id": str(active_leaf_event_id or existing.get("active_leaf_event_id") or "").strip(),
            "branch_summary": self._compact_text(summary),
            "compaction_summary": self._compact_text(compaction_summary or summary),
            "summary_hash": hashlib.sha256(str(summary or "").encode("utf-8")).hexdigest(),
            "created_at": created_at,
            "updated_at": self._now_iso(),
            "metadata": to_jsonable(dict(metadata or existing.get("metadata") or {})),
        }
        index.setdefault("branches", {})[normalized_branch_id] = branch
        self._save_branch_index(index)
        self.safe_append_event(
            {
                "event_id": f"evt-{uuid.uuid4().hex}",
                "type": "branch_summary_updated",
                "timestamp": branch["updated_at"],
                "branch_id": normalized_branch_id,
                "payload": {
                    "branch_id": normalized_branch_id,
                    "parent_branch_id": branch["parent_branch_id"],
                    "active_leaf_event_id": branch["active_leaf_event_id"],
                    "summary_hash": branch["summary_hash"],
                },
            }
        )
        return branch

    def read_branch_summary(self, branch_id: str) -> Dict[str, Any]:
        normalized_branch_id = str(branch_id or "").strip()
        if not normalized_branch_id:
            return {}
        return dict(self._load_branch_index().get("branches", {}).get(normalized_branch_id) or {})

    def list_branch_summaries(self) -> List[Dict[str, Any]]:
        branches = self._load_branch_index().get("branches", {})
        return sorted(
            [dict(item) for item in branches.values() if isinstance(item, dict)],
            key=lambda item: str(item.get("updated_at") or ""),
        )

    def build_branch_context_bundle_payload(self, branch_id: str, *, include_events: bool = False) -> Dict[str, Any]:
        """Represent a branch summary as a draft ContextBundle-compatible payload."""
        branch = self.read_branch_summary(branch_id)
        if not branch:
            raise ValueError(f"branch summary not found: {branch_id}")
        events = [
            event for event in self.read_events(branch_id=branch["branch_id"])
            if str(event.get("type") or "") != "branch_summary_updated"
        ]
        event_refs = [str(event.get("event_id") or "") for event in events if str(event.get("event_id") or "")]
        return {
            "source_mode": "runtime_branch",
            "source_file": f"{self.current_path.name}#branch_id={branch['branch_id']}",
            "summary": branch.get("compaction_summary") or branch.get("branch_summary") or "",
            "suggested_target": "ContentReader.context_bundles",
            "payload": {
                "branch": branch,
                "event_refs": event_refs,
                "events": events if include_events else [],
            },
            "metadata": {
                "branch_id": branch["branch_id"],
                "parent_branch_id": branch.get("parent_branch_id", ""),
                "active_leaf_event_id": branch.get("active_leaf_event_id", ""),
                "event_count": len(events),
            },
        }
