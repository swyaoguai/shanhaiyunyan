"""
MiniMax适配器
文档: https://www.minimaxi.com/platform_overview
"""

from typing import Dict, Any, List
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class MiniMaxAdapter(BaseLLMAdapter):
    """MiniMax适配器"""

    AVAILABLE_MODELS = [
        "MiniMax-Text-01",
        "abab6.5s-chat",
        "abab6.5-chat",
        "abab6.5t-chat",
        "abab5.5s-chat",
        "abab5.5-chat",
    ]

    def get_default_base_url(self) -> str:
        return "https://api.minimax.chat/v1"

    def _get_endpoint(self) -> str:
        return "/text/chatcompletion_v2"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """转换请求为MiniMax格式"""
        messages = []
        for msg in request.messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            messages.append(msg_dict)

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        if request.stop:
            payload["stop"] = request.stop

        # MiniMax特有参数
        if "tools" in request.extra_params:
            payload["tools"] = request.extra_params["tools"]
        if "tool_choice" in request.extra_params:
            payload["tool_choice"] = request.extra_params["tool_choice"]
        if "mask_sensitive_info" in request.extra_params:
            payload["mask_sensitive_info"] = request.extra_params["mask_sensitive_info"]

        return payload

    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        """转换MiniMax响应为统一格式"""
        # MiniMax的响应结构
        choices = raw_response.get("choices", [])
        usage = raw_response.get("usage")

        return ChatCompletionResponse(
            id=raw_response.get("id", ""),
            model=raw_response.get("model", ""),
            choices=choices,
            usage=usage,
            raw_response=raw_response,
        )
