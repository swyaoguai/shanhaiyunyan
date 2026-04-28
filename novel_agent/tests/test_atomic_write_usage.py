"""关键写盘点应使用唯一临时文件路径。"""

from pathlib import Path


def test_settings_route_uses_atomic_temp_builder():
    content = Path("novel_agent/web/routes/settings.py").read_text(encoding="utf-8")

    assert "atomic_write_text" in content
    assert "env_path.with_suffix('.tmp')" not in content


def test_knowledge_route_uses_atomic_temp_builder():
    content = Path("novel_agent/web/routes/knowledge.py").read_text(encoding="utf-8")

    assert "atomic_write_text" in content
    assert "with_suffix(f\"{path.suffix}.tmp\")" not in content


def test_aux_memory_uses_atomic_temp_builder():
    content = Path("novel_agent/aux_memory.py").read_text(encoding="utf-8")

    assert "atomic_write_json" in content
    assert "with_suffix(f\"{path.suffix}.tmp\")" not in content


def test_session_store_uses_atomic_write_json():
    content = Path("novel_agent/agents/session_store.py").read_text(encoding="utf-8")

    assert "atomic_write_json" in content
    assert "temp_path.replace(path)" not in content
