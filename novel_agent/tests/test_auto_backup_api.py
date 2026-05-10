"""自动备份接口测试"""

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novel_agent.web.api import auto_backup


class FakeAutoBackupService:
    def __init__(self):
        self._running = False
        self._config = {
            "enabled": False,
            "schedule": "daily",
            "daily_time": "02:00",
            "weekly_day": 0,
            "weekly_time": "02:00",
            "custom_interval_hours": 24,
            "max_backups": 10,
            "backup_on_exit": True,
            "include_knowledge_base": True,
            "last_backup_time": None,
        }

    def get_config(self):
        return self._config.copy()

    def update_config(self, updates):
        self._config.update(updates)
        self._running = bool(self._config.get("enabled"))
        return self.get_config()

    def _calculate_next_backup_time(self):
        return datetime(2026, 5, 11, 2, 0, 0) if self._config.get("enabled") else None


def _build_client(monkeypatch):
    service = FakeAutoBackupService()
    monkeypatch.setattr(auto_backup, "get_auto_backup_service", lambda: service)

    app = FastAPI()
    app.include_router(auto_backup.router, prefix="/api/v1")
    app.include_router(auto_backup.router, prefix="/api")
    return TestClient(app), service


def test_auto_backup_toggle_route_updates_enabled_status(monkeypatch):
    client, service = _build_client(monkeypatch)

    response = client.post("/api/v1/auto-backup/toggle", json={"enabled": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "自动备份已启用"
    assert payload["data"]["enabled"] is True
    assert service.get_config()["enabled"] is True

    status = client.get("/api/v1/auto-backup/status")
    assert status.status_code == 200
    assert status.json()["data"]["running"] is True
    assert status.json()["data"]["next_backup_time"] == "2026-05-11T02:00:00"


def test_auto_backup_toggle_requires_enabled(monkeypatch):
    client, _service = _build_client(monkeypatch)

    response = client.post("/api/v1/auto-backup/toggle", json={})

    assert response.status_code == 400
    assert response.json()["detail"] == "enabled is required"

