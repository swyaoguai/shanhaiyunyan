"""Shared worldbuilding persistence helpers."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _extract_fenced_json_text(raw_content: str) -> str:
    text = str(raw_content or "").strip()
    if not text:
        return ""
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    return (fenced_match.group(1) if fenced_match else text).strip()


def _parse_raw_worldbuilding_content(raw_content: str) -> Dict[str, Any]:
    text = _extract_fenced_json_text(raw_content)
    if not text:
        return {}
    normalized_text = re.sub(r'(?<=")\s*，\s*(?=")', ", ", text)
    try:
        parsed = json.loads(normalized_text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("[WorldbuildingPersistence] raw_content JSON parse failed; keeping text summary")
        return {"raw_content": text}


def _looks_like_embedded_world_json(value: Any) -> bool:
    text = str(value or "").strip()
    if not text.startswith("{"):
        return False
    markers = (
        '"world_name"',
        '"world_type"',
        '"core_concept"',
        '"power_system"',
        '"geography"',
        '"factions"',
    )
    return any(marker in text for marker in markers)


def normalize_worldbuilding_payload(payload: Any, *, fallback_world_type: str = "") -> Dict[str, Any]:
    """Return a project-data compatible worldbuilding payload."""
    if isinstance(payload, dict) and isinstance(payload.get("world"), dict):
        normalized: Dict[str, Any] = dict(payload)
        world = dict(payload["world"])
    elif isinstance(payload, dict):
        normalized = {}
        world = dict(payload)
    else:
        return {}

    if set(world.keys()) == {"raw_content"}:
        parsed_world = _parse_raw_worldbuilding_content(str(world.get("raw_content") or ""))
        if parsed_world:
            world = parsed_world

    if not world:
        return {}

    world_name = str(world.get("name") or world.get("world_name") or "").strip()
    if world_name:
        world["name"] = world_name
        world["world_name"] = world_name
    if fallback_world_type and not str(world.get("world_type") or "").strip():
        world["world_type"] = fallback_world_type

    normalized["world"] = world
    return normalized


def merge_worldbuilding_payload(existing_payload: Any, incoming_payload: Any) -> Dict[str, Any]:
    """Merge generated worldbuilding data without erasing existing side sections."""
    incoming = normalize_worldbuilding_payload(incoming_payload)
    if not incoming:
        return dict(existing_payload) if isinstance(existing_payload, dict) else {}

    merged: Dict[str, Any] = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    existing_world = merged.get("world") if isinstance(merged.get("world"), dict) else {}
    next_world = dict(existing_world)
    incoming_world = incoming["world"]
    next_world.update(incoming_world)
    if "raw_content" in next_world and any(
        key != "raw_content" and value not in (None, "", [], {})
        for key, value in incoming_world.items()
    ):
        next_world.pop("raw_content", None)
    if "requirements" not in incoming_world and _looks_like_embedded_world_json(next_world.get("requirements")):
        next_world.pop("requirements", None)
    merged["world"] = next_world

    for key in ("locations", "items"):
        value = incoming.get(key)
        if isinstance(value, dict) and value:
            merged[key] = value

    events = incoming.get("events")
    if isinstance(events, list) and events:
        merged["events"] = events

    return merged


def persist_worldbuilding_project_data(
    payload: Any,
    *,
    project_manager: Any = None,
) -> Optional[Dict[str, Any]]:
    """Persist generated worldbuilding to the active project's canonical data file."""
    if project_manager is None:
        from .project_manager import get_project_manager

        project_manager = get_project_manager()

    if not getattr(project_manager, "current_project_id", None):
        return None

    normalized = normalize_worldbuilding_payload(payload)
    if not normalized:
        return None

    existing_payload = project_manager.load_project_data("worldbuilding")
    merged_payload = merge_worldbuilding_payload(existing_payload, normalized)
    if not merged_payload.get("world"):
        return None

    project_manager.save_project_data("worldbuilding", merged_payload)

    try:
        from .library_service import get_library_service

        project_dir = project_manager.get_current_project_dir()
        svc = get_library_service(project_dir)
        svc.upsert_from_legacy("worldbuilding", merged_payload)
    except Exception as exc:
        logger.warning(f"[WorldbuildingPersistence] Library sync failed: {exc}")

    return merged_payload


def load_context_worldbuilding_payload(project_dir: Path) -> Dict[str, Any]:
    """Recover worldbuilding data from context.json when the canonical file is empty."""
    context_file = Path(project_dir) / "context.json"
    if not context_file.exists():
        return {}

    try:
        data = json.loads(context_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[WorldbuildingPersistence] Failed to read context world: {exc}")
        return {}

    contexts = data.get("contexts") if isinstance(data, dict) else {}
    world_item = contexts.get("world") if isinstance(contexts, dict) else {}
    world_value = world_item.get("value") if isinstance(world_item, dict) else None
    return normalize_worldbuilding_payload({"world": world_value})


def recover_worldbuilding_from_context(*, project_manager: Any = None) -> Optional[Dict[str, Any]]:
    """Persist context.json world data back to worldbuilding.json if available."""
    if project_manager is None:
        from .project_manager import get_project_manager

        project_manager = get_project_manager()

    if not getattr(project_manager, "current_project_id", None):
        return None

    payload = load_context_worldbuilding_payload(project_manager.get_current_project_dir())
    if not payload:
        return None
    return persist_worldbuilding_project_data(payload, project_manager=project_manager)
