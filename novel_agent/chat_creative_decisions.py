"""Chat-driven creative decision and revision support."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DECISION_STATE_KEY = "chat_creative_decisions"

DISCUSSION_ONLY_MARKERS = (
    "先讨论",
    "先聊",
    "别落盘",
    "不要落盘",
    "先别保存",
    "不要保存",
    "先不保存",
    "先别存档",
    "别存档",
    "不要存档",
    "先不存档",
    "暂不存档",
    "先别写入",
    "不要写入",
)

MODIFICATION_MARKERS = (
    "修改",
    "改成",
    "改为",
    "更改",
    "调整",
    "修正",
    "重写",
    "替换",
    "删除",
    "删掉",
    "移除",
    "补充",
    "加入",
    "增加",
    "不要",
    "不能",
    "以后",
    "后续",
    "设定为",
    "保存",
    "写入",
    "同步",
)

CREATIVE_OBJECTS: Dict[str, Dict[str, Any]] = {
    "worldbuilding": {
        "data_type": "worldbuilding",
        "label": "世界观",
        "title_key": "name",
        "keywords": ("世界观", "世界设定", "力量体系", "地理", "势力", "规则", "修炼体系"),
    },
    "characters": {
        "data_type": "characters",
        "label": "角色",
        "title_key": "name",
        "keywords": ("角色", "人物", "主角", "配角", "反派", "人设", "角色卡", "人物档案", "动机"),
    },
    "eventlines": {
        "data_type": "eventlines",
        "label": "事件线",
        "title_key": "name",
        "keywords": ("事件线", "事件", "主线", "支线", "剧情线", "伏笔"),
    },
    "outline": {
        "data_type": "outline",
        "label": "大纲",
        "title_key": "title",
        "keywords": ("大纲", "章节大纲", "卷纲", "剧情走向", "主线"),
    },
    "detail_settings": {
        "data_type": "detail_settings",
        "label": "细纲",
        "title_key": "name",
        "keywords": ("细纲", "场景", "桥段", "段落规划"),
    },
    "chapter_settings": {
        "data_type": "chapter_settings",
        "label": "章纲",
        "title_key": "name",
        "keywords": ("章纲", "章节设定", "本章目标", "章内"),
    },
    "chapters": {
        "data_type": "chapters",
        "label": "正文",
        "title_key": "title",
        "keywords": ("正文", "章节正文", "第", "章", "段落", "内容"),
    },
    "chapter_summary": {
        "data_type": "chapter_summary",
        "label": "章节总结",
        "title_key": "name",
        "keywords": ("章节总结", "总结", "阶段总结", "摘要"),
    },
    "items": {
        "data_type": "items",
        "label": "物品设定",
        "title_key": "name",
        "keywords": ("物品", "道具", "法宝", "装备", "物件"),
    },
}


@dataclass
class CreativeDecision:
    decision_type: str
    message: str
    targets: List[str] = field(default_factory=list)
    should_update_content: bool = False
    should_update_contract: bool = True
    reason: str = ""

    def to_record(self, *, mode: str, status: str, updated_files: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "id": f"chat-decision-{re.sub(r'[^0-9]', '', now)[:14]}",
            "created_at": now,
            "mode": mode,
            "decision_type": self.decision_type,
            "message": self.message,
            "targets": list(self.targets),
            "should_update_content": bool(self.should_update_content),
            "should_update_contract": bool(self.should_update_contract),
            "reason": self.reason,
            "status": status,
            "updated_files": list(updated_files or []),
        }


def _normalize_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"auto", "discussion", "plan", "execute"} else "auto"


def _contains_any(text: str, markers: Tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _detect_targets(message: str) -> List[str]:
    targets: List[str] = []
    for key, config in CREATIVE_OBJECTS.items():
        if any(keyword in message for keyword in config["keywords"]):
            targets.append(key)
    if "润色" in message or "文风" in message or "风格" in message:
        if "chapters" not in targets:
            targets.append("chapters")
    return targets


def detect_creative_decision(message: str, mode: str = "auto") -> Optional[CreativeDecision]:
    """Classify a chat message as a creative decision or revision request."""
    text = str(message or "").strip()
    if not text:
        return None

    effective_mode = _normalize_mode(mode)
    if _contains_any(text, DISCUSSION_ONLY_MARKERS) or effective_mode == "discussion":
        return CreativeDecision(
            decision_type="discussion_only",
            message=text,
            targets=_detect_targets(text),
            should_update_content=False,
            should_update_contract=False,
            reason="user_requested_discussion_only",
        )

    has_modification = _contains_any(text, MODIFICATION_MARKERS)
    targets = _detect_targets(text)
    has_direction = any(token in text for token in ("方向", "基调", "风格", "主题", "路线", "流程"))
    if not has_modification and not targets and not has_direction:
        return None

    should_update_content = bool(has_modification and targets and effective_mode != "plan")
    decision_type = "content_revision" if should_update_content else "direction_update"
    if not targets and has_direction:
        targets = ["creation_contract"]

    return CreativeDecision(
        decision_type=decision_type,
        message=text,
        targets=targets,
        should_update_content=should_update_content,
        should_update_contract=True,
        reason="chat_message_contains_creative_direction_or_revision",
    )


def _append_unique_note(existing: Any, note: str) -> List[str]:
    notes = [str(item).strip() for item in existing] if isinstance(existing, list) else []
    notes = [item for item in notes if item]
    if note and note not in notes:
        notes.append(note)
    return notes[-50:]


def _chapter_number_from_message(message: str) -> int:
    match = re.search(r"第\s*(\d+)\s*章", message)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 0


def _row_matches_message(row: Dict[str, Any], message: str, *, data_type: str) -> bool:
    if data_type == "chapters":
        target_number = _chapter_number_from_message(message)
        if target_number:
            try:
                return int(row.get("chapter_number") or row.get("number") or 0) == target_number
            except (TypeError, ValueError):
                return False
    title_parts = [
        str(row.get("name") or ""),
        str(row.get("title") or ""),
        str(row.get("description") or ""),
    ]
    return any(part and part in message for part in title_parts)


def _make_revision_row(config: Dict[str, Any], message: str) -> Dict[str, Any]:
    title_key = str(config.get("title_key") or "name")
    now = datetime.now().isoformat()
    row = {
        title_key: f"{config.get('label', '内容')}聊天修正记录",
        "description": message,
        "kind": "chat_revision",
        "revision_notes": [message],
        "created_at": now,
        "updated_at": now,
    }
    if title_key != "title":
        row.setdefault("title", row[title_key])
    return row


def _update_project_rows(pm: Any, data_type: str, message: str) -> Optional[Dict[str, str]]:
    config = next((cfg for cfg in CREATIVE_OBJECTS.values() if cfg.get("data_type") == data_type), None)
    if not config:
        return None

    try:
        rows = pm.load_project_data(data_type)
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []

    touched = False
    matched = False
    next_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            next_rows.append(row)
            continue
        row_copy = dict(row)
        if _row_matches_message(row_copy, message, data_type=data_type) or not rows:
            row_copy["revision_notes"] = _append_unique_note(row_copy.get("revision_notes"), message)
            row_copy["updated_at"] = datetime.now().isoformat()
            touched = True
            matched = True
        next_rows.append(row_copy)

    if rows and not matched:
        # Keep the original rows intact and add a scoped revision row.
        next_rows.append(_make_revision_row(config, message))
        touched = True
    elif not rows:
        next_rows.append(_make_revision_row(config, message))
        touched = True

    if not touched:
        return None

    existed_before = False
    try:
        data_path = pm.get_project_data_path(data_type)
        existed_before = data_path.exists()
        pm.save_project_data(data_type, next_rows)
    except Exception:
        return None

    return {
        "path": str(data_path),
        "kind": data_type,
        "label": str(config.get("label") or data_type),
        "status": "updated" if existed_before else "created",
    }


def _update_creation_contract(pm: Any, decision: CreativeDecision) -> Optional[Dict[str, str]]:
    try:
        payload = pm.load_project_state("creation_contract", default={})
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    payload.setdefault("metadata", {})
    if not isinstance(payload.get("metadata"), dict):
        payload["metadata"] = {}
    payload.setdefault("scope", {})
    if not isinstance(payload.get("scope"), dict):
        payload["scope"] = {}

    payload["metadata"]["chat_revision_notes"] = _append_unique_note(
        payload["metadata"].get("chat_revision_notes"),
        decision.message,
    )
    discussion_context = str(payload["scope"].get("discussion_context") or "").strip()
    addition = f"用户聊天决策：{decision.message}"
    if addition not in discussion_context:
        payload["scope"]["discussion_context"] = (discussion_context + "\n" + addition).strip()
    payload["updated_at"] = datetime.now().isoformat()
    pm.save_project_state("creation_contract", payload)
    try:
        path = pm.get_project_state_path("creation_contract")
    except Exception:
        path = Path("")
    return {
        "path": str(path),
        "kind": "creation_contract",
        "label": "创作合同",
        "status": "updated",
    }


def _update_task_pool(pm: Any, decision: CreativeDecision) -> Optional[Dict[str, str]]:
    try:
        payload = pm.load_project_state("task_pool", default={})
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or not payload:
        return None
    payload.setdefault("metadata", {})
    if not isinstance(payload.get("metadata"), dict):
        payload["metadata"] = {}
    payload["metadata"]["chat_revision_notes"] = _append_unique_note(
        payload["metadata"].get("chat_revision_notes"),
        decision.message,
    )
    payload["metadata"]["needs_replan"] = True
    payload["updated_at"] = datetime.now().isoformat()
    pm.save_project_state("task_pool", payload)
    try:
        path = pm.get_project_state_path("task_pool")
    except Exception:
        path = Path("")
    return {
        "path": str(path),
        "kind": "task_pool",
        "label": "任务池",
        "status": "updated",
    }


def _append_decision_record(pm: Any, record: Dict[str, Any]) -> None:
    try:
        existing = pm.load_project_state(DECISION_STATE_KEY, default=[])
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []
    existing.append(record)
    pm.save_project_state(DECISION_STATE_KEY, existing[-200:])


def apply_creative_decision(pm: Any, decision: CreativeDecision, mode: str = "auto") -> Dict[str, Any]:
    """Persist a creative decision and apply deterministic project updates."""
    effective_mode = _normalize_mode(mode)
    updated_files: List[Dict[str, str]] = []

    if decision.should_update_contract:
        contract_file = _update_creation_contract(pm, decision)
        if contract_file:
            updated_files.append(contract_file)
        task_pool_file = _update_task_pool(pm, decision)
        if task_pool_file:
            updated_files.append(task_pool_file)

    if decision.should_update_content and effective_mode != "plan":
        for target in decision.targets:
            config = CREATIVE_OBJECTS.get(target)
            data_type = str((config or {}).get("data_type") or "").strip()
            if not data_type:
                continue
            file_record = _update_project_rows(pm, data_type, decision.message)
            if file_record:
                updated_files.append(file_record)

    status = "applied" if updated_files else "recorded"
    record = decision.to_record(mode=effective_mode, status=status, updated_files=updated_files)
    _append_decision_record(pm, record)
    return {
        "applied": bool(updated_files),
        "decision": record,
        "updated_files": updated_files,
    }


def process_chat_creative_decision(pm: Any, message: str, mode: str = "auto") -> Optional[Dict[str, Any]]:
    """Detect and persist/apply a chat creative decision."""
    decision = detect_creative_decision(message, mode=mode)
    if decision is None:
        return None
    return apply_creative_decision(pm, decision, mode=mode)
