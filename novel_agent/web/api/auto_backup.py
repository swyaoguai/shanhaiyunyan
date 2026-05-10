"""
自动备份API

提供自动备份配置和管理的Web接口
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from novel_agent.utils.auto_backup import get_auto_backup_service, BackupSchedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auto-backup", tags=["auto-backup"])


# ===== 请求模型 =====

class AutoBackupConfigUpdate(BaseModel):
    """自动备份配置更新"""
    enabled: Optional[bool] = Field(None, description="是否启用自动备份")
    schedule: Optional[str] = Field(None, description="备份计划: disabled/on_exit/daily/weekly/custom")
    daily_time: Optional[str] = Field(None, description="每天备份时间 (HH:MM)")
    weekly_day: Optional[int] = Field(None, description="每周备份日期 (0=周一, 6=周日)")
    weekly_time: Optional[str] = Field(None, description="每周备份时间 (HH:MM)")
    custom_interval_hours: Optional[int] = Field(None, description="自定义间隔(小时)")
    max_backups: Optional[int] = Field(None, description="最多保留备份数")
    backup_on_exit: Optional[bool] = Field(None, description="退出时备份")
    include_knowledge_base: Optional[bool] = Field(None, description="包含知识库")


# ===== API端点 =====

@router.get("/config")
async def get_auto_backup_config():
    """
    获取自动备份配置
    
    返回当前的自动备份设置
    """
    try:
        service = get_auto_backup_service()
        config = service.get_config()
        
        return {
            "success": True,
            "data": config
        }
        
    except Exception as e:
        logger.error(f"Failed to get auto backup config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_auto_backup_config(updates: AutoBackupConfigUpdate):
    """
    更新自动备份配置
    
    - **enabled**: 是否启用自动备份
    - **schedule**: 备份计划类型
    - **daily_time**: 每天备份时间
    - **weekly_day**: 每周备份日期
    - **weekly_time**: 每周备份时间
    - **custom_interval_hours**: 自定义间隔
    - **max_backups**: 最多保留备份数
    - **backup_on_exit**: 退出时是否备份
    - **include_knowledge_base**: 是否包含知识库
    """
    try:
        service = get_auto_backup_service()
        
        # 只更新提供的字段
        if hasattr(updates, "model_dump"):
            update_dict = updates.model_dump(exclude_unset=True)
        else:
            update_dict = updates.dict(exclude_unset=True)
        
        # 验证schedule值
        if "schedule" in update_dict:
            try:
                BackupSchedule(update_dict["schedule"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid schedule value. Must be one of: {[s.value for s in BackupSchedule]}"
                )
        
        # 验证时间格式
        for time_field in ["daily_time", "weekly_time"]:
            if time_field in update_dict:
                time_str = update_dict[time_field]
                try:
                    hour, minute = map(int, time_str.split(":"))
                    if not (0 <= hour < 24 and 0 <= minute < 60):
                        raise ValueError
                except:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid time format for {time_field}. Use HH:MM format."
                    )
        
        # 验证weekly_day
        if "weekly_day" in update_dict:
            if not (0 <= update_dict["weekly_day"] <= 6):
                raise HTTPException(
                    status_code=400,
                    detail="weekly_day must be between 0 (Monday) and 6 (Sunday)"
                )
        
        # 更新配置
        config = service.update_config(update_dict)
        
        return {
            "success": True,
            "message": "自动备份配置已更新",
            "data": config
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update auto backup config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/toggle")
async def toggle_auto_backup(updates: AutoBackupConfigUpdate):
    """
    切换自动备份启用状态

    兼容旧版前端调用的 `/auto-backup/toggle` 接口。
    """
    if updates.enabled is None:
        raise HTTPException(status_code=400, detail="enabled is required")

    response = await update_auto_backup_config(AutoBackupConfigUpdate(enabled=updates.enabled))
    response["message"] = "自动备份已启用" if updates.enabled else "自动备份已禁用"
    return response


@router.post("/start")
async def start_auto_backup():
    """
    启动自动备份服务
    
    手动启动自动备份服务
    """
    try:
        service = get_auto_backup_service()
        await service.start()
        
        return {
            "success": True,
            "message": "自动备份服务已启动"
        }
        
    except Exception as e:
        logger.error(f"Failed to start auto backup service: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_auto_backup():
    """
    停止自动备份服务
    
    手动停止自动备份服务
    """
    try:
        service = get_auto_backup_service()
        await service.stop()
        
        return {
            "success": True,
            "message": "自动备份服务已停止"
        }
        
    except Exception as e:
        logger.error(f"Failed to stop auto backup service: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backup-now")
async def backup_now():
    """
    立即执行备份
    
    手动触发一次备份
    """
    try:
        service = get_auto_backup_service()
        await service._perform_backup()
        
        return {
            "success": True,
            "message": "备份已完成"
        }
        
    except Exception as e:
        logger.error(f"Failed to perform backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_auto_backup_status():
    """
    获取自动备份服务状态
    
    返回服务是否运行、最后备份时间等信息
    """
    try:
        service = get_auto_backup_service()
        config = service.get_config()
        
        # 计算下次备份时间
        next_backup_time = service._calculate_next_backup_time()
        
        return {
            "success": True,
            "data": {
                "running": service._running,
                "enabled": config.get("enabled", False),
                "schedule": config.get("schedule"),
                "last_backup_time": config.get("last_backup_time"),
                "next_backup_time": next_backup_time.isoformat() if next_backup_time else None,
                "max_backups": config.get("max_backups"),
                "backup_on_exit": config.get("backup_on_exit")
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get auto backup status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 模块职责说明：提供自动备份配置和管理的Web API接口
