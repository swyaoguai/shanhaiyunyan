"""
重试装饰器
提供异步函数的自动重试和降级机制
"""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Callable, Optional, Type, Tuple, Any, List
from dataclasses import dataclass, field

from ..constants import RETRY_DEFAULTS

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3                    # 最大重试次数
    delay: float = 1.0                       # 初始延迟（秒）
    backoff: float = 2.0                      # 退避倍数
    max_delay: float = 60.0                   # 最大延迟（秒）
    jitter: bool = True                       # 是否添加随机抖动
    jitter_range: Tuple[float, float] = (0.5, 1.5)   # 抖动范围
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,)  # 需要重试的异常类型
    ignore_exceptions: Tuple[Type[Exception], ...] = ()  # 不重试的异常类型


@dataclass
class RetryStats:
    """重试统计"""
    attempts: int = 0
    successful: bool = False
    last_error: Optional[str] = None
    total_delay: float = 0.0
    errors: List[str] = field(default_factory=list)


def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ignore_exceptions: Tuple[Type[Exception], ...] = (),
    fallback: Optional[Callable] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception, RetryStats], None]] = None
):
    """
    异步重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 退避倍数（每次重试延迟乘以此值）
        max_delay: 最大延迟（秒）
        jitter: 是否添加随机抖动（防止雪崩）
        retry_exceptions: 需要重试的异常类型
        ignore_exceptions: 不重试的异常类型（直接抛出）
        fallback: 所有重试失败后的降级函数
        on_retry: 每次重试时的回调 (attempt, exception)
        on_failure: 最终失败时的回调 (exception, stats)
        
    Usage:
        @async_retry(max_retries=3, delay=2.0)
        async def my_api_call():
            ...
        
        @async_retry(
            max_retries=5,
            fallback=async_fallback_func,
            on_retry=lambda attempt, e: print(f"Retry {attempt}: {e}")
        )
        async def critical_operation():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            stats = RetryStats()
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                stats.attempts = attempt + 1
                
                try:
                    result = await func(*args, **kwargs)
                    stats.successful = True
                    return result
                    
                except ignore_exceptions as e:
                    # 不重试的异常，直接抛出
                    raise
                    
                except retry_exceptions as e:
                    last_exception = e
                    stats.errors.append(str(e))
                    stats.last_error = str(e)
                    
                    if attempt >= max_retries:
                        # 已达最大重试次数
                        break
                    
                    # 计算延迟
                    wait_time = min(current_delay, max_delay)
                    if jitter:
                        jitter_min, jitter_max = RETRY_DEFAULTS.JITTER_RANGE
                        wait_time *= random.uniform(jitter_min, jitter_max)
                    
                    stats.total_delay += wait_time
                    
                    # 回调
                    if on_retry:
                        try:
                            if asyncio.iscoroutinefunction(on_retry):
                                await on_retry(attempt + 1, e)
                            else:
                                on_retry(attempt + 1, e)
                        except Exception as callback_error:
                            logger.warning(f"on_retry callback error: {callback_error}")
                    
                    logger.warning(
                        f"[{func.__name__}] Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {wait_time:.2f}s..."
                    )
                    
                    await asyncio.sleep(wait_time)
                    current_delay *= backoff
            
            # 所有重试都失败了
            if on_failure:
                try:
                    if asyncio.iscoroutinefunction(on_failure):
                        await on_failure(last_exception, stats)
                    else:
                        on_failure(last_exception, stats)
                except Exception as callback_error:
                    logger.warning(f"on_failure callback error: {callback_error}")
            
            # 尝试降级
            if fallback:
                logger.info(f"[{func.__name__}] Executing fallback function")
                try:
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    else:
                        return fallback(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"[{func.__name__}] Fallback failed: {fallback_error}")
            
            # 没有降级或降级失败，抛出最后的异常
            raise last_exception
        
        # 附加配置到函数
        wrapper.retry_config = RetryConfig(
            max_retries=max_retries,
            delay=delay,
            backoff=backoff,
            max_delay=max_delay,
            jitter=jitter,
            retry_exceptions=retry_exceptions,
            ignore_exceptions=ignore_exceptions
        )
        
        return wrapper
    return decorator


def retry_with_config(config: RetryConfig, fallback: Optional[Callable] = None):
    """
    使用配置对象的重试装饰器
    
    Usage:
        config = RetryConfig(max_retries=5, delay=2.0)
        
        @retry_with_config(config)
        async def my_func():
            ...
    """
    return async_retry(
        max_retries=config.max_retries,
        delay=config.delay,
        backoff=config.backoff,
        max_delay=config.max_delay,
        jitter=config.jitter,
        retry_exceptions=config.retry_exceptions,
        ignore_exceptions=config.ignore_exceptions,
        fallback=fallback
    )


class CircuitBreaker:
    """
    熔断器
    
    当失败次数达到阈值时，熔断器打开，后续请求直接失败
    经过恢复时间后，进入半开状态，允许部分请求通过
    如果成功，关闭熔断器；如果失败，重新打开
    """
    
    def __init__(
        self,
        failure_threshold: int = RETRY_DEFAULTS.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = RETRY_DEFAULTS.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        success_threshold: int = RETRY_DEFAULTS.CIRCUIT_BREAKER_SUCCESS_THRESHOLD
    ):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 失败阈值，达到后熔断
            recovery_timeout: 恢复超时时间（秒）
            success_threshold: 半开状态需要的成功次数
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func: Callable, *args, **kwargs):
        """
        通过熔断器调用函数
        
        Args:
            func: 要调用的异步函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            CircuitBreakerOpen: 熔断器打开时抛出
        """
        if self.state == "open":
            if self._should_try_reset():
                self.state = "half-open"
                self.success_count = 0
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is open. "
                    f"Retry after {self._time_until_reset():.1f}s"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """成功回调"""
        if self.state == "half-open":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "closed"
                self.failure_count = 0
                logger.info("Circuit breaker closed")
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        """失败回调"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "half-open":
            self.state = "open"
            logger.warning("Circuit breaker re-opened from half-open state")
        elif self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
    
    def _should_try_reset(self) -> bool:
        """检查是否应该尝试恢复"""
        if self.last_failure_time is None:
            return True
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.recovery_timeout
    
    def _time_until_reset(self) -> float:
        """距离恢复的时间"""
        if self.last_failure_time is None:
            return 0
        elapsed = time.time() - self.last_failure_time
        return max(0, self.recovery_timeout - elapsed)
    
    def reset(self):
        """重置熔断器"""
        self.state = "closed"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    @property
    def is_open(self) -> bool:
        return self.state == "open"
    
    @property
    def stats(self) -> dict:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "time_until_reset": self._time_until_reset() if self.is_open else 0
        }


class CircuitBreakerOpen(Exception):
    """熔断器打开异常"""
    pass


# ==================== 便捷函数 ====================

def create_llm_retry(
    on_retry_callback: Optional[Callable] = None
):
    """
    创建LLM调用专用的重试装饰器
    
    针对LLM API的特点进行优化：
    - 较多的重试次数（5次）
    - 较短的初始延迟（0.5秒）
    - 较小的退避倍数（1.5x）
    - 适中的最大延迟（30秒）
    """
    return async_retry(
        max_retries=RETRY_DEFAULTS.LLM_MAX_RETRIES,
        delay=RETRY_DEFAULTS.LLM_INITIAL_DELAY,
        backoff=RETRY_DEFAULTS.LLM_BACKOFF,
        max_delay=RETRY_DEFAULTS.LLM_MAX_DELAY,
        jitter=True,
        on_retry=on_retry_callback
    )


def create_network_retry():
    """
    创建网络请求专用的重试装饰器
    
    针对网络请求的特点：
    - 较少的重试次数（3次）
    - 较大的退避倍数（2.5x）
    - 较长的最大延迟（120秒）
    """
    return async_retry(
        max_retries=RETRY_DEFAULTS.NETWORK_MAX_RETRIES,
        delay=RETRY_DEFAULTS.INITIAL_DELAY,
        backoff=RETRY_DEFAULTS.NETWORK_BACKOFF,
        max_delay=RETRY_DEFAULTS.NETWORK_MAX_DELAY,
        jitter=True
    )


# 模块职责说明：提供异步函数的自动重试装饰器和熔断器机制，支持指数退避和抖动。