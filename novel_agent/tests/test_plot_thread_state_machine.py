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


def test_plot_thread_auto_starts_from_eventline_schedule():
    machine = PlotThreadStateMachine()
    machine.sync_with_outline(
        {},
        total_chapters=6,
        reset=True,
        eventlines=[
            {
                "thread_id": "auction_line",
                "name": "拍卖会支线",
                "description": "拿到玄铁令",
                "start_chapter": 2,
                "target_return_chapter": 3,
                "max_consecutive_chapters": 1,
            }
        ],
    )

    plan_1 = machine.plan_chapter(1, {"title": "主线开场"})
    assert plan_1["active_thread_id"] == "main"

    plan_2 = machine.plan_chapter(2, {"title": "自动切入拍卖会"})
    assert plan_2["active_thread_id"] == "auction_line"
    assert plan_2["last_transition_reason"] == "scheduled_thread_start"
    complete_2 = machine.complete_chapter(2, {}, "正文")
    assert complete_2["active_thread_id"] == "main"
    assert complete_2["transition_reason"] == "guard_forced_return_main"

    plan_3 = machine.plan_chapter(3, {"title": "回主线"})
    assert plan_3["active_thread_id"] == "main"


def test_plot_thread_eventline_without_start_does_not_auto_start():
    machine = PlotThreadStateMachine()
    machine.sync_with_outline(
        {},
        total_chapters=4,
        reset=True,
        eventlines=[
            {
                "thread_id": "unscheduled_line",
                "name": "只作为资料参考的事件线",
                "description": "没有指定落点时不自动抢占第1章。",
            }
        ],
    )

    plan_1 = machine.plan_chapter(1, {"title": "主线开场"})

    assert plan_1["active_thread_id"] == "main"
    assert plan_1["last_transition_reason"] == "keep_current_thread"


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


@pytest.mark.asyncio
async def test_coordinator_chapter_body_persists_to_chapters_without_polluting_global_outline(tmp_path):
    data_dir = tmp_path / "data"
    manager = ProjectManager(data_dir=data_dir)

    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        coordinator = NovelCoordinator(project_dir=tmp_path / "project")
        manager.save_project_data(
            "outline",
            [
                {
                    "title": "主线大纲",
                    "name": "主线大纲",
                    "global_outline": "全局蓝图",
                    "volume_plan": "第一卷：起势",
                    "content": "",
                }
            ],
        )
        manager.save_project_data(
            "chapter_settings",
            [
                {"chapter_number": 1, "name": "第一章", "description": "开局"},
                {"chapter_number": 2, "name": "第二章", "description": "入局"},
            ],
        )

        chapter_rows = coordinator._load_project_chapter_rows()
        result = await coordinator._persist_project_ready_chapter_result(
            {
                "chapter_number": 2,
                "chapter_title": "第二章",
                "content": "第二章正文",
            },
            chapter_rows,
        )

        chapters = manager.load_project_data("chapters")
        outline = manager.load_project_data("outline")
        assert chapters[1]["chapter_number"] == 2
        assert chapters[1]["content"] == "第二章正文"
        assert outline[0]["title"] == "主线大纲"
        assert outline[0].get("content", "") == ""
        assert result["chapters_path"].endswith("chapters.json")
    finally:
        project_manager_module._project_manager = old_manager


@pytest.mark.asyncio
async def test_coordinator_chapter_body_uses_chapter_number_not_row_index(tmp_path):
    data_dir = tmp_path / "data"
    manager = ProjectManager(data_dir=data_dir)

    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        coordinator = NovelCoordinator(project_dir=tmp_path / "project")
        manager.save_project_data(
            "chapters",
            [
                {
                    "chapter_number": 2,
                    "title": "第二章",
                    "summary": "已有章纲",
                    "content": "",
                }
            ],
        )

        await coordinator._persist_project_ready_chapter_result(
            {
                "chapter_number": 2,
                "chapter_title": "第二章",
                "content": "第二章正文",
            },
            [],
        )

        chapters = manager.load_project_data("chapters")
        rows_by_number = {row["chapter_number"]: row for row in chapters}
        assert rows_by_number[1]["title"] == "第1章"
        assert rows_by_number[2]["title"] == "第二章"
        assert rows_by_number[2]["content"] == "第二章正文"
    finally:
        project_manager_module._project_manager = old_manager


def test_coordinator_chapter_planning_context_reads_chapter_and_detail_settings(tmp_path):
    data_dir = tmp_path / "data"
    manager = ProjectManager(data_dir=data_dir)

    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        coordinator = NovelCoordinator(project_dir=tmp_path / "project")
        manager.save_project_data(
            "chapter_settings",
            [
                {
                    "chapter_number": 3,
                    "name": "雨夜摊牌",
                    "chapter_goal": "逼问同盟",
                    "plot_thread": {"switch_to": "ally_line", "thread_id": "ally_line"},
                }
            ],
        )
        manager.save_project_data(
            "detail_settings",
            [
                {
                    "chapter_number": 3,
                    "name": "雨巷对峙",
                    "scene_goal": "用证据逼出破绽",
                    "conflict": "同盟拒不承认",
                }
            ],
        )

        planning = coordinator._get_chapter_planning_context(3)

        assert "章纲设定" in planning["prompt"]
        assert "细纲设定" in planning["prompt"]
        assert "逼问同盟" in planning["prompt"]
        assert planning["plot_thread"]["switch_to"] == "ally_line"
    finally:
        project_manager_module._project_manager = old_manager
