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
import re
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
from ..memory_manager import get_memory_manager
from ..aux_memory import get_aux_memory_service
from ..project_manager import get_project_manager
from .plot_thread_state import PlotThreadStateMachine

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
        
        # 记忆管理（先初始化，因为管理器需要用到）
        self.memory_manager = get_memory_manager()
        self.aux_memory_service = get_aux_memory_service()
        self.project_manager = get_project_manager()
        
        # 初始化上下文管理器（使用当前项目目录）
        self._init_managers()
        self._plot_thread_state_key = "plot_thread_state"
        self._plot_thread_machine = PlotThreadStateMachine()
        self._plot_thread_lock = asyncio.Lock()
        self._load_plot_thread_state()
        self._memory_agent_ids: Dict[str, str] = {}
        self._memory_contract_version = "2026-02-07.1"
        
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

    @staticmethod
    def _normalize_trend_platforms(platforms: Optional[List[str]]) -> List[str]:
        normalized: List[str] = []
        for platform in platforms or []:
            value = str(platform or "").strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    @staticmethod
    def _extract_trend_tool_error(result: Any) -> str:
        if result is None:
            return ""
        if hasattr(result, "content") and result.content:
            first = result.content[0]
            text = getattr(first, "text", "")
            if isinstance(text, str):
                return text.strip()
        return ""

    def _get_trend_tool_name(self, platform: str) -> str:
        mapping = {
            "douban": "get_douban_rank",
            "weread": "get_weread_rank",
            "zhihu": "get_zhihu_trending",
            "gcores": "get_gcores_new",
            "toutiao": "get_toutiao_trending",
            "netease": "get_netease_news_trending",
            "tencent": "get_tencent_news_trending",
            "thepaper": "get_thepaper_trending",
            "bilibili": "get_bilibili_rank",
            "douyin": "get_douyin_trending",
            "weibo": "get_weibo_trending",
            "36kr": "get_36kr_trending",
            "sspai": "get_sspai_rank",
            "ifanr": "get_ifanr_news",
            "juejin": "get_juejin_article_rank",
            "smzdm": "get_smzdm_rank",
        }
        normalized = str(platform or "").strip().lower()
        return mapping.get(normalized, f"get_{normalized}_trending")

    def _build_trend_tool_candidates(self, platform: str) -> List[str]:
        normalized = str(platform or "").strip().lower()
        if not normalized:
            return []

        candidates: List[str] = []

        def _add(tool_name: str) -> None:
            if tool_name and tool_name not in candidates:
                candidates.append(tool_name)

        mapped = self._get_trend_tool_name(normalized)
        _add(mapped)

        modern = f"get_{normalized}_trending"
        _add(modern)
        _add(modern.replace("_", "-"))

        if mapped:
            _add(mapped.replace("_", "-"))

        return candidates

    @staticmethod
    def _select_balanced_trend_candidates(
        trends_data: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not trends_data or limit <= 0:
            return []

        platform_buckets: Dict[str, List[Dict[str, Any]]] = {}
        platform_order: List[str] = []

        for trend in trends_data:
            platform = str(trend.get("platform", "")).strip().lower()
            if platform not in platform_buckets:
                platform_buckets[platform] = []
                platform_order.append(platform)
            platform_buckets[platform].append(trend)

        merged: List[Dict[str, Any]] = []
        cursor = {platform: 0 for platform in platform_order}
        while len(merged) < limit:
            appended = False
            for platform in platform_order:
                idx = cursor[platform]
                items = platform_buckets.get(platform, [])
                if idx >= len(items):
                    continue
                merged.append(items[idx])
                cursor[platform] = idx + 1
                appended = True
                if len(merged) >= limit:
                    break
            if not appended:
                break

        return merged

    async def _search_trends_for_collab(
        self,
        platforms: Optional[List[str]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """协作模式热点检索：多平台回退 + 去重 + 轮询均衡聚合。"""
        selected_platforms = self._normalize_trend_platforms(platforms)
        total_limit = int(limit or 0)
        if not selected_platforms or total_limit <= 0:
            return []

        def _extract_tag(text: str, tag: str) -> str:
            if not text:
                return ""
            match = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
            return match.group(1).strip() if match else ""

        def _strip_xml(text: str) -> str:
            if not text:
                return ""
            return re.sub(r"<[^>]+>", "", text).strip()

        def _parse_trend_payload(payload: Any) -> List[Dict[str, str]]:
            rows: List[Dict[str, str]] = []
            if payload is None:
                return rows

            if isinstance(payload, list):
                for item in payload:
                    rows.extend(_parse_trend_payload(item))
                return rows

            if isinstance(payload, dict):
                for key in ("data", "list", "items", "result"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        rows.extend(_parse_trend_payload(value))
                        return rows

                title_val = payload.get("title") or payload.get("name") or payload.get("content") or ""
                if isinstance(title_val, (list, dict)):
                    rows.extend(_parse_trend_payload(title_val))
                    return rows

                title_text = str(title_val or "").strip()
                title = _extract_tag(title_text, "title") or _strip_xml(title_text) or title_text
                if title:
                    hot_val = (
                        payload.get("hot")
                        or payload.get("hotValue")
                        or payload.get("heat")
                        or payload.get("popularity")
                        or payload.get("score")
                        or ""
                    )
                    url_val = payload.get("url") or payload.get("link") or ""
                    rows.append(
                        {
                            "title": str(title),
                            "hot": str(hot_val or ""),
                            "url": str(url_val or ""),
                        }
                    )
                return rows

            if isinstance(payload, str):
                text = payload.strip()
                if not text:
                    return rows
                try:
                    parsed = json.loads(text)
                    rows.extend(_parse_trend_payload(parsed))
                    return rows
                except json.JSONDecodeError:
                    title = _extract_tag(text, "title") or _strip_xml(text) or text
                    if title:
                        rows.append(
                            {
                                "title": str(title),
                                "hot": _extract_tag(text, "popularity"),
                                "url": _extract_tag(text, "link"),
                            }
                        )
                return rows

            return rows

        try:
            seen_titles = set()
            platform_trends: Dict[str, List[Dict[str, Any]]] = {
                platform: [] for platform in selected_platforms
            }

            for platform in selected_platforms:
                tool_candidates = self._build_trend_tool_candidates(platform)
                result = None
                used_tool = ""

                for tool_name in tool_candidates:
                    try:
                        # 使用 Skill 系统
                        current = self.worldbuilder.use_skill("trends_search", tool_name, limit=total_limit)
                    except Exception as call_error:
                        logger.debug(
                            f"[Coordinator] 热点工具调用异常({platform}, {tool_name}): {call_error}"
                        )
                        continue

                    # 检查 Skill 调用结果
                    if not current or not current.get("success"):
                        error_msg = current.get("error", "") if current else "unknown error"
                        lowered_error = error_msg.lower()
                        if "not found" in lowered_error:
                            logger.debug(
                                f"[Coordinator] 热点工具不存在，尝试下一个候选: platform={platform}, tool={tool_name}"
                            )
                            continue
                        logger.debug(
                            f"[Coordinator] 热点工具调用失败({platform}, {tool_name}): {error_msg}"
                        )
                        continue

                    if current and current.get("success"):
                        result = current
                        used_tool = tool_name
                        break

                if result is None:
                    logger.debug(
                        f"[Coordinator] 未获取到平台热点({platform})，候选工具: {tool_candidates}"
                    )
                    continue

                # 处理 Skill 返回的数据
                if result and result.get("data"):
                    data_items = result.get("data", [])
                    for item in data_items:
                        title = str(item.get("title") or "").strip()
                        if not title or title in seen_titles:
                            continue
                        seen_titles.add(title)
                        platform_trends[platform].append(
                            {
                                "title": title,
                                "hot": str(item.get("热度", "") or ""),
                                "url": str(item.get("url", "") or ""),
                                "platform": platform,
                            }
                        )
                        if len(platform_trends[platform]) >= total_limit:
                            break

                logger.debug(
                    f"[Coordinator] 平台热点获取成功: platform={platform}, tool={used_tool}, count={len(platform_trends[platform])}"
                )

            merged_candidates: List[Dict[str, Any]] = []
            for platform in selected_platforms:
                merged_candidates.extend(platform_trends.get(platform, []))
            return self._select_balanced_trend_candidates(merged_candidates, limit=total_limit)
        except Exception as e:
            logger.warning(f"[Coordinator] 热点检索失败: {e}")
            return []

    def _build_trends_prompt_block(self, trends_data: List[Dict[str, Any]], limit: int = 5) -> str:
        if not trends_data:
            return ""

        parts: List[str] = []
        parts.append("热点融合要求：")
        parts.append("请从热点候选中选择 1-2 条与当前剧情最契合的内容进行改编融入。")
        parts.append("不要原样照抄热点标题，不要写成新闻播报，要转化为角色动机/冲突/事件触发。")
        parts.append("")
        parts.append("[热点候选]")

        for trend in self._select_balanced_trend_candidates(trends_data, limit=limit):
            title = str(trend.get("title", "")).strip()
            if not title:
                continue
            platform = str(trend.get("platform", "")).strip()
            hot = str(trend.get("hot", "")).strip()
            source = f"[{platform}]" if platform else ""
            heat = f"（热度:{hot}）" if hot else ""
            parts.append(f"- {source}{title}{heat}")

        parts.append("")
        return "\n".join(parts)
    
    def _load_plot_thread_state(self) -> None:
        """Load persisted plot thread state for the current project."""
        try:
            payload = self.project_manager.load_project_state(
                self._plot_thread_state_key, default=None
            )
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to load state: {exc}")
            payload = None
        self._plot_thread_machine.load(payload if isinstance(payload, dict) else None)

    def _save_plot_thread_state(self) -> None:
        """Persist plot thread state for the current project."""
        try:
            self.project_manager.save_project_state(
                self._plot_thread_state_key, self._plot_thread_machine.snapshot()
            )
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to save state: {exc}")

    def _sync_plot_thread_state_with_outline(
        self,
        outline_data: Optional[Dict[str, Any]],
        total_chapters: int,
        reset: bool,
    ) -> Dict[str, Any]:
        """Sync thread definitions from outline and persist."""
        try:
            state = self._plot_thread_machine.sync_with_outline(
                outline_data if isinstance(outline_data, dict) else {},
                total_chapters=total_chapters,
                reset=reset,
            )
            self._save_plot_thread_state()
            return state
        except Exception as exc:
            logger.warning(f"[PlotThread] failed to sync with outline: {exc}")
            return self._plot_thread_machine.snapshot()

    async def _plan_plot_thread_for_chapter(
        self,
        chapter_num: int,
        chapter_outline: Any,
    ) -> Dict[str, Any]:
        """Plan active thread before writing a chapter."""
        async with self._plot_thread_lock:
            try:
                context = self._plot_thread_machine.plan_chapter(chapter_num, chapter_outline)
                self._save_plot_thread_state()
                return context
            except Exception as exc:
                logger.warning(f"[PlotThread] failed to plan chapter {chapter_num}: {exc}")
                return {
                    "active_thread_id": "main",
                    "active_thread": {"id": "main", "title": "主线", "thread_type": "main"},
                    "subplot_streak": 0,
                    "last_transition_reason": "plan_failed",
                    "threads_overview": [],
                    "writer_guidance": "保持主线推进。",
                }

    async def _complete_plot_thread_for_chapter(
        self,
        chapter_num: int,
        chapter_outline: Any,
        chapter_content: str,
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply post-chapter transitions and persist state."""
        async with self._plot_thread_lock:
            try:
                result = self._plot_thread_machine.complete_chapter(
                    chapter_number=chapter_num,
                    chapter_outline=chapter_outline,
                    chapter_content=chapter_content,
                    evaluation=evaluation or {},
                )
                self._save_plot_thread_state()
                return result
            except Exception as exc:
                logger.warning(f"[PlotThread] failed to finalize chapter {chapter_num}: {exc}")
                return {
                    "active_thread_id": self._plot_thread_machine.snapshot().get(
                        "active_thread_id", "main"
                    ),
                    "resolved_thread_ids": [],
                    "transition_reason": "complete_failed",
                    "threads_overview": [],
                }

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

    def _build_memory_contract(self) -> Dict[str, Any]:
        """定义记忆权威源与冲突合并规则（版本化）"""
        return {
            "contract_version": self._memory_contract_version,
            "updated_at": datetime.now().isoformat(),
            "source_of_truth": {
                "chapter_facts": "KnowledgeBase",
                "session_state": "SessionStore",
                "workflow_state": "ContextManager+Checkpoint",
                "long_term_preferences_and_summary": "MemoryManager(Wensi)"
            },
            "conflict_resolution": {
                "priority_order": [
                    "KnowledgeBase",
                    "SessionStore",
                    "ContextManager+Checkpoint",
                    "MemoryManager(Wensi)"
                ],
                "default_strategy": "last_write_wins_with_priority",
                "versioning": "timestamp+contract_version",
                "notes": "高优先级源覆盖低优先级源；同优先级冲突按最近更新时间合并。"
            }
        }

    def _memory_meta_file(self) -> Path:
        return self.project_dir / "memory_sync_meta.json"

    def _memory_snapshot_file(self) -> Path:
        return self.project_dir / "memory_snapshot.json"

    def _append_memory_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """记录记忆同步事件到本地文件，便于排障与审计"""
        try:
            path = self._memory_meta_file()
            payload = {
                "contract": self._build_memory_contract(),
                "project": self.project.to_dict() if self.project else {},
                "project_scope": self.project_manager.current_project_id or "",
                "updated_at": datetime.now().isoformat(),
                "events": []
            }

            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        payload.update(existing)
                        payload["contract"] = self._build_memory_contract()
                        payload["updated_at"] = datetime.now().isoformat()
                except Exception:
                    pass

            payload.setdefault("events", [])
            payload["events"].append({
                "type": event_type,
                "time": datetime.now().isoformat(),
                "data": data or {}
            })

            # 控制事件数量，防止无限增长
            if len(payload["events"]) > 300:
                payload["events"] = payload["events"][-300:]

            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to append memory event: {e}")

    async def _ensure_memory_agent(self, agent_type: str) -> Optional[str]:
        """确保指定类型的记忆Agent已创建"""
        project_scope = self.project_manager.current_project_id or (self.project.id if self.project else "default")
        scoped_key = f"{project_scope}:{agent_type}"
        if scoped_key in self._memory_agent_ids:
            return self._memory_agent_ids[scoped_key]

        if not self.memory_manager.wensi_service.is_available:
            self._append_memory_event("memory_agent_skipped", {
                "agent_type": agent_type,
                "reason": "wensi_unavailable"
            })
            return None

        try:
            agent_name = f"novel_{project_scope}_{agent_type}".lower()
            agent_id = await self.memory_manager.wensi_service.create_agent(name=agent_name)
            if agent_id:
                self._memory_agent_ids[scoped_key] = agent_id
                self._append_memory_event("memory_agent_created", {
                    "agent_type": agent_type,
                    "project_scope": project_scope,
                    "agent_id": agent_id
                })
                return agent_id
            self._append_memory_event("memory_agent_create_failed", {
                "agent_type": agent_type,
                "project_scope": project_scope
            })
        except Exception as e:
            logger.warning(f"Failed to create memory agent for {agent_type}: {e}")
            self._append_memory_event("memory_agent_create_exception", {
                "agent_type": agent_type,
                "error": str(e)
            })
        return None

    async def _sync_memory_for_agent(self, agent_type: str) -> None:
        """按Agent类型执行记忆同步"""
        try:
            agent_id = await self._ensure_memory_agent(agent_type)
            if not agent_id:
                return

            success = await self.memory_manager.sync_project_to_memory(agent_type, agent_id)
            self._append_memory_event("memory_sync", {
                "agent_type": agent_type,
                "agent_id": agent_id,
                "success": success
            })
        except Exception as e:
            logger.warning(f"Memory sync failed for {agent_type}: {e}")
            self._append_memory_event("memory_sync_exception", {
                "agent_type": agent_type,
                "error": str(e)
            })

    async def _sync_memory_stage(self, stage: str) -> None:
        """在关键阶段执行增量记忆同步"""
        stage_agent_map = {
            "init": ["ChapterWriter"],
            "worldbuilding": ["Worldbuilder", "ChapterWriter"],
            "outlining": ["Outliner", "ChapterWriter"],
            "writing": ["ChapterWriter", "Polisher"],
            "resume": ["ChapterWriter"]
        }
        for agent_type in stage_agent_map.get(stage, []):
            await self._sync_memory_for_agent(agent_type)

    async def _export_memory_snapshot(self, reason: str) -> None:
        """导出记忆快照到项目目录"""
        try:
            memory_payload = {
                "reason": reason,
                "exported_at": datetime.now().isoformat(),
                "contract": self._build_memory_contract(),
                "project": self.project.to_dict() if self.project else {},
                "project_scope": self.project_manager.current_project_id or "",
                "agent_memories": {}
            }

            for scoped_key, agent_id in self._memory_agent_ids.items():
                try:
                    memory_payload["agent_memories"][scoped_key] = await self.memory_manager.export_memory_to_project(agent_id)
                except Exception as e:
                    memory_payload["agent_memories"][scoped_key] = {"_error": str(e)}

            self._memory_snapshot_file().write_text(
                json.dumps(memory_payload, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            self._append_memory_event("memory_export", {"reason": reason, "agent_count": len(self._memory_agent_ids)})
        except Exception as e:
            logger.warning(f"Failed to export memory snapshot: {e}")
            self._append_memory_event("memory_export_exception", {"reason": reason, "error": str(e)})
    
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
        
        # 使用 ProjectManager 创建新项目
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pm_project = self.project_manager.create_project(
            name=f"{novel_type}小说_{timestamp}",
            description=f"类型：{novel_type}，主题：{theme or '未指定'}"
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
            total_chapters=volume_count * chapters_per_volume
        )
        
        # 初始化检查点
        self._update_checkpoint(state=WorkflowState.IDLE, current_chapter=0)
        await self._sync_memory_stage("init")
        
        yield {
            "stage": "init",
            "message": f"开始创作小说...（项目ID: {pm_project.id}）",
            "progress": 0,
            "project_id": pm_project.id,
            "project_dir": str(self.project_dir)
        }
        
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
            
            # 保存到 ContextManager
            self.context_manager.save("world", world_data, "world")
            
            # 更新世界管理器并保存到项目目录
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
                logger.info(f"World saved to: {self.project_dir / 'worldbuilding.json'}")
            
            self._update_checkpoint(add_stage="worldbuilding")
            await self._sync_memory_stage("worldbuilding")
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
            await self._sync_memory_stage("outlining")
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
            self._sync_plot_thread_state_with_outline(
                outline_data=outline_data,
                total_chapters=total_chapters,
                reset=True,
            )
            
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
            
            await self._sync_memory_stage("writing")

            # === Stage 4: 完成 ===
            self._update_checkpoint(state=WorkflowState.COMPLETED)
            self.project.status = "completed"
            self.project.updated_at = datetime.now().isoformat()
            self.project.word_count = sum(len(ch.get("content", "")) for ch in written_chapters)
            
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
        context["plot_thread"] = await self._plan_plot_thread_for_chapter(
            chapter_num=chapter_num,
            chapter_outline=chapter_outline,
        )

        aux_query = self._build_aux_memory_query(chapter_num, chapter_outline, context)
        aux_injection = self._get_aux_memory_injection_context(aux_query)
        context["aux_memory"] = {
            "enabled": aux_injection.get("enabled", False),
            "items": aux_injection.get("items", []),
            "prompt_preview": aux_injection.get("prompt_preview", ""),
            "count": aux_injection.get("count", 0),
            "mode": aux_injection.get("mode", "fast"),
        }
        
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

        plot_thread_result = await self._complete_plot_thread_for_chapter(
            chapter_num=chapter_num,
            chapter_outline=chapter_outline,
            chapter_content=chapter_content,
            evaluation=evaluation,
        )
        
        # 保存章节
        chapter_data = {
            "number": chapter_num,
            "title": chapter_outline.get("title", f"第{chapter_num}章"),
            "content": chapter_content,
            "word_count": len(chapter_content),
            "evaluation": evaluation,
            "plot_thread": plot_thread_result,
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
                await self._sync_memory_stage("writing")
                self._update_checkpoint(state=WorkflowState.COMPLETED)
                self.project.status = "completed"
                self.project.updated_at = datetime.now().isoformat()
                self.project.word_count = sum(len(ch.get("content", "")) for ch in written_chapters)
                
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
        chapter_title: str = "",
        enable_trends: bool = False,
        trends_platforms: Optional[List[str]] = None,
        trends_query: str = "",
    ) -> Dict[str, Any]:
        """撰写单个章节"""
        context = self.context_manager.get_chapter_context(chapter_number)
        context["world"] = self.world_manager.get_world_context()
        context["characters"] = self.character_manager.get_character_context()
        outline_payload = {
            "title": chapter_title or f"Chapter {chapter_number}",
            "summary": chapter_outline,
        }
        context["plot_thread"] = await self._plan_plot_thread_for_chapter(
            chapter_num=chapter_number,
            chapter_outline=outline_payload,
        )

        aux_query = f"{chapter_title or ''} {chapter_outline} chapter:{chapter_number}".strip()
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
                    f"[Coordinator] 协作写章注入热点: count={len(trends_data)}, query={trends_query[:80]}"
                )
        context["trends_data"] = trends_data
        
        result = await self.chapter_writer.execute({
            "chapter_outline": chapter_outline,
            "chapter_title": chapter_title or f"第{chapter_number}章",
            "chapter_number": chapter_number
        }, context=context)
        await self._complete_plot_thread_for_chapter(
            chapter_num=chapter_number,
            chapter_outline=outline_payload,
            chapter_content=result.get("content", ""),
            evaluation={},
        )
        return result
    
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
            "plot_thread_state": self._plot_thread_machine.snapshot(),
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

    def get_memory_diagnostics(self) -> Dict[str, Any]:
        """获取记忆契约与同步诊断信息"""
        meta_file = self._memory_meta_file()
        snapshot_file = self._memory_snapshot_file()

        diagnostics = {
            "contract": self._build_memory_contract(),
            "memory_agent_count": len(self._memory_agent_ids),
            "memory_agents": list(self._memory_agent_ids.keys()),
            "meta_file": str(meta_file),
            "meta_exists": meta_file.exists(),
            "snapshot_file": str(snapshot_file),
            "snapshot_exists": snapshot_file.exists(),
        }

        if meta_file.exists():
            try:
                diagnostics["meta"] = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception as e:
                diagnostics["meta_error"] = str(e)

        if snapshot_file.exists():
            try:
                diagnostics["snapshot"] = json.loads(snapshot_file.read_text(encoding="utf-8"))
            except Exception as e:
                diagnostics["snapshot_error"] = str(e)

        return diagnostics


# 模块职责说明：实现协调者-工作者多智能体协作模式，管理小说创作的完整工作流、检查点保存和并行写作。
