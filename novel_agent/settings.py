"""
统一配置管理模块

使用 pydantic-settings 实现类型安全的配置管理，
支持环境变量和 .env 文件。

模块职责说明：提供统一的配置管理接口，整合分散的配置文件。
"""

import os
import logging
from typing import Optional, List
from pathlib import Path
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


class LLMSettings(BaseSettings):
    """LLM配置"""
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, v: str) -> str:
        """确保api_base不以/结尾"""
        return v.rstrip("/")


class ServerSettings(BaseSettings):
    """服务器配置"""
    model_config = SettingsConfigDict(env_prefix="SERVER_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 5656
    debug: bool = False
    cors_origins: List[str] = ["*"]


class CacheSettings(BaseSettings):
    """缓存配置"""
    model_config = SettingsConfigDict(env_prefix="CACHE_", env_file=".env", extra="ignore")

    enabled: bool = True
    default_ttl: int = 3600  # 1小时
    memory_cache_size: int = 100
    cleanup_interval: int = 3600  # 每小时清理一次


class RateLimitSettings(BaseSettings):
    """频率限制配置"""
    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", env_file=".env", extra="ignore")

    enabled: bool = False
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10
    cooldown_seconds: int = 60


class KnowledgeBaseSettings(BaseSettings):
    """知识库配置"""
    model_config = SettingsConfigDict(env_prefix="KB_", env_file=".env", extra="ignore")

    enabled: bool = True
    embedding_provider: str = "api"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-ada-002"
    onnx_model_dir: str = ""
    onnx_model_file: str = "model.onnx"
    onnx_tokenizer_dir: str = ""
    onnx_max_length: int = 512
    onnx_threads: Optional[int] = None
    onnx_pooling: str = "cls"
    chunk_size: int = 500
    chunk_overlap: int = 50


class LoggingSettings(BaseSettings):
    """日志配置"""
    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env", extra="ignore")

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    sanitize_secrets: bool = True


class PathsSettings(BaseSettings):
    """路径配置"""
    model_config = SettingsConfigDict(env_prefix="PATH_", env_file=".env", extra="ignore")

    data_dir: Optional[str] = None
    logs_dir: Optional[str] = None
    exports_dir: Optional[str] = None
    novel_output_dir: Optional[str] = None

    def get_data_dir(self) -> Path:
        """获取数据目录"""
        if self.data_dir:
            return Path(self.data_dir)
        return self._get_default_data_dir()

    def get_logs_dir(self) -> Path:
        """获取日志目录"""
        if self.logs_dir:
            return Path(self.logs_dir)
        return self.get_data_dir() / "logs"

    def get_exports_dir(self) -> Path:
        """获取导出目录"""
        if self.exports_dir:
            return Path(self.exports_dir)
        return self._get_app_root() / "exports"

    def get_novel_output_dir(self) -> Path:
        """获取小说输出目录"""
        if self.novel_output_dir:
            return Path(self.novel_output_dir)
        return self._get_app_root() / "novel_output"

    @staticmethod
    def _get_app_root() -> Path:
        """获取应用根目录"""
        import sys
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent.parent
        return Path.cwd()

    @staticmethod
    def _get_default_data_dir() -> Path:
        """获取默认数据目录"""
        data_dir = PathsSettings._get_app_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


class AppSettings(BaseSettings):
    """
    应用统一配置

    整合所有配置模块，提供统一的配置访问接口。
    支持环境变量和 .env 文件。

    Usage:
        from novel_agent.settings import settings
        print(settings.llm.model)
        print(settings.server.port)
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 子配置模块
    llm: LLMSettings = LLMSettings()
    server: ServerSettings = ServerSettings()
    cache: CacheSettings = CacheSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    knowledge_base: KnowledgeBaseSettings = KnowledgeBaseSettings()
    logging: LoggingSettings = LoggingSettings()
    paths: PathsSettings = PathsSettings()

    # 应用信息
    app_name: str = "山海·云烟"
    app_version: str = "1.0"
    debug: bool = False

    def setup_logging(self) -> None:
        """配置日志系统"""
        import logging as logging_module

        level = getattr(logging_module, self.logging.level.upper(), logging_module.INFO)

        # 如果启用敏感信息净化
        if self.logging.sanitize_secrets:
            from .utils.log_sanitizer import setup_sanitizing_logging
            setup_sanitizing_logging(level, self.logging.format)
        else:
            logging_module.basicConfig(
                level=level,
                format=self.logging.format
            )

        logger.info(f"Logging configured: level={self.logging.level}")

    def ensure_directories(self) -> None:
        """确保所有必要目录存在"""
        dirs = [
            self.paths.get_data_dir(),
            self.paths.get_logs_dir(),
            self.paths.get_exports_dir(),
            self.paths.get_novel_output_dir(),
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        logger.info(f"Directories ensured: {[str(d) for d in dirs]}")


# 全局配置实例（使用lru_cache实现单例）
@lru_cache()
def get_settings() -> AppSettings:
    """获取全局配置实例"""
    return AppSettings()


# 便捷访问
settings = get_settings()


# 兼容旧配置接口
def get_llm_config() -> LLMSettings:
    """获取LLM配置（兼容接口）"""
    return settings.llm


def get_server_config() -> ServerSettings:
    """获取服务器配置（兼容接口）"""
    return settings.server


def get_cache_config() -> CacheSettings:
    """获取缓存配置（兼容接口）"""
    return settings.cache
