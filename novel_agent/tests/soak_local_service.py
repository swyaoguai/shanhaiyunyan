"""
本地服务 10 分钟 soak test。

说明：
- 启动真实 FastAPI 服务
- 持续对本地 HTTP / WebSocket 做轻量长时压测
- 不触发真实 LLM 外部调用，聚焦服务稳定性、会话管理、锁与 WS 基础链路
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from collections import defaultdict
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
class OpStat:
    name: str
    count: int = 0
    failures: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, duration_ms: float, ok: bool) -> None:
        self.count += 1
        if not ok:
            self.failures += 1
        self.total_ms += duration_ms
        if duration_ms > self.max_ms:
            self.max_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        avg_ms = self.total_ms / self.count if self.count else 0.0
        return {
            "name": self.name,
            "count": self.count,
            "failures": self.failures,
            "avg_ms": round(avg_ms, 3),
            "max_ms": round(self.max_ms, 3),
        }


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


async def _timed_request(
    client: httpx.AsyncClient,
    stats: Dict[str, OpStat],
    name: str,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    started = time.perf_counter()
    try:
        response = await client.request(method, path, **kwargs)
        ok = response.status_code < 500
        return response
    except Exception:
        ok = False
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        stats[name].add(duration_ms, ok)


async def _status_worker(
    *,
    client: httpx.AsyncClient,
    stats: Dict[str, OpStat],
    stop_at: float,
) -> None:
    while time.perf_counter() < stop_at:
        try:
            await _timed_request(client, stats, "status", "GET", "/api/v1/status")
            await _timed_request(client, stats, "projects", "GET", "/api/v1/projects")
        except Exception:
            pass
        await asyncio.sleep(1.0)


async def _session_worker(
    *,
    client: httpx.AsyncClient,
    stats: Dict[str, OpStat],
    stop_at: float,
    prefix: str,
) -> None:
    index = 0
    while time.perf_counter() < stop_at:
        session_id = f"{prefix}_{index}"
        index += 1
        try:
            await _timed_request(client, stats, "chat_sessions_list", "GET", "/api/v1/chat/sessions")
            await _timed_request(client, stats, "chat_session_create", "POST", f"/api/v1/chat/sessions?session_id={session_id}")
            await _timed_request(client, stats, "chat_history", "GET", f"/api/v1/chat/history?session_id={session_id}")
            await _timed_request(client, stats, "chat_workflow_status", "GET", f"/api/v1/chat/workflow-status?session_id={session_id}")
            await _timed_request(client, stats, "chat_reset", "POST", f"/api/v1/chat/reset?session_id={session_id}")
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def _websocket_worker(
    *,
    ws_url: str,
    stats: Dict[str, OpStat],
    stop_at: float,
) -> None:
    while time.perf_counter() < stop_at:
        started = time.perf_counter()
        ok = False
        try:
            async with websockets.connect(ws_url, open_timeout=10, close_timeout=10) as websocket:
                raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                payload = json.loads(raw)
                ok = payload.get("type") == "connected"
        except Exception:
            ok = False
        finally:
            stats["websocket_connect"].add((time.perf_counter() - started) * 1000, ok)
        await asyncio.sleep(2.0)


def _render_markdown(
    *,
    duration_seconds: int,
    base_url: str,
    stats: Dict[str, OpStat],
    uptime_seconds: float,
) -> str:
    lines = [
        "# Local Service Soak Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Base URL: {base_url}",
        f"- Target duration: {duration_seconds}s",
        f"- Actual uptime observed: {uptime_seconds:.2f}s",
        "",
        "| Operation | Count | Failures | Avg ms | Max ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in sorted(stats):
        item = stats[name]
        avg_ms = item.total_ms / item.count if item.count else 0.0
        lines.append(f"| {name} | {item.count} | {item.failures} | {avg_ms:.2f} | {item.max_ms:.2f} |")
    lines.extend(
        [
            "",
            "## Notes",
            "- 本脚本只覆盖真实本地服务的稳定性，不触发真实 LLM 网络调用。",
            "- 若要继续推进，应在更宽松权限下做真实浏览器与真实 API 的长时端到端压测。",
        ]
    )
    return "\n".join(lines)


async def main(duration_seconds: int = 600) -> int:
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

    started_at = time.perf_counter()
    stats: Dict[str, OpStat] = defaultdict(lambda: OpStat(name=""))
    try:
        await _wait_until_ready(base_url)
        # fill names after first touch
        def _named(name: str) -> OpStat:
            if not stats[name].name:
                stats[name].name = name
            return stats[name]

        # pre-seed expected names for ordered reports
        for name in [
            "status",
            "projects",
            "chat_sessions_list",
            "chat_session_create",
            "chat_history",
            "chat_workflow_status",
            "chat_reset",
            "websocket_connect",
        ]:
            _named(name)

        stop_at = time.perf_counter() + duration_seconds
        async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
            await asyncio.gather(
                _status_worker(client=client, stats=stats, stop_at=stop_at),
                _session_worker(client=client, stats=stats, stop_at=stop_at, prefix="soak_a"),
                _session_worker(client=client, stats=stats, stop_at=stop_at, prefix="soak_b"),
                _websocket_worker(ws_url=ws_url, stats=stats, stop_at=stop_at),
            )

        uptime_seconds = time.perf_counter() - started_at
        report_dir = ROOT_DIR / ".omx" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = report_dir / f"soak-local-service-{timestamp}.json"
        md_path = report_dir / f"soak-local-service-{timestamp}.md"

        json_path.write_text(
            json.dumps(
                {
                    "base_url": base_url,
                    "duration_seconds": duration_seconds,
                    "uptime_seconds": round(uptime_seconds, 3),
                    "stats": {name: item.to_dict() for name, item in stats.items()},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        md_path.write_text(
            _render_markdown(
                duration_seconds=duration_seconds,
                base_url=base_url,
                stats=stats,
                uptime_seconds=uptime_seconds,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "json_report": str(json_path.relative_to(ROOT_DIR)),
                    "markdown_report": str(md_path.relative_to(ROOT_DIR)),
                    "duration_seconds": duration_seconds,
                    "uptime_seconds": round(uptime_seconds, 3),
                    "stats": {name: item.to_dict() for name, item in stats.items()},
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
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    raise SystemExit(asyncio.run(main(duration)))
