"""Novel-to-script fixed workbench API."""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from typing import Any, Dict
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from ...agent_config import AgentModelConfig, get_config_manager
from ...agents.llm_client import LLMClient
from ...novel_to_script_service import (
    NOVEL_TO_SCRIPT_STATE_KEY,
    NovelToScriptService,
)
from ..models.requests import (
    NovelToScriptBatchReconvertRequest,
    NovelToScriptConvertRequest,
    NovelToScriptExportRequest,
    NovelToScriptStateRequest,
)

router = APIRouter()


def _get_library_character_context() -> str:
    try:
        from ...library_service import get_library_service
        svc = get_library_service()
        if svc.is_degraded:
            return ""
        chars = svc.list_entries(entry_type="character")
        if not chars:
            return ""
        lines = ["[角色参考]"]
        for c in chars[:8]:
            name = c.content_structured.get("name", c.title)
            role = c.content_structured.get("role", "")
            desc = c.content_structured.get("description", "")
            lines.append(f"- {name}({role}): {desc[:60]}" if desc else f"- {name}: {role}")
        return "\n".join(lines)
    except Exception:
        return ""

logger = logging.getLogger(__name__)
_service = NovelToScriptService()

NOVEL_IMPORT_MAX_BYTES = 20 * 1024 * 1024
NOVEL_TO_SCRIPT_TOKEN_LIMIT = 6000
NOVEL_TO_SCRIPT_TIMEOUT_SECONDS = 240


def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"success": True, **data})


def _safe_export_filename(name: str) -> str:
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in (name or "").strip())
    return cleaned or "novel_to_script"


def _resolve_model_config(api_config_id: str = "", model: str = "") -> AgentModelConfig:
    manager = get_config_manager()
    api_base = ""
    api_key = ""
    temperature = 0.7
    max_tokens = NOVEL_TO_SCRIPT_TOKEN_LIMIT
    resolved_model = (model or "").strip()

    if api_config_id:
        multi = manager.get_multi_config()
        for cfg in multi.configs:
            if cfg.id == api_config_id:
                api_base = cfg.api_base
                api_key = cfg.api_key
                temperature = cfg.temperature
                max_tokens = cfg.max_tokens
                if not resolved_model and cfg.models:
                    resolved_model = cfg.models[0]
                break

    if not api_base or not api_key:
        global_config = manager.get_global_config()
        api_base = api_base or global_config.api_base
        api_key = api_key or global_config.api_key
        temperature = global_config.temperature or temperature
        max_tokens = global_config.max_tokens or max_tokens
        if not resolved_model:
            resolved_model = global_config.model

    if not api_base or not api_key:
        raise HTTPException(status_code=400, detail="未配置可用的 API，请先在设置中完成 API 配置。")
    if not resolved_model:
        raise HTTPException(status_code=400, detail="未选择模型，请先在面板中选择模型。")

    return AgentModelConfig(
        agent_name="NovelToScriptPanel",
        api_config_id=api_config_id,
        api_base=api_base,
        api_key=api_key,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        use_global=False,
    )


async def _run_conversion_prompt(prompt: Dict[str, str], *, api_config_id: str = "", model: str = "") -> str:
    model_config = _resolve_model_config(api_config_id=api_config_id, model=model)
    client = LLMClient(model_config=model_config, metrics_namespace="NovelToScriptPanel")
    max_tokens = min(int(model_config.max_tokens or NOVEL_TO_SCRIPT_TOKEN_LIMIT), NOVEL_TO_SCRIPT_TOKEN_LIMIT)

    try:
        return await asyncio.wait_for(
            client.call(
                messages=[{"role": "user", "content": prompt["user_prompt"]}],
                temperature=model_config.temperature,
                max_tokens=max_tokens,
                system_prompt=prompt["system_prompt"],
                stream=False,
                enable_retry=True,
            ),
            timeout=NOVEL_TO_SCRIPT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "[NovelToScript] Prompt timed out after %ss (model=%s, max_tokens=%s)",
            NOVEL_TO_SCRIPT_TIMEOUT_SECONDS,
            model_config.model,
            max_tokens,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"模型响应超时（{NOVEL_TO_SCRIPT_TIMEOUT_SECONDS} 秒）。"
                "请尝试缩短输入内容、按章节转换，或切换模型后重试。"
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        detail = str(exc).strip() or "剧本转换失败，请稍后重试。"
        logger.warning("[NovelToScript] Prompt failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from exc


def _build_docx_bytes(title: str, result: Dict[str, Any]) -> bytes:
    paragraphs = _service.build_export_text(title, result).strip("\n").split("\n")

    xml_paragraphs = []
    for paragraph in paragraphs:
        text = paragraph if paragraph else ""
        xml_paragraphs.append(
            f"<w:p><w:r><w:t xml:space=\"preserve\">{xml_escape(text)}</w:t></w:r></w:p>"
        )

    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" mc:Ignorable=\"w14 wp14\">"
        f"<w:body>{''.join(xml_paragraphs)}<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/></w:sectPr></w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
            "</Relationships>",
        )
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


@router.get("/novel-to-script/capabilities")
async def get_novel_to_script_capabilities():
    return _ok({"data": _service.get_capabilities()})


@router.post("/novel-to-script/import")
async def import_novel_to_script(
    novel_file: UploadFile = File(...),
):
    from ...project_manager import get_project_manager
    from ...novel_import_service import get_novel_import_service

    pm = get_project_manager()
    file_bytes = await novel_file.read(NOVEL_IMPORT_MAX_BYTES + 1)
    if not file_bytes:
        return JSONResponse({"success": False, "error": "上传文件为空"}, status_code=400)
    if len(file_bytes) > NOVEL_IMPORT_MAX_BYTES:
        return JSONResponse(
            {"success": False, "error": f"文件过大，最大支持 {NOVEL_IMPORT_MAX_BYTES // (1024 * 1024)}MB"},
            status_code=413,
        )

    import_service = get_novel_import_service(data_dir=pm.data_dir)
    try:
        parsed = import_service.parse_novel_file(
            filename=novel_file.filename or "import.txt",
            raw_bytes=file_bytes,
        )
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    normalized = _service.normalize_source(
        source_type="file",
        source_filename=parsed["filename"],
        source_text=parsed["content"],
        source_chapters=parsed["chapters"],
    )
    analysis = _service.analyze_source(normalized)

    return _ok(
        {
            "data": {
                "source_type": "file",
                "source_filename": normalized["source_filename"],
                "source_text": normalized["source_text"],
                "source_chapters": normalized["source_chapters"],
                "chapter_count": normalized["chapter_count"],
                "word_count": normalized["word_count"],
                "analysis": analysis,
            }
        }
    )


@router.post("/novel-to-script/convert")
async def convert_novel_to_script(request: NovelToScriptConvertRequest):
    normalized_config = _service.normalize_config(request.config.model_dump())
    normalized_source = _service.normalize_source(
        source_type=request.source_type,
        source_filename=request.source_filename,
        source_text=request.source_text,
        source_chapters=[item.model_dump() for item in request.source_chapters],
    )
    plan = _service.plan_conversion(source_payload=normalized_source, config=normalized_config)
    batch_results = []

    for batch in plan["batches"]:
        prompt = _service.build_messages(source_payload=batch, config=normalized_config)
        lib_ctx = _get_library_character_context()
        if lib_ctx and "user" in prompt:
            prompt["user"] = lib_ctx + "\n\n" + prompt["user"]
        try:
            raw_output = await _run_conversion_prompt(
                prompt,
                api_config_id=request.api_config_id,
                model=request.model,
            )
        except HTTPException as exc:
            detail = getattr(exc, "detail", "转换失败")
            if isinstance(detail, str):
                detail = f"第 {batch['batch_number']} / {plan['batch_count']} 批转换失败：{detail}"
            raise HTTPException(status_code=exc.status_code, detail=detail) from exc

        batch_results.append(
            {
                **batch,
                "result": _service.parse_conversion_result(raw_output),
            }
        )

    result = _service.merge_batch_results(batch_results, plan=plan)

    return _ok(
        {
            "data": {
                "source": normalized_source,
                "config": {
                    **normalized_config,
                    "resolved_mode": plan["resolved_mode"],
                },
                "analysis": plan["analysis"],
                "conversion_plan": plan,
                "result": result,
                "title": request.title or request.source_filename or "小说转剧本",
            }
        }
    )


@router.post("/novel-to-script/reconvert-batch")
async def reconvert_novel_to_script_batch(request: NovelToScriptBatchReconvertRequest):
    normalized_config = _service.normalize_config(request.config.model_dump())
    normalized_source = _service.normalize_source(
        source_type=request.source_type,
        source_filename=request.source_filename,
        source_text=request.source_text,
        source_chapters=[item.model_dump() for item in request.source_chapters],
    )
    plan = _service.plan_conversion(source_payload=normalized_source, config=normalized_config)

    try:
        batch = _service.get_batch_from_plan(plan, request.batch_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = _service.build_messages(source_payload=batch, config=normalized_config)
    try:
        raw_output = await _run_conversion_prompt(
            prompt,
            api_config_id=request.api_config_id,
            model=request.model,
        )
    except HTTPException as exc:
        detail = getattr(exc, "detail", "转换失败")
        if isinstance(detail, str):
            detail = f"第 {batch['batch_number']} / {plan['batch_count']} 批重转失败：{detail}"
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc

    replacement_batch = {
        **batch,
        "result": _service.parse_conversion_result(raw_output),
    }

    merged_result = _service.merge_with_existing_batch(
        plan=plan,
        existing_batches=request.existing_batches,
        replacement_batch=replacement_batch,
    )

    return _ok(
        {
            "data": {
                "source": normalized_source,
                "config": {
                    **normalized_config,
                    "resolved_mode": plan["resolved_mode"],
                },
                "analysis": plan["analysis"],
                "conversion_plan": plan,
                "batch_result": replacement_batch,
                "result": merged_result,
            }
        }
    )


@router.get("/novel-to-script/state")
async def get_novel_to_script_state():
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    try:
        data = pm.load_project_state(NOVEL_TO_SCRIPT_STATE_KEY, default=None)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    return _ok({"data": data})


@router.post("/novel-to-script/state")
async def save_novel_to_script_state(request: NovelToScriptStateRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    try:
        pm.save_project_state(NOVEL_TO_SCRIPT_STATE_KEY, request.data)
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    return _ok({"state_key": NOVEL_TO_SCRIPT_STATE_KEY})


@router.post("/novel-to-script/export")
async def export_novel_to_script(
    request: NovelToScriptExportRequest,
    format: str = "txt",
):
    normalized_format = (format or "txt").strip().lower()
    if normalized_format not in {"txt", "md", "docx"}:
        raise HTTPException(status_code=400, detail="仅支持导出 txt、md 或 docx。")

    result = request.result or {}
    try:
        content = _service.build_export_text(request.title, result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename_stem = _safe_export_filename(request.title or "小说转剧本")
    if normalized_format == "docx":
        data = _build_docx_bytes(request.title, result)
        encoded_name = quote(f"{filename_stem}.docx")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": (
                    "attachment; filename=novel_to_script.docx; "
                    f"filename*=UTF-8''{encoded_name}"
                )
            },
        )

    media_type = "text/markdown; charset=utf-8" if normalized_format == "md" else "text/plain; charset=utf-8"
    encoded_name = quote(f"{filename_stem}.{normalized_format}")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=novel_to_script.{normalized_format}; "
                f"filename*=UTF-8''{encoded_name}"
            )
        },
    )
