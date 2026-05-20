"""长篇协作模式运行时状态存储。"""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.atomic_write import atomic_write_text
from .contracts import TaskDefinition
from .runtime_event_log import RuntimeEventLog
from .runtime_events import (
    build_legacy_trace_event,
    normalize_legacy_trace_event,
)
from .runtime_messages import attach_runtime_message
from .task_pool import TaskPool


logger = logging.getLogger(__name__)


class RuntimeStateStore:
    """封装任务池、执行轨迹、阶段总结、plot thread 等运行时状态落盘。"""

    def __init__(
        self,
        *,
        project_dir_provider: Callable[[], Path],
        project_manager_provider: Callable[[], Any],
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.project_dir_provider = project_dir_provider
        self.project_manager_provider = project_manager_provider
        self.now_provider = now_provider or datetime.now

    def _get_project_dir(self) -> Path:
        return Path(self.project_dir_provider())

    def _get_project_manager(self) -> Any:
        return self.project_manager_provider()

    def _now_iso(self) -> str:
        return self.now_provider().isoformat()

    def load_plot_thread_state(self, state_key: str) -> Optional[Dict[str, Any]]:
        try:
            payload = self._get_project_manager().load_project_state(state_key, default=None)
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to load state: {exc}")
            return None

    def save_plot_thread_state(self, state_key: str, payload: Dict[str, Any]) -> bool:
        try:
            self._get_project_manager().save_project_state(state_key, dict(payload or {}))
            return True
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to save state: {exc}")
            return False

    def persist_contract_runtime(
        self,
        *,
        persisted_contract: Dict[str, Any],
        task_pool: TaskPool,
        approved: bool,
        supervised_mode: bool,
        fallback_to_orchestrated: bool,
        initialized_at: str,
    ) -> Dict[str, Any]:
        contract_id = str(persisted_contract.get("contract_id") or "").strip()
        task_pool_payload = task_pool.to_dict()
        execution_trace = {
            "contract_id": contract_id,
            "status": "initialized" if approved else "draft_rejected",
            "supervised_mode": bool(supervised_mode),
            "fallback_to_orchestrated": bool(fallback_to_orchestrated),
            "updated_at": initialized_at,
            "events": [],
            "runtime_events": [],
        }
        event_type = "contract_confirmation" if approved else "contract_rejection"
        trace_payload = attach_runtime_message(
            event_type,
            {
                "event": "contract_confirmed" if approved else "contract_rejected",
                "timestamp": initialized_at,
                "task_count": len(task_pool.list_tasks()),
            },
            run_id=contract_id,
            now_provider=self.now_provider,
        )
        trace_event, runtime_event = build_legacy_trace_event(
            event_type,
            trace_payload,
            timestamp=initialized_at,
            run_id=contract_id,
            now_provider=self.now_provider,
        )
        execution_trace["events"].append(trace_event)
        execution_trace["runtime_events"].append(runtime_event)
        project_manager = self._get_project_manager()
        project_manager.save_project_state("creation_contract", persisted_contract)
        project_manager.save_project_state("task_graph_draft", persisted_contract.get("task_graph", []))
        project_manager.save_project_state("task_pool", task_pool_payload)
        project_manager.save_project_state("collab_execution_trace", execution_trace)
        RuntimeEventLog(self._get_project_dir()).safe_append_event(runtime_event)
        return {
            "creation_contract": persisted_contract,
            "task_pool": task_pool_payload,
            "collab_execution_trace": execution_trace,
        }

    def load_runtime_task_pool(self) -> TaskPool:
        payload = self._get_project_manager().load_project_state("task_pool", default={})
        if isinstance(payload, dict) and payload:
            try:
                return TaskPool.from_dict(payload)
            except Exception as exc:
                logger.warning(f"[Coordinator] 加载运行态任务池失败，回退为空任务池: {exc}")
        return TaskPool()

    def save_runtime_task_pool(self, task_pool: TaskPool) -> Dict[str, Any]:
        payload = task_pool.to_dict()
        self._get_project_manager().save_project_state("task_pool", payload)
        return payload

    def append_execution_event(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        supervised_mode: bool,
        fallback_to_orchestrated: bool,
    ) -> Dict[str, Any]:
        trace = self._get_project_manager().load_project_state("collab_execution_trace", default={})
        if not isinstance(trace, dict):
            trace = {}
        trace.setdefault("events", [])
        trace.setdefault("runtime_events", [])
        trace.setdefault("status", "initialized")
        trace.setdefault("supervised_mode", bool(supervised_mode))
        trace.setdefault("fallback_to_orchestrated", bool(fallback_to_orchestrated))

        normalized_events: List[Dict[str, Any]] = []
        for item in trace.get("events", []):
            if not isinstance(item, dict):
                continue
            normalized_events.append(normalize_legacy_trace_event(item, now_provider=self.now_provider))
        trace["events"] = normalized_events

        prepared_payload = attach_runtime_message(
            event_type,
            payload,
            run_id=str(trace.get("contract_id") or trace.get("run_id") or "").strip(),
            now_provider=self.now_provider,
        )
        event_payload, runtime_event = build_legacy_trace_event(
            event_type,
            prepared_payload,
            run_id=str(trace.get("contract_id") or trace.get("run_id") or "").strip(),
            now_provider=self.now_provider,
        )

        trace["events"].append(event_payload)
        if len(trace["events"]) > 500:
            trace["events"] = trace["events"][-500:]
        runtime_events = [
            item for item in trace.get("runtime_events", [])
            if isinstance(item, dict)
        ]
        runtime_events.append(runtime_event)
        if len(runtime_events) > 500:
            runtime_events = runtime_events[-500:]
        trace["runtime_events"] = runtime_events
        trace["updated_at"] = event_payload["timestamp"]
        self._get_project_manager().save_project_state("collab_execution_trace", trace)
        RuntimeEventLog(self._get_project_dir()).safe_append_event(runtime_event)
        return trace

    def upsert_runtime_task(
        self,
        *,
        task_type: str,
        title: str,
        description: str,
        input_data: Dict[str, Any],
        expected_outputs: Optional[List[str]],
        candidate_agents: List[str],
        review_required: bool,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[TaskPool, TaskDefinition]:
        runtime_pool = self.load_runtime_task_pool()
        normalized_title = str(title or task_type).strip() or str(task_type or "").strip()
        normalized_type = str(task_type or "").strip()
        matched_task = None

        for item in runtime_pool.list_tasks():
            if item.task_type != normalized_type:
                continue
            if normalized_title and str(item.title or "").strip() == normalized_title:
                matched_task = item
                break

        if matched_task is None:
            matched_task = runtime_pool.create_task(
                task_type=normalized_type,
                title=normalized_title,
                description=str(description or "").strip(),
                inputs=dict(input_data or {}),
                expected_outputs=list(expected_outputs or []),
                candidate_agents=list(candidate_agents or []),
                review_required=bool(review_required),
                metadata=dict(task_metadata or {}),
            )
        else:
            matched_task.inputs = dict(input_data or {})
            matched_task.expected_outputs = list(expected_outputs or [])
            matched_task.candidate_agents = list(candidate_agents or [])
            matched_task.review_required = bool(review_required)
            if isinstance(task_metadata, dict) and task_metadata:
                matched_task.metadata.update(dict(task_metadata))
            matched_task.touch()
            runtime_pool.updated_at = self._now_iso()

        self.save_runtime_task_pool(runtime_pool)
        return runtime_pool, matched_task

    def persist_stage_summary(self, summary_payload: Dict[str, Any], summary_text: str) -> Dict[str, str]:
        normalized_payload = dict(summary_payload or {})
        start_chapter = int(normalized_payload.get("start_chapter") or 1)
        end_chapter = int(normalized_payload.get("end_chapter") or start_chapter)

        state_key = "collab_stage_summaries"
        existing_summaries = self._get_project_manager().load_project_state(state_key, default=[])
        if not isinstance(existing_summaries, list):
            existing_summaries = []

        replaced = False
        for index, item in enumerate(existing_summaries):
            if not isinstance(item, dict):
                continue
            if int(item.get("start_chapter") or 0) == start_chapter and int(item.get("end_chapter") or 0) == end_chapter:
                existing_summaries[index] = normalized_payload
                replaced = True
                break
        if not replaced:
            existing_summaries.append(normalized_payload)
        self._get_project_manager().save_project_state(state_key, existing_summaries)

        summary_dir = self._get_project_dir() / "stage_summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_file = summary_dir / f"第{start_chapter}-{end_chapter}章-剧情总结.md"
        summary_existed_before = summary_file.exists()
        old_content = summary_file.read_text(encoding="utf-8") if summary_file.exists() else None
        atomic_write_text(summary_file, str(summary_text or ""), old_content=old_content)

        return {
            "summary_path": str(summary_file),
            "summary_status": "updated" if summary_existed_before else "created",
        }
