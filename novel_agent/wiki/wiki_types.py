"""
Wiki 数据模型

基于 Karpathy LLM Wiki 模式的核心数据结构：
- WikiPage: wiki页面（Markdown + YAML frontmatter）
- Frontmatter: 页面元数据
- WikiLink: 页面间链接关系
- WikiGraph: 知识图谱
- IngestResult: 摄取结果
- LintIssue / LintReport: 质量检查
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class PageType(str, Enum):
    """Wiki 页面类型"""
    CHARACTER = "character"          # 角色
    WORLD = "world"                  # 世界观
    PLOT = "plot"                    # 剧情
    CHAPTER = "chapter"              # 章节摘要
    CONSTRAINT = "constraint"        # 剧情约束
    CONCEPT = "concept"              # 概念/设定
    SOURCE = "source"                # 来源摘要
    QUERY = "query"                  # 保存的查询/研究
    SYNTHESIS = "synthesis"          # 跨来源分析
    COMPARISON = "comparison"        # 对比分析
    INDEX = "index"                  # 目录页
    OVERVIEW = "overview"            # 全局摘要
    LOG = "log"                      # 操作日志
    PURPOSE = "purpose"              # 创作目标
    SCHEMA = "schema"                # 结构规则
    CUSTOM = "custom"                # 自定义类型


# 页面类型对应的子目录
PAGE_TYPE_DIRS: Dict[PageType, str] = {
    PageType.CHARACTER: "characters",
    PageType.WORLD: "world",
    PageType.PLOT: "plot",
    PageType.CHAPTER: "chapters",
    PageType.CONSTRAINT: "constraints",
    PageType.CONCEPT: "concepts",
    PageType.SOURCE: "sources",
    PageType.QUERY: "queries",
    PageType.SYNTHESIS: "synthesis",
    PageType.COMPARISON: "comparisons",
    PageType.CUSTOM: "custom",
}

# 不存储在子目录中的页面（直接在 wiki/ 根目录）
ROOT_PAGES = {PageType.INDEX, PageType.OVERVIEW, PageType.LOG}


@dataclass
class Frontmatter:
    """
    YAML frontmatter 元数据
    
    每个 wiki 页面的头部元数据，遵循 LLM Wiki 规范。
    """
    page_type: PageType
    title: str
    sources: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    # 小说创作特有字段
    chapter_number: Optional[int] = None
    character_role: Optional[str] = None  # 主角/反派/配角
    constraint_type: Optional[str] = None  # character_death/ability_change 等
    severity: Optional[str] = None  # critical/high/medium/low
    entities: List[str] = field(default_factory=list)  # 涉及的实体名称
    # 元数据
    word_count: int = 0
    status: str = "active"  # active/archived/draft

    def to_yaml_dict(self) -> Dict[str, Any]:
        """转换为 YAML 可序列化的字典"""
        d: Dict[str, Any] = {
            "type": self.page_type.value,
            "title": self.title,
        }
        if self.sources:
            d["sources"] = self.sources
        if self.tags:
            d["tags"] = self.tags
        if self.created_at:
            d["created_at"] = self.created_at
        if self.updated_at:
            d["updated_at"] = self.updated_at
        if self.chapter_number is not None:
            d["chapter_number"] = self.chapter_number
        if self.character_role:
            d["character_role"] = self.character_role
        if self.constraint_type:
            d["constraint_type"] = self.constraint_type
        if self.severity:
            d["severity"] = self.severity
        if self.entities:
            d["entities"] = self.entities
        if self.word_count:
            d["word_count"] = self.word_count
        if self.status != "active":
            d["status"] = self.status
        return d

    @classmethod
    def from_yaml_dict(cls, d: Dict[str, Any]) -> "Frontmatter":
        """从 YAML 字典创建"""
        page_type = PageType(d.get("type", "custom"))
        return cls(
            page_type=page_type,
            title=d.get("title", ""),
            sources=d.get("sources", []),
            tags=d.get("tags", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            chapter_number=d.get("chapter_number"),
            character_role=d.get("character_role"),
            constraint_type=d.get("constraint_type"),
            severity=d.get("severity"),
            entities=d.get("entities", []),
            word_count=d.get("word_count", 0),
            status=d.get("status", "active"),
        )


@dataclass
class WikiPage:
    """
    Wiki 页面
    
    一个完整的 wiki 页面 = frontmatter + markdown body
    存储为 .md 文件，格式：
        ---
        type: character
        title: 主角
        sources: [chapter_1.md]
        ---
        
        # 主角
        
        正文内容...
    """
    frontmatter: Frontmatter
    body: str  # Markdown 正文（不含 frontmatter）
    file_path: Optional[Path] = None  # 相对于 wiki/ 目录的路径

    @property
    def title(self) -> str:
        return self.frontmatter.title

    @property
    def page_type(self) -> PageType:
        return self.frontmatter.page_type

    @property
    def sources(self) -> List[str]:
        return self.frontmatter.sources

    @property
    def tags(self) -> List[str]:
        return self.frontmatter.tags

    @property
    def entities(self) -> List[str]:
        return self.frontmatter.entities

    def extract_wikilinks(self) -> List[str]:
        """从正文提取所有 [[wikilink]] 目标"""
        return WIKILINK_PATTERN.findall(self.body)

    def extract_wikilinks_full(self) -> List["WikiLink"]:
        """提取完整的 WikiLink 对象（包含来源页面）"""
        targets = self.extract_wikilinks()
        return [
            WikiLink(source=self.title, target=target)
            for target in targets
        ]

    def to_markdown(self) -> str:
        """序列化为完整的 Markdown 文件内容（含 frontmatter）"""
        lines = ["---"]
        for key, value in self.frontmatter.to_yaml_dict().items():
            if isinstance(value, list):
                if value:
                    # 列表格式
                    items = ", ".join(str(v) for v in value)
                    lines.append(f"{key}: [{items}]")
                # 空列表不输出
            elif isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif value is not None:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")
        lines.append(self.body)
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, content: str, file_path: Optional[Path] = None) -> "WikiPage":
        """从 Markdown 文件内容反序列化"""
        frontmatter, body = parse_frontmatter(content)
        return cls(
            frontmatter=frontmatter,
            body=body,
            file_path=file_path,
        )

    def content_hash(self) -> str:
        """计算页面内容的 SHA256 哈希"""
        return hashlib.sha256(
            self.to_markdown().encode("utf-8")
        ).hexdigest()

    def plain_text(self) -> str:
        """提取纯文本（去除 Markdown 格式），用于向量化"""
        text = self.body
        # 移除 Markdown 标记
        text = re.sub(r"#{1,6}\s+", "", text)  # 标题
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # 粗体
        text = re.sub(r"\*(.+?)\*", r"\1", text)  # 斜体
        text = re.sub(r"`(.+?)`", r"\1", text)  # 行内代码
        text = re.sub(r"```[\s\S]*?```", "", text)  # 代码块
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # 图片
        text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)  # 链接
        text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)  # wikilink
        text = re.sub(r"\n{3,}", "\n\n", text)  # 多余空行
        return text.strip()


# Wikilink 正则：匹配 [[target]] 和 [[target|display]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


@dataclass
class WikiLink:
    """页面间的链接关系"""
    source: str  # 来源页面标题
    target: str  # 目标页面标题

    def __hash__(self) -> int:
        return hash((self.source, self.target))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WikiLink):
            return NotImplemented
        return self.source == other.source and self.target == other.target


@dataclass
class WikiGraphNode:
    """知识图谱节点"""
    title: str
    page_type: PageType
    degree: int = 0  # 连接数
    sources: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    community: int = -1  # 社区编号（Louvain）

    @property
    def display_size(self) -> float:
        """节点显示大小（√缩放）"""
        return max(1.0, (self.degree + 1) ** 0.5)


@dataclass
class WikiGraphEdge:
    """知识图谱边"""
    source: str  # 来源页面标题
    target: str  # 目标页面标题
    weight: float = 1.0  # 相关性权重
    signals: Dict[str, float] = field(default_factory=dict)  # 各信号的贡献

    @property
    def display_color(self) -> str:
        """边的颜色（基于权重）"""
        if self.weight >= 8.0:
            return "#22c55e"  # 绿色（强相关）
        elif self.weight >= 4.0:
            return "#86efac"  # 浅绿
        elif self.weight >= 2.0:
            return "#d1d5db"  # 灰色
        else:
            return "#e5e7eb"  # 浅灰（弱相关）


@dataclass
class WikiGraph:
    """知识图谱"""
    nodes: Dict[str, WikiGraphNode] = field(default_factory=dict)
    edges: List[WikiGraphEdge] = field(default_factory=list)
    communities: Dict[int, List[str]] = field(default_factory=dict)  # 社区编号 → 页面标题列表

    def get_neighbors(self, title: str) -> List[str]:
        """获取指定页面的邻居"""
        neighbors = set()
        for edge in self.edges:
            if edge.source == title:
                neighbors.add(edge.target)
            elif edge.target == title:
                neighbors.add(edge.source)
        return list(neighbors)

    def get_degree(self, title: str) -> int:
        """获取指定页面的度数"""
        return len(self.get_neighbors(title))

    def get_common_neighbors(self, title_a: str, title_b: str) -> List[str]:
        """获取两个页面的共同邻居"""
        neighbors_a = set(self.get_neighbors(title_a))
        neighbors_b = set(self.get_neighbors(title_b))
        return list(neighbors_a & neighbors_b)

    def get_edges_for_node(self, title: str) -> List[WikiGraphEdge]:
        """获取指定页面的所有边"""
        return [
            e for e in self.edges
            if e.source == title or e.target == title
        ]

    def get_isolated_pages(self) -> List[str]:
        """获取孤立页面（度数 ≤ 1）"""
        return [
            title for title, node in self.nodes.items()
            if node.degree <= 1
        ]

    def get_bridge_nodes(self, min_clusters: int = 3) -> List[str]:
        """获取桥接节点（连接 min_clusters 个以上社区）"""
        bridges = []
        for title, node in self.nodes.items():
            neighbor_communities = set()
            for neighbor in self.get_neighbors(title):
                if neighbor in self.nodes:
                    neighbor_communities.add(self.nodes[neighbor].community)
            if len(neighbor_communities) >= min_clusters:
                bridges.append(title)
        return bridges


@dataclass
class IngestResult:
    """摄取结果"""
    source_file: str  # 原始来源文件
    source_hash: str  # 文件 SHA256
    pages_created: List[str] = field(default_factory=list)  # 创建的页面标题
    pages_updated: List[str] = field(default_factory=list)  # 更新的页面标题
    review_items: List[Dict[str, Any]] = field(default_factory=list)  # 待审核项
    search_queries: List[str] = field(default_factory=list)  # 深度研究搜索词
    analysis: Optional[str] = None  # Step1 分析结果
    success: bool = True
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class LintIssue:
    """Lint 检查问题"""
    issue_type: str  # isolated_page / dead_link / outdated / contradiction / missing_page
    severity: str  # critical / high / medium / low
    page_title: str  # 涉及的页面
    description: str  # 问题描述
    suggestion: str = ""  # 修复建议

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.issue_type}: {self.page_title} - {self.description}"


@dataclass
class LintReport:
    """Lint 检查报告"""
    issues: List[LintIssue] = field(default_factory=list)
    total_pages: int = 0
    total_links: int = 0
    isolated_count: int = 0
    dead_link_count: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    def summary(self) -> str:
        """生成摘要文本"""
        lines = [
            f"## Lint 检查报告 ({self.timestamp})",
            f"",
            f"- 总页面数: {self.total_pages}",
            f"- 总链接数: {self.total_links}",
            f"- 孤立页面: {self.isolated_count}",
            f"- 死链接: {self.dead_link_count}",
            f"- 问题总数: {len(self.issues)}",
            f"  - 严重: {self.critical_count}",
            f"  - 高: {self.high_count}",
        ]
        if self.issues:
            lines.append("")
            lines.append("### 问题列表")
            for issue in self.issues:
                lines.append(f"- {issue}")
        return "\n".join(lines)


# ===== 工具函数 =====

def parse_frontmatter(content: str) -> tuple[Frontmatter, str]:
    """
    解析 Markdown 文件中的 YAML frontmatter
    
    Args:
        content: 完整的 Markdown 文件内容
        
    Returns:
        (Frontmatter, body) 元组
    """
    content = content.strip()
    
    if not content.startswith("---"):
        # 没有 frontmatter，返回默认值
        return Frontmatter(page_type=PageType.CUSTOM, title=""), content
    
    # 找到第二个 ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return Frontmatter(page_type=PageType.CUSTOM, title=""), content
    
    yaml_str = content[3:end_idx].strip()
    body = content[end_idx + 3:].strip()
    
    # 简单的 YAML 解析（避免引入 pyyaml 依赖）
    fm_dict = _simple_yaml_parse(yaml_str)
    frontmatter = Frontmatter.from_yaml_dict(fm_dict)
    
    return frontmatter, body


def _simple_yaml_parse(yaml_str: str) -> Dict[str, Any]:
    """
    简单的 YAML 解析器（仅支持 frontmatter 常用格式）
    
    支持：
    - key: value
    - key: [item1, item2]
    - key: "string value"
    - 多行字符串（缩进）
    """
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[str]] = None
    
    for line in yaml_str.split("\n"):
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        
        # 检查是否是 key: value 行
        colon_idx = line.find(":")
        if colon_idx > 0 and not line.startswith(" "):
            # 保存之前的列表
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None
            
            key = line[:colon_idx].strip()
            value_str = line[colon_idx + 1:].strip()
            
            current_key = key
            
            if not value_str:
                # 空值，可能是多行
                current_list = []
                continue
            
            # 解析值
            result[key] = _parse_yaml_value(value_str)
        
        elif line.startswith("  - ") and current_key:
            # 列表项
            if current_list is None:
                current_list = []
            item = line.strip()[2:].strip()  # 去掉 "- "
            current_list.append(item)
    
    # 保存最后的列表
    if current_key and current_list is not None:
        result[current_key] = current_list
    
    return result


def _parse_yaml_value(value_str: str) -> Any:
    """解析单个 YAML 值"""
    value_str = value_str.strip()
    
    # 列表格式: [item1, item2]
    if value_str.startswith("[") and value_str.endswith("]"):
        inner = value_str[1:-1].strip()
        if not inner:
            return []
        items = [item.strip().strip('"').strip("'") for item in inner.split(",")]
        return [item for item in items if item]
    
    # 布尔值
    if value_str.lower() in ("true", "yes"):
        return True
    if value_str.lower() in ("false", "no"):
        return False
    
    # 数字
    try:
        if "." in value_str:
            return float(value_str)
        return int(value_str)
    except ValueError:
        pass
    
    # 字符串（去掉引号）
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]
    
    return value_str


def now_iso() -> str:
    """返回当前时间的 ISO 格式字符串"""
    return datetime.now().isoformat(timespec="seconds")


def generate_page_filename(title: str, page_type: PageType) -> str:
    """
    生成页面文件名
    
    格式：{title}.md
    清理不合法的文件名字符
    """
    # 清理文件名
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title)
    safe_title = re.sub(r"\s+", "_", safe_title).strip("._")
    if not safe_title:
        safe_title = f"unnamed_{page_type.value}"
    return f"{safe_title}.md"


def get_page_subdir(page_type: PageType) -> Optional[str]:
    """获取页面类型对应的子目录名，根目录页面返回 None"""
    if page_type in ROOT_PAGES:
        return None
    return PAGE_TYPE_DIRS.get(page_type, "custom")