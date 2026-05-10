"""长篇协作模式 scoped registry。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from ..route_targets import (
    ROUTE_TARGET_HELPER_SERVICE,
    ROUTE_TARGET_AGENT,
    RouteTargetDescriptor,
    descriptor_from_capability,
)


class CollabServiceRegistry:
    """管理长篇协作阶段使用的本地服务。"""

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}

    def register(self, name: str, service: Any) -> Any:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("service name is required")
        self._services[normalized_name] = service
        return service

    def register_many(self, services: Dict[str, Any]) -> Dict[str, Any]:
        registered: Dict[str, Any] = {}
        for name, service in dict(services or {}).items():
            registered[name] = self.register(name, service)
        return registered

    def get(self, name: str, default: Any = None) -> Any:
        return self._services.get(str(name or "").strip(), default)

    def list_agents(self) -> List[str]:
        return sorted(self._services.keys(), key=str.lower)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_count": len(self._services),
            "services": self.list_agents(),
        }


class CollabAgentRegistry:
    """Scoped 协作参与者注册表，可回退到全局能力注册表。"""

    def __init__(self, fallback_registry_provider: Optional[Callable[[], Any]] = None) -> None:
        self._agents: Dict[str, Any] = {}
        self._capabilities: Dict[str, Any] = {}
        self._fallback_registry_provider = fallback_registry_provider

    def _get_fallback_registry(self) -> Any:
        if self._fallback_registry_provider is None:
            return None
        return self._fallback_registry_provider()

    def register(self, agent: Any) -> Any:
        if agent is None:
            raise ValueError("agent is required")
        capability = agent.get_capabilities()
        agent_name = str(getattr(capability, "agent_name", "") or getattr(agent, "name", "")).strip()
        if not agent_name:
            raise ValueError("agent capability name is required")
        capability.agent_name = agent_name
        self._agents[agent_name] = agent
        self._capabilities[agent_name] = capability
        return capability

    def register_many(self, agents: List[Any]) -> List[Any]:
        results: List[Any] = []
        for agent in agents or []:
            if agent is None:
                continue
            results.append(self.register(agent))
        return results

    def unregister(self, agent_name: str) -> bool:
        normalized_name = str(agent_name or "").strip()
        existed = normalized_name in self._agents or normalized_name in self._capabilities
        self._agents.pop(normalized_name, None)
        self._capabilities.pop(normalized_name, None)
        return existed

    def clear(self) -> None:
        self._agents.clear()
        self._capabilities.clear()

    def get(self, agent_name: str, default: Any = None) -> Any:
        return self._agents.get(str(agent_name or "").strip(), default)

    def get_agent(self, agent_name: str) -> Any:
        normalized_name = str(agent_name or "").strip()
        local = self._agents.get(normalized_name)
        if local is not None:
            return local
        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "get_agent"):
            return fallback.get_agent(normalized_name)
        return None

    def get_capability(self, agent_name: str) -> Any:
        normalized_name = str(agent_name or "").strip()
        local = self._capabilities.get(normalized_name)
        if local is not None:
            return local
        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "get_capability"):
            return fallback.get_capability(normalized_name)
        return None

    def get_route_target(self, agent_name: str) -> Optional[RouteTargetDescriptor]:
        normalized_name = str(agent_name or "").strip()
        capability = self._capabilities.get(normalized_name)
        if capability is not None:
            metadata = dict(getattr(capability, "metadata", {}) or {})
            runtime = str(metadata.get("runtime") or "").strip()
            kind = (
                ROUTE_TARGET_HELPER_SERVICE
                if runtime == "service_backed"
                else metadata.get("route_target_kind") or ROUTE_TARGET_AGENT
            )
            return descriptor_from_capability(
                capability,
                kind=kind,
                execution_backend=str(metadata.get("execution_backend") or runtime or "collab_participant"),
                visibility=str(metadata.get("visibility") or "internal"),
                risk_level=str(metadata.get("risk_level") or "normal"),
            )
        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "get_route_target"):
            return fallback.get_route_target(normalized_name)
        return None

    def list_route_targets(self) -> List[RouteTargetDescriptor]:
        targets_by_id: Dict[str, RouteTargetDescriptor] = {}
        for agent_name in sorted(self._capabilities.keys(), key=str.lower):
            target = self.get_route_target(agent_name)
            if target is not None:
                targets_by_id[target.id] = target
        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "list_route_targets"):
            for target in fallback.list_route_targets() or []:
                if isinstance(target, RouteTargetDescriptor) and target.id not in targets_by_id:
                    targets_by_id[target.id] = target
        return [
            target
            for _, target in sorted(targets_by_id.items(), key=lambda item: item[0].lower())
        ]

    def list_agents(self) -> List[str]:
        names = set(self._agents.keys())
        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "list_agents"):
            names.update(fallback.list_agents() or [])
        return sorted(names, key=str.lower)

    def _build_candidate_payload(self, agent_name: str, capability: Any, estimate: Any) -> Dict[str, Any]:
        capability_payload = capability.to_dict() if hasattr(capability, "to_dict") else asdict(capability)
        return {
            "agent_name": agent_name,
            "capability": capability_payload,
            "estimate": dict(estimate or {}),
        }

    def find_candidates(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized_task = dict(task or {})
        candidates: Dict[str, Dict[str, Any]] = {}

        for agent_name, agent in self._agents.items():
            capability = self._capabilities.get(agent_name)
            if capability is None or not hasattr(agent, "accepts_task"):
                continue
            if not agent.accepts_task(normalized_task):
                continue
            estimate = agent.estimate_cost(normalized_task) if hasattr(agent, "estimate_cost") else {}
            candidates[agent_name] = self._build_candidate_payload(agent_name, capability, estimate)

        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "find_candidates"):
            for item in fallback.find_candidates(normalized_task) or []:
                if not isinstance(item, dict):
                    continue
                agent_name = str(item.get("agent_name") or "").strip()
                if not agent_name or agent_name in candidates:
                    continue
                candidates[agent_name] = {
                    "agent_name": agent_name,
                    "capability": dict(item.get("capability") or {}),
                    "estimate": dict(item.get("estimate") or {}),
                }

        ordered = list(candidates.values())
        ordered.sort(
            key=lambda item: (
                -int((item.get("capability") or {}).get("priority", 0) or 0),
                str(item.get("agent_name") or "").lower(),
            )
        )
        return ordered

    def coverage_by_task_type(self) -> Dict[str, List[str]]:
        coverage: Dict[str, List[str]] = {}

        for agent_name, capability in self._capabilities.items():
            for task_type in getattr(capability, "accept_task_types", []) or []:
                normalized_task_type = str(task_type or "").strip()
                if not normalized_task_type:
                    continue
                coverage.setdefault(normalized_task_type, [])
                if agent_name not in coverage[normalized_task_type]:
                    coverage[normalized_task_type].append(agent_name)

        fallback = self._get_fallback_registry()
        if fallback is not None and hasattr(fallback, "coverage_by_task_type"):
            for task_type, agent_names in dict(fallback.coverage_by_task_type() or {}).items():
                normalized_task_type = str(task_type or "").strip()
                if not normalized_task_type:
                    continue
                coverage.setdefault(normalized_task_type, [])
                for agent_name in agent_names or []:
                    normalized_agent_name = str(agent_name or "").strip()
                    if normalized_agent_name and normalized_agent_name not in coverage[normalized_task_type]:
                        coverage[normalized_task_type].append(normalized_agent_name)

        for task_type in coverage:
            coverage[task_type].sort(key=str.lower)
        return coverage

    def to_dict(self) -> Dict[str, Any]:
        local_capabilities = []
        for agent_name, capability in sorted(self._capabilities.items(), key=lambda item: item[0].lower()):
            capability_payload = capability.to_dict() if hasattr(capability, "to_dict") else asdict(capability)
            local_capabilities.append(capability_payload)

        return {
            "agent_count": len(self.list_agents()),
            "agents": self.list_agents(),
            "scoped_agents": sorted(self._agents.keys(), key=str.lower),
            "scoped_capabilities": local_capabilities,
            "route_targets": [target.to_dict() for target in self.list_route_targets()],
            "coverage_by_task_type": self.coverage_by_task_type(),
        }
