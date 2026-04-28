"""
本地 chat / workflow 性能烟雾压测脚本。

说明：
- 只测本地编排与会话层开销，不包含真实 LLM 网络耗时
- 适合在开发机快速验证最近改动是否明显放大 orchestration latency
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, List
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from novel_agent.agents.router_agent import RouterAgent
from novel_agent.project_manager import ProjectManager
from novel_agent.web.models.requests import ChatRequest, CreateNovelRequest
from novel_agent.web.routes import chat as chat_routes
from novel_agent.web.routes import novel as novel_routes


@dataclass
class PerfResult:
    name: str
    runs: int
    total_seconds: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    extra: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "runs": self.runs,
            "total_seconds": round(self.total_seconds, 4),
            "avg_ms": round(self.avg_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "extra": self.extra,
        }


class InMemoryChatStore:
    def __init__(self):
        self.saved_states: List[Any] = []
        self._states: Dict[tuple[str, str], Any] = {}

    def load(self, session_id, project_id):
        return self._states.get((project_id, session_id))

    def save(self, state):
        self.saved_states.append(state)
        self._states[(state.project_id, state.session_id)] = state
        return True

    def delete(self, session_id, project_id):
        self._states.pop((project_id, session_id), None)
        return True


class PerfCommunicatorAgent:
    def __init__(self):
        self.conversation_history = []
        self.collected_info = {
            "novel_type": "玄幻",
            "theme": "复仇成长",
            "protagonist": "林渡",
            "plot_idea": "宗门覆灭后的复仇与重建",
            "volume_count": 1,
            "chapters_per_volume": 5,
        }

    def set_router_agent(self, router_agent):
        self.router_agent = router_agent

    def set_knowledge_base(self, knowledge_base):
        self.knowledge_base = knowledge_base

    async def start_conversation(self):
        self.conversation_history.append({"role": "assistant", "content": "opening"})
        return "opening"

    async def chat(self, user_message, runtime_context=None):
        self.conversation_history.append({"role": "user", "content": user_message})
        reply = f"echo:{user_message}"
        self.conversation_history.append({"role": "assistant", "content": reply})
        return {
            "reply": reply,
            "is_complete": False,
            "collected_info": self.collected_info,
        }


class PerfRouter:
    async def analyze_intent(self, message):
        class _Intent:
            primary_intent = type("_Value", (), {"value": "create_novel"})()
            confidence = 0.95

        return _Intent()

    async def route_and_respond(self, message, context=None):
        return {
            "response": "已切换到创作协调器并开始执行。",
            "routed_to": "Coordinator",
            "delegated_result": {
                "agent_name": "Coordinator",
                "action": "create_novel",
                "params": dict((context or {}).get("creation_requirements") or {}),
            },
            "routing_info": {"steps": []},
        }


class PerfFormalCoordinator:
    def __init__(self, pm: ProjectManager, project_dir: Path):
        self.project_manager = pm
        self.project_dir = project_dir
        self.progress_callback = None
        self.project = None

    async def create_novel(self, *args, **kwargs):
        raise AssertionError("/novel/create perf path should use formal router execution")

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
        self.project_manager.save_project_data(
            "outline",
            [{"chapter_number": 1, "title": "第1章 旧城归来", "summary": "林渡回到旧城。", "content": "第1章正文"}],
        )
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
        file_path.write_text("\n\n".join(str(chapter.get("content") or "") for chapter in chapters), encoding="utf-8")


def _percentile(data: List[float], ratio: float) -> float:
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    ordered = sorted(data)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[idx]


def _summarize(name: str, durations: Iterable[float], extra: Dict[str, Any]) -> PerfResult:
    values = list(durations)
    return PerfResult(
        name=name,
        runs=len(values),
        total_seconds=sum(values),
        avg_ms=(sum(values) / len(values) * 1000) if values else 0.0,
        p50_ms=_percentile(values, 0.50) * 1000,
        p95_ms=_percentile(values, 0.95) * 1000,
        min_ms=(min(values) * 1000) if values else 0.0,
        max_ms=(max(values) * 1000) if values else 0.0,
        extra=extra,
    )


async def _bench_create_session_burst() -> PerfResult:
    store = InMemoryChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    async def create_once():
        start = time.perf_counter()
        response = await chat_routes.create_chat_session()
        elapsed = time.perf_counter() - start
        payload = json.loads(response.body.decode("utf-8"))
        return elapsed, payload["session_id"]

    with patch("novel_agent.agents.get_chat_session_store", lambda: store), patch(
        "novel_agent.project_manager.get_project_manager",
        lambda: type("_PM", (), {"current_project_id": "proj-test"})(),
    ):
        pairs = await asyncio.gather(*[create_once() for _ in range(20)])

    durations = [item[0] for item in pairs]
    session_ids = [item[1] for item in pairs]
    return _summarize(
        "create_chat_session_burst",
        durations,
        {"unique_session_ids": len(set(session_ids)), "requested": len(session_ids)},
    )


async def _bench_same_session_chat_sequential() -> PerfResult:
    store = InMemoryChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    async def send_once(index: int):
        start = time.perf_counter()
        response = await chat_routes.chat(ChatRequest(message=f"hello-{index}", session_id="copilot"))
        elapsed = time.perf_counter() - start
        payload = json.loads(response.body.decode("utf-8"))
        return elapsed, payload["reply"]

    with patch("novel_agent.agents.CommunicatorAgent", PerfCommunicatorAgent), patch(
        "novel_agent.agents.get_chat_session_store",
        lambda: store,
    ), patch(
        "novel_agent.project_manager.get_project_manager",
        lambda: type("_PM", (), {"current_project_id": "proj-test"})(),
    ), patch("novel_agent.web.routes.chat.get_router_agent", lambda: None), patch(
        "novel_agent.prompts.check_user_input_security",
        lambda message: (True, message),
    ), patch("novel_agent.prompts.get_security_response", lambda: "blocked"):
        pairs = [await send_once(i) for i in range(50)]

    return _summarize(
        "same_session_chat_sequential",
        [item[0] for item in pairs],
        {"saved_states": len(store.saved_states)},
    )


async def _bench_same_session_chat_concurrent() -> PerfResult:
    store = InMemoryChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    async def send_once(index: int):
        start = time.perf_counter()
        response = await chat_routes.chat(ChatRequest(message=f"concurrent-{index}", session_id="copilot"))
        elapsed = time.perf_counter() - start
        payload = json.loads(response.body.decode("utf-8"))
        return elapsed, payload["reply"]

    with patch("novel_agent.agents.CommunicatorAgent", PerfCommunicatorAgent), patch(
        "novel_agent.agents.get_chat_session_store",
        lambda: store,
    ), patch(
        "novel_agent.project_manager.get_project_manager",
        lambda: type("_PM", (), {"current_project_id": "proj-test"})(),
    ), patch("novel_agent.web.routes.chat.get_router_agent", lambda: None), patch(
        "novel_agent.prompts.check_user_input_security",
        lambda message: (True, message),
    ), patch("novel_agent.prompts.get_security_response", lambda: "blocked"):
        pairs = await asyncio.gather(*[send_once(i) for i in range(20)])

    return _summarize(
        "same_session_chat_concurrent",
        [item[0] for item in pairs],
        {"saved_states": len(store.saved_states)},
    )


async def _bench_multi_session_chat_concurrent() -> PerfResult:
    store = InMemoryChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    async def send_once(index: int):
        session_id = f"copilot_{index}"
        start = time.perf_counter()
        response = await chat_routes.chat(ChatRequest(message=f"session-{index}", session_id=session_id))
        elapsed = time.perf_counter() - start
        payload = json.loads(response.body.decode("utf-8"))
        return elapsed, payload["reply"], session_id

    with patch("novel_agent.agents.CommunicatorAgent", PerfCommunicatorAgent), patch(
        "novel_agent.agents.get_chat_session_store",
        lambda: store,
    ), patch(
        "novel_agent.project_manager.get_project_manager",
        lambda: type("_PM", (), {"current_project_id": "proj-test"})(),
    ), patch("novel_agent.web.routes.chat.get_router_agent", lambda: None), patch(
        "novel_agent.prompts.check_user_input_security",
        lambda message: (True, message),
    ), patch("novel_agent.prompts.get_security_response", lambda: "blocked"):
        pairs = await asyncio.gather(*[send_once(i) for i in range(20)])

    return _summarize(
        "multi_session_chat_concurrent",
        [item[0] for item in pairs],
        {
            "unique_sessions": len({item[2] for item in pairs}),
            "saved_states": len(store.saved_states),
        },
    )


async def _bench_multi_session_mixed_ops() -> PerfResult:
    store = InMemoryChatStore()
    chat_routes.chat_sessions.clear()
    chat_routes._ACTIVE_WORKFLOW_RUNS.clear()

    async def worker(index: int):
        session_id = f"mix_{index}"
        step_durations: List[float] = []

        start = time.perf_counter()
        await chat_routes.create_chat_session(session_id=session_id)
        step_durations.append(time.perf_counter() - start)

        start = time.perf_counter()
        await chat_routes.chat(ChatRequest(message=f"hello-{index}", session_id=session_id))
        step_durations.append(time.perf_counter() - start)

        if index % 2 == 0:
            start = time.perf_counter()
            await chat_routes.reset_chat(session_id=session_id)
            step_durations.append(time.perf_counter() - start)

        return step_durations, session_id

    with patch("novel_agent.agents.CommunicatorAgent", PerfCommunicatorAgent), patch(
        "novel_agent.agents.get_chat_session_store",
        lambda: store,
    ), patch(
        "novel_agent.project_manager.get_project_manager",
        lambda: type("_PM", (), {"current_project_id": "proj-test"})(),
    ), patch("novel_agent.web.routes.chat.get_router_agent", lambda: None), patch(
        "novel_agent.prompts.check_user_input_security",
        lambda message: (True, message),
    ), patch("novel_agent.prompts.get_security_response", lambda: "blocked"):
        pairs = await asyncio.gather(*[worker(i) for i in range(12)])

    flat = [duration for item, _ in pairs for duration in item]
    reset_count = sum(1 for _, session_id in pairs if int(session_id.split("_")[-1]) % 2 == 0)
    return _summarize(
        "multi_session_mixed_ops",
        flat,
        {
            "workers": len(pairs),
            "resets": reset_count,
            "saved_states": len(store.saved_states),
        },
    )


async def _bench_routed_chat_formal_create() -> PerfResult:
    with TemporaryDirectory() as td:
        pm = ProjectManager(data_dir=Path(td) / "data")
        coordinator = PerfFormalCoordinator(pm=pm, project_dir=pm._get_project_dir(pm.current_project_id))
        router = RouterAgent(coordinator=coordinator)
        request = CreateNovelRequest(
            novel_type="玄幻",
            theme="复仇成长",
            plot_idea="宗门覆灭后的复仇与重建",
            volume_count=1,
            chapters_per_volume=1,
            session_id="copilot",
        )

        async def run_once():
            start = time.perf_counter()
            response = await novel_routes.create_novel(request)
            chunks = []
            async for raw in response.body_iterator:
                chunks.append(raw)
            elapsed = time.perf_counter() - start
            return elapsed, len(chunks), pm.load_project_state("task_pool", default={})

        with patch("novel_agent.web.routes.novel.get_coordinator", lambda: coordinator), patch(
            "novel_agent.web.routes.novel.get_router_agent",
            lambda: router,
        ), patch("novel_agent.web.routes.novel.get_project_manager", lambda: pm), patch(
            "novel_agent.project_manager.get_project_manager",
            lambda: pm,
        ), patch("novel_agent.web.routes.novel.get_chat_session_store", lambda: InMemoryChatStore()):
            pairs = [await run_once() for _ in range(10)]

    return _summarize(
        "formal_create_route_smoke",
        [item[0] for item in pairs],
        {
            "avg_sse_chunks": round(sum(item[1] for item in pairs) / len(pairs), 2),
            "task_pool_source": pairs[-1][2].get("metadata", {}).get("source", "") if pairs else "",
        },
    )


def _render_markdown(results: List[PerfResult]) -> str:
    lines = [
        "# Local Performance Smoke Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        "- Scope: 本地编排与会话层开销，不包含真实 LLM 网络耗时",
        "",
        "| Scenario | Runs | Avg ms | P50 ms | P95 ms | Min ms | Max ms | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in results:
        notes = ", ".join(f"{key}={value}" for key, value in item.extra.items())
        lines.append(
            f"| {item.name} | {item.runs} | {item.avg_ms:.2f} | {item.p50_ms:.2f} | {item.p95_ms:.2f} | {item.min_ms:.2f} | {item.max_ms:.2f} | {notes} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "- 这些数据用于观察最近重构是否显著放大本地 orchestration overhead。",
            "- 如需真实性能结论，下一步应在真实 API / 前端 / 多 session 环境下做端到端压测。",
        ]
    )
    return "\n".join(lines)


async def main() -> int:
    results = [
        await _bench_create_session_burst(),
        await _bench_same_session_chat_sequential(),
        await _bench_same_session_chat_concurrent(),
        await _bench_multi_session_chat_concurrent(),
        await _bench_multi_session_mixed_ops(),
        await _bench_routed_chat_formal_create(),
    ]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = Path(".omx") / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"perf-chat-smoke-{timestamp}.json"
    md_path = report_dir / f"perf-chat-smoke-{timestamp}.md"

    json_path.write_text(
        json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(results), encoding="utf-8")

    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "results": [item.to_dict() for item in results]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
