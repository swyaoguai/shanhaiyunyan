"""原子写入辅助工具。"""

from __future__ import annotations

import json
from pathlib import Path
from time import time_ns
from typing import Any, Optional
from uuid import uuid4


def build_atomic_temp_path(path: Path) -> Path:
    """为目标路径生成唯一临时文件路径。"""
    unique_suffix = f"{time_ns()}_{uuid4().hex}"
    if path.suffix:
        return path.with_suffix(f"{path.suffix}.tmp.{unique_suffix}")
    return path.with_name(f"{path.name}.tmp.{unique_suffix}")


def atomic_write_text(path: Path, content: str, old_content: Optional[str] = None) -> None:
    """原子写入文本内容，失败时可选回滚。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = build_atomic_temp_path(path)

    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

        if old_content is not None:
            path.write_text(old_content, encoding="utf-8")
        raise


def atomic_write_json(
    path: Path,
    payload: Any,
    old_content: Optional[str] = None,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """原子写入JSON内容，失败时可选回滚。"""
    content = json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, content, old_content=old_content)
