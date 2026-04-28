"""
Wiki 索引管理器

自动维护 wiki 的核心文件：
- purpose.md: 创作目标和风格偏好
- schema.md: wiki 结构规则
- index.md: 内容目录（自动生成）
- overview.md: 全局摘要（每次摄取后更新）
- log.md: 操作日志（时间线记录）
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_types import (
    Frontmatter,
    PageType,
    WikiPage,
    now_iso,
)

logger = logging.getLogger(__name__)


# ===== 模板 =====

PURPOSE_TEMPLATE = """# 创作目标

## 核心主题
{theme}

## 风格偏好
{style}

## 目标读者
{target_audience}

## 关键问题
{key_questions}

## 研究范围
{research_scope}

## 创作理念
{philosophy}
"""

SCHEMA_TEMPLATE = """# Wiki 结构规则

## 页面类型

| 类型 | 说明 | 子目录 |
|------|------|--------|
| character | 角色页面 | characters/ |
| world | 世界观设定 | world/ |
| plot | 剧情线 | plot/ |
| chapter | 章节摘要 | chapters/ |
| constraint | 剧情约束 | constraints/ |
| concept | 概念/术语 | concepts/ |
| source | 来源摘要 | sources/ |
| synthesis | 跨来源分析 | synthesis/ |
| comparison | 对比分析 | comparisons/ |

## 命名规范
- 角色：使用角色名（如 `林枫.md`）
- 世界观：使用设定名（如 `力量体系.md`）
- 剧情：使用线名（如 `主线.md`、`支线A.md`）
- 章节：使用章节号（如 `第1章.md`）
- 约束：使用约束描述（如 `林枫不可死亡.md`）

## 链接规范
- 使用 `[[页面名]]` 语法创建跨引用
- 角色页面必须链接到相关世界观和剧情线
- 章节摘要必须链接到出场角色和涉及设定
- 约束页面必须链接到相关角色和章节

## Frontmatter 规范
每个页面必须包含 YAML frontmatter：
- `type`: 页面类型（必填）
- `title`: 页面标题（必填）
- `sources`: 来源文件列表（推荐）
- `tags`: 标签列表（推荐）
- `created_at`: 创建时间（自动）
- `updated_at`: 更新时间（自动）

## 质量标准
- 每个角色页面至少包含：基本信息、性格、能力、关系
- 每个世界观页面至少包含：概述、规则、限制
- 每个章节摘要至少包含：核心事件、角色变化、伏笔
- 所有页面必须有至少一个 [[wikilink]]
"""


class WikiIndexManager:
    """
    Wiki 索引管理器
    
    负责维护 wiki 的核心索引文件。
    """

    def __init__(self, wiki_dir: Path):
        self._wiki_dir = wiki_dir

    @property
    def wiki_dir(self) -> Path:
        return self._wiki_dir

    # ------------------------------------------------------------------
    #  Purpose.md
    # ------------------------------------------------------------------

    def create_purpose(
        self,
        theme: str = "待补充",
        style: str = "网文爽文风格，节奏明快",
        target_audience: str = "网文读者",
        key_questions: str = "- 主角如何从弱变强？\n- 核心冲突如何解决？",
        research_scope: str = "小说创作相关",
        philosophy: str = "以读者体验为核心，追求爽感与深度的平衡",
    ) -> WikiPage:
        """创建 purpose.md"""
        body = PURPOSE_TEMPLATE.format(
            theme=theme,
            style=style,
            target_audience=target_audience,
            key_questions=key_questions,
            research_scope=research_scope,
            philosophy=philosophy,
        )
        
        page = WikiPage(
            frontmatter=Frontmatter(
                page_type=PageType.PURPOSE,
                title="创作目标",
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=body,
            file_path=Path("purpose.md"),
        )
        return page

    def load_purpose(self) -> Optional[str]:
        """加载 purpose.md 内容"""
        purpose_path = self._wiki_dir / "purpose.md"
        if purpose_path.exists():
            return purpose_path.read_text(encoding="utf-8")
        return None

    # ------------------------------------------------------------------
    #  Schema.md
    # ------------------------------------------------------------------

    def create_schema(self) -> WikiPage:
        """创建 schema.md"""
        page = WikiPage(
            frontmatter=Frontmatter(
                page_type=PageType.SCHEMA,
                title="Wiki 结构规则",
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=SCHEMA_TEMPLATE,
            file_path=Path("schema.md"),
        )
        return page

    def load_schema(self) -> Optional[str]:
        """加载 schema.md 内容"""
        schema_path = self._wiki_dir / "schema.md"
        if schema_path.exists():
            return schema_path.read_text(encoding="utf-8")
        return None

    # ------------------------------------------------------------------
    #  Index.md（内容目录）
    # ------------------------------------------------------------------

    def generate_index(self, pages: List[WikiPage]) -> WikiPage:
        """
        生成 index.md 内容目录
        
        按页面类型分组，列出所有页面。
        """
        # 按类型分组
        by_type: Dict[str, List[WikiPage]] = {}
        for page in pages:
            type_name = page.page_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(page)
        
        # 类型显示名
        type_display = {
            "character": "👤 角色",
            "world": "🌍 世界观",
            "plot": "📖 剧情",
            "chapter": "📄 章节摘要",
            "constraint": "⚠️ 剧情约束",
            "concept": "💡 概念",
            "source": "📚 来源",
            "synthesis": "🔗 综合分析",
            "comparison": "⚖️ 对比",
            "query": "🔍 查询",
            "custom": "📝 自定义",
        }
        
        lines = [
            "# 📚 知识库目录",
            "",
            f"*自动生成于 {now_iso()}*",
            "",
            f"共 **{len(pages)}** 个页面",
            "",
        ]
        
        # 按类型输出
        for type_name in ["character", "world", "plot", "chapter", "constraint", 
                          "concept", "source", "synthesis", "comparison", "query", "custom"]:
            type_pages = by_type.get(type_name, [])
            if not type_pages:
                continue
            
            display = type_display.get(type_name, type_name)
            lines.append(f"## {display} ({len(type_pages)})")
            lines.append("")
            
            for page in sorted(type_pages, key=lambda p: p.title):
                # 构建相对路径链接
                if page.file_path:
                    link = str(page.file_path).replace("\\", "/")
                    lines.append(f"- [{page.title}]({link})")
                else:
                    lines.append(f"- {page.title}")
            
            lines.append("")
        
        body = "\n".join(lines)
        
        return WikiPage(
            frontmatter=Frontmatter(
                page_type=PageType.INDEX,
                title="知识库目录",
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=body,
            file_path=Path("index.md"),
        )

    # ------------------------------------------------------------------
    #  Overview.md（全局摘要）
    # ------------------------------------------------------------------

    def generate_overview(
        self,
        pages: List[WikiPage],
        purpose: Optional[str] = None,
    ) -> WikiPage:
        """
        生成 overview.md 全局摘要
        
        综合所有页面信息，生成项目概览。
        """
        # 统计
        type_counts: Dict[str, int] = {}
        total_words = 0
        all_tags: Dict[str, int] = {}
        all_entities: set = set()
        
        for page in pages:
            type_name = page.page_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            total_words += len(page.body.replace(" ", "").replace("\n", ""))
            for tag in page.tags:
                all_tags[tag] = all_tags.get(tag, 0) + 1
            all_entities.update(page.entities)
        
        # 提取角色列表
        characters = [p.title for p in pages if p.page_type == PageType.CHARACTER]
        # 提取世界观要素
        world_elements = [p.title for p in pages if p.page_type == PageType.WORLD]
        # 提取剧情线
        plot_lines = [p.title for p in pages if p.page_type == PageType.PLOT]
        
        lines = [
            "# 📖 项目概览",
            "",
            f"*自动更新于 {now_iso()}*",
            "",
            "## 统计",
            "",
            f"- 总页面数: {len(pages)}",
            f"- 总字数: {total_words}",
            f"- 总标签数: {len(all_tags)}",
            "",
        ]
        
        # 类型分布
        if type_counts:
            lines.append("## 页面分布")
            lines.append("")
            for type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                lines.append(f"- {type_name}: {count}")
            lines.append("")
        
        # 角色列表
        if characters:
            lines.append("## 主要角色")
            lines.append("")
            for char in characters[:20]:
                lines.append(f"- [[{char}]]")
            lines.append("")
        
        # 世界观
        if world_elements:
            lines.append("## 世界观要素")
            lines.append("")
            for elem in world_elements[:10]:
                lines.append(f"- [[{elem}]]")
            lines.append("")
        
        # 剧情线
        if plot_lines:
            lines.append("## 剧情线")
            lines.append("")
            for plot in plot_lines[:10]:
                lines.append(f"- [[{plot}]]")
            lines.append("")
        
        # 热门标签
        if all_tags:
            lines.append("## 热门标签")
            lines.append("")
            top_tags = sorted(all_tags.items(), key=lambda x: -x[1])[:15]
            for tag, count in top_tags:
                lines.append(f"- {tag} ({count})")
            lines.append("")
        
        body = "\n".join(lines)
        
        return WikiPage(
            frontmatter=Frontmatter(
                page_type=PageType.OVERVIEW,
                title="项目概览",
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=body,
            file_path=Path("overview.md"),
        )

    # ------------------------------------------------------------------
    #  Log.md（操作日志）
    # ------------------------------------------------------------------

    def append_log(
        self,
        action: str,
        details: str = "",
        pages_affected: Optional[List[str]] = None,
    ) -> None:
        """
        追加操作日志到 log.md
        
        格式遵循 Karpathy LLM Wiki 规范：
        ```
        ## 2026-04-28 15:00:00 - ingest
        - 来源: chapter_5.md
        - 创建: 第5章, 林枫突破金丹
        - 更新: overview.md, index.md
        ```
        """
        log_path = self._wiki_dir / "log.md"
        
        # 如果文件不存在，创建头部
        if not log_path.exists():
            header = "# 📋 操作日志\n\n*记录所有 wiki 操作*\n\n"
            log_path.write_text(header, encoding="utf-8")
        
        # 构建日志条目
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_lines = [
            f"## {timestamp} - {action}",
            "",
        ]
        
        if details:
            entry_lines.append(details)
            entry_lines.append("")
        
        if pages_affected:
            entry_lines.append("涉及页面:")
            for page_title in pages_affected:
                entry_lines.append(f"- [[{page_title}]]")
            entry_lines.append("")
        
        entry_lines.append("---\n")
        
        # 追加到文件
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(entry_lines))
        
        logger.debug(f"[WikiIndex] 日志已记录: {action}")

    def load_log(self, max_entries: int = 50) -> str:
        """加载 log.md 内容"""
        log_path = self._wiki_dir / "log.md"
        if not log_path.exists():
            return ""
        content = log_path.read_text(encoding="utf-8")
        # 只返回最近的条目
        entries = content.split("---")
        if len(entries) > max_entries:
            entries = entries[-max_entries:]
        return "---".join(entries)

    # ------------------------------------------------------------------
    #  初始化
    # ------------------------------------------------------------------

    def initialize_wiki(
        self,
        theme: str = "待补充",
        style: str = "网文爽文风格",
    ) -> None:
        """
        初始化 wiki 目录结构和核心文件
        
        创建：
        - purpose.md
        - schema.md
        - index.md（空）
        - overview.md（空）
        - log.md（空）
        - 所有子目录
        """
        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        from .wiki_types import PAGE_TYPE_DIRS
        for subdir in set(PAGE_TYPE_DIRS.values()):
            (self._wiki_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        # 创建核心文件（如果不存在）
        purpose_path = self._wiki_dir / "purpose.md"
        if not purpose_path.exists():
            purpose = self.create_purpose(theme=theme, style=style)
            purpose_path.write_text(purpose.to_markdown(), encoding="utf-8")
        
        schema_path = self._wiki_dir / "schema.md"
        if not schema_path.exists():
            schema = self.create_schema()
            schema_path.write_text(schema.to_markdown(), encoding="utf-8")
        
        # 创建空的 index/overview/log
        for filename in ["index.md", "overview.md", "log.md"]:
            filepath = self._wiki_dir / filename
            if not filepath.exists():
                filepath.write_text(f"# {filename.replace('.md', '')}\n\n", encoding="utf-8")
        
        logger.info(f"[WikiIndex] Wiki 初始化完成: {self._wiki_dir}")