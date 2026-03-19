"""
备份管理API

提供项目备份、导出、导入和恢复的Web接口
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from novel_agent.utils.backup import get_backup_service
from novel_agent.project_manager import get_project_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])


# ===== 请求模型 =====

class CreateBackupRequest(BaseModel):
    """创建备份请求"""
    project_id: str = Field(..., description="项目ID")
    backup_type: str = Field("full", description="备份类型: full/partial")
    include_items: Optional[list[str]] = Field(None, description="要包含的项目(partial时使用)")
    local_storage_data: Optional[dict] = Field(None, description="localStorage数据")


class RestoreBackupRequest(BaseModel):
    """恢复备份请求"""
    backup_id: str = Field(..., description="备份ID")
    target_project_id: Optional[str] = Field(None, description="目标项目ID(可选)")
    overwrite: bool = Field(False, description="是否覆盖现有文件")


# ===== API端点 =====

@router.post("/create")
async def create_backup(request: CreateBackupRequest):
    """
    创建项目备份
    
    - **project_id**: 项目ID
    - **backup_type**: 备份类型(full/partial)
    - **include_items**: 要包含的项目列表(partial时使用)
    """
    try:
        backup_service = get_backup_service()
        project_manager = get_project_manager()
        
        # 获取项目信息
        project = project_manager.get_project(request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 创建备份
        result = backup_service.create_backup(
            project_id=request.project_id,
            project_name=project.name,
            backup_type=request.backup_type,
            include_items=request.include_items,
            local_storage_data=request.local_storage_data
        )
        
        return {
            "success": True,
            "message": "备份创建成功",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_backups():
    """
    列出所有备份
    
    返回所有可用备份的列表
    """
    try:
        backup_service = get_backup_service()
        backups = backup_service.list_backups()
        
        return {
            "success": True,
            "backups": backups,
            "count": len(backups)
        }
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info/{backup_id}")
async def get_backup_info(backup_id: str):
    """
    获取备份详细信息
    
    - **backup_id**: 备份ID
    """
    try:
        backup_service = get_backup_service()
        info = backup_service.get_backup_info(backup_id)
        
        if not info:
            raise HTTPException(status_code=404, detail="Backup not found")
        
        return {
            "success": True,
            "data": info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore")
async def restore_backup(request: RestoreBackupRequest):
    """
    恢复备份
    
    - **backup_id**: 备份ID
    - **target_project_id**: 目标项目ID(可选,默认使用原项目ID)
    - **overwrite**: 是否覆盖现有文件
    """
    try:
        backup_service = get_backup_service()
        
        result = backup_service.restore_backup(
            backup_id=request.backup_id,
            target_project_id=request.target_project_id,
            overwrite=request.overwrite
        )
        
        return {
            "success": True,
            "message": "备份恢复成功",
            "data": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{backup_id}")
async def delete_backup(backup_id: str):
    """
    删除备份
    
    - **backup_id**: 备份ID
    """
    try:
        backup_service = get_backup_service()
        success = backup_service.delete_backup(backup_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Backup not found")
        
        return {
            "success": True,
            "message": "备份删除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{backup_id}")
async def download_backup(backup_id: str):
    """
    下载备份文件
    
    - **backup_id**: 备份ID
    """
    try:
        backup_service = get_backup_service()
        info = backup_service.get_backup_info(backup_id)
        
        if not info:
            raise HTTPException(status_code=404, detail="Backup not found")
        
        backup_path = Path(info["backup_path"])
        
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        # 生成下载文件名
        project_name = info.get("project_name", "project")
        filename = f"{project_name}_backup_{backup_id}.zip"
        
        return FileResponse(
            path=backup_path,
            filename=filename,
            media_type="application/zip"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_backup(file: UploadFile = File(...)):
    """
    导入备份文件
    
    上传一个备份ZIP文件并导入到系统中
    """
    try:
        backup_service = get_backup_service()
        
        # 保存上传的文件到临时位置
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)
        
        try:
            # 导入备份
            backup_id = backup_service.import_backup(tmp_path)
            
            # 获取导入的备份信息
            info = backup_service.get_backup_info(backup_id)
            
            return {
                "success": True,
                "message": "备份导入成功",
                "data": {
                    "backup_id": backup_id,
                    "info": info
                }
            }
            
        finally:
            # 清理临时文件
            if tmp_path.exists():
                tmp_path.unlink()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to import backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 模块职责说明：提供项目备份、导出、导入和恢复的Web API接口