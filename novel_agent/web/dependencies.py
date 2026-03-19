"""
依赖注入模块

提供全局实例的访问和管理。
"""

from typing import Optional
from ..workflow import NovelCoordinator
from ..agents import RouterAgent

# 全局实例
_coordinator: Optional[NovelCoordinator] = None
_router_agent: Optional[RouterAgent] = None


def get_coordinator() -> Optional[NovelCoordinator]:
    """获取协调器实例"""
    return _coordinator


def set_coordinator(coordinator: NovelCoordinator) -> None:
    """设置协调器实例"""
    global _coordinator
    _coordinator = coordinator


def get_router_agent() -> Optional[RouterAgent]:
    """获取路由智能体实例"""
    return _router_agent


def set_router_agent(router_agent: RouterAgent) -> None:
    """设置路由智能体实例"""
    global _router_agent
    _router_agent = router_agent