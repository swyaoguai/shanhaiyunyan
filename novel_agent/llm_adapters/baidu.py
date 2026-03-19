"""
百度文心一言适配器 (千帆大模型平台)
文档: https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Nlks5zkzu
百度使用OAuth2认证，需要access_token
"""

import time
from typing import Dict, Any, List, Optional
import requests
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class BaiduAdapter(BaseLLMAdapter):
    """百度文心一言适配器 - 通过千帆大模型平台"""

    AVAILABLE_MODELS = [
        "ernie-4.0-8k-latest", "ernie-4.0-8k",
        "ernie-4.0-turbo-8k", "ernie-4.0-turbo-128k",
        "ernie-3.5-8k", "ernie-3.5-128k",
        "ernie-speed-8k", "ernie-speed-128k",
        "ernie-speed-pro-128k",
        "ernie-lite-8k", "ernie-lite-pro-8k",
        "ernie-tiny-8k",
        "ernie-novel-8k",
        "ernie-character-8k",
    ]

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        super().__init__(api_key, api_secret, **kwargs)
        self.access_token: Optional[str] = None
        self.token_expire_time: float = 0
        self.auth_base_url = "https://aip.baidubce.com/oauth/2.0/token"

    def get_default_base_url(self) -> str:
        return "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop"

    def _get_endpoint(self) -> str:
        # 百度需要模型名称作为端点的一部分
        return "/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        token = self._ensure_access_token()
        return {
            "Content-Type": "application/json",
        }

    def _ensure_access_token(self) -> str:
        """确保获取有效的access_token"""
        if self.access_token and time.time() < self.token_expire_time:
            return self.access_token

        # 获取新的access_token
        url = f"{self.auth_base_url}"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.api_secret,
        }

        response = requests.post(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        self.access_token = data["access_token"]
        # 提前5分钟过期，避免边界问题
        self.token_expire_time = time.time() + data.get("expires_in", 3600) - 300

        return self.access_token

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """转换请求为百度格式"""
        # 百度的消息格式与OpenAI相同
        messages = []
        for msg in request.messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            messages.append(msg_dict)

        payload = {
            "messages": messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.max_tokens:
            payload["max_output_tokens"] = request.max_tokens

        if request.stop:
            payload["stop"] = request.stop

        # 百度特有参数
        if "system" in request.extra_params:
            payload["system"] = request.extra_params["system"]
        if "disable_search" in request.extra_params:
            payload["disable_search"] = request.extra_params["disable_search"]
        if "enable_citation" in request.extra_params:
            payload["enable_citation"] = request.extra_params["enable_citation"]

        return payload

    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        """转换百度响应为统一格式"""
        # 百度的响应格式与OpenAI略有不同
        choices = []
        if "result" in raw_response:
            # 非流式响应
            choices.append({
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": raw_response.get("result", ""),
                },
                "finish_reason": "stop" if raw_response.get("is_end", False) else None,
            })
        elif "choices" in raw_response:
            choices = raw_response["choices"]

        usage = None
        if "usage" in raw_response:
            usage = raw_response["usage"]

        return ChatCompletionResponse(
            id=raw_response.get("id", str(int(time.time()))),
            model=raw_response.get("model", ""),
            choices=choices,
            usage=usage,
            raw_response=raw_response,
        )

    def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """重写以支持百度特定的URL格式"""
        token = self._ensure_access_token()
        url = f"{self.base_url}/chat/{request.model}?access_token={token}"
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
