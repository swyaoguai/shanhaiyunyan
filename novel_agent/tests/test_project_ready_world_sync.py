"""
回归测试：ProjectReadyTaskExecutor._execute_build_world 必须把生成的世界观
同步到 coordinator.world_manager 的内存态，避免后续 ChapterWriter 拿到
"暂无世界观设定"，导致章节正文与世界观脱钩。

同时覆盖 WorldManager.ensure_loaded / apply_payload 的防御性 fallback。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from novel_agent.context.world_manager import WorldManager, WorldSetting
from novel_agent.project_manager import Project, ProjectManager
from novel_agent.workflow.project_ready import ProjectReadyTaskExecutor


class _StubContextManager:
    """最小化的 context_manager 假对象，只记录保存的 key/value。"""

    def __init__(self) -> None:
        self.saved: Dict[str, Any] = {}

    def save(self, key: str, value: Any, category: str = "") -> None:  # noqa: ARG002
        self.saved[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.saved.get(key, default)


class _StubTask:
    """模拟 TaskDefinition：只提供 executor 用到的字段。"""

    def __init__(self, inputs: Dict[str, Any]) -> None:
        self.inputs = dict(inputs)
        self.title = "构建世界观"
        self.description = "单测用任务"
        self.expected_outputs = ["worldbuilding.json"]
        self.review_required = False


class _StubCoordinator:
    """最小 coordinator，提供 executor 所需接口。"""

    def __init__(self, project_dir: Path, fake_world: Dict[str, Any]) -> None:
        self.project_dir = project_dir
        self.project_manager = ProjectManager(data_dir=project_dir.parent)
        self.project_manager.projects = {}
        self.project_manager.current_project_id = project_dir.name
        self.project_manager.projects[project_dir.name] = Project(id=project_dir.name, name="测试项目")
        self.world_manager = WorldManager(project_dir)
        self.context_manager = _StubContextManager()
        # executor 会引用它作为 fallback_agent，但我们会直接把 _run_autonomous_task 换成桩
        self.worldbuilder = type("_FakeAgent", (), {"name": "Worldbuilder"})()
        self._fake_world = fake_world
        self.collab_agent_registry = None
        self.capability_registry = None

    async def _run_autonomous_task(self, **_kwargs: Any) -> Dict[str, Any]:
        return {
            "result": {"world": self._fake_world},
            "selected_agent": "Worldbuilder",
            "execution_mode": "test",
            "fallback_used": False,
        }

    def _build_metadata_patch(self, _run_result: Dict[str, Any]) -> Dict[str, Any]:
        return {"test": True}


def _world_payload() -> Dict[str, Any]:
    return {
        "world_name": "瑞安朝",
        "world_type": "古代言情",
        "power_system": {"note": "无灵气，宫廷政治驱动"},
        "geography": {"capital": "长安"},
        "factions": [
            {"name": "李氏皇族", "description": "瑞安朝统治者"},
            {"name": "苏家", "description": "江南世家"},
        ],
        "rules": ["皇权至上", "门阀联姻是常态"],
        "culture": {"style": "宋明融合"},
    }


def test_execute_build_world_syncs_world_manager(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)

    coordinator = _StubCoordinator(project_dir=project_dir, fake_world=_world_payload())
    assert coordinator.world_manager.world is None, "前置条件：构造后 world_manager 应为空"

    executor = ProjectReadyTaskExecutor(coordinator)
    task = _StubTask(inputs={"novel_type": "古代言情", "theme": "赐婚"})

    result = asyncio.run(executor._execute_build_world(task))

    assert result["result_ref"] == "worldbuilding.json"

    world = coordinator.world_manager.world
    assert world is not None, "修复的核心断言：build_world 后 world_manager 必须已填充"
    assert world.name == "瑞安朝"
    assert world.world_type == "古代言情"
    assert "李氏皇族" in {item.get("name") for item in world.factions}

    context = coordinator.world_manager.get_world_context()
    assert "暂无世界观设定" not in context
    assert "瑞安朝" in context

    # 同步路径也应写入 context_manager 和 worldbuilding.json
    assert "world" in coordinator.context_manager.saved
    assert (project_dir / "worldbuilding.json").exists()


def test_world_manager_ensure_loaded_recovers_from_disk(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "worldbuilding.json").write_text(
        json.dumps({"world": _world_payload()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manager = WorldManager(project_dir)
    # 模拟某个异常路径让 world 被清空
    manager.world = None
    assert manager.world is None

    assert manager.ensure_loaded() is True
    assert manager.world is not None
    assert manager.world.name == "瑞安朝"


def test_world_manager_apply_payload_handles_bare_world_dict(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)

    manager = WorldManager(project_dir)
    manager.world = None

    # 直接传裸的 world dict（没有外层 {"world": ...} 包装）
    assert manager.apply_payload({"world": _world_payload()}) is True
    assert manager.world is not None
    assert manager.world.name == "瑞安朝"


def test_world_manager_apply_payload_returns_false_for_junk(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)

    manager = WorldManager(project_dir)
    manager.world = None

    # 不含任何世界观关键字段的 dict 应视为失败
    assert manager.apply_payload({"unrelated": 1}) is False
    assert manager.world is None
