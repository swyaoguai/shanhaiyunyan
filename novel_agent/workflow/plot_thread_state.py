"""Plot thread state machine for mainline/subline transitions."""

from __future__ import annotations

import copy
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PlotThreadStateMachine:
    """State machine that orchestrates mainline/subline transitions."""

    STATE_VERSION = "2026-02-24.1"
    MAIN_THREAD_ID = "main"
    DEFAULT_MAX_SUBPLOT_STREAK = 2
    MAX_HISTORY = 200

    _CONTENT_RETURN_MAIN_RE = re.compile(
        r"<!--\s*PLOT_THREAD:return_main\s*-->", re.IGNORECASE
    )
    _CONTENT_COMPLETE_RE = re.compile(
        r"<!--\s*PLOT_THREAD:complete(?:\s+([A-Za-z0-9_-]{1,64}))?\s*-->",
        re.IGNORECASE,
    )
    _CONTENT_SWITCH_RE = re.compile(
        r"<!--\s*PLOT_THREAD:switch:([A-Za-z0-9_-]{1,64})\s*-->", re.IGNORECASE
    )

    _INLINE_THREAD_RE = re.compile(r"\[thread:([A-Za-z0-9_-]{1,64})\]", re.IGNORECASE)
    _INLINE_SWITCH_RE = re.compile(r"\[switch:([A-Za-z0-9_-]{1,64})\]", re.IGNORECASE)
    _INLINE_RETURN_MAIN_RE = re.compile(r"\[(?:return_main|回主线)\]", re.IGNORECASE)
    _INLINE_COMPLETE_RE = re.compile(r"\[(?:complete_thread|结束支线)\]", re.IGNORECASE)
    _INLINE_RETURN_BY_RE = re.compile(r"\[return_by:(\d{1,4})\]", re.IGNORECASE)

    def __init__(self, project_dir: Optional[Path] = None, state: Optional[Dict[str, Any]] = None):
        # Backward-compat: if project_dir is a dict, treat it as state
        if isinstance(project_dir, dict):
            state = project_dir
            project_dir = None
        self.project_dir = project_dir
        self.state_key: str = "plot_thread_state"
        self.state: Dict[str, Any] = self._normalize_state(state)
        self._ensure_thread(
            self.MAIN_THREAD_ID,
            {
                "id": self.MAIN_THREAD_ID,
                "title": "主线",
                "thread_type": "main",
                "status": "active",
            },
            overwrite=False,
        )

    def reset(self) -> None:
        self.state = self._normalize_state(None)
        self._ensure_thread(
            self.MAIN_THREAD_ID,
            {
                "id": self.MAIN_THREAD_ID,
                "title": "主线",
                "thread_type": "main",
                "status": "active",
            },
            overwrite=False,
        )

    def load(self, payload: Optional[Dict[str, Any]]) -> None:
        self.state = self._normalize_state(payload)
        self._ensure_thread(
            self.MAIN_THREAD_ID,
            {
                "id": self.MAIN_THREAD_ID,
                "title": "主线",
                "thread_type": "main",
                "status": "active",
            },
            overwrite=False,
        )

    def snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(self.state)

    def sync_with_outline(
        self,
        outline_data: Optional[Dict[str, Any]],
        total_chapters: int = 0,
        reset: bool = False,
    ) -> Dict[str, Any]:
        if reset:
            self.reset()

        if total_chapters and total_chapters > 0:
            self.state["total_chapters"] = int(total_chapters)

        for index, raw_thread in enumerate(self._extract_outline_threads(outline_data), start=1):
            thread = self._normalize_thread_entry(raw_thread, fallback_id=f"subplot_{index}")
            thread_id = thread.get("id")
            if not thread_id:
                continue
            self._ensure_thread(thread_id, thread, overwrite=False)

        self._touch()
        return self.snapshot()

    def plan_chapter(self, chapter_number: int, chapter_outline: Any) -> Dict[str, Any]:
        chapter_number = max(1, int(chapter_number))
        directives = self._extract_chapter_directives(chapter_outline)

        current = self.state.get("active_thread_id", self.MAIN_THREAD_ID)
        target = current
        reason = "keep_current_thread"

        if directives["return_to_main"]:
            target = self.MAIN_THREAD_ID
            reason = "directive_return_main"
        elif directives["switch_to"]:
            target = directives["switch_to"]
            reason = "directive_switch_to"
        elif directives["thread_id"]:
            target = directives["thread_id"]
            reason = "directive_thread_id"
        elif self._should_force_return_main(chapter_number, current):
            target = self.MAIN_THREAD_ID
            reason = "guard_forced_return_main"

        self._ensure_thread(target, self._build_default_thread(target), overwrite=False)
        self._apply_directive_metadata(target, directives, chapter_number)
        self._set_active_thread(target, chapter_number, reason)

        active = self.state["active_thread_id"]
        self.state["chapter_thread_map"][str(chapter_number)] = active
        if active == self.MAIN_THREAD_ID:
            self.state["subplot_streak"] = 0
        else:
            self.state["subplot_streak"] = int(self.state.get("subplot_streak", 0)) + 1

        active_thread = self.state["threads"][active]
        active_thread["last_active_chapter"] = chapter_number

        self._touch()
        return {
            "active_thread_id": active,
            "active_thread": copy.deepcopy(active_thread),
            "subplot_streak": self.state["subplot_streak"],
            "last_transition_reason": self.state.get("last_transition_reason", ""),
            "threads_overview": self._threads_overview(),
            "writer_guidance": self._build_writer_guidance(chapter_number, active, directives),
        }

    def complete_chapter(
        self,
        chapter_number: int,
        chapter_outline: Any,
        chapter_content: str,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del evaluation  # reserved for future evaluator-driven transitions

        chapter_number = max(1, int(chapter_number))
        chapter_key = str(chapter_number)
        active = self.state["chapter_thread_map"].get(
            chapter_key, self.state.get("active_thread_id", self.MAIN_THREAD_ID)
        )
        self._ensure_thread(active, self._build_default_thread(active), overwrite=False)

        directives = self._extract_chapter_directives(chapter_outline)
        markers = self._extract_content_markers(chapter_content)
        resolved_threads: List[str] = []
        transition_reason = ""

        active_thread = self.state["threads"][active]
        active_thread["last_active_chapter"] = chapter_number

        complete_current = directives["complete_thread"] or markers["complete_current"]
        if complete_current and active != self.MAIN_THREAD_ID:
            active_thread["status"] = "completed"
            resolved_threads.append(active)

        marker_complete_id = markers["complete_thread_id"]
        if marker_complete_id and marker_complete_id in self.state["threads"]:
            self.state["threads"][marker_complete_id]["status"] = "completed"
            if marker_complete_id not in resolved_threads:
                resolved_threads.append(marker_complete_id)

        if markers["switch_to"]:
            self._set_active_thread(
                markers["switch_to"], chapter_number, "content_marker_switch_to"
            )
            transition_reason = "content_marker_switch_to"
        elif markers["return_main"]:
            self._set_active_thread(
                self.MAIN_THREAD_ID, chapter_number, "content_marker_return_main"
            )
            transition_reason = "content_marker_return_main"
        elif complete_current and active != self.MAIN_THREAD_ID:
            self._set_active_thread(self.MAIN_THREAD_ID, chapter_number, "thread_completed")
            transition_reason = "thread_completed"
        elif self._should_force_return_main(chapter_number, active):
            self._set_active_thread(
                self.MAIN_THREAD_ID, chapter_number, "guard_forced_return_main"
            )
            transition_reason = "guard_forced_return_main"

        self._touch()
        return {
            "active_thread_id": self.state["active_thread_id"],
            "resolved_thread_ids": resolved_threads,
            "transition_reason": transition_reason or self.state.get("last_transition_reason", ""),
            "threads_overview": self._threads_overview(),
        }

    def _normalize_state(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        state = {
            "version": self.STATE_VERSION,
            "active_thread_id": self.MAIN_THREAD_ID,
            "last_transition_reason": "init",
            "threads": {},
            "chapter_thread_map": {},
            "transition_history": [],
            "subplot_streak": 0,
            "total_chapters": 0,
            "updated_at": now,
        }
        if not isinstance(payload, dict):
            return state

        if isinstance(payload.get("version"), str) and payload["version"]:
            state["version"] = payload["version"]
        if isinstance(payload.get("active_thread_id"), str) and payload["active_thread_id"]:
            state["active_thread_id"] = payload["active_thread_id"]
        if isinstance(payload.get("last_transition_reason"), str):
            state["last_transition_reason"] = payload["last_transition_reason"]
        if isinstance(payload.get("threads"), dict):
            state["threads"] = copy.deepcopy(payload["threads"])
        if isinstance(payload.get("chapter_thread_map"), dict):
            state["chapter_thread_map"] = {
                str(k): str(v)
                for k, v in payload["chapter_thread_map"].items()
                if isinstance(k, (str, int)) and isinstance(v, str)
            }
        if isinstance(payload.get("transition_history"), list):
            state["transition_history"] = [
                item for item in payload["transition_history"] if isinstance(item, dict)
            ][-self.MAX_HISTORY :]
        if isinstance(payload.get("subplot_streak"), int) and payload["subplot_streak"] >= 0:
            state["subplot_streak"] = payload["subplot_streak"]
        if isinstance(payload.get("total_chapters"), int) and payload["total_chapters"] >= 0:
            state["total_chapters"] = payload["total_chapters"]
        if isinstance(payload.get("updated_at"), str) and payload["updated_at"]:
            state["updated_at"] = payload["updated_at"]

        return state

    def _touch(self) -> None:
        self.state["updated_at"] = datetime.now().isoformat()

    def _ensure_thread(
        self, thread_id: str, thread_data: Dict[str, Any], overwrite: bool = False
    ) -> None:
        if not thread_id:
            return
        threads = self.state["threads"]
        existing = threads.get(thread_id)
        if existing and not overwrite:
            for key, value in thread_data.items():
                if key not in existing or existing[key] in ("", None):
                    existing[key] = value
            return
        if existing and overwrite:
            merged = copy.deepcopy(existing)
            merged.update(thread_data)
            threads[thread_id] = merged
            return
        threads[thread_id] = copy.deepcopy(thread_data)

    def _set_active_thread(self, thread_id: str, chapter_number: int, reason: str) -> None:
        thread_id = thread_id or self.MAIN_THREAD_ID
        self._ensure_thread(thread_id, self._build_default_thread(thread_id), overwrite=False)

        previous = self.state.get("active_thread_id", self.MAIN_THREAD_ID)
        self.state["active_thread_id"] = thread_id
        self.state["last_transition_reason"] = reason

        if previous != thread_id:
            self.state["transition_history"].append(
                {
                    "chapter": chapter_number,
                    "from": previous,
                    "to": thread_id,
                    "reason": reason,
                    "time": datetime.now().isoformat(),
                }
            )
            self.state["transition_history"] = self.state["transition_history"][
                -self.MAX_HISTORY :
            ]

        if thread_id == self.MAIN_THREAD_ID:
            self.state["subplot_streak"] = 0

    def _should_force_return_main(self, chapter_number: int, thread_id: str) -> bool:
        if thread_id == self.MAIN_THREAD_ID:
            return False
        thread = self.state["threads"].get(thread_id, {})

        target_return = self._to_positive_int(thread.get("target_return_chapter"))
        if target_return and chapter_number > target_return:
            return True

        max_streak = self._to_positive_int(thread.get("max_consecutive_chapters"))
        if not max_streak:
            max_streak = self.DEFAULT_MAX_SUBPLOT_STREAK
        if int(self.state.get("subplot_streak", 0)) >= max_streak:
            return True

        return False

    def _threads_overview(self) -> List[Dict[str, Any]]:
        overview: List[Dict[str, Any]] = []
        for thread_id, thread in self.state["threads"].items():
            overview.append(
                {
                    "id": thread_id,
                    "title": thread.get("title", thread_id),
                    "thread_type": thread.get("thread_type", "subplot"),
                    "status": thread.get("status", "active"),
                    "target_return_chapter": thread.get("target_return_chapter"),
                    "last_active_chapter": thread.get("last_active_chapter", 0),
                }
            )
        overview.sort(key=lambda item: (0 if item["id"] == self.MAIN_THREAD_ID else 1, item["id"]))
        return overview

    def _build_writer_guidance(
        self, chapter_number: int, active_thread_id: str, directives: Dict[str, Any]
    ) -> str:
        active = self.state["threads"].get(active_thread_id, {})
        title = active.get("title") or active_thread_id
        objective = active.get("objective") or directives.get("chapter_goal") or ""
        target_return = active.get("target_return_chapter")
        streak = self.state.get("subplot_streak", 0)

        if active_thread_id == self.MAIN_THREAD_ID:
            return (
                f"当前章节（第{chapter_number}章）应推进主线。"
                "除非本章指令明确切换支线，否则不要偏离主线。"
            )

        parts = [
            f"当前章节（第{chapter_number}章）处于支线[{title}]。",
            "请优先完成该支线的阶段目标，并在章末给出回主线钩子。",
        ]
        if objective:
            parts.append(f"本线目标：{objective}")
        if target_return:
            parts.append(f"最晚在第{target_return}章回到主线。")
        parts.append(f"当前支线连续章数：{streak}")
        return " ".join(parts)

    def _extract_outline_threads(self, outline_data: Optional[Dict[str, Any]]) -> List[Any]:
        if not isinstance(outline_data, dict):
            return []

        collected: List[Any] = []
        for key in ("plot_threads", "threads"):
            value = outline_data.get(key)
            if isinstance(value, list):
                collected.extend(value)
            elif isinstance(value, dict):
                collected.extend(value.values())

        recurring = outline_data.get("recurring_elements")
        if isinstance(recurring, dict):
            foreshadowing = recurring.get("foreshadowing_threads")
            if isinstance(foreshadowing, list):
                for item in foreshadowing:
                    if isinstance(item, str) and item.strip():
                        collected.append(
                            {
                                "title": item.strip(),
                                "objective": item.strip(),
                                "thread_type": "subplot",
                            }
                        )

        return collected

    def _normalize_thread_entry(self, entry: Any, fallback_id: str) -> Dict[str, Any]:
        if isinstance(entry, str):
            title = entry.strip() or fallback_id
            return {
                "id": fallback_id,
                "title": title,
                "thread_type": "subplot",
                "status": "active",
                "objective": title,
                "start_chapter": 1,
                "last_active_chapter": 0,
                "target_return_chapter": None,
                "max_consecutive_chapters": self.DEFAULT_MAX_SUBPLOT_STREAK,
            }

        data = entry if isinstance(entry, dict) else {}
        thread_id = (
            data.get("id")
            or data.get("thread_id")
            or data.get("key")
            or data.get("name")
            or fallback_id
        )
        thread_id = str(thread_id).strip() or fallback_id
        thread_type = str(data.get("thread_type") or data.get("type") or "subplot").lower()
        if thread_id == self.MAIN_THREAD_ID:
            thread_type = "main"

        return {
            "id": thread_id,
            "title": str(data.get("title") or data.get("name") or thread_id),
            "thread_type": thread_type,
            "status": str(data.get("status") or "active"),
            "objective": str(data.get("objective") or ""),
            "start_chapter": self._to_positive_int(data.get("start_chapter")) or 1,
            "last_active_chapter": self._to_positive_int(data.get("last_active_chapter")) or 0,
            "target_return_chapter": self._to_positive_int(data.get("return_by_chapter"))
            or self._to_positive_int(data.get("target_return_chapter")),
            "max_consecutive_chapters": self._to_positive_int(
                data.get("max_consecutive_chapters")
            )
            or self.DEFAULT_MAX_SUBPLOT_STREAK,
        }

    def _build_default_thread(self, thread_id: str) -> Dict[str, Any]:
        if thread_id == self.MAIN_THREAD_ID:
            return {
                "id": thread_id,
                "title": "主线",
                "thread_type": "main",
                "status": "active",
                "objective": "",
                "start_chapter": 1,
                "last_active_chapter": 0,
                "target_return_chapter": None,
                "max_consecutive_chapters": self.DEFAULT_MAX_SUBPLOT_STREAK,
            }
        return {
            "id": thread_id,
            "title": thread_id,
            "thread_type": "subplot",
            "status": "active",
            "objective": "",
            "start_chapter": 1,
            "last_active_chapter": 0,
            "target_return_chapter": None,
            "max_consecutive_chapters": self.DEFAULT_MAX_SUBPLOT_STREAK,
        }

    def _apply_directive_metadata(
        self, thread_id: str, directives: Dict[str, Any], chapter_number: int
    ) -> None:
        thread = self.state["threads"].get(thread_id)
        if not thread:
            return

        if directives["thread_title"]:
            thread["title"] = directives["thread_title"]
        if directives["objective"]:
            thread["objective"] = directives["objective"]
        if directives["return_by_chapter"]:
            thread["target_return_chapter"] = directives["return_by_chapter"]
        if directives["max_consecutive"]:
            thread["max_consecutive_chapters"] = directives["max_consecutive"]
        if not thread.get("start_chapter"):
            thread["start_chapter"] = chapter_number

    def _extract_chapter_directives(self, chapter_outline: Any) -> Dict[str, Any]:
        directives = {
            "thread_id": None,
            "thread_title": None,
            "switch_to": None,
            "return_to_main": False,
            "return_by_chapter": None,
            "complete_thread": False,
            "objective": None,
            "chapter_goal": None,
            "max_consecutive": None,
        }

        if isinstance(chapter_outline, dict):
            self._read_directives_from_dict(chapter_outline, directives)
            for nested_key in ("plot_thread", "thread", "story_thread", "thread_plan"):
                nested = chapter_outline.get(nested_key)
                if isinstance(nested, dict):
                    self._read_directives_from_dict(nested, directives)

            summary = chapter_outline.get("summary")
            title = chapter_outline.get("title")
            self._read_inline_markers(f"{title or ''}\n{summary or ''}", directives)
        else:
            self._read_inline_markers(str(chapter_outline or ""), directives)

        return directives

    def _read_directives_from_dict(
        self, source: Dict[str, Any], directives: Dict[str, Any]
    ) -> None:
        def pick_str(*keys: str) -> Optional[str]:
            for key in keys:
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        def pick_bool(*keys: str) -> Optional[bool]:
            for key in keys:
                if key in source:
                    return bool(source.get(key))
            return None

        thread_id = pick_str("thread_id", "active_thread", "plot_thread_id")
        switch_to = pick_str("switch_to", "switch_to_thread", "enter_thread")
        thread_title = pick_str("thread_title", "title", "name")
        objective = pick_str("objective", "thread_objective", "goal")
        chapter_goal = pick_str("chapter_goal", "goal_for_this_chapter")

        if thread_id:
            directives["thread_id"] = thread_id
        if switch_to:
            directives["switch_to"] = switch_to
        if thread_title:
            directives["thread_title"] = thread_title
        if objective:
            directives["objective"] = objective
        if chapter_goal:
            directives["chapter_goal"] = chapter_goal

        return_to_main = pick_bool("return_to_main", "back_to_main")
        complete_thread = pick_bool("complete_thread", "thread_completed", "end_thread")
        if return_to_main is not None:
            directives["return_to_main"] = return_to_main
        if complete_thread is not None:
            directives["complete_thread"] = complete_thread

        return_by = self._to_positive_int(
            source.get("return_by_chapter") or source.get("return_by")
        )
        max_consecutive = self._to_positive_int(
            source.get("max_consecutive_chapters") or source.get("max_streak")
        )

        if return_by:
            directives["return_by_chapter"] = return_by
        if max_consecutive:
            directives["max_consecutive"] = max_consecutive

    def _read_inline_markers(self, text: str, directives: Dict[str, Any]) -> None:
        if not text:
            return

        text = str(text)
        thread_match = self._INLINE_THREAD_RE.search(text)
        switch_match = self._INLINE_SWITCH_RE.search(text)
        return_main_match = self._INLINE_RETURN_MAIN_RE.search(text)
        complete_match = self._INLINE_COMPLETE_RE.search(text)
        return_by_match = self._INLINE_RETURN_BY_RE.search(text)

        if thread_match:
            directives["thread_id"] = thread_match.group(1)
        if switch_match:
            directives["switch_to"] = switch_match.group(1)
        if return_main_match:
            directives["return_to_main"] = True
        if complete_match:
            directives["complete_thread"] = True
        if return_by_match:
            directives["return_by_chapter"] = int(return_by_match.group(1))

    def _extract_content_markers(self, content: str) -> Dict[str, Any]:
        text = content or ""
        complete_match = self._CONTENT_COMPLETE_RE.search(text)
        switch_match = self._CONTENT_SWITCH_RE.search(text)
        return {
            "return_main": bool(self._CONTENT_RETURN_MAIN_RE.search(text)),
            "complete_current": bool(complete_match and not complete_match.group(1)),
            "complete_thread_id": complete_match.group(1) if complete_match else None,
            "switch_to": switch_match.group(1) if switch_match else None,
        }

    @staticmethod
    def _to_positive_int(value: Any) -> Optional[int]:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        return number

    # --- Persistence methods (coordinator-compatible) ---

    def load_plot_thread_state(self) -> None:
        """Load persisted plot thread state for the current project."""
        if self.project_dir is None:
            logger.warning("[PlotThread] project_dir not set, skipping load")
            return
        try:
            from ..project_manager import get_project_manager
            pm = get_project_manager()
            payload = pm.load_project_state(self.state_key, default=None)
            self.load(payload if isinstance(payload, dict) else None)
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to load state: {exc}")

    def save_plot_thread_state(self) -> None:
        """Persist plot thread state for the current project."""
        if self.project_dir is None:
            logger.warning("[PlotThread] project_dir not set, skipping save")
            return
        try:
            from ..project_manager import get_project_manager
            pm = get_project_manager()
            pm.save_project_state(self.state_key, self.snapshot())
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to save state: {exc}")

    def sync_with_outline_external(
        self,
        outline_data: Optional[Dict[str, Any]],
        total_chapters: int,
        reset: bool,
    ) -> Dict[str, Any]:
        """Sync thread definitions from outline and persist (coordinator-compatible wrapper)."""
        result = self.sync_with_outline(outline_data, total_chapters, reset)
        self.save_plot_thread_state()
        return result

    async def plan_for_chapter(self, chapter_num: int, chapter_outline: Any) -> Dict[str, Any]:
        """Plan active thread before writing a chapter (async wrapper)."""
        context = self.plan_chapter(chapter_num, chapter_outline)
        self.save_plot_thread_state()
        return context

    async def complete_for_chapter(
        self,
        chapter_num: int,
        chapter_outline: Any,
        chapter_content: str,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply post-chapter transitions and persist state (async wrapper)."""
        result = self.complete_chapter(
            chapter_number=chapter_num,
            chapter_outline=chapter_outline,
            chapter_content=chapter_content,
            evaluation=evaluation,
        )
        self.save_plot_thread_state()
        return result

