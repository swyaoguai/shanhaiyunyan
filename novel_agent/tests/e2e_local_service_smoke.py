"""
本地服务近端到端联调烟雾脚本。

说明：
- 启动真实 FastAPI 服务（本地 uvicorn）
- 使用 HTTP + WebSocket 做近端到端联调
- 不依赖真实浏览器，因此适用于当前沙箱/权限限制环境
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
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


@dataclass
class EndpointResult:
    name: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    ok: bool
    notes: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "duration_ms": round(self.duration_ms, 3),
            "ok": self.ok,
            "notes": self.notes,
        }


def _render_markdown(results: List[EndpointResult], websocket_info: Dict[str, Any]) -> str:
    lines = [
        "# Local Service E2E Smoke Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        "- Scope: 真实 FastAPI 服务 + HTTP + WebSocket 联调，不包含真实浏览器自动化",
        "",
        "| Name | Method | Path | Status | Duration ms | OK | Notes |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for item in results:
        notes = ", ".join(f"{key}={value}" for key, value in item.notes.items())
        lines.append(
            f"| {item.name} | {item.method} | {item.path} | {item.status_code} | {item.duration_ms:.2f} | {'✅' if item.ok else '❌'} | {notes} |"
        )
    lines.extend(
        [
            "",
            "## WebSocket",
            f"- connected: {websocket_info.get('connected')}",
            f"- first_message_type: {websocket_info.get('first_message_type')}",
            f"- first_payload_keys: {websocket_info.get('first_payload_keys')}",
        ]
    )
    return "\n".join(lines)


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


async def _call_json(client: httpx.AsyncClient, *, name: str, method: str, path: str, **kwargs) -> EndpointResult:
    started = time.perf_counter()
    response = await client.request(method, path, **kwargs)
    duration_ms = (time.perf_counter() - started) * 1000
    notes: Dict[str, Any] = {}
    try:
        payload = response.json()
        if isinstance(payload, dict):
            notes["keys"] = list(payload.keys())[:6]
            if "count" in payload:
                notes["count"] = payload.get("count")
    except Exception:
        notes["content_length"] = len(response.text or "")
    return EndpointResult(
        name=name,
        method=method,
        path=path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        ok=response.status_code < 400,
        notes=notes,
    )


async def _check_websocket(ws_url: str) -> Dict[str, Any]:
    async with websockets.connect(ws_url, open_timeout=10, close_timeout=10) as websocket:
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        payload = json.loads(raw)
        return {
            "connected": True,
            "first_message_type": payload.get("type"),
            "first_payload_keys": list((payload.get("payload") or {}).keys()),
        }


async def main() -> int:
    if not SERVER_PYTHON.exists():
        raise RuntimeError(f"missing server python: {SERVER_PYTHON}")
    if not SERVER_SCRIPT.exists():
        raise RuntimeError(f"missing server script: {SERVER_SCRIPT}")

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

        results: List[EndpointResult] = []
        async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
            results.append(await _call_json(client, name="root_html", method="GET", path="/"))
            results.append(await _call_json(client, name="status", method="GET", path="/api/v1/status"))
            results.append(await _call_json(client, name="projects", method="GET", path="/api/v1/projects"))
            results.append(await _call_json(client, name="chat_sessions", method="GET", path="/api/v1/chat/sessions"))

            create_session = await _call_json(client, name="create_chat_session", method="POST", path="/api/v1/chat/sessions")
            results.append(create_session)

            # follow-up calls on a real generated session
            create_response = await client.post("/api/v1/chat/sessions")
            create_payload = create_response.json()
            session_id = str(create_payload.get("session_id") or "copilot")

            results.append(await _call_json(client, name="chat_history", method="GET", path=f"/api/v1/chat/history?session_id={session_id}"))
            results.append(await _call_json(client, name="chat_workflow_status", method="GET", path=f"/api/v1/chat/workflow-status?session_id={session_id}"))
            results.append(await _call_json(client, name="reset_chat", method="POST", path=f"/api/v1/chat/reset?session_id={session_id}"))

        websocket_info = await _check_websocket(ws_url)

        report_dir = ROOT_DIR / ".omx" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = report_dir / f"e2e-local-service-smoke-{timestamp}.json"
        md_path = report_dir / f"e2e-local-service-smoke-{timestamp}.md"
        json_path.write_text(
            json.dumps(
                {
                    "base_url": base_url,
                    "results": [item.to_dict() for item in results],
                    "websocket": websocket_info,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        md_path.write_text(_render_markdown(results, websocket_info), encoding="utf-8")

        print(
            json.dumps(
                {
                    "json_report": str(json_path.relative_to(ROOT_DIR)),
                    "markdown_report": str(md_path.relative_to(ROOT_DIR)),
                    "websocket": websocket_info,
                    "results": [item.to_dict() for item in results],
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
    raise SystemExit(asyncio.run(main()))
