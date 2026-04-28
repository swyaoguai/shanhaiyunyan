"""统一资料库类型定义"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EntryType(str, Enum):
    OUTLINE = "outline"
    DETAIL_OUTLINE = "detail_outline"
    CHAPTER_SETTING = "chapter_setting"
    CHARACTER = "character"
    EVENTLINE = "eventline"
    WORLD = "world"
    ITEM = "item"
    CHAPTER_SUMMARY = "chapter_summary"
    CUSTOM = "custom"
    FREE_MEMORY = "free_memory"


class SourceType(str, Enum):
    GENERATED = "generated"
    MANUAL = "manual"
    IMPORTED = "imported"
    DERIVED = "derived"


BUILTIN_ENTRY_TYPES = {
    EntryType.OUTLINE,
    EntryType.DETAIL_OUTLINE,
    EntryType.CHAPTER_SETTING,
    EntryType.CHARACTER,
    EntryType.EVENTLINE,
    EntryType.WORLD,
    EntryType.ITEM,
    EntryType.CHAPTER_SUMMARY,
    EntryType.FREE_MEMORY,
}

LEGACY_DATA_TYPE_MAP: Dict[str, EntryType] = {
    "outline": EntryType.OUTLINE,
    "characters": EntryType.CHARACTER,
    "worldbuilding": EntryType.WORLD,
    "items": EntryType.ITEM,
    "eventlines": EntryType.EVENTLINE,
    "detail_settings": EntryType.DETAIL_OUTLINE,
    "chapter_settings": EntryType.CHAPTER_SETTING,
}

ENTRY_TYPE_TO_LEGACY: Dict[EntryType, str] = {v: k for k, v in LEGACY_DATA_TYPE_MAP.items()}


def generate_entry_id(entry_type: str, index: Optional[int] = None) -> str:
    if index is not None:
        return f"{entry_type}_{index}"
    return f"{entry_type}_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class LibraryEntry:
    id: str
    entry_type: str
    title: str
    summary: str = ""
    content_structured: Dict[str, Any] = field(default_factory=dict)
    source_type: str = SourceType.MANUAL.value
    source_ref: Dict[str, Any] = field(default_factory=dict)
    category_key: str = ""
    builtin: bool = True
    tags: List[str] = field(default_factory=list)
    relations: List[str] = field(default_factory=list)
    status: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self):
        if not self.category_key:
            self.category_key = self.entry_type

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LibraryEntry:
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class KnowledgeNode(LibraryEntry):
    """Obsidian 风格知识节点统一模型。"""

    links_in: List[str] = field(default_factory=list)
    links_out: List[str] = field(default_factory=list)
    vector_text: str = ""
    source_path: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.vector_text:
            self.vector_text = self.summary or self.title

    @classmethod
    def from_entry(cls, entry: LibraryEntry, **overrides: Any) -> KnowledgeNode:
        payload = entry.to_dict()
        payload.update(overrides)
        return cls(**payload)


@dataclass
class CategoryMeta:
    key: str
    name: str
    icon: str = ""
    builtin: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CategoryMeta:
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


BUILTIN_CATEGORIES: List[CategoryMeta] = [
    CategoryMeta(key="character", name="角色档案", icon="ri-user-smile-line"),
    CategoryMeta(key="world", name="世界设定", icon="ri-earth-line"),
    CategoryMeta(key="item", name="道具物品", icon="ri-sword-line"),
    CategoryMeta(key="eventline", name="事件线", icon="ri-git-branch-line"),
    CategoryMeta(key="outline", name="大纲", icon="ri-file-list-3-line"),
    CategoryMeta(key="detail_outline", name="细纲设定", icon="ri-file-text-line"),
    CategoryMeta(key="chapter_setting", name="章纲设定", icon="ri-book-open-line"),
    CategoryMeta(key="chapter_summary", name="正文摘要", icon="ri-article-line"),
    CategoryMeta(key="free_memory", name="自由记忆", icon="ri-brain-line", builtin=True),
]

CURRENT_LIBRARY_VERSION = 1


KNOWLEDGE_NODE_TYPES = {
    EntryType.CHAPTER_SUMMARY.value,
    EntryType.CHARACTER.value,
    EntryType.WORLD.value,
    EntryType.EVENTLINE.value,
    EntryType.OUTLINE.value,
    EntryType.DETAIL_OUTLINE.value,
    EntryType.CHAPTER_SETTING.value,
    EntryType.CUSTOM.value,
}


@dataclass
class LibraryPayload:
    version: int = CURRENT_LIBRARY_VERSION
    entries: List[LibraryEntry] = field(default_factory=list)
    categories_meta: List[CategoryMeta] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
            "categories_meta": [c.to_dict() for c in self.categories_meta],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LibraryPayload:
        entries = [LibraryEntry.from_dict(e) for e in data.get("entries", [])]
        cats = [CategoryMeta.from_dict(c) for c in data.get("categories_meta", [])]
        return cls(
            version=data.get("version", CURRENT_LIBRARY_VERSION),
            entries=entries,
            categories_meta=cats,
        )

    @classmethod
    def empty(cls) -> LibraryPayload:
        return cls(
            version=CURRENT_LIBRARY_VERSION,
            entries=[],
            categories_meta=list(BUILTIN_CATEGORIES),
        )
