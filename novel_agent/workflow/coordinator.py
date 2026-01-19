"""
小说创作协调器
实现协调者-工作者多智能体协作模式

增强功能：
- 工作流状态管理 (WorkflowState)
- 检查点保存/恢复 (Checkpoint)
- 并行章节写作
- 回调处理器集成
- 指标收集
- 智能路由集成
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, AsyncGenerator, Callable, Awaitable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging

from ..agents import (
    WorldbuilderAgent,
    OutlinerAgent,
    ChapterWriterAgent,
    PolisherAgent,
    EvaluatorAgent
)
from ..agents.message_bus import (
    get_message_bus, MessageType, AgentMessage,
    create_user_input_request
)
from ..context import ContextManager, CharacterManager, WorldManager
from ..utils.metrics import get_metrics_collector
from ..constants import WRITING_CONFIG, TIMEOUTS

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
    - 并行章节写作
    - 回调处理器
    - 消息总线集成
    - 智能路由（自动意图识别）
    """
    
    def __init__(
        self,
        project_dir: Optional[Path] = None,
        progress_callback: Optional[ProgressCallback] = None,
        parallel_chapters: int = 1,
        auto_save_checkpoint: bool = True
    ):
        """
        初始化协调器
        
        Args:
            project_dir: 项目目录
            progress_callback: 进度回调函数
            parallel_chapters: 并行写作的章节数
            auto_save_checkpoint: 是否自动保存检查点
        """
        from ..constants import PATH_DEFAULTS
        self.project_dir = project_dir or Path(PATH_DEFAULTS.NOVEL_OUTPUT_DIR)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # 回调和并行配置
        self.progress_callback = progress_callback
        self.parallel_chapters = max(1, parallel_chapters)
        self.auto_save_checkpoint = auto_save_checkpoint
        
        # 初始化各专业Agent（传入回调处理器）
        self.worldbuilder = WorldbuilderAgent()
        self.outliner = OutlinerAgent()
        self.chapter_writer = ChapterWriterAgent()
        self.polisher = PolisherAgent()
        self.evaluator = EvaluatorAgent()
        
        # 为Agent设置回调处理器
        if progress_callback:
            self._setup_agent_callbacks()
        
        # 初始化上下文管理器
        self.context_manager = ContextManager(self.project_dir)
        self.character_manager = CharacterManager(self.project_dir)
        self.world_manager = WorldManager(self.project_dir)
        
        # 项目信息
        self.project: Optional[NovelProject] = None
        
        # 工作流状态
        self.workflow_state = WorkflowState.IDLE
        self.checkpoint: Optional[WorkflowCheckpoint] = None
        self._load_checkpoint()
        
        # 消息总线和指标
        self.message_bus = get_message_bus()
        self.metrics = get_metrics_collector()
        
        # 控制标志
        self._paused = False
        self._cancelled = False
        
        # 消息总线状态
        self._bus_started = False
        self._subscribed = False
        
        # 待处理的用户输入请求
        self._pending_user_inputs: Dict[str, asyncio.Future] = {}
        
        logger.info(f"NovelCoordinator initialized with project dir: {self.project_dir}")
    
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
        
        for agent in [self.worldbuilder, self.outliner, self.chapter_writer,
                      self.polisher, self.evaluator]:
            agent.set_callback_handler(agent_callback)
    
    def _load_checkpoint(self):
        """加载检查点"""
        checkpoint_file = self.project_dir / "checkpoint.json"
        if checkpoint_file.exists():
            try:
                data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                self.checkpoint = WorkflowCheckpoint.from_dict(data)
                self.workflow_state = self.checkpoint.state
                logger.info(f"Checkpoint loaded: state={self.checkpoint.state.value}, chapter={self.checkpoint.current_chapter}")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
    
    def _save_checkpoint(self):
        """保存检查点"""
        if not self.auto_save_checkpoint or not self.checkpoint:
            return
        
        try:
            checkpoint_file = self.project_dir / "checkpoint.json"
            checkpoint_file.write_text(
                json.dumps(self.checkpoint.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.debug(f"Checkpoint saved: state={self.checkpoint.state.value}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def _update_checkpoint(
        self,
        state: Optional[WorkflowState] = None,
        current_chapter: Optional[int] = None,
        add_stage: Optional[str] = None,
        error_info: Optional[str] = None
    ):
        """更新检查点"""
        if self.checkpoint is None:
            self.checkpoint = WorkflowCheckpoint(
                state=WorkflowState.IDLE,
                current_chapter=0,
                completed_stages=[],
                project_data=asdict(self.project) if self.project else {},
                last_updated=datetime.now().isoformat()
            )
        
        if state:
            self.checkpoint.state = state
            self.workflow_state = state
        if current_chapter is not None:
            self.checkpoint.current_chapter = current_chapter
        if add_stage and add_stage not in self.checkpoint.completed_stages:
            self.checkpoint.completed_stages.append(add_stage)
        if error_info:
            self.checkpoint.error_info = error_info
        
        self.checkpoint.last_updated = datetime.now().isoformat()
        self.checkpoint.project_data = asdict(self.project) if self.project else {}
        
        self._save_checkpoint()
    
    async def _notify_progress(self, data: Dict[str, Any]):
        """通知进度"""
        if self.progress_callback:
            try:
                await self.progress_callback(data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def pause(self):
        """暂停工作流"""
        self._paused = True
        self._update_checkpoint(state=WorkflowState.PAUSED)
        logger.info("Workflow paused")
    
    def resume(self):
        """恢复工作流"""
        self._paused = False
        logger.info("Workflow resumed")
    
    def cancel(self):
        """取消工作流"""
        self._cancelled = True
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
    
    async def create_novel(
        self,
        novel_type: str,
        theme: str = "",
        requirements: str = "",
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 10
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
        
        # 确保消息总线启动
        await self._ensure_message_bus_started()
        
        # 让所有Agent订阅消息总线
        await self._subscribe_all_agents()
        
        # 创建项目
        project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.project = NovelProject(
            id=project_id,
            title="",  # 待生成
            novel_type=novel_type,
            status="planning",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            total_chapters=volume_count * chapters_per_volume
        )
        
        # 初始化检查点
        self._update_checkpoint(state=WorkflowState.IDLE, current_chapter=0)
        
        yield {"stage": "init", "message": "开始创作小说...", "progress": 0}
        
        try:
            # === Stage 1: 世界观构建 ===
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            self._update_checkpoint(state=WorkflowState.WORLDBUILDING)
            yield {"stage": "worldbuilding", "message": "正在构建世界观...", "progress": 5}
            
            world_result = await self.worldbuilder.execute({
                "novel_type": novel_type,
                "theme": theme,
                "requirements": requirements
            })
            
            world_data = world_result.get("world", {})
            self.context_manager.save("world", world_data, "world")
            
            # 更新世界管理器
            if isinstance(world_data, dict):
                from ..context.world_manager import WorldSetting
                world_setting = WorldSetting(
                    name=world_data.get("world_name", "未命名世界"),
                    world_type=novel_type,
                    power_system=world_data.get("power_system", {}),
                    geography=world_data.get("geography", {}),
                    factions=world_data.get("factions", []),
                    rules=world_data.get("rules", []),
                    culture=world_data.get("culture", {})
                )
                self.world_manager.set_world(world_setting)
            
            self._update_checkpoint(add_stage="worldbuilding")
            yield {
                "stage": "worldbuilding",
                "message": "世界观构建完成",
                "progress": 15,
                "data": world_data
            }
            
            # === Stage 2: 大纲规划 ===
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            self._update_checkpoint(state=WorkflowState.OUTLINING)
            yield {"stage": "outlining", "message": "正在规划故事大纲...", "progress": 20}
            
            outline_result = await self.outliner.execute({
                "world": world_data,
                "protagonist": protagonist,
                "plot_idea": plot_idea,
                "volume_count": volume_count,
                "chapters_per_volume": chapters_per_volume
            }, context={"world": world_data})
            
            outline_data = outline_result.get("outline", {})
            self.context_manager.save("outline", outline_data, "plot")
            
            # 更新项目标题
            if isinstance(outline_data, dict):
                self.project.title = outline_data.get("title", f"{novel_type}小说")
            
            self._update_checkpoint(add_stage="outlining")
            yield {
                "stage": "outlining",
                "message": "故事大纲规划完成",
                "progress": 30,
                "data": outline_data
            }
            
            # === Stage 3: 章节撰写 ===
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            self._update_checkpoint(state=WorkflowState.WRITING)
            self.project.status = "writing"
            
            chapters = self._extract_chapters(outline_data)
            total_chapters = len(chapters)
            
            yield {"stage": "writing", "message": f"开始撰写 {total_chapters} 个章节...", "progress": 35}
            
            written_chapters = []
            
            # 根据并行配置决定写作方式
            if self.parallel_chapters > 1:
                # 并行写作
                async for progress_data in self._write_chapters_parallel(
                    chapters, world_data, outline_data
                ):
                    yield progress_data
                    if progress_data.get("stage") == "cancelled":
                        return
                    if progress_data.get("stage") == "chapter_complete":
                        written_chapters.append(progress_data.get("chapter"))
            else:
                # 串行写作
                async for progress_data in self._write_chapters_serial(
                    chapters, world_data, outline_data
                ):
                    yield progress_data
                    if progress_data.get("stage") == "cancelled":
                        return
                    if progress_data.get("stage") == "chapter_complete":
                        written_chapters.append(progress_data.get("chapter"))
            
            # === Stage 4: 完成 ===
            self._update_checkpoint(state=WorkflowState.COMPLETED)
            self.project.status = "completed"
            self.project.updated_at = datetime.now().isoformat()
            self.project.word_count = sum(len(ch.get("content", "")) for ch in written_chapters)
            
            # 保存完整小说
            novel_file = self.project_dir / f"{self.project.title}.txt"
            self._save_novel(novel_file, written_chapters)
            
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
            logger.error(f"Novel creation failed: {e}")
            yield {
                "stage": "failed",
                "message": f"创作失败: {str(e)}",
                "error": str(e)
            }
            raise
    
    async def _subscribe_all_agents(self):
        """让所有Agent订阅消息总线"""
        agents = [
            self.worldbuilder,
            self.outliner,
            self.chapter_writer,
            self.polisher,
            self.evaluator
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
    
    async def _write_chapters_parallel(
        self,
        chapters: List[Dict],
        world_data: Dict,
        outline_data: Dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """并行写作章节"""
        total_chapters = len(chapters)
        written_chapters: Dict[int, Dict] = {}
        
        # 分批处理
        for batch_start in range(0, total_chapters, self.parallel_chapters):
            if await self._check_pause_cancel():
                yield {"stage": "cancelled", "message": "创作已取消"}
                return
            
            batch_end = min(batch_start + self.parallel_chapters, total_chapters)
            batch = chapters[batch_start:batch_end]
            
            progress = 35 + int(50 * (batch_start / total_chapters))
            
            yield {
                "stage": "writing",
                "message": f"正在并行撰写第 {batch_start + 1}-{batch_end} 章...",
                "progress": progress,
                "current_chapter": batch_start + 1,
                "total_chapters": total_chapters
            }
            
            # 并行执行这一批章节
            tasks = []
            for i, chapter_outline in enumerate(batch):
                chapter_num = batch_start + i + 1
                # 获取之前的章节用于上下文
                prev_chapters = [written_chapters[j] for j in sorted(written_chapters.keys())]
                tasks.append(
                    self._write_single_chapter_internal(
                        chapter_num, chapter_outline, prev_chapters
                    )
                )
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, result in enumerate(results):
                chapter_num = batch_start + i + 1
                
                if isinstance(result, Exception):
                    logger.error(f"Chapter {chapter_num} failed: {result}")
                    yield {
                        "stage": "chapter_error",
                        "message": f"第 {chapter_num} 章写作失败: {str(result)}",
                        "chapter_number": chapter_num,
                        "error": str(result)
                    }
                else:
                    written_chapters[chapter_num] = result
                    self.project.completed_chapters = max(
                        self.project.completed_chapters, chapter_num
                    )
                    
                    yield {
                        "stage": "chapter_complete",
                        "message": f"第 {chapter_num} 章完成",
                        "progress": progress,
                        "chapter": result
                    }
            
            self._update_checkpoint(current_chapter=batch_end)
    
    async def _write_single_chapter_internal(
        self,
        chapter_num: int,
        chapter_outline: Dict,
        previous_chapters: List[Dict]
    ) -> Dict[str, Any]:
        """写作单个章节的内部实现"""
        # 获取上下文
        context = self.context_manager.get_relevant_context("ChapterWriter")
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        
        if previous_chapters:
            context["previous_summary"] = self._summarize_chapter(
                previous_chapters[-1].get("content", "")
            )
        
        # 撰写章节
        chapter_result = await self.chapter_writer.execute({
            "chapter_outline": chapter_outline.get("summary", str(chapter_outline)),
            "chapter_title": chapter_outline.get("title", f"第{chapter_num}章"),
            "chapter_number": chapter_num
        }, context=context)
        
        chapter_content = chapter_result.get("content", "")
        
        # 评估与润色
        eval_result = await self.evaluator.execute({
            "content": chapter_content,
            "chapter_outline": chapter_outline
        }, context=context)
        
        evaluation = eval_result.get("evaluation", {})
        
        # 如果评估不通过，进行润色
        if not evaluation.get("passed", True):
            polish_result = await self.polisher.execute({
                "content": chapter_content,
                "feedback": json.dumps(evaluation.get("suggestions", []), ensure_ascii=False)
            })
            chapter_content = polish_result.get("content", chapter_content)
        
        # 保存章节
        chapter_data = {
            "number": chapter_num,
            "title": chapter_outline.get("title", f"第{chapter_num}章"),
            "content": chapter_content,
            "word_count": len(chapter_content),
            "evaluation": evaluation
        }
        
        self.context_manager.save_chapter_result(
            chapter_num,
            chapter_content,
            self._summarize_chapter(chapter_content)
        )
        
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
        
        # 恢复项目信息
        if self.checkpoint.project_data:
            self.project = NovelProject(**self.checkpoint.project_data)
        
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
                
                # 根据并行配置决定写作方式
                if self.parallel_chapters > 1:
                    async for progress_data in self._write_chapters_parallel(
                        chapters, world_data, outline_data
                    ):
                        yield progress_data
                        if progress_data.get("stage") == "cancelled":
                            return
                        if progress_data.get("stage") == "chapter_complete":
                            written_chapters.append(progress_data.get("chapter"))
                else:
                    async for progress_data in self._write_chapters_serial(
                        chapters, world_data, outline_data
                    ):
                        yield progress_data
                        if progress_data.get("stage") == "cancelled":
                            return
                        if progress_data.get("stage") == "chapter_complete":
                            written_chapters.append(progress_data.get("chapter"))
                
                # 完成
                self._update_checkpoint(state=WorkflowState.COMPLETED)
                self.project.status = "completed"
                self.project.updated_at = datetime.now().isoformat()
                self.project.word_count = sum(len(ch.get("content", "")) for ch in written_chapters)
                
                # 保存小说
                novel_file = self.project_dir / f"{self.project.title}.txt"
                self._save_novel(novel_file, written_chapters)
                
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
        self.context_manager.save("world", world_data, "world")
        
        return result
    
    async def generate_outline(
        self, 
        world: Optional[Dict] = None,
        protagonist: str = "",
        plot_idea: str = "",
        volume_count: int = 1,
        chapters_per_volume: int = 10
    ) -> Dict[str, Any]:
        """单独生成大纲"""
        if world is None:
            world = self.context_manager.get("world", {})
        
        result = await self.outliner.execute({
            "world": world,
            "protagonist": protagonist,
            "plot_idea": plot_idea,
            "volume_count": volume_count,
            "chapters_per_volume": chapters_per_volume
        }, context={"world": world})
        
        outline_data = result.get("outline", {})
        self.context_manager.save("outline", outline_data, "plot")
        
        return result
    
    async def write_single_chapter(
        self,
        chapter_number: int,
        chapter_outline: str,
        chapter_title: str = ""
    ) -> Dict[str, Any]:
        """撰写单个章节"""
        context = self.context_manager.get_chapter_context(chapter_number)
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        
        return await self.chapter_writer.execute({
            "chapter_outline": chapter_outline,
            "chapter_title": chapter_title or f"第{chapter_number}章",
            "chapter_number": chapter_number
        }, context=context)
    
    async def continue_chapter(
        self,
        chapter_index: int,
        chapter_title: str,
        existing_content: str,
        target_words: int = WRITING_CONFIG.CONTINUE_DEFAULT_WORDS
    ) -> Dict[str, Any]:
        """AI续写章节内容"""
        context = self.context_manager.get_chapter_context(chapter_index + 1)
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        context["existing_content"] = existing_content
        
        # 构建续写提示
        prompt = f"""你是一位专业的小说作家。请基于以下已有内容进行续写，保持风格一致，情节连贯。

章节标题：{chapter_title}

已有内容：
{existing_content}

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
        """章节摘要"""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."
    
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
        
        file_path.write_text("".join(content_parts), encoding="utf-8")
        logger.info(f"Novel saved to: {file_path}")
    
    def get_project_status(self) -> Dict[str, Any]:
        """获取项目状态"""
        return {
            "project": self.project.to_dict() if self.project else None,
            "workflow_state": self.workflow_state.value,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "world": self.world_manager.export_for_llm(),
            "characters": self.character_manager.export_for_llm(),
            "contexts": self.context_manager.export_all(),
            "metrics": self.metrics.get_report(),
            "context_stats": self.context_manager.get_stats()
        }
    
    def get_metrics_report(self) -> Dict[str, Any]:
        """获取详细的指标报告"""
        return {
            "summary": self.metrics.get_report(),
            "token_usage": self.metrics.get_token_usage_by_agent(),
            "performance": self.metrics.get_performance_summary(),
            "recent_errors": self.metrics.get_recent_errors()
        }


# 模块职责说明：实现协调者-工作者多智能体协作模式，管理小说创作的完整工作流、检查点保存和并行写作。
