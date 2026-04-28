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
from novel_agent.workflow.contracts import (
    CreationContract,
    ExecutionPolicy,
    TaskDefinition,
    TaskDependency,
    build_default_creation_contract,
    build_default_task_graph,
)
from novel_agent.workflow.coordinator import NovelCoordinator
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
        if self._raise_error:
            raise RuntimeError(f"{self.name} failed")
        return dict(self._result)


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
        with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            instance = NovelCoordinator(project_dir=Path(temp_dir))
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
        assert len(task_graph) == 8
        assert task_graph[0].task_type == "build_world"
        assert task_graph[1].task_type == "build_outline"
        assert task_graph[2].task_type == "write_chapter"
        assert task_graph[-1].inputs["chapter_number"] == 6

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

        removed = registry.unregister("SnapshotAgent")
        assert removed is True
        assert registry.get_agent("SnapshotAgent") is None
        assert registry.list_agents() == []


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
            result={"success": True, "outline": {"title": "归墟录", "chapters": [{"title": "第一章", "summary": "旧城归来"}]}},
        )
        registry.register_many([world_agent, outline_agent])
        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
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
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=2)

        task_by_type = {
            item["task_type"]: item
            for item in execute_result["task_pool"]["tasks"]
        }
        trace = coordinator.project_manager.load_project_state("collab_execution_trace", default={})
        event_types = [item["type"] for item in trace.get("events", [])]

        assert init_result["task_pool"]["tasks"]
        assert task_by_type["build_world"]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_world"]["result_ref"] == "worldbuilding.json"
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
            result={"success": True, "outline": {"title": "归墟录", "chapters": [{"title": "第一章", "summary": "旧城归来"}]}},
        )
        registry.register_many([failing_world_agent, outline_agent])

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
            result={"success": True, "outline": {"title": "归墟录", "chapters": [{"title": "第一章", "summary": "旧城归来"}]}},
        )
        registry.register_many([world_agent, outline_agent])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
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
        contract.task_graph[1].metadata["stop_on_review_required"] = True

        coordinator.initialize_task_pool_from_contract(contract.to_dict(), approved=True)
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=3)

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
            result={
                "success": True,
                "outline": {
                    "title": "归墟录",
                    "chapters": [
                        {"title": "第一章", "summary": "旧城归来"},
                        {"title": "第二章", "summary": "风雪入城"},
                    ],
                },
            },
        )
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
            outline_agent,
            context_agent,
            reader_agent,
            chapter_agent,
            evaluator_agent,
            polisher_agent,
            expansion_agent,
        ])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.outliner = outline_agent
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
        execute_result = await coordinator.execute_project_ready_tasks(max_tasks=3)

        task_by_type = {}
        for item in execute_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)

        first_write_task = task_by_type["write_chapter"][0]
        outline_rows = coordinator.project_manager.load_project_data("outline")
        chapter_path = Path(first_write_task["result_ref"])

        assert task_by_type["build_world"][0]["status"] == TaskStatus.COMPLETED
        assert task_by_type["build_outline"][0]["status"] == TaskStatus.COMPLETED
        assert first_write_task["status"] == TaskStatus.COMPLETED
        assert first_write_task["assigned_agent"] == "ChapterWriter"
        assert first_write_task["result_ref"]
        assert chapter_path.exists()
        assert chapter_path.read_text(encoding="utf-8") == "第一章正式正文"
        assert isinstance(outline_rows, list) and outline_rows[0]["content"] == "第一章正式正文"
        assert execute_result["stopped_on_task_type"] == ""
        assert execute_result["chapter_tasks_executed"] == 1
        assert execute_result["stop_reason"] == "max_tasks_reached"
        assert execute_result["project_ready_execution"]["stop_reason"] == "max_tasks_reached"
        assert execute_result["project_ready_execution"]["chapter_tasks_executed"] == 1
        assert execute_result["task_pool"]["metadata"]["project_ready_execution"]["stop_reason"] == "max_tasks_reached"

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
            result={
                "success": True,
                "outline": {
                    "title": "归墟录",
                    "chapters": [
                        {"title": "第一章", "summary": "旧城归来"},
                        {"title": "第二章", "summary": "风雪入城"},
                        {"title": "第三章", "summary": "夜雨旧巷"},
                    ],
                },
            },
        )
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
            outline_agent,
            context_agent,
            reader_agent,
            chapter_agent,
            evaluator_agent,
            polisher_agent,
            expansion_agent,
        ])

        coordinator.capability_registry = registry
        coordinator.worldbuilder = world_agent
        coordinator.outliner = outline_agent
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
        execute_result = await coordinator.execute_project_ready_tasks(
            max_tasks=5,
            max_chapter_tasks=2,
        )

        task_by_type = {}
        for item in execute_result["task_pool"]["tasks"]:
            task_by_type.setdefault(item["task_type"], []).append(item)

        write_tasks = task_by_type["write_chapter"]
        outline_rows = coordinator.project_manager.load_project_data("outline")

        assert task_by_type["build_world"][0]["status"] == TaskStatus.COMPLETED
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
        assert outline_rows[0]["content"] == "统一章节正文"
        assert outline_rows[1]["content"] == "统一章节正文"
        assert outline_rows[2]["content"] == ""

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
            elif task.task_type == "build_outline":
                runtime_pool.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    assigned_agent="Outliner",
                    result_ref="outline.json",
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

            async def fake_send_task(receiver, task_type, task_data, context=None, timeout=0):
                captured["receiver"] = receiver
                captured["task_type"] = task_type
                captured["task_data"] = dict(task_data or {})
                captured["context"] = dict(context or {})
                return {"outline": {"title": "测试大纲"}}

            agent.send_task = fake_send_task

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
    async def test_router_create_novel_returns_draft_contract_confirmation_payload(self, mock_model_config):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("novel_agent.agents.base_agent.get_config_manager") as mock_manager:
                mock_manager.return_value.get_effective_config.return_value = mock_model_config

                from novel_agent.workflow.coordinator import NovelCoordinator
                from novel_agent.agents.router_agent import RouterAgent

                coordinator = NovelCoordinator(project_dir=Path(temp_dir))
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
