"""
Web中间件模块
提供速率限制、请求追踪、安全性增强等功能
"""

import time
import asyncio
import hashlib
import logging
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps
import uuid

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..constants import RATE_LIMIT_DEFAULTS, TIMEOUTS

logger = logging.getLogger(__name__)


# ==================== 速率限制 ====================

@dataclass
class RateLimitConfig:
    """速率限制配置"""
    requests_per_minute: int = RATE_LIMIT_DEFAULTS.REQUESTS_PER_MINUTE
    requests_per_hour: int = RATE_LIMIT_DEFAULTS.REQUESTS_PER_HOUR
    burst_limit: int = RATE_LIMIT_DEFAULTS.BURST_LIMIT  # 突发请求限制
    cooldown_seconds: int = RATE_LIMIT_DEFAULTS.COOLDOWN_SECONDS  # 冷却时间


@dataclass
class ClientState:
    """客户端状态"""
    request_times: list = field(default_factory=list)
    is_blocked: bool = False
    block_until: float = 0


class RateLimiter:
    """
    速率限制器
    
    使用滑动窗口算法实现：
    - 每分钟请求限制
    - 每小时请求限制
    - 突发请求限制
    - IP黑名单
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.clients: Dict[str, ClientState] = defaultdict(ClientState)
        self.blacklist: set = set()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识（IP地址）"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _cleanup_old_requests(self, state: ClientState):
        """清理过期的请求记录"""
        now = time.time()
        hour_ago = now - 3600
        state.request_times = [t for t in state.request_times if t > hour_ago]
    
    async def check_rate_limit(self, request: Request) -> Optional[Dict]:
        """
        检查速率限制
        
        Returns:
            None 表示允许，Dict 表示被限制（包含错误信息）
        """
        client_id = self._get_client_id(request)
        
        # 检查黑名单
        if client_id in self.blacklist:
            return {
                "error": "Blocked",
                "message": "Your IP has been blocked",
                "retry_after": -1
            }
        
        state = self.clients[client_id]
        now = time.time()
        
        # 检查是否在冷却期
        if state.is_blocked and now < state.block_until:
            return {
                "error": "Rate Limited",
                "message": "Too many requests, please try again later",
                "retry_after": int(state.block_until - now)
            }
        
        # 重置冷却状态
        if state.is_blocked and now >= state.block_until:
            state.is_blocked = False
        
        # 清理旧记录
        self._cleanup_old_requests(state)
        
        # 检查每分钟限制
        minute_ago = now - 60
        recent_requests = [t for t in state.request_times if t > minute_ago]
        
        if len(recent_requests) >= self.config.requests_per_minute:
            state.is_blocked = True
            state.block_until = now + self.config.cooldown_seconds
            return {
                "error": "Rate Limited",
                "message": f"Exceeded {self.config.requests_per_minute} requests per minute",
                "retry_after": self.config.cooldown_seconds
            }
        
        # 检查每小时限制
        if len(state.request_times) >= self.config.requests_per_hour:
            state.is_blocked = True
            state.block_until = now + self.config.cooldown_seconds * 5
            return {
                "error": "Rate Limited",
                "message": f"Exceeded {self.config.requests_per_hour} requests per hour",
                "retry_after": self.config.cooldown_seconds * 5
            }
        
        # 检查突发限制（最近2秒内的请求）
        burst_window = now - 2
        burst_requests = [t for t in state.request_times if t > burst_window]
        if len(burst_requests) >= self.config.burst_limit:
            return {
                "error": "Burst Limited",
                "message": "Too many requests in a short time",
                "retry_after": 5
            }
        
        # 记录请求
        state.request_times.append(now)
        return None
    
    def add_to_blacklist(self, client_id: str):
        """添加到黑名单"""
        self.blacklist.add(client_id)
        logger.warning(f"Client {client_id} added to blacklist")
    
    def remove_from_blacklist(self, client_id: str):
        """从黑名单移除"""
        self.blacklist.discard(client_id)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "active_clients": len(self.clients),
            "blacklisted": len(self.blacklist),
            "config": {
                "requests_per_minute": self.config.requests_per_minute,
                "requests_per_hour": self.config.requests_per_hour,
                "burst_limit": self.config.burst_limit
            }
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""
    
    def __init__(self, app, limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.limiter = limiter or RateLimiter()
    
    async def dispatch(self, request: Request, call_next):
        # 跳过静态文件和健康检查
        path = request.url.path
        if path.startswith("/static") or path == "/health":
            return await call_next(request)
        
        # 检查速率限制
        result = await self.limiter.check_rate_limit(request)
        if result:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": result
                },
                headers={"Retry-After": str(result.get("retry_after", 60))}
            )
        
        return await call_next(request)


# ==================== 请求追踪 ====================

class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    请求追踪中间件
    
    为每个请求生成唯一ID，用于日志追踪和调试
    """
    
    async def dispatch(self, request: Request, call_next):
        # 生成请求ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        
        # 记录请求开始
        start_time = time.time()
        
        # 将request_id注入到请求状态
        request.state.request_id = request_id
        
        # 处理请求
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 添加响应头
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        
        # 记录日志
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"- {response.status_code} ({process_time:.3f}s)"
        )
        
        return response


# ==================== 安全性增强 ====================

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    安全性中间件
    
    添加安全响应头，防止常见攻击
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 对API响应禁用缓存
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        
        return response


# ==================== CORS增强 ====================

class CORSConfig:
    """CORS配置"""
    allow_origins: list = ["*"]
    allow_methods: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers: list = ["*"]
    allow_credentials: bool = True
    max_age: int = TIMEOUTS.CORS_MAX_AGE


# ==================== 辅助函数 ====================

def setup_middleware(app, config: Optional[Dict] = None):
    """
    设置所有中间件
    
    Args:
        app: FastAPI应用
        config: 配置字典
    """
    config = config or {}
    
    # 速率限制
    if config.get("rate_limit", {}).get("enabled", True):
        rate_config = RateLimitConfig(
            requests_per_minute=config.get("rate_limit", {}).get("per_minute", 60),
            requests_per_hour=config.get("rate_limit", {}).get("per_hour", 1000),
            burst_limit=config.get("rate_limit", {}).get("burst", 10)
        )
        app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(rate_config))
    
    # 请求追踪
    if config.get("request_tracking", True):
        app.add_middleware(RequestTrackingMiddleware)
    
    # 安全性
    if config.get("security", True):
        app.add_middleware(SecurityMiddleware)
    
    logger.info("Middleware setup complete")


# 全局速率限制器实例
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter