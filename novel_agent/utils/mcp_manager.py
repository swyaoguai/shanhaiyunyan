import json
import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dotenv import load_dotenv
from contextlib import AsyncExitStack

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

# MCP是可选依赖，如果未安装则禁用MCP功能
MCP_AVAILABLE = False
MCP_SDK_VERSION = None
try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    import mcp
    MCP_SDK_VERSION = getattr(mcp, '__version__', 'unknown')
    MCP_AVAILABLE = True
    logger.info(f"MCP SDK加载成功: 版本 {MCP_SDK_VERSION}")
except ImportError as e:
    logger.warning(f"MCP package not installed. MCP features will be disabled. Error: {e}")
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


class MCPManager:
    """MCP管理器，用于管理MCP服务器连接和工具调用"""
    
    def __init__(self, config_path: str = "mcp_config.json"):
        self.config_path = self._find_config_path(config_path)
        self.servers: Dict[str, Any] = {}
        self.config = self._load_config()
        self._sessions = {}
        self._exit_stacks = {}
    
    def _find_config_path(self, config_filename: str) -> Path:
        """查找配置文件路径，支持PyInstaller打包"""
        import sys
        
        # 可能的配置文件位置
        possible_paths = []
        
        if getattr(sys, 'frozen', False):
            # PyInstaller打包后运行
            exe_dir = Path(sys.executable).parent
            possible_paths = [
                exe_dir.parent / config_filename,  # 便携版根目录
                exe_dir / config_filename,  # app目录
                Path.cwd() / config_filename,  # 当前工作目录
            ]
        else:
            # 开发模式
            possible_paths = [
                Path.cwd() / config_filename,  # 当前工作目录
                Path(__file__).parent.parent.parent / config_filename,  # 项目根目录
            ]
        
        for p in possible_paths:
            if p.exists():
                logger.info(f"Found MCP config at: {p}")
                return p
        
        # 默认返回第一个路径
        return possible_paths[0] if possible_paths else Path(config_filename)

    def _load_config(self) -> Dict:
        """加载MCP配置"""
        if not self.config_path.exists():
            logger.warning(f"MCP config file not found: {self.config_path}")
            return {"mcpServers": {}}
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return {"mcpServers": {}}

    async def initialize(self):
        """初始化连接所有配置的MCP服务器"""
        if not MCP_AVAILABLE:
            logger.info("MCP not available, skipping server initialization")
            return
        
        mcp_servers = self.config.get("mcpServers", {})
        
        for server_name, server_config in mcp_servers.items():
            try:
                await self.connect_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")

    async def connect_server(self, server_name: str, config: Dict):
        """连接单个MCP服务器"""
        if not MCP_AVAILABLE:
            logger.warning(f"MCP not available, cannot connect to server: {server_name}")
            return
        
        if server_name in self._sessions:
            return

        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env", {})
        
        # 合并当前环境变量
        current_env = os.environ.copy()
        current_env.update(env)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=current_env
        )

        try:
            # 创建上下文管理器并进入
            stack = AsyncExitStack()
            self._exit_stacks[server_name] = stack
            
            # MCP SDK 1.x 的新API：stdio_client返回一个异步上下文管理器
            # 进入上下文后获取 (read_stream, write_stream)
            streams = await stack.enter_async_context(stdio_client(server_params))
            
            # streams 是一个元组 (read_stream, write_stream)
            if isinstance(streams, tuple) and len(streams) == 2:
                read_stream, write_stream = streams
            else:
                # 如果API再次改变，尝试其他方式
                logger.error(f"Unexpected stdio_client return type: {type(streams)}")
                raise TypeError(f"stdio_client returned unexpected type: {type(streams)}")
            
            # 创建ClientSession
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            
            self._sessions[server_name] = session
            logger.info(f"Connected to MCP server: {server_name}")
            
        except Exception as e:
            logger.error(f"Error connecting to {server_name}: {e}")
            if server_name in self._exit_stacks:
                try:
                    await self._exit_stacks[server_name].aclose()
                except Exception:
                    pass
                del self._exit_stacks[server_name]
            raise

    async def list_tools(self, server_name: str) -> List[Dict]:
        """列出指定服务器的工具"""
        if server_name not in self._sessions:
            logger.warning(f"Server {server_name} not connected")
            return []
        
        try:
            result = await self._sessions[server_name].list_tools()
            return result.tools
        except Exception as e:
            logger.error(f"Error listing tools for {server_name}: {e}")
            return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """调用工具"""
        if server_name not in self._sessions:
            raise ValueError(f"Server {server_name} not connected")
            
        try:
            result = await self._sessions[server_name].call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling tool {tool_name} on {server_name}: {e}")
            raise

    async def get_all_tools(self) -> List[Dict]:
        """获取所有可用工具"""
        all_tools = []
        for server_name in self._sessions:
            tools = await self.list_tools(server_name)
            for tool in tools:
                # 添加服务器名称前缀以区分同名工具
                tool_dict = tool.model_dump() if hasattr(tool, 'model_dump') else tool.__dict__
                tool_dict['server_name'] = server_name
                all_tools.append(tool_dict)
        return all_tools

    async def close(self):
        """关闭所有连接"""
        for name, stack in self._exit_stacks.items():
            try:
                await stack.aclose()
                logger.info(f"Closed connection to {name}")
            except Exception as e:
                logger.error(f"Error closing connection to {name}: {e}")
        self._sessions.clear()
        self._exit_stacks.clear()

# 全局实例
mcp_manager = MCPManager()