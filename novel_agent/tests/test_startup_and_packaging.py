import sys
from pathlib import Path


def test_packaged_agent_api_config_persists_next_to_portable_exe(monkeypatch, tmp_path):
    portable_dir = tmp_path / "Portable"
    portable_dir.mkdir()
    exe_path = portable_dir / "app.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))

    from novel_agent.agent_config import AgentConfigManager

    manager = AgentConfigManager()
    cfg = manager.add_api_config(
        name="portable-api",
        api_base="http://127.0.0.1:8000/v1",
        api_key="test-key",
        models=["deepseek-test"],
    )
    assert manager.set_active_config(cfg.id, "deepseek-test") is True

    data_dir = portable_dir / "data"
    assert manager.config_dir == data_dir
    assert (data_dir / "global_api_config.json").exists()
    assert (portable_dir / ".env").exists()
    env_text = (portable_dir / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_BASE=http://127.0.0.1:8000/v1" in env_text
    assert "OPENAI_MODEL=deepseek-test" in env_text


def test_packaged_config_reload_reads_portable_env(monkeypatch, tmp_path):
    portable_dir = tmp_path / "Portable"
    portable_dir.mkdir()
    exe_path = portable_dir / "app.exe"
    exe_path.write_text("", encoding="utf-8")
    (portable_dir / ".env").write_text(
        "\n".join([
            "OPENAI_API_KEY=portable-key",
            "OPENAI_API_BASE=http://127.0.0.1:8000/v1",
            "OPENAI_MODEL=portable-model",
            "HOST=0.0.0.0",
            "PORT=5656",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))

    from novel_agent.config import Config

    assert Config.reload() is True
    assert Config.llm.api_key == "portable-key"
    assert Config.llm.api_base == "http://127.0.0.1:8000/v1"
    assert Config.llm.model == "portable-model"


def test_knowledge_base_settings_accepts_blank_onnx_threads(monkeypatch):
    monkeypatch.setenv("KB_ONNX_THREADS", "")

    from novel_agent.settings import KnowledgeBaseSettings

    settings = KnowledgeBaseSettings(_env_file=None)

    assert settings.onnx_threads is None


def test_frozen_app_root_prefers_portable_exe_directory(monkeypatch, tmp_path):
    portable_dir = tmp_path / "Portable"
    portable_dir.mkdir()
    (portable_dir / "data").mkdir()
    exe_path = portable_dir / "app.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))

    from novel_agent.constants import get_app_root
    from novel_agent.settings import PathsSettings

    assert get_app_root() == portable_dir
    assert PathsSettings._get_app_root() == portable_dir


def test_frozen_app_root_does_not_fallback_to_parent_development_data(monkeypatch, tmp_path):
    repo_like_parent = tmp_path / "repo"
    dist_dir = repo_like_parent / "dist"
    dist_dir.mkdir(parents=True)
    (repo_like_parent / "data").mkdir()
    exe_path = dist_dir / "app.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))

    from novel_agent.constants import get_app_root

    assert get_app_root() == dist_dir


def test_packaged_skills_dir_prefers_external_portable_copy_then_bundled(monkeypatch, tmp_path):
    portable_dir = tmp_path / "Portable"
    bundled_dir = tmp_path / "bundle"
    external_skills = portable_dir / "skills"
    bundled_skills = bundled_dir / "skills"
    external_skills.mkdir(parents=True)
    bundled_skills.mkdir(parents=True)
    exe_path = portable_dir / "app.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled_dir), raising=False)

    from novel_agent.constants import get_skills_dir

    assert get_skills_dir() == external_skills
    external_skills.rmdir()
    assert get_skills_dir() == bundled_skills


def test_portable_build_uses_sanitized_staging_data_without_release_cleaner():
    content = Path("build_portable.py").read_text(encoding="utf-8")

    assert "clean_for_release.py" not in content
    assert '("清理个人数据", clean_before_build)' not in content
    assert '("准备发布数据", prepare_release_data)' in content
    assert "data_dir = RELEASE_DATA_DIR" in content
    assert "exe_src.unlink()" in content
    assert "SOURCE_ONNX_MODEL_DIR" in content
    assert 'PORTABLE_DIR / "novel_agent" / "models" / "embedding" / "default"' in content
    assert '"--specpath", str(BUILD_DIR)' in content
    assert "--add-data\", f\"{data_dir};novel_agent/data\"" in content
    assert "SOURCE_SKILLS_DIR" in content
    assert "--add-data\", f\"{skills_dir};skills\"" in content
    assert '"skills_config.json"' in content
    assert '"trends_search": True' in content


def test_knowledge_local_onnx_paths_use_app_root(monkeypatch, tmp_path):
    from novel_agent.web.routes import knowledge

    monkeypatch.setattr(knowledge, "get_app_root", lambda: tmp_path)

    expected = tmp_path / "novel_agent" / "models" / "embedding" / "default"

    assert knowledge._repo_default_onnx_model_dir() == expected
    assert knowledge._resolve_onnx_model_dir("novel_agent/models/embedding/default") == expected


def test_packaged_runtime_window_close_schedules_shutdown(monkeypatch):
    from novel_agent.web.routes import runtime

    runtime._reset_browser_window_state_for_tests()
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    scheduled = []
    monkeypatch.setattr(
        runtime,
        "_schedule_shutdown_check",
        lambda delay, reason: scheduled.append((delay, reason)) or True,
    )

    heartbeat = runtime.record_browser_window_heartbeat("window-a")
    scheduled.clear()
    closed = runtime.record_browser_window_closed("window-a")

    assert heartbeat["enabled"] is True
    assert closed["active_windows"] == 0
    assert closed["scheduled_shutdown"] is True
    assert scheduled == [(runtime.BROWSER_CLOSE_GRACE_SECONDS, "browser_window_closed")]

    runtime._reset_browser_window_state_for_tests()


def test_packaged_runtime_keeps_process_when_another_window_is_active(monkeypatch):
    from novel_agent.web.routes import runtime

    runtime._reset_browser_window_state_for_tests()
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    scheduled = []
    monkeypatch.setattr(
        runtime,
        "_schedule_shutdown_check",
        lambda delay, reason: scheduled.append((delay, reason)) or True,
    )

    runtime.record_browser_window_heartbeat("window-a")
    runtime.record_browser_window_heartbeat("window-b")
    scheduled.clear()
    closed = runtime.record_browser_window_closed("window-a")

    assert closed["active_windows"] == 1
    assert closed["scheduled_shutdown"] is False
    assert scheduled == []

    runtime._reset_browser_window_state_for_tests()


def test_runtime_window_close_shutdown_is_disabled_in_dev(monkeypatch):
    from novel_agent.web.routes import runtime

    runtime._reset_browser_window_state_for_tests()
    monkeypatch.delenv("SHANHAI_ENABLE_BROWSER_CLOSE_SHUTDOWN", raising=False)
    monkeypatch.delenv("SHANHAI_DISABLE_BROWSER_CLOSE_SHUTDOWN", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert runtime.record_browser_window_heartbeat("window-a") == {
        "enabled": False,
        "active_windows": 0,
        "scheduled_shutdown": False,
    }

    runtime._reset_browser_window_state_for_tests()
