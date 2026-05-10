"""
配置管理模块
支持OpenAI兼容API (v1接口)
"""

import os
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

from .constants import (
    API_ENDPOINTS,
    LLM_DEFAULTS,
    WRITING_CONFIG,
    SERVER_DEFAULTS
)

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()


class LLMConfig(BaseModel):
    """LLM配置"""
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    api_base: str = os.getenv("OPENAI_API_BASE", API_ENDPOINTS.OPENAI_BASE_URL)
    model: str = os.getenv("OPENAI_MODEL", LLM_DEFAULTS.DEFAULT_MODEL)
    max_tokens: int = int(os.getenv("MAX_TOKENS", str(LLM_DEFAULTS.MAX_TOKENS)))
    temperature: float = float(os.getenv("TEMPERATURE", str(LLM_DEFAULTS.TEMPERATURE)))


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = os.getenv("HOST", SERVER_DEFAULTS.HOST)
    port: int = int(os.getenv("PORT", str(SERVER_DEFAULTS.PORT)))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


class PathConfig(BaseModel):
    """路径配置"""
    base_dir: Path = Path(__file__).parent
    prompts_dir: Path = base_dir / "prompts"
    output_dir: Path = base_dir / "output"
    templates_dir: Path = base_dir / "web" / "templates"
    static_dir: Path = base_dir / "web" / "static"
    
    def ensure_dirs(self):
        """确保目录存在"""
        self.output_dir.mkdir(parents=True, exist_ok=True)


class NovelConfig(BaseModel):
    """小说生成配置"""
    # 支持的小说类型
    novel_types: list = [
        "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", 
        "军事", "历史", "游戏", "体育", "科幻", "悬疑",
        "轻小说", "言情", "同人"
    ]
    
    # 章节长度配置
    chapter_min_words: int = WRITING_CONFIG.CHAPTER_MIN_WORDS
    chapter_max_words: int = WRITING_CONFIG.CHAPTER_MAX_WORDS
    
    # 大纲层级
    outline_levels: list = ["卷", "章节"]


class Config:
    """全局配置"""
    llm = LLMConfig()
    server = ServerConfig()
    paths = PathConfig()
    novel = NovelConfig()

    @classmethod
    def init(cls):
        """初始化配置"""
        cls.paths.ensure_dirs()
        return cls

    @classmethod
    def reload(cls):
        """
        热重载配置

        从.env文件重新加载环境变量并更新LLM配置单例。
        使用override=True确保环境变量被.env文件值覆盖。

        Returns:
            bool: 成功返回True，失败返回False

        Example:
            >>> Config.reload()
            True
        """
        try:
            from .constants import get_app_root

            # 优先使用运行根目录下的 .env；便携版中为 exe 同级目录。
            env_file = get_app_root() / ".env"

            # 兼容：若项目根目录不存在，则回退到当前工作目录
            if not env_file.exists():
                fallback_env = Path.cwd() / ".env"
                if fallback_env.exists():
                    env_file = fallback_env
                else:
                    logger.error(f".env file not found at: {env_file} or {fallback_env}")
                    return False

            # 重新加载环境变量（使用override=True覆盖现有值）
            # 使用encoding='utf-8'避免Windows GBK编码问题
            load_dotenv(dotenv_path=env_file, override=True, encoding='utf-8')

            # 重新创建配置实例以捕获更新的环境变量。
            # LLMConfig/ServerConfig 的字段默认值在模块导入时已求值，
            # 因此热重载时必须显式传入 os.environ 中的新值。
            cls.llm = LLMConfig(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                api_base=os.getenv("OPENAI_API_BASE", API_ENDPOINTS.OPENAI_BASE_URL),
                model=os.getenv("OPENAI_MODEL", LLM_DEFAULTS.DEFAULT_MODEL),
                max_tokens=int(os.getenv("MAX_TOKENS", str(LLM_DEFAULTS.MAX_TOKENS))),
                temperature=float(os.getenv("TEMPERATURE", str(LLM_DEFAULTS.TEMPERATURE))),
            )
            cls.server = ServerConfig(
                host=os.getenv("HOST", SERVER_DEFAULTS.HOST),
                port=int(os.getenv("PORT", str(SERVER_DEFAULTS.PORT))),
                debug=os.getenv("DEBUG", "false").lower() == "true",
            )

            logger.info("Configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False


# 全局配置实例
config = Config()
