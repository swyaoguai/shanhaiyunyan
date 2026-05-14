from pathlib import Path

from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.web.routes import diagnostics


def test_support_log_text_reads_and_sanitizes_logs(tmp_path):
    log_file = tmp_path / "agent.log"
    log_file.write_text("normal line\napi_key=sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")

    text = diagnostics.build_support_log_text([log_file])

    assert "山海·云烟 支持日志" in text
    assert "swjiarui@126.com" in text
    assert "normal line" in text
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "***API_KEY***" in text


def test_diagnostics_log_export_endpoint(monkeypatch, tmp_path):
    log_file = tmp_path / "agent.log"
    log_file.write_text("hello log", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "_candidate_log_files", lambda: [log_file])

    client = TestClient(create_app())
    info = client.get("/api/diagnostics/support-info")
    logs = client.get("/api/diagnostics/logs")
    export = client.get("/api/diagnostics/logs/export")

    assert info.status_code == 200
    assert info.json()["support_email"] == "swjiarui@126.com"
    assert info.json()["log_count"] == 1
    assert logs.status_code == 200
    assert "hello log" in logs.text
    assert export.status_code == 200
    assert export.headers["content-disposition"].endswith('.txt"')
    assert "hello log" in export.text
