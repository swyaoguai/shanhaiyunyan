"""
Web应用主模块
提供用户友好的Web界面

增强功能：
- 智能路由：集成RouterAgent实现意图识别和自动工具调用
- 知识库优先：在响应用户前先检索知识库
- 响应保证：设置默认消息处理器确保每个请求都有响应
"""

import os
import json
import httpx
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..config import config
from ..workflow import NovelCoordinator
from ..agents import RouterAgent
from ..constants import (
    TIMEOUTS,
    LLM_DEFAULTS,
    API_ENDPOINTS,
    WRITING_CONFIG
)
from ..knowledge_base.config import KnowledgeBaseConfig, SiliconFlowConfig, ChunkingConfig, RetrievalConfig
from ..utils.mcp_manager import mcp_manager

# 日志记录器
logger = logging.getLogger(__name__)

# 热点配置默认值常量（集中管理，避免分散硬编码）
TRENDS_CONFIG_DEFAULTS = {
    "enabled": True,
    "auto_refresh": False,
    "refresh_interval": 300,
    "default_platforms": [],  # 空列表表示不预选任何平台，用户需手动选择
    "show_in_infinite_write": True,
    "show_in_multi_agent": True
}


# 全局协调器实例
coordinator: Optional[NovelCoordinator] = None
# 全局路由智能体实例
router_agent: Optional[RouterAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global coordinator, router_agent
    config.init()
    
    # 创建WebSocket进度回调
    from .websocket import WebSocketProgressCallback
    ws_callback = WebSocketProgressCallback()
    
    # 创建协调器并设置回调
    coordinator = NovelCoordinator(
        config.paths.output_dir,
        progress_callback=ws_callback
    )
    
    # 创建路由智能体，并关联协调器
    router_agent = RouterAgent(coordinator=coordinator)
    
    # 尝试为路由智能体配置知识库（必须使用真实向量存储，不使用模拟）
    from ..project_manager import get_project_manager
    pm = get_project_manager()
    if pm.current_project_id:
        try:
            from ..knowledge_base import KnowledgeBase
            from ..knowledge_base.data_layer.vector_store import CHROMA_AVAILABLE, CHROMA_IMPORT_ERROR
            
            # 首先检查ChromaDB是否可用
            if not CHROMA_AVAILABLE:
                logger.error(
                    f"[Router] ChromaDB不可用: {CHROMA_IMPORT_ERROR}。"
                    "请运行: pip install chromadb"
                )
            else:
                config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
                
                has_api_key = False
                if config_path.exists():
                    try:
                        kb_config = json.loads(config_path.read_text(encoding="utf-8"))
                        has_api_key = bool(kb_config.get("siliconflow_api_key"))
                    except Exception:
                        pass
                
                if has_api_key:
                    kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=False)
                    router_agent.set_knowledge_base(kb)
                    logger.info("[Router] ✓ 知识库已配置（使用真实向量存储）")
                else:
                    logger.info("[Router] 未配置向量化API Key，跳过知识库功能")
        except ImportError as e:
            logger.error(f"[Router] 知识库初始化失败（ChromaDB不可用）: {e}")
        except ValueError as e:
            logger.warning(f"[Router] 知识库配置错误: {e}")
        except Exception as e:
            logger.warning(f"[Router] 知识库初始化失败: {e}")
    
    # 启动消息总线
    from ..agents.message_bus import get_message_bus
    bus = get_message_bus()
    await bus.start()
    
    # 设置默认消息处理器（确保每个请求都有响应）
    async def default_message_handler(message):
        """默认消息处理器 - 当没有其他智能体处理时，由路由智能体接管"""
        if router_agent:
            try:
                # 从消息中提取用户输入
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
        title="小说创作智能体",
        description="基于多智能体协作的智能小说创作系统",
        version="1.1.0",
        lifespan=lifespan
    )
    
    # 静态文件 - 支持PyInstaller打包
    def get_resource_path(relative_path: str) -> Path:
        """获取资源路径，兼容PyInstaller打包（onefile和onedir模式）"""
        import sys
        
        # PyInstaller打包后的路径
        if getattr(sys, 'frozen', False):
            # 打包后运行
            # 优先使用 _MEIPASS（onefile模式解压临时目录）
            if hasattr(sys, '_MEIPASS'):
                # onefile 模式：资源解压到临时目录
                meipass = Path(sys._MEIPASS)
                resource_path = meipass / "novel_agent" / "web" / relative_path
                if resource_path.exists():
                    return resource_path
            
            # 获取exe所在目录
            exe_dir = Path(sys.executable).parent
            
            # 尝试多个可能的位置
            possible_paths = [
                # onefile模式：临时目录
                Path(getattr(sys, '_MEIPASS', '')) / "novel_agent" / "web" / relative_path,
                # onedir模式：_internal目录
                exe_dir / "_internal" / "novel_agent" / "web" / relative_path,
                # 便携版结构：resources目录
                exe_dir.parent / "resources" / relative_path,
                exe_dir / "resources" / relative_path,
                # 直接在exe目录下
                exe_dir / relative_path,
            ]
            
            for p in possible_paths:
                if p.exists():
                    logger.info(f"[Resource] 找到资源路径: {p}")
                    return p
            
            # 如果都没找到，记录日志并返回第一个有效路径
            logger.warning(f"[Resource] 未找到资源 {relative_path}，尝试的路径: {[str(p) for p in possible_paths]}")
            # 返回临时目录路径（如果存在）或exe目录路径
            if hasattr(sys, '_MEIPASS'):
                return Path(sys._MEIPASS) / "novel_agent" / "web" / relative_path
            return exe_dir / "_internal" / "novel_agent" / "web" / relative_path
        else:
            # 开发模式
            return Path(__file__).parent / relative_path
    
    static_dir = get_resource_path("static")
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    # 模板
    templates_dir = get_resource_path("templates")
    templates_dir.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))
    
    # ========== 请求模型 ==========
    
    class CreateNovelRequest(BaseModel):
        """创建小说请求"""
        novel_type: str = "玄幻"
        theme: str = ""
        requirements: str = ""
        protagonist: str = ""
        plot_idea: str = ""
        volume_count: int = 1
        chapters_per_volume: int = 5
    
    class GenerateWorldRequest(BaseModel):
        """生成世界观请求"""
        novel_type: str = "玄幻"
        theme: str = ""
        requirements: str = ""
    
    class GenerateOutlineRequest(BaseModel):
        """生成大纲请求"""
        protagonist: str = ""
        plot_idea: str = ""
        volume_count: int = 1
        chapters_per_volume: int = 10
    
    class WriteChapterRequest(BaseModel):
        """撰写章节请求"""
        chapter_number: int = 1
        chapter_index: int = 0  # 章节索引（从0开始）
        chapter_outline: str = ""
        chapter_title: str = ""
        existing_content: str = ""  # 已有内容（用于续写/润色）
        action: str = "write"  # write/continue/polish
        word_count: int = WRITING_CONFIG.CONTINUE_DEFAULT_WORDS  # 续写时的目标字数
    
    # ========== 页面路由 ==========
    
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """首页"""
        return templates.TemplateResponse("index.html", {
            "request": request,
            "novel_types": config.novel.novel_types
        })
    
    # ========== API路由 ==========
    
    @app.post("/api/create")
    async def create_novel(request: CreateNovelRequest):
        """创建小说(流式输出)"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        async def generate():
            async for progress in coordinator.create_novel(
                novel_type=request.novel_type,
                theme=request.theme,
                requirements=request.requirements,
                protagonist=request.protagonist,
                plot_idea=request.plot_idea,
                volume_count=request.volume_count,
                chapters_per_volume=request.chapters_per_volume
            ):
                yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    
    @app.post("/api/world")
    async def generate_world(request: GenerateWorldRequest):
        """生成世界观"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        result = await coordinator.generate_world(
            novel_type=request.novel_type,
            theme=request.theme,
            requirements=request.requirements
        )
        return JSONResponse(result)
    
    @app.post("/api/outline")
    async def generate_outline(request: GenerateOutlineRequest):
        """生成大纲"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        result = await coordinator.generate_outline(
            protagonist=request.protagonist,
            plot_idea=request.plot_idea,
            volume_count=request.volume_count,
            chapters_per_volume=request.chapters_per_volume
        )
        return JSONResponse(result)
    
    @app.post("/api/chapter")
    async def write_chapter(request: WriteChapterRequest):
        """撰写/续写/润色章节"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        try:
            action = request.action.lower()
            
            if action == "continue":
                # AI续写
                result = await coordinator.continue_chapter(
                    chapter_index=request.chapter_index,
                    chapter_title=request.chapter_title,
                    existing_content=request.existing_content,
                    target_words=request.word_count
                )
            elif action == "polish":
                # AI润色
                result = await coordinator.polish_content(
                    content=request.existing_content,
                    chapter_title=request.chapter_title
                )
            else:
                # 默认写作
                result = await coordinator.write_single_chapter(
                    chapter_number=request.chapter_number,
                    chapter_outline=request.chapter_outline,
                    chapter_title=request.chapter_title
                )
            
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e),
                "content": ""
            })
    
    @app.get("/api/status")
    async def get_status():
        """获取项目状态"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        return JSONResponse(coordinator.get_project_status())
    
    @app.get("/api/types")
    async def get_novel_types():
        """获取支持的小说类型"""
        return JSONResponse({"types": config.novel.novel_types})
    
    # ========== 设置API ==========
    
    class APIConfigRequest(BaseModel):
        """API配置请求"""
        api_base: str
        api_key: str
        model: str = ""
    
    class FetchModelsRequest(BaseModel):
        """获取模型列表请求"""
        api_base: str
        api_key: str
    
    @app.get("/api/settings")
    async def get_settings():
        """获取当前API配置"""
        return JSONResponse({
            "api_base": config.llm.api_base,
            "api_key": config.llm.api_key[:8] + "****" if len(config.llm.api_key) > 8 else "****",
            "api_key_set": bool(config.llm.api_key and config.llm.api_key != "your-api-key-here"),
            "model": config.llm.model,
            "max_tokens": config.llm.max_tokens,
            "temperature": config.llm.temperature
        })
    
    @app.post("/api/settings")
    async def save_settings(request: APIConfigRequest):
        """保存API配置到.env文件"""
        env_path = Path(__file__).parent.parent.parent / ".env"
        
        # 读取现有配置
        env_content = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_content[key.strip()] = value.strip()
        
        # 更新配置
        env_content["OPENAI_API_BASE"] = request.api_base
        env_content["OPENAI_API_KEY"] = request.api_key
        if request.model:
            env_content["OPENAI_MODEL"] = request.model
        
        # 写入文件
        lines = []
        lines.append("# OpenAI兼容API配置")
        lines.append(f"OPENAI_API_KEY={env_content.get('OPENAI_API_KEY', '')}")
        lines.append(f"OPENAI_API_BASE={env_content.get('OPENAI_API_BASE', '')}")
        lines.append(f"OPENAI_MODEL={env_content.get('OPENAI_MODEL', 'gpt-4')}")
        lines.append("")
        lines.append("# 服务配置")
        lines.append(f"HOST={env_content.get('HOST', '0.0.0.0')}")
        lines.append(f"PORT={env_content.get('PORT', '8000')}")
        lines.append(f"DEBUG={env_content.get('DEBUG', 'false')}")
        lines.append("")
        lines.append("# 生成配置")
        lines.append(f"MAX_TOKENS={env_content.get('MAX_TOKENS', '4096')}")
        lines.append(f"TEMPERATURE={env_content.get('TEMPERATURE', '0.7')}")
        
        # Atomic write pattern: write to temp file, then rename
        temp_path = env_path.with_suffix('.tmp')
        try:
            # Step 1: Write to file
            temp_path.write_text("\n".join(lines), encoding="utf-8")
            temp_path.rename(env_path)

            # Step 2: Reload config from file (update runtime with new values)
            from ..config import Config
            reload_success = Config.reload()
            if not reload_success:
                # Rollback: delete the file if reload failed
                if env_path.exists():
                    try:
                        env_path.unlink()
                    except Exception:
                        pass
                return JSONResponse({
                    "success": False,
                    "error": "Failed to reload configuration"
                }, status_code=500)

        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to write .env file: {e}")
            # Cleanup temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return JSONResponse({
                "success": False,
                "error": f"Failed to save settings: {e}"
            }, status_code=500)

        # Step 3: Recreate coordinator with updated config
        global coordinator
        # 保存原有的progress_callback
        from .websocket import WebSocketProgressCallback
        ws_callback = WebSocketProgressCallback()
        coordinator = NovelCoordinator(
            config.paths.output_dir,
            progress_callback=ws_callback
        )
        
        return JSONResponse({"success": True, "message": "配置已保存"})
    @app.post("/api/settings/reload")
    async def reload_settings():
        """手动重载配置文件"""
        # Step 1: Reload config from .env file
        from ..config import Config
        reload_success = Config.reload()

        if not reload_success:
            return JSONResponse({
                "success": False,
                "error": "Failed to reload configuration"
            }, status_code=500)

        # Step 2: Recreate coordinator with updated config
        global coordinator
        from .websocket import WebSocketProgressCallback
        ws_callback = WebSocketProgressCallback()
        coordinator = NovelCoordinator(
            config.paths.output_dir,
            progress_callback=ws_callback
        )

        # Step 3: Return updated config values
        return JSONResponse({
            "success": True,
            "data": {
                "api_key": config.llm.api_key,
                "api_base": config.llm.api_base,
                "model": config.llm.model
            }
        })

    
    @app.post("/api/models")
    async def fetch_models(request: FetchModelsRequest):
        """从API获取可用模型列表"""
        try:
            # 构建请求URL
            base_url = request.api_base.rstrip("/")
            models_url = f"{base_url}/models"
            
            # 发起请求
            async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_SHORT) as client:
                response = await client.get(
                    models_url,
                    headers={
                        "Authorization": f"Bearer {request.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = []
                    
                    # 解析模型列表（兼容OpenAI格式）
                    if "data" in data:
                        for model in data["data"]:
                            model_id = model.get("id", "")
                            if model_id:
                                models.append(model_id)
                    elif isinstance(data, list):
                        for model in data:
                            if isinstance(model, str):
                                models.append(model)
                            elif isinstance(model, dict) and "id" in model:
                                models.append(model["id"])
                    
                    if models:
                        # 排序，把常用模型放前面
                        priority_models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "deepseek-chat", "claude"]
                        def sort_key(m):
                            for i, p in enumerate(priority_models):
                                if p in m.lower():
                                    return (0, i, m)
                            return (1, 0, m)
                        models.sort(key=sort_key)
                        
                        return JSONResponse({
                            "success": True,
                            "models": models
                        })
                    else:
                        return JSONResponse({
                            "success": False,
                            "error": "未能解析模型列表，请手动输入模型名称",
                            "models": []
                        })
                else:
                    return JSONResponse({
                        "success": False,
                        "error": f"请求失败 (HTTP {response.status_code})，该API可能不支持获取模型列表，请手动输入",
                        "models": []
                    })
                    
        except httpx.TimeoutException:
            return JSONResponse({
                "success": False,
                "error": "请求超时，请检查API地址是否正确",
                "models": []
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"获取失败: {str(e)}，请手动输入模型名称",
                "models": []
            })
    
    class TestConnectionRequest(BaseModel):
        """测试连接请求"""
        api_base: str = ""
        api_key: str = ""
        model: str = ""
        config_id: str = ""  # 可选：从已保存的配置中获取API Key
    
    @app.post("/api/test-connection")
    async def test_connection(request: TestConnectionRequest):
        """测试API连接"""
        import time
        
        try:
            # 获取实际的 API Base 和 API Key
            api_base = request.api_base
            api_key = request.api_key
            test_model = request.model
            
            # 如果提供了 config_id，从保存的配置中获取信息
            if request.config_id:
                from ..agent_config import get_config_manager
                manager = get_config_manager()
                for config in manager.multi_config.configs:
                    if config.id == request.config_id:
                        if not api_base:
                            api_base = config.api_base
                        if not api_key:
                            api_key = config.api_key
                        if not test_model and config.models:
                            test_model = config.models[0]
                        break
            
            # 如果还是没有 api_key，尝试从激活的配置获取
            if not api_key and api_base:
                from ..agent_config import get_config_manager
                manager = get_config_manager()
                # 查找匹配 api_base 的配置
                for config in manager.multi_config.configs:
                    if config.api_base == api_base and config.api_key:
                        api_key = config.api_key
                        if not test_model and config.models:
                            test_model = config.models[0]
                        break
            
            if not api_base:
                return JSONResponse({
                    "success": False,
                    "error": "未提供API地址"
                })
            
            if not api_key:
                return JSONResponse({
                    "success": False,
                    "error": "未配置API密钥，请先保存配置后再测试"
                })
            
            base_url = api_base.rstrip("/")
            if not base_url.endswith('/v1'):
                base_url = base_url + '/v1' if not base_url.endswith('/') else base_url + 'v1'
            
            # 使用请求中的模型，或默认模型
            if not test_model:
                test_model = "gpt-3.5-turbo"
            
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_LONG) as client:
                # 尝试发送一个简单的请求测试连接
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": test_model,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5
                    }
                )
                
                response_time = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    return JSONResponse({
                        "success": True,
                        "message": "连接成功！API配置正确",
                        "model_tested": test_model,
                        "response_time": response_time
                    })
                elif response.status_code == 401:
                    return JSONResponse({
                        "success": False,
                        "error": "API密钥无效或已过期"
                    })
                elif response.status_code == 404:
                    return JSONResponse({
                        "success": False,
                        "error": f"模型 '{test_model}' 不存在或API端点错误"
                    })
                elif response.status_code == 429:
                    return JSONResponse({
                        "success": False,
                        "error": "请求过于频繁，请稍后再试"
                    })
                else:
                    error_text = response.text[:200] if response.text else ""
                    return JSONResponse({
                        "success": False,
                        "error": f"连接失败 (HTTP {response.status_code}): {error_text}"
                    })
                    
        except httpx.TimeoutException:
            return JSONResponse({
                "success": False,
                "error": "连接超时，请检查API地址是否正确或网络连接"
            })
        except httpx.ConnectError as e:
            return JSONResponse({
                "success": False,
                "error": f"无法连接到服务器: {str(e)}"
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"连接失败: {str(e)}"
            })
    
    # ========== 全局API配置（多配置管理） ==========
    
    class GlobalAPIConfigRequest(BaseModel):
        """全局API配置请求（兼容旧接口）"""
        api_base: str = ""
        api_key: str = ""
        model: str = ""
        temperature: float = LLM_DEFAULTS.TEMPERATURE
        max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    
    class AddAPIConfigRequest(BaseModel):
        """添加API配置请求"""
        name: str
        api_base: str
        api_key: str
        models: List[str] = []
        temperature: float = LLM_DEFAULTS.TEMPERATURE
        max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    
    class UpdateAPIConfigRequest(BaseModel):
        """更新API配置请求"""
        name: str = None
        api_base: str = None
        api_key: str = None
        models: List[str] = None
        temperature: float = None
        max_tokens: int = None
    
    class SetActiveConfigRequest(BaseModel):
        """设置激活配置请求"""
        config_id: str
        model: str = ""
    
    class AddModelRequest(BaseModel):
        """添加模型请求"""
        model: str
    
    @app.get("/api/global-config")
    async def get_global_api_config():
        """获取全局API配置（兼容接口）"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        config = manager.get_global_config()
        multi = manager.get_multi_config()
        
        return JSONResponse({
            "api_base": config.api_base,
            "api_key": config.api_key[:8] + "****" if len(config.api_key) > 8 else "",
            "api_key_set": bool(config.api_key),
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "is_configured": config.is_configured(),
            # 新增：多配置信息
            "multi_config": {
                "configs": manager.list_api_configs(),
                "active_config_id": multi.active_config_id,
                "active_model": multi.active_model
            }
        })
    
    @app.post("/api/global-config")
    async def save_global_api_config(request: GlobalAPIConfigRequest):
        """保存全局API配置（兼容旧接口）"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        # 获取当前配置的API Key
        current_api_key = manager.get_global_config().api_key
        
        # 判断是否需要保留原有API Key
        api_key = request.api_key
        should_keep_original = (
            api_key.endswith("****") or
            api_key == "••••••••" or
            (not api_key and current_api_key)
        )
        
        if should_keep_original:
            api_key = current_api_key
        
        manager.set_global_config(
            api_base=request.api_base,
            api_key=api_key,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        return JSONResponse({"success": True, "message": "全局API配置已保存"})
    
    # ===== 多配置管理API =====
    
    @app.get("/api/api-configs")
    async def list_api_configs():
        """获取所有API配置列表"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        multi = manager.get_multi_config()
        
        return JSONResponse({
            "configs": manager.list_api_configs(),
            "active_config_id": multi.active_config_id,
            "active_model": multi.active_model
        })
    
    @app.post("/api/api-configs")
    async def add_api_config(request: AddAPIConfigRequest):
        """添加新的API配置"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        config = manager.add_api_config(
            name=request.name,
            api_base=request.api_base,
            api_key=request.api_key,
            models=request.models,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        return JSONResponse({
            "success": True,
            "message": f"API配置 '{request.name}' 已添加",
            "config": config.to_dict()
        })
    
    @app.put("/api/api-configs/{config_id}")
    async def update_api_config_by_id(config_id: str, request: UpdateAPIConfigRequest):
        """更新指定的API配置"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        # 构建更新参数
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.api_base is not None:
            updates["api_base"] = request.api_base
        if request.api_key is not None and not request.api_key.endswith("****"):
            updates["api_key"] = request.api_key
        if request.models is not None:
            updates["models"] = request.models
        if request.temperature is not None:
            updates["temperature"] = request.temperature
        if request.max_tokens is not None:
            updates["max_tokens"] = request.max_tokens
        
        config = manager.update_api_config(config_id, **updates)
        
        if config:
            return JSONResponse({
                "success": True,
                "message": "API配置已更新",
                "config": config.to_dict()
            })
        else:
            raise HTTPException(status_code=404, detail="配置不存在")
    
    @app.delete("/api/api-configs/{config_id}")
    async def delete_api_config_by_id(config_id: str):
        """删除指定的API配置"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        if manager.delete_api_config(config_id):
            return JSONResponse({
                "success": True,
                "message": "API配置已删除"
            })
        else:
            raise HTTPException(status_code=404, detail="配置不存在")
    
    @app.post("/api/api-configs/active")
    async def set_active_api_config(request: SetActiveConfigRequest):
        """设置激活的API配置和模型"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        if manager.set_active_config(request.config_id, request.model):
            return JSONResponse({
                "success": True,
                "message": "已切换到指定配置"
            })
        else:
            raise HTTPException(status_code=404, detail="配置不存在")
    
    @app.post("/api/api-configs/{config_id}/models")
    async def add_model_to_api_config(config_id: str, request: AddModelRequest):
        """向配置添加模型"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        if manager.add_model_to_config(config_id, request.model):
            return JSONResponse({
                "success": True,
                "message": f"模型 '{request.model}' 已添加"
            })
        else:
            raise HTTPException(status_code=404, detail="配置不存在")
    
    @app.delete("/api/api-configs/{config_id}/models/{model}")
    async def remove_model_from_api_config(config_id: str, model: str):
        """从配置移除模型"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        if manager.remove_model_from_config(config_id, model):
            return JSONResponse({
                "success": True,
                "message": f"模型 '{model}' 已移除"
            })
        else:
            raise HTTPException(status_code=404, detail="配置不存在")
    
    # ========== Agent配置API ==========
    
    class AgentConfigUpdateRequest(BaseModel):
        """Agent配置更新请求
        
        使用Optional类型，只更新明确提供的字段，避免默认值覆盖用户已保存的设置
        """
        api_base: Optional[str] = None
        api_key: Optional[str] = None
        model: Optional[str] = None
        temperature: Optional[float] = None
        max_tokens: Optional[int] = None
        use_global: Optional[bool] = None
    
    @app.get("/api/agents")
    async def list_agents():
        """获取所有Agent及其配置状态"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        global_config = manager.get_global_config()
        return JSONResponse({
            "agents": manager.list_agents(),
            "global_configured": global_config.is_configured(),
            "global_model": global_config.model or "(未配置)"
        })
    
    @app.get("/api/agents/{agent_name}")
    async def get_agent_config(agent_name: str):
        """获取单个Agent的配置"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        config = manager.get_config(agent_name)
        global_config = manager.get_global_config()
        return JSONResponse({
            "name": config.agent_name,
            "api_base": config.api_base,
            "api_key": config.api_key[:8] + "****" if len(config.api_key) > 8 else "",
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "description": config.description,
            "is_configured": config.is_configured(),
            "use_global": config.use_global,
            "global_configured": global_config.is_configured(),
            "global_model": global_config.model
        })
    
    @app.post("/api/agents/{agent_name}")
    async def update_agent_config(agent_name: str, request: AgentConfigUpdateRequest):
        """更新Agent配置
        
        只更新请求中明确提供的字段（非None），避免默认值覆盖用户已保存的设置
        """
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        
        # 构建只包含非None值的更新字典
        updates = {}
        if request.api_base is not None:
            updates['api_base'] = request.api_base
        if request.api_key is not None:
            updates['api_key'] = request.api_key
        if request.model is not None:
            updates['model'] = request.model
        if request.temperature is not None:
            updates['temperature'] = request.temperature
        if request.max_tokens is not None:
            updates['max_tokens'] = request.max_tokens
        if request.use_global is not None:
            updates['use_global'] = request.use_global
        
        # 只有当有更新内容时才调用更新方法
        if updates:
            manager.update_config(agent_name, **updates)
            logger.info(f"[AgentConfig] 更新 {agent_name} 配置: {updates}")
        
        return JSONResponse({"success": True, "message": f"{agent_name} 配置已更新"})
    
    @app.post("/api/agents/copy-to-all")
    async def copy_config_to_all(source: str):
        """将一个Agent的配置复制到所有Agent"""
        from ..agent_config import get_config_manager
        manager = get_config_manager()
        manager.copy_config_to_all(source)
        return JSONResponse({"success": True, "message": "配置已复制到所有Agent"})
    
    @app.post("/api/fetch-models")
    async def fetch_models_v2(request: FetchModelsRequest):
        """
        从API获取可用模型列表
        兼容OpenAI v1接口格式
        """
        import httpx
        
        api_base = request.api_base.rstrip('/')
        # 如果已经以/v1结尾，不再添加
        if not api_base.endswith('/v1'):
            if api_base.endswith('/'):
                api_base = api_base + 'v1'
            else:
                api_base = api_base + '/v1'
        
        models_url = f"{api_base}/models"
        
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.HTTP_MEDIUM) as client:
                response = await client.get(models_url, headers=headers)
                
                # 检查响应内容类型
                content_type = response.headers.get("content-type", "")
                
                if response.status_code == 200:
                    # 检测是否返回了HTML而非JSON（常见错误）
                    response_text = response.text.strip()
                    if response_text.startswith("<!DOCTYPE") or response_text.startswith("<html"):
                        return JSONResponse({
                            "success": False,
                            "error": "API返回了HTML页面而非模型列表。该服务可能不支持 /models 端点，请手动输入模型名称",
                            "models": [],
                            "hint": "常用模型: gpt-4, gpt-3.5-turbo, claude-3-opus, gemini-pro 等"
                        })
                    
                    try:
                        data = response.json()
                    except (ValueError, json.JSONDecodeError):
                        return JSONResponse({
                            "success": False,
                            "error": "API返回的不是有效的JSON格式，请手动输入模型名称",
                            "models": []
                        })
                    
                    # 兼容OpenAI格式
                    models = []
                    if isinstance(data, dict) and "data" in data:
                        for m in data["data"]:
                            if isinstance(m, dict):
                                model_id = m.get("id") or m.get("name") or m.get("model")
                                if model_id and isinstance(model_id, str):
                                    models.append(model_id)
                            elif isinstance(m, str):
                                models.append(m)
                    elif isinstance(data, list):
                        for m in data:
                            if isinstance(m, dict):
                                model_id = m.get("id") or m.get("name") or m.get("model")
                                if model_id and isinstance(model_id, str):
                                    models.append(model_id)
                            elif isinstance(m, str):
                                models.append(m)
                    
                    # 过滤无效值（如HTML内容）
                    valid_models = []
                    for m in models:
                        if m and isinstance(m, str) and len(m) < 200 and not m.startswith("<"):
                            valid_models.append(m)
                    
                    if valid_models:
                        # 排序
                        valid_models = sorted(valid_models)
                        return JSONResponse({
                            "success": True,
                            "models": valid_models
                        })
                    else:
                        return JSONResponse({
                            "success": False,
                            "error": "未能解析到有效的模型列表，请手动输入模型名称",
                            "models": [],
                            "hint": "常用模型: gpt-4, gpt-3.5-turbo, claude-3-opus, gemini-pro 等"
                        })
                else:
                    return JSONResponse({
                        "success": False,
                        "error": f"API返回错误 (HTTP {response.status_code})，请手动输入模型名称",
                        "models": []
                    })
        except httpx.TimeoutException:
            return JSONResponse({
                "success": False,
                "error": "连接超时，请检查API地址是否正确",
                "models": []
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"获取失败: {str(e)}",
                "models": []
            })
    
    # ========== 对话API (沟通Agent) ==========
    
    class ChatRequest(BaseModel):
        """对话请求"""
        message: str
        session_id: str = "default"
    
    # 存储对话会话
    chat_sessions = {}
    
    @app.post("/api/chat/start")
    async def start_chat(session_id: str = "default"):
        """开始新对话"""
        from ..agents import CommunicatorAgent
        
        agent = CommunicatorAgent()
        opening = await agent.start_conversation()
        chat_sessions[session_id] = agent
        
        return JSONResponse({
            "session_id": session_id,
            "reply": opening,
            "is_complete": False
        })
    
    @app.post("/api/chat")
    async def chat(request: ChatRequest):
        """发送对话消息（增强版：集成智能路由）"""
        from ..agents import CommunicatorAgent
        from ..prompts import check_user_input_security, get_security_response
        
        session_id = request.session_id
        
        # 安全检查 - 检测是否有探测系统提示词的企图
        is_safe, processed_message = check_user_input_security(request.message)
        if not is_safe:
            # 检测到安全威胁，返回标准拒绝回复
            return JSONResponse({
                "reply": get_security_response(),
                "is_complete": False
            })
        
        # 获取或创建会话
        if session_id not in chat_sessions:
            agent = CommunicatorAgent()
            
            # 为沟通智能体配置知识库和路由器
            if router_agent:
                agent.set_router_agent(router_agent)
                if router_agent.knowledge_base:
                    agent.set_knowledge_base(router_agent.knowledge_base)
            
            await agent.start_conversation()
            chat_sessions[session_id] = agent
        
        agent = chat_sessions[session_id]
        
        try:
            result = await agent.chat(processed_message)
            
            # 响应保证：如果没有回复，使用路由智能体生成
            if not result.get("reply") and router_agent:
                router_result = await router_agent.route_and_respond(processed_message)
                result["reply"] = router_result.get("response", "抱歉，我暂时无法理解您的需求。")
                result["routed"] = True
            
            return JSONResponse(result)
            
        except Exception as e:
            logger.error(f"[Chat] 处理失败: {e}")
            # 响应保证：即使出错也返回友好提示
            return JSONResponse({
                "reply": "抱歉，处理您的请求时遇到问题。请稍后重试。",
                "is_complete": False,
                "error": str(e)
            })
    
    @app.post("/api/chat/complete")
    async def complete_chat(session_id: str = "default"):
        """完成对话，获取结构化需求"""
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        agent = chat_sessions[session_id]
        requirements = await agent.get_structured_requirements()
        
        # 清理会话
        del chat_sessions[session_id]
        
        return JSONResponse({
            "success": True,
            "requirements": requirements
        })
    
    # ===== 用户输入提交API =====
    
    class UserInputRequest(BaseModel):
        """用户输入请求"""
        request_id: str
        user_input: str
    
    @app.post("/api/user-input")
    async def submit_user_input(request: UserInputRequest):
        """提交用户输入（响应Agent的输入请求）"""
        if not coordinator:
            raise HTTPException(status_code=500, detail="Coordinator not initialized")
        
        try:
            await coordinator.submit_user_input(request.request_id, request.user_input)
            return JSONResponse({"success": True})
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    @app.get("/api/message-bus/stats")
    async def get_message_bus_stats():
        """获取消息总线统计"""
        from ..agents.message_bus import get_message_bus
        bus = get_message_bus()
        return JSONResponse(bus.get_stats())
    
    @app.get("/api/message-bus/dead-letters")
    async def get_dead_letters():
        """获取死信队列"""
        from ..agents.message_bus import get_message_bus
        bus = get_message_bus()
        dead_letters = bus.get_dead_letters()
        return JSONResponse({
            "count": len(dead_letters),
            "messages": [msg.to_dict() for msg in dead_letters[:50]]  # 最多返回50条
        })
    
    # ===== 项目管理API =====
    
    class ProjectCreateRequest(BaseModel):
        name: str
        description: str = ""
    
    class ProjectUpdateRequest(BaseModel):
        name: str = None
        description: str = None
    
    @app.get("/api/projects")
    async def list_projects():
        """获取项目列表"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        return JSONResponse({
            "projects": pm.list_projects(),
            "current_project_id": pm.current_project_id
        })
    
    @app.post("/api/projects")
    async def create_project(request: ProjectCreateRequest):
        """创建新项目"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        project = pm.create_project(request.name, request.description)
        return JSONResponse({
            "success": True,
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description
            }
        })
    
    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str):
        """获取项目详情"""
        from ..project_manager import get_project_manager
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
            "chapter_count": project.chapter_count
        })
    
    @app.post("/api/projects/{project_id}/switch")
    async def switch_project(project_id: str):
        """切换当前项目"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        if pm.switch_project(project_id):
            return JSONResponse({"success": True})
        raise HTTPException(status_code=404, detail="Project not found")
    
    @app.put("/api/projects/{project_id}")
    async def update_project(project_id: str, request: ProjectUpdateRequest):
        """更新项目信息"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        project = pm.update_project(project_id, **updates)
        if project:
            return JSONResponse({"success": True})
        raise HTTPException(status_code=404, detail="Project not found")
    
    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str):
        """删除项目"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        if pm.delete_project(project_id):
            return JSONResponse({"success": True})
        raise HTTPException(status_code=400, detail="Cannot delete project")
    
    # ===== 项目数据API =====
    
    # ========== 知识库配置API ==========
    
    class KnowledgeBaseConfigRequest(BaseModel):
        """知识库配置请求"""
        # 硅基流动API配置
        siliconflow_api_key: str = ""
        siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
        siliconflow_model: str = "BAAI/bge-m3"
        siliconflow_embedding_dim: int = 1024
        # 分块配置
        chunk_size: int = 500
        chunk_overlap: int = 50
        # 检索配置
        vector_weight: float = 0.7
        fulltext_weight: float = 0.3
        default_top_k: int = 5
    
    @app.get("/api/knowledge-base/config")
    async def get_knowledge_base_config():
        """获取知识库配置"""
        # 从环境变量和配置文件加载当前配置
        config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
        
        # 默认配置
        default_config = {
            "siliconflow_api_key": os.getenv("SILICONFLOW_API_KEY", ""),
            "siliconflow_base_url": os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
            "siliconflow_model": os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3"),
            "siliconflow_embedding_dim": int(os.getenv("SILICONFLOW_EMBEDDING_DIM", "1024")),
            "chunk_size": 500,
            "chunk_overlap": 50,
            "vector_weight": 0.7,
            "fulltext_weight": 0.3,
            "default_top_k": 5
        }
        
        # 尝试从配置文件加载
        if config_path.exists():
            try:
                saved_config = json.loads(config_path.read_text(encoding="utf-8"))
                default_config.update(saved_config)
            except Exception:
                pass
        
        # 掩码API Key
        api_key = default_config.get("siliconflow_api_key", "")
        return JSONResponse({
            "siliconflow_api_key": api_key[:8] + "****" if len(api_key) > 8 else "",
            "siliconflow_api_key_set": bool(api_key),
            "siliconflow_base_url": default_config.get("siliconflow_base_url", ""),
            "siliconflow_model": default_config.get("siliconflow_model", ""),
            "siliconflow_embedding_dim": default_config.get("siliconflow_embedding_dim", 1024),
            "chunk_size": default_config.get("chunk_size", 500),
            "chunk_overlap": default_config.get("chunk_overlap", 50),
            "vector_weight": default_config.get("vector_weight", 0.7),
            "fulltext_weight": default_config.get("fulltext_weight", 0.3),
            "default_top_k": default_config.get("default_top_k", 5),
            "is_configured": bool(api_key)
        })
    
    @app.post("/api/knowledge-base/config")
    async def save_knowledge_base_config(request: KnowledgeBaseConfigRequest):
        """保存知识库配置"""
        config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
        env_path = Path(__file__).parent.parent.parent / ".env"
        
        # 加载现有配置
        existing_config = {}
        if config_path.exists():
            try:
                existing_config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        # 更新配置（如果API Key是掩码，不更新）
        api_key = request.siliconflow_api_key
        if api_key.endswith("****"):
            api_key = existing_config.get("siliconflow_api_key", "")
        
        new_config = {
            "siliconflow_api_key": api_key,
            "siliconflow_base_url": request.siliconflow_base_url,
            "siliconflow_model": request.siliconflow_model,
            "siliconflow_embedding_dim": request.siliconflow_embedding_dim,
            "chunk_size": request.chunk_size,
            "chunk_overlap": request.chunk_overlap,
            "vector_weight": request.vector_weight,
            "fulltext_weight": request.fulltext_weight,
            "default_top_k": request.default_top_k
        }
        
        # 保存到JSON配置文件
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(new_config, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # 同时更新.env文件中的硅基流动配置
        env_content = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_content[key.strip()] = value.strip()
        
        # 更新硅基流动相关环境变量
        if api_key:
            env_content["SILICONFLOW_API_KEY"] = api_key
        env_content["SILICONFLOW_BASE_URL"] = request.siliconflow_base_url
        env_content["SILICONFLOW_EMBEDDING_MODEL"] = request.siliconflow_model
        env_content["SILICONFLOW_EMBEDDING_DIM"] = str(request.siliconflow_embedding_dim)
        
        # 写入.env文件
        lines = []
        lines.append("# OpenAI兼容API配置")
        lines.append(f"OPENAI_API_KEY={env_content.get('OPENAI_API_KEY', '')}")
        lines.append(f"OPENAI_API_BASE={env_content.get('OPENAI_API_BASE', '')}")
        lines.append(f"OPENAI_MODEL={env_content.get('OPENAI_MODEL', 'gpt-4')}")
        lines.append("")
        lines.append("# 硅基流动向量模型配置")
        lines.append(f"SILICONFLOW_API_KEY={env_content.get('SILICONFLOW_API_KEY', '')}")
        lines.append(f"SILICONFLOW_BASE_URL={env_content.get('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')}")
        lines.append(f"SILICONFLOW_EMBEDDING_MODEL={env_content.get('SILICONFLOW_EMBEDDING_MODEL', 'BAAI/bge-m3')}")
        lines.append(f"SILICONFLOW_EMBEDDING_DIM={env_content.get('SILICONFLOW_EMBEDDING_DIM', '1024')}")
        lines.append("")
        lines.append("# 服务配置")
        lines.append(f"HOST={env_content.get('HOST', '0.0.0.0')}")
        lines.append(f"PORT={env_content.get('PORT', '8000')}")
        lines.append(f"DEBUG={env_content.get('DEBUG', 'false')}")
        lines.append("")
        lines.append("# 生成配置")
        lines.append(f"MAX_TOKENS={env_content.get('MAX_TOKENS', '4096')}")
        lines.append(f"TEMPERATURE={env_content.get('TEMPERATURE', '0.7')}")
        
        env_path.write_text("\n".join(lines), encoding="utf-8")
        
        return JSONResponse({"success": True, "message": "知识库配置已保存"})
    
    class TestEmbeddingRequest(BaseModel):
        """测试向量化服务请求"""
        api_base: str = ""
        api_key: str = ""
        model: str = ""
    
    @app.post("/api/knowledge-base/test-embedding")
    async def test_embedding_connection(request: TestEmbeddingRequest = None):
        """测试向量化服务连接"""
        import time
        
        # 从请求参数或配置文件加载配置
        config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
        
        # 优先使用请求参数
        # 检查是否是掩码格式（前端使用 •••••••• 或 ****）
        is_masked = False
        if request and request.api_key:
            masked_patterns = ["••••••••", "********", "****"]
            is_masked = any(request.api_key.endswith(p) or request.api_key == p for p in masked_patterns)
        
        if request and request.api_key and not is_masked:
            api_key = request.api_key
            base_url = request.api_base or "https://api.siliconflow.cn/v1"
            model = request.model or "BAAI/bge-m3"
        else:
            # 从配置文件加载
            api_key = os.getenv("SILICONFLOW_API_KEY", "")
            base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
            model = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
            
            if config_path.exists():
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    api_key = config.get("siliconflow_api_key", api_key)
                    base_url = config.get("siliconflow_base_url", base_url)
                    model = config.get("siliconflow_model", model)
                except Exception:
                    pass
        
        if not api_key:
            return JSONResponse({
                "success": False,
                "error": "未配置硅基流动API密钥"
            })
        
        try:
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "input": ["测试文本"],
                        "encoding_format": "float"
                    }
                )
                
                response_time = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    data = response.json()
                    embedding_dim = len(data.get("data", [{}])[0].get("embedding", []))
                    return JSONResponse({
                        "success": True,
                        "message": "向量化服务连接成功！",
                        "model": model,
                        "embedding_dim": embedding_dim,
                        "response_time": response_time
                    })
                elif response.status_code == 401:
                    return JSONResponse({
                        "success": False,
                        "error": "API密钥无效或已过期"
                    })
                else:
                    return JSONResponse({
                        "success": False,
                        "error": f"请求失败 (HTTP {response.status_code}): {response.text[:200]}"
                    })
                    
        except httpx.TimeoutException:
            return JSONResponse({
                "success": False,
                "error": "连接超时，请检查网络或API地址"
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"连接失败: {str(e)}"
            })
    
    # ========== 资料库文件导入API ==========
    
    class ImportFileRequest(BaseModel):
        """导入文件请求"""
        content: str  # 文件内容（UTF-8文本）
        filename: str  # 文件名
        category_id: str  # 目标分类ID
        category_key: str = ""  # 分类存储键
        title: str = ""  # 可选的标题覆盖
        split_mode: str = "auto"  # 分割模式: auto, paragraph, none
    
    class CreateCategoryRequest(BaseModel):
        """创建分类请求"""
        name: str
        icon: str = "ri-folder-line"
    
    @app.post("/api/knowledge-base/import-file")
    async def import_file_to_knowledge(request: ImportFileRequest):
        """
        导入文件到资料库
        
        支持 .txt 和 .md 文件，UTF-8编码
        """
        try:
            # 解析文件名获取标题
            filename = request.filename
            title = request.title or filename.rsplit('.', 1)[0] if '.' in filename else filename
            
            content = request.content
            
            # 根据分割模式处理内容
            if request.split_mode == "paragraph":
                # 按段落分割，每个段落作为单独条目
                paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                items = []
                for i, para in enumerate(paragraphs):
                    if len(para) > 20:  # 过滤太短的段落
                        items.append({
                            "id": f"{int(__import__('time').time() * 1000)}_{i}",
                            "name": f"{title} - 片段{i+1}",
                            "description": para[:100] + "..." if len(para) > 100 else para,
                            "details": para,
                            "source_file": filename,
                            "created_at": __import__('datetime').datetime.now().isoformat()
                        })
                return JSONResponse({
                    "success": True,
                    "items": items,
                    "count": len(items),
                    "message": f"已解析 {len(items)} 个段落"
                })
            elif request.split_mode == "chapter":
                # 按章节标记分割 (支持 # 标题 或 第X章)
                import re
                chapter_pattern = r'(?:^|\n)(#{1,3}\s+.+|第[一二三四五六七八九十百千万\d]+章.*)(?:\n|$)'
                parts = re.split(chapter_pattern, content)
                
                items = []
                current_title = title
                current_content = ""
                
                for i, part in enumerate(parts):
                    part = part.strip()
                    if not part:
                        continue
                    
                    # 检查是否是标题行
                    if re.match(r'^#{1,3}\s+', part) or re.match(r'^第[一二三四五六七八九十百千万\d]+章', part):
                        # 保存上一个章节
                        if current_content:
                            items.append({
                                "id": f"{int(__import__('time').time() * 1000)}_{len(items)}",
                                "name": current_title,
                                "description": current_content[:100] + "..." if len(current_content) > 100 else current_content,
                                "details": current_content,
                                "source_file": filename,
                                "created_at": __import__('datetime').datetime.now().isoformat()
                            })
                        current_title = part.lstrip('#').strip()
                        current_content = ""
                    else:
                        current_content += part + "\n"
                
                # 保存最后一个章节
                if current_content:
                    items.append({
                        "id": f"{int(__import__('time').time() * 1000)}_{len(items)}",
                        "name": current_title,
                        "description": current_content[:100] + "..." if len(current_content) > 100 else current_content,
                        "details": current_content.strip(),
                        "source_file": filename,
                        "created_at": __import__('datetime').datetime.now().isoformat()
                    })
                
                return JSONResponse({
                    "success": True,
                    "items": items,
                    "count": len(items),
                    "message": f"已解析 {len(items)} 个章节"
                })
            else:
                # 整个文件作为一个条目
                item = {
                    "id": str(int(__import__('time').time() * 1000)),
                    "name": title,
                    "description": content[:200] + "..." if len(content) > 200 else content,
                    "details": content,
                    "source_file": filename,
                    "created_at": __import__('datetime').datetime.now().isoformat()
                }
                return JSONResponse({
                    "success": True,
                    "items": [item],
                    "count": 1,
                    "message": f"已导入文件: {filename}"
                })
                
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"导入失败: {str(e)}",
                "items": [],
                "count": 0
            })
    
    @app.post("/api/knowledge-base/categories")
    async def create_knowledge_category(request: CreateCategoryRequest):
        """创建新的资料分类"""
        import time
        
        category_id = f"db-custom-{int(time.time() * 1000)}"
        category_key = f"custom_{int(time.time() * 1000)}"
        
        return JSONResponse({
            "success": True,
            "category": {
                "id": category_id,
                "key": category_key,
                "name": request.name,
                "icon": request.icon,
                "builtin": False
            }
        })
    
    @app.get("/api/knowledge-base/stats")
    async def get_knowledge_base_stats():
        """获取知识库统计信息"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        
        if not pm.current_project_id:
            return JSONResponse({
                "configured": False,
                "message": "请先选择一个项目"
            })
        
        # 获取知识库数据目录（位于工作区根目录的 data/knowledge_base）
        data_dir = Path(__file__).parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
        
        stats = {
            "configured": False,
            "project_id": pm.current_project_id,
            "chapter_count": 0,
            "chunk_count": 0,
            "vector_count": 0,
            "storage_size_mb": 0,
            "chapters": []  # 章节列表用于按章节删除
        }
        
        if data_dir.exists():
            stats["configured"] = True
            
            # 计算存储大小
            total_size = 0
            for f in data_dir.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size
            stats["storage_size_mb"] = round(total_size / (1024 * 1024), 2)
            
            # 尝试获取章节数和分块数
            db_path = data_dir / "knowledge.db"
            if db_path.exists():
                import sqlite3
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    
                    # 检查表是否存在
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chapters'")
                    if cursor.fetchone():
                        cursor.execute("SELECT COUNT(*) FROM chapters")
                        stats["chapter_count"] = cursor.fetchone()[0]
                        
                        # 获取章节列表
                        cursor.execute("SELECT chapter_id, title, chapter_number FROM chapters ORDER BY chapter_number")
                        stats["chapters"] = [
                            {"chapter_id": row[0], "title": row[1], "chapter_number": row[2]}
                            for row in cursor.fetchall()
                        ]
                    
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
                    if cursor.fetchone():
                        cursor.execute("SELECT COUNT(*) FROM chunks")
                        stats["chunk_count"] = cursor.fetchone()[0]
                    
                    conn.close()
                except Exception as e:
                    print(f"获取知识库统计信息失败: {e}")
            
            # 获取向量数（Chroma）
            chroma_dir = data_dir / "chroma"
            if chroma_dir.exists():
                try:
                    import chromadb
                    client = chromadb.PersistentClient(path=str(chroma_dir))
                    collection = client.get_or_create_collection("novel_knowledge")
                    stats["vector_count"] = collection.count()
                except Exception:
                    pass
        
        return JSONResponse(stats)
    
    class ClearKnowledgeBaseRequest(BaseModel):
        """清除知识库请求"""
        clear_all: bool = False  # 是否清除整个知识库
        chapter_ids: List[str] = []  # 要清除的章节ID列表
    
    @app.post("/api/knowledge-base/clear")
    async def clear_knowledge_base(request: ClearKnowledgeBaseRequest):
        """
        清除知识库数据
        
        支持两种模式：
        1. 清除整个知识库（clear_all=True）
        2. 清除指定章节（提供chapter_ids列表）
        """
        from ..project_manager import get_project_manager
        import shutil
        import sqlite3
        
        pm = get_project_manager()
        
        if not pm.current_project_id:
            return JSONResponse({
                "success": False,
                "error": "请先选择一个项目"
            })
        
        data_dir = Path(__file__).parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
        
        if not data_dir.exists():
            return JSONResponse({
                "success": True,
                "message": "知识库为空，无需清除"
            })
        
        try:
            if request.clear_all:
                # 清除整个项目的知识库
                shutil.rmtree(data_dir)
                data_dir.mkdir(parents=True, exist_ok=True)
                
                return JSONResponse({
                    "success": True,
                    "message": f"已清除项目 {pm.current_project_id} 的所有知识库数据"
                })
            
            elif request.chapter_ids:
                # 清除指定章节
                deleted_count = 0
                db_path = data_dir / "knowledge.db"
                chroma_dir = data_dir / "chroma"
                
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    
                    for chapter_id in request.chapter_ids:
                        # 删除章节
                        cursor.execute("DELETE FROM chapters WHERE chapter_id = ?", (chapter_id,))
                        
                        # 删除相关的chunks
                        cursor.execute("DELETE FROM chunks WHERE chapter_id = ?", (chapter_id,))
                        
                        # 删除FTS索引（如果存在）
                        try:
                            cursor.execute("DELETE FROM chunks_fts WHERE chapter_id = ?", (chapter_id,))
                        except:
                            pass
                        
                        deleted_count += cursor.rowcount
                    
                    conn.commit()
                    conn.close()
                
                # 从向量数据库中删除
                if chroma_dir.exists():
                    try:
                        import chromadb
                        client = chromadb.PersistentClient(path=str(chroma_dir))
                        collection = client.get_or_create_collection("novel_knowledge")
                        
                        for chapter_id in request.chapter_ids:
                            # 删除该章节的所有向量
                            collection.delete(where={"chapter_id": chapter_id})
                    except Exception as e:
                        print(f"从向量库删除失败: {e}")
                
                return JSONResponse({
                    "success": True,
                    "message": f"已清除 {len(request.chapter_ids)} 个章节的知识库数据",
                    "deleted_chapters": request.chapter_ids
                })
            
            else:
                return JSONResponse({
                    "success": False,
                    "error": "请指定清除全部（clear_all=True）或提供章节ID列表（chapter_ids）"
                })
                
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"清除失败: {str(e)}"
            })
    
    @app.delete("/api/knowledge-base/chapter/{chapter_id}")
    async def delete_knowledge_chapter(chapter_id: str):
        """删除知识库中的单个章节"""
        from ..project_manager import get_project_manager
        import sqlite3
        
        pm = get_project_manager()
        
        if not pm.current_project_id:
            raise HTTPException(status_code=400, detail="请先选择一个项目")
        
        data_dir = Path(__file__).parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
        db_path = data_dir / "knowledge.db"
        chroma_dir = data_dir / "chroma"
        
        deleted = False
        
        try:
            # 从SQLite删除
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chapters WHERE chapter_id = ?", (chapter_id,))
                cursor.execute("DELETE FROM chunks WHERE chapter_id = ?", (chapter_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                conn.close()
            
            # 从Chroma删除
            if chroma_dir.exists():
                try:
                    import chromadb
                    client = chromadb.PersistentClient(path=str(chroma_dir))
                    collection = client.get_or_create_collection("novel_knowledge")
                    collection.delete(where={"chapter_id": chapter_id})
                except Exception:
                    pass
            
            if deleted:
                return JSONResponse({
                    "success": True,
                    "message": f"章节 {chapter_id} 已从知识库删除"
                })
            else:
                return JSONResponse({
                    "success": False,
                    "error": "章节不存在"
                })
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    
    @app.get("/api/project-data/{data_type}")
    async def get_project_data(data_type: str):
        """获取当前项目的数据（characters, outline, worldbuilding, items）"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        
        # 检查是否有当前项目
        if not pm.current_project_id:
            return JSONResponse({
                "data": [],
                "error": "请先选择或创建一个项目",
                "no_project": True
            })
        
        try:
            data = pm.load_project_data(data_type)
            return JSONResponse({"data": data})
        except ValueError as e:
            return JSONResponse({
                "data": [],
                "error": str(e)
            })
    
    @app.post("/api/project-data/{data_type}")
    async def save_project_data(data_type: str, request: Request):
        """保存当前项目的数据"""
        from ..project_manager import get_project_manager
        pm = get_project_manager()
        
        # 检查是否有当前项目
        if not pm.current_project_id:
            return JSONResponse({
                "success": False,
                "error": "请先选择或创建一个项目"
            }, status_code=400)
        
        try:
            body = await request.json()
            data = body.get("data", [])
            pm.save_project_data(data_type, data)
            return JSONResponse({"success": True})
        except ValueError as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            }, status_code=400)
    
    # ===== 无限续写API =====
    
    # 存储无限续写Agent实例（内存缓存，持久化数据在 session_store 中）
    continuous_writers = {}
    
    class ContinuousWriteStartRequest(BaseModel):
        """开始无限续写请求"""
        story_beginning: str  # 故事开头或灵感
        session_id: str = "default"
        words_per_chapter: int = 2500
        model: str = ""  # 可选的模型名称
        api_config_id: str = ""  # 可选的API配置ID，用于选择特定的API配置
        enable_trends: bool = False  # 是否启用热点融合
        trends_platforms: List[str] = []  # 热点搜索平台
        trends_query: str = ""  # 热点搜索关键词
        current_chapter: int = 0  # 恢复会话时的当前章节号（用于会话过期后恢复）
        recovered_chapters: List[dict] = []  # 恢复会话时的完整章节数据（确保上下文连贯）
        auto_restore: bool = True  # 是否自动从持久化存储恢复会话
    
    class ContinuousWriteContinueRequest(BaseModel):
        """继续续写请求"""
        session_id: str = "default"
        inspiration: str = ""  # 可选的新灵感
        model: str = ""  # 可选的模型名称
        api_config_id: str = ""  # 可选的API配置ID，用于选择特定的API配置
        enable_trends: bool = False  # 是否启用热点融合
        trends_platforms: List[str] = []  # 热点搜索平台
    
    class ContinuousWriteInspirationRequest(BaseModel):
        """添加灵感请求"""
        session_id: str = "default"
        inspiration: str  # 灵感内容
        chapter: int = 0  # 0表示下一章
    
    class ContinuousWriteCorrectionRequest(BaseModel):
        """添加剧情纠正请求"""
        session_id: str = "default"
        correction: str  # 纠正内容
        chapter: int = 0  # 0表示下一章
    
    @app.post("/api/continuous-write/start")
    async def start_continuous_write(request: ContinuousWriteStartRequest):
        """
        开始无限续写
        
        根据用户提供的故事开头或灵感开始创作第一章
        支持会话持久化：服务重启后可自动恢复，换模型后保持连贯
        """
        from ..agents import ContinuousWriter, ContinuousWriteConfig
        from ..agents.session_store import get_session_store
        from ..agent_config import AgentModelConfig
        from ..project_manager import get_project_manager
        
        session_id = request.session_id
        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        
        # 检查是否需要从持久化存储恢复会话
        session_store = get_session_store()
        existing_session = session_store.load(session_id, project_id) if request.auto_restore else None
        
        if existing_session and existing_session.chapters:
            logger.info(f"[ContinuousWrite] 发现持久化会话，已有 {len(existing_session.chapters)} 章")
        
        # 创建配置
        write_config = ContinuousWriteConfig(
            words_per_chapter=request.words_per_chapter,
            auto_save_to_kb=True,
            check_consistency=True,
            enable_trends_search=request.enable_trends,
            trends_platforms=request.trends_platforms if request.trends_platforms else ["zhihu", "douban"]
        )
        
        # 创建模型配置
        # 使用全局配置管理器获取有效配置，确保使用正确的 API 地址
        from ..agent_config import get_config_manager
        config_manager = get_config_manager()
        
        # 获取API配置：优先使用指定的api_config_id，否则使用激活的全局配置
        api_base = ""
        api_key = ""
        temperature = LLM_DEFAULTS.TEMPERATURE
        max_tokens = LLM_DEFAULTS.MAX_TOKENS
        model_name = request.model
        
        if request.api_config_id:
            # 使用指定的API配置
            multi_config = config_manager.get_multi_config()
            for cfg in multi_config.configs:
                if cfg.id == request.api_config_id:
                    api_base = cfg.api_base
                    api_key = cfg.api_key
                    temperature = cfg.temperature
                    max_tokens = cfg.max_tokens
                    if not model_name and cfg.models:
                        model_name = cfg.models[0]
                    logger.info(f"[ContinuousWrite] 使用指定的API配置: {cfg.name} ({cfg.id})")
                    break
        
        # 如果没有找到指定配置，回退到全局配置
        if not api_base or not api_key:
            global_config = config_manager.get_global_config()
            api_base = global_config.api_base
            api_key = global_config.api_key
            temperature = global_config.temperature
            max_tokens = global_config.max_tokens
            if not model_name:
                model_name = global_config.model
            logger.info("[ContinuousWrite] 使用激活的全局API配置")
        
        model_config = None
        if model_name:
            # 指定了模型时，使用选中配置的 API 地址，但使用指定的模型
            model_config = AgentModelConfig(
                agent_name="ContinuousWriter",
                api_base=api_base,
                api_key=api_key,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                use_global=False  # 使用显式提供的配置
            )
        # 如果没有指定模型，model_config 为 None，Agent 会自动使用全局配置
        
        # 创建Agent实例，传入会话ID和项目ID以支持持久化
        writer = ContinuousWriter(
            write_config=write_config,
            model_config=model_config,
            session_id=session_id,
            project_id=project_id
        )
        
        # 设置当前使用的模型（用于追踪模型切换）
        if model_name:
            writer.set_model(model_name)
        
        # 尝试获取知识库实例（必须配置真实向量化服务，不使用模拟）
        pm = get_project_manager()
        if pm.current_project_id:
            try:
                from ..knowledge_base import KnowledgeBase
                from ..knowledge_base.data_layer.vector_store import CHROMA_AVAILABLE, CHROMA_IMPORT_ERROR
                
                # 首先检查ChromaDB是否可用
                if not CHROMA_AVAILABLE:
                    logger.error(
                        f"[ContinuousWriter] ChromaDB不可用: {CHROMA_IMPORT_ERROR}。"
                        "请运行: pip install chromadb"
                    )
                else:
                    # 检查是否配置了向量化服务
                    config_path = Path(__file__).parent.parent / "data" / "knowledge_base_config.json"
                    
                    has_api_key = False
                    if config_path.exists():
                        try:
                            kb_config = json.loads(config_path.read_text(encoding="utf-8"))
                            has_api_key = bool(kb_config.get("siliconflow_api_key"))
                        except Exception:
                            pass
                    
                    if has_api_key:
                        # 有API Key，初始化真实知识库（不使用mock）
                        kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=False)
                        writer.set_knowledge_base(kb)
                        logger.info("[ContinuousWriter] ✓ 知识库已配置（使用真实向量存储）")
                    else:
                        # 没有API Key，不使用知识库
                        logger.info(
                            "[ContinuousWriter] 未配置向量化API Key，跳过知识库功能。"
                            "如需启用知识库，请在设置中配置SiliconFlow API Key。"
                        )
            except ImportError as e:
                # ChromaDB导入失败
                logger.error(f"[ContinuousWriter] 知识库初始化失败（ChromaDB不可用）: {e}")
            except ValueError as e:
                # 配置错误
                logger.warning(f"[ContinuousWriter] 知识库配置错误: {e}")
            except Exception as e:
                # 其他错误
                logger.warning(f"[ContinuousWriter] 知识库初始化失败: {e}")
        
        # 保存实例到内存缓存
        continuous_writers[session_id] = writer
        
        # 执行开始创作
        result = await writer.execute({
            "action": "start",
            "content": request.story_beginning,
            "trends_query": request.trends_query if request.enable_trends else "",
            "current_chapter": request.current_chapter,  # 传递当前章节号（用于会话恢复）
            "recovered_chapters": request.recovered_chapters  # 传递完整章节数据（确保上下文连贯）
        })
        
        # 添加会话信息到响应
        result["session_id"] = session_id
        result["project_id"] = project_id
        result["model_used"] = model_name
        
        return JSONResponse(result)
    
    @app.post("/api/continuous-write/continue")
    async def continue_continuous_write(request: ContinuousWriteContinueRequest):
        """
        继续续写下一章
        
        基于已有内容续写下一章，可选择性地加入新灵感
        支持热点融合：如果启用，会先搜索热点再创作
        支持模型切换：换模型后自动传递完整上下文保持连贯性
        """
        from ..agent_config import AgentModelConfig
        from ..agents.session_store import get_session_store
        from ..project_manager import get_project_manager
        
        session_id = request.session_id
        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        
        # 尝试从内存缓存获取，如果不存在则尝试从持久化存储恢复
        if session_id not in continuous_writers:
            session_store = get_session_store()
            existing_session = session_store.load(session_id, project_id)
            
            if existing_session and existing_session.chapters:
                # 从持久化存储恢复会话
                logger.info(f"[ContinuousWrite] 从持久化存储恢复会话 {session_id}，已有 {len(existing_session.chapters)} 章")
                
                from ..agents import ContinuousWriter, ContinuousWriteConfig
                
                write_config = ContinuousWriteConfig(
                    words_per_chapter=existing_session.words_per_chapter,
                    auto_save_to_kb=True,
                    check_consistency=True
                )
                
                # 恢复Writer实例
                writer = ContinuousWriter(
                    write_config=write_config,
                    session_id=session_id,
                    project_id=project_id
                )
                
                # 会话状态会在执行时自动从持久化存储加载
                continuous_writers[session_id] = writer
            else:
                raise HTTPException(status_code=404, detail="续写会话不存在，请先开始新故事")
        
        writer = continuous_writers[session_id]
        
        # 如果指定了新模型或API配置，更新模型配置（包含完整的 API 配置）
        if request.model or request.api_config_id:
            from ..agent_config import get_config_manager
            config_manager = get_config_manager()
            
            # 获取API配置：优先使用指定的api_config_id
            api_base = ""
            api_key = ""
            temperature = LLM_DEFAULTS.TEMPERATURE
            max_tokens = LLM_DEFAULTS.MAX_TOKENS
            
            if request.api_config_id:
                multi_config = config_manager.get_multi_config()
                for cfg in multi_config.configs:
                    if cfg.id == request.api_config_id:
                        api_base = cfg.api_base
                        api_key = cfg.api_key
                        temperature = cfg.temperature
                        max_tokens = cfg.max_tokens
                        logger.info(f"[ContinuousWrite] 续写使用指定的API配置: {cfg.name}")
                        break
            
            # 回退到全局配置
            if not api_base or not api_key:
                global_config = config_manager.get_global_config()
                api_base = global_config.api_base
                api_key = global_config.api_key
                temperature = global_config.temperature
                max_tokens = global_config.max_tokens
            
            # 使用请求中的模型，或从配置中获取第一个模型
            model_to_use = request.model
            if not model_to_use and request.api_config_id:
                multi_config = config_manager.get_multi_config()
                for cfg in multi_config.configs:
                    if cfg.id == request.api_config_id and cfg.models:
                        model_to_use = cfg.models[0]
                        break
            
            if model_to_use:
                model_config = AgentModelConfig(
                    agent_name="ContinuousWriter",
                    api_base=api_base,
                    api_key=api_key,
                    model=model_to_use,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    use_global=False
                )
                writer.model_config = model_config
                # 重新创建客户端以应用新配置
                writer.client = writer._create_client()
                # 更新模型追踪（用于检测模型切换）
                writer.set_model(model_to_use)
        
        # 构建执行参数
        execute_params = {
            "action": "continue",
            "content": request.inspiration
        }
        
        # 如果启用热点融合，添加相关参数
        if request.enable_trends:
            execute_params["trends_query"] = request.inspiration or "热门话题"
            if request.trends_platforms:
                execute_params["trends_platforms"] = request.trends_platforms
        
        result = await writer.execute(execute_params)
        
        return JSONResponse(result)
    
    @app.post("/api/continuous-write/inspiration")
    async def add_inspiration(request: ContinuousWriteInspirationRequest):
        """添加灵感到续写"""
        session_id = request.session_id
        
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        chapter = request.chapter if request.chapter > 0 else writer._current_chapter + 1
        
        result = writer._add_inspiration({
            "content": request.inspiration,
            "chapter": chapter
        })
        
        return JSONResponse(result)
    
    @app.post("/api/continuous-write/correction")
    async def add_correction(request: ContinuousWriteCorrectionRequest):
        """添加剧情纠正"""
        session_id = request.session_id
        
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        chapter = request.chapter if request.chapter > 0 else writer._current_chapter + 1
        
        result = writer._add_correction({
            "content": request.correction,
            "chapter": chapter
        })
        
        return JSONResponse(result)
    
    @app.post("/api/continuous-write/stop")
    async def stop_continuous_write(session_id: str = "default"):
        """停止续写"""
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        result = writer._stop_writing()
        
        return JSONResponse(result)
    
    @app.get("/api/continuous-write/status")
    async def get_continuous_write_status(session_id: str = "default"):
        """获取续写状态"""
        if session_id not in continuous_writers:
            return JSONResponse({
                "session_exists": False,
                "message": "没有活跃的续写会话"
            })
        
        writer = continuous_writers[session_id]
        status = writer._get_status()
        status["session_exists"] = True
        
        return JSONResponse(status)
    
    @app.get("/api/continuous-write/chapters")
    async def get_continuous_write_chapters(session_id: str = "default"):
        """获取所有已写章节"""
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        chapters = writer.get_all_chapters()
        
        return JSONResponse({
            "success": True,
            "total": len(chapters),
            "chapters": chapters
        })
    
    @app.get("/api/continuous-write/chapter/{chapter_number}")
    async def get_continuous_write_chapter(chapter_number: int, session_id: str = "default"):
        """获取指定章节"""
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        result = writer._get_chapter(chapter_number)
        
        return JSONResponse(result)
    
    class UpdateInfiniteWriteChapterRequest(BaseModel):
        """更新无限续写章节请求"""
        chapter_index: int  # 章节索引（从0开始）
        title: Optional[str] = None  # 新标题
        content: Optional[str] = None  # 新内容
    
    @app.put("/api/continuous-write/chapter")
    async def update_continuous_write_chapter(request: UpdateInfiniteWriteChapterRequest, session_id: str = "default"):
        """更新无限续写章节（标题或内容）"""
        # 注意：此API直接操作前端维护的章节列表，实际数据存储在localStorage
        # 这里主要用于记录操作日志和可能的后端知识库同步
        
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[ContinuousWrite] 更新章节: index={request.chapter_index}, "
                   f"title_changed={request.title is not None}, "
                   f"content_changed={request.content is not None}")
        
        # 如果存在会话，尝试更新会话中的章节数据
        if session_id in continuous_writers:
            writer = continuous_writers[session_id]
            chapters = writer._written_chapters
            
            if 0 <= request.chapter_index < len(chapters):
                chapter = chapters[request.chapter_index]
                
                if request.title is not None:
                    chapter["title"] = request.title
                
                if request.content is not None:
                    chapter["content"] = request.content
                    # 重新计算字数
                    import re
                    chapter["word_count"] = len(re.sub(r'\s+', '', request.content))
                    # 更新摘要
                    chapter["summary"] = request.content[:200] + "..." if len(request.content) > 200 else request.content
                
                return JSONResponse({
                    "success": True,
                    "message": "章节已更新",
                    "chapter": chapter
                })
        
        # 即使没有活跃会话，也返回成功（前端会处理localStorage存储）
        return JSONResponse({
            "success": True,
            "message": "章节更新请求已接收",
            "note": "数据将存储在本地"
        })
    
    class RegexReplaceRequest(BaseModel):
        """正则替换请求"""
        content: str  # 原始内容
        pattern: str  # 正则表达式
        replacement: str  # 替换内容
        flags: str = ""  # 正则标志 (i=忽略大小写, g=全局, m=多行)
    
    @app.post("/api/text/regex-replace")
    async def regex_replace(request: RegexReplaceRequest):
        """执行正则替换"""
        import re
        
        try:
            # 解析标志
            regex_flags = 0
            if 'i' in request.flags:
                regex_flags |= re.IGNORECASE
            if 'm' in request.flags:
                regex_flags |= re.MULTILINE
            if 's' in request.flags:
                regex_flags |= re.DOTALL
            
            # 编译正则表达式
            pattern = re.compile(request.pattern, regex_flags)
            
            # 查找所有匹配
            matches = list(pattern.finditer(request.content))
            match_count = len(matches)
            
            # 执行替换
            if 'g' in request.flags or not request.flags:
                # 全局替换（默认）
                new_content = pattern.sub(request.replacement, request.content)
            else:
                # 只替换第一个
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
    
    @app.post("/api/text/regex-find")
    async def regex_find(request: RegexReplaceRequest):
        """正则查找（预览匹配结果）"""
        import re
        
        try:
            # 解析标志
            regex_flags = 0
            if 'i' in request.flags:
                regex_flags |= re.IGNORECASE
            if 'm' in request.flags:
                regex_flags |= re.MULTILINE
            if 's' in request.flags:
                regex_flags |= re.DOTALL
            
            # 编译正则表达式
            pattern = re.compile(request.pattern, regex_flags)
            
            # 查找所有匹配
            matches = []
            for match in pattern.finditer(request.content):
                # 获取匹配上下文
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
                "matches": matches[:100],  # 最多返回100个匹配
                "total_count": len(matches)
            })
            
        except re.error as e:
            return JSONResponse({
                "success": False,
                "error": f"无效的正则表达式: {str(e)}",
                "matches": [],
                "total_count": 0
            })
    
    @app.delete("/api/continuous-write/session")
    async def delete_continuous_write_session(session_id: str = "default"):
        """删除续写会话（包括持久化数据）"""
        from ..agents.session_store import get_session_store
        from ..project_manager import get_project_manager
        
        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        
        deleted_memory = False
        deleted_storage = False
        
        # 从内存缓存删除
        if session_id in continuous_writers:
            del continuous_writers[session_id]
            deleted_memory = True
        
        # 从持久化存储删除
        session_store = get_session_store()
        if session_store.exists(session_id, project_id):
            session_store.delete(session_id, project_id)
            deleted_storage = True
        
        if deleted_memory or deleted_storage:
            return JSONResponse({
                "success": True,
                "message": "会话已删除",
                "deleted_from_memory": deleted_memory,
                "deleted_from_storage": deleted_storage
            })
        
        return JSONResponse({"success": False, "message": "会话不存在"})
    
    @app.get("/api/continuous-write/sessions")
    async def list_continuous_write_sessions():
        """
        列出所有持久化的续写会话
        
        用于恢复之前的续写会话
        """
        from ..agents.session_store import get_session_store
        from ..project_manager import get_project_manager
        
        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        
        session_store = get_session_store()
        sessions = session_store.list_sessions(project_id)
        
        # 标记哪些会话当前在内存中活跃
        for session in sessions:
            session["active_in_memory"] = session["session_id"] in continuous_writers
        
        return JSONResponse({
            "success": True,
            "sessions": sessions,
            "project_id": project_id
        })
    
    @app.get("/api/continuous-write/session/{session_id}/context")
    async def get_continuous_write_context(session_id: str):
        """
        获取续写会话的上下文信息
        
        用于在换模型或恢复会话时查看当前剧情状态
        """
        from ..agents.session_store import get_session_store
        from ..project_manager import get_project_manager
        
        pm = get_project_manager()
        project_id = pm.current_project_id or ""
        
        session_store = get_session_store()
        context = session_store.get_context_for_continuation(session_id, project_id)
        
        if not context:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return JSONResponse({
            "success": True,
            "context": context
        })
    
    class AddDeadCharacterRequest(BaseModel):
        """添加死亡角色请求"""
        session_id: str = "default"
        character_name: str
    
    @app.post("/api/continuous-write/dead-character")
    async def add_dead_character(request: AddDeadCharacterRequest):
        """
        手动添加死亡角色
        
        确保后续章节不会让该角色复活
        """
        session_id = request.session_id
        
        if session_id not in continuous_writers:
            raise HTTPException(status_code=404, detail="续写会话不存在")
        
        writer = continuous_writers[session_id]
        result = writer._add_dead_character(request.character_name)
        
        return JSONResponse(result)
    
    # ===== 提示词管理API =====
    
    class SavePromptRequest(BaseModel):
        """保存提示词请求"""
        content: str  # 提示词内容
    
    @app.get("/api/prompts")
    async def list_prompts():
        """
        列出所有Agent类型及其可用的任务提示词
        
        返回:
            - agents: Agent类型列表，每个包含name、description和tasks
        """
        try:
            from ..prompts.prompt_manager import get_prompt_manager
            
            pm = get_prompt_manager()
            agents = pm.list_agents()
            
            return JSONResponse({
                "success": True,
                "agents": agents
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"加载Agent列表失败: {str(e)}",
                "agents": []
            })
    
    @app.get("/api/prompts/{agent_type}")
    async def get_agent_prompts(agent_type: str):
        """
        获取指定Agent的所有提示词
        
        Args:
            agent_type: Agent类型（如worldbuilder, chapter_writer等）
        
        返回:
            - system_prompt: 系统提示词（不含安全协议，安全协议已硬编码到系统层级）
            - tasks: 任务提示词列表
            - has_custom: 是否有自定义提示词
        """
        try:
            from ..prompts.prompt_manager import get_prompt_manager
            
            pm = get_prompt_manager()
            
            # 检查是否是无效的agent_type（如元数据键）
            if agent_type.startswith('_'):
                return JSONResponse({
                    "success": False,
                    "error": f"无效的Agent类型: {agent_type}"
                })
            
            # 使用 get_system_prompt_raw 获取不含安全协议的原始提示词
            # 安全协议已硬编码到系统层级，不需要在UI中显示
            system_prompt = pm.get_system_prompt_raw(agent_type)
            tasks = pm.list_tasks(agent_type)
            
            # 检查是否有自定义提示词
            has_custom = {}
            for task in tasks:
                has_custom[task["name"]] = task.get("is_custom", False)
            
            return JSONResponse({
                "success": True,
                "agent_type": agent_type,
                "system_prompt": system_prompt,
                "tasks": tasks,
                "has_custom": has_custom
            })
        except ValueError as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"加载提示词失败: {str(e)}"
            })
    
    @app.get("/api/prompts/{agent_type}/{task_name}")
    async def get_task_prompt(agent_type: str, task_name: str):
        """
        获取指定任务的提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称（如write_chapter, polish等）
        
        返回:
            - prompt: 提示词内容
            - is_custom: 是否为自定义提示词
            - default_prompt: 默认提示词（如果存在自定义，同时返回默认）
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        
        try:
            prompt = pm.get_task_prompt(agent_type, task_name)
            is_custom = pm.has_custom_prompt(agent_type, task_name)
            
            result = {
                "success": True,
                "agent_type": agent_type,
                "task_name": task_name,
                "prompt": prompt,
                "is_custom": is_custom
            }
            
            # 如果是自定义提示词，同时返回默认提示词以便对比
            if is_custom:
                default_prompt = pm.get_default_prompt(agent_type, task_name)
                result["default_prompt"] = default_prompt
            
            return JSONResponse(result)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    
    @app.post("/api/prompts/{agent_type}/{task_name}")
    async def save_custom_prompt(agent_type: str, task_name: str, request: SavePromptRequest):
        """
        保存自定义提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称
            request: 包含content字段的请求体
        
        返回:
            - success: 是否成功
            - message: 消息
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        
        try:
            pm.save_custom_prompt(agent_type, task_name, request.content)
            return JSONResponse({
                "success": True,
                "message": f"已保存 {agent_type}/{task_name} 的自定义提示词"
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.delete("/api/prompts/{agent_type}/{task_name}")
    async def delete_custom_prompt(agent_type: str, task_name: str):
        """
        删除自定义提示词，恢复使用默认提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称
        
        返回:
            - success: 是否成功
            - message: 消息
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        
        try:
            pm.delete_custom_prompt(agent_type, task_name)
            return JSONResponse({
                "success": True,
                "message": f"已删除 {agent_type}/{task_name} 的自定义提示词，将使用默认提示词"
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.post("/api/prompts/reload")
    async def reload_prompts():
        """
        重新加载所有提示词配置
        
        从文件重新读取自定义提示词配置
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        pm.reload()
        
        return JSONResponse({
            "success": True,
            "message": "提示词配置已重新加载"
        })
    
    @app.post("/api/prompts/{agent_type}/system")
    async def save_system_prompt(agent_type: str, request: SavePromptRequest):
        """
        保存自定义系统提示词
        
        Args:
            agent_type: Agent类型
            request: 包含content字段的请求体
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        
        try:
            pm.save_custom_prompt(agent_type, "system", request.content)
            return JSONResponse({
                "success": True,
                "message": f"已保存 {agent_type} 的自定义系统提示词"
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.delete("/api/prompts/{agent_type}/system")
    async def delete_system_prompt(agent_type: str):
        """
        删除自定义系统提示词
        
        Args:
            agent_type: Agent类型
        """
        from ..prompts.prompt_manager import get_prompt_manager
        
        pm = get_prompt_manager()
        
        try:
            pm.delete_custom_prompt(agent_type, "system")
            return JSONResponse({
                "success": True,
                "message": f"已删除 {agent_type} 的自定义系统提示词"
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    # ========== Token统计API ==========
    
    @app.get("/api/token-stats/summary")
    async def get_token_stats_summary(
        days: int = 30,
        model: str = None,
        agent_name: str = None
    ):
        """
        获取Token统计摘要
        
        Args:
            days: 统计天数（默认30天）
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        summary = store.get_summary(days=days, model=model, agent_name=agent_name)
        
        return JSONResponse(summary)
    
    @app.get("/api/token-stats/daily")
    async def get_token_stats_daily(
        days: int = 7,
        model: str = None,
        agent_name: str = None
    ):
        """
        获取每日Token统计
        
        Args:
            days: 统计天数（默认7天）
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        stats = store.get_daily_stats(days=days, model=model, agent_name=agent_name)
        
        return JSONResponse({
            "period": f"{days} days",
            "data": stats
        })
    
    @app.get("/api/token-stats/weekly")
    async def get_token_stats_weekly(
        weeks: int = 4,
        model: str = None,
        agent_name: str = None
    ):
        """
        获取每周Token统计
        
        Args:
            weeks: 统计周数（默认4周）
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        stats = store.get_weekly_stats(weeks=weeks, model=model, agent_name=agent_name)
        
        return JSONResponse({
            "period": f"{weeks} weeks",
            "data": stats
        })
    
    @app.get("/api/token-stats/hourly")
    async def get_token_stats_hourly(
        hours: int = 24,
        model: str = None,
        agent_name: str = None
    ):
        """
        获取小时统计（24小时曲线图数据）
        
        Args:
            hours: 统计小时数（默认24小时）
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        stats = store.get_hourly_stats(hours=hours, model=model, agent_name=agent_name)
        
        return JSONResponse({
            "period": f"{hours} hours",
            "data": stats
        })
    
    @app.get("/api/token-stats/by-model")
    async def get_token_stats_by_model(
        days: int = 30,
        agent_name: str = None
    ):
        """
        获取按模型分组的统计
        
        Args:
            days: 统计天数（默认30天）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        stats = store.get_model_stats(days=days, agent_name=agent_name)
        
        return JSONResponse({
            "period": f"{days} days",
            "data": stats
        })
    
    @app.get("/api/token-stats/by-agent")
    async def get_token_stats_by_agent(
        days: int = 30,
        model: str = None
    ):
        """
        获取按Agent分组的统计
        
        Args:
            days: 统计天数（默认30天）
            model: 筛选模型（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        stats = store.get_agent_stats(days=days, model=model)
        
        return JSONResponse({
            "period": f"{days} days",
            "data": stats
        })
    
    @app.get("/api/token-stats/filters")
    async def get_token_stats_filters():
        """
        获取可用的筛选选项（模型列表、Agent列表）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        
        return JSONResponse({
            "models": store.get_available_models(),
            "agents": store.get_available_agents()
        })
    
    @app.get("/api/token-stats/recent")
    async def get_token_stats_recent(
        limit: int = 100,
        model: str = None,
        agent_name: str = None
    ):
        """
        获取最近的Token使用记录
        
        Args:
            limit: 返回数量限制（默认100）
            model: 筛选模型（可选）
            agent_name: 筛选Agent（可选）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        records = store.get_recent_records(limit=limit, model=model, agent_name=agent_name)
        
        return JSONResponse({
            "total": len(records),
            "records": records
        })
    
    @app.post("/api/token-stats/cleanup")
    async def cleanup_token_stats(days: int = 90):
        """
        清理旧的Token统计记录
        
        Args:
            days: 保留天数（默认90天）
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        deleted_count = store.cleanup_old_records(days=days)
        
        return JSONResponse({
            "success": True,
            "deleted_count": deleted_count,
            "message": f"已删除 {deleted_count} 条 {days} 天前的记录"
        })
    
    @app.post("/api/token-stats/reset")
    async def reset_token_stats():
        """
        重置所有Token统计数据（清空整个表）
        
        警告：此操作不可恢复！
        """
        from ..utils.token_stats import get_token_stats_store
        
        store = get_token_stats_store()
        deleted_count = store.reset_all()
        
        return JSONResponse({
            "success": True,
            "deleted_count": deleted_count,
            "message": f"已重置所有统计数据，共删除 {deleted_count} 条记录"
        })
    
    # ========== 热点/热梗搜索API ==========
    
    @app.get("/api/trends/status")
    async def get_trends_status():
        """
        获取热点搜索服务状态
        
        返回：
            - available: 服务是否可用
            - tools: 可用的热点搜索工具列表
            - message: 状态消息（始终返回）
        """
        try:
            await mcp_manager.initialize()
            tools = await mcp_manager.list_tools("trends-hub")
            
            # 转换工具列表
            tool_list = []
            for tool in tools:
                tool_dict = tool.model_dump() if hasattr(tool, 'model_dump') else tool.__dict__
                tool_list.append({
                    "name": tool_dict.get("name", ""),
                    "description": tool_dict.get("description", "")
                })
            
            is_available = len(tool_list) > 0
            return JSONResponse({
                "available": is_available,
                "tools": tool_list,
                "server": "trends-hub",
                "message": "热点服务已连接" if is_available else "未找到热点搜索工具，请检查MCP服务配置"
            })
        except Exception as e:
            logger.warning(f"[Trends] 热点服务状态检查失败: {e}")
            return JSONResponse({
                "available": False,
                "tools": [],
                "error": str(e),
                "message": "热点搜索服务未连接，请确保MCP服务已启动"
            })
    
    class TrendSearchRequest(BaseModel):
        """热点搜索请求"""
        platform: str = "weibo"  # weibo, zhihu, douyin, bilibili, baidu, toutiao
        category: str = ""  # 可选的分类
        limit: int = 20  # 返回数量限制
    
    # 平台ID到MCP工具名称的映射（基于 mcp-trends-hub@1.6.0）
    PLATFORM_TOOL_MAP = {
        # 创作灵感类
        "douban": "get-douban-rank",
        "weread": "get-weread-rank",
        "zhihu": "get-zhihu-trending",
        "gcores": "get-gcores-new",
        # 热点资讯类
        "toutiao": "get-toutiao-trending",
        "netease": "get-netease-news-trending",
        "tencent": "get-tencent-news-trending",
        "thepaper": "get-thepaper-trending",
        # 视频娱乐类
        "bilibili": "get-bilibili-rank",
        "douyin": "get-douyin-trending",
        # 科技资讯类
        "36kr": "get-36kr-trending",
        "sspai": "get-sspai-rank",
        "ifanr": "get-ifanr-news",
        "juejin": "get-juejin-article-rank",
        # 购物生活类
        "smzdm": "get-smzdm-rank",
    }
    
    @app.post("/api/trends/search")
    async def search_trends(request: TrendSearchRequest):
        """
        搜索热点/热梗
        
        Args:
            platform: 平台名称 (weibo, zhihu, douyin, bilibili, baidu, toutiao等)
            category: 分类（可选）
            limit: 返回数量限制
        
        返回：
            - success: 是否成功
            - trends: 热点列表
            - platform: 平台名称
        """
        try:
            await mcp_manager.initialize()
            
            # 使用映射表获取正确的工具名称
            tool_name = PLATFORM_TOOL_MAP.get(request.platform)
            if not tool_name:
                # 如果平台不在映射表中，尝试默认格式
                tool_name = f"get-{request.platform}-trending"
                logger.warning(f"[Trends] 未知平台 '{request.platform}'，尝试默认工具名称: {tool_name}")
            
            # 构建参数
            arguments = {}
            if request.category:
                arguments["category"] = request.category
            if request.limit:
                arguments["limit"] = request.limit
            
            # 调用MCP工具
            result = await mcp_manager.call_tool("trends-hub", tool_name, arguments)
            
            # 解析结果
            trends = []
            
            def parse_trend_item(item_data):
                """递归解析热点条目，处理可能的多层JSON编码"""
                # 如果是字符串，尝试解析为JSON
                if isinstance(item_data, str):
                    try:
                        parsed = json.loads(item_data)
                        return parse_trend_item(parsed)  # 递归解析，处理多层编码
                    except json.JSONDecodeError:
                        # 纯文本，作为标题
                        return {"title": item_data.strip()} if item_data.strip() else None
                elif isinstance(item_data, dict):
                    return item_data
                else:
                    return {"title": str(item_data)} if item_data else None
            
            if result:
                # MCP返回的结果通常是content字段
                if hasattr(result, 'content') and result.content:
                    for item in result.content:
                        if hasattr(item, 'text'):
                            # 尝试解析JSON格式的结果
                            try:
                                data = json.loads(item.text)
                                logger.debug(f"[Trends] 解析到的数据类型: {type(data)}, 内容: {str(data)[:200]}")
                                
                                if isinstance(data, list):
                                    # 列表中的每个元素可能也需要解析
                                    for list_item in data:
                                        parsed_item = parse_trend_item(list_item)
                                        if parsed_item:
                                            trends.append(parsed_item)
                                elif isinstance(data, dict):
                                    # 尝试多种常见的数据结构
                                    if 'data' in data and isinstance(data['data'], list):
                                        for list_item in data['data']:
                                            parsed_item = parse_trend_item(list_item)
                                            if parsed_item:
                                                trends.append(parsed_item)
                                    elif 'list' in data and isinstance(data['list'], list):
                                        for list_item in data['list']:
                                            parsed_item = parse_trend_item(list_item)
                                            if parsed_item:
                                                trends.append(parsed_item)
                                    elif 'items' in data and isinstance(data['items'], list):
                                        for list_item in data['items']:
                                            parsed_item = parse_trend_item(list_item)
                                            if parsed_item:
                                                trends.append(parsed_item)
                                    elif 'result' in data and isinstance(data['result'], list):
                                        for list_item in data['result']:
                                            parsed_item = parse_trend_item(list_item)
                                            if parsed_item:
                                                trends.append(parsed_item)
                                    elif 'title' in data or 'name' in data:
                                        # 单个热点条目
                                        trends.append(data)
                                    else:
                                        # 未知结构，记录日志
                                        logger.warning(f"[Trends] 未知的数据结构: {list(data.keys())}")
                                        trends.append(data)
                                else:
                                    # 其他类型，包装成对象
                                    parsed_item = parse_trend_item(data)
                                    if parsed_item:
                                        trends.append(parsed_item)
                            except json.JSONDecodeError:
                                # 如果不是JSON，作为纯文本处理
                                text = item.text.strip()
                                if text:
                                    trends.append({"title": text})
            
            # 辅助函数：从可能嵌套的结构中提取纯文本标题
            def extract_title(value, depth=0):
                """递归提取标题，处理多层嵌套的 JSON 字符串或对象"""
                import re
                
                if depth > 5:  # 防止无限递归
                    return str(value) if value else ""
                
                if value is None:
                    return ""
                
                # 如果是字符串
                if isinstance(value, str):
                    value = value.strip()
                    
                    # 检查是否包含 XML/HTML 标签，如 <title>...</title>
                    # 使用正则提取标签内的文本
                    xml_match = re.match(r'^<(\w+)>(.*)</\1>$', value, re.DOTALL)
                    if xml_match:
                        inner_content = xml_match.group(2).strip()
                        return extract_title(inner_content, depth + 1)
                    
                    # 通用的 HTML/XML 标签清理（去除所有标签，保留文本）
                    if '<' in value and '>' in value:
                        # 去除所有 HTML/XML 标签
                        cleaned = re.sub(r'<[^>]+>', '', value).strip()
                        if cleaned:
                            return cleaned
                    
                    # 检查是否看起来像 JSON 对象
                    if value.startswith('{') and value.endswith('}'):
                        try:
                            parsed = json.loads(value)
                            return extract_title(parsed, depth + 1)
                        except json.JSONDecodeError:
                            return value
                    # 检查是否看起来像 JSON 数组
                    elif value.startswith('[') and value.endswith(']'):
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, list) and len(parsed) > 0:
                                return extract_title(parsed[0], depth + 1)
                        except json.JSONDecodeError:
                            return value
                    return value
                
                # 如果是字典
                if isinstance(value, dict):
                    title = value.get("title") or value.get("name") or value.get("content")
                    if title:
                        return extract_title(title, depth + 1)
                    # 如果没有常见的标题字段，返回整个对象的字符串表示
                    return str(value)
                
                # 如果是列表
                if isinstance(value, list) and len(value) > 0:
                    return extract_title(value[0], depth + 1)
                
                return str(value)
            
            # 标准化热点数据格式
            normalized_trends = []
            for i, trend in enumerate(trends[:request.limit]):
                # 此时 trend 应该已经是 dict 了（经过 parse_trend_item 处理）
                if isinstance(trend, dict):
                    # 使用递归函数提取纯文本标题
                    title = extract_title(trend.get("title") or trend.get("name") or trend.get("content"))
                    
                    # 如果 title 为空，使用整个对象的字符串表示
                    if not title or not title.strip():
                        title = f"热点 {i + 1}"
                    
                    # 同样处理 hot 字段
                    hot = trend.get("hot") or trend.get("hotValue") or trend.get("heat") or trend.get("score") or ""
                    if isinstance(hot, dict):
                        hot = hot.get("hot") or hot.get("value") or str(hot)
                    
                    normalized = {
                        "title": title,
                        "hot": str(hot) if hot else "",
                        "url": str(trend.get("url") or trend.get("link") or ""),
                        "rank": i + 1
                    }
                    normalized_trends.append(normalized)
                else:
                    # 纯字符串内容作为标题
                    title = extract_title(trend) if trend else f"热点 {i + 1}"
                    normalized_trends.append({
                        "title": title,
                        "hot": "",
                        "url": "",
                        "rank": i + 1
                    })
            
            logger.info(f"[Trends] 平台 {request.platform} 获取到 {len(normalized_trends)} 条热点")
            
            return JSONResponse({
                "success": True,
                "trends": normalized_trends,
                "platform": request.platform,
                "count": len(normalized_trends)
            })
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"热点搜索失败: {e}")
            return JSONResponse({
                "success": False,
                "trends": [],
                "platform": request.platform,
                "error": str(e),
                "message": f"获取{request.platform}热点失败，请检查MCP服务是否正常运行"
            })
    
    @app.get("/api/trends/platforms")
    async def get_trend_platforms():
        """
        获取支持的热点平台列表
        
        返回可用的热点搜索平台及其描述
        """
        # 基于 mcp-trends-hub@1.6.0 实际可用的工具列表
        platforms = [
            # ===== 创作灵感类（适合小说/网文） =====
            {
                "id": "douban",
                "name": "豆瓣热榜",
                "icon": "ri-douban-fill",
                "description": "获取豆瓣图书/电影热门，获取故事灵感",
                "tool": "get-douban-rank",
                "category": "创作灵感"
            },
            {
                "id": "weread",
                "name": "微信读书",
                "icon": "ri-book-open-fill",
                "description": "获取微信读书热门小说排行",
                "tool": "get-weread-rank",
                "category": "创作灵感"
            },
            {
                "id": "zhihu",
                "name": "知乎热榜",
                "icon": "ri-zhihu-fill",
                "description": "获取知乎热门话题和故事",
                "tool": "get-zhihu-trending",
                "category": "创作灵感"
            },
            {
                "id": "gcores",
                "name": "机核",
                "icon": "ri-gamepad-fill",
                "description": "获取机核游戏/文化新闻，ACG灵感",
                "tool": "get-gcores-new",
                "category": "创作灵感"
            },
            # ===== 热点资讯类 =====
            {
                "id": "toutiao",
                "name": "头条热榜",
                "icon": "ri-newspaper-fill",
                "description": "获取今日头条热门",
                "tool": "get-toutiao-trending",
                "category": "热点资讯"
            },
            {
                "id": "netease",
                "name": "网易新闻",
                "icon": "ri-netease-cloud-music-fill",
                "description": "获取网易新闻热点",
                "tool": "get-netease-news-trending",
                "category": "热点资讯"
            },
            {
                "id": "tencent",
                "name": "腾讯新闻",
                "icon": "ri-qq-fill",
                "description": "获取腾讯新闻热点",
                "tool": "get-tencent-news-trending",
                "category": "热点资讯"
            },
            {
                "id": "thepaper",
                "name": "澎湃新闻",
                "icon": "ri-newspaper-line",
                "description": "获取澎湃新闻热门",
                "tool": "get-thepaper-trending",
                "category": "热点资讯"
            },
            # ===== 视频/娱乐类 =====
            {
                "id": "bilibili",
                "name": "B站热门",
                "icon": "ri-bilibili-fill",
                "description": "获取B站热门视频和话题",
                "tool": "get-bilibili-rank",
                "category": "视频娱乐"
            },
            {
                "id": "douyin",
                "name": "抖音热点",
                "icon": "ri-tiktok-fill",
                "description": "获取抖音热点视频",
                "tool": "get-douyin-trending",
                "category": "视频娱乐"
            },
            # ===== 科技资讯类 =====
            {
                "id": "36kr",
                "name": "36氪",
                "icon": "ri-article-fill",
                "description": "获取36氪科技新闻",
                "tool": "get-36kr-trending",
                "category": "科技资讯"
            },
            {
                "id": "sspai",
                "name": "少数派",
                "icon": "ri-apps-fill",
                "description": "获取少数派热门文章",
                "tool": "get-sspai-rank",
                "category": "科技资讯"
            },
            {
                "id": "ifanr",
                "name": "爱范儿",
                "icon": "ri-smartphone-fill",
                "description": "获取爱范儿科技资讯",
                "tool": "get-ifanr-news",
                "category": "科技资讯"
            },
            {
                "id": "juejin",
                "name": "掘金",
                "icon": "ri-code-s-slash-fill",
                "description": "获取掘金热门技术文章",
                "tool": "get-juejin-article-rank",
                "category": "科技资讯"
            },
            # ===== 购物/生活类 =====
            {
                "id": "smzdm",
                "name": "什么值得买",
                "icon": "ri-shopping-cart-fill",
                "description": "获取什么值得买热门好价",
                "tool": "get-smzdm-rank",
                "category": "购物生活"
            }
        ]
        
        return JSONResponse({
            "platforms": platforms
        })
    
    @app.post("/api/trends/multi-search")
    async def multi_search_trends(platforms: List[str] = ["weibo", "zhihu"]):
        """
        同时搜索多个平台的热点
        
        Args:
            platforms: 平台ID列表
        
        返回：
            各平台的热点合集
        """
        results = {}
        
        for platform in platforms:
            try:
                await mcp_manager.initialize()
                tool_name = f"get-{platform}-trending"
                result = await mcp_manager.call_tool("trends-hub", tool_name, {})
                
                trends = []
                if result and hasattr(result, 'content') and result.content:
                    for item in result.content:
                        if hasattr(item, 'text'):
                            try:
                                import json
                                data = json.loads(item.text)
                                if isinstance(data, list):
                                    trends = data
                                elif isinstance(data, dict) and 'data' in data:
                                    trends = data['data']
                            except:
                                pass
                
                results[platform] = {
                    "success": True,
                    "trends": trends[:10]
                }
            except Exception as e:
                results[platform] = {
                    "success": False,
                    "error": str(e),
                    "trends": []
                }
        
        return JSONResponse({
            "success": True,
            "results": results
        })
    
    # ========== 热点开关配置API ==========
    
    class TrendsConfigRequest(BaseModel):
        """热点配置请求"""
        enabled: Optional[bool] = None
        auto_refresh: Optional[bool] = None
        refresh_interval: Optional[int] = None  # 秒
        default_platforms: Optional[List[str]] = None
        show_in_infinite_write: Optional[bool] = None
        show_in_multi_agent: Optional[bool] = None
    
    @app.get("/api/trends/config")
    async def get_trends_config():
        """获取热点搜索配置"""
        config_path = Path(__file__).parent.parent / "data" / "trends_config.json"
        
        # 使用统一的默认配置常量
        config_data = TRENDS_CONFIG_DEFAULTS.copy()
        
        if config_path.exists():
            try:
                saved_config = json.loads(config_path.read_text(encoding="utf-8"))
                config_data.update(saved_config)
            except Exception:
                pass
        
        return JSONResponse(config_data)
    
    @app.post("/api/trends/config")
    async def save_trends_config(request: TrendsConfigRequest):
        """保存热点搜索配置"""
        import logging
        logger = logging.getLogger(__name__)
        
        config_path = Path(__file__).parent.parent / "data" / "trends_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 打印完整的请求体，便于调试
        logger.info(f"[TrendsConfig] ===== 收到保存请求 =====")
        logger.info(f"[TrendsConfig] enabled={request.enabled}")
        logger.info(f"[TrendsConfig] auto_refresh={request.auto_refresh}")
        logger.info(f"[TrendsConfig] refresh_interval={request.refresh_interval}")
        logger.info(f"[TrendsConfig] default_platforms={request.default_platforms}")
        print(f"[TrendsConfig] 收到保存请求: platforms={request.default_platforms}")  # 强制打印到控制台
        
        # 先加载现有配置，不使用硬编码默认值作为基础
        config_data = {}
        
        if config_path.exists():
            try:
                config_data = json.loads(config_path.read_text(encoding="utf-8"))
                logger.info(f"[TrendsConfig] 加载现有配置: {config_data}")
            except Exception as e:
                logger.error(f"[TrendsConfig] 加载配置失败: {e}")
                config_data = {}
        
        # 只更新传入的非None字段
        if request.enabled is not None:
            config_data["enabled"] = request.enabled
        if request.auto_refresh is not None:
            config_data["auto_refresh"] = request.auto_refresh
        if request.refresh_interval is not None:
            config_data["refresh_interval"] = request.refresh_interval
        if request.default_platforms is not None:
            config_data["default_platforms"] = request.default_platforms
            logger.info(f"[TrendsConfig] 正在更新 default_platforms 为: {request.default_platforms}")
            print(f"[TrendsConfig] 正在更新 default_platforms 为: {request.default_platforms}")
        else:
            logger.warning(f"[TrendsConfig] default_platforms 为 None，不更新此字段")
            print(f"[TrendsConfig] 警告: default_platforms 为 None!")
        
        # 处理显示开关配置（合并到同一个请求中，避免竞态条件）
        if request.show_in_infinite_write is not None:
            config_data["show_in_infinite_write"] = request.show_in_infinite_write
        if request.show_in_multi_agent is not None:
            config_data["show_in_multi_agent"] = request.show_in_multi_agent
        
        # 确保必要字段存在（仅当不存在时才使用统一的默认值常量）
        for key, default_value in TRENDS_CONFIG_DEFAULTS.items():
            if key not in config_data:
                config_data[key] = default_value
        
        # 保存到文件
        try:
            final_json = json.dumps(config_data, ensure_ascii=False, indent=2)
            config_path.write_text(final_json, encoding="utf-8")
            logger.info(f"[TrendsConfig] 配置已保存到 {config_path}")
            logger.info(f"[TrendsConfig] 保存的内容: {config_data}")
            print(f"[TrendsConfig] 配置已成功保存: {config_data}")
            
            # 验证写入：立即重新读取确认
            verify_content = config_path.read_text(encoding="utf-8")
            verify_data = json.loads(verify_content)
            logger.info(f"[TrendsConfig] 验证读取: {verify_data}")
            print(f"[TrendsConfig] 验证读取: {verify_data.get('default_platforms')}")
        except Exception as e:
            logger.error(f"[TrendsConfig] 保存配置失败: {e}")
            print(f"[TrendsConfig] 保存失败: {e}")
            return JSONResponse({
                "success": False,
                "error": f"保存失败: {str(e)}"
            })
        
        return JSONResponse({
            "success": True,
            "message": "热点配置已保存",
            "saved_config": config_data  # 返回保存的配置以便前端确认
        })
    
    class TrendsVisibilityRequest(BaseModel):
        """热点显示配置请求"""
        show_in_infinite_write: bool = True
        show_in_multi_agent: bool = True
    
    @app.post("/api/trends/visibility")
    async def save_trends_visibility(request: TrendsVisibilityRequest):
        """保存热点显示开关配置"""
        import logging
        logger = logging.getLogger(__name__)
        
        config_path = Path(__file__).parent.parent / "data" / "trends_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载现有配置 - 只有在文件存在时才读取
        config_data = {}
        
        if config_path.exists():
            try:
                config_data = json.loads(config_path.read_text(encoding="utf-8"))
                logger.info(f"[TrendsVisibility] 加载现有配置: {config_data}")
            except Exception as e:
                logger.error(f"[TrendsVisibility] 加载配置失败: {e}")
                config_data = {}
        
        # 只更新显示配置，保留其他所有现有配置
        config_data["show_in_infinite_write"] = request.show_in_infinite_write
        config_data["show_in_multi_agent"] = request.show_in_multi_agent
        
        # 确保必要字段存在（仅当不存在时才使用统一的默认值常量）
        for key, default_value in TRENDS_CONFIG_DEFAULTS.items():
            if key not in config_data:
                config_data[key] = default_value
        
        logger.info(f"[TrendsVisibility] 保存配置: {config_data}")
        config_path.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return JSONResponse({
            "success": True,
            "message": "热点显示配置已保存"
        })
    
    return app


# 模块职责说明：提供FastAPI Web应用，包含小说创作、项目管理、API配置等HTTP接口，集成智能路由确保响应保证。

