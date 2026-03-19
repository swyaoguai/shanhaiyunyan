# 中国AI大模型API统一适配器

支持8大国内主流AI服务商的统一API适配层，提供一致接口调用各种大语言模型。

## 支持的AI服务商

| 服务商 | 类型标识 | 特点 | 认证方式 |
|--------|----------|------|----------|
| **百度文心一言** | `baidu` | 中文理解强，企业场景丰富 | OAuth2 access_token |
| **阿里通义千问** | `alibaba` | OpenAI兼容，生态完善 | Bearer Token |
| **讯飞星火** | `iflytek` | 语音识别强，多模态 | Bearer Token |
| **智谱AI ChatGLM** | `zhipu` | 开源模型，性价比高 | Bearer Token |
| **月之暗面 Kimi** | `moonshot` | 长文本支持优秀 | Bearer Token |
| **字节豆包** | `doubao` | 火山引擎，推理快 | Bearer Token |
| **MiniMax** | `minimax` | 多模态能力强 | Bearer Token |
| **DeepSeek** | `deepseek` | 代码能力突出 | Bearer Token |

## 快速开始

### 安装

```bash
# 确保已安装依赖
pip install aiohttp requests
```

### 基础使用

```python
from novel_agent.llm_adapters import create_llm

# 创建LLM实例（以阿里通义为例）
llm = create_llm(
    provider="alibaba",
    api_key="your-api-key",
    model="qwen-plus-latest"
)

# 简单对话
response = llm.chat([
    ("system", "你是一个 helpful 的助手"),
    ("user", "你好，请介绍一下自己")
])
print(response)
```

### 从环境变量创建

```python
from novel_agent.llm_adapters import create_llm_from_env

# 设置环境变量：ALIBABA_API_KEY=your-api-key
llm = create_llm_from_env("alibaba")

response = llm.chat([("user", "你好")])
```

## 环境变量配置

各服务商的环境变量名称：

```bash
# 百度文心 (需要API Key和Secret Key)
export BAIDU_API_KEY="your-api-key"
export BAIDU_API_SECRET="your-secret-key"

# 阿里通义
export ALIBABA_API_KEY="your-api-key"

# 讯飞星火 (可选: IFLYTEK_APP_ID)
export IFLYTEK_API_KEY="your-api-key"
export IFLYTEK_API_SECRET="your-api-secret"

# 智谱AI
export ZHIPU_API_KEY="your-api-key"

# 月之暗面Kimi
export MOONSHOT_API_KEY="your-api-key"

# 字节豆包
export DOUBAO_API_KEY="your-api-key"

# MiniMax
export MINIMAX_API_KEY="your-api-key"

# DeepSeek
export DEEPSEEK_API_KEY="your-api-key"
```

## 各服务商详细使用

### 1. 百度文心一言 (Baidu ERNIE)

```python
from novel_agent.llm_adapters import create_llm

llm = create_llm(
    provider="baidu",
    api_key="your-api-key",
    api_secret="your-secret-key",
    model="ernie-4.0-8k-latest"
)

# 查看可用模型
print(llm.get_available_models())

response = llm.chat([
    ("user", "请写一首关于春天的诗")
], temperature=0.8)
```

**可用模型**：`ernie-4.0-8k-latest`, `ernie-3.5-8k`, `ernie-speed-8k`, `ernie-lite-8k` 等

### 2. 阿里通义千问 (Alibaba Qwen)

```python
from novel_agent.llm_adapters import create_llm, ProviderType

# 方式1：使用类型枚举
llm = create_llm(
    provider=ProviderType.ALIBABA,
    api_key="your-api-key",
    model="qwen-max-latest"
)

# 方式2：使用字符串
llm = create_llm(
    provider="alibaba",
    api_key="your-api-key",
    model="qwen-plus-latest"
)

# 复杂对话
response = llm.chat(
    messages=[
        ("system", "你是一个专业的Python程序员"),
        ("user", "写一个快速排序算法")
    ],
    temperature=0.3,
    max_tokens=2000
)
```

**可用模型**：`qwen-max-latest`, `qwen-plus-latest`, `qwen-turbo-latest`, `qwen-coder-plus` 等

### 3. 讯飞星火 (iFlytek Spark)

```python
llm = create_llm(
    provider="iflytek",
    api_key="your-api-key",
    api_secret="your-api-secret",  # 可选
    model="generalv3.5"
)
```

**可用模型**：`generalv3.5`, `generalv3`, `4.0Ultra`, `pro-128k`, `lite` 等

### 4. 智谱AI ChatGLM (Zhipu)

```python
llm = create_llm(
    provider="zhipu",
    api_key="your-api-key",
    model="glm-4.7"
)
```

**可用模型**：`glm-4.7`, `glm-4.6`, `glm-4.5`, `glm-4-flash`, `glm-4-air` 等

### 5. 月之暗面 Kimi (Moonshot)

```python
llm = create_llm(
    provider="moonshot",
    api_key="your-api-key",
    model="kimi-k2-5"
)

# Kimi擅长长文本
long_text = "..." # 长文档内容
response = llm.chat([
    ("system", "总结以下文档的主要观点"),
    ("user", long_text)
])
```

**可用模型**：`kimi-k2-5`, `kimi-k2-0`, `moonshot-v1-32k`, `moonshot-v1-128k` 等

### 6. 字节豆包 (Doubao)

```python
llm = create_llm(
    provider="doubao",
    api_key="your-api-key",
    model="doubao-1.5-pro-32k"
)
```

**可用模型**：`doubao-1.5-pro-32k`, `doubao-1.5-lite-32k`, `doubao-pro-128k` 等

### 7. MiniMax

```python
llm = create_llm(
    provider="minimax",
    api_key="your-api-key",
    model="MiniMax-Text-01"
)
```

**可用模型**：`MiniMax-Text-01`, `abab6.5s-chat`, `abab6.5-chat` 等

### 8. DeepSeek

```python
llm = create_llm(
    provider="deepseek",
    api_key="your-api-key",
    model="deepseek-chat"
)

# 使用推理模型
response = llm.chat(
    messages=[("user", "解这个方程：2x + 5 = 15")],
    model="deepseek-reasoner"
)
```

**可用模型**：`deepseek-chat`, `deepseek-reasoner`, `deepseek-coder`

## 高级用法

### 异步调用

```python
import asyncio
from novel_agent.llm_adapters import create_llm

llm = create_llm("alibaba", "your-api-key")

async def main():
    response = await llm.achat([
        ("user", "异步你好")
    ])
    print(response)

asyncio.run(main())
```

### 流式输出

```python
import asyncio

async def stream_chat():
    llm = create_llm("alibaba", "your-api-key")

    async for chunk in llm.achat_stream([
        ("user", "讲一个长故事")
    ]):
        print(chunk, end="", flush=True)

asyncio.run(stream_chat())
```

### 使用适配器工厂

```python
from novel_agent.llm_adapters import LLMAdapterFactory, ProviderType

# 查看所有支持的服务商
providers = LLMAdapterFactory.list_providers()
for p in providers:
    print(f"{p.value}: {p.name}")

# 获取某服务商支持的模型
models = LLMAdapterFactory.get_available_models(ProviderType.ALIBABA)
print(models)

# 直接创建适配器
adapter = LLMAdapterFactory.create(
    provider=ProviderType.ZHIPU,
    api_key="your-key"
)
```

### 自定义参数

```python
from novel_agent.llm_adapters import create_llm, Message

llm = create_llm("alibaba", "your-key")

# 使用额外参数（服务商特定）
response = llm.chat(
    messages=[
        Message(role="user", content="你好")
    ],
    temperature=0.5,
    max_tokens=500,
    top_p=0.9,
    # 阿里特定参数
    result_format="message",  # 返回格式
    enable_search=True,       # 启用搜索
)
```

## 完整示例

见 `examples/` 目录下的示例文件：
- `example_sync.py` - 同步调用示例
- `example_async.py` - 异步调用示例
- `example_stream.py` - 流式调用示例
- `example_multi_provider.py` - 多服务商对比示例

## 开发指南

### 添加新的适配器

1. 继承 `BaseLLMAdapter`
2. 实现必需的方法
3. 在 `factory.py` 中注册

```python
from novel_agent.llm_adapters import BaseLLMAdapter, ChatCompletionRequest, ChatCompletionResponse

class MyAdapter(BaseLLMAdapter):
    def get_default_base_url(self) -> str:
        return "https://api.example.com/v1"

    def _get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _convert_request(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        # 转换请求格式
        return {...}

    def _convert_response(self, raw_response: Dict[str, Any]) -> ChatCompletionResponse:
        # 转换响应格式
        return ChatCompletionResponse(...)
```

## 注意事项

1. **API密钥安全**：切勿将API密钥硬编码在代码中，使用环境变量
2. **错误处理**：网络错误或API限制时会自动重试3次
3. **超时设置**：默认超时60秒，可通过 `timeout` 参数调整
4. **令牌消耗**：注意监控各服务商的令牌消耗情况
5. **模型可用性**：部分模型可能需要申请权限

## 获取API密钥

- **百度**：https://cloud.baidu.com/product/wenxinworkshop
- **阿里**：https://dashscope.console.aliyun.com
- **讯飞**：https://xinghuo.xfyun.cn/sparkapi
- **智谱**：https://open.bigmodel.cn
- **Kimi**：https://platform.moonshot.cn
- **豆包**：https://console.volcengine.com/ark
- **MiniMax**：https://www.minimaxi.com/platform
- **DeepSeek**：https://platform.deepseek.com

## 许可证

MIT License
