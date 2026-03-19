"""
日志净化工具

自动移除日志中的敏感信息，防止API密钥等泄露到日志文件。

模块职责说明：提供日志净化功能，保护敏感信息安全。
"""

import re
import logging
from typing import Any, Dict, List, Set, Optional, Union
from functools import lru_cache


# 敏感字段名（不区分大小写）
SENSITIVE_FIELD_NAMES: Set[str] = {
    # API密钥相关
    "api_key", "apikey", "api-key",
    "secret", "secret_key", "secretkey", "secret-key",
    "token", "access_token", "accesstoken", "access-token",
    "refresh_token", "refreshtoken", "refresh-token",
    "auth_token", "authtoken", "auth-token",
    "bearer", "authorization",

    # 密码相关
    "password", "passwd", "pwd", "pass",
    "credential", "credentials",

    # 私钥相关
    "private_key", "privatekey", "private-key",
    "private", "priv_key",

    # 其他敏感信息
    "session_id", "sessionid", "session-id",
    "cookie", "csrf_token", "csrftoken",
}

# 敏感模式（正则表达式）
SENSITIVE_PATTERNS = [
    # OpenAI API Key
    (r"sk-[a-zA-Z0-9]{20,}", "***API_KEY***"),
    (r"sk-proj-[a-zA-Z0-9]{20,}", "***API_KEY***"),

    # Bearer Token
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer ***TOKEN***"),

    # JWT Token
    (r"eyJ[a-zA-Z0-9\-._~+/]+=*\.eyJ[a-zA-Z0-9\-._~+/]+=*\.[a-zA-Z0-9\-._~+/]+=*", "***JWT***"),

    # 通用密钥格式
    (r"[a-zA-Z0-9]{32,}", "***KEY***"),

    # 邮箱地址（部分隐藏）
    (r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", r"***@\2"),
]

# 替换字符串
MASK = "***"


class LogSanitizer:
    """
    日志净化器

    自动检测并替换日志中的敏感信息。
    """

    def __init__(
        self,
        sensitive_fields: Optional[Set[str]] = None,
        custom_patterns: Optional[List[tuple]] = None,
        mask: str = MASK
    ):
        """
        初始化日志净化器

        Args:
            sensitive_fields: 额外的敏感字段名
            custom_patterns: 额外的敏感模式 [(pattern, replacement), ...]
            mask: 替换字符串
        """
        self.sensitive_fields = SENSITIVE_FIELD_NAMES.copy()
        if sensitive_fields:
            self.sensitive_fields.update(f.lower() for f in sensitive_fields)

        self.patterns = SENSITIVE_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)

        self.mask = mask

        # 编译正则表达式
        self._compiled_patterns = [
            (re.compile(p, re.IGNORECASE), r)
            for p, r in self.patterns
        ]

    def sanitize_string(self, text: str) -> str:
        """
        净化字符串

        Args:
            text: 原始字符串

        Returns:
            净化后的字符串
        """
        if not isinstance(text, str):
            return text

        result = text

        # 应用模式替换
        for pattern, replacement in self._compiled_patterns:
            result = pattern.sub(replacement, result)

        return result

    def sanitize_dict(self, data: Dict, depth: int = 0, max_depth: int = 10) -> Dict:
        """
        净化字典

        Args:
            data: 原始字典
            depth: 当前递归深度
            max_depth: 最大递归深度

        Returns:
            净化后的字典
        """
        if depth > max_depth:
            return {"_truncated": "max depth exceeded"}

        result = {}
        for key, value in data.items():
            key_lower = key.lower() if isinstance(key, str) else ""

            # 检查是否是敏感字段
            if key_lower in self.sensitive_fields:
                result[key] = self.mask
            elif isinstance(value, str):
                # 检查字符串值中的敏感模式
                result[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value, depth + 1, max_depth)
            else:
                result[key] = value

        return result

    def sanitize_list(self, data: List, depth: int = 0, max_depth: int = 10) -> List:
        """
        净化列表

        Args:
            data: 原始列表
            depth: 当前递归深度
            max_depth: 最大递归深度

        Returns:
            净化后的列表
        """
        if depth > max_depth:
            return ["_truncated: max depth exceeded"]

        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.sanitize_string(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item, depth + 1, max_depth))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item, depth + 1, max_depth))
            else:
                result.append(item)

        return result

    def sanitize(self, data: Any) -> Any:
        """
        通用净化方法

        Args:
            data: 任意数据

        Returns:
            净化后的数据
        """
        if isinstance(data, str):
            return self.sanitize_string(data)
        elif isinstance(data, dict):
            return self.sanitize_dict(data)
        elif isinstance(data, list):
            return self.sanitize_list(data)
        elif isinstance(data, tuple):
            return tuple(self.sanitize_list(list(data)))
        else:
            return data


# 全局净化器实例
_global_sanitizer: Optional[LogSanitizer] = None


def get_sanitizer() -> LogSanitizer:
    """获取全局日志净化器实例"""
    global _global_sanitizer
    if _global_sanitizer is None:
        _global_sanitizer = LogSanitizer()
    return _global_sanitizer


def sanitize_for_log(data: Any) -> Any:
    """
    便捷函数：净化数据用于日志

    Args:
        data: 任意数据

    Returns:
        净化后的数据

    Usage:
        logger.info(f"Request data: {sanitize_for_log(request_data)}")
    """
    return get_sanitizer().sanitize(data)


class SanitizingFormatter(logging.Formatter):
    """
    自动净化日志格式化器

    在格式化日志时自动净化消息中的敏感信息。
    """

    def __init__(self, fmt=None, datefmt=None, style='%', sanitizer=None):
        super().__init__(fmt, datefmt, style)
        self.sanitizer = sanitizer or get_sanitizer()

    def format(self, record):
        # 先使用父类格式化
        formatted = super().format(record)

        # 净化消息
        return self.sanitizer.sanitize_string(formatted)


def setup_sanitizing_logging(
    level: int = logging.INFO,
    fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
):
    """
    设置带净化的日志配置

    Args:
        level: 日志级别
        fmt: 日志格式

    Usage:
        from novel_agent.utils.log_sanitizer import setup_sanitizing_logging
        setup_sanitizing_logging()
    """
    # 创建净化格式化器
    formatter = SanitizingFormatter(fmt)

    # 配置根日志器
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]


# 敏感字段检测器（用于验证）
def contains_sensitive_data(text: str) -> bool:
    """
    检测字符串中是否包含敏感数据

    Args:
        text: 待检测字符串

    Returns:
        是否包含敏感数据
    """
    sanitizer = get_sanitizer()
    sanitized = sanitizer.sanitize_string(text)
    return sanitized != text
