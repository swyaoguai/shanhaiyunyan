"""
页面路由模块

提供Web页面渲染路由。
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# 模板引擎将通过依赖注入提供
_templates = None


def set_templates(templates):
    """设置Jinja2模板引擎"""
    global _templates
    _templates = templates


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    from ...config import config
    from ...version import get_app_version
    
    if _templates is None:
        return HTMLResponse("<h1>模板引擎未初始化</h1>", status_code=500)
    
    response = _templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "novel_types": config.novel.novel_types,
            "app_version": get_app_version(),
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
