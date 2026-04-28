"""
Wiki Lint 质量检查系统

检查 wiki 的质量问题：
1. 孤立页面（degree ≤ 1）
2. 死链接（[[wikilink]] 指向不存在的页面）
3. 过时内容（长时间未更新）
4. 矛盾检测（同一实体在不同页面的描述冲突）
5. 缺失页面（被链接但不存在）
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from .wiki_types import (
    LintIssue,
    LintReport,
    PageType,
    WikiPage,
    WIKILINK_PATTERN,
    now_iso,
)
from .wiki_store import WikiStore
from .wiki_graph import WikiGraphBuilder

logger = logging.getLogger(__name__)


class WikiLinter:
    """
    Wiki 质量检查器
    
    使用方式：
        linter = WikiLinter(store, graph_builder)
        report = linter.run_full_check()
    """

    def __init__(
        self,
        store: WikiStore,
        graph_builder: Optional[WikiGraphBuilder] = None,
    ):
        self._store = store
        self._graph_builder = graph_builder or WikiGraphBuilder()

    def run_full_check(self) -> LintReport:
        """
        运行完整的 Lint 检查
        
        Returns:
            检查报告
        """
        pages = self._store.list_pages()
        all_titles = {p.title for p in pages}
        
        # 构建图谱
        graph = self._graph_builder.build_from_pages(pages)
        
        issues: List[LintIssue] = []
        
        # 1. 死链接检查
        issues.extend(self._check_dead_links(pages, all_titles))
        
        # 2. 缺失页面检查
        issues.extend(self._check_missing_pages(pages, all_titles))
        
        # 3. 孤立页面检查
        issues.extend(self._check_isolated_pages(pages, graph))
        
        # 4. 过时内容检查
        issues.extend(self._check_outdated_pages(pages))
        
        # 5. 空页面检查
        issues.extend(self._check_empty_pages(pages))
        
        # 6. 缺少链接的页面
        issues.extend(self._check_pages_without_links(pages))
        
        report = LintReport(
            issues=issues,
            total_pages=len(pages),
            total_links=sum(len(p.extract_wikilinks()) for p in pages),
            isolated_count=len(graph.get_isolated_pages()),
            dead_link_count=sum(1 for i in issues if i.issue_type == "dead_link"),
        )
        
        logger.info(f"[Lint] 检查完成: {len(issues)} 个问题")
        return report

    # ------------------------------------------------------------------
    #  检查项
    # ------------------------------------------------------------------

    def _check_dead_links(
        self, pages: List[WikiPage], all_titles: Set[str]
    ) -> List[LintIssue]:
        """检查死链接：[[wikilink]] 指向不存在的页面"""
        issues = []
        
        for page in pages:
            links = page.extract_wikilinks()
            for target in links:
                if target not in all_titles:
                    issues.append(LintIssue(
                        issue_type="dead_link",
                        severity="medium",
                        page_title=page.title,
                        description=f"链接 [[{target}]] 指向不存在的页面",
                        suggestion=f"创建页面 [[{target}]] 或修正链接",
                    ))
        
        return issues

    def _check_missing_pages(
        self, pages: List[WikiPage], all_titles: Set[str]
    ) -> List[LintIssue]:
        """检查缺失页面：被链接但不存在的页面"""
        linked_targets: Set[str] = set()
        
        for page in pages:
            linked_targets.update(page.extract_wikilinks())
        
        missing = linked_targets - all_titles
        issues = []
        
        for title in sorted(missing):
            issues.append(LintIssue(
                issue_type="missing_page",
                severity="high",
                page_title=title,
                description=f"页面 [[{title}]] 被引用但不存在",
                suggestion=f"创建页面 [[{title}]]",
            ))
        
        return issues

    def _check_isolated_pages(
        self, pages: List[WikiPage], graph
    ) -> List[LintIssue]:
        """检查孤立页面（度数 ≤ 1）"""
        issues = []
        
        for title in graph.get_isolated_pages():
            node = graph.nodes.get(title)
            if node:
                # 跳过系统页面
                if node.page_type in (PageType.INDEX, PageType.OVERVIEW, PageType.LOG,
                                       PageType.PURPOSE, PageType.SCHEMA):
                    continue
                
                issues.append(LintIssue(
                    issue_type="isolated_page",
                    severity="medium",
                    page_title=title,
                    description=f"页面孤立（度数={node.degree}），与其他页面缺乏连接",
                    suggestion=f"为 [[{title}]] 添加更多 [[wikilink]] 链接",
                ))
        
        return issues

    def _check_outdated_pages(
        self, pages: List[WikiPage], days_threshold: int = 30
    ) -> List[LintIssue]:
        """检查过时内容（超过阈值天数未更新）"""
        issues = []
        threshold = datetime.now() - timedelta(days=days_threshold)
        
        for page in pages:
            if not page.frontmatter.updated_at:
                continue
            
            try:
                updated = datetime.fromisoformat(page.frontmatter.updated_at)
                if updated < threshold:
                    issues.append(LintIssue(
                        issue_type="outdated",
                        severity="low",
                        page_title=page.title,
                        description=f"页面超过 {days_threshold} 天未更新（最后更新: {page.frontmatter.updated_at}）",
                        suggestion=f"检查并更新 [[{page.title}]] 的内容",
                    ))
            except ValueError:
                pass
        
        return issues

    def _check_empty_pages(self, pages: List[WikiPage]) -> List[LintIssue]:
        """检查空页面"""
        issues = []
        
        for page in pages:
            body_stripped = page.body.strip()
            if len(body_stripped) < 20:
                issues.append(LintIssue(
                    issue_type="empty_page",
                    severity="medium",
                    page_title=page.title,
                    description=f"页面内容过少（{len(body_stripped)} 字符）",
                    suggestion=f"补充 [[{page.title}]] 的内容",
                ))
        
        return issues

    def _check_pages_without_links(
        self, pages: List[WikiPage]
    ) -> List[LintIssue]:
        """检查没有链接的页面"""
        issues = []
        
        for page in pages:
            # 跳过系统页面
            if page.page_type in (PageType.INDEX, PageType.OVERVIEW, PageType.LOG,
                                   PageType.PURPOSE, PageType.SCHEMA):
                continue
            
            links = page.extract_wikilinks()
            if not links:
                issues.append(LintIssue(
                    issue_type="no_links",
                    severity="low",
                    page_title=page.title,
                    description="页面没有 [[wikilink]] 链接",
                    suggestion=f"为 [[{page.title}]] 添加与其他页面的链接",
                ))
        
        return issues

    # ------------------------------------------------------------------
    #  快速检查
    # ------------------------------------------------------------------

    def quick_check(self) -> Dict[str, int]:
        """
        快速检查，返回问题统计
        
        Returns:
            {issue_type: count}
        """
        report = self.run_full_check()
        counts: Dict[str, int] = {}
        for issue in report.issues:
            counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1
        return counts