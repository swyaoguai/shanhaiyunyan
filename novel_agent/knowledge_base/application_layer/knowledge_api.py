"""
知识管理API模块

提供知识库的增删改查操作接口。
支持：
- 章节内容管理
- 知识片段管理
- 批量操作
"""

import logging
import uuid
import hashlib
from collections import defaultdict
from typing import Optional, Any
from dataclasses import dataclass

from ..config import KnowledgeBaseConfig
from ..data_layer.vector_store import VectorStore
from ..data_layer.fulltext_store import FullTextStore
from ..data_layer.metadata_store import MetadataStore, ChapterInfo
from ..logic_layer.chunker import TextChunker, TextChunk
from ..logic_layer.embeddings import EmbeddingService
from ..logic_layer.chapter_marker import ChapterMarker

logger = logging.getLogger(__name__)


@dataclass
class AddChapterResult:
    """添加章节结果"""
    chapter_id: str
    title: str
    word_count: int
    chunk_count: int
    success: bool
    error: Optional[str] = None


class KnowledgeAPI:
    """
    知识管理API
    
    提供知识库的高级操作接口。
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        fulltext_store: FullTextStore,
        metadata_store: MetadataStore,
        embedding_service: EmbeddingService,
        chunker: TextChunker,
        chapter_marker: ChapterMarker
    ):
        """
        初始化知识管理API
        
        Args:
            vector_store: 向量存储
            fulltext_store: 全文存储
            metadata_store: 元数据存储
            embedding_service: 向量化服务
            chunker: 文本分块器
            chapter_marker: 章节标记器
        """
        self.vector_store = vector_store
        self.fulltext_store = fulltext_store
        self.metadata_store = metadata_store
        self.embedding_service = embedding_service
        self.chunker = chunker
        self.chapter_marker = chapter_marker
    
    def add_chapter(
        self,
        chapter_id: Optional[str],
        title: str,
        content: str,
        chapter_number: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> AddChapterResult:
        """
        添加章节到知识库
        
        Args:
            chapter_id: 章节ID（可选，自动生成）
            title: 章节标题
            content: 章节内容
            chapter_number: 章节序号
            metadata: 其他元数据
        
        Returns:
            添加结果
        """
        try:
            # 生成章节ID
            if not chapter_id:
                chapter_id = f"chapter_{uuid.uuid4().hex[:8]}"
            
            # 计算字数
            word_count = self._count_words(content)
            
            # 文本分块
            chunks = self.chunker.chunk(content)
            chunk_count = len(chunks)
            
            if chunk_count == 0:
                return AddChapterResult(
                    chapter_id=chapter_id,
                    title=title,
                    word_count=word_count,
                    chunk_count=0,
                    success=False,
                    error="内容为空或无法分块"
                )
            
            # 向量化
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_service.embed_batch(chunk_texts)
            embedding_info = self._get_embedding_info()
            
            # 准备存储数据
            chunk_ids = [f"{chapter_id}_chunk_{i}" for i in range(chunk_count)]
            chunk_metadatas = []
            chunk_info_list = []
            
            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    "chapter_id": chapter_id,
                    "chunk_index": i,
                    "word_count": chunk.word_count,
                    "embedding_provider": embedding_info.get("provider", embedding_info.get("base_url", "api")),
                    "embedding_model": embedding_info.get("model", ""),
                    "embedding_dim": embedding_info.get("embedding_dim", 0),
                    "content_hash": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                    **(metadata or {})
                }
                chunk_metadatas.append(chunk_metadata)
                
                chunk_info_list.append({
                    "chunk_id": chunk_ids[i],
                    "chapter_id": chapter_id,
                    "chunk_index": i,
                    "start_pos": chunk.start_pos,
                    "end_pos": chunk.end_pos,
                    "word_count": chunk.word_count,
                })
            
            # 存储到向量数据库
            self.vector_store.upsert(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=chunk_metadatas
            )
            
            # 存储到全文索引
            self.fulltext_store.add_batch(
                ids=chunk_ids,
                documents=chunk_texts,
                chapter_ids=[chapter_id] * chunk_count,
                chunk_indices=list(range(chunk_count)),
                metadatas=chunk_metadatas
            )
            
            # 存储元数据
            self.metadata_store.add_chapter(
                chapter_id=chapter_id,
                title=title,
                chapter_number=chapter_number,
                word_count=word_count,
                metadata=metadata
            )
            self.metadata_store.add_chunks_batch(chunk_info_list)
            self.metadata_store.update_chapter_chunk_count(chapter_id, chunk_count)
            
            logger.info(f"章节添加成功: {chapter_id}, {title}, "
                       f"{word_count}字, {chunk_count}块")
            
            return AddChapterResult(
                chapter_id=chapter_id,
                title=title,
                word_count=word_count,
                chunk_count=chunk_count,
                success=True
            )
            
        except Exception as e:
            logger.error(f"添加章节失败: {e}")
            return AddChapterResult(
                chapter_id=chapter_id or "",
                title=title,
                word_count=0,
                chunk_count=0,
                success=False,
                error=str(e)
            )

    def _get_embedding_info(self) -> dict:
        try:
            info = self.embedding_service.get_model_info()
            return info if isinstance(info, dict) else {}
        except Exception:
            return {}
    
    def update_chapter(
        self,
        chapter_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        chapter_number: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> AddChapterResult:
        """
        更新章节
        
        Args:
            chapter_id: 章节ID
            title: 新标题
            content: 新内容
            chapter_number: 新序号
            metadata: 新元数据
        
        Returns:
            更新结果
        """
        # 检查章节是否存在
        existing = self.metadata_store.get_chapter(chapter_id)
        if not existing:
            return AddChapterResult(
                chapter_id=chapter_id,
                title=title or "",
                word_count=0,
                chunk_count=0,
                success=False,
                error="章节不存在"
            )
        
        # 如果内容更新，需要重建索引
        if content is not None:
            # 先备份旧内容，避免“先删后加”失败导致数据丢失
            backup_title = existing.title
            backup_number = existing.chapter_number
            backup_metadata = existing.metadata
            backup_content = self.get_chapter_content(chapter_id)
            if backup_content is None:
                return AddChapterResult(
                    chapter_id=chapter_id,
                    title=title or existing.title,
                    word_count=0,
                    chunk_count=0,
                    success=False,
                    error="无法读取旧章节内容，已拒绝执行高风险更新"
                )

            deleted = self.delete_chapter(chapter_id)
            if not deleted:
                return AddChapterResult(
                    chapter_id=chapter_id,
                    title=title or existing.title,
                    word_count=0,
                    chunk_count=0,
                    success=False,
                    error="删除旧章节失败，未执行更新"
                )
            
            # 重新添加；若失败则尽力回滚
            updated_result = self.add_chapter(
                chapter_id=chapter_id,
                title=title or existing.title,
                content=content,
                chapter_number=chapter_number or existing.chapter_number,
                metadata=metadata or existing.metadata
            )
            if updated_result.success:
                return updated_result

            logger.error(f"更新章节失败，开始回滚: {chapter_id}, error={updated_result.error}")
            rollback_result = self.add_chapter(
                chapter_id=chapter_id,
                title=backup_title,
                content=backup_content,
                chapter_number=backup_number,
                metadata=backup_metadata
            )
            rollback_error = ""
            if not rollback_result.success:
                rollback_error = f"，且回滚失败: {rollback_result.error}"

            return AddChapterResult(
                chapter_id=chapter_id,
                title=title or existing.title,
                word_count=0,
                chunk_count=0,
                success=False,
                error=f"更新失败: {updated_result.error}{rollback_error}"
            )
        
        # 只更新元数据
        updated = self.metadata_store.update_chapter(
            chapter_id=chapter_id,
            title=title,
            chapter_number=chapter_number,
            metadata=metadata
        )
        
        if updated:
            return AddChapterResult(
                chapter_id=chapter_id,
                title=updated.title,
                word_count=updated.word_count,
                chunk_count=updated.chunk_count,
                success=True
            )
        
        return AddChapterResult(
            chapter_id=chapter_id,
            title=title or "",
            word_count=0,
            chunk_count=0,
            success=False,
            error="更新失败"
        )
    
    def delete_chapter(self, chapter_id: str) -> bool:
        """
        删除章节
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            是否删除成功
        """
        try:
            # 获取所有分块ID
            chunks = self.metadata_store.get_chunks_by_chapter(chapter_id)
            chunk_ids = [c["chunk_id"] for c in chunks]
            
            # 从向量存储删除
            if chunk_ids:
                self.vector_store.delete(ids=chunk_ids)
            
            # 从全文索引删除
            self.fulltext_store.delete_by_chapter(chapter_id)
            
            # 删除分块元数据
            self.metadata_store.delete_chunks_by_chapter(chapter_id)
            
            # 删除章节元数据
            self.metadata_store.delete_chapter(chapter_id)
            
            logger.info(f"章节删除成功: {chapter_id}, 删除{len(chunk_ids)}个分块")
            return True
            
        except Exception as e:
            logger.error(f"删除章节失败: {e}")
            return False
    
    def get_chapter(self, chapter_id: str) -> Optional[ChapterInfo]:
        """
        获取章节信息
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节信息
        """
        return self.metadata_store.get_chapter(chapter_id)
    
    def get_chapter_content(self, chapter_id: str) -> Optional[str]:
        """
        获取章节完整内容
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节内容
        """
        chunks = self.metadata_store.get_chunks_by_chapter(chapter_id)
        if not chunks:
            return None
        
        # 获取所有分块的文档内容
        chunk_ids = [c["chunk_id"] for c in chunks]
        results = self.vector_store.get(ids=chunk_ids)
        
        if not results or not results.get("documents"):
            return None
        
        # 按顺序拼接内容
        documents = dict(zip(results["ids"], results["documents"]))
        content_parts = []
        for chunk_id in chunk_ids:
            if chunk_id in documents:
                content_parts.append(documents[chunk_id])
        
        return "\n".join(content_parts)
    
    def list_chapters(
        self,
        order_by: str = "chapter_number",
        ascending: bool = True,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[ChapterInfo]:
        """
        列出所有章节
        
        Args:
            order_by: 排序字段
            ascending: 是否升序
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            章节列表
        """
        return self.metadata_store.list_chapters(
            order_by=order_by,
            ascending=ascending,
            limit=limit,
            offset=offset
        )
    
    def import_document(
        self,
        content: str,
        auto_detect_chapters: bool = True,
        default_title: str = "未命名文档"
    ) -> list[AddChapterResult]:
        """
        导入文档
        
        自动检测章节结构并添加到知识库
        
        Args:
            content: 文档内容
            auto_detect_chapters: 是否自动检测章节
            default_title: 默认标题（当无法检测章节时使用）
        
        Returns:
            添加结果列表
        """
        results = []
        
        if auto_detect_chapters:
            # 检测章节
            chapters = self.chapter_marker.detect_chapters(content)
            
            if chapters:
                for chapter in chapters:
                    result = self.add_chapter(
                        chapter_id=chapter.chapter_id,
                        title=chapter.title,
                        content=chapter.content,
                        chapter_number=chapter.chapter_number
                    )
                    results.append(result)
                return results
        
        # 无法检测章节，作为单个章节处理
        result = self.add_chapter(
            chapter_id=None,
            title=default_title,
            content=content,
            chapter_number=1
        )
        results.append(result)
        
        return results
    
    def search_nodes(
        self,
        query: str,
        limit: int = 10,
        node_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """搜索知识节点。"""
        query = (query or "").strip()
        if not query:
            return []

        metadata_hits = self._search_metadata_nodes(query, node_type=node_type, limit=limit)
        vector_hits = self._search_vector_nodes(query, limit=limit)
        merged = self._merge_search_hits(metadata_hits, vector_hits, limit=limit)
        return merged

    def get_node_neighbors(self, node_id: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        """获取节点的邻居关系。"""
        node_id = (node_id or "").strip()
        if not node_id:
            return {"incoming": [], "outgoing": []}

        chapter = self.metadata_store.get_chapter(node_id)
        if chapter:
            node = self._chapter_to_node(chapter)
        else:
            node = self.get_node(node_id)
        if not node:
            return {"incoming": [], "outgoing": []}

        outgoing = node.get("links_out", [])[:limit]
        incoming = self._find_incoming_neighbors(node_id, limit=limit)
        return {"incoming": incoming, "outgoing": outgoing}

    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        """按节点 ID 获取知识节点。"""
        node_id = (node_id or "").strip()
        if not node_id:
            return None

        chapter = self.metadata_store.get_chapter(node_id)
        if chapter:
            return self._chapter_to_node(chapter)

        hits = self._search_metadata_nodes(node_id, limit=1)
        return hits[0] if hits else None

    def _search_metadata_nodes(self, query: str, node_type: Optional[str] = None, limit: int = 10) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        query_lower = query.lower()
        for chapter in self.metadata_store.list_chapters(limit=None):
            node = self._chapter_to_node(chapter)
            if node_type and node.get("type") != node_type:
                continue
            haystack = " ".join([
                node.get("id", ""),
                node.get("title", ""),
                node.get("summary", ""),
                " ".join(node.get("links_out", [])),
                " ".join(node.get("tags", [])),
            ]).lower()
            if query_lower in haystack:
                node["score"] = 1.0
                hits.append(node)
        return hits[:limit]

    def _search_vector_nodes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            results = self.vector_store.search(query, limit=limit)
        except Exception:
            return []
        nodes: list[dict[str, Any]] = []
        for item in results or []:
            meta = item.get("metadata") or {}
            nodes.append({
                "id": meta.get("chapter_id") or meta.get("node_id") or item.get("id"),
                "type": meta.get("type") or "chapter_summary",
                "title": meta.get("title") or item.get("id", ""),
                "summary": item.get("document") or "",
                "score": item.get("score", 0.0),
                "links_out": meta.get("links", []),
                "metadata": meta,
            })
        return nodes

    def _merge_search_hits(self, metadata_hits: list[dict[str, Any]], vector_hits: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for hit in vector_hits + metadata_hits:
            hit_id = str(hit.get("id") or "").strip()
            if not hit_id:
                continue
            if hit_id not in merged or hit.get("score", 0.0) > merged[hit_id].get("score", 0.0):
                merged[hit_id] = hit
        return sorted(merged.values(), key=lambda x: x.get("score", 0.0), reverse=True)[:limit]

    def _find_incoming_neighbors(self, node_id: str, limit: int = 20) -> list[dict[str, Any]]:
        incoming: list[dict[str, Any]] = []
        for chapter in self.metadata_store.list_chapters(limit=None):
            node = self._chapter_to_node(chapter)
            if node_id in node.get("links_out", []):
                incoming.append({"id": node["id"], "title": node["title"], "type": node["type"]})
            if len(incoming) >= limit:
                break
        return incoming[:limit]

    def _chapter_to_node(self, chapter: ChapterInfo) -> dict[str, Any]:
        metadata = chapter.metadata or {}
        return {
            "id": chapter.chapter_id,
            "type": "chapter_summary",
            "title": chapter.title,
            "summary": metadata.get("summary_text") or metadata.get("summary") or "",
            "links_out": metadata.get("links", []),
            "links_in": metadata.get("links_in", []),
            "tags": metadata.get("tags", []),
            "metadata": metadata,
        }

    def get_statistics(self) -> dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            统计信息
        """
        metadata_stats = self.metadata_store.get_statistics()
        
        return {
            "chapter_count": metadata_stats["chapter_count"],
            "total_words": metadata_stats["total_words"],
            "total_chunks": metadata_stats["total_chunks"],
            "vector_count": self.vector_store.count(),
            "fulltext_count": self.fulltext_store.count(),
            "embedding_cache_size": self.embedding_service.get_cache_size(),
        }
    
    def clear_all(self) -> bool:
        """
        清空知识库
        
        Returns:
            是否成功
        """
        try:
            self.vector_store.clear()
            self.fulltext_store.clear()
            self.metadata_store.clear()
            self.embedding_service.clear_cache()
            logger.info("知识库已清空")
            return True
        except Exception as e:
            logger.error(f"清空知识库失败: {e}")
            return False
    
    def _count_words(self, text: str) -> int:
        """统计字数"""
        import re
        text = re.sub(r'\s+', '', text)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        non_chinese = len(text) - chinese_chars
        english_words = non_chinese // 5 if non_chinese > 0 else 0
        return chinese_chars + english_words
