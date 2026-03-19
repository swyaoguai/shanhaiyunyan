"""Project management API routes."""

import json
import shutil
import tempfile
import zipfile
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..models.requests import (
    ProjectCreateRequest,
    ProjectStateBatchGetRequest,
    ProjectStateBatchSetRequest,
    ProjectUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BACKUP_UPLOAD_MAX_BYTES = 100 * 1024 * 1024
BACKUP_UPLOAD_CHUNK_BYTES = 1024 * 1024
BACKUP_EXTRACT_MAX_TOTAL_BYTES = 500 * 1024 * 1024
BACKUP_EXTRACT_MAX_FILES = 10000
BACKUP_EXTRACT_MAX_COMPRESSION_RATIO = 200
NOVEL_IMPORT_MAX_BYTES = 20 * 1024 * 1024


def _is_path_within(base_dir: Path, target_path: Path) -> bool:
    resolved_base = base_dir.resolve()
    resolved_target = target_path.resolve()
    try:
        return resolved_target.is_relative_to(resolved_base)
    except AttributeError:
        return str(resolved_target).startswith(str(resolved_base))


def _get_backup_targets() -> dict:
    from ...constants import get_app_root, get_data_dir

    app_root = Path(get_app_root())
    root_data_dir = Path(get_data_dir())
    package_data_dir = Path(__file__).resolve().parents[2] / "data"

    return {
        "app_root": app_root,
        "root_data_dir": root_data_dir,
        "package_data_dir": package_data_dir,
        "env_file": app_root / ".env",
    }


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()

            if len(members) > BACKUP_EXTRACT_MAX_FILES:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件数量超过限制（最多 {BACKUP_EXTRACT_MAX_FILES} 个）",
                )

            declared_total_size = 0
            validated_members = []

            for member in members:
                member_path = (target_dir / member.filename).resolve()
                if not _is_path_within(target_dir, member_path):
                    raise HTTPException(status_code=400, detail=f"非法压缩包路径: {member.filename}")

                declared_total_size += max(0, member.file_size)
                if declared_total_size > BACKUP_EXTRACT_MAX_TOTAL_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"解压后文件总大小超过限制（最大 "
                            f"{BACKUP_EXTRACT_MAX_TOTAL_BYTES // (1024 * 1024)}MB）"
                        ),
                    )

                if member.compress_size > 0:
                    compression_ratio = member.file_size / member.compress_size
                    if compression_ratio > BACKUP_EXTRACT_MAX_COMPRESSION_RATIO:
                        raise HTTPException(
                            status_code=400,
                            detail=f"压缩包存在异常高压缩比文件: {member.filename}",
                        )

                validated_members.append((member, member_path))

            extracted_total_size = 0
            for member, member_path in validated_members:
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue

                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as source, member_path.open("wb") as destination:
                    while True:
                        chunk = source.read(BACKUP_UPLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        extracted_total_size += len(chunk)
                        if extracted_total_size > BACKUP_EXTRACT_MAX_TOTAL_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail=(
                                    f"解压后文件总大小超过限制（最大 "
                                    f"{BACKUP_EXTRACT_MAX_TOTAL_BYTES // (1024 * 1024)}MB）"
                                ),
                            )
                        destination.write(chunk)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="备份文件不是有效的ZIP格式") from exc


def _require_current_project(pm) -> None:
    if not pm.current_project_id:
        raise ValueError("请先选择或创建一个项目")


def _copy_dir_contents(src: Path, dst: Path, overwrite: bool) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for file in src.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not target.exists():
            shutil.copy2(file, target)


@router.get("/projects")
async def list_projects():
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    return JSONResponse({
        "projects": pm.list_projects(),
        "current_project_id": pm.current_project_id,
    })


@router.post("/projects")
async def create_project(request: ProjectCreateRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project = pm.create_project(request.name, request.description)
    return JSONResponse({
        "success": True,
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
        },
    })


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project = pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return JSONResponse({
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at,
        "word_count": project.word_count,
        "chapter_count": project.chapter_count,
    })


@router.post("/projects/{project_id}/switch")
async def switch_project(project_id: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if pm.switch_project(project_id):
        return JSONResponse({"success": True})
    raise HTTPException(status_code=404, detail="Project not found")


@router.put("/projects/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    project = pm.update_project(project_id, **updates)
    if project:
        return JSONResponse({"success": True})
    raise HTTPException(status_code=404, detail="Project not found")


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if pm.delete_project(project_id):
        return JSONResponse({"success": True})
    raise HTTPException(status_code=400, detail="Cannot delete project")


@router.get("/project-data/{data_type}")
async def get_project_data(data_type: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"data": [], "error": "请先选择或创建一个项目", "no_project": True})

    try:
        return JSONResponse({"data": pm.load_project_data(data_type)})
    except ValueError as e:
        return JSONResponse({"data": [], "error": str(e)})


@router.post("/project-data/{data_type}")
async def save_project_data(data_type: str, request: Request):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    try:
        body = await request.json()
        data_rows = body.get("data", [])
        pm.save_project_data(data_type, data_rows)

        if data_type == "outline":
            try:
                from ...novel_import_service import get_novel_import_service

                import_service = get_novel_import_service(data_dir=pm.data_dir)
                chapters = import_service.chapters_from_outline(
                    data_rows if isinstance(data_rows, list) else []
                )
                import_service.refresh_collab_memory(
                    project_id=pm.current_project_id or "",
                    chapters=chapters,
                    source_file="project_outline",
                )
            except Exception as exc:
                logger.warning(f"[Projects] Failed to refresh collaborative memory: {exc}")

        return JSONResponse({"success": True})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


@router.post("/projects/import-novel")
async def import_novel_to_collab_mode(
    novel_file: UploadFile = File(...),
    merge_mode: str = Form("append"),
):
    """Import txt/md/docx novel file into collaborative mode and auto-build memory."""
    from ...project_manager import get_project_manager
    from ...novel_import_service import get_novel_import_service

    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择或创建一个项目"}, status_code=400)

    normalized_merge_mode = (merge_mode or "append").strip().lower()
    if normalized_merge_mode not in {"append", "replace"}:
        return JSONResponse({"success": False, "error": "merge_mode 仅支持 append/replace"}, status_code=400)

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

    outline = [] if normalized_merge_mode == "replace" else pm.load_project_data("outline")
    if not isinstance(outline, list):
        outline = []

    imported_items = []
    for chapter in parsed["chapters"]:
        imported_items.append(
            {
                "title": chapter.get("title") or f"第{chapter.get('chapter_number', len(outline) + 1)}章",
                "summary": chapter.get("summary", ""),
                "content": chapter.get("content", ""),
                "word_count": chapter.get("word_count", 0),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_from": "collab_import",
                "source_file": parsed["filename"],
            }
        )

    outline.extend(imported_items)
    pm.save_project_data("outline", outline)

    chapters = import_service.chapters_from_outline(outline)
    memory = import_service.refresh_collab_memory(
        project_id=pm.current_project_id or "",
        chapters=chapters,
        source_file=parsed["filename"],
    )

    return JSONResponse(
        {
            "success": True,
            "mode": "collab_write",
            "project_id": pm.current_project_id,
            "filename": parsed["filename"],
            "merge_mode": normalized_merge_mode,
            "imported_chapters": len(parsed["chapters"]),
            "total_chapters": len(outline),
            "total_words": sum(ch.get("word_count", 0) for ch in parsed["chapters"]),
            "memory_summary": {
                "chapter_cards": len(memory.get("chapter_cards", [])),
                "issue_cards": len(memory.get("issue_cards", [])),
                "edit_tasks": len(memory.get("edit_tasks", [])),
            },
        }
    )


@router.post("/project-state/batch-get")
async def batch_get_project_state(request: ProjectStateBatchGetRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    states = {}
    for state_key in request.keys[:100]:
        try:
            states[state_key] = pm.load_project_state(state_key, default=None)
        except ValueError:
            return JSONResponse(
                {"success": False, "error": f"Invalid project state key: {state_key}"},
                status_code=400,
            )

    return JSONResponse({"success": True, "states": states})


@router.post("/project-state/batch-set")
async def batch_set_project_state(request: ProjectStateBatchSetRequest):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    saved_keys = []
    for state_key, data in request.states.items():
        try:
            pm.save_project_state(state_key, data)
            saved_keys.append(state_key)
        except ValueError:
            return JSONResponse(
                {"success": False, "error": f"Invalid project state key: {state_key}"},
                status_code=400,
            )

    return JSONResponse({"success": True, "saved_keys": saved_keys})


@router.get("/project-state/{state_key}")
async def get_project_state(state_key: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        data = pm.load_project_state(state_key, default=None)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key, "data": data})


@router.post("/project-state/{state_key}")
async def save_project_state(state_key: str, request: Request):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        body = await request.json()
        pm.save_project_state(state_key, body.get("data"))
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key})


@router.delete("/project-state/{state_key}")
async def delete_project_state(state_key: str):
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    try:
        _require_current_project(pm)
        deleted = pm.delete_project_state(state_key)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    return JSONResponse({"success": True, "state_key": state_key, "deleted": deleted})


@router.get("/projects/backup/export")
async def export_backup():
    targets = _get_backup_targets()
    app_root = targets["app_root"]

    backup_dir = app_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"novel-agent-backup-{timestamp}.zip"
    backup_path = backup_dir / backup_name

    manifest = {
        "backup_version": "1.0",
        "created_at": datetime.now().isoformat(),
        "includes": {
            "root_data_dir": str(targets["root_data_dir"]),
            "package_data_dir": str(targets["package_data_dir"]),
            "env_file": targets["env_file"].exists(),
        },
    }

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        if targets["root_data_dir"].exists():
            for file in targets["root_data_dir"].rglob("*"):
                if file.is_file():
                    rel = file.relative_to(targets["root_data_dir"])
                    zf.write(file, f"root_data/{rel.as_posix()}")

        if targets["package_data_dir"].exists():
            for file in targets["package_data_dir"].rglob("*"):
                if file.is_file():
                    rel = file.relative_to(targets["package_data_dir"])
                    zf.write(file, f"package_data/{rel.as_posix()}")

        if targets["env_file"].exists():
            zf.write(targets["env_file"], "env/.env")

    return FileResponse(
        path=str(backup_path),
        media_type="application/zip",
        filename=backup_name,
    )


@router.post("/projects/backup/import")
async def import_backup(
    backup_file: UploadFile = File(...),
    overwrite: bool = Form(False),
):
    filename = (backup_file.filename or "").lower()
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持zip备份文件")

    targets = _get_backup_targets()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        zip_path = temp_dir_path / "backup.zip"

        uploaded_size = 0
        with zip_path.open("wb") as output:
            while True:
                chunk = await backup_file.read(BACKUP_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                uploaded_size += len(chunk)
                if uploaded_size > BACKUP_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"备份文件超过大小限制（最大 {BACKUP_UPLOAD_MAX_BYTES // (1024 * 1024)}MB）",
                    )
                output.write(chunk)

        if uploaded_size == 0:
            raise HTTPException(status_code=400, detail="备份文件为空")

        extract_dir = temp_dir_path / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(zip_path, extract_dir)

        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=400, detail="备份文件缺少 manifest.json，格式不受支持")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="manifest.json 解析失败")

        source_root_data = extract_dir / "root_data"
        source_package_data = extract_dir / "package_data"

        root_data_dst = targets["root_data_dir"]
        package_data_dst = targets["package_data_dir"]

        root_data_dst.parent.mkdir(parents=True, exist_ok=True)
        package_data_dst.parent.mkdir(parents=True, exist_ok=True)

        if overwrite:
            if source_root_data.exists():
                if root_data_dst.exists():
                    shutil.rmtree(root_data_dst)
                shutil.copytree(source_root_data, root_data_dst)
            if source_package_data.exists():
                if package_data_dst.exists():
                    shutil.rmtree(package_data_dst)
                shutil.copytree(source_package_data, package_data_dst)
        else:
            _copy_dir_contents(source_root_data, root_data_dst, overwrite=False)
            _copy_dir_contents(source_package_data, package_data_dst, overwrite=False)

        source_env = extract_dir / "env" / ".env"
        if source_env.exists() and (overwrite or not targets["env_file"].exists()):
            targets["env_file"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_env, targets["env_file"])

        from ...project_manager import get_project_manager

        get_project_manager()._load_projects()

        return JSONResponse({
            "success": True,
            "message": "备份导入成功，已刷新项目状态",
            "overwrite": overwrite,
            "manifest": manifest,
        })
