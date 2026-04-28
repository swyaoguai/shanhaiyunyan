"""工作流记忆同步与诊断。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class MemorySyncManager:
    """封装记忆契约、同步事件、快照导出与诊断。"""

    def __init__(
        self,
        *,
        project_dir_provider: Callable[[], Path],
        project_scope_provider: Callable[[], str],
        project_payload_provider: Callable[[], Dict[str, Any]],
        memory_manager: Any,
        contract_version_provider: Callable[[], str],
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.project_dir_provider = project_dir_provider
        self.project_scope_provider = project_scope_provider
        self.project_payload_provider = project_payload_provider
        self.memory_manager = memory_manager
        self.contract_version_provider = contract_version_provider
        self.now_provider = now_provider or datetime.now
        # 问题11修复：添加文件写入锁，防止并发写入丢失事件
        self._write_lock = asyncio.Lock()

    def _now_iso(self) -> str:
        return self.now_provider().isoformat()

    def build_contract(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version_provider(),
            "updated_at": self._now_iso(),
            "source_of_truth": {
                "chapter_facts": "KnowledgeBase",
                "session_state": "SessionStore",
                "workflow_state": "ContextManager+Checkpoint",
                "long_term_preferences_and_summary": "MemoryManager(Wensi)",
            },
            "conflict_resolution": {
                "priority_order": [
                    "KnowledgeBase",
                    "SessionStore",
                    "ContextManager+Checkpoint",
                    "MemoryManager(Wensi)",
                ],
                "default_strategy": "last_write_wins_with_priority",
                "versioning": "timestamp+contract_version",
                "notes": "高优先级源覆盖低优先级源；同优先级冲突按最近更新时间合并。",
            },
        }

    def meta_file(self) -> Path:
        return Path(self.project_dir_provider()) / "memory_sync_meta.json"

    def snapshot_file(self) -> Path:
        return Path(self.project_dir_provider()) / "memory_snapshot.json"

    async def append_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """问题11修复：使用 asyncio.Lock 防止并发写入丢失事件。"""
        try:
            async with self._write_lock:
                path = self.meta_file()
                payload = {
                    "contract": self.build_contract(),
                    "project": self.project_payload_provider(),
                    "project_scope": self.project_scope_provider(),
                    "updated_at": self._now_iso(),
                    "events": [],
                }

                if path.exists():
                    try:
                        existing = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(existing, dict):
                            payload.update(existing)
                            payload["contract"] = self.build_contract()
                            payload["updated_at"] = self._now_iso()
                    except Exception:
                        pass

                payload.setdefault("events", [])
                payload["events"].append(
                    {
                        "type": event_type,
                        "time": self._now_iso(),
                        "data": data or {},
                    }
                )
                if len(payload["events"]) > 300:
                    payload["events"] = payload["events"][-300:]

                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to append memory event: {exc}")

    async def ensure_memory_agent(self, agent_ids: Dict[str, str], agent_type: str) -> Optional[str]:
        project_scope = self.project_scope_provider() or "default"
        scoped_key = f"{project_scope}:{agent_type}"
        if scoped_key in agent_ids:
            return agent_ids[scoped_key]

        if not self.memory_manager.wensi_service.is_available:
            await self.append_event(
                "memory_agent_skipped",
                {"agent_type": agent_type, "reason": "wensi_unavailable"},
            )
            return None

        try:
            agent_name = f"novel_{project_scope}_{agent_type}".lower()
            agent_id = await self.memory_manager.wensi_service.create_agent(name=agent_name)
            if agent_id:
                agent_ids[scoped_key] = agent_id
                await self.append_event(
                    "memory_agent_created",
                    {
                        "agent_type": agent_type,
                        "project_scope": project_scope,
                        "agent_id": agent_id,
                    },
                )
                return agent_id
            await self.append_event(
                "memory_agent_create_failed",
                {"agent_type": agent_type, "project_scope": project_scope},
            )
        except Exception as exc:
            logger.warning(f"Failed to create memory agent for {agent_type}: {exc}")
            await self.append_event(
                "memory_agent_create_exception",
                {"agent_type": agent_type, "error": str(exc)},
            )
        return None

    async def sync_memory_for_agent(self, agent_ids: Dict[str, str], agent_type: str) -> None:
        try:
            agent_id = await self.ensure_memory_agent(agent_ids, agent_type)
            if not agent_id:
                return
            success = await self.memory_manager.sync_project_to_memory(agent_type, agent_id)
            await self.append_event(
                "memory_sync",
                {"agent_type": agent_type, "agent_id": agent_id, "success": success},
            )
        except Exception as exc:
            logger.warning(f"Memory sync failed for {agent_type}: {exc}")
            await self.append_event(
                "memory_sync_exception",
                {"agent_type": agent_type, "error": str(exc)},
            )

    async def sync_stage(self, agent_ids: Dict[str, str], stage: str) -> None:
        stage_agent_map = {
            "init": ["ChapterWriter"],
            "worldbuilding": ["Worldbuilder", "ChapterWriter"],
            "outlining": ["Outliner", "ChapterWriter"],
            "writing": ["ChapterWriter", "Polisher"],
            "resume": ["ChapterWriter"],
        }
        for agent_type in stage_agent_map.get(stage, []):
            await self.sync_memory_for_agent(agent_ids, agent_type)

    async def export_snapshot(self, agent_ids: Dict[str, str], reason: str) -> None:
        try:
            memory_payload = {
                "reason": reason,
                "exported_at": self._now_iso(),
                "contract": self.build_contract(),
                "project": self.project_payload_provider(),
                "project_scope": self.project_scope_provider(),
                "agent_memories": {},
            }

            for scoped_key, agent_id in agent_ids.items():
                try:
                    memory_payload["agent_memories"][scoped_key] = await self.memory_manager.export_memory_to_project(agent_id)
                except Exception as exc:
                    memory_payload["agent_memories"][scoped_key] = {"_error": str(exc)}

            self.snapshot_file().write_text(
                json.dumps(memory_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            await self.append_event("memory_export", {"reason": reason, "agent_count": len(agent_ids)})
        except Exception as exc:
            logger.warning(f"Failed to export memory snapshot: {exc}")
            await self.append_event("memory_export_exception", {"reason": reason, "error": str(exc)})

    def diagnostics(self, agent_ids: Dict[str, str]) -> Dict[str, Any]:
        meta_file = self.meta_file()
        snapshot_file = self.snapshot_file()
        diagnostics = {
            "contract": self.build_contract(),
            "memory_agent_count": len(agent_ids),
            "memory_agents": list(agent_ids.keys()),
            "meta_file": str(meta_file),
            "meta_exists": meta_file.exists(),
            "snapshot_file": str(snapshot_file),
            "snapshot_exists": snapshot_file.exists(),
        }

        if meta_file.exists():
            try:
                diagnostics["meta"] = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception as exc:
                diagnostics["meta_error"] = str(exc)

        if snapshot_file.exists():
            try:
                diagnostics["snapshot"] = json.loads(snapshot_file.read_text(encoding="utf-8"))
            except Exception as exc:
                diagnostics["snapshot_error"] = str(exc)

        return diagnostics
