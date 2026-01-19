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
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable, Awaitable, Union
from pathlib import Path

from openai import AsyncOpenAI
import httpx

from ..config import config
from ..agent_config import AgentModelConfig, get_config_manager
from ..utils.retry import async_retry, RetryConfig
from ..utils.metrics import get_metrics_collector, MetricsContext
from ..utils.mcp_manager import mcp_manager
from ..utils.token_stats import record_token_usage
from ..constants import TIMEOUTS, RETRY_DEFAULTS

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 回调处理器类型
CallbackHandler = Callable[[Dict[str, Any]], Awaitable[Optional[Any]]]


class BaseAgent(ABC):
    """
    Agent基类 - 支持独立模型配置
    
    增强功能：
    - 回调机制：支持请求用户输入
    - 重试支持：LLM调用自动重试
    - 指标收集：自动记录调用指标
    - 消息总线：支持Agent间通信
    """
    
    def __init__(
        self,
        name: str,
        prompt_file: Optional[str] = None,
        model_config: Optional[AgentModelConfig] = None,
        callback_handler: Optional[CallbackHandler] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        初始化Agent
        
        Args:
            name: Agent名称
            prompt_file: 系统提示词文件路径(相对于prompts目录)
            model_config: 可选的模型配置，如果不提供则从配置管理器加载
            callback_handler: 回调处理器，用于请求用户输入等
            retry_config: 重试配置
        """
        self.name = name
        self.prompt_file = prompt_file
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
        self.client = self._create_client()
        
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
    
    def _create_client(self) -> AsyncOpenAI:
        """创建OpenAI客户端"""
        # 优先使用Agent独立配置，否则使用全局配置
        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        
        # 设置较长的超时时间，适合大模型生成场景
        # connect: 连接超时, read: 读取超时, write: 写入超时, pool: 连接池超时
        timeout_config = httpx.Timeout(
            connect=60.0,      # 连接超时60秒
            read=600.0,        # 读取超时600秒（10分钟），适合长文本生成
            write=120.0,       # 写入超时120秒
            pool=60.0          # 连接池超时60秒
        )
        
        logger.info(f"[{self.name}] Creating OpenAI client: base_url={api_base}, timeout=read:600s, max_retries=0")
        
        return AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout_config,
            max_retries=0  # 禁用SDK内部重试，使用我们自己的重试逻辑
        )
    
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
    
    def update_config(self, **kwargs) -> None:
        """
        更新Agent配置并重新初始化客户端
        
        Args:
            **kwargs: 要更新的配置字段
        """
        manager = get_config_manager()
        self.model_config = manager.update_config(self.name, **kwargs)
        self.client = self._create_client()
        logger.info(f"[{self.name}] Config updated, model: {self._get_model_name()}")
    
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
                
                # 执行任务
                result = await self.execute(task_data, context)
                
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
        """加载系统提示词"""
        if not self.prompt_file:
            return self._get_default_prompt()
        
        prompt_path = config.paths.prompts_dir / self.prompt_file
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        else:
            logger.warning(f"Prompt file not found: {prompt_path}, using default")
            return self._get_default_prompt()
    
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
        
        last_error = None
        current_delay = self.retry_config.delay
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return await self._call_llm_internal(messages, temperature, max_tokens, stream)
            except Exception as e:
                last_error = e
                
                if attempt >= self.retry_config.max_retries:
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
                
                await asyncio.sleep(wait_time)
                current_delay *= self.retry_config.backoff
        
        # 所有重试失败
        logger.error(f"[{self.name}] LLM call failed after {self.retry_config.max_retries + 1} attempts")
        raise last_error
    
    async def _call_llm_internal(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool
    ) -> Union[str, AsyncGenerator[str, None]]:
        """内部LLM调用实现"""
        start_time = time.time()
        
        # 注入系统提示词
        full_messages = [
            {"role": "system", "content": self.system_prompt}
        ] + messages
        
        params = {
            "model": self._get_model_name(),
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self._get_temperature(),
            "max_tokens": max_tokens if max_tokens is not None else self._get_max_tokens(),
            "stream": stream
        }
        
        # 诊断日志：记录请求详情
        api_base = self.model_config.api_base or config.llm.api_base
        total_chars = sum(len(m.get("content", "")) for m in full_messages)
        logger.info(
            f"[{self.name}] Calling LLM - Model: {params['model']}, "
            f"API: {api_base}, Messages: {len(full_messages)}, "
            f"Total chars: {total_chars}, Max tokens: {params['max_tokens']}"
        )
        
        try:
            if stream:
                return self._stream_response(params)
            else:
                response = await self.client.chat.completions.create(**params)
                content = response.choices[0].message.content
                
                # 计算token使用
                usage = getattr(response, 'usage', None)
                tokens_in = usage.prompt_tokens if usage else 0
                tokens_out = usage.completion_tokens if usage else 0
                
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
                    tokens_in=0,
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
    
    def _parse_api_error(self, error_msg: str, model_name: str, api_base: str) -> Optional[str]:
        """
        解析API错误并返回用户友好的提示消息
        
        Args:
            error_msg: 原始错误消息
            model_name: 使用的模型名称
            api_base: API基础URL
            
        Returns:
            用户友好的错误消息，如果无法解析则返回None
        """
        error_lower = error_msg.lower()
        
        # 检查是否是模型不存在错误（Google API 404）
        if "404" in error_msg or "not found" in error_lower or "not_found" in error_lower:
            if "entity" in error_lower or "model" in error_lower or "requested" in error_lower:
                return (
                    f"模型 '{model_name}' 在API服务器上不可用。\n"
                    f"API地址: {api_base}\n"
                    f"可能原因:\n"
                    f"1. 模型名称不正确或已更改\n"
                    f"2. 代理服务器暂时无法访问该模型\n"
                    f"3. Google API 配额已用完\n"
                    f"建议: 请在设置中切换到其他可用模型（如 gemini-2.5-flash）"
                )
        
        # 检查是否是认证错误
        if "401" in error_msg or "unauthorized" in error_lower or "invalid" in error_lower and "key" in error_lower:
            return (
                f"API认证失败。\n"
                f"API地址: {api_base}\n"
                f"请检查API密钥是否正确配置。"
            )
        
        # 检查是否是配额限制
        if "429" in error_msg or "rate limit" in error_lower or "quota" in error_lower:
            return (
                f"API请求频率超限或配额已用完。\n"
                f"模型: {model_name}\n"
                f"请稍后重试，或切换到其他模型。"
            )
        
        # 检查是否是超时
        if "timeout" in error_lower or "timed out" in error_lower:
            return (
                f"API请求超时。\n"
                f"模型: {model_name}\n"
                f"API地址: {api_base}\n"
                f"可能原因: 网络问题或服务器响应慢，请稍后重试。"
            )
        
        # 检查是否是连接错误
        if "connection" in error_lower or "connect" in error_lower:
            return (
                f"无法连接到API服务器。\n"
                f"API地址: {api_base}\n"
                f"请检查:\n"
                f"1. 网络连接是否正常\n"
                f"2. 代理服务器是否已启动\n"
                f"3. API地址是否正确"
            )
        
        return None
    
    async def _stream_response(self, params: dict) -> AsyncGenerator[str, None]:
        """流式响应生成器"""
        response = await self.client.chat.completions.create(**params)
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
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
        if self.callback_handler:
            try:
                await self.callback_handler({
                    "type": "progress_update",
                    "agent": self.name,
                    "message": message,
                    "progress": progress,
                    "data": data
                })
            except Exception as e:
                logger.warning(f"[{self.name}] Progress notification failed: {e}")
    
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
    
    # ==================== MCP 工具集成 ====================

    async def use_mcp_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用MCP工具
        
        Args:
            server_name: MCP服务器名称 (如 "trends-hub")
            tool_name: 工具名称 (如 "get-weibo-trending")
            arguments: 工具参数
            
        Returns:
            工具调用结果
        """
        try:
            # 确保MCP管理器已初始化
            await mcp_manager.initialize()
            
            # 调用工具
            logger.info(f"[{self.name}] Calling MCP tool {tool_name} on {server_name}")
            result = await mcp_manager.call_tool(server_name, tool_name, arguments)
            
            # 记录指标
            self.metrics.record_call(
                agent_name=self.name,
                duration=0,  # 简化处理，暂不记录详细时间
                success=True,
                method=f"mcp_tool:{server_name}:{tool_name}"
            )
            
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Failed to call MCP tool {tool_name}: {e}")
            self.metrics.record_call(
                agent_name=self.name,
                duration=0,
                success=False,
                error=str(e),
                method=f"mcp_tool:{server_name}:{tool_name}"
            )
            raise

    async def get_available_mcp_tools(self) -> List[Dict]:
        """
        获取所有可用的MCP工具列表
        
        Returns:
            工具列表，每个工具包含 name, description, server_name 等字段
        """
        try:
            await mcp_manager.initialize()
            return await mcp_manager.get_all_tools()
        except Exception as e:
            logger.error(f"[{self.name}] Failed to get MCP tools: {e}")
            return []

    # ==================== 指标获取 ====================
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取本Agent的指标统计"""
        agent_metrics = self.metrics.get_agent_metrics(self.name)
        if agent_metrics:
            return agent_metrics.to_dict()
        return {}


# 模块职责说明：Agent基类，实现LLM调用封装、上下文注入、回调机制、重试支持、指标收集和MCP工具调用。
