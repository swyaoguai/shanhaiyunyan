"""
辅助记忆服务

实现长期辅助记忆的本地持久化与检索能力。
当前阶段聚焦：Category/Item CRUD + 手工注入预览（M1）。
"""

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import get_data_dir
from .utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _parse_iso_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


@dataclass
class AuxMemoryResource:
    """辅助记忆来源对象（当前阶段仅做结构预留）"""

    id: str
    project_id: str
    user_id: str = ""
    source_type: str = "manual"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuxMemoryCategory:
    """辅助记忆分类"""

    id: str
    project_id: str
    user_id: str = ""
    name: str = ""
    description: str = ""
    summary: str = ""
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuxMemoryItem:
    """辅助记忆条目"""

    id: str
    project_id: str
    user_id: str = ""
    category_id: str = ""
    source_resource_id: str = ""
    memory_type: str = "preference"
    summary: str = ""
    details: str = ""
    score: float = 0.5
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuxMemoryRelation:
    """分类-条目关系（当前阶段仅做结构预留）"""

    id: str
    project_id: str
    category_id: str
    item_id: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuxMemoryService:
    """辅助记忆服务"""

    DEFAULT_CONFIG: Dict[str, Any] = {
        "injection_enabled": True,
        "injection_mode": "fast",
        "injection_top_k": 6,
        "injection_max_chars": 1200,
        "auto_classify_enabled": True,
        "auto_summary_enabled": True,
        "auto_summary_top_items": 5,
    }

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or get_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return value != 0

        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "y"}:
            return True
        if text in {"0", "false", "no", "off", "n", ""}:
            return False
        return default

    @staticmethod
    def _as_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            number = int(value)
        except Exception:
            number = int(default)
        return max(min_value, min(number, max_value))

    def _project_aux_dir(self, project_id: str) -> Path:
        path = self.data_dir / "projects" / project_id / "aux_memory"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _categories_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "categories.json"

    def _items_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "items.json"

    def _resources_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "resources.json"

    def _history_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "history.json"

    def _config_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "config.json"

    def _injection_records_path(self, project_id: str) -> Path:
        return self._project_aux_dir(project_id) / "injection_records.json"

    def _load_json_list(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return payload
            logger.warning(f"[AuxMemory] 文件结构异常（非列表）: {path}")
            return []
        except Exception as exc:
            logger.warning(f"[AuxMemory] 读取失败: {path} - {exc}")
            return []

    def _atomic_write_json(self, path: Path, payload: List[Dict[str, Any]]) -> None:
        atomic_write_json(path, payload, ensure_ascii=False, indent=2)

    def _load_categories(self, project_id: str) -> List[AuxMemoryCategory]:
        result: List[AuxMemoryCategory] = []
        for row in self._load_json_list(self._categories_path(project_id)):
            try:
                result.append(AuxMemoryCategory(**row))
            except Exception as exc:
                logger.warning(f"[AuxMemory] 跳过无效分类数据: {exc}")
        return result

    def _save_categories(self, project_id: str, categories: List[AuxMemoryCategory]) -> None:
        self._atomic_write_json(
            self._categories_path(project_id),
            [c.to_dict() for c in categories]
        )

    def _load_items(self, project_id: str) -> List[AuxMemoryItem]:
        result: List[AuxMemoryItem] = []
        for row in self._load_json_list(self._items_path(project_id)):
            try:
                result.append(AuxMemoryItem(**row))
            except Exception as exc:
                logger.warning(f"[AuxMemory] 跳过无效条目数据: {exc}")
        return result

    def _save_items(self, project_id: str, items: List[AuxMemoryItem]) -> None:
        self._atomic_write_json(
            self._items_path(project_id),
            [item.to_dict() for item in items]
        )

    def _load_resources(self, project_id: str) -> List[AuxMemoryResource]:
        result: List[AuxMemoryResource] = []
        for row in self._load_json_list(self._resources_path(project_id)):
            try:
                result.append(AuxMemoryResource(**row))
            except Exception as exc:
                logger.warning(f"[AuxMemory] 跳过无效来源数据: {exc}")
        return result

    def _save_resources(self, project_id: str, resources: List[AuxMemoryResource]) -> None:
        self._atomic_write_json(
            self._resources_path(project_id),
            [resource.to_dict() for resource in resources]
        )

    def _read_history(self, project_id: str) -> List[Dict[str, Any]]:
        return self._load_json_list(self._history_path(project_id))

    def _write_history(self, project_id: str, rows: List[Dict[str, Any]]) -> None:
        self._atomic_write_json(self._history_path(project_id), rows)

    def _read_injection_records(self, project_id: str) -> List[Dict[str, Any]]:
        return self._load_json_list(self._injection_records_path(project_id))

    def _write_injection_records(self, project_id: str, rows: List[Dict[str, Any]]) -> None:
        self._atomic_write_json(self._injection_records_path(project_id), rows)

    def _read_config(self, project_id: str) -> Dict[str, Any]:
        path = self._config_path(project_id)
        if not path.exists():
            return dict(self.DEFAULT_CONFIG)

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return dict(self.DEFAULT_CONFIG)
            merged = dict(self.DEFAULT_CONFIG)
            merged.update(payload)
            return merged
        except Exception as exc:
            logger.warning(f"[AuxMemory] 读取配置失败: {exc}")
            return dict(self.DEFAULT_CONFIG)

    def _write_config(self, project_id: str, payload: Dict[str, Any]) -> None:
        path = self._config_path(project_id)
        merged = dict(self.DEFAULT_CONFIG)
        merged.update(payload)
        atomic_write_json(path, merged, ensure_ascii=False, indent=2)

    def get_config(self, project_id: str) -> Dict[str, Any]:
        return self._read_config(project_id)

    def update_config(self, project_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        config = self._read_config(project_id)
        config.update(updates)

        config["injection_top_k"] = self._as_int(config.get("injection_top_k"), 6, 1, 20)
        config["injection_max_chars"] = self._as_int(config.get("injection_max_chars"), 1200, 200, 4000)
        config["auto_summary_top_items"] = self._as_int(config.get("auto_summary_top_items"), 5, 1, 20)

        for key in (
            "injection_enabled",
            "auto_classify_enabled",
            "auto_summary_enabled",
        ):
            config[key] = self._as_bool(config.get(key), self.DEFAULT_CONFIG[key])

        if config.get("injection_mode") not in {"fast", "deep"}:
            config["injection_mode"] = "fast"

        self._write_config(project_id, config)
        return config

    def _record_injection_event(
        self,
        project_id: str,
        query: str,
        mode: str,
        top_k: int,
        count: int,
        items: List[Dict[str, Any]],
        source: str = "writing",
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            rows = self._read_injection_records(project_id)
            rows.append(
                {
                    "id": _gen_id("inj"),
                    "project_id": project_id,
                    "query": (query or "")[:500],
                    "mode": mode,
                    "top_k": int(top_k),
                    "count": int(count),
                    "source": source,
                    "where": where or {},
                    "items": [
                        {
                            "id": row.get("id", ""),
                            "summary": row.get("summary", ""),
                            "category_id": row.get("category_id", ""),
                            "score": row.get("score", 0.0),
                            "match_score": row.get("match_score", 0.0),
                        }
                        for row in (items or [])[:10]
                    ],
                    "created_at": _now_iso(),
                }
            )
            if len(rows) > 300:
                rows = rows[-300:]
            self._write_injection_records(project_id, rows)
        except Exception as exc:
            logger.warning(f"[AuxMemory] 记录注入命中失败（不影响主流程）: {exc}")

    def list_injection_records(
        self,
        project_id: str,
        limit: int = 20,
        source: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._read_injection_records(project_id)
        if source:
            rows = [row for row in rows if str(row.get("source", "")) == source]

        safe_limit = max(1, min(int(limit or 20), 100))
        rows = rows[-safe_limit:]
        rows.reverse()
        return rows

    def _snapshot_state(self, project_id: str) -> Dict[str, Any]:
        return {
            "categories": [category.to_dict() for category in self._load_categories(project_id)],
            "items": [item.to_dict() for item in self._load_items(project_id)],
        }

    def _record_history(self, project_id: str, action: str, meta: Optional[Dict[str, Any]] = None) -> None:
        try:
            rows = self._read_history(project_id)
            rows.append(
                {
                    "id": _gen_id("his"),
                    "project_id": project_id,
                    "action": action,
                    "meta": meta or {},
                    "snapshot": self._snapshot_state(project_id),
                    "created_at": _now_iso(),
                }
            )
            if len(rows) > 100:
                rows = rows[-100:]
            self._write_history(project_id, rows)
        except Exception as exc:
            logger.warning(f"[AuxMemory] 写入历史失败（不影响主流程）: {exc}")

    @staticmethod
    def _split_keywords(text: str) -> List[str]:
        return [token for token in re.split(r"[\s,，。；;、|]+", text.lower()) if len(token) >= 1]

    @classmethod
    def _category_semantic_keywords(cls, memory_type: str) -> List[str]:
        memory_type = (memory_type or "").lower()
        mapping = {
            "preference": ["偏好", "喜好", "习惯"],
            "style": ["文风", "风格", "语气", "节奏"],
            "constraint": ["规则", "约束", "禁忌", "避免"],
            "fact": ["事实", "设定", "信息"],
        }
        for key, keywords in mapping.items():
            if key in memory_type:
                return keywords
        return []

    def _infer_category_id(
        self,
        project_id: str,
        summary: str,
        details: str,
        tags: Optional[List[str]] = None,
        user_id: str = "",
        memory_type: str = "",
    ) -> str:
        categories = self.list_categories(project_id=project_id, user_id=user_id or None, enabled_only=True)
        if not categories:
            return ""

        text = f"{summary} {details} {' '.join(tags or [])}".lower()
        semantic_keywords = self._category_semantic_keywords(memory_type)

        best_score = 0.0
        best_id = ""

        for category in categories:
            score = 0.0
            category_name = (category.name or "").lower()
            category_desc = (category.description or "").lower()

            if category_name and category_name in text:
                score += 2.5

            for token in self._split_keywords(f"{category_name} {category_desc}"):
                if token in text:
                    score += 0.4

            for tag in tags or []:
                tag_text = tag.lower()
                if tag_text and (tag_text in category_name or tag_text in category_desc):
                    score += 0.8

            for keyword in semantic_keywords:
                if keyword in category_name or keyword in category_desc:
                    score += 0.7

            if score > best_score:
                best_score = score
                best_id = category.id

        if len(categories) == 1 and not best_id:
            return categories[0].id

        return best_id if best_score >= 0.7 else ""

    def _refresh_category_summary(
        self,
        project_id: str,
        category_id: str,
        categories: Optional[List[AuxMemoryCategory]] = None,
        items: Optional[List[AuxMemoryItem]] = None,
    ) -> bool:
        if not category_id:
            return False

        config = self._read_config(project_id)
        if not config.get("auto_summary_enabled", True):
            return False

        categories = categories or self._load_categories(project_id)
        items = items or self._load_items(project_id)
        target = next((category for category in categories if category.id == category_id), None)
        if not target:
            return False

        top_n = max(1, min(int(config.get("auto_summary_top_items", 5)), 20))
        ranked_items = [
            item
            for item in items
            if item.category_id == category_id and item.enabled
        ]
        ranked_items.sort(key=lambda item: (item.score, item.updated_at), reverse=True)

        if not ranked_items:
            next_summary = ""
        else:
            snippets: List[str] = []
            for item in ranked_items[:top_n]:
                summary_text = item.summary.strip()
                if not summary_text:
                    continue
                if len(summary_text) > 30:
                    summary_text = f"{summary_text[:30]}..."
                snippets.append(summary_text)
            next_summary = "；".join(snippets)

        if target.summary == next_summary:
            return False

        target.summary = next_summary
        target.updated_at = _now_iso()
        return True

    def _refresh_category_summaries(
        self,
        project_id: str,
        category_ids: List[str],
        categories: Optional[List[AuxMemoryCategory]] = None,
        items: Optional[List[AuxMemoryItem]] = None,
    ) -> bool:
        valid_ids = {str(category_id) for category_id in (category_ids or []) if str(category_id).strip()}
        if not valid_ids:
            return False

        categories = categories or self._load_categories(project_id)
        items = items or self._load_items(project_id)

        changed = False
        for category_id in valid_ids:
            if self._refresh_category_summary(
                project_id=project_id,
                category_id=category_id,
                categories=categories,
                items=items,
            ):
                changed = True
        return changed

    def list_history(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._read_history(project_id)
        safe_limit = max(1, min(int(limit or 20), 100))
        rows = rows[-safe_limit:]
        rows.reverse()

        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row.get("id", ""),
                    "project_id": row.get("project_id", ""),
                    "action": row.get("action", ""),
                    "meta": row.get("meta", {}),
                    "created_at": row.get("created_at", ""),
                    "snapshot_stats": {
                        "categories": len((row.get("snapshot") or {}).get("categories") or []),
                        "items": len((row.get("snapshot") or {}).get("items") or []),
                    },
                }
            )
        return result

    def rollback(self, project_id: str, history_id: str) -> Optional[Dict[str, Any]]:
        rows = self._read_history(project_id)
        target = next((row for row in rows if row.get("id") == history_id), None)
        if not target:
            return None

        snapshot = target.get("snapshot") or {}
        categories = []
        for row in snapshot.get("categories") or []:
            try:
                categories.append(AuxMemoryCategory(**row))
            except Exception:
                continue

        items = []
        for row in snapshot.get("items") or []:
            try:
                items.append(AuxMemoryItem(**row))
            except Exception:
                continue

        self._save_categories(project_id, categories)
        self._save_items(project_id, items)

        self._record_history(
            project_id,
            "rollback",
            {
                "history_id": history_id,
                "restored_action": target.get("action", ""),
            },
        )

        return {
            "history_id": history_id,
            "restored_action": target.get("action", ""),
            "categories": len(categories),
            "items": len(items),
        }

    # ===== 资源导入 =====

    def list_resources(self, project_id: str, user_id: Optional[str] = None) -> List[AuxMemoryResource]:
        resources = self._load_resources(project_id)
        if user_id is not None:
            resources = [resource for resource in resources if resource.user_id in ("", user_id)]
        resources.sort(key=lambda resource: resource.updated_at, reverse=True)
        return resources

    def get_resource(self, project_id: str, resource_id: str) -> Optional[AuxMemoryResource]:
        for resource in self._load_resources(project_id):
            if resource.id == resource_id:
                return resource
        return None

    def create_resource(
        self,
        project_id: str,
        source_type: str,
        content: str,
        user_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuxMemoryResource:
        resource = AuxMemoryResource(
            id=_gen_id("res"),
            project_id=project_id,
            user_id=user_id,
            source_type=source_type,
            content=content,
            metadata=metadata or {},
        )

        resources = self._load_resources(project_id)
        resources.append(resource)
        self._save_resources(project_id, resources)
        return resource

    def import_resource_text(
        self,
        project_id: str,
        content: str,
        source_type: str = "manual",
        user_id: str = "",
        title: str = "",
        category_id: str = "",
        min_line_chars: int = 6,
        max_items: int = 20,
        default_score: float = 0.6,
    ) -> Dict[str, Any]:
        resource = self.create_resource(
            project_id=project_id,
            source_type=source_type,
            content=content,
            user_id=user_id,
            metadata={"title": title},
        )

        lines = []
        for raw_line in content.splitlines():
            line = raw_line.strip().lstrip("-•*0123456789. ")
            if len(line) >= max(1, min_line_chars):
                lines.append(line)

        lines = lines[: max(1, min(int(max_items or 20), 100))]

        created_items: List[AuxMemoryItem] = []
        for line in lines:
            summary = line[:120].strip()
            item = self.create_item(
                project_id=project_id,
                summary=summary,
                details=line,
                category_id=category_id,
                memory_type="fact",
                score=default_score,
                enabled=True,
                tags=["导入"],
                user_id=user_id,
                extra={"title": title} if title else {},
                source_resource_id=resource.id,
            )
            created_items.append(item)

        self._record_history(
            project_id,
            "import_resource",
            {
                "resource_id": resource.id,
                "source_type": source_type,
                "imported_items": len(created_items),
                "title": title,
            },
        )

        return {
            "resource": resource.to_dict(),
            "items": [item.to_dict() for item in created_items],
        }

    # ===== 分类 CRUD =====

    def list_categories(
        self,
        project_id: str,
        user_id: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[AuxMemoryCategory]:
        categories = self._load_categories(project_id)

        if user_id is not None:
            categories = [c for c in categories if c.user_id in ("", user_id)]

        if enabled_only:
            categories = [c for c in categories if c.enabled]

        categories.sort(key=lambda c: c.updated_at, reverse=True)
        return categories

    def get_category(self, project_id: str, category_id: str) -> Optional[AuxMemoryCategory]:
        for category in self._load_categories(project_id):
            if category.id == category_id:
                return category
        return None

    def create_category(
        self,
        project_id: str,
        name: str,
        description: str = "",
        summary: str = "",
        enabled: bool = True,
        user_id: str = ""
    ) -> AuxMemoryCategory:
        categories = self._load_categories(project_id)
        category = AuxMemoryCategory(
            id=_gen_id("cat"),
            project_id=project_id,
            user_id=user_id,
            name=name.strip(),
            description=description,
            summary=summary,
            enabled=enabled
        )
        categories.append(category)
        self._save_categories(project_id, categories)

        items = self._load_items(project_id)
        config = self._read_config(project_id)
        auto_mapped = 0
        if config.get("auto_classify_enabled", True):
            changed = False
            for item in items:
                if item.category_id:
                    continue
                inferred_id = self._infer_category_id(
                    project_id=project_id,
                    summary=item.summary,
                    details=item.details,
                    tags=item.tags,
                    user_id=item.user_id,
                    memory_type=item.memory_type,
                )
                if inferred_id == category.id:
                    item.category_id = category.id
                    item.updated_at = _now_iso()
                    auto_mapped += 1
                    changed = True

            if changed:
                self._refresh_category_summary(
                    project_id=project_id,
                    category_id=category.id,
                    categories=categories,
                    items=items,
                )
                self._save_items(project_id, items)
                self._save_categories(project_id, categories)

        self._record_history(
            project_id,
            "create_category",
            {"category_id": category.id, "auto_mapped_items": auto_mapped},
        )
        return category

    def update_category(
        self,
        project_id: str,
        category_id: str,
        updates: Dict[str, Any]
    ) -> Optional[AuxMemoryCategory]:
        categories = self._load_categories(project_id)
        allowed_fields = {"name", "description", "summary", "enabled", "user_id"}

        for category in categories:
            if category.id != category_id:
                continue

            for key, value in updates.items():
                if key in allowed_fields:
                    setattr(category, key, value)

            category.updated_at = _now_iso()
            self._save_categories(project_id, categories)
            self._record_history(project_id, "update_category", {"category_id": category.id})
            return category

        return None

    def delete_category(self, project_id: str, category_id: str) -> Tuple[bool, int]:
        categories = self._load_categories(project_id)
        before_count = len(categories)
        categories = [c for c in categories if c.id != category_id]

        if len(categories) == before_count:
            return False, 0

        items = self._load_items(project_id)
        filtered_items = [item for item in items if item.category_id != category_id]
        removed_items = len(items) - len(filtered_items)

        self._save_categories(project_id, categories)
        self._save_items(project_id, filtered_items)
        self._record_history(
            project_id,
            "delete_category",
            {"category_id": category_id, "removed_items": removed_items}
        )
        return True, removed_items

    # ===== 条目 CRUD =====

    def list_items(
        self,
        project_id: str,
        category_id: Optional[str] = None,
        query: str = "",
        user_id: Optional[str] = None,
        enabled_only: bool = False,
        memory_type: str = "",
    ) -> List[AuxMemoryItem]:
        items = self._load_items(project_id)

        if category_id:
            items = [item for item in items if item.category_id == category_id]

        if user_id is not None:
            items = [item for item in items if item.user_id in ("", user_id)]

        if enabled_only:
            items = [item for item in items if item.enabled]

        normalized_memory_type = str(memory_type or "").strip()
        if normalized_memory_type:
            items = [item for item in items if str(item.memory_type or "") == normalized_memory_type]

        query = query.strip().lower()
        if query:
            items = [
                item
                for item in items
                if query in self._item_search_text(item)
            ]

        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items

    def get_item(self, project_id: str, item_id: str) -> Optional[AuxMemoryItem]:
        for item in self._load_items(project_id):
            if item.id == item_id:
                return item
        return None

    def create_item(
        self,
        project_id: str,
        summary: str,
        details: str = "",
        category_id: str = "",
        memory_type: str = "preference",
        score: float = 0.5,
        enabled: bool = True,
        tags: Optional[List[str]] = None,
        user_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
        source_resource_id: str = ""
    ) -> AuxMemoryItem:
        config = self._read_config(project_id)
        input_tags = tags or []

        auto_classified = False
        if not category_id and config.get("auto_classify_enabled", True):
            inferred_category_id = self._infer_category_id(
                project_id=project_id,
                summary=summary,
                details=details,
                tags=input_tags,
                user_id=user_id,
                memory_type=memory_type,
            )
            if inferred_category_id:
                category_id = inferred_category_id
                auto_classified = True

        if category_id and not self.get_category(project_id, category_id):
            raise ValueError("分类不存在")

        item = AuxMemoryItem(
            id=_gen_id("mem"),
            project_id=project_id,
            user_id=user_id,
            category_id=category_id,
            source_resource_id=source_resource_id,
            memory_type=memory_type,
            summary=summary.strip(),
            details=details,
            score=max(0.0, min(1.0, float(score))),
            enabled=enabled,
            tags=input_tags,
            extra=extra or {}
        )

        items = self._load_items(project_id)
        items.append(item)
        self._save_items(project_id, items)

        summary_changed = False
        categories = self._load_categories(project_id)
        if item.category_id:
            summary_changed = self._refresh_category_summary(
                project_id=project_id,
                category_id=item.category_id,
                categories=categories,
                items=items,
            )
        if summary_changed:
            self._save_categories(project_id, categories)

        self._record_history(
            project_id,
            "create_item",
            {
                "item_id": item.id,
                "category_id": item.category_id,
                "auto_classified": auto_classified,
            }
        )
        return item

    def update_item(
        self,
        project_id: str,
        item_id: str,
        updates: Dict[str, Any]
    ) -> Optional[AuxMemoryItem]:
        items = self._load_items(project_id)
        allowed_fields = {
            "summary",
            "details",
            "category_id",
            "memory_type",
            "score",
            "enabled",
            "tags",
            "extra",
            "user_id",
            "source_resource_id",
        }

        for item in items:
            if item.id != item_id:
                continue

            old_category_id = item.category_id

            for key, value in updates.items():
                if key not in allowed_fields:
                    continue

                if key == "category_id" and value and not self.get_category(project_id, str(value)):
                    raise ValueError("分类不存在")

                if key == "score":
                    value = max(0.0, min(1.0, float(value)))

                setattr(item, key, value)

            item.updated_at = _now_iso()
            self._save_items(project_id, items)

            categories = self._load_categories(project_id)
            dirty_categories = False
            affected_category_ids = {old_category_id, item.category_id}
            for category_id in affected_category_ids:
                if not category_id:
                    continue
                changed = self._refresh_category_summary(
                    project_id=project_id,
                    category_id=category_id,
                    categories=categories,
                    items=items,
                )
                if changed:
                    dirty_categories = True

            if dirty_categories:
                self._save_categories(project_id, categories)

            self._record_history(project_id, "update_item", {"item_id": item.id})
            return item

        return None

    def delete_item(self, project_id: str, item_id: str) -> bool:
        items = self._load_items(project_id)
        deleted_item = next((item for item in items if item.id == item_id), None)
        filtered = [item for item in items if item.id != item_id]
        if len(filtered) == len(items):
            return False

        self._save_items(project_id, filtered)

        if deleted_item and deleted_item.category_id:
            categories = self._load_categories(project_id)
            changed = self._refresh_category_summary(
                project_id=project_id,
                category_id=deleted_item.category_id,
                categories=categories,
                items=filtered,
            )
            if changed:
                self._save_categories(project_id, categories)

        self._record_history(project_id, "delete_item", {"item_id": item_id})
        return True

    def batch_update_items_enabled(
        self,
        project_id: str,
        item_ids: List[str],
        enabled: bool,
    ) -> Dict[str, int]:
        id_set = {str(item_id).strip() for item_id in (item_ids or []) if str(item_id).strip()}
        if not id_set:
            return {"requested": 0, "updated": 0, "matched": 0}

        items = self._load_items(project_id)
        requested_count = len(id_set)
        matched_count = 0
        updated_count = 0
        affected_categories: List[str] = []
        now = _now_iso()
        enabled_value = bool(enabled)

        for item in items:
            if item.id not in id_set:
                continue
            matched_count += 1
            if bool(item.enabled) == enabled_value:
                continue
            item.enabled = enabled_value
            item.updated_at = now
            updated_count += 1
            if item.category_id:
                affected_categories.append(item.category_id)

        if updated_count > 0:
            self._save_items(project_id, items)
            categories = self._load_categories(project_id)
            if self._refresh_category_summaries(
                project_id=project_id,
                category_ids=affected_categories,
                categories=categories,
                items=items,
            ):
                self._save_categories(project_id, categories)
            self._record_history(
                project_id,
                "batch_update_items",
                {
                    "updated_count": updated_count,
                    "matched_count": matched_count,
                    "enabled": enabled_value,
                },
            )

        return {
            "requested": requested_count,
            "matched": matched_count,
            "updated": updated_count,
        }

    def delete_items(self, project_id: str, item_ids: List[str], action: str = "delete_items") -> int:
        id_set = {str(item_id).strip() for item_id in (item_ids or []) if str(item_id).strip()}
        if not id_set:
            return 0

        items = self._load_items(project_id)
        deleted_items = [item for item in items if item.id in id_set]
        if not deleted_items:
            return 0

        filtered_items = [item for item in items if item.id not in id_set]
        self._save_items(project_id, filtered_items)

        affected_categories = [item.category_id for item in deleted_items if item.category_id]
        if affected_categories:
            categories = self._load_categories(project_id)
            if self._refresh_category_summaries(
                project_id=project_id,
                category_ids=affected_categories,
                categories=categories,
                items=filtered_items,
            ):
                self._save_categories(project_id, categories)

        self._record_history(
            project_id,
            action,
            {
                "deleted_count": len(deleted_items),
                "requested_count": len(id_set),
            },
        )
        return len(deleted_items)

    def clear_items(
        self,
        project_id: str,
        category_id: Optional[str] = None,
        query: str = "",
        user_id: Optional[str] = None,
        enabled_only: bool = False,
        memory_type: str = "",
    ) -> Dict[str, int]:
        target_items = self.list_items(
            project_id=project_id,
            category_id=category_id or None,
            query=query,
            user_id=user_id,
            enabled_only=enabled_only,
            memory_type=memory_type,
        )

        target_ids = [item.id for item in target_items]
        deleted_count = self.delete_items(project_id, target_ids, action="clear_items")
        return {"matched": len(target_ids), "deleted": deleted_count}

    # ===== 检索与注入预览 =====

    @staticmethod
    def _item_search_text(item: AuxMemoryItem) -> str:
        tags = item.tags if isinstance(item.tags, list) else []
        tag_text = " ".join([str(tag) for tag in tags])
        return f"{item.summary} {item.details} {tag_text}".lower()

    def _score_item(self, item: AuxMemoryItem, query: str) -> Tuple[float, str]:
        base_score = float(item.score)
        query = query.strip().lower()

        if not query:
            return base_score, "无查询词，按基础权重排序"

        text = self._item_search_text(item)
        score = base_score
        reasons: List[str] = []

        if query in text:
            score += 1.2
            reasons.append("完整短语命中")

        tokens = [token for token in re.split(r"[\s,，。；;]+", query) if token]
        token_hits = sum(1 for token in tokens if token in text)
        if token_hits > 0:
            score += token_hits * 0.25
            reasons.append(f"关键词命中 {token_hits} 项")

        if not reasons:
            reasons.append("回退基础分")

        return score, "，".join(reasons)

    def _deep_rerank_records(
        self,
        project_id: str,
        query: str,
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        query_tokens = self._split_keywords(query)
        categories_map = {row.id: row for row in self._load_categories(project_id)}

        now_dt = datetime.now()
        result: List[Dict[str, Any]] = []
        for row in records:
            base_score = float(row.get("match_score", 0.0))
            summary_text = str(row.get("summary", "")).lower()
            detail_text = str(row.get("details", "")).lower()
            tags_text = " ".join([str(tag).lower() for tag in row.get("tags", [])])
            category = categories_map.get(row.get("category_id", ""))
            category_text = ""
            if category:
                category_text = f"{category.name} {category.description} {category.summary}".lower()

            deep_score = base_score
            deep_reasons: List[str] = []

            summary_hits = sum(1 for token in query_tokens if token in summary_text)
            detail_hits = sum(1 for token in query_tokens if token in detail_text)
            tag_hits = sum(1 for token in query_tokens if token in tags_text)
            category_hits = sum(1 for token in query_tokens if token in category_text)

            if summary_hits:
                deep_score += summary_hits * 0.55
                deep_reasons.append(f"摘要命中 {summary_hits}")
            if detail_hits:
                deep_score += detail_hits * 0.25
                deep_reasons.append(f"详情命中 {detail_hits}")
            if tag_hits:
                deep_score += tag_hits * 0.3
                deep_reasons.append(f"标签命中 {tag_hits}")
            if category_hits:
                deep_score += category_hits * 0.2
                deep_reasons.append(f"分类语义命中 {category_hits}")

            updated_dt = _parse_iso_dt(str(row.get("updated_at", "")))
            if updated_dt:
                age_days = max(0.0, (now_dt - updated_dt).total_seconds() / 86400.0)
                if age_days <= 7:
                    deep_score += 0.18
                    deep_reasons.append("近期更新加权")
                elif age_days <= 30:
                    deep_score += 0.08
                    deep_reasons.append("近月更新加权")

            row["deep_score"] = round(deep_score, 4)
            if deep_reasons:
                row["match_reason"] = f"{row.get('match_reason', '')}；deep:{'，'.join(deep_reasons)}"
            else:
                row["match_reason"] = f"{row.get('match_reason', '')}；deep:回退基础排序"

            result.append(row)

        result.sort(key=lambda row: (row.get("deep_score", 0.0), row.get("match_score", 0.0)), reverse=True)
        return result

    def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
        mode: str = "fast",
        user_id: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        enabled_only: bool = True,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        where = where or {}

        if where.get("project_id") and str(where.get("project_id")) != project_id:
            return []

        effective_user_id = user_id
        if where.get("user_id"):
            effective_user_id = str(where.get("user_id"))

        effective_category_ids = category_ids
        where_category_ids = where.get("category_ids")
        if isinstance(where_category_ids, list) and where_category_ids:
            effective_category_ids = [str(category_id) for category_id in where_category_ids if str(category_id).strip()]

        effective_enabled_only = enabled_only
        if "enabled_only" in where:
            effective_enabled_only = self._as_bool(where.get("enabled_only"), enabled_only)

        min_score = where.get("min_score")
        if min_score is not None:
            try:
                min_score = max(0.0, min(1.0, float(min_score)))
            except Exception:
                min_score = None

        items = self.list_items(
            project_id=project_id,
            query="",
            user_id=effective_user_id,
            enabled_only=effective_enabled_only,
        )

        if effective_category_ids:
            category_id_set = set(effective_category_ids)
            items = [item for item in items if item.category_id in category_id_set]

        if min_score is not None:
            items = [item for item in items if float(item.score) >= min_score]

        ranked: List[Dict[str, Any]] = []
        for item in items:
            match_score, reason = self._score_item(item, query)
            row = item.to_dict()
            row["match_score"] = round(match_score, 4)
            row["match_reason"] = reason
            ranked.append(row)

        ranked.sort(key=lambda row: (row["match_score"], row.get("updated_at", "")), reverse=True)
        safe_top_k = max(1, min(int(top_k or 5), 20))
        result = ranked[:safe_top_k]

        if mode == "deep":
            # M3: deep 模式使用 fast 召回后进行二次重排。
            deep_candidate_count = max(safe_top_k * 3, 15)
            deep_candidates = ranked[:deep_candidate_count]
            reranked = self._deep_rerank_records(project_id, query, deep_candidates)
            result = reranked[:safe_top_k]

        categories_map = {row.id: row for row in self._load_categories(project_id)}
        resources_map = {row.id: row for row in self._load_resources(project_id)}
        for row in result:
            category = categories_map.get(row.get("category_id", ""))
            resource = resources_map.get(row.get("source_resource_id", ""))
            row["reference"] = {
                "item_id": row.get("id", ""),
                "category": {
                    "id": category.id,
                    "name": category.name,
                } if category else None,
                "source_resource": {
                    "id": resource.id,
                    "source_type": resource.source_type,
                    "title": str((resource.metadata or {}).get("title", "")),
                } if resource else None,
            }

        return result

    def get_item_trace(
        self,
        project_id: str,
        item_id: str,
        limit: int = 20,
    ) -> Optional[Dict[str, Any]]:
        item = self.get_item(project_id, item_id)
        if not item:
            return None

        category = self.get_category(project_id, item.category_id) if item.category_id else None
        resource = self.get_resource(project_id, item.source_resource_id) if item.source_resource_id else None

        records = self.list_injection_records(project_id=project_id, limit=max(limit, 100))
        related_records: List[Dict[str, Any]] = []
        for row in records:
            row_items = row.get("items") or []
            for injected_item in row_items:
                if str(injected_item.get("id", "")) == item_id:
                    related_records.append(
                        {
                            "record_id": row.get("id", ""),
                            "created_at": row.get("created_at", ""),
                            "query": row.get("query", ""),
                            "source": row.get("source", ""),
                            "mode": row.get("mode", ""),
                            "match_score": injected_item.get("match_score", 0.0),
                        }
                    )
                    break

        safe_limit = max(1, min(int(limit or 20), 100))
        related_records = related_records[:safe_limit]

        return {
            "item": item.to_dict(),
            "category": category.to_dict() if category else None,
            "source_resource": resource.to_dict() if resource else None,
            "injection_refs": related_records,
            "ref_count": len(related_records),
        }

    def get_injection_for_writing(
        self,
        project_id: str,
        query: str,
        user_id: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = self._read_config(project_id)
        if not config.get("injection_enabled", True):
            return {
                "enabled": False,
                "items": [],
                "prompt_preview": "",
                "count": 0,
                "mode": config.get("injection_mode", "fast"),
                "config": config,
            }

        preview = self.build_injection_preview(
            project_id=project_id,
            query=query,
            top_k=int(config.get("injection_top_k", 6)),
            user_id=user_id,
            category_ids=category_ids,
            mode=str(config.get("injection_mode", "fast")),
            max_chars=int(config.get("injection_max_chars", 1200)),
            where=where,
        )

        self._record_injection_event(
            project_id=project_id,
            query=query,
            mode=preview.get("mode", "fast"),
            top_k=int(config.get("injection_top_k", 6)),
            count=int(preview.get("count", 0)),
            items=preview.get("items", []),
            source="writing",
            where=where,
        )

        preview["enabled"] = True
        preview["config"] = config
        return preview

    def build_injection_preview(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
        user_id: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        mode: str = "fast",
        max_chars: int = 1200,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        records = self.retrieve(
            project_id=project_id,
            query=query,
            top_k=top_k,
            mode=mode,
            user_id=user_id,
            category_ids=category_ids,
            enabled_only=True,
            where=where,
        )

        lines = [
            "[辅助记忆注入建议（低优先级）]",
            "以下内容用于偏好/风格约束，不可覆盖剧情硬事实："
        ]

        for index, row in enumerate(records, start=1):
            tags = row.get("tags") or []
            tag_text = "、".join(tags[:4]) if tags else "未标注"
            lines.append(
                f"{index}. {row.get('summary', '').strip()}（标签：{tag_text}；理由：{row.get('match_reason', '')}）"
            )

            details = (row.get("details") or "").replace("\n", " ").strip()
            if details:
                if len(details) > 120:
                    details = f"{details[:120]}..."
                lines.append(f"   - {details}")

        prompt_preview = "\n".join(lines)
        if len(prompt_preview) > max_chars:
            prompt_preview = f"{prompt_preview[:max_chars]}..."

        return {
            "items": records,
            "prompt_preview": prompt_preview,
            "count": len(records),
            "mode": mode,
        }


_aux_memory_service: Optional[AuxMemoryService] = None


def get_aux_memory_service() -> AuxMemoryService:
    """获取辅助记忆服务全局实例"""
    global _aux_memory_service
    if _aux_memory_service is None:
        _aux_memory_service = AuxMemoryService()
    return _aux_memory_service
