"""
LLM客户端模块

封装OpenAI API调用，支持重试、指标收集和错误处理。
从BaseAgent中提取出来，实现单一职责。

模块职责说明：提供统一的LLM调用接口，包含重试、指标收集和错误处理。
"""

import time
import asyncio
import logging
import random
from typing import Optional, Dict, Any, List, Union, AsyncGenerator
from dataclasses import dataclass

from openai import AsyncOpenAI
import httpx

from ..config import config
from ..agent_config import AgentModelConfig
from ..constants import RETRY_DEFAULTS
from ..timeout_settings import get_llm_timeout_settings
from ..utils.llm_params import normalize_max_tokens
from ..utils.metrics import get_metrics_collector
from ..utils.token_stats import record_token_usage


logger = logging.getLogger(__name__)


def _is_retryable_error(error: Exception) -> bool:
    from ..utils.retry import is_retryable_error
    return is_retryable_error(error)


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = RETRY_DEFAULTS.MAX_RETRIES
    delay: float = RETRY_DEFAULTS.INITIAL_DELAY
    backoff: float = RETRY_DEFAULTS.BACKOFF_MULTIPLIER
    max_delay: float = RETRY_DEFAULTS.MAX_DELAY
    jitter: bool = True


@dataclass
class LLMCallResult:
    """LLM调用结果"""
    content: str
    tokens_in: int = 0
    tokens_out: int = 0
    duration: float = 0.0
    success: bool = True
    error: Optional[str] = None


class LLMClient:
    """
    LLM客户端

    封装OpenAI兼容API的调用，提供：
    - 自动重试机制
    - 指标收集
    - 错误处理和诊断
    - 流式输出支持
    """

    def __init__(
        self,
        model_config: AgentModelConfig,
        retry_config: Optional[RetryConfig] = None,
        metrics_namespace: str = "default"
    ):
        """
        初始化LLM客户端

        Args:
            model_config: 模型配置
            retry_config: 重试配置
            metrics_namespace: 指标命名空间（用于区分不同调用者）
        """
        self.model_config = model_config
        self.retry_config = retry_config or RetryConfig()
        self.metrics_namespace = metrics_namespace

        # 创建OpenAI客户端
        self._client = self._create_client()

        # 指标收集器
        self.metrics = get_metrics_collector()

    def _create_client(self) -> AsyncOpenAI:
        """创建OpenAI客户端"""
        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        llm_timeouts = get_llm_timeout_settings()

        timeout_config = httpx.Timeout(
            connect=float(llm_timeouts["connect"]),
            read=float(llm_timeouts["read"]),
            write=float(llm_timeouts["write"]),
            pool=float(llm_timeouts["pool"]),
        )

        logger.info(
            "[LLMClient:%s] Creating client: base_url=%s, timeout=connect:%ss/read:%ss/write:%ss/pool:%ss",
            self.metrics_namespace,
            api_base,
            llm_timeouts["connect"],
            llm_timeouts["read"],
            llm_timeouts["write"],
            llm_timeouts["pool"],
        )

        return AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout_config,
            max_retries=0  # 禁用SDK内部重试
        )

    @property
    def model_name(self) -> str:
        """获取模型名称"""
        return self.model_config.model or config.llm.model

    @property
    def temperature(self) -> float:
        """获取温度参数"""
        return self.model_config.temperature

    @property
    def max_tokens(self) -> int:
        """获取最大token数"""
        return self.model_config.max_tokens

    def update_config(self, model_config: AgentModelConfig) -> None:
        """更新配置并重建客户端"""
        self.model_config = model_config
        self._client = self._create_client()
        logger.info(f"[LLMClient:{self.metrics_namespace}] Config updated, model: {self.model_name}")

    async def call(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        enable_retry: bool = True
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        调用LLM

        Args:
            messages: 消息列表
            temperature: 温度参数（覆盖配置）
            max_tokens: 最大token数（覆盖配置）
            system_prompt: 系统提示词
            stream: 是否流式输出
            enable_retry: 是否启用重试

        Returns:
            响应文本或流式生成器
        """
        if enable_retry:
            return await self._call_with_retry(
                messages, temperature, max_tokens, system_prompt, stream
            )
        else:
            return await self._call_internal(
                messages, temperature, max_tokens, system_prompt, stream
            )

    async def _call_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool
    ) -> Union[str, AsyncGenerator[str, None]]:
        """带重试的LLM调用"""
        last_error = None
        current_delay = self.retry_config.delay

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return await self._call_internal(
                    messages, temperature, max_tokens, system_prompt, stream
                )
            except Exception as e:
                last_error = e

                if attempt >= self.retry_config.max_retries:
                    break

                if not _is_retryable_error(e):
                    break

                # 计算延迟
                wait_time = min(current_delay, self.retry_config.max_delay)
                if self.retry_config.jitter:
                    jitter_min, jitter_max = RETRY_DEFAULTS.JITTER_RANGE
                    wait_time *= random.uniform(jitter_min, jitter_max)

                logger.warning(
                    f"[LLMClient:{self.metrics_namespace}] Call failed "
                    f"(attempt {attempt + 1}/{self.retry_config.max_retries + 1}): {e}. "
                    f"Retrying in {wait_time:.2f}s..."
                )

                await asyncio.sleep(wait_time)
                current_delay *= self.retry_config.backoff

        logger.error(
            f"[LLMClient:{self.metrics_namespace}] All retries exhausted"
        )
        raise last_error

    async def _call_internal(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool
    ) -> Union[str, AsyncGenerator[str, None]]:
        """内部LLM调用实现"""
        start_time = time.time()

        # 构建消息
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # 调用参数
        params = {
            "model": self.model_name,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": normalize_max_tokens(
                max_tokens if max_tokens is not None else self.max_tokens,
                source=f"LLMClient:{self.metrics_namespace}",
            ),
            "stream": stream
        }

        # 日志
        total_chars = sum(len(m.get("content", "")) for m in full_messages)
        logger.info(
            f"[LLMClient:{self.metrics_namespace}] Calling LLM - "
            f"Model: {params['model']}, Messages: {len(full_messages)}, "
            f"Chars: {total_chars}, MaxTokens: {params['max_tokens']}"
        )

        try:
            if stream:
                return self._stream_response(params)
            else:
                response = await self._client.chat.completions.create(**params)
                content = response.choices[0].message.content

                # 提取token使用
                usage = getattr(response, 'usage', None)
                tokens_in = usage.prompt_tokens if usage else 0
                tokens_out = usage.completion_tokens if usage else 0

                # 记录指标
                duration = time.time() - start_time
                self._record_metrics(tokens_in, tokens_out, duration, True)

                logger.info(
                    f"[LLMClient:{self.metrics_namespace}] Response: "
                    f"{len(content)} chars, tokens: {tokens_in}+{tokens_out}, "
                    f"time: {duration:.2f}s"
                )

                return content

        except Exception as e:
            duration = time.time() - start_time
            self._record_metrics(0, 0, duration, False, str(e))

            # 解析错误
            user_msg = self._parse_error(str(e), params['model'])
            logger.error(
                f"[LLMClient:{self.metrics_namespace}] Call failed after {duration:.2f}s: {e}"
            )

            if user_msg:
                raise Exception(user_msg) from e
            raise

    async def _stream_response(self, params: dict) -> AsyncGenerator[str, None]:
        """流式响应生成器"""
        response = await self._client.chat.completions.create(**params)
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _record_metrics(
        self,
        tokens_in: int,
        tokens_out: int,
        duration: float,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """记录指标"""
        # 内存指标
        self.metrics.record_call(
            agent_name=self.metrics_namespace,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration=duration,
            success=success,
            error=error,
            method="llm_call"
        )

        # SQLite持久化
        try:
            record_token_usage(
                agent_name=self.metrics_namespace,
                model=self.model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                success=success,
                method="llm_call",
                duration=duration
            )
        except Exception as e:
            logger.warning(
                f"[LLMClient:{self.metrics_namespace}] Failed to record to SQLite: {e}"
            )

    def _parse_error(self, error_msg: str, model_name: str) -> Optional[str]:
        """解析API错误并返回用户友好提示"""
        error_lower = error_msg.lower()
        api_base = self.model_config.api_base or config.llm.api_base

        # 模型不存在
        if "404" in error_msg or "not found" in error_lower:
            if "entity" in error_lower or "model" in error_lower:
                return (
                    f"模型 '{model_name}' 在API服务器上不可用。\n"
                    f"API地址: {api_base}\n"
                    f"可能原因:\n"
                    f"1. 模型名称不正确\n"
                    f"2. 代理服务器暂时无法访问\n"
                    f"建议: 请在设置中切换到其他可用模型"
                )

        # 认证错误
        if "401" in error_msg or "unauthorized" in error_lower:
            return f"API认证失败，请检查API密钥配置。API地址: {api_base}"

        # 配额限制
        if "429" in error_msg or "rate limit" in error_lower or "quota" in error_lower:
            return f"API请求频率超限或配额已用完。模型: {model_name}"

        # 超时
        if "timeout" in error_lower:
            return f"API请求超时。模型: {model_name}，请稍后重试。"

        # 连接错误
        if "connection" in error_lower:
            return (
                f"无法连接到API服务器。\n"
                f"API地址: {api_base}\n"
                f"请检查网络连接和代理设置"
            )

        return None


# 便捷函数
def create_llm_client(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    retry_config: Optional[RetryConfig] = None,
    metrics_namespace: str = "default"
) -> LLMClient:
    """
    创建LLM客户端的便捷函数

    Args:
        model_name: 模型名称
        temperature: 温度参数
        max_tokens: 最大token数
        api_key: API密钥
        api_base: API基础URL
        retry_config: 重试配置
        metrics_namespace: 指标命名空间

    Returns:
        LLMClient实例
    """
    model_config = AgentModelConfig(
        agent_name="LLMClient",
        model=model_name,
        temperature=temperature if temperature is not None else config.llm.temperature,
        max_tokens=max_tokens if max_tokens is not None else config.llm.max_tokens,
        api_key=api_key,
        api_base=api_base
    )

    return LLMClient(model_config, retry_config, metrics_namespace)
