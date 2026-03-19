"""
月之暗面 Moonshot Kimi 适配器 (OpenAI兼容模式)
文档: https://platform.moonshot.cn/docs
"""

from typing import Dict, Any, List
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class MoonshotAdapter(BaseLLMAdapter):
    """月之暗面 Moonshot Kimi 适配器 - OpenAI兼容模式"""

    AVAILABLE_MODELS = [
        "kimi-k2-0",
        "kimi-k2-0-32k",
        "kimi-k2-0-128k",
        "kimi-k2-5",
        "kimi-k2-5-32k",
        "kimi-k2-5-128k",
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "moonshot-v1-auto",
    ]

    def get_default_base_url(self) -> str:
        return "https://api.moonshot.cn/v1"

    def _get_endpoint(self) -> str:
        return "/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """转换请求为OpenAI兼容格式"""
        payload = {
            "model": request.model,
            "messages": self._convert_messages(request.messages),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        if request.stop:
            payload["stop"] = request.stop

        # Moonshot特有参数
        if "response_format" in request.extra_params:
            payload["response_format"] = request.extra_params["response_format"]
        if "tools" in request.extra_params:
            payload["tools"] = request.extra_params["tools"]
        if "tool_choice" in request.extra_params:
            payload["tool_choice"] = request.extra_params["tool_choice"]

        payload.update({k: v for k, v in request.extra_params.items()
                       if k not in ["response_format", "tools", "tool_choice"]})

        return payload

    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        """转换响应为统一格式"""
        return ChatCompletionResponse(
            id=raw_response.get("id", ""),
            model=raw_response.get("model", ""),
            choices=raw_response.get("choices", []),
            usage=raw_response.get("usage"),
            created=raw_response.get("created", 0),
            raw_response=raw_response,
        )

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """转换消息列表"""
        result = []
        for msg in messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.name:
                msg_dict["name"] = msg.name
            result.append(msg_dict)
        return result
