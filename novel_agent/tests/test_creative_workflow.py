import pytest

from novel_agent.agents.evaluator import EvaluatorAgent
from novel_agent.workflow.artifact_review import review_artifact_basic
from novel_agent.workflow.creative_executor import CreativeWorkflowExecutor, TaskExecutionResult
from novel_agent.workflow.creative_workflow import CreativeWorkflowRun
from novel_agent.workflow.workflow_context import Artifact, WorkflowContext
from novel_agent.workflow.workflow_planner import build_workflow_plan, detect_target_categories


def test_creative_workflow_planner_orders_dependent_categories():
    plan = build_workflow_plan(user_request="先帮我写角色卡和世界观看看")

    assert plan.target_categories == ["worldbuilding", "characters"]
    assert [task.task_type for task in plan.tasks] == ["prepare_context", "worldbuilding", "characters"]
    assert plan.tasks[1].target_agent == "Worldbuilder"
    assert plan.tasks[2].input_refs == ["worldbuilding"]


def test_creative_workflow_planner_detects_custom_category_aliases():
    categories = [
        {
            "id": "db-custom-force",
            "key": "custom_force",
            "name": "势力阵营",
            "aliases": ["门派势力"],
        }
    ]

    detected = detect_target_categories("生成势力阵营 合欢宗，暗中控制边城商路", knowledge_categories=categories)

    assert detected == ["custom_force"]


def test_basic_artifact_review_reports_missing_character_identity():
    review = review_artifact_basic(
        task_id="create_characters",
        artifact_id="artifact-1",
        artifact_type="characters",
        artifact=[{"name": "主角", "description": "短"}],
        revision_target="CharacterBuilder",
    )

    assert review.passed is False
    assert review.severity == "major"
    assert review.revision_target == "CharacterBuilder"
    assert review.issues


def test_basic_artifact_review_stops_worldbuilding_missing_info():
    review = review_artifact_basic(
        task_id="create_worldbuilding",
        artifact_id="artifact-world",
        artifact_type="worldbuilding",
        artifact={
            "status": "missing_info",
            "missing_info": ["副本核心机制", "主角能力限制"],
        },
        revision_target="Worldbuilder",
    )

    assert review.passed is False
    assert review.severity == "major"
    assert "副本核心机制" in review.missing_info
    assert any(issue.type == "missing_info" for issue in review.issues)


@pytest.mark.asyncio
async def test_creative_workflow_executor_runs_tasks_with_reviews_and_handoffs():
    plan = build_workflow_plan(user_request="先帮我写世界观和角色卡看看")
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="先帮我写世界观和角色卡看看",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="先帮我写世界观和角色卡看看"),
        run_id="creative-test-run",
    )
    emitted = []
    task_calls = []

    async def fake_runner(task, workflow_context):
        task_calls.append(task.task_type)
        if task.task_type == "worldbuilding":
            return TaskExecutionResult(
                success=True,
                agent_name="Worldbuilder",
                action="worldbuild",
                response="世界观已生成。",
                artifact={
                    "world_name": "玄铁界",
                    "history": "宗门与边城商路相互纠缠，旧宗门覆灭后留下无法公开的真相。",
                    "power_system": "剑修、符箓与商会情报网共同构成修行秩序。",
                    "regions": "边城、旧宗门遗址、商路驿站彼此牵连，足以支撑角色后续选择。",
                },
                artifact_type="worldbuilding",
                target_path="worldbuilding.json",
                created_files=[{"kind": "worldbuilding", "path": "worldbuilding.json"}],
            )
        assert any(
            artifact.get("artifact_type") == "worldbuilding"
            for artifact in workflow_context.previous_artifacts.values()
        )
        return TaskExecutionResult(
            success=True,
            agent_name="CharacterBuilder",
            action="create_character",
            response="角色卡已生成。",
            artifact=[
                {
                    "name": "林渡",
                    "description": "旧宗门覆灭后幸存的少年剑修，正在追查商路背后的真相。",
                    "role": "主角",
                }
            ],
            artifact_type="characters",
            target_path="characters.json",
            updated_files=[{"kind": "characters", "path": "characters.json"}],
            reused_files=[{"kind": "worldbuilding", "path": "worldbuilding.json"}],
        )

    async def fake_emitter(current_run, payload):
        emitted.append(payload)

    completed = await CreativeWorkflowExecutor(
        run=run,
        task_runner=fake_runner,
        progress_emitter=fake_emitter,
    ).execute()

    assert completed.status == "completed"
    assert task_calls == ["worldbuilding", "characters"]
    assert [task.task_type for task in completed.completed_tasks] == [
        "prepare_context",
        "worldbuilding",
        "characters",
    ]
    assert all(review.passed for review in completed.reviews)
    assert len(completed.handoff_notes) == 2
    assert completed.created_files == [{"kind": "worldbuilding", "path": "worldbuilding.json"}]
    assert completed.updated_files == [{"kind": "characters", "path": "characters.json"}]
    assert completed.reused_files == [{"kind": "worldbuilding", "path": "worldbuilding.json"}]
    assert emitted[-1]["creative_workflow"]["status"] == "completed"


@pytest.mark.asyncio
async def test_creative_workflow_executor_retries_failed_review_once():
    plan = build_workflow_plan(user_request="生成角色卡", target_categories=["characters"])
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="生成角色卡",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="生成角色卡"),
        run_id="creative-retry-run",
    )
    attempts = 0

    async def fake_runner(task, workflow_context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return TaskExecutionResult(
                success=True,
                agent_name="CharacterBuilder",
                action="create_character",
                response="角色卡草稿过薄。",
                artifact=[{"name": "主角", "description": "短"}],
                artifact_type="characters",
            )
        assert workflow_context.review_feedback[-1]["passed"] is False
        return TaskExecutionResult(
            success=True,
            agent_name="CharacterBuilder",
            action="create_character",
            response="角色卡已补全。",
            artifact=[
                {
                    "name": "林渡",
                    "description": "宗门覆灭后幸存的少年剑修，正在追查师父失踪和旧案真相。",
                    "role": "主角",
                }
            ],
            artifact_type="characters",
        )

    completed = await CreativeWorkflowExecutor(run=run, task_runner=fake_runner).execute()

    assert completed.status == "completed"
    assert attempts == 2
    assert completed.task_queue[1].retry_count == 1
    assert [review.passed for review in completed.reviews] == [False, True]
    assert completed.artifacts["create_characters-artifact-1"].status == "revision_requested"
    assert completed.artifacts["create_characters-artifact-2"].status == "committed"


@pytest.mark.asyncio
async def test_creative_workflow_executor_marks_artifact_failed_after_retry_exhaustion():
    plan = build_workflow_plan(user_request="生成角色卡", target_categories=["characters"])
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="生成角色卡",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="生成角色卡"),
        run_id="creative-failed-run",
    )

    async def failing_runner(task, workflow_context):
        raise RuntimeError("builder unavailable")

    completed = await CreativeWorkflowExecutor(run=run, task_runner=failing_runner).execute()

    assert completed.status == "failed"
    assert completed.task_queue[1].retry_count == 1
    assert completed.completed_tasks[-1].status == "failed"
    assert completed.artifacts["create_characters-artifact-1"].status == "revision_requested"
    assert completed.artifacts["create_characters-artifact-2"].status == "failed"


def test_creative_workflow_run_records_interruption_and_replans_tail_tasks():
    plan = build_workflow_plan(user_request="先写世界观和角色卡", target_categories=["worldbuilding", "characters"])
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="先写世界观和角色卡",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="先写世界观和角色卡"),
        run_id="creative-interrupt-run",
    )
    for task in run.task_queue:
        task.status = "completed"
    run.add_artifact(Artifact(
        artifact_id="character-artifact",
        artifact_type="characters",
        task_id="create_characters",
        content=[{"name": "林渡", "description": "以复仇为目标的少年剑修。"}],
        status="committed",
    ))

    interruption = run.apply_user_interruption("不对，主角不是复仇，是寻找失踪师父。")
    restored = CreativeWorkflowRun.from_dict(run.to_dict())

    assert interruption.affected_categories == ["characters"]
    assert run.status == "paused"
    assert run.task_queue[2].status == "pending"
    assert run.artifacts["character-artifact"].status == "revision_requested"
    assert restored.user_interruptions[-1].message == "不对，主角不是复仇，是寻找失踪师父。"
    assert restored.task_queue[2].status == "pending"


@pytest.mark.asyncio
async def test_evaluator_contextual_review_retries_after_user_interruption_conflict():
    plan = build_workflow_plan(user_request="生成角色卡", target_categories=["characters"])
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="生成角色卡",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="生成角色卡"),
        run_id="creative-evaluator-run",
    )
    run.apply_user_interruption("不对，主角不是复仇，是寻找失踪师父。")
    attempts = 0
    evaluator = EvaluatorAgent()

    async def fake_runner(task, workflow_context):
        nonlocal attempts
        attempts += 1
        description = "以复仇为核心目标的少年剑修。" if attempts == 1 else "寻找失踪师父的少年剑修。"
        return TaskExecutionResult(
            success=True,
            agent_name="CharacterBuilder",
            action="create_character",
            response="角色卡已生成。",
            artifact=[{"name": "林渡", "description": description, "role": "主角"}],
            artifact_type="characters",
        )

    async def review_runner(task, artifact, workflow_context, basic_review):
        return await evaluator.review_artifact(
            task_id=task.task_id,
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            artifact=artifact.content,
            revision_target=task.target_agent,
            workflow_context=workflow_context,
        )

    completed = await CreativeWorkflowExecutor(
        run=run,
        task_runner=fake_runner,
        review_runner=review_runner,
    ).execute()

    assert completed.status == "completed"
    assert attempts == 2
    assert [review.passed for review in completed.reviews] == [False, True]
    assert completed.reviews[0].issues[0].type == "context_conflict"


@pytest.mark.asyncio
async def test_creative_workflow_executor_resume_skips_completed_tasks():
    plan = build_workflow_plan(user_request="先写世界观和角色卡", target_categories=["worldbuilding", "characters"])
    run = CreativeWorkflowRun.create(
        project_id="project-1",
        user_request="先写世界观和角色卡",
        workflow_plan=plan,
        canonical_context=WorkflowContext(original_request="先写世界观和角色卡"),
        run_id="creative-resume-run",
    )
    run.task_queue[0].status = "completed"
    run.task_queue[1].status = "completed"
    run.task_queue[2].status = "pending"
    called = []

    async def fake_runner(task, workflow_context):
        called.append(task.task_type)
        return TaskExecutionResult(
            success=True,
            agent_name="CharacterBuilder",
            action="create_character",
            response="角色卡已生成。",
            artifact=[{"name": "林渡", "description": "寻找失踪师父的少年剑修。", "role": "主角"}],
            artifact_type="characters",
        )

    completed = await CreativeWorkflowExecutor(run=run, task_runner=fake_runner).execute()

    assert completed.status == "completed"
    assert called == ["characters"]
