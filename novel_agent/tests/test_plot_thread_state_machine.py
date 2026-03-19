"""Tests for plot thread state machine and coordinator persistence hooks."""

import pytest

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.workflow.coordinator import NovelCoordinator
from novel_agent.workflow.plot_thread_state import PlotThreadStateMachine


def test_plot_thread_directive_switch_and_guard_return():
    machine = PlotThreadStateMachine()
    machine.sync_with_outline(
        {
            "plot_threads": [
                {"id": "side_a", "title": "支线A", "max_consecutive_chapters": 2}
            ]
        },
        total_chapters=10,
        reset=True,
    )

    plan_1 = machine.plan_chapter(
        1,
        {
            "title": "切入支线",
            "summary": "调查线索",
            "plot_thread": {
                "switch_to": "side_a",
                "return_by_chapter": 2,
                "objective": "找到关键证据",
            },
        },
    )
    assert plan_1["active_thread_id"] == "side_a"
    machine.complete_chapter(1, {"plot_thread": {"switch_to": "side_a"}}, "正文")

    plan_2 = machine.plan_chapter(2, {"title": "继续支线", "summary": "继续调查"})
    assert plan_2["active_thread_id"] == "side_a"
    machine.complete_chapter(2, {}, "正文")

    plan_3 = machine.plan_chapter(3, {"title": "触发回主线", "summary": "收束支线"})
    assert plan_3["active_thread_id"] == "main"
    transition_history = machine.snapshot().get("transition_history", [])
    assert any(
        item.get("reason") == "guard_forced_return_main" for item in transition_history
    )


def test_plot_thread_content_marker_return_main():
    machine = PlotThreadStateMachine()
    machine.sync_with_outline(
        {"plot_threads": [{"id": "side_b", "title": "支线B"}]},
        total_chapters=8,
        reset=True,
    )

    machine.plan_chapter(1, {"plot_thread": {"switch_to": "side_b"}})
    result = machine.complete_chapter(
        1,
        {"plot_thread": {"switch_to": "side_b"}},
        "正文内容\n<!-- PLOT_THREAD:return_main -->",
    )

    assert result["active_thread_id"] == "main"
    assert result["transition_reason"] == "content_marker_return_main"


def test_plot_thread_state_snapshot_roundtrip():
    machine = PlotThreadStateMachine()
    machine.sync_with_outline(
        {"recurring_elements": {"foreshadowing_threads": ["伏笔A"]}},
        total_chapters=6,
        reset=True,
    )
    machine.plan_chapter(1, {"summary": "[switch:subplot_1]"})
    snapshot = machine.snapshot()

    restored = PlotThreadStateMachine(snapshot)
    restored_state = restored.snapshot()

    assert restored_state["total_chapters"] == 6
    assert "main" in restored_state["threads"]
    assert "subplot_1" in restored_state["threads"]


@pytest.mark.asyncio
async def test_coordinator_plot_thread_state_persistence(tmp_path):
    data_dir = tmp_path / "data"
    manager = ProjectManager(data_dir=data_dir)

    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        coordinator = NovelCoordinator(project_dir=tmp_path / "project")
        coordinator._sync_plot_thread_state_with_outline(
            outline_data={"plot_threads": [{"id": "side_c", "title": "支线C"}]},
            total_chapters=5,
            reset=True,
        )

        plan = await coordinator._plan_plot_thread_for_chapter(
            chapter_num=1,
            chapter_outline={"plot_thread": {"switch_to": "side_c"}},
        )
        assert plan["active_thread_id"] == "side_c"

        await coordinator._complete_plot_thread_for_chapter(
            chapter_num=1,
            chapter_outline={"plot_thread": {"switch_to": "side_c"}},
            chapter_content="正文\n<!-- PLOT_THREAD:return_main -->",
            evaluation={},
        )

        persisted = manager.load_project_state("plot_thread_state", default={})
        assert persisted.get("active_thread_id") == "main"
        assert persisted.get("total_chapters") == 5
    finally:
        project_manager_module._project_manager = old_manager
