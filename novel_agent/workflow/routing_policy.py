"""长篇协作模式的显式路由规则。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .execution_context import CollabExecutionContext, ContextValidationError


class RoutingPolicyError(ValueError):
    """路由规则解析失败。"""


@dataclass
class RouteRule:
    task_type: str
    stage: str = ""
    preferred_agent_name: str = ""
    required_context_keys: List[str] = field(default_factory=list)
    discover_candidates: bool = True
    allow_fixed_agent: bool = True


@dataclass
class RouteDecision:
    agent_name: str
    route_reason: str
    candidate_source: str
    candidate_names: List[str] = field(default_factory=list)
    required_context_keys: List[str] = field(default_factory=list)
    fallback_agent_names: List[str] = field(default_factory=list)


class RoutingPolicy:
    """显式任务路由规则层。"""

    def __init__(self, rules: Optional[List[RouteRule]] = None) -> None:
        self.rules = list(rules or [])

    @classmethod
    def default(cls) -> "RoutingPolicy":
        return cls(
            rules=[
                RouteRule("build_world", stage="creation_mainline", preferred_agent_name="Worldbuilder", required_context_keys=["project_dir"]),
                RouteRule("build_characters", stage="creation_mainline", preferred_agent_name="CharacterBuilder", required_context_keys=["project_dir", "world"]),
                RouteRule("build_outline", stage="creation_mainline", preferred_agent_name="Outliner", required_context_keys=["project_dir", "world"]),
                RouteRule("build_world", stage="project_ready", preferred_agent_name="Worldbuilder", required_context_keys=["project_dir"]),
                RouteRule("build_outline", stage="project_ready", preferred_agent_name="Outliner", required_context_keys=["project_dir"]),
                RouteRule("summary_orchestrate", stage="project_ready", preferred_agent_name="SummaryOrchestrator", required_context_keys=["project_dir", "chapters"]),
                RouteRule("context_plan", stage="chapter_market", preferred_agent_name="ContextStrategy", required_context_keys=["project_dir", "chapter_outline"]),
                RouteRule("content_read", stage="chapter_market", preferred_agent_name="ContentReader", required_context_keys=["project_dir", "chapter_outline"]),
                RouteRule("write_chapter", stage="chapter_market", preferred_agent_name="ChapterWriter", required_context_keys=["project_dir", "world", "characters", "chapter_outline"]),
                RouteRule("evaluate_chapter", stage="chapter_market", preferred_agent_name="Evaluator", required_context_keys=["project_dir", "world", "characters", "chapter_outline"]),
                RouteRule("polish_chapter", stage="chapter_market", preferred_agent_name="Polisher", required_context_keys=["project_dir", "chapter_outline"]),
                RouteRule("expand_content", stage="chapter_market", preferred_agent_name="ContentExpansion", required_context_keys=["project_dir", "chapter_outline"]),
                RouteRule("summary_orchestrate", stage="chapter_market", preferred_agent_name="SummaryOrchestrator", required_context_keys=["project_dir", "chapters"]),
                RouteRule("build_world", preferred_agent_name="Worldbuilder"),
                RouteRule("build_characters", preferred_agent_name="CharacterBuilder"),
                RouteRule("build_outline", preferred_agent_name="Outliner"),
                RouteRule("summary_orchestrate", preferred_agent_name="SummaryOrchestrator"),
                RouteRule("context_plan", preferred_agent_name="ContextStrategy"),
                RouteRule("content_read", preferred_agent_name="ContentReader"),
                RouteRule("write_chapter", preferred_agent_name="ChapterWriter"),
                RouteRule("evaluate_chapter", preferred_agent_name="Evaluator"),
                RouteRule("polish_chapter", preferred_agent_name="Polisher"),
                RouteRule("expand_content", preferred_agent_name="ContentExpansion"),
            ]
        )

    def _match_rule(self, task_type: str, stage: str = "") -> Optional[RouteRule]:
        normalized_task_type = str(task_type or "").strip()
        normalized_stage = str(stage or "").strip()

        for rule in self.rules:
            if rule.task_type == normalized_task_type and rule.stage == normalized_stage:
                return rule
        for rule in self.rules:
            if rule.task_type == normalized_task_type and not rule.stage:
                return rule
        return None

    def resolve(
        self,
        *,
        task_type: str,
        stage: str,
        context: CollabExecutionContext,
        capability_registry: Any = None,
        input_data: Optional[Dict[str, Any]] = None,
        fallback_agent_name: str = "",
    ) -> RouteDecision:
        rule = self._match_rule(task_type, stage)
        if rule is None:
            raise RoutingPolicyError(f"No route rule found for task_type={task_type}, stage={stage}")

        missing_keys = context.missing_keys(rule.required_context_keys)
        if missing_keys:
            raise ContextValidationError(f"Missing required context keys: {', '.join(missing_keys)}")

        # 13.4 修复：优先使用规则表中的 preferred_agent_name，capability_registry 仅作校验
        candidates: List[Dict[str, Any]] = []
        if rule.discover_candidates and capability_registry is not None:
            candidates = capability_registry.find_candidates(
                {
                    "task_type": str(task_type or "").strip(),
                    "inputs": dict(input_data or {}),
                }
            )

        candidate_names = [
            str(item.get("agent_name") or "").strip()
            for item in candidates
            if str(item.get("agent_name") or "").strip()
        ]

        # 优先使用能力注册表给出的候选，规则表只用于在候选中挑选首选项。
        # 如果没有候选，不把 preferred_agent_name 当作“隐式可执行者”，避免绕过注册表。
        preferred = str(rule.preferred_agent_name or "").strip()
        if candidate_names:
            selected_agent_name = preferred if preferred in candidate_names else candidate_names[0]
            return RouteDecision(
                agent_name=selected_agent_name,
                route_reason=(
                    f"matched explicit route {task_type}"
                    + (f"@{stage}" if stage else "")
                    + f" via capability candidate {selected_agent_name}"
                ),
                candidate_source="capability_registry",
                candidate_names=candidate_names,
                required_context_keys=list(rule.required_context_keys or []),
                fallback_agent_names=[str(fallback_agent_name or "").strip()] if str(fallback_agent_name or "").strip() else [],
            )

        # 最后尝试 fallback_agent_name
        fixed_agent_name = str(fallback_agent_name or "").strip()
        if rule.allow_fixed_agent and fixed_agent_name:
            return RouteDecision(
                agent_name=fixed_agent_name,
                route_reason=(
                    f"matched explicit route {task_type}"
                    + (f"@{stage}" if stage else "")
                    + f" via fixed route agent {fixed_agent_name}"
                ),
                candidate_source="fixed_route_rule",
                candidate_names=candidate_names,
                required_context_keys=list(rule.required_context_keys or []),
                fallback_agent_names=[fixed_agent_name],
            )

        raise RoutingPolicyError(f"No dispatchable agent found for task_type={task_type}, stage={stage}")
