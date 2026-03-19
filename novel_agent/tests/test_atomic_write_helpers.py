"""原子写入工具测试。"""

from pathlib import Path

from novel_agent.utils.atomic_write import atomic_write_json, atomic_write_text


def test_atomic_write_text_with_rollback(tmp_path: Path):
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new", old_content="old")

    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_json_roundtrip(tmp_path: Path):
    target = tmp_path / "data.json"

    atomic_write_json(target, {"a": 1, "b": "x"}, ensure_ascii=False, indent=2)

    content = target.read_text(encoding="utf-8")
    assert '"a": 1' in content
    assert '"b": "x"' in content

