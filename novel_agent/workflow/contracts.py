"""监督式自组织协作的合同与任务模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


def _now_iso() -> str:
    """返回当前 ISO8601 时间。"""
    return datetime.now().isoformat()


def _new_id() -> str:
    """返回 UUID 字符串。"""
    return str(uuid.uuid4())


@dataclass
class TaskDependency:
    """任务依赖定义。"""

    dependency_key: str
    required: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDependency":
        return cls(
            dependency_key=str(data.get("dependency_key") or "").strip(),
            required=bool(data.get("required", True)),
            description=str(data.get("description") or "").strip(),
        )


@dataclass
class TaskDefinition:
    """任务定义。"""

    task_id: str = field(default_factory=_new_id)
    task_type: str = ""
    title: str = ""
    description: str = ""
    status: str = "pending"
    priority: int = 50
    depends_on: List[str] = field(default_factory=list)
    dependencies: List[TaskDependency] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)
    candidate_agents: List[str] = field(default_factory=list)
    assigned_agent: str = ""
    result_ref: str = ""
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    review_required: bool = False
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def touch(self) -> None:
        """刷新更新时间。"""
        self.updated_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["dependencies"] = [item.to_dict() for item in self.dependencies]
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDefinition":
        dependencies_raw = data.get("dependencies") or []
        return cls(
            task_id=str(data.get("task_id") or _new_id()).strip(),
            task_type=str(data.get("task_type") or "").strip(),
            title=str(data.get("title") or "").strip(),
            description=str(data.get("description") or "").strip(),
            status=str(data.get("status") or "pending").strip() or "pending",
            priority=int(data.get("priority", 50) or 50),
            depends_on=[
                str(item).strip()
                for item in (data.get("depends_on") or [])
                if str(item).strip()
            ],
            dependencies=[
                TaskDependency.from_dict(item)
                for item in dependencies_raw
                if isinstance(item, dict)
            ],
            inputs=dict(data.get("inputs") or {}),
            expected_outputs=[
                str(item).strip()
                for item in (data.get("expected_outputs") or [])
                if str(item).strip()
            ],
            candidate_agents=[
                str(item).strip()
                for item in (data.get("candidate_agents") or [])
                if str(item).strip()
            ],
            assigned_agent=str(data.get("assigned_agent") or "").strip(),
            result_ref=str(data.get("result_ref") or "").strip(),
            retry_count=int(data.get("retry_count", 0) or 0),
            metadata=dict(data.get("metadata") or {}),
            review_required=bool(data.get("review_required", False)),
            created_at=str(data.get("created_at") or _now_iso()).strip(),
            updated_at=str(data.get("updated_at") or _now_iso()).strip(),
        )


@dataclass
class ExecutionPolicy:
    """执行策略定义。"""

    supervised_mode: bool = True
    fallback_to_orchestrated: bool = True
    max_negotiation_rounds: int = 3
    max_task_retries: int = 2
    claim_timeout_seconds: int = 30
    task_timeout_seconds: int = 900
    require_user_confirmation_nodes: List[str] = field(
        default_factory=lambda: [
            "contract_confirmation",
            "outline_confirmation",
            "replan_confirmation",
            "final_review",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionPolicy":
        return cls(
            supervised_mode=bool(data.get("supervised_mode", True)),
            fallback_to_orchestrated=bool(data.get("fallback_to_orchestrated", True)),
            max_negotiation_rounds=int(data.get("max_negotiation_rounds", 3) or 3),
            max_task_retries=int(data.get("max_task_retries", 2) or 2),
            claim_timeout_seconds=int(data.get("claim_timeout_seconds", 30) or 30),
            task_timeout_seconds=int(data.get("task_timeout_seconds", 900) or 900),
            require_user_confirmation_nodes=[
                str(item).strip()
                for item in (data.get("require_user_confirmation_nodes") or [])
                if str(item).strip()
            ] or [
                "contract_confirmation",
                "outline_confirmation",
                "replan_confirmation",
                "final_review",
            ],
        )


@dataclass
class CreationContract:
    """创作任务合同。"""

    contract_id: str = field(default_factory=_new_id)
    goal: str = "创作一部长篇小说"
    user_confirmed: bool = False
    scope: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    deliverables: List[str] = field(default_factory=list)
    agent_candidates: List[str] = field(default_factory=list)
    task_graph: List[TaskDefinition] = field(default_factory=list)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    source_session_id: str = ""
    source_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def touch(self) -> None:
        """刷新更新时间。"""
        self.updated_at = _now_iso()

    def add_task(self, task: TaskDefinition) -> None:
        """向任务图中追加任务。"""
        self.task_graph.append(task)
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "goal": self.goal,
            "user_confirmed": self.user_confirmed,
            "scope": dict(self.scope),
            "constraints": dict(self.constraints),
            "deliverables": list(self.deliverables),
            "agent_candidates": list(self.agent_candidates),
            "task_graph": [task.to_dict() for task in self.task_graph],
            "execution_policy": self.execution_policy.to_dict(),
            "source_session_id": self.source_session_id,
            "source_message": self.source_message,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreationContract":
        tasks = [
            TaskDefinition.from_dict(item)
            for item in (data.get("task_graph") or [])
            if isinstance(item, dict)
        ]
        execution_policy_raw = data.get("execution_policy") or {}
        return cls(
            contract_id=str(data.get("contract_id") or _new_id()).strip(),
            goal=str(data.get("goal") or "创作一部长篇小说").strip() or "创作一部长篇小说",
            user_confirmed=bool(data.get("user_confirmed", False)),
            scope=dict(data.get("scope") or {}),
            constraints=dict(data.get("constraints") or {}),
            deliverables=[
                str(item).strip()
                for item in (data.get("deliverables") or [])
                if str(item).strip()
            ],
            agent_candidates=[
                str(item).strip()
                for item in (data.get("agent_candidates") or [])
                if str(item).strip()
            ],
            task_graph=tasks,
            execution_policy=ExecutionPolicy.from_dict(execution_policy_raw),
            source_session_id=str(data.get("source_session_id") or "").strip(),
            source_message=str(data.get("source_message") or "").strip(),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or _now_iso()).strip(),
            updated_at=str(data.get("updated_at") or _now_iso()).strip(),
        )


def build_default_creation_contract(
    *,
    novel_type: str = "",
    theme: str = "",
    requirements: str = "",
    protagonist: str = "",
    plot_idea: str = "",
    volume_count: int = 1,
    chapters_per_volume: int = 5,
    target_word_count: int = 0,
    target_words_per_chapter: int = 0,
    ai_autonomy_requested: bool = False,
    source_session_id: str = "",
    source_message: str = "",
    user_confirmed: bool = False,
) -> CreationContract:
    """根据现有创作参数构建默认合同。"""
    total_chapters = max(1, int(volume_count or 1)) * max(1, int(chapters_per_volume or 1))
    normalized_target_words = max(0, int(target_word_count or 0))
    normalized_words_per_chapter = max(0, int(target_words_per_chapter or 0))
    if normalized_target_words and total_chapters and not normalized_words_per_chapter:
        normalized_words_per_chapter = max(500, int((normalized_target_words + total_chapters - 1) / total_chapters))

    contract = CreationContract(
        goal="创作一部长篇小说",
        user_confirmed=user_confirmed,
        scope={
            "novel_type": str(novel_type or "").strip(),
            "theme": str(theme or "").strip(),
            "requirements": str(requirements or "").strip(),
            "protagonist": str(protagonist or "").strip(),
            "plot_idea": str(plot_idea or "").strip(),
            "volume_count": max(1, int(volume_count or 1)),
            "chapters_per_volume": max(1, int(chapters_per_volume or 1)),
            "total_chapters": total_chapters,
            "target_word_count": normalized_target_words,
            "target_words_per_chapter": normalized_words_per_chapter,
            "ai_autonomy_requested": bool(ai_autonomy_requested),
        },
        constraints={
            "style": [],
            "forbidden": [],
            "quality_rules": ["避免AI腔", "保证连贯性"],
        },
        deliverables=[
            "worldbuilding.json",
            "characters.json",
            "outline.json",
            "chapters/*.md",
            "stage_summaries/*.md",
        ],
        agent_candidates=[
            "Worldbuilder",
            "Outliner",
            "CharacterBuilder",
            "ContextStrategy",
            "ContentReader",
            "ChapterWriter",
            "Evaluator",
            "Polisher",
            "ContentExpansion",
            "FileNaming",
            "SummaryOrchestrator",
        ],
        source_session_id=str(source_session_id or "").strip(),
        source_message=str(source_message or "").strip(),
        metadata={
            "draft": not user_confirmed,
            "created_from": "legacy_orchestrated_flow",
        },
    )
    return contract


def build_default_task_graph(contract: CreationContract) -> List[TaskDefinition]:
    """基于合同生成阶段一默认任务图草案。"""
    scope = contract.scope or {}
    total_chapters = max(1, int(scope.get("total_chapters") or 1))
    discussion_context = str(scope.get("discussion_context") or "").strip()
    target_word_count = int(scope.get("target_word_count") or 0)
    target_words_per_chapter = int(scope.get("target_words_per_chapter") or 0)
    ai_autonomy_requested = bool(scope.get("ai_autonomy_requested", False))
    autonomous_brief = (
        "用户已授权助手自主安排未指定的世界观、角色姓名、人物设定和剧情细节；"
        "请在已给定题材、主题、篇幅与讨论方向内主动补全，不要因姓名或剧情空白而要求用户继续补充。"
        if ai_autonomy_requested
        else ""
    )
    discussion_inputs = (
        {
            "discussion_context": discussion_context,
            "recent_discussion": discussion_context,
        }
        if discussion_context
        else {}
    )

    tasks: List[TaskDefinition] = [
        TaskDefinition(
            task_type="build_world",
            title="生成世界观",
            description="基于创作合同生成世界观设定",
            priority=100,
            expected_outputs=["worldbuilding.json"],
            candidate_agents=["Worldbuilder"],
            inputs={
                "novel_type": scope.get("novel_type", ""),
                "theme": scope.get("theme", ""),
                "requirements": scope.get("requirements", ""),
                "target_word_count": target_word_count,
                "ai_autonomy_requested": ai_autonomy_requested,
                **({"autonomous_brief": autonomous_brief} if autonomous_brief else {}),
                **discussion_inputs,
            },
        ),
        TaskDefinition(
            task_type="build_characters",
            title="生成角色档案",
            description="基于世界观、主角设定和创作要求生成角色档案",
            priority=98,
            depends_on=[],
            dependencies=[
                TaskDependency(
                    dependency_key="world_ready",
                    required=True,
                    description="需要先完成世界观生成",
                )
            ],
            expected_outputs=["characters.json"],
            candidate_agents=["CharacterBuilder"],
            inputs={
                "novel_type": scope.get("novel_type", ""),
                "theme": scope.get("theme", ""),
                "protagonist": scope.get("protagonist", ""),
                "plot_idea": scope.get("plot_idea", ""),
                "character_request": (
                    scope.get("protagonist", "")
                    or scope.get("plot_idea", "")
                    or autonomous_brief
                ),
                "request_mode": "autonomous_draft" if ai_autonomy_requested else "draft",
                "target_word_count": target_word_count,
                "ai_autonomy_requested": ai_autonomy_requested,
                **({"autonomous_brief": autonomous_brief} if autonomous_brief else {}),
                **discussion_inputs,
            },
        ),
        TaskDefinition(
            task_type="build_outline",
            title="生成大纲",
            description="基于世界观、角色档案和主角设定生成章节大纲",
            priority=95,
            depends_on=[],
            dependencies=[
                TaskDependency(
                    dependency_key="world_ready",
                    required=True,
                    description="需要先完成世界观生成",
                ),
                TaskDependency(
                    dependency_key="characters_ready",
                    required=True,
                    description="需要先完成角色档案生成",
                ),
            ],
            expected_outputs=["outline.json"],
            candidate_agents=["Outliner"],
            inputs={
                "protagonist": scope.get("protagonist", ""),
                "plot_idea": scope.get("plot_idea", ""),
                "volume_count": scope.get("volume_count", 1),
                "chapters_per_volume": scope.get("chapters_per_volume", 5),
                "target_word_count": target_word_count,
                "target_words_per_chapter": target_words_per_chapter,
                "ai_autonomy_requested": ai_autonomy_requested,
                **({"autonomous_brief": autonomous_brief} if autonomous_brief else {}),
                **discussion_inputs,
            },
            review_required=True,
        ),
    ]

    for chapter_number in range(1, total_chapters + 1):
        tasks.append(
            TaskDefinition(
                task_type="write_chapter",
                title=f"创作第{chapter_number}章",
                description=f"根据大纲创作第{chapter_number}章正文",
                priority=max(10, 90 - chapter_number),
                depends_on=[],
                dependencies=[
                    TaskDependency(
                        dependency_key="outline_ready",
                        required=True,
                        description="需要先完成大纲生成",
                    )
                ],
                expected_outputs=[f"chapters/chapter_{chapter_number}.md"],
                candidate_agents=["ChapterWriter"],
                inputs={
                    "chapter_number": chapter_number,
                    **({"word_count": target_words_per_chapter} if target_words_per_chapter else {}),
                    **discussion_inputs,
                },
            )
        )

    for end_chapter in range(10, total_chapters + 1, 10):
        start_chapter = max(1, end_chapter - 9)
        tasks.append(
            TaskDefinition(
                task_type="summary_orchestrate",
                title=f"生成第{start_chapter}-{end_chapter}章阶段总结",
                description=f"汇总第{start_chapter}-{end_chapter}章剧情与阶段产物",
                priority=max(5, 60 - end_chapter // 10),
                depends_on=[],
                expected_outputs=[f"stage_summaries/第{start_chapter}-{end_chapter}章-剧情总结.md"],
                candidate_agents=["SummaryOrchestrator"],
                inputs={
                    "start_chapter": start_chapter,
                    "end_chapter": end_chapter,
                    "chapters": [],
                    **discussion_inputs,
                },
                metadata={
                    "result_kind": "stage_summary",
                    "summary_range": [start_chapter, end_chapter],
                },
            )
        )

    return tasks
