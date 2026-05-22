"""
LLM客户端模块

封装OpenAI API调用，支持重试、指标收集和错误处理。
从BaseAgent中提取出来，实现单一职责。

支持三种API端点：
- openai_chat: OpenAI Chat Completions API (/v1/chat/completions)
- openai_responses: OpenAI Responses API (/v1/responses)
- anthropic: Anthropic Messages API (/v1/messages)

模块职责说明：提供统一的LLM调用接口，包含重试、指标收集和错误处理。
"""

import time
import asyncio
import logging
import random
import json
import re
from typing import Optional, Dict, Any, List, Union, AsyncGenerator, Tuple
from dataclasses import dataclass

from openai import AsyncOpenAI
import httpx

from ..config import config
from ..agent_config import AgentModelConfig
from ..constants import RETRY_DEFAULTS
from ..timeout_settings import get_llm_timeout_settings
from ..utils.llm_params import add_temperature_param, is_temperature_parameter_error, normalize_max_tokens
from ..utils.metrics import get_metrics_collector
from ..utils.token_stats import extract_token_usage, estimate_tokens_from_messages, estimate_tokens_from_text, record_token_usage
from .api_key_rotation import (
    KeyUseResult,
    classify_key_error,
    get_api_key_rotation_service,
    is_api_key_rotation_enabled,
)


logger = logging.getLogger(__name__)

# 支持的API类型常量
API_TYPE_OPENAI_CHAT = "openai_chat"
API_TYPE_OPENAI_RESPONSES = "openai_responses"
API_TYPE_ANTHROPIC = "anthropic"
VALID_API_TYPES = {API_TYPE_OPENAI_CHAT, API_TYPE_OPENAI_RESPONSES, API_TYPE_ANTHROPIC}


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

    封装多种LLM API的调用，提供：
    - 自动重试机制
    - 指标收集
    - 错误处理和诊断
    - 流式输出支持
    - 支持 OpenAI Chat Completions / OpenAI Responses / Anthropic Messages 三种API
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

        # 根据 api_type 创建对应的客户端
        self._api_type = self._resolve_api_type()
        self._rotation_client_cache: Dict[Tuple[str, str], Any] = {}
        self._client = self._create_client()

        # 指标收集器
        self.metrics = get_metrics_collector()

    def _resolve_api_type(self) -> str:
        """解析并验证 api_type"""
        api_type = getattr(self.model_config, 'api_type', '') or API_TYPE_OPENAI_CHAT
        if api_type not in VALID_API_TYPES:
            logger.warning(
                f"[LLMClient:{self.metrics_namespace}] Unknown api_type '{api_type}', "
                f"falling back to '{API_TYPE_OPENAI_CHAT}'"
            )
            api_type = API_TYPE_OPENAI_CHAT
        return api_type

    def _build_timeout_config(self) -> httpx.Timeout:
        llm_timeouts = get_llm_timeout_settings()
        return httpx.Timeout(
            connect=float(llm_timeouts["connect"]),
            read=float(llm_timeouts["read"]),
            write=float(llm_timeouts["write"]),
            pool=float(llm_timeouts["pool"]),
        )

    def _create_client(self):
        """根据 api_type 创建对应的客户端"""
        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        llm_timeouts = get_llm_timeout_settings()

        timeout_config = self._build_timeout_config()

        logger.info(
            "[LLMClient:%s] Creating client: api_type=%s, base_url=%s, timeout=connect:%ss/read:%ss/write:%ss/pool:%ss",
            self.metrics_namespace,
            self._api_type,
            api_base,
            llm_timeouts["connect"],
            llm_timeouts["read"],
            llm_timeouts["write"],
            llm_timeouts["pool"],
        )

        if self._api_type == API_TYPE_ANTHROPIC:
            return self._create_anthropic_client(api_key, api_base, timeout_config)
        else:
            return self._create_openai_client(api_key, api_base, timeout_config)

    def _create_openai_client(self, api_key: str, api_base: str, timeout_config: httpx.Timeout):
        """创建 OpenAI-compatible 客户端。"""
        kwargs = {
            "api_key": api_key,
            "base_url": api_base,
            "timeout": timeout_config,
            "max_retries": 0,  # 禁用SDK内部重试
        }
        if self._is_tsc5_api_base_value(api_base):
            kwargs["default_headers"] = {"User-Agent": "ShanhaiYunyan/1.0"}
        if self._is_mimo_api_base(api_base):
            kwargs["default_headers"] = {"api-key": api_key}
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
        if self._api_type == API_TYPE_ANTHROPIC:
            return False
        return bool(is_api_key_rotation_enabled() and self._rotation_entries())

    def _select_rotated_openai_client(self, exclude_key_ids: Optional[set[str]] = None):
        if not self._should_use_key_rotation():
            return self._client, None

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

    async def _run_openai_operation_with_rotation(self, operation):
        """Run one OpenAI-compatible operation, trying another key on key-level failures."""
        if not self._should_use_key_rotation():
            return await operation(self._client)

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
                response = await operation(client)
            except Exception as exc:
                last_error = exc
                result = classify_key_error(exc)
                service.report_key_result(config_id, key_entry.id, result, exc)
                attempted.add(key_entry.id)
                logger.warning(
                    "[LLMClient:%s] key %s reported %s; trying another key if available",
                    self.metrics_namespace,
                    key_entry.preview,
                    result.value,
                )
                if result == KeyUseResult.UNKNOWN:
                    raise
                continue

            service.report_key_result(config_id, key_entry.id, KeyUseResult.SUCCESS)
            return response

    def _create_anthropic_client(self, api_key: str, api_base: str, timeout_config: httpx.Timeout):
        """创建 Anthropic 客户端"""
        if self._should_use_raw_anthropic_http():
            logger.info(
                "[LLMClient:%s] Using raw Anthropic HTTP transport for New API-compatible relay",
                self.metrics_namespace,
            )
            return None

        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError(
                "anthropic SDK is required for api_type='anthropic'. "
                "Install it with: pip install anthropic>=0.45.0"
            )

        # Anthropic SDK 使用不同的超时格式
        anthropic_timeout = httpx.Timeout(
            connect=timeout_config.connect,
            read=timeout_config.read,
            write=timeout_config.write,
            pool=timeout_config.pool,
        )

        kwargs = {
            "api_key": api_key,
            "timeout": anthropic_timeout,
            "max_retries": 0,  # 禁用SDK内部重试，使用我们自己的重试
        }

        # Anthropic SDK 的 base_url 是根地址，SDK 会自行追加 /v1/messages。
        # 兼容用户在设置页按 OpenAI 习惯填写的 .../v1，避免变成 /v1/v1/messages。
        normalized_base_url = self._normalize_anthropic_base_url(api_base)
        if normalized_base_url:
            kwargs["base_url"] = normalized_base_url
        if self._is_mimo_api_base(api_base):
            kwargs["default_headers"] = {"api-key": api_key}

        return AsyncAnthropic(**kwargs)

    @property
    def api_type(self) -> str:
        """获取当前API类型"""
        return self._api_type

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

    def _is_tsc5_api_base(self) -> bool:
        model_config = getattr(self, "model_config", None)
        api_base = getattr(model_config, "api_base", "") or config.llm.api_base or ""
        return self._is_tsc5_api_base_value(api_base)

    @staticmethod
    def _is_tsc5_api_base_value(api_base: str) -> bool:
        return "tsc5.top" in str(api_base or "").lower()

    def _should_use_raw_anthropic_http(self) -> bool:
        """Use direct HTTP for relays whose Anthropic compatibility differs from the SDK."""
        if not hasattr(self, "model_config"):
            return False
        return self._is_tsc5_api_base()

    def _should_omit_max_tokens(self) -> bool:
        return self._is_tsc5_api_base()

    def _temperatureless_retry_params(self, params: Dict[str, Any], error: Exception) -> Optional[Dict[str, Any]]:
        if "temperature" not in params or not is_temperature_parameter_error(error):
            return None
        retry_params = dict(params)
        retry_params.pop("temperature", None)
        logger.warning(
            "[LLMClient:%s] Provider rejected temperature; retrying once without it",
            self.metrics_namespace,
        )
        return retry_params

    def _should_use_responses_string_input(self) -> bool:
        """Use the documented Responses string input shape for stricter New API relays."""
        return self._is_tsc5_api_base()

    @staticmethod
    def _is_responses_upstream_not_found(error: Exception) -> bool:
        """Detect relays that expose /responses but route the selected model to a missing upstream."""
        error_text = str(error or "").lower()
        status_code = getattr(error, "status_code", None)
        if status_code != 404 and "404" not in error_text:
            return False
        return any(
            token in error_text
            for token in (
                "bad_response_status_code",
                "openai_error",
                "responses_upstream_not_found",
            )
        )

    @staticmethod
    def _split_system_messages(
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], str]:
        system_parts: List[str] = []
        if system_prompt:
            system_parts.append(str(system_prompt).strip())

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

    def _build_openai_chat_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
    ) -> List[Dict[str, Any]]:
        normalized, resolved_system_prompt = self._split_system_messages(messages, system_prompt)
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

    def update_config(self, model_config: AgentModelConfig) -> None:
        """更新配置并重建客户端"""
        self.model_config = model_config
        self._api_type = self._resolve_api_type()
        self._rotation_client_cache.clear()
        self._client = self._create_client()
        logger.info(f"[LLMClient:{self.metrics_namespace}] Config updated, model: {self.model_name}, api_type: {self._api_type}")

    async def call(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        enable_retry: bool = True,
        usage_collector: Optional[Dict[str, Any]] = None,
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
                messages, temperature, max_tokens, system_prompt, stream, usage_collector
            )
        else:
            return await self._call_internal(
                messages, temperature, max_tokens, system_prompt, stream, usage_collector
            )

    async def _call_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """带重试的LLM调用"""
        last_error = None
        current_delay = self.retry_config.delay

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return await self._call_internal(
                    messages, temperature, max_tokens, system_prompt, stream, usage_collector
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
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """内部LLM调用实现 - 根据 api_type 路由到不同的调用方式"""
        if self._api_type == API_TYPE_ANTHROPIC:
            return await self._call_anthropic(messages, temperature, max_tokens, system_prompt, stream, usage_collector)
        elif self._api_type == API_TYPE_OPENAI_RESPONSES:
            return await self._call_openai_responses(messages, temperature, max_tokens, system_prompt, stream, usage_collector)
        else:
            return await self._call_openai_chat(messages, temperature, max_tokens, system_prompt, stream, usage_collector)

    # ============================================================
    # OpenAI Chat Completions API
    # ============================================================

    async def _call_openai_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """OpenAI Chat Completions API 调用"""
        start_time = time.time()

        # 构建消息
        full_messages = self._build_openai_chat_messages(messages, system_prompt)

        resolved_max_tokens = normalize_max_tokens(
            max_tokens if max_tokens is not None else self.max_tokens,
            source=f"LLMClient:{self.metrics_namespace}",
        )

        # 调用参数
        params = {
            "model": self.model_name,
            "messages": full_messages,
            "stream": stream
        }
        add_temperature_param(
            params,
            model=params["model"],
            temperature=temperature if temperature is not None else self.temperature,
            source=f"LLMClient:{self.metrics_namespace}",
        )
        if not self._should_omit_max_tokens():
            params["max_tokens"] = resolved_max_tokens

        # 日志
        total_chars = sum(len(m.get("content", "")) for m in full_messages)
        estimated_tokens_in = estimate_tokens_from_messages(full_messages)
        logger.info(
            f"[LLMClient:{self.metrics_namespace}] Calling OpenAI Chat - "
            f"Model: {params['model']}, Messages: {len(full_messages)}, "
            f"Chars: {total_chars}, MaxTokens: {params.get('max_tokens', 'provider_default')}"
        )

        try:
            if stream:
                return self._stream_openai_chat(params, usage_collector=usage_collector)
            else:
                try:
                    response = await self._run_openai_operation_with_rotation(
                        lambda client: client.chat.completions.create(**params)
                    )
                except Exception as exc:
                    retry_params = self._temperatureless_retry_params(params, exc)
                    if retry_params is None:
                        raise
                    params = retry_params
                    response = await self._run_openai_operation_with_rotation(
                        lambda client: client.chat.completions.create(**params)
                    )
                content = response.choices[0].message.content

                # 提取token使用
                usage = getattr(response, 'usage', None)
                tokens_in, tokens_out = extract_token_usage(
                    usage,
                    fallback_tokens_in=estimated_tokens_in,
                    fallback_tokens_out=estimate_tokens_from_text(content),
                )

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
            self._record_metrics(estimated_tokens_in, 0, duration, False, str(e))

            # 解析错误
            user_msg = self._parse_error(str(e), params['model'])
            logger.error(
                f"[LLMClient:{self.metrics_namespace}] Call failed after {duration:.2f}s: {e}"
            )

            if user_msg:
                raise Exception(user_msg) from e
            raise

    @staticmethod
    def _is_stream_options_unsupported(error: Exception) -> bool:
        error_lower = str(error or "").lower()
        return (
            "stream_options" in error_lower
            and any(token in error_lower for token in ("unsupported", "unknown", "extra", "unrecognized", "not allowed", "unexpected", "invalid"))
        )

    def _should_include_stream_options(self) -> bool:
        if self._is_tsc5_api_base():
            return False
        return True

    async def _stream_openai_chat(
        self,
        params: dict,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """OpenAI Chat 流式响应生成器"""
        request_params = dict(params)
        if (
            request_params.get("stream")
            and "stream_options" not in request_params
            and self._should_include_stream_options()
        ):
            request_params["stream_options"] = {"include_usage": True}
        try:
            response = await self._run_openai_operation_with_rotation(
                lambda client: client.chat.completions.create(**request_params)
            )
        except Exception as exc:
            retry_params = self._temperatureless_retry_params(request_params, exc)
            if retry_params is not None:
                request_params = retry_params
                response = await self._run_openai_operation_with_rotation(
                    lambda client: client.chat.completions.create(**request_params)
                )
            elif "stream_options" in request_params and self._is_stream_options_unsupported(exc):
                if usage_collector is not None:
                    usage_collector["usage_unavailable_reason"] = "stream_options_unsupported"
                request_params.pop("stream_options", None)
                response = await self._run_openai_operation_with_rotation(
                    lambda client: client.chat.completions.create(**request_params)
                )
            else:
                raise
        async for chunk in response:
            usage = chunk.get("usage") if isinstance(chunk, dict) else getattr(chunk, "usage", None)
            if usage is not None and usage_collector is not None:
                usage_collector["usage"] = usage
            choices = chunk.get("choices") if isinstance(chunk, dict) else getattr(chunk, "choices", None)
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
            content = delta.get("content") if isinstance(delta, dict) else getattr(delta, "content", None)
            if content:
                yield content

    # ============================================================
    # OpenAI Responses API
    # ============================================================

    async def _call_openai_responses(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """OpenAI Responses API 调用 (/v1/responses)"""
        start_time = time.time()

        non_system_messages, resolved_system_prompt = self._split_system_messages(messages, system_prompt)
        use_string_input = self._should_use_responses_string_input()

        # 构建 input（Responses API 使用 input 字段而非 messages）。
        #
        # 注意：Responses API 中 system prompt 更推荐使用顶层 instructions 字段，
        # 而不是作为 input 数组中的 system 消息。部分 OpenAI 兼容中转虽然接受
        # {"role": "system", "content": "..."}，但可能返回 HTTP 200 且 output=[]。
        # New API 文档同时允许 input 使用 string 或 array<object>。对探索仓这类
        # New API 中转使用更保守的 string input，避免 typed input + instructions
        # 组合被网关当成异常请求体拦截。
        responses_input: Union[str, List[Dict[str, Any]]]
        if use_string_input:
            responses_input = self._build_responses_string_input(non_system_messages, resolved_system_prompt)
        else:
            responses_input = self._build_responses_input_items(non_system_messages)

        resolved_max_tokens = normalize_max_tokens(
            max_tokens if max_tokens is not None else self.max_tokens,
            source=f"LLMClient:{self.metrics_namespace}",
        )

        # Responses API 参数
        params = {
            "model": self.model_name,
            "input": responses_input,
            "max_output_tokens": resolved_max_tokens,
        }
        add_temperature_param(
            params,
            model=params["model"],
            temperature=temperature if temperature is not None else self.temperature,
            source=f"LLMClient:{self.metrics_namespace}",
        )
        if resolved_system_prompt and not use_string_input:
            params["instructions"] = resolved_system_prompt

        if isinstance(responses_input, str):
            total_chars = len(responses_input)
            estimated_tokens_in = estimate_tokens_from_text(responses_input)
        else:
            total_chars = self._responses_input_char_count(responses_input)
            estimated_tokens_in = (
                estimate_tokens_from_messages(responses_input)
                + estimate_tokens_from_text(resolved_system_prompt)
            )
        logger.info(
            f"[LLMClient:{self.metrics_namespace}] Calling OpenAI Responses - "
            f"Model: {params['model']}, Input: {1 if isinstance(responses_input, str) else len(responses_input)}, "
            f"Chars: {total_chars}, MaxOutputTokens: {params['max_output_tokens']}"
        )

        try:
            if stream:
                return self._stream_openai_responses_with_chat_fallback(
                    params,
                    messages,
                    temperature,
                    max_tokens,
                    system_prompt,
                    usage_collector,
                )
            else:
                try:
                    response = await self._run_openai_operation_with_rotation(
                        lambda client: client.responses.create(**params)
                    )
                except Exception as exc:
                    retry_params = self._temperatureless_retry_params(params, exc)
                    if retry_params is None:
                        raise
                    params = retry_params
                    response = await self._run_openai_operation_with_rotation(
                        lambda client: client.responses.create(**params)
                    )

                # 提取内容 - Responses API 的输出格式
                content = self._extract_responses_content(response)
                if not str(content or "").strip():
                    logger.warning(
                        "[LLMClient:%s] Responses API returned empty visible text. Response shape: %s",
                        self.metrics_namespace,
                        self._summarize_responses_shape(response),
                    )
                    content = await self._retry_openai_responses_with_string_input(
                        params=params,
                        messages=messages,
                        system_prompt=resolved_system_prompt,
                    )

                # 提取token使用
                usage = getattr(response, 'usage', None)
                tokens_in, tokens_out = extract_token_usage(
                    usage,
                    fallback_tokens_in=estimated_tokens_in,
                    fallback_tokens_out=estimate_tokens_from_text(content),
                )

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
            self._record_metrics(estimated_tokens_in, 0, duration, False, str(e))

            if self._is_responses_upstream_not_found(e):
                logger.warning(
                    "[LLMClient:%s] Responses upstream is unavailable for model %s; "
                    "falling back to OpenAI Chat Completions",
                    self.metrics_namespace,
                    params["model"],
                )
                return await self._call_openai_chat(
                    messages,
                    temperature,
                    max_tokens,
                    system_prompt,
                    stream,
                    usage_collector,
                )

            user_msg = self._parse_error(str(e), params['model'])
            logger.error(
                f"[LLMClient:{self.metrics_namespace}] Responses call failed after {duration:.2f}s: {e}"
            )

            if user_msg:
                raise Exception(user_msg) from e
            raise

    @staticmethod
    def _build_responses_input_items(messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """构建 Responses API 的 typed input，按 api_type 适配官方新接口。"""
        input_items: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "user") or "user").strip() or "user"
            content = msg.get("content", "")
            if role == "system":
                # system 内容会在调用方合并到 instructions；这里避免重复塞入 input。
                continue
            if role not in {"user", "assistant", "developer"}:
                role = "user"
            input_items.append({
                "role": role,
                "content": [
                    {
                        "type": "input_text" if role != "assistant" else "output_text",
                        "text": str(content or ""),
                    }
                ],
            })
        if not input_items:
            input_items.append({
                "role": "user",
                "content": [{"type": "input_text", "text": ""}],
            })
        return input_items

    @staticmethod
    def _responses_input_char_count(input_items: List[Dict[str, Any]]) -> int:
        total = 0
        for item in input_items:
            content = item.get("content", "")
            if isinstance(content, str):
                total += len(content)
                continue
            if isinstance(content, list):
                for content_item in content:
                    if isinstance(content_item, dict):
                        total += len(str(content_item.get("text") or content_item.get("content") or ""))
                    else:
                        total += len(str(content_item or ""))
        return total

    @staticmethod
    def _build_responses_string_input(messages: List[Dict[str, str]], system_prompt: Optional[str]) -> str:
        """为空输出兜底构建最保守的 Responses string input。"""
        parts: List[str] = []
        if system_prompt:
            parts.append(f"写作提示：\n{system_prompt}")
        for msg in messages:
            role = str(msg.get("role", "user") or "user").strip() or "user"
            content = str(msg.get("content", "") or "").strip()
            if not content:
                continue
            role_label = "用户" if role == "user" else "助手" if role == "assistant" else "系统"
            parts.append(f"{role_label}：\n{content}")
        return "\n\n".join(parts).strip() or "Hello"

    async def _retry_openai_responses_with_string_input(
        self,
        *,
        params: Dict[str, Any],
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
    ) -> str:
        """Responses typed input 返回空文本时，使用 string input 进行一次兼容兜底。"""
        fallback_params = dict(params)
        fallback_params["input"] = self._build_responses_string_input(messages, system_prompt)
        # string input 已包含系统指令，避免 instructions 被部分中转重复拼接。
        fallback_params.pop("instructions", None)

        logger.warning(
            "[LLMClient:%s] Retrying Responses API with string input fallback",
            self.metrics_namespace,
        )
        fallback_response = await self._run_openai_operation_with_rotation(
            lambda client: client.responses.create(**fallback_params)
        )
        fallback_content = self._extract_responses_content(fallback_response)
        if str(fallback_content or "").strip():
            return fallback_content

        logger.warning(
            "[LLMClient:%s] Responses API string fallback also returned empty visible text. Response shape: %s",
            self.metrics_namespace,
            self._summarize_responses_shape(fallback_response),
        )
        raise ValueError(
            "Responses API returned empty visible text for both typed input and string input fallback. "
            "Please verify the selected api_type/model/provider supports /v1/responses."
        )

    def _extract_responses_content(self, response) -> str:
        """从 Responses API 响应中尽量提取可见文本，兼容不同中转实现。"""
        direct_text = getattr(response, 'output_text', None)
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text

        parts = []

        def append_text(value: Any) -> None:
            if isinstance(value, str) and value:
                parts.append(value)

        output = getattr(response, 'output', None) or []
        for item in output:
            if isinstance(item, dict):
                item_type = str(item.get('type') or '')
                if item_type == 'message':
                    for content_item in item.get('content') or []:
                        if isinstance(content_item, dict):
                            append_text(content_item.get('text') or content_item.get('content'))
                append_text(item.get('text') or item.get('content'))
                continue

            item_type = getattr(item, 'type', '')
            if item_type == 'message':
                content_list = getattr(item, 'content', []) or []
                for content_item in content_list:
                    if isinstance(content_item, dict):
                        append_text(content_item.get('text') or content_item.get('content'))
                        continue
                    content_type = getattr(content_item, 'type', '')
                    if content_type in {'output_text', 'text'} or hasattr(content_item, 'text'):
                        append_text(getattr(content_item, 'text', ''))
            elif hasattr(item, 'text'):
                append_text(getattr(item, 'text', ''))

        content = "".join(parts)
        if content.strip():
            return content

        try:
            raw = response.model_dump()
            raw_output_text = raw.get('output_text')
            if isinstance(raw_output_text, str) and raw_output_text.strip():
                return raw_output_text
            for choice in raw.get('choices') or []:
                if not isinstance(choice, dict):
                    continue
                message = choice.get('message') or {}
                if isinstance(message, dict):
                    append_text(message.get('content') or message.get('text'))
            for item in raw.get('output') or []:
                if not isinstance(item, dict):
                    continue
                append_text(item.get('text') or item.get('content'))
                for content_item in item.get('content') or []:
                    if isinstance(content_item, dict):
                        append_text(content_item.get('text') or content_item.get('content'))
        except Exception:
            pass

        return "".join(parts)

    @staticmethod
    def _summarize_responses_shape(response) -> str:
        """Return a safe, compact shape summary for empty Responses API outputs."""
        try:
            raw = response.model_dump()
        except Exception:
            return str(type(response).__name__)

        output_summary = []
        for item in raw.get('output') or []:
            if not isinstance(item, dict):
                output_summary.append({"type": type(item).__name__})
                continue
            content_summary = []
            for content_item in item.get('content') or []:
                if isinstance(content_item, dict):
                    content_summary.append({
                        "type": content_item.get('type'),
                        "has_text": bool(str(content_item.get('text') or content_item.get('content') or "").strip()),
                    })
                else:
                    content_summary.append({"type": type(content_item).__name__})
            output_summary.append({
                "type": item.get('type'),
                "status": item.get('status'),
                "content": content_summary,
            })

        summary = {
            "keys": sorted(str(key) for key in raw.keys()),
            "status": raw.get('status'),
            "incomplete_details": raw.get('incomplete_details'),
            "output": output_summary,
            "has_output_text": bool(str(raw.get('output_text') or "").strip()),
        }
        return json.dumps(summary, ensure_ascii=False, default=str)[:2000]

    async def _stream_openai_responses(
        self,
        params: dict,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """OpenAI Responses 流式响应生成器"""
        request_params = dict(params)
        try:
            stream = await self._run_openai_operation_with_rotation(
                lambda client: client.responses.create(stream=True, **request_params)
            )
        except Exception as exc:
            retry_params = self._temperatureless_retry_params(request_params, exc)
            if retry_params is None:
                raise
            request_params = retry_params
            stream = await self._run_openai_operation_with_rotation(
                lambda client: client.responses.create(stream=True, **request_params)
            )
        async for event in stream:
            usage = event.get("usage") if isinstance(event, dict) else getattr(event, "usage", None)
            if usage is not None and usage_collector is not None:
                usage_collector["usage"] = usage
            # Responses API 流式事件
            event_type = event.get("type", "") if isinstance(event, dict) else getattr(event, 'type', '')
            if event_type == 'response.output_text.delta':
                delta = event.get("delta", "") if isinstance(event, dict) else getattr(event, 'delta', '')
                if delta:
                    yield delta
            elif (isinstance(event, dict) and "delta" in event) or hasattr(event, 'delta'):
                raw_delta = event.get("delta") if isinstance(event, dict) else getattr(event, "delta", None)
                delta_text = raw_delta.get("text", "") if isinstance(raw_delta, dict) else getattr(raw_delta, 'text', '') if hasattr(raw_delta, 'text') else str(raw_delta)
                if delta_text:
                    yield delta_text

    async def _stream_openai_responses_with_chat_fallback(
        self,
        params: dict,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream Responses output, falling back to Chat when the relay lacks a Responses upstream."""
        try:
            async for chunk in self._stream_openai_responses(params, usage_collector=usage_collector):
                yield chunk
        except Exception as exc:
            if not self._is_responses_upstream_not_found(exc):
                raise
            logger.warning(
                "[LLMClient:%s] Responses stream upstream is unavailable for model %s; "
                "falling back to OpenAI Chat Completions",
                self.metrics_namespace,
                params.get("model"),
            )
            fallback_stream = await self._call_openai_chat(
                messages,
                temperature,
                max_tokens,
                system_prompt,
                True,
                usage_collector,
            )
            async for chunk in fallback_stream:
                yield chunk

    # ============================================================
    # Anthropic Messages API
    # ============================================================

    async def _call_anthropic(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str],
        stream: bool,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """Anthropic Messages API 调用。

        Anthropic 的 /v1/messages 与 OpenAI Chat/Responses 不同：
        - system 使用顶层参数，不作为 messages 角色传入；
        - messages 仅允许 user/assistant，并且工具结果以 user content 中的
          {"type": "tool_result", "tool_use_id": "..."} 内容块续传；
        - 流式工具参数通过 content_block_delta/input_json_delta.partial_json
          分片返回，只能在 content_block_stop 后解析。
        """
        start_time = time.time()

        anthropic_messages, system_prompt = self._build_anthropic_messages(messages, system_prompt)

        resolved_max_tokens = normalize_max_tokens(
            max_tokens if max_tokens is not None else self.max_tokens,
            source=f"LLMClient:{self.metrics_namespace}",
        )

        # Anthropic API 参数
        params = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": resolved_max_tokens,
        }
        add_temperature_param(
            params,
            model=params["model"],
            temperature=temperature if temperature is not None else self.temperature,
            source=f"LLMClient:{self.metrics_namespace}",
        )

        if system_prompt:
            params["system"] = system_prompt

        total_chars = sum(len(self._anthropic_content_to_text(m.get("content", ""))) for m in anthropic_messages)
        estimated_tokens_in = (
            sum(estimate_tokens_from_text(self._anthropic_content_to_text(m.get("content", ""))) for m in anthropic_messages)
            + estimate_tokens_from_text(system_prompt)
        )
        logger.info(
            f"[LLMClient:{self.metrics_namespace}] Calling Anthropic Messages - "
            f"Model: {params['model']}, Messages: {len(anthropic_messages)}, "
            f"Chars: {total_chars}, MaxTokens: {params['max_tokens']}"
        )

        try:
            if stream:
                return self._stream_anthropic(params, usage_collector=usage_collector)
            else:
                if self._should_use_raw_anthropic_http():
                    response = await self._post_raw_anthropic(params)
                else:
                    response = await self._client.messages.create(**params)

                # 提取内容；如果模型以 tool_use 停止且没有可见文本，则返回
                # JSON 形式的工具调用描述，供上层进行显式处理或记录。
                content, tool_uses = self._extract_anthropic_content(response)
                if not content and tool_uses:
                    content = json.dumps({"tool_calls": tool_uses}, ensure_ascii=False)

                # 提取token使用
                tokens_in, tokens_out = extract_token_usage(
                    self._event_value(response, "usage", None),
                    fallback_tokens_in=estimated_tokens_in,
                    fallback_tokens_out=estimate_tokens_from_text(content),
                )

                duration = time.time() - start_time
                self._record_metrics(tokens_in, tokens_out, duration, True)

                logger.info(
                    f"[LLMClient:{self.metrics_namespace}] Anthropic Response: "
                    f"{len(content)} chars, tokens: {tokens_in}+{tokens_out}, "
                    f"time: {duration:.2f}s"
                )

                return content

        except Exception as e:
            duration = time.time() - start_time
            self._record_metrics(estimated_tokens_in, 0, duration, False, str(e))

            user_msg = self._parse_anthropic_error(str(e))
            logger.error(
                f"[LLMClient:{self.metrics_namespace}] Anthropic call failed after {duration:.2f}s: {e}"
            )

            if user_msg:
                raise Exception(user_msg) from e
            raise

    @staticmethod
    def _is_mimo_api_base(api_base: str) -> bool:
        """Return True for Xiaomi MiMo API bases that document api-key auth."""
        return "xiaomimimo.com" in str(api_base or "").lower()

    @staticmethod
    def _is_official_anthropic_api_base(api_base: str) -> bool:
        api_base_lower = str(api_base or "").lower()
        return "anthropic.com" in api_base_lower and "xiaomimimo.com" not in api_base_lower

    @classmethod
    def _build_anthropic_headers(cls, api_key: str, api_base: str) -> Dict[str, str]:
        """Build Anthropic-compatible headers for official and relay endpoints."""
        headers = {"Content-Type": "application/json"}
        if cls._is_mimo_api_base(api_base):
            headers["api-key"] = api_key
            return headers

        headers["anthropic-version"] = "2023-06-01"
        if cls._is_official_anthropic_api_base(api_base):
            headers["x-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _anthropic_messages_url(self) -> str:
        api_base = self.model_config.api_base or config.llm.api_base
        base_url = self._normalize_anthropic_base_url(api_base)
        return f"{base_url}/v1/messages"

    async def _post_raw_anthropic(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call Anthropic Messages with raw HTTP for New API-compatible relays."""
        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        async with httpx.AsyncClient(timeout=self._build_timeout_config()) as client:
            response = await client.post(
                self._anthropic_messages_url(),
                headers=self._build_anthropic_headers(api_key, api_base),
                json=params,
            )

        payload = self._safe_json_response(response)
        if response.status_code >= 400:
            detail = self._anthropic_error_detail(payload, response.text)
            raise RuntimeError(f"HTTP {response.status_code}: {detail}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Anthropic relay returned non-object JSON: {str(payload)[:200]}")
        return payload

    @staticmethod
    def _safe_json_response(response: Any) -> Any:
        try:
            return response.json()
        except Exception:
            return None

    @classmethod
    def _anthropic_error_detail(cls, payload: Any, text: str = "") -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                for key in ("message", "detail", "type", "code"):
                    value = error.get(key)
                    if value:
                        return str(value)[:500]
            if error:
                return str(error)[:500]
            for key in ("message", "detail"):
                value = payload.get(key)
                if value:
                    return str(value)[:500]
        return str(text or "request failed")[:500]

    @staticmethod
    def _normalize_anthropic_base_url(api_base: str) -> str:
        """Normalize Anthropic SDK base_url to the API root instead of /v1."""
        base_url = str(api_base or "").strip().rstrip("/")
        if not base_url:
            return ""
        last_segment = base_url.rsplit("/", 1)[-1].lower()
        if re.fullmatch(r"v\d+(\.\d+)?", last_segment):
            base_url = base_url.rsplit("/", 1)[0].rstrip("/")
        return base_url

    def _build_anthropic_messages(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Build Anthropic-compatible messages while preserving content blocks."""
        anthropic_messages: List[Dict[str, Any]] = []
        resolved_system = system_prompt

        for msg in messages:
            role = str(msg.get("role", "user") or "user").strip()
            content = msg.get("content", "")

            if role == "system":
                system_text = self._anthropic_content_to_text(content)
                if system_text:
                    resolved_system = f"{system_text}\n\n{resolved_system}" if resolved_system else system_text
                continue

            if role not in {"user", "assistant"}:
                role = "user"

            anthropic_messages.append({
                "role": role,
                "content": self._normalize_anthropic_content(content),
            })

        if not anthropic_messages:
            anthropic_messages.append({"role": "user", "content": "Hello"})

        return self._merge_consecutive_messages(anthropic_messages), resolved_system

    @staticmethod
    def _normalize_anthropic_content(content: Any) -> Any:
        """Keep Anthropic content blocks intact; coerce plain values to text."""
        if isinstance(content, list):
            normalized_blocks: List[Dict[str, Any]] = []
            for block in content:
                if isinstance(block, dict):
                    block_type = str(block.get("type") or "").strip()
                    if block_type:
                        normalized_blocks.append(block)
                    else:
                        normalized_blocks.append({"type": "text", "text": str(block)})
                else:
                    normalized_blocks.append({"type": "text", "text": str(block or "")})
            return normalized_blocks
        return str(content or "")

    @staticmethod
    def _anthropic_content_to_text(content: Any) -> str:
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif block:
                    parts.append(str(block))
            return "\n".join(part for part in parts if part).strip()
        return str(content or "").strip()

    @staticmethod
    def _merge_anthropic_content(left: Any, right: Any) -> Any:
        """Merge consecutive same-role Anthropic content without corrupting blocks."""
        if isinstance(left, list) or isinstance(right, list):
            left_blocks = left if isinstance(left, list) else [{"type": "text", "text": str(left or "")}]
            right_blocks = right if isinstance(right, list) else [{"type": "text", "text": str(right or "")}]
            return [*left_blocks, *right_blocks]

        left_text = str(left or "")
        right_text = str(right or "")
        if not left_text:
            return right_text
        if not right_text:
            return left_text
        return f"{left_text}\n\n{right_text}"

    def _merge_consecutive_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并连续同角色消息，避免违反 Anthropic 多轮消息格式。"""
        if not messages:
            return messages

        merged = [messages[0].copy()]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                merged[-1]["content"] = self._merge_anthropic_content(
                    merged[-1].get("content", ""),
                    msg.get("content", ""),
                )
            else:
                merged.append(msg.copy())
        return merged

    @staticmethod
    def _event_value(event: Any, key: str, default: Any = None) -> Any:
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)

    @classmethod
    def _nested_event_value(cls, event: Any, *keys: str, default: Any = None) -> Any:
        value = event
        for key in keys:
            value = cls._event_value(value, key, None)
            if value is None:
                return default
        return value

    def _extract_anthropic_content(self, response: Any) -> Tuple[str, List[Dict[str, Any]]]:
        text_parts: List[str] = []
        tool_uses: List[Dict[str, Any]] = []

        content_blocks = response.get("content", []) if isinstance(response, dict) else getattr(response, "content", [])
        for block in content_blocks or []:
            block_type = self._event_value(block, "type", "")
            text = self._event_value(block, "text", None)
            if isinstance(text, str):
                text_parts.append(text)
                continue

            if block_type == "tool_use":
                tool_input = self._event_value(block, "input", {})
                tool_uses.append({
                    "id": self._event_value(block, "id", ""),
                    "name": self._event_value(block, "name", ""),
                    "input": tool_input if isinstance(tool_input, dict) else {},
                })

        return "".join(text_parts), tool_uses

    async def _stream_anthropic(
        self,
        params: dict,
        usage_collector: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Anthropic 流式响应生成器。

        不使用 SDK 的 text_stream 快捷通道，因为 text_stream 只返回文本，
        无法解析 content_block_start/content_block_delta/content_block_stop
        中的 tool_use 与 input_json_delta.partial_json。
        """
        tool_buffers: Dict[int, Dict[str, Any]] = {}

        async for event in self._iter_anthropic_stream_events(params):
            usage = self._event_value(event, "usage", None)
            if usage is None:
                usage = self._nested_event_value(event, "delta", "usage", default=None)
            if usage is not None and usage_collector is not None:
                usage_collector["usage"] = usage
            event_type = self._event_value(event, "type", "")

            if event_type == "content_block_start":
                index = int(self._event_value(event, "index", 0) or 0)
                block = self._event_value(event, "content_block", {}) or {}
                if self._event_value(block, "type", "") == "tool_use":
                    tool_buffers[index] = {
                        "id": self._event_value(block, "id", ""),
                        "name": self._event_value(block, "name", ""),
                        "partial_json": "",
                    }
                continue

            if event_type == "content_block_delta":
                delta_type = self._nested_event_value(event, "delta", "type", default="")
                text = self._nested_event_value(event, "delta", "text", default="")
                if delta_type == "text_delta" or (text and not delta_type):
                    if text:
                        yield text
                elif delta_type == "input_json_delta":
                    index = int(self._event_value(event, "index", 0) or 0)
                    partial_json = self._nested_event_value(event, "delta", "partial_json", default="")
                    if partial_json:
                        tool_buffers.setdefault(index, {
                            "id": "",
                            "name": "",
                            "partial_json": "",
                        })["partial_json"] += partial_json
                continue

            if event_type == "content_block_stop":
                index = int(self._event_value(event, "index", 0) or 0)
                tool_state = tool_buffers.get(index)
                if not tool_state:
                    continue

                raw_input = str(tool_state.get("partial_json") or "")
                try:
                    parsed_input = json.loads(raw_input) if raw_input.strip() else {}
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "[LLMClient:%s] Failed to parse Anthropic tool input JSON for tool %s/%s: %s; raw=%s",
                        self.metrics_namespace,
                        tool_state.get("name", ""),
                        tool_state.get("id", ""),
                        exc,
                        raw_input[:1000],
                    )
                    parsed_input = {}

                logger.info(
                    "[LLMClient:%s] Anthropic tool_use parsed: name=%s id=%s input_keys=%s",
                    self.metrics_namespace,
                    tool_state.get("name", ""),
                    tool_state.get("id", ""),
                    sorted(parsed_input.keys()) if isinstance(parsed_input, dict) else [],
                )
                continue

    async def _iter_anthropic_stream_events(self, params: Dict[str, Any]) -> AsyncGenerator[Any, None]:
        if not self._should_use_raw_anthropic_http():
            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    yield event
            return

        api_key = self.model_config.api_key or config.llm.api_key
        api_base = self.model_config.api_base or config.llm.api_base
        request_params = dict(params)
        request_params["stream"] = True
        async with httpx.AsyncClient(timeout=self._build_timeout_config()) as client:
            async with client.stream(
                "POST",
                self._anthropic_messages_url(),
                headers=self._build_anthropic_headers(api_key, api_base),
                json=request_params,
            ) as response:
                if response.status_code >= 400:
                    raw_error = (await response.aread()).decode("utf-8", errors="replace")
                    payload = None
                    try:
                        payload = json.loads(raw_error)
                    except Exception:
                        pass
                    detail = self._anthropic_error_detail(payload, raw_error)
                    raise RuntimeError(f"HTTP {response.status_code}: {detail}")

                async for line in response.aiter_lines():
                    data = self._parse_sse_data_line(line)
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug(
                            "[LLMClient:%s] Ignoring non-JSON Anthropic stream line: %s",
                            self.metrics_namespace,
                            data[:300],
                        )

    @staticmethod
    def _parse_sse_data_line(line: str) -> str:
        line = str(line or "").strip()
        if not line or line.startswith(":") or line.startswith("event:"):
            return ""
        if line.startswith("data:"):
            return line[5:].strip()
        if line.startswith("{") or line.startswith("["):
            return line
        return ""

    def _parse_anthropic_error(self, error_msg: str) -> Optional[str]:
        """解析 Anthropic API 错误"""
        error_lower = error_msg.lower()

        if "authentication" in error_lower or "invalid x-api-key" in error_lower or "401" in error_msg:
            return "Anthropic API认证失败，请检查API Key配置。"

        if "rate_limit" in error_lower or "429" in error_msg:
            return "Anthropic API请求频率超限，请稍后重试。"

        if "overloaded" in error_lower or "529" in error_msg:
            return "Anthropic API当前过载，请稍后重试。"

        if "not_found" in error_lower or "404" in error_msg:
            return f"Anthropic模型 '{self.model_name}' 不可用，请检查模型名称。"

        if "timeout" in error_lower:
            return f"Anthropic API请求超时。模型: {self.model_name}"

        return None

    # ============================================================
    # 通用方法
    # ============================================================

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
    api_type: Optional[str] = None,
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
        api_type: API类型 ("openai_chat", "openai_responses", "anthropic")
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
        api_base=api_base,
        api_type=api_type or "openai_chat"
    )

    return LLMClient(model_config, retry_config, metrics_namespace)
