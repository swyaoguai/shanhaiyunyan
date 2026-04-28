"""
Wiki Review 审核系统

异步人工审核系统：
- LLM 在摄取时标记需要人工判断的项
- 预定义操作：创建页面、深度研究、跳过
- 用户在方便时处理审核项
- 支持预生成搜索词（用于深度研究）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_types import now_iso

logger = logging.getLogger(__name__)

REVIEWS_DIR = "reviews"
REVIEWS_INDEX = "reviews_index.json"


@dataclass
class ReviewItem:
    """审核项"""
    id: str
    title: str  # 审核项标题
    description: str  # 描述
    source_page: str  # 来源页面
    action_type: str  # create_page / deep_research / skip / manual
    status: str = "pending"  # pending / approved / rejected / skipped
    search_queries: List[str] = field(default_factory=list)  # 预生成的搜索词
    suggested_page_type: str = ""  # 建议的页面类型
    suggested_content: str = ""  # LLM 建议的内容
    created_at: str = ""
    resolved_at: str = ""
    resolved_by: str = ""  # user / auto
    notes: str = ""  # 用户备注

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source_page": self.source_page,
            "action_type": self.action_type,
            "status": self.status,
            "search_queries": self.search_queries,
            "suggested_page_type": self.suggested_page_type,
            "suggested_content": self.suggested_content,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReviewItem":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            source_page=d.get("source_page", ""),
            action_type=d.get("action_type", "manual"),
            status=d.get("status", "pending"),
            search_queries=d.get("search_queries", []),
            suggested_page_type=d.get("suggested_page_type", ""),
            suggested_content=d.get("suggested_content", ""),
            created_at=d.get("created_at", ""),
            resolved_at=d.get("resolved_at", ""),
            resolved_by=d.get("resolved_by", ""),
            notes=d.get("notes", ""),
        )


class ReviewManager:
    """
    审核管理器
    
    管理待审核项的生命周期。
    """

    def __init__(self, project_dir: Path):
        self._project_dir = project_dir
        self._reviews_dir = project_dir / ".llm-wiki" / REVIEWS_DIR
        self._index_path = project_dir / ".llm-wiki" / REVIEWS_INDEX
        self._items: List[ReviewItem] = []
        self._load()

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def add_item(self, item: ReviewItem) -> ReviewItem:
        """添加审核项"""
        if not item.created_at:
            item.created_at = now_iso()
        if not item.id:
            import uuid
            item.id = str(uuid.uuid4())[:8]
        
        self._items.append(item)
        self._save()
        
        logger.info(f"[Review] 新增审核项: {item.title} ({item.action_type})")
        return item

    def add_items(self, items: List[ReviewItem]) -> List[ReviewItem]:
        """批量添加审核项"""
        result = []
        for item in items:
            result.append(self.add_item(item))
        return result

    def get_item(self, item_id: str) -> Optional[ReviewItem]:
        """获取审核项"""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def list_items(
        self,
        status: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> List[ReviewItem]:
        """列出审核项"""
        items = list(self._items)
        
        if status:
            items = [i for i in items if i.status == status]
        if action_type:
            items = [i for i in items if i.action_type == action_type]
        
        return items

    def approve(self, item_id: str, notes: str = "") -> Optional[ReviewItem]:
        """批准审核项"""
        item = self.get_item(item_id)
        if not item:
            return None
        
        item.status = "approved"
        item.resolved_at = now_iso()
        item.resolved_by = "user"
        item.notes = notes
        self._save()
        
        logger.info(f"[Review] 批准: {item.title}")
        return item

    def reject(self, item_id: str, notes: str = "") -> Optional[ReviewItem]:
        """拒绝审核项"""
        item = self.get_item(item_id)
        if not item:
            return None
        
        item.status = "rejected"
        item.resolved_at = now_iso()
        item.resolved_by = "user"
        item.notes = notes
        self._save()
        
        logger.info(f"[Review] 拒绝: {item.title}")
        return item

    def skip(self, item_id: str, notes: str = "") -> Optional[ReviewItem]:
        """跳过审核项"""
        item = self.get_item(item_id)
        if not item:
            return None
        
        item.status = "skipped"
        item.resolved_at = now_iso()
        item.resolved_by = "user"
        item.notes = notes
        self._save()
        
        logger.info(f"[Review] 跳过: {item.title}")
        return item

    # ------------------------------------------------------------------
    #  统计
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """获取审核统计"""
        total = len(self._items)
        pending = sum(1 for i in self._items if i.status == "pending")
        approved = sum(1 for i in self._items if i.status == "approved")
        rejected = sum(1 for i in self._items if i.status == "rejected")
        skipped = sum(1 for i in self._items if i.status == "skipped")
        
        action_counts: Dict[str, int] = {}
        for item in self._items:
            action_counts[item.action_type] = action_counts.get(item.action_type, 0) + 1
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "skipped": skipped,
            "action_counts": action_counts,
        }

    def get_pending_count(self) -> int:
        """获取待审核数量"""
        return sum(1 for i in self._items if i.status == "pending")

    # ------------------------------------------------------------------
    #  批量操作
    # ------------------------------------------------------------------

    def get_approved_items(self) -> List[ReviewItem]:
        """获取所有已批准的审核项"""
        return [i for i in self._items if i.status == "approved"]

    def get_deep_research_items(self) -> List[ReviewItem]:
        """获取需要深度研究的审核项"""
        return [
            i for i in self._items
            if i.status == "approved" and i.action_type == "deep_research"
        ]

    def get_create_page_items(self) -> List[ReviewItem]:
        """获取需要创建页面的审核项"""
        return [
            i for i in self._items
            if i.status == "approved" and i.action_type == "create_page"
        ]

    # ------------------------------------------------------------------
    #  持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从文件加载审核项"""
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._items = [ReviewItem.from_dict(d) for d in data]
            except Exception as e:
                logger.warning(f"[Review] 加载审核项失败: {e}")
                self._items = []

    def _save(self) -> None:
        """保存审核项到文件"""
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            data = [item.to_dict() for item in self._items]
            self._index_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[Review] 保存审核项失败: {e}")

    def clear_resolved(self) -> int:
        """清理已解决的审核项"""
        before = len(self._items)
        self._items = [
            i for i in self._items
            if i.status == "pending"
        ]
        self._save()
        cleared = before - len(self._items)
        if cleared:
            logger.info(f"[Review] 清理了 {cleared} 个已解决的审核项")
        return cleared