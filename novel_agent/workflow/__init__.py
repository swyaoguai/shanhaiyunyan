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
from .contracts import (
    CreationContract,
    TaskDefinition,
    TaskDependency,
    ExecutionPolicy,
    build_default_creation_contract,
    build_default_task_graph,
)
from .agent_dispatcher import AgentDispatcher, DispatchResult
from .checkpoint_manager import CheckpointManager
from .collab_registry import CollabAgentRegistry, CollabServiceRegistry
from .collab_services import (
    BaseCollabService,
    ContextStrategyService,
    ContentReaderService,
    ContentExpansionService,
    FileNamingService,
    SummaryService,
    ServiceBackedCollabParticipant,
    build_default_collab_participants,
    build_default_collab_service_registry,
)
from .execution_context import CollabExecutionContext, ContextValidationError, TaskExecutionEnvelope
from .context_bundle import (
    ContextBundle,
    confirm_context_bundle,
    create_context_bundle,
    load_confirmed_context_bundles_from_project_dir,
)
from .memory_sync import MemorySyncManager
from .routing_policy import RouteDecision, RouteRule, RoutingPolicy, RoutingPolicyError
from .runtime_event_log import RuntimeEventLog
from .runtime_events import AgentRuntimeEvent, make_runtime_event
from .runtime_hooks import RuntimeHookContext, RuntimeHookRegistry, get_runtime_hook_registry
from .runtime_messages import (
    AgentRuntimeMessage,
    ArtifactEnvelope,
    attach_runtime_message,
    make_artifact_envelope,
    make_runtime_message,
    make_runtime_message_for_event,
)
from .runtime_state import RuntimeStateStore
from .task_pool import TaskPool, TaskPoolSnapshot, TaskStatus

__all__ = [
    "NovelCoordinator",
    "WorkflowState",
    "WorkflowCheckpoint",
    "NovelProject",
    "CreationContract",
    "TaskDefinition",
    "TaskDependency",
    "ExecutionPolicy",
    "build_default_creation_contract",
    "build_default_task_graph",
    "AgentDispatcher",
    "DispatchResult",
    "CheckpointManager",
    "CollabAgentRegistry",
    "CollabServiceRegistry",
    "BaseCollabService",
    "ContextStrategyService",
    "ContentReaderService",
    "ContentExpansionService",
    "FileNamingService",
    "SummaryService",
    "ServiceBackedCollabParticipant",
    "build_default_collab_participants",
    "build_default_collab_service_registry",
    "CollabExecutionContext",
    "ContextValidationError",
    "TaskExecutionEnvelope",
    "ContextBundle",
    "confirm_context_bundle",
    "create_context_bundle",
    "load_confirmed_context_bundles_from_project_dir",
    "MemorySyncManager",
    "RouteDecision",
    "RouteRule",
    "RoutingPolicy",
    "RoutingPolicyError",
    "AgentRuntimeEvent",
    "AgentRuntimeMessage",
    "ArtifactEnvelope",
    "RuntimeEventLog",
    "attach_runtime_message",
    "make_artifact_envelope",
    "make_runtime_event",
    "RuntimeHookContext",
    "RuntimeHookRegistry",
    "get_runtime_hook_registry",
    "make_runtime_message",
    "make_runtime_message_for_event",
    "RuntimeStateStore",
    "TaskPool",
    "TaskPoolSnapshot",
    "TaskStatus",
]
