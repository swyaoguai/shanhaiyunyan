import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, patch

from fastapi.responses import JSONResponse

import pytest

from novel_agent.agent_config import AgentModelConfig
from novel_agent.agents.base_agent import AgentCapability, BaseAgent
from novel_agent.agents.capability_registry import AgentCapabilityRegistry
from novel_agent.constants import get_data_dir
from novel_agent.project_manager import ProjectManager
from novel_agent.route_targets import (
    ROUTE_TARGET_AGENT,
    ROUTE_TARGET_HELPER_SERVICE,
    ROUTE_TARGET_UI_VIRTUAL,
)
from novel_agent.workflow.contracts import (
    CreationContract,
    ExecutionPolicy,
    TaskDefinition,
    TaskDependency,
    build_default_creation_contract,
    build_default_task_graph,
)
from novel_agent.workflow.coordinator import NovelCoordinator
from novel_agent.workflow.execution_context import CollabExecutionContext
from novel_agent.workflow.routing_policy import RoutingPolicy
from novel_agent.workflow.task_pool import TaskPool, TaskStatus
from novel_agent.web.routes.novel import get_status


class StubAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        *,
        accepted_tasks: Optional[list[str]] = None,
        priority: int = 50,
        result: Optional[Dict[str, Any]] = None,
        raise_error: bool = False,
        model_config: Optional[AgentModelConfig] = None,
    ):
        self._accepted_tasks = accepted_tasks or []
        self._priority = priority
        self._result = result if result is not None else {"success": True}
        self._raise_error = raise_error
        self.calls = []
        super().__init__(
            name=name,
            model_config=model_config or AgentModelConfig(
                agent_name=name,
                model="test-model",
                api_key="test-key",
                api_base="https://example.invalid/v1",
                temperature=0.3,
                max_tokens=1024,
            ),
        )

    def _get_default_prompt(self) -> str:
        return "stub"

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=list(self._accepted_tasks),
            accept_task_types=list(self._accepted_tasks),
            required_inputs=["input"],
            produced_outputs=["success"],
            priority=self._priority,
            max_concurrency=1,
            metadata={"agent_class": self.__class__.__name__},
        )

    async def execute(self, input_data: Dict[str, Any], context=None) -> Dict[str, Any]:
        self.calls.append({
            "input_data": dict(input_data or {}),
            "context": dict(context or {}) if isinstance(context, dict) else context,
        })
        if self._raise_error:
            raise RuntimeError(f"{self.name} failed")
        return dict(self._result)


def build_character_stub() -> StubAgent:
    return StubAgent(
        "AutoCharacterBuilder",
        accepted_tasks=["build_characters"],
        priority=98,
        result={
            "success": True,
            "characters": [
                {
                    "name": "林渊",
                    "role": "主角",
                    "description": "旧案幸存者。",
                }
            ],
        },
    )


def build_chapter_settings_stub(total_chapters: int = 2) -> StubAgent:
    return StubAgent(
        "AutoChapterSettingBuilder",
        accepted_tasks=["chapter_settings"],
        priority=94,
        result={
            "success": True,
            "rows": [
                {
                    "name": f"第{chapter_number}章",
                    "description": f"章纲摘要{chapter_number}",
                    "chapter_number": chapter_number,
                    "chapter_goal": f"目标{chapter_number}",
                    "key_event": f"事件{chapter_number}",
                    "ending_hook": f"钩子{chapter_number}",
                }
                for chapter_number in range(1, total_chapters + 1)
            ],
        },
    )


def build_valid_outline_payload(title: str = "归墟录", volume_count: int = 1) -> Dict[str, Any]:
    volumes = [
        {
            "volume_number": index,
            "volume_title": f"第{index}卷 风雪旧城",
            "volume_summary": f"第{index}卷围绕旧城归来后的阶段目标展开。",
            "core_conflict": "旧案真相与宗门余波持续冲突。",
            "protagonist_growth": "主角从被动自保走向主动追查。",
            "volume_climax": "主角在卷末拿到关键证据。",
            "key_events": ["旧城归来", "暗线浮现", "卷末反击"],
            "foreshadowing": "旧案证物会在后续回收。",
        }
        for index in range(1, volume_count + 1)
    ]
    return {
        "title": title,
        "intro": "旧城归来后的复仇成长故事。",
        "story_synopsis": "林渊回到旧城，追查宗门旧案并重建信任。",
        "global_outline": (
            "书名《归墟录》。故事梗概：主角林渊回到旧城，从旧案线索切入，"
            "在宗门余波、势力追索和自我怀疑中逐步成长。世界规则以宗门秩序与旧城暗线为核心，"
            "中心思想是创伤后的自救与重建，矛盾冲突集中在真相追查、旧友立场和势力围堵。"
        ),
        "theme": "复仇成长",
        "main_conflict": "旧案真相与现实势力的对抗。",
        "selling_points": ["旧城悬疑", "复仇成长"],
        "ending_direction": "主角揭开旧案并完成阶段性成长。",
        "plot_threads": [
            {"name": "旧案追查线", "description": "围绕宗门旧案逐步推进。"},
        ],
        "volumes": volumes,
        "notes": "只保留卷级规划，章纲阶段再拆分单章。",
    }


@pytest.fixture
def mock_model_config():
    return AgentModelConfig(
        agent_name="TestAgent",
        model="test-model",
        api_key="test-key",
        api_base="https://example.invalid/v1",
        temperature=0.5,
        max_tokens=2048,
    )


@pytest.fixture
def coordinator(mock_model_config):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        project_manager = ProjectManager(data_dir=temp_path / "data")
        project = project_manager.create_project("测试项目", "隔离项目")
        project_manager.switch_project(project.id)
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            with (
                patch("novel_agent.project_manager.get_project_manager", return_value=project_manager),
                patch("novel_agent.workflow.coordinator.get_project_manager", return_value=project_manager),
            ):
                instance = NovelCoordinator(project_dir=project_manager._get_project_dir(project.id))
                instance.switch_to_project(project.id)
            yield instance


class TestContractModels:
    def test_task_definition_roundtrip_with_dependencies(self):
        task = TaskDefinition(
            task_type="write_chapter",
            title="创作第一章",
            description="根据大纲创作章节",
            priority=88,
            depends_on=["outline-task"],
            dependencies=[
                TaskDependency(
                    dependency_key="outline_ready",
                    required=True,
                    description="需要先完成大纲",
                )
            ],
            inputs={"chapter_number": 1},
            expected_outputs=["chapters/chapter_1.md"],
            candidate_agents=["ChapterWriter"],
            assigned_agent="ChapterWriter",
            result_ref="chapters/chapter_1.md",
            retry_count=1,
            metadata={"source": "test"},
            review_required=True,
        )

        restored = TaskDefinition.from_dict(task.to_dict())

        assert restored.task_type == "write_chapter"
        assert restored.depends_on == ["outline-task"]
        assert len(restored.dependencies) == 1
        assert restored.dependencies[0].dependency_key == "outline_ready"
        assert restored.candidate_agents == ["ChapterWriter"]
        assert restored.review_required is True
        assert restored.metadata["source"] == "test"

    def test_creation_contract_roundtrip_preserves_execution_policy(self):
        contract = CreationContract(
            goal="测试创作",
            user_confirmed=True,
            scope={"novel_type": "玄幻"},
            constraints={"quality_rules": ["避免AI腔"]},
            deliverables=["outline.json"],
            agent_candidates=["Outliner"],
            task_graph=[TaskDefinition(task_type="build_outline", title="生成大纲")],
            execution_policy=ExecutionPolicy(
                supervised_mode=True,
                fallback_to_orchestrated=True,
                max_negotiation_rounds=5,
                max_task_retries=4,
                claim_timeout_seconds=15,
                task_timeout_seconds=600,
                require_user_confirmation_nodes=["contract_confirmation", "final_review"],
            ),
            metadata={"stage": "test"},
        )

        restored = CreationContract.from_dict(contract.to_dict())

        assert restored.user_confirmed is True
        assert restored.execution_policy.supervised_mode is True
        assert restored.execution_policy.fallback_to_orchestrated is True
        assert restored.execution_policy.max_negotiation_rounds == 5
        assert restored.task_graph[0].task_type == "build_outline"
        assert restored.metadata["stage"] == "test"

    def test_build_default_creation_contract_and_task_graph(self):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=2,
            chapters_per_volume=3,
            source_session_id="sess-1",
            source_message="用户确认方案",
            user_confirmed=True,
        )
        task_graph = build_default_task_graph(contract)

        assert contract.scope["total_chapters"] == 6
        assert contract.user_confirmed is True
        assert contract.metadata["draft"] is False
        assert len(task_graph) == 10
        assert task_graph[0].task_type == "build_world"
        assert task_graph[1].task_type == "build_characters"
        assert task_graph[2].task_type == "build_outline"
        assert task_graph[3].task_type == "chapter_settings"
        assert task_graph[4].task_type == "write_chapter"
        assert task_graph[-1].inputs["chapter_number"] == 6
        assert task_graph[4].dependencies[0].dependency_key == "chapter_settings_ready"
        assert contract.metadata["pause_after_chapter_settings"] is True
        assert task_graph[3].review_required is True
        assert task_graph[3].metadata["stop_on_review_required"] is True

    def test_build_default_task_graph_adds_stage_summary_tasks_for_ten_chapters(self):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=10,
            user_confirmed=True,
        )

        task_graph = build_default_task_graph(contract)
        summary_tasks = [task for task in task_graph if task.task_type == "summary_orchestrate"]

        assert len(summary_tasks) == 1
        assert summary_tasks[0].inputs["start_chapter"] == 1
        assert summary_tasks[0].inputs["end_chapter"] == 10
        assert summary_tasks[0].candidate_agents == ["SummaryOrchestrator"]

    def test_build_default_task_graph_carries_discussion_context_to_generation_tasks(self):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="黑暗修仙",
            requirements="不要低俗",
            protagonist="林渡",
            plot_idea="宗门覆灭后的复仇与重建",
            volume_count=1,
            chapters_per_volume=1,
            user_confirmed=True,
        )
        contract.scope["discussion_context"] = "用户讨论确认：合欢宗元素危险克制，前期不要升级太快。"

        task_graph = build_default_task_graph(contract)
        task_by_type = {task.task_type: task for task in task_graph}

        assert "合欢宗元素" in task_by_type["build_world"].inputs["discussion_context"]
        assert "合欢宗元素" in task_by_type["build_characters"].inputs["recent_discussion"]
        assert "合欢宗元素" in task_by_type["build_outline"].inputs["discussion_context"]
        assert "合欢宗元素" in task_by_type["chapter_settings"].inputs["discussion_context"]
        assert "合欢宗元素" in task_by_type["write_chapter"].inputs["discussion_context"]


class TestBaseAgentCapabilities:
    class PassiveAgent(BaseAgent):
        def _get_default_prompt(self) -> str:
            return "passive"

        async def execute(self, input_data: Dict[str, Any], context=None) -> Dict[str, Any]:
            return {"success": True}

    def test_base_agent_default_capability_is_conservative(self, mock_model_config):
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            agent = self.PassiveAgent(name="PassiveAgent")

        capability = agent.get_capabilities()

        assert capability.agent_name == "PassiveAgent"
        assert capability.accept_task_types == []
        assert agent.accepts_task({"task_type": "write_chapter"}) is False
        assert agent.requires_inputs() == []
        assert agent.produces_outputs() == []
        estimate = agent.estimate_cost({"task_type": "write_chapter"})
        assert estimate["confidence"] == 0.0

    def test_accepts_task_and_io_come_from_capability(self):
        agent = StubAgent(
            "CapabilityAgent",
            accepted_tasks=["context_plan", "content_read"],
            result={"success": True},
        )

        assert agent.accepts_task({"task_type": "context_plan"}) is True
        assert agent.accepts_task({"task_type": "write_chapter"}) is False
        assert agent.requires_inputs() == ["input"]
        assert agent.produces_outputs() == ["success"]
        assert agent.estimate_cost({"task_type": "content_read"})["confidence"] == pytest.approx(0.3)


class TestCapabilityRegistry:
    def test_registry_finds_candidates_by_priority(self):
        registry = AgentCapabilityRegistry()
        low = StubAgent("LowPriority", accepted_tasks=["write_chapter"], priority=10)
        high = StubAgent("HighPriority", accepted_tasks=["write_chapter"], priority=90)
        other = StubAgent("OtherAgent", accepted_tasks=["context_plan"], priority=80)

        registry.register_many([low, high, other])

        candidates = registry.find_candidates({"task_type": "write_chapter"})

        assert [item["agent_name"] for item in candidates] == ["HighPriority", "LowPriority"]
        assert registry.find_candidate_names({"task_type": "context_plan"}) == ["OtherAgent"]
        assert registry.coverage_by_task_type()["write_chapter"] == ["HighPriority", "LowPriority"]

    def test_registry_unregister_and_snapshot(self):
        registry = AgentCapabilityRegistry()
        agent = StubAgent("SnapshotAgent", accepted_tasks=["evaluate_chapter"], priority=70)

        registry.register(agent)
        snapshot = registry.to_dict()
        assert snapshot["agent_count"] == 1
        assert snapshot["agents"] == ["SnapshotAgent"]
        assert snapshot["route_targets"][0]["id"] == "SnapshotAgent"
        assert snapshot["route_targets"][0]["kind"] == ROUTE_TARGET_AGENT

        removed = registry.unregister("SnapshotAgent")
        assert removed is True
        assert registry.get_agent("SnapshotAgent") is None
        assert registry.list_agents() == []

    def test_routing_policy_uses_dynamic_capability_candidate_without_explicit_rule(self):
        registry = AgentCapabilityRegistry()
        registry.register(StubAgent("RepairAgent", accepted_tasks=["unexpected_repair"], priority=90))

        decision = RoutingPolicy.default().resolve(
            task_type="unexpected_repair",
            stage="",
            context=CollabExecutionContext.from_legacy_context({}),
            capability_registry=registry,
            input_data={"input": "x"},
        )

        assert decision.agent_name == "RepairAgent"
        assert decision.candidate_source == "dynamic_capability_registry"
        assert decision.candidate_names == ["RepairAgent"]

    def test_routing_policy_prefers_fixed_builtin_agent_for_explicit_route(self):
        registry = AgentCapabilityRegistry()
        registry.register(StubAgent("AutoOutliner", accepted_tasks=["build_outline"], priority=99))

        decision = RoutingPolicy.default().resolve(
            task_type="build_outline",
            stage="project_ready",
            context=CollabExecutionContext.from_legacy_context({"project_dir": "C:/tmp/project"}),
            capability_registry=registry,
            input_data={"plot_idea": "旧城归来"},
            fallback_agent_name="Outliner",
        )

        assert decision.agent_name == "Outliner"
        assert decision.candidate_source == "fixed_route_rule"
        assert decision.candidate_names[0] == "Outliner"
        assert "fixed preferred agent" in decision.route_reason


class TestTaskPool:
    def test_task_pool_status_flow_and_retry_count(self):
        pool = TaskPool()
        dependency = pool.create_task(
            task_type="build_outline",
            title="生成大纲",
            candidate_agents=["Outliner"],
        )
        task = pool.create_task(
            task_type="write_chapter",
            title="创作第一章",
            depends_on=[dependency.task_id],
            candidate_agents=["ChapterWriter"],
        )

        ready_before = pool.get_ready_tasks()
        assert [item.task_id for item in ready_before] == [dependency.task_id]

        pool.update_task_status(
            task.task_id,
            TaskStatus.BLOCKED,
            metadata_patch={"blocked_reason": "waiting"},
        )
        assert pool.get_task(task.task_id).status == TaskStatus.BLOCKED

        pool.claim_task(dependency.task_id, "Outliner")
        pool.start_task(dependency.task_id, "Outliner")
        pool.complete_task(dependency.task_id, "outline.json")

        pool.claim_task(task.task_id, "ChapterWriter")
        pool.start_task(task.task_id, "ChapterWriter")
        pool.fail_task(task.task_id, "temporary error")

        failed = pool.get_task(task.task_id)
        assert failed.status == TaskStatus.FAILED
        assert failed.retry_count == 1
        assert failed.metadata["error"] == "temporary error"

    def test_task_pool_ready_review_snapshot_and_restore(self):
        prereq = TaskDefinition(task_type="build_outline", title="大纲")
        main = TaskDefinition(
            task_type="write_chapter",
            title="第一章",
            depends_on=[prereq.task_id],
        )
        pool = TaskPool([prereq, main])

        assert pool.get_ready_tasks()[0].task_id == prereq.task_id

        pool.claim_task(prereq.task_id, "Outliner")
        pool.start_task(prereq.task_id, "Outliner")
        pool.complete_task(prereq.task_id, "outline.json")

        ready = pool.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == main.task_id

        pool.claim_task(main.task_id, "ChapterWriter")
        pool.start_task(main.task_id, "ChapterWriter")
        pool.mark_review_required(main.task_id, "需要人工复核")
        assert pool.get_task(main.task_id).status == TaskStatus.REVIEW_REQUIRED

        restored = TaskPool.from_dict(pool.to_dict())
        assert restored.get_task(main.task_id).status == TaskStatus.REVIEW_REQUIRED
        assert restored.dependency_graph()[main.task_id] == [prereq.task_id]


class TestCoordinatorAutonomousTask:
    def test_phase2_scoped_collab_registry_excludes_helpers_from_global_registry(self, coordinator):
        global_agents = coordinator.capability_registry.list_agents()
        scoped_agents = coordinator.collab_agent_registry.list_agents()

        assert "ContextStrategy" not in global_agents
        assert "ContentReader" not in global_agents
        assert "ContentExpansion" not in global_agents
        assert "SummaryOrchestrator" not in global_agents
        assert "FileNaming" not in global_agents

        assert "ContextStrategy" in scoped_agents
        assert "ContentReader" in scoped_agents
        assert "ContentExpansion" in scoped_agents
        assert "SummaryOrchestrator" in scoped_agents
        assert "FileNaming" not in scoped_agents
        assert coordinator.collab_service_registry.get("file_naming") is coordinator.file_naming

    def test_route_target_snapshot_unifies_agents_helpers_and_virtual_targets(self, coordinator):
        snapshot = coordinator.get_route_targets()
        targets = {item["id"]: item for item in snapshot["targets"]}

        assert targets["Coordinator"]["kind"] == ROUTE_TARGET_UI_VIRTUAL
        assert targets["ChapterWriter"]["kind"] == ROUTE_TARGET_AGENT
        assert targets["ContextStrategy"]["kind"] == ROUTE_TARGET_HELPER_SERVICE
        assert "write_chapter" in targets["ChapterWriter"]["accept_task_types"]
        assert "context_plan" in targets["ContextStrategy"]["accept_task_types"]

    @pytest.mark.asyncio
    async def test_phase2_scoped_collab_registry_routes_helper_tasks(self, coordinator):
        result = await coordinator._run_autonomous_task(
            task_type="context_plan",
            input_data={
                "chapter_number": 1,
                "chapter_title": "第一章",
                "world": {"era": "玄幻"},
            },
            context={"project_dir": str(coordinator.project_dir)},
            fallback_agent=coordinator.context_strategy,
            title="上下文规划",
        )

        assert result["selected_agent"] == "ContextStrategy"
        assert result["candidate_agents"] == ["ContextStrategy"]
        assert result["result"]["strategy"]["chapter_number"] == 1

    @pytest.mark.asyncio
    async def test_run_autonomous_task_prefers_capability_candidate(self, coordinator):
        registry = AgentCapabilityRegistry()
        auto_agent = StubAgent(
            "AutoWriter",
            accepted_tasks=["write_chapter"],
            priority=99,
            result={"success": True, "content": "auto"},
        )
        fallback_agent = StubAgent(
            "FallbackWriter",
            accepted_tasks=["write_chapter"],
            priority=20,
            result={"success": True, "content": "fallback"},
        )
        registry.register(auto_agent)

        coordinator.capability_registry = registry
        coordinator.supervised_mode = True
        coordinator.fallback_to_orchestrated = True

        result = await coordinator._run_autonomous_task(
            task_type="write_chapter",
            input_data={"input": "chapter"},
            fallback_agent=fallback_agent,
            title="写章",
            expected_outputs=["content"],
        )

        runtime_task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
        runtime_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        runtime_tasks = runtime_task_pool.get("tasks", [])
        runtime_task = next(
            (
                item for item in runtime_tasks
                if item.get("task_type") == "write_chapter" and item.get("title") == "写章"
            ),
            None,
        )

        assert result["selected_agent"] == "AutoWriter"
        assert result["execution_mode"] == "autonomous"
        assert result["fallback_used"] is False
        assert result["result"]["content"] == "auto"
        assert result["runtime_task_pool"]["tasks"]
        assert runtime_tasks
        assert runtime_task is not None
        assert runtime_task["status"] == TaskStatus.COMPLETED
        assert runtime_task["assigned_agent"] == "AutoWriter"
        assert set(result["runtime_task_pool"].keys()) == {"tasks", "created_at", "updated_at", "metadata"}
        assert runtime_task["metadata"]["candidate_source"] == "capability_registry"
        assert runtime_task["metadata"]["route_reason"]
        assert runtime_task["metadata"]["context_snapshot_id"]
        event_types = [item["type"] for item in runtime_trace["events"]]
        assert "task_registered" in event_types
        assert event_types[-1] == "task_completed"
        assert all("created_at" not in item for item in runtime_trace["events"])
        assert all(item.get("timestamp") for item in runtime_trace["events"])

    @pytest.mark.asyncio
    async def test_run_autonomous_task_falls_back_after_failure(self, coordinator):
        registry = AgentCapabilityRegistry()
        failing_agent = StubAgent(
            "AutoEvaluator",
            accepted_tasks=["evaluate_chapter"],
            priority=99,
            raise_error=True,
        )
        fallback_agent = StubAgent(
            "FallbackEvaluator",
            accepted_tasks=["evaluate_chapter"],
            priority=10,
            result={"success": True, "evaluation": {"passed": True}},
        )
        registry.register(failing_agent)

        coordinator.capability_registry = registry
        coordinator.supervised_mode = True
        coordinator.fallback_to_orchestrated = True

        result = await coordinator._run_autonomous_task(
            task_type="evaluate_chapter",
            input_data={"input": "content"},
            fallback_agent=fallback_agent,
            title="评估章节",
            review_required=True,
        )

        tasks = result["task_pool"]["tasks"]
        statuses = [task["status"] for task in tasks]
        runtime_task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
        runtime_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        runtime_tasks = runtime_task_pool.get("tasks", [])
        runtime_task = next(
            (
                item for item in runtime_tasks
                if item.get("task_type") == "evaluate_chapter" and item.get("title") == "评估章节"
            ),
            None,
        )

        assert result["selected_agent"] == "FallbackEvaluator"
        assert result["execution_mode"] == "fallback_orchestrated"
        assert result["fallback_used"] is True
        assert "AutoEvaluator failed" in result["autonomous_error"]
        assert result["fallback_provenance"]["from_agent"] == "AutoEvaluator"
        assert result["fallback_provenance"]["to_agent"] == "FallbackEvaluator"
        assert TaskStatus.FAILED in statuses
        assert TaskStatus.COMPLETED in statuses
        assert runtime_task is not None
        assert runtime_task["assigned_agent"] == "FallbackEvaluator"
        assert runtime_task["status"] == TaskStatus.COMPLETED
        assert runtime_task["metadata"]["fallback_provenance"]["from_agent"] == "AutoEvaluator"
        event_types = [item["type"] for item in runtime_trace["events"]]
        assert "task_failed" in event_types
        assert "task_fallback_started" in event_types
        assert event_types[-1] == "task_completed"

    @pytest.mark.asyncio
    async def test_run_autonomous_task_surfaces_structured_agent_failure_reason(self, coordinator):
        registry = AgentCapabilityRegistry()
        failing_agent = StubAgent(
            "AutoCharacterBuilder",
            accepted_tasks=["build_characters"],
            priority=99,
            result={
                "success": False,
                "response_message": "角色卡草稿质量不足，暂不保存。",
                "missing_info": ["角色缺少 name", "角色描述过短"],
                "validation_issues": ["缺少已确认角色名：沈清悦"],
            },
        )
        registry.register(failing_agent)

        coordinator.capability_registry = registry
        coordinator.supervised_mode = True
        coordinator.fallback_to_orchestrated = False

        with pytest.raises(RuntimeError) as exc_info:
            await coordinator._run_autonomous_task(
                task_type="build_characters",
                input_data={"input": "characters"},
                title="生成角色档案",
            )

        error_text = str(exc_info.value)
        runtime_task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
        runtime_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        failed_task = next(item for item in runtime_task_pool.get("tasks", []) if item.get("task_type") == "build_characters")
        failed_event = next(item for item in runtime_trace.get("events", []) if item.get("type") == "task_failed")

        assert "角色卡草稿质量不足" in error_text
        assert "角色缺少 name" in error_text
        assert "缺少已确认角色名：沈清悦" in error_text
        assert failed_task["metadata"]["error"] == error_text
        assert failed_event["error"] == error_text

    @pytest.mark.asyncio
    async def test_run_autonomous_task_without_supervised_mode_uses_fallback_directly(self, coordinator):
        registry = AgentCapabilityRegistry()
        auto_agent = StubAgent(
            "AutoContext",
            accepted_tasks=["context_plan"],
            priority=99,
            result={"success": True, "strategy": {"k": "v"}},
        )
        fallback_agent = StubAgent(
            "FallbackContext",
            accepted_tasks=["context_plan"],
            priority=1,
            result={"success": True, "strategy": {"mode": "fallback"}},
        )
        registry.register(auto_agent)

        coordinator.capability_registry = registry
        coordinator.supervised_mode = False
        coordinator.fallback_to_orchestrated = True

        result = await coordinator._run_autonomous_task(
            task_type="context_plan",
            input_data={"input": "ctx"},
            fallback_agent=fallback_agent,
            title="上下文规划",
        )

        assert result["selected_agent"] == "FallbackContext"
        assert result["execution_mode"] == "autonomous"
        assert result["fallback_used"] is True
        assert result["autonomous_error"] == ""
        assert result["result"]["strategy"]["mode"] == "fallback"
        assert result["candidate_source"] == "fallback_direct"

    @pytest.mark.asyncio
    async def test_run_autonomous_task_uses_fixed_route_when_capability_candidates_are_empty(self, coordinator):
        coordinator.capability_registry = AgentCapabilityRegistry()
        fallback_agent = StubAgent(
            "FallbackWorldbuilder",
            accepted_tasks=["build_world"],
            priority=10,
            result={"success": True, "world": {"world_name": "固定路由世界"}},
        )

        result = await coordinator._run_autonomous_task(
            task_type="build_world",
            input_data={"novel_type": "玄幻"},
            context={"project_dir": str(coordinator.project_dir)},
            fallback_agent=fallback_agent,
            stage="project_ready",
            title="构建世界观",
            expected_outputs=["world"],
        )

        runtime_task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
        runtime_task = next(
            (
                item for item in runtime_task_pool.get("tasks", [])
                if item.get("task_type") == "build_world" and item.get("title") == "构建世界观"
            ),
            None,
        )

        assert result["selected_agent"] == "FallbackWorldbuilder"
        assert result["candidate_source"] == "fixed_route_rule"
        assert "fixed route agent" in result["route_reason"]
        assert runtime_task is not None
        assert runtime_task["metadata"]["candidate_source"] == "fixed_route_rule"

    @pytest.mark.asyncio
    async def test_run_autonomous_task_creates_and_removes_task_scoped_ephemeral_agent(self, coordinator):
        coordinator.capability_registry = AgentCapabilityRegistry()
        coordinator.allow_ephemeral_agents = True
        coordinator.agent_dispatcher.ephemeral_agent_factory = lambda envelope, reason: StubAgent(
            "EphemeralRepair",
            accepted_tasks=[envelope.task_type],
            priority=5,
            result={"success": True, "response": "临时处理完成"},
        )

        result = await coordinator._run_autonomous_task(
            task_type="unexpected_repair",
            input_data={"input": "broken state"},
            title="突发修复",
        )

        runtime_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        event_types = [item["type"] for item in runtime_trace["events"]]

        assert result["selected_agent"] == "EphemeralRepair"
        assert result["candidate_source"] == "ephemeral_agent"
        assert result["result"]["response"] == "临时处理完成"
        assert "EphemeralRepair" not in coordinator.collab_agent_registry.list_agents()
        assert "ephemeral_agent_created" in event_types
        assert "ephemeral_agent_removed" in event_types

    @pytest.mark.asyncio
    async def test_run_autonomous_task_fails_fast_when_required_context_is_missing(self, coordinator):
        coordinator.capability_registry = AgentCapabilityRegistry()
        fallback_agent = StubAgent(
            "FallbackWorldbuilder",
            accepted_tasks=["build_world"],
            priority=10,
            result={"success": True, "world": {"world_name": "不应执行"}},
        )
        fallback_agent.execute = AsyncMock(return_value={"success": True, "world": {"world_name": "不应执行"}})

        with pytest.raises(Exception, match="Missing required context keys: project_dir"):
            await coordinator._run_autonomous_task(
                task_type="build_world",
                input_data={"novel_type": "玄幻"},
                context={},
                fallback_agent=fallback_agent,
                stage="project_ready",
                title="缺上下文世界观",
                expected_outputs=["world"],
            )

        fallback_agent.execute.assert_not_awaited()


class TestCoordinatorChapterTaskMarket:
    @pytest.mark.asyncio
    async def test_execute_chapter_task_market_runs_dependency_chain_with_polish_feedback_loop(self, coordinator):
        registry = AgentCapabilityRegistry()
        registry.register_many([
            StubAgent(
                "AutoContextStrategy",
                accepted_tasks=["context_plan"],
                priority=90,
                result={"success": True, "strategy": {"read_plan": [{"key": "chapter_outline"}]}},
            ),
            StubAgent(
                "AutoContentReader",
                accepted_tasks=["content_read"],
                priority=89,
                result={
                    "success": True,
                    "loaded_context": {"chapter_outline": "已加载大纲", "world": {"name": "world"}},
                    "report": [{"key": "chapter_outline", "loaded": True}],
                    "permanent_memory": {"loaded_keys": ["knowledge_base"]},
                },
            ),
            StubAgent(
                "AutoChapterWriter",
                accepted_tasks=["write_chapter"],
                priority=95,
                result={"success": True, "content": "初稿内容", "word_count": 1000},
            ),
            StubAgent(
                "AutoEvaluator",
                accepted_tasks=["evaluate_chapter"],
                priority=92,
                result={
                    "success": True,
                    "evaluation": {
                        "passed": False,
                        "suggestions": ["加强冲突", "补足描写"],
                    },
                },
            ),
            StubAgent(
                "AutoPolisher",
                accepted_tasks=["polish_chapter"],
                priority=91,
                result={"success": True, "content": "润色后内容"},
            ),
            StubAgent(
                "AutoExpansion",
                accepted_tasks=["expand_content"],
                priority=80,
                result={"success": True, "content": "扩写后终稿", "word_count": 2200, "expanded": True},
            ),
        ])

        coordinator.capability_registry = registry
        task_pool = coordinator._build_chapter_autonomous_task_pool(
            chapter_num=1,
            chapter_title="第一章",
            chapter_outline_text="旧城归来",
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "",
                "chapter_outline": "旧城归来",
                "project_dir": str(coordinator.project_dir),
            },
        )

        result = await coordinator._execute_chapter_task_market(
            chapter_num=1,
            task_pool=task_pool,
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "",
                "chapter_outline": "旧城归来",
                "project_dir": str(coordinator.project_dir),
            },
            fallback_agents={},
        )

        task_snapshot = result["task_pool"]["tasks"]
        task_by_type = {item["task_type"]: item for item in task_snapshot}
        execution_results = result["results"]

        assert task_by_type["context_plan"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["content_read"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["write_chapter"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["evaluate_chapter"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["polish_chapter"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["expand_content"]["status"] == TaskStatus.COMPLETED
        assert execution_results["evaluate_chapter"]["result"]["evaluation"]["passed"] is False
        assert execution_results["polish_chapter"]["result"]["content"] == "润色后内容"
        assert execution_results["expand_content"]["result"]["content"] == "扩写后终稿"

    @pytest.mark.asyncio
    async def test_execute_chapter_task_market_skips_polish_when_evaluation_passes(self, coordinator):
        registry = AgentCapabilityRegistry()
        registry.register_many([
            StubAgent(
                "AutoContextStrategy",
                accepted_tasks=["context_plan"],
                priority=90,
                result={"success": True, "strategy": {"read_plan": [{"key": "chapter_outline"}]}},
            ),
            StubAgent(
                "AutoContentReader",
                accepted_tasks=["content_read"],
                priority=89,
                result={"success": True, "loaded_context": {"chapter_outline": "已加载大纲"}, "report": []},
            ),
            StubAgent(
                "AutoChapterWriter",
                accepted_tasks=["write_chapter"],
                priority=95,
                result={"success": True, "content": "初稿内容", "word_count": 1000},
            ),
            StubAgent(
                "AutoEvaluator",
                accepted_tasks=["evaluate_chapter"],
                priority=92,
                result={"success": True, "evaluation": {"passed": True, "suggestions": []}},
            ),
            StubAgent(
                "AutoPolisher",
                accepted_tasks=["polish_chapter"],
                priority=91,
                result={"success": True, "content": "不应执行"},
            ),
            StubAgent(
                "AutoExpansion",
                accepted_tasks=["expand_content"],
                priority=80,
                result={"success": True, "content": "扩写终稿", "word_count": 2100, "expanded": True},
            ),
        ])

        coordinator.capability_registry = registry
        task_pool = coordinator._build_chapter_autonomous_task_pool(
            chapter_num=2,
            chapter_title="第二章",
            chapter_outline_text="风雪入城",
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "上一章摘要",
                "chapter_outline": "风雪入城",
                "project_dir": str(coordinator.project_dir),
            },
        )

        result = await coordinator._execute_chapter_task_market(
            chapter_num=2,
            task_pool=task_pool,
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "上一章摘要",
                "chapter_outline": "风雪入城",
                "project_dir": str(coordinator.project_dir),
            },
            fallback_agents={},
        )

        task_snapshot = result["task_pool"]["tasks"]
        task_by_type = {item["task_type"]: item for item in task_snapshot}
        execution_results = result["results"]

        assert task_by_type["evaluate_chapter"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["polish_chapter"]["status"] == TaskStatus.ABORTED
        assert "polish_chapter" not in execution_results
        assert execution_results["expand_content"]["result"]["content"] == "扩写终稿"


    @pytest.mark.asyncio
    async def test_execute_chapter_task_market_runs_summary_orchestrate_on_tenth_chapter(self, coordinator):
        registry = AgentCapabilityRegistry()
        registry.register_many([
            StubAgent(
                "AutoContextStrategy",
                accepted_tasks=["context_plan"],
                priority=90,
                result={"success": True, "strategy": {"read_plan": [{"key": "chapter_outline"}]}},
            ),
            StubAgent(
                "AutoContentReader",
                accepted_tasks=["content_read"],
                priority=89,
                result={"success": True, "loaded_context": {"chapter_outline": "已加载大纲"}, "report": []},
            ),
            StubAgent(
                "AutoChapterWriter",
                accepted_tasks=["write_chapter"],
                priority=95,
                result={"success": True, "content": "第十章正文", "word_count": 1800},
            ),
            StubAgent(
                "AutoEvaluator",
                accepted_tasks=["evaluate_chapter"],
                priority=92,
                result={"success": True, "evaluation": {"passed": True, "suggestions": []}},
            ),
            StubAgent(
                "AutoPolisher",
                accepted_tasks=["polish_chapter"],
                priority=91,
                result={"success": True, "content": "不应执行"},
            ),
            StubAgent(
                "AutoExpansion",
                accepted_tasks=["expand_content"],
                priority=80,
                result={"success": True, "content": "第十章终稿", "word_count": 2200, "expanded": True},
            ),
            StubAgent(
                "AutoSummary",
                accepted_tasks=["summary_orchestrate"],
                priority=70,
                result={
                    "success": True,
                    "summary": "第1-10章剧情总结",
                    "summary_payload": {
                        "start_chapter": 1,
                        "end_chapter": 10,
                        "chapter_count": 10,
                        "chapters": [{"chapter_number": i, "title": f"第{i}章", "summary": f"摘要{i}"} for i in range(1, 11)],
                        "summary": "第1-10章剧情总结",
                    },
                },
            ),
        ])

        coordinator.capability_registry = registry
        previous_chapters = [
            {"number": i, "title": f"第{i}章", "content": f"前文内容{i}"}
            for i in range(1, 10)
        ]
        task_pool = coordinator._build_chapter_autonomous_task_pool(
            chapter_num=10,
            chapter_title="第十章",
            chapter_outline_text="十章收束",
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "上一章摘要",
                "chapter_outline": "十章收束",
                "chapter_title": "第十章",
                "previous_chapters": previous_chapters,
                "project_dir": str(coordinator.project_dir),
            },
        )

        result = await coordinator._execute_chapter_task_market(
            chapter_num=10,
            task_pool=task_pool,
            base_context={
                "world": {"era": "玄幻"},
                "characters": [{"name": "林渊"}],
                "previous_summary": "上一章摘要",
                "chapter_outline": "十章收束",
                "chapter_title": "第十章",
                "previous_chapters": previous_chapters,
                "project_dir": str(coordinator.project_dir),
            },
            fallback_agents={},
        )

        task_snapshot = result["task_pool"]["tasks"]
        task_by_type = {item["task_type"]: item for item in task_snapshot}
        execution_results = result["results"]

        assert task_by_type["summary_orchestrate"]["status"] == TaskStatus.COMPLETED
        assert execution_results["summary_orchestrate"]["result"]["summary"] == "第1-10章剧情总结"
        assert execution_results["summary_orchestrate"]["result"]["summary_payload"]["end_chapter"] == 10


class TestCoordinatorContractConfirmation:
    def test_initialize_task_pool_from_contract_persists_state(self, coordinator):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            source_session_id="sess-2",
            source_message="请先给我方案",
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        result = coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)

        saved_contract = coordinator.project_manager.load_project_state("creation_contract", default={})
        saved_task_pool = coordinator.project_manager.load_project_state("task_pool", default={})
        saved_trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})

        assert result["creation_contract"]["user_confirmed"] is True
        assert result["creation_contract"]["metadata"]["draft"] is False
        assert result["task_pool"]["metadata"]["contract_id"] == contract.contract_id
        assert len(result["task_pool"]["tasks"]) == len(contract.task_graph)
        assert saved_contract["contract_id"] == contract.contract_id
        assert saved_task_pool["metadata"]["source"] == "contract_confirmation"
        assert saved_trace["status"] == "initialized"
        assert saved_trace["events"][0]["type"] == "contract_confirmation"
        assert "created_at" not in saved_trace["events"][0]
        assert saved_trace["events"][0]["timestamp"]

    def test_initialize_task_pool_hydrates_semantic_dependencies(self, coordinator):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        result = coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        tasks = result["task_pool"]["tasks"]
        first_by_type = {}
        write_tasks = []
        for task in tasks:
            first_by_type.setdefault(task["task_type"], task)
            if task["task_type"] == "write_chapter":
                write_tasks.append(task)

        assert first_by_type["build_characters"]["depends_on"] == [first_by_type["build_world"]["task_id"]]
        assert set(first_by_type["build_outline"]["depends_on"]) == {
            first_by_type["build_world"]["task_id"],
            first_by_type["build_characters"]["task_id"],
        }
        assert first_by_type["chapter_settings"]["depends_on"] == [first_by_type["build_outline"]["task_id"]]
        assert all(task["depends_on"] == [first_by_type["chapter_settings"]["task_id"]] for task in write_tasks)

    def test_initialize_task_pool_respects_disabled_chapter_settings_pause(self, coordinator):
        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=1,
            user_confirmed=False,
        )
        contract.metadata["pause_after_chapter_settings"] = False
        contract.task_graph = build_default_task_graph(contract)

        result = coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        chapter_settings_task = next(
            item for item in result["task_pool"]["tasks"]
            if item["task_type"] == "chapter_settings"
        )

        assert chapter_settings_task["review_required"] is False
        assert "stop_on_review_required" not in chapter_settings_task["metadata"]


    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_runs_world_and_outline_in_formal_task_pool(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        character_agent = build_character_stub()
        registry.register_many([world_agent, character_agent, outline_agent])
        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        init_result = coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=3)

        task_by_type = {
            item["task_type"]: item
            for item in execute_result["task_pool"]["tasks"]
        }
        trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        event_types = [item["type"] for item in trace.get("events", [])]

        assert init_result["task_pool"]["tasks"]
        assert task_by_type["build_world"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_world"]["result_ref"] == "worldbuilding.json"
        assert task_by_type["build_characters"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_characters"]["result_ref"] == "characters.json"
        assert task_by_type["build_outline"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_outline"]["result_ref"] == "outline.json"
        assert task_by_type["write_chapter"]["status"] == TaskStatus.PENDING
        assert execute_result["stopped_on_task_type"] == ""
        assert coordinator.context_manager.get("world", {})["world_name"] == "玄荒界"
        assert coordinator.context_manager.get("outline", {})["title"] == "归墟录"
        assert "task_started" in event_types
        assert "task_completed" in event_types
        assert event_types[-1] == "project_ready_execution_cycle"

    @pytest.mark.asyncio
    async def test_project_ready_world_task_fails_without_meaningful_artifact(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={
                "success": True,
                "world": {
                    "status": "missing_info",
                    "missing_info": ["novel_type"],
                },
            },
        )
        registry.register(world_agent)
        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent

        contract = build_default_creation_contract(
            novel_type="",
            theme="",
            requirements="",
            protagonist="",
            plot_idea="",
            volume_count=1,
            chapters_per_volume=1,
            user_confirmed=True,
        )
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=1)
        world_task = next(
            item for item in execute_result["task_pool"]["tasks"]
            if item["task_type"] == "build_world"
        )

        assert world_task["status"] == TaskStatus.FAILED
        assert not world_task["result_ref"]
        assert "novel_type" in world_task["metadata"]["error"]
        assert execute_result["stop_reason"] == "task_failed"
        assert coordinator.project_manager.load_project_data("worldbuilding") == []

    @pytest.mark.asyncio
    async def test_project_ready_tasks_inherit_discussion_context_from_contract(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        character_agent = build_character_stub()
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        registry.register_many([world_agent, character_agent, outline_agent])
        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="黑暗修仙",
            requirements="不要低俗，前期压抑",
            protagonist="林渡",
            plot_idea="宗门覆灭后的复仇与重建",
            volume_count=1,
            chapters_per_volume=1,
            user_confirmed=True,
        )
        contract.scope["discussion_context"] = "用户明确要求合欢宗元素必须危险克制，不要低俗；前期不要升级太快。"
        contract.task_graph = build_default_task_graph(contract)
        for task in contract.task_graph:
            task.inputs.pop("discussion_context", None)
            task.inputs.pop("recent_discussion", None)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        await coordinator.execute_project_ready_tasks(max_tasks=3)

        assert "合欢宗元素" in world_agent.calls[0]["input_data"]["discussion_context"]
        assert "合欢宗元素" in character_agent.calls[0]["input_data"]["recent_discussion"]
        assert "合欢宗元素" in outline_agent.calls[0]["input_data"]["discussion_context"]

    @pytest.mark.asyncio
    async def test_zero_start_creation_pipeline_keeps_planning_artifacts_consistent(self, coordinator):
        """Regression: fresh creation must not mix character cards, global outline,
        volume planning, chapter settings, and eventlines into the same content."""

        world_payload = {
            "world_name": "瑞安朝",
            "world_type": "古代甜宠",
            "geography": {"京城": "贵族府邸与朝堂所在"},
            "factions": [
                {"name": "苏府", "description": "女主娘家"},
                {"name": "镇北王府", "description": "男主府邸"},
            ],
            "rules": ["男女主无背叛、无长误会", "宅门冲突两章内化解"],
            "story_hooks": ["赐婚先婚后爱", "嫡姐挑拨", "朝堂弹劾"],
        }
        characters_payload = [
            {
                "name": "苏晚宁",
                "role": "女主角",
                "identity": "苏府庶女，奉旨嫁入镇北王府",
                "description": "外柔内刚，擅长理家与察言观色。",
                "personality": ["温和", "清醒", "有主见"],
                "goals": ["在王府站稳脚跟", "与萧景珩建立真实信任"],
                "relationships": {"萧景珩": "丈夫", "苏明珠": "嫡姐与挑拨者"},
            },
            {
                "name": "萧景珩",
                "role": "男主角",
                "identity": "镇北王世子",
                "description": "外冷内热，因军功被朝堂忌惮。",
                "personality": ["克制", "护短", "专一"],
                "goals": ["守住边军清名", "保护苏晚宁"],
                "relationships": {"苏晚宁": "妻子", "苏明珠": "外部干扰"},
            },
        ]
        global_outline = (
            "书名：《春庭雪》\n简介：苏晚宁奉旨嫁入镇北王府，与萧景珩先婚后爱。\n"
            "故事梗概：两人从试探到互信，在嫡姐挑拨和朝堂弹劾中并肩破局。\n"
            "世界或时代规则：瑞安朝重门第与军功，宅门与朝堂互相牵动。\n"
            "中心思想：被安排的婚姻也能靠尊重和信任长出真心。\n"
            "矛盾冲突：苏明珠挑拨、御史弹劾、王府内外对庶女身份的偏见。\n"
            "前期剧情方向：新婚试探、回门风波、王府立足。\n"
            "叙事节奏：甜宠日常与小风波交替，误会不过章。\n"
            "小说卖点：外冷内热世子与外柔内刚庶女的双向守护。\n"
            "角色关系与成长方向：苏晚宁从谨慎自保到主动并肩，萧景珩从克制疏离到公开护妻。"
        )
        outline_payload = {
            "title": "春庭雪",
            "intro": "庶女与世子先婚后爱。",
            "story_synopsis": "苏晚宁与萧景珩在宅门与朝堂小风波中建立信任。",
            "global_outline": global_outline,
            "theme": "信任与尊重",
            "main_conflict": "两人需要在身份偏见、嫡姐挑拨和朝堂弹劾中守住婚姻。",
            "selling_points": "甜宠、护妻、宅门小反击。",
            "ending_direction": "弹劾化解，夫妻圆满相守。",
            "plot_threads": [
                {
                    "id": "main",
                    "title": "先婚后爱，相守一生",
                    "objective": "从奉旨成婚到公开互信",
                    "scope": "全书",
                },
                {
                    "id": "sister_scheme",
                    "title": "嫡姐挑拨线",
                    "objective": "化解苏明珠挑拨并反向稳固夫妻信任",
                    "scope": "第一卷",
                },
            ],
            "volumes": [
                {
                    "volume_number": 1,
                    "volume_title": "新婚试探",
                    "volume_summary": "新婚夜与回门风波建立信任基础。",
                    "core_conflict": "苏晚宁庶女身份被轻视，苏明珠趁机挑拨。",
                    "protagonist_growth": "苏晚宁从谨慎自保到敢于表达需求。",
                    "volume_climax": "回门宴上萧景珩当众护妻。",
                    "key_events": ["新婚夜分寸相处", "王府理家初显", "回门宴联手反击"],
                    "foreshadowing": "御史台暗中收集镇北王府军功旧案。",
                },
                {
                    "volume_number": 2,
                    "volume_title": "并肩破局",
                    "volume_summary": "朝堂弹劾升温，夫妻共同查证旧案。",
                    "core_conflict": "御史弹劾与苏府旧怨合流。",
                    "protagonist_growth": "苏晚宁从被保护者成长为破局同盟。",
                    "volume_climax": "夫妻面圣呈证，弹劾者反受惩。",
                    "key_events": ["旧账线索浮出", "夫妻分头查证", "金殿呈证"],
                    "foreshadowing": "边军旧账中的空名册在终局回收。",
                },
            ],
            "notes": "章纲阶段只能展开各卷关键事件，不能改名或改关系。",
        }
        chapter_settings_payload = [
            {
                "chapter_number": 1,
                "name": "第1章 新婚夜",
                "description": "苏晚宁与萧景珩新婚夜分寸相处。",
                "chapter_goal": "建立先婚后爱的初始距离与体贴细节。",
                "key_event": "萧景珩主动给苏晚宁留出安全边界。",
                "ending_hook": "苏晚宁发现王府账册有异常空项。",
            },
            {
                "chapter_number": 2,
                "name": "第2章 回门风波",
                "description": "回门宴上苏明珠挑拨失败。",
                "chapter_goal": "让夫妻第一次联手应对娘家压力。",
                "key_event": "萧景珩当众维护苏晚宁。",
                "ending_hook": "御史台的人在宴后与苏府管事密谈。",
            },
            {
                "chapter_number": 3,
                "name": "第3章 金殿呈证",
                "description": "夫妻查证后面圣破局。",
                "chapter_goal": "回收朝堂弹劾线并完成关系公开。",
                "key_event": "苏晚宁呈上空名册证据。",
                "ending_hook": "萧景珩牵起她的手回府。",
            },
        ]

        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": world_payload},
        )
        character_agent = StubAgent(
            "AutoCharacterBuilder",
            accepted_tasks=["build_characters"],
            priority=98,
            result={"success": True, "characters": characters_payload},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=97,
            result={"success": True, "outline": outline_payload},
        )
        chapter_settings_agent = StubAgent(
            "AutoChapterSettingBuilder",
            accepted_tasks=["chapter_settings"],
            priority=96,
            result={"success": True, "rows": chapter_settings_payload},
        )
        registry.register_many([world_agent, character_agent, outline_agent, chapter_settings_agent])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent
        coordinator.chapter_setting_builder = chapter_settings_agent

        contract = build_default_creation_contract(
            novel_type="古代甜宠",
            theme="先婚后爱、互相信任",
            requirements="无背叛、无长误会、甜宠为主",
            protagonist="苏晚宁、萧景珩",
            plot_idea="奉旨成婚后在宅门与朝堂风波中相知相守",
            volume_count=2,
            chapters_per_volume=3,
            user_confirmed=True,
        )
        contract.metadata["pause_after_chapter_settings"] = True
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=4, max_chapter_tasks=0)

        assert execute_result["stop_reason"] == "review_required"
        assert execute_result["stopped_on_task_type"] == "chapter_settings"

        saved_world = coordinator.project_manager.load_project_data("worldbuilding")
        saved_characters = coordinator.project_manager.load_project_data("characters")
        saved_outline = coordinator.project_manager.load_project_data("outline")
        saved_eventlines = coordinator.project_manager.load_project_data("eventlines")
        saved_chapter_settings = coordinator.project_manager.load_project_data("chapter_settings")

        assert saved_world["world"]["world_name"] == "瑞安朝"
        assert {row["name"] for row in saved_characters} == {"苏晚宁", "萧景珩"}
        assert all("林渊" not in json.dumps(row, ensure_ascii=False) for row in saved_characters)

        assert isinstance(saved_outline, list) and len(saved_outline) == 1
        outline_row = saved_outline[0]
        assert outline_row["title"] == "主线大纲"
        assert "作者：AI助手" not in outline_row["global_outline"]
        assert "第1卷：新婚试探" in outline_row["volume_plan"]
        assert outline_row["global_outline"] != outline_row["volume_plan"]
        assert not outline_row.get("chapter_number")
        assert "chapters" not in json.dumps(outline_row.get("volumes"), ensure_ascii=False)

        eventline_names = {row.get("name") for row in saved_eventlines if isinstance(row, dict)}
        assert "先婚后爱，相守一生" in eventline_names
        assert "嫡姐挑拨线" in eventline_names
        assert any(row.get("source_scope") == "volume_foreshadowing" for row in saved_eventlines)

        assert [row["chapter_number"] for row in saved_chapter_settings] == [1, 2, 3]
        assert "苏晚宁" in chapter_settings_agent.calls[0]["input_data"]["characters"][0]["name"]
        assert "先婚后爱，相守一生" in json.dumps(
            chapter_settings_agent.calls[0]["input_data"]["eventlines"],
            ensure_ascii=False,
        )
        assert "全书/分卷概览" not in saved_chapter_settings[0]["chapter_goal"]

    @pytest.mark.asyncio
    async def test_project_ready_character_task_does_not_use_unregistered_real_fallback(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        registry.register_many([world_agent, outline_agent])
        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.outliner = outline_agent
        coordinator.character_builder.execute = AsyncMock(
            return_value={"success": True, "characters": [{"name": "不应执行"}]}
        )

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=3)
        task_by_type = {
            item["task_type"]: item
            for item in execute_result["task_pool"]["tasks"]
        }

        assert task_by_type["build_world"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_characters"]["status"] == TaskStatus.FAILED
        assert task_by_type["build_outline"]["status"] == TaskStatus.PENDING
        assert execute_result["stop_reason"] == "task_failed"
        assert execute_result["stopped_on_task_type"] == "build_characters"
        coordinator.character_builder.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_stops_on_fallback_and_persists_runtime_metadata(self, coordinator):
        registry = AgentCapabilityRegistry()
        failing_world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            raise_error=True,
        )
        fallback_world_agent = StubAgent(
            "FallbackWorldbuilder",
            accepted_tasks=["build_world"],
            priority=10,
            result={"success": True, "world": {"world_name": "回退世界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        registry.register_many([failing_world_agent, fallback_world_agent, outline_agent])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = fallback_world_agent
        coordinator.outliner = outline_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=4)

        task_pool = execute_result["task_pool"]
        project_ready_execution = task_pool["metadata"]["project_ready_execution"]
        trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        event_types = [item["type"] for item in trace.get("events", [])]

        assert execute_result["stop_reason"] == "fallback_triggered"
        assert execute_result["stopped_on_task_type"] == "build_world"
        assert project_ready_execution["stop_reason"] == "fallback_triggered"
        assert project_ready_execution["stopped_on_task_type"] == "build_world"
        assert event_types[-1] == "project_ready_execution_cycle"

    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_stops_on_review_required_when_task_opt_in_enabled(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        character_agent = build_character_stub()
        registry.register_many([world_agent, character_agent, outline_agent])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)
        contract.task_graph[2].metadata["stop_on_review_required"] = True

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=4)

        assert execute_result["stop_reason"] == "review_required"
        assert execute_result["stopped_on_task_type"] == "build_outline"
        assert execute_result["task_pool"]["metadata"]["project_ready_execution"]["stop_reason"] == "review_required"

    @pytest.mark.asyncio
    async def test_get_status_exposes_project_ready_execution_snapshot(self, coordinator):
        runtime_pool = TaskPool()
        runtime_pool.metadata["project_ready_execution"] = {
            "stop_reason": "max_chapter_tasks_reached",
            "stopped_on_task_type": "write_chapter",
            "chapter_tasks_executed": 2,
        }
        coordinator.project_manager.save_project_state("task_pool", runtime_pool.to_dict())
        coordinator.project_manager.save_project_state("collab_execution_trace", {"events": []})
        coordinator.project_manager.save_project_state("creation_contract", {"contract_id": "contract-1"})

        with patch("novel_agent.web.routes.novel.get_coordinator", return_value=coordinator):
            response = await get_status()

        assert isinstance(response, JSONResponse)
        payload = json.loads(response.body.decode("utf-8"))
        assert payload["project_ready_execution"]["stop_reason"] == "max_chapter_tasks_reached"
        assert payload["project_ready_execution"]["stopped_on_task_type"] == "write_chapter"
        assert payload["project_ready_execution"]["chapter_tasks_executed"] == 2

    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_runs_first_write_chapter_in_formal_task_pool(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        character_agent = build_character_stub()
        chapter_settings_agent = build_chapter_settings_stub(total_chapters=2)
        context_agent = StubAgent(
            "AutoContextStrategy",
            accepted_tasks=["context_plan"],
            priority=90,
            result={"success": True, "strategy": {"read_plan": [{"key": "chapter_outline"}]}},
        )
        reader_agent = StubAgent(
            "AutoContentReader",
            accepted_tasks=["content_read"],
            priority=89,
            result={"success": True, "loaded_context": {"chapter_outline": "旧城归来"}, "report": []},
        )
        chapter_agent = StubAgent(
            "AutoChapterWriter",
            accepted_tasks=["write_chapter"],
            priority=99,
            result={"success": True, "content": "第一章正式正文", "word_count": 1800},
        )
        evaluator_agent = StubAgent(
            "AutoEvaluator",
            accepted_tasks=["evaluate_chapter"],
            priority=92,
            result={"success": True, "evaluation": {"passed": True, "suggestions": []}},
        )
        polisher_agent = StubAgent(
            "AutoPolisher",
            accepted_tasks=["polish_chapter"],
            priority=91,
            result={"success": True, "content": "不应执行"},
        )
        expansion_agent = StubAgent(
            "AutoExpansion",
            accepted_tasks=["expand_content"],
            priority=80,
            result={"success": True, "content": "第一章正式正文", "word_count": 2200, "expanded": True},
        )
        file_naming_agent = StubAgent(
            "AutoFileNaming",
            accepted_tasks=[],
            priority=50,
            result={"success": True, "filename": "第1章-第一章-2200字.md", "word_count": 2200},
        )
        registry.register_many([
            world_agent,
            character_agent,
            outline_agent,
            chapter_settings_agent,
            context_agent,
            reader_agent,
            chapter_agent,
            evaluator_agent,
            polisher_agent,
            expansion_agent,
        ])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent
        coordinator.chapter_setting_builder = chapter_settings_agent
        coordinator.context_strategy = context_agent
        coordinator.content_reader = reader_agent
        coordinator.chapter_writer = chapter_agent
        coordinator.evaluator = evaluator_agent
        coordinator.polisher = polisher_agent
        coordinator.content_expansion = expansion_agent
        coordinator.file_naming = file_naming_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=2,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        review_result = await coordinator.execute_project_ready_tasks(max_tasks=5)

        assert review_result["stop_reason"] == "review_required"
        assert review_result["stopped_on_task_type"] == "chapter_settings"

        task_by_type = {}
        for item in review_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)
        assert task_by_type["chapter_settings"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["write_chapter"][0]["status"] == TaskStatus.PENDING
        assert chapter_agent.calls == []

        blocked_result = await coordinator.execute_project_ready_tasks(max_tasks=5, max_chapter_tasks=1)
        blocked_task_by_type = {}
        for item in blocked_result["task_pool"]["tasks"]:
            blocked_task_by_type.setdefault(item["task_type"], []).append(item)

        assert blocked_result["stop_reason"] == "chapter_settings_review_required"
        assert blocked_result["stopped_on_task_type"] == "write_chapter"
        assert blocked_task_by_type["write_chapter"][0]["status"] == TaskStatus.BLOCKED
        assert coordinator.project_manager.load_project_data("chapters") == []
        assert not any(coordinator.project_manager.get_chapters_dir().glob("*.md"))
        assert chapter_agent.calls == []

        coordinator.approve_chapter_settings_review()

        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=5, max_chapter_tasks=1)

        task_by_type = {}
        for item in execute_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)

        first_write_task = task_by_type["write_chapter"][0]
        outline_rows = coordinator.project_manager.load_project_data("outline")
        chapter_path = Path(first_write_task["result_ref"])

        assert task_by_type["build_world"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_characters"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_outline"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["chapter_settings"][0]["status"] == TaskStatus.COMPLETED
        assert first_write_task["status"] == TaskStatus.COMPLETED
        assert first_write_task["assigned_agent"] == "ChapterWriter"
        assert first_write_task["result_ref"]
        assert chapter_path.exists()
        assert chapter_path.read_text(encoding="utf-8") == "第一章正式正文"
        assert isinstance(outline_rows, list) and outline_rows[0]["title"] == "主线大纲"
        assert not outline_rows[0].get("chapter_number")
        saved_settings = coordinator.project_manager.load_project_data("chapter_settings")
        assert saved_settings[0]["chapter_goal"] == "目标1"
        assert "目标1" in chapter_agent.calls[0]["context"]["chapter_outline"]
        assert execute_result["stopped_on_task_type"] == "write_chapter"
        assert execute_result["chapter_tasks_executed"] == 1
        assert execute_result["stop_reason"] == "max_chapter_tasks_reached"
        assert execute_result["project_ready_execution"]["stop_reason"] == "max_chapter_tasks_reached"
        assert execute_result["project_ready_execution"]["chapter_tasks_executed"] == 1
        assert execute_result["task_pool"]["metadata"]["project_ready_execution"]["stop_reason"] == "max_chapter_tasks_reached"
        assert not (get_data_dir() / "projects" / coordinator.project_manager.current_project_id / "aux_memory").exists()

    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_runs_multiple_write_chapters_until_chapter_limit(self, coordinator):
        registry = AgentCapabilityRegistry()
        world_agent = StubAgent(
            "AutoWorldbuilder",
            accepted_tasks=["build_world"],
            priority=100,
            result={"success": True, "world": {"world_name": "玄荒界"}},
        )
        outline_agent = StubAgent(
            "AutoOutliner",
            accepted_tasks=["build_outline"],
            priority=95,
            result={"success": True, "outline": build_valid_outline_payload()},
        )
        character_agent = build_character_stub()
        chapter_settings_agent = build_chapter_settings_stub(total_chapters=3)
        context_agent = StubAgent(
            "AutoContextStrategy",
            accepted_tasks=["context_plan"],
            priority=90,
            result={"success": True, "strategy": {"read_plan": [{"key": "chapter_outline"}]}},
        )
        reader_agent = StubAgent(
            "AutoContentReader",
            accepted_tasks=["content_read"],
            priority=89,
            result={"success": True, "loaded_context": {"chapter_outline": "已加载大纲"}, "report": []},
        )
        chapter_agent = StubAgent(
            "AutoChapterWriter",
            accepted_tasks=["write_chapter"],
            priority=99,
            result={"success": True, "content": "统一章节正文", "word_count": 1800},
        )
        evaluator_agent = StubAgent(
            "AutoEvaluator",
            accepted_tasks=["evaluate_chapter"],
            priority=92,
            result={"success": True, "evaluation": {"passed": True, "suggestions": []}},
        )
        polisher_agent = StubAgent(
            "AutoPolisher",
            accepted_tasks=["polish_chapter"],
            priority=91,
            result={"success": True, "content": "不应执行"},
        )
        expansion_agent = StubAgent(
            "AutoExpansion",
            accepted_tasks=["expand_content"],
            priority=80,
            result={"success": True, "content": "统一章节正文", "word_count": 2200, "expanded": True},
        )
        file_naming_agent = StubAgent(
            "AutoFileNaming",
            accepted_tasks=[],
            priority=50,
            result={"success": True, "filename": "章节文件.md", "word_count": 2200},
        )
        registry.register_many([
            world_agent,
            character_agent,
            outline_agent,
            chapter_settings_agent,
            context_agent,
            reader_agent,
            chapter_agent,
            evaluator_agent,
            polisher_agent,
            expansion_agent,
        ])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.character_builder = character_agent
        coordinator.outliner = outline_agent
        coordinator.chapter_setting_builder = chapter_settings_agent
        coordinator.context_strategy = context_agent
        coordinator.content_reader = reader_agent
        coordinator.chapter_writer = chapter_agent
        coordinator.evaluator = evaluator_agent
        coordinator.polisher = polisher_agent
        coordinator.content_expansion = expansion_agent
        coordinator.file_naming = file_naming_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=3,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        review_result = await coordinator.execute_project_ready_tasks(
            max_tasks=7,
            max_chapter_tasks=2,
        )

        task_by_type = {}
        for item in review_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)
        assert review_result["stop_reason"] == "review_required"
        assert review_result["stopped_on_task_type"] == "chapter_settings"
        assert task_by_type["chapter_settings"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["write_chapter"][0]["status"] == TaskStatus.PENDING

        coordinator.approve_chapter_settings_review()
        execute_result = await coordinator.execute_project_ready_tasks(
            max_tasks=7,
            max_chapter_tasks=2,
        )

        task_by_type = {}
        for item in execute_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)

        write_tasks = task_by_type["write_chapter"]
        outline_rows = coordinator.project_manager.load_project_data("outline")
        chapter_rows = coordinator.project_manager.load_project_data("chapters")

        assert task_by_type["build_world"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_characters"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_outline"][0]["status"] == TaskStatus.COMPLETED
        assert write_tasks[0]["status"] == TaskStatus.COMPLETED
        assert write_tasks[1]["status"] == TaskStatus.COMPLETED
        assert write_tasks[2]["status"] == TaskStatus.PENDING
        assert execute_result["chapter_tasks_executed"] == 2
        assert execute_result["stopped_on_task_type"] == "write_chapter"
        assert execute_result["stop_reason"] == "max_chapter_tasks_reached"
        assert execute_result["project_ready_execution"]["stop_reason"] == "max_chapter_tasks_reached"
        assert execute_result["task_pool"]["metadata"]["project_ready_execution"]["chapter_tasks_executed"] == 2
        assert isinstance(outline_rows, list)
        assert outline_rows[0]["title"] == "主线大纲"
        assert not outline_rows[0].get("chapter_number")
        assert isinstance(chapter_rows, list)
        assert len(chapter_rows) == 2
        assert chapter_rows[0]["content"] == "统一章节正文"
        assert chapter_rows[1]["content"] == "统一章节正文"

    @pytest.mark.asyncio
    async def test_execute_project_ready_tasks_runs_project_stage_summary_and_persists_result(self, coordinator):
        registry = AgentCapabilityRegistry()
        summary_agent = StubAgent(
            "AutoSummary",
            accepted_tasks=["summary_orchestrate"],
            priority=90,
            result={
                "success": True,
                "summary": "第1-10章剧情总结\n- 第10章《终局》：统一阶段总结",
                "summary_payload": {
                    "start_chapter": 1,
                    "end_chapter": 10,
                    "chapter_count": 10,
                    "chapters": [{"chapter_number": i, "title": f"第{i}章", "summary": f"摘要{i}"} for i in range(1, 11)],
                    "summary": "第1-10章剧情总结\n- 第10章《终局》：统一阶段总结",
                },
            },
        )
        registry.register(summary_agent)

        coordinator.capability_registry = registry
        coordinator.summary_orchestrator = summary_agent

        contract = build_default_creation_contract(
            novel_type="玄幻",
            theme="复仇成长",
            requirements="压抑递进",
            protagonist="林渊",
            plot_idea="旧城归来",
            volume_count=1,
            chapters_per_volume=10,
            user_confirmed=False,
        )
        contract.task_graph = build_default_task_graph(contract)

        init_result = coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        runtime_pool = TaskPool.from_dict(init_result["task_pool"])
        for task in runtime_pool.list_tasks():
            if task.task_type == "build_world":
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="Worldbuilder",
                    result_ref="worldbuilding.json",
                )
            elif task.task_type == "build_characters":
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="CharacterBuilder",
                    result_ref="characters.json",
                )
            elif task.task_type == "build_outline":
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="Outliner",
                    result_ref="outline.json",
                )
            elif task.task_type == "chapter_settings":
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="ChapterSettingBuilder",
                    result_ref="chapter_settings.json",
                )
            elif task.task_type == "write_chapter":
                chapter_number = int((task.inputs or {}).get("chapter_number") or 0)
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="ChapterWriter",
                    result_ref=f"chapters/{chapter_number:03d}.md",
                )
        coordinator.project_manager.save_project_state("task_pool", runtime_pool.to_dict())

        outline_rows = []
        for chapter_number in range(1, 11):
            outline_rows.append({
                "chapter_number": chapter_number,
                "title": f"第{chapter_number}章",
                "summary": f"摘要{chapter_number}",
                "content": f"第{chapter_number}章正文",
            })
        coordinator.project_manager.save_project_data("outline", outline_rows)

        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=2, max_chapter_tasks=0)

        task_by_type = {}
        for item in execute_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)

        summary_task = task_by_type["summary_orchestrate"][0]
        stage_summaries = coordinator.project_manager.load_project_state("collab_stage_summaries", default=[])

        assert summary_task["status"] == TaskStatus.COMPLETED
        assert summary_task["assigned_agent"] == "AutoSummary"
        assert summary_task["result_ref"].endswith("第1-10章-剧情总结.md")
        assert Path(summary_task["result_ref"]).exists()
        assert "第1-10章剧情总结" in Path(summary_task["result_ref"]).read_text(encoding="utf-8")
        assert isinstance(stage_summaries, list)
        assert stage_summaries[-1]["end_chapter"] == 10
        assert execute_result["stop_reason"] == ""

class TestCommunicatorMessageBusFallback:
    @pytest.mark.asyncio
    async def test_request_outline_uses_build_outline_task_type_on_message_bus_fallback(self, mock_model_config):
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config

            from novel_agent.agents.communicator import CommunicatorAgent

            agent = CommunicatorAgent(router_agent=None)
            captured = {}

            async def fake_send_task_stream(receiver, task_type, task_data, context=None, timeout=0):
                captured["receiver"] = receiver
                captured["task_type"] = task_type
                captured["task_data"] = dict(task_data or {})
                captured["context"] = dict(context or {})
                yield {
                    "msg_type": "task_completed",
                    "payload": {"result": {"outline": {"title": "测试大纲"}}},
                }

            agent.send_task_stream = fake_send_task_stream

            result = await agent.request_outline(
                world={"world_name": "玄荒界"},
                protagonist="林渊",
                plot_idea="旧城归来",
                volume_count=1,
                chapters_per_volume=3,
            )

            assert captured["receiver"] == "Outliner"
            assert captured["task_type"] == "build_outline"
            assert captured["task_data"]["protagonist"] == "林渊"
            assert captured["context"]["world"]["world_name"] == "玄荒界"
            assert result["outline"]["title"] == "测试大纲"


class TestRouterContractDraft:
    @pytest.mark.asyncio
    async def test_router_creation_requirements_semantic_fallback_handles_mixed_chinese_request(self, mock_model_config):
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config

            from novel_agent.agents.router_agent import RouterAgent

            router = RouterAgent()
            message = "我想写古代甜宠题材的小说，篇幅5w字左右，主角叫天齐，女主角你随便帮我想个吧"
            requirements = await router._build_creation_requirements_async(
                {"creation_requirements": {"novel_type": "言情", "plot_idea": message}},
                message,
            )

        assert requirements["novel_type"] == "古代言情"
        assert requirements["theme"] == "古代甜宠"
        assert requirements["protagonist"] == "天齐"
        assert requirements["target_word_count"] == 50000
        assert requirements["chapters_per_volume"] >= 10
        assert "女主角由助手构思" in requirements["requirements"]
        assert requirements["ai_autonomy_requested"] is True
        assert requirements["plot_idea"] != requirements["source_message"]

    @pytest.mark.asyncio
    async def test_router_contract_draft_keeps_unspecified_plot_empty_for_broad_brief(self, mock_model_config):
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config

            from novel_agent.agents.router_agent import RouterAgent

            router = RouterAgent()
            message = "我想写一本古代的甜宠题材小说，篇幅在5万字左右。其他的信息你帮我完善就行"
            requirements = await router._build_creation_requirements_async({}, message)

        assert requirements["novel_type"] == "古代言情"
        assert requirements["theme"] == "古代甜宠"
        assert requirements["target_word_count"] == 50000
        assert requirements["chapters_per_volume"] >= 10
        assert "篇幅约50000字" in requirements["requirements"]
        assert requirements["ai_autonomy_requested"] is True
        assert requirements["plot_idea"] == ""

    @pytest.mark.asyncio
    async def test_creation_contract_passes_ai_autonomy_to_character_task(self, mock_model_config):
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config

            from novel_agent.agents.router_agent import RouterAgent

            router = RouterAgent()
            message = "我想写一本古代甜宠小说，篇幅5w字，其他的你随便帮我安排"
            requirements = await router._build_creation_requirements_async({}, message)
            contract_payload = router._build_creation_contract_payload(
                requirements,
                context={"session_id": "copilot"},
                user_confirmed=False,
            )

        assert contract_payload["scope"]["ai_autonomy_requested"] is True
        character_task = next(
            task for task in contract_payload["task_graph"]
            if task["task_type"] == "build_characters"
        )
        assert character_task["inputs"]["ai_autonomy_requested"] is True
        assert character_task["inputs"]["request_mode"] == "autonomous_draft"
        assert "用户已授权助手自主安排" in character_task["inputs"]["character_request"]

    @pytest.mark.asyncio
    async def test_router_create_novel_returns_draft_contract_confirmation_payload(self, mock_model_config):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            project_manager = ProjectManager(data_dir=temp_path / "data")
            project = project_manager.create_project("测试项目", "隔离项目")
            project_manager.switch_project(project.id)
            with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
                mock_manager.return_value.get_effective_config.return_value = mock_model_config

                from novel_agent.workflow.coordinator import NovelCoordinator
                from novel_agent.agents.router_agent import RouterAgent

                with (
                    patch("novel_agent.project_manager.get_project_manager", return_value=project_manager),
                    patch("novel_agent.agents.router_agent.get_project_manager", return_value=project_manager, create=True),
                    patch("novel_agent.workflow.coordinator.get_project_manager", return_value=project_manager),
                ):
                    coordinator = NovelCoordinator(project_dir=project_manager._get_project_dir(project.id))
                    coordinator.switch_to_project(project.id)
                    router = RouterAgent(coordinator=coordinator)

                    result = await router.route_and_respond(
                        "我想写一部玄幻复仇成长小说，主角林渊，从旧城归来开始。",
                        context={
                            "session_id": "copilot",
                            "auto_execute": False,
                            "creation_requirements": {
                                "novel_type": "玄幻",
                                "theme": "复仇成长",
                                "requirements": "压抑递进",
                                "protagonist": "林渊",
                                "plot_idea": "旧城归来",
                                "volume_count": 1,
                                "chapters_per_volume": 3,
                            },
                            "conversation_history": [
                                {"role": "user", "content": "我想写一部玄幻复仇成长小说"},
                                {"role": "assistant", "content": "主角和整体风格有什么偏好吗？"},
                                {"role": "user", "content": "主角叫林渊，压抑递进，从旧城归来开始。"},
                            ],
                        },
                    )

                delegated = result["delegated_result"]
                params = delegated["params"]
                contract_payload = params["creation_contract"]

                assert delegated["action"] == "confirm_creation_contract"
                assert delegated["requires_confirmation"] is True
                assert params["contract_status"] == "draft"
                assert contract_payload["user_confirmed"] is False
                assert contract_payload["metadata"]["draft"] is True
                assert len(params["task_graph_draft"]) == len(contract_payload["task_graph"])
                assert "创作合同草案" in delegated["response"]
