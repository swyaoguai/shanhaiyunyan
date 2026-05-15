from types import SimpleNamespace

from novel_agent.chapter_knowledge_sync import (
    ChapterKnowledgeSyncService,
    chapter_content_hash,
    upsert_knowledge_base_chapter,
)


class FakeKnowledgeBase:
    def __init__(self):
        self.chapters = {}
        self.add_calls = []
        self.update_calls = []
        self.delete_calls = []

    def get_chapter(self, chapter_id):
        item = self.chapters.get(chapter_id)
        if not item:
            return None
        return SimpleNamespace(**item)

    def add_chapter(self, **kwargs):
        self.add_calls.append(kwargs)
        self.chapters[kwargs["chapter_id"]] = {
            "chapter_id": kwargs["chapter_id"],
            "title": kwargs["title"],
            "chapter_number": kwargs["chapter_number"],
            "metadata": kwargs.get("metadata") or {},
        }
        return SimpleNamespace(success=True, chunk_count=2)

    def update_chapter(self, **kwargs):
        self.update_calls.append(kwargs)
        current = self.chapters.setdefault(kwargs["chapter_id"], {"chapter_id": kwargs["chapter_id"]})
        current["title"] = kwargs.get("title", current.get("title", ""))
        current["chapter_number"] = kwargs.get("chapter_number", current.get("chapter_number"))
        current["metadata"] = kwargs.get("metadata") or current.get("metadata") or {}
        return SimpleNamespace(success=True, chunk_count=3)

    def delete_chapter(self, chapter_id):
        self.delete_calls.append(chapter_id)
        return self.chapters.pop(chapter_id, None) is not None

    def list_chapters(self, limit=None):
        return [SimpleNamespace(**item) for item in self.chapters.values()]

    def close(self):
        pass


class FakeProjectManager:
    current_project_id = "proj001"

    def __init__(self, chapters=None, config=None):
        self._chapters = chapters or []
        self._config = config or {}

    def load_project_state(self, key, default=None):
        return self._config or default

    def load_project_data(self, data_type):
        return self._chapters if data_type == "chapters" else []


def test_upsert_chapter_skips_when_content_hash_matches():
    kb = FakeKnowledgeBase()
    content_hash = chapter_content_hash("已有正文")
    kb.chapters["chapter_1"] = {
        "chapter_id": "chapter_1",
        "title": "第一章",
        "chapter_number": 1,
        "metadata": {"content_hash": content_hash},
    }

    result = upsert_knowledge_base_chapter(
        kb,
        chapter_id="chapter_1",
        title="第一章",
        content="已有正文",
        chapter_number=1,
    )

    assert result["status"] == "skipped_unchanged"
    assert kb.add_calls == []
    assert kb.update_calls == []


def test_upsert_chapter_updates_existing_when_content_changes():
    kb = FakeKnowledgeBase()
    kb.chapters["chapter_1"] = {
        "chapter_id": "chapter_1",
        "title": "第一章",
        "chapter_number": 1,
        "metadata": {"content_hash": chapter_content_hash("旧正文")},
    }

    result = upsert_knowledge_base_chapter(
        kb,
        chapter_id="chapter_1",
        title="第一章",
        content="新正文",
        chapter_number=1,
    )

    assert result["status"] == "updated"
    assert kb.update_calls
    assert kb.update_calls[0]["metadata"]["content_hash"] == chapter_content_hash("新正文")


def test_sync_chapters_deletes_removed_project_chapters():
    kb = FakeKnowledgeBase()
    kb.chapters["chapter_1"] = {
        "chapter_id": "chapter_1",
        "title": "第一章",
        "chapter_number": 1,
        "metadata": {"source": "project_chapters", "content_hash": chapter_content_hash("第一章正文")},
    }
    kb.chapters["chapter_2"] = {
        "chapter_id": "chapter_2",
        "title": "第二章",
        "chapter_number": 2,
        "metadata": {"source": "project_chapters", "content_hash": chapter_content_hash("第二章正文")},
    }
    pm = FakeProjectManager(chapters=[{"chapter_number": 1, "title": "第一章", "content": "第一章正文"}])

    result = ChapterKnowledgeSyncService(pm, knowledge_base_factory=lambda project_id: kb).sync_chapters()

    assert result["success"] is True
    assert result["deleted"] == 1
    assert "chapter_2" in kb.delete_calls


def test_sync_chapters_respects_edit_sync_toggle():
    kb = FakeKnowledgeBase()
    pm = FakeProjectManager(
        chapters=[{"chapter_number": 1, "title": "第一章", "content": "正文"}],
        config={"auto_vector_sync_enabled": True, "sync_on_edit_enabled": False},
    )

    result = ChapterKnowledgeSyncService(pm, knowledge_base_factory=lambda project_id: kb).sync_chapters(trigger="edit")

    assert result["status"] == "disabled_edit_sync"
    assert kb.add_calls == []
