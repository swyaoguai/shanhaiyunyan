"""
阿里云通义千问适配器 (OpenAI兼容模式)
文档: https://help.aliyun.com/zh/model-studio/qwen-api-reference
"""

from typing import Dict, Any, List
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class AlibabaQwenAdapter(BaseLLMAdapter):
    """阿里通义千问适配器 - OpenAI兼容模式"""

    AVAILABLE_MODELS = [
        "qwen-max-latest", "qwen-max",
        "qwen-plus-latest", "qwen-plus",
        "qwen-turbo-latest", "qwen-turbo",
        "qwen-coder-plus", "qwen-coder-turbo",
        "qwen-math-plus", "qwen-math-turbo",
        "qwen-vl-plus", "qwen-vl-max",
    ]

    def get_default_base_url(self) -> str:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"

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

        # 添加额外参数
        payload.update(request.extra_params)

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
