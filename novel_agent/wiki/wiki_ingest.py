"""
Wiki 两步链式摄取管道

基于 Karpathy LLM Wiki 模式的两步摄取：
Step 1: LLM 分析源文档 → 结构化分析（实体、概念、连接、矛盾）
Step 2: LLM 根据分析 → 生成 wiki 页面

支持：
- SHA256 增量缓存（跳过未变化的文件）
- 持久化摄取队列（崩溃恢复）
- 来源溯源（sources[] 字段）
- overview.md / index.md 自动更新
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Awaitable

from .wiki_types import (
    Frontmatter,
    IngestResult,
    PageType,
    WikiPage,
    now_iso,
)
from .wiki_store import WikiStore
from .wiki_index import WikiIndexManager
from .wiki_graph import WikiGraphBuilder

logger = logging.getLogger(__name__)

# 摄取队列文件名
QUEUE_FILENAME = ".wiki_ingest_queue.json"


@dataclass
class IngestTask:
    """摄取任务"""
    source_path: str  # 源文件路径
    source_hash: str  # 文件 SHA256
    status: str = "pending"  # pending / processing / completed / failed
    retries: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "status": self.status,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IngestTask":
        return cls(
            source_path=d.get("source_path", ""),
            source_hash=d.get("source_hash", ""),
            status=d.get("status", "pending"),
            retries=d.get("retries", 0),
            max_retries=d.get("max_retries", 3),
            error=d.get("error"),
            created_at=d.get("created_at", ""),
            completed_at=d.get("completed_at", ""),
        )


# LLM 调用接口类型
LLMCallFn = Callable[[str, str], Awaitable[str]]


class WikiIngestPipeline:
    """
    Wiki 两步链式摄取管道
    
    使用方式：
        pipeline = WikiIngestPipeline(store, index, graph_builder, llm_call)
        result = await pipeline.ingest_file(source_path)
    """

    def __init__(
        self,
        store: WikiStore,
        index: WikiIndexManager,
        graph_builder: WikiGraphBuilder,
        llm_call: Optional[LLMCallFn] = None,
    ):
        """
        初始化摄取管道
        
        Args:
            store: wiki 页面存储
            index: 索引管理器
            graph_builder: 图谱构建器
            llm_call: LLM 调用函数 (system_prompt, user_prompt) -> response
        """
        self._store = store
        self._index = index
        self._graph_builder = graph_builder
        self._llm_call = llm_call
        self._queue: List[IngestTask] = []
        self._queue_path = store.wiki_dir / QUEUE_FILENAME
        self._load_queue()

    # ------------------------------------------------------------------
    #  主摄取流程
    # ------------------------------------------------------------------

    async def ingest_file(self, source_path: Path) -> IngestResult:
        """
        摄取单个文件（两步链式）
        
        Args:
            source_path: 源文件路径
            
        Returns:
            摄取结果
        """
        start_time = time.time()
        
        # 计算文件哈希
        if not source_path.exists():
            return IngestResult(
                source_file=str(source_path),
                source_hash="",
                success=False,
                error=f"文件不存在: {source_path}",
            )
        
        file_bytes = source_path.read_bytes()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # SHA256 增量检查
        cached_hash = self._store.get_cached_hash(str(source_path))
        if cached_hash == file_hash:
            logger.info(f"[Ingest] 文件未变化，跳过: {source_path.name}")
            return IngestResult(
                source_file=str(source_path),
                source_hash=file_hash,
                success=True,
                duration_seconds=time.time() - start_time,
            )
        
        # 读取源文件内容
        try:
            source_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                source_content = file_bytes.decode("gbk")
            except Exception:
                return IngestResult(
                    source_file=str(source_path),
                    source_hash=file_hash,
                    success=False,
                    error=f"无法解码文件: {source_path}",
                )
        
        # 获取现有 wiki 上下文
        existing_pages = self._store.list_all_titles()
        purpose = self._index.load_purpose() or ""
        
        # Step 1: LLM 分析
        logger.info(f"[Ingest] Step 1: 分析 {source_path.name}...")
        analysis = await self._step1_analyze(
            source_content=source_content,
            source_name=source_path.name,
            existing_pages=existing_pages,
            purpose=purpose,
        )
        
        # Step 2: LLM 生成 wiki 页面
        logger.info(f"[Ingest] Step 2: 生成 wiki 页面...")
        wiki_pages = await self._step2_generate(
            analysis=analysis,
            source_content=source_content,
            source_name=source_path.name,
            existing_pages=existing_pages,
            purpose=purpose,
        )
        
        # 保存页面
        pages_created = []
        pages_updated = []
        for page in wiki_pages:
            existing = self._store.load_page(page.title)
            if existing:
                pages_updated.append(page.title)
            else:
                pages_created.append(page.title)
            self._store.save_page(page)
        
        # 更新哈希缓存
        self._store.update_hash(str(source_path), file_hash)
        
        # 更新 index.md 和 overview.md
        all_pages = self._store.list_pages()
        index_page = self._index.generate_index(all_pages)
        self._store.save_page(index_page)
        
        overview_page = self._index.generate_overview(all_pages, purpose)
        self._store.save_page(overview_page)
        
        # 记录日志
        self._index.append_log(
            action="ingest",
            details=f"来源: {source_path.name}",
            pages_affected=pages_created + pages_updated,
        )
        
        # 重建图谱
        self._graph_builder.build_from_pages(all_pages)
        
        duration = time.time() - start_time
        logger.info(
            f"[Ingest] 完成: {source_path.name} -> "
            f"创建 {len(pages_created)}, 更新 {len(pages_updated)}, "
            f"耗时 {duration:.1f}s"
        )
        
        return IngestResult(
            source_file=str(source_path),
            source_hash=file_hash,
            pages_created=pages_created,
            pages_updated=pages_updated,
            analysis=analysis,
            success=True,
            duration_seconds=duration,
        )

    async def ingest_text(
        self,
        content: str,
        source_name: str = "manual_input",
    ) -> IngestResult:
        """
        摄取文本内容（非文件）
        
        Args:
            content: 文本内容
            source_name: 来源名称
            
        Returns:
            摄取结果
        """
        start_time = time.time()
        
        existing_pages = self._store.list_all_titles()
        purpose = self._index.load_purpose() or ""
        
        # Step 1
        analysis = await self._step1_analyze(
            source_content=content,
            source_name=source_name,
            existing_pages=existing_pages,
            purpose=purpose,
        )
        
        # Step 2
        wiki_pages = await self._step2_generate(
            analysis=analysis,
            source_content=content,
            source_name=source_name,
            existing_pages=existing_pages,
            purpose=purpose,
        )
        
        # 保存
        pages_created = []
        pages_updated = []
        for page in wiki_pages:
            existing = self._store.load_page(page.title)
            if existing:
                pages_updated.append(page.title)
            else:
                pages_created.append(page.title)
            self._store.save_page(page)
        
        # 更新索引
        all_pages = self._store.list_pages()
        index_page = self._index.generate_index(all_pages)
        self._store.save_page(index_page)
        
        overview_page = self._index.generate_overview(all_pages, purpose)
        self._store.save_page(overview_page)
        
        self._index.append_log(
            action="ingest_text",
            details=f"来源: {source_name}",
            pages_affected=pages_created + pages_updated,
        )
        
        self._graph_builder.build_from_pages(all_pages)
        
        return IngestResult(
            source_file=source_name,
            source_hash=hashlib.sha256(content.encode()).hexdigest(),
            pages_created=pages_created,
            pages_updated=pages_updated,
            analysis=analysis,
            success=True,
            duration_seconds=time.time() - start_time,
        )

    # ------------------------------------------------------------------
    #  两步链式 LLM 调用
    # ------------------------------------------------------------------

    async def _step1_analyze(
        self,
        source_content: str,
        source_name: str,
        existing_pages: List[str],
        purpose: str,
    ) -> str:
        """
        Step 1: LLM 分析源文档
        
        输出结构化分析：
        - 关键实体（角色、地点、组织）
        - 核心概念（设定、规则、术语）
        - 与现有 wiki 的连接
        - 矛盾和张力
        - wiki 结构建议
        """
        system_prompt = """你是一个专业的知识分析器。你的任务是分析源文档，提取结构化信息用于构建wiki。

请输出以下结构的分析结果（使用Markdown格式）：

## 关键实体
列出文档中提到的所有重要实体（角色、地点、组织、物品等），每个实体包含：
- 名称
- 类型（角色/地点/组织/物品）
- 简要描述
- 与其他实体的关系

## 核心概念
列出文档中的核心概念（设定、规则、术语、能力体系等）

## 剧情要点
列出关键剧情事件、转折点、伏笔

## 与现有wiki的连接
分析这些内容与现有wiki页面的关系：
- 应该链接到哪些现有页面
- 是否与现有内容矛盾
- 是否需要更新现有页面

## 矛盾检测
检查新内容与现有知识是否存在矛盾

## wiki结构建议
建议如何组织这些内容为wiki页面：
- 应该创建哪些新页面
- 每个页面的类型和标题
- 页面间的链接关系"""

        existing_list = "\n".join(f"- {title}" for title in existing_pages[:50])
        
        user_prompt = f"""## 来源文件
{source_name}

## 现有wiki页面
{existing_list if existing_pages else "（暂无现有页面）"}

## 创作目标
{purpose[:500] if purpose else "（未设置）"}

## 源文档内容
{source_content[:8000]}

请分析以上内容，提取结构化信息。"""

        if self._llm_call:
            return await self._llm_call(system_prompt, user_prompt)
        else:
            # 无 LLM 时返回基础分析
            return self._fallback_analysis(source_content, source_name)

    async def _step2_generate(
        self,
        analysis: str,
        source_content: str,
        source_name: str,
        existing_pages: List[str],
        purpose: str,
    ) -> List[WikiPage]:
        """
        Step 2: LLM 根据分析生成 wiki 页面
        
        输出：wiki 页面列表（含 frontmatter 和正文）
        """
        system_prompt = """你是一个专业的wiki页面生成器。根据分析结果，生成结构化的wiki页面。

每个页面必须包含：
1. YAML frontmatter（用 --- 包围）
2. Markdown 正文

输出格式：用 ===PAGE_SEPARATOR=== 分隔每个页面。

每个页面的格式：
---
type: [页面类型]
title: [页面标题]
sources: [来源文件列表]
tags: [标签列表]
entities: [涉及实体列表]
---

# 页面标题

正文内容...

使用 [[页面名]] 语法创建跨引用链接。

页面类型包括：character（角色）、world（世界观）、plot（剧情）、chapter（章节摘要）、constraint（约束）、concept（概念）

请确保：
1. 每个页面都有完整的 frontmatter
2. 正文内容详细且有结构
3. 使用 [[wikilink]] 创建交叉引用
4. 来源字段包含源文件名"""

        user_prompt = f"""## 分析结果
{analysis[:6000]}

## 源文件名
{source_name}

## 现有wiki页面
{", ".join(existing_pages[:30])}

请根据分析结果生成wiki页面。用 ===PAGE_SEPARATOR=== 分隔每个页面。"""

        if self._llm_call:
            response = await self._llm_call(system_prompt, user_prompt)
            return self._parse_generated_pages(response, source_name)
        else:
            # 无 LLM 时返回基础页面
            return self._fallback_generate(source_content, source_name)

    def _parse_generated_pages(
        self, response: str, source_name: str
    ) -> List[WikiPage]:
        """解析 LLM 生成的 wiki 页面"""
        pages = []
        
        # 按分隔符分割
        sections = response.split("===PAGE_SEPARATOR===")
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            try:
                page = WikiPage.from_markdown(section)
                # 确保有来源
                if source_name not in page.frontmatter.sources:
                    page.frontmatter.sources.append(source_name)
                # 确保有创建时间
                if not page.frontmatter.created_at:
                    page.frontmatter.created_at = now_iso()
                pages.append(page)
            except Exception as e:
                logger.warning(f"[Ingest] 解析页面失败: {e}")
        
        return pages

    # ------------------------------------------------------------------
    #  降级方案（无 LLM 时）
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_analysis(content: str, source_name: str) -> str:
        """无 LLM 时的基础分析"""
        import re
        
        # 提取可能的实体名（中文人名/地名模式）
        names = set()
        for match in re.finditer(r"[\u4e00-\u9fa5]{2,4}(?:说|道|想|看|走|来|去)", content):
            name = match.group()[:-1]
            if len(name) >= 2:
                names.add(name)
        
        lines = [
            "## 关键实体",
            "",
        ]
        for name in sorted(names)[:20]:
            lines.append(f"- {name}（角色）")
        
        lines.extend([
            "",
            "## 核心概念",
            "- 待补充",
            "",
            "## 剧情要点",
            f"- 来源: {source_name}",
            "",
            "## wiki结构建议",
            "- 创建章节摘要页面",
        ])
        
        return "\n".join(lines)

    @staticmethod
    def _fallback_generate(
        content: str, source_name: str
    ) -> List[WikiPage]:
        """无 LLM 时的基础页面生成"""
        # 创建一个来源摘要页
        page = WikiPage(
            frontmatter=Frontmatter(
                page_type=PageType.SOURCE,
                title=source_name.replace(".md", "").replace(".txt", ""),
                sources=[source_name],
                tags=["auto-generated"],
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=f"# {source_name}\n\n{content[:2000]}",
        )
        return [page]

    # ------------------------------------------------------------------
    #  摄取队列
    # ------------------------------------------------------------------

    def enqueue(self, source_path: Path) -> IngestTask:
        """将文件加入摄取队列"""
        file_hash = ""
        if source_path.exists():
            file_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        
        task = IngestTask(
            source_path=str(source_path),
            source_hash=file_hash,
            status="pending",
            created_at=now_iso(),
        )
        self._queue.append(task)
        self._save_queue()
        return task

    async def process_queue(self) -> List[IngestResult]:
        """处理摄取队列中的所有任务"""
        results = []
        
        for task in self._queue:
            if task.status in ("completed",):
                continue
            
            if task.retries >= task.max_retries:
                task.status = "failed"
                continue
            
            task.status = "processing"
            self._save_queue()
            
            try:
                result = await self.ingest_file(Path(task.source_path))
                if result.success:
                    task.status = "completed"
                    task.completed_at = now_iso()
                else:
                    task.status = "failed"
                    task.error = result.error
                results.append(result)
            except Exception as e:
                task.retries += 1
                task.error = str(e)
                if task.retries >= task.max_retries:
                    task.status = "failed"
                logger.error(f"[Ingest] 队列任务失败: {task.source_path}: {e}")
            
            self._save_queue()
        
        return results

    def get_queue_status(self) -> List[Dict[str, Any]]:
        """获取队列状态"""
        return [task.to_dict() for task in self._queue]

    def _load_queue(self) -> None:
        """从文件加载队列"""
        if self._queue_path.exists():
            try:
                data = json.loads(self._queue_path.read_text(encoding="utf-8"))
                self._queue = [IngestTask.from_dict(t) for t in data]
            except Exception:
                self._queue = []

    def _save_queue(self) -> None:
        """保存队列到文件"""
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            data = [t.to_dict() for t in self._queue]
            self._queue_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[Ingest] 保存队列失败: {e}")