"""
资料库管理API

提供项目资料文件的上传、管理和访问接口
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse

from novel_agent.utils.resource_manager import get_resource_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


# ===== API端点 =====

@router.post("/upload")
async def upload_resource(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    file_type: Optional[str] = Form(None),
    description: str = Form(""),
    tags: Optional[str] = Form(None)
):
    """
    上传资料文件
    
    - **project_id**: 项目ID
    - **file**: 文件
    - **file_type**: 文件类型(document/reference/image/other,可选)
    - **description**: 描述
    - **tags**: 标签(逗号分隔)
    """
    try:
        resource_manager = get_resource_manager()
        
        # 保存上传的文件到临时位置
        import tempfile
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)
        
        try:
            # 解析标签
            tag_list = [t.strip() for t in tags.split(",")] if tags else []
            
            # 添加资料
            resource = resource_manager.add_resource(
                project_id=project_id,
                source_path=tmp_path,
                file_type=file_type,
                description=description,
                tags=tag_list
            )
            
            return {
                "success": True,
                "message": "资料上传成功",
                "data": resource.to_dict()
            }
            
        finally:
            # 清理临时文件
            if tmp_path.exists():
                tmp_path.unlink()
        
    except Exception as e:
        logger.error(f"Failed to upload resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_resources(
    project_id: Optional[str] = Query(None, description="项目ID"),
    file_type: Optional[str] = Query(None, description="文件类型过滤"),
    tags: Optional[str] = Query(None, description="标签过滤(逗号分隔)")
):
    """
    列出项目资料
    
    - **project_id**: 项目ID(可选,默认使用当前项目)
    - **file_type**: 文件类型过滤(可选)
    - **tags**: 标签过滤(可选,逗号分隔)
    """
    try:
        # 如果没有提供project_id,使用当前项目
        if not project_id:
            from novel_agent.project_manager import get_project_manager
            pm = get_project_manager()
            project_id = pm.current_project_id
            
            if not project_id:
                return {
                    "success": True,
                    "resources": [],
                    "count": 0
                }
        
        resource_manager = get_resource_manager()
        
        # 解析标签
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        
        resources = resource_manager.list_resources(
            project_id=project_id,
            file_type=file_type,
            tags=tag_list
        )
        
        return {
            "success": True,
            "resources": [r.to_dict() for r in resources],
            "count": len(resources)
        }
        
    except Exception as e:
        logger.error(f"Failed to list resources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info/{project_id}/{file_id}")
async def get_resource_info(project_id: str, file_id: str):
    """
    获取资料详细信息
    
    - **project_id**: 项目ID
    - **file_id**: 文件ID
    """
    try:
        resource_manager = get_resource_manager()
        resource = resource_manager.get_resource(project_id, file_id)
        
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return {
            "success": True,
            "data": resource.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get resource info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update/{project_id}/{file_id}")
async def update_resource(
    project_id: str,
    file_id: str,
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None)
):
    """
    更新资料信息
    
    - **project_id**: 项目ID
    - **file_id**: 文件ID
    - **description**: 描述(可选)
    - **tags**: 标签(可选,逗号分隔)
    """
    try:
        resource_manager = get_resource_manager()
        
        # 解析标签
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        
        resource = resource_manager.update_resource(
            project_id=project_id,
            file_id=file_id,
            description=description,
            tags=tag_list
        )
        
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return {
            "success": True,
            "message": "资料更新成功",
            "data": resource.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{project_id}/{file_id}")
async def delete_resource(project_id: str, file_id: str):
    """
    删除资料
    
    - **project_id**: 项目ID
    - **file_id**: 文件ID
    """
    try:
        resource_manager = get_resource_manager()
        success = resource_manager.delete_resource(project_id, file_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return {
            "success": True,
            "message": "资料删除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{project_id}/{file_id}")
async def download_resource(project_id: str, file_id: str):
    """
    下载资料文件
    
    - **project_id**: 项目ID
    - **file_id**: 文件ID
    """
    try:
        resource_manager = get_resource_manager()
        
        # 获取资料信息
        resource = resource_manager.get_resource(project_id, file_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        # 获取文件路径
        file_path = resource_manager.get_resource_path(project_id, file_id)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="Resource file not found")
        
        return FileResponse(
            path=file_path,
            filename=resource.original_filename,
            media_type=resource.mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_resource_statistics(project_id: Optional[str] = Query(None, description="项目ID")):
    """
    获取资料库统计信息
    
    - **project_id**: 项目ID(可选,默认使用当前项目)
    """
    try:
        # 如果没有提供project_id,使用当前项目
        if not project_id:
            from novel_agent.project_manager import get_project_manager
            pm = get_project_manager()
            project_id = pm.current_project_id
            
            if not project_id:
                return {
                    "success": True,
                    "total_count": 0,
                    "total_size": 0,
                    "by_type": {}
                }
        
        resource_manager = get_resource_manager()
        stats = resource_manager.get_statistics(project_id)
        
        return {
            "success": True,
            **stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get resource statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 模块职责说明：提供项目资料文件的上传、管理和访问Web API接口