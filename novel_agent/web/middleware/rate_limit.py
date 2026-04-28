"""
请求频率限制中间件

基于IP地址的滑动窗口频率限制，防止API滥用。
支持配置不同路由的不同限制策略。

模块职责说明：实现基于内存的请求频率限制，保护系统免受滥用。
"""

import time
import logging
from typing import Dict, Optional, Callable, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from functools import wraps

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...constants import RATE_LIMIT_DEFAULTS


logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """频率限制配置"""
    requests_per_minute: int = RATE_LIMIT_DEFAULTS.REQUESTS_PER_MINUTE
    requests_per_hour: int = RATE_LIMIT_DEFAULTS.REQUESTS_PER_HOUR
    burst_limit: int = RATE_LIMIT_DEFAULTS.BURST_LIMIT
    cooldown_seconds: int = RATE_LIMIT_DEFAULTS.COOLDOWN_SECONDS
    enable_burst: bool = False


@dataclass
class ClientState:
    """客户端状态"""
    minute_requests: list = field(default_factory=list)  # 分钟内的请求时间戳
    hour_requests: list = field(default_factory=list)    # 小时内的请求时间戳
    blocked_until: float = 0                             # 封禁截止时间
    total_blocked: int = 0                               # 累计被封禁次数


class RateLimiter:
    """
    频率限制器

    使用滑动窗口算法实现精确的请求频率控制。
    支持分钟级和小时级限制，以及突发流量控制。
    """

    def __init__(
        self,
        config: Optional[RateLimitConfig] = None,
        cleanup_interval: int = 300  # 清理间隔（秒）
    ):
        """
        初始化频率限制器

        Args:
            config: 频率限制配置
            cleanup_interval: 清理过期记录的间隔（秒）
        """
        self.config = config or RateLimitConfig()
        self.cleanup_interval = cleanup_interval
        self._clients: Dict[str, ClientState] = defaultdict(ClientState)
        self._lock = Lock()
        self._last_cleanup = time.time()

        logger.info(
            f"RateLimiter initialized: {self.config.requests_per_minute}/min, "
            f"{self.config.requests_per_hour}/hour, burst={self.config.burst_limit}"
        )

    def _cleanup_if_needed(self):
        """定期清理过期记录"""
        now = time.time()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        self._last_cleanup = now
        minute_ago = now - 60
        hour_ago = now - 3600

        with self._lock:
            # 清理过期的时间戳
            for client_id, state in self._clients.items():
                state.minute_requests = [t for t in state.minute_requests if t > minute_ago]
                state.hour_requests = [t for t in state.hour_requests if t > hour_ago]

            # 移除长时间无活动的客户端（超过1小时）
            inactive_clients = [
                cid for cid, state in self._clients.items()
                if not state.hour_requests and state.blocked_until < now
            ]
            for cid in inactive_clients:
                del self._clients[cid]

            if inactive_clients:
                logger.debug(f"Cleaned up {len(inactive_clients)} inactive clients")

    def _get_client_id(self, request: Request) -> str:
        """
        获取客户端标识

        优先使用X-Forwarded-For（代理后的真实IP），否则使用连接IP
        """
        # 检查代理头
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # 取第一个IP（最原始的客户端IP）
            return forwarded.split(",")[0].strip()

        # 检查真实IP头
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 使用连接IP
        if request.client:
            return request.client.host

        return "unknown"

    def check(self, request: Request) -> Tuple[bool, Optional[str], int]:
        """
        检查请求是否被允许

        Args:
            request: FastAPI请求对象

        Returns:
            Tuple[is_allowed, error_message, retry_after]
            - is_allowed: 是否允许请求
            - error_message: 错误消息（如果不允许）
            - retry_after: 建议重试等待时间（秒）
        """
        self._cleanup_if_needed()

        client_id = self._get_client_id(request)
        now = time.time()

        with self._lock:
            state = self._clients[client_id]

            # 检查是否在封禁期
            if state.blocked_until > now:
                retry_after = int(state.blocked_until - now)
                logger.warning(
                    f"Client {client_id} blocked, retry after {retry_after}s "
                    f"(total blocks: {state.total_blocked})"
                )
                return False, "请求过于频繁，请稍后再试", retry_after

            # 清理过期的时间戳
            minute_ago = now - 60
            hour_ago = now - 3600
            state.minute_requests = [t for t in state.minute_requests if t > minute_ago]
            state.hour_requests = [t for t in state.hour_requests if t > hour_ago]

            # 检查分钟限制
            if len(state.minute_requests) >= self.config.requests_per_minute:
                # 触发封禁
                state.blocked_until = now + self.config.cooldown_seconds
                state.total_blocked += 1
                logger.warning(
                    f"Client {client_id} exceeded minute limit "
                    f"({len(state.minute_requests)}/{self.config.requests_per_minute}), "
                    f"blocked for {self.config.cooldown_seconds}s"
                )
                return False, "请求过于频繁，请稍后再试", self.config.cooldown_seconds

            # 检查小时限制
            if len(state.hour_requests) >= self.config.requests_per_hour:
                state.blocked_until = now + self.config.cooldown_seconds
                state.total_blocked += 1
                logger.warning(
                    f"Client {client_id} exceeded hour limit "
                    f"({len(state.hour_requests)}/{self.config.requests_per_hour}), "
                    f"blocked for {self.config.cooldown_seconds}s"
                )
                return False, "小时请求次数已达上限，请稍后再试", self.config.cooldown_seconds

            # 检查突发限制（快速连续请求）
            if self.config.enable_burst and self.config.burst_limit > 0 and state.minute_requests:
                recent_count = sum(1 for t in state.minute_requests if now - t < 5)
                if recent_count >= self.config.burst_limit:
                    logger.warning(
                        f"Client {client_id} burst limit hit "
                        f"({recent_count} requests in 5s)"
                    )
                    # 短暂延迟，不封禁
                    return False, "请求过快，请稍后再试", 2

            # 记录本次请求
            state.minute_requests.append(now)
            state.hour_requests.append(now)

            return True, None, 0

    def get_stats(self) -> Dict:
        """获取频率限制统计信息"""
        with self._lock:
            active_clients = len([
                c for c in self._clients.values()
                if c.minute_requests or c.blocked_until > time.time()
            ])
            blocked_clients = len([
                c for c in self._clients.values()
                if c.blocked_until > time.time()
            ])

            return {
                "total_clients_tracked": len(self._clients),
                "active_clients": active_clients,
                "currently_blocked": blocked_clients,
                "config": {
                    "requests_per_minute": self.config.requests_per_minute,
                    "requests_per_hour": self.config.requests_per_hour,
                    "burst_limit": self.config.burst_limit,
                    "cooldown_seconds": self.config.cooldown_seconds
                }
            }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    频率限制中间件

    自动对所有API请求进行频率限制检查。
    """

    # 不需要频率限制的路径
    SKIP_PATHS = {
        "/",
        "/health",
        "/favicon.ico",
        # 设置类只读接口不受限
        "/api/settings",
        "/api/global-config",
        "/api/agents",
        "/api/api-configs",
        "/api/timeout-settings",
        "/api/knowledge-base/config",
        "/api/knowledge-base/stats",
        "/api/chapter-summary-config",
        "/api/skills",
        "/api/project-state",
        "/api/project-data",
        "/api/projects",
        "/api/aux-memory",
    }

    # 需要更严格限制的路径（LLM调用等）
    STRICT_PATHS = {
        "/api/chat",
        "/api/novel",
        "/api/continuous-write",
    }

    def __init__(
        self,
        app: ASGIApp,
        config: Optional[RateLimitConfig] = None,
        strict_config: Optional[RateLimitConfig] = None
    ):
        """
        初始化中间件

        Args:
            app: ASGI应用
            config: 默认频率限制配置
            strict_config: 严格路径的频率限制配置
        """
        super().__init__(app)
        self.limiter = RateLimiter(config)

        # 严格路径使用更严格的配置
        strict_cfg = strict_config or RateLimitConfig(
            requests_per_minute=20,
            requests_per_hour=200,
            burst_limit=5,
            cooldown_seconds=120
        )
        self.strict_limiter = RateLimiter(strict_cfg)

        logger.info("RateLimitMiddleware initialized")

    def _should_skip(self, path: str) -> bool:
        """检查是否应该跳过频率限制"""
        if path in self.SKIP_PATHS:
            return True
        if path.startswith("/static"):
            return True
        return False

    def _is_strict_path(self, path: str) -> bool:
        """检查是否是严格限制路径"""
        for strict_path in self.STRICT_PATHS:
            if path.startswith(strict_path):
                return True
        return False

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        path = request.url.path

        # 跳过静态资源和健康检查
        if self._should_skip(path):
            return await call_next(request)

        # 选择限制器
        limiter = self.strict_limiter if self._is_strict_path(path) else self.limiter

        # 检查频率限制
        is_allowed, error_message, retry_after = limiter.check(request)

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": error_message or "请求频率超限",
                    "error": {
                        "code": 1005,
                        "name": "RATE_LIMIT_EXCEEDED",
                        "message": error_message or "请求频率超限"
                    },
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        # 添加限流状态头
        response = await call_next(request)
        return response


# 装饰器版本的频率限制（用于单个路由）
def rate_limit(
    requests_per_minute: int = 30,
    burst_limit: int = 5
):
    """
    频率限制装饰器

    用于对单个路由函数进行更细粒度的控制

    Args:
        requests_per_minute: 每分钟最大请求数
        burst_limit: 突发限制

    Usage:
        @router.post("/chat")
        @rate_limit(requests_per_minute=20)
        async def chat(request: Request, message: ChatMessage):
            ...
    """
    limiter = RateLimiter(RateLimitConfig(
        requests_per_minute=requests_per_minute,
        burst_limit=burst_limit
    ))

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            is_allowed, error_message, retry_after = limiter.check(request)

            if not is_allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": 1005,
                        "message": error_message,
                        "retry_after": retry_after
                    }
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


# 全局频率限制器实例
_global_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """获取全局频率限制器实例"""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(config)
    return _global_limiter
