"""Diagnostics and support-log routes."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from ...constants import get_app_root, get_data_dir
from ...utils.log_sanitizer import sanitize_for_log

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_LOG_BYTES = 2 * 1024 * 1024
SUPPORT_EMAIL = "swjiarui@126.com"


def _candidate_log_files() -> List[Path]:
    root = get_app_root()
    data_dir = get_data_dir()
    candidates: List[Path] = [
        root / "agent.log",
        root / "startup_error.txt",
        data_dir / "logs" / "agent.log",
    ]

    for log_dir in (data_dir / "logs", root / "logs", root / "novel_agent" / "logs"):
        if log_dir.exists():
            candidates.extend(path for path in log_dir.rglob("*") if path.is_file())

    seen = set()
    unique: List[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if resolved in seen or not resolved.exists() or not resolved.is_file():
            continue
        seen.add(resolved)
        unique.append(resolved)

    unique.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return unique


def _tail_text(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
        data = handle.read(max_bytes)
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = f"[仅显示最后 {max_bytes} 字节，原始大小 {size} 字节]\n{text}"
    return str(sanitize_for_log(text))


def build_support_log_text(files: Iterable[Path] | None = None) -> str:
    selected = list(files) if files is not None else _candidate_log_files()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "山海·云烟 支持日志",
        f"导出时间: {now}",
        f"支持邮箱: {SUPPORT_EMAIL}",
        f"数据目录: {get_data_dir()}",
        f"应用目录: {get_app_root()}",
        "",
    ]

    if not selected:
        lines.append("未找到可导出的日志文件。")
        return "\n".join(lines)

    for path in selected:
        try:
            stat = path.stat()
            lines.extend([
                "=" * 80,
                f"文件: {path}",
                f"大小: {stat.st_size} 字节",
                f"修改时间: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
                "-" * 80,
                _tail_text(path),
                "",
            ])
        except Exception as exc:
            logger.warning("Failed to read support log %s: %s", path, exc)
            lines.extend([
                "=" * 80,
                f"文件: {path}",
                f"读取失败: {exc}",
                "",
            ])
    return "\n".join(lines)


@router.get("/diagnostics/support-info")
async def get_support_info():
    files = _candidate_log_files()
    return JSONResponse({
        "support_email": SUPPORT_EMAIL,
        "log_count": len(files),
        "logs": [
            {
                "path": str(path),
                "size": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
            for path in files[:20]
        ],
    })


@router.get("/diagnostics/logs")
async def get_support_logs():
    return PlainTextResponse(build_support_log_text(), media_type="text/plain; charset=utf-8")


@router.get("/diagnostics/logs/export")
async def export_support_logs():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="shanhai_logs_{timestamp}.txt"'
    }
    return PlainTextResponse(
        build_support_log_text(),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )
