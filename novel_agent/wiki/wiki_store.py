"""
Wiki 页面存储服务

负责 wiki 页面的 CRUD 操作，将 WikiPage 对象读写为 Markdown 文件。
支持：
- 页面的增删改查
- 按类型/标签/关键词检索
- SHA256 增量缓存
- 线程安全
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .wiki_types import (
    Frontmatter,
    PAGE_TYPE_DIRS,
    PageType,
    WikiPage,
    WIKILINK_PATTERN,
    generate_page_filename,
    get_page_subdir,
    now_iso,
    parse_frontmatter,
)

logger = logging.getLogger(__name__)

# SHA256 缓存文件名
HASH_CACHE_FILENAME = ".wiki_hash_cache.json"


class WikiStore:
    """
    Wiki 页面存储服务
    
    将 wiki 页面存储为 Markdown 文件，目录结构：
    
    wiki_dir/
    ├── index.md
    ├── overview.md
    ├── log.md
    ├── characters/
    │   ├── 主角.md
    │   └── 反派.md
    ├── world/
    │   └── 力量体系.md
    ├── plot/
    │   └── 主线.md
    ├── chapters/
    │   ├── 第1章.md
    │   └── 第2章.md
    └── constraints/
        └── 角色死亡.md
    """

    def __init__(self, wiki_dir: Path):
        """
        初始化 WikiStore
        
        Args:
            wiki_dir: wiki 目录路径（通常是 project_dir/wiki）
        """
        self._wiki_dir = wiki_dir
        self._lock = threading.RLock()
        self._page_cache: Dict[str, WikiPage] = {}  # title → WikiPage
        self._hash_cache: Dict[str, str] = {}  # file_path → sha256
        self._hash_cache_path = wiki_dir / HASH_CACHE_FILENAME
        self._dirty = True  # 是否需要重新扫描

    @property
    def wiki_dir(self) -> Path:
        return self._wiki_dir

    # ------------------------------------------------------------------
    #  初始化
    # ------------------------------------------------------------------

    def ensure_dirs(self) -> None:
        """确保所有 wiki 子目录存在"""
        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        for subdir in set(PAGE_TYPE_DIRS.values()):
            (self._wiki_dir / subdir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def save_page(self, page: WikiPage) -> Path:
        """
        保存 wiki 页面到文件
        
        自动维护双向链接：
        - 正向链接：当前页面的 [[wikilink]] → links_out
        - 反向链接：被链接页面自动更新 links_in
        
        Args:
            page: 要保存的页面
            
        Returns:
            保存后的文件路径（相对于 wiki_dir）
        """
        with self._lock:
            # 确定文件路径
            file_path = self._resolve_file_path(page)
            full_path = self._wiki_dir / file_path
            
            # 确保目录存在
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 更新时间戳
            if not page.frontmatter.created_at:
                page.frontmatter.created_at = now_iso()
            page.frontmatter.updated_at = now_iso()
            
            # 写入文件
            content = page.to_markdown()
            full_path.write_text(content, encoding="utf-8")
            
            # 更新缓存
            old_page = self._page_cache.get(page.title)
            page.file_path = file_path
            self._page_cache[page.title] = page
            self._hash_cache[str(file_path)] = page.content_hash()
            self._save_hash_cache()
            
            # 维护双向链接
            self._update_bidirectional_links(page, old_page)
            
            logger.info(f"[WikiStore] 保存页面: {page.title} -> {file_path}")
            return file_path

    def load_page(self, title: str) -> Optional[WikiPage]:
        """
        按标题加载页面
        
        Args:
            title: 页面标题
            
        Returns:
            WikiPage 或 None
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            return self._page_cache.get(title)

    def load_page_by_path(self, file_path: Path) -> Optional[WikiPage]:
        """
        按文件路径加载页面
        
        Args:
            file_path: 相对于 wiki_dir 的路径
            
        Returns:
            WikiPage 或 None
        """
        safe_path = self._safe_relative_path(file_path)
        if safe_path is None:
            return None

        full_path = self._wiki_dir / safe_path
        if not full_path.exists():
            return None
        
        try:
            content = full_path.read_text(encoding="utf-8")
            page = WikiPage.from_markdown(content, file_path=safe_path)
            return page
        except Exception as e:
            logger.warning(f"[WikiStore] 加载页面失败 {safe_path}: {e}")
            return None

    def delete_page_by_path(self, file_path: Path) -> bool:
        """
        按文件路径删除页面，用于处理空标题或重名标题页面。

        Args:
            file_path: 相对于 wiki_dir 的路径

        Returns:
            是否删除成功
        """
        with self._lock:
            safe_path = self._safe_relative_path(file_path)
            if safe_path is None:
                return False

            page = self.load_page_by_path(safe_path)
            full_path = self._wiki_dir / safe_path
            if not full_path.exists():
                return False

            full_path.unlink()

            if page:
                cached = self._page_cache.get(page.title)
                if cached and cached.file_path == safe_path:
                    self._page_cache.pop(page.title, None)
            self._hash_cache.pop(str(safe_path), None)
            self._save_hash_cache()

            logger.info(f"[WikiStore] 删除页面: {safe_path}")
            return True

    def delete_page(self, title: str) -> bool:
        """
        删除页面
        
        Args:
            title: 页面标题
            
        Returns:
            是否删除成功
        """
        with self._lock:
            page = self.load_page(title)
            if not page or not page.file_path:
                return False
            
            full_path = self._wiki_dir / page.file_path
            if full_path.exists():
                full_path.unlink()
            
            # 清理缓存
            self._page_cache.pop(title, None)
            self._hash_cache.pop(str(page.file_path), None)
            self._save_hash_cache()
            
            logger.info(f"[WikiStore] 删除页面: {title}")
            return True

    def list_pages(
        self,
        page_type: Optional[PageType] = None,
        tags: Optional[List[str]] = None,
    ) -> List[WikiPage]:
        """
        列出页面
        
        Args:
            page_type: 按类型过滤
            tags: 按标签过滤（任一匹配）
            
        Returns:
            页面列表
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            pages = list(self._page_cache.values())
            
            if page_type:
                pages = [p for p in pages if p.page_type == page_type]
            
            if tags:
                tag_set = set(tags)
                pages = [p for p in pages if tag_set & set(p.tags)]
            
            return pages

    def list_all_titles(self) -> List[str]:
        """列出所有页面标题"""
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            return list(self._page_cache.keys())

    def page_exists(self, title: str) -> bool:
        """检查页面是否存在"""
        return self.load_page(title) is not None

    # ------------------------------------------------------------------
    #  搜索
    # ------------------------------------------------------------------

    def search_by_text(self, query: str, top_k: int = 10) -> List[WikiPage]:
        """
        简单的文本搜索（分词匹配）
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            
        Returns:
            匹配的页面列表（按相关性排序）
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            query_lower = query.lower()
            # 中文双字分词 + 英文单词分词
            tokens = self._tokenize(query_lower)
            
            scored: List[tuple[float, WikiPage]] = []
            for page in self._page_cache.values():
                score = self._calculate_text_score(page, tokens, query_lower)
                if score > 0:
                    scored.append((score, page))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            return [page for _, page in scored[:top_k]]

    def get_all_wikilinks(self) -> Dict[str, List[str]]:
        """
        获取所有页面的 wikilink 关系
        
        Returns:
            {source_title: [target_title, ...]}
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            links: Dict[str, List[str]] = {}
            for title, page in self._page_cache.items():
                targets = page.extract_wikilinks()
                if targets:
                    links[title] = targets
            return links

    # ------------------------------------------------------------------
    #  SHA256 增量缓存
    # ------------------------------------------------------------------

    def get_cached_hash(self, file_path: str) -> Optional[str]:
        """获取文件的缓存哈希"""
        with self._lock:
            if not self._hash_cache:
                self._load_hash_cache()
            return self._hash_cache.get(file_path)

    def update_hash(self, file_path: str, file_hash: str) -> None:
        """更新文件哈希缓存"""
        with self._lock:
            self._hash_cache[file_path] = file_hash
            self._save_hash_cache()

    def is_file_changed(self, file_path: Path) -> bool:
        """
        检查文件是否发生变化
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否变化（True = 需要重新摄取）
        """
        if not file_path.exists():
            return True
        
        current_hash = hashlib.sha256(
            file_path.read_bytes()
        ).hexdigest()
        
        cached_hash = self.get_cached_hash(str(file_path))
        return current_hash != cached_hash

    # ------------------------------------------------------------------
    #  统计
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """获取 wiki 统计信息"""
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            type_counts: Dict[str, int] = {}
            total_words = 0
            total_links = 0
            
            for page in self._page_cache.values():
                type_name = page.page_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
                total_words += len(re.sub(r"\s+", "", page.body))
                total_links += len(page.extract_wikilinks())
            
            return {
                "total_pages": len(self._page_cache),
                "type_counts": type_counts,
                "total_words": total_words,
                "total_links": total_links,
                "wiki_dir": str(self._wiki_dir),
            }

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _resolve_file_path(self, page: WikiPage) -> Path:
        """确定页面的文件路径"""
        if page.file_path:
            return page.file_path
        
        filename = generate_page_filename(page.title, page.page_type)
        subdir = get_page_subdir(page.page_type)
        
        if subdir:
            return Path(subdir) / filename
        return Path(filename)

    def _safe_relative_path(self, file_path: Path) -> Optional[Path]:
        """校验 wiki 内部相对路径，避免越权访问。"""
        try:
            raw_path = Path(file_path)
            if raw_path.is_absolute():
                return None
            full_path = (self._wiki_dir / raw_path).resolve()
            wiki_root = self._wiki_dir.resolve()
            full_path.relative_to(wiki_root)
            if full_path.suffix.lower() != ".md":
                return None
            return full_path.relative_to(wiki_root)
        except Exception:
            return None

    def _scan_all_pages(self) -> None:
        """扫描 wiki 目录，加载所有页面到缓存"""
        self._page_cache.clear()
        
        if not self._wiki_dir.exists():
            self._dirty = False
            return
        
        for md_file in self._wiki_dir.rglob("*.md"):
            # 跳过隐藏文件
            if md_file.name.startswith("."):
                continue
            
            try:
                relative_path = md_file.relative_to(self._wiki_dir)
                content = md_file.read_text(encoding="utf-8")
                page = WikiPage.from_markdown(content, file_path=relative_path)
                self._page_cache[page.title] = page
            except Exception as e:
                logger.warning(f"[WikiStore] 扫描页面失败 {md_file}: {e}")
        
        self._dirty = False
        logger.debug(f"[WikiStore] 扫描完成，共 {len(self._page_cache)} 个页面")

    def _load_hash_cache(self) -> None:
        """从文件加载 SHA256 缓存"""
        if self._hash_cache_path.exists():
            try:
                self._hash_cache = json.loads(
                    self._hash_cache_path.read_text(encoding="utf-8")
                )
            except Exception:
                self._hash_cache = {}

    def _save_hash_cache(self) -> None:
        """保存 SHA256 缓存到文件"""
        try:
            self._hash_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._hash_cache_path.write_text(
                json.dumps(self._hash_cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[WikiStore] 保存哈希缓存失败: {e}")

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        简单分词：中文双字 + 英文单词
        """
        tokens: List[str] = []
        # 英文单词
        english_words = re.findall(r"[a-zA-Z]+", text)
        tokens.extend(w.lower() for w in english_words)
        # 中文双字
        chinese_chars = re.findall(r"[\u4e00-\u9fa5]", text)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        # 单字也加入（权重较低）
        tokens.extend(chinese_chars)
        return tokens

    @staticmethod
    def _calculate_text_score(
        page: WikiPage, tokens: List[str], query_lower: str
    ) -> float:
        """计算页面与查询的文本匹配分数"""
        title_lower = page.title.lower()
        body_lower = page.body.lower()
        tags_lower = " ".join(page.tags).lower()
        
        score = 0.0
        
        # 标题完全匹配
        if query_lower in title_lower:
            score += 20.0
        
        # 标题 token 匹配
        title_tokens = set(WikiStore._tokenize(title_lower))
        title_matches = sum(1 for t in tokens if t in title_tokens)
        score += title_matches * 5.0
        
        # 标签匹配
        for tag in page.tags:
            if query_lower in tag.lower():
                score += 10.0
        
        # 正文 token 匹配
        body_tokens = set(WikiStore._tokenize(body_lower))
        body_matches = sum(1 for t in tokens if t in body_tokens)
        score += body_matches * 1.0
        
        return score

    def mark_dirty(self) -> None:
        """标记缓存需要重新扫描"""
        self._dirty = True

    def _update_bidirectional_links(
        self, new_page: WikiPage, old_page: Optional[WikiPage]
    ) -> None:
        """
        维护双向链接（数据互链）
        
        当页面 A 保存时：
        1. 提取 A 的所有 [[wikilink]] 目标
        2. 对比旧版本，找出新增和移除的链接
        3. 更新被链接页面的反向链接信息
        """
        new_targets = set(new_page.extract_wikilinks())
        old_targets = set(old_page.extract_wikilinks()) if old_page else set()
        
        # 需要添加反向链接的目标
        added_targets = new_targets - old_targets
        # 需要移除反向链接的目标
        removed_targets = old_targets - new_targets
        
        # 对于已缓存的目标页面，更新其反向链接信息
        for target_title in (added_targets | removed_targets):
            target_page = self._page_cache.get(target_title)
            if not target_page:
                continue
            
            # 重新计算 target_page 的 links_in
            links_in = []
            for title, page in self._page_cache.items():
                if title == target_title:
                    continue
                page_targets = set(page.extract_wikilinks())
                if target_title in page_targets:
                    links_in.append(title)
            
            # 更新 frontmatter.entities 中的反向链接标记
            # 保留非链接来源的 entities
            non_link_entities = [
                e for e in target_page.frontmatter.entities
                if not any(
                    p.title == e and target_title in p.extract_wikilinks()
                    for p in self._page_cache.values()
                )
            ]
            target_page.frontmatter.entities = list(set(non_link_entities + links_in))

    def get_backlinks(self, title: str) -> List[WikiPage]:
        """
        获取指向指定页面的所有反向链接（谁链接到了这个页面）
        
        Args:
            title: 目标页面标题
            
        Returns:
            链接到该页面的页面列表
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            backlinks = []
            for page_title, page in self._page_cache.items():
                if page_title == title:
                    continue
                targets = page.extract_wikilinks()
                if title in targets:
                    backlinks.append(page)
            
            return backlinks

    def get_bidirectional_links(self, title: str) -> Dict[str, List[str]]:
        """
        获取页面的双向链接关系
        
        Args:
            title: 页面标题
            
        Returns:
            {
                "links_out": ["页面A", "页面B"],  # 当前页面链接到的页面
                "links_in": ["页面C", "页面D"],   # 链接到当前页面的页面
            }
        """
        with self._lock:
            page = self.load_page(title)
            if not page:
                return {"links_out": [], "links_in": []}
            
            links_out = page.extract_wikilinks()
            links_in = [p.title for p in self.get_backlinks(title)]
            
            return {
                "links_out": links_out,
                "links_in": links_in,
            }

    def get_all_bidirectional_links(self) -> Dict[str, Dict[str, List[str]]]:
        """
        获取所有页面的双向链接关系
        
        Returns:
            {
                "页面A": {"links_out": [...], "links_in": [...]},
                "页面B": {"links_out": [...], "links_in": [...]},
            }
        """
        with self._lock:
            if self._dirty:
                self._scan_all_pages()
            
            result = {}
            all_titles = list(self._page_cache.keys())
            
            # 预计算所有 links_out
            links_out_map: Dict[str, List[str]] = {}
            for title, page in self._page_cache.items():
                links_out_map[title] = page.extract_wikilinks()
            
            # 反向推导 links_in
            links_in_map: Dict[str, List[str]] = {t: [] for t in all_titles}
            for source_title, targets in links_out_map.items():
                for target in targets:
                    if target in links_in_map:
                        links_in_map[target].append(source_title)
            
            for title in all_titles:
                result[title] = {
                    "links_out": links_out_map.get(title, []),
                    "links_in": links_in_map.get(title, []),
                }
            
            return result
