"""
字节跳动豆包适配器 (OpenAI兼容模式 - 通过火山引擎)
文档: https://www.volcengine.com/product/doubao
"""

from typing import Dict, Any, List
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class DoubaoAdapter(BaseLLMAdapter):
    """字节豆包适配器 - 通过火山引擎OpenAI兼容模式"""

    AVAILABLE_MODELS = [
        "doubao-1.5-pro-32k",
        "doubao-1.5-pro-256k",
        "doubao-1.5-lite-32k",
        "doubao-pro-32k",
        "doubao-pro-128k",
        "doubao-lite-4k",
        "doubao-lite-32k",
        "doubao-vision-pro-32k",
        "doubao-vision-lite-32k",
        "doubao-embedding",
        "doubao-embedding-large",
    ]

    def get_default_base_url(self) -> str:
        return "https://ark.cn-beijing.volces.com/api/v3"

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

        # 豆包特有参数
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
