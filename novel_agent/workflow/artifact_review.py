"""Deterministic baseline reviews for serial creative workflow artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ReviewIssue:
    type: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    task_id: str
    artifact_id: str
    artifact_type: str
    passed: bool
    severity: str = "none"
    issues: List[ReviewIssue] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    missing_info: List[str] = field(default_factory=list)
    revision_target: str = ""
    revision_instructions: str = ""
    requires_user_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload


def _text_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except Exception:
        return len(str(value or ""))


def _issue(issue_type: str, message: str) -> ReviewIssue:
    return ReviewIssue(type=issue_type, message=message)


def review_artifact_basic(
    *,
    task_id: str,
    artifact_id: str,
    artifact_type: str,
    artifact: Any,
    revision_target: str,
) -> ReviewResult:
    """Run a local structural review before the workflow advances."""

    issues: List[ReviewIssue] = []
    missing_info: List[str] = []
    normalized_type = str(artifact_type or "").strip()
    if normalized_type == "worldbuilding":
        if not isinstance(artifact, dict) or not artifact:
            issues.append(_issue("missing_artifact", "世界观结果为空或不是对象。"))
        else:
            declared_missing = artifact.get("missing_info")
            if isinstance(declared_missing, list):
                missing_info.extend(str(item).strip() for item in declared_missing if str(item).strip())
            elif isinstance(declared_missing, str) and declared_missing.strip():
                missing_info.append(declared_missing.strip())
            status = str(artifact.get("status") or "").strip().lower()
            if status in {"missing_info", "needs_input", "needs_confirmation", "pending_confirmation"}:
                issues.append(_issue("missing_info", "世界观生成结果声明信息不足，需要用户补充。"))
            if missing_info:
                issues.append(_issue("missing_info", "世界观缺少关键信息：" + "、".join(missing_info[:5])))
            meaningful_keys = [key for key, value in artifact.items() if value not in (None, "", [], {})]
            if len(meaningful_keys) < 3:
                missing_info.append("世界观有效字段不足")
                issues.append(_issue("missing_fields", "世界观有效字段过少，无法支撑后续阶段。"))
            name = str(artifact.get("world_name") or artifact.get("name") or "").strip()
            if name in {"", "未命名世界", "默认世界"}:
                missing_info.append("世界名称或核心标识")
                issues.append(_issue("missing_identity", "世界观缺少可识别的名称或核心标识。"))
            if _text_size(artifact) < 120:
                issues.append(_issue("thin_context", "世界观内容过短，对角色和大纲不可用。"))

    elif normalized_type == "characters":
        if not isinstance(artifact, list) or not artifact:
            issues.append(_issue("missing_artifact", "角色卡结果为空。"))
        else:
            valid_count = 0
            placeholder_names = {"主角", "男主", "女主", "角色", "人物", "角色1", "人物1"}
            for row in artifact:
                if not isinstance(row, dict):
                    issues.append(_issue("invalid_row", "存在非对象角色项。"))
                    continue
                name = str(row.get("name") or "").strip()
                description = str(row.get("description") or "").strip()
                if not name or name in placeholder_names:
                    issues.append(_issue("missing_identity", "角色缺少明确姓名。"))
                    continue
                if len(description) < 6:
                    issues.append(_issue("thin_character", f"角色 {name} 简介过短。"))
                    continue
                valid_count += 1
            if valid_count <= 0:
                issues.append(_issue("no_valid_character", "没有通过基础审查的角色卡。"))

    elif normalized_type == "outline":
        if not isinstance(artifact, list) or not artifact:
            issues.append(_issue("missing_artifact", "大纲结果为空。"))
        else:
            for index, row in enumerate(artifact[:3], 1):
                if not isinstance(row, dict):
                    issues.append(_issue("invalid_row", f"第 {index} 条大纲不是对象。"))
                    continue
                if not str(row.get("title") or "").strip():
                    issues.append(_issue("missing_title", f"第 {index} 条大纲缺少标题。"))
                if not str(row.get("summary") or row.get("content") or "").strip():
                    issues.append(_issue("missing_summary", f"第 {index} 条大纲缺少摘要。"))

    elif normalized_type == "chapters":
        content = str(artifact.get("content") if isinstance(artifact, dict) else artifact or "").strip()
        if len(content) < 80:
            issues.append(_issue("thin_chapter", "章节正文过短，无法作为有效章节提交。"))

    else:
        if artifact in (None, "", [], {}):
            issues.append(_issue("missing_artifact", f"{normalized_type or '资料'}结果为空。"))

    passed = len(issues) == 0
    severity = "none" if passed else ("major" if any(issue.type.startswith("missing") for issue in issues) else "minor")
    instructions = ""
    if not passed:
        instructions = "；".join(issue.message for issue in issues[:5])

    return ReviewResult(
        task_id=task_id,
        artifact_id=artifact_id,
        artifact_type=normalized_type,
        passed=passed,
        severity=severity,
        issues=issues,
        missing_info=missing_info,
        revision_target=revision_target,
        revision_instructions=instructions,
        requires_user_confirmation=False,
    )


def review_artifact_contextual(
    *,
    task_id: str,
    artifact_id: str,
    artifact_type: str,
    artifact: Any,
    revision_target: str,
    workflow_context: Any,
) -> ReviewResult:
    """Run lightweight context checks that need the shared workflow context."""

    normalized_type = str(artifact_type or "").strip()
    issues: List[ReviewIssue] = []
    missing_info: List[str] = []
    conflicts: List[Dict[str, Any]] = []

    try:
        artifact_text = json.dumps(artifact, ensure_ascii=False)
    except Exception:
        artifact_text = str(artifact or "")

    interruptions = getattr(workflow_context, "user_interruptions", []) or []
    for interruption in interruptions:
        message = str((interruption or {}).get("message") if isinstance(interruption, dict) else interruption or "").strip()
        if not message:
            continue
        match = re.search(r"不是(.{1,24}?)[，,。；;\s]+(?:而是|是|改成)(.{1,40})", message)
        if match:
            forbidden = match.group(1).strip()
            expected = match.group(2).strip()
            if forbidden and forbidden in artifact_text:
                issues.append(_issue("context_conflict", f"产物仍包含用户已否定的设定：{forbidden}。"))
                conflicts.append({
                    "type": "user_interruption_conflict",
                    "forbidden": forbidden,
                    "expected": expected,
                    "message": message,
                })

    passed = len(issues) == 0
    severity = "none" if passed else "major"
    instructions = "；".join(issue.message for issue in issues[:5]) if issues else ""

    return ReviewResult(
        task_id=task_id,
        artifact_id=artifact_id,
        artifact_type=normalized_type,
        passed=passed,
        severity=severity,
        issues=issues,
        conflicts=conflicts,
        missing_info=missing_info,
        revision_target=revision_target,
        revision_instructions=instructions,
        requires_user_confirmation=False,
    )
