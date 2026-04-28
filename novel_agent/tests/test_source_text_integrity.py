"""源码文本完整性回归测试。"""

from pathlib import Path

from novel_agent.agents.continuous_writer import SUSPICIOUS_MOJIBAKE_FRAGMENTS


def test_python_sources_are_utf8_clean():
    source_root = Path("novel_agent")
    python_files = sorted(source_root.rglob("*.py"))

    assert python_files, "应至少找到一个 Python 源文件"

    for path in python_files:
        content = path.read_text(encoding="utf-8")
        assert "\ufffd" not in content, f"{path} 包含替换字符，可能存在编码损坏"
        assert not any(fragment in content for fragment in SUSPICIOUS_MOJIBAKE_FRAGMENTS), (
            f"{path} 包含疑似乱码片段"
        )
