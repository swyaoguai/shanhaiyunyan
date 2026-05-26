"""Auto-save structured artifacts from assistant chat replies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


BUILTIN_CATEGORY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "key": "worldbuilding",
        "name": "世界观设定",
        "builtin": True,
        "aliases": [
            "世界观",
            "世界设定",
            "世界观设定",
            "基础设定",
            "力量体系",
            "修炼体系",
            "魔法体系",
            "地理环境",
            "历史背景",
            "文化习俗",
            "势力",
            "规则",
        ],
    },
    {
        "key": "characters",
        "name": "角色档案",
        "builtin": True,
        "aliases": [
            "角色",
            "角色档案",
            "人物",
            "人物档案",
            "人设",
            "核心人设",
            "角色卡",
            "人物卡",
            "主角",
            "配角",
            "反派",
        ],
    },
    {
        "key": "outline",
        "name": "大纲",
        "builtin": True,
        "aliases": [
            "大纲",
            "故事大纲",
            "章节大纲",
            "总纲",
            "主线大纲",
            "剧情规划",
            "章节规划",
            "后续创作计划",
            "创作计划",
        ],
    },
    {
        "key": "detail_settings",
        "name": "细纲设定",
        "builtin": True,
        "aliases": ["细纲", "细纲设定", "详细大纲", "分场细纲", "场景规划"],
    },
    {
        "key": "chapter_settings",
        "name": "章纲设定",
        "builtin": True,
        "aliases": ["章纲", "章纲设定", "章节设定", "本章目标", "章节目标"],
    },
    {
        "key": "eventlines",
        "name": "事件线",
        "builtin": True,
        "aliases": ["事件线", "剧情线", "故事线", "主线", "支线", "伏笔", "冲突线"],
    },
    {
        "key": "items",
        "name": "道具物品",
        "builtin": True,
        "aliases": ["道具", "物品", "装备", "法宝", "线索物", "物件"],
    },
    {
        "key": "chapter_summary",
        "name": "正文摘要",
        "builtin": True,
        "aliases": ["正文摘要", "章节摘要", "章节总结", "剧情摘要", "阶段总结"],
    },
    {
        "key": "chapters",
        "name": "正文章节",
        "builtin": True,
        "aliases": ["正文章节", "章节正文", "正文", "小说正文"],
    },
]

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BOLD_HEADING_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(.{2,80}?)\*\*\s*[:：]?\s*$")
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:第?\s*[一二三四五六七八九十百千万两零〇0-9]+\s*[、.．]|[一二三四五六七八九十百千万两零〇]+[、.．])\s*(.{2,80}?)\s*$"
)
_SHORT_COLON_HEADING_RE = re.compile(r"^\s*([^：:\n]{2,36})[：:]\s*$")
_CHAPTER_RE = re.compile(r"第\s*([0-9一二三四五六七八九十百千万两零〇]+)\s*章")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、]\s*)")
_FAILED_SECTION_TITLE_MARKERS = ("失败", "错误", "异常", "取消", "中止", "未能", "无法")
_FAILED_SECTION_BODY_MARKERS = (
    "生成失败",
    "执行失败",
    "创建失败",
    "保存失败",
    "构建失败",
    "角色构建结果为空",
    "未能创建",
    "未能生成",
    "无法创建",
    "无法生成",
    "当前请求失败",
    "当前信息不足",
)
_CHAT_TRANSCRIPT_TITLE_MARKERS = (
    "聊天生成",
    "聊天修正记录",
    "我帮你",
    "好啦",
    "好的",
    "已根据这轮讨论",
    "已自动同步",
)


@dataclass
class ChatArtifact:
    data_type: str
    category_name: str
    rows: List[Dict[str, Any]] = field(default_factory=list)
    builtin: bool = True


def process_assistant_auto_save(
    project_manager: Any,
    assistant_text: str,
    *,
    mode: str,
    auto_save_enabled: bool,
    categories: Optional[List[Dict[str, Any]]] = None,
    session_id: str = "",
    source_mode: str = "multi_agent",
) -> Optional[Dict[str, Any]]:
    """Extract and persist assistant-generated artifacts when auto-save is enabled."""
    if str(mode or "").strip().lower() != "execute" or not auto_save_enabled:
        return None
    if not project_manager or not getattr(project_manager, "current_project_id", ""):
        return None

    text = str(assistant_text or "").strip()
    if not text:
        return None

    artifacts = extract_chat_artifacts(text, categories=categories)
    if not artifacts:
        return None

    created_files: List[Dict[str, str]] = []
    updated_files: List[Dict[str, str]] = []
    saved_artifacts: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for artifact in artifacts:
        if not artifact.rows:
            continue
        try:
            file_record, saved_count = _persist_artifact(
                project_manager,
                artifact,
                session_id=session_id,
                source_text=text,
                source_mode=source_mode,
            )
        except Exception as exc:
            errors.append({
                "data_type": artifact.data_type,
                "error": str(exc),
            })
            continue

        if not file_record or saved_count <= 0:
            continue
        if file_record["status"] == "created":
            created_files.append(file_record)
        else:
            updated_files.append(file_record)
        saved_artifacts.append({
            "data_type": artifact.data_type,
            "category_name": artifact.category_name,
            "count": saved_count,
            "builtin": artifact.builtin,
        })

    if not saved_artifacts and not errors:
        return None

    summary = _format_summary(saved_artifacts, errors)
    return {
        "applied": bool(saved_artifacts),
        "summary": summary,
        "artifacts": saved_artifacts,
        "created_files": created_files,
        "updated_files": updated_files,
        "errors": errors,
    }


def extract_chat_artifacts(
    assistant_text: str,
    *,
    categories: Optional[List[Dict[str, Any]]] = None,
) -> List[ChatArtifact]:
    text = str(assistant_text or "").strip()
    if not text:
        return []

    category_defs = _merge_category_definitions(categories or [])
    sections = _split_markdown_sections(text)
    grouped: Dict[str, ChatArtifact] = {}

    for title, content in sections:
        section_text = str(content or "").strip()
        section_title = _clean_title(title) or "聊天生成资料"
        if not section_text:
            continue
        if _is_failed_artifact_section(section_title, section_text):
            continue

        category = _classify_section(section_title, section_text, category_defs)
        if not category:
            continue

        data_type = str(category.get("key") or "").strip()
        if not data_type:
            continue
        if not _is_saveable_artifact_section(data_type, section_title, section_text, category):
            continue
        rows = _rows_for_category(data_type, section_title, section_text)
        if not rows:
            continue

        artifact = grouped.setdefault(
            data_type,
            ChatArtifact(
                data_type=data_type,
                category_name=str(category.get("name") or data_type),
                builtin=bool(category.get("builtin", True)),
            ),
        )
        artifact.rows.extend(rows)

    return [artifact for artifact in grouped.values() if artifact.rows]


def _persist_artifact(
    project_manager: Any,
    artifact: ChatArtifact,
    *,
    session_id: str,
    source_text: str,
    source_mode: str,
) -> Tuple[Dict[str, str], int]:
    from .source_modes import ensure_record_source_mode, normalize_source_mode

    data_type = artifact.data_type
    path = project_manager.get_project_data_path(data_type)
    existed_before = path.exists()
    normalized_source_mode = normalize_source_mode(source_mode, default="multi_agent")

    existing_rows = project_manager.load_project_data(data_type)
    if not isinstance(existing_rows, list):
        existing_rows = []

    now = datetime.now().isoformat()
    prepared_rows = []
    for row in artifact.rows:
        row_copy = dict(row)
        row_copy.setdefault("source", "copilot_auto_save")
        row_copy.setdefault("source_type", "copilot_chat")
        if session_id:
            row_copy.setdefault("source_session_id", session_id)
        row_copy.setdefault("source_preview", source_text[:300])
        row_copy = ensure_record_source_mode(
            row_copy,
            normalized_source_mode,
            source_type="copilot_chat",
            source_session_id=session_id,
        )
        row_copy["updated_at"] = now
        row_copy.setdefault("created_at", now)
        prepared_rows.append(row_copy)

    merged_rows, saved_count = _merge_rows(data_type, existing_rows, prepared_rows)
    if saved_count <= 0:
        return {}, 0

    project_manager.save_project_data(data_type, merged_rows)

    try:
        from .library_service import get_library_service

        svc = get_library_service(project_manager.get_current_project_dir())
        svc.upsert_from_legacy(data_type, merged_rows)
    except Exception:
        pass

    return {
        "path": str(path),
        "kind": data_type,
        "label": artifact.category_name,
        "status": "updated" if existed_before else "created",
    }, saved_count


def _merge_rows(
    data_type: str,
    existing_rows: List[Dict[str, Any]],
    new_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    merged = [dict(row) for row in existing_rows if isinstance(row, dict)]
    index_by_key: Dict[str, int] = {}
    for index, row in enumerate(merged):
        key = _row_identity(data_type, row)
        if key and key not in index_by_key:
            index_by_key[key] = index

    saved_count = 0
    for row in new_rows:
        row_copy = dict(row)
        if data_type == "chapters":
            _ensure_chapter_number(row_copy, merged)
        key = _row_identity(data_type, row_copy)
        if key and key in index_by_key:
            original = merged[index_by_key[key]]
            created_at = original.get("created_at")
            original.update(row_copy)
            if created_at:
                original["created_at"] = created_at
        else:
            if key:
                index_by_key[key] = len(merged)
            merged.append(row_copy)
        saved_count += 1
    return merged, saved_count


def _row_identity(data_type: str, row: Dict[str, Any]) -> str:
    if data_type == "chapters":
        chapter_number = row.get("chapter_number") or row.get("number")
        if chapter_number:
            return f"chapter:{chapter_number}"
    for key in ("id", "name", "title", "chapter_title"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return f"{data_type}:{value}"
    return ""


def _ensure_chapter_number(row: Dict[str, Any], existing_rows: List[Dict[str, Any]]) -> None:
    if row.get("chapter_number") or row.get("number"):
        return
    used = []
    for item in existing_rows:
        try:
            used.append(int(item.get("chapter_number") or item.get("number") or 0))
        except (TypeError, ValueError):
            continue
    row["chapter_number"] = (max(used) if used else 0) + 1


def _split_markdown_sections(text: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, List[str]]] = []
    current_title = ""
    current_lines: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = _extract_heading(line)
        if heading:
            if current_title or any(part.strip() for part in current_lines):
                sections.append((current_title, current_lines))
            current_title = heading
            current_lines = []
        else:
            current_lines.append(line)

    if current_title or any(part.strip() for part in current_lines):
        sections.append((current_title, current_lines))

    if not sections:
        return [("聊天生成资料", text)]

    return [
        (title or "聊天生成资料", "\n".join(lines).strip())
        for title, lines in sections
        if (title or "\n".join(lines).strip())
    ]


def _extract_heading(line: str) -> str:
    stripped = str(line or "").strip()
    if not stripped:
        return ""

    for regex in (_HEADING_RE, _BOLD_HEADING_RE, _NUMBERED_HEADING_RE, _SHORT_COLON_HEADING_RE):
        match = regex.match(stripped)
        if match:
            candidate = _clean_title(match.group(1))
            if _looks_like_heading(candidate):
                return candidate
    return ""


def _looks_like_heading(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 2 or len(text) > 80:
        return False
    if text.endswith(("。", "！", "？", "；")):
        return False
    return True


def _merge_category_definitions(categories: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {
        str(item["key"]): dict(item) for item in BUILTIN_CATEGORY_DEFINITIONS
    }
    for item in categories:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        existing = merged.get(key, {})
        aliases = []
        for alias in [*(existing.get("aliases") or []), *(item.get("aliases") or [])]:
            text = str(alias or "").strip()
            if text and text not in aliases:
                aliases.append(text)
        merged[key] = {**existing, **dict(item), "aliases": aliases}
    return list(merged.values())


def _classify_section(
    title: str,
    content: str,
    categories: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if _is_chapter_section(title, content):
        return next((item for item in categories if item.get("key") == "chapters"), None)

    title_text = _normalize_match_text(title)
    body_text = _normalize_match_text(content[:500])
    best: Optional[Dict[str, Any]] = None
    best_score = 0

    for category in categories:
        for alias in _category_aliases(category):
            normalized_alias = _normalize_match_text(alias)
            if not normalized_alias:
                continue
            score = 0
            if normalized_alias in title_text:
                score = 100 + len(normalized_alias)
            elif len(normalized_alias) >= 2 and normalized_alias in body_text:
                score = len(normalized_alias)
            if score > best_score:
                best = category
                best_score = score

    return best


def _category_aliases(category: Dict[str, Any]) -> List[str]:
    values = [
        category.get("name"),
        category.get("key"),
        category.get("id"),
        *(category.get("aliases") or [] if isinstance(category.get("aliases"), list) else []),
    ]
    aliases: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


def _is_chapter_section(title: str, content: str) -> bool:
    title_text = str(title or "")
    content_text = str(content or "")
    if _CHAPTER_RE.search(title_text):
        return "正文" in title_text or len(content_text) >= 120
    if any(token in title_text for token in ("章节正文", "正文章节", "小说正文")):
        return len(content_text) >= 120
    return False


def _is_failed_artifact_section(title: str, content: str) -> bool:
    title_text = _normalize_match_text(title)
    if title_text and any(marker in title_text for marker in _FAILED_SECTION_TITLE_MARKERS):
        return True

    body_text = _normalize_match_text(str(content or "")[:300])
    return any(marker in body_text for marker in _FAILED_SECTION_BODY_MARKERS)


def _category_matches_title(category: Dict[str, Any], title: str) -> bool:
    title_text = _normalize_match_text(title)
    if not title_text:
        return False
    return any(
        _normalize_match_text(alias) in title_text
        for alias in _category_aliases(category)
        if _normalize_match_text(alias)
    )


def _has_labeled_field(content: str, labels: Iterable[str]) -> bool:
    for label in labels:
        if re.search(rf"(?:^|\n)\s*(?:[-*]\s*)?{re.escape(label)}\s*[：:]", content):
            return True
    return False


def _is_chat_transcript_section(title: str) -> bool:
    normalized_title = _normalize_match_text(title)
    return any(_normalize_match_text(marker) in normalized_title for marker in _CHAT_TRANSCRIPT_TITLE_MARKERS)


def _is_saveable_artifact_section(
    data_type: str,
    title: str,
    content: str,
    category: Dict[str, Any],
) -> bool:
    clean_content = _clean_content(content)
    if not clean_content or _is_chat_transcript_section(title):
        return False
    title_matches_category = _category_matches_title(category, title)

    if data_type == "chapters":
        return _is_chapter_section(title, clean_content)
    if data_type == "characters":
        return bool(
            _extract_named_value(clean_content, ("姓名", "角色名", "名字", "主角", "男主", "女主", "配角", "反派"))
            or (
                title_matches_category
                and _has_labeled_field(clean_content, ("身份", "性格", "动机", "目标", "关系", "外貌", "能力", "背景"))
            )
        )
    if data_type in {"worldbuilding", "outline", "detail_settings", "chapter_settings", "eventlines", "items", "chapter_summary"}:
        return title_matches_category and len(clean_content) >= 8
    if not bool(category.get("builtin", True)):
        return title_matches_category and len(clean_content) >= 2
    return title_matches_category and len(clean_content) >= 8


def _rows_for_category(data_type: str, title: str, content: str) -> List[Dict[str, Any]]:
    clean_title = _clean_title(title)
    clean_content = _clean_content(content)
    if not clean_content:
        return []

    if data_type == "worldbuilding":
        return [{
            "name": _fallback_title(clean_title, "世界观设定"),
            "kind": _infer_world_kind(clean_title),
            "description": _summarize(clean_content),
            "details": clean_content,
        }]
    if data_type == "characters":
        name = _extract_named_value(clean_content, ("姓名", "角色名", "名字", "主角", "男主", "女主", "配角", "反派"))
        return [{
            "name": name or _fallback_title(clean_title, "聊天生成角色"),
            "role": _infer_character_role(clean_title, clean_content),
            "description": _summarize(clean_content),
            "details": clean_content,
        }]
    if data_type == "outline":
        return [{
            "title": _fallback_title(clean_title, "聊天生成大纲"),
            "summary": clean_content,
        }]
    if data_type == "detail_settings":
        return [{
            "name": _fallback_title(clean_title, "聊天生成细纲"),
            "scene_goal": _summarize(clean_content),
            "notes": clean_content,
        }]
    if data_type == "chapter_settings":
        chapter_number = _parse_chapter_number(clean_title) or _parse_chapter_number(clean_content[:120])
        row = {
            "name": _fallback_title(clean_title, "聊天生成章纲"),
            "chapter_goal": _summarize(clean_content),
            "notes": clean_content,
        }
        if chapter_number:
            row["chapter_number"] = chapter_number
        return [row]
    if data_type == "eventlines":
        return [{
            "name": _fallback_title(clean_title, "聊天生成事件线"),
            "conflict": _summarize(clean_content),
            "status": "规划中",
            "notes": clean_content,
        }]
    if data_type == "items":
        return [{
            "name": _extract_named_value(clean_content, ("名称", "道具名", "物品名")) or _fallback_title(clean_title, "聊天生成物品"),
            "item_type": _infer_item_type(clean_title, clean_content),
            "description": _summarize(clean_content),
            "details": clean_content,
        }]
    if data_type == "chapter_summary":
        chapter_number = _parse_chapter_number(clean_title) or _parse_chapter_number(clean_content[:120])
        row = {
            "name": _fallback_title(clean_title, "聊天生成章节摘要"),
            "summary_text": clean_content,
        }
        if chapter_number:
            row["chapter_number"] = chapter_number
        return [row]
    if data_type == "chapters":
        chapter_number = _parse_chapter_number(clean_title) or _parse_chapter_number(clean_content[:120])
        row = {
            "title": _fallback_title(clean_title, "聊天生成正文"),
            "content": clean_content,
            "summary": _summarize(clean_content),
        }
        if chapter_number:
            row["chapter_number"] = chapter_number
        return [row]

    return [{
        "name": _fallback_title(clean_title, "聊天生成资料"),
        "title": _fallback_title(clean_title, "聊天生成资料"),
        "description": _summarize(clean_content),
        "details": clean_content,
        "content": clean_content,
    }]


def _clean_title(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\s*#{1,6}\s*", "", text)
    text = re.sub(r"^\s*(?:第?\s*[一二三四五六七八九十百千万两零〇0-9]+\s*[、.．])\s*", "", text)
    text = re.sub(r"^\s*[-*+]\s*", "", text)
    text = text.strip("*`：: \t")
    return text.strip()


def _clean_content(value: str) -> str:
    lines = [line.rstrip() for line in str(value or "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _fallback_title(title: str, fallback: str) -> str:
    text = _clean_title(title)
    if not text or text == "聊天生成资料":
        return fallback
    return text[:80]


def _summarize(content: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    text = _LIST_PREFIX_RE.sub("", text)
    return text[:limit].strip()


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[\s`*_#>\-—:：,，.。;；!！?？()\[\]（）【】《》]+", "", str(value or "").lower())


def _extract_named_value(content: str, labels: Iterable[str]) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^\n，,；;。()（）]{{1,40}})", content)
        if match:
            return match.group(1).strip(" -_*`")
    return ""


def _infer_character_role(title: str, content: str) -> str:
    text = f"{title}\n{content}"
    for role in ("主角", "男主", "女主", "配角", "反派", "导师", "盟友"):
        if role in text:
            return "主角" if role in {"男主", "女主"} else role
    return "其他"


def _infer_world_kind(title: str) -> str:
    mapping = [
        ("力量", "power_system"),
        ("修炼", "power_system"),
        ("魔法", "magic_system"),
        ("地理", "geography"),
        ("历史", "history"),
        ("文化", "culture"),
        ("势力", "faction"),
        ("规则", "rule"),
        ("地点", "location"),
        ("时间线", "timeline"),
        ("主题", "theme"),
    ]
    for marker, kind in mapping:
        if marker in title:
            return kind
    return "other"


def _infer_item_type(title: str, content: str) -> str:
    text = f"{title}\n{content}"
    for item_type in ("武器", "法宝", "道具", "装备", "资源", "线索"):
        if item_type in text:
            return item_type
    return "未分类"


def _parse_chapter_number(text: str) -> int:
    match = _CHAPTER_RE.search(str(text or ""))
    if not match:
        return 0
    raw = match.group(1).strip()
    if raw.isdigit():
        return int(raw)
    return _chinese_number_to_int(raw)


def _chinese_number_to_int(raw: str) -> int:
    digit_map = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    unit_map = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    current = 0
    for char in raw:
        if char in digit_map:
            current = digit_map[char]
            continue
        if char in unit_map:
            unit_value = unit_map[char]
            if current == 0:
                current = 1
            if unit_value >= 10000:
                total = (total + current) * unit_value
            else:
                total += current * unit_value
            current = 0
            continue
        return 0
    return total + current


def _format_summary(saved_artifacts: List[Dict[str, Any]], errors: List[Dict[str, str]]) -> str:
    if not saved_artifacts and errors:
        return "自动同步资料失败，请稍后重试或手动保存。"
    parts = [
        f"{item.get('category_name') or item.get('data_type')} {item.get('count') or 0} 条"
        for item in saved_artifacts
    ]
    suffix = f"；{len(errors)} 类资料同步失败" if errors else ""
    return "已自动同步到资料库：" + "、".join(parts) + suffix + "。"
