"""
Web路由模块

将所有API路由按功能拆分到独立模块，提高代码可维护性。
每个模块使用FastAPI的APIRouter进行路由注册。

支持API版本控制：
- /api/v1/* - 版本化API（推荐）
- /api/* - 兼容旧版本（保持向后兼容）
"""

from fastapi import FastAPI

from .pages import router as pages_router
from .novel import router as novel_router
from .settings import router as settings_router
from .agents import router as agents_router
from .chat import router as chat_router
from .projects import router as projects_router
from .knowledge import router as knowledge_router
from .continuous_write import router as continuous_write_router
from .prompts import router as prompts_router
from .token_stats import router as token_stats_router
from .trends import router as trends_router
from .aux_memory import router as aux_memory_router
from .short_story import router as short_story_router
from .novel_to_script import router as novel_to_script_router
from .skills import router as skills_router
from .wiki import router as wiki_router
from .runtime import router as runtime_router
from .diagnostics import router as diagnostics_router
from ..api.backup import router as backup_router
from ..api.resources import router as resources_router
from ..api.auto_backup import router as auto_backup_router

# API版本
API_VERSION = "v1"


def register_routes(app: FastAPI, use_versioned_api: bool = True) -> None:
    """
    注册所有路由到FastAPI应用

    Args:
        app: FastAPI应用实例
        use_versioned_api: 是否注册版本化API前缀

    Notes:
        - 推荐前端与外部调用统一使用 `/api/v1`
        - `/api` 当前仅作为兼容层保留
    """
    # 页面路由（无前缀）
    app.include_router(pages_router)

    # API路由
    # 推荐使用版本化前缀 /api/v1，同时保持 /api 兼容层
    api_routers = [
        (novel_router, "小说创作"),
        (settings_router, "设置"),
        (agents_router, "Agent配置"),
        (chat_router, "对话"),
        (projects_router, "项目管理"),
        (knowledge_router, "知识库"),
        (continuous_write_router, "无限续写"),
        (prompts_router, "提示词管理"),
        (token_stats_router, "Token统计"),
        (trends_router, "热点搜索"),
        (aux_memory_router, "辅助记忆"),
        (short_story_router, "短篇创作"),
        (novel_to_script_router, "小说转剧本"),
        (skills_router, "Skills管理"),
        (wiki_router, "Wiki知识系统"),
        (runtime_router, "运行时"),
        (diagnostics_router, "诊断日志"),
        (backup_router, "备份管理"),
        (resources_router, "资料库管理"),
        (auto_backup_router, "自动备份"),
    ]

    for router, tag in api_routers:
        if use_versioned_api:
            # 版本化API（推荐）
            app.include_router(router, prefix=f"/api/{API_VERSION}", tags=[tag])
        # 向后兼容（无版本前缀）
        app.include_router(router, prefix="/api", tags=[tag])
