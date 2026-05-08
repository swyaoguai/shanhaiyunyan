"""
Web应用主模块（重构版）

提供用户友好的Web界面。
使用模块化路由设计，将所有API路由拆分到独立模块。

增强功能：
- 智能路由：集成RouterAgent实现意图识别和自动工具调用
- 知识库优先：在响应用户前先检索知识库
- 响应保证：设置默认消息处理器确保每个请求都有响应
"""

import json
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import config
from ..workflow import NovelCoordinator
from ..agents import RouterAgent
from .dependencies import set_coordinator, set_router_agent
from .routes import register_routes
from .routes.pages import set_templates
from .websocket import setup_websocket_routes

# 日志记录器
logger = logging.getLogger(__name__)


def _get_resource_path(relative_path: str) -> Path:
    """
    获取资源路径，兼容PyInstaller打包（onefile和onedir模式）
    
    Args:
        relative_path: 相对于web目录的路径
        
    Returns:
        资源的绝对路径
    """
    import sys
    
    if getattr(sys, 'frozen', False):
        # 打包后运行
        if hasattr(sys, '_MEIPASS'):
            meipass = Path(sys._MEIPASS)
            resource_path = meipass / "novel_agent" / "web" / relative_path
            if resource_path.exists():
                return resource_path
        
        exe_dir = Path(sys.executable).parent
        
        possible_paths = [
            Path(getattr(sys, '_MEIPASS', '')) / "novel_agent" / "web" / relative_path,
            exe_dir / "_internal" / "novel_agent" / "web" / relative_path,
            exe_dir.parent / "resources" / relative_path,
            exe_dir / "resources" / relative_path,
            exe_dir / relative_path,
        ]
        
        for p in possible_paths:
            if p.exists():
                logger.info(f"[Resource] 找到资源路径: {p}")
                return p
        
        logger.warning(f"[Resource] 未找到资源 {relative_path}")
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / "novel_agent" / "web" / relative_path
        return exe_dir / "_internal" / "novel_agent" / "web" / relative_path
    else:
        # 开发模式
        return Path(__file__).parent / relative_path


async def _setup_knowledge_base_for_router(router_agent: RouterAgent) -> None:
    """为路由智能体配置知识库"""
    from ..project_manager import get_project_manager
    
    pm = get_project_manager()
    if not pm.current_project_id:
        return
    
    try:
        from ..knowledge_base import KnowledgeBase
        from ..knowledge_base.data_layer.vector_store import CHROMA_AVAILABLE, CHROMA_IMPORT_ERROR
        
        if not CHROMA_AVAILABLE:
            logger.error(f"[Router] ChromaDB不可用: {CHROMA_IMPORT_ERROR}")
            return
        
        config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
        
        has_embedding_config = False
        if config_path.exists():
            try:
                kb_config = json.loads(config_path.read_text(encoding="utf-8"))
                provider = str(kb_config.get("embedding_provider") or "api").lower()
                has_embedding_config = bool(kb_config.get("siliconflow_api_key"))
                if provider in {"local", "local_onnx"}:
                    has_embedding_config = bool(kb_config.get("onnx_model_dir"))
            except Exception:
                pass
        else:
            provider = os.getenv("KB_EMBEDDING_PROVIDER", os.getenv("EMBEDDING_PROVIDER", "api")).lower()
            has_embedding_config = bool(os.getenv("SILICONFLOW_API_KEY", ""))
            if provider in {"local", "local_onnx"}:
                has_embedding_config = bool(os.getenv("KB_ONNX_MODEL_DIR", ""))
        
        if has_embedding_config:
            kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=False)
            router_agent.set_knowledge_base(kb)

            from .dependencies import get_coordinator
            coordinator = get_coordinator()
            if coordinator and hasattr(coordinator, "set_knowledge_base"):
                coordinator.set_knowledge_base(kb)

            logger.info("[Router] ✓ 知识库已配置，并已同步到协调器子Agent（使用真实向量存储）")
        else:
            logger.info("[Router] 未配置可用向量化 provider，跳过知识库功能")
            
    except ImportError as e:
        logger.error(f"[Router] 知识库初始化失败（ChromaDB不可用）: {e}")
    except ValueError as e:
        logger.warning(f"[Router] 知识库配置错误: {e}")
    except Exception as e:
        logger.warning(f"[Router] 知识库初始化失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    config.init()
    
    # 创建WebSocket进度回调
    from .websocket import WebSocketProgressCallback
    ws_callback = WebSocketProgressCallback()
    
    # 创建协调器并设置回调
    coordinator = NovelCoordinator(
        config.paths.output_dir,
        progress_callback=ws_callback
    )
    set_coordinator(coordinator)
    
    # 创建路由智能体，并关联协调器
    router_agent = RouterAgent(coordinator=coordinator)
    set_router_agent(router_agent)
    
    # 尝试为路由智能体配置知识库
    await _setup_knowledge_base_for_router(router_agent)
    
    # 启动消息总线
    from ..agents.message_bus import get_message_bus
    bus = get_message_bus()
    await bus.start()
    
    # 设置默认消息处理器
    async def default_message_handler(message):
        """默认消息处理器 - 当没有其他智能体处理时，由路由智能体接管"""
        if router_agent:
            try:
                user_input = message.payload.get("content", "") or message.payload.get("message", "")
                if user_input:
                    result = await router_agent.route_and_respond(user_input)
                    logger.info(f"[DefaultHandler] 路由智能体处理了未投递消息: {message.id}")
                    return result
            except Exception as e:
                logger.error(f"[DefaultHandler] 路由智能体处理失败: {e}")
        return None
    
    bus.set_default_handler(default_message_handler)
    logger.info("[MessageBus] 默认消息处理器已设置")
    
    yield
    
    # 清理资源 - 停止消息总线
    await bus.stop()


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    
    app = FastAPI(
        title="山海·云烟",
        description="基于多智能体协作的智能小说创作系统",
        version="1.0",
        lifespan=lifespan
    )
    
    # 配置静态文件
    static_dir = _get_resource_path("static")
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    # 配置模板
    templates_dir = _get_resource_path("templates")
    templates_dir.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))
    
    # 注入模板引擎到页面路由模块
    set_templates(templates)
    
    # 注册所有路由
    register_routes(app)
    setup_websocket_routes(app)
    
    return app


# 模块职责说明：提供FastAPI Web应用入口，包含生命周期管理和路由注册。
# 所有具体路由实现已拆分到 routes/ 目录下的各个模块。
