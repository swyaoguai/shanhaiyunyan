"""
统一日志配置模块
提供全局日志配置和格式化
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..constants import LOGGING_CONFIG


# 日志格式
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DETAILED_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(filename)s:%(lineno)d | %(message)s"
SIMPLE_FORMAT = "%(levelname)s: %(message)s"

# 日志颜色（用于控制台输出）
COLORS = {
    'DEBUG': '\033[36m',     # 青色
    'INFO': '\033[32m',      # 绿色
    'WARNING': '\033[33m',   # 黄色
    'ERROR': '\033[31m',     # 红色
    'CRITICAL': '\033[35m',  # 紫色
    'RESET': '\033[0m'       # 重置
}


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（用于控制台）"""
    
    def __init__(self, fmt: str = DEFAULT_FORMAT, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            color = COLORS.get(record.levelname, COLORS['RESET'])
            reset = COLORS['RESET']
            record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


class LogConfig:
    """日志配置类"""
    
    def __init__(
        self,
        level: str = "INFO",
        log_dir: Optional[Path] = None,
        log_to_file: bool = True,
        log_to_console: bool = True,
        max_file_size: int = LOGGING_CONFIG.MAX_FILE_SIZE,
        backup_count: int = LOGGING_CONFIG.BACKUP_COUNT,
        use_colors: bool = True,
        detailed_format: bool = False
    ):
        self.level = self._parse_level(level)
        self.log_dir = log_dir or Path(__file__).parent.parent / "logs"
        self.log_to_file = log_to_file
        self.log_to_console = log_to_console
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.use_colors = use_colors
        self.format = DETAILED_FORMAT if detailed_format else DEFAULT_FORMAT
    
    @staticmethod
    def _parse_level(level: str) -> int:
        """解析日志级别"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        return level_map.get(level.upper(), logging.INFO)


def setup_logging(config: Optional[LogConfig] = None) -> logging.Logger:
    """
    设置全局日志配置
    
    Args:
        config: 日志配置对象，如果为None则使用环境变量或默认值
        
    Returns:
        根日志记录器
    """
    if config is None:
        config = LogConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"),
            log_to_file=os.environ.get("LOG_TO_FILE", "true").lower() == "true",
            log_to_console=os.environ.get("LOG_TO_CONSOLE", "true").lower() == "true",
            use_colors=os.environ.get("LOG_COLORS", "true").lower() == "true",
            detailed_format=os.environ.get("LOG_DETAILED", "false").lower() == "true"
        )
    
    # 获取根日志记录器
    root_logger = logging.getLogger("novel_agent")
    root_logger.setLevel(config.level)
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    if config.log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(config.level)
        console_formatter = ColoredFormatter(config.format, use_colors=config.use_colors)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # 文件处理器
    if config.log_to_file:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 常规日志文件
        log_file = config.log_dir / f"novel_agent_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(config.level)
        file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        root_logger.addHandler(file_handler)
        
        # 错误日志单独文件
        error_file = config.log_dir / "errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        root_logger.addHandler(error_handler)
    
    # 设置第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    root_logger.info(f"Logging configured: level={logging.getLevelName(config.level)}, "
                     f"file={config.log_to_file}, console={config.log_to_console}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称（通常是模块名）
        
    Returns:
        日志记录器
    """
    if not name.startswith("novel_agent"):
        name = f"novel_agent.{name}"
    return logging.getLogger(name)


# 便捷函数
def debug(msg: str, *args, **kwargs):
    """输出DEBUG级别日志"""
    get_logger("main").debug(msg, *args, **kwargs)

def info(msg: str, *args, **kwargs):
    """输出INFO级别日志"""
    get_logger("main").info(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs):
    """输出WARNING级别日志"""
    get_logger("main").warning(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs):
    """输出ERROR级别日志"""
    get_logger("main").error(msg, *args, **kwargs)

def critical(msg: str, *args, **kwargs):
    """输出CRITICAL级别日志"""
    get_logger("main").critical(msg, *args, **kwargs)


# 自动初始化（首次导入时）
_initialized = False

def ensure_initialized():
    """确保日志系统已初始化"""
    global _initialized
    if not _initialized:
        setup_logging()
        _initialized = True


# 模块加载时自动初始化
ensure_initialized()


# 模块职责说明：统一日志配置，提供带颜色的控制台输出和文件轮转功能。