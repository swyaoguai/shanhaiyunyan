"""长篇协作模式统一执行入口。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import json
import re
import logging
import uuid

from ..constants import WRITING_CONFIG
from ..utils.atomic_write import atomic_write_json
from .context_delta import build_context_delta
from .execution_context import CollabExecutionContext, TaskExecutionEnvelope
from .output_validation import format_output_validation_error, validate_task_outputs
from .routing_policy import RoutingPolicy, RoutingPolicyError
from .runtime_event_log import RuntimeEventLog
from .runtime_events import (
    build_legacy_trace_event,
    normalize_legacy_trace_event,
)
from .runtime_hooks import get_runtime_hook_registry, make_runtime_hook_context
from .runtime_messages import attach_runtime_message
from .runtime_state import RuntimeStateStore
from .task_pool import TaskPool, TaskStatus
from .contracts import TaskDefinition
from .workflow_context import AgentHandoff
from .collab_run_state import CollabRunStateStore

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    success: bool
    agent_name: str
    result: Dict[str, Any]
    route_reason: str = ""
    candidate_source: str = ""
    candidate_agents: List[str] = field(default_factory=list)
    context_snapshot_id: str = ""
    fallback_used: bool = False
    fallback_agent: str = ""
    fallback_provenance: Dict[str, Any] = field(default_factory=dict)
    autonomous_error: str = ""
    execution_mode: str = "autonomous"
    context: Dict[str, Any] = field(default_factory=dict)
    task_pool: Dict[str, Any] = field(default_factory=dict)
    runtime_task_pool: Dict[str, Any] = field(default_factory=dict)
    output_validation: Dict[str, Any] = field(default_factory=dict)
    handoff: Dict[str, Any] = field(default_factory=dict)
    context_delta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _format_agent_failure(result: Any) -> str:
    """Turn an agent failure payload into a concise user-facing reason."""
    if not isinstance(result, dict):
        return "任务执行失败：助手未返回结构化结果。"

    primary = str(
        result.get("error")
        or result.get("response_message")
        or result.get("message")
        or result.get("reason")
        or ""
    ).strip()

    details: List[str] = []
    for key in ("missing_info", "validation_issues", "violations", "issues"):
        value = result.get(key)
        if isinstance(value, list):
            details.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            details.append(value.strip())

    if not primary:
        primary = "任务执行失败"
    if details:
        joined_details = "；".join(dict.fromkeys(details[:4]))
        if joined_details and joined_details not in primary:
            primary = f"{primary}：{joined_details}"

    raw_response = str(result.get("raw_response") or "").strip()
    if raw_response and primary == "任务执行失败":
        compact_raw = re.sub(r"\s+", " ", raw_response)[:160]
        primary = f"{primary}，模型原始返回：{compact_raw}"

    return primary[:500] or "任务执行失败"


class AgentDispatcher:
    """多 Agent 协作模式的 Phase 1 统一执行入口。"""

    def __init__(
        self,
        *,
        routing_policy: RoutingPolicy,
        capability_registry_provider: Callable[[], Any],
        project_manager_provider: Callable[[], Any],
        project_dir_provider: Callable[[], Path],
        save_runtime_task_pool: Callable[[TaskPool], Dict[str, Any]],
        notify_progress: Callable[[Dict[str, Any]], Awaitable[None]],
        supervised_mode_provider: Callable[[], bool],
        fallback_to_orchestrated_provider: Callable[[], bool],
        allow_ephemeral_agent_provider: Optional[Callable[[], bool]] = None,
        ephemeral_agent_factory: Optional[Callable[[Any, str], Any]] = None,
        runtime_state_store: Optional[RuntimeStateStore] = None,
        collab_run_state_store: Optional[CollabRunStateStore] = None,
    ) -> None:
        self.routing_policy = routing_policy
        self.capability_registry_provider = capability_registry_provider
        self.project_manager_provider = project_manager_provider
        self.project_dir_provider = project_dir_provider
        self.save_runtime_task_pool = save_runtime_task_pool
        self.notify_progress = notify_progress
        self.supervised_mode_provider = supervised_mode_provider
        self.fallback_to_orchestrated_provider = fallback_to_orchestrated_provider
        self.allow_ephemeral_agent_provider = allow_ephemeral_agent_provider or (lambda: False)
        self.ephemeral_agent_factory = ephemeral_agent_factory
        self.runtime_state_store = runtime_state_store
        self.collab_run_state_store = collab_run_state_store
        # 13.5 批量写入：延迟持久化缓存
        self._deferred_events: List[Dict[str, Any]] = []
        self._deferred_snapshots: List[Dict[str, Any]] = []
        self._deferred_handoffs: List[Dict[str, Any]] = []
        self._deferred_context_deltas: List[Dict[str, Any]] = []

    def _get_capability_registry(self) -> Any:
        return self.capability_registry_provider()

    def _get_project_manager(self) -> Any:
        return self.project_manager_provider()

    def _get_project_dir(self) -> Path:
        return Path(self.project_dir_provider())

    def _ensure_run_state(self) -> None:
        if self.collab_run_state_store is None:
            return
        try:
            self.collab_run_state_store.ensure_run(status="running")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] ensure collab run state failed: {exc}")

    def _append_run_runtime_event(self, runtime_event: Dict[str, Any]) -> None:
        if self.collab_run_state_store is None or not isinstance(runtime_event, dict):
            return
        try:
            self.collab_run_state_store.append_runtime_event(runtime_event)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] append collab runtime event failed: {exc}")

    def _record_run_checkpoint(
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
    ) -> None:
        if self.collab_run_state_store is None:
            return
        try:
            self.collab_run_state_store.record_checkpoint(
                node=node,
                status=status,
                task_id=task_id,
                task_type=task_type,
                agent_name=agent_name,
                context=context,
                task_pool=task_pool,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] record collab checkpoint failed: {exc}")

    def _merge_run_context_overlay(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.collab_run_state_store is None:
            return dict(context or {})
        try:
            return self.collab_run_state_store.merge_context_overlay(context)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] merge collab shared memory failed: {exc}")
            return dict(context or {})

    def _append_run_handoff(self, handoff: Dict[str, Any]) -> None:
        if self.collab_run_state_store is None:
            return
        try:
            self.collab_run_state_store.append_handoff(handoff)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] append collab handoff failed: {exc}")

    def _append_run_artifact(
        self,
        *,
        task_id: str,
        task_type: str,
        agent_name: str,
        artifact_refs: List[str],
        result_keys: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.collab_run_state_store is None:
            return
        try:
            self.collab_run_state_store.append_artifact(
                task_id=task_id,
                task_type=task_type,
                agent_name=agent_name,
                artifact_refs=artifact_refs,
                result_keys=result_keys,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] append collab artifact failed: {exc}")

    def _sync_run_memory(
        self,
        *,
        context: Dict[str, Any],
        task_id: str,
        task_type: str,
        agent_name: str,
        context_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.collab_run_state_store is None:
            return
        try:
            self.collab_run_state_store.upsert_memory_from_context(
                context=context,
                task_id=task_id,
                task_type=task_type,
                agent_name=agent_name,
                context_delta=context_delta,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] sync collab shared memory failed: {exc}")

    @staticmethod
    def _unique_strings(values: List[Any]) -> List[str]:
        normalized: List[str] = []
        for value in values or []:
            item = str(value or "").strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized

    def _prime_required_context_keys(self, envelope: TaskExecutionEnvelope) -> List[str]:
        required: List[str] = list(envelope.required_context_keys or [])
        getter = getattr(self.routing_policy, "required_context_keys_for", None)
        if callable(getter):
            try:
                required.extend(getter(envelope.task_type, envelope.stage))
            except Exception:
                pass
        envelope.required_context_keys = self._unique_strings(required)
        return list(envelope.required_context_keys)

    @staticmethod
    def _source_of_truth_summary(
        context: CollabExecutionContext,
        keys: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        source_map = dict(getattr(context, "source_of_truth", {}) or {})
        if not source_map:
            return {}
        normalized_keys = [
            str(item or "").strip()
            for item in (keys or [])
            if str(item or "").strip()
        ]
        if not normalized_keys:
            normalized_keys = sorted(source_map.keys())
        return {
            key: str(source_map.get(key) or "").strip()
            for key in normalized_keys
            if str(source_map.get(key) or "").strip()
        }

    def _append_execution_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        project_manager = self._get_project_manager()
        trace = project_manager.load_project_state("collab_execution_trace", default={})
        if not isinstance(trace, dict):
            trace = {}
        trace.setdefault("events", [])
        trace.setdefault("runtime_events", [])
        trace.setdefault("status", "initialized")
        trace.setdefault("supervised_mode", bool(self.supervised_mode_provider()))
        trace.setdefault("fallback_to_orchestrated", bool(self.fallback_to_orchestrated_provider()))

        normalized_events: List[Dict[str, Any]] = []
        for item in trace.get("events", []):
            if not isinstance(item, dict):
                continue
            normalized_events.append(normalize_legacy_trace_event(item))
        trace["events"] = normalized_events

        run_id = str(trace.get("contract_id") or trace.get("run_id") or "").strip()
        prepared_payload = self._prepare_execution_payload(event_type, payload, run_id=run_id)
        event_payload, runtime_event = build_legacy_trace_event(
            event_type,
            prepared_payload,
            run_id=run_id,
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
        project_manager.save_project_state("collab_execution_trace", trace)
        RuntimeEventLog(self._get_project_dir()).safe_append_event(runtime_event)
        self._append_run_runtime_event(runtime_event)
        return trace

    def _prepare_execution_payload(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        run_id: str = "",
    ) -> Dict[str, Any]:
        """Attach typed message/artifact envelopes while preserving legacy fields."""
        return attach_runtime_message(event_type, payload, run_id=run_id)

    def _emit_execution_event(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        defer_persist: bool = False,
    ) -> None:
        """写入执行事件；批量模式下先缓存，保持现有延迟落盘行为。"""
        prepared_payload = self._prepare_execution_payload(event_type, payload)
        if defer_persist:
            event_payload, _runtime_event = build_legacy_trace_event(event_type, prepared_payload)
            self._deferred_events.append(event_payload)
            return
        self._append_execution_event(event_type, prepared_payload)

    async def _run_runtime_hooks(
        self,
        stage: str,
        event: Dict[str, Any],
        *,
        task_id: str = "",
        task_type: str = "",
        agent_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        defer_persist: bool = False,
    ) -> List[Any]:
        context = make_runtime_hook_context(
            stage=stage,
            project_dir=self._get_project_dir(),
            task_id=task_id,
            task_type=task_type,
            agent_name=agent_name,
            metadata=metadata,
        )
        try:
            return await get_runtime_hook_registry().run(stage, event, context)
        except Exception as exc:
            self._emit_execution_event(
                "runtime_hook_error",
                {
                    "hook_stage": stage,
                    "task_id": task_id,
                    "task_type": task_type,
                    "assigned_agent": agent_name,
                    "error": str(exc),
                },
                defer_persist=defer_persist,
            )
            return []

    def _record_context_snapshot(
        self,
        *,
        envelope: TaskExecutionEnvelope,
        route_reason: str,
        candidate_source: str,
        candidate_agents: List[str],
        defer_persist: bool = False,
    ) -> str:
        snapshot_id = f"ctx-{uuid.uuid4().hex[:12]}"
        # 13.5 修复：限制上下文快照大小，只保留关键字段
        context_dict = envelope.context.to_dict()
        required_context_keys = list(envelope.required_context_keys or [])
        missing_context_keys = envelope.context.missing_keys(required_context_keys)
        source_summary = self._source_of_truth_summary(envelope.context, required_context_keys)
        snapshot_context = {}
        for key in ("stage", "world", "characters", "chapter_outline", "previous_summary", "context_strategy"):
            if key in context_dict:
                val = context_dict[key]
                # 对大字段只保留类型和大小信息
                if isinstance(val, (dict, list)) and len(str(val)) > 2000:
                    snapshot_context[key] = f"<{type(val).__name__} len={len(val)}>"
                else:
                    snapshot_context[key] = val

        snapshot = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now().isoformat(),
            "task_type": envelope.task_type,
            "stage": envelope.stage,
            "title": envelope.title,
            "route_reason": route_reason,
            "candidate_source": candidate_source,
            "candidate_agents": list(candidate_agents or []),
            "required_context_keys": required_context_keys,
            "missing_context_keys": missing_context_keys,
            "source_of_truth_summary": source_summary,
            "context": snapshot_context,
        }

        if defer_persist:
            # 13.5 延迟模式：缓存快照，稍后批量写入
            self._deferred_snapshots.append(snapshot)
            return snapshot_id

        project_manager = self._get_project_manager()
        snapshot_store = project_manager.load_project_state("collab_context_snapshots", default={})
        if not isinstance(snapshot_store, dict):
            snapshot_store = {}
        snapshot_store.setdefault("items", [])

        items = [
            item for item in snapshot_store.get("items", [])
            if isinstance(item, dict)
        ]
        items.append(snapshot)
        if len(items) > 200:
            items = items[-200:]
        snapshot_store["items"] = items
        snapshot_store["updated_at"] = snapshot["created_at"]
        project_manager.save_project_state("collab_context_snapshots", snapshot_store)
        return snapshot_id

    def _persist_permanent_memory(self, permanent_memory: Dict[str, Any]) -> None:
        if not isinstance(permanent_memory, dict):
            return
        project_manager = self._get_project_manager()
        project_manager.save_project_state("collab_permanent_memory", permanent_memory)
        try:
            memory_path = self._get_project_dir() / "client_state" / "collab_permanent_memory.json"
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            old_content = memory_path.read_text(encoding="utf-8") if memory_path.exists() else None
            atomic_write_json(memory_path, permanent_memory, old_content=old_content)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"[AgentDispatcher] 保存协作永久记忆文件失败: {exc}")

    def _resolve_agent_instance(self, agent_name: str, fallback_agent: Any = None) -> Any:
        registry = self._get_capability_registry()
        if registry is not None:
            agent = registry.get_agent(agent_name)
            if agent is not None:
                return agent

        if fallback_agent is not None:
            fallback_name = str(getattr(fallback_agent, "name", "") or "").strip()
            if fallback_name and fallback_name == str(agent_name or "").strip():
                return fallback_agent
        return None

    def _ephemeral_agents_enabled(self) -> bool:
        try:
            return bool(self.allow_ephemeral_agent_provider())
        except Exception:
            return False

    def _build_ephemeral_agent(self, envelope: TaskExecutionEnvelope, reason: str) -> Any:
        if self.ephemeral_agent_factory is not None:
            return self.ephemeral_agent_factory(envelope, reason)

        from ..agents.ephemeral_task_agent import EphemeralTaskAgent

        return EphemeralTaskAgent(
            task_type=envelope.task_type,
            stage=envelope.stage,
            title=envelope.title,
            reason=reason,
        )

    def _register_ephemeral_agent(
        self,
        envelope: TaskExecutionEnvelope,
        reason: str,
    ) -> Tuple[Any, str, bool]:
        if not self._ephemeral_agents_enabled():
            return None, "", False
        registry = self._get_capability_registry()
        if registry is None or not hasattr(registry, "register"):
            return None, "", False

        agent = self._build_ephemeral_agent(envelope, reason)
        agent_name = str(getattr(agent, "name", "") or "").strip()
        if not agent_name:
            raise RuntimeError("临时Agent缺少名称")
        registry.register(agent)
        self._append_execution_event(
            "ephemeral_agent_created",
            {
                "agent": agent_name,
                "task_type": envelope.task_type,
                "stage": envelope.stage,
                "title": envelope.title,
                "reason": reason,
                "lifecycle": "task_scoped",
            },
        )
        return agent, agent_name, True

    def _unregister_ephemeral_agent(self, agent_name: str) -> None:
        normalized = str(agent_name or "").strip()
        if not normalized:
            return
        registry = self._get_capability_registry()
        removed = False
        if registry is not None and hasattr(registry, "unregister"):
            try:
                removed = bool(registry.unregister(normalized))
            except Exception:
                removed = False
        self._append_execution_event(
            "ephemeral_agent_removed",
            {
                "agent": normalized,
                "removed": removed,
                "lifecycle": "task_scoped",
            },
        )

    def _resolve_agent_model(self, agent_name: str, agent_instance: Any = None) -> str:
        target_name = str(agent_name or getattr(agent_instance, "name", "") or "").strip()
        candidates: List[str] = []
        for attr_name in ("_get_model_name", "get_model_name"):
            getter = getattr(agent_instance, attr_name, None) if agent_instance is not None else None
            if callable(getter):
                try:
                    candidates.append(str(getter() or "").strip())
                except Exception:
                    pass
        for attr_name in ("model", "model_name", "current_model", "active_model"):
            value = getattr(agent_instance, attr_name, "") if agent_instance is not None else ""
            candidates.append(str(value or "").strip())
        config_obj = getattr(agent_instance, "config", None) if agent_instance is not None else None
        if config_obj is not None:
            candidates.append(str(getattr(config_obj, "model", "") or "").strip())
        llm_config = getattr(agent_instance, "llm_config", None) if agent_instance is not None else None
        if isinstance(llm_config, dict):
            candidates.append(str(llm_config.get("model") or "").strip())

        for value in candidates:
            if value:
                return value

        if target_name:
            try:
                from ..agent_config import get_config_manager
                cfg = get_config_manager().get_effective_config(target_name)
                model_name = str(getattr(cfg, "model", "") or "").strip()
                if model_name:
                    return model_name
            except Exception as exc:
                logger.debug(f"[AgentDispatcher] resolve model failed for {target_name}: {exc}")
        return ""

    def _append_state_item(
        self,
        state_key: str,
        item: Dict[str, Any],
        *,
        max_items: int,
    ) -> None:
        project_manager = self._get_project_manager()
        store = project_manager.load_project_state(state_key, default={})
        if not isinstance(store, dict):
            store = {}
        items = [
            existing for existing in store.get("items", [])
            if isinstance(existing, dict)
        ]
        items.append(dict(item or {}))
        if len(items) > max_items:
            items = items[-max_items:]
        store["items"] = items
        store["updated_at"] = datetime.now().isoformat()
        project_manager.save_project_state(state_key, store)

    def _persist_context_delta(self, delta: Dict[str, Any], *, defer_persist: bool = False) -> None:
        if not isinstance(delta, dict) or not delta.get("delta_id"):
            return
        if defer_persist:
            self._deferred_context_deltas.append(dict(delta))
            return
        self._append_state_item("collab_context_deltas", delta, max_items=300)

    def _persist_handoff(self, handoff: Dict[str, Any], *, defer_persist: bool = False) -> None:
        if not isinstance(handoff, dict) or not handoff.get("task_id"):
            return
        if defer_persist:
            self._deferred_handoffs.append(dict(handoff))
            self._append_run_handoff(handoff)
            return
        self._append_state_item("collab_handoffs", handoff, max_items=300)
        self._append_run_handoff(handoff)

    @staticmethod
    def _extract_artifact_refs(task: TaskDefinition, result: Dict[str, Any]) -> List[str]:
        refs: List[str] = []
        if task.result_ref:
            refs.append(str(task.result_ref))
        for key in ("artifact_id", "target_path", "path", "filename", "summary_path", "result_ref"):
            value = result.get(key) if isinstance(result, dict) else None
            if isinstance(value, str) and value.strip():
                refs.append(value.strip())
        created_files = result.get("created_files") if isinstance(result, dict) else None
        if isinstance(created_files, list):
            for item in created_files:
                if isinstance(item, dict):
                    path = str(item.get("path") or "").strip()
                    if path:
                        refs.append(path)
        return AgentDispatcher._unique_strings(refs)

    @staticmethod
    def _summarize_result_for_handoff(task_type: str, result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""
        for key in ("response_message", "message", "summary"):
            value = str(result.get(key) or "").strip()
            if value:
                return re.sub(r"\s+", " ", value)[:240]
        if task_type == "write_chapter" and str(result.get("content") or "").strip():
            return f"已生成章节正文，约 {result.get('word_count') or len(str(result.get('content') or ''))} 字。"
        if task_type == "content_read":
            loaded = result.get("loaded_context")
            if isinstance(loaded, dict):
                return "已加载上下文：" + "、".join(list(loaded.keys())[:8])
        if task_type == "evaluate_chapter":
            evaluation = result.get("evaluation")
            if isinstance(evaluation, dict):
                passed = evaluation.get("passed")
                return "章节评估通过。" if passed else "章节评估需要修订。"
        if task_type == "summary_orchestrate" and isinstance(result.get("summary_payload"), dict):
            payload = result.get("summary_payload") or {}
            return f"已生成第{payload.get('start_chapter', '?')}-{payload.get('end_chapter', '?')}章阶段总结。"
        return f"{task_type or '任务'} 已完成。"

    def _build_agent_handoff(
        self,
        *,
        task: TaskDefinition,
        runtime_task: TaskDefinition,
        task_type: str,
        agent_name: str,
        result: Dict[str, Any],
        context_snapshot_id: str,
        context_delta: Dict[str, Any],
        output_validation: Dict[str, Any],
        required_context_keys: List[str],
    ) -> Dict[str, Any]:
        produced_keys = self._unique_strings(
            list((context_delta or {}).get("added_keys") or [])
            + list((context_delta or {}).get("updated_keys") or [])
        )
        artifact_refs = self._extract_artifact_refs(task, result)
        summary = self._summarize_result_for_handoff(task_type, result)
        risks: List[str] = []
        if (output_validation or {}).get("warning_outputs"):
            risks.append("输出缺少建议字段：" + "、".join(output_validation.get("warning_outputs") or []))
        if not (output_validation or {}).get("passed", True):
            risks.append("输出校验未通过")

        handoff = AgentHandoff(
            artifact_id=artifact_refs[0] if artifact_refs else context_snapshot_id,
            artifact_type=str(task_type or "").strip(),
            task_id=str(runtime_task.task_id or task.task_id or "").strip(),
            agent_name=str(agent_name or "").strip(),
            context_snapshot_id=str(context_snapshot_id or "").strip(),
            decisions=[summary] if summary else [],
            dependencies=[str(item) for item in (task.depends_on or [])],
            new_facts=[
                f"{key}: {(context_delta.get('summaries') or {}).get(key, {}).get('preview') or (context_delta.get('summaries') or {}).get(key, {}).get('type') or 'updated'}"
                for key in list((context_delta or {}).get("added_keys") or [])[:8]
            ],
            changed_facts=[
                f"{key}: {(context_delta.get('overwrite_reasons') or {}).get(key, 'updated')}"
                for key in list((context_delta or {}).get("updated_keys") or [])[:8]
            ],
            risks=risks,
            next_context_summary=summary,
            artifact_refs=artifact_refs,
            context_delta_id=str((context_delta or {}).get("delta_id") or "").strip(),
            consumed_context_keys=self._unique_strings(list(required_context_keys or []) + list((task.inputs or {}).keys())),
            produced_context_keys=produced_keys,
            output_validation=dict(output_validation or {}),
        )
        return handoff.to_dict()

    def _update_task_metadata(
        self,
        *,
        task: TaskDefinition,
        runtime_task: TaskDefinition,
        candidate_names: List[str],
        route_reason: str,
        candidate_source: str,
        context_snapshot_id: str,
        execution_mode: str,
        selected_agent_name: str,
        fallback_provenance: Optional[Dict[str, Any]] = None,
        selected_model: str = "",
        required_context_keys: Optional[List[str]] = None,
        missing_context_keys: Optional[List[str]] = None,
        source_of_truth_summary: Optional[Dict[str, str]] = None,
        output_validation: Optional[Dict[str, Any]] = None,
        handoff: Optional[Dict[str, Any]] = None,
        context_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        model_label = str(selected_model or self._resolve_agent_model(selected_agent_name) or "").strip()
        metadata_patch = {
            "route_reason": route_reason,
            "candidate_source": candidate_source,
            "context_snapshot_id": context_snapshot_id,
            "execution_mode": execution_mode,
            "selected_agent": selected_agent_name,
            "fallback_provenance": dict(fallback_provenance or {}),
        }
        if required_context_keys is not None:
            metadata_patch["required_context_keys"] = self._unique_strings(required_context_keys)
        if missing_context_keys is not None:
            metadata_patch["missing_context_keys"] = self._unique_strings(missing_context_keys)
        if source_of_truth_summary is not None:
            metadata_patch["source_of_truth_summary"] = dict(source_of_truth_summary or {})
        if output_validation is not None:
            metadata_patch["output_validation"] = dict(output_validation or {})
        if handoff is not None:
            metadata_patch["handoff"] = dict(handoff or {})
        if context_delta is not None:
            metadata_patch["context_delta"] = dict(context_delta or {})
            if isinstance(context_delta, dict) and context_delta.get("delta_id"):
                metadata_patch["context_delta_id"] = str(context_delta.get("delta_id") or "").strip()
        if model_label:
            metadata_patch.update({
                "model": model_label,
                "current_model": model_label,
                "active_model": model_label,
                "model_used": model_label,
            })
        task.candidate_agents = list(candidate_names or [])
        task.metadata.update(metadata_patch)
        task.touch()

        runtime_task.candidate_agents = list(candidate_names or [])
        runtime_task.metadata.update(metadata_patch)
        runtime_task.touch()

    def flush_deferred_persistence(self) -> None:
        """13.5 批量写入：将缓存的事件和快照一次性持久化到磁盘。"""
        if (
            not self._deferred_events
            and not self._deferred_snapshots
            and not self._deferred_handoffs
            and not self._deferred_context_deltas
        ):
            return

        project_manager = self._get_project_manager()

        # 批量写入快照
        if self._deferred_snapshots:
            snapshot_store = project_manager.load_project_state("collab_context_snapshots", default={})
            if not isinstance(snapshot_store, dict):
                snapshot_store = {}
            snapshot_store.setdefault("items", [])
            items = [
                item for item in snapshot_store.get("items", [])
                if isinstance(item, dict)
            ]
            items.extend(self._deferred_snapshots)
            if len(items) > 200:
                items = items[-200:]
            snapshot_store["items"] = items
            snapshot_store["updated_at"] = datetime.now().isoformat()
            project_manager.save_project_state("collab_context_snapshots", snapshot_store)
            self._deferred_snapshots.clear()

        if self._deferred_context_deltas:
            delta_store = project_manager.load_project_state("collab_context_deltas", default={})
            if not isinstance(delta_store, dict):
                delta_store = {}
            delta_items = [
                item for item in delta_store.get("items", [])
                if isinstance(item, dict)
            ]
            delta_items.extend(self._deferred_context_deltas)
            if len(delta_items) > 300:
                delta_items = delta_items[-300:]
            delta_store["items"] = delta_items
            delta_store["updated_at"] = datetime.now().isoformat()
            project_manager.save_project_state("collab_context_deltas", delta_store)
            self._deferred_context_deltas.clear()

        if self._deferred_handoffs:
            handoff_store = project_manager.load_project_state("collab_handoffs", default={})
            if not isinstance(handoff_store, dict):
                handoff_store = {}
            handoff_items = [
                item for item in handoff_store.get("items", [])
                if isinstance(item, dict)
            ]
            handoff_items.extend(self._deferred_handoffs)
            if len(handoff_items) > 300:
                handoff_items = handoff_items[-300:]
            handoff_store["items"] = handoff_items
            handoff_store["updated_at"] = datetime.now().isoformat()
            project_manager.save_project_state("collab_handoffs", handoff_store)
            self._deferred_handoffs.clear()

        # 批量写入事件
        if self._deferred_events:
            trace = project_manager.load_project_state("collab_execution_trace", default={})
            if not isinstance(trace, dict):
                trace = {}
            trace.setdefault("events", [])
            trace.setdefault("runtime_events", [])
            trace.setdefault("status", "initialized")
            trace.setdefault("supervised_mode", bool(self.supervised_mode_provider()))
            trace.setdefault("fallback_to_orchestrated", bool(self.fallback_to_orchestrated_provider()))

            normalized_events: List[Dict[str, Any]] = []
            for item in trace.get("events", []):
                if not isinstance(item, dict):
                    continue
                normalized_events.append(normalize_legacy_trace_event(item))
            trace["events"] = normalized_events

            runtime_events = [
                item for item in trace.get("runtime_events", [])
                if isinstance(item, dict)
            ]
            flushed_events: List[Dict[str, Any]] = []
            for item in self._deferred_events:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("runtime_event"), dict):
                    event_payload = normalize_legacy_trace_event(item)
                    runtime_event = dict(item.get("runtime_event") or {})
                    resolved_run_id = str(trace.get("contract_id") or trace.get("run_id") or "").strip()
                    if not runtime_event.get("run_id"):
                        runtime_event["run_id"] = resolved_run_id
                    event_payload["run_id"] = runtime_event.get("run_id", "")
                    if isinstance(event_payload.get("runtime_message"), dict) and resolved_run_id:
                        runtime_message = dict(event_payload.get("runtime_message") or {})
                        metadata = dict(runtime_message.get("metadata") or {})
                        metadata.setdefault("run_id", resolved_run_id)
                        runtime_message["metadata"] = metadata
                        event_payload["runtime_message"] = runtime_message
                        if isinstance(runtime_event.get("payload"), dict):
                            runtime_event["payload"]["runtime_message"] = runtime_message
                    event_payload["runtime_event"] = runtime_event
                else:
                    legacy_type = str(item.get("type") or "unknown").strip() or "unknown"
                    event_payload, runtime_event = build_legacy_trace_event(
                        legacy_type,
                        item,
                        timestamp=str(item.get("timestamp") or "").strip(),
                        run_id=str(trace.get("contract_id") or trace.get("run_id") or "").strip(),
                    )
                flushed_events.append(event_payload)
                runtime_events.append(runtime_event)

            trace["events"].extend(flushed_events)
            if len(trace["events"]) > 500:
                trace["events"] = trace["events"][-500:]
            if len(runtime_events) > 500:
                runtime_events = runtime_events[-500:]
            trace["runtime_events"] = runtime_events
            trace["updated_at"] = datetime.now().isoformat()
            project_manager.save_project_state("collab_execution_trace", trace)
            RuntimeEventLog(self._get_project_dir()).safe_append_events(
                event.get("runtime_event", {})
                for event in flushed_events
                if isinstance(event.get("runtime_event"), dict)
            )
            for event in flushed_events:
                runtime_event = event.get("runtime_event") if isinstance(event, dict) else None
                if isinstance(runtime_event, dict):
                    self._append_run_runtime_event(runtime_event)
            self._deferred_events.clear()

    async def dispatch(
        self,
        *,
        envelope: TaskExecutionEnvelope,
        task_pool: TaskPool,
        task: TaskDefinition,
        runtime_pool: TaskPool,
        runtime_task: TaskDefinition,
        fallback_agent: Any = None,
        defer_persist: bool = False,
    ) -> DispatchResult:
        self._ensure_run_state()
        envelope.context = CollabExecutionContext.from_legacy_context(
            self._merge_run_context_overlay(envelope.context.to_dict()),
            stage=envelope.stage,
        )
        fallback_agent_name = str(
            envelope.fallback_agent_name or getattr(fallback_agent, "name", "") or ""
        ).strip()
        ephemeral_agent_name = ""
        required_context_keys = self._prime_required_context_keys(envelope)
        missing_context_keys = envelope.context.missing_keys(required_context_keys)
        source_of_truth_summary = self._source_of_truth_summary(envelope.context, required_context_keys)
        output_validation: Dict[str, Any] = {}
        handoff_payload: Dict[str, Any] = {}
        context_delta_payload: Dict[str, Any] = {}

        self._emit_execution_event(
            "route_start",
            {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "title": envelope.title,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
                "source_of_truth_summary": source_of_truth_summary,
            },
            defer_persist=defer_persist,
        )
        self._record_run_checkpoint(
            node="route_start",
            status="running",
            task_id=runtime_task.task_id,
            task_type=envelope.task_type,
            context=envelope.context.to_dict(),
            task_pool=runtime_pool.to_dict(),
            metadata={
                "title": envelope.title,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
            },
        )
        await self._run_runtime_hooks(
            "before_route",
            {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "title": envelope.title,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
            },
            task_id=runtime_task.task_id,
            task_type=envelope.task_type,
            defer_persist=defer_persist,
        )

        try:
            envelope.validate_required_context()
            if not self.supervised_mode_provider() and fallback_agent is not None:
                selected_agent_name = fallback_agent_name or str(getattr(fallback_agent, "name", "") or "").strip()
                selected_agent = fallback_agent
                candidate_names: List[str] = []
                route_reason = f"matched explicit route {envelope.task_type} via direct fallback because supervised_mode is disabled"
                candidate_source = "fallback_direct"
            else:
                decision = self.routing_policy.resolve(
                    task_type=envelope.task_type,
                    stage=envelope.stage,
                    context=envelope.context,
                    capability_registry=self._get_capability_registry(),
                    input_data=envelope.input_data,
                    fallback_agent_name=fallback_agent_name,
                )
                selected_agent_name = str(decision.agent_name or "").strip()
                candidate_names = list(decision.candidate_names or [])
                route_reason = decision.route_reason
                candidate_source = decision.candidate_source
                if decision.required_context_keys:
                    required_context_keys = self._unique_strings(
                        list(required_context_keys) + list(decision.required_context_keys or [])
                    )
                    envelope.required_context_keys = required_context_keys
                    missing_context_keys = envelope.context.missing_keys(required_context_keys)
                    source_of_truth_summary = self._source_of_truth_summary(envelope.context, required_context_keys)
                selected_agent = self._resolve_agent_instance(selected_agent_name, fallback_agent=fallback_agent)
                if selected_agent is None:
                    raise RuntimeError(f"任务 {envelope.task_type} 缺少可执行Agent: {selected_agent_name}")
        except Exception as exc:
            if isinstance(exc, RoutingPolicyError):
                try:
                    selected_agent, selected_agent_name, registered = self._register_ephemeral_agent(
                        envelope,
                        reason=str(exc),
                    )
                    if registered and selected_agent is not None:
                        ephemeral_agent_name = selected_agent_name
                        candidate_names = [selected_agent_name]
                        route_reason = (
                            f"{str(exc)}; created task-scoped ephemeral agent {selected_agent_name}"
                        )
                        candidate_source = "ephemeral_agent"
                    else:
                        raise
                except Exception:
                    route_reason = str(exc)
                    candidate_source = "route_rejected"
                    context_snapshot_id = self._record_context_snapshot(
                        envelope=envelope,
                        route_reason=route_reason,
                        candidate_source=candidate_source,
                        candidate_agents=[],
                    )
                    task_pool.fail_task(task.task_id, error=route_reason)
                    runtime_pool.fail_task(runtime_task.task_id, error=route_reason)
                    self._update_task_metadata(
                        task=task,
                        runtime_task=runtime_task,
                        candidate_names=[],
                        route_reason=route_reason,
                        candidate_source=candidate_source,
                        context_snapshot_id=context_snapshot_id,
                        execution_mode="rejected",
                        selected_agent_name="",
                        required_context_keys=required_context_keys,
                        missing_context_keys=missing_context_keys,
                        source_of_truth_summary=source_of_truth_summary,
                    )
                    self.save_runtime_task_pool(runtime_pool)
                    self._emit_execution_event(
                        "route_end",
                        {
                            "task_id": runtime_task.task_id,
                            "task_type": envelope.task_type,
                            "title": envelope.title,
                            "status": "failed",
                            "reason": route_reason,
                            "candidate_source": candidate_source,
                            "context_snapshot_id": context_snapshot_id,
                            "required_context_keys": required_context_keys,
                            "missing_context_keys": missing_context_keys,
                        },
                        defer_persist=defer_persist,
                    )
                    self._append_execution_event(
                        "task_rejected",
                        {
                            "task_id": runtime_task.task_id,
                            "task_type": envelope.task_type,
                            "title": envelope.title,
                            "reason": route_reason,
                            "context_snapshot_id": context_snapshot_id,
                            "required_context_keys": required_context_keys,
                            "missing_context_keys": missing_context_keys,
                        },
                    )
                    raise
            else:
                route_reason = str(exc)
                candidate_source = "route_rejected"
                context_snapshot_id = self._record_context_snapshot(
                    envelope=envelope,
                    route_reason=route_reason,
                    candidate_source=candidate_source,
                    candidate_agents=[],
                )
                task_pool.fail_task(task.task_id, error=route_reason)
                runtime_pool.fail_task(runtime_task.task_id, error=route_reason)
                self._update_task_metadata(
                    task=task,
                    runtime_task=runtime_task,
                    candidate_names=[],
                    route_reason=route_reason,
                    candidate_source=candidate_source,
                    context_snapshot_id=context_snapshot_id,
                    execution_mode="rejected",
                    selected_agent_name="",
                    required_context_keys=required_context_keys,
                    missing_context_keys=missing_context_keys,
                    source_of_truth_summary=source_of_truth_summary,
                )
                self.save_runtime_task_pool(runtime_pool)
                self._emit_execution_event(
                    "route_end",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "title": envelope.title,
                        "status": "failed",
                        "reason": route_reason,
                        "candidate_source": candidate_source,
                        "context_snapshot_id": context_snapshot_id,
                        "required_context_keys": required_context_keys,
                        "missing_context_keys": missing_context_keys,
                    },
                    defer_persist=defer_persist,
                )
                self._append_execution_event(
                    "task_rejected",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "title": envelope.title,
                        "reason": route_reason,
                        "context_snapshot_id": context_snapshot_id,
                        "required_context_keys": required_context_keys,
                        "missing_context_keys": missing_context_keys,
                    },
                )
                raise

        context_snapshot_id = self._record_context_snapshot(
            envelope=envelope,
            route_reason=route_reason,
            candidate_source=candidate_source,
            candidate_agents=candidate_names,
            defer_persist=defer_persist,
        )
        self._emit_execution_event(
            "route_end",
            {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "title": envelope.title,
                "assigned_agent": selected_agent_name,
                "candidate_agents": candidate_names,
                "candidate_source": candidate_source,
                "route_reason": route_reason,
                "context_snapshot_id": context_snapshot_id,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
                "source_of_truth_summary": source_of_truth_summary,
            },
            defer_persist=defer_persist,
        )
        self._record_run_checkpoint(
            node="route_end",
            status="running",
            task_id=runtime_task.task_id,
            task_type=envelope.task_type,
            agent_name=selected_agent_name,
            context=envelope.context.to_dict(),
            task_pool=runtime_pool.to_dict(),
            metadata={
                "candidate_agents": candidate_names,
                "candidate_source": candidate_source,
                "route_reason": route_reason,
                "context_snapshot_id": context_snapshot_id,
            },
        )
        await self._run_runtime_hooks(
            "after_route",
            {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "assigned_agent": selected_agent_name,
                "candidate_agents": candidate_names,
                "candidate_source": candidate_source,
                "route_reason": route_reason,
                "context_snapshot_id": context_snapshot_id,
            },
            task_id=runtime_task.task_id,
            task_type=envelope.task_type,
            agent_name=selected_agent_name,
            defer_persist=defer_persist,
        )

        claimed_by = selected_agent_name or str(getattr(selected_agent, "name", "") or "").strip()
        selected_model = self._resolve_agent_model(claimed_by, selected_agent)
        fallback_provenance: Dict[str, Any] = {}
        execution_mode = "autonomous"
        fallback_used = candidate_source == "fallback_direct"
        autonomous_error = ""

        self._update_task_metadata(
            task=task,
            runtime_task=runtime_task,
            candidate_names=candidate_names,
            route_reason=route_reason,
            candidate_source=candidate_source,
            context_snapshot_id=context_snapshot_id,
            execution_mode=execution_mode,
            selected_agent_name=claimed_by,
            selected_model=selected_model,
            required_context_keys=required_context_keys,
            missing_context_keys=missing_context_keys,
            source_of_truth_summary=source_of_truth_summary,
        )
        task_pool.claim_task(task.task_id, claimed_by)
        task_pool.start_task(task.task_id, claimed_by)
        runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.CLAIMED, assigned_agent=claimed_by)
        runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.RUNNING, assigned_agent=claimed_by)
        # 问题17修复：runtime_pool 状态必须立即持久化，不能延迟
        self.save_runtime_task_pool(runtime_pool)
        self._emit_execution_event(
            "task_claimed",
            {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "title": envelope.title,
                "assigned_agent": claimed_by,
                "candidate_source": candidate_source,
                "route_reason": route_reason,
                "context_snapshot_id": context_snapshot_id,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
                "model": selected_model,
                "current_model": selected_model,
                "active_model": selected_model,
                "model_used": selected_model,
            },
            defer_persist=defer_persist,
        )
        # 13.5 延迟模式：缓存事件而非立即写盘
        _task_started_event = {
            "task_id": runtime_task.task_id,
            "task_type": envelope.task_type,
            "assigned_agent": claimed_by,
            "fallback_candidate": fallback_agent_name,
            "route_reason": route_reason,
            "candidate_source": candidate_source,
            "context_snapshot_id": context_snapshot_id,
            "required_context_keys": required_context_keys,
            "missing_context_keys": missing_context_keys,
            "model": selected_model,
            "current_model": selected_model,
            "active_model": selected_model,
            "model_used": selected_model,
        }
        if defer_persist:
            self._deferred_events.append({
                "type": "task_started",
                "timestamp": datetime.now().isoformat(),
                **_task_started_event,
            })
        else:
            self._append_execution_event("task_started", _task_started_event)
        self._record_run_checkpoint(
            node="task_start",
            status="running",
            task_id=runtime_task.task_id,
            task_type=envelope.task_type,
            agent_name=claimed_by,
            context=envelope.context.to_dict(),
            task_pool=runtime_pool.to_dict(),
            metadata={
                "context_snapshot_id": context_snapshot_id,
                "candidate_source": candidate_source,
                "route_reason": route_reason,
            },
        )

        await self.notify_progress(
            {
                "type": "sub_agent_started",
                "stage": envelope.task_type,
                "agent": claimed_by,
                "task_type": envelope.task_type,
                "title": str(envelope.title or envelope.task_type).strip(),
                "message": f"{claimed_by} 正在执行: {envelope.title or envelope.task_type}",
                "model": selected_model,
                "current_model": selected_model,
                "active_model": selected_model,
                "model_used": selected_model,
            }
        )

        current_context = envelope.context.clone()
        try:
            before_dispatch_results = await self._run_runtime_hooks(
                "before_task_dispatch",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "input_keys": sorted(str(key) for key in (envelope.input_data or {}).keys()),
                },
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                defer_persist=defer_persist,
            )
            task_block = next(
                (
                    item for item in before_dispatch_results
                    if isinstance(item, dict) and item.get("block")
                ),
                None,
            )
            if task_block:
                block_reason = str(task_block.get("reason") or "runtime hook blocked task").strip()
                task_pool.block_task(task.task_id, block_reason)
                runtime_pool.block_task(runtime_task.task_id, block_reason)
                self.save_runtime_task_pool(runtime_pool)
                self._emit_execution_event(
                    "task_blocked",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": claimed_by,
                        "reason": block_reason,
                        "context_snapshot_id": context_snapshot_id,
                    },
                    defer_persist=defer_persist,
                )
                return DispatchResult(
                    success=False,
                    agent_name=claimed_by,
                    result={"success": False, "blocked": True, "reason": block_reason},
                    route_reason=route_reason,
                    candidate_source=candidate_source,
                    candidate_agents=candidate_names,
                    context_snapshot_id=context_snapshot_id,
                    execution_mode="blocked",
                    context=current_context.to_dict(),
                    task_pool=task_pool.to_dict(),
                    runtime_task_pool=runtime_pool.to_dict(),
                )

            result = await selected_agent.execute(envelope.input_data, context=current_context.to_agent_context())
            after_result_results = await self._run_runtime_hooks(
                "after_task_result",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "result_keys": sorted(str(key) for key in (result or {}).keys()) if isinstance(result, dict) else [],
                },
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                defer_persist=defer_persist,
            )
            for hook_result in after_result_results:
                if isinstance(hook_result, dict) and isinstance(hook_result.get("result_patch"), dict) and isinstance(result, dict):
                    result.update(hook_result["result_patch"])
            self._emit_execution_event(
                "validation_start",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "expected_outputs": list(task.expected_outputs or []),
                },
                defer_persist=defer_persist,
            )
            output_validation = validate_task_outputs(
                task_type=envelope.task_type,
                expected_outputs=task.expected_outputs,
                result=result,
            )
            self._emit_execution_event(
                "validation_end",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                },
                defer_persist=defer_persist,
            )
            if (
                not isinstance(result, dict)
                or not result.get("success", True)
                or not output_validation.get("passed", False)
            ):
                failure_msg = _format_agent_failure(result)
                if isinstance(result, dict) and result.get("success", True) and not output_validation.get("passed", False):
                    failure_msg = format_output_validation_error(output_validation)
                logger.warning(
                    f"[AgentDispatcher] 任务首次执行失败，task_type={envelope.task_type}, "
                    f"agent={claimed_by}, reason={failure_msg[:200]}，正在重试..."
                )
                retry_context = envelope.context.clone()
                result = await selected_agent.execute(
                    envelope.input_data, context=retry_context.to_agent_context()
                )
                self._emit_execution_event(
                    "validation_start",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": claimed_by,
                        "context_snapshot_id": context_snapshot_id,
                        "expected_outputs": list(task.expected_outputs or []),
                        "attempt": "retry",
                    },
                    defer_persist=defer_persist,
                )
                output_validation = validate_task_outputs(
                    task_type=envelope.task_type,
                    expected_outputs=task.expected_outputs,
                    result=result,
                )
                self._emit_execution_event(
                    "validation_end",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": claimed_by,
                        "context_snapshot_id": context_snapshot_id,
                        "output_validation": output_validation,
                        "attempt": "retry",
                    },
                    defer_persist=defer_persist,
                )
                if (
                    not isinstance(result, dict)
                    or not result.get("success", True)
                    or not output_validation.get("passed", False)
                ):
                    if isinstance(result, dict) and result.get("success", True) and not output_validation.get("passed", False):
                        raise RuntimeError(format_output_validation_error(output_validation))
                    raise RuntimeError(_format_agent_failure(result))
            if bool(result.get("fallback_used")) or bool(result.get("coverage_fallback_used")):
                fallback_used = True

            artifact_refs = self._extract_artifact_refs(task, result)
            if artifact_refs or isinstance(result, dict):
                result_keys = sorted(str(key) for key in (result or {}).keys()) if isinstance(result, dict) else []
                self._emit_execution_event(
                    "artifact_created",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": claimed_by,
                        "context_snapshot_id": context_snapshot_id,
                        "artifact_refs": artifact_refs,
                        "result_keys": result_keys,
                    },
                    defer_persist=defer_persist,
                )
                self._append_run_artifact(
                    task_id=runtime_task.task_id,
                    task_type=envelope.task_type,
                    agent_name=claimed_by,
                    artifact_refs=artifact_refs,
                    result_keys=result_keys,
                    metadata={"context_snapshot_id": context_snapshot_id},
                )

            before_context = current_context.to_dict()
            current_context.apply_task_result(envelope.task_type, result)
            context_delta_payload = build_context_delta(
                before=before_context,
                after=current_context.to_dict(),
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
            ).to_dict()
            self._persist_context_delta(context_delta_payload, defer_persist=defer_persist)
            self._sync_run_memory(
                context=current_context.to_dict(),
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                context_delta=context_delta_payload,
            )
            self._emit_execution_event(
                "context_delta_created",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "added_keys": context_delta_payload.get("added_keys", []),
                    "updated_keys": context_delta_payload.get("updated_keys", []),
                    "removed_keys": context_delta_payload.get("removed_keys", []),
                },
                defer_persist=defer_persist,
            )
            await self._run_runtime_hooks(
                "after_context_delta",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "added_keys": context_delta_payload.get("added_keys", []),
                    "updated_keys": context_delta_payload.get("updated_keys", []),
                    "removed_keys": context_delta_payload.get("removed_keys", []),
                },
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                defer_persist=defer_persist,
            )
            handoff_payload = self._build_agent_handoff(
                task=task,
                runtime_task=runtime_task,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                result=result,
                context_snapshot_id=context_snapshot_id,
                context_delta=context_delta_payload,
                output_validation=output_validation,
                required_context_keys=required_context_keys,
            )
            self._persist_handoff(handoff_payload, defer_persist=defer_persist)
            self._emit_execution_event(
                "handoff_created",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "handoff": handoff_payload,
                },
                defer_persist=defer_persist,
            )
            if envelope.task_type == "content_read":
                self._persist_permanent_memory(current_context.permanent_memory)

            if task.review_required:
                task_pool.mark_review_required(task.task_id)
                runtime_pool.mark_review_required(runtime_task.task_id)
            task_pool.complete_task(task.task_id)
            runtime_pool.complete_task(runtime_task.task_id)
            self._update_task_metadata(
                task=task,
                runtime_task=runtime_task,
                candidate_names=candidate_names,
                route_reason=route_reason,
                candidate_source=candidate_source,
                context_snapshot_id=context_snapshot_id,
                execution_mode=execution_mode,
                selected_agent_name=claimed_by,
                fallback_provenance=fallback_provenance,
                selected_model=selected_model,
                required_context_keys=required_context_keys,
                missing_context_keys=missing_context_keys,
                source_of_truth_summary=source_of_truth_summary,
                output_validation=output_validation,
                handoff=handoff_payload,
                context_delta=context_delta_payload,
            )
            # 问题17修复：runtime_pool 状态必须立即持久化，不能延迟
            self.save_runtime_task_pool(runtime_pool)
            # 13.5 延迟模式：缓存事件而非立即写盘
            _task_completed_event = {
                "task_id": runtime_task.task_id,
                "task_type": envelope.task_type,
                "assigned_agent": claimed_by,
                "review_required": bool(task.review_required),
                "route_reason": route_reason,
                "candidate_source": candidate_source,
                "context_snapshot_id": context_snapshot_id,
                "fallback_used": fallback_used,
                "required_context_keys": required_context_keys,
                "missing_context_keys": missing_context_keys,
                "output_validation": output_validation,
                "context_delta_id": context_delta_payload.get("delta_id", ""),
                "handoff": handoff_payload,
                "model": selected_model,
                "current_model": selected_model,
                "active_model": selected_model,
                "model_used": selected_model,
            }
            if defer_persist:
                self._deferred_events.append({
                    "type": "task_completed",
                    "timestamp": datetime.now().isoformat(),
                    **_task_completed_event,
                })
            else:
                self._append_execution_event("task_completed", _task_completed_event)
            self._record_run_checkpoint(
                node="task_end",
                status="completed",
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                context=current_context.to_dict(),
                task_pool=runtime_pool.to_dict(),
                metadata={
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "fallback_used": fallback_used,
                },
            )
            await self.notify_progress(
                {
                    "type": "sub_agent_completed",
                    "stage": envelope.task_type,
                    "agent": claimed_by,
                    "task_type": envelope.task_type,
                    "title": str(envelope.title or envelope.task_type).strip(),
                    "message": f"{claimed_by} 完成: {envelope.title or envelope.task_type}",
                    "model": selected_model,
                    "current_model": selected_model,
                    "active_model": selected_model,
                    "model_used": selected_model,
                }
            )
        except Exception as exc:
            autonomous_error = str(exc)
            logger.warning(
                f"[AgentDispatcher] 自治任务执行失败，task_type={envelope.task_type}, agent={claimed_by}, error={autonomous_error}"
            )
            task_pool.fail_task(task.task_id, error=autonomous_error)
            runtime_pool.fail_task(runtime_task.task_id, error=autonomous_error)
            self._update_task_metadata(
                task=task,
                runtime_task=runtime_task,
                candidate_names=candidate_names,
                route_reason=route_reason,
                candidate_source=candidate_source,
                context_snapshot_id=context_snapshot_id,
                execution_mode=execution_mode,
                selected_agent_name=claimed_by,
                fallback_provenance=fallback_provenance,
                selected_model=selected_model,
                required_context_keys=required_context_keys,
                missing_context_keys=missing_context_keys,
                source_of_truth_summary=source_of_truth_summary,
                output_validation=output_validation,
            )
            self.save_runtime_task_pool(runtime_pool)
            self._append_execution_event(
                "task_failed",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": claimed_by,
                    "error": autonomous_error,
                    "route_reason": route_reason,
                    "candidate_source": candidate_source,
                    "context_snapshot_id": context_snapshot_id,
                    "required_context_keys": required_context_keys,
                    "missing_context_keys": missing_context_keys,
                    "output_validation": output_validation,
                    "model": selected_model,
                    "current_model": selected_model,
                    "active_model": selected_model,
                    "model_used": selected_model,
                },
            )
            self._record_run_checkpoint(
                node="task_failed",
                status="failed",
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=claimed_by,
                context=current_context.to_dict(),
                task_pool=runtime_pool.to_dict(),
                metadata={
                    "error": autonomous_error,
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                },
            )
            await self.notify_progress(
                {
                    "type": "sub_agent_failed",
                    "stage": envelope.task_type,
                    "agent": claimed_by,
                    "task_type": envelope.task_type,
                    "title": str(envelope.title or envelope.task_type).strip(),
                    "error": autonomous_error,
                    "message": f"{claimed_by} 执行失败: {autonomous_error[:100]}",
                    "model": selected_model,
                    "current_model": selected_model,
                    "active_model": selected_model,
                    "model_used": selected_model,
                }
            )

            can_fallback = (
                self.fallback_to_orchestrated_provider()
                and fallback_agent is not None
                and fallback_agent is not selected_agent
            )
            if not can_fallback:
                if ephemeral_agent_name:
                    self._unregister_ephemeral_agent(ephemeral_agent_name)
                raise

            retry_claimed_by = fallback_agent_name or str(getattr(fallback_agent, "name", "") or "").strip()
            retry_model = self._resolve_agent_model(retry_claimed_by, fallback_agent)
            retry_task = task_pool.create_task(
                task_type=envelope.task_type,
                title=f"{envelope.title or envelope.task_type}-fallback",
                description=f"{task.description}（fallback）" if task.description else "fallback",
                inputs=dict(envelope.input_data or {}),
                expected_outputs=list(task.expected_outputs or []),
                candidate_agents=[retry_claimed_by] if retry_claimed_by else [],
                review_required=bool(task.review_required),
                metadata={
                    "route_reason": route_reason,
                    "candidate_source": candidate_source,
                    "context_snapshot_id": context_snapshot_id,
                    "fallback_provenance": {
                        "from_agent": claimed_by,
                        "reason": autonomous_error,
                    },
                    "required_context_keys": required_context_keys,
                    "missing_context_keys": missing_context_keys,
                    "source_of_truth_summary": source_of_truth_summary,
                    "model": retry_model,
                    "current_model": retry_model,
                    "active_model": retry_model,
                    "model_used": retry_model,
                },
            )
            task_pool.claim_task(retry_task.task_id, retry_claimed_by)
            task_pool.start_task(retry_task.task_id, retry_claimed_by)
            runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.CLAIMED, assigned_agent=retry_claimed_by)
            runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.RUNNING, assigned_agent=retry_claimed_by)
            execution_mode = "fallback_orchestrated"
            fallback_used = True
            fallback_provenance = {
                "from_agent": claimed_by,
                "to_agent": retry_claimed_by,
                "reason": autonomous_error,
            }
            self._update_task_metadata(
                task=task,
                runtime_task=runtime_task,
                candidate_names=candidate_names,
                route_reason=route_reason,
                candidate_source=candidate_source,
                context_snapshot_id=context_snapshot_id,
                execution_mode=execution_mode,
                selected_agent_name=retry_claimed_by,
                fallback_provenance=fallback_provenance,
                selected_model=retry_model,
                required_context_keys=required_context_keys,
                missing_context_keys=missing_context_keys,
                source_of_truth_summary=source_of_truth_summary,
                output_validation=output_validation,
            )
            self.save_runtime_task_pool(runtime_pool)
            self._append_execution_event(
                "task_fallback_started",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_from": claimed_by,
                    "context_snapshot_id": context_snapshot_id,
                    "required_context_keys": required_context_keys,
                    "missing_context_keys": missing_context_keys,
                    "model": retry_model,
                    "current_model": retry_model,
                    "active_model": retry_model,
                    "model_used": retry_model,
                },
            )
            await self.notify_progress(
                {
                    "type": "sub_agent_fallback",
                    "stage": envelope.task_type,
                    "agent": retry_claimed_by,
                    "task_type": envelope.task_type,
                    "title": str(envelope.title or envelope.task_type).strip(),
                    "fallback_from": claimed_by,
                    "message": f"{retry_claimed_by} 回退执行: {envelope.title or envelope.task_type}",
                    "model": retry_model,
                    "current_model": retry_model,
                    "active_model": retry_model,
                    "model_used": retry_model,
                }
            )

            result = await fallback_agent.execute(envelope.input_data, context=envelope.context.to_agent_context())
            self._emit_execution_event(
                "validation_start",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "context_snapshot_id": context_snapshot_id,
                    "expected_outputs": list(task.expected_outputs or []),
                },
                defer_persist=defer_persist,
            )
            output_validation = validate_task_outputs(
                task_type=envelope.task_type,
                expected_outputs=task.expected_outputs,
                result=result,
            )
            self._emit_execution_event(
                "validation_end",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                },
                defer_persist=defer_persist,
            )
            if (
                not isinstance(result, dict)
                or not result.get("success", True)
                or not output_validation.get("passed", False)
            ):
                fallback_error = str((result or {}).get("error") or "fallback_task_failed")
                if isinstance(result, dict) and result.get("success", True) and not output_validation.get("passed", False):
                    fallback_error = format_output_validation_error(output_validation)
                task_pool.fail_task(retry_task.task_id, error=fallback_error)
                runtime_pool.fail_task(runtime_task.task_id, error=fallback_error)
                self._update_task_metadata(
                    task=task,
                    runtime_task=runtime_task,
                    candidate_names=candidate_names,
                    route_reason=route_reason,
                    candidate_source=candidate_source,
                    context_snapshot_id=context_snapshot_id,
                    execution_mode=execution_mode,
                    selected_agent_name=retry_claimed_by,
                    fallback_provenance=fallback_provenance,
                    selected_model=retry_model,
                    required_context_keys=required_context_keys,
                    missing_context_keys=missing_context_keys,
                    source_of_truth_summary=source_of_truth_summary,
                    output_validation=output_validation,
                )
                self.save_runtime_task_pool(runtime_pool)
                self._append_execution_event(
                    "task_failed",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": retry_claimed_by,
                        "fallback_used": True,
                        "error": fallback_error,
                        "context_snapshot_id": context_snapshot_id,
                        "required_context_keys": required_context_keys,
                        "missing_context_keys": missing_context_keys,
                        "output_validation": output_validation,
                        "model": retry_model,
                        "current_model": retry_model,
                        "active_model": retry_model,
                        "model_used": retry_model,
                    },
                )
                self._emit_execution_event(
                    "fallback_end",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": retry_claimed_by,
                        "fallback_from": claimed_by,
                        "fallback_used": True,
                        "status": "failed",
                        "error": fallback_error,
                        "context_snapshot_id": context_snapshot_id,
                        "output_validation": output_validation,
                    },
                    defer_persist=defer_persist,
                )
                if ephemeral_agent_name:
                    self._unregister_ephemeral_agent(ephemeral_agent_name)
                raise RuntimeError(fallback_error)

            artifact_refs = self._extract_artifact_refs(retry_task, result)
            if artifact_refs or isinstance(result, dict):
                result_keys = sorted(str(key) for key in (result or {}).keys()) if isinstance(result, dict) else []
                self._emit_execution_event(
                    "artifact_created",
                    {
                        "task_id": runtime_task.task_id,
                        "task_type": envelope.task_type,
                        "assigned_agent": retry_claimed_by,
                        "fallback_used": True,
                        "context_snapshot_id": context_snapshot_id,
                        "artifact_refs": artifact_refs,
                        "result_keys": result_keys,
                    },
                    defer_persist=defer_persist,
                )
                self._append_run_artifact(
                    task_id=runtime_task.task_id,
                    task_type=envelope.task_type,
                    agent_name=retry_claimed_by,
                    artifact_refs=artifact_refs,
                    result_keys=result_keys,
                    metadata={"context_snapshot_id": context_snapshot_id, "fallback_used": True},
                )

            current_context = envelope.context.clone()
            before_context = current_context.to_dict()
            current_context.apply_task_result(envelope.task_type, result)
            context_delta_payload = build_context_delta(
                before=before_context,
                after=current_context.to_dict(),
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=retry_claimed_by,
            ).to_dict()
            self._persist_context_delta(context_delta_payload, defer_persist=defer_persist)
            self._sync_run_memory(
                context=current_context.to_dict(),
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=retry_claimed_by,
                context_delta=context_delta_payload,
            )
            self._emit_execution_event(
                "context_delta_created",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "context_snapshot_id": context_snapshot_id,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "added_keys": context_delta_payload.get("added_keys", []),
                    "updated_keys": context_delta_payload.get("updated_keys", []),
                    "removed_keys": context_delta_payload.get("removed_keys", []),
                },
                defer_persist=defer_persist,
            )
            handoff_payload = self._build_agent_handoff(
                task=retry_task,
                runtime_task=runtime_task,
                task_type=envelope.task_type,
                agent_name=retry_claimed_by,
                result=result,
                context_snapshot_id=context_snapshot_id,
                context_delta=context_delta_payload,
                output_validation=output_validation,
                required_context_keys=required_context_keys,
            )
            self._persist_handoff(handoff_payload, defer_persist=defer_persist)
            self._emit_execution_event(
                "handoff_created",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "context_snapshot_id": context_snapshot_id,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "handoff": handoff_payload,
                },
                defer_persist=defer_persist,
            )
            if envelope.task_type == "content_read":
                self._persist_permanent_memory(current_context.permanent_memory)
            if task.review_required:
                task_pool.mark_review_required(retry_task.task_id)
                runtime_pool.mark_review_required(runtime_task.task_id)
            task_pool.complete_task(retry_task.task_id)
            runtime_pool.complete_task(runtime_task.task_id)
            self._update_task_metadata(
                task=task,
                runtime_task=runtime_task,
                candidate_names=candidate_names,
                route_reason=route_reason,
                candidate_source=candidate_source,
                context_snapshot_id=context_snapshot_id,
                execution_mode=execution_mode,
                selected_agent_name=retry_claimed_by,
                fallback_provenance=fallback_provenance,
                selected_model=retry_model,
                required_context_keys=required_context_keys,
                missing_context_keys=missing_context_keys,
                source_of_truth_summary=source_of_truth_summary,
                output_validation=output_validation,
                handoff=handoff_payload,
                context_delta=context_delta_payload,
            )
            self.save_runtime_task_pool(runtime_pool)
            self._emit_execution_event(
                "fallback_end",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_from": claimed_by,
                    "fallback_used": True,
                    "status": "completed",
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                },
                defer_persist=defer_persist,
            )
            self._append_execution_event(
                "task_completed",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "review_required": bool(task.review_required),
                    "context_snapshot_id": context_snapshot_id,
                    "required_context_keys": required_context_keys,
                    "missing_context_keys": missing_context_keys,
                    "output_validation": output_validation,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "handoff": handoff_payload,
                    "model": retry_model,
                    "current_model": retry_model,
                    "active_model": retry_model,
                    "model_used": retry_model,
                },
            )
            self._record_run_checkpoint(
                node="task_end",
                status="completed",
                task_id=runtime_task.task_id,
                task_type=envelope.task_type,
                agent_name=retry_claimed_by,
                context=current_context.to_dict(),
                task_pool=runtime_pool.to_dict(),
                metadata={
                    "context_snapshot_id": context_snapshot_id,
                    "output_validation": output_validation,
                    "context_delta_id": context_delta_payload.get("delta_id", ""),
                    "fallback_used": True,
                    "fallback_from": claimed_by,
                },
            )
            claimed_by = retry_claimed_by

        if ephemeral_agent_name:
            self._unregister_ephemeral_agent(ephemeral_agent_name)

        return DispatchResult(
            success=True,
            agent_name=claimed_by,
            result=result,
            route_reason=route_reason,
            candidate_source=candidate_source,
            candidate_agents=candidate_names,
            context_snapshot_id=context_snapshot_id,
            fallback_used=fallback_used,
            fallback_agent=fallback_agent_name,
            fallback_provenance=fallback_provenance,
            autonomous_error=autonomous_error,
            execution_mode=execution_mode,
            context=current_context.to_dict(),
            task_pool=task_pool.to_dict(),
            runtime_task_pool=runtime_pool.to_dict(),
            output_validation=output_validation,
            handoff=handoff_payload,
            context_delta=context_delta_payload,
        )

    async def run_autonomous_task(
        self,
        *,
        task_type: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        fallback_agent: Any = None,
        stage: str = "",
        title: str = "",
        description: str = "",
        expected_outputs: Optional[List[str]] = None,
        review_required: bool = False,
        defer_persist: bool = False,
    ) -> Dict[str, Any]:
        """Phase 1 unified execution entry: explicit routing + context contract + fallback."""
        from .contracts import TaskDefinition
        from .execution_context import CollabExecutionContext, TaskExecutionEnvelope

        self._ensure_run_state()
        task_pool = TaskPool()
        task = task_pool.create_task(
            task_type=task_type,
            title=title or task_type,
            description=description,
            inputs=dict(input_data or {}),
            expected_outputs=list(expected_outputs or []),
            candidate_agents=[],
            review_required=review_required,
        )
        fallback_agent_name = getattr(fallback_agent, "name", "") if fallback_agent is not None else ""

        runtime_pool, runtime_task = self.runtime_state_store.upsert_runtime_task(
            task_type=task_type,
            title=title or task_type,
            description=description,
            input_data=dict(input_data or {}),
            expected_outputs=list(expected_outputs or []),
            candidate_agents=[],
            review_required=review_required,
            task_metadata={"source": "runtime_autonomous_task"},
        )
        # 13.5 延迟模式：缓存事件而非立即写盘
        _registered_event = {
            "task_id": runtime_task.task_id,
            "task_type": task_type,
            "title": str(title or task_type),
            "stage": str(stage or "").strip(),
            "candidate_agents": [],
        }
        if defer_persist:
            self._deferred_events.append({
                "type": "task_registered",
                "timestamp": datetime.now().isoformat(),
                **_registered_event,
            })
        else:
            self._append_execution_event("task_registered", _registered_event)
        envelope = TaskExecutionEnvelope(
            task_type=task_type,
            stage=str(stage or "").strip(),
            title=str(title or task_type),
            input_data=dict(input_data or {}),
            context=CollabExecutionContext.from_legacy_context(
                context,
                stage=str(stage or "").strip(),
            ),
            fallback_agent_name=fallback_agent_name,
        )
        dispatch_result = await self.dispatch(
            envelope=envelope,
            task_pool=task_pool,
            task=task,
            runtime_pool=runtime_pool,
            runtime_task=runtime_task,
            fallback_agent=fallback_agent,
            defer_persist=defer_persist,
        )
        return {
            "result": dispatch_result.result,
            "task_pool": dispatch_result.task_pool,
            "runtime_task_pool": dispatch_result.runtime_task_pool,
            "selected_agent": dispatch_result.agent_name,
            "candidate_agents": dispatch_result.candidate_agents,
            "execution_mode": dispatch_result.execution_mode,
            "fallback_used": dispatch_result.fallback_used,
            "fallback_agent": dispatch_result.fallback_agent,
            "fallback_provenance": dispatch_result.fallback_provenance,
            "autonomous_error": dispatch_result.autonomous_error,
            "route_reason": dispatch_result.route_reason,
            "candidate_source": dispatch_result.candidate_source,
            "context_snapshot_id": dispatch_result.context_snapshot_id,
            "context": dispatch_result.context,
            "output_validation": dispatch_result.output_validation,
            "handoff": dispatch_result.handoff,
            "context_delta": dispatch_result.context_delta,
        }

    def build_chapter_task_pool(
        self,
        *,
        chapter_num: int,
        chapter_title: str,
        chapter_outline_text: str,
        base_context: Dict[str, Any],
    ) -> TaskPool:
        """Build chapter-level autonomous task pool."""
        chapter_tag = f"chapter_{chapter_num}"
        task_pool = TaskPool()

        context_plan_task = task_pool.create_task(
            task_type="context_plan",
            title=f"第{chapter_num}章上下文规划",
            description="为章节写作选择需要加载的上下文",
            priority=95,
            inputs={
                "chapter_number": chapter_num,
                "chapter_title": chapter_title,
                "world": base_context.get("world"),
                "characters": base_context.get("characters"),
                "previous_summary": base_context.get("previous_summary", ""),
            },
            expected_outputs=["strategy"],
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        context_plan_task.metadata["output_key"] = "context_strategy"

        content_read_task = task_pool.create_task(
            task_type="content_read",
            title=f"第{chapter_num}章上下文读取",
            description="根据上下文策略加载章节写作所需材料",
            priority=94,
            depends_on=[context_plan_task.task_id],
            inputs={
                "strategy": {},
                "chapter_outline": chapter_outline_text,
            },
            expected_outputs=["loaded_context", "report", "permanent_memory"],
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        content_read_task.metadata["output_key"] = "content_reader"

        write_chapter_task = task_pool.create_task(
            task_type="write_chapter",
            title=f"第{chapter_num}章正文创作",
            description="根据章节大纲生成正文",
            priority=93,
            depends_on=[content_read_task.task_id],
            inputs={
                "chapter_outline": chapter_outline_text,
                "chapter_title": chapter_title,
                "chapter_number": chapter_num,
            },
            expected_outputs=["content", "word_count"],
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        write_chapter_task.metadata["output_key"] = "write_chapter"

        evaluate_task = task_pool.create_task(
            task_type="evaluate_chapter",
            title=f"第{chapter_num}章质量评估",
            description="评估章节是否通过质检",
            priority=92,
            depends_on=[write_chapter_task.task_id],
            inputs={
                "content": "",
                "chapter_outline": chapter_outline_text,
            },
            expected_outputs=["evaluation"],
            review_required=True,
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        evaluate_task.metadata["output_key"] = "evaluate_chapter"

        polish_task = task_pool.create_task(
            task_type="polish_chapter",
            title=f"第{chapter_num}章润色修订",
            description="根据评估建议对章节进行修订",
            priority=91,
            depends_on=[evaluate_task.task_id],
            status=TaskStatus.BLOCKED,
            inputs={
                "content": "",
                "feedback": "",
            },
            expected_outputs=["content"],
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        polish_task.metadata["output_key"] = "polish_chapter"

        expand_task = task_pool.create_task(
            task_type="expand_content",
            title=f"第{chapter_num}章内容补足",
            description="在不破坏结构的前提下补足字数与细节",
            priority=80,
            depends_on=[evaluate_task.task_id],
            inputs={
                "content": "",
                "target_words": WRITING_CONFIG.CHAPTER_DEFAULT_WORDS,
                "chapter_title": chapter_title,
                "chapter_outline": chapter_outline_text,
            },
            expected_outputs=["content", "word_count", "expanded"],
            metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
        )
        expand_task.metadata["output_key"] = "expand_content"

        if chapter_num % 10 == 0:
            start_chapter = max(1, chapter_num - 9)
            summary_task = task_pool.create_task(
                task_type="summary_orchestrate",
                title=f"第{start_chapter}-{chapter_num}章阶段总结",
                description="对十章阶段内容进行总结归档",
                priority=70,
                depends_on=[expand_task.task_id],
                inputs={
                    "start_chapter": start_chapter,
                    "end_chapter": chapter_num,
                    "chapters": [],
                },
                expected_outputs=["summary", "summary_payload"],
                metadata={"chapter_number": chapter_num, "chapter_task_group": chapter_tag},
            )
            summary_task.metadata["output_key"] = "summary_orchestrate"

        return task_pool

    async def execute_chapter_task_market_loop(
        self,
        *,
        chapter_num: int,
        task_pool: TaskPool,
        base_context: Dict[str, Any],
        fallback_agents: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute chapter-level task market loop.

        13.5 修复：使用 defer_persist=True 延迟持久化，循环结束后统一刷盘，
        将每章 30+ 次磁盘 IO 降低到 1 次批量写入。
        """
        self._ensure_run_state()
        working_context = dict(base_context or {})
        execution_results: Dict[str, Dict[str, Any]] = {}
        loop_guard = 0
        self._record_run_checkpoint(
            node="chapter_market_start",
            status="running",
            task_type="chapter_market",
            context=working_context,
            task_pool=task_pool.to_dict(),
            metadata={"chapter_number": chapter_num},
        )

        while True:
            ready_tasks = task_pool.get_ready_tasks()
            if not ready_tasks:
                break

            current_task = ready_tasks[0]
            current_inputs = dict(current_task.inputs or {})
            task_context = dict(working_context)

            if current_task.task_type == "content_read":
                strategy_result = execution_results.get("context_strategy", {}).get("result", {})
                if isinstance(strategy_result, dict):
                    current_inputs["strategy"] = strategy_result.get("strategy", current_inputs.get("strategy", {}))
                task_context["chapter_outline"] = current_inputs.get("chapter_outline", working_context.get("chapter_outline", ""))

            elif current_task.task_type == "write_chapter":
                task_context["chapter_outline"] = current_inputs.get("chapter_outline", working_context.get("chapter_outline", ""))

            elif current_task.task_type == "evaluate_chapter":
                chapter_result = execution_results.get("write_chapter", {}).get("result", {})
                if isinstance(chapter_result, dict):
                    current_inputs["content"] = chapter_result.get("content", current_inputs.get("content", ""))

            elif current_task.task_type == "polish_chapter":
                evaluation_payload = execution_results.get("evaluate_chapter", {}).get("result", {})
                evaluation = evaluation_payload.get("evaluation", {}) if isinstance(evaluation_payload, dict) else {}
                if evaluation.get("passed", True):
                    task_pool.abort_task(current_task.task_id, "evaluation_passed_skip_polish")
                    loop_guard += 1
                    if loop_guard > 10:
                        raise RuntimeError(f"章节任务市场循环异常，chapter={chapter_num}")
                    continue
                chapter_result = execution_results.get("write_chapter", {}).get("result", {})
                if isinstance(chapter_result, dict):
                    current_inputs["content"] = chapter_result.get("content", current_inputs.get("content", ""))
                current_inputs["feedback"] = json.dumps(
                    evaluation.get("suggestions", []),
                    ensure_ascii=False,
                )

            elif current_task.task_type == "expand_content":
                polish_result = execution_results.get("polish_chapter", {}).get("result", {})
                chapter_result = execution_results.get("write_chapter", {}).get("result", {})
                if isinstance(polish_result, dict) and polish_result.get("content"):
                    current_inputs["content"] = polish_result.get("content", current_inputs.get("content", ""))
                elif isinstance(chapter_result, dict):
                    current_inputs["content"] = chapter_result.get("content", current_inputs.get("content", ""))

            elif current_task.task_type == "summary_orchestrate":
                end_chapter = int(current_inputs.get("end_chapter") or chapter_num)
                start_chapter = int(current_inputs.get("start_chapter") or max(1, end_chapter - 9))
                prior_chapters = list(working_context.get("previous_chapters") or [])
                expand_result = execution_results.get("expand_content", {}).get("result", {})
                chapter_result = execution_results.get("write_chapter", {}).get("result", {})
                final_content = ""
                if isinstance(expand_result, dict) and expand_result.get("content"):
                    final_content = str(expand_result.get("content") or "")
                elif isinstance(chapter_result, dict):
                    final_content = str(chapter_result.get("content") or "")
                current_chapter_payload = {
                    "number": chapter_num,
                    "chapter_number": chapter_num,
                    "title": working_context.get("chapter_title") or current_inputs.get("chapter_title") or f"第{chapter_num}章",
                    "content": final_content,
                }
                current_inputs["chapters"] = prior_chapters[-9:] + [current_chapter_payload]
                task_context["chapters"] = list(current_inputs.get("chapters") or [])

            # 13.5 修复：使用 defer_persist=True 延迟持久化
            run_result = await self.run_autonomous_task(
                task_type=current_task.task_type,
                input_data=current_inputs,
                context=task_context,
                fallback_agent=fallback_agents.get(current_task.task_type),
                stage="chapter_market",
                title=current_task.title,
                description=current_task.description,
                expected_outputs=current_task.expected_outputs,
                review_required=bool(current_task.review_required),
                defer_persist=True,
            )

            output_key = str(current_task.metadata.get("output_key") or current_task.task_type).strip() or current_task.task_type
            execution_results[output_key] = run_result

            selected_agent = str(run_result.get("selected_agent") or "").strip()
            if selected_agent:
                task_pool.claim_task(current_task.task_id, selected_agent)
                task_pool.start_task(current_task.task_id, selected_agent)
            else:
                task_pool.start_task(current_task.task_id)

            result_payload = run_result.get("result", {})
            merged_context = run_result.get("context", {})
            if current_task.review_required:
                task_pool.mark_review_required(current_task.task_id)
            task_pool.complete_task(current_task.task_id)
            current_task.metadata.update({
                "route_reason": run_result.get("route_reason", ""),
                "candidate_source": run_result.get("candidate_source", ""),
                "context_snapshot_id": run_result.get("context_snapshot_id", ""),
                "fallback_provenance": run_result.get("fallback_provenance", {}),
            })
            current_task.touch()
            # 13.3 修复：使用显式 merge 而非整体替换，避免丢失之前任务积累的上下文
            if isinstance(merged_context, dict) and merged_context:
                working_context.update(merged_context)

            if current_task.task_type == "context_plan" and isinstance(result_payload, dict):
                strategy = result_payload.get("strategy", {})
                if isinstance(strategy, dict):
                    working_context["context_strategy"] = strategy

            if current_task.task_type == "polish_chapter" and isinstance(result_payload, dict):
                polished_content = str(result_payload.get("content") or "").strip()
                if polished_content:
                    working_context["latest_polished_content"] = polished_content

            loop_guard += 1
            if loop_guard > 10:
                raise RuntimeError(f"章节任务市场循环异常，chapter={chapter_num}")

        # 13.5 修复：循环结束后统一持久化任务池状态和缓存的事件/快照
        self.save_runtime_task_pool(task_pool)
        self.flush_deferred_persistence()
        self._record_run_checkpoint(
            node="chapter_market_end",
            status="completed",
            task_type="chapter_market",
            context=working_context,
            task_pool=task_pool.to_dict(),
            metadata={
                "chapter_number": chapter_num,
                "result_keys": sorted(execution_results.keys()),
            },
        )

        return {
            "task_pool": task_pool.to_dict(),
            "results": execution_results,
            "context": working_context,
        }
