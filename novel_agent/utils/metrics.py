"""
指标收集器
用于监控Agent性能和资源使用
"""

import time
import asyncio
import logging
from functools import wraps
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from ..constants import METRICS_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    """单次调用记录"""
    agent_name: str
    method: str
    start_time: float
    end_time: Optional[float] = None
    tokens_in: int = 0
    tokens_out: int = 0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        """调用耗时（秒）"""
        if self.end_time is None:
            return 0
        return self.end_time - self.start_time
    
    @property
    def total_tokens(self) -> int:
        """总token数"""
        return self.tokens_in + self.tokens_out
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "method": self.method,
            "duration": self.duration,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "success": self.success,
            "error": self.error,
            "timestamp": datetime.fromtimestamp(self.start_time).isoformat()
        }


@dataclass
class AgentMetrics:
    """单个Agent的指标统计"""
    agent_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_time_seconds: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    call_history: List[CallRecord] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_calls == 0:
            return 0
        return self.successful_calls / self.total_calls
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        if self.total_calls == 0:
            return 0
        return self.failed_calls / self.total_calls
    
    @property
    def avg_duration(self) -> float:
        """平均耗时"""
        if self.total_calls == 0:
            return 0
        return self.total_time_seconds / self.total_calls
    
    @property
    def total_tokens(self) -> int:
        """总token数"""
        return self.total_tokens_in + self.total_tokens_out
    
    @property
    def avg_tokens_per_call(self) -> float:
        """每次调用的平均token数"""
        if self.total_calls == 0:
            return 0
        return self.total_tokens / self.total_calls
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": f"{self.success_rate:.2%}",
            "total_tokens": self.total_tokens,
            "tokens_in": self.total_tokens_in,
            "tokens_out": self.total_tokens_out,
            "avg_tokens_per_call": f"{self.avg_tokens_per_call:.0f}",
            "total_time_seconds": f"{self.total_time_seconds:.2f}",
            "avg_duration": f"{self.avg_duration:.2f}s",
            "min_duration": f"{self.min_duration:.2f}s" if self.min_duration != float('inf') else "N/A",
            "max_duration": f"{self.max_duration:.2f}s"
        }


class MetricsCollector:
    """
    指标收集器
    
    功能：
    1. 收集Agent调用指标
    2. Token使用统计
    3. 性能监控
    4. 错误追踪
    """
    
    def __init__(self, max_history: int = METRICS_CONFIG.MAX_HISTORY):
        """
        初始化指标收集器
        
        Args:
            max_history: 每个Agent保留的最大历史记录数
        """
        self.metrics: Dict[str, AgentMetrics] = {}
        self.max_history = max_history
        self.global_start_time = time.time()
        self._active_calls: Dict[str, CallRecord] = {}
        self._lock = asyncio.Lock()
        
        logger.info("MetricsCollector initialized")
    
    def _ensure_agent_metrics(self, agent_name: str) -> AgentMetrics:
        """确保Agent的指标对象存在"""
        if agent_name not in self.metrics:
            self.metrics[agent_name] = AgentMetrics(agent_name=agent_name)
        return self.metrics[agent_name]
    
    async def start_call(
        self,
        agent_name: str,
        method: str = "execute",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        开始记录一次调用
        
        Args:
            agent_name: Agent名称
            method: 方法名
            metadata: 额外元数据
            
        Returns:
            调用ID
        """
        call_id = f"{agent_name}_{time.time_ns()}"
        record = CallRecord(
            agent_name=agent_name,
            method=method,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        async with self._lock:
            self._active_calls[call_id] = record
        
        return call_id
    
    async def end_call(
        self,
        call_id: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        success: bool = True,
        error: Optional[str] = None
    ) -> Optional[CallRecord]:
        """
        结束一次调用的记录
        
        Args:
            call_id: 调用ID
            tokens_in: 输入token数
            tokens_out: 输出token数
            success: 是否成功
            error: 错误信息
            
        Returns:
            调用记录
        """
        async with self._lock:
            record = self._active_calls.pop(call_id, None)
            if record is None:
                return None
            
            record.end_time = time.time()
            record.tokens_in = tokens_in
            record.tokens_out = tokens_out
            record.success = success
            record.error = error
            
            # 更新Agent指标
            metrics = self._ensure_agent_metrics(record.agent_name)
            metrics.total_calls += 1
            if success:
                metrics.successful_calls += 1
            else:
                metrics.failed_calls += 1
            
            metrics.total_tokens_in += tokens_in
            metrics.total_tokens_out += tokens_out
            metrics.total_time_seconds += record.duration
            
            if record.duration < metrics.min_duration:
                metrics.min_duration = record.duration
            if record.duration > metrics.max_duration:
                metrics.max_duration = record.duration
            
            # 添加到历史记录
            metrics.call_history.append(record)
            
            # 限制历史记录数量
            if len(metrics.call_history) > self.max_history:
                metrics.call_history = metrics.call_history[-self.max_history:]
            
            return record
    
    def record_call(
        self,
        agent_name: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration: float = 0,
        success: bool = True,
        error: Optional[str] = None,
        method: str = "execute"
    ) -> None:
        """
        同步记录一次调用（简化版）
        
        Args:
            agent_name: Agent名称
            tokens_in: 输入token数
            tokens_out: 输出token数
            duration: 耗时（秒）
            success: 是否成功
            error: 错误信息
            method: 方法名
        """
        metrics = self._ensure_agent_metrics(agent_name)
        
        record = CallRecord(
            agent_name=agent_name,
            method=method,
            start_time=time.time() - duration,
            end_time=time.time(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            success=success,
            error=error
        )
        
        metrics.total_calls += 1
        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1
        
        metrics.total_tokens_in += tokens_in
        metrics.total_tokens_out += tokens_out
        metrics.total_time_seconds += duration
        
        if duration > 0:
            if duration < metrics.min_duration:
                metrics.min_duration = duration
            if duration > metrics.max_duration:
                metrics.max_duration = duration
        
        metrics.call_history.append(record)
        
        if len(metrics.call_history) > self.max_history:
            metrics.call_history = metrics.call_history[-self.max_history:]
    
    def get_agent_metrics(self, agent_name: str) -> Optional[AgentMetrics]:
        """获取特定Agent的指标"""
        return self.metrics.get(agent_name)
    
    def get_all_metrics(self) -> Dict[str, AgentMetrics]:
        """获取所有Agent的指标"""
        return self.metrics.copy()
    
    def get_report(self) -> Dict[str, Any]:
        """
        获取完整的统计报告
        
        Returns:
            统计报告字典
        """
        total_calls = sum(m.total_calls for m in self.metrics.values())
        total_tokens = sum(m.total_tokens for m in self.metrics.values())
        total_time = sum(m.total_time_seconds for m in self.metrics.values())
        total_errors = sum(m.failed_calls for m in self.metrics.values())
        
        uptime = time.time() - self.global_start_time
        
        return {
            "summary": {
                "total_agents": len(self.metrics),
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "total_time_seconds": f"{total_time:.2f}",
                "total_errors": total_errors,
                "overall_error_rate": f"{(total_errors / total_calls * 100):.2f}%" if total_calls > 0 else "0%",
                "uptime_seconds": f"{uptime:.2f}"
            },
            "agents": {
                name: metrics.to_dict()
                for name, metrics in self.metrics.items()
            },
            "generated_at": datetime.now().isoformat()
        }
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的错误记录
        
        Args:
            limit: 最大返回数量
            
        Returns:
            错误记录列表
        """
        errors = []
        for metrics in self.metrics.values():
            for record in metrics.call_history:
                if not record.success:
                    errors.append(record.to_dict())
        
        # 按时间倒序排序
        errors.sort(key=lambda x: x["timestamp"], reverse=True)
        return errors[:limit]
    
    def get_token_usage_by_agent(self) -> Dict[str, Dict[str, int]]:
        """获取每个Agent的token使用情况"""
        return {
            name: {
                "tokens_in": metrics.total_tokens_in,
                "tokens_out": metrics.total_tokens_out,
                "total": metrics.total_tokens
            }
            for name, metrics in self.metrics.items()
        }
    
    def get_performance_summary(self) -> Dict[str, Dict[str, str]]:
        """获取性能摘要"""
        return {
            name: {
                "avg_duration": f"{metrics.avg_duration:.2f}s",
                "min_duration": f"{metrics.min_duration:.2f}s" if metrics.min_duration != float('inf') else "N/A",
                "max_duration": f"{metrics.max_duration:.2f}s",
                "calls_per_minute": f"{(metrics.total_calls / max(metrics.total_time_seconds, 1)) * 60:.2f}"
            }
            for name, metrics in self.metrics.items()
        }
    
    def reset(self):
        """重置所有指标"""
        self.metrics.clear()
        self._active_calls.clear()
        self.global_start_time = time.time()
        logger.info("Metrics reset")
    
    def reset_agent(self, agent_name: str):
        """重置特定Agent的指标"""
        if agent_name in self.metrics:
            del self.metrics[agent_name]
            logger.info(f"Metrics reset for agent: {agent_name}")


# 全局指标收集器实例
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器实例"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """重置全局指标收集器"""
    global _metrics_collector
    if _metrics_collector:
        _metrics_collector.reset()
    _metrics_collector = None


# ==================== 装饰器 ====================

def track_metrics(agent_name: str = None, method: str = None):
    """
    指标追踪装饰器
    
    自动记录函数调用的指标
    
    Usage:
        @track_metrics(agent_name="Outliner")
        async def generate_outline(self, ...):
            ...
    
    注意：此装饰器仅支持异步函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 尝试从self获取agent名称
            _agent_name = agent_name
            if _agent_name is None and args:
                _agent_name = getattr(args[0], 'name', None) or type(args[0]).__name__
            
            _method = method or func.__name__
            collector = get_metrics_collector()
            
            call_id = await collector.start_call(_agent_name, _method)
            
            try:
                result = await func(*args, **kwargs)
                
                # 尝试从结果中提取token信息
                tokens_in = 0
                tokens_out = 0
                if isinstance(result, dict):
                    tokens_in = result.get("tokens_in", result.get("prompt_tokens", 0))
                    tokens_out = result.get("tokens_out", result.get("completion_tokens", 0))
                
                await collector.end_call(
                    call_id,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    success=True
                )
                
                return result
                
            except Exception as e:
                await collector.end_call(
                    call_id,
                    success=False,
                    error=str(e)
                )
                raise
        
        return wrapper
    return decorator


class MetricsContext:
    """
    指标上下文管理器
    
    Usage:
        async with MetricsContext("Outliner", "generate_outline") as ctx:
            result = await do_something()
            ctx.set_tokens(100, 500)
    """
    
    def __init__(self, agent_name: str, method: str = "execute"):
        self.agent_name = agent_name
        self.method = method
        self.collector = get_metrics_collector()
        self.call_id: Optional[str] = None
        self.tokens_in = 0
        self.tokens_out = 0
    
    async def __aenter__(self):
        self.call_id = await self.collector.start_call(
            self.agent_name,
            self.method
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        success = exc_type is None
        error = str(exc_val) if exc_val else None
        
        await self.collector.end_call(
            self.call_id,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            success=success,
            error=error
        )
    
    def set_tokens(self, tokens_in: int = 0, tokens_out: int = 0):
        """设置token使用量"""
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


# 模块职责说明：收集Agent性能指标和资源使用统计，支持调用追踪和错误记录。