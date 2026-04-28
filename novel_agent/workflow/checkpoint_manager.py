"""工作流检查点持久化管理。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class CheckpointManager:
    """管理 workflow checkpoint 文件的读写与 payload 更新。"""

    def __init__(
        self,
        *,
        project_dir_provider: Callable[[], Path],
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.project_dir_provider = project_dir_provider
        self.now_provider = now_provider or datetime.now

    def checkpoint_path(self) -> Path:
        return Path(self.project_dir_provider()) / "checkpoint.json"

    def load_payload(self) -> Optional[Dict[str, Any]]:
        checkpoint_file = self.checkpoint_path()
        if not checkpoint_file.exists():
            return None
        try:
            payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning(f"Failed to load checkpoint: {exc}")
            return None

    def save_payload(self, payload: Optional[Dict[str, Any]], *, enabled: bool = True) -> bool:
        """问题10修复：使用原子写入避免检查点文件损坏。"""
        if not enabled or not isinstance(payload, dict) or not payload:
            return False
        try:
            from ..utils.atomic_write import atomic_write_json
            checkpoint_file = self.checkpoint_path()
            old_content = checkpoint_file.read_text(encoding="utf-8") if checkpoint_file.exists() else None
            atomic_write_json(
                checkpoint_file,
                payload,
                old_content=old_content,
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to save checkpoint: {exc}")
            return False

    def build_updated_payload(
        self,
        existing_payload: Optional[Dict[str, Any]],
        *,
        state_value: Optional[str] = None,
        current_chapter: Optional[int] = None,
        add_stage: Optional[str] = None,
        error_info: Optional[str] = None,
        project_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(existing_payload or {})
        payload.setdefault("state", "idle")
        payload.setdefault("current_chapter", 0)
        payload.setdefault("completed_stages", [])
        payload.setdefault("project_data", {})
        payload.setdefault("last_updated", self.now_provider().isoformat())
        payload.setdefault("error_info", None)

        if state_value:
            payload["state"] = str(state_value)
        if current_chapter is not None:
            payload["current_chapter"] = int(current_chapter)
        if add_stage:
            completed_stages = list(payload.get("completed_stages") or [])
            if add_stage not in completed_stages:
                completed_stages.append(add_stage)
            payload["completed_stages"] = completed_stages
        if error_info:
            payload["error_info"] = error_info
        payload["last_updated"] = self.now_provider().isoformat()
        payload["project_data"] = dict(project_data or {})
        return payload
