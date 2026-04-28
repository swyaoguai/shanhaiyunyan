"""
Wiki → LibraryService 适配器

让 WikiStore 兼容 LibraryService 的接口，这样所有现有代码
无需修改即可使用新的 Wiki 系统。

适配器实现的方法：
- list_entries / get_entry / upsert_entry / upsert_entries / delete_entry
- upsert_from_legacy / project_legacy_view
- list_categories / upsert_category
- is_degraded / library_path / load / save
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_types import (
    Frontmatter,
    PageType,
    WikiPage,
    now_iso,
)
from .wiki_store import WikiStore
from .wiki_index import WikiIndexManager
from .wiki_graph import WikiGraphBuilder

logger = logging.getLogger(__name__)

# entry_type → PageType 映射
ENTRY_TYPE_TO_PAGE_TYPE = {
    "character": PageType.CHARACTER,
    "world": PageType.WORLD,
    "outline": PageType.PLOT,
    "chapter_summary": PageType.CHAPTER,
    "constraint": PageType.CONSTRAINT,
    "item": PageType.CONCEPT,
    "eventline": PageType.PLOT,
    "custom": PageType.CUSTOM,
}

# PageType → entry_type 反向映射
PAGE_TYPE_TO_ENTRY_TYPE = {
    PageType.CHARACTER: "character",
    PageType.WORLD: "world",
    PageType.PLOT: "outline",
    PageType.CHAPTER: "chapter_summary",
    PageType.CONSTRAINT: "constraint",
    PageType.CONCEPT: "item",
    PageType.CUSTOM: "custom",
    PageType.SOURCE: "custom",
    PageType.QUERY: "custom",
    PageType.SYNTHESIS: "custom",
    PageType.COMPARISON: "custom",
}


class LibraryEntryCompat:
    """
    兼容 LibraryEntry 的数据对象
    
    从 WikiPage 转换而来，提供与旧 LibraryEntry 相同的接口。
    """

    def __init__(
        self,
        id: str = "",
        entry_type: str = "custom",
        category_key: str = "",
        title: str = "",
        summary: str = "",
        content_structured: Optional[Dict[str, Any]] = None,
        relations: Optional[List[str]] = None,
        links_out: Optional[List[str]] = None,
        links_in: Optional[List[str]] = None,
        vector_text: str = "",
        tags: Optional[List[str]] = None,
        created_at: str = "",
        updated_at: str = "",
        source_type: str = "",
        **kwargs,
    ):
        self.id = id
        self.entry_type = entry_type
        self.category_key = category_key
        self.title = title
        self.summary = summary
        self.content_structured = content_structured or {}
        self.relations = relations or []
        self.links_out = links_out or []
        self.links_in = links_in or []
        self.vector_text = vector_text
        self.tags = tags or []
        self.created_at = created_at
        self.updated_at = updated_at
        self.source_type = source_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "category_key": self.category_key,
            "title": self.title,
            "summary": self.summary,
            "content_structured": self.content_structured,
            "relations": self.relations,
            "links_out": self.links_out,
            "links_in": self.links_in,
            "vector_text": self.vector_text,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_type": self.source_type,
        }

    @classmethod
    def from_wiki_page(cls, page: WikiPage) -> "LibraryEntryCompat":
        """从 WikiPage 创建兼容对象"""
        entry_type = PAGE_TYPE_TO_ENTRY_TYPE.get(page.page_type, "custom")
        
        # 从正文提取摘要（前200字）
        clean_body = re.sub(r"#+\s+", "", page.body)
        summary = clean_body[:200].strip()
        
        return cls(
            id=page.title,  # 用标题作为ID
            entry_type=entry_type,
            title=page.title,
            summary=summary,
            content_structured={
                "body": page.body,
                "vector_text": page.plain_text(),
                "summary_text": summary,
            },
            relations=page.extract_wikilinks(),
            links_out=page.extract_wikilinks(),
            links_in=[],
            vector_text=page.plain_text(),
            tags=page.tags,
            created_at=page.frontmatter.created_at,
            updated_at=page.frontmatter.updated_at,
        )

    @classmethod
    def from_legacy_data(cls, data: Dict[str, Any], entry_type: str) -> "LibraryEntryCompat":
        """从旧格式数据创建"""
        title = (
            data.get("name")
            or data.get("title")
            or data.get("chapter_title")
            or "未命名"
        )
        
        return cls(
            id=f"{entry_type}_{title}",
            entry_type=entry_type,
            title=title,
            summary=str(data.get("description", ""))[:200],
            content_structured=data,
            tags=data.get("tags", []),
            created_at=now_iso(),
            updated_at=now_iso(),
        )


class CategoryMetaCompat:
    """兼容 CategoryMeta 的数据对象"""

    def __init__(self, key: str = "", name: str = "", builtin: bool = False, **kwargs):
        self.key = key
        self.name = name
        self.builtin = builtin

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "name": self.name, "builtin": self.builtin}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CategoryMetaCompat":
        return cls(
            key=d.get("key", ""),
            name=d.get("name", ""),
            builtin=d.get("builtin", False),
        )


class WikiLibraryAdapter:
    """
    Wiki → LibraryService 适配器
    
    实现 LibraryService 的完整接口，底层使用 WikiStore。
    """

    def __init__(self, project_dir: Path):
        self._project_dir = project_dir
        self._wiki_dir = project_dir / "wiki"
        self._lock = threading.RLock()
        
        # 初始化 wiki 组件
        self._store = WikiStore(self._wiki_dir)
        self._index = WikiIndexManager(self._wiki_dir)
        self._graph_builder = WikiGraphBuilder()
        
        # 确保 wiki 目录存在
        if not self._wiki_dir.exists():
            self._index.initialize_wiki()
            self._store.ensure_dirs()

    @property
    def is_degraded(self) -> bool:
        """永远不会降级"""
        return False

    @property
    def library_path(self) -> Path:
        """返回 wiki 目录（兼容旧接口）"""
        return self._wiki_dir

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def list_entries(
        self,
        entry_type: Optional[str] = None,
        category_key: Optional[str] = None,
    ) -> List[LibraryEntryCompat]:
        """列出条目"""
        with self._lock:
            page_type = ENTRY_TYPE_TO_PAGE_TYPE.get(entry_type) if entry_type else None
            pages = self._store.list_pages(page_type=page_type)
            
            entries = [LibraryEntryCompat.from_wiki_page(p) for p in pages]
            
            if category_key:
                entries = [e for e in entries if e.category_key == category_key]
            
            return entries

    def get_entry(self, entry_id: str) -> Optional[LibraryEntryCompat]:
        """获取单个条目"""
        with self._lock:
            page = self._store.load_page(entry_id)
            if page:
                return LibraryEntryCompat.from_wiki_page(page)
            return None

    def upsert_entry(self, entry) -> LibraryEntryCompat:
        """创建或更新条目"""
        with self._lock:
            # 如果是 LibraryEntryCompat，转为 WikiPage
            if isinstance(entry, LibraryEntryCompat):
                page = self._compat_entry_to_page(entry)
            elif isinstance(entry, dict):
                page = self._dict_to_page(entry)
            else:
                # 尝试从对象属性提取
                page = self._object_to_page(entry)
            
            self._store.save_page(page)
            
            # 更新索引
            self._update_indexes()
            
            return LibraryEntryCompat.from_wiki_page(page)

    def upsert_entries(self, entries: List) -> List[LibraryEntryCompat]:
        """批量创建或更新条目"""
        results = []
        for entry in entries:
            results.append(self.upsert_entry(entry))
        return results

    def delete_entry(self, entry_id: str) -> bool:
        """删除条目"""
        with self._lock:
            result = self._store.delete_page(entry_id)
            if result:
                self._update_indexes()
            return result

    # ------------------------------------------------------------------
    #  Legacy 兼容
    # ------------------------------------------------------------------

    def upsert_from_legacy(self, data_type: str, data: Any) -> List[LibraryEntryCompat]:
        """从旧格式数据导入"""
        with self._lock:
            entries = []
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        entry = LibraryEntryCompat.from_legacy_data(item, data_type)
                        page = self._compat_entry_to_page(entry)
                        self._store.save_page(page)
                        entries.append(entry)
            elif isinstance(data, dict):
                # 处理嵌套结构
                if "characters" in data:
                    for char in data["characters"]:
                        entry = LibraryEntryCompat.from_legacy_data(char, "character")
                        page = self._compat_entry_to_page(entry)
                        self._store.save_page(page)
                        entries.append(entry)
                elif "world" in data:
                    world = data["world"]
                    if isinstance(world, dict):
                        entry = LibraryEntryCompat.from_legacy_data(world, "world")
                        page = self._compat_entry_to_page(entry)
                        self._store.save_page(page)
                        entries.append(entry)
                elif "chapters" in data:
                    for chapter in data["chapters"]:
                        entry = LibraryEntryCompat.from_legacy_data(chapter, "outline")
                        page = self._compat_entry_to_page(entry)
                        self._store.save_page(page)
                        entries.append(entry)
                else:
                    entry = LibraryEntryCompat.from_legacy_data(data, data_type)
                    page = self._compat_entry_to_page(entry)
                    self._store.save_page(page)
                    entries.append(entry)
            
            self._update_indexes()
            return entries

    def project_legacy_view(self, data_type: str) -> Any:
        """投影为旧格式视图"""
        with self._lock:
            pages = self._store.list_pages()
            
            if data_type == "outline":
                return [
                    {
                        "chapter_number": p.frontmatter.chapter_number or i + 1,
                        "title": p.title,
                        "summary": p.body[:200],
                    }
                    for i, p in enumerate(pages)
                    if p.page_type == PageType.PLOT
                ]
            elif data_type == "characters":
                return [
                    {"name": p.title, "description": p.body[:200], "tags": p.tags}
                    for p in pages
                    if p.page_type == PageType.CHARACTER
                ]
            elif data_type == "worldbuilding":
                world_pages = [p for p in pages if p.page_type == PageType.WORLD]
                if world_pages:
                    return {
                        "world": {"name": world_pages[0].title, "content": world_pages[0].body},
                        "locations": [],
                    }
                return {}
            
            return []

    def sync_legacy_file(self, data_type: str) -> None:
        """同步到旧文件（no-op，wiki 是 source of truth）"""
        pass

    def sync_all_legacy_files(self) -> None:
        """同步所有旧文件（no-op）"""
        pass

    # ------------------------------------------------------------------
    #  Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> List[CategoryMetaCompat]:
        """列出分类"""
        # 从 wiki 页面类型推导分类
        pages = self._store.list_pages()
        types_seen = set()
        categories = []
        
        for page in pages:
            type_name = page.page_type.value
            if type_name not in types_seen:
                types_seen.add(type_name)
                categories.append(CategoryMetaCompat(
                    key=type_name,
                    name=type_name,
                    builtin=True,
                ))
        
        return categories

    def upsert_category(self, category) -> CategoryMetaCompat:
        """创建或更新分类（wiki 中分类是隐式的）"""
        if isinstance(category, dict):
            return CategoryMetaCompat.from_dict(category)
        return category

    # ------------------------------------------------------------------
    #  Load / Save
    # ------------------------------------------------------------------

    def load(self):
        """加载数据（兼容旧接口）"""
        # 返回一个兼容对象
        pages = self._store.list_pages()
        
        class CompatPayload:
            def __init__(self, pages):
                self.version = 1
                self.entries = [LibraryEntryCompat.from_wiki_page(p) for p in pages]
                self.categories_meta = []
        
        return CompatPayload(pages)

    def save(self, payload=None) -> None:
        """保存数据（wiki 自动保存）"""
        pass

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _compat_entry_to_page(self, entry: LibraryEntryCompat) -> WikiPage:
        """将兼容条目转为 WikiPage"""
        page_type = ENTRY_TYPE_TO_PAGE_TYPE.get(entry.entry_type, PageType.CUSTOM)
        
        # 构建正文
        body_parts = [f"# {entry.title}", ""]
        
        if entry.summary:
            body_parts.append(entry.summary)
            body_parts.append("")
        
        # 从 content_structured 提取内容
        cs = entry.content_structured or {}
        body = cs.get("body", "")
        if body:
            body_parts.append(body)
        else:
            for key, value in cs.items():
                if key in ("body", "vector_text", "summary_text"):
                    continue
                if isinstance(value, str) and value:
                    body_parts.append(f"## {key}")
                    body_parts.append(value)
                    body_parts.append("")
                elif isinstance(value, list) and value:
                    body_parts.append(f"## {key}")
                    for item in value:
                        if isinstance(item, str):
                            body_parts.append(f"- {item}")
                        elif isinstance(item, dict):
                            name = item.get("name", item.get("title", str(item)[:50]))
                            body_parts.append(f"- [[{name}]]")
                    body_parts.append("")
        
        # 添加关系链接
        if entry.relations:
            body_parts.append("## 关联")
            for rel in entry.relations:
                body_parts.append(f"- [[{rel}]]")
            body_parts.append("")
        
        body_text = "\n".join(body_parts)
        
        frontmatter = Frontmatter(
            page_type=page_type,
            title=entry.title,
            sources=["library.json"],
            tags=entry.tags or [],
            created_at=entry.created_at or now_iso(),
            updated_at=entry.updated_at or now_iso(),
            word_count=len(re.sub(r"\s+", "", body_text)),
        )
        
        return WikiPage(
            frontmatter=frontmatter,
            body=body_text,
        )

    def _dict_to_page(self, data: Dict[str, Any]) -> WikiPage:
        """将字典转为 WikiPage"""
        title = data.get("title", data.get("name", "未命名"))
        entry_type = data.get("entry_type", "custom")
        page_type = ENTRY_TYPE_TO_PAGE_TYPE.get(entry_type, PageType.CUSTOM)
        
        body_parts = [f"# {title}", ""]
        
        for key, value in data.items():
            if key in ("id", "entry_type", "title", "name", "created_at", "updated_at", "tags"):
                continue
            if isinstance(value, str) and value:
                body_parts.append(f"## {key}")
                body_parts.append(value)
                body_parts.append("")
        
        body = "\n".join(body_parts)
        
        return WikiPage(
            frontmatter=Frontmatter(
                page_type=page_type,
                title=title,
                tags=data.get("tags", []),
                created_at=data.get("created_at", now_iso()),
                updated_at=data.get("updated_at", now_iso()),
            ),
            body=body,
        )

    def _object_to_page(self, obj) -> WikiPage:
        """将任意对象转为 WikiPage"""
        title = getattr(obj, "title", getattr(obj, "name", "未命名"))
        entry_type = getattr(obj, "entry_type", "custom")
        page_type = ENTRY_TYPE_TO_PAGE_TYPE.get(entry_type, PageType.CUSTOM)
        
        body = f"# {title}\n\n"
        summary = getattr(obj, "summary", "")
        if summary:
            body += summary
        
        return WikiPage(
            frontmatter=Frontmatter(
                page_type=page_type,
                title=title,
                tags=getattr(obj, "tags", []),
                created_at=getattr(obj, "created_at", now_iso()),
                updated_at=getattr(obj, "updated_at", now_iso()),
            ),
            body=body,
        )

    def _update_indexes(self) -> None:
        """更新 index.md 和 overview.md"""
        try:
            pages = self._store.list_pages()
            index_page = self._index.generate_index(pages)
            self._store.save_page(index_page)
            
            overview_page = self._index.generate_overview(pages)
            self._store.save_page(overview_page)
        except Exception as e:
            logger.warning(f"[WikiAdapter] 更新索引失败: {e}")