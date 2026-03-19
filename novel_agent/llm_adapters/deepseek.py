"""
DeepSeek适配器
文档: https://platform.deepseek.com/api-docs
DeepSeek API与OpenAI API兼容
"""

from typing import Dict, Any, List
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class DeepSeekAdapter(BaseLLMAdapter):
    """DeepSeek适配器 - OpenAI兼容模式"""

    AVAILABLE_MODELS = [
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-coder",
    ]

    def get_default_base_url(self) -> str:
        return "https://api.deepseek.com"

    def _get_endpoint(self) -> str:
        return "/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """转换请求为OpenAI兼容格式"""
        messages = []
        for msg in request.messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.name:
                msg_dict["name"] = msg.name
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

        # DeepSeek特有参数
        if "response_format" in request.extra_params:
            payload["response_format"] = request.extra_params["response_format"]
        if "tools" in request.extra_params:
            payload["tools"] = request.extra_params["tools"]
        if "tool_choice" in request.extra_params:
            payload["tool_choice"] = request.extra_params["tool_choice"]
        if "logprobs" in request.extra_params:
            payload["logprobs"] = request.extra_params["logprobs"]
        if "top_logprobs" in request.extra_params:
            payload["top_logprobs"] = request.extra_params["top_logprobs"]

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
