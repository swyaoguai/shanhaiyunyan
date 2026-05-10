"""Agent 能力注册表。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from .base_agent import AgentCapability, BaseAgent
from ..route_targets import (
    ROUTE_TARGET_AGENT,
    RouteTargetDescriptor,
    descriptor_from_agent,
)


class AgentCapabilityRegistry:
    """管理 Agent 能力声明与任务候选查询。"""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}
        self._capabilities: Dict[str, AgentCapability] = {}

    def register(self, agent: BaseAgent) -> AgentCapability:
        """
        注册单个 Agent，并缓存其能力声明。
        """
        capability = agent.get_capabilities()
        agent_name = str(capability.agent_name or agent.name).strip() or agent.name
        capability.agent_name = agent_name
        self._agents[agent_name] = agent
        self._capabilities[agent_name] = capability
        return capability

    def register_many(self, agents: List[BaseAgent]) -> List[AgentCapability]:
        """
        批量注册 Agent。
        """
        results: List[AgentCapability] = []
        for agent in agents or []:
            if not isinstance(agent, BaseAgent):
                continue
            results.append(self.register(agent))
        return results

    def unregister(self, agent_name: str) -> bool:
        """
        取消注册指定 Agent。
        """
        normalized_name = str(agent_name or "").strip()
        existed = normalized_name in self._capabilities or normalized_name in self._agents
        self._capabilities.pop(normalized_name, None)
        self._agents.pop(normalized_name, None)
        return existed

    def clear(self) -> None:
        """清空注册表。"""
        self._agents.clear()
        self._capabilities.clear()

    def get_capability(self, agent_name: str) -> Optional[AgentCapability]:
        """获取指定 Agent 的能力声明。"""
        return self._capabilities.get(str(agent_name or "").strip())

    def get_agent(self, agent_name: str) -> Optional[BaseAgent]:
        """获取指定 Agent 实例。"""
        return self._agents.get(str(agent_name or "").strip())

    def get_route_target(self, agent_name: str) -> Optional[RouteTargetDescriptor]:
        """获取统一路由目标描述。"""
        agent = self.get_agent(agent_name)
        if agent is None:
            return None
        return descriptor_from_agent(agent, kind=ROUTE_TARGET_AGENT)

    def list_route_targets(self) -> List[RouteTargetDescriptor]:
        """列出统一路由目标描述。"""
        targets: List[RouteTargetDescriptor] = []
        for agent_name in self.list_agents():
            target = self.get_route_target(agent_name)
            if target is not None:
                targets.append(target)
        return targets

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """以字典形式列出全部能力声明。"""
        return [
            capability.to_dict()
            for _, capability in sorted(self._capabilities.items(), key=lambda item: item[0].lower())
        ]

    def list_agents(self) -> List[str]:
        """列出已注册 Agent 名称。"""
        return sorted(self._agents.keys(), key=str.lower)

    def find_candidates(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        查找能处理某任务的候选 Agent。
        
        返回结果已按：
        1. 是否接受任务
        2. priority 降序
        3. agent_name 升序
        排序。
        """
        task = dict(task or {})
        candidates: List[Dict[str, Any]] = []

        for agent_name, agent in self._agents.items():
            capability = self._capabilities.get(agent_name)
            if capability is None:
                continue
            # 13.7 修复：跳过没有 accepts_task() 的 Service-backed 参与者
            if not hasattr(agent, "accepts_task") or not callable(getattr(agent, "accepts_task", None)):
                continue
            if not agent.accepts_task(task):
                continue

            # 13.7 修复：跳过没有 estimate_cost() 的 Service-backed 参与者
            if not hasattr(agent, "estimate_cost") or not callable(getattr(agent, "estimate_cost", None)):
                continue
            estimate = agent.estimate_cost(task)
            candidates.append({
                "agent_name": agent_name,
                "capability": capability.to_dict(),
                "estimate": dict(estimate or {}),
            })

        candidates.sort(
            key=lambda item: (
                -int((item.get("capability") or {}).get("priority", 0) or 0),
                str(item.get("agent_name") or "").lower(),
            )
        )
        return candidates

    def find_candidate_names(self, task: Dict[str, Any]) -> List[str]:
        """仅返回候选 Agent 名称列表。"""
        return [item["agent_name"] for item in self.find_candidates(task)]

    def coverage_by_task_type(self) -> Dict[str, List[str]]:
        """
        统计每种任务类型由哪些 Agent 覆盖。
        """
        coverage: Dict[str, List[str]] = {}
        for agent_name, capability in self._capabilities.items():
            for task_type in capability.accept_task_types or []:
                normalized_task_type = str(task_type or "").strip()
                if not normalized_task_type:
                    continue
                coverage.setdefault(normalized_task_type, [])
                if agent_name not in coverage[normalized_task_type]:
                    coverage[normalized_task_type].append(agent_name)

        for task_type in coverage:
            coverage[task_type].sort(key=str.lower)
        return coverage

    def to_dict(self) -> Dict[str, Any]:
        """导出注册表快照。"""
        return {
            "agent_count": len(self._agents),
            "agents": self.list_agents(),
            "capabilities": self.list_capabilities(),
            "route_targets": [target.to_dict() for target in self.list_route_targets()],
            "coverage_by_task_type": self.coverage_by_task_type(),
        }


_capability_registry: Optional[AgentCapabilityRegistry] = None


def get_capability_registry() -> AgentCapabilityRegistry:
    """获取全局能力注册表。"""
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = AgentCapabilityRegistry()
    return _capability_registry


def reset_capability_registry() -> None:
    """重置全局能力注册表。"""
    global _capability_registry
    _capability_registry = None
