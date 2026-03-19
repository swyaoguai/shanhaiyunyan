"""知识库路由回归测试"""

import sqlite3
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

import novel_agent.project_manager as project_manager_module
from novel_agent.constants import get_data_dir
from novel_agent.project_manager import ProjectManager
from novel_agent.web.app import create_app


def test_delete_knowledge_chapter_returns_success_when_only_chapter_row_exists(tmp_path):
    app = create_app()
    client = TestClient(app)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    project_id = "kbproj01"
    (data_dir / "projects.json").write_text(
        json.dumps(
            {
                "projects": {
                    project_id: {
                        "id": project_id,
                        "name": "KB Project",
                        "description": "",
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00",
                        "word_count": 0,
                        "chapter_count": 0,
                    }
                },
                "current_project_id": project_id,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manager = ProjectManager(data_dir=data_dir)

    old_manager = project_manager_module._project_manager
    project_manager_module._project_manager = manager

    try:
        kb_dir = Path(get_data_dir()) / "knowledge_base" / project_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        db_path = kb_dir / "knowledge.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS chapters (chapter_id TEXT PRIMARY KEY, title TEXT, chapter_number INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id TEXT, content TEXT)")
        cursor.execute("DELETE FROM chapters")
        cursor.execute("DELETE FROM chunks")
        cursor.execute(
            "INSERT INTO chapters (chapter_id, title, chapter_number) VALUES (?, ?, ?)",
            ("ch-only", "Only Chapter", 1),
        )
        conn.commit()
        conn.close()

        response = client.delete("/api/knowledge-base/chapter/ch-only")
        payload = response.json()

        assert response.status_code == 200
        assert payload.get("success") is True

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chapters WHERE chapter_id = ?", ("ch-only",))
        remaining = cursor.fetchone()[0]
        conn.close()

        assert remaining == 0
    finally:
        shutil.rmtree(kb_dir, ignore_errors=True)
        project_manager_module._project_manager = old_manager
