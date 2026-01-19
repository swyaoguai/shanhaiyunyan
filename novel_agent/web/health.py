"""
健康检查模块
提供系统健康状态、依赖检查、性能指标等
"""

import os
import sys
import time
import asyncio
import platform
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import psutil

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """组件健康状态"""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0
    last_check: str = ""
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """系统健康状态"""
    status: HealthStatus
    version: str
    uptime: float
    components: List[ComponentHealth]
    system_info: Dict[str, Any]
    timestamp: str


class HealthChecker:
    """
    健康检查器
    
    检查项目：
    - 系统资源（CPU、内存、磁盘）
    - LLM API连接
    - 数据库连接
    - 外部服务
    """
    
    def __init__(self, version: str = "1.0.0"):
        self.version = version
        self.start_time = time.time()
        
        # 阈值配置
        self.thresholds = {
            "cpu_percent": 90,
            "memory_percent": 90,
            "disk_percent": 95,
            "api_timeout": 10.0
        }
    
    async def check_all(self) -> SystemHealth:
        """执行全面健康检查"""
        components = []
        
        # 检查各组件
        components.append(await self._check_system_resources())
        components.append(await self._check_llm_api())
        components.append(await self._check_database())
        
        # 计算总体状态
        if any(c.status == HealthStatus.UNHEALTHY for c in components):
            overall_status = HealthStatus.UNHEALTHY
        elif any(c.status == HealthStatus.DEGRADED for c in components):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        return SystemHealth(
            status=overall_status,
            version=self.version,
            uptime=time.time() - self.start_time,
            components=components,
            system_info=self._get_system_info(),
            timestamp=datetime.now().isoformat()
        )
    
    async def check_quick(self) -> Dict[str, Any]:
        """快速健康检查（仅返回基本状态）"""
        try:
            # 基本检查
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            is_healthy = (
                memory.percent < self.thresholds["memory_percent"] and
                disk.percent < self.thresholds["disk_percent"]
            )
            
            return {
                "status": "healthy" if is_healthy else "degraded",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _check_system_resources(self) -> ComponentHealth:
        """检查系统资源"""
        start = time.time()
        
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            issues = []
            status = HealthStatus.HEALTHY
            
            if cpu_percent > self.thresholds["cpu_percent"]:
                issues.append(f"CPU usage high: {cpu_percent}%")
                status = HealthStatus.DEGRADED
            
            if memory.percent > self.thresholds["memory_percent"]:
                issues.append(f"Memory usage high: {memory.percent}%")
                status = HealthStatus.DEGRADED
            
            if disk.percent > self.thresholds["disk_percent"]:
                issues.append(f"Disk usage critical: {disk.percent}%")
                status = HealthStatus.UNHEALTHY
            
            return ComponentHealth(
                name="system_resources",
                status=status,
                message="; ".join(issues) if issues else "All resources OK",
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat(),
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2)
                }
            )
        except Exception as e:
            return ComponentHealth(
                name="system_resources",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat()
            )
    
    async def _check_llm_api(self) -> ComponentHealth:
        """检查LLM API连接"""
        start = time.time()
        
        try:
            from ..config import config
            import httpx
            
            if not config.llm.api_base or not config.llm.api_key:
                return ComponentHealth(
                    name="llm_api",
                    status=HealthStatus.DEGRADED,
                    message="LLM API not configured",
                    latency_ms=(time.time() - start) * 1000,
                    last_check=datetime.now().isoformat()
                )
            
            # 测试API连接
            async with httpx.AsyncClient(timeout=self.thresholds["api_timeout"]) as client:
                response = await client.get(
                    f"{config.llm.api_base.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {config.llm.api_key}"}
                )
                
                latency = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    return ComponentHealth(
                        name="llm_api",
                        status=HealthStatus.HEALTHY,
                        message="Connected",
                        latency_ms=latency,
                        last_check=datetime.now().isoformat(),
                        details={"model": config.llm.model}
                    )
                elif response.status_code == 401:
                    return ComponentHealth(
                        name="llm_api",
                        status=HealthStatus.UNHEALTHY,
                        message="Invalid API key",
                        latency_ms=latency,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    return ComponentHealth(
                        name="llm_api",
                        status=HealthStatus.DEGRADED,
                        message=f"HTTP {response.status_code}",
                        latency_ms=latency,
                        last_check=datetime.now().isoformat()
                    )
                    
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="llm_api",
                status=HealthStatus.UNHEALTHY,
                message="Connection timeout",
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat()
            )
        except Exception as e:
            return ComponentHealth(
                name="llm_api",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat()
            )
    
    async def _check_database(self) -> ComponentHealth:
        """检查数据库连接"""
        start = time.time()
        
        try:
            from pathlib import Path
            
            # 检查数据目录
            from ..constants import PATH_DEFAULTS
            data_dir = Path(PATH_DEFAULTS.DATA_DIR)
            
            if not data_dir.exists():
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.DEGRADED,
                    message="Data directory not found",
                    latency_ms=(time.time() - start) * 1000,
                    last_check=datetime.now().isoformat()
                )
            
            # 检查SQLite数据库（如果存在）
            db_files = list(data_dir.glob("**/*.db"))
            
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="OK",
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat(),
                details={
                    "data_dir": str(data_dir),
                    "db_files": len(db_files)
                }
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000,
                last_check=datetime.now().isoformat()
            )
    
    def _get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "cpu_count": os.cpu_count(),
            "pid": os.getpid()
        }


# 全局健康检查器
_health_checker: Optional[HealthChecker] = None


def get_health_checker(version: str = "1.0.0") -> HealthChecker:
    """获取全局健康检查器"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker(version)
    return _health_checker


def setup_health_routes(app, version: str = "1.0.0"):
    """
    设置健康检查路由
    
    Args:
        app: FastAPI应用
        version: 应用版本
    """
    checker = get_health_checker(version)
    
    @app.get("/health")
    async def health_check():
        """快速健康检查"""
        return await checker.check_quick()
    
    @app.get("/health/full")
    async def full_health_check():
        """完整健康检查"""
        health = await checker.check_all()
        return {
            "status": health.status.value,
            "version": health.version,
            "uptime": health.uptime,
            "timestamp": health.timestamp,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                    "details": c.details
                }
                for c in health.components
            ],
            "system": health.system_info
        }
    
    @app.get("/health/ready")
    async def readiness_check():
        """就绪检查（用于K8s）"""
        health = await checker.check_all()
        
        # 检查关键组件
        llm_ok = any(
            c.name == "llm_api" and c.status != HealthStatus.UNHEALTHY
            for c in health.components
        )
        
        if llm_ok:
            return {"status": "ready"}
        else:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready"}
            )
    
    @app.get("/health/live")
    async def liveness_check():
        """存活检查（用于K8s）"""
        return {"status": "alive", "timestamp": datetime.now().isoformat()}
    
    logger.info("Health check routes setup complete")