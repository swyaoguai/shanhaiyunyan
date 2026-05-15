from pathlib import Path

import pytest

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.story_memory_actions import handle_story_memory_request


class FakeSearchItem:
    document = "第3章里，配角阿洛把青铜扣藏进井沿，暗示后续密道。"
    score = 0.88
    metadata = {"chapter_id": "chapter_3", "chapter_number": 3, "title": "井边夜谈"}


class FakeKnowledgeBase:
    def search(self, **kwargs):
        return type("SearchResponse", (), {"results": [FakeSearchItem()]})()


class FakeRouter:
    knowledge_base = FakeKnowledgeBase()


def _write_project_payload(data_dir: Path, project_id: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "projects.json").write_text(
        (
            '{"projects":{"%s":{"id":"%s","name":"故事","description":"",'
            '"created_at":"2026-01-01T00:00:00","updated_at":"2026-01-01T00:00:00",'
            '"word_count":0,"chapter_count":0}},"current_project_id":"%s"}'
        ) % (project_id, project_id, project_id),
        encoding="utf-8",
    )


@pytest.fixture()
def project_manager(tmp_path):
    project_id = "story001"
    data_dir = tmp_path / "data"
    _write_project_payload(data_dir, project_id)
    manager = ProjectManager(data_dir=data_dir)
    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager
    try:
        yield manager
    finally:
        project_manager_module._project_manager = old_manager


@pytest.mark.asyncio
async def test_story_memory_lookup_returns_candidate_chapter(project_manager):
    result = await handle_story_memory_request(FakeRouter(), "那个配角埋的伏笔我忘了在第几章，帮我找找")

    assert result is not None
    assert result["delegated_result"]["action"] == "foreshadowing_lookup"
    assert "第3章" in result["response"]
    assert "青铜扣" in result["response"]


@pytest.mark.asyncio
async def test_story_memory_backfill_registers_eventline(project_manager):
    result = await handle_story_memory_request(FakeRouter(), "把这个青铜扣伏笔在后续创作里回填")

    assert result is not None
    assert result["delegated_result"]["action"] == "foreshadowing_backfill"
    rows = project_manager.load_project_data("eventlines")
    assert len(rows) == 1
    assert rows[0]["type"] == "foreshadowing_backfill"
    assert rows[0]["source_chapters"] == [3]
