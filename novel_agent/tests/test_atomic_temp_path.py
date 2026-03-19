"""原子写入临时文件路径生成测试。"""

from pathlib import Path

from novel_agent.utils.atomic_write import build_atomic_temp_path


def test_build_atomic_temp_path_is_unique_for_same_target():
    target = Path("sample.json")

    path1 = build_atomic_temp_path(target)
    path2 = build_atomic_temp_path(target)

    assert path1 != path2
    assert path1.name.startswith("sample.json.tmp.")
    assert path2.name.startswith("sample.json.tmp.")


def test_build_atomic_temp_path_without_suffix():
    target = Path("env")

    temp_path = build_atomic_temp_path(target)

    assert temp_path.name.startswith("env.tmp.")

