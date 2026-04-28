"""
真实 API 环境端到端烟雾脚本（最小创作链）。

说明：
- 启动真实本地服务
- 创建/切换项目
- 建立 WebSocket 订阅 `novel_progress`
- 调用 `/api/v1/create` 触发最小创作链
- 采集 SSE / WebSocket / status 轮询结果
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
import websockets


SERVER_SCRIPT = ROOT_DIR / ".omx" / "reports" / "e2e_server.py"
SERVER_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"


def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _wait_until_ready(base_url: str, timeout_seconds: float = 40.0) -> None:
    deadline = time.perf_counter() + timeout_seconds
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.perf_counter() < deadline:
            try:
                response = await client.get(f"{base_url}/")
                if response.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError("local service did not become ready in time")


async def _collect_ws(ws_url: str, stop_event: asyncio.Event, sink: List[Dict[str, Any]]) -> None:
    try:
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=10) as websocket:
            first = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            sink.append({"type": first.get("type"), "payload_keys": list((first.get("payload") or {}).keys())})
            await websocket.send(json.dumps({"action": "subscribe", "topic": "novel_progress"}, ensure_ascii=False))
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                payload = json.loads(raw)
                sink.append(
                    {
                        "type": payload.get("type"),
                        "payload_keys": list((payload.get("payload") or {}).keys()),
                    }
                )
                if len(sink) >= 40:
                    break
    except Exception as exc:
        sink.append({"type": "ws_error", "error": str(exc)})


async def _poll_status(base_url: str, stop_event: asyncio.Event, sink: List[Dict[str, Any]], session_id: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        while not stop_event.is_set():
            try:
                response = await client.get(f"/api/v1/chat/workflow-status?session_id={session_id}")
                payload = response.json()
                sink.append(
                    {
                        "status": ((payload.get("workflow") or {}).get("status") or ""),
                        "current_agent": ((payload.get("workflow") or {}).get("current_agent") or ""),
                    }
                )
            except Exception as exc:
                sink.append({"status": "poll_error", "error": str(exc)})
            await asyncio.sleep(2.0)


async def main(timeout_seconds: int = 180) -> int:
    if not SERVER_PYTHON.exists() or not SERVER_SCRIPT.exists():
        raise RuntimeError("missing local server runtime prerequisites")

    port = _pick_port()
    base_url = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/ws"
    process = subprocess.Popen(
        [str(SERVER_PYTHON), str(SERVER_SCRIPT), str(port)],
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        await _wait_until_ready(base_url)
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            projects_resp = await client.get("/api/v1/projects")
            projects_payload = projects_resp.json()
            before_project_count = len(projects_payload.get("projects", []))

            created_projects: List[str] = []
            for name in ["E2E压力A", "E2E压力B"]:
                response = await client.post("/api/v1/projects", json={"name": name, "description": "real api smoke"})
                payload = response.json()
                created_projects.append(((payload.get("project") or {}).get("id") or ""))

            switch_payloads = []
            for project_id in created_projects:
                if project_id:
                    switch_resp = await client.post(f"/api/v1/projects/{project_id}/switch")
                    switch_payloads.append(switch_resp.json())

            session_id = f"realapi_{int(time.time())}"
            create_payload = {
                "novel_type": "玄幻",
                "theme": "复仇成长",
                "requirements": "压测烟雾用最小任务",
                "protagonist": "林渡",
                "plot_idea": "宗门覆灭后的复仇与重建",
                "volume_count": 1,
                "chapters_per_volume": 1,
                "session_id": session_id,
            }

            stop_event = asyncio.Event()
            ws_sink: List[Dict[str, Any]] = []
            status_sink: List[Dict[str, Any]] = []
            ws_task = asyncio.create_task(_collect_ws(ws_url, stop_event, ws_sink))
            poll_task = asyncio.create_task(_poll_status(base_url, stop_event, status_sink, session_id))

            sse_chunks: List[Dict[str, Any]] = []
            create_started = time.perf_counter()
            create_result = {"completed": False, "timed_out": False, "error": ""}
            try:
                async with client.stream("POST", "/api/v1/create", json=create_payload, timeout=timeout_seconds) as response:
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            payload = {"raw": raw}
                        sse_chunks.append(payload)
                        stage = str(payload.get("stage") or "").strip()
                        if stage in {"completed", "failed", "cancelled"}:
                            create_result["completed"] = True
                            break
            except httpx.TimeoutException:
                create_result["timed_out"] = True
            except Exception as exc:
                create_result["error"] = str(exc)
            finally:
                create_result["duration_seconds"] = round(time.perf_counter() - create_started, 3)
                stop_event.set()
                await asyncio.gather(ws_task, poll_task, return_exceptions=True)

            final_status = await client.get(f"/api/v1/chat/workflow-status?session_id={session_id}")
            final_status_payload = final_status.json()
            projects_after = await client.get("/api/v1/projects")
            after_project_count = len(projects_after.json().get("projects", []))

        report_dir = ROOT_DIR / ".omx" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = report_dir / f"e2e-real-api-smoke-{timestamp}.json"
        md_path = report_dir / f"e2e-real-api-smoke-{timestamp}.md"

        report = {
            "base_url": base_url,
            "timeout_seconds": timeout_seconds,
            "project_count_before": before_project_count,
            "project_count_after": after_project_count,
            "created_projects": created_projects,
            "switch_results": switch_payloads,
            "create_payload": {k: v for k, v in create_payload.items() if k != "requirements"},
            "create_result": create_result,
            "sse_chunk_count": len(sse_chunks),
            "sse_preview": sse_chunks[:10],
            "ws_messages": ws_sink[:20],
            "status_samples": status_sink[:20],
            "final_workflow": final_status_payload.get("workflow"),
            "final_reply": final_status_payload.get("reply"),
        }

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_lines = [
            "# Real API E2E Smoke Report",
            "",
            f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"- Base URL: {base_url}",
            f"- Timeout: {timeout_seconds}s",
            "",
            f"- project_count_before: {before_project_count}",
            f"- project_count_after: {after_project_count}",
            f"- created_projects: {created_projects}",
            f"- create_completed: {create_result.get('completed')}",
            f"- create_timed_out: {create_result.get('timed_out')}",
            f"- create_error: {create_result.get('error')}",
            f"- create_duration_seconds: {create_result.get('duration_seconds')}",
            f"- sse_chunk_count: {len(sse_chunks)}",
            "",
            "## Final Workflow",
            "```json",
            json.dumps(final_status_payload.get("workflow"), ensure_ascii=False, indent=2),
            "```",
            "",
            "## WebSocket Preview",
            "```json",
            json.dumps(ws_sink[:10], ensure_ascii=False, indent=2),
            "```",
        ]
        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        print(
            json.dumps(
                {
                    "json_report": str(json_path.relative_to(ROOT_DIR)),
                    "markdown_report": str(md_path.relative_to(ROOT_DIR)),
                    "create_result": create_result,
                    "sse_chunk_count": len(sse_chunks),
                    "final_workflow_status": ((final_status_payload.get("workflow") or {}).get("status") or ""),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    timeout_value = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    raise SystemExit(asyncio.run(main(timeout_value)))
