"""Tests for LibraryService, LibraryEntry, and library_mappers."""

import json
import threading
from pathlib import Path

import pytest

from novel_agent.library_types import (
    CURRENT_LIBRARY_VERSION,
    CategoryMeta,
    EntryType,
    KnowledgeNode,
    LibraryEntry,
    LibraryPayload,
    SourceType,
    generate_entry_id,
    BUILTIN_CATEGORIES,
)
from novel_agent.library_mappers import (
    outline_to_entries,
    characters_to_entries,
    worldbuilding_to_entries,
    items_to_entries,
    eventlines_to_entries,
    detail_settings_to_entries,
    chapter_settings_to_entries,
    outline_settings_to_entries,
    chapter_summaries_to_entries,
    entries_to_outline,
    entries_to_characters,
    entries_to_worldbuilding,
    entries_to_items,
    entries_to_chapter_summaries,
)
from novel_agent.library_service import LibraryService


# ---------------------------------------------------------------------------
#  Types
# ---------------------------------------------------------------------------

class TestLibraryTypes:

    def test_entry_from_dict_roundtrip(self):
        entry = LibraryEntry(
            id="character_0",
            entry_type="character",
            title="林渡",
            summary="宗门遗孤",
            content_structured={"name": "林渡", "role": "主角"},
        )
        d = entry.to_dict()
        restored = LibraryEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.title == entry.title
        assert restored.content_structured == entry.content_structured
        assert restored.category_key == "character"

    def test_entry_auto_category_key(self):
        entry = LibraryEntry(id="x", entry_type="outline", title="t")
        assert entry.category_key == "outline"

    def test_knowledge_node_from_entry(self):
        entry = LibraryEntry(id="n_1", entry_type="chapter_summary", title="第1章摘要", summary="摘要")
        node = KnowledgeNode.from_entry(entry, links_out=["[[林渡]]"], vector_text="第1章 摘要")
        assert node.id == entry.id
        assert node.links_out == ["[[林渡]]"]
        assert node.vector_text == "第1章 摘要"

    def test_payload_roundtrip(self):
        payload = LibraryPayload.empty()
        payload.entries.append(
            LibraryEntry(id="test_0", entry_type="character", title="A")
        )
        d = payload.to_dict()
        restored = LibraryPayload.from_dict(d)
        assert restored.version == CURRENT_LIBRARY_VERSION
        assert len(restored.entries) == 1
        assert restored.entries[0].title == "A"
        assert len(restored.categories_meta) == len(BUILTIN_CATEGORIES)

    def test_generate_entry_id_with_index(self):
        eid = generate_entry_id("character", 5)
        assert eid == "character_5"

    def test_generate_entry_id_random(self):
        eid = generate_entry_id("character")
        assert eid.startswith("character_")
        assert len(eid) == len("character_") + 8


# ---------------------------------------------------------------------------
#  Mappers: legacy → entries
# ---------------------------------------------------------------------------

class TestMappers:

    def test_outline_to_entries(self):
        data = [
            {"chapter_number": 1, "title": "开篇", "summary": "故事开始"},
            {"chapter_number": 2, "title": "转折", "summary": "剧情转向"},
        ]
        entries = outline_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "outline"
        assert len(entries[0].content_structured["chapters"]) == 2

    def test_outline_to_entries_dict_format(self):
        data = {"chapters": [{"chapter_number": 1, "title": "A"}]}
        entries = outline_to_entries(data)
        assert len(entries) == 1

    def test_characters_to_entries(self):
        data = [
            {"name": "林渡", "role": "主角", "description": "少年剑修"},
            {"name": "苏晚", "role": "女主", "description": "宗门弟子"},
        ]
        entries = characters_to_entries(data)
        assert len(entries) == 2
        assert entries[0].title == "林渡"
        assert entries[1].entry_type == "character"

    def test_worldbuilding_to_entries(self):
        data = {"world": {"name": "玄天大陆"}, "locations": []}
        entries = worldbuilding_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "world"
        assert entries[0].content_structured["world"]["name"] == "玄天大陆"

    def test_items_to_entries(self):
        data = [{"name": "断魂剑", "description": "上古神兵"}]
        entries = items_to_entries(data)
        assert len(entries) == 1
        assert entries[0].title == "断魂剑"

    def test_eventlines_to_entries(self):
        data = [{"name": "复仇线", "conflict": "恩怨情仇"}]
        entries = eventlines_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "eventline"

    def test_detail_settings_to_entries(self):
        data = [{"name": "第一卷细纲", "scene_goal": "建立冲突"}]
        entries = detail_settings_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "detail_outline"

    def test_chapter_settings_to_entries(self):
        data = [{"name": "第一章纲", "chapter_goal": "引入主角"}]
        entries = chapter_settings_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "chapter_setting"

    def test_outline_settings_to_custom(self):
        data = [{"name": "大纲设定1", "goal": "目标"}]
        entries = outline_settings_to_entries(data)
        assert len(entries) == 1
        assert entries[0].entry_type == "custom"
        assert entries[0].category_key == "outline_settings_legacy"

    def test_empty_data_returns_empty(self):
        assert outline_to_entries([]) == []
        assert characters_to_entries([]) == []
        assert worldbuilding_to_entries(None) == []

    def test_chapter_summaries_to_entries(self):
        data = [
            {"chapter_number": 1, "summary_text": "Main character appears", "key_events": ["battle", "meeting"], "appearing_characters": ["Char1"], "ending_hook": "cliffhanger"},
            {"chapter_number": 3, "summary_text": "Conflict escalates"},
        ]
        entries = chapter_summaries_to_entries(data)
        assert len(entries) == 2
        assert entries[0].entry_type == "chapter_summary"
        assert entries[0].title == "Main character appears"
        assert entries[0].content_structured["summary_text"] == "Main character appears"
        assert entries[1].entry_type == "chapter_summary"
        assert entries[1].id.startswith("chapter_summary_")

    def test_chapter_summaries_empty(self):
        assert chapter_summaries_to_entries([]) == []
        assert chapter_summaries_to_entries(None) == []

    def test_entries_to_chapter_summaries(self):
        from novel_agent.library_types import LibraryEntry, EntryType, SourceType, _now_iso
        entries = [
            LibraryEntry(
                id="chapter_summary_1", entry_type=EntryType.CHAPTER_SUMMARY.value,
                title="Chapter 1 summary",
                content_structured={"chapter_number": 1, "summary_text": "test", "key_events": [], "appearing_characters": [], "ending_hook": ""},
            )
        ]
        result = entries_to_chapter_summaries(entries)
        assert len(result) == 1
        assert result[0]["chapter_number"] == 1


# ---------------------------------------------------------------------------
#  Mappers: entries → legacy
# ---------------------------------------------------------------------------

class TestProjectors:

    def test_entries_to_outline(self):
        chapters = [{"chapter_number": 1, "title": "A"}]
        entry = LibraryEntry(
            id="outline_0", entry_type="outline", title="大纲",
            content_structured={"chapters": chapters},
        )
        result = entries_to_outline([entry])
        assert result == chapters

    def test_entries_to_characters(self):
        entries = [
            LibraryEntry(id="c_0", entry_type="character", title="X",
                         content_structured={"name": "X", "role": "主"}),
            LibraryEntry(id="c_1", entry_type="character", title="Y",
                         content_structured={"name": "Y"}),
        ]
        result = entries_to_characters(entries)
        assert len(result) == 2
        assert result[0]["name"] == "X"

    def test_entries_to_worldbuilding(self):
        entry = LibraryEntry(
            id="w_0", entry_type="world", title="世界",
            content_structured={"world": {"name": "大陆"}},
        )
        result = entries_to_worldbuilding([entry])
        assert result["world"]["name"] == "大陆"

    def test_entries_to_items(self):
        entry = LibraryEntry(
            id="i_0", entry_type="item", title="剑",
            content_structured={"name": "剑", "description": "利器"},
        )
        result = entries_to_items([entry])
        assert len(result) == 1


# ---------------------------------------------------------------------------
#  LibraryService
# ---------------------------------------------------------------------------

class TestLibraryService:

    @pytest.fixture
    def project_dir(self, tmp_path):
        d = tmp_path / "test_project"
        d.mkdir()
        return d

    @pytest.fixture
    def svc(self, project_dir):
        return LibraryService(project_dir)

    def test_load_creates_empty_library(self, svc, project_dir):
        payload = svc.load()
        assert payload.version == CURRENT_LIBRARY_VERSION
        assert (project_dir / "library.json").exists()

    def test_bootstrap_from_legacy(self, svc, project_dir):
        outline_data = [{"chapter_number": 1, "title": "Ch1", "summary": "..."}]
        (project_dir / "outline.json").write_text(
            json.dumps(outline_data, ensure_ascii=False), encoding="utf-8"
        )
        chars = [{"name": "A", "role": "主角"}]
        (project_dir / "characters.json").write_text(
            json.dumps(chars, ensure_ascii=False), encoding="utf-8"
        )
        world = {"world": {"name": "玄天大陆"}}
        (project_dir / "worldbuilding.json").write_text(
            json.dumps(world, ensure_ascii=False), encoding="utf-8"
        )

        payload = svc.load()
        assert len(payload.entries) >= 3
        types = {e.entry_type for e in payload.entries}
        assert "outline" in types
        assert "character" in types
        assert "world" in types

        assert (project_dir / ".library_backup" / "outline.json").exists()

    def test_bootstrap_idempotent(self, svc, project_dir):
        (project_dir / "outline.json").write_text("[]", encoding="utf-8")
        svc.load()
        first_entries = len(svc.load().entries)
        svc2 = LibraryService(project_dir)
        second_entries = len(svc2.load().entries)
        assert first_entries == second_entries

    def test_upsert_and_get_entry(self, svc):
        svc.load()
        entry = LibraryEntry(
            id="test_1", entry_type="character", title="TestChar",
            content_structured={"name": "TestChar"},
        )
        svc.upsert_entry(entry)
        fetched = svc.get_entry("test_1")
        assert fetched is not None
        assert fetched.title == "TestChar"

    def test_chapter_summary_node_gets_obsidian_links(self, svc):
        svc.load()
        entry = KnowledgeNode(
            id="chapter_summary_1",
            entry_type=EntryType.CHAPTER_SUMMARY.value,
            title="第1章摘要",
            summary="林渡遇到苏晚，提到[[宗门大比]]。",
            content_structured={
                "chapter_number": 1,
                "summary_text": "林渡遇到苏晚，提到[[宗门大比]]。",
                "vector_text": "第1章摘要 林渡遇到苏晚",
            },
            relations=["[[林渡]]", "[[苏晚]]"],
            vector_text="第1章摘要 林渡遇到苏晚",
        )
        saved = svc.upsert_entry(entry)
        fetched = svc.get_entry("chapter_summary_1")
        assert fetched is not None
        assert fetched.links_out == ["[[林渡]]", "[[苏晚]]", "[[宗门大比]]"]
        assert saved.links_out == fetched.links_out

    def test_upsert_knowledge_node_normalizes_entry(self, svc):
        svc.load()
        entry = KnowledgeNode(
            id="chapter_summary_1",
            entry_type="chapter_summary",
            title="第1章摘要",
            summary="林渡回城",
            links_out=["[[林渡]]"],
            vector_text="第1章 林渡回城",
        )
        saved = svc.upsert_entry(entry)
        fetched = svc.get_entry("chapter_summary_1")
        assert isinstance(saved, KnowledgeNode)
        assert isinstance(fetched, KnowledgeNode)
        assert fetched.links_out == ["[[林渡]]"]
        assert fetched.vector_text == "第1章 林渡回城"

    def test_upsert_updates_existing(self, svc):
        svc.load()
        entry = LibraryEntry(id="u_1", entry_type="character", title="V1")
        svc.upsert_entry(entry)
        entry.title = "V2"
        svc.upsert_entry(entry)
        assert svc.get_entry("u_1").title == "V2"
        assert len(svc.list_entries(entry_type="character")) == 1

    def test_upsert_entries_normalizes_knowledge_nodes(self, svc):
        svc.load()
        entries = [
            KnowledgeNode(
                id="chapter_summary_2",
                entry_type=EntryType.CHAPTER_SUMMARY.value,
                title="第2章摘要",
                summary="和[[林渡]]有关。",
                content_structured={"chapter_number": 2, "summary_text": "和[[林渡]]有关。"},
            )
        ]
        saved = svc.upsert_entries(entries)
        assert len(saved) == 1
        assert isinstance(saved[0], KnowledgeNode)
        assert svc.get_entry("chapter_summary_2").links_out == ["[[林渡]]"]

    def test_delete_entry(self, svc):
        svc.load()
        entry = LibraryEntry(id="d_1", entry_type="item", title="Sword")
        svc.upsert_entry(entry)
        assert svc.delete_entry("d_1") is True
        assert svc.get_entry("d_1") is None

    def test_delete_nonexistent(self, svc):
        svc.load()
        assert svc.delete_entry("nope") is False

    def test_list_entries_by_type(self, svc):
        svc.load()
        svc.upsert_entries([
            LibraryEntry(id="c_0", entry_type="character", title="A"),
            LibraryEntry(id="c_1", entry_type="character", title="B"),
            LibraryEntry(id="i_0", entry_type="item", title="Sword"),
        ])
        chars = svc.list_entries(entry_type="character")
        assert len(chars) == 2
        items = svc.list_entries(entry_type="item")
        assert len(items) == 1

    def test_list_entries_by_category(self, svc):
        svc.load()
        svc.upsert_entries([
            LibraryEntry(id="x_0", entry_type="custom", title="A", category_key="magic"),
            LibraryEntry(id="x_1", entry_type="custom", title="B", category_key="magic"),
            LibraryEntry(id="x_2", entry_type="custom", title="C", category_key="other"),
        ])
        magic = svc.list_entries(category_key="magic")
        assert len(magic) == 2

    def test_upsert_from_legacy(self, svc):
        svc.load()
        data = [{"name": "A", "role": "主"}, {"name": "B"}]
        entries = svc.upsert_from_legacy("characters", data)
        assert len(entries) == 2
        assert svc.list_entries(entry_type="character") == entries

    def test_upsert_from_legacy_worldbuilding_returns_knowledge_node(self, svc):
        svc.load()
        data = {"world": {"name": "玄天大陆"}, "locations": []}
        entries = svc.upsert_from_legacy("worldbuilding", data)
        assert len(entries) == 1
        assert isinstance(entries[0], KnowledgeNode)
        assert entries[0].title == "世界设定"
        assert entries[0].entry_type == "world"

    def test_chapter_summary_entries_roundtrip_as_knowledge_nodes(self, svc):
        svc.load()
        entry = LibraryEntry(
            id="chapter_summary_3",
            entry_type=EntryType.CHAPTER_SUMMARY.value,
            title="第3章摘要",
            summary="和[[林渡]]、[[苏晚]]有关。",
            content_structured={
                "chapter_number": 3,
                "summary_text": "和[[林渡]]、[[苏晚]]有关。",
                "vector_text": "第3章摘要 和林渡苏晚有关。",
            },
            relations=["[[林渡]]", "[[苏晚]]"],
        )
        saved = svc.upsert_entry(entry)
        fetched = svc.get_entry("chapter_summary_3")
        assert isinstance(saved, KnowledgeNode)
        assert isinstance(fetched, KnowledgeNode)
        assert fetched.links_out == ["[[林渡]]", "[[苏晚]]"]
        assert fetched.vector_text == "第3章摘要 和[[林渡]]、[[苏晚]]有关。" or fetched.vector_text == "第3章摘要 和林渡苏晚有关。"

    def test_project_legacy_view(self, svc):
        svc.load()
        outline = [{"chapter_number": 1, "title": "Ch1"}]
        svc.upsert_from_legacy("outline", outline)
        view = svc.project_legacy_view("outline")
        assert isinstance(view, list)
        assert len(view) == 1
        assert view[0]["title"] == "Ch1"

    def test_upsert_category(self, svc):
        svc.load()
        cat = CategoryMeta(key="magic_system", name="魔法体系", builtin=False)
        svc.upsert_category(cat)
        cats = svc.list_categories()
        keys = {c.key for c in cats}
        assert "magic_system" in keys

    def test_concurrent_writes(self, svc):
        svc.load()
        errors = []

        def writer(n):
            try:
                for i in range(5):
                    svc.upsert_entry(
                        LibraryEntry(id=f"t{n}_{i}", entry_type="character", title=f"C{n}_{i}")
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        all_entries = svc.list_entries(entry_type="character")
        assert len(all_entries) == 15

    def test_file_fingerprint_cache(self, svc, project_dir):
        svc.load()
        svc.upsert_entry(LibraryEntry(id="fp_0", entry_type="item", title="X"))
        svc2 = LibraryService(project_dir)
        payload = svc2.load()
        assert svc2.get_entry("fp_0") is not None
