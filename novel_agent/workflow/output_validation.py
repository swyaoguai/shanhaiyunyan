"""Task output validation helpers for collaborative execution."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _has_key(payload: Dict[str, Any], key: str) -> bool:
    return key in payload


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _simple_output_name(name: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name or "").strip()))


def _missing_meaningful(payload: Dict[str, Any], keys: List[str]) -> List[str]:
    return [key for key in keys if not _is_meaningful(payload.get(key))]


def _missing_present(payload: Dict[str, Any], keys: List[str]) -> List[str]:
    return [key for key in keys if not _has_key(payload, key)]


def _task_specific_missing(task_type: str, result: Dict[str, Any]) -> List[str]:
    normalized = str(task_type or "").strip()

    if normalized == "build_world":
        return _missing_meaningful(result, ["world"])
    if normalized == "build_characters":
        return _missing_meaningful(result, ["characters"])
    if normalized == "build_outline":
        return _missing_meaningful(result, ["outline"])
    if normalized == "chapter_settings":
        if _is_meaningful(result.get("chapter_settings")) or _is_meaningful(result.get("rows")):
            return []
        return ["chapter_settings|rows"]
    if normalized == "context_plan":
        return _missing_meaningful(result, ["strategy"])
    if normalized == "content_read":
        # Empty reads are valid when the strategy has no items; require shape, not size.
        return _missing_present(result, ["loaded_context", "report"])
    if normalized == "write_chapter":
        return _missing_meaningful(result, ["content"])
    if normalized == "evaluate_chapter":
        return _missing_present(result, ["evaluation"])
    if normalized == "polish_chapter":
        if result.get("skipped") or result.get("skip") or result.get("evaluation_passed"):
            return []
        return _missing_meaningful(result, ["content"])
    if normalized == "expand_content":
        return _missing_meaningful(result, ["content"])
    if normalized == "summary_orchestrate":
        if _is_meaningful(result.get("summary")) or _is_meaningful(result.get("summary_payload")):
            return []
        return ["summary|summary_payload"]
    return []


def _task_specific_covered_outputs(task_type: str) -> set[str]:
    normalized = str(task_type or "").strip()
    return {
        "build_world": {"world"},
        "build_characters": {"characters"},
        "build_outline": {"outline"},
        "chapter_settings": {"chapter_settings", "rows"},
        "context_plan": {"strategy"},
        "content_read": {"loaded_context", "report", "permanent_memory"},
        "write_chapter": {"content", "word_count"},
        "evaluate_chapter": {"evaluation"},
        "polish_chapter": {"content"},
        "expand_content": {"content", "word_count", "expanded"},
        "summary_orchestrate": {"summary", "summary_payload"},
    }.get(normalized, set())


def validate_task_outputs(
    *,
    task_type: str,
    expected_outputs: Optional[List[str]],
    result: Any,
) -> Dict[str, Any]:
    """Validate an agent result against task-specific and simple expected outputs."""
    expected = [
        str(item or "").strip()
        for item in (expected_outputs or [])
        if str(item or "").strip()
    ]
    validation: Dict[str, Any] = {
        "passed": True,
        "task_type": str(task_type or "").strip(),
        "expected_outputs": expected,
        "missing_outputs": [],
        "skipped_outputs": [],
        "warning_outputs": [],
    }

    if not isinstance(result, dict):
        validation["passed"] = False
        validation["missing_outputs"] = ["structured_result"]
        return validation

    missing: List[str] = _task_specific_missing(task_type, result)
    covered_outputs = _task_specific_covered_outputs(task_type)

    for output_name in expected:
        if not _simple_output_name(output_name):
            validation["skipped_outputs"].append(output_name)
            continue
        if output_name in covered_outputs:
            continue
        if not _is_meaningful(result.get(output_name)):
            missing.append(output_name)

    if str(task_type or "").strip() in {"write_chapter", "expand_content"} and "word_count" not in result:
        validation["warning_outputs"].append("word_count")

    deduped_missing = list(dict.fromkeys(missing))
    validation["missing_outputs"] = deduped_missing
    validation["passed"] = not deduped_missing
    return validation


def format_output_validation_error(validation: Dict[str, Any]) -> str:
    missing = [
        str(item or "").strip()
        for item in (validation or {}).get("missing_outputs", [])
        if str(item or "").strip()
    ]
    task_type = str((validation or {}).get("task_type") or "").strip() or "unknown"
    if not missing:
        return f"任务 {task_type} 输出校验失败"
    return f"任务 {task_type} 缺少必需输出: {', '.join(missing)}"
