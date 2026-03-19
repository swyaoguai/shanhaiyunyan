"""
讯飞星火适配器 (SparkDesk)
文档: https://www.xfyun.cn/doc/spark/HTTP调用文档.html
讯飞星火使用appId/apiKey/apiSecret进行鉴权
"""

import time
import hashlib
import hmac
from typing import Dict, Any, List
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
import requests
from . import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse, Message


class iFlytekAdapter(BaseLLMAdapter):
    """讯飞星火适配器"""

    AVAILABLE_MODELS = [
        "generalv3.5",      # 星火V3.5
        "generalv3",        # 星火V3.0
        "generalv2.5",      # 星火V2.5
        "generalv2",        # 星火V2.0
        "generalv1.5",      # 星火V1.5
        "general",          # 星火V1.0
        "4.0Ultra",         # 星火4.0
        "pro-128k",         # 专业版128K
        "max-32k",          # 最大32K
        "lite",             # 轻量版
    ]

    def __init__(self, api_key: str, api_secret: str, app_id: str = "", **kwargs):
        # api_key在这里对应apiSecret，需要特殊处理
        super().__init__(api_key, api_secret, **kwargs)
        self.app_id = app_id or kwargs.get("app_id", "")
        self.api_secret = api_secret  # 实际鉴权用的apiSecret

    def get_default_base_url(self) -> str:
        return "https://spark-api-open.xf-yun.com/v1"

    def _get_endpoint(self) -> str:
        return "/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        # 讯飞新版HTTP API使用Bearer Token方式
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """转换请求为讯飞格式"""
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

        # 讯飞特有参数
        if "user" in request.extra_params:
            payload["user"] = request.extra_params["user"]

        payload.update({k: v for k, v in request.extra_params.items()
                       if k != "user"})

        return payload

    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        """转换讯飞响应为统一格式"""
        choices = raw_response.get("choices", [])
        usage = raw_response.get("usage")

        return ChatCompletionResponse(
            id=raw_response.get("id", str(int(time.time()))),
            model=raw_response.get("model", ""),
            choices=choices,
            usage=usage,
            created=raw_response.get("created", 0),
            raw_response=raw_response,
        )
