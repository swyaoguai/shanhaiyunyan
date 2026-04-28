"""Tests for continuous-write routes."""

import io
import zipfile

from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.web.routes.continuous_write import (
    CONTINUOUS_WRITE_MAX_TOKENS_LIMIT,
    _cap_continuous_write_max_tokens,
)


def test_continuous_write_export_routes_return_clean_text_and_docx():
    app = create_app()
    client = TestClient(app)
    payload = {
        "title": "雨夜回声",
        "chapters": [
            {
                "chapter_number": 2,
                "title": "旧案",
                "content": "## 第2章 旧案\n她在旧档案里翻到了一封未寄出的信。",
            },
            {
                "chapter_number": 1,
                "title": "归来",
                "content": "# 第1章 归来\n周岚拖着箱子走进雨夜旧城。",
            },
        ],
    }

    export_txt = client.post("/api/continuous-write/export?format=txt", json=payload)
    assert export_txt.status_code == 200
    assert "attachment;" in export_txt.headers["content-disposition"]
    assert export_txt.text.startswith("雨夜回声")
    assert "\n1.\n周岚拖着箱子走进雨夜旧城。" in export_txt.text
    assert "\n2.\n她在旧档案里翻到了一封未寄出的信。" in export_txt.text
    assert "第1章 归来" not in export_txt.text
    assert "第2章 旧案" not in export_txt.text

    export_docx = client.post("/api/continuous-write/export?format=docx", json=payload)
    assert export_docx.status_code == 200
    assert export_docx.content.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(export_docx.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "雨夜回声" in document_xml
    assert "周岚拖着箱子走进雨夜旧城。" in document_xml
    assert "她在旧档案里翻到了一封未寄出的信。" in document_xml
    assert "第1章 归来" not in document_xml


def test_continuous_write_export_rejects_invalid_format():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/continuous-write/export?format=pdf",
        json={"title": "测试", "chapters": [{"chapter_number": 1, "content": "正文"}]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "导出格式仅支持 txt、md、docx。"


def test_continuous_write_caps_oversized_max_tokens():
    assert _cap_continuous_write_max_tokens(18888) == CONTINUOUS_WRITE_MAX_TOKENS_LIMIT
    assert _cap_continuous_write_max_tokens(4096) == 4096
    assert _cap_continuous_write_max_tokens(0) == 4096
