"""
智能体模块 (Agents Module)

包含所有智能体实现和通信基础设施：
- BaseAgent: 智能体基类，支持回调、重试、指标收集
- RouterAgent: 智能路由智能体，负责意图识别、知识库检索、工具调用
- 专业智能体: Worldbuilder, Outliner, ChapterWriter, Polisher, Evaluator
- CommunicatorAgent: 用户对话智能体
- ContinuousWriter: 无限续写智能体
- SessionStore: 会话持久化存储（确保换模型后保持连贯性）
- MessageBus: 智能体间消息总线
- KnowledgeBaseMixin: 知识库混入类（多Agent协作共享）
- SharedKnowledgeContext: 共享知识上下文（多Agent状态同步）
- Letta适配器（可选）
"""

from .base_agent import BaseAgent
from .router_agent import RouterAgent, UserIntent, IntentAnalysis
from .worldbuilder import WorldbuilderAgent
from .outliner import OutlinerAgent
from .chapter_writer import ChapterWriterAgent
from .polisher import PolisherAgent
from .evaluator import EvaluatorAgent
from .communicator import CommunicatorAgent
from .continuous_writer import ContinuousWriter, ContinuousWriteConfig
from .session_store import SessionStore, SessionState, get_session_store
from .knowledge_mixin import KnowledgeBaseMixin, SharedKnowledgeContext

# 消息总线
from .message_bus import (
    MessageBus,
    MessageType,
    AgentMessage,
    get_message_bus,
    reset_message_bus,
    create_task_message,
    create_completion_message,
    create_context_update_message,
    create_user_input_request
)

__all__ = [
    # 智能体基类
    "BaseAgent",
    
    # 智能路由智能体
    "RouterAgent",
    "UserIntent",
    "IntentAnalysis",
    
    # 专业智能体
    "WorldbuilderAgent",
    "OutlinerAgent",
    "ChapterWriterAgent",
    "PolisherAgent",
    "EvaluatorAgent",
    "CommunicatorAgent",
    
    # 无限续写智能体
    "ContinuousWriter",
    "ContinuousWriteConfig",
    
    # 会话持久化存储
    "SessionStore",
    "SessionState",
    "get_session_store",
    
    # 知识库混入（多Agent协作）
    "KnowledgeBaseMixin",
    "SharedKnowledgeContext",
    
    # 消息总线
    "MessageBus",
    "MessageType",
    "AgentMessage",
    "get_message_bus",
    "reset_message_bus",
    "create_task_message",
    "create_completion_message",
    "create_context_update_message",
    "create_user_input_request",
]
