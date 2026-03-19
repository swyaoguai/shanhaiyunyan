"""
Web API模块

提供备份、资料库和自动备份的API接口
"""

from .backup import router as backup_router
from .resources import router as resources_router
from .auto_backup import router as auto_backup_router

__all__ = ["backup_router", "resources_router", "auto_backup_router"]