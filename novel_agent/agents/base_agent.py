"""
Agent基类
实现LLM调用封装、上下文注入、日志等通用功能
支持每个Agent独立的模型配置
增强功能：回调机制、重试支持、指标收集、消息总线集成
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable, Awaitable, Union, Tuple
from pathlib import Path

from openai import AsyncOpenAI
import httpx

from ..config import config
from ..agent_config import AgentModelConfig, get_config_manager
from ..utils.retry import async_retry, RetryConfig
from ..utils.metrics import get_metrics_collector, MetricsContext
from ..utils.token_stats import extract_token_usage, estimate_tokens_from_messages, estimate_tokens_from_text, record_token_usage
from ..utils.llm_params import add_temperature_param, is_temperature_parameter_error, normalize_max_tokens
from ..constants import TIMEOUTS, RETRY_DEFAULTS
from ..timeout_settings import get_llm_timeout_settings
from .api_key_rotation import (
    KeyUseResult,
    classify_key_error,
    get_api_key_rotation_service,
    is_api_key_rotation_enabled,
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 回调处理器类型
CallbackHandler = Callable[[Dict[str, Any]], Awaitable[Optional[Any]]]


@dataclass
class AgentCapability:
    """Agent能力声明。"""

    agent_name: str
    capabilities: List[str] = field(default_factory=list)
    accept_task_types: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    produced_outputs: List[str] = field(default_factory=list)
    priority: int = 50
    max_concurrency: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseAgent(ABC):
    """
    Agent基类 - 支持独立模型配置
    
    增强功能：
    - 回调机制：支持请求用户输入
    - 重试支持：LLM调用自动重试
    - 指标收集：自动记录调用指标
    - 消息总线：支持Agent间通信
    """
    
    # Agent名称 → PromptManager agent_type 映射表
    # 子类可通过覆盖此属性或设置 prompt_manager_key 来自定义映射
    _PROMPT_MANAGER_KEY_MAP: Dict[str, str] = {
        "ChapterWriter": "chapter_writer",
        "Worldbuilder": "worldbuilder",
        "Evaluator": "evaluator",
        "Polisher": "polisher",
        "Communicator": "communicator",
        "ContinuousWriter": "continuous_writer",
        "Outliner": "outliner",
        "Router": "router",
        "copilot": "copilot",
    }

    def __init__(
        self,
        name: str,
        prompt_file: Optional[str] = None,
        model_config: Optional[AgentModelConfig] = None,
        callback_handler: Optional[CallbackHandler] = None,
        retry_config: Optional[RetryConfig] = None,
        prompt_manager_key: Optional[str] = None,
    ):
        """
        初始化Agent
        
        Args:
            name: Agent名称
            prompt_file: 系统提示词文件路径(相对于prompts目录)
            model_config: 可选的模型配置，如果不提供则从配置管理器加载
            callback_handler: 回调处理器，用于请求用户输入等
            retry_config: 重试配置
            prompt_manager_key: PromptManager中的agent_type键名，用于获取用户自定义提示词
        """
        self.name = name
        self.prompt_file = prompt_file
        self.prompt_manager_key = prompt_manager_key or self._PROMPT_MANAGER_KEY_MAP.get(name, "")
        self.system_prompt = self._load_system_prompt()
        
        # 加载或使用提供的模型配置
        self.model_config = model_config or self._load_model_config()
        
        # 回调和重试配置
        self.callback_handler = callback_handler
        self.retry_config = retry_config or RetryConfig(
            max_retries=RETRY_DEFAULTS.MAX_RETRIES,
            delay=RETRY_DEFAULTS.INITIAL_DELAY,
            backoff=RETRY_DEFAULTS.BACKOFF_MULTIPLIER,
            max_delay=RETRY_DEFAULTS.MAX_DELAY
        )
        
        # 初始化OpenAI客户端
        self._rotation_client_cache: Dict[tuple[str, str], Any] = {}
        self.client = self._create_client()
        
        # LLMClient代理（用于非openai_chat类型的API路由）
        self._llm_client = None
        
        # 指标收集器
        self.metrics = get_metrics_collector()
        
        # 消息总线（延迟初始化）
        self._message_bus = None
        
        # 消息订阅状态
        self._subscribed = False
        
        # 待处理的用户输入请求
        self._pending_responses: Dict[str, 'asyncio.Future'] = {}
        
        logger.info(f"Initialized {self.name} Agent (model: {self._get_model_name()})")
    
    def _load_model_config(self) -> AgentModelConfig:
        """从配置管理器加载模型配置（使用全局配置合并）"""
        manager = get_config_manager()
        return manager.get_effective_config(self.name)
    
    def _build_timeout_config(self) -> httpx.Timeout:
        llm_timeouts = get_llm_timeout_settings()
        return httpx.Timeout(
            connect=float(llm_timeouts["connect"]),
            read=float(llm_timeouts["read"]),
            write=float(llm_timeouts["write"]),
            pool=float(llm_timeouts["pool"]),
        )

    def _create_client(self) -> AsyncOpenAI:
        """创建OpenAI客户端（仅用于openai_chat类型）"""
        # 优先使用Agent独立配置，否则使用全局配置
        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        llm_timeouts = get_llm_timeout_settings()
        timeout_config = self._build_timeout_config()
        
        logger.info(
            "[%s] Creating OpenAI client: base_url=%s, timeout=connect:%ss/read:%ss/write:%ss/pool:%ss, max_retries=0",
            self.name,
            api_base,
            llm_timeouts["connect"],
            llm_timeouts["read"],
            llm_timeouts["write"],
            llm_timeouts["pool"],
        )
        
        return self._create_openai_client(api_key, api_base, timeout_config)

    @staticmethod
    def _is_tsc5_api_base_value(api_base: str) -> bool:
        return "tsc5.top" in str(api_base or "").lower()

    def _create_openai_client(self, api_key: str, api_base: str, timeout_config: httpx.Timeout) -> AsyncOpenAI:
        kwargs = {
            "api_key": api_key,
            "base_url": api_base,
            "timeout": timeout_config,
            "max_retries": 0,  # 禁用SDK内部重试，使用我们自己的重试逻辑
        }
        if self._is_tsc5_api_base_value(api_base):
            kwargs["default_headers"] = {"User-Agent": "ShanhaiYunyan/1.0"}
        return AsyncOpenAI(**kwargs)

    def _rotation_config_id(self) -> str:
        return (
            str(getattr(self.model_config, "api_config_id", "") or "").strip()
            or f"{self._api_type}:{self.model_config.api_base or config.llm.api_base}"
        )

    def _rotation_entries(self):
        if hasattr(self.model_config, "get_enabled_key_entries"):
            return self.model_config.get_enabled_key_entries()
        return []

    def _should_use_key_rotation(self) -> bool:
        return bool(self._api_type == "openai_chat" and is_api_key_rotation_enabled() and self._rotation_entries())

    def _select_rotated_openai_client(self, exclude_key_ids: Optional[set[str]] = None):
        if not self._should_use_key_rotation():
            return self.client, None

        service = get_api_key_rotation_service()
        config_id = self._rotation_config_id()
        selected = service.get_next_key(config_id, self._rotation_entries(), exclude_key_ids)
        if not selected:
            return None, None

        api_base = self.model_config.api_base or config.llm.api_base
        cache_key = (api_base, selected.id)
        client = self._rotation_client_cache.get(cache_key)
        if client is None:
            client = self._create_openai_client(selected.key, api_base, self._build_timeout_config())
            self._rotation_client_cache[cache_key] = client
        return client, selected

    async def _create_chat_completion_with_rotation(self, params: Dict[str, Any]):
        if not self._should_use_key_rotation():
            return await self.client.chat.completions.create(**params)

        service = get_api_key_rotation_service()
        config_id = self._rotation_config_id()
        attempted: set[str] = set()
        last_error: Optional[BaseException] = None

        while True:
            client, key_entry = self._select_rotated_openai_client(attempted)
            if not client or not key_entry:
                if last_error:
                    raise last_error
                raise RuntimeError("No available API key in rotation pool")

            try:
                response = await client.chat.completions.create(**params)
            except Exception as exc:
                last_error = exc
                result = classify_key_error(exc)
                service.report_key_result(config_id, key_entry.id, result, exc)
                attempted.add(key_entry.id)
                logger.warning(
                    "[%s] key %s reported %s; trying another key if available",
                    self.name,
                    key_entry.preview,
                    result.value,
                )
                if result == KeyUseResult.UNKNOWN:
                    raise
                continue

            service.report_key_result(config_id, key_entry.id, KeyUseResult.SUCCESS)
            return response
    
    def _get_or_create_llm_client(self):
        """获取或创建LLMClient实例（用于非openai_chat类型的API路由）"""
        if self._llm_client is None:
            from .llm_client import LLMClient
            self._llm_client = LLMClient(
                model_config=self.model_config,
                retry_config=None,  # BaseAgent自己处理重试
                metrics_namespace=self.name
            )
        return self._llm_client
    
    @property
    def _api_type(self) -> str:
        """获取当前配置的API类型"""
        return getattr(self.model_config, 'api_type', '') or 'openai_chat'
    
    def _get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        return self.model_config.model or config.llm.model
    
    def _get_temperature(self) -> float:
        """获取温度参数
        
        model_config 由 get_effective_config 返回，已包含合并后的有效值
        """
        return self.model_config.temperature
    
    def _get_max_tokens(self) -> int:
        """获取最大token数

        model_config 由 get_effective_config 返回，已包含合并后的有效值
        """
        return self.model_config.max_tokens

    def _is_tsc5_api_base(self) -> bool:
        """识别探索仓中转域名。"""
        api_base = self.model_config.api_base or config.llm.api_base or ""
        return self._is_tsc5_api_base_value(api_base)

    def _should_omit_max_tokens(self) -> bool:
        """探索仓等严格 OpenAI 兼容中转不携带 max_tokens。"""
        return self._is_tsc5_api_base()

    def _temperatureless_retry_params(self, params: Dict[str, Any], error: Exception) -> Optional[Dict[str, Any]]:
        """Retry once without temperature when a strict provider rejects it."""
        if "temperature" not in params or not is_temperature_parameter_error(error):
            return None
        retry_params = dict(params)
        retry_params.pop("temperature", None)
        logger.warning("[%s] 当前模型接口拒绝 temperature 参数，已去掉该参数后重试一次", self.name)
        return retry_params

    def _split_system_messages(self, messages: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], str]:
        system_parts: List[str] = []
        if self.system_prompt:
            system_parts.append(str(self.system_prompt).strip())

        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user") or "user").strip() or "user"
            content = message.get("content", "")
            if role == "system":
                text = str(content or "").strip()
                if text:
                    system_parts.append(text)
                continue
            normalized.append(dict(message))

        return normalized, "\n\n".join(part for part in system_parts if part)

    def _build_openai_chat_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """构建 Chat Completions 消息，按中转兼容性调整 system role。"""
        normalized, resolved_system_prompt = self._split_system_messages(messages)
        if not resolved_system_prompt:
            return normalized
        if not self._is_tsc5_api_base():
            return [{"role": "system", "content": resolved_system_prompt}] + normalized

        if not normalized:
            return [{"role": "user", "content": resolved_system_prompt}]

        for message in normalized:
            if message.get("role") == "user":
                content = message.get("content", "")
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                message["content"] = f"写作提示:\n{resolved_system_prompt}\n\n{content}"
                return normalized

        normalized.insert(0, {"role": "user", "content": resolved_system_prompt})
        return normalized

    def update_config(self, **kwargs) -> None:
        """
        更新Agent配置并重新初始化客户端
        
        Args:
            **kwargs: 要更新的配置字段
        """
        manager = get_config_manager()
        self.model_config = manager.update_config(self.name, **kwargs)
        self.client = self._create_client()
        self._llm_client = None  # 重置LLMClient以使用新配置
        self._rotation_client_cache.clear()
        logger.info(f"[{self.name}] Config updated, model: {self._get_model_name()}, api_type: {self._api_type}")

    def refresh_model_config(self) -> bool:
        """
        重新从配置管理器加载生效配置。

        Returns:
            bool: 配置是否发生变化
        """
        latest = self._load_model_config()
        current = self.model_config

        changed = any([
            current.api_base != latest.api_base,
            current.get_primary_key() != latest.get_primary_key(),
            [entry.id for entry in current.get_enabled_key_entries()] != [entry.id for entry in latest.get_enabled_key_entries()],
            current.model != latest.model,
            current.temperature != latest.temperature,
            current.max_tokens != latest.max_tokens,
            current.use_global != latest.use_global,
            getattr(current, 'api_type', 'openai_chat') != getattr(latest, 'api_type', 'openai_chat'),
            getattr(current, 'api_config_id', '') != getattr(latest, 'api_config_id', ''),
        ])

        if not changed:
            return False

        self.model_config = latest
        self.client = self._create_client()
        self._llm_client = None  # 重置LLMClient以使用新配置
        self._rotation_client_cache.clear()
        logger.info(
            f"[{self.name}] Effective config refreshed: model={self._get_model_name()}, "
            f"use_global={self.model_config.use_global}, api_type={self._api_type}"
        )
        return True
    
    def set_callback_handler(self, handler: CallbackHandler) -> None:
        """设置回调处理器"""
        self.callback_handler = handler
    
    def set_retry_config(self, retry_cfg: RetryConfig) -> None:
        """设置重试配置"""
        self.retry_config = retry_cfg
    
    @property
    def message_bus(self):
        """获取消息总线（延迟加载）"""
        if self._message_bus is None:
            from .message_bus import get_message_bus
            self._message_bus = get_message_bus()
        return self._message_bus
    
    async def ensure_subscribed(self):
        """确保Agent已订阅消息总线"""
        if not self._subscribed:
            self.message_bus.subscribe(self.name, self._handle_incoming_message)
            self._subscribed = True
            logger.info(f"[{self.name}] Subscribed to message bus")
    
    async def _handle_incoming_message(self, message: 'AgentMessage') -> Optional['AgentMessage']:
        """
        处理接收到的消息
        
        Args:
            message: 收到的消息
            
        Returns:
            响应消息（如果需要）
        """
        from .message_bus import MessageType, AgentMessage
        
        logger.debug(f"[{self.name}] Received message: {message.msg_type.value} from {message.sender}")
        
        try:
            if message.msg_type == MessageType.TASK_ASSIGNED:
                # 处理任务分配
                task_data = message.payload.get("task_data", {})
                context = message.payload.get("context")

                previous_callback = self.callback_handler
                self.callback_handler = self._create_task_callback_proxy(message, previous_callback)
                try:
                    # 执行任务
                    result = await self.execute(task_data, context)
                finally:
                    self.callback_handler = previous_callback
                
                # 创建完成响应
                response = AgentMessage(
                    msg_type=MessageType.TASK_COMPLETED,
                    sender=self.name,
                    receiver=message.sender,
                    payload={
                        "task_id": message.id,
                        "result": result,
                        "success": True
                    },
                    reply_to=message.id
                )
                
                # 发送响应
                await self.message_bus.reply(message, response)
                return response
            
            elif message.msg_type == MessageType.CONTEXT_REQUEST:
                # 处理上下文请求
                context_key = message.payload.get("key")
                # 子类可以重写此方法提供上下文
                context_value = await self._get_context(context_key)
                
                response = AgentMessage(
                    msg_type=MessageType.CONTEXT_UPDATED,
                    sender=self.name,
                    receiver=message.sender,
                    payload={"key": context_key, "value": context_value},
                    reply_to=message.id
                )
                await self.message_bus.reply(message, response)
                return response
            
            elif message.msg_type == MessageType.CONTEXT_UPDATED:
                # 处理上下文更新广播
                await self._on_context_updated(
                    message.payload.get("key"),
                    message.payload.get("value"),
                    message.sender
                )
                return None
            
            elif message.msg_type == MessageType.USER_INPUT_RECEIVED:
                # 处理用户输入响应
                if message.reply_to in self._pending_responses:
                    future = self._pending_responses.pop(message.reply_to)
                    if not future.done():
                        future.set_result(message.payload.get("input"))
                return None
            
        except Exception as e:
            logger.error(f"[{self.name}] Error handling message: {e}")
            # 发送失败响应
            from .message_bus import AgentMessage, MessageType
            error_response = AgentMessage(
                msg_type=MessageType.TASK_FAILED,
                sender=self.name,
                receiver=message.sender,
                payload={
                    "task_id": message.id,
                    "error": str(e),
                    "success": False
                },
                reply_to=message.id
            )
            await self.message_bus.publish(error_response)
            return error_response
        
        return None

    def _create_task_callback_proxy(
        self,
        message: 'AgentMessage',
        previous_handler: Optional[CallbackHandler]
    ) -> CallbackHandler:
        """为总线任务包装回调，将过程事件回传给请求方。"""

        async def proxy(data: Dict[str, Any]) -> Optional[Any]:
            await self._publish_task_callback_event(message, data)
            if previous_handler:
                return await previous_handler(data)
            return None

        return proxy

    async def _publish_task_callback_event(self, message: 'AgentMessage', data: Optional[Dict[str, Any]]) -> None:
        """将子 Agent 回调事件转发为消息总线事件。"""
        if not data:
            return

        from .message_bus import AgentMessage, MessageType

        payload = dict(data)
        payload.setdefault("task_id", message.id)

        event_type = str(payload.get("type") or "").strip()
        msg_type = MessageType.USER_INPUT_REQUIRED if event_type == "user_input_required" else MessageType.TASK_PROGRESS

        progress_message = AgentMessage(
            msg_type=msg_type,
            sender=self.name,
            receiver=message.sender,
            payload=payload,
            reply_to=message.id
        )
        await self.message_bus.publish(progress_message)
    
    async def _get_context(self, key: str) -> Any:
        """
        获取上下文（子类可重写）
        
        Args:
            key: 上下文键
            
        Returns:
            上下文值
        """
        return None
    
    async def _on_context_updated(self, key: str, value: Any, sender: str):
        """
        上下文更新回调（子类可重写）
        
        Args:
            key: 上下文键
            value: 上下文值
            sender: 发送者
        """
        pass
    
    def _load_system_prompt(self) -> str:
        """加载系统提示词
        
        优先级：
        1. PromptManager 中的内置文件提示词（用户 system 自定义只作为补充追加）
        2. prompts/*.md 文件（与 BaseAgent 运行时一致的文件提示词）
        3. 代码内置默认提示词（_get_default_prompt fallback）
        """
        # 优先从 PromptManager 获取（包含用户自定义配置）
        if self.prompt_manager_key:
            try:
                from ..prompts.prompt_manager import get_prompt_manager
                pm = get_prompt_manager()
                prompt = pm.get_system_prompt(self.prompt_manager_key, inject_security=True)
                if prompt:
                    logger.info(f"[{self.name}] 使用 PromptManager 提示词 (key={self.prompt_manager_key})")
                    return prompt
            except Exception as e:
                logger.warning(f"[{self.name}] 从 PromptManager 加载提示词失败: {e}")
        
        # 回退到文件提示词
        if not self.prompt_file:
            return self._get_default_prompt()
        
        prompt_path = config.paths.prompts_dir / self.prompt_file
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        else:
            logger.warning(f"Prompt file not found: {prompt_path}, using default")
            return self._get_default_prompt()

    def _render_custom_task_prompt(self, task_name: str, **variables: Any) -> str:
        """Render a PromptManager task prompt only when the user customized it."""
        if not self.prompt_manager_key:
            return ""
        try:
            from ..prompts.prompt_manager import get_prompt_manager

            pm = get_prompt_manager()
            if not pm.has_custom_prompt(self.prompt_manager_key, task_name):
                return ""
            return pm.render_prompt(self.prompt_manager_key, task_name, **variables).strip()
        except Exception as e:
            logger.warning(
                f"[{self.name}] 加载自定义任务提示词失败: "
                f"{self.prompt_manager_key}.{task_name}: {e}"
            )
            return ""
    
    @abstractmethod
    def _get_default_prompt(self) -> str:
        """获取默认系统提示词(子类实现)"""
        pass
    
    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        enable_retry: bool = True
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        调用LLM（支持自动重试和指标收集）
        
        Args:
            messages: 消息列表
            temperature: 温度参数(可选，覆盖配置)
            max_tokens: 最大token数(可选，覆盖配置)
            stream: 是否流式输出
            enable_retry: 是否启用重试
            
        Returns:
            LLM响应文本或流式生成器
        """
        if enable_retry:
            return await self._call_llm_with_retry(messages, temperature, max_tokens, stream)
        else:
            return await self._call_llm_internal(messages, temperature, max_tokens, stream)
    
    async def _call_llm_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool
    ) -> Union[str, AsyncGenerator[str, None]]:
        """带重试的LLM调用"""
        import asyncio

        if stream:
            return self._stream_response_with_retry(messages, temperature, max_tokens)
        
        last_error = None
        attempts_made = 0
        current_delay = self.retry_config.delay

        for attempt in range(self.retry_config.max_retries + 1):
            attempts_made = attempt + 1
            try:
                return await self._call_llm_internal(messages, temperature, max_tokens, stream)
            except Exception as e:
                last_error = e

                if attempt >= self.retry_config.max_retries:
                    break

                if not self._is_retryable_error(e):
                    break
                
                # 计算延迟
                wait_time = min(current_delay, self.retry_config.max_delay)
                if self.retry_config.jitter:
                    import random
                    jitter_min, jitter_max = RETRY_DEFAULTS.JITTER_RANGE
                    wait_time *= random.uniform(jitter_min, jitter_max)
                
                logger.warning(
                    f"[{self.name}] LLM call failed (attempt {attempt + 1}/{self.retry_config.max_retries + 1}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                try:
                    await self._emit_callback_event({
                        "type": "progress_update",
                        "agent": self.name,
                        "message": "模型响应不稳定，正在自动重试...",
                        "progress": None,
                        "retry_attempt": attempt + 1,
                        "max_attempts": self.retry_config.max_retries + 1,
                    })
                except Exception:
                    pass

                await asyncio.sleep(wait_time)
                current_delay *= self.retry_config.backoff
        
        logger.error(f"[{self.name}] LLM call failed after {attempts_made} attempts")
        raise last_error

    async def _stream_response_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> AsyncGenerator[str, None]:
        """对流式响应在建立阶段和传输阶段都提供重试与续传兜底。"""
        start_time = time.time()
        last_error: Optional[Exception] = None
        current_delay = self.retry_config.delay
        max_retries = max(int(self.retry_config.max_retries or 0), 1)
        base_messages = [dict(message) for message in messages]
        visible_text = ""

        for attempt in range(max_retries + 1):
            try:
                attempt_base_text = visible_text
                usage_collector: Dict[str, Any] = {}
                stream = await self._call_llm_internal(
                    base_messages if not visible_text else self._build_stream_resume_messages(base_messages, visible_text),
                    temperature,
                    max_tokens,
                    True,
                    usage_collector=usage_collector,
                )

                continuation_raw = ""
                continuation_visible = ""
                async for chunk in stream:
                    if not chunk:
                        continue

                    if not attempt_base_text:
                        visible_text += chunk
                        yield chunk
                        continue

                    continuation_raw += chunk
                    candidate_visible = self._strip_stream_overlap(attempt_base_text, continuation_raw)
                    delta = candidate_visible[len(continuation_visible):]
                    if not delta:
                        continue

                    continuation_visible = candidate_visible
                    visible_text = attempt_base_text + continuation_visible
                    yield delta

                duration = time.time() - start_time
                metric_messages = [{"role": "system", "content": self.system_prompt}] + base_messages
                tokens_in, tokens_out = extract_token_usage(
                    usage_collector.get("usage"),
                    fallback_tokens_in=estimate_tokens_from_messages(metric_messages),
                    fallback_tokens_out=estimate_tokens_from_text(visible_text),
                )
                self.metrics.record_call(
                    agent_name=self.name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    duration=duration,
                    success=True,
                    method="call_llm_stream",
                )
                try:
                    record_token_usage(
                        agent_name=self.name,
                        model=self._get_model_name(),
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        success=True,
                        method="call_llm_stream",
                        duration=duration,
                    )
                except Exception as sqlite_err:
                    logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {sqlite_err}")
                return
            except Exception as e:
                last_error = e
                if attempt >= max_retries or not self._is_retryable_stream_error(e):
                    duration = time.time() - start_time
                    metric_messages = [{"role": "system", "content": self.system_prompt}] + base_messages
                    tokens_in = estimate_tokens_from_messages(metric_messages)
                    self.metrics.record_call(
                        agent_name=self.name,
                        tokens_in=tokens_in,
                        tokens_out=estimate_tokens_from_text(visible_text),
                        duration=duration,
                        success=False,
                        error=str(e),
                        method="call_llm_stream",
                    )
                    try:
                        record_token_usage(
                            agent_name=self.name,
                            model=self._get_model_name(),
                            tokens_in=tokens_in,
                            tokens_out=estimate_tokens_from_text(visible_text),
                            success=False,
                            method="call_llm_stream",
                            duration=duration,
                        )
                    except Exception as sqlite_err:
                        logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {sqlite_err}")
                    logger.error(
                        f"[{self.name}] Stream failed after {attempt + 1}/{max_retries + 1} attempts: {e}"
                    )
                    raise

                wait_time = min(current_delay, self.retry_config.max_delay)
                if self.retry_config.jitter:
                    import random
                    jitter_min, jitter_max = RETRY_DEFAULTS.JITTER_RANGE
                    wait_time *= random.uniform(jitter_min, jitter_max)

                retry_mode = "resume" if visible_text else "restart"
                logger.warning(
                    f"[{self.name}] Stream failed (attempt {attempt + 1}/{max_retries + 1}, mode={retry_mode}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                current_delay *= self.retry_config.backoff

        raise last_error  # pragma: no cover
    
    async def _call_llm_internal(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """内部LLM调用实现"""
        # 对于非 openai_chat 类型，委托给 LLMClient 处理
        if self._api_type != 'openai_chat':
            llm_client = self._get_or_create_llm_client()
            return await llm_client.call(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=self.system_prompt,
                stream=stream,
                enable_retry=False,  # BaseAgent 自己处理重试
                usage_collector=usage_collector,
            )
        
        start_time = time.time()
        
        # 注入系统提示词
        full_messages = self._build_openai_chat_messages(messages)

        resolved_max_tokens = normalize_max_tokens(
            max_tokens if max_tokens is not None else self._get_max_tokens(),
            source=self.name,
        )

        params = {
            "model": self._get_model_name(),
            "messages": full_messages,
            "stream": stream
        }
        add_temperature_param(
            params,
            model=params["model"],
            temperature=temperature if temperature is not None else self._get_temperature(),
            source=self.name,
        )
        if not self._should_omit_max_tokens():
            params["max_tokens"] = resolved_max_tokens
        
        # 诊断日志：记录请求详情
        api_base = self.model_config.api_base or config.llm.api_base
        total_chars = sum(len(m.get("content", "")) for m in full_messages)
        logger.info(
            f"[{self.name}] Calling LLM - Model: {params['model']}, "
            f"API: {api_base}, Messages: {len(full_messages)}, "
            f"Total chars: {total_chars}, Max tokens: {params.get('max_tokens', 'provider_default')}, "
            f"Stream requested: {stream}, Callback stream: {self._should_prefer_streaming_requests()}"
        )
        
        try:
            if stream:
                return self._stream_response(params, usage_collector=usage_collector)
            else:
                if self._should_prefer_streaming_requests():
                    usage_collector = {}
                    content = await self._collect_stream_response_text(
                        params,
                        emit_callback=True,
                        usage_collector=usage_collector,
                    )
                    duration = time.time() - start_time
                    tokens_in, tokens_out = extract_token_usage(
                        usage_collector.get("usage"),
                        fallback_tokens_in=estimate_tokens_from_messages(params.get("messages", [])),
                        fallback_tokens_out=estimate_tokens_from_text(content),
                    )
                    self.metrics.record_call(
                        agent_name=self.name,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        duration=duration,
                        success=True,
                        method="call_llm_stream_aggregated"
                    )
                    try:
                        record_token_usage(
                            agent_name=self.name,
                            model=params['model'],
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            success=True,
                            method="call_llm_stream_aggregated",
                            duration=duration
                        )
                    except Exception as sqlite_err:
                        logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {sqlite_err}")
                    logger.info(
                        f"[{self.name}] Received aggregated streamed response: {len(content)} chars, "
                        f"time: {duration:.2f}s"
                    )
                    if not content.strip():
                        from ..utils.retry import EmptyResponseError
                        raise EmptyResponseError(f"[{self.name}] LLM 流式返回空内容")
                    return content
                try:
                    response = await self._create_chat_completion_with_rotation(params)
                except Exception as create_error:
                    retry_params = self._temperatureless_retry_params(params, create_error)
                    if retry_params is not None:
                        response = await self._create_chat_completion_with_rotation(retry_params)
                    elif self._should_force_stream_fallback(create_error, stream=stream):
                        logger.warning(
                            f"[{self.name}] Non-stream request rejected by provider, retrying with streaming fallback"
                        )
                        usage_collector = {}
                        content = await self._collect_stream_response_text(params, usage_collector=usage_collector)
                        duration = time.time() - start_time
                        tokens_in, tokens_out = extract_token_usage(
                            usage_collector.get("usage"),
                            fallback_tokens_in=estimate_tokens_from_messages(params.get("messages", [])),
                            fallback_tokens_out=estimate_tokens_from_text(content),
                        )
                        self.metrics.record_call(
                            agent_name=self.name,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            duration=duration,
                            success=True,
                            method="call_llm_stream_fallback"
                        )
                        try:
                            record_token_usage(
                                agent_name=self.name,
                                model=params['model'],
                                tokens_in=tokens_in,
                                tokens_out=tokens_out,
                                success=True,
                                method="call_llm_stream_fallback",
                                duration=duration
                            )
                        except Exception as sqlite_err:
                            logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {sqlite_err}")
                        logger.info(
                            f"[{self.name}] Received streamed fallback response: {len(content)} chars, "
                            f"time: {duration:.2f}s"
                        )
                        return content
                    else:
                        raise
                
                # 验证响应格式
                if isinstance(response, str):
                    logger.error(f"[{self.name}] API返回了字符串而不是对象: {response[:200]}")
                    raise Exception(f"API返回格式错误: {response[:200]}")
                
                if not hasattr(response, 'choices') or not response.choices:
                    logger.error(f"[{self.name}] API响应缺少choices字段: {response}")
                    raise Exception(f"API响应格式错误，缺少choices字段")
                
                content = response.choices[0].message.content
                
                # 处理content为None的情况（某些模型可能返回None，如refusal/tool_calls）
                if content is None:
                    refusal = getattr(response.choices[0].message, 'refusal', None)
                    if refusal:
                        content = refusal
                        logger.warning(
                            f"[{self.name}] LLM returned refusal: '{content[:100]}'"
                        )
                    else:
                        from ..utils.retry import EmptyResponseError
                        logger.warning(f"[{self.name}] LLM returned empty content, will retry")
                        raise EmptyResponseError(f"[{self.name}] LLM 返回空内容")

                if not content.strip():
                    from ..utils.retry import EmptyResponseError
                    logger.warning(f"[{self.name}] LLM returned blank content, will retry")
                    raise EmptyResponseError(f"[{self.name}] LLM 返回空白内容")
                
                # 计算token使用
                usage = getattr(response, 'usage', None)
                tokens_in, tokens_out = extract_token_usage(
                    usage,
                    fallback_tokens_in=estimate_tokens_from_messages(full_messages),
                    fallback_tokens_out=estimate_tokens_from_text(content),
                )
                
                # 记录指标（内存）
                duration = time.time() - start_time
                self.metrics.record_call(
                    agent_name=self.name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    duration=duration,
                    success=True,
                    method="call_llm"
                )
                
                # 记录到SQLite持久化存储
                try:
                    record_token_usage(
                        agent_name=self.name,
                        model=params['model'],
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        success=True,
                        method="call_llm",
                        duration=duration
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {e}")
                
                logger.info(
                    f"[{self.name}] Received response: {len(content)} chars, "
                    f"tokens: {tokens_in}+{tokens_out}, time: {duration:.2f}s"
                )
                return content
                
        except Exception as e:
            # 记录失败指标（内存）
            duration = time.time() - start_time
            self.metrics.record_call(
                agent_name=self.name,
                duration=duration,
                success=False,
                error=str(e),
                method="call_llm"
            )
            
            # 记录失败到SQLite持久化存储
            try:
                record_token_usage(
                    agent_name=self.name,
                    model=params.get('model', ''),
                    tokens_in=estimate_tokens_from_messages(params.get("messages", [])),
                    tokens_out=0,
                    success=False,
                    method="call_llm",
                    duration=duration
                )
            except Exception as sqlite_err:
                logger.warning(f"[{self.name}] Failed to record token usage to SQLite: {sqlite_err}")
            
            # 增强错误诊断日志
            error_type = type(e).__name__
            api_base = self.model_config.api_base or config.llm.api_base
            model_name = params.get('model', 'unknown')
            error_msg = str(e)
            
            # 解析常见错误并提供用户友好的提示
            user_friendly_msg = self._parse_api_error(error_msg, model_name, api_base)
            
            logger.error(
                f"[{self.name}] LLM call failed after {duration:.2f}s - "
                f"Error type: {error_type}, Message: {e}, "
                f"API: {api_base}, Model: {model_name}"
            )
            
            # 抛出更友好的错误消息
            if user_friendly_msg:
                raise Exception(user_friendly_msg) from e
            raise

    def _should_prefer_streaming_requests(self) -> bool:
        """在存在上游回调时优先使用 provider 流式请求。"""
        return self.callback_handler is not None

    @staticmethod
    def _should_force_stream_fallback(error: Exception, *, stream: bool) -> bool:
        """识别需要改用流式请求的提供商错误。"""
        if stream:
            return False
        error_lower = str(error or "").lower()
        return (
            "streaming is required" in error_lower
            or ("longer than 10 minutes" in error_lower and "stream" in error_lower)
        )

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        """识别适合自动重试的传输/服务端错误。"""
        from ..utils.retry import is_retryable_error
        return is_retryable_error(error)

    _is_retryable_stream_error = _is_retryable_error

    @staticmethod
    def _is_stream_options_unsupported(error: Exception) -> bool:
        """识别不支持 stream_options.include_usage 的 OpenAI 兼容接口。"""
        error_lower = str(error or "").lower()
        return (
            "stream_options" in error_lower
            and any(token in error_lower for token in ("unsupported", "unknown", "extra", "unrecognized", "not allowed", "unexpected", "invalid"))
        )

    @staticmethod
    def _is_request_blocked_error(error: Exception) -> bool:
        """识别中转/网关对请求体的泛化阻断。"""
        error_lower = str(error or "").lower()
        return any(
            token in error_lower
            for token in (
                "request was blocked",
                "your request was blocked",
                "403",
                "forbidden",
                "permissiondenied",
                "permission denied",
            )
        )

    @classmethod
    def _should_retry_stream_without_options(cls, error: Exception) -> bool:
        """部分 OpenAI 兼容中转会把 stream_options 直接泛化成 403 blocked。"""
        return cls._is_stream_options_unsupported(error) or cls._is_request_blocked_error(error)

    def _should_include_stream_options(self) -> bool:
        """是否在流式请求中附加用量统计参数。"""
        if self._is_tsc5_api_base():
            return False
        return True

    @staticmethod
    def _extract_chat_completion_content(response: Any) -> str:
        """从非流式 Chat Completion 响应中提取正文，兼容 SDK 对象和 dict。"""
        if isinstance(response, str):
            return response
        choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
        if not choices:
            raise Exception("API响应格式错误，缺少choices字段")
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        if message is None:
            raise Exception("API响应格式错误，缺少message字段")
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if content is None:
            content = message.get("refusal") if isinstance(message, dict) else getattr(message, "refusal", None)
        return str(content or "")

    async def _yield_non_stream_fallback(
        self,
        params: dict,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式请求被中转阻断时，退回非流式请求并一次性产出文本。"""
        fallback_params = dict(params)
        fallback_params["stream"] = False
        fallback_params.pop("stream_options", None)
        logger.warning(
            f"[{self.name}] Streaming request was blocked by provider; retrying once without stream"
        )
        response = await self._create_chat_completion_with_rotation(fallback_params)
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        if usage is not None and usage_collector is not None:
            usage_collector["usage"] = usage
        content = self._extract_chat_completion_content(response)
        if not content.strip():
            from ..utils.retry import EmptyResponseError
            raise EmptyResponseError(f"[{self.name}] LLM 非流式兜底返回空内容")
        yield content

    @staticmethod
    def _strip_stream_overlap(existing_text: str, incoming_text: str, max_overlap: int = 256) -> str:
        """去掉续传内容与已输出尾部的重叠前缀，避免重复显示。"""
        if not existing_text or not incoming_text:
            return incoming_text

        search_limit = min(len(existing_text), len(incoming_text), max_overlap)
        for overlap in range(search_limit, 0, -1):
            if existing_text.endswith(incoming_text[:overlap]):
                return incoming_text[overlap:]
        return incoming_text

    @staticmethod
    def _build_stream_resume_messages(
        messages: List[Dict[str, str]],
        partial_text: str,
        *,
        tail_chars: int = 2000,
    ) -> List[Dict[str, str]]:
        """构造续传提示，让模型从已输出内容后自然接写。"""
        safe_partial = (partial_text or "")[-tail_chars:]
        resume_instruction = (
            "上一次回答因流式传输中断。请严格从上面 assistant 已输出内容的末尾自然继续，"
            "不要重复已有文字，不要重写开头，也不要解释中断原因，直接继续输出剩余内容。"
        )
        resumed_messages = [dict(message) for message in messages]
        if safe_partial:
            resumed_messages.append({"role": "assistant", "content": safe_partial})
        resumed_messages.append({"role": "user", "content": resume_instruction})
        return resumed_messages

    async def _collect_stream_response_text(
        self,
        params: Dict[str, Any],
        emit_callback: bool = False,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> str:
        """将流式响应聚合成普通文本，供非流式调用兜底使用。"""
        stream_params = dict(params)
        stream_params["stream"] = True
        chunks: List[str] = []
        async for chunk in self._stream_response(stream_params, usage_collector=usage_collector):
            if chunk:
                chunks.append(chunk)
                if emit_callback:
                    await self._emit_callback_event({
                        "type": "llm_chunk",
                        "agent": self.name,
                        "content": chunk,
                        "delta": chunk,
                    })
        return "".join(chunks)

    async def _emit_callback_event(self, data: Dict[str, Any]) -> Optional[Any]:
        """向回调处理器发送任意事件。"""
        if not self.callback_handler:
            return None
        try:
            return await self.callback_handler(data)
        except Exception as e:
            logger.warning(f"[{self.name}] Callback event failed: {e}")
            return None
    
    def _parse_api_error(self, error_msg: str, model_name: str, api_base: str) -> Optional[str]:
        """
        解析API错误并返回用户友好的提示消息（增强版）
        
        改进：
        - 更详细的错误分类
        - 提供具体的解决方案
        - 友好的格式化输出
        
        Args:
            error_msg: 原始错误消息
            model_name: 使用的模型名称
            api_base: API基础URL
            
        Returns:
            用户友好的错误消息，如果无法解析则返回None
        """
        error_lower = error_msg.lower()

        # 检查是否是服务商拒绝/权限阻断。
        # OpenAI SDK 的 PermissionDeniedError 在部分兼容接口中只暴露
        # "Your request was blocked."，没有保留 HTTP 403 文本，因此需要显式识别。
        if (
            "403" in error_msg
            or "forbidden" in error_lower
            or "permissiondenied" in error_lower
            or "permission denied" in error_lower
            or "request was blocked" in error_lower
            or "your request was blocked" in error_lower
            or "model_not_allowed" in error_lower
        ):
            return (
                f"🚫 模型服务拒绝了本次请求\n\n"
                f"当前Agent：{self.name}\n"
                f"模型：{model_name}\n"
                f"API地址：{api_base}\n\n"
                f"❌ 可能原因：\n"
                f"  • 当前Agent绑定的API Key没有该模型的调用权限\n"
                f"  • 当前Agent绑定的模型在该中转服务中不可用\n"
                f"  • 请求内容触发了服务商的风控或内容过滤\n"
                f"  • 中转服务临时拦截了该来源或该请求\n\n"
                f"💡 解决方案：\n"
                f"  1. 在模型设置中检查“{self.name}”的独立模型配置\n"
                f"  2. 用该配置执行一次连接测试，确认模型可用\n"
                f"  3. 只在需要时切换这个Agent的模型或API配置，不必强制所有Agent统一\n"
                f"  4. 如果连接测试通过但聊天仍被拦截，尝试调整输入表述后重试"
            )
        
        # 检查是否是模型不存在错误（Google API 404）
        if "404" in error_msg or "not found" in error_lower or "not_found" in error_lower:
            if "entity" in error_lower or "model" in error_lower or "requested" in error_lower:
                return (
                    f"🤖 模型不可用\n\n"
                    f"模型名称：{model_name}\n"
                    f"API地址：{api_base}\n\n"
                    f"❌ 可能原因：\n"
                    f"  • 模型名称不正确或已更改\n"
                    f"  • 代理服务器暂时无法访问该模型\n"
                    f"  • API配额已用完或权限不足\n\n"
                    f"💡 解决方案：\n"
                    f"  1. 在设置中切换到其他可用模型\n"
                    f"  2. 推荐模型：gemini-2.0-flash-exp, claude-3-5-sonnet\n"
                    f"  3. 检查API密钥是否有该模型的访问权限"
                )
        
        # 检查是否是认证错误
        if "401" in error_msg or "unauthorized" in error_lower or ("invalid" in error_lower and "key" in error_lower):
            return (
                f"🔑 API认证失败\n\n"
                f"API地址：{api_base}\n\n"
                f"❌ 可能原因：\n"
                f"  • API密钥未配置或格式错误\n"
                f"  • API密钥已过期或被撤销\n"
                f"  • 密钥权限不足\n\n"
                f"💡 解决方案：\n"
                f"  1. 检查.env文件中的API密钥配置\n"
                f"  2. 确认密钥格式正确（无多余空格）\n"
                f"  3. 在API提供商网站重新生成密钥"
            )
        
        # 检查是否是配额限制
        if "429" in error_msg or "rate limit" in error_lower or "quota" in error_lower:
            return (
                f"⏱️ API请求限制\n\n"
                f"模型：{model_name}\n\n"
                f"❌ 可能原因：\n"
                f"  • 请求频率超过限制（每分钟/每天）\n"
                f"  • 免费配额已用完\n"
                f"  • 并发请求数超限\n\n"
                f"💡 解决方案：\n"
                f"  1. 等待1-2分钟后重试\n"
                f"  2. 切换到其他模型分散负载\n"
                f"  3. 升级API套餐获取更高配额\n"
                f"  4. 检查是否有其他程序在使用同一API密钥"
            )
        
        # 检查是否是超时
        if "timeout" in error_lower or "timed out" in error_lower:
            return (
                f"⏰ 请求超时\n\n"
                f"模型：{model_name}\n"
                f"API地址：{api_base}\n\n"
                f"❌ 可能原因：\n"
                f"  • 网络连接不稳定\n"
                f"  • API服务器响应慢\n"
                f"  • 请求内容过长导致处理时间长\n\n"
                f"💡 解决方案：\n"
                f"  1. 检查网络连接状态\n"
                f"  2. 稍后重试（服务器可能繁忙）\n"
                f"  3. 减少单次请求的内容长度\n"
                f"  4. 切换到响应更快的模型"
            )
        
        # 检查是否是连接错误
        if "connection" in error_lower or "connect" in error_lower:
            return (
                f"🌐 网络连接失败\n\n"
                f"API地址：{api_base}\n\n"
                f"❌ 可能原因：\n"
                f"  • 本地网络断开或不稳定\n"
                f"  • 代理服务器未启动或配置错误\n"
                f"  • API服务器暂时不可用\n"
                f"  • 防火墙阻止了连接\n\n"
                f"💡 解决方案：\n"
                f"  1. 检查网络连接（尝试访问其他网站）\n"
                f"  2. 确认代理服务器已启动（如使用代理）\n"
                f"  3. 检查API地址是否正确\n"
                f"  4. 尝试关闭VPN或防火墙后重试"
            )
        
        # 检查是否是内容过滤错误
        if "content" in error_lower and ("filter" in error_lower or "policy" in error_lower or "safety" in error_lower):
            return (
                f"🛡️ 内容安全检查\n\n"
                f"❌ 您的请求或生成的内容触发了安全策略\n\n"
                f"💡 解决方案：\n"
                f"  1. 调整您的输入内容，避免敏感话题\n"
                f"  2. 使用更中性的表达方式\n"
                f"  3. 切换到其他模型（不同模型的安全策略不同）"
            )
        
        # 检查是否是token超限
        if "token" in error_lower and ("limit" in error_lower or "exceed" in error_lower or "maximum" in error_lower):
            return (
                f"📏 内容长度超限\n\n"
                f"模型：{model_name}\n\n"
                f"❌ 请求或响应的token数量超过模型限制\n\n"
                f"💡 解决方案：\n"
                f"  1. 减少输入内容的长度\n"
                f"  2. 分段处理长文本\n"
                f"  3. 切换到支持更长上下文的模型\n"
                f"  4. 在设置中降低max_tokens参数"
            )
        
        return None
    
    async def _stream_response(
        self,
        params: dict,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式响应生成器"""
        try:
            request_params = dict(params)
            if (
                request_params.get("stream")
                and "stream_options" not in request_params
                and self._should_include_stream_options()
            ):
                request_params["stream_options"] = {"include_usage": True}
            try:
                response = await self._create_chat_completion_with_rotation(request_params)
            except Exception as exc:
                retry_params = self._temperatureless_retry_params(request_params, exc)
                if retry_params is not None:
                    request_params = retry_params
                    response = await self._create_chat_completion_with_rotation(request_params)
                elif "stream_options" in request_params and self._should_retry_stream_without_options(exc):
                    logger.info(
                        f"[{self.name}] 当前模型接口不兼容 stream_options.include_usage，退回普通流式请求"
                    )
                    if usage_collector is not None:
                        usage_collector["usage_unavailable_reason"] = "stream_options_unsupported"
                    request_params.pop("stream_options", None)
                    try:
                        response = await self._create_chat_completion_with_rotation(request_params)
                    except Exception as retry_exc:
                        if self._is_request_blocked_error(retry_exc):
                            async for chunk in self._yield_non_stream_fallback(params, usage_collector=usage_collector):
                                yield chunk
                            return
                        raise
                elif self._is_request_blocked_error(exc):
                    async for chunk in self._yield_non_stream_fallback(params, usage_collector=usage_collector):
                        yield chunk
                    return
                else:
                    raise

            # 验证响应是否是流式生成器
            if isinstance(response, str):
                logger.error(f"[{self.name}] 流式API返回了字符串: {response[:200]}")
                raise Exception(f"流式API返回格式错误: {response[:200]}")
            
            chunk_count = 0
            async for chunk in response:
                chunk_count += 1
                if isinstance(chunk, str):
                    # 如果chunk是字符串，直接yield
                    yield chunk
                    continue

                usage = chunk.get("usage") if isinstance(chunk, dict) else getattr(chunk, "usage", None)
                if usage is not None and usage_collector is not None:
                    usage_collector["usage"] = usage

                choices = chunk.get("choices") if isinstance(chunk, dict) else getattr(chunk, "choices", None)
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, 'delta', None)
                content = delta.get("content") if isinstance(delta, dict) else getattr(delta, 'content', None) if delta is not None else None
                if content:
                    yield content
                    continue

                # 部分 OpenAI 兼容中转会发送 delta=None 或仅含 finish_reason 的收尾 chunk。
                # 这类 chunk 不应中断整个流式回复。
                finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else getattr(choice, 'finish_reason', None)
                if finish_reason:
                    logger.debug(f"[{self.name}] Stream choice finished: {finish_reason}")
                    continue
            
            if chunk_count == 0:
                logger.warning(f"[{self.name}] 流式响应没有产生任何chunk")
                
        except Exception as e:
            logger.error(f"[{self.name}] 流式响应处理失败: {e}")
            api_base = self.model_config.api_base or config.llm.api_base
            model_name = str(params.get("model") or "unknown")
            user_friendly_msg = self._parse_api_error(
                f"{type(e).__name__}: {e}",
                model_name,
                api_base,
            )
            if user_friendly_msg:
                raise Exception(user_friendly_msg) from e
            raise
    
    def inject_context(self, base_prompt: str, context: Dict[str, Any]) -> str:
        """
        注入上下文到提示词
        
        Args:
            base_prompt: 基础提示词
            context: 上下文字典
            
        Returns:
            注入上下文后的提示词
        """
        result = base_prompt
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"  # {{key}} 格式
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=2)
            result = result.replace(placeholder, str(value))
        return result
    
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行Agent任务(子类实现)
        
        Args:
            input_data: 输入数据
            context: 上下文信息
            
        Returns:
            执行结果
        """
        pass

    # ==================== 能力声明接口 ====================

    def get_capabilities(self) -> AgentCapability:
        """
        获取Agent标准能力声明。
        
        默认实现尽量保守，保证现有子类不改代码也可接入能力注册表。
        子类后续可按需重写，补充更准确的任务类型、输入输出与优先级。
        """
        return AgentCapability(
            agent_name=self.name,
            capabilities=[],
            accept_task_types=[],
            required_inputs=[],
            produced_outputs=[],
            priority=50,
            max_concurrency=1,
            metadata={
                "prompt_file": self.prompt_file or "",
                "agent_class": self.__class__.__name__,
            },
        )

    def accepts_task(self, task: Dict[str, Any]) -> bool:
        """
        判断当前Agent是否接受某类任务。
        
        默认规则：
        - 若能力声明未配置 `accept_task_types`，返回 False，避免误接单
        - 支持匹配 `task_type`
        """
        capability = self.get_capabilities()
        task_type = str((task or {}).get("task_type") or "").strip()
        if not task_type:
            return False
        accepted_types = {
            str(item).strip()
            for item in capability.accept_task_types
            if str(item).strip()
        }
        return task_type in accepted_types

    def estimate_cost(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        估算任务执行成本。
        
        当前为轻量默认实现，后续可被具体Agent覆盖。
        """
        capability = self.get_capabilities()
        task_type = str((task or {}).get("task_type") or "").strip()
        return {
            "agent_name": self.name,
            "task_type": task_type,
            "priority": capability.priority,
            "max_concurrency": capability.max_concurrency,
            "estimated_tokens": 0,
            "estimated_seconds": 0,
            "confidence": 0.3 if self.accepts_task(task) else 0.0,
        }

    def requires_inputs(self, task: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        返回任务所需输入字段。
        
        默认直接读取能力声明。
        """
        capability = self.get_capabilities()
        return [
            str(item).strip()
            for item in capability.required_inputs
            if str(item).strip()
        ]

    def produces_outputs(self, task: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        返回任务产出字段。
        
        默认直接读取能力声明。
        """
        capability = self.get_capabilities()
        return [
            str(item).strip()
            for item in capability.produced_outputs
            if str(item).strip()
        ]
    
    # ==================== 回调机制 ====================
    
    async def request_user_input(
        self,
        question: str,
        options: Optional[List[str]] = None,
        input_type: str = "text",
        timeout: float = TIMEOUTS.AGENT_DEFAULT
    ) -> Optional[str]:
        """
        请求用户输入（通过回调处理器）
        
        Args:
            question: 问题内容
            options: 可选项列表
            input_type: 输入类型 ("text", "select", "confirm")
            timeout: 超时时间（秒）
            
        Returns:
            用户输入，超时或无回调处理器返回None
        """
        if not self.callback_handler:
            logger.warning(f"[{self.name}] No callback handler set, cannot request user input")
            return None
        
        try:
            result = await self.callback_handler({
                "type": "user_input_required",
                "agent": self.name,
                "question": question,
                "options": options,
                "input_type": input_type
            })
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Callback handler error: {e}")
            return None
    
    async def notify_progress(
        self,
        message: str,
        progress: float = 0,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        通知进度更新
        
        Args:
            message: 进度消息
            progress: 进度百分比 (0-100)
            data: 附加数据
        """
        await self._emit_callback_event({
            "type": "progress_update",
            "agent": self.name,
            "message": message,
            "progress": progress,
            "data": data
        })
    
    # ==================== 消息总线集成 ====================
    
    async def send_message(
        self,
        receiver: str,
        msg_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        发送消息到其他Agent
        
        Args:
            receiver: 接收者名称
            msg_type: 消息类型
            payload: 消息内容
        """
        from .message_bus import AgentMessage, MessageType
        
        # 确保已订阅
        await self.ensure_subscribed()
        
        try:
            message = AgentMessage(
                msg_type=MessageType(msg_type),
                sender=self.name,
                receiver=receiver,
                payload=payload
            )
            await self.message_bus.publish(message)
        except Exception as e:
            logger.error(f"[{self.name}] Failed to send message: {e}")
    
    async def send_task(
        self,
        receiver: str,
        task_type: str,
        task_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        timeout: float = TIMEOUTS.AGENT_DEFAULT
    ) -> Optional[Dict[str, Any]]:
        """
        发送任务并等待响应
        
        Args:
            receiver: 接收者Agent名称
            task_type: 任务类型
            task_data: 任务数据
            context: 上下文信息
            timeout: 超时时间（秒）
            
        Returns:
            任务结果，超时返回None
        """
        from .message_bus import AgentMessage, MessageType, create_task_message
        
        # 确保已订阅
        await self.ensure_subscribed()
        
        # 创建任务消息
        message = create_task_message(
            sender=self.name,
            receiver=receiver,
            task_type=task_type,
            task_data=task_data
        )
        
        if context:
            message.payload["context"] = context
        
        # 发送并等待响应
        response = await self.message_bus.request(message, timeout=timeout)
        
        if response:
            return response.payload.get("result")
        
        logger.warning(f"[{self.name}] Task to {receiver} timed out after {timeout}s")
        return None

    async def send_task_stream(
        self,
        receiver: str,
        task_type: str,
        task_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        timeout: float = TIMEOUTS.AGENT_DEFAULT
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送任务并流式接收中间事件与最终结果。

        Yields:
            dict: 标准化后的消息总线事件
        """
        from .message_bus import MessageType, create_task_message

        await self.ensure_subscribed()

        message = create_task_message(
            sender=self.name,
            receiver=receiver,
            task_type=task_type,
            task_data=task_data
        )

        if context:
            message.payload["context"] = context

        async for response in self.message_bus.request_stream(message, timeout=timeout):
            yield {
                "message_id": response.id,
                "reply_to": response.reply_to,
                "sender": response.sender,
                "receiver": response.receiver,
                "msg_type": response.msg_type.value,
                "payload": dict(response.payload or {}),
                "is_terminal": response.msg_type in {
                    MessageType.TASK_COMPLETED,
                    MessageType.TASK_FAILED,
                    MessageType.CONTEXT_UPDATED,
                }
            }
    
    async def broadcast(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """
        广播消息给所有Agent
        
        Args:
            msg_type: 消息类型
            payload: 消息内容
        """
        await self.send_message("*", msg_type, payload)
    
    async def request_user_input_via_bus(
        self,
        question: str,
        options: Optional[List[str]] = None,
        input_type: str = "text",
        timeout: float = TIMEOUTS.AGENT_DEFAULT
    ) -> Optional[str]:
        """
        通过消息总线请求用户输入
        
        Args:
            question: 问题内容
            options: 可选项列表
            input_type: 输入类型
            timeout: 超时时间
            
        Returns:
            用户输入，超时返回None
        """
        from .message_bus import create_user_input_request
        import asyncio
        
        # 确保已订阅
        await self.ensure_subscribed()
        
        # 创建请求消息
        message = create_user_input_request(
            sender=self.name,
            question=question,
            options=options,
            input_type=input_type
        )
        
        # 创建Future等待响应
        future: asyncio.Future = asyncio.Future()
        self._pending_responses[message.id] = future
        
        try:
            # 发送请求
            await self.message_bus.publish(message)
            
            # 等待响应
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] User input request timed out")
            return None
        finally:
            self._pending_responses.pop(message.id, None)
    
    # ==================== Skill 系统集成 ====================

    def use_skill(self, skill_name: str, method: str, **kwargs):
        """
        使用 Skill
        
        Args:
            skill_name: Skill 名称（如 "trends_search"）
            method: 要调用的方法名（如 "get_weibo_trending"）
            **kwargs: 方法参数
            
        Returns:
            {"success": bool, "data": Any, "error": str}
        """
        try:
            from ..constants import get_data_dir, get_skills_dir

            # 检查Skill是否启用
            config_path = get_data_dir() / "skills_config.json"
            if config_path.exists():
                import json
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    enabled_skills = config.get("enabled_skills", {})
                    if not enabled_skills.get(skill_name, False):
                        logger.warning(f"[{self.name}] Skill '{skill_name}' is not enabled")
                        return {"success": False, "error": f"Skill '{skill_name}' is not enabled"}
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to load skills config: {e}")
            
            # 动态导入 Skill
            # 将 skill_name 中的 "-" 转换为 "_" 用于目录名
            skill_dir_name = skill_name.replace("-", "_")
            skill_path = get_skills_dir() / skill_dir_name / "scripts"
            
            if not skill_path.exists():
                logger.error(f"[{self.name}] Skill directory not found: {skill_path}")
                return {"success": False, "error": f"Skill '{skill_name}' not found"}
            
            # 查找服务文件
            service_file = None
            for f in skill_path.glob("*_service.py"):
                service_file = f
                break
            
            if not service_file:
                logger.error(f"[{self.name}] No service file found in {skill_path}")
                return {"success": False, "error": f"Skill '{skill_name}' service not found"}
            
            # 导入模块
            import importlib.util
            import sys
            
            module_name = f"{skill_dir_name}_service"
            
            # 如果模块已经加载，重新加载以获取最新版本
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                spec = importlib.util.spec_from_file_location(module_name, service_file)
                if spec is None or spec.loader is None:
                    return {"success": False, "error": f"Failed to load module spec for {skill_name}"}
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            
            # 获取服务实例
            if not hasattr(module, 'get_service'):
                logger.error(f"[{self.name}] Module {module_name} has no get_service function")
                return {"success": False, "error": f"Skill '{skill_name}' has no get_service function"}
            
            service = module.get_service()
            
            # 调用方法
            if not hasattr(service, method):
                logger.error(f"[{self.name}] Service has no method '{method}'")
                return {"success": False, "error": f"Method '{method}' not found in skill '{skill_name}'"}
            
            logger.info(f"[{self.name}] Calling skill: {skill_name}.{method}({kwargs})")
            result = getattr(service, method)(**kwargs)
            
            # 确保返回格式统一
            if isinstance(result, dict):
                return result
            else:
                return {"success": True, "data": result}
                
        except Exception as e:
            logger.error(f"[{self.name}] Failed to use skill {skill_name}.{method}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ==================== 指标获取 ====================
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取本Agent的指标统计"""
        agent_metrics = self.metrics.get_agent_metrics(self.name)
        if agent_metrics:
            return agent_metrics.to_dict()
        return {}


# 模块职责说明：Agent基类，实现LLM调用封装、上下文注入、回调机制、重试支持、指标收集和Skill系统集成。
