"""
工作流模块（智能体协作）

包含小说创作的完整工作流管理：
- NovelCoordinator: 主协调器，实现协调者-工作者智能体模式
- WorkflowState: 工作流状态枚举
- WorkflowCheckpoint: 检查点数据结构
- NovelProject: 小说项目数据结构

增强功能：
- 智能路由：自动识别用户意图
- 知识库优先：创作前检索相关上下文
- 响应保证：确保每个请求都有智能体响应
"""

from .coordinator import (
    NovelCoordinator,
    WorkflowState,
    WorkflowCheckpoint,
    NovelProject
)

__all__ = [
    "NovelCoordinator",
    "WorkflowState",
    "WorkflowCheckpoint",
    "NovelProject"
]
