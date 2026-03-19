"""
中国AI服务商大模型API统一适配器
支持：百度文心、阿里通义、讯飞星火、智谱AI、月之暗面Kimi、字节豆包、MiniMax、DeepSeek
"""

import os
import json
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator, Union, Callable
from enum import Enum
import aiohttp
import requests
from urllib.parse import urlencode


class ProviderType(Enum):
    """支持的AI服务商类型"""
    BAIDU = "baidu"           # 百度文心一言
    ALIBABA = "alibaba"       # 阿里通义千问
    IFLYTEK = "iflytek"       # 讯飞星火
    ZHIPU = "zhipu"           # 智谱AI
    MOONSHOT = "moonshot"     # 月之暗面Kimi
    DOUBAO = "doubao"         # 字节豆包
    MINIMAX = "minimax"       # MiniMax
    DEEPSEEK = "deepseek"     # DeepSeek


@dataclass
class Message:
    """统一消息格式"""
    role: str  # "system", "user", "assistant"
    content: str
    name: Optional[str] = None


@dataclass
class ChatCompletionRequest:
    """统一聊天完成请求"""
    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    stream: bool = False
    stop: Optional[List[str]] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatCompletionResponse:
    """统一聊天完成响应"""
    id: str
    model: str
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None
    created: int = field(default_factory=lambda: int(time.time()))
    raw_response: Dict[str, Any] = field(default_factory=dict, repr=False)

    def get_content(self) -> str:
        """获取响应内容"""
        if self.choices and len(self.choices) > 0:
            choice = self.choices[0]
            if "message" in choice:
                return choice["message"].get("content", "")
            elif "text" in choice:
                return choice["text"]
            elif "delta" in choice:
                return choice["delta"].get("content", "")
        return ""


class BaseLLMAdapter(ABC):
    """LLM适配器基类"""

    def __init__(self, api_key: str, api_secret: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = kwargs.get("base_url", self.get_default_base_url())
        self.timeout = kwargs.get("timeout", 60)
        self.max_retries = kwargs.get("max_retries", 3)
        self.retry_delay = kwargs.get("retry_delay", 1.0)

    @abstractmethod
    def get_default_base_url(self) -> str:
        """获取默认API基础URL"""
        pass

    @abstractmethod
    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """将统一请求转换为服务商特定格式"""
        pass

    @abstractmethod
    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        """将服务商响应转换为统一格式"""
        pass

    @abstractmethod
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        pass

    def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """同步聊天完成"""
        url = f"{self.base_url}{self._get_endpoint()}"
        headers = self._get_headers()
        payload = self._convert_request(request)

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                raw_data = response.json()
                return self._convert_response(raw_data)
            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))

        raise RuntimeError("Max retries exceeded")

    async def achat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """异步聊天完成"""
        url = f"{self.base_url}{self._get_endpoint()}"
        headers = self._get_headers()
        payload = self._convert_request(request)

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, headers=headers, json=payload, timeout=self.timeout
                    ) as response:
                        response.raise_for_status()
                        raw_data = await response.json()
                        return self._convert_response(raw_data)
            except asyncio.TimeoutError:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise RuntimeError("Max retries exceeded")

    async def achat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        """异步流式聊天完成"""
        url = f"{self.base_url}{self._get_endpoint()}"
        headers = self._get_headers()
        payload = self._convert_request(request)
        payload["stream"] = True

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = self._extract_stream_content(chunk)
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    def _get_endpoint(self) -> str:
        """获取API端点路径"""
        return "/chat/completions"

    def _extract_stream_content(self, chunk: Dict[str, Any]) -> Optional[str]:
        """从流式响应块中提取内容"""
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            return delta.get("content")
        return None

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """转换消息格式为标准OpenAI格式"""
        return [
            {"role": msg.role, "content": msg.content, **({"name": msg.name} if msg.name else {})}
            for msg in messages
        ]


# 导出主要类
from .factory import LLMAdapterFactory, UnifiedLLM, create_llm, create_llm_from_env
from .baidu import BaiduAdapter
from .alibaba import AlibabaQwenAdapter
from .iflytek import iFlytekAdapter
from .zhipu import ZhipuAIAdapter
from .moonshot import MoonshotAdapter
from .doubao import DoubaoAdapter
from .minimax import MiniMaxAdapter
from .deepseek import DeepSeekAdapter

__all__ = [
    "ProviderType",
    "Message",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "BaseLLMAdapter",
    "LLMAdapterFactory",
    "UnifiedLLM",
    "create_llm",
    "create_llm_from_env",
    "BaiduAdapter",
    "AlibabaQwenAdapter",
    "iFlytekAdapter",
    "ZhipuAIAdapter",
    "MoonshotAdapter",
    "DoubaoAdapter",
    "MiniMaxAdapter",
    "DeepSeekAdapter",
]
