"""
常量定义模块

将项目中所有硬编码的数值、URL、超时时间等提取到此处统一管理。
所有业务代码应从此处引入常量，禁止在代码中直接使用硬编码值。

模块职责说明：统一管理项目中的所有常量配置，包括API端点、超时时间、默认参数等。
"""

import os
from dataclasses import dataclass
from typing import Dict, Tuple


# ========================================
# API 相关常量
# ========================================

@dataclass(frozen=True)
class APIEndpoints:
    """API端点配置"""
    # OpenAI默认端点
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_CHAT_COMPLETIONS: str = "/chat/completions"
    OPENAI_MODELS: str = "/models"
    OPENAI_EMBEDDINGS: str = "/embeddings"
    
    @classmethod
    def get_chat_url(cls, base_url: str = None) -> str:
        """获取完整的聊天API URL"""
        base = base_url or cls.OPENAI_BASE_URL
        base = base.rstrip('/')
        return f"{base}{cls.OPENAI_CHAT_COMPLETIONS}"
    
    @classmethod
    def get_models_url(cls, base_url: str = None) -> str:
        """获取完整的模型列表API URL"""
        base = base_url or cls.OPENAI_BASE_URL
        base = base.rstrip('/')
        return f"{base}{cls.OPENAI_MODELS}"
    
    @classmethod
    def get_embeddings_url(cls, base_url: str = None) -> str:
        """获取完整的嵌入API URL"""
        base = base_url or cls.OPENAI_BASE_URL
        base = base.rstrip('/')
        return f"{base}{cls.OPENAI_EMBEDDINGS}"


API_ENDPOINTS = APIEndpoints()


# ========================================
# 超时配置（秒）
# ========================================

@dataclass(frozen=True)
class TimeoutConfig:
    """超时时间配置"""
    # HTTP请求超时
    HTTP_SHORT: float = 10.0      # 短请求（健康检查等）
    HTTP_MEDIUM: float = 15.0     # 中等请求（获取模型列表等）
    HTTP_LONG: float = 30.0       # 长请求（API测试、聊天等）
    HTTP_VERY_LONG: float = 60.0  # 超长请求（大文本生成等）
    
    # Agent执行超时
    AGENT_DEFAULT: float = 300.0  # 5分钟
    AGENT_SHORT: float = 60.0     # 1分钟
    AGENT_LONG: float = 600.0     # 10分钟
    
    # 消息队列超时
    MESSAGE_QUEUE: float = 1.0    # 消息队列轮询
    
    # 缓存TTL（秒）
    CACHE_DEFAULT_TTL: int = 3600      # 1小时
    CACHE_SHORT_TTL: int = 300         # 5分钟
    CACHE_LONG_TTL: int = 86400        # 24小时
    
    # CORS最大缓存时间
    CORS_MAX_AGE: int = 3600


TIMEOUTS = TimeoutConfig()


# ========================================
# LLM 模型默认参数
# ========================================

@dataclass(frozen=True)
class LLMDefaults:
    """LLM模型默认参数"""
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 4096
    TOP_P: float = 1.0
    FREQUENCY_PENALTY: float = 0.0
    PRESENCE_PENALTY: float = 0.0
    
    # 默认模型
    DEFAULT_MODEL: str = "gpt-4"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-ada-002"


LLM_DEFAULTS = LLMDefaults()


# ========================================
# 嵌入向量配置
# ========================================

@dataclass(frozen=True)
class EmbeddingConfig:
    """嵌入向量配置"""
    # OpenAI嵌入模型维度
    DIMENSION_ADA_002: int = 1536
    DIMENSION_3_SMALL: int = 1536
    DIMENSION_3_LARGE: int = 3072
    
    # 本地模型默认维度
    DIMENSION_LOCAL_DEFAULT: int = 384
    
    # 随机嵌入默认维度
    DIMENSION_RANDOM: int = 256
    
    # 默认维度
    DEFAULT_DIMENSION: int = 1536
    
    @classmethod
    def get_dimension_for_model(cls, model: str) -> int:
        """根据模型名获取嵌入维度"""
        if "3-large" in model:
            return cls.DIMENSION_3_LARGE
        elif "3-small" in model:
            return cls.DIMENSION_3_SMALL
        elif "ada-002" in model or "ada" in model:
            return cls.DIMENSION_ADA_002
        return cls.DEFAULT_DIMENSION


EMBEDDING_CONFIG = EmbeddingConfig()


# ========================================
# 写作配置
# ========================================

@dataclass(frozen=True)
class WritingConfig:
    """小说写作相关配置"""
    # 章节字数限制
    CHAPTER_MIN_WORDS: int = 2000
    CHAPTER_MAX_WORDS: int = 4000
    CHAPTER_DEFAULT_WORDS: int = 3000
    
    # 续写默认字数
    CONTINUE_DEFAULT_WORDS: int = 500
    
    # 摘要最大长度
    SUMMARY_MAX_LENGTH: int = 300
    CHAPTER_SUMMARY_MAX_LENGTH: int = 200
    
    # 上下文压缩
    CONTEXT_COMPRESS_MAX_LENGTH: int = 2000
    MAX_CONTEXT_TOKENS: int = 8000
    
    # 一致性检查截断长度
    CONSISTENCY_CHECK_TRUNCATE: int = 500
    
    # 对话历史截断长度
    HISTORY_TRUNCATE_LENGTH: int = 200
    
    # 默认卷数和每卷章节数
    DEFAULT_VOLUME_COUNT: int = 3
    DEFAULT_CHAPTERS_PER_VOLUME: int = 30


WRITING_CONFIG = WritingConfig()


# ========================================
# 速率限制配置
# ========================================

@dataclass(frozen=True)
class RateLimitDefaults:
    """速率限制默认值"""
    REQUESTS_PER_MINUTE: int = 200
    REQUESTS_PER_HOUR: int = 1000
    BURST_LIMIT: int = 10
    COOLDOWN_SECONDS: int = 60       # 冷却时间（秒）
    DEFAULT_RETRY_AFTER: int = 60    # 默认重试等待时间（秒）


RATE_LIMIT_DEFAULTS = RateLimitDefaults()


# ========================================
# 缓存配置
# ========================================

@dataclass(frozen=True)
class CacheConfig:
    """缓存配置"""
    DEFAULT_TTL: int = 3600          # 默认TTL（秒）
    MEMORY_CACHE_SIZE: int = 100     # 内存缓存大小
    LLM_CACHE_TTL: int = 3600        # LLM调用缓存TTL


CACHE_CONFIG = CacheConfig()


# ========================================
# 消息总线配置
# ========================================

@dataclass(frozen=True)
class MessageBusConfig:
    """消息总线配置"""
    DEFAULT_TTL: int = 300           # 消息默认生存时间（秒）
    HISTORY_LIMIT: int = 100         # 历史消息保留数量
    HIGH_PRIORITY: int = 10          # 高优先级消息


MESSAGE_BUS_CONFIG = MessageBusConfig()


# ========================================
# WebSocket配置
# ========================================

@dataclass(frozen=True)
class WebSocketConfig:
    """WebSocket配置"""
    HEARTBEAT_INTERVAL: int = 30     # 心跳间隔（秒）
    RECONNECT_DELAY: int = 5         # 重连延迟（秒）


WEBSOCKET_CONFIG = WebSocketConfig()


# ========================================
# 指标收集配置
# ========================================

@dataclass(frozen=True)
class MetricsConfig:
    """指标配置"""
    MAX_HISTORY: int = 1000          # 最大历史记录数


METRICS_CONFIG = MetricsConfig()


# ========================================
# Agent温度配置
# ========================================

@dataclass(frozen=True)
class AgentTemperatureConfig:
    """各Agent的LLM温度配置"""
    # 创意类Agent（章节写作、沟通等）
    CREATIVE_HIGH: float = 0.8       # 高创意温度
    CREATIVE_MEDIUM: float = 0.7     # 中等创意温度
    
    # 编辑润色类Agent
    POLISHER_MAIN: float = 0.6       # 主润色温度
    POLISHER_STYLE: float = 0.7      # 风格转换温度
    
    # 评估分析类Agent（需要稳定输出）
    EVALUATOR_STABLE: float = 0.3    # 稳定评估温度
    
    # 总结摘要类
    SUMMARY_STABLE: float = 0.3      # 摘要温度


AGENT_TEMPERATURE = AgentTemperatureConfig()


# ========================================
# Agent Token配置
# ========================================

@dataclass(frozen=True)
class AgentTokenConfig:
    """各Agent的Token配置"""
    # 章节写作（需要大输出）
    CHAPTER_WRITER_MAX_TOKENS: int = 6000
    
    # 通用Agent默认值
    DEFAULT_MAX_TOKENS: int = 4096


AGENT_TOKEN_CONFIG = AgentTokenConfig()


# ========================================
# 重试配置
# ========================================

@dataclass(frozen=True)
class RetryDefaults:
    """重试策略默认配置"""
    MAX_RETRIES: int = 3
    INITIAL_DELAY: float = 2.0
    BACKOFF_MULTIPLIER: float = 2.0
    MAX_DELAY: float = 60.0
    JITTER_RANGE: Tuple[float, float] = (0.5, 1.5)
    
    # LLM专用重试配置
    LLM_MAX_RETRIES: int = 5
    LLM_INITIAL_DELAY: float = 0.5
    LLM_BACKOFF: float = 1.5
    LLM_MAX_DELAY: float = 30.0
    
    # 网络请求重试配置
    NETWORK_MAX_RETRIES: int = 3
    NETWORK_BACKOFF: float = 2.5
    NETWORK_MAX_DELAY: float = 120.0
    
    # 断路器配置
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 30.0
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2


RETRY_DEFAULTS = RetryDefaults()


# ========================================
# 日志配置
# ========================================

@dataclass(frozen=True)
class LoggingConfig:
    """日志配置"""
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT: int = 5


LOGGING_CONFIG = LoggingConfig()


# ========================================
# 成本估算配置
# ========================================

@dataclass(frozen=True)
class CostConfig:
    """API成本估算配置（美元/1K tokens）"""
    GPT4_INPUT_COST: float = 0.03
    GPT4_OUTPUT_COST: float = 0.06


COST_CONFIG = CostConfig()


# ========================================
# 上下文优先级权重
# ========================================

@dataclass(frozen=True)
class ContextPriorityWeights:
    """上下文项目优先级权重"""
    WORLD: float = 1.0
    CHARACTER: float = 0.9
    PLOT: float = 0.8
    CHAPTER: float = 0.7
    SYNC: float = 0.5
    GENERAL: float = 0.3


CONTEXT_PRIORITY = ContextPriorityWeights()


# ========================================
# 分页配置
# ========================================

@dataclass(frozen=True)
class PaginationConfig:
    """分页默认值"""
    DEFAULT_LIMIT: int = 100
    DEFAULT_OFFSET: int = 0
    MAX_LIMIT: int = 1000


PAGINATION_CONFIG = PaginationConfig()


# ========================================
# HTTP状态码常量
# ========================================

@dataclass(frozen=True)
class HTTPStatus:
    """HTTP状态码"""
    OK: int = 200
    CREATED: int = 201
    NO_CONTENT: int = 204
    BAD_REQUEST: int = 400
    UNAUTHORIZED: int = 401
    FORBIDDEN: int = 403
    NOT_FOUND: int = 404
    METHOD_NOT_ALLOWED: int = 405
    TOO_MANY_REQUESTS: int = 429
    INTERNAL_SERVER_ERROR: int = 500
    SERVICE_UNAVAILABLE: int = 503


HTTP_STATUS = HTTPStatus()


# ========================================
# 验证规则
# ========================================

@dataclass(frozen=True)
class ValidationRules:
    """验证规则常量"""
    # 字符串长度
    MIN_STRING_LENGTH: int = 0
    MAX_STRING_LENGTH: int = 10000
    
    # API Key长度
    MIN_API_KEY_LENGTH: int = 20
    MAX_API_KEY_LENGTH: int = 200


VALIDATION_RULES = ValidationRules()


# ========================================
# 服务器默认配置
# ========================================

@dataclass(frozen=True)
class ServerDefaults:
    """服务器默认配置"""
    HOST: str = "0.0.0.0"
    PORT: int = 5656
    DEBUG: bool = False


SERVER_DEFAULTS = ServerDefaults()


# ========================================
# 测试常量（仅用于测试）
# ========================================

@dataclass(frozen=True)
class TestConstants:
    """测试用常量"""
    TEST_API_KEY: str = "test-key"
    TEST_API_BASE: str = "https://api.test.com/v1"
    TEST_PROMPT_TOKENS: int = 100
    TEST_COMPLETION_TOKENS: int = 50


TEST_CONSTANTS = TestConstants()


# ========================================
# 默认路径配置
# ========================================

def get_app_root():
    """
    获取应用根目录，支持PyInstaller打包
    
    开发模式: 返回项目根目录
    打包模式: 返回exe所在目录的上级目录（便携版结构）
    """
    import sys
    from pathlib import Path
    
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后运行
        exe_dir = Path(sys.executable).parent
        # 便携版结构：exe在app目录下，数据在上级目录
        return exe_dir.parent
    else:
        # 开发模式：使用当前工作目录
        return Path.cwd()


def get_data_dir():
    """获取数据目录"""
    from pathlib import Path
    root = get_app_root()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


class PathDefaultsClass:
    """默认路径配置 - 动态计算以支持PyInstaller打包"""
    
    @property
    def DATA_DIR(self) -> str:
        return str(get_data_dir())
    
    @property
    def STATS_DIR(self) -> str:
        path = get_data_dir() / "stats"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    @property
    def EXPORTS_DIR(self) -> str:
        path = get_app_root() / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    @property
    def NOVEL_OUTPUT_DIR(self) -> str:
        path = get_app_root() / "novel_output"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    @property
    def LOGS_DIR(self) -> str:
        path = get_data_dir() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)


PATH_DEFAULTS = PathDefaultsClass()


# ========================================
# 辅助函数
# ========================================

def get_env_or_default(key: str, default: str) -> str:
    """从环境变量获取值，如果不存在则返回默认值"""
    return os.getenv(key, default)


def get_env_int(key: str, default: int) -> int:
    """从环境变量获取整数值"""
    return int(os.getenv(key, str(default)))


def get_env_float(key: str, default: float) -> float:
    """从环境变量获取浮点数值"""
    return float(os.getenv(key, str(default)))


def get_env_bool(key: str, default: bool = False) -> bool:
    """从环境变量获取布尔值"""
    return os.getenv(key, str(default).lower()).lower() in ("true", "1", "yes")