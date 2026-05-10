"""Regression tests for shared novel import parsing."""

import io
import zipfile

import pytest

from novel_agent.novel_import_service import NovelImportService


def _build_docx_bytes(lines: list[str]) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>"
        for line in lines
    )
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body>"
        "</w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "raw_bytes"),
    [
        (
            "sample.txt",
            "第123章 雨夜\n林风在雨夜遇见旧友，决定连夜进城。\n第124章 异象\n城门口突然出现异光。".encode("utf-8"),
        ),
        (
            "sample.md",
            "# 第123章 雨夜\n林风在雨夜遇见旧友，决定连夜进城。\n# 第124章 异象\n城门口突然出现异光。".encode("utf-8"),
        ),
        (
            "sample.docx",
            _build_docx_bytes(
                [
                    "第123章 雨夜",
                    "林风在雨夜遇见旧友，决定连夜进城。",
                    "第124章 异象",
                    "城门口突然出现异光。",
                ]
            ),
        ),
    ],
)
def test_parse_novel_file_preserves_source_chapter_numbers(filename, raw_bytes):
    service = NovelImportService()

    parsed = service.parse_novel_file(filename, raw_bytes)

    assert [chapter["chapter_number"] for chapter in parsed["chapters"]] == [123, 124]
    assert [chapter["title"] for chapter in parsed["chapters"]] == ["雨夜", "异象"]


def test_parse_novel_file_does_not_treat_chapter_prefixed_body_as_titles():
    service = NovelImportService()
    content = "\n".join(
        f"第{index}章 标题{index}\n"
        f"第{index}章正文里主角继续调查，并发现新的线索。\n"
        "后续正文继续展开。"
        for index in range(1, 124)
    )

    parsed = service.parse_novel_file("sample.txt", content.encode("utf-8"))

    assert len(parsed["chapters"]) == 123
    assert parsed["chapters"][0]["chapter_number"] == 1
    assert parsed["chapters"][0]["title"] == "标题1"
    assert parsed["chapters"][122]["chapter_number"] == 123
    assert parsed["chapters"][122]["title"] == "标题123"
    assert "第1章正文里主角继续调查" in parsed["chapters"][0]["content"]
