"""
无限续写API路由模块

包含无限续写的开始、继续、同步、重新生成等功能。
"""

import io
import re
import logging
import asyncio
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from ..models.requests import (
    ContinuousWriteStartRequest,
    ContinuousWriteContinueRequest,
    ContinuousWriteSyncRequest,
    ContinuousWriteRegenerateRequest,
    ContinuousWriteInspirationRequest,
    ContinuousWriteCorrectionRequest,
    UpdateInfiniteWriteChapterRequest,
    AddDeadCharacterRequest,
    RegexReplaceRequest,
    ContinuousWriteExportRequest,
)
from ...constants import LLM_DEFAULTS

logger = logging.getLogger(__name__)

router = APIRouter()

# 存储无限续写Agent实例（按 project_id + session_id 隔离）
continuous_writers = {}
_continuous_writer_locks = {}
_continuous_locks_guard = asyncio.Lock()
_MAX_WRITERS_POOL = 200
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NOVEL_IMPORT_MAX_BYTES = 20 * 1024 * 1024


def _wire_character_manager(writer, pm) -> None:
    """为 ContinuousWriter 注入 CharacterManager（静默失败）。"""
    try:
        from ...context.character_manager import CharacterManager
        project_dir = pm._get_project_dir(pm.current_project_id)
        cm = CharacterManager(project_dir)
        writer.set_character_manager(cm)
    except Exception as e:
        logger.warning(f"[ContinuousWriter] CharacterManager初始化失败: {e}")
_EXPORT_CHAPTER_HEADING_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s*)?第\s*\d+\s*章[^\n\r]*[\r\n]+")
CONTINUOUS_WRITE_MAX_TOKENS_LIMIT = 8192

def _safe_export_filename(name: str) -> str:
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in (name or "").strip())
    return cleaned or "continuous_write"


def _clean_export_chapter_content(content: Any) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    return _EXPORT_CHAPTER_HEADING_RE.sub("", text, count=1).strip()


def _normalize_export_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", (title or "").strip())
    return normalized or "无限续写"


def _build_continuous_write_export_lines(title: str, chapters: List[Dict[str, Any]]) -> List[str]:
    ordered = sorted(
        [chapter for chapter in chapters if isinstance(chapter, dict)],
        key=lambda chapter: int(chapter.get("chapter_number", 0) or 0),
    )
    if not ordered:
        raise HTTPException(status_code=400, detail="当前没有可导出的章节。")

    lines: List[str] = [_normalize_export_title(title), ""]
    for index, chapter in enumerate(ordered):
        chapter_number = int(chapter.get("chapter_number", index + 1) or (index + 1))
        lines.append(f"{chapter_number}.")
        content = _clean_export_chapter_content(chapter.get("content", ""))
        if content:
            lines.extend(content.split("\n"))
        if index != len(ordered) - 1:
            lines.append("")
    return lines


def _render_continuous_write_export_text(title: str, chapters: List[Dict[str, Any]]) -> str:
    return "\n".join(_build_continuous_write_export_lines(title, chapters)).strip() + "\n"


def _build_continuous_write_docx_bytes(title: str, chapters: List[Dict[str, Any]]) -> bytes:
    paragraphs = _build_continuous_write_export_lines(title, chapters)

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


def _normalize_session_id(session_id: str) -> str:
    value = (session_id or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="session_id 不能为空")
    if not _SESSION_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=400, detail="session_id 包含非法字符")
    return value


def _cap_continuous_write_max_tokens(max_tokens: int | None) -> int:
    """Clamp continuous-write max_tokens to a provider-safe range."""
    parsed = int(max_tokens or LLM_DEFAULTS.MAX_TOKENS)
    capped = max(1, min(parsed, CONTINUOUS_WRITE_MAX_TOKENS_LIMIT))
    if capped != parsed:
        logger.warning(
            "[ContinuousWrite] max_tokens %s exceeds safe limit, capped to %s",
            parsed,
            capped,
        )
    return capped

async def _get_writer_lock(writer_key: str) -> asyncio.Lock:
    async with _continuous_locks_guard:
        lock = _continuous_writer_locks.get(writer_key)
        if lock is None:
            if len(_continuous_writer_locks) >= _MAX_WRITERS_POOL:
                for old_key in list(_continuous_writer_locks):
                    old_lock = _continuous_writer_locks[old_key]
                    if not old_lock.locked():
                        _continuous_writer_locks.pop(old_key, None)
                        continuous_writers.pop(old_key, None)
                        break
            lock = asyncio.Lock()
            _continuous_writer_locks[writer_key] = lock
        return lock

def _writer_key(project_id: str, session_id: str) -> str:
    return f"{project_id}::{session_id}"


def clear_project_runtime(project_id: str) -> int:
    """清理指定项目的无限续写内存态实例与锁。"""
    prefix = f"{str(project_id or '').strip()}::"
    if not prefix or prefix == "::":
        return 0

    removed = 0
    for key in list(continuous_writers.keys()):
        if key.startswith(prefix):
            writer = continuous_writers.pop(key, None)
            kb = getattr(writer, "knowledge_base", None)
            if kb is not None and hasattr(kb, "close"):
                try:
                    kb.close()
                except Exception as exc:
                    logger.warning(f"[ContinuousWrite] Failed to close knowledge base for {key}: {exc}")
            if writer is not None and hasattr(writer, "set_knowledge_base"):
                writer.set_knowledge_base(None)
            removed += 1

    for key in list(_continuous_writer_locks.keys()):
        if key.startswith(prefix):
            _continuous_writer_locks.pop(key, None)

    logger.info(f"[ContinuousWrite] Cleared runtime writers for project={project_id}, removed={removed}")
    return removed


def resolve_continuous_write_model_config(model: str = "", api_config_id: str = "") -> tuple[Any, str]:
    """统一解析无限续写模型配置，处理指定配置与全局配置回退。"""
    from ...agent_config import AgentModelConfig, get_config_manager

    config_manager = get_config_manager()
    requested_model = str(model or "").strip()
    selected_config = None

    if api_config_id:
        multi_config = config_manager.get_multi_config()
        for cfg in multi_config.configs:
            if cfg.id == api_config_id:
                selected_config = cfg
                break

    if selected_config:
        api_base = selected_config.api_base
        api_key = selected_config.get_primary_key()
        api_keys = selected_config.api_keys
        api_type = selected_config.api_type
        temperature = selected_config.temperature
        max_tokens = selected_config.max_tokens
        model_name = requested_model or (selected_config.models[0] if selected_config.models else "")
        resolved_api_config_id = selected_config.id
        logger.info(
            "[ContinuousWrite] 使用指定的API配置: %s (%s), api_type=%s, model=%s",
            selected_config.name,
            selected_config.id,
            api_type,
            model_name,
        )
    else:
        global_config = config_manager.get_global_config()
        api_base = global_config.api_base
        api_key = global_config.get_primary_key()
        api_keys = global_config.api_keys
        api_type = global_config.api_type
        temperature = global_config.temperature
        max_tokens = global_config.max_tokens
        model_name = requested_model or global_config.model
        resolved_api_config_id = config_manager.get_multi_config().active_config_id
        logger.info(
            "[ContinuousWrite] 使用激活的全局API配置: %s, api_type=%s, model=%s",
            resolved_api_config_id,
            api_type,
            model_name,
        )

    max_tokens = _cap_continuous_write_max_tokens(max_tokens)

    if not model_name:
        return None, ""

    model_config = AgentModelConfig(
        agent_name="ContinuousWriter",
        api_config_id=resolved_api_config_id,
        api_base=api_base,
        api_key=api_key,
        api_keys=api_keys,
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        use_global=False,
        api_type=api_type or "openai_chat",
    )
    return model_config, model_name


def _apply_continuous_write_model_config(writer, model_config: Any, model_name: str) -> None:
    """Apply a selected API/model config to an existing ContinuousWriter instance."""
    if not model_config or not model_name:
        return
    writer.model_config = model_config
    writer.client = writer._create_client()
    if hasattr(writer, "_llm_client"):
        writer._llm_client = None
    if hasattr(writer, "_rotation_client_cache"):
        writer._rotation_client_cache.clear()
    writer.set_model(model_name)
    logger.info(
        "[ContinuousWrite] Writer config applied: config_id=%s, api_type=%s, api_base=%s, model=%s",
        getattr(model_config, "api_config_id", ""),
        getattr(model_config, "api_type", "openai_chat"),
        getattr(model_config, "api_base", ""),
        model_name,
    )


def _sync_writer_from_session(writer: Any, state: Any) -> None:
    """Ensure a runtime writer has the persisted session data loaded."""
    if state is None:
        return
    writer._session_state = state
    writer._story_beginning = state.story_beginning
    writer._current_chapter = state.current_chapter
    writer._written_chapters = state.chapters.copy()
    writer._dead_characters = state.dead_characters.copy()
    writer._user_inspirations = state.inspirations.copy()
    writer._corrections = state.corrections.copy()
    try:
        from ...agents.continuous_writer import CharacterState, PlotPoint

        writer._characters = {
            name: CharacterState(**payload) if isinstance(payload, dict) else CharacterState(name=name)
            for name, payload in (state.character_states or {}).items()
        }
        writer._plot_points = [
            PlotPoint(**item)
            for item in (state.plot_points or [])
            if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning(f"[ContinuousWrite] Failed to restore writer memory details: {exc}")


async def _refresh_infinite_memory(
    project_id: str,
    session_id: str,
    chapters: List[dict],
    source_file: str = "runtime",
    data_dir: Path | None = None,
) -> None:
    try:
        from ...novel_import_service import get_novel_import_service

        service = get_novel_import_service(data_dir=data_dir)
        service.refresh_infinite_memory(
            project_id=project_id,
            session_id=session_id,
            chapters=chapters,
            source_file=source_file,
        )
    except Exception as exc:
        logger.warning(f"[ContinuousWrite] Failed to refresh isolated memory: {exc}")


def _chapter_numbers_from_payload(chapters: Any) -> List[int]:
    numbers: set[int] = set()
    if not isinstance(chapters, list):
        return []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        try:
            number = int(chapter.get("chapter_number") or 0)
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            numbers.add(number)
    return sorted(numbers)


def _clear_continuous_write_session_memory(state: Any) -> None:
    """Clear hidden continuity fields when the visible chapter list is empty."""
    state.story_beginning = ""
    state.inspirations = []
    state.corrections = []
    state.dead_characters = []
    state.character_states = {}
    state.plot_points = []
    state.is_running = False


def _delete_project_knowledge_chapters(
    project_id: str,
    data_dir: Path | None,
    chapter_numbers: List[int],
) -> int:
    numbers = sorted({int(num) for num in chapter_numbers if isinstance(num, int) and num > 0})
    if not numbers or not project_id:
        return 0

    deleted = 0
    try:
        from ...knowledge_base.data_layer.vector_store import CHROMA_AVAILABLE
        from ...knowledge_runtime import create_project_knowledge_base, has_embedding_config, load_knowledge_base_settings

        if not CHROMA_AVAILABLE:
            return 0

        kb_settings = load_knowledge_base_settings(data_dir)
        if not has_embedding_config(kb_settings):
            return 0

        kb = create_project_knowledge_base(
            project_id,
            data_dir=data_dir,
            use_mock_embeddings=False,
        )
        try:
            for num in numbers:
                try:
                    if kb.delete_chapter(f"chapter_{num}"):
                        deleted += 1
                except Exception as e:
                    logger.warning(f"[ContinuousWrite] 删除知识库章节失败: chapter_{num}, {e}")
        finally:
            kb.close()
    except Exception as e:
        logger.warning(f"[ContinuousWrite] 同步知识库失败: {e}")

    return deleted


@router.post("/continuous-write/import")
async def import_novel_to_infinite_write(
    novel_file: UploadFile = File(...),
    session_id: str = Form("default"),
):
    """Import txt/md/docx into infinite-write mode and auto-build isolated memory."""
    from ...agents.session_store import SessionState, get_session_store
    from ...novel_import_service import get_novel_import_service
    from ...project_manager import get_project_manager

    normalized_session_id = _normalize_session_id(session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""

    file_bytes = await novel_file.read(NOVEL_IMPORT_MAX_BYTES + 1)
    if not file_bytes:
        return JSONResponse({"success": False, "error": "上传文件为空"}, status_code=400)
    if len(file_bytes) > NOVEL_IMPORT_MAX_BYTES:
        return JSONResponse(
            {"success": False, "error": f"文件过大，最大支持 {NOVEL_IMPORT_MAX_BYTES // (1024 * 1024)}MB"},
            status_code=413,
        )

    service = get_novel_import_service(data_dir=pm.data_dir)
    try:
        parsed = service.parse_novel_file(
            filename=novel_file.filename or "import.txt",
            raw_bytes=file_bytes,
        )
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    imported_chapters = parsed["chapters"]
    current_chapter = max(
        [int(ch.get("chapter_number") or 0) for ch in imported_chapters if isinstance(ch, dict)] or [len(imported_chapters)]
    )
    story_beginning = imported_chapters[0].get("content", "")[:500] if imported_chapters else ""

    session_store = get_session_store()
    existing = await session_store.aload(normalized_session_id, project_id)
    state = existing or SessionState(
        session_id=normalized_session_id,
        project_id=project_id,
        words_per_chapter=2500,
    )
    state.story_beginning = story_beginning
    state.chapters = imported_chapters
    state.current_chapter = current_chapter
    state.is_running = False
    state.inspirations = []
    state.corrections = []
    await session_store.asave(state)

    writer_key = _writer_key(project_id, normalized_session_id)
    lock = await _get_writer_lock(writer_key)
    async with lock:
        writer = continuous_writers.get(writer_key)
        if writer is not None:
            writer._apply_client_sync(imported_chapters, current_chapter, [])

    memory = service.refresh_infinite_memory(
        project_id=project_id,
        session_id=normalized_session_id,
        chapters=imported_chapters,
        source_file=parsed["filename"],
    )
    try:
        material_supplement = service.supplement_project_materials(
            project_manager=pm,
            source_file=parsed["filename"],
            chapters=imported_chapters,
        )
        if material_supplement.get("success"):
            try:
                from ...library_service import get_library_service

                svc = get_library_service()
                for data_type, stats in material_supplement.get("data_types", {}).items():
                    if stats.get("changed"):
                        svc.upsert_from_legacy(data_type, pm.load_project_data(data_type))
            except Exception as sync_exc:
                logger.debug(f"[ContinuousWrite] Library sync after import material supplement skipped: {sync_exc}")
    except Exception as exc:
        logger.warning(f"[ContinuousWrite] Failed to supplement project materials from imported novel: {exc}")
        material_supplement = {"success": False, "error": str(exc), "data_types": {}}

    return JSONResponse(
        {
            "success": True,
            "mode": "infinite_write",
            "session_id": normalized_session_id,
            "project_id": project_id,
            "filename": parsed["filename"],
            "imported_chapters": len(imported_chapters),
            "current_chapter": current_chapter,
            "chapters": imported_chapters,
            "total_words": sum(ch.get("word_count", 0) for ch in imported_chapters),
            "memory_summary": {
                "chapter_memory": len(memory.get("chapter_memory", [])),
                "character_index": len(memory.get("character_index", [])),
                "pending_hooks": len(memory.get("pending_hooks", [])),
            },
            "material_supplement": material_supplement,
        }
    )


@router.post("/continuous-write/start")
async def start_continuous_write(request: ContinuousWriteStartRequest):
    """开始无限续写"""
    from ...agents import ContinuousWriter, ContinuousWriteConfig
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    session_id = _normalize_session_id(request.session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    session_store = get_session_store()
    existing_session = await session_store.aload(session_id, project_id) if request.auto_restore else None
    
    if existing_session and existing_session.chapters:
        logger.info(f"[ContinuousWrite] 发现持久化会话，已有 {len(existing_session.chapters)} 章")
    
    write_config = ContinuousWriteConfig(
        words_per_chapter=request.words_per_chapter,
        auto_save_to_kb=True,
        check_consistency=True,
        enable_trends_search=request.enable_trends,
        trends_platforms=request.trends_platforms if request.trends_platforms else ["toutiao", "douyin"]
    )
    
    model_config, model_name = resolve_continuous_write_model_config(
        model=request.model,
        api_config_id=request.api_config_id,
    )
    
    writer = ContinuousWriter(
        write_config=write_config,
        model_config=model_config,
        session_id=session_id,
        project_id=project_id
    )
    
    if model_name:
        writer.set_model(model_name)
    
    # 尝试配置知识库
    if pm.current_project_id:
        try:
            from ...knowledge_base.data_layer.vector_store import CHROMA_AVAILABLE, CHROMA_IMPORT_ERROR
            from ...knowledge_runtime import create_project_knowledge_base, has_embedding_config, load_knowledge_base_settings
            
            if not CHROMA_AVAILABLE:
                logger.error(f"[ContinuousWriter] ChromaDB不可用: {CHROMA_IMPORT_ERROR}")
            else:
                kb_settings = load_knowledge_base_settings(pm.data_dir)
                if has_embedding_config(kb_settings):
                    kb = create_project_knowledge_base(
                        pm.current_project_id,
                        data_dir=pm.data_dir,
                        use_mock_embeddings=False,
                    )
                    writer.set_knowledge_base(kb)
                    logger.info("[ContinuousWriter] ✓ 知识库已配置（使用真实向量存储）")
                else:
                    logger.info("[ContinuousWriter] 未配置可用向量化 provider，跳过知识库功能")
        except ImportError as e:
            logger.error(f"[ContinuousWriter] 知识库初始化失败（ChromaDB不可用）: {e}")
        except ValueError as e:
            logger.warning(f"[ContinuousWriter] 知识库配置错误: {e}")
        except Exception as e:
            logger.warning(f"[ContinuousWriter] 知识库初始化失败: {e}")

        _wire_character_manager(writer, pm)

    writer_key = _writer_key(project_id, session_id)
    lock = await _get_writer_lock(writer_key)
    async with lock:
        result = await writer.execute({
            "action": "start",
            "content": request.story_beginning,
            "trends_query": request.trends_query if request.enable_trends else "",
            "current_chapter": request.current_chapter,
            "recovered_chapters": request.recovered_chapters
        })

        # 仅在初始化成功后注册到内存，避免半初始化实例残留
        continuous_writers[writer_key] = writer

        await _refresh_infinite_memory(
            project_id=project_id,
            session_id=session_id,
            chapters=writer.get_all_chapters(),
            source_file="runtime_start",
            data_dir=pm.data_dir,
        )
        
        result["session_id"] = session_id
        result["project_id"] = project_id
        result["model_used"] = model_name
        
        return JSONResponse(result)


@router.post("/continuous-write/continue")
async def continue_continuous_write(request: ContinuousWriteContinueRequest):
    """继续续写下一章"""
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    session_id = _normalize_session_id(request.session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    writer_key = _writer_key(project_id, session_id)
    lock = await _get_writer_lock(writer_key)
    async with lock:
        session_store = get_session_store()
        if writer_key not in continuous_writers:
            existing_session = await session_store.aload(session_id, project_id)
            
            if existing_session and existing_session.chapters:
                logger.info(f"[ContinuousWrite] 从持久化存储恢复会话 {session_id}，已有 {len(existing_session.chapters)} 章")
                
                from ...agents import ContinuousWriter, ContinuousWriteConfig
                
                write_config = ContinuousWriteConfig(
                    words_per_chapter=existing_session.words_per_chapter,
                    auto_save_to_kb=True,
                    check_consistency=True
                )
                
                writer = ContinuousWriter(
                    write_config=write_config,
                    session_id=session_id,
                    project_id=project_id
                )

                if pm.current_project_id:
                    _wire_character_manager(writer, pm)

                _sync_writer_from_session(writer, existing_session)
                continuous_writers[writer_key] = writer
            else:
                raise HTTPException(status_code=404, detail="续写会话不存在，请先开始新故事")
        
        writer = continuous_writers[writer_key]

        if not getattr(writer, "_written_chapters", None):
            existing_session = await session_store.aload(session_id, project_id)
            if existing_session and existing_session.chapters:
                logger.info(
                    f"[ContinuousWrite] 运行态会话为空，已从持久化存储恢复 {len(existing_session.chapters)} 章"
                )
                _sync_writer_from_session(writer, existing_session)
            elif request.chapters:
                logger.info(
                    f"[ContinuousWrite] 运行态会话为空，已从客户端章节快照恢复 {len(request.chapters)} 章"
                )
                current_chapter = request.current_chapter
                if current_chapter <= 0:
                    current_chapter = max(
                        [int(ch.get("chapter_number", 0) or 0) for ch in request.chapters if isinstance(ch, dict)]
                        or [0]
                    )
                writer._apply_client_sync(request.chapters, current_chapter, [])
            else:
                return JSONResponse(
                    {"success": False, "error": "未找到可续写的章节数据，请刷新页面或重新同步会话后再试。"},
                    status_code=409,
                )

        if request.model or request.api_config_id:
            model_config, model_to_use = resolve_continuous_write_model_config(
                model=request.model,
                api_config_id=request.api_config_id,
            )
            if model_to_use:
                _apply_continuous_write_model_config(writer, model_config, model_to_use)

        execute_params = {
            "action": "continue",
            "content": request.inspiration
        }

        if request.enable_trends:
            execute_params["trends_query"] = request.inspiration or "热门话题"
            if request.trends_platforms:
                execute_params["trends_platforms"] = request.trends_platforms

        result = await writer.execute(execute_params)
        await _refresh_infinite_memory(
            project_id=project_id,
            session_id=session_id,
            chapters=writer.get_all_chapters(),
            source_file="runtime_continue",
            data_dir=pm.data_dir,
        )
        return JSONResponse(result)


@router.post("/continuous-write/inspiration")
async def add_inspiration(request: ContinuousWriteInspirationRequest):
    """添加灵感到续写"""
    session_id = _normalize_session_id(request.session_id)
    
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[writer_key]
        chapter = request.chapter if request.chapter > 0 else writer._current_chapter + 1
        
        result = writer._add_inspiration({
            "content": request.inspiration,
            "chapter": chapter
        })
        
        return JSONResponse(result)


@router.post("/continuous-write/correction")
async def add_correction(request: ContinuousWriteCorrectionRequest):
    """添加剧情纠正"""
    session_id = _normalize_session_id(request.session_id)
    
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[writer_key]
        chapter = request.chapter if request.chapter > 0 else writer._current_chapter + 1
        
        result = writer._add_correction({
            "content": request.correction,
            "chapter": chapter
        })
        
        return JSONResponse(result)


@router.post("/continuous-write/stop")
async def stop_continuous_write(session_id: str = "default"):
    """停止续写"""
    session_id = _normalize_session_id(session_id)
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[writer_key]
        result = writer._stop_writing()
        
        return JSONResponse(result)


@router.get("/continuous-write/status")
async def get_continuous_write_status(session_id: str = "default"):
    """获取续写状态"""
    session_id = _normalize_session_id(session_id)
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            return JSONResponse({
                "session_exists": False,
                "message": "没有活跃的续写会话"
            })
        
        writer = continuous_writers[writer_key]
        status = writer._get_status()
        status["session_exists"] = True
        
        return JSONResponse(status)


@router.get("/continuous-write/chapters")
async def get_continuous_write_chapters(session_id: str = "default"):
    """获取所有已写章节"""
    session_id = _normalize_session_id(session_id)
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[writer_key]
        chapters = writer.get_all_chapters()
        
        return JSONResponse({
            "success": True,
            "total": len(chapters),
            "chapters": chapters
        })


@router.get("/continuous-write/chapter/{chapter_number}")
async def get_continuous_write_chapter(chapter_number: int, session_id: str = "default"):
    """获取指定章节"""
    session_id = _normalize_session_id(session_id)
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)
    
    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[writer_key]
        result = writer._get_chapter(chapter_number)
        
        return JSONResponse(result)


@router.post("/continuous-write/export")
async def export_continuous_write(request: ContinuousWriteExportRequest, format: str = "txt"):
    normalized_format = (format or "txt").strip().lower()
    if normalized_format not in {"txt", "md", "docx"}:
        raise HTTPException(status_code=400, detail="导出格式仅支持 txt、md、docx。")

    title = _normalize_export_title(request.title)
    chapters = [chapter for chapter in request.chapters if isinstance(chapter, dict)]
    if normalized_format == "txt":
        content = _render_continuous_write_export_text(title, chapters)
        filename = f"{_safe_export_filename(title)}.txt"
        media_type = "text/plain; charset=utf-8"
        data = content.encode("utf-8")
    elif normalized_format == "md":
        content = _render_continuous_write_export_text(title, chapters)
        filename = f"{_safe_export_filename(title)}.md"
        media_type = "text/markdown; charset=utf-8"
        data = content.encode("utf-8")
    else:
        filename = f"{_safe_export_filename(title)}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        data = _build_continuous_write_docx_bytes(title, chapters)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return Response(content=data, media_type=media_type, headers=headers)


@router.put("/continuous-write/chapter")
async def update_continuous_write_chapter(request: UpdateInfiniteWriteChapterRequest, session_id: str = "default"):
    """更新无限续写章节"""
    session_id = _normalize_session_id(session_id)
    logger.info(f"[ContinuousWrite] 更新章节: index={request.chapter_index}, "
               f"title_changed={request.title is not None}, "
               f"content_changed={request.content is not None}")
    
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    writer_key = _writer_key(project_id, session_id)

    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key in continuous_writers:
            writer = continuous_writers[writer_key]
            chapters = writer._written_chapters
            
            if 0 <= request.chapter_index < len(chapters):
                chapter = chapters[request.chapter_index]
                
                if request.title is not None:
                    chapter["title"] = request.title
                
                if request.content is not None:
                    chapter["content"] = request.content
                    chapter["word_count"] = len(re.sub(r'\s+', '', request.content))
                    chapter["summary"] = request.content[:200] + "..." if len(request.content) > 200 else request.content

                await _refresh_infinite_memory(
                    project_id=project_id,
                    session_id=session_id,
                    chapters=writer.get_all_chapters(),
                    source_file="runtime_update",
                    data_dir=pm.data_dir,
                )
                
                return JSONResponse({
                    "success": True,
                    "message": "章节已更新",
                    "chapter": chapter
                })
        
        return JSONResponse({
            "success": False,
            "message": "更新失败：会话不存在或章节索引越界"
        }, status_code=404)


@router.post("/continuous-write/sync")
async def sync_continuous_write(request: ContinuousWriteSyncRequest):
    """同步前端的章节列表到后端会话"""
    from ...agents.session_store import get_session_store, SessionState
    from ...project_manager import get_project_manager
    
    session_id = _normalize_session_id(request.session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    deleted_numbers = [n for n in request.deleted_chapters if isinstance(n, int)]
    writer_key = _writer_key(project_id, session_id)

    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key in continuous_writers:
            writer = continuous_writers[writer_key]
            existing_numbers = _chapter_numbers_from_payload(writer.get_all_chapters())
            effective_deleted_numbers = deleted_numbers
            if not effective_deleted_numbers and not request.chapters and request.current_chapter <= 0:
                effective_deleted_numbers = existing_numbers

            result = writer._apply_client_sync(request.chapters, request.current_chapter, effective_deleted_numbers)
            await _refresh_infinite_memory(
                project_id=project_id,
                session_id=session_id,
                chapters=writer.get_all_chapters(),
                source_file="runtime_sync",
                data_dir=pm.data_dir,
            )
            if effective_deleted_numbers and not getattr(writer, "knowledge_base", None):
                _delete_project_knowledge_chapters(project_id, pm.data_dir, effective_deleted_numbers)
            return JSONResponse(result)
    
    session_store = get_session_store()
    state = await session_store.aload(session_id, project_id)
    if not state:
        state = SessionState(session_id=session_id, project_id=project_id)
    
    existing_numbers = _chapter_numbers_from_payload(state.chapters)
    state.chapters = request.chapters
    if request.current_chapter > 0:
        state.current_chapter = request.current_chapter
    else:
        last_num = 0
        if request.chapters:
            last_num = max([c.get("chapter_number", 0) for c in request.chapters if isinstance(c, dict)] or [0])
        state.current_chapter = last_num

    if not request.chapters and state.current_chapter == 0:
        _clear_continuous_write_session_memory(state)
    
    await session_store.asave(state)
    await _refresh_infinite_memory(
        project_id=project_id,
        session_id=session_id,
        chapters=[c for c in request.chapters if isinstance(c, dict)],
        source_file="runtime_sync",
        data_dir=pm.data_dir,
    )
    
    # 清理被删除章节的知识库数据；清空章节列表时，即使前端没带 deleted_chapters，也清理旧章节向量。
    effective_deleted_numbers = deleted_numbers
    if not effective_deleted_numbers and not request.chapters and state.current_chapter == 0:
        effective_deleted_numbers = existing_numbers
    deleted_knowledge_chapters = _delete_project_knowledge_chapters(
        project_id,
        pm.data_dir,
        effective_deleted_numbers,
    )
    
    return JSONResponse({
        "success": True,
        "message": "会话已同步",
        "current_chapter": state.current_chapter,
        "deleted_knowledge_chapters": deleted_knowledge_chapters,
    })


@router.post("/continuous-write/regenerate")
async def regenerate_continuous_write(request: ContinuousWriteRegenerateRequest):
    """重新生成指定章节"""
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    session_id = _normalize_session_id(request.session_id)
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    writer_key = _writer_key(project_id, session_id)

    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            session_store = get_session_store()
            existing_session = await session_store.aload(session_id, project_id)
            
            if existing_session and existing_session.chapters:
                logger.info(f"[ContinuousWrite] 从持久化存储恢复会话 {session_id}")
                
                from ...agents import ContinuousWriter, ContinuousWriteConfig
                
                write_config = ContinuousWriteConfig(
                    words_per_chapter=existing_session.words_per_chapter,
                    auto_save_to_kb=True,
                    check_consistency=True
                )
                
                writer = ContinuousWriter(
                    write_config=write_config,
                    session_id=session_id,
                    project_id=project_id
                )

                if pm.current_project_id:
                    _wire_character_manager(writer, pm)

                continuous_writers[writer_key] = writer
            else:
                raise HTTPException(status_code=404, detail="续写会话不存在，请先开始新故事")
        
        writer = continuous_writers[writer_key]
    
    if request.model or request.api_config_id:
        model_config, model_to_use = resolve_continuous_write_model_config(
            model=request.model,
            api_config_id=request.api_config_id,
        )
        if model_to_use:
            _apply_continuous_write_model_config(writer, model_config, model_to_use)
    
    execute_params = {
        "action": "regenerate",
        "chapter_number": request.chapter_number,
        "content": request.inspiration
    }
    
    if request.enable_trends:
        execute_params["trends_query"] = request.inspiration or "热门话题"
        if request.trends_platforms:
            execute_params["trends_platforms"] = request.trends_platforms

    result = await writer.execute(execute_params)
    await _refresh_infinite_memory(
        project_id=project_id,
        session_id=session_id,
        chapters=writer.get_all_chapters(),
        source_file="runtime_regenerate",
        data_dir=pm.data_dir,
    )
    return JSONResponse(result)


@router.post("/text/regex-replace")
async def regex_replace(request: RegexReplaceRequest):
    """执行正则替换"""
    try:
        regex_flags = 0
        if 'i' in request.flags:
            regex_flags |= re.IGNORECASE
        if 'm' in request.flags:
            regex_flags |= re.MULTILINE
        if 's' in request.flags:
            regex_flags |= re.DOTALL
        
        pattern = re.compile(request.pattern, regex_flags)
        
        matches = list(pattern.finditer(request.content))
        match_count = len(matches)
        
        if 'g' in request.flags or not request.flags:
            new_content = pattern.sub(request.replacement, request.content)
        else:
            new_content = pattern.sub(request.replacement, request.content, count=1)
        
        return JSONResponse({
            "success": True,
            "new_content": new_content,
            "match_count": match_count,
            "replaced": match_count > 0
        })
        
    except re.error as e:
        return JSONResponse({
            "success": False,
            "error": f"无效的正则表达式: {str(e)}",
            "new_content": request.content,
            "match_count": 0
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"替换失败: {str(e)}",
            "new_content": request.content,
            "match_count": 0
        })


@router.post("/text/regex-find")
async def regex_find(request: RegexReplaceRequest):
    """正则查找（预览匹配结果）"""
    try:
        regex_flags = 0
        if 'i' in request.flags:
            regex_flags |= re.IGNORECASE
        if 'm' in request.flags:
            regex_flags |= re.MULTILINE
        if 's' in request.flags:
            regex_flags |= re.DOTALL
        
        pattern = re.compile(request.pattern, regex_flags)
        
        matches = []
        for match in pattern.finditer(request.content):
            start = max(0, match.start() - 30)
            end = min(len(request.content), match.end() + 30)
            context = request.content[start:end]
            
            matches.append({
                "match": match.group(),
                "start": match.start(),
                "end": match.end(),
                "context": context,
                "line": request.content[:match.start()].count('\n') + 1
            })
        
        return JSONResponse({
            "success": True,
            "matches": matches[:100],
            "total_count": len(matches)
        })
        
    except re.error as e:
        return JSONResponse({
            "success": False,
            "error": f"无效的正则表达式: {str(e)}",
            "matches": [],
            "total_count": 0
        })


@router.delete("/continuous-write/session")
async def delete_continuous_write_session(session_id: str = "default"):
    """删除续写会话"""
    session_id = _normalize_session_id(session_id)
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    deleted_memory = False
    deleted_storage = False
    
    writer_key = _writer_key(project_id, session_id)
    lock = await _get_writer_lock(writer_key)
    async with lock:
        deleted_chapter_numbers: List[int] = []
        if writer_key in continuous_writers:
            writer = continuous_writers[writer_key]
            deleted_chapter_numbers.extend(_chapter_numbers_from_payload(writer.get_all_chapters()))
            del continuous_writers[writer_key]
            deleted_memory = True
        
        session_store = get_session_store()
        state = await session_store.aload(session_id, project_id)
        if state:
            deleted_chapter_numbers.extend(_chapter_numbers_from_payload(state.chapters))
        if await session_store.aexists(session_id, project_id):
            await session_store.adelete(session_id, project_id)
            deleted_storage = True

        if deleted_memory and not deleted_storage:
            # 仅内存态时，释放锁容器项
            _continuous_writer_locks.pop(writer_key, None)

    deleted_knowledge_chapters = _delete_project_knowledge_chapters(
        project_id,
        pm.data_dir,
        deleted_chapter_numbers,
    )

    try:
        from ...novel_import_service import get_novel_import_service

        get_novel_import_service(data_dir=pm.data_dir).delete_infinite_memory(project_id, session_id)
    except Exception as exc:
        logger.warning(f"[ContinuousWrite] Failed to delete isolated memory: {exc}")
    
    if deleted_memory or deleted_storage:
        return JSONResponse({
            "success": True,
            "message": "会话已删除",
            "deleted_from_memory": deleted_memory,
            "deleted_from_storage": deleted_storage,
            "deleted_knowledge_chapters": deleted_knowledge_chapters
        })
    
    return JSONResponse({"success": False, "message": "会话不存在"})


@router.get("/continuous-write/sessions")
async def list_continuous_write_sessions():
    """列出所有持久化的续写会话"""
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    session_store = get_session_store()
    sessions = session_store.list_sessions(project_id)
    
    for session in sessions:
        key = _writer_key(project_id, session["session_id"])
        session["active_in_memory"] = key in continuous_writers
    
    return JSONResponse({
        "success": True,
        "sessions": sessions,
        "project_id": project_id
    })


@router.get("/continuous-write/session/{session_id}/context")
async def get_continuous_write_context(session_id: str):
    """获取续写会话的上下文信息"""
    session_id = _normalize_session_id(session_id)
    from ...agents.session_store import get_session_store
    from ...project_manager import get_project_manager
    
    pm = get_project_manager()
    project_id = pm.current_project_id or ""
    
    session_store = get_session_store()
    context = await session_store.aget_context_for_continuation(session_id, project_id)
    
    if not context:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return JSONResponse({
        "success": True,
        "context": context
    })


@router.post("/continuous-write/dead-character")
async def add_dead_character(request: AddDeadCharacterRequest):
    """手动添加死亡角色"""
    session_id = _normalize_session_id(request.session_id)
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    writer_key = _writer_key(pm.current_project_id or "", session_id)

    lock = await _get_writer_lock(writer_key)
    async with lock:
        if writer_key not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")

        writer = continuous_writers[writer_key]
        result = writer._add_dead_character(request.character_name)
        
        return JSONResponse(result)
