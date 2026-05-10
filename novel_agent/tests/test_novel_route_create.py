import json
from pathlib import Path

import pytest

from novel_agent.agents.router_agent import RouterAgent
from novel_agent.project_manager import ProjectManager
from novel_agent.web.models.requests import CreateNovelRequest
from novel_agent.web.routes import chat as chat_routes
from novel_agent.web.routes import novel as novel_routes


class _FakeChatStore:
    def load(self, session_id, project_id):
        return None


class _FakeFormalCoordinator:
    def __init__(self, pm: ProjectManager, project_dir: Path):
        self.project_manager = pm
        self.project_dir = project_dir
        self.progress_callback = None
        self.project = None
        self.last_execute_kwargs = {}

    async def create_novel(self, *args, **kwargs):
        raise AssertionError("/novel/create should use formal router execution path")

    def initialize_task_pool_from_contract(self, contract_payload, approved=True):
        task_pool = {
            "metadata": {
                "contract_id": contract_payload.get("contract_id", "contract-1"),
                "source": "contract_confirmation",
            },
            "tasks": [
                {"task_id": "world-1", "task_type": "build_world", "title": "生成世界观", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {}},
                {"task_id": "outline-1", "task_type": "build_outline", "title": "生成大纲", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {}},
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
            ],
        }
        self.project_manager.save_project_state("creation_contract", contract_payload)
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state(
            "collab_execution_trace",
            {"status": "initialized", "events": [{"type": "contract_confirmation"}]},
        )
        return {"creation_contract": contract_payload, "task_pool": task_pool}

    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        if self.progress_callback:
            await self.progress_callback(
                {
                    "type": "sub_agent_dispatching",
                    "stage": "project_dispatch",
                    "agent": "Coordinator",
                    "task_type": "build_world",
                    "title": "生成世界观",
                    "message": "正在调度任务: 生成世界观",
                }
            )

        (self.project_dir / "worldbuilding.json").write_text(
            json.dumps({"world": {"world_name": "玄幻世界"}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outline_rows = [
            {"chapter_number": 1, "title": "第1章 旧城归来", "summary": "林渡回到旧城。", "content": "第1章正文"},
        ]
        self.project_manager.save_project_data("outline", outline_rows)
        chapters_dir = self.project_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapter_one = chapters_dir / "001_第1章_旧城归来.md"
        chapter_one.write_text("第1章正文", encoding="utf-8")

        task_pool = self.project_manager.load_project_state("task_pool", default={})
        for task in task_pool.get("tasks", []):
            task["status"] = "completed"
            if task.get("task_type") == "build_world":
                task["assigned_agent"] = "Worldbuilder"
                task["result_ref"] = "worldbuilding.json"
            elif task.get("task_type") == "build_outline":
                task["assigned_agent"] = "Outliner"
                task["result_ref"] = "outline.json"
            elif task.get("task_type") == "write_chapter":
                task["assigned_agent"] = "ChapterWriter"
                task["result_ref"] = str(chapter_one)
        task_pool["metadata"]["project_ready_execution"] = {
            "executed_task_count": 3,
            "chapter_tasks_executed": 1,
            "stop_reason": "",
            "stopped_on_task_type": "",
        }
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state(
            "collab_execution_trace",
            {"status": "initialized", "events": [{"type": "contract_confirmation"}, {"type": "project_ready_execution_cycle"}]},
        )
        return {
            "task_pool": task_pool,
            "executed_tasks": [
                {"task_id": "world-1", "task_type": "build_world", "title": "生成世界观", "selected_agent": "Worldbuilder", "result_ref": "worldbuilding.json"},
                {"task_id": "outline-1", "task_type": "build_outline", "title": "生成大纲", "selected_agent": "Outliner", "result_ref": "outline.json"},
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "selected_agent": "ChapterWriter", "result_ref": str(chapter_one)},
            ],
            "project_ready_execution": task_pool["metadata"]["project_ready_execution"],
            "stop_reason": "",
            "stopped_on_task_type": "",
        }

    def _save_novel(self, file_path: Path, chapters):
        content = "\n\n".join(str(chapter.get("content") or "") for chapter in chapters)
        file_path.write_text(content, encoding="utf-8")


class _FailingFormalCoordinator(_FakeFormalCoordinator):
    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        raise RuntimeError("formal task pool boom")


class _TaskFailedFormalCoordinator(_FakeFormalCoordinator):
    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        task_pool = self.project_manager.load_project_state("task_pool", default={})
        for task in task_pool.get("tasks", []):
            if task.get("task_type") == "build_world":
                task["status"] = "completed"
                task["assigned_agent"] = "Worldbuilder"
                task["result_ref"] = "worldbuilding.json"
            elif task.get("task_type") == "build_outline":
                task["status"] = "pending"
            elif task.get("task_type") == "write_chapter":
                task["status"] = "pending"
        task_pool.setdefault("tasks", []).insert(
            1,
            {
                "task_id": "characters-1",
                "task_type": "build_characters",
                "title": "生成角色档案",
                "status": "failed",
                "result_ref": "",
                "assigned_agent": "CharacterBuilder",
                "inputs": {},
                "metadata": {"error": "角色卡草稿质量不足"},
            },
        )
        task_pool.setdefault("metadata", {})["project_ready_execution"] = {
            "executed_task_count": 1,
            "chapter_tasks_executed": 0,
            "stop_reason": "task_failed",
            "stopped_on_task_type": "build_characters",
        }
        self.project_manager.save_project_state("task_pool", task_pool)
        return {
            "task_pool": task_pool,
            "executed_tasks": [
                {"task_id": "world-1", "task_type": "build_world", "title": "生成世界观", "selected_agent": "Worldbuilder", "result_ref": "worldbuilding.json"},
            ],
            "project_ready_execution": task_pool["metadata"]["project_ready_execution"],
            "stop_reason": "task_failed",
            "stopped_on_task_type": "build_characters",
        }


@pytest.mark.asyncio
async def test_novel_create_route_uses_formal_router_execution(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FakeFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_chat_session_store", lambda: _FakeChatStore())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    response = await novel_routes.create_novel(
        CreateNovelRequest(
            novel_type="玄幻",
            theme="复仇成长",
            plot_idea="宗门覆灭后的复仇与重建",
            volume_count=1,
            chapters_per_volume=1,
            session_id="copilot",
        )
    )

    events = []
    async for raw in response.body_iterator:
        events.append(raw)

    joined = "".join(
        item.decode("utf-8") if isinstance(item, (bytes, bytearray)) else str(item)
        for item in events
    )

    saved_task_pool = pm.load_project_state("task_pool", default={})
    saved_trace = pm.load_project_state("collab_execution_trace", default={})

    assert "已切换到正式多助手协作执行链" in joined
    assert "当前任务池中的章节任务已全部完成。" in joined
    assert coordinator.last_execute_kwargs == {"max_tasks": 3, "max_chapter_tasks": 1}
    assert saved_task_pool.get("metadata", {}).get("source") == "contract_confirmation"
    assert saved_task_pool.get("metadata", {}).get("project_ready_execution", {}).get("executed_task_count") == 3
    assert any(item.get("type") == "project_ready_execution_cycle" for item in saved_trace.get("events", []))

    status_response = await chat_routes.get_chat_workflow_status(session_id="copilot")
    status_payload = json.loads(status_response.body.decode("utf-8"))
    assert status_payload["workflow"]["status"] == "completed"


@pytest.mark.asyncio
async def test_formal_router_execution_does_not_report_empty_outline_as_chapter_complete(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _TaskFailedFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)

    contract_payload = {
        "contract_id": "contract-failed-character",
        "scope": {
            "novel_type": "古代甜宠",
            "theme": "甜宠",
            "plot_idea": "",
            "volume_count": 1,
            "chapters_per_volume": 17,
        },
        "task_graph": [],
    }

    result = await router._execute_create_novel_pipeline_formal(
        message="我想写一本古代甜宠题材小说，篇幅5w字，其他的你随便帮我安排",
        context={"run_id": "run-task-failed"},
        requirements={},
        contract_payload=contract_payload,
    )

    assert result["is_complete"] is False
    assert result["focus_chapter"] == 1
    assert "当前停止原因：任务执行失败" in result["response"]
    assert "章节任务尚未完成：上游任务已停止，请先处理当前停止原因。" in result["response"]
    assert "当前任务池中的章节任务已全部完成。" not in result["response"]


@pytest.mark.asyncio
async def test_novel_create_route_failure_updates_shared_workflow_status(tmp_path, monkeypatch):
    pm = ProjectManager(data_dir=tmp_path / "data")
    project_dir = pm._get_project_dir(pm.current_project_id)
    coordinator = _FailingFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_chat_session_store", lambda: _FakeChatStore())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)

    response = await novel_routes.create_novel(
        CreateNovelRequest(
            novel_type="玄幻",
            theme="复仇成长",
            plot_idea="宗门覆灭后的复仇与重建",
            volume_count=1,
            chapters_per_volume=1,
            session_id="copilot_fail",
        )
    )

    events = []
    async for item in response.body_iterator:
        events.append(item)
    joined = "".join(
        item.decode("utf-8") if isinstance(item, (bytes, bytearray)) else str(item)
        for item in events
    )
    assert "创建小说失败" in joined

    status_response = await chat_routes.get_chat_workflow_status(session_id="copilot_fail")
    status_payload = json.loads(status_response.body.decode("utf-8"))
    assert status_payload["workflow"]["status"] == "failed"
    assert "formal task pool boom" in status_payload["reply"]
