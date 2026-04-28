"""Project management API routes."""

import json
import shutil
import tempfile
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..models.requests import (
    ProjectCreateRequest,
    ProjectStateBatchGetRequest,
    ProjectStateBatchSetRequest,
    ProjectUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BACKUP_UPLOAD_MAX_BYTES = 100 * 1024 * 1024
BACKUP_UPLOAD_CHUNK_BYTES = 1024 * 1024
BACKUP_EXTRACT_MAX_TOTAL_BYTES = 500 * 1024 * 1024
BACKUP_EXTRACT_MAX_FILES = 10000
BACKUP_EXTRACT_MAX_COMPRESSION_RATIO = 200
NOVEL_IMPORT_MAX_BYTES = 20 * 1024 * 1024
BUILTIN_PROJECT_DATA_TYPES = {
    "outline",
    "worldbuilding",
    "characters",
    "items",
    "eventlines",
    "outline_settings",
    "detail_settings",
    "chapter_settings",
    "chapter_summary",
}


def _is_path_within(base_dir: Path, target_path: Path) -> bool:
    resolved_base = base_dir.resolve()
    resolved_target = target_path.resolve()
    try:
        return resolved_target.is_relative_to(resolved_base)
    except AttributeError:
        return str(resolved_target).startswith(str(resolved_base))


def _normalize_project_row(row: Any, title_key: str = "name") -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    normalized = dict(row)
    primary_title = str(normalized.get(title_key) or normalized.get("title") or "").strip()
    if title_key == "title":
        normalized["title"] = primary_title
    else:
        normalized[title_key] = primary_title
    if "description" in normalized or "content" in normalized:
        normalized["description"] = str(
            normalized.get("description") or normalized.get("content") or ""
        ).strip()
    if "details" in normalized and isinstance(normalized.get("details"), str):
        normalized["details"] = str(normalized.get("details") or "").strip()
    if not str(normalized.get("description") or "").strip():
        normalized["description"] = _summarize_project_value(
            normalized.get("details")
            or normalized.get("summary")
            or normalized.get("notes")
            or normalized.get("motivation")
            or normalized.get("goal")
            or normalized.get("goals")
            or normalized.get("conflict")
            or normalized.get("key_event")
            or normalized.get("properties")
            or normalized.get("effects")
            or normalized.get("participants")
            or normalized.get("tags")
        )
    return normalized


def _summarize_project_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(
                    item.get("name")
                    or item.get("title")
                    or item.get("description")
                    or item.get("content")
                    or ""
                ).strip()
                if not text:
                    for _v in item.values():
                        if isinstance(_v, str) and _v.strip():
                            text = _v.strip()
                            break
            else:
                text = str(item).strip()
            if text:
                parts.append(text)
            if len(parts) >= 3:
                break
        tail = f"等{len(value)}项" if len(value) > 3 else ""
        if parts:
            return "、".join(parts) + tail
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        str_parts: List[str] = []
        list_parts: List[str] = []
        for _k, item in value.items():
            if isinstance(item, str) and item.strip():
                str_parts.append(item.strip())
            elif isinstance(item, list) and item:
                first_items = []
                for li in item[:3]:
                    if isinstance(li, dict):
                        t = str(li.get("name") or li.get("title") or li.get("description") or "").strip()
                    else:
                        t = str(li).strip()
                    if t:
                        first_items.append(t)
                if first_items:
                    tail = f"等{len(item)}项" if len(item) > 3 else ""
                    list_parts.append("、".join(first_items) + tail)
        all_parts = str_parts + list_parts
        if all_parts:
            return "；".join(all_parts[:4])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _coerce_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.replace("；", "，").replace("、", "，").replace("\n", "，")
        return [part.strip() for part in text.split("，") if part.strip()]
    return []


def _coerce_optional_text(value: Any) -> str:
    return str(value or "").strip()


def _maybe_parse_structured_text(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return ""
    if text[:1] in {"{", "["}:
        try:
            return json.loads(text)
        except Exception:
            return text
    return text


def _normalize_outline_rows(payload: Any) -> List[Dict[str, Any]]:
    source = payload.get("chapters") if isinstance(payload, dict) and isinstance(payload.get("chapters"), list) else payload
    if not isinstance(source, list):
        return []

    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(source, start=1):
        normalized = _normalize_project_row(row, title_key="title")
        if not normalized:
            continue
        normalized["title"] = normalized.get("title") or f"第{index}章"
        normalized["summary"] = str(
            normalized.get("summary") or normalized.get("content") or ""
        ).strip()
        normalized["content"] = str(normalized.get("content") or "").strip()
        rows.append(normalized)
    return rows


def _normalize_worldbuilding_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [_normalize_project_row(row, title_key="name") for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    rows: List[Dict[str, Any]] = []
    world_payload = payload.get("world", payload)
    if isinstance(world_payload, dict):
        world_name = str(world_payload.get("name") or world_payload.get("world_name") or "").strip()
        world_type = str(world_payload.get("world_type") or "").strip()
        if world_name or world_type:
            rows.append({
                "name": world_name or "世界名称",
                "description": world_type,
                "kind": "world",
                "details": _summarize_project_value(world_payload.get("theme") or world_payload.get("requirements")),
                "tags": _coerce_text_list(world_payload.get("tags")),
            })

        theme = _summarize_project_value(world_payload.get("theme"))
        if theme:
            rows.append({"name": "主题基调", "description": theme, "kind": "theme"})

        requirements = _summarize_project_value(world_payload.get("requirements"))
        if requirements:
            rows.append({"name": "创作要求", "description": requirements, "kind": "requirements"})

        section_fields = [
            ("power_system", "力量体系"),
            ("geography", "地理环境"),
            ("history", "历史背景"),
            ("culture", "文化习俗"),
            ("magic_system", "魔法体系"),
            ("technology_level", "科技水平"),
            ("timeline", "时间线"),
        ]
        for key, label in section_fields:
            summary = _summarize_project_value(world_payload.get(key))
            if summary:
                rows.append({
                    "name": label,
                    "description": summary,
                    "details": summary if isinstance(world_payload.get(key), str) else json.dumps(world_payload.get(key), ensure_ascii=False),
                    "kind": key,
                })

        rules = world_payload.get("rules")
        if isinstance(rules, list):
            for rule in rules:
                text = str(rule).strip()
                if text:
                    rows.append({"name": "世界规则", "description": text, "details": "", "kind": "rule"})

        factions = world_payload.get("factions")
        if isinstance(factions, list):
            for faction in factions:
                if not isinstance(faction, dict):
                    continue
                name = str(faction.get("name") or "势力阵营").strip() or "势力阵营"
                description = _summarize_project_value(faction.get("description") or faction)
                rows.append({
                    "name": name,
                    "description": description,
                    "details": _coerce_optional_text(faction.get("details")),
                    "kind": "faction",
                    "leader": _coerce_optional_text(faction.get("leader")),
                    "goal": _coerce_optional_text(faction.get("goal")),
                    "tags": _coerce_text_list(faction.get("tags")),
                })

    for location_name, location_payload in (payload.get("locations") or {}).items() if isinstance(payload.get("locations"), dict) else []:
        rows.append({
            "name": str(location_name).strip() or "地点",
            "description": _summarize_project_value(location_payload),
            "details": _coerce_optional_text(location_payload.get("details")) if isinstance(location_payload, dict) else "",
            "kind": "location",
            "region": _coerce_optional_text(location_payload.get("region")) if isinstance(location_payload, dict) else "",
            "tags": _coerce_text_list(location_payload.get("tags")) if isinstance(location_payload, dict) else [],
        })

    for item_name, item_payload in (payload.get("items") or {}).items() if isinstance(payload.get("items"), dict) else []:
        rows.append({
            "name": str(item_name).strip() or "设定条目",
            "description": _summarize_project_value(item_payload),
            "details": _coerce_optional_text(item_payload.get("details")) if isinstance(item_payload, dict) else "",
            "kind": "item",
            "owner": _coerce_optional_text(item_payload.get("owner")) if isinstance(item_payload, dict) else "",
            "effects": item_payload.get("effects") if isinstance(item_payload, dict) else [],
            "tags": _coerce_text_list(item_payload.get("tags")) if isinstance(item_payload, dict) else [],
        })

    events = payload.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            name = str(event.get("name") or event.get("title") or event.get("date") or "历史事件").strip()
            rows.append({
                "name": name or "历史事件",
                "description": _summarize_project_value(event.get("description") or event),
                "details": _coerce_optional_text(event.get("details")),
                "kind": "event",
                "date": _coerce_optional_text(event.get("date")),
                "impact": _coerce_optional_text(event.get("impact")),
                "participants": event.get("participants") if isinstance(event.get("participants"), list) else _coerce_text_list(event.get("participants")),
            })

    return rows


def _normalize_character_rows(payload: Any) -> List[Dict[str, Any]]:
    from ...context.character_manager import CharacterManager

    try:
        manager = CharacterManager()
        normalized = manager._normalize_character_payload(payload)
    except ValueError:
        return []
    return [dict(item) for item in normalized.values()]


def _normalize_item_rows(payload: Any) -> List[Dict[str, Any]]:
    source = payload.get("items") if isinstance(payload, dict) and "items" in payload else payload
    rows: List[Dict[str, Any]] = []

    if isinstance(source, list):
        for row in source:
            normalized = _normalize_project_row(row, title_key="name")
            if normalized:
                rows.append(normalized)
        return rows

    if isinstance(source, dict):
        for name, row in source.items():
            if isinstance(row, dict):
                normalized = _normalize_project_row(row, title_key="name")
                normalized["name"] = normalized.get("name") or str(name).strip()
                rows.append(normalized)
            else:
                rows.append({"name": str(name).strip(), "description": _summarize_project_value(row)})
    return rows


def _normalize_named_rows(payload: Any, title_key: str = "name") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    source = payload if isinstance(payload, list) else []
    for row in source:
        normalized = _normalize_project_row(row, title_key=title_key)
        if normalized:
            primary_key = title_key if title_key in normalized else "name"
            normalized[primary_key] = str(
                normalized.get(primary_key)
                or normalized.get("title")
                or normalized.get("name")
                or "未命名条目"
            ).strip() or "未命名条目"
            rows.append(normalized)
    return rows


def _normalize_builtin_project_data(data_type: str, payload: Any) -> Dict[str, Any]:
    if data_type == "outline":
        return {"data": _normalize_outline_rows(payload), "raw_data": payload}
    if data_type == "worldbuilding":
        return {"data": _normalize_worldbuilding_rows(payload), "raw_data": payload}
    if data_type == "characters":
        return {"data": _normalize_character_rows(payload), "raw_data": payload}
    if data_type == "items":
        return {"data": _normalize_item_rows(payload), "raw_data": payload}
    if data_type in {"eventlines", "outline_settings", "detail_settings", "chapter_settings"}:
        return {"data": _normalize_named_rows(payload, title_key="name"), "raw_data": payload}
    if data_type == "chapter_summary":
        data = payload if isinstance(payload, list) else []
        return {"data": data, "raw_data": payload}
    return {"data": payload}


def _denormalize_outline_rows(rows: Any, existing_payload: Any) -> Any:
    normalized_rows = _normalize_outline_rows(rows)
    if isinstance(existing_payload, dict) and "chapters" in existing_payload:
        updated = dict(existing_payload)
        updated["chapters"] = normalized_rows
        return updated
    return normalized_rows


def _denormalize_worldbuilding_rows(rows: Any, existing_payload: Any) -> Any:
    normalized_rows = [
        _normalize_project_row(row, title_key="name")
        for row in rows
        if isinstance(row, dict)
    ] if isinstance(rows, list) else []
    if not normalized_rows:
        return []

    base_payload: Dict[str, Any] = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    world_existing = base_payload.get("world") if isinstance(base_payload.get("world"), dict) else {}
    world: Dict[str, Any] = dict(world_existing)
    world.setdefault("name", str(world_existing.get("name") or world_existing.get("world_name") or "项目世界观").strip() or "项目世界观")
    world.setdefault("world_name", world["name"])
    world.setdefault("world_type", str(world_existing.get("world_type") or "条目式设定").strip() or "条目式设定")

    locations: Dict[str, Dict[str, Any]] = {}
    items: Dict[str, Dict[str, Any]] = {}
    events: List[Dict[str, Any]] = []
    factions: List[Dict[str, Any]] = []
    rules: List[str] = []

    section_map = {
        "power_system": "power_system",
        "geography": "geography",
        "history": "history",
        "culture": "culture",
        "magic_system": "magic_system",
        "technology_level": "technology_level",
        "timeline": "timeline",
    }

    for row in normalized_rows:
        name = str(row.get("name") or "").strip()
        kind = str(row.get("kind") or "").strip()
        if not kind:
            inferred_kind_map = {
                "世界名称": "world",
                "主题基调": "theme",
                "创作要求": "requirements",
                "力量体系": "power_system",
                "地理环境": "geography",
                "历史背景": "history",
                "文化习俗": "culture",
                "魔法体系": "magic_system",
                "科技水平": "technology_level",
                "时间线": "timeline",
                "世界规则": "rule",
            }
            kind = inferred_kind_map.get(name, "")
        description = _coerce_optional_text(row.get("description"))
        details = row.get("details")
        tags = _coerce_text_list(row.get("tags"))

        if kind == "world":
            actual_name = description if name == "世界名称" and description else name
            if actual_name:
                world["name"] = actual_name
                world["world_name"] = actual_name
            if description:
                if name != "世界名称":
                    world["world_type"] = description
            detail_text = _coerce_optional_text(details)
            if detail_text:
                world["theme"] = detail_text
            if tags:
                world["tags"] = tags
            continue

        if kind == "theme":
            world["theme"] = description or _coerce_optional_text(details)
            continue

        if kind == "requirements":
            world["requirements"] = description or _coerce_optional_text(details)
            continue

        if kind in section_map:
            world[section_map[kind]] = _maybe_parse_structured_text(details or description)
            continue

        if kind == "rule":
            text = description or _coerce_optional_text(details) or name
            if text:
                rules.append(text)
            continue

        if kind == "faction":
            if name:
                faction_payload: Dict[str, Any] = {
                    "name": name,
                    "description": description,
                }
                if _coerce_optional_text(details):
                    faction_payload["details"] = _coerce_optional_text(details)
                if _coerce_optional_text(row.get("leader")):
                    faction_payload["leader"] = _coerce_optional_text(row.get("leader"))
                if _coerce_optional_text(row.get("goal")):
                    faction_payload["goal"] = _coerce_optional_text(row.get("goal"))
                if tags:
                    faction_payload["tags"] = tags
                factions.append(faction_payload)
            continue

        if kind == "location" and name:
            payload: Dict[str, Any] = {"description": description}
            if _coerce_optional_text(details):
                payload["details"] = _coerce_optional_text(details)
            if _coerce_optional_text(row.get("region")):
                payload["region"] = _coerce_optional_text(row.get("region"))
            if tags:
                payload["tags"] = tags
            locations[name] = payload
            continue

        if kind == "item" and name:
            payload = {"description": description}
            if _coerce_optional_text(details):
                payload["details"] = _coerce_optional_text(details)
            if _coerce_optional_text(row.get("owner")):
                payload["owner"] = _coerce_optional_text(row.get("owner"))
            effects = row.get("effects")
            if effects:
                payload["effects"] = effects if isinstance(effects, list) else _coerce_text_list(effects)
            if tags:
                payload["tags"] = tags
            items[name] = payload
            continue

        if kind == "event":
            event_payload: Dict[str, Any] = {
                "title": name or "历史事件",
                "description": description,
            }
            if _coerce_optional_text(details):
                event_payload["details"] = _coerce_optional_text(details)
            if _coerce_optional_text(row.get("date")):
                event_payload["date"] = _coerce_optional_text(row.get("date"))
            if _coerce_optional_text(row.get("impact")):
                event_payload["impact"] = _coerce_optional_text(row.get("impact"))
            participants = row.get("participants")
            if participants:
                event_payload["participants"] = participants if isinstance(participants, list) else _coerce_text_list(participants)
            events.append(event_payload)
            continue

        fallback_text = "：".join(part for part in [name, description or _coerce_optional_text(details)] if part)
        if fallback_text:
            rules.append(fallback_text)

    if factions:
        world["factions"] = factions
    if rules:
        world["rules"] = rules

    base_payload["world"] = world
    base_payload["locations"] = locations
    base_payload["items"] = items
    base_payload["events"] = events
    return base_payload


def _denormalize_character_rows(rows: Any, existing_payload: Any) -> Any:
    from ...context.character_manager import CharacterManager

    manager = CharacterManager()
    normalized: Dict[str, Dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            char_data = manager._coerce_character_data(row)
            if char_data:
                normalized[char_data["name"]] = char_data

    if isinstance(existing_payload, dict) and "characters" in existing_payload:
        updated = dict(existing_payload)
        updated["characters"] = normalized
        return updated
    return normalized if normalized else []


def _denormalize_item_rows(rows: Any, existing_payload: Any) -> Any:
    normalized_rows = [
        _normalize_project_row(row, title_key="name")
        for row in rows
        if isinstance(row, dict)
    ] if isinstance(rows, list) else []

    if isinstance(existing_payload, dict) and "items" in existing_payload:
        updated = dict(existing_payload)
        if isinstance(existing_payload.get("items"), dict):
            updated["items"] = {
                str(row.get("name") or "").strip(): row
                for row in normalized_rows
                if str(row.get("name") or "").strip()
            }
        else:
            updated["items"] = normalized_rows
        return updated
    return normalized_rows


def _denormalize_named_rows(rows: Any) -> Any:
    return _normalize_named_rows(rows, title_key="name")


def _denormalize_builtin_project_data(data_type: str, rows: Any, existing_payload: Any) -> Any:
    if data_type == "outline":
        return _denormalize_outline_rows(rows, existing_payload)
    if data_type == "worldbuilding":
        return _denormalize_worldbuilding_rows(rows, existing_payload)
    if data_type == "characters":
        return _denormalize_character_rows(rows, existing_payload)
    if data_type == "items":
        return _denormalize_item_rows(rows, existing_payload)
    if data_type in {"eventlines", "outline_settings", "detail_settings", "chapter_settings"}:
        return _denormalize_named_rows(rows)
    return rows


def _get_backup_targets() -> dict:
    from ...constants import get_app_root, get_data_dir

    app_root = Path(get_app_root())
    root_data_dir = Path(get_data_dir())
    package_data_dir = Path(__file__).resolve().parents[2] / "data"

    return {
        "app_root": app_root,
        "root_data_dir": root_data_dir,
        "package_data_dir": package_data_dir,
        "env_file": app_root / ".env",
    }


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()

            if len(members) > BACKUP_EXTRACT_MAX_FILES:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件数量超过限制（最多 {BACKUP_EXTRACT_MAX_FILES} 个）",
                )

            declared_total_size = 0
            validated_members = []

            for member in members:
                member_path = (target_dir / member.filename).resolve()
                if not _is_path_within(target_dir, member_path):
                    raise HTTPException(status_code=400, detail=f"非法压缩包路径: {member.filename}")

                declared_total_size += max(0, member.file_size)
                if declared_total_size > BACKUP_EXTRACT_MAX_TOTAL_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"解压后文件总大小超过限制（最大 "
                            f"{BACKUP_EXTRACT_MAX_TOTAL_BYTES // (1024 * 1024)}MB）"
                        ),
                    )

                if member.compress_size > 0:
                    compression_ratio = member.file_size / member.compress_size
                    if compression_ratio > BACKUP_EXTRACT_MAX_COMPRESSION_RATIO:
                        raise HTTPException(
                            status_code=400,
                            detail=f"压缩包存在异常高压缩比文件: {member.filename}",
                        )

                validated_members.append((member, member_path))

            extracted_total_size = 0
            for member, member_path in validated_members:
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue

                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as source, member_path.open("wb") as destination:
                    while True:
                        chunk = source.read(BACKUP_UPLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        extracted_total_size += len(chunk)
                        if extracted_total_size > BACKUP_EXTRACT_MAX_TOTAL_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail=(
                                    f"解压后文件总大小超过限制（最大 "
                                    f"{BACKUP_EXTRACT_MAX_TOTAL_BYTES // (1024 * 1024)}MB）"
                                ),
                            )
                        destination.write(chunk)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="备份文件不是有效的ZIP格式") from exc


def _require_current_project(pm) -> None:
    if not pm.current_project_id:
        raise ValueError("请先选择或创建一个项目")


def _copy_dir_contents(src: Path, dst: Path, overwrite: bool) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for file in src.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not target.exists():
            shutil.copy2(file, target)


@router.get("/projects")
async def list_projects():
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    return JSONResponse({
        "projects": pm.list_projects(),
        "current_project_id": pm.current_project_id,
    })


@router.post("/projects")
async def create_project(request: ProjectCreateRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project = pm.create_project(request.name, request.description)
    return JSONResponse({
        "success": True,
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
        },
    })


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project = pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return JSONResponse({
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at,
        "word_count": project.word_count,
        "chapter_count": project.chapter_count,
    })


@router.post("/projects/{project_id}/switch")
async def switch_project(project_id: str):
    from ...project_manager import get_project_manager
    from ..runtime_refresh import refresh_runtime_after_project_switch

    pm = get_project_manager()
    target_project = pm.get_project(project_id)
    if not target_project:
        raise HTTPException(status_code=404, detail="Project not found")

    previous_project_id = pm.current_project_id or ""
    if not pm.switch_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    refresh_result = refresh_runtime_after_project_switch(
        previous_project_id=previous_project_id,
        current_project_id=project_id,
    )
    return JSONResponse({
        "success": True,
        "project_id": project_id,
        "project_name": target_project.name,
        "runtime_synced": True,
        "refresh_result": refresh_result,
    })


@router.put("/projects/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    project = pm.update_project(project_id, **updates)
    if project:
        return JSONResponse({"success": True})
    raise HTTPException(status_code=404, detail="Project not found")


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if pm.delete_project(project_id):
        return JSONResponse({"success": True})
    raise HTTPException(status_code=400, detail="Cannot delete project")


@router.get("/project-data/{data_type}")
async def get_project_data(data_type: str):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"data": [], "error": "请先选择或创建一个项目", "no_project": True})

    try:
        svc = get_library_service()
        if not svc.is_degraded:
            legacy_view = svc.project_legacy_view(data_type)
            # 修复：只在 legacy_view 非空时使用，避免库文件存在但视图为空时返回空数据
            if legacy_view:
                if data_type in BUILTIN_PROJECT_DATA_TYPES:
                    return JSONResponse(_normalize_builtin_project_data(data_type, legacy_view))
                return JSONResponse({"data": legacy_view})
    except Exception as e:
        logger.debug(f"[Projects] Library read fallback: {e}")

    try:
        payload = pm.load_project_data(data_type)
        if data_type in BUILTIN_PROJECT_DATA_TYPES:
            return JSONResponse(_normalize_builtin_project_data(data_type, payload))
        return JSONResponse({"data": payload})
    except ValueError as e:
        return JSONResponse({"data": [], "error": str(e)})


@router.post("/project-data/{data_type}")
async def save_project_data(data_type: str, request: Request):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    try:
        body = await request.json()
        data_rows = body.get("data", [])
        existing_payload = pm.load_project_data(data_type)
        payload_to_save = (
            _denormalize_builtin_project_data(data_type, data_rows, existing_payload)
            if data_type in BUILTIN_PROJECT_DATA_TYPES
            else data_rows
        )
        pm.save_project_data(data_type, payload_to_save)

        try:
            from ...library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy(data_type, payload_to_save)
        except Exception as e:
            logger.debug(f"[Projects] Library sync on save: {e}")

        if data_type == "outline":
            try:
                from ...novel_import_service import get_novel_import_service

                import_service = get_novel_import_service(data_dir=pm.data_dir)
                chapters = import_service.chapters_from_outline(_normalize_outline_rows(payload_to_save))
                import_service.refresh_collab_memory(
                    project_id=pm.current_project_id or "",
                    chapters=chapters,
                    source_file="project_outline",
                )
            except Exception as exc:
                logger.warning(f"[Projects] Failed to refresh collaborative memory: {exc}")

        return JSONResponse({"success": True})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


# ------------------------------------------------------------------
#  Library API endpoints
# ------------------------------------------------------------------

@router.get("/library/entries")
async def list_library_entries(entry_type: str = "", category_key: str = ""):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "data": [], "error": "请先选择项目"})

    svc = get_library_service()
    entries = svc.list_entries(
        entry_type=entry_type or None,
        category_key=category_key or None,
    )
    return JSONResponse({"success": True, "data": [e.to_dict() for e in entries]})


@router.get("/library/entries/{entry_id}")
async def get_library_entry(entry_id: str):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "data": None, "error": "请先选择项目"})

    svc = get_library_service()
    entry = svc.get_entry(entry_id)
    if not entry:
        return JSONResponse({"success": False, "data": None, "error": "条目不存在"}, status_code=404)
    return JSONResponse({"success": True, "data": entry.to_dict()})


@router.post("/library/entries")
async def create_library_entry(request: Request):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service
    from ...library_types import LibraryEntry, generate_entry_id

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择项目"}, status_code=400)

    body = await request.json()
    entry_type = body.get("entry_type", "custom")
    if not body.get("id"):
        body["id"] = generate_entry_id(entry_type)
    entry = LibraryEntry.from_dict(body)

    svc = get_library_service()
    result = svc.upsert_entry(entry)
    return JSONResponse({"success": True, "data": result.to_dict()})


@router.put("/library/entries/{entry_id}")
async def update_library_entry(entry_id: str, request: Request):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service
    from ...library_types import LibraryEntry

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择项目"}, status_code=400)

    svc = get_library_service()
    existing = svc.get_entry(entry_id)
    if not existing:
        return JSONResponse({"success": False, "error": "条目不存在"}, status_code=404)

    body = await request.json()
    merged = existing.to_dict()
    merged.update({k: v for k, v in body.items() if v is not None})
    merged["id"] = entry_id
    entry = LibraryEntry.from_dict(merged)

    result = svc.upsert_entry(entry)
    return JSONResponse({"success": True, "data": result.to_dict()})


@router.delete("/library/entries/{entry_id}")
async def delete_library_entry(entry_id: str):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择项目"}, status_code=400)

    svc = get_library_service()
    deleted = svc.delete_entry(entry_id)
    if not deleted:
        return JSONResponse({"success": False, "error": "条目不存在"}, status_code=404)
    return JSONResponse({"success": True})


@router.get("/library/categories")
async def list_library_categories():
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "data": [], "error": "请先选择项目"})

    svc = get_library_service()
    cats = svc.list_categories()
    return JSONResponse({"success": True, "data": [c.to_dict() for c in cats]})


@router.post("/library/categories")
async def upsert_library_category(request: Request):
    from ...project_manager import get_project_manager
    from ...library_service import get_library_service
    from ...library_types import CategoryMeta

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择项目"}, status_code=400)

    body = await request.json()
    cat = CategoryMeta.from_dict(body)
    svc = get_library_service()
    result = svc.upsert_category(cat)
    return JSONResponse({"success": True, "data": result.to_dict()})


@router.post("/projects/import-novel")
async def import_novel_to_collab_mode(
    novel_file: UploadFile = File(...),
    merge_mode: str = Form("append"),
):
    """Import txt/md/docx novel file into collaborative mode and auto-build memory."""
    from ...project_manager import get_project_manager
    from ...novel_import_service import get_novel_import_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    normalized_merge_mode = (merge_mode or "append").strip().lower()
    if normalized_merge_mode not in {"append", "replace"}:
        return JSONResponse({"success": False, "error": "merge_mode 仅支持 append/replace"}, status_code=400)

    file_bytes = await novel_file.read(NOVEL_IMPORT_MAX_BYTES + 1)
    if not file_bytes:
        return JSONResponse({"success": False, "error": "上传文件为空"}, status_code=400)
    if len(file_bytes) > NOVEL_IMPORT_MAX_BYTES:
        return JSONResponse(
            {"success": False, "error": f"文件过大，最大支持 {NOVEL_IMPORT_MAX_BYTES // (1024 * 1024)}MB"},
            status_code=413,
        )

    import_service = get_novel_import_service(data_dir=pm.data_dir)
    try:
        parsed = import_service.parse_novel_file(
            filename=novel_file.filename or "import.txt",
            raw_bytes=file_bytes,
        )
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    outline = [] if normalized_merge_mode == "replace" else pm.load_project_data("outline")
    if not isinstance(outline, list):
        outline = []

    imported_items = []
    for chapter in parsed["chapters"]:
        imported_items.append(
            {
                "title": chapter.get("title") or f"第{chapter.get('chapter_number', len(outline) + 1)}章",
                "summary": chapter.get("summary", ""),
                "content": chapter.get("content", ""),
                "word_count": chapter.get("word_count", 0),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_from": "collab_import",
                "source_file": parsed["filename"],
            }
        )

    outline.extend(imported_items)
    pm.save_project_data("outline", outline)

    chapters = import_service.chapters_from_outline(outline)
    memory = import_service.refresh_collab_memory(
        project_id=pm.current_project_id or "",
        chapters=chapters,
        source_file=parsed["filename"],
    )

    return JSONResponse(
        {
            "success": True,
            "mode": "collab_write",
            "project_id": pm.current_project_id,
            "filename": parsed["filename"],
            "merge_mode": normalized_merge_mode,
            "imported_chapters": len(parsed["chapters"]),
            "total_chapters": len(outline),
            "total_words": sum(ch.get("word_count", 0) for ch in parsed["chapters"]),
            "memory_summary": {
                "chapter_cards": len(memory.get("chapter_cards", [])),
                "issue_cards": len(memory.get("issue_cards", [])),
                "edit_tasks": len(memory.get("edit_tasks", [])),
            },
        }
    )


@router.post("/project-state/batch-get")
async def batch_get_project_state(request: ProjectStateBatchGetRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    states = {}
    for state_key in request.keys[:100]:
        try:
            states[state_key] = pm.load_project_state(state_key, default=None)
        except ValueError:
            return JSONResponse(
                {"success": False, "error": f"Invalid project state key: {state_key}"},
                status_code=400,
            )

    return JSONResponse({"success": True, "states": states})


@router.post("/project-state/batch-set")
async def batch_set_project_state(request: ProjectStateBatchSetRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    saved_keys = []
    for state_key, data in request.states.items():
        try:
            pm.save_project_state(state_key, data)
            saved_keys.append(state_key)
        except ValueError:
            return JSONResponse(
                {"success": False, "error": f"Invalid project state key: {state_key}"},
                status_code=400,
            )

    return JSONResponse({"success": True, "saved_keys": saved_keys})


@router.get("/project-state/{state_key}")
async def get_project_state(state_key: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        data = pm.load_project_state(state_key, default=None)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key, "data": data})


@router.post("/project-state/{state_key}")
async def save_project_state(state_key: str, request: Request):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        body = await request.json()
        pm.save_project_state(state_key, body.get("data"))
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key})


@router.delete("/project-state/{state_key}")
async def delete_project_state(state_key: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        deleted = pm.delete_project_state(state_key)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key, "deleted": deleted})


@router.get("/chapter-summary-config")
async def get_chapter_summary_config():
    from ...chapter_summary_service import get_auto_summary_config
    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError:
        return JSONResponse({"auto_summary_enabled": False})
    config = get_auto_summary_config(pm.current_project_id)
    return JSONResponse(config)


@router.post("/chapter-summary-config")
async def set_chapter_summary_config(request: Request):
    from ...chapter_summary_service import set_auto_summary_enabled
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    body = await request.json()
    enabled = bool(body.get("auto_summary_enabled", False))
    set_auto_summary_enabled(pm.current_project_id, enabled)
    return JSONResponse({"success": True, "auto_summary_enabled": enabled})


@router.get("/projects/backup/export")
async def export_backup():
    targets = _get_backup_targets()
    app_root = targets["app_root"]

    backup_dir = app_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"novel-agent-backup-{timestamp}.zip"
    backup_path = backup_dir / backup_name

    manifest = {
        "backup_version": "1.0",
        "created_at": datetime.now().isoformat(),
        "includes": {
            "root_data_dir": str(targets["root_data_dir"]),
            "package_data_dir": str(targets["package_data_dir"]),
            "env_file": targets["env_file"].exists(),
        },
    }

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        if targets["root_data_dir"].exists():
            for file in targets["root_data_dir"].rglob("*"):
                if file.is_file():
                    rel = file.relative_to(targets["root_data_dir"])
                    zf.write(file, f"root_data/{rel.as_posix()}")

        if targets["package_data_dir"].exists():
            for file in targets["package_data_dir"].rglob("*"):
                if file.is_file():
                    rel = file.relative_to(targets["package_data_dir"])
                    zf.write(file, f"package_data/{rel.as_posix()}")

        if targets["env_file"].exists():
            zf.write(targets["env_file"], "env/.env")

    return FileResponse(
        path=str(backup_path),
        media_type="application/zip",
        filename=backup_name,
    )


@router.post("/projects/backup/import")
async def import_backup(
    backup_file: UploadFile = File(...),
    overwrite: bool = Form(False),
):
    filename = (backup_file.filename or "").lower()
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持zip备份文件")

    targets = _get_backup_targets()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        zip_path = temp_dir_path / "backup.zip"

        uploaded_size = 0
        with zip_path.open("wb") as output:
            while True:
                chunk = await backup_file.read(BACKUP_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                uploaded_size += len(chunk)
                if uploaded_size > BACKUP_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"备份文件超过大小限制（最大 {BACKUP_UPLOAD_MAX_BYTES // (1024 * 1024)}MB）",
                    )
                output.write(chunk)

        if uploaded_size == 0:
            raise HTTPException(status_code=400, detail="备份文件为空")

        extract_dir = temp_dir_path / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(zip_path, extract_dir)

        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=400, detail="备份文件缺少 manifest.json，格式不受支持")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="manifest.json 解析失败")

        source_root_data = extract_dir / "root_data"
        source_package_data = extract_dir / "package_data"

        root_data_dst = targets["root_data_dir"]
        package_data_dst = targets["package_data_dir"]

        root_data_dst.parent.mkdir(parents=True, exist_ok=True)
        package_data_dst.parent.mkdir(parents=True, exist_ok=True)

        if overwrite:
            if source_root_data.exists():
                if root_data_dst.exists():
                    shutil.rmtree(root_data_dst)
                shutil.copytree(source_root_data, root_data_dst)
            if source_package_data.exists():
                if package_data_dst.exists():
                    shutil.rmtree(package_data_dst)
                shutil.copytree(source_package_data, package_data_dst)
        else:
            _copy_dir_contents(source_root_data, root_data_dst, overwrite=False)
            _copy_dir_contents(source_package_data, package_data_dst, overwrite=False)

        source_env = extract_dir / "env" / ".env"
        if source_env.exists() and (overwrite or not targets["env_file"].exists()):
            targets["env_file"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_env, targets["env_file"])

        from ...project_manager import get_project_manager

        get_project_manager()._load_projects()

        return JSONResponse({
            "success": True,
            "message": "备份导入成功，已刷新项目状态",
            "overwrite": overwrite,
            "manifest": manifest,
        })
