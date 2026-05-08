"""ProjectManager 重载行为回归测试"""

import json

from novel_agent.project_manager import ProjectManager


def _build_projects_payload(project_id: str, name: str) -> dict:
    return {
        "projects": {
            project_id: {
                "id": project_id,
                "name": name,
                "description": "",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "word_count": 0,
                "chapter_count": 0,
            }
        },
        "current_project_id": project_id,
    }


def test_load_projects_replaces_memory_state(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    meta_file = data_dir / "projects.json"
    meta_file.write_text(
        json.dumps(_build_projects_payload("aaaa1111", "Project A")),
        encoding="utf-8",
    )

    manager = ProjectManager(data_dir=data_dir)
    assert sorted(manager.projects.keys()) == ["aaaa1111"]

    meta_file.write_text(
        json.dumps(_build_projects_payload("bbbb2222", "Project B")),
        encoding="utf-8",
    )
    manager._load_projects()

    assert sorted(manager.projects.keys()) == ["bbbb2222"]
    assert manager.current_project_id == "bbbb2222"


def test_create_project_persists_custom_novel_type(tmp_path):
    manager = ProjectManager(data_dir=tmp_path / "data")

    project = manager.create_project(
        "自定义分类项目",
        "分类应保存为可引用字段",
        novel_type="修仙副本爽文",
    )

    reloaded = ProjectManager(data_dir=tmp_path / "data")

    assert reloaded.projects[project.id].novel_type == "修仙副本爽文"
    assert reloaded.list_projects()[0]["novel_type"] == "修仙副本爽文"


def test_chapters_are_stored_independently_from_outline(tmp_path):
    manager = ProjectManager(data_dir=tmp_path / "data")
    manager.save_project_data("outline", [{"title": "会被清空的大纲", "summary": "只影响大纲"}])
    manager.save_project_data(
        "chapters",
        [{"chapter_number": 1, "title": "正文第一章", "content": "真正的正文"}],
    )

    manager.save_project_data("outline", [])

    chapters = manager.load_project_data("chapters")
    assert len(chapters) == 1
    assert chapters[0]["title"] == "正文第一章"
    assert chapters[0]["content"] == "真正的正文"


def test_chapters_fallback_loads_legacy_markdown_files(tmp_path):
    manager = ProjectManager(data_dir=tmp_path / "data")
    project_dir = manager.get_current_project_dir()
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "chapters.json").unlink(missing_ok=True)
    (chapters_dir / "第2章-1200字.md").write_text("旧章节正文", encoding="utf-8")

    chapters = manager.load_project_data("chapters")
    assert chapters[0]["chapter_number"] == 2
    assert chapters[0]["title"] == "第2章"
    assert chapters[0]["content"] == "旧章节正文"


def test_get_chapters_dir_returns_markdown_directory_not_chapters_json(tmp_path):
    manager = ProjectManager(data_dir=tmp_path / "data")
    chapters_dir = manager.get_chapters_dir()

    assert chapters_dir.name == "chapters"
    assert chapters_dir.is_dir()
    assert chapters_dir != manager.get_project_data_path("chapters")
    assert manager.get_project_data_path("chapters").name == "chapters.json"
