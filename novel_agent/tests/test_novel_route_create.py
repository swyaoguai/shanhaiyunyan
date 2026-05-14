import json
from pathlib import Path

import pytest

from novel_agent.agents.router_agent import RouterAgent
from novel_agent.project_manager import ProjectManager
from novel_agent.web.models.requests import ConfirmCreationContractRequest, CreateNovelRequest, ResumeCreationFlowRequest
from novel_agent.web.routes import chat as chat_routes
from novel_agent.web.routes import novel as novel_routes


def _isolated_project_manager(tmp_path, monkeypatch) -> tuple[ProjectManager, Path]:
    pm = ProjectManager(data_dir=tmp_path / "data")
    project = pm.create_project("测试项目", "隔离项目")
    assert pm.switch_project(project.id)
    project_dir = pm._get_project_dir(project.id)

    monkeypatch.setattr("novel_agent.project_manager._project_manager", pm)
    monkeypatch.setattr("novel_agent.project_manager.get_project_manager", lambda: pm)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_project_manager", lambda: pm)
    return pm, project_dir


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


class _ResumeFormalCoordinator(_FakeFormalCoordinator):
    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        task_pool = self.project_manager.load_project_state("task_pool", default={})
        chapters_dir = self.project_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapter_one = chapters_dir / "001_第1章_续跑.md"
        chapter_one.write_text("续跑正文", encoding="utf-8")
        for task in task_pool.get("tasks", []):
            if task.get("task_type") == "write_chapter":
                task["status"] = "completed"
                task["assigned_agent"] = "ChapterWriter"
                task["result_ref"] = str(chapter_one)
        task_pool.setdefault("metadata", {})["project_ready_execution"] = {
            "executed_task_count": 1,
            "chapter_tasks_executed": 1,
            "stop_reason": "",
            "stopped_on_task_type": "",
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state(
            "collab_execution_trace",
            {"status": "running", "events": [{"type": "project_ready_execution_cycle"}]},
        )
        return {
            "task_pool": task_pool,
            "executed_tasks": [
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "selected_agent": "ChapterWriter", "result_ref": str(chapter_one)}
            ],
            "project_ready_execution": task_pool["metadata"]["project_ready_execution"],
            "stop_reason": "",
            "stopped_on_task_type": "",
        }


class _GuardedResumeFormalCoordinator(_FakeFormalCoordinator):
    def __init__(self, pm: ProjectManager, project_dir: Path):
        super().__init__(pm=pm, project_dir=project_dir)
        self.approve_calls = 0

    def approve_chapter_settings_review(self):
        self.approve_calls += 1
        state = {"approved": True, "status": "approved"}
        self.project_manager.save_project_state("chapter_settings_review", state)
        return state

    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {
            "max_tasks": max_tasks,
            "max_chapter_tasks": max_chapter_tasks,
        }
        review_state = self.project_manager.load_project_state("chapter_settings_review", default={})
        approved = isinstance(review_state, dict) and bool(review_state.get("approved"))
        task_pool = self.project_manager.load_project_state("task_pool", default={})
        if approved:
            chapters_dir = self.project_dir / "chapters"
            chapters_dir.mkdir(parents=True, exist_ok=True)
            chapter_one = chapters_dir / "001_第1章_续跑.md"
            chapter_one.write_text("续跑正文", encoding="utf-8")
            for task in task_pool.get("tasks", []):
                if task.get("task_type") == "write_chapter":
                    task["status"] = "completed"
                    task["assigned_agent"] = "ChapterWriter"
                    task["result_ref"] = str(chapter_one)
            execution = {
                "executed_task_count": 1,
                "chapter_tasks_executed": 1,
                "stop_reason": "",
                "stopped_on_task_type": "",
                "max_tasks": max_tasks,
                "max_chapter_tasks": max_chapter_tasks,
            }
        else:
            for task in task_pool.get("tasks", []):
                if task.get("task_type") == "write_chapter":
                    task["status"] = "blocked"
                    task.setdefault("metadata", {})["blocked_reason"] = "章纲设定尚未确认，已阻止提前创建正文章节文件"
            execution = {
                "executed_task_count": 0,
                "chapter_tasks_executed": 0,
                "stop_reason": "chapter_settings_review_required",
                "stopped_on_task_type": "write_chapter",
                "max_tasks": max_tasks,
                "max_chapter_tasks": max_chapter_tasks,
            }
        task_pool.setdefault("metadata", {})["project_ready_execution"] = execution
        self.project_manager.save_project_state("task_pool", task_pool)
        return {
            "task_pool": task_pool,
            "executed_tasks": [],
            "project_ready_execution": execution,
            "stop_reason": execution["stop_reason"],
            "stopped_on_task_type": execution["stopped_on_task_type"],
        }


class _IdempotentConfirmCoordinator(_ResumeFormalCoordinator):
    def __init__(self, pm: ProjectManager, project_dir: Path):
        super().__init__(pm=pm, project_dir=project_dir)
        self.initialize_calls = 0

    def initialize_task_pool_from_contract(self, contract_payload, approved=True):
        self.initialize_calls += 1
        raise AssertionError("重复确认已确认合同不应重新初始化任务池")


class _ReviewBreakFormalCoordinator(_FakeFormalCoordinator):
    def initialize_task_pool_from_contract(self, contract_payload, approved=True):
        task_pool = {
            "metadata": {"contract_id": contract_payload.get("contract_id", "contract-review")},
            "tasks": [
                {"task_id": "settings-1", "task_type": "chapter_settings", "title": "生成章纲设定", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {}},
                {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
            ],
        }
        self.project_manager.save_project_state("creation_contract", contract_payload)
        self.project_manager.save_project_state("task_pool", task_pool)
        self.project_manager.save_project_state("collab_execution_trace", {"status": "initialized", "events": []})
        return {"creation_contract": contract_payload, "task_pool": task_pool}

    async def execute_project_ready_tasks(self, max_tasks=2, max_chapter_tasks=1):
        self.last_execute_kwargs = {"max_tasks": max_tasks, "max_chapter_tasks": max_chapter_tasks}
        self.project_manager.save_project_data(
            "outline",
            [{"chapter_number": 1, "title": "赐婚", "summary": "赐婚开始", "content": ""}],
        )
        self.project_manager.save_project_data(
            "chapter_settings",
            [{"chapter_number": 1, "name": "赐婚", "description": "赐婚开始"}],
        )
        task_pool = self.project_manager.load_project_state("task_pool", default={})
        for task in task_pool.get("tasks", []):
            if task.get("task_type") == "chapter_settings":
                task["status"] = "completed"
                task["assigned_agent"] = "ChapterSettingBuilder"
                task["result_ref"] = "chapter_settings.json"
        task_pool.setdefault("metadata", {})["project_ready_execution"] = {
            "executed_task_count": 1,
            "chapter_tasks_executed": 0,
            "stop_reason": "review_required",
            "stopped_on_task_type": "chapter_settings",
        }
        self.project_manager.save_project_state("task_pool", task_pool)
        return {
            "task_pool": task_pool,
            "executed_tasks": [
                {"task_id": "settings-1", "task_type": "chapter_settings", "title": "生成章纲设定", "selected_agent": "ChapterSettingBuilder", "result_ref": "chapter_settings.json"},
            ],
            "project_ready_execution": task_pool["metadata"]["project_ready_execution"],
            "stop_reason": "review_required",
            "stopped_on_task_type": "chapter_settings",
        }


@pytest.mark.asyncio
async def test_novel_create_route_uses_formal_router_execution(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _FakeFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_router_agent", lambda: router)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_chat_session_store", lambda: _FakeChatStore())
    monkeypatch.setattr("novel_agent.web.routes.chat.get_coordinator", lambda: coordinator)

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
async def test_resume_creation_flow_continues_existing_task_pool(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _ResumeFormalCoordinator(pm=pm, project_dir=project_dir)
    contract_payload = {"contract_id": "contract-resume", "task_graph": []}
    task_pool = {
        "metadata": {
            "contract_id": "contract-resume",
            "project_ready_execution": {
                "stop_reason": "review_required",
                "stopped_on_task_type": "chapter_settings",
            },
        },
        "tasks": [
            {"task_id": "settings-1", "task_type": "chapter_settings", "title": "生成章纲设定", "status": "completed", "result_ref": "chapter_settings.json", "assigned_agent": "ChapterSettingBuilder", "inputs": {}},
            {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
        ],
    }
    pm.save_project_state("creation_contract", contract_payload)
    pm.save_project_state("task_pool", task_pool)
    pm.save_project_state("collab_execution_trace", {"events": []})

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)

    response = await novel_routes.resume_creation_flow(
        ResumeCreationFlowRequest(session_id="copilot", max_tasks=6, max_chapter_tasks=1)
    )
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["success"] is True
    assert payload["project_ready_execution"]["executed_task_count"] == 1
    assert payload["stopped_on_task_type"] == ""
    assert coordinator.last_execute_kwargs == {"max_tasks": 6, "max_chapter_tasks": 1}
    saved_task_pool = pm.load_project_state("task_pool", default={})
    write_task = next(item for item in saved_task_pool["tasks"] if item["task_type"] == "write_chapter")
    assert write_task["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_creation_flow_requires_explicit_chapter_settings_approval(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _GuardedResumeFormalCoordinator(pm=pm, project_dir=project_dir)
    contract_payload = {"contract_id": "contract-review", "task_graph": []}
    task_pool = {
        "metadata": {
            "contract_id": "contract-review",
            "project_ready_execution": {
                "stop_reason": "review_required",
                "stopped_on_task_type": "chapter_settings",
            },
        },
        "tasks": [
            {"task_id": "settings-1", "task_type": "chapter_settings", "title": "生成章纲设定", "status": "completed", "result_ref": "chapter_settings.json", "assigned_agent": "ChapterSettingBuilder", "inputs": {}},
            {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
        ],
    }
    pm.save_project_state("creation_contract", contract_payload)
    pm.save_project_state("task_pool", task_pool)
    pm.save_project_state("chapter_settings_review", {"approved": False, "status": "pending_review"})
    pm.save_project_state("collab_execution_trace", {"events": []})

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)

    blocked_response = await novel_routes.resume_creation_flow(
        ResumeCreationFlowRequest(session_id="copilot", max_tasks=6, max_chapter_tasks=1)
    )
    blocked_payload = json.loads(blocked_response.body.decode("utf-8"))

    assert blocked_payload["stop_reason"] == "chapter_settings_review_required"
    assert "不会提前创建正文章节文件" in blocked_payload["message"]
    assert coordinator.approve_calls == 0
    assert not any((project_dir / "chapters").glob("*.md")) if (project_dir / "chapters").exists() else True

    approved_response = await novel_routes.resume_creation_flow(
        ResumeCreationFlowRequest(
            session_id="copilot",
            max_tasks=6,
            max_chapter_tasks=1,
            approve_chapter_settings=True,
        )
    )
    approved_payload = json.loads(approved_response.body.decode("utf-8"))

    assert approved_payload["stop_reason"] == ""
    assert coordinator.approve_calls == 1
    assert any((project_dir / "chapters").glob("*.md"))


@pytest.mark.asyncio
async def test_confirm_creation_contract_reuses_existing_confirmed_task_pool(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _IdempotentConfirmCoordinator(pm=pm, project_dir=project_dir)
    contract_payload = {
        "contract_id": "contract-confirmed",
        "user_confirmed": True,
        "task_graph": [],
    }
    task_pool = {
        "metadata": {"contract_id": "contract-confirmed", "source": "contract_confirmation"},
        "tasks": [
            {"task_id": "settings-1", "task_type": "chapter_settings", "title": "生成章纲设定", "status": "completed", "result_ref": "chapter_settings.json", "assigned_agent": "ChapterSettingBuilder", "inputs": {}},
            {"task_id": "chapter-1", "task_type": "write_chapter", "title": "创作第1章", "status": "pending", "result_ref": "", "assigned_agent": "", "inputs": {"chapter_number": 1}},
        ],
    }
    pm.save_project_state("creation_contract", contract_payload)
    pm.save_project_state("task_pool", task_pool)
    pm.save_project_state("collab_execution_trace", {"events": []})

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)

    response = await novel_routes.confirm_creation_contract(
        ConfirmCreationContractRequest(
            contract_id="contract-confirmed",
            approved=True,
            session_id="copilot",
            contract_payload=contract_payload,
        )
    )
    payload = json.loads(response.body.decode("utf-8"))

    assert payload["success"] is True
    assert payload["message"] == "合同已确认过，已沿用现有任务池继续执行。"
    assert coordinator.initialize_calls == 0
    assert coordinator.last_execute_kwargs == {"max_tasks": 7, "max_chapter_tasks": 2}
    saved_task_pool = pm.load_project_state("task_pool", default={})
    write_task = next(item for item in saved_task_pool["tasks"] if item["task_type"] == "write_chapter")
    assert write_task["status"] == "completed"


def test_contract_confirmation_preview_marks_reused_project_outputs(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    pm.save_project_data("worldbuilding", {"world": {"world_name": "瑞安朝"}})
    pm.save_project_data("characters", [{"name": "苏婉儿"}])
    pm.save_project_data("outline", [{"chapter_number": 1, "title": "赐婚", "summary": "赐婚开始"}])
    pm.save_project_data("chapter_settings", [{"chapter_number": 1, "name": "赐婚", "description": "赐婚开始"}])
    chapters_dir = pm.get_chapters_dir()
    (chapters_dir / "001_赐婚.md").write_text("已有第一章正文", encoding="utf-8")
    router = RouterAgent(coordinator=None)

    contract_payload = {
        "contract_id": "contract-preview",
        "scope": {"novel_type": "古代言情", "theme": "赐婚", "total_chapters": 2},
        "constraints": {},
        "deliverables": ["worldbuilding.json", "chapters/*.md"],
        "agent_candidates": ["Worldbuilder", "ChapterWriter"],
        "task_graph": [
            {"task_type": "build_world", "title": "生成世界观", "inputs": {}},
            {"task_type": "build_characters", "title": "生成角色档案", "inputs": {}},
            {"task_type": "build_outline", "title": "生成大纲", "inputs": {}},
            {"task_type": "chapter_settings", "title": "生成章纲设定", "inputs": {}},
            {"task_type": "write_chapter", "title": "创作第1章", "inputs": {"chapter_number": 1}},
            {"task_type": "write_chapter", "title": "创作第2章", "inputs": {"chapter_number": 2}},
        ],
    }

    result = router._build_contract_confirmation_response(
        requirements={},
        contract_payload=contract_payload,
        context={"run_id": "run-preview"},
    )

    assert "生成世界观（已完成，将复用）" in result["response"]
    assert "创作第1章（已完成，将复用）" in result["response"]
    preview = result["params"]["creation_contract"]["task_graph_preview"]
    assert preview[0]["preview_status"] == "reuse"
    assert preview[4]["preview_status"] == "reuse"
    assert preview[5]["preview_status"] == "pending"


def test_formal_task_file_record_maps_chapter_settings_kind(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "chapter_settings.json").write_text("[]", encoding="utf-8")
    router = RouterAgent(coordinator=None)

    record = router._build_formal_task_file_record(
        task={"task_type": "chapter_settings", "result_ref": "chapter_settings.json", "title": "生成章纲设定"},
        project_dir=project_dir,
        existing_paths=set(),
    )

    assert record is not None
    assert record["kind"] == "chapter_settings"
    assert record["label"] == "章纲设定"


@pytest.mark.asyncio
async def test_formal_router_response_explains_chapter_settings_review_break(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _ReviewBreakFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    result = await router._execute_create_novel_pipeline_formal(
        message="开始创作",
        context={"run_id": "run-review"},
        requirements={},
        contract_payload={"contract_id": "contract-review", "scope": {}, "task_graph": []},
    )

    assert result["is_complete"] is False
    assert result["awaiting_user_review"] is True
    assert result["resume_endpoint"] == "/api/v1/contract/resume"
    assert "章纲设定已生成，正文创作已暂停等待你的审阅。" in result["response"]
    assert "审阅通过后将从第 1 章继续。" in result["response"]


@pytest.mark.asyncio
async def test_formal_router_execution_does_not_report_empty_outline_as_chapter_complete(tmp_path, monkeypatch):
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _TaskFailedFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

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
    pm, project_dir = _isolated_project_manager(tmp_path, monkeypatch)
    coordinator = _FailingFormalCoordinator(pm=pm, project_dir=project_dir)
    router = RouterAgent(coordinator=coordinator)

    monkeypatch.setattr("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator)
    monkeypatch.setattr("novel_agent.web.routes.novel.get_router_agent", lambda: router)
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
