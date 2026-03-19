"""
自动备份服务

支持定时自动备份功能
"""

import asyncio
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

from .backup import get_backup_service
from ..project_manager import get_project_manager

logger = logging.getLogger(__name__)


class BackupSchedule(str, Enum):
    """备份计划类型"""
    DISABLED = "disabled"  # 禁用
    ON_EXIT = "on_exit"    # 退出时
    DAILY = "daily"        # 每天
    WEEKLY = "weekly"      # 每周
    CUSTOM = "custom"      # 自定义间隔


class AutoBackupService:
    """自动备份服务"""
    
    def __init__(self):
        self.backup_service = get_backup_service()
        self.project_manager = get_project_manager()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._config = self._load_config()
    
    def _get_config_file(self) -> Path:
        """获取配置文件路径"""
        from ..constants import get_data_dir
        config_file = Path(get_data_dir()) / "auto_backup_config.json"
        return config_file
    
    def _load_config(self) -> Dict[str, Any]:
        """加载自动备份配置"""
        config_file = self._get_config_file()
        
        if not config_file.exists():
            return self._get_default_config()
        
        try:
            import json
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load auto backup config: {e}")
            return self._get_default_config()
    
    def _save_config(self) -> None:
        """保存自动备份配置"""
        import json
        config_file = self._get_config_file()
        config_file.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    @staticmethod
    def _get_default_config() -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "enabled": False,
            "schedule": BackupSchedule.DAILY.value,
            "daily_time": "02:00",  # 每天凌晨2点
            "weekly_day": 0,  # 周一 (0=周一, 6=周日)
            "weekly_time": "02:00",
            "custom_interval_hours": 24,
            "max_backups": 10,  # 最多保留10个备份
            "backup_on_exit": True,  # 退出时备份
            "include_knowledge_base": True,  # 包含知识库
            "last_backup_time": None
        }
    
    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self._config.copy()
    
    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新配置"""
        self._config.update(updates)
        self._save_config()
        
        # 如果启用状态改变,重启服务
        if "enabled" in updates:
            if updates["enabled"] and not self._running:
                asyncio.create_task(self.start())
            elif not updates["enabled"] and self._running:
                asyncio.create_task(self.stop())
        
        return self._config
    
    async def start(self) -> None:
        """启动自动备份服务"""
        if self._running:
            logger.warning("Auto backup service already running")
            return
        
        if not self._config.get("enabled", False):
            logger.info("Auto backup is disabled")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._backup_loop())
        logger.info("Auto backup service started")
    
    async def stop(self) -> None:
        """停止自动备份服务"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto backup service stopped")
    
    async def _backup_loop(self) -> None:
        """备份循环"""
        while self._running:
            try:
                # 计算下次备份时间
                next_backup_time = self._calculate_next_backup_time()
                
                if next_backup_time:
                    # 等待到下次备份时间
                    now = datetime.now()
                    wait_seconds = (next_backup_time - now).total_seconds()
                    
                    if wait_seconds > 0:
                        logger.info(f"Next auto backup scheduled at: {next_backup_time}")
                        await asyncio.sleep(wait_seconds)
                    
                    # 执行备份
                    if self._running:
                        await self._perform_backup()
                else:
                    # 没有计划的备份,等待1小时后重新检查
                    await asyncio.sleep(3600)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto backup loop: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟
    
    def _calculate_next_backup_time(self) -> Optional[datetime]:
        """计算下次备份时间"""
        schedule = self._config.get("schedule", BackupSchedule.DISABLED.value)
        now = datetime.now()
        
        if schedule == BackupSchedule.DISABLED.value:
            return None
        
        elif schedule == BackupSchedule.DAILY.value:
            # 每天指定时间
            time_str = self._config.get("daily_time", "02:00")
            hour, minute = map(int, time_str.split(":"))
            next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # 如果今天的时间已过,设置为明天
            if next_time <= now:
                next_time = next_time.replace(day=next_time.day + 1)
            
            return next_time
        
        elif schedule == BackupSchedule.WEEKLY.value:
            # 每周指定日期和时间
            target_weekday = self._config.get("weekly_day", 0)
            time_str = self._config.get("weekly_time", "02:00")
            hour, minute = map(int, time_str.split(":"))
            
            # 计算距离目标星期几还有多少天
            current_weekday = now.weekday()
            days_until_target = (target_weekday - current_weekday) % 7
            
            next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            next_time = next_time.replace(day=next_time.day + days_until_target)
            
            # 如果是今天但时间已过,设置为下周
            if days_until_target == 0 and next_time <= now:
                next_time = next_time.replace(day=next_time.day + 7)
            
            return next_time
        
        elif schedule == BackupSchedule.CUSTOM.value:
            # 自定义间隔
            interval_hours = self._config.get("custom_interval_hours", 24)
            last_backup = self._config.get("last_backup_time")
            
            if last_backup:
                last_time = datetime.fromisoformat(last_backup)
                next_time = last_time.replace(hour=last_time.hour + interval_hours)
            else:
                # 首次备份,立即执行
                next_time = now
            
            return next_time
        
        return None
    
    async def _perform_backup(self) -> None:
        """执行备份"""
        try:
            # 获取当前项目
            current_project = self.project_manager.get_current_project()
            
            if not current_project:
                logger.warning("No current project for auto backup")
                return
            
            logger.info(f"Starting auto backup for project: {current_project.name}")
            
            # 创建备份
            result = self.backup_service.create_backup(
                project_id=current_project.id,
                project_name=current_project.name,
                backup_type="full"
            )
            
            # 更新最后备份时间
            self._config["last_backup_time"] = datetime.now().isoformat()
            self._save_config()
            
            # 清理旧备份
            await self._cleanup_old_backups()
            
            logger.info(f"Auto backup completed: {result['backup_id']}")
            
        except Exception as e:
            logger.error(f"Auto backup failed: {e}")
    
    async def _cleanup_old_backups(self) -> None:
        """清理旧备份"""
        try:
            max_backups = self._config.get("max_backups", 10)
            backups = self.backup_service.list_backups()
            
            # 按时间排序,保留最新的N个
            if len(backups) > max_backups:
                backups_to_delete = backups[max_backups:]
                
                for backup in backups_to_delete:
                    backup_id = backup.get("backup_id")
                    if backup_id:
                        self.backup_service.delete_backup(backup_id)
                        logger.info(f"Deleted old backup: {backup_id}")
        
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
    
    async def backup_on_exit(self) -> None:
        """退出时备份"""
        if not self._config.get("backup_on_exit", True):
            return
        
        logger.info("Performing backup on exit...")
        await self._perform_backup()


# 全局单例
_auto_backup_service: Optional[AutoBackupService] = None


def get_auto_backup_service() -> AutoBackupService:
    """获取自动备份服务全局实例"""
    global _auto_backup_service
    if _auto_backup_service is None:
        _auto_backup_service = AutoBackupService()
    return _auto_backup_service


# 模块职责说明：提供定时自动备份功能,支持每天/每周/自定义间隔/退出时备份