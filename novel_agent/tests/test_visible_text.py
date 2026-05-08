from novel_agent.agents.visible_text import (
    stream_visible_text,
    strip_visible_technical_markers,
)


def test_strip_visible_technical_markers_extracts_reply_from_wrapped_json():
    raw = '子助手返回：{"status":"ok","reply":"后续 Worldbuilder 会整理设定\\n\\n- 第一项"}'

    result = strip_visible_technical_markers(
        raw,
        lambda text: text.replace("Worldbuilder", "世界观构建师"),
    )

    assert result == "后续 世界观构建师 会整理设定\n\n- 第一项"
    assert "status" not in result


def test_strip_visible_technical_markers_accepts_content_payloads():
    raw = '```json\n{"type":"chunk","content":"第一行\\n第二行"}\n```'

    assert strip_visible_technical_markers(raw) == "第一行\n第二行"


def test_stream_visible_text_holds_partial_json_until_visible_text_exists():
    assert stream_visible_text('{"reply": "还没闭合') is None
    assert stream_visible_text('{"reply": "可以显示了"}') == "可以显示了"


def test_stream_visible_text_keeps_plain_markdown_streaming():
    assert stream_visible_text("## 标题\n- 条目") == "## 标题\n- 条目"


def test_strip_visible_technical_markers_does_not_leak_metadata_only_json():
    raw = '助手返回：{"status":"completed","task_graph":[{"title":"世界观"}]}'

    assert strip_visible_technical_markers(raw) == ""
