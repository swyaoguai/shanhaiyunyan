"""协作执行上下文合同。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ContextValidationError(ValueError):
    """执行上下文校验失败。"""


def _copy(value: Any) -> Any:
    return deepcopy(value)


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


@dataclass
class CollabExecutionContext:
    """长篇协作模式下的执行上下文。"""

    project_dir: str = ""
    stage: str = ""
    world: Dict[str, Any] = field(default_factory=dict)
    characters: List[Dict[str, Any]] = field(default_factory=list)
    outline: Dict[str, Any] = field(default_factory=dict)
    chapter_outline: Any = ""
    previous_summary: str = ""
    previous_chapters: List[Dict[str, Any]] = field(default_factory=list)
    loaded_context: Dict[str, Any] = field(default_factory=dict)
    aux_memory: Dict[str, Any] = field(default_factory=dict)
    permanent_memory: Dict[str, Any] = field(default_factory=dict)
    context_strategy: Dict[str, Any] = field(default_factory=dict)
    cache_meta: Dict[str, Any] = field(default_factory=dict)
    source_of_truth: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy_context(
        cls,
        context: Optional[Dict[str, Any]],
        *,
        stage: str = "",
    ) -> "CollabExecutionContext":
        payload = dict(context or {})
        instance = cls(stage=str(stage or "").strip())

        for key, value in payload.items():
            instance._assign_value(str(key or "").strip(), value, source="legacy_context")
        return instance

    def clone(self) -> "CollabExecutionContext":
        return CollabExecutionContext(
            project_dir=str(self.project_dir or ""),
            stage=str(self.stage or ""),
            world=_copy(self.world),
            characters=_copy(self.characters),
            outline=_copy(self.outline),
            chapter_outline=_copy(self.chapter_outline),
            previous_summary=str(self.previous_summary or ""),
            previous_chapters=_copy(self.previous_chapters),
            loaded_context=_copy(self.loaded_context),
            aux_memory=_copy(self.aux_memory),
            permanent_memory=_copy(self.permanent_memory),
            context_strategy=_copy(self.context_strategy),
            cache_meta=_copy(self.cache_meta),
            source_of_truth=_copy(self.source_of_truth),
            extra=_copy(self.extra),
        )

    def _assign_value(self, key: str, value: Any, *, source: str = "") -> None:
        if not key:
            return

        if key == "project_dir":
            self.project_dir = str(value or "")
        elif key == "stage":
            self.stage = str(value or "")
        elif key == "world" and isinstance(value, dict):
            self.world = _copy(value)
        elif key == "characters" and isinstance(value, list):
            self.characters = _copy(value)
        elif key == "outline" and isinstance(value, dict):
            self.outline = _copy(value)
        elif key == "chapter_outline":
            self.chapter_outline = _copy(value)
        elif key == "previous_summary":
            self.previous_summary = str(value or "")
        elif key == "previous_chapters" and isinstance(value, list):
            self.previous_chapters = _copy(value)
        elif key == "loaded_context" and isinstance(value, dict):
            self.loaded_context = _copy(value)
        elif key == "aux_memory" and isinstance(value, dict):
            self.aux_memory = _copy(value)
        elif key == "permanent_memory" and isinstance(value, dict):
            self.permanent_memory = _copy(value)
        elif key == "context_strategy" and isinstance(value, dict):
            self.context_strategy = _copy(value)
        elif key == "cache_meta" and isinstance(value, dict):
            self.cache_meta = _copy(value)
        elif key == "source_of_truth" and isinstance(value, dict):
            self.source_of_truth = _copy(value)
        else:
            self.extra[key] = _copy(value)

        if source:
            self.source_of_truth[key] = source

    def get(self, key: str, default: Any = None) -> Any:
        merged = self.to_dict()
        return merged.get(key, default)

    def missing_keys(self, required_keys: List[str]) -> List[str]:
        missing: List[str] = []
        for key in required_keys or []:
            normalized = str(key or "").strip()
            if not normalized:
                continue
            if not _has_meaningful_value(self.get(normalized)):
                missing.append(normalized)
        return missing

    def validate_required_keys(self, required_keys: List[str]) -> None:
        missing = self.missing_keys(required_keys)
        if missing:
            raise ContextValidationError(f"Missing required context keys: {', '.join(missing)}")

    def merge_loaded_context(self, loaded_context: Dict[str, Any]) -> None:
        if not isinstance(loaded_context, dict):
            return
        self.loaded_context.update(_copy(loaded_context))
        for key, value in loaded_context.items():
            self._assign_value(str(key or "").strip(), value, source="content_read")

    def merge_permanent_memory(self, permanent_memory: Dict[str, Any]) -> None:
        if not isinstance(permanent_memory, dict):
            return
        merged = dict(self.permanent_memory or {})
        for key, value in permanent_memory.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged.get(key) or {})
                nested.update(_copy(value))
                merged[key] = nested
            else:
                merged[key] = _copy(value)
        self.permanent_memory = merged
        self.source_of_truth["permanent_memory"] = "content_read"

    def apply_task_result(self, task_type: str, result: Dict[str, Any]) -> "CollabExecutionContext":
        """将任务执行结果显式 merge 到上下文中（13.3 修复：扩展支持更多任务类型）。"""
        if not isinstance(result, dict):
            return self

        normalized_task_type = str(task_type or "").strip()
        if normalized_task_type == "context_plan":
            strategy = result.get("strategy")
            if isinstance(strategy, dict):
                self.context_strategy = _copy(strategy)
                self.extra["context_strategy"] = _copy(strategy)
                self.source_of_truth["context_strategy"] = "context_plan"
        elif normalized_task_type == "content_read":
            self.merge_loaded_context(result.get("loaded_context", {}))
            self.merge_permanent_memory(result.get("permanent_memory", {}))
        elif normalized_task_type == "write_chapter":
            chapter_content = str(result.get("content") or "").strip()
            if chapter_content:
                self.extra["latest_chapter_content"] = chapter_content
                self.source_of_truth["latest_chapter_content"] = "write_chapter"
            word_count = result.get("word_count")
            if word_count is not None:
                self.extra["latest_word_count"] = word_count
                self.source_of_truth["latest_word_count"] = "write_chapter"
        elif normalized_task_type == "evaluate_chapter":
            evaluation = result.get("evaluation")
            if isinstance(evaluation, dict):
                self.extra["latest_evaluation"] = _copy(evaluation)
                self.source_of_truth["latest_evaluation"] = "evaluate_chapter"
        elif normalized_task_type == "polish_chapter":
            polished_content = str(result.get("content") or "").strip()
            if polished_content:
                self.extra["latest_polished_content"] = polished_content
                self.source_of_truth["latest_polished_content"] = "polish_chapter"
        elif normalized_task_type == "expand_content":
            expanded_content = str(result.get("content") or "").strip()
            if expanded_content:
                self.extra["latest_expanded_content"] = expanded_content
                self.source_of_truth["latest_expanded_content"] = "expand_content"
            word_count = result.get("word_count")
            if word_count is not None:
                self.extra["latest_word_count"] = word_count
                self.source_of_truth["latest_word_count"] = "expand_content"
        elif normalized_task_type == "summary_orchestrate":
            summary = result.get("summary")
            if summary:
                self.extra["latest_summary"] = _copy(summary) if isinstance(summary, dict) else str(summary)
                self.source_of_truth["latest_summary"] = "summary_orchestrate"
            summary_payload = result.get("summary_payload")
            if isinstance(summary_payload, dict):
                self.extra["latest_summary_payload"] = _copy(summary_payload)
                self.source_of_truth["latest_summary_payload"] = "summary_orchestrate"
        return self

    def to_agent_context(self) -> Dict[str, Any]:
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        """问题7修复：移除 loaded_context 的重复 merge，只保留作为独立 key 的写入。"""
        payload = _copy(self.extra)

        if self.project_dir:
            payload["project_dir"] = str(self.project_dir)
        if self.stage:
            payload["stage"] = str(self.stage)
        if self.world:
            payload["world"] = _copy(self.world)
        if self.characters:
            payload["characters"] = _copy(self.characters)
        if self.outline:
            payload["outline"] = _copy(self.outline)
        if _has_meaningful_value(self.chapter_outline):
            payload["chapter_outline"] = _copy(self.chapter_outline)
        if self.previous_summary:
            payload["previous_summary"] = str(self.previous_summary)
        if self.previous_chapters:
            payload["previous_chapters"] = _copy(self.previous_chapters)
        if self.aux_memory:
            payload["aux_memory"] = _copy(self.aux_memory)
        if self.permanent_memory:
            payload["permanent_memory"] = _copy(self.permanent_memory)
        if self.context_strategy:
            payload["context_strategy"] = _copy(self.context_strategy)
        if self.cache_meta:
            payload["cache_meta"] = _copy(self.cache_meta)
        if self.loaded_context:
            payload["loaded_context"] = _copy(self.loaded_context)
        if self.source_of_truth:
            payload["source_of_truth"] = _copy(self.source_of_truth)
        return payload


@dataclass
class TaskExecutionEnvelope:
    """统一执行入口使用的任务信封。"""

    task_type: str
    stage: str
    title: str
    input_data: Dict[str, Any]
    context: CollabExecutionContext
    fallback_agent_name: str = ""
    required_context_keys: List[str] = field(default_factory=list)

    def validate_required_context(self) -> None:
        self.context.validate_required_keys(self.required_context_keys)
