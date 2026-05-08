"""长篇协作模式统一执行入口。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
import json
import re
import logging
import uuid

from ..constants import WRITING_CONFIG
from ..utils.atomic_write import atomic_write_json
from .execution_context import CollabExecutionContext, TaskExecutionEnvelope
from .routing_policy import RoutingPolicy
from .runtime_state import RuntimeStateStore
from .task_pool import TaskPool, TaskStatus
from .contracts import TaskDefinition

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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        runtime_state_store: Optional[RuntimeStateStore] = None,
    ) -> None:
        self.routing_policy = routing_policy
        self.capability_registry_provider = capability_registry_provider
        self.project_manager_provider = project_manager_provider
        self.project_dir_provider = project_dir_provider
        self.save_runtime_task_pool = save_runtime_task_pool
        self.notify_progress = notify_progress
        self.supervised_mode_provider = supervised_mode_provider
        self.fallback_to_orchestrated_provider = fallback_to_orchestrated_provider
        self.runtime_state_store = runtime_state_store
        # 13.5 批量写入：延迟持久化缓存
        self._deferred_events: List[Dict[str, Any]] = []
        self._deferred_snapshots: List[Dict[str, Any]] = []

    def _get_capability_registry(self) -> Any:
        return self.capability_registry_provider()

    def _get_project_manager(self) -> Any:
        return self.project_manager_provider()

    def _get_project_dir(self) -> Path:
        return Path(self.project_dir_provider())

    def _append_execution_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        project_manager = self._get_project_manager()
        trace = project_manager.load_project_state("collab_execution_trace", default={})
        if not isinstance(trace, dict):
            trace = {}
        trace.setdefault("events", [])
        trace.setdefault("status", "initialized")
        trace.setdefault("supervised_mode", bool(self.supervised_mode_provider()))
        trace.setdefault("fallback_to_orchestrated", bool(self.fallback_to_orchestrated_provider()))

        normalized_events: List[Dict[str, Any]] = []
        for item in trace.get("events", []):
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            normalized_timestamp = str(
                normalized_item.get("timestamp")
                or normalized_item.get("created_at")
                or ""
            ).strip()
            if not normalized_timestamp:
                normalized_timestamp = datetime.now().isoformat()
            normalized_item["timestamp"] = normalized_timestamp
            normalized_item.pop("created_at", None)
            normalized_events.append(normalized_item)
        trace["events"] = normalized_events

        event_timestamp = datetime.now().isoformat()
        event_payload = {
            "type": str(event_type or "").strip() or "unknown",
            "timestamp": event_timestamp,
        }
        if isinstance(payload, dict) and payload:
            event_payload.update(payload)
        event_payload["timestamp"] = str(event_payload.get("timestamp") or event_timestamp).strip() or event_timestamp
        event_payload.pop("created_at", None)

        trace["events"].append(event_payload)
        if len(trace["events"]) > 500:
            trace["events"] = trace["events"][-500:]
        trace["updated_at"] = event_payload["timestamp"]
        project_manager.save_project_state("collab_execution_trace", trace)
        return trace

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
            "required_context_keys": list(envelope.required_context_keys or []),
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
        if not self._deferred_events and not self._deferred_snapshots:
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

        # 批量写入事件
        if self._deferred_events:
            trace = project_manager.load_project_state("collab_execution_trace", default={})
            if not isinstance(trace, dict):
                trace = {}
            trace.setdefault("events", [])
            trace.setdefault("status", "initialized")
            trace.setdefault("supervised_mode", bool(self.supervised_mode_provider()))
            trace.setdefault("fallback_to_orchestrated", bool(self.fallback_to_orchestrated_provider()))

            normalized_events: List[Dict[str, Any]] = []
            for item in trace.get("events", []):
                if not isinstance(item, dict):
                    continue
                normalized_item = dict(item)
                normalized_timestamp = str(
                    normalized_item.get("timestamp")
                    or normalized_item.get("created_at")
                    or ""
                ).strip()
                if not normalized_timestamp:
                    normalized_timestamp = datetime.now().isoformat()
                normalized_item["timestamp"] = normalized_timestamp
                normalized_item.pop("created_at", None)
                normalized_events.append(normalized_item)
            trace["events"] = normalized_events

            trace["events"].extend(self._deferred_events)
            if len(trace["events"]) > 500:
                trace["events"] = trace["events"][-500:]
            trace["updated_at"] = datetime.now().isoformat()
            project_manager.save_project_state("collab_execution_trace", trace)
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
        fallback_agent_name = str(
            envelope.fallback_agent_name or getattr(fallback_agent, "name", "") or ""
        ).strip()

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
                selected_agent = self._resolve_agent_instance(selected_agent_name, fallback_agent=fallback_agent)
                if selected_agent is None:
                    raise RuntimeError(f"任务 {envelope.task_type} 缺少可执行Agent: {selected_agent_name}")
        except Exception as exc:
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
            )
            self.save_runtime_task_pool(runtime_pool)
            self._append_execution_event(
                "task_rejected",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "title": envelope.title,
                    "reason": route_reason,
                    "context_snapshot_id": context_snapshot_id,
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
        )
        task_pool.claim_task(task.task_id, claimed_by)
        task_pool.start_task(task.task_id, claimed_by)
        runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.CLAIMED, assigned_agent=claimed_by)
        runtime_pool.update_task_status(runtime_task.task_id, TaskStatus.RUNNING, assigned_agent=claimed_by)
        # 问题17修复：runtime_pool 状态必须立即持久化，不能延迟
        self.save_runtime_task_pool(runtime_pool)
        # 13.5 延迟模式：缓存事件而非立即写盘
        _task_started_event = {
            "task_id": runtime_task.task_id,
            "task_type": envelope.task_type,
            "assigned_agent": claimed_by,
            "fallback_candidate": fallback_agent_name,
            "route_reason": route_reason,
            "candidate_source": candidate_source,
            "context_snapshot_id": context_snapshot_id,
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
            result = await selected_agent.execute(envelope.input_data, context=current_context.to_agent_context())
            if not isinstance(result, dict) or not result.get("success", True):
                raise RuntimeError(str((result or {}).get("error") or "task_failed"))

            current_context.apply_task_result(envelope.task_type, result)
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
                    "model": selected_model,
                    "current_model": selected_model,
                    "active_model": selected_model,
                    "model_used": selected_model,
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
            if not isinstance(result, dict) or not result.get("success", True):
                fallback_error = str((result or {}).get("error") or "fallback_task_failed")
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
                        "model": retry_model,
                        "current_model": retry_model,
                        "active_model": retry_model,
                        "model_used": retry_model,
                    },
                )
                raise RuntimeError(fallback_error)

            current_context = envelope.context.clone()
            current_context.apply_task_result(envelope.task_type, result)
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
            )
            self.save_runtime_task_pool(runtime_pool)
            self._append_execution_event(
                "task_completed",
                {
                    "task_id": runtime_task.task_id,
                    "task_type": envelope.task_type,
                    "assigned_agent": retry_claimed_by,
                    "fallback_used": True,
                    "review_required": bool(task.review_required),
                    "context_snapshot_id": context_snapshot_id,
                    "model": retry_model,
                    "current_model": retry_model,
                    "active_model": retry_model,
                    "model_used": retry_model,
                },
            )
            claimed_by = retry_claimed_by

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
        working_context = dict(base_context or {})
        execution_results: Dict[str, Dict[str, Any]] = {}
        loop_guard = 0

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

        return {
            "task_pool": task_pool.to_dict(),
            "results": execution_results,
            "context": working_context,
        }
