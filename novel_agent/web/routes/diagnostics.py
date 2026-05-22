"""Diagnostics and support-log routes."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from ...constants import get_app_root, get_data_dir
from ...utils.log_sanitizer import sanitize_for_log

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_LOG_BYTES = 512 * 1024
MAX_SUPPORT_LOG_FILES = 8
SUPPORT_EMAIL = "swjiarui@126.com"
DEFAULT_LOG_SCOPE = "session"
DEFAULT_LOG_DETAIL = "compact"

_LOG_TIMESTAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3,6})?")
_LOG_LEVEL_RE = re.compile(r"\s-\s(?P<logger>.*?)\s-\s(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s-\s")
_STARTUP_MARKER_RE = re.compile(
    r"(Started server process|数据目录写入权限检查通过|ChromaDB导入成功)"
)
_COMPACT_DROP_RE = re.compile(
    r"("
    r"uvicorn\.access|"
    r"\b(?:GET|POST|OPTIONS)\s+/(?:api/(?:v1/)?(?:status|app/runtime|window-heartbeat)|static/)|"
    r"/api/(?:v1/)?(?:status|app/runtime|window-heartbeat)|"
    r"/static/|"
    r"window-heartbeat|"
    r"WebSocket (?:connected|disconnected|accepted|closed)|"
    r"connection (?:open|closed)|"
    r"HTTP Request: (?:GET|POST|OPTIONS) .+ \"HTTP/[^\"]+ 2\d\d"
    r")",
    re.IGNORECASE,
)
_COMPACT_KEEP_RE = re.compile(
    r"("
    r"Started server process|数据目录写入权限检查通过|启动|startup|"
    r"配置验证|API配置|api config|active config|Synced active config|"
    r"CoverImages|CoverPrompt|封面|image generation|"
    r"Responses|Anthropic|Router|空响应|timeout|超时|"
    r"Skills? 目录|skills|知识库向量|knowledge base|embedding provider|"
    r"HTTP (?:4\d\d|5\d\d)|status(?:_code)?[=: ](?:4\d\d|5\d\d)|"
    r"403|404|429|500|502|503|504|524|"
    r"fallback|retry|降级|重试|失败|错误|blocked|origin_gateway_timeout"
    r")",
    re.IGNORECASE,
)
_IMPORTANT_LEVELS = {"WARNING", "ERROR", "CRITICAL"}


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


def _read_tail_text(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
        data = handle.read(max_bytes)
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = f"[仅显示最后 {max_bytes} 字节，原始大小 {size} 字节]\n{text}"
    return text


def _tail_text(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    text = _read_tail_text(path, max_bytes=max_bytes)
    return str(sanitize_for_log(text))


def _parse_log_timestamp(line: str) -> datetime | None:
    match = _LOG_TIMESTAMP_RE.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _parse_request_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _latest_session_start(raw_texts: Iterable[str]) -> datetime | None:
    latest: datetime | None = None
    for text in raw_texts:
        for line in text.splitlines():
            if not _STARTUP_MARKER_RE.search(line):
                continue
            timestamp = _parse_log_timestamp(line)
            if timestamp and (latest is None or timestamp > latest):
                latest = timestamp
    return latest


def _filter_log_text(text: str, *, start_at: datetime | None, end_at: datetime | None) -> str:
    if start_at is None and end_at is None:
        return text

    kept: list[str] = []
    include_current = False
    for line in text.splitlines():
        timestamp = _parse_log_timestamp(line)
        if timestamp is not None:
            include_current = True
            if start_at is not None and timestamp < start_at:
                include_current = False
            if end_at is not None and timestamp > end_at:
                include_current = False
        if include_current:
            kept.append(line)
    return "\n".join(kept)


def _normalize_log_detail(detail: str | None) -> str:
    normalized = str(detail or DEFAULT_LOG_DETAIL).strip().lower()
    if normalized not in {"compact", "full"}:
        return DEFAULT_LOG_DETAIL
    return normalized


def _split_log_entries(text: str) -> list[list[str]]:
    entries: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if _parse_log_timestamp(line) is not None and current:
            entries.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(current)
    return entries


def _log_entry_level(entry: str) -> str:
    match = _LOG_LEVEL_RE.search(entry)
    return match.group("level") if match else ""


def _should_keep_compact_entry(entry: str) -> bool:
    if not entry.strip():
        return False
    level = _log_entry_level(entry)
    if level in _IMPORTANT_LEVELS:
        return True
    if _COMPACT_KEEP_RE.search(entry):
        return True
    if not _parse_log_timestamp(entry.splitlines()[0] if entry.splitlines() else ""):
        return not _COMPACT_DROP_RE.search(entry)
    if _COMPACT_DROP_RE.search(entry):
        return False
    return False


def _compact_log_text(text: str) -> tuple[str, int]:
    entries = _split_log_entries(text)
    kept: list[str] = []
    omitted = 0
    for entry_lines in entries:
        entry = "\n".join(entry_lines)
        if _should_keep_compact_entry(entry):
            kept.append(entry)
        else:
            omitted += len(entry_lines)
    return "\n".join(kept), omitted


def _resolve_log_time_window(
    scope: str = DEFAULT_LOG_SCOPE,
    *,
    start: str | None = None,
    end: str | None = None,
    raw_texts: Iterable[str] | None = None,
) -> tuple[str, datetime | None, datetime | None, str]:
    normalized_scope = str(scope or DEFAULT_LOG_SCOPE).strip().lower()
    if normalized_scope not in {"session", "24h", "range", "all"}:
        normalized_scope = DEFAULT_LOG_SCOPE

    end_at = _parse_request_datetime(end)
    if normalized_scope == "all":
        return normalized_scope, None, end_at, "全部可用日志"

    if normalized_scope == "24h":
        final_end = end_at or datetime.now()
        start_at = final_end - timedelta(hours=24)
        return normalized_scope, start_at, end_at, "最近 24 小时"

    if normalized_scope == "range":
        start_at = _parse_request_datetime(start)
        label = "自定义时间段"
        return normalized_scope, start_at, end_at, label

    start_at = _latest_session_start(raw_texts or [])
    if start_at is None:
        return normalized_scope, None, end_at, "本次启动（未找到启动切分点，已导出可用日志）"
    return normalized_scope, start_at, end_at, f"本次启动（从 {start_at.strftime('%Y-%m-%d %H:%M:%S')} 起）"


def build_support_log_text(
    files: Iterable[Path] | None = None,
    *,
    scope: str = DEFAULT_LOG_SCOPE,
    start: str | None = None,
    end: str | None = None,
    detail: str = DEFAULT_LOG_DETAIL,
) -> str:
    selected = list(files) if files is not None else _candidate_log_files()
    selected = selected[:MAX_SUPPORT_LOG_FILES]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_entries: list[tuple[Path, str]] = []
    for path in selected:
        try:
            raw_entries.append((path, _read_tail_text(path)))
        except Exception as exc:
            logger.warning("Failed to read support log %s: %s", path, exc)
            raw_entries.append((path, f"读取失败: {exc}"))

    resolved_scope, start_at, end_at, range_label = _resolve_log_time_window(
        scope,
        start=start,
        end=end,
        raw_texts=[text for _, text in raw_entries],
    )
    resolved_detail = _normalize_log_detail(detail)
    detail_label = "精简日志（隐藏心跳、静态资源和常规 INFO）" if resolved_detail == "compact" else "完整日志"
    lines = [
        "山海·云烟 支持日志",
        f"导出时间: {now}",
        f"日志范围: {range_label}",
        f"日志模式: {detail_label}",
        f"支持邮箱: {SUPPORT_EMAIL}",
        f"数据目录: {get_data_dir()}",
        f"应用目录: {get_app_root()}",
        "",
    ]

    if not selected:
        lines.append("未找到可导出的日志文件。")
        return "\n".join(lines)

    matched_count = 0
    omitted_count = 0
    for path, raw_text in raw_entries:
        try:
            stat = path.stat()
            filtered_text = _filter_log_text(raw_text, start_at=start_at, end_at=end_at)
            if resolved_detail == "compact":
                filtered_text, omitted = _compact_log_text(filtered_text)
                omitted_count += omitted
            if (start_at is not None or end_at is not None) and not filtered_text.strip():
                continue
            matched_count += 1
            lines.extend([
                "=" * 80,
                f"文件: {path}",
                f"大小: {stat.st_size} 字节",
                f"修改时间: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
                "-" * 80,
                str(sanitize_for_log(filtered_text)),
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
    if matched_count == 0:
        if resolved_detail == "compact":
            lines.append("所选日志范围内未找到精简后需要导出的关键日志；如需排查常规流程，请切换为完整日志。")
        else:
            lines.append("所选日志范围内未找到可导出的日志内容。")
    if resolved_scope == "range" and start_at is None and end_at is None:
        lines.append("提示：自定义时间段未填写起止时间，已退回为可用日志范围。")
    if resolved_detail == "compact" and omitted_count:
        lines.append(f"提示：精简模式已隐藏 {omitted_count} 行常规日志。需要完整上下文时请选择完整日志。")
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
async def get_support_logs(
    scope: str = DEFAULT_LOG_SCOPE,
    start: str | None = None,
    end: str | None = None,
    detail: str = DEFAULT_LOG_DETAIL,
):
    return PlainTextResponse(
        build_support_log_text(scope=scope, start=start, end=end, detail=detail),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/diagnostics/logs/export")
async def export_support_logs(
    scope: str = DEFAULT_LOG_SCOPE,
    start: str | None = None,
    end: str | None = None,
    detail: str = DEFAULT_LOG_DETAIL,
):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="shanhai_logs_{timestamp}.txt"'
    }
    return PlainTextResponse(
        build_support_log_text(scope=scope, start=start, end=end, detail=detail),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )
