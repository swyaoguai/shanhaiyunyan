"""
API错误处理模块
定义统一的错误码和错误响应格式
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..constants import RATE_LIMIT_DEFAULTS


class ErrorCode(Enum):
    """错误码枚举"""
    
    # 通用错误 (1xxx)
    UNKNOWN_ERROR = 1000
    VALIDATION_ERROR = 1001
    INVALID_REQUEST = 1002
    NOT_FOUND = 1003
    METHOD_NOT_ALLOWED = 1004
    RATE_LIMIT_EXCEEDED = 1005
    
    # 认证错误 (2xxx)
    UNAUTHORIZED = 2000
    INVALID_API_KEY = 2001
    API_KEY_EXPIRED = 2002
    
    # 配置错误 (3xxx)
    CONFIG_NOT_FOUND = 3000
    CONFIG_INVALID = 3001
    GLOBAL_API_NOT_CONFIGURED = 3002
    AGENT_NOT_CONFIGURED = 3003
    
    # Agent错误 (4xxx)
    AGENT_NOT_FOUND = 4000
    AGENT_EXECUTION_FAILED = 4001
    AGENT_TIMEOUT = 4002
    
    # 项目错误 (5xxx)
    PROJECT_NOT_FOUND = 5000
    PROJECT_CREATE_FAILED = 5001
    PROJECT_DELETE_FAILED = 5002
    
    # LLM错误 (6xxx)
    LLM_API_ERROR = 6000
    LLM_TIMEOUT = 6001
    LLM_RATE_LIMIT = 6002
    LLM_INVALID_RESPONSE = 6003
    
    # Letta错误 (7xxx)
    LETTA_NOT_AVAILABLE = 7000
    LETTA_NOT_ENABLED = 7001
    LETTA_API_ERROR = 7002
    
    # 工作流错误 (8xxx)
    WORKFLOW_NOT_FOUND = 8000
    WORKFLOW_FAILED = 8001
    CHECKPOINT_NOT_FOUND = 8002


# 错误码对应的HTTP状态码
ERROR_HTTP_STATUS = {
    ErrorCode.UNKNOWN_ERROR: 500,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.INVALID_API_KEY: 401,
    ErrorCode.API_KEY_EXPIRED: 401,
    
    ErrorCode.CONFIG_NOT_FOUND: 404,
    ErrorCode.CONFIG_INVALID: 400,
    ErrorCode.GLOBAL_API_NOT_CONFIGURED: 400,
    ErrorCode.AGENT_NOT_CONFIGURED: 400,
    
    ErrorCode.AGENT_NOT_FOUND: 404,
    ErrorCode.AGENT_EXECUTION_FAILED: 500,
    ErrorCode.AGENT_TIMEOUT: 504,
    
    ErrorCode.PROJECT_NOT_FOUND: 404,
    ErrorCode.PROJECT_CREATE_FAILED: 500,
    ErrorCode.PROJECT_DELETE_FAILED: 500,
    
    ErrorCode.LLM_API_ERROR: 502,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_RATE_LIMIT: 429,
    ErrorCode.LLM_INVALID_RESPONSE: 502,
    
    ErrorCode.LETTA_NOT_AVAILABLE: 503,
    ErrorCode.LETTA_NOT_ENABLED: 400,
    ErrorCode.LETTA_API_ERROR: 502,
    
    ErrorCode.WORKFLOW_NOT_FOUND: 404,
    ErrorCode.WORKFLOW_FAILED: 500,
    ErrorCode.CHECKPOINT_NOT_FOUND: 404,
}


@dataclass
class ErrorResponse:
    """统一错误响应格式"""
    success: bool
    error_code: int
    error_name: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "error": {
                "code": self.error_code,
                "name": self.error_name,
                "message": self.message
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        if self.request_id:
            result["request_id"] = self.request_id
        return result


class APIError(Exception):
    """API错误基类"""
    
    def __init__(
        self,
        code: ErrorCode,
        message: str = "",
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message or code.name.replace("_", " ").title()
        self.details = details
        self.status_code = ERROR_HTTP_STATUS.get(code, 500)
        super().__init__(self.message)
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        return ErrorResponse(
            success=False,
            error_code=self.code.value,
            error_name=self.code.name,
            message=self.message,
            details=self.details,
            request_id=request_id
        )


# 常用错误类
class ValidationError(APIError):
    """验证错误"""
    def __init__(self, message: str = "Validation failed", details: Dict[str, Any] = None):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, details)


class NotFoundError(APIError):
    """资源未找到"""
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            ErrorCode.NOT_FOUND, 
            f"{resource} not found"
        )


class ConfigurationError(APIError):
    """配置错误"""
    def __init__(self, message: str = "Configuration error"):
        super().__init__(ErrorCode.CONFIG_INVALID, message)


class AgentError(APIError):
    """Agent执行错误"""
    def __init__(self, agent_name: str, message: str = "Agent execution failed"):
        super().__init__(
            ErrorCode.AGENT_EXECUTION_FAILED,
            f"[{agent_name}] {message}",
            {"agent": agent_name}
        )


class LLMError(APIError):
    """LLM API错误"""
    def __init__(self, message: str = "LLM API error", provider: str = ""):
        super().__init__(
            ErrorCode.LLM_API_ERROR,
            message,
            {"provider": provider} if provider else None
        )


class RateLimitError(APIError):
    """频率限制错误"""
    def __init__(self, retry_after: int = RATE_LIMIT_DEFAULTS.DEFAULT_RETRY_AFTER):
        super().__init__(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            f"Rate limit exceeded. Please retry after {retry_after} seconds.",
            {"retry_after": retry_after}
        )


# FastAPI异常处理器
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """
    APIError异常处理器
    用于FastAPI的exception_handler
    """
    request_id = getattr(request.state, 'request_id', None)
    response = exc.to_response(request_id)
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response.to_dict()
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Pydantic验证错误处理器
    """
    from pydantic import ValidationError as PydanticValidationError
    
    if isinstance(exc, PydanticValidationError):
        errors = []
        for error in exc.errors():
            field = ".".join(str(x) for x in error["loc"])
            errors.append({
                "field": field,
                "message": error["msg"],
                "type": error["type"]
            })
        
        api_error = ValidationError(
            "Request validation failed",
            {"validation_errors": errors}
        )
        return await api_error_handler(request, api_error)
    
    # 其他验证错误
    api_error = ValidationError(str(exc))
    return await api_error_handler(request, api_error)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    通用异常处理器
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 记录错误
    logger.exception(f"Unhandled exception: {exc}")
    
    api_error = APIError(
        ErrorCode.UNKNOWN_ERROR,
        "An unexpected error occurred",
        {"type": type(exc).__name__}
    )
    return await api_error_handler(request, api_error)


def register_error_handlers(app):
    """
    注册所有错误处理器到FastAPI应用
    
    Usage:
        from novel_agent.web.errors import register_error_handlers
        
        app = FastAPI()
        register_error_handlers(app)
    """
    from pydantic import ValidationError as PydanticValidationError
    
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


# 成功响应辅助函数
def success_response(
    data: Any = None, 
    message: str = "Success",
    **kwargs
) -> Dict[str, Any]:
    """
    创建成功响应
    
    Args:
        data: 响应数据
        message: 成功消息
        **kwargs: 额外字段
        
    Returns:
        响应字典
    """
    result = {
        "success": True,
        "message": message
    }
    if data is not None:
        result["data"] = data
    result.update(kwargs)
    return result


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """
    创建分页响应
    
    Args:
        items: 数据项列表
        total: 总数量
        page: 当前页码
        page_size: 每页大小
        
    Returns:
        分页响应字典
    """
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "success": True,
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }