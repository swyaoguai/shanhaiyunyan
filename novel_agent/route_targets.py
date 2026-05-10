"""Unified route target descriptors for agents, helpers, tools, and UI targets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


ROUTE_TARGET_AGENT = "agent"
ROUTE_TARGET_HELPER_SERVICE = "helper_service"
ROUTE_TARGET_TOOL = "tool"
ROUTE_TARGET_UI_VIRTUAL = "ui_virtual"
ROUTE_TARGET_EPHEMERAL_AGENT = "ephemeral_agent"


@dataclass
class RouteTargetDescriptor:
    """Canonical description of anything the router can point at."""

    id: str
    kind: str
    display_name: str
    purpose: str = ""
    accept_task_types: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    produced_outputs: List[str] = field(default_factory=list)
    risk_level: str = "normal"
    visibility: str = "internal"
    execution_backend: str = ""
    priority: int = 50
    max_concurrency: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RouteTargetRegistry:
    """Small registry that exposes a shared view across route target kinds."""

    def __init__(self, targets: Optional[Iterable[RouteTargetDescriptor]] = None) -> None:
        self._targets: Dict[str, RouteTargetDescriptor] = {}
        self.register_many(list(targets or []))

    def register(self, target: RouteTargetDescriptor) -> RouteTargetDescriptor:
        normalized_id = str(getattr(target, "id", "") or "").strip()
        if not normalized_id:
            raise ValueError("route target id is required")
        target.id = normalized_id
        self._targets[normalized_id] = target
        return target

    def register_many(self, targets: Iterable[RouteTargetDescriptor]) -> List[RouteTargetDescriptor]:
        registered: List[RouteTargetDescriptor] = []
        for target in targets or []:
            if isinstance(target, RouteTargetDescriptor):
                registered.append(self.register(target))
        return registered

    def unregister(self, target_id: str) -> bool:
        normalized_id = str(target_id or "").strip()
        existed = normalized_id in self._targets
        self._targets.pop(normalized_id, None)
        return existed

    def get(self, target_id: str) -> Optional[RouteTargetDescriptor]:
        return self._targets.get(str(target_id or "").strip())

    def list_targets(self) -> List[RouteTargetDescriptor]:
        return [
            target
            for _, target in sorted(self._targets.items(), key=lambda item: item[0].lower())
        ]

    def find_candidates(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        task_type = str((task or {}).get("task_type") or "").strip()
        if not task_type:
            return []
        candidates: List[Dict[str, Any]] = []
        for target in self._targets.values():
            accepted = {str(item or "").strip() for item in target.accept_task_types or []}
            if task_type not in accepted:
                continue
            candidates.append({
                "agent_name": target.id,
                "target_id": target.id,
                "route_target": target.to_dict(),
                "capability": {
                    "agent_name": target.id,
                    "capabilities": list(target.accept_task_types or []),
                    "accept_task_types": list(target.accept_task_types or []),
                    "required_inputs": list(target.required_inputs or []),
                    "produced_outputs": list(target.produced_outputs or []),
                    "priority": int(target.priority or 0),
                    "max_concurrency": int(target.max_concurrency or 1),
                    "metadata": dict(target.metadata or {}),
                },
                "estimate": {"priority": int(target.priority or 0), "confidence": 0.3},
            })
        candidates.sort(
            key=lambda item: (
                -int((item.get("capability") or {}).get("priority", 0) or 0),
                str(item.get("target_id") or item.get("agent_name") or "").lower(),
            )
        )
        return candidates

    def coverage_by_task_type(self) -> Dict[str, List[str]]:
        coverage: Dict[str, List[str]] = {}
        for target in self._targets.values():
            for task_type in target.accept_task_types or []:
                normalized = str(task_type or "").strip()
                if not normalized:
                    continue
                coverage.setdefault(normalized, [])
                if target.id not in coverage[normalized]:
                    coverage[normalized].append(target.id)
        for task_type in coverage:
            coverage[task_type].sort(key=str.lower)
        return coverage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_count": len(self._targets),
            "targets": [target.to_dict() for target in self.list_targets()],
            "coverage_by_task_type": self.coverage_by_task_type(),
        }


def _metadata_display_name(metadata: Dict[str, Any], fallback: str) -> str:
    for key in ("display_name", "label", "name"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return fallback


def descriptor_from_capability(
    capability: Any,
    *,
    kind: str,
    execution_backend: str,
    visibility: str = "internal",
    risk_level: str = "normal",
) -> RouteTargetDescriptor:
    metadata = dict(getattr(capability, "metadata", {}) or {})
    target_id = str(getattr(capability, "agent_name", "") or "").strip()
    if not target_id:
        raise ValueError("capability agent_name is required")
    return RouteTargetDescriptor(
        id=target_id,
        kind=metadata.get("route_target_kind") or kind,
        display_name=_metadata_display_name(metadata, target_id),
        purpose=str(metadata.get("purpose") or metadata.get("description") or "").strip(),
        accept_task_types=[
            str(item).strip()
            for item in getattr(capability, "accept_task_types", []) or []
            if str(item).strip()
        ],
        required_inputs=[
            str(item).strip()
            for item in getattr(capability, "required_inputs", []) or []
            if str(item).strip()
        ],
        produced_outputs=[
            str(item).strip()
            for item in getattr(capability, "produced_outputs", []) or []
            if str(item).strip()
        ],
        risk_level=str(metadata.get("risk_level") or risk_level).strip() or risk_level,
        visibility=str(metadata.get("visibility") or visibility).strip() or visibility,
        execution_backend=str(metadata.get("execution_backend") or execution_backend).strip() or execution_backend,
        priority=int(getattr(capability, "priority", 50) or 50),
        max_concurrency=int(getattr(capability, "max_concurrency", 1) or 1),
        metadata=metadata,
    )


def descriptor_from_agent(
    agent: Any,
    *,
    kind: str = ROUTE_TARGET_AGENT,
    visibility: str = "user_visible",
    risk_level: str = "writes_project_content",
) -> RouteTargetDescriptor:
    capability = agent.get_capabilities()
    return descriptor_from_capability(
        capability,
        kind=kind,
        execution_backend=agent.__class__.__name__,
        visibility=visibility,
        risk_level=risk_level,
    )


DEFAULT_INTENT_ROUTE_TARGETS: Dict[str, RouteTargetDescriptor] = {
    "create_novel": RouteTargetDescriptor(
        id="Coordinator",
        kind=ROUTE_TARGET_UI_VIRTUAL,
        display_name="创作协调器",
        purpose="组织世界观、大纲、角色和章节创作工作流",
        accept_task_types=["create_novel"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="NovelCoordinator",
        priority=100,
    ),
    "create_character": RouteTargetDescriptor(
        id="CharacterBuilder",
        kind=ROUTE_TARGET_AGENT,
        display_name="角色构建师",
        purpose="生成结构化角色卡与角色设定",
        accept_task_types=["build_characters", "create_character"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=80,
    ),
    "create_eventlines": RouteTargetDescriptor(
        id="EventlineBuilder",
        kind=ROUTE_TARGET_AGENT,
        display_name="事件线构建师",
        purpose="生成主线、支线和人物事件线",
        accept_task_types=["create_eventlines"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=70,
    ),
    "create_detail_outline": RouteTargetDescriptor(
        id="DetailOutlineBuilder",
        kind=ROUTE_TARGET_AGENT,
        display_name="细纲构建师",
        purpose="生成分场、冲突和推进要点",
        accept_task_types=["create_detail_outline"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=70,
    ),
    "create_chapter_settings": RouteTargetDescriptor(
        id="ChapterSettingBuilder",
        kind=ROUTE_TARGET_AGENT,
        display_name="章纲构建师",
        purpose="生成章节目标、关键事件和结尾钩子",
        accept_task_types=["create_chapter_settings"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=70,
    ),
    "create_project_data": RouteTargetDescriptor(
        id="ProjectDataBuilder",
        kind=ROUTE_TARGET_UI_VIRTUAL,
        display_name="资料构建器",
        purpose="根据对话生成项目资料库条目",
        accept_task_types=["create_project_data"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="RouterAgent",
        priority=70,
    ),
    "continue_write": RouteTargetDescriptor(
        id="ContinuousWriter",
        kind=ROUTE_TARGET_AGENT,
        display_name="连续创作师",
        purpose="基于现有正文和上下文续写章节",
        accept_task_types=["continue_write"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=80,
    ),
    "polish_content": RouteTargetDescriptor(
        id="Polisher",
        kind=ROUTE_TARGET_AGENT,
        display_name="文字润色师",
        purpose="润色、改写和提升文本表达",
        accept_task_types=["polish_content", "polish_chapter"],
        risk_level="writes_project_content",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=80,
    ),
    "search_web": RouteTargetDescriptor(
        id="WebSearch",
        kind=ROUTE_TARGET_TOOL,
        display_name="网络搜索工具",
        purpose="调用外部搜索技能获取网页信息",
        accept_task_types=["search_web"],
        risk_level="external_tool",
        visibility="user_visible",
        execution_backend="Skill",
        priority=60,
    ),
    "search_trends": RouteTargetDescriptor(
        id="TrendsSearch",
        kind=ROUTE_TARGET_TOOL,
        display_name="热点搜索工具",
        purpose="调用热点技能获取趋势信息",
        accept_task_types=["search_trends"],
        risk_level="external_tool",
        visibility="user_visible",
        execution_backend="Skill",
        priority=60,
    ),
    "query_knowledge": RouteTargetDescriptor(
        id="Communicator",
        kind=ROUTE_TARGET_AGENT,
        display_name="沟通助手",
        purpose="结合知识库回答用户问题",
        accept_task_types=["query_knowledge", "general_chat"],
        risk_level="read_only",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=50,
    ),
    "general_chat": RouteTargetDescriptor(
        id="Communicator",
        kind=ROUTE_TARGET_AGENT,
        display_name="沟通助手",
        purpose="对话、澄清需求和轻量规划",
        accept_task_types=["general_chat"],
        risk_level="read_only",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=50,
    ),
    "ask_help": RouteTargetDescriptor(
        id="Communicator",
        kind=ROUTE_TARGET_AGENT,
        display_name="沟通助手",
        purpose="解释功能和使用方式",
        accept_task_types=["ask_help"],
        risk_level="read_only",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=50,
    ),
    "provide_feedback": RouteTargetDescriptor(
        id="Communicator",
        kind=ROUTE_TARGET_AGENT,
        display_name="沟通助手",
        purpose="接收用户反馈并给出后续建议",
        accept_task_types=["provide_feedback"],
        risk_level="read_only",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=50,
    ),
    "project_manage": RouteTargetDescriptor(
        id="ProjectManager",
        kind=ROUTE_TARGET_UI_VIRTUAL,
        display_name="项目管理器",
        purpose="展示或处理项目状态类请求",
        accept_task_types=["project_manage"],
        risk_level="project_state",
        visibility="user_visible",
        execution_backend="RouterAgent",
        priority=50,
    ),
    "config_settings": RouteTargetDescriptor(
        id="Communicator",
        kind=ROUTE_TARGET_AGENT,
        display_name="沟通助手",
        purpose="解释配置问题并引导设置",
        accept_task_types=["config_settings"],
        risk_level="read_only",
        visibility="user_visible",
        execution_backend="BaseAgent",
        priority=50,
    ),
}


def get_default_intent_route_target(intent_name: str) -> Optional[RouteTargetDescriptor]:
    return DEFAULT_INTENT_ROUTE_TARGETS.get(str(intent_name or "").strip())


def build_default_route_target_registry() -> RouteTargetRegistry:
    registry = RouteTargetRegistry()
    for target in DEFAULT_INTENT_ROUTE_TARGETS.values():
        existing = registry.get(target.id)
        if existing is None:
            registry.register(RouteTargetDescriptor(**target.to_dict()))
            continue
        for task_type in target.accept_task_types or []:
            if task_type not in existing.accept_task_types:
                existing.accept_task_types.append(task_type)
        existing.priority = max(int(existing.priority or 0), int(target.priority or 0))
        existing.metadata.update(dict(target.metadata or {}))
    return registry
