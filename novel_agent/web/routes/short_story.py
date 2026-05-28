"""
短篇创作固定面板 API。
"""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from xml.sax.saxutils import escape as xml_escape
from urllib.parse import quote
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from ...agent_config import AgentModelConfig, get_config_manager
from ...agents.llm_client import LLMClient
from ...short_story_service import (
    ShortStoryCreatorService,
    parse_chapters_from_full_text,
    parse_fusion_candidates,
    parse_material_analysis,
    parse_outline_payload,
    parse_story_tags,
    parse_synopsis_candidates,
    parse_title_candidates,
)
from ...short_story_settings import (
    DEFAULT_SHORT_STORY_TIMEOUTS,
    SHORT_STORY_TIMEOUT_MAX,
    SHORT_STORY_TIMEOUT_MIN,
    get_short_story_timeout_settings,
    save_short_story_timeout_settings,
)
from ..models.requests import (
    ShortStoryChapterGenerateRequest,
    ShortStoryChapterSaveRequest,
    ShortStoryOutlineConfirmRequest,
    ShortStoryQualityRewriteRequest,
    ShortStoryRollbackRequest,
    ShortStoryReviewCommitRequest,
    ShortStorySimpleFixRequest,
    ShortStoryTimeoutSettingsRequest,
    ShortStorySelectionRequest,
    ShortStoryStartRequest,
    ShortStoryWorkflowRequest,
)

router = APIRouter()

_service = ShortStoryCreatorService()
logger = logging.getLogger(__name__)

SHORT_STORY_TOKEN_LIMITS = {
    "input_analysis": 2200,
    "fusion": 3200,
    "synopsis": 2500,
    "outline": 4500,
    "chapter": 2800,
    "quality": 7000,  # 质量检查需要容纳较长报告与修订建议
    "quality_rewrite": 3200,
    "coherence": 2000,  # 复审同样只需要报告
    "title": 1800,
    "tags": 1400,
}


def _service_call(func, *args, **kwargs) -> Dict[str, Any]:
    try:
        return func(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_model_config(api_config_id: str = "", model: str = "") -> AgentModelConfig:
    manager = get_config_manager()
    api_base = ""
    api_key = ""
    temperature = 0.8
    max_tokens = 5000
    resolved_model = (model or "").strip()

    api_type = "openai_chat"
    if api_config_id:
        multi = manager.get_multi_config()
        for cfg in multi.configs:
            if cfg.id == api_config_id:
                api_base = cfg.api_base
                api_key = cfg.api_key
                temperature = cfg.temperature
                max_tokens = cfg.max_tokens
                api_type = getattr(cfg, 'api_type', 'openai_chat') or 'openai_chat'
                if not resolved_model and cfg.models:
                    resolved_model = cfg.models[0]
                break

    if not api_base or not api_key:
        global_config = manager.get_global_config()
        api_base = api_base or global_config.api_base
        api_key = api_key or global_config.api_key
        if not resolved_model:
            resolved_model = global_config.model
        temperature = global_config.temperature or temperature
        max_tokens = global_config.max_tokens or max_tokens
        api_type = getattr(global_config, 'api_type', 'openai_chat') or api_type

    if not api_base or not api_key:
        raise HTTPException(status_code=400, detail="未配置可用的 API，请先在设置中完成 API 配置。")
    if not resolved_model:
        raise HTTPException(status_code=400, detail="未选择模型，请先在面板中选择模型。")

    return AgentModelConfig(
        agent_name="ShortStoryPanel",
        api_config_id=api_config_id,
        api_base=api_base,
        api_key=api_key,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        use_global=False,
        api_type=api_type,
    )


async def _run_prompt(
    prompt: str,
    api_config_id: str = "",
    model: str = "",
    *,
    max_tokens_limit: int | None = None,
    timeout_seconds: int = 120,
) -> str:
    model_config = _resolve_model_config(api_config_id=api_config_id, model=model)
    client = LLMClient(model_config=model_config, metrics_namespace="ShortStoryPanel")
    max_tokens = model_config.max_tokens
    if max_tokens_limit is not None:
        max_tokens = min(int(max_tokens or max_tokens_limit), int(max_tokens_limit))

    try:
        return await asyncio.wait_for(
            client.call(
                messages=[{"role": "user", "content": prompt}],
                temperature=model_config.temperature,
                max_tokens=max_tokens,
                system_prompt="你是专业的中文短篇小说创作助手，请严格遵守用户给出的格式输出。",
                stream=False,
                enable_retry=True,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "[ShortStoryPanel] Prompt timed out after %ss (model=%s, max_tokens=%s)",
            timeout_seconds,
            model_config.model,
            max_tokens,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"模型响应超时（{timeout_seconds} 秒）。"
                "当前接口可能无响应，或所选模型不适合该步骤；请重试或切换模型。"
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        detail = str(exc).strip() or "短篇接口调用失败，请稍后重试。"
        logger.warning("[ShortStoryPanel] Prompt failed: %s", detail)
        raise HTTPException(status_code=502, detail=detail) from exc


def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"success": True, **data})


def _safe_export_filename(name: str) -> str:
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in (name or "").strip())
    return cleaned or "short_story"


def _get_short_story_prompt_limits(step: str) -> Dict[str, int]:
    return {
        "max_tokens_limit": SHORT_STORY_TOKEN_LIMITS[step],
        "timeout_seconds": get_short_story_timeout_settings().get(step, DEFAULT_SHORT_STORY_TIMEOUTS[step]),
    }


def _build_docx_bytes(payload: Dict[str, Any]) -> bytes:
    paragraphs = _service.build_clean_export_lines(payload)

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


@router.get("/short-story/capabilities")
async def get_short_story_capabilities():
    return JSONResponse(_service_call(_service.get_capabilities))


@router.post("/short-story/workflow/start")
async def start_short_story_workflow(request: ShortStoryStartRequest):
    category = (request.category or request.tone or "其他").strip() or "其他"
    source_input = (request.source_input or "").strip()
    return JSONResponse(
        _service_call(
            _service.start_workflow,
            request.keywords,
            request.target_total_words,
            request.chapter_word_target,
            category,
            source_input,
        )
    )


@router.post("/short-story/workflow/status")
async def get_short_story_workflow_status(request: ShortStoryWorkflowRequest):
    return JSONResponse(_service_call(_service.get_workflow_status, request.workflow))


@router.post("/short-story/workflow/rollback")
async def rollback_short_story_workflow(request: ShortStoryRollbackRequest):
    return JSONResponse(
        _service_call(
            _service.rollback_workflow,
            workflow=request.workflow,
            target_step=request.target_step,
            feedback=request.feedback,
        )
    )


@router.get("/short-story/settings")
async def get_short_story_settings():
    return _ok(
        {
            "data": {
                "timeouts": get_short_story_timeout_settings(),
                "timeout_range": {
                    "min": SHORT_STORY_TIMEOUT_MIN,
                    "max": SHORT_STORY_TIMEOUT_MAX,
                },
            }
        }
    )


@router.post("/short-story/settings")
async def save_short_story_settings(request: ShortStoryTimeoutSettingsRequest):
    try:
        timeouts = save_short_story_timeout_settings(request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _ok(
        {
            "data": {
                "timeouts": timeouts,
                "timeout_range": {
                    "min": SHORT_STORY_TIMEOUT_MIN,
                    "max": SHORT_STORY_TIMEOUT_MAX,
                },
            }
        }
    )


@router.post("/short-story/input/analyze")
async def analyze_short_story_input(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_input_analysis_prompt, request.workflow)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("input_analysis"),
    )
    workflow = request.workflow or {}
    parsed = parse_material_analysis(
        raw_output,
        fallback_source=str(workflow.get("raw_input") or ""),
        fallback_category=str(workflow.get("category") or "其他"),
    )
    result = _service_call(_service.record_input_analysis, workflow, parsed)
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "raw_output": raw_output,
                "analysis": parsed,
            }
        }
    )


@router.post("/short-story/fusion-options/generate")
async def generate_short_story_fusion_options(request: ShortStoryWorkflowRequest):
    workflow = request.workflow or {}
    if workflow.get("state") == "awaiting_fusion_selection":
        workflow["state"] = "generating_fusion_options"
        workflow["fusion_candidates"] = []
        workflow["selected_fusion"] = {}
        workflow["selected_fusion_index"] = None
    prompt_result = _service_call(_service.build_fusion_options_prompt, workflow)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("fusion"),
    )
    candidates = parse_fusion_candidates(raw_output)
    if len(candidates) != 3:
        raise HTTPException(status_code=400, detail="创意方案解析失败，请重新生成。")
    result = _service_call(_service.register_fusion_candidates, workflow, candidates)
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "raw_output": raw_output,
                "candidates": candidates,
            }
        }
    )


@router.post("/short-story/fusion-options/select")
async def select_short_story_fusion_option(request: ShortStorySelectionRequest):
    return JSONResponse(_service_call(_service.select_fusion, request.workflow, request.selection))


@router.post("/short-story/synopsis/generate")
async def generate_short_story_synopsis(request: ShortStoryWorkflowRequest):
    # 如果当前状态是 awaiting_synopsis_selection，需要重置回 generating_synopsis 以支持重新生成
    workflow = request.workflow or {}
    if workflow.get("state") == "awaiting_synopsis_selection":
        workflow["state"] = "generating_synopsis"
        workflow["synopsis_candidates"] = []
        workflow["selected_synopsis"] = ""
        workflow["selected_synopsis_index"] = None
    
    prompt_result = _service_call(_service.build_synopsis_prompt, workflow, request.feedback)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("synopsis"),
    )
    candidates = parse_synopsis_candidates(raw_output)
    if len(candidates) != 5:
        raise HTTPException(status_code=400, detail="导语解析失败，请重新生成。")
    result = _service_call(_service.register_synopsis_candidates, workflow, candidates)
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "raw_output": raw_output,
                "candidates": candidates,
            }
        }
    )


@router.post("/short-story/synopsis/select")
async def select_short_story_synopsis(request: ShortStorySelectionRequest):
    return JSONResponse(_service_call(_service.select_synopsis, request.workflow, request.selection))


@router.post("/short-story/outline/generate")
async def generate_short_story_outline(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_outline_prompt, request.workflow)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("outline"),
    )
    workflow = request.workflow or {}
    parsed = parse_outline_payload(raw_output, int(workflow.get("planned_chapters", 0) or 0))
    result = _service_call(
        _service.record_outline,
        workflow=request.workflow,
        outline_text=parsed["outline_text"],
        character_table=parsed["character_table"],
        timeline=parsed["timeline"],
        chapter_blueprints=parsed["chapter_blueprints"],
    )
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "raw_output": raw_output,
                "outline": parsed,
            }
        }
    )


@router.post("/short-story/outline/confirm")
async def confirm_short_story_outline(request: ShortStoryOutlineConfirmRequest):
    return JSONResponse(_service_call(_service.confirm_outline, request.workflow, request.approved, request.feedback))


@router.post("/short-story/outline/repair-placeholders")
async def repair_short_story_placeholder_outline(request: ShortStoryWorkflowRequest):
    return JSONResponse(_service_call(_service.rollback_placeholder_blueprints, request.workflow, request.feedback))


@router.post("/short-story/chapter/generate")
async def generate_short_story_chapter(request: ShortStoryChapterGenerateRequest):
    normalized_workflow = request.workflow or {}
    chapters = [
        item for item in normalized_workflow.get("chapters", [])
        if int(item.get("chapter_number", 0) or 0) < int(request.chapter_number or 0)
    ]
    previous_text = _service.render_chapters(chapters) if chapters else "无"
    prompt_result = _service_call(
        _service.build_chapter_prompt,
        normalized_workflow,
        chapter_number=request.chapter_number,
        previous_chapters_text=previous_text,
    )
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("chapter"),
    )
    chapter_title = prompt_result["data"]["chapter_title"]
    result = _service_call(
        _service.record_chapter,
        workflow=normalized_workflow,
        chapter_number=request.chapter_number,
        title=chapter_title,
        content=raw_output.strip(),
    )
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "chapter": {
                    "chapter_number": request.chapter_number,
                    "title": chapter_title,
                    "content": raw_output.strip(),
                },
                "next_step": result["data"]["next_step"],
            }
        }
    )


@router.post("/short-story/chapter/generate-all")
async def generate_all_short_story_chapters(request: ShortStoryWorkflowRequest):
    workflow = request.workflow or {}
    current_workflow = workflow
    generated_chapters = []

    planned = int(current_workflow.get("planned_chapters", 0) or 0)
    for chapter_number in range(1, planned + 1):
        existing_numbers = {int(item.get("chapter_number", 0)) for item in current_workflow.get("chapters", [])}
        if chapter_number in existing_numbers:
            continue

        previous_chapters = [
            item for item in current_workflow.get("chapters", [])
            if int(item.get("chapter_number", 0) or 0) < chapter_number
        ]
        previous_text = _service.render_chapters(previous_chapters) or "无"
        prompt_result = _service_call(
            _service.build_chapter_prompt,
            current_workflow,
            chapter_number=chapter_number,
            previous_chapters_text=previous_text,
        )
        prompt = prompt_result["data"]["prompt"]
        try:
            raw_output = await _run_prompt(
                prompt,
                request.api_config_id,
                request.model,
                **_get_short_story_prompt_limits("chapter"),
            )
        except HTTPException as exc:
            if generated_chapters:
                detail = str(exc.detail).strip() or "章节生成中断，请稍后重试。"
                return _ok(
                    {
                        "data": {
                            "workflow": current_workflow,
                            "generated_chapters": generated_chapters,
                            "partial": True,
                            "failed_chapter": chapter_number,
                            "error": detail,
                        }
                    }
                )
            raise
        chapter_title = prompt_result["data"]["chapter_title"]
        record_result = _service_call(
            _service.record_chapter,
            workflow=current_workflow,
            chapter_number=chapter_number,
            title=chapter_title,
            content=raw_output.strip(),
        )
        current_workflow = record_result["data"]["workflow"]
        generated_chapters.append(
            {
                "chapter_number": chapter_number,
                "title": chapter_title,
                "content": raw_output.strip(),
            }
        )

    return _ok(
        {
            "data": {
                "workflow": current_workflow,
                "generated_chapters": generated_chapters,
            }
        }
    )


@router.post("/short-story/chapter/save")
async def save_short_story_chapter(request: ShortStoryChapterSaveRequest):
    return JSONResponse(
        _service_call(
            _service.record_chapter,
            workflow=request.workflow,
            chapter_number=request.chapter_number,
            title=request.title,
            content=request.content,
        )
    )


@router.post("/short-story/quality-check/generate")
async def generate_short_story_quality_check(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_quality_check_prompt, request.workflow, use_batch=True, batch_size=3)
    data = prompt_result["data"]
    
    # 检查是否使用分批处理
    if data.get("use_batch"):
        # 分批处理
        batches = data["batches"]
        all_reports = []
        
        for batch in batches:
            batch_report = await _run_prompt(
                batch["prompt"],
                request.api_config_id,
                request.model,
                **_get_short_story_prompt_limits("quality"),
            )
            all_reports.append(f"## 批次 {batch['batch_index'] + 1}（第{batch['batch_start']}-{batch['batch_end']}章）\n{batch_report}")
        
        # 合并报告
        if len(all_reports) == 1:
            raw_output = all_reports[0]
        else:
            raw_output = "# 分批质检报告\n\n" + "\n\n".join(all_reports)
            all_passed = all("✅" in report or "通过" in report for report in all_reports)
            if all_passed:
                raw_output += "\n\n## 总结\n✅ 所有批次质量检查通过，无需修改。"
            else:
                raw_output += "\n\n## 总结\n⚠️ 部分章节存在问题，请查看上述详细报告。"
        
        prompt = f"分批质检（共{len(batches)}批）"
    else:
        # 单次处理
        prompt = data["prompt"]
        raw_output = await _run_prompt(
            prompt,
            request.api_config_id,
            request.model,
            **_get_short_story_prompt_limits("quality"),
        )
    
    passed = "质量检查通过" in raw_output or "通过" in raw_output
    revised_chapters = parse_chapters_from_full_text(raw_output)
    simple_fixes = _service.extract_simple_quality_fixes(request.workflow, raw_output)
    rewrite_targets = _service.extract_quality_rewrite_targets(request.workflow, raw_output)
    return _ok(
        {
            "data": {
                "workflow": request.workflow,
                "prompt": prompt,
                "report": raw_output,
                "passed": passed,
                "revised_chapters": revised_chapters,
                "simple_fixes": simple_fixes,
                "rewrite_targets": rewrite_targets,
            }
        }
    )


@router.post("/short-story/quality-check/commit")
async def commit_short_story_quality_check(request: ShortStoryReviewCommitRequest):
    revised_chapters = _service.normalize_chapters_payload(request.chapters) if request.chapters else None
    return JSONResponse(
        _service_call(
            _service.record_quality_check,
            workflow=request.workflow,
            report=request.report,
            passed=request.passed,
            revised_chapters=revised_chapters,
        )
    )


@router.post("/short-story/quality-check/apply-simple-fixes")
async def apply_short_story_quality_simple_fixes(request: ShortStorySimpleFixRequest):
    revised_chapters = _service.normalize_chapters_payload(request.chapters) if request.chapters else None
    return JSONResponse(
        _service_call(
            _service.apply_simple_quality_fixes,
            workflow=request.workflow,
            report=request.report,
            chapters=revised_chapters,
        )
    )


@router.post("/short-story/quality-check/rewrite-issue-chapters")
async def rewrite_short_story_quality_issue_chapters(request: ShortStoryQualityRewriteRequest):
    revised_chapters = _service.normalize_chapters_payload(request.chapters) if request.chapters else None
    targets = _service.extract_quality_rewrite_targets(request.workflow, request.report)
    if not targets:
        raise HTTPException(status_code=400, detail="当前质检报告中没有需要大模型重写的章节问题。")

    rewritten_chapters = []
    prompts = []
    for target in targets:
        chapter_number = int(target["chapter_number"])
        prompt_result = _service_call(
            _service.build_quality_issue_rewrite_prompt,
            request.workflow,
            chapter_number=chapter_number,
            issues=target.get("issues") or [],
            chapters=revised_chapters,
        )
        prompt = prompt_result["data"]["prompt"]
        raw_output = await _run_prompt(
            prompt,
            request.api_config_id,
            request.model,
            **_get_short_story_prompt_limits("quality_rewrite"),
        )
        title = prompt_result["data"]["chapter_title"]
        rewritten_chapters.append(
            {
                "chapter_number": chapter_number,
                "title": title,
                "content": raw_output.strip(),
            }
        )
        prompts.append(
            {
                "chapter_number": chapter_number,
                "prompt": prompt,
                "issues": target.get("issues") or [],
            }
        )

    result = _service_call(
        _service.rewrite_quality_issue_chapters,
        workflow=request.workflow,
        rewritten_chapters=rewritten_chapters,
        chapters=revised_chapters,
    )
    return _ok(
        {
            "data": {
                **result["data"],
                "rewrite_targets": targets,
                "prompts": prompts,
            }
        }
    )


@router.post("/short-story/coherence-review/generate")
async def generate_short_story_coherence_review(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_coherence_review_prompt, request.workflow, use_batch=True, batch_size=3)
    data = prompt_result["data"]
    
    # 检查是否使用分批处理
    if data.get("use_batch"):
        # 分批处理
        batches = data["batches"]
        all_reports = []
        
        for batch in batches:
            batch_report = await _run_prompt(
                batch["prompt"],
                request.api_config_id,
                request.model,
                **_get_short_story_prompt_limits("coherence"),
            )
            all_reports.append(f"## 批次 {batch['batch_index'] + 1}（第{batch['batch_start']}-{batch['batch_end']}章）\n{batch_report}")
        
        # 合并报告
        if len(all_reports) == 1:
            raw_output = all_reports[0]
        else:
            raw_output = "# 分批复审报告\n\n" + "\n\n".join(all_reports)
            all_passed = all("✅" in report or "通过" in report for report in all_reports)
            if all_passed:
                raw_output += "\n\n## 总结\n✅ 所有批次复审通过。"
            else:
                raw_output += "\n\n## 总结\n⚠️ 部分章节存在问题，请查看上述详细报告。"
        
        prompt = f"分批复审（共{len(batches)}批）"
    else:
        # 单次处理
        prompt = data["prompt"]
        raw_output = await _run_prompt(
            prompt,
            request.api_config_id,
            request.model,
            **_get_short_story_prompt_limits("coherence"),
        )
    
    passed = "复审通过" in raw_output or "正文定稿" in raw_output or "通过" in raw_output
    final_chapters = parse_chapters_from_full_text(raw_output)
    return _ok(
        {
            "data": {
                "workflow": request.workflow,
                "prompt": prompt,
                "report": raw_output,
                "passed": passed,
                "final_chapters": final_chapters,
            }
        }
    )


@router.post("/short-story/coherence-review/commit")
async def commit_short_story_coherence_review(request: ShortStoryReviewCommitRequest):
    revised_chapters = _service.normalize_chapters_payload(request.chapters) if request.chapters else None
    return JSONResponse(
        _service_call(
            _service.record_coherence_review,
            workflow=request.workflow,
            report=request.report,
            passed=request.passed,
            final_chapters=revised_chapters,
        )
    )


@router.post("/short-story/title/generate")
async def generate_short_story_titles(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_title_prompt, request.workflow, "", request.feedback)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("title"),
    )
    candidates = parse_title_candidates(raw_output)
    if len(candidates) != 5:
        raise HTTPException(status_code=400, detail="书名解析失败，请重新生成。")
    result = _service_call(_service.register_title_candidates, request.workflow, candidates)
    return _ok(
        {
            "data": {
                "workflow": result["data"]["workflow"],
                "prompt": prompt,
                "raw_output": raw_output,
                "candidates": candidates,
            }
        }
    )


@router.post("/short-story/title/select")
async def select_short_story_title(request: ShortStorySelectionRequest):
    return JSONResponse(_service_call(_service.select_title, request.workflow, request.selection))


@router.post("/short-story/assemble")
async def assemble_short_story(request: ShortStoryWorkflowRequest):
    prompt_result = _service_call(_service.build_story_tags_prompt, request.workflow)
    prompt = prompt_result["data"]["prompt"]
    raw_output = await _run_prompt(
        prompt,
        request.api_config_id,
        request.model,
        **_get_short_story_prompt_limits("tags"),
    )
    current_workflow = request.workflow or {}
    parsed_tags = parse_story_tags(raw_output, current_workflow.get("category") or current_workflow.get("tone") or "其他")
    tagged = _service_call(_service.record_story_tags, current_workflow, parsed_tags)
    assembled = _service_call(_service.assemble_output, tagged["data"]["workflow"])
    payload = assembled.get("data", {})
    payload["raw_tags_output"] = raw_output
    payload["story_tags"] = parsed_tags
    return _ok({"data": payload})


@router.post("/short-story/export")
async def export_short_story(request: ShortStoryWorkflowRequest, format: str = "txt"):
    normalized_format = (format or "txt").strip().lower()
    if normalized_format not in {"txt", "md", "docx"}:
        raise HTTPException(status_code=400, detail="导出格式仅支持 txt、md、docx。")

    payload = _service_call(_service.build_export_payload, request.workflow)["data"]
    title = _safe_export_filename(payload["title"])
    if normalized_format == "txt":
        content = _service.render_export_text(payload)
        filename = f"{title}.txt"
        media_type = "text/plain; charset=utf-8"
        data = content.encode("utf-8")
    elif normalized_format == "md":
        content = _service.render_export_markdown(payload)
        filename = f"{title}.md"
        media_type = "text/markdown; charset=utf-8"
        data = content.encode("utf-8")
    else:
        filename = f"{title}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        data = _build_docx_bytes(payload)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return Response(content=data, media_type=media_type, headers=headers)
