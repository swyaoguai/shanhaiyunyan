"""
小说创作协调器
实现协调者-工作者多智能体协作模式

增强功能：
- 工作流状态管理 (WorkflowState)
- 检查点保存/恢复 (Checkpoint)
- 串行章节写作
- 回调处理器集成
- 指标收集
- 智能路由集成（强制LLM意图识别）
"""

import asyncio
import json
import re
from typing import Dict, Any, Optional, List, AsyncGenerator, Callable, Awaitable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging

from ..agents.worldbuilder import WorldbuilderAgent
from ..agents.outliner import OutlinerAgent
from ..agents.chapter_writer import ChapterWriterAgent
from ..agents.polisher import PolisherAgent
from ..agents.evaluator import EvaluatorAgent
from ..agents.character_builder import CharacterBuilderAgent
from ..agents.capability_registry import get_capability_registry
from ..agents.message_bus import (
    get_message_bus, MessageType, AgentMessage,
    create_user_input_request
)
from ..context import ContextManager, CharacterManager, WorldManager
from ..utils.metrics import get_metrics_collector
from ..constants import WRITING_CONFIG, TIMEOUTS
from ..utils.atomic_write import atomic_write_text, atomic_write_json
from ..content_sanitizer import strip_internal_author_markers
from ..outline_utils import (
    build_outline_overview_row,
    extract_outline_chapter_rows,
    extract_eventlines_from_outline,
    merge_eventline_rows,
    normalize_outline_payload,
)
from ..memory_manager import get_memory_manager
from ..aux_memory import get_aux_memory_service
from ..project_manager import get_project_manager
from ..route_targets import build_default_route_target_registry
from .plot_thread_state import PlotThreadStateMachine
from .contracts import (
    CreationContract,
    TaskDefinition,
    build_default_creation_contract,
    build_default_task_graph,
)
from .agent_dispatcher import AgentDispatcher
from .checkpoint_manager import CheckpointManager
from .collab_registry import CollabAgentRegistry, CollabServiceRegistry
from .collab_services import (
    build_default_collab_participants,
    build_default_collab_service_registry,
)
from .execution_context import CollabExecutionContext, TaskExecutionEnvelope
from .memory_sync import MemorySyncManager
from .routing_policy import RoutingPolicy
from .runtime_state import RuntimeStateStore
from .task_pool import TaskPool, TaskStatus

logger = logging.getLogger(__name__)


class WorkflowState(Enum):
    """工作流状态"""
    IDLE = "idle"                    # 空闲
    WORLDBUILDING = "worldbuilding"  # 世界观构建中
    OUTLINING = "outlining"          # 大纲规划中
    WRITING = "writing"              # 章节撰写中
    POLISHING = "polishing"          # 润色中
    COMPLETED = "completed"          # 已完成
    PAUSED = "paused"                # 已暂停
    FAILED = "failed"                # 失败


@dataclass
class WorkflowCheckpoint:
    """工作流检查点"""
    state: WorkflowState
    current_chapter: int
    completed_stages: List[str]
    project_data: Dict[str, Any]
    last_updated: str
    error_info: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "current_chapter": self.current_chapter,
            "completed_stages": self.completed_stages,
            "project_data": self.project_data,
            "last_updated": self.last_updated,
            "error_info": self.error_info
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowCheckpoint':
        return cls(
            state=WorkflowState(data["state"]),
            current_chapter=data["current_chapter"],
            completed_stages=data["completed_stages"],
            project_data=data.get("project_data", {}),
            last_updated=data["last_updated"],
            error_info=data.get("error_info")
        )


@dataclass
class NovelProject:
    """小说项目数据结构"""
    id: str
    title: str
    novel_type: str
    status: str  # planning/writing/completed/paused/failed
    created_at: str
    updated_at: str
    total_chapters: int = 0
    completed_chapters: int = 0
    word_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 回调处理器类型
ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]


class NovelCoordinator:
    """
    小说创作协调器
    
    采用协调者-工作者智能体模式：
    - 协调器负责任务分配和流程控制
    - 各专业智能体作为工作者执行具体任务
    - ContextManager负责上下文的隔离与同步
    
    增强功能：
    - 工作流状态管理和检查点
    - 串行章节写作
    - 回调处理器
    - 消息总线集成
    - 智能路由（强制LLM意图识别）
    """
    
    def __init__(
        self,
        project_dir: Optional[Path] = None,
        progress_callback: Optional[ProgressCallback] = None,
        auto_save_checkpoint: bool = True
    ):
        """
        初始化协调器
        
        Args:
            project_dir: 项目目录
            progress_callback: 进度回调函数
            auto_save_checkpoint: 是否自动保存检查点
        """
        from ..constants import PATH_DEFAULTS
        self.project_dir = project_dir or Path(PATH_DEFAULTS.NOVEL_OUTPUT_DIR)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # 回调配置
        self.progress_callback = progress_callback
        self.auto_save_checkpoint = auto_save_checkpoint
        
        # 初始化各专业Agent（传入回调处理器）
        self.worldbuilder = WorldbuilderAgent()
        self.outliner = OutlinerAgent()
        self.chapter_writer = ChapterWriterAgent()
        self.polisher = PolisherAgent()
        self.evaluator = EvaluatorAgent()
        self.character_builder = CharacterBuilderAgent()
        self.collab_service_registry = CollabServiceRegistry()
        self.collab_service_registry.register_many(build_default_collab_service_registry())
        self.collab_agent_registry = CollabAgentRegistry(
            fallback_registry_provider=lambda: self.capability_registry
        )
        default_collab_participants = build_default_collab_participants(
            {
                name: self.collab_service_registry.get(name)
                for name in self.collab_service_registry.list_agents()
            }
        )
        self.collab_agent_registry.register_many(list(default_collab_participants.values()))
        self.context_strategy = default_collab_participants["ContextStrategy"]
        self.content_reader = default_collab_participants["ContentReader"]
        self.content_expansion = default_collab_participants["ContentExpansion"]
        # 问题6修复：使用 ServiceBackedCollabParticipant 包装后的实例，与其他服务保持一致
        self.file_naming = default_collab_participants.get("FileNaming") or self.collab_service_registry.get("file_naming")
        self.summary_orchestrator = default_collab_participants["SummaryOrchestrator"]
        
        # 为Agent设置回调处理器
        if progress_callback:
            self._setup_agent_callbacks()
        
        # 记忆管理（先初始化，因为管理器需要用到）
        self.memory_manager = get_memory_manager()
        self.aux_memory_service = get_aux_memory_service()
        self.project_manager = get_project_manager()
        self.checkpoint_manager = CheckpointManager(
            project_dir_provider=lambda: self.project_dir,
        )
        self.runtime_state_store = RuntimeStateStore(
            project_dir_provider=lambda: self.project_dir,
            project_manager_provider=lambda: self.project_manager,
        )
        self.memory_sync_manager = MemorySyncManager(
            project_dir_provider=lambda: self.project_dir,
            project_scope_provider=lambda: self.project_manager.current_project_id or (self.project.id if self.project else ""),
            project_payload_provider=lambda: self.project.to_dict() if self.project else {},
            memory_manager=self.memory_manager,
            contract_version_provider=lambda: self._memory_contract_version,
        )
        
        # 初始化上下文管理器（使用当前项目目录）
        self._init_managers()
        self._plot_thread_state_key = "plot_thread_state"
        self._plot_thread_machine = PlotThreadStateMachine(project_dir=self.project_dir)
        self._plot_thread_lock = asyncio.Lock()
        self._load_plot_thread_state()
        self._memory_agent_ids: Dict[str, str] = {}
        self._memory_contract_version = "2026-02-07.1"
        self._trends_service: Optional[Any] = None
        self._project_ready_executor: Optional['ProjectReadyTaskExecutor'] = None

        # 项目信息
        self.project: Optional[NovelProject] = None
        
        # 工作流状态
        self.workflow_state = WorkflowState.IDLE
        self._last_active_workflow_state = WorkflowState.IDLE
        self.checkpoint: Optional[WorkflowCheckpoint] = None
        self._load_checkpoint()
        
        # 消息总线和指标
        self.message_bus = get_message_bus()
        self.metrics = get_metrics_collector()

        # Agent能力注册表
        self.capability_registry = get_capability_registry()
        self.capability_registry.register_many([
            self.worldbuilder,
            self.outliner,
            self.chapter_writer,
            self.polisher,
            self.evaluator,
            self.character_builder,
        ])
        self.allow_ephemeral_agents = True
        self.routing_policy = RoutingPolicy.default()
        self.agent_dispatcher = AgentDispatcher(
            routing_policy=self.routing_policy,
            capability_registry_provider=lambda: self.collab_agent_registry,
            project_manager_provider=lambda: self.project_manager,
            project_dir_provider=lambda: self.project_dir,
            save_runtime_task_pool=self.runtime_state_store.save_runtime_task_pool,
            notify_progress=self._notify_progress,
            supervised_mode_provider=lambda: self.supervised_mode,
            fallback_to_orchestrated_provider=lambda: self.fallback_to_orchestrated,
            allow_ephemeral_agent_provider=lambda: self.allow_ephemeral_agents,
            runtime_state_store=self.runtime_state_store,
        )

        # 问题9修复：为需要 LLM 的 Service 创建共享 LLMClient 并注入
        from ..agents.llm_client import create_llm_client
        from ..agent_config import get_config_manager
        _cfg_mgr = get_config_manager()
        _active_cfg = _cfg_mgr.multi_config.get_active_config()
        _active_api_type = getattr(_active_cfg, 'api_type', 'openai_chat') if _active_cfg else 'openai_chat'
        self._service_llm_client = create_llm_client(
            metrics_namespace="collab_service",
            api_type=_active_api_type,
        )
        for service_name in ("content_expansion", "summary_orchestrator"):
            svc = self.collab_service_registry.get(service_name)
            if svc is not None and hasattr(svc, "set_llm_client"):
                svc.set_llm_client(self._service_llm_client)
        # 同时为 ServiceBackedCollabParticipant 包装的实例注入
        for participant_name in ("ContentExpansion", "SummaryOrchestrator"):
            participant = default_collab_participants.get(participant_name)
            if participant is not None and hasattr(participant, "set_llm_client"):
                participant.set_llm_client(self._service_llm_client)

        # 共享知识库实例（由Web层统一注入）
        self.knowledge_base = None

        # 监督式自组织保底策略
        self.supervised_mode = True
        self.fallback_to_orchestrated = True
        
        # 控制标志
        self._paused = False
        self._cancelled = False
        
        # 消息总线状态
        self._bus_started = False
        self._subscribed = False
        
        # 待处理的用户输入请求
        self._pending_user_inputs: Dict[str, asyncio.Future] = {}
        self._project_persistence_lock = asyncio.Lock()

        logger.info(f"NovelCoordinator initialized with project dir: {self.project_dir}")

    def _sync_outline_to_library(self, outline_rows: List[Dict[str, Any]]) -> None:
        """Dedup: sync outline to library service."""
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy("outline", outline_rows)
        except Exception as e:
            logger.warning(f"[Coordinator] Library outline sync failed: {e}")

    def _sync_eventlines_to_library(self, eventline_rows: List[Dict[str, Any]]) -> None:
        """Dedup: sync eventlines to library service."""
        try:
            from ..library_service import get_library_service
            svc = get_library_service()
            svc.upsert_from_legacy("eventlines", eventline_rows)
        except Exception as e:
            logger.warning(f"[Coordinator] Library eventlines sync failed: {e}")

    def _sync_eventlines_from_outline(self, outline_data: Any) -> Dict[str, Any]:
        generated_rows = extract_eventlines_from_outline(outline_data)
        if not generated_rows:
            return {"eventline_count": 0, "status": "skipped"}

        existing_rows = self.project_manager.load_project_data("eventlines")
        merged_rows = merge_eventline_rows(existing_rows, generated_rows)
        if merged_rows != existing_rows:
            self.project_manager.save_project_data("eventlines", merged_rows)
            self._sync_eventlines_to_library(merged_rows)
            return {
                "eventline_count": len(generated_rows),
                "merged_count": len(merged_rows),
                "status": "updated",
            }
        return {
            "eventline_count": len(generated_rows),
            "merged_count": len(merged_rows),
            "status": "unchanged",
        }

    def _build_metadata_patch(self, run_result: Dict[str, Any]) -> Dict[str, Any]:
        """Dedup: build metadata patch for project-ready task execution."""
        return {
            "project_task_execution": "ready_task_loop",
            "selected_agent": run_result.get("selected_agent", ""),
            "execution_mode": run_result.get("execution_mode", ""),
            "fallback_used": bool(run_result.get("fallback_used", False)),
            "route_reason": run_result.get("route_reason", ""),
            "candidate_source": run_result.get("candidate_source", ""),
            "context_snapshot_id": run_result.get("context_snapshot_id", ""),
            "fallback_provenance": run_result.get("fallback_provenance", {}),
        }

    def _init_managers(self):
        """初始化或重新初始化所有管理器（使用当前项目目录）"""
        # 如果有当前项目，使用项目目录；否则使用默认目录
        if self.project_manager.current_project_id:
            current_project_dir = self.project_manager._get_project_dir(
                self.project_manager.current_project_id
            )
            self.project_dir = current_project_dir
        
        # 初始化上下文管理器
        self.context_manager = ContextManager(self.project_dir)
        self.character_manager = CharacterManager(self.project_dir)
        self.world_manager = WorldManager(self.project_dir)
        
        logger.debug(f"Managers initialized with project dir: {self.project_dir}")
    
    def switch_to_project(self, project_id: str) -> bool:
        """
        切换到指定项目并同步所有管理器
        
        Args:
            project_id: 项目ID
            
        Returns:
            是否切换成功
        """
        if not self.project_manager.switch_project(project_id):
            logger.warning(f"Failed to switch to project {project_id}")
            return False
        
        # 获取新项目目录
        new_project_dir = self.project_manager._get_project_dir(project_id)
        self.project_dir = new_project_dir
        
        # 重新初始化所有管理器
        self._init_managers()
        
        # 重新加载检查点和状态
        self._load_checkpoint()
        self._load_plot_thread_state()
        
        logger.info(f"Switched to project {project_id}, dir: {new_project_dir}")
        return True

    def set_knowledge_base(self, knowledge_base) -> None:
        """统一为协调器及其子Agent注入知识库实例。"""
        self.knowledge_base = knowledge_base

        for agent in [
            self.worldbuilder,
            self.outliner,
            self.chapter_writer,
            self.polisher,
            self.evaluator,
            self.character_builder,
            self.context_strategy,
            self.content_reader,
            self.content_expansion,
            self.file_naming,
            self.summary_orchestrator,
        ]:
            if hasattr(agent, "set_knowledge_base"):
                try:
                    agent.set_knowledge_base(knowledge_base)
                except Exception as exc:
                    logger.warning(f"[Coordinator] 为 {getattr(agent, 'name', type(agent).__name__)} 注入知识库失败: {exc}")

        logger.info("[Coordinator] 知识库已同步到协调器子Agent")

    def _build_aux_memory_query(self, chapter_num: int, chapter_outline: Dict[str, Any], context: Dict[str, Any]) -> str:
        """构建辅助记忆检索查询文本"""
        chunks: List[str] = []

        outline_text = chapter_outline.get("summary") or str(chapter_outline)
        if outline_text:
            chunks.append(str(outline_text))

        chapter_title = chapter_outline.get("title")
        if chapter_title:
            chunks.append(str(chapter_title))

        if context.get("previous_summary"):
            chunks.append(str(context.get("previous_summary")))

        chunks.append(f"chapter:{chapter_num}")
        query = "\n".join([chunk for chunk in chunks if chunk]).strip()
        return query[:1000]

    def _get_aux_memory_injection_context(self, query: str) -> Dict[str, Any]:
        """获取辅助记忆注入上下文（低优先级）"""
        current_project_id = self.project_manager.current_project_id
        if not current_project_id:
            return {
                "enabled": False,
                "prompt_preview": "",
                "items": [],
                "count": 0,
                "mode": "fast",
            }

        try:
            payload = self.aux_memory_service.get_injection_for_writing(
                project_id=current_project_id,
                query=query,
            )
            if isinstance(payload, dict):
                return payload
            logger.warning("[AuxMemory] 注入上下文格式异常，回退为空")
            return {
                "enabled": False,
                "prompt_preview": "",
                "items": [],
                "count": 0,
                "mode": "fast",
            }
        except Exception as exc:
            logger.warning(f"[AuxMemory] 获取注入上下文失败: {exc}")
            return {
                "enabled": False,
                "prompt_preview": "",
                "items": [],
                "count": 0,
                "mode": "fast",
            }

    def _init_trends_service(self) -> 'TrendsService':
        from .trends_service import TrendsService
        return TrendsService(worldbuilder=self.worldbuilder)

    async def _search_trends_for_collab(self, platforms: Optional[List[str]], limit: int = 5) -> List[Dict[str, Any]]:
        svc = self._trends_service or self._init_trends_service()
        self._trends_service = svc
        return await svc.search_trends(platforms=platforms, limit=limit)

    def _build_trends_prompt_block(self, trends_data: List[Dict[str, Any]], limit: int = 5) -> str:
        from .trends_service import build_trends_prompt_block
        return build_trends_prompt_block(trends_data, limit)

    def _init_plot_thread_machine(self) -> 'PlotThreadStateMachine':
        from .plot_thread_state import PlotThreadStateMachine
        pm = PlotThreadStateMachine(project_dir=self.project_dir)
        if self._plot_thread_state_key:
            pm.state_key = self._plot_thread_state_key
        return pm

    def _load_plot_thread_state(self) -> None:
        self._plot_thread_machine = self._init_plot_thread_machine()
        self._plot_thread_machine.load_plot_thread_state()

    def _save_plot_thread_state(self) -> None:
        if hasattr(self, '_plot_thread_machine'):
            self._plot_thread_machine.save_plot_thread_state()

    def _sync_plot_thread_state_with_outline(
        self,
        outline_data: Optional[Dict[str, Any]],
        total_chapters: int,
        reset: bool,
    ) -> Dict[str, Any]:
        eventlines = self.project_manager.load_project_data("eventlines")
        if not isinstance(eventlines, list):
            eventlines = []
        return self._plot_thread_machine.sync_with_outline_external(
            outline_data if isinstance(outline_data, dict) else {},
            total_chapters=total_chapters,
            reset=reset,
            eventlines=[row for row in eventlines if isinstance(row, dict)],
        )

    async def _plan_plot_thread_for_chapter(
        self,
        chapter_num: int,
        chapter_outline: Any,
    ) -> Dict[str, Any]:
        async with self._plot_thread_lock:
            return await self._plot_thread_machine.plan_for_chapter(chapter_num, chapter_outline)

    async def _complete_plot_thread_for_chapter(
        self,
        chapter_num: int,
        chapter_outline: Any,
        chapter_content: str,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        async with self._plot_thread_lock:
            return await self._plot_thread_machine.complete_for_chapter(
                chapter_num, chapter_outline, chapter_content, evaluation,
            )

    async def _ensure_message_bus_started(self):
        """确保消息总线已启动并订阅"""
        if not self._bus_started:
            await self.message_bus.start()
            self._bus_started = True
            logger.info("Message bus started")
        
        if not self._subscribed:
            self.message_bus.subscribe("coordinator", self._handle_agent_message)
            # 订阅用户输入请求类型
            self.message_bus.subscribe_type(
                MessageType.USER_INPUT_REQUIRED,
                self._handle_user_input_request
            )
            self._subscribed = True
            logger.info("Coordinator subscribed to message bus")
    
    async def _handle_agent_message(self, message: AgentMessage) -> None:
        """
        处理来自Agent的消息
        
        Args:
            message: Agent消息
        """
        logger.debug(f"Coordinator received message: {message.msg_type.value} from {message.sender}")
        
        if message.msg_type == MessageType.TASK_COMPLETED:
            # 任务完成，记录指标
            result = message.payload.get("result", {})
            success = message.payload.get("success", True)
            
            if self.progress_callback:
                await self._notify_progress({
                    "type": "agent_task_completed",
                    "agent": message.sender,
                    "success": success,
                    "result_summary": str(result)[:200]
                })
        
        elif message.msg_type == MessageType.TASK_FAILED:
            # 任务失败
            error = message.payload.get("error", "Unknown error")
            logger.error(f"Task failed from {message.sender}: {error}")
            
            if self.progress_callback:
                await self._notify_progress({
                    "type": "agent_task_failed",
                    "agent": message.sender,
                    "error": error
                })
        
        elif message.msg_type == MessageType.TASK_PROGRESS:
            # 进度更新
            if self.progress_callback:
                await self._notify_progress({
                    "type": "agent_progress",
                    "agent": message.sender,
                    **message.payload
                })
    
    async def _handle_user_input_request(self, message: AgentMessage) -> None:
        """
        处理用户输入请求
        
        Args:
            message: 用户输入请求消息
        """
        question = message.payload.get("question", "")
        options = message.payload.get("options")
        input_type = message.payload.get("input_type", "text")
        
        logger.info(f"User input requested by {message.sender}: {question}")
        
        # 通过回调通知前端
        if self.progress_callback:
            await self._notify_progress({
                "type": "user_input_required",
                "request_id": message.id,
                "agent": message.sender,
                "question": question,
                "options": options,
                "input_type": input_type
            })
    
    async def submit_user_input(self, request_id: str, user_input: str) -> None:
        """
        提交用户输入（由Web层调用）
        
        Args:
            request_id: 请求ID
            user_input: 用户输入
        """
        # 发送用户输入响应
        response = AgentMessage(
            msg_type=MessageType.USER_INPUT_RECEIVED,
            sender="coordinator",
            receiver="*",  # 广播
            payload={"input": user_input},
            reply_to=request_id
        )
        await self.message_bus.publish(response)
        logger.info(f"User input submitted for request {request_id}")
    
    def _setup_agent_callbacks(self):
        """为所有Agent设置回调处理器"""
        async def agent_callback(data: Dict[str, Any]) -> Optional[Any]:
            if self.progress_callback:
                await self.progress_callback(data)
            return None
        
        for agent in [
            self.worldbuilder,
            self.outliner,
            self.chapter_writer,
            self.polisher,
            self.evaluator,
            self.character_builder,
            self.context_strategy,
            self.content_reader,
            self.content_expansion,
            self.file_naming,
            self.summary_orchestrator,
        ]:
            agent.set_callback_handler(agent_callback)
    
    def _load_checkpoint(self):
        """加载检查点"""
        data = self.checkpoint_manager.load_payload()
        if isinstance(data, dict) and data:
            try:
                self.checkpoint = WorkflowCheckpoint.from_dict(data)
                self.workflow_state = self.checkpoint.state
                logger.info(f"Checkpoint loaded: state={self.checkpoint.state.value}, chapter={self.checkpoint.current_chapter}")
            except Exception as e:
                logger.warning(f"Failed to hydrate checkpoint: {e}")
    
    def _save_checkpoint(self):
        """保存检查点"""
        if not self.checkpoint:
            return
        saved = self.checkpoint_manager.save_payload(
            self.checkpoint.to_dict(),
            enabled=self.auto_save_checkpoint,
        )
        if saved:
            logger.debug(f"Checkpoint saved: state={self.checkpoint.state.value}")
    
    def _update_checkpoint(
        self,
        state: Optional[WorkflowState] = None,
        current_chapter: Optional[int] = None,
        add_stage: Optional[str] = None,
        error_info: Optional[str] = None
    ):
        """更新检查点"""
        payload = self.checkpoint_manager.build_updated_payload(
            self.checkpoint.to_dict() if self.checkpoint else None,
            state_value=state.value if state else None,
            current_chapter=current_chapter,
            add_stage=add_stage,
            error_info=error_info,
            project_data=asdict(self.project) if self.project else {},
        )
        self.checkpoint = WorkflowCheckpoint.from_dict(payload)
        self.workflow_state = self.checkpoint.state
        if state and state != WorkflowState.PAUSED:
            self._last_active_workflow_state = state
        self._save_checkpoint()
    
    async def _notify_progress(self, data: Dict[str, Any]):
        """通知进度"""
        if self.progress_callback:
            try:
                await self.progress_callback(data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _build_memory_contract(self) -> Dict[str, Any]:
        """定义记忆权威源与冲突合并规则（版本化）"""
        return self.memory_sync_manager.build_contract()

    def _memory_meta_file(self) -> Path:
        return self.memory_sync_manager.meta_file()

    def _memory_snapshot_file(self) -> Path:
        return self.memory_sync_manager.snapshot_file()

    async def _append_memory_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """记录记忆同步事件到本地文件，便于排障与审计"""
        await self.memory_sync_manager.append_event(event_type, data)

    async def _ensure_memory_agent(self, agent_type: str) -> Optional[str]:
        """确保指定类型的记忆Agent已创建"""
        return await self.memory_sync_manager.ensure_memory_agent(self._memory_agent_ids, agent_type)

    async def _sync_memory_for_agent(self, agent_type: str) -> None:
        """按Agent类型执行记忆同步"""
        await self.memory_sync_manager.sync_memory_for_agent(self._memory_agent_ids, agent_type)

    async def _sync_memory_stage(self, stage: str) -> None:
        """在关键阶段执行增量记忆同步"""
        await self.memory_sync_manager.sync_stage(self._memory_agent_ids, stage)

    async def _export_memory_snapshot(self, reason: str) -> None:
        """导出记忆快照到项目目录"""
        await self.memory_sync_manager.export_snapshot(self._memory_agent_ids, reason)
    
    def pause(self):
        """暂停工作流"""
        if self.workflow_state != WorkflowState.PAUSED:
            self._last_active_workflow_state = self.workflow_state
        self._paused = True
        self._update_checkpoint(state=WorkflowState.PAUSED)
        logger.info("Workflow paused")
    
    def resume(self):
        """恢复工作流"""
        self._paused = False
        self._cancelled = False
        resume_state = self._last_active_workflow_state
        if resume_state == WorkflowState.PAUSED:
            resume_state = WorkflowState.WRITING
        if self.workflow_state == WorkflowState.PAUSED or (
            self.checkpoint and self.checkpoint.state == WorkflowState.PAUSED
        ):
            self._update_checkpoint(state=resume_state)
            if self.project and resume_state == WorkflowState.WRITING:
                self.project.status = "writing"
                self.project.updated_at = datetime.now().isoformat()
        logger.info("Workflow resumed")
    
    def cancel(self):
        """取消工作流"""
        self._cancelled = True
        self._paused = False
        cancel_resume_state = self.workflow_state
        if cancel_resume_state == WorkflowState.PAUSED:
            cancel_resume_state = self._last_active_workflow_state
        if cancel_resume_state == WorkflowState.PAUSED:
            cancel_resume_state = WorkflowState.WRITING
        self._update_checkpoint(state=cancel_resume_state, error_info="cancel_requested")
        logger.info("Workflow cancelled")
    
    async def _check_pause_cancel(self) -> bool:
        """检查是否需要暂停或取消"""
        if self._cancelled:
            return True
        
        while self._paused:
            await asyncio.sleep(1)
            if self._cancelled:
                return True
        
        return False

    async def check_pause_cancel(self) -> bool:
        """公共暂停/取消检查接口。"""
        return await self._check_pause_cancel()

    def _persist_creation_contract(
        self,
        *,
        novel_type: str,
        theme: str,
        requirements: str,
        protagonist: str,
        plot_idea: str,
        volume_count: int,
        chapters_per_volume: int,
        session_context: Optional[Dict[str, Any]] = None,
        user_confirmed: bool = True,
        ai_autonomy_requested: bool = False,
    ) -> Dict[str, Any]:
        """保存当前项目的创作合同与任务图草案。"""
        session_context = dict(session_context or {})
        contract = build_default_creation_contract(
            novel_type=novel_type,
            theme=theme,
            requirements=requirements,
            protagonist=protagonist,
            plot_idea=plot_idea,
            volume_count=volume_count,
            chapters_per_volume=chapters_per_volume,
            ai_autonomy_requested=ai_autonomy_requested,
            source_session_id=str(session_context.get("session_id") or "").strip(),
            source_message=str(plot_idea or "").strip(),
            user_confirmed=user_confirmed,
        )

        conversation_history = session_context.get("conversation_history")
        collected_info = session_context.get("collected_info")
        discussion_lines: List[str] = []
        if isinstance(conversation_history, list):
            for item in conversation_history:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip().lower()
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                role_label = "用户" if role == "user" else "助手" if role == "assistant" else "系统"
                discussion_lines.append(f"{role_label}：{content}")

        if isinstance(collected_info, dict) and collected_info:
            contract.metadata["collected_info"] = dict(collected_info)

        discussion_context = "\n".join(discussion_lines).strip()
        if discussion_context:
            contract.scope["discussion_context"] = discussion_context[:6000]

        contract.metadata.update({
            "generated_by": "NovelCoordinator",
            "stage": "orchestrated_execution",
            "project_id": self.project_manager.current_project_id or "",
        })
        contract.task_graph = build_default_task_graph(contract)
        payload = contract.to_dict()

        self.project_manager.save_project_state("creation_contract", payload)
        self.project_manager.save_project_state("task_graph_draft", payload.get("task_graph", []))
        return payload

    def initialize_task_pool_from_contract(
        self,
        contract_payload: Dict[str, Any],
        approved: bool = True,
    ) -> Dict[str, Any]:
        """基于已确认合同初始化正式任务池与协作执行轨迹。"""
        if not isinstance(contract_payload, dict) or not contract_payload:
            raise ValueError("contract_payload 不能为空")

        contract = CreationContract.from_dict(contract_payload)
        contract.user_confirmed = bool(approved)
        contract.updated_at = datetime.now().isoformat()
        contract.metadata = dict(contract.metadata or {})
        contract.metadata["draft"] = not bool(approved)
        contract.metadata["confirmed_at"] = contract.updated_at if approved else ""

        task_pool = TaskPool()
        created_tasks: List[TaskDefinition] = []
        for task in contract.task_graph:
            if not isinstance(task, TaskDefinition):
                continue
            created_tasks.append(
                task_pool.create_task(
                    task_type=task.task_type,
                    title=task.title,
                    description=task.description,
                    inputs=dict(task.inputs or {}),
                    expected_outputs=list(task.expected_outputs or []),
                    candidate_agents=list(task.candidate_agents or []),
                    priority=int(task.priority or 0),
                    depends_on=list(task.depends_on or []),
                    review_required=bool(task.review_required),
                    metadata=dict(task.metadata or {}),
                )
            )

        self._hydrate_project_task_depends_on(created_tasks)

        task_pool.metadata.update({
            "contract_id": contract.contract_id,
            "source": "contract_confirmation",
            "approved": bool(approved),
            "supervised_mode": bool(self.supervised_mode),
            "fallback_to_orchestrated": bool(self.fallback_to_orchestrated),
            "initialized_at": contract.updated_at,
        })

        persisted_contract = contract.to_dict()
        return self.runtime_state_store.persist_contract_runtime(
            persisted_contract=persisted_contract,
            task_pool=task_pool,
            approved=bool(approved),
            supervised_mode=bool(self.supervised_mode),
            fallback_to_orchestrated=bool(self.fallback_to_orchestrated),
            initialized_at=contract.updated_at,
        )

    def _hydrate_project_task_depends_on(self, tasks: List[TaskDefinition]) -> None:
        """将合同语义依赖映射为正式任务池可执行的 depends_on。"""
        if not isinstance(tasks, list) or not tasks:
            return

        first_by_type: Dict[str, TaskDefinition] = {}
        write_chapter_by_number: Dict[int, TaskDefinition] = {}
        for task in tasks:
            if not isinstance(task, TaskDefinition):
                continue
            task_type = str(task.task_type or "").strip()
            if task_type and task_type not in first_by_type:
                first_by_type[task_type] = task
            if task_type == "write_chapter":
                try:
                    chapter_number = int((task.inputs or {}).get("chapter_number") or 0)
                except (TypeError, ValueError):
                    chapter_number = 0
                if chapter_number > 0:
                    write_chapter_by_number[chapter_number] = task

        dependency_map = {
            "world_ready": first_by_type.get("build_world"),
            "characters_ready": first_by_type.get("build_characters"),
            "outline_ready": first_by_type.get("build_outline"),
        }

        for task in tasks:
            if not isinstance(task, TaskDefinition):
                continue
            depends_on = list(task.depends_on or [])
            for dependency in task.dependencies or []:
                dependency_key = str(getattr(dependency, "dependency_key", "") or "").strip()
                mapped_task = dependency_map.get(dependency_key)
                if mapped_task is None:
                    continue
                if mapped_task.task_id not in depends_on:
                    depends_on.append(mapped_task.task_id)

            if str(task.task_type or "").strip() == "summary_orchestrate":
                try:
                    end_chapter = int((task.inputs or {}).get("end_chapter") or 0)
                except (TypeError, ValueError):
                    end_chapter = 0
                end_chapter_task = write_chapter_by_number.get(end_chapter)
                if end_chapter_task is not None and end_chapter_task.task_id not in depends_on:
                    depends_on.append(end_chapter_task.task_id)

            task.depends_on = depends_on
            task.touch()

    def _load_project_outline_rows(self) -> List[Dict[str, Any]]:
        """加载项目级大纲行。"""
        outline_rows = self.project_manager.load_project_data("outline")
        if not isinstance(outline_rows, list):
            return []
        return [row for row in outline_rows if isinstance(row, dict)]

    @staticmethod
    def _normalize_chapter_number(value: Any, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        return number if number > 0 else default

    @staticmethod
    def _is_global_outline_overview_row(row: Dict[str, Any]) -> bool:
        title = str(row.get("title") or row.get("name") or "").strip()
        return (
            title == "主线大纲"
            or bool(row.get("global_outline"))
            or bool(row.get("volume_plan"))
            or bool(row.get("volumes"))
        )

    @classmethod
    def _sort_chapter_rows(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        indexed_rows: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            copied = dict(row)
            copied["chapter_number"] = cls._normalize_chapter_number(
                copied.get("chapter_number") or copied.get("chapter") or copied.get("number"),
                index,
            )
            indexed_rows.append(copied)
        return sorted(indexed_rows, key=lambda item: int(item.get("chapter_number") or 0))

    def _chapter_rows_with_slot(
        self,
        rows: List[Dict[str, Any]],
        chapter_number: int,
        timestamp: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        by_number: Dict[int, Dict[str, Any]] = {}
        for row in self._sort_chapter_rows([row for row in rows if isinstance(row, dict)]):
            number = self._normalize_chapter_number(row.get("chapter_number"), len(by_number) + 1)
            if number not in by_number:
                by_number[number] = row
                continue
            existing = by_number[number]
            if not str(existing.get("content") or "").strip() and str(row.get("content") or "").strip():
                by_number[number] = row

        for number in range(1, max(1, int(chapter_number or 1)) + 1):
            by_number.setdefault(
                number,
                {
                    "chapter_number": number,
                    "title": f"第{number}章",
                    "summary": "",
                    "content": "",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )

        ordered_rows = [by_number[number] for number in sorted(by_number)]
        return ordered_rows, by_number[max(1, int(chapter_number or 1))]

    def _chapter_rows_from_settings(self, settings_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(settings_rows, start=1):
            if not isinstance(row, dict):
                continue
            chapter_number = self._normalize_chapter_number(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            title = str(row.get("name") or row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
            rows.append(
                {
                    "chapter_number": chapter_number,
                    "title": title,
                    "summary": str(
                        row.get("description")
                        or row.get("chapter_goal")
                        or row.get("key_event")
                        or ""
                    ).strip(),
                    "content": "",
                    "chapter_goal": row.get("chapter_goal", ""),
                    "key_event": row.get("key_event", ""),
                    "ending_hook": row.get("ending_hook", ""),
                    "plot_thread": row.get("plot_thread"),
                    "source": "chapter_settings",
                }
            )
        return self._sort_chapter_rows(rows)

    def _load_project_chapter_rows(self) -> List[Dict[str, Any]]:
        """Load executable chapter rows, preferring chapters and then chapter settings."""
        chapter_rows = self.project_manager.load_project_data("chapters")
        if isinstance(chapter_rows, list) and any(isinstance(row, dict) for row in chapter_rows):
            return self._sort_chapter_rows([row for row in chapter_rows if isinstance(row, dict)])

        chapter_settings = self.project_manager.load_project_data("chapter_settings")
        if isinstance(chapter_settings, list) and any(isinstance(row, dict) for row in chapter_settings):
            return self._chapter_rows_from_settings([row for row in chapter_settings if isinstance(row, dict)])

        outline_rows = self._load_project_outline_rows()
        legacy_rows = extract_outline_chapter_rows(outline_rows)
        return self._sort_chapter_rows(legacy_rows)

    def _load_project_previous_chapters(self, chapter_number: int, outline_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为项目级章节任务收集前序章节内容。"""
        previous_chapters: List[Dict[str, Any]] = []
        for row in self._sort_chapter_rows([row for row in outline_rows if isinstance(row, dict)]):
            row_number = int(row.get("chapter_number") or 0)
            if row_number >= max(1, int(chapter_number or 1)):
                continue
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            title = str(row.get("title") or f"第{row_number}章").strip() or f"第{row_number}章"
            previous_chapters.append({
                "number": row_number,
                "chapter_number": row_number,
                "title": title,
                "chapter_title": title,
                "content": content,
            })
        return previous_chapters

    def _find_project_row_by_chapter(self, data_type: str, chapter_number: int) -> Dict[str, Any]:
        rows = self.project_manager.load_project_data(data_type)
        if not isinstance(rows, list):
            return {}
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            row_number = self._normalize_chapter_number(
                row.get("chapter_number") or row.get("chapter") or row.get("number"),
                index,
            )
            if row_number == chapter_number:
                return dict(row)
        return {}

    @staticmethod
    def _format_project_row_for_prompt(label: str, row: Dict[str, Any]) -> str:
        if not isinstance(row, dict) or not row:
            return ""
        visible_fields = [
            ("名称", row.get("name") or row.get("title")),
            ("说明", row.get("description")),
            ("章节目标", row.get("chapter_goal")),
            ("场景目标", row.get("scene_goal")),
            ("关键事件", row.get("key_event") or row.get("event")),
            ("冲突", row.get("conflict")),
            ("章末钩子", row.get("ending_hook") or row.get("hook")),
            ("备注", row.get("notes")),
        ]
        lines = [f"【{label}】"]
        for field_label, value in visible_fields:
            text = str(value or "").strip()
            if text:
                lines.append(f"- {field_label}：{text}")
        return "\n".join(lines).strip() if len(lines) > 1 else ""

    def _get_chapter_planning_context(self, chapter_number: int) -> Dict[str, Any]:
        chapter_setting = self._find_project_row_by_chapter("chapter_settings", chapter_number)
        detail_setting = self._find_project_row_by_chapter("detail_settings", chapter_number)
        blocks = [
            self._format_project_row_for_prompt("章纲设定", chapter_setting),
            self._format_project_row_for_prompt("细纲设定", detail_setting),
        ]
        return {
            "chapter_setting": chapter_setting,
            "detail_setting": detail_setting,
            "prompt": "\n\n".join(block for block in blocks if block).strip(),
            "plot_thread": chapter_setting.get("plot_thread") if isinstance(chapter_setting.get("plot_thread"), dict) else {},
        }

    async def _persist_project_ready_chapter_result(
        self,
        chapter_result: Dict[str, Any],
        outline_rows: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """将项目级 ready-task 产出的章节结果写回项目数据。"""
        outline_path = self.project_manager.get_project_data_path("outline")
        outline_existed_before = outline_path.exists()
        chapters_path = self.project_manager.get_project_data_path("chapters")
        chapters_existed_before = chapters_path.exists()
        chapter_number = int(
            chapter_result.get("chapter_number")
            or chapter_result.get("number")
            or 1
        )
        chapter_title = str(
            chapter_result.get("chapter_title")
            or chapter_result.get("title")
            or f"第{chapter_number}章"
        ).strip() or f"第{chapter_number}章"
        chapter_content = strip_internal_author_markers(chapter_result.get("content"))
        timestamp = datetime.now().isoformat()

        chapter_rows = self.project_manager.load_project_data("chapters")
        if not isinstance(chapter_rows, list) or not any(isinstance(row, dict) for row in chapter_rows):
            chapter_rows = [
                dict(row) for row in outline_rows
                if isinstance(row, dict) and not self._is_global_outline_overview_row(row)
            ]
        chapter_rows, row = self._chapter_rows_with_slot(chapter_rows, chapter_number, timestamp)
        row["chapter_number"] = chapter_number
        row["title"] = chapter_title
        row["content"] = chapter_content
        row["updated_at"] = timestamp

        self.project_manager.save_project_data("chapters", chapter_rows)

        legacy_outline_rows = self._load_project_outline_rows()
        if legacy_outline_rows and not all(
            self._is_global_outline_overview_row(row) for row in legacy_outline_rows if isinstance(row, dict)
        ):
            legacy_rows, legacy_row = self._chapter_rows_with_slot(legacy_outline_rows, chapter_number, timestamp)
            legacy_row["chapter_number"] = chapter_number
            legacy_row["title"] = chapter_title
            legacy_row["content"] = chapter_content
            legacy_row["updated_at"] = timestamp
            self.project_manager.save_project_data("outline", legacy_rows)
            self._sync_outline_to_library(legacy_rows)

        chapters_dir = self.project_manager.get_chapters_dir()
        suggested_filename = str(chapter_result.get("suggested_filename") or "").strip()
        if suggested_filename:
            safe_filename = re.sub(r'[\\/:*?"<>|]+', "_", suggested_filename).strip()
            if not safe_filename.lower().endswith(".md"):
                safe_filename = f"{safe_filename}.md"
            chapter_file = chapters_dir / safe_filename
        else:
            safe_title = re.sub(r'[\\/:*?"<>|]+', "_", chapter_title).strip() or f"chapter_{chapter_number}"
            safe_title = re.sub(r"\s+", "_", safe_title).strip("._") or f"chapter_{chapter_number}"
            chapter_file = chapters_dir / f"{chapter_number:03d}_{safe_title[:48]}.md"

        chapter_existed_before = chapter_file.exists()
        old_content = chapter_file.read_text(encoding="utf-8") if chapter_file.exists() else None
        atomic_write_text(chapter_file, chapter_content, old_content=old_content)

        # 自动生成章节摘要（问题1修复：使用 await 替代 asyncio.run）
        try:
            from ..chapter_summary_service import (
                get_auto_summary_enabled,
                generate_chapter_summary,
                save_chapter_summary_to_library,
            )
            if get_auto_summary_enabled(self.project_manager.current_project_id):
                summary = await generate_chapter_summary(
                    chapter_number=chapter_number,
                    title=chapter_title,
                    content=chapter_content,
                )
                save_chapter_summary_to_library(chapter_number, summary)
        except Exception as e:
            logger.warning(f"[Coordinator] Auto chapter summary failed: {e}")

        return {
            "outline_path": str(outline_path),
            "outline_status": "updated" if outline_existed_before else "created",
            "chapters_path": str(chapters_path),
            "chapters_status": "updated" if chapters_existed_before else "created",
            "chapter_path": str(chapter_file),
            "chapter_status": "updated" if chapter_existed_before else "created",
        }

    def _load_project_stage_summary_chapters(
        self,
        start_chapter: int,
        end_chapter: int,
        outline_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """加载项目级阶段总结所需章节内容。"""
        chapter_items: List[Dict[str, Any]] = []
        normalized_start = max(1, int(start_chapter or 1))
        normalized_end = max(normalized_start, int(end_chapter or normalized_start))

        rows_by_number = {
            int(row.get("chapter_number") or 0): row
            for row in self._sort_chapter_rows([row for row in outline_rows if isinstance(row, dict)])
        }
        for chapter_number in range(normalized_start, normalized_end + 1):
            row = rows_by_number.get(chapter_number)
            if not isinstance(row, dict):
                continue
            content = str(row.get("content") or "").strip()
            title = str(row.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
            summary = str(row.get("summary") or "").strip()
            if not content and not summary:
                continue
            chapter_items.append({
                "chapter_number": chapter_number,
                "number": chapter_number,
                "title": title,
                "chapter_title": title,
                "content": content,
                "summary": summary,
            })

        return chapter_items

    def _persist_project_stage_summary_result(
        self,
        summary_result: Dict[str, Any],
    ) -> Dict[str, str]:
        """将项目级阶段总结结果写回项目状态与文件。"""
        summary_payload = dict(summary_result.get("summary_payload") or {})
        summary_text = str(summary_result.get("summary") or summary_payload.get("summary") or "").strip()
        return self.runtime_state_store.persist_stage_summary(summary_payload, summary_text)

    def _init_project_ready_executor(self) -> 'ProjectReadyTaskExecutor':
        from .project_ready import ProjectReadyTaskExecutor
        if self._project_ready_executor is None:
            self._project_ready_executor = ProjectReadyTaskExecutor(coordinator=self)
        return self._project_ready_executor

    async def _execute_project_ready_batch(
        self,
        *,
        max_tasks: int = 2,
        max_chapter_tasks: Optional[int] = 1,
    ) -> Dict[str, Any]:
        """Execute next batch of project-ready tasks."""
        executor = self._init_project_ready_executor()
        return await executor.execute_next_batch(
            max_tasks=max_tasks,
            max_chapter_tasks=max_chapter_tasks,
        )

    async def execute_project_ready_tasks(
        self,
        *,
        max_tasks: int = 2,
        max_chapter_tasks: Optional[int] = 1,
    ) -> Dict[str, Any]:
        """Execute project-ready tasks. Delegates to ProjectReadyTaskExecutor."""
        executor = self._init_project_ready_executor()
        return await executor.execute_next_batch(
            max_tasks=max_tasks,
            max_chapter_tasks=max_chapter_tasks,
        )

    def _load_runtime_task_pool(self) -> TaskPool:
        """加载项目级运行态任务池；若不存在则返回空任务池。"""
        return self.runtime_state_store.load_runtime_task_pool()

    def _save_runtime_task_pool(self, task_pool: TaskPool) -> Dict[str, Any]:
        """持久化项目级运行态任务池。"""
        return self.runtime_state_store.save_runtime_task_pool(task_pool)

    def _append_collab_execution_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """追加协作执行轨迹事件并落盘。"""
        return self.runtime_state_store.append_execution_event(
            event_type,
            payload,
            supervised_mode=bool(self.supervised_mode),
            fallback_to_orchestrated=bool(self.fallback_to_orchestrated),
        )

    def _upsert_runtime_task(
        self,
        *,
        task_type: str,
        title: str,
        description: str,
        input_data: Dict[str, Any],
        expected_outputs: Optional[List[str]],
        candidate_agents: List[str],
        review_required: bool,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[TaskPool, TaskDefinition]:
        """将单次自治任务映射到项目级运行态任务池。"""
        return self.runtime_state_store.upsert_runtime_task(
            task_type=task_type,
            title=title,
            description=description,
            input_data=input_data,
            expected_outputs=expected_outputs,
            candidate_agents=candidate_agents,
            review_required=review_required,
            task_metadata=task_metadata,
        )

    def _build_chapter_autonomous_task_pool(
        self,
        *,
        chapter_num: int,
        chapter_title: str,
        chapter_outline_text: str,
        base_context: Dict[str, Any],
    ) -> TaskPool:
        """Build chapter-level autonomous task pool. Delegates to dispatcher."""
        return self.agent_dispatcher.build_chapter_task_pool(
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            chapter_outline_text=chapter_outline_text,
            base_context=base_context,
        )

    async def _execute_chapter_task_market(
        self,
        *,
        chapter_num: int,
        task_pool: TaskPool,
        base_context: Dict[str, Any],
        fallback_agents: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute chapter task market loop. Delegates to dispatcher."""
        return await self.agent_dispatcher.execute_chapter_task_market_loop(
            chapter_num=chapter_num,
            task_pool=task_pool,
            base_context=base_context,
            fallback_agents=fallback_agents,
        )

    async def _stage_worldbuilding(
        self,
        *,
        novel_type: str,
        effective_theme: str,
        effective_requirements: str,
        effective_protagonist: str,
        effective_plot_idea: str,
        effective_volume_count: int,
        effective_chapters_per_volume: int,
        session_id: str,
        collected_info: Dict[str, Any],
        conversation_history: List[Any],
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        """
        执行世界观构建阶段。
        Returns: (progress_events, world_data, creation_context)
        """
        progress: list[Dict[str, Any]] = []

        if await self._check_pause_cancel():
            progress.append({"stage": "cancelled", "message": "创作已取消"})
            return progress, {}, {}

        self._update_checkpoint(state=WorkflowState.WORLDBUILDING)
        progress.append({"stage": "worldbuilding", "message": "正在构建世界观...", "progress": 5})

        creation_context = {
            "project_dir": str(self.project_dir),
            "session_id": session_id,
            "collected_info": collected_info,
            "conversation_history": conversation_history,
            "creation_requirements": {
                "novel_type": novel_type,
                "theme": effective_theme,
                "requirements": effective_requirements,
                "protagonist": effective_protagonist,
                "plot_idea": effective_plot_idea,
                "volume_count": effective_volume_count,
                "chapters_per_volume": effective_chapters_per_volume,
            },
        }

        world_run_result = await self._run_autonomous_task(
            task_type="build_world",
            input_data={
                "novel_type": novel_type,
                "theme": effective_theme,
                "requirements": effective_requirements,
                "protagonist": effective_protagonist,
                "plot_idea": effective_plot_idea,
            },
            context=creation_context,
            fallback_agent=self.worldbuilder,
            stage="creation_mainline",
            title="构建世界观",
            description="为长篇创作主流程生成世界观设定",
            expected_outputs=["world"],
        )
        world_result = world_run_result.get("result", {}) if isinstance(world_run_result, dict) else {}
        world_data = world_result.get("world", {})

        self.context_manager.save("world", world_data, "world")
        if isinstance(world_data, dict):
            from ..context.world_manager import WorldSetting
            from ..worldbuilding_persistence import persist_worldbuilding_project_data

            world_setting = WorldSetting(
                name=world_data.get("world_name", "未命名世界"),
                world_type=novel_type,
                power_system=world_data.get("power_system", {}),
                geography=world_data.get("geography", {}),
                factions=world_data.get("factions", []),
                rules=world_data.get("rules", []),
                culture=world_data.get("culture", {}),
            )
            self.world_manager.set_world(world_setting)
            persist_worldbuilding_project_data({"world": world_data})

        self._update_checkpoint(add_stage="worldbuilding")
        await self._sync_memory_stage("worldbuilding")
        progress.append({
            "stage": "worldbuilding",
            "message": "世界观构建完成",
            "progress": 15,
            "data": world_data,
        })

        return progress, world_data, creation_context

    async def _stage_character_building(
        self,
        *,
        world_data: Dict[str, Any],
        creation_context: Dict[str, Any],
        novel_type: str,
        effective_theme: str,
        effective_protagonist: str,
        effective_plot_idea: str,
    ) -> tuple[list[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        执行角色构建阶段。
        Returns: (progress_events, built_characters)
        """
        progress: list[Dict[str, Any]] = []
        progress.append({"stage": "character_building", "message": "正在构建角色档案...", "progress": 18})

        character_context = dict(creation_context)
        character_context["world"] = world_data
        character_run_result = await self._run_autonomous_task(
            task_type="build_characters",
            input_data={
                "novel_type": novel_type,
                "theme": effective_theme,
                "protagonist": effective_protagonist,
                "plot_idea": effective_plot_idea,
                "character_request": effective_protagonist or effective_plot_idea,
                "request_mode": "draft",
            },
            context=character_context,
            fallback_agent=self.character_builder,
            stage="creation_mainline",
            title="构建角色档案",
            description="基于世界观和核心设定生成角色档案草稿",
            expected_outputs=["characters"],
        )
        character_result = character_run_result.get("result", {}) if isinstance(character_run_result, dict) else {}
        built_characters = character_result.get("characters", []) if isinstance(character_result, dict) else []

        for raw_char in built_characters:
            if not isinstance(raw_char, dict):
                continue
            try:
                from ..context.character_manager import Character
                self.character_manager.add_character(Character(**raw_char))
            except Exception as exc:
                logger.warning(f"[Coordinator] 角色档案写入失败: {exc}")

        self.context_manager.save("characters", self.character_manager.export_for_llm(), "character")
        try:
            from ..project_data_recovery import persist_project_data

            persist_project_data("characters", self.character_manager.export_for_llm(), project_manager=self.project_manager)
        except Exception as exc:
            logger.warning(f"[Coordinator] 角色档案同步到项目资料库失败: {exc}")
        progress.append({
            "stage": "character_building",
            "message": f"角色档案构建完成，共 {len(self.character_manager.get_all_characters())} 个角色",
            "progress": 22,
            "data": self.character_manager.export_for_llm(),
        })

        return progress, built_characters

    async def _stage_outlining(
        self,
        *,
        world_data: Dict[str, Any],
        creation_context: Dict[str, Any],
        novel_type: str,
        effective_protagonist: str,
        effective_plot_idea: str,
        effective_volume_count: int,
        effective_chapters_per_volume: int,
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        """
        执行大纲规划阶段。
        Returns: (progress_events, outline_data)
        """
        progress: list[Dict[str, Any]] = []

        if await self._check_pause_cancel():
            progress.append({"stage": "cancelled", "message": "创作已取消"})
            return progress, {}

        self._update_checkpoint(state=WorkflowState.OUTLINING)
        progress.append({"stage": "outlining", "message": "正在规划故事大纲...", "progress": 20})

        outline_context = dict(creation_context)
        outline_context["world"] = world_data
        outline_context["characters"] = self.character_manager.export_for_llm()
        outline_run_result = await self._run_autonomous_task(
            task_type="build_outline",
            input_data={
                "world": world_data,
                "protagonist": effective_protagonist,
                "plot_idea": effective_plot_idea,
                "volume_count": effective_volume_count,
                "chapters_per_volume": effective_chapters_per_volume,
            },
            context=outline_context,
            fallback_agent=self.outliner,
            stage="creation_mainline",
            title="规划故事大纲",
            description="基于世界观和角色设定规划长篇大纲",
            expected_outputs=["outline"],
        )
        outline_result = outline_run_result.get("result", {}) if isinstance(outline_run_result, dict) else {}
        outline_data = normalize_outline_payload(outline_result.get("outline", {}))

        self.context_manager.save("outline", outline_data, "plot")
        outline_rows = self._outline_to_project_rows(outline_data)
        self._persist_outline_rows(outline_rows)
        self._sync_eventlines_from_outline(outline_data)

        if isinstance(outline_data, dict):
            self.project.title = outline_data.get("title", f"{novel_type}小说")

        self._update_checkpoint(add_stage="outlining")
        await self._sync_memory_stage("outlining")
        progress.append({
            "stage": "outlining",
            "message": "故事大纲规划完成",
            "progress": 30,
            "data": outline_data,
        })

        return progress, outline_data

    async def create_novel(
        self,
        novel_type: str,
        theme: str = "",
        requirements: str = "",
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 10,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        创建一部新小说(完整流程)
        采用流式输出，实时返回进度
        
        Args:
            novel_type: 小说类型
            theme: 主题
            requirements: 特殊要求
            protagonist: 主角设定
            plot_idea: 剧情构思
            volume_count: 卷数
            chapters_per_volume: 每卷章节数
            
        Yields:
            进度信息和生成结果
        """
        # 重置控制标志
        self._paused = False
        self._cancelled = False
        session_context = dict(session_context or {})
        conversation_history = session_context.get("conversation_history")
        if not isinstance(conversation_history, list):
            conversation_history = []
        collected_info = session_context.get("collected_info")
        if not isinstance(collected_info, dict):
            collected_info = {}
        session_id = str(session_context.get("session_id") or "").strip()
        effective_theme = str(collected_info.get("theme") or theme or "").strip()
        effective_requirements = str(collected_info.get("requirements") or requirements or "").strip()
        effective_protagonist = str(collected_info.get("protagonist") or protagonist or "").strip()
        effective_plot_idea = str(collected_info.get("plot_idea") or plot_idea or "").strip()
        effective_volume_count = volume_count
        try:
            if collected_info.get("volume_count"):
                effective_volume_count = max(1, int(collected_info.get("volume_count")))
        except (TypeError, ValueError):
            effective_volume_count = volume_count
        effective_chapters_per_volume = chapters_per_volume
        try:
            if collected_info.get("chapters_per_volume"):
                effective_chapters_per_volume = max(1, int(collected_info.get("chapters_per_volume")))
        except (TypeError, ValueError):
            effective_chapters_per_volume = chapters_per_volume

        # 确保消息总线启动
        await self._ensure_message_bus_started()
        
        # 让所有Agent订阅消息总线
        await self._subscribe_all_agents()
        
        # 使用 ProjectManager 创建新项目
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pm_project = self.project_manager.create_project(
            name=f"{novel_type}小说_{timestamp}",
            description=f"类型：{novel_type}，主题：{effective_theme or '未指定'}",
            novel_type=novel_type,
        )
        
        # 切换到新项目（这会同步所有管理器的目录）
        self.switch_to_project(pm_project.id)
        
        # 创建 NovelProject 对象
        self.project = NovelProject(
            id=pm_project.id,
            title="",  # 待生成
            novel_type=novel_type,
            status="planning",
            created_at=pm_project.created_at,
            updated_at=pm_project.updated_at,
            total_chapters=effective_volume_count * effective_chapters_per_volume
        )
        
        contract_payload = self._persist_creation_contract(
            novel_type=novel_type,
            theme=effective_theme,
            requirements=effective_requirements,
            protagonist=effective_protagonist,
            plot_idea=effective_plot_idea,
            volume_count=effective_volume_count,
            chapters_per_volume=effective_chapters_per_volume,
            session_context=session_context,
            user_confirmed=True,
            ai_autonomy_requested=bool(collected_info.get("ai_autonomy_requested", False)),
        )

        # 初始化检查点
        self._update_checkpoint(state=WorkflowState.IDLE, current_chapter=0)
        await self._sync_memory_stage("init")
        
        yield {
            "stage": "init",
            "message": f"开始创作小说...（项目ID: {pm_project.id}）",
            "progress": 0,
            "project_id": pm_project.id,
            "project_dir": str(self.project_dir),
            "creation_contract": contract_payload,
        }
        
        try:
            # === Stage 1: 世界观构建 ===
            world_progress, world_data, creation_context = await self._stage_worldbuilding(
                novel_type=novel_type,
                effective_theme=effective_theme,
                effective_requirements=effective_requirements,
                effective_protagonist=effective_protagonist,
                effective_plot_idea=effective_plot_idea,
                effective_volume_count=effective_volume_count,
                effective_chapters_per_volume=effective_chapters_per_volume,
                session_id=session_id,
                collected_info=collected_info,
                conversation_history=conversation_history,
            )
            for event in world_progress:
                yield event
            if world_progress and world_progress[0].get("stage") == "cancelled":
                return
            
            # === Stage 1.5: 角色构建 ===
            char_progress, built_characters = await self._stage_character_building(
                world_data=world_data,
                creation_context=creation_context,
                novel_type=novel_type,
                effective_theme=effective_theme,
                effective_protagonist=effective_protagonist,
                effective_plot_idea=effective_plot_idea,
            )
            for event in char_progress:
                yield event

            # === Stage 2: 大纲规划 ===
            outline_progress, outline_data = await self._stage_outlining(
                world_data=world_data,
                creation_context=creation_context,
                novel_type=novel_type,
                effective_protagonist=effective_protagonist,
                effective_plot_idea=effective_plot_idea,
                effective_volume_count=effective_volume_count,
                effective_chapters_per_volume=effective_chapters_per_volume,
            )
            for event in outline_progress:
                yield event
            if outline_progress and outline_progress[0].get("stage") == "cancelled":
                return
            
            # === Stage 3: 章节撰写 ===
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            self._update_checkpoint(state=WorkflowState.WRITING)
            self.project.status = "writing"
            
            chapters = self._extract_chapters(outline_data)
            total_chapters = len(chapters)
            self._sync_plot_thread_state_with_outline(
                outline_data=outline_data,
                total_chapters=total_chapters,
                reset=True,
            )
            
            yield {"stage": "writing", "message": f"开始撰写 {total_chapters} 个章节...", "progress": 35}
            
            written_chapters = []
            
            # 串行写作
            async for progress_data in self._write_chapters_serial(
                chapters, world_data, outline_data
            ):
                yield progress_data
                if progress_data.get("stage") == "cancelled":
                    return
                if progress_data.get("stage") == "chapter_complete":
                    written_chapters.append(progress_data.get("chapter"))
            
            await self._sync_memory_stage("writing")

            # === Stage 4: 完成 ===
            self._update_checkpoint(state=WorkflowState.COMPLETED)
            self.project.status = "completed"
            self.project.updated_at = datetime.now().isoformat()
            # 问题8修复：使用去空白字符统计中文字数
            self.project.word_count = sum(len(re.sub(r"\s+", "", ch.get("content", ""))) for ch in written_chapters)
            
            # 保存完整小说
            novel_file = self.project_dir / f"{self.project.title}.txt"
            self._save_novel(novel_file, written_chapters)
            await self._export_memory_snapshot("create_novel_completed")
            
            yield {
                "stage": "completed",
                "message": "小说创作完成！",
                "progress": 100,
                "project": self.project.to_dict(),
                "file_path": str(novel_file),
                "metrics": self.metrics.get_report()
            }
            
        except Exception as e:
            self._update_checkpoint(state=WorkflowState.FAILED, error_info=str(e))
            await self._export_memory_snapshot("create_novel_failed")
            logger.error(f"Novel creation failed: {e}")
            yield {
                "stage": "failed",
                "message": f"创作失败: {str(e)}",
                "error": str(e)
            }
            raise

    def _outline_to_project_rows(self, outline_data: Any) -> List[Dict[str, Any]]:
        timestamp = datetime.now().isoformat()
        chapter_rows = extract_outline_chapter_rows(outline_data, timestamp=timestamp)
        if chapter_rows:
            return chapter_rows
        overview = build_outline_overview_row(outline_data, timestamp=timestamp)
        return [overview] if overview else []

    def _persist_outline_rows(self, outline_rows: List[Dict[str, Any]]) -> Dict[str, str]:
        outline_path = self.project_manager.get_project_data_path("outline")
        existed_before = outline_path.exists()
        self.project_manager.save_project_data("outline", outline_rows)
        self._sync_outline_to_library(outline_rows)
        return {
            "outline_path": str(outline_path),
            "outline_status": "updated" if existed_before else "created",
        }

    async def _subscribe_all_agents(self):
        """让所有Agent订阅消息总线"""
        agents = [
            self.worldbuilder,
            self.outliner,
            self.chapter_writer,
            self.polisher,
            self.evaluator,
            self.character_builder,
            self.context_strategy,
            self.content_reader,
            self.content_expansion,
            self.file_naming,
            self.summary_orchestrator,
        ]
        
        for agent in agents:
            await agent.ensure_subscribed()
        
        logger.info("All agents subscribed to message bus")
    
    async def _write_chapters_serial(
        self,
        chapters: List[Dict],
        world_data: Dict,
        outline_data: Dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """串行写作章节"""
        total_chapters = len(chapters)
        written_chapters = []
        
        for i, chapter_outline in enumerate(chapters):
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            chapter_num = i + 1
            progress = 35 + int(50 * (i / total_chapters))
            
            self._update_checkpoint(current_chapter=chapter_num)
            
            yield {
                "stage": "writing",
                "message": f"正在撰写第 {chapter_num} 章...",
                "progress": progress,
                "current_chapter": chapter_num,
                "total_chapters": total_chapters
            }
            
            chapter_data = await self._write_single_chapter_internal(
                chapter_num, chapter_outline, written_chapters
            )
            
            written_chapters.append(chapter_data)
            self.project.completed_chapters = chapter_num
            
            yield {
                "stage": "chapter_complete",
                "message": f"第 {chapter_num} 章完成",
                "progress": progress,
                "chapter": chapter_data
            }
    
    async def _run_autonomous_task(
        self,
        *,
        task_type: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        fallback_agent: Any = None,
        stage: str = "",
        title: str = "",
        description: str = "",
        expected_outputs: Optional[List[str]] = None,
        review_required: bool = False,
    ) -> Dict[str, Any]:
        """Phase 1 unified execution entry: explicit routing + context contract + fallback."""
        return await self.agent_dispatcher.run_autonomous_task(
            task_type=task_type,
            input_data=input_data,
            context=context,
            fallback_agent=fallback_agent,
            stage=stage,
            title=title,
            description=description,
            expected_outputs=expected_outputs,
            review_required=review_required,
        )

    def _resolve_chapter_market_results(
        self,
        chapter_market_results: Dict[str, Any],
        chapter_num: int,
        chapter_title: str,
    ) -> Dict[str, Any]:
        """Parse chapter task market results. Pure function in collab_services."""
        from .collab_services import resolve_chapter_market_results as _resolve
        return _resolve(chapter_market_results, chapter_num, chapter_title)

    async def _write_single_chapter_internal(
        self,
        chapter_num: int,
        chapter_outline: Dict,
        previous_chapters: List[Dict]
    ) -> Dict[str, Any]:
        """写作单个章节的内部实现"""
        chapter_outline = dict(chapter_outline or {})
        planning_context = self._get_chapter_planning_context(chapter_num)
        if planning_context.get("plot_thread") and not isinstance(chapter_outline.get("plot_thread"), dict):
            chapter_outline["plot_thread"] = planning_context["plot_thread"]

        # 获取上下文
        context = await self.context_manager.get_optimized_context("ChapterWriter")
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        context["eventlines"] = self._get_eventline_context()
        context["project_dir"] = str(self.project_dir)
        context["chapter_setting"] = planning_context.get("chapter_setting", {})
        context["detail_setting"] = planning_context.get("detail_setting", {})
        context["chapter_planning"] = planning_context.get("prompt", "")
        try:
            contract_payload = self.project_manager.load_project_state("creation_contract", default={})
        except Exception:
            contract_payload = {}
        contract_scope = contract_payload.get("scope", {}) if isinstance(contract_payload, dict) else {}
        if isinstance(contract_scope, dict):
            discussion_context = str(contract_scope.get("discussion_context") or "").strip()
            if discussion_context:
                context["discussion_context"] = discussion_context
                context["recent_discussion"] = discussion_context

        if previous_chapters:
            context["previous_summary"] = self._summarize_chapter(
                previous_chapters[-1].get("content", "")
            )
        context["plot_thread"] = await self._plan_plot_thread_for_chapter(
            chapter_num=chapter_num,
            chapter_outline=chapter_outline,
        )

        chapter_title = chapter_outline.get("title", f"第{chapter_num}章")
        chapter_outline_text = chapter_outline.get("summary", str(chapter_outline))
        if planning_context.get("prompt"):
            chapter_outline_text = (
                f"{chapter_outline_text}\n\n"
                "【本章章纲/细纲约束】\n"
                f"{planning_context['prompt']}"
            ).strip()
        context["chapter_title"] = chapter_title
        context["chapter_outline"] = chapter_outline_text
        context["previous_chapters"] = list(previous_chapters or [])

        # 问题4修复：将辅助记忆注入移到章节任务市场执行之前
        aux_query = self._build_aux_memory_query(chapter_num, chapter_outline, context)
        aux_injection = self._get_aux_memory_injection_context(aux_query)
        context["aux_memory"] = {
            "enabled": aux_injection.get("enabled", False),
            "items": aux_injection.get("items", []),
            "prompt_preview": aux_injection.get("prompt_preview", ""),
            "count": aux_injection.get("count", 0),
            "mode": aux_injection.get("mode", "fast"),
        }

        chapter_task_market = self._build_chapter_autonomous_task_pool(
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            chapter_outline_text=chapter_outline_text,
            base_context=context,
        )
        chapter_market_result = await self._execute_chapter_task_market(
            chapter_num=chapter_num,
            task_pool=chapter_task_market,
            base_context=context,
            fallback_agents={
                "context_plan": self.context_strategy,
                "content_read": self.content_reader,
                "write_chapter": self.chapter_writer,
                "evaluate_chapter": self.evaluator,
                "polish_chapter": self.polisher,
                "expand_content": self.content_expansion,
                "summary_orchestrate": self.summary_orchestrator,
            },
        )
        chapter_market_results = chapter_market_result.get("results", {})
        # 问题2修复：使用 update 合并而非整体替换，避免丢失 world/characters/eventlines 等字段
        market_context = chapter_market_result.get("context")
        if isinstance(market_context, dict) and market_context:
            context.update(market_context)

        # 从章节任务市场结果中解析章节数据
        resolved = self._resolve_chapter_market_results(
            chapter_market_results=chapter_market_results,
            chapter_num=chapter_num,
            chapter_title=chapter_title,
        )
        raw_chapter_content = resolved["chapter_content"]
        evaluation = resolved["evaluation"]
        expanded_result = resolved["expanded_result"]
        summary_result = resolved["summary_result"]
        summary_payload = resolved["summary_payload"]
        reader_result = resolved["reader_result"]
        autonomy_trace = resolved["autonomy_trace"]

        plot_thread_result = await self._complete_plot_thread_for_chapter(
            chapter_num=chapter_num,
            chapter_outline=chapter_outline,
            chapter_content=raw_chapter_content,
            evaluation=evaluation,
        )
        chapter_content = strip_internal_author_markers(raw_chapter_content)

        file_naming_result = await self.file_naming.execute({
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "content": chapter_content,
        }, context=context)

        normalized_word_count = int(
            file_naming_result.get("word_count")
            or resolved["normalized_word_count"]
            or 0
        )

        # 保存章节
        chapter_data = {
            "number": chapter_num,
            "title": chapter_title,
            "content": chapter_content,
            "word_count": normalized_word_count,
            "evaluation": evaluation,
            "plot_thread": plot_thread_result,
            "suggested_filename": str(file_naming_result.get("filename") or ""),
            "context_strategy": context.get("context_strategy", {}),
            "content_reader_report": reader_result.get("report", []) if isinstance(reader_result, dict) else [],
            "expanded": bool(expanded_result.get("expanded", False)) if isinstance(expanded_result, dict) else False,
            "autonomy_trace": autonomy_trace,
        }
        if isinstance(summary_result, dict) and summary_result:
            chapter_data["stage_summary"] = str(summary_result.get("summary") or "")
        
        self.context_manager.save_chapter_result(
            chapter_num,
            chapter_content,
            self._summarize_chapter(chapter_content)
        )
        try:
            synced_development = self.character_manager.sync_development_from_text(
                chapter_content,
                chapter_number=chapter_num,
            )
            if synced_development:
                chapter_data["character_development_sync"] = synced_development
        except Exception as e:
            logger.warning(f"[Coordinator] Character development sync failed: {e}")

        # 自动生成章节摘要（问题1修复：使用 await 替代 asyncio.run）
        try:
            from ..chapter_summary_service import (
                get_auto_summary_enabled,
                generate_chapter_summary,
                save_chapter_summary_to_library,
            )
            if get_auto_summary_enabled(self.project_manager.current_project_id):
                summary = await generate_chapter_summary(
                    chapter_number=chapter_num,
                    title=chapter_title,
                    content=chapter_content,
                )
                save_chapter_summary_to_library(chapter_num, summary)
        except Exception as e:
            logger.warning(f"[Coordinator] Auto chapter summary failed: {e}")

        if isinstance(summary_payload, dict) and summary_payload:
            summary_persist_result = self.runtime_state_store.persist_stage_summary(
                summary_payload,
                chapter_data.get("stage_summary", ""),
            )
            chapter_data["stage_summary_file"] = str(summary_persist_result.get("summary_path") or "")

        return chapter_data
    
    async def resume_from_checkpoint(self) -> AsyncGenerator[Dict[str, Any], None]:
        """从检查点恢复创作"""
        if not self.checkpoint:
            yield {"stage": "error", "message": "没有找到检查点"}
            return
        
        state = self.checkpoint.state
        
        if state == WorkflowState.COMPLETED:
            yield {"stage": "info", "message": "项目已完成，无需恢复"}
            return
        
        if state == WorkflowState.FAILED:
            yield {"stage": "info", "message": "项目之前失败，需要重新开始"}
            return
        
        # 重置控制标志
        self._paused = False
        self._cancelled = False
        
        # 恢复项目信息（问题3修复：过滤多余字段避免 TypeError）
        if self.checkpoint.project_data:
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(NovelProject)}
            filtered_data = {k: v for k, v in self.checkpoint.project_data.items() if k in valid_fields}
            self.project = NovelProject(**filtered_data)

        await self._sync_memory_stage("resume")
        
        yield {
            "stage": "resume",
            "message": f"从检查点恢复: 状态={state.value}, 章节={self.checkpoint.current_chapter}",
            "checkpoint": self.checkpoint.to_dict()
        }
        
        try:
            # 根据状态恢复
            if state == WorkflowState.WRITING or state == WorkflowState.PAUSED:
                # 从写作阶段恢复
                start_chapter = self.checkpoint.current_chapter
                outline_data = self.context_manager.get("outline", {})
                world_data = self.context_manager.get("world", {})
                chapters = self._extract_chapters(outline_data)
                self._sync_plot_thread_state_with_outline(
                    outline_data=outline_data,
                    total_chapters=len(chapters),
                    reset=False,
                )
                
                if start_chapter > 0:
                    chapters = chapters[start_chapter:]
                
                if not chapters:
                    yield {"stage": "info", "message": "所有章节已完成"}
                    return
                
                yield {
                    "stage": "resume_writing",
                    "message": f"从第 {start_chapter + 1} 章继续撰写...",
                    "remaining_chapters": len(chapters)
                }
                
                self._update_checkpoint(state=WorkflowState.WRITING)
                self.project.status = "writing"
                
                written_chapters = []
                
                # 串行写作
                async for progress_data in self._write_chapters_serial(
                    chapters, world_data, outline_data
                ):
                    yield progress_data
                    if progress_data.get("stage") == "cancelled":
                        return
                    if progress_data.get("stage") == "chapter_complete":
                        written_chapters.append(progress_data.get("chapter"))
                
                # 完成
                await self._sync_memory_stage("writing")
                self._update_checkpoint(state=WorkflowState.COMPLETED)
                self.project.status = "completed"
                self.project.updated_at = datetime.now().isoformat()
                # 问题8修复：使用去空白字符统计中文字数
                self.project.word_count = sum(len(re.sub(r"\s+", "", ch.get("content", ""))) for ch in written_chapters)
                
                # 保存小说
                novel_file = self.project_dir / f"{self.project.title}.txt"
                self._save_novel(novel_file, written_chapters)
                await self._export_memory_snapshot("resume_completed")
                
                yield {
                    "stage": "completed",
                    "message": "小说创作完成！",
                    "progress": 100,
                    "project": self.project.to_dict(),
                    "file_path": str(novel_file),
                    "metrics": self.metrics.get_report()
                }
            
            elif state == WorkflowState.WORLDBUILDING:
                yield {"stage": "info", "message": "需要重新开始世界观构建"}
            
            elif state == WorkflowState.OUTLINING:
                yield {"stage": "info", "message": "需要重新开始大纲规划"}
                
        except Exception as e:
            self._update_checkpoint(state=WorkflowState.FAILED, error_info=str(e))
            await self._export_memory_snapshot("resume_failed")
            logger.error(f"Resume from checkpoint failed: {e}")
            yield {
                "stage": "failed",
                "message": f"恢复失败: {str(e)}",
                "error": str(e)
            }
            raise
    
    async def generate_world(self, novel_type: str, theme: str = "", requirements: str = "") -> Dict[str, Any]:
        """单独生成世界观"""
        result = await self.worldbuilder.execute({
            "novel_type": novel_type,
            "theme": theme,
            "requirements": requirements
        })

        world_data = result.get("world", {})
        missing_status = isinstance(world_data, dict) and str(world_data.get("status") or "").strip().lower() in {
            "missing_info",
            "needs_input",
            "needs_confirmation",
            "pending_confirmation",
        }
        has_missing_info = isinstance(world_data, dict) and bool(world_data.get("missing_info"))
        if not missing_status and not has_missing_info:
            self.context_manager.save("world", world_data, "world")
        if isinstance(world_data, dict) and world_data and not missing_status and not has_missing_info:
            from ..worldbuilding_persistence import persist_worldbuilding_project_data

            persist_worldbuilding_project_data({"world": world_data})

        return result
    
    async def generate_outline(
        self,
        world: Optional[Dict] = None,
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 10,
        characters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """单独生成大纲"""
        if world is None:
            world = self.context_manager.get("world", {})
        if characters is None:
            characters = self.character_manager.export_for_llm()
        
        result = await self.outliner.execute({
            "world": world,
            "characters": characters,
            "protagonist": protagonist,
            "plot_idea": plot_idea,
            "volume_count": volume_count,
            "chapters_per_volume": chapters_per_volume
        }, context={"world": world, "characters": characters})

        outline_data = normalize_outline_payload(result.get("outline", {}))
        result["outline"] = outline_data
        self.context_manager.save("outline", outline_data, "plot")
        outline_rows = self._outline_to_project_rows(outline_data)
        if outline_rows:
            self._persist_outline_rows(outline_rows)
        self._sync_eventlines_from_outline(outline_data)

        return result
    
    async def write_single_chapter(
        self,
        chapter_number: int,
        chapter_outline: str,
        chapter_title: str = "",
        enable_trends: bool = False,
        trends_platforms: Optional[List[str]] = None,
        trends_query: str = "",
    ) -> Dict[str, Any]:
        """撰写单个章节（走统一协作子Agent闭环）。"""
        outline_payload = {
            "title": chapter_title or f"第{chapter_number}章",
            "summary": chapter_outline,
        }

        previous_chapters: List[Dict[str, Any]] = []
        if chapter_number > 1:
            previous_summary = self.context_manager.get(f"chapter_{chapter_number - 1}_summary", "")
            if previous_summary:
                previous_chapters.append({
                    "number": chapter_number - 1,
                    "title": f"第{chapter_number - 1}章",
                    "content": previous_summary,
                })

        result = await self._write_single_chapter_internal(
            chapter_num=chapter_number,
            chapter_outline=outline_payload,
            previous_chapters=previous_chapters,
        )

        if enable_trends:
            trends_data = await self._search_trends_for_collab(trends_platforms, limit=5)
            if trends_data:
                logger.debug(
                    f"[Coordinator] 协作写章注入热点: count={len(trends_data)}, query={trends_query[:80]}"
                )
                result["trends_data"] = trends_data

        try:
            persist_result = await self._persist_project_ready_chapter_result(
                result,
                self._load_project_chapter_rows(),
            )
            result.update({
                "chapter_path": persist_result.get("chapter_path", ""),
                "outline_path": persist_result.get("outline_path", ""),
            })
        except Exception as exc:
            logger.warning(f"[Coordinator] 单章正文同步到项目资料库失败: {exc}")

        return result

    async def write_chapter_from_context(
        self,
        chapter_number: int,
        chapter_outline: Dict[str, Any],
        previous_chapters: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """公共章节写作接口，供外部在保留上下文时调用。"""
        return await self._write_single_chapter_internal(
            chapter_num=chapter_number,
            chapter_outline=chapter_outline,
            previous_chapters=previous_chapters,
        )

    def extract_outline_chapters(self, outline_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """公共大纲章节提取接口。"""
        return self._extract_chapters(outline_data)

    def save_compiled_novel(self, file_path: Path, chapters: List[Dict[str, Any]]) -> None:
        """公共合集保存接口。"""
        self._save_novel(file_path, chapters)
    
    async def continue_chapter(
        self,
        chapter_index: int,
        chapter_title: str,
        existing_content: str,
        target_words: int = WRITING_CONFIG.CONTINUE_DEFAULT_WORDS,
        enable_trends: bool = False,
        trends_platforms: Optional[List[str]] = None,
        trends_query: str = "",
    ) -> Dict[str, Any]:
        """AI续写章节内容"""
        context = self.context_manager.get_chapter_context(chapter_index + 1)
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        context["eventlines"] = self._get_eventline_context()
        context["existing_content"] = existing_content

        aux_query = f"{chapter_title or ''} {existing_content[-500:]} chapter:{chapter_index + 1}".strip()
        aux_injection = self._get_aux_memory_injection_context(aux_query)
        context["aux_memory"] = {
            "enabled": aux_injection.get("enabled", False),
            "items": aux_injection.get("items", []),
            "prompt_preview": aux_injection.get("prompt_preview", ""),
            "count": aux_injection.get("count", 0),
            "mode": aux_injection.get("mode", "fast"),
        }

        trends_data: List[Dict[str, Any]] = []
        if enable_trends:
            trends_data = await self._search_trends_for_collab(trends_platforms, limit=5)
            if trends_data:
                logger.debug(
                    f"[Coordinator] 协作续写注入热点: count={len(trends_data)}, query={trends_query[:80]}"
                )
        trends_prompt_block = self._build_trends_prompt_block(trends_data, limit=5)
        
        # 构建续写提示
        prompt = f"""你是一位专业的小说作家。请基于以下已有内容进行续写，保持风格一致，情节连贯。

章节标题：{chapter_title}

已有内容：
{existing_content}

世界设定摘要：
{context.get("world", "暂无世界设定")}

角色摘要：
{context.get("characters", "暂无角色")}

事件线摘要：
{context.get("eventlines", "暂无事件线")}

辅助记忆约束（低优先级）：
{context.get("aux_memory", {}).get("prompt_preview", "未启用辅助记忆或无匹配")}

{trends_prompt_block}

请续写约{target_words}字的内容，注意：
1. 保持与前文一致的叙事风格和人称
2. 自然衔接，不要重复已有内容
3. 推进情节发展，可以增加对话、动作、心理描写
4. 只输出续写的内容，不要包含任何说明文字"""
        
        try:
            result = await self.chapter_writer.call_llm([
                {"role": "system", "content": "你是一位专业的小说作家，擅长各类题材的创作。"},
                {"role": "user", "content": prompt}
            ])
            
            return {
                "success": True,
                "content": result,
                "action": "continue"
            }
        except Exception as e:
            logger.error(f"Chapter continuation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": ""
            }

    def _get_eventline_context(self, limit: int = 3) -> str:
        rows = self.project_manager.load_project_data("eventlines")
        if not isinstance(rows, list) or not rows:
            return "暂无事件线"

        lines = ["【事件线】"]
        count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "未命名事件线").strip() or "未命名事件线"
            conflict = str(row.get("conflict") or row.get("description") or "").strip()
            status = str(row.get("status") or "").strip()
            summary = "｜".join(part for part in [conflict, status] if part)
            lines.append(f"- {name}" + (f"：{summary}" if summary else ""))
            count += 1
            if count >= limit:
                break
        return "\n".join(lines) if count else "暂无事件线"
    
    async def polish_content(
        self,
        content: str,
        chapter_title: str = ""
    ) -> Dict[str, Any]:
        """AI润色内容"""
        prompt = f"""你是一位专业的文字编辑。请对以下小说内容进行润色和优化。

{f'章节标题：{chapter_title}' if chapter_title else ''}

原文内容：
{content}

请进行以下优化：
1. 优化语言表达，使文字更加流畅优美
2. 丰富细节描写（环境、动作、表情等）
3. 增强情感表达和氛围感
4. 修正语法错误和不通顺的句子
5. 保持原文的核心情节和人物特征不变

请直接输出润色后的完整内容，不要包含任何说明文字。"""
        
        try:
            result = await self.polisher.call_llm([
                {"role": "system", "content": "你是一位专业的文字编辑，擅长润色和优化小说文本。"},
                {"role": "user", "content": prompt}
            ])
            
            return {
                "success": True,
                "content": result,
                "action": "polish"
            }
        except Exception as e:
            logger.error(f"Content polishing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": ""
            }
    
    def _extract_chapters(self, outline_data: Dict) -> List[Dict]:
        """从大纲中提取章节列表"""
        chapters = []
        outline_data = normalize_outline_payload(outline_data)
        
        if isinstance(outline_data, dict):
            # 尝试从volumes中提取
            volumes = outline_data.get("volumes", [])
            for volume in volumes:
                if isinstance(volume, dict):
                    vol_chapters = volume.get("chapters", [])
                    chapters.extend(vol_chapters)
            
            # 如果没有volumes，尝试直接获取chapters
            if not chapters:
                chapters = outline_data.get("chapters", [])
        
        # 如果还是空的，创建默认章节
        if not chapters:
            chapters = [{"title": f"第{i+1}章", "summary": "待生成"} for i in range(10)]
        
        return chapters
    
    def _summarize_chapter(self, content: str, max_length: int = WRITING_CONFIG.SUMMARY_MAX_LENGTH) -> str:
        """章节摘要（问题5修复：提取关键情节而非纯截断）"""
        if not content or not content.strip():
            return ""
        # 去除空白后统计实际字数
        clean = re.sub(r"\s+", "", content)
        if len(clean) <= max_length:
            return content.strip()
        # 按段落分割，优先保留对话和关键段落
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        summary_parts: List[str] = []
        current_len = 0
        for para in paragraphs:
            para_clean_len = len(re.sub(r"\s+", "", para))
            if current_len + para_clean_len > max_length:
                # 最后一段如果太长，截取到目标长度
                remaining = max_length - current_len
                if remaining > 20:
                    summary_parts.append(para[:remaining])
                break
            summary_parts.append(para)
            current_len += para_clean_len
        return "\n".join(summary_parts) if summary_parts else clean[:max_length]
    
    def _save_novel(self, file_path: Path, chapters: List[Dict]) -> None:
        """保存小说到文件"""
        content_parts = []
        
        if self.project:
            content_parts.append(f"《{self.project.title}》\n")
            content_parts.append(f"类型：{self.project.novel_type}\n")
            content_parts.append("=" * 50 + "\n\n")
        
        for i, chapter in enumerate(chapters):
            # 使用.get()避免KeyError，提供默认值
            chapter_title = chapter.get('title', f'第{i+1}章')
            chapter_content = chapter.get('content', '')
            content_parts.append(f"\n{chapter_title}\n\n")
            content_parts.append(chapter_content)
            content_parts.append("\n\n" + "-" * 30 + "\n")
        
        old_content = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        atomic_write_text(file_path, "".join(content_parts), old_content=old_content)
        logger.info(f"Novel saved to: {file_path}")
    
    def get_candidate_agents_for_task(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查询指定任务的候选 Agent 列表。"""
        return self.collab_agent_registry.find_candidates(task)

    def get_route_targets(self) -> Dict[str, Any]:
        """Return the unified route target snapshot used by router, dispatcher, and UI."""
        registry = build_default_route_target_registry()
        if hasattr(self.capability_registry, "list_route_targets"):
            registry.register_many(self.capability_registry.list_route_targets())
        if hasattr(self.collab_agent_registry, "list_route_targets"):
            registry.register_many(self.collab_agent_registry.list_route_targets())
        return registry.to_dict()

    def _resolve_runtime_model_label(self) -> str:
        """解析当前运行态可见模型名称，用于前端实时状态显示。"""
        try:
            task_pool = self.project_manager.load_project_state("task_pool", default={})
            tasks = task_pool.get("tasks", []) if isinstance(task_pool, dict) else []
            active_task = next(
                (
                    task for task in tasks
                    if isinstance(task, dict)
                    and str(task.get("status") or "").strip().lower() in {"running", "claimed", "blocked"}
                ),
                None,
            )
            metadata = active_task.get("metadata", {}) if isinstance(active_task, dict) else {}
            if isinstance(metadata, dict):
                for key in ("current_model", "model", "model_used", "active_model"):
                    value = str(metadata.get(key) or "").strip()
                    if value:
                        return value
            agent_name = str(
                (active_task or {}).get("assigned_agent")
                or (metadata or {}).get("selected_agent")
                or ""
            ).strip()
            if agent_name:
                from ..agent_config import get_config_manager
                cfg = get_config_manager().get_effective_config(agent_name)
                model_name = str(getattr(cfg, "model", "") or "").strip()
                if model_name:
                    return model_name
        except Exception as exc:
            logger.debug(f"[Coordinator] resolve runtime active model failed: {exc}")

        try:
            from ..agent_config import get_config_manager
            active_config = get_config_manager().multi_config.get_active_config()
            return str(getattr(active_config, "model", "") or "").strip()
        except Exception as exc:
            logger.debug(f"[Coordinator] resolve active model failed: {exc}")
            return ""

    def get_project_status(self) -> Dict[str, Any]:
        """获取项目状态"""
        workflow_state = self.workflow_state.value
        if self._cancelled:
            workflow_state = "cancelled"
        elif self._paused:
            workflow_state = WorkflowState.PAUSED.value
        model_label = self._resolve_runtime_model_label()
        return {
            "project": self.project.to_dict() if self.project else None,
            "workflow_state": workflow_state,
            "model": model_label,
            "current_model": model_label,
            "active_model": model_label,
            "model_used": model_label,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "world": self.world_manager.export_for_llm(),
            "characters": self.character_manager.export_for_llm(),
            "contexts": self.context_manager.export_all(),
            "plot_thread_state": self._plot_thread_machine.snapshot(),
            "metrics": self.metrics.get_report(),
            "context_stats": self.context_manager.get_stats(),
            "capability_registry": self.capability_registry.to_dict(),
            "collab_agent_registry": self.collab_agent_registry.to_dict(),
            "collab_service_registry": self.collab_service_registry.to_dict(),
        }
    
    def get_metrics_report(self) -> Dict[str, Any]:
        """获取详细的指标报告"""
        return {
            "summary": self.metrics.get_report(),
            "token_usage": self.metrics.get_token_usage_by_agent(),
            "performance": self.metrics.get_performance_summary(),
            "recent_errors": self.metrics.get_recent_errors()
        }

    def get_memory_diagnostics(self) -> Dict[str, Any]:
        """获取记忆契约与同步诊断信息"""
        return self.memory_sync_manager.diagnostics(self._memory_agent_ids)


# 模块职责说明：实现协调者-工作者多智能体协作模式，管理小说创作的完整工作流、检查点保存和串行章节写作。
