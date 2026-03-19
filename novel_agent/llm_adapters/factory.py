"""
LLM适配器工厂和统一接口
"""

import os
from typing import Optional, Dict, Any
from . import ProviderType, Message, ChatCompletionRequest, ChatCompletionResponse
from .baidu import BaiduAdapter
from .alibaba import AlibabaQwenAdapter
from .iflytek import iFlytekAdapter
from .zhipu import ZhipuAIAdapter
from .moonshot import MoonshotAdapter
from .doubao import DoubaoAdapter
from .minimax import MiniMaxAdapter
from .deepseek import DeepSeekAdapter


class LLMAdapterFactory:
    """LLM适配器工厂"""

    _adapters = {
        ProviderType.BAIDU: BaiduAdapter,
        ProviderType.ALIBABA: AlibabaQwenAdapter,
        ProviderType.IFLYTEK: iFlytekAdapter,
        ProviderType.ZHIPU: ZhipuAIAdapter,
        ProviderType.MOONSHOT: MoonshotAdapter,
        ProviderType.DOUBAO: DoubaoAdapter,
        ProviderType.MINIMAX: MiniMaxAdapter,
        ProviderType.DEEPSEEK: DeepSeekAdapter,
    }

    @classmethod
    def create(
        cls,
        provider: ProviderType,
        api_key: str,
        api_secret: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        创建适配器实例

        Args:
            provider: 服务商类型
            api_key: API密钥
            api_secret: API密钥（用于需要双密钥的服务商如百度、讯飞）
            **kwargs: 其他参数（如app_id、base_url等）
        """
        adapter_class = cls._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported provider: {provider}")

        return adapter_class(api_key=api_key, api_secret=api_secret, **kwargs)

    @classmethod
    def create_from_env(cls, provider: ProviderType, **kwargs) -> Any:
        """
        从环境变量创建适配器实例

        环境变量命名规范：
        - {PROVIDER}_API_KEY: API密钥
        - {PROVIDER}_API_SECRET: API密钥（需要时）
        - {PROVIDER}_APP_ID: 应用ID（需要时）
        """
        prefix = provider.value.upper()

        api_key = os.getenv(f"{prefix}_API_KEY")
        if not api_key:
            # 尝试常见变体
            api_key = os.getenv(f"{prefix}_KEY") or os.getenv(f"{prefix}_TOKEN")

        if not api_key:
            raise ValueError(f"Missing API key for {provider.value}. "
                           f"Set {prefix}_API_KEY environment variable.")

        api_secret = os.getenv(f"{prefix}_API_SECRET")
        app_id = os.getenv(f"{prefix}_APP_ID")

        if app_id:
            kwargs["app_id"] = app_id

        return cls.create(provider, api_key, api_secret, **kwargs)

    @classmethod
    def get_available_models(cls, provider: ProviderType) -> list:
        """获取服务商支持的模型列表"""
        adapter_class = cls._adapters.get(provider)
        if adapter_class and hasattr(adapter_class, "AVAILABLE_MODELS"):
            return adapter_class.AVAILABLE_MODELS
        return []

    @classmethod
    def list_providers(cls) -> list:
        """列出所有支持的服务商"""
        return [p for p in ProviderType]


class UnifiedLLM:
    """统一LLM调用接口"""

    def __init__(
        self,
        provider: ProviderType,
        api_key: str,
        api_secret: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ):
        self.adapter = LLMAdapterFactory.create(
            provider, api_key, api_secret, **kwargs
        )
        self.provider = provider
        self.default_model = model

    @classmethod
    def from_env(cls, provider: ProviderType, model: Optional[str] = None, **kwargs):
        """从环境变量创建"""
        adapter = LLMAdapterFactory.create_from_env(provider, **kwargs)
        instance = cls.__new__(cls)
        instance.adapter = adapter
        instance.provider = provider
        instance.default_model = model
        return instance

    def chat(
        self,
        messages: list,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        简单对话接口

        Args:
            messages: 消息列表，格式为[(role, content), ...] 或 Message对象列表
            model: 模型名称，默认使用初始化时指定的模型
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数

        Returns:
            模型回复内容
        """
        # 转换消息格式
        if messages and isinstance(messages[0], tuple):
            msg_list = [Message(role=m[0], content=m[1]) for m in messages]
        else:
            msg_list = messages if isinstance(messages[0], Message) else [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages
            ]

        request = ChatCompletionRequest(
            model=model or self.default_model or self._get_default_model(),
            messages=msg_list,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_params=kwargs,
        )

        response = self.adapter.chat_completion(request)
        return response.get_content()

    async def achat(
        self,
        messages: list,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """异步简单对话接口"""
        if messages and isinstance(messages[0], tuple):
            msg_list = [Message(role=m[0], content=m[1]) for m in messages]
        else:
            msg_list = messages if isinstance(messages[0], Message) else [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages
            ]

        request = ChatCompletionRequest(
            model=model or self.default_model or self._get_default_model(),
            messages=msg_list,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_params=kwargs,
        )

        response = await self.adapter.achat_completion(request)
        return response.get_content()

    async def achat_stream(
        self,
        messages: list,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """异步流式对话接口"""
        if messages and isinstance(messages[0], tuple):
            msg_list = [Message(role=m[0], content=m[1]) for m in messages]
        else:
            msg_list = messages if isinstance(messages[0], Message) else [
                Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages
            ]

        request = ChatCompletionRequest(
            model=model or self.default_model or self._get_default_model(),
            messages=msg_list,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_params=kwargs,
        )

        async for chunk in self.adapter.achat_completion_stream(request):
            yield chunk

    def _get_default_model(self) -> str:
        """获取默认模型"""
        models = LLMAdapterFactory.get_available_models(self.provider)
        return models[0] if models else ""

    def get_available_models(self) -> list:
        """获取当前服务商支持的所有模型"""
        return LLMAdapterFactory.get_available_models(self.provider)


# 便捷函数
def create_llm(
    provider: str,
    api_key: str,
    api_secret: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> UnifiedLLM:
    """
    创建统一LLM实例的便捷函数

    Args:
        provider: 服务商名称 (baidu/alibaba/iflytek/zhipu/moonshot/doubao/minimax/deepseek)
        api_key: API密钥
        api_secret: API密钥（需要时，如百度、讯飞）
        model: 默认模型名称
        **kwargs: 其他参数
    """
    provider_type = ProviderType(provider.lower())
    return UnifiedLLM(provider_type, api_key, api_secret, model, **kwargs)


def create_llm_from_env(provider: str, model: Optional[str] = None, **kwargs) -> UnifiedLLM:
    """从环境变量创建统一LLM实例"""
    provider_type = ProviderType(provider.lower())
    return UnifiedLLM.from_env(provider_type, model, **kwargs)
