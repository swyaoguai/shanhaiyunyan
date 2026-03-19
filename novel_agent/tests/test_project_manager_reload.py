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

