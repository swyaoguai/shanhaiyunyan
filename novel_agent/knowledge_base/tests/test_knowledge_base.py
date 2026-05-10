"""
知识库测试

使用pytest运行: pytest novel_agent/knowledge_base/tests/ -v
"""

import os
import tempfile
import pytest
from pathlib import Path

# 导入被测模块
from ..config import KnowledgeBaseConfig, ChunkingConfig
from ..logic_layer.chunker import TextChunker
from ..logic_layer.chapter_marker import ChapterMarker
from ..logic_layer.embeddings import MockEmbeddingService
from ..data_layer.fulltext_store import FullTextStore
from ..data_layer.metadata_store import MetadataStore
from ..config import SQLiteConfig


class TestTextChunker:
    """文本分块器测试"""
    
    def test_basic_chunking(self):
        """测试基本分块功能"""
        chunker = TextChunker(ChunkingConfig(chunk_size=100, chunk_overlap=10))
        
        text = "这是第一段内容。\n\n这是第二段内容。\n\n这是第三段内容。"
        chunks = chunker.chunk(text)
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.text
            assert chunk.word_count > 0
    
    def test_empty_text(self):
        """测试空文本"""
        chunker = TextChunker()
        
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
    
    def test_long_text_chunking(self):
        """测试长文本分块"""
        chunker = TextChunker(ChunkingConfig(chunk_size=50, chunk_overlap=5))
        
        # 生成长文本
        text = "这是一段测试内容。" * 100
        chunks = chunker.chunk(text)
        
        assert len(chunks) > 1
        # 检查分块大小
        for chunk in chunks[:-1]:  # 最后一块可能较小
            assert len(chunk.text) <= 60  # 允许一定误差
    
    def test_chunk_overlap(self):
        """测试分块重叠"""
        chunker = TextChunker(ChunkingConfig(chunk_size=50, chunk_overlap=10))
        
        text = "A" * 100 + "B" * 100
        chunks = chunker.chunk(text)
        
        # 检查是否有重叠
        if len(chunks) >= 2:
            # 相邻块之间应该有重叠内容
            pass  # 重叠检测逻辑
    
    def test_estimate_chunks(self):
        """测试分块数量估算"""
        chunker = TextChunker(ChunkingConfig(chunk_size=100, chunk_overlap=10))
        
        text = "A" * 500
        estimated = chunker.estimate_chunks(text)
        actual = len(chunker.chunk(text))
        
        # 估算值应该接近实际值
        assert abs(estimated - actual) <= 2


class TestChapterMarker:
    """章节标记器测试"""
    
    def test_detect_chinese_chapters(self):
        """测试中文章节检测"""
        marker = ChapterMarker()
        
        text = """
第一章 开端

这是第一章的内容。主角登场了。

第二章 发展

这是第二章的内容。故事继续发展。

第三章 高潮

这是第三章的内容。情节到达高潮。
"""
        chapters = marker.detect_chapters(text)
        
        assert len(chapters) == 3
        assert chapters[0].title == "开端"
        assert chapters[0].chapter_number == 1
        assert chapters[1].chapter_number == 2
        assert chapters[2].chapter_number == 3
    
    def test_detect_english_chapters(self):
        """测试英文章节检测"""
        marker = ChapterMarker()
        
        text = """
Chapter 1: Introduction

This is chapter one content.

Chapter 2: Development

This is chapter two content.
"""
        chapters = marker.detect_chapters(text)
        
        assert len(chapters) >= 2
    
    def test_parse_chinese_number(self):
        """测试中文数字解析"""
        marker = ChapterMarker()
        
        assert marker._parse_chinese_number("一") == 1
        assert marker._parse_chinese_number("十") == 10
        assert marker._parse_chinese_number("十二") == 12
        assert marker._parse_chinese_number("二十三") == 23
        assert marker._parse_chinese_number("一百") == 100
        assert marker._parse_chinese_number("123") == 123

    def test_detect_chapters_ignores_chapter_prefixed_body_lines(self):
        """正文行以第X章开头时不应被误判为章节标题"""
        marker = ChapterMarker()

        text = """
第1章 标题1
第1章正文里主角继续调查，并发现新的线索。
后续正文继续展开。

第2章 标题2
第2章正文里主角继续调查，并发现新的线索。
后续正文继续展开。
"""
        chapters = marker.detect_chapters(text)

        assert len(chapters) == 2
        assert [chapter.chapter_number for chapter in chapters] == [1, 2]
        assert [chapter.title for chapter in chapters] == ["标题1", "标题2"]
        assert "第1章正文里主角继续调查" in chapters[0].content
    
    def test_no_chapters(self):
        """测试无章节标记的文本"""
        marker = ChapterMarker()
        
        text = "这是一段没有章节标记的普通文本。只是一些内容。"
        chapters = marker.detect_chapters(text)
        
        assert len(chapters) == 0


class TestMockEmbeddingService:
    """模拟向量服务测试"""
    
    def test_embed_single(self):
        """测试单文本向量化"""
        service = MockEmbeddingService(embedding_dim=128)
        
        embedding = service.embed("测试文本")
        
        assert len(embedding) == 128
        # 检查是否归一化
        norm = sum(x ** 2 for x in embedding) ** 0.5
        assert abs(norm - 1.0) < 0.01
    
    def test_embed_batch(self):
        """测试批量向量化"""
        service = MockEmbeddingService(embedding_dim=128)
        
        texts = ["文本1", "文本2", "文本3"]
        embeddings = service.embed_batch(texts)
        
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 128
    
    def test_same_text_same_embedding(self):
        """测试相同文本产生相同向量"""
        service = MockEmbeddingService(embedding_dim=128)
        
        emb1 = service.embed("相同的文本")
        emb2 = service.embed("相同的文本")
        
        assert emb1 == emb2
    
    def test_cache(self):
        """测试缓存功能"""
        service = MockEmbeddingService(embedding_dim=128)
        
        service.embed("文本1")
        service.embed("文本2")
        
        assert service.get_cache_size() == 2
        
        service.clear_cache()
        assert service.get_cache_size() == 0


class TestFullTextStore:
    """全文搜索存储测试"""
    
    @pytest.fixture
    def store(self, tmp_path):
        """创建临时全文存储"""
        db_path = str(tmp_path / "test.db")
        config = SQLiteConfig(db_path=db_path)
        store = FullTextStore(config)
        yield store
        store.close()
    
    def test_add_and_search(self, store):
        """测试添加和搜索"""
        store.add(
            id="doc1",
            document="这是一段关于人工智能的文本",
            chapter_id="ch1"
        )
        store.add(
            id="doc2",
            document="这是一段关于机器学习的文本",
            chapter_id="ch1"
        )
        
        results = store.search("人工智能")
        
        assert len(results) >= 1
        assert results[0].id == "doc1"
    
    def test_batch_add(self, store):
        """测试批量添加"""
        store.add_batch(
            ids=["d1", "d2", "d3"],
            documents=["文档一", "文档二", "文档三"],
            chapter_ids=["ch1", "ch1", "ch2"]
        )
        
        assert store.count() == 3
        assert store.count_by_chapter("ch1") == 2
    
    def test_delete(self, store):
        """测试删除"""
        store.add(id="doc1", document="测试文档", chapter_id="ch1")
        
        assert store.count() == 1
        
        store.delete("doc1")
        
        assert store.count() == 0
    
    def test_chapter_filter(self, store):
        """测试章节过滤"""
        store.add(id="d1", document="内容一", chapter_id="ch1")
        store.add(id="d2", document="内容二", chapter_id="ch2")
        store.add(id="d3", document="内容三", chapter_id="ch1")
        
        results = store.search("内容", chapter_filter=["ch1"])
        
        assert len(results) == 2
        for r in results:
            assert "ch1" in store.get(r.id)["chapter_id"]


class TestMetadataStore:
    """元数据存储测试"""
    
    @pytest.fixture
    def store(self, tmp_path):
        """创建临时元数据存储"""
        db_path = str(tmp_path / "test.db")
        config = SQLiteConfig(db_path=db_path)
        store = MetadataStore(config)
        yield store
        store.close()
    
    def test_add_chapter(self, store):
        """测试添加章节"""
        chapter = store.add_chapter(
            chapter_id="ch1",
            title="第一章",
            chapter_number=1,
            word_count=1000
        )
        
        assert chapter.chapter_id == "ch1"
        assert chapter.title == "第一章"
        assert chapter.chapter_number == 1
    
    def test_update_chapter(self, store):
        """测试更新章节"""
        store.add_chapter(chapter_id="ch1", title="原标题", chapter_number=1)
        
        updated = store.update_chapter(chapter_id="ch1", title="新标题")
        
        assert updated.title == "新标题"
    
    def test_list_chapters(self, store):
        """测试章节列表"""
        store.add_chapter("ch1", "第一章", 1)
        store.add_chapter("ch2", "第二章", 2)
        store.add_chapter("ch3", "第三章", 3)
        
        chapters = store.list_chapters(order_by="chapter_number")
        
        assert len(chapters) == 3
        assert chapters[0].chapter_number == 1
        assert chapters[2].chapter_number == 3
    
    def test_delete_chapter(self, store):
        """测试删除章节"""
        store.add_chapter("ch1", "第一章", 1)
        
        assert store.count_chapters() == 1
        
        store.delete_chapter("ch1")
        
        assert store.count_chapters() == 0
    
    def test_statistics(self, store):
        """测试统计信息"""
        store.add_chapter("ch1", "第一章", 1, word_count=1000)
        store.add_chapter("ch2", "第二章", 2, word_count=2000)
        
        stats = store.get_statistics()
        
        assert stats["chapter_count"] == 2
        assert stats["total_words"] == 3000


class TestKnowledgeBaseIntegration:
    """知识库集成测试"""
    
    @pytest.fixture
    def kb(self, tmp_path):
        """创建临时知识库"""
        from ..knowledge_base import KnowledgeBase
        from ..config import KnowledgeBaseConfig
        
        config = KnowledgeBaseConfig(
            project_id="test",
            data_dir=str(tmp_path)
        )
        
        kb = KnowledgeBase(
            project_id="test",
            config=config,
            use_mock_embeddings=True
        )
        yield kb
        kb.close()
    
    def test_add_and_search_chapter(self, kb):
        """测试添加和搜索章节"""
        # 添加章节
        result = kb.add_chapter(
            chapter_id="ch1",
            title="第一章 开端",
            content="主角张三是一个普通的大学生。有一天，他发现了一本神秘的古书。"
                    "这本书记载了许多奇异的知识，改变了他的人生。",
            chapter_number=1
        )
        
        assert result.success
        assert result.chunk_count > 0
        
        # 搜索
        response = kb.search("张三是谁")
        
        assert response.total > 0
        assert "张三" in response.results[0].document
    
    def test_chapter_navigation(self, kb):
        """测试章节导航"""
        kb.add_chapter("ch1", "第一章", "内容1", 1)
        kb.add_chapter("ch2", "第二章", "内容2", 2)
        kb.add_chapter("ch3", "第三章", "内容3", 3)
        
        # 获取目录
        toc = kb.get_table_of_contents()
        assert len(toc) == 3
        
        # 导航
        next_ch = kb.get_next_chapter("ch1")
        assert next_ch.chapter_id == "ch2"
        
        prev_ch = kb.get_previous_chapter("ch2")
        assert prev_ch.chapter_id == "ch1"
    
    def test_import_document(self, kb):
        """测试文档导入"""
        document = """
第一章 开端

这是第一章的内容。

第二章 发展

这是第二章的内容。
"""
        results = kb.import_document(document, auto_detect_chapters=True)
        
        assert len(results) == 2
        assert all(r.success for r in results)
    
    def test_statistics(self, kb):
        """测试统计信息"""
        kb.add_chapter("ch1", "第一章", "A" * 1000, 1)
        kb.add_chapter("ch2", "第二章", "B" * 2000, 2)
        
        stats = kb.get_statistics()
        
        assert stats["chapter_count"] == 2
        assert stats["vector_count"] > 0
    
    def test_clear(self, kb):
        """测试清空"""
        kb.add_chapter("ch1", "第一章", "内容", 1)
        
        assert kb.get_statistics()["chapter_count"] == 1
        
        kb.clear()
        
        assert kb.get_statistics()["chapter_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
