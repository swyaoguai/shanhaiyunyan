"""
Wiki 旧数据迁移脚本

将现有资料库（library.json）和知识中心数据迁移为 wiki 页面格式。

迁移映射：
- character → wiki/characters/{name}.md
- world → wiki/world/{name}.md
- outline → wiki/plot/{name}.md
- chapter_summary → wiki/chapters/{name}.md
- constraint → wiki/constraints/{name}.md
"""

from __future__ import annotations

import json
import logging
import re
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

logger = logging.getLogger(__name__)


class WikiMigrator:
    """
    旧数据迁移器
    
    将 library.json 中的条目迁移为独立的 wiki 页面文件。
    """

    def __init__(self, project_dir: Path, wiki_dir: Optional[Path] = None):
        """
        初始化迁移器
        
        Args:
            project_dir: 项目目录
            wiki_dir: wiki 目录（默认 project_dir/wiki）
        """
        self._project_dir = project_dir
        self._wiki_dir = wiki_dir or project_dir / "wiki"
        self._store = WikiStore(self._wiki_dir)
        self._index = WikiIndexManager(self._wiki_dir)

    def migrate_all(self) -> Dict[str, int]:
        """
        执行完整迁移
        
        Returns:
            迁移统计 {type: count}
        """
        stats: Dict[str, int] = {}
        
        # 1. 初始化 wiki 目录
        self._index.initialize_wiki()
        self._store.ensure_dirs()
        
        # 2. 迁移 library.json
        library_stats = self._migrate_library()
        stats.update(library_stats)
        
        # 3. 迁移旧 JSON 文件（兼容）
        legacy_stats = self._migrate_legacy_files()
        for k, v in legacy_stats.items():
            stats[k] = stats.get(k, 0) + v
        
        # 4. 生成 index.md 和 overview.md
        all_pages = self._store.list_pages()
        index_page = self._index.generate_index(all_pages)
        self._store.save_page(index_page)
        
        overview_page = self._index.generate_overview(all_pages)
        self._store.save_page(overview_page)
        
        # 5. 记录日志
        total = sum(stats.values())
        self._index.append_log(
            action="migrate",
            details=f"从旧数据迁移完成，共 {total} 个页面",
            pages_affected=[p.title for p in all_pages],
        )
        
        logger.info(f"[Migrate] 迁移完成: {stats}")
        return stats

    def _migrate_library(self) -> Dict[str, int]:
        """迁移 library.json"""
        library_path = self._project_dir / "library.json"
        if not library_path.exists():
            return {}
        
        try:
            data = json.loads(library_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Migrate] 读取 library.json 失败: {e}")
            return {}
        
        entries = data.get("entries", [])
        stats: Dict[str, int] = {}
        
        for entry in entries:
            try:
                page = self._entry_to_page(entry)
                if page:
                    self._store.save_page(page)
                    type_name = page.page_type.value
                    stats[type_name] = stats.get(type_name, 0) + 1
            except Exception as e:
                logger.warning(f"[Migrate] 迁移条目失败: {e}")
        
        return stats

    def _entry_to_page(self, entry: Dict[str, Any]) -> Optional[WikiPage]:
        """将 library.json 条目转换为 wiki 页面"""
        entry_type = entry.get("entry_type", "custom")
        title = entry.get("title", "未命名")
        summary = entry.get("summary", "")
        content_structured = entry.get("content_structured", {})
        
        # 映射类型
        type_map = {
            "character": PageType.CHARACTER,
            "world": PageType.WORLD,
            "outline": PageType.PLOT,
            "chapter_summary": PageType.CHAPTER,
            "custom": PageType.CUSTOM,
        }
        page_type = type_map.get(entry_type, PageType.CUSTOM)
        
        # 构建正文
        body_parts = [f"# {title}", ""]
        
        if summary:
            body_parts.append(summary)
            body_parts.append("")
        
        # 从 content_structured 提取内容
        if content_structured:
            body_parts.append("## 详细信息")
            body_parts.append("")
            body_parts.append(self._structured_to_markdown(content_structured))
            body_parts.append("")
        
        # 提取关系
        relations = entry.get("relations", [])
        if relations:
            body_parts.append("## 关联")
            body_parts.append("")
            for rel in relations:
                if isinstance(rel, str):
                    body_parts.append(f"- [[{rel}]]")
                elif isinstance(rel, dict):
                    body_parts.append(f"- [[{rel.get('name', rel.get('target', ''))}]]")
            body_parts.append("")
        
        # 提取链接
        links_out = entry.get("links_out", [])
        # links_out 已经通过 [[wikilink]] 在正文中体现
        
        body = "\n".join(body_parts)
        
        # 构建 frontmatter
        tags = entry.get("tags", [])
        if isinstance(tags, list):
            tags = [str(t) for t in tags]
        else:
            tags = []
        
        entities = []
        if entry_type == "character":
            entities.append(title)
        
        frontmatter = Frontmatter(
            page_type=page_type,
            title=title,
            sources=["library.json"],
            tags=tags,
            created_at=entry.get("created_at", now_iso()),
            updated_at=entry.get("updated_at", now_iso()),
            entities=entities,
            word_count=len(re.sub(r"\s+", "", body)),
        )
        
        # 角色特有字段
        if entry_type == "character":
            role = content_structured.get("role", "")
            if role:
                frontmatter.character_role = role
        
        return WikiPage(
            frontmatter=frontmatter,
            body=body,
        )

    def _migrate_legacy_files(self) -> Dict[str, int]:
        """迁移旧的 JSON 文件"""
        stats: Dict[str, int] = {}
        
        legacy_files = {
            "characters.json": PageType.CHARACTER,
            "worldbuilding.json": PageType.WORLD,
            "outline.json": PageType.PLOT,
        }
        
        for filename, page_type in legacy_files.items():
            file_path = self._project_dir / filename
            if not file_path.exists():
                continue
            
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                count = self._migrate_legacy_data(data, filename, page_type)
                if count > 0:
                    stats[page_type.value] = stats.get(page_type.value, 0) + count
            except Exception as e:
                logger.warning(f"[Migrate] 迁移 {filename} 失败: {e}")
        
        return stats

    def _migrate_legacy_data(
        self, data: Any, source_name: str, page_type: PageType
    ) -> int:
        """迁移单个旧文件的数据"""
        count = 0
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    page = self._dict_to_page(item, source_name, page_type)
                    if page:
                        self._store.save_page(page)
                        count += 1
        elif isinstance(data, dict):
            # 可能是单个对象或包含列表的对象
            if "characters" in data:
                for char in data["characters"]:
                    page = self._dict_to_page(char, source_name, PageType.CHARACTER)
                    if page:
                        self._store.save_page(page)
                        count += 1
            elif "world" in data:
                world = data["world"]
                if isinstance(world, dict):
                    page = self._dict_to_page(world, source_name, PageType.WORLD)
                    if page:
                        self._store.save_page(page)
                        count += 1
            elif "chapters" in data:
                for chapter in data["chapters"]:
                    page = self._dict_to_page(chapter, source_name, PageType.PLOT)
                    if page:
                        self._store.save_page(page)
                        count += 1
            else:
                page = self._dict_to_page(data, source_name, page_type)
                if page:
                    self._store.save_page(page)
                    count += 1
        
        return count

    def _dict_to_page(
        self, data: Dict[str, Any], source_name: str, page_type: PageType
    ) -> Optional[WikiPage]:
        """将字典转换为 wiki 页面"""
        title = (
            data.get("name")
            or data.get("title")
            or data.get("chapter_title")
            or "未命名"
        )
        
        body_parts = [f"# {title}", ""]
        
        # 提取所有字段
        for key, value in data.items():
            if key in ("name", "title", "chapter_title", "id"):
                continue
            if not value:
                continue
            
            if isinstance(value, str):
                body_parts.append(f"## {key}")
                body_parts.append(value)
                body_parts.append("")
            elif isinstance(value, list):
                body_parts.append(f"## {key}")
                for item in value:
                    if isinstance(item, str):
                        body_parts.append(f"- {item}")
                    elif isinstance(item, dict):
                        item_name = item.get("name", item.get("title", str(item)[:50]))
                        body_parts.append(f"- [[{item_name}]]")
                body_parts.append("")
            elif isinstance(value, dict):
                body_parts.append(f"## {key}")
                body_parts.append(self._structured_to_markdown(value))
                body_parts.append("")
        
        body = "\n".join(body_parts)
        
        frontmatter = Frontmatter(
            page_type=page_type,
            title=title,
            sources=[source_name],
            tags=[],
            created_at=now_iso(),
            updated_at=now_iso(),
            word_count=len(re.sub(r"\s+", "", body)),
        )
        
        return WikiPage(frontmatter=frontmatter, body=body)

    @staticmethod
    def _structured_to_markdown(data: Dict[str, Any], indent: int = 0) -> str:
        """将结构化数据转换为 Markdown"""
        lines = []
        prefix = "  " * indent
        
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}- **{key}**:")
                for k, v in value.items():
                    lines.append(f"{prefix}  - {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{prefix}- **{key}**:")
                for item in value:
                    if isinstance(item, str):
                        lines.append(f"{prefix}  - {item}")
                    elif isinstance(item, dict):
                        lines.append(f"{prefix}  - {json.dumps(item, ensure_ascii=False)[:100]}")
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}- **{key}**: {value}")
        
        return "\n".join(lines)