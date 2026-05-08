import io
import zipfile

import pytest
from fastapi import HTTPException

from novel_agent.web.routes.knowledge import (
    _inspect_local_onnx_model,
    _safe_extract_zip_bytes,
)


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_safe_extract_local_onnx_package_normalizes_required_files(tmp_path):
    target = tmp_path / "default"
    package = _zip_bytes({
        "package/model.onnx": b"fake-model",
        "package/tokenizer.json": "{}",
        "package/metadata.json": '{"model_id":"fake/bge","embedding_dim":512}',
    })

    result = _safe_extract_zip_bytes(package, target)
    status = _inspect_local_onnx_model({
        "onnx_model_dir": str(target),
        "onnx_model_file": "model.onnx",
        "onnx_tokenizer_dir": "",
    })

    assert result["copied_files"][:2] == ["model.onnx", "tokenizer.json"]
    assert status["installed"] is True
    assert status["metadata"]["model_id"] == "fake/bge"


def test_safe_extract_local_onnx_package_rejects_zip_slip(tmp_path):
    package = _zip_bytes({
        "../model.onnx": b"fake-model",
        "tokenizer.json": "{}",
    })

    with pytest.raises(HTTPException):
        _safe_extract_zip_bytes(package, tmp_path / "default")
