"""
Wiki 系统 API 路由

提供 Wiki 页面的 CRUD、搜索、图谱、Lint、Review 等接口。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


# ===== 请求模型 =====

class WikiPageCreate(BaseModel):
    title: str
    page_type: str = "custom"
    body: str = ""
    tags: list[str] = []
    sources: list[str] = []


class WikiPageUpdate(BaseModel):
    body: Optional[str] = None
    tags: Optional[list[str]] = None
    sources: Optional[list[str]] = None


class WikiSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    include_graph: bool = True
    include_vector: bool = True
    context_window: int = 8000


class WikiIngestRequest(BaseModel):
    content: str
    source_name: str = "manual_input"


# ===== 辅助函数 =====

def _get_wiki_compat():
    """获取 Wiki 兼容层实例"""
    from novel_agent.project_manager import get_project_manager
    from novel_agent.wiki import WikiCompatLayer
    pm = get_project_manager()
    project_dir = pm.get_project_data_path("outline").parent
    return WikiCompatLayer(project_dir)


def _get_wiki_store():
    """获取 WikiStore 实例"""
    from novel_agent.project_manager import get_project_manager
    from novel_agent.wiki import WikiStore
    pm = get_project_manager()
    project_dir = pm.get_project_data_path("outline").parent
    return WikiStore(project_dir / "wiki")


# ===== 页面 CRUD =====

@router.get("/pages")
async def list_pages(
    page_type: Optional[str] = None,
    tags: Optional[str] = None,
):
    """列出所有 wiki 页面"""
    try:
        store = _get_wiki_store()
        from novel_agent.wiki import PageType
        pt = PageType(page_type) if page_type else None
        tag_list = tags.split(",") if tags else None
        pages = store.list_pages(page_type=pt, tags=tag_list)
        return JSONResponse({
            "success": True,
            "data": [
                {
                    "title": p.title,
                    "page_type": p.page_type.value,
                    "tags": p.tags,
                    "sources": p.sources,
                    "word_count": len(p.body.replace(" ", "").replace("\n", "")),
                    "links_out": p.extract_wikilinks(),
                    "updated_at": p.frontmatter.updated_at,
                }
                for p in pages
            ],
            "total": len(pages),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 列出页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{title}")
async def get_page(title: str):
    """获取单个 wiki 页面"""
    try:
        store = _get_wiki_store()
        page = store.load_page(title)
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        
        # 获取双向链接
        backlinks = store.get_backlinks(title)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "page_type": page.page_type.value,
                "body": page.body,
                "tags": page.tags,
                "sources": page.sources,
                "entities": page.entities,
                "links_out": page.extract_wikilinks(),
                "links_in": [p.title for p in backlinks],
                "word_count": len(page.body.replace(" ", "").replace("\n", "")),
                "created_at": page.frontmatter.created_at,
                "updated_at": page.frontmatter.updated_at,
                "file_path": str(page.file_path) if page.file_path else None,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 获取页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pages")
async def create_page(data: WikiPageCreate):
    """创建 wiki 页面"""
    try:
        store = _get_wiki_store()
        from novel_agent.wiki import WikiPage, Frontmatter, PageType, now_iso
        
        pt = PageType(data.page_type) if data.page_type in [t.value for t in PageType] else PageType.CUSTOM
        
        page = WikiPage(
            frontmatter=Frontmatter(
                page_type=pt,
                title=data.title,
                tags=data.tags,
                sources=data.sources,
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=data.body,
        )
        
        file_path = store.save_page(page)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "file_path": str(file_path),
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 创建页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pages/{title}")
async def update_page(title: str, data: WikiPageUpdate):
    """更新 wiki 页面"""
    try:
        store = _get_wiki_store()
        page = store.load_page(title)
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        
        if data.body is not None:
            page.body = data.body
        if data.tags is not None:
            page.frontmatter.tags = data.tags
        if data.sources is not None:
            page.frontmatter.sources = data.sources
        
        file_path = store.save_page(page)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "file_path": str(file_path),
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 更新页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pages/{title}")
async def delete_page(title: str):
    """删除 wiki 页面"""
    try:
        store = _get_wiki_store()
        result = store.delete_page(title)
        if not result:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        return JSONResponse({"success": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 删除页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 搜索 =====

@router.post("/search")
async def search_wiki(data: WikiSearchRequest):
    """多阶段检索"""
    try:
        compat = _get_wiki_compat()
        result = await compat.retriever.retrieve(
            query=data.query,
            context_window=data.context_window,
            top_k=data.top_k,
            include_graph=data.include_graph,
            include_vector=data.include_vector,
        )
        return JSONResponse({
            "success": True,
            "data": result.to_dict(),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/text")
async def text_search(q: str, top_k: int = 10):
    """简单文本搜索"""
    try:
        store = _get_wiki_store()
        pages = store.search_by_text(q, top_k=top_k)
        return JSONResponse({
            "success": True,
            "data": [
                {
                    "title": p.title,
                    "page_type": p.page_type.value,
                    "summary": p.body[:200],
                    "tags": p.tags,
                }
                for p in pages
            ],
        })
    except Exception as e:
        logger.error(f"[Wiki API] 文本搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 知识图谱 =====

@router.get("/graph")
async def get_graph():
    """获取知识图谱数据"""
    try:
        compat = _get_wiki_compat()
        pages = compat.store.list_pages()
        graph = compat.graph_builder.build_from_pages(pages)
        
        nodes = []
        for title, node in graph.nodes.items():
            nodes.append({
                "id": title,
                "label": title,
                "type": node.page_type.value,
                "degree": node.degree,
                "size": node.display_size,
                "tags": node.tags,
            })
        
        edges = []
        for edge in graph.edges:
            edges.append({
                "source": edge.source,
                "target": edge.target,
                "weight": round(edge.weight, 2),
                "signals": edge.signals,
                "color": edge.display_color,
            })
        
        stats = compat.graph_builder.get_statistics()
        
        return JSONResponse({
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "statistics": stats,
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/backlinks/{title}")
async def get_backlinks(title: str):
    """获取页面的反向链接"""
    try:
        store = _get_wiki_store()
        backlinks = store.get_backlinks(title)
        return JSONResponse({
            "success": True,
            "data": [p.title for p in backlinks],
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取反向链接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/insights")
async def get_graph_insights():
    """获取图谱洞察（意外连接、知识缺口）"""
    try:
        compat = _get_wiki_compat()
        pages = compat.store.list_pages()
        compat.graph_builder.build_from_pages(pages)
        
        surprising = compat.graph_builder.get_surprising_connections()
        gaps = compat.graph_builder.get_knowledge_gaps()
        
        return JSONResponse({
            "success": True,
            "data": {
                "surprising_connections": surprising[:10],
                "knowledge_gaps": gaps[:10],
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取图谱洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Lint =====

@router.get("/lint")
async def run_lint():
    """运行 Lint 质量检查"""
    try:
        compat = _get_wiki_compat()
        report = compat.linter.run_full_check()
        return JSONResponse({
            "success": True,
            "data": {
                "total_pages": report.total_pages,
                "total_links": report.total_links,
                "isolated_count": report.isolated_count,
                "dead_link_count": report.dead_link_count,
                "issues": [
                    {
                        "type": i.issue_type,
                        "severity": i.severity,
                        "page": i.page_title,
                        "description": i.description,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues
                ],
                "summary": report.summary(),
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] Lint 检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Review =====

@router.get("/reviews")
async def list_reviews(status: Optional[str] = None):
    """列出审核项"""
    try:
        compat = _get_wiki_compat()
        items = compat.review.list_items(status=status)
        return JSONResponse({
            "success": True,
            "data": [i.to_dict() for i in items],
            "pending_count": compat.review.get_pending_count(),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 列出审核项失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reviews/{item_id}/approve")
async def approve_review(item_id: str, notes: str = ""):
    """批准审核项"""
    try:
        compat = _get_wiki_compat()
        item = compat.review.approve(item_id, notes)
        if not item:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return JSONResponse({"success": True, "data": item.to_dict()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reviews/{item_id}/reject")
async def reject_review(item_id: str, notes: str = ""):
    """拒绝审核项"""
    try:
        compat = _get_wiki_compat()
        item = compat.review.reject(item_id, notes)
        if not item:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return JSONResponse({"success": True, "data": item.to_dict()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 摄取 =====

@router.post("/ingest")
async def ingest_text(data: WikiIngestRequest):
    """摄取文本内容到 wiki"""
    try:
        compat = _get_wiki_compat()
        result = await compat.ingest.ingest_text(
            content=data.content,
            source_name=data.source_name,
        )
        return JSONResponse({
            "success": result.success,
            "data": {
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "duration": result.duration_seconds,
                "error": result.error,
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 摄取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 统计 =====

@router.get("/stats")
async def get_stats():
    """获取 wiki 统计信息"""
    try:
        compat = _get_wiki_compat()
        stats = compat.get_statistics()
        return JSONResponse({
            "success": True,
            "data": stats,
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 迁移 =====

@router.post("/migrate")
async def migrate_from_library():
    """从旧资料库迁移数据到 wiki"""
    try:
        compat = _get_wiki_compat()
        stats = compat.migrate_from_library()
        return JSONResponse({
            "success": True,
            "data": stats,
        })
    except Exception as e:
        logger.error(f"[Wiki API] 迁移失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))