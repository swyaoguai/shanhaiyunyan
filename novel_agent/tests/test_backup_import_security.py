"""备份导入安全测试"""

import io
import json
import tempfile
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import novel_agent.project_manager as project_manager_module
from novel_agent.project_manager import ProjectManager
from novel_agent.web.app import create_app
from novel_agent.web.routes import projects as projects_routes


def _build_zip(payloads: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in payloads.items():
            zf.writestr(path, content)
    return buf.getvalue()


def test_backup_import_rejects_oversized_file(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(projects_routes, "BACKUP_UPLOAD_MAX_BYTES", 1024)
    payload = b"x" * 2048

    response = client.post(
        "/api/projects/backup/import",
        files={"backup_file": ("too-large.zip", payload, "application/zip")},
        data={"overwrite": "false"},
    )

    assert response.status_code == 413
    assert "大小限制" in response.json().get("detail", "")


def test_backup_import_rejects_non_zip_content():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/projects/backup/import",
        files={"backup_file": ("broken.zip", b"not-a-zip", "application/zip")},
        data={"overwrite": "false"},
    )

    assert response.status_code == 400
    assert "ZIP" in response.json().get("detail", "")


def test_backup_import_rejects_zip_slip_payload():
    app = create_app()
    client = TestClient(app)

    zip_payload = _build_zip(
        {
            "manifest.json": "{}",
            "../escape.txt": "evil",
        }
    )

    response = client.post(
        "/api/projects/backup/import",
        files={"backup_file": ("evil.zip", zip_payload, "application/zip")},
        data={"overwrite": "false"},
    )

    assert response.status_code == 400
    assert "非法压缩包路径" in response.json().get("detail", "")


def test_backup_import_rejects_zip_bomb_by_declared_size(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(projects_routes, "BACKUP_EXTRACT_MAX_TOTAL_BYTES", 1024)

    zip_payload = _build_zip(
        {
            "manifest.json": json.dumps({"backup_version": "1.0"}),
            "root_data/huge.txt": "a" * 2048,
        }
    )

    response = client.post(
        "/api/projects/backup/import",
        files={"backup_file": ("zip-bomb.zip", zip_payload, "application/zip")},
        data={"overwrite": "false"},
    )

    assert response.status_code == 413
    assert "解压后文件总大小超过限制" in response.json().get("detail", "")


def test_backup_import_rejects_too_many_files(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(projects_routes, "BACKUP_EXTRACT_MAX_FILES", 2)

    zip_payload = _build_zip(
        {
            "manifest.json": json.dumps({"backup_version": "1.0"}),
            "root_data/a.txt": "a",
            "root_data/b.txt": "b",
        }
    )

    response = client.post(
        "/api/projects/backup/import",
        files={"backup_file": ("many-files.zip", zip_payload, "application/zip")},
        data={"overwrite": "false"},
    )

    assert response.status_code == 413
    assert "文件数量超过限制" in response.json().get("detail", "")


def test_backup_import_refreshes_project_manager_state(monkeypatch):
    app = create_app()
    client = TestClient(app)

    with tempfile.TemporaryDirectory() as tmp:
        app_root = Path(tmp)
        data_dir = app_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        def _projects_payload(project_id: str, name: str) -> dict:
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

        (data_dir / "projects.json").write_text(
            json.dumps(_projects_payload("aaaa1111", "Project A"), ensure_ascii=False),
            encoding="utf-8",
        )

        manager = ProjectManager(data_dir=data_dir)

        old_manager = project_manager_module._project_manager
        project_manager_module._project_manager = manager

        monkeypatch.setattr(
            projects_routes,
            "_get_backup_targets",
            lambda: {
                "app_root": app_root,
                "root_data_dir": data_dir,
                "package_data_dir": app_root / "package_data",
                "env_file": app_root / ".env",
            },
        )

        try:
            backup_zip = _build_zip(
                {
                    "manifest.json": json.dumps({"backup_version": "1.0"}, ensure_ascii=False),
                    "root_data/projects.json": json.dumps(
                        _projects_payload("bbbb2222", "Project B"),
                        ensure_ascii=False,
                    ),
                }
            )

            response = client.post(
                "/api/projects/backup/import",
                files={"backup_file": ("restore.zip", backup_zip, "application/zip")},
                data={"overwrite": "true"},
            )

            assert response.status_code == 200
            assert sorted(manager.projects.keys()) == ["bbbb2222"]
            assert manager.current_project_id == "bbbb2222"
        finally:
            project_manager_module._project_manager = old_manager
