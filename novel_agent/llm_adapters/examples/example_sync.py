"""
同步调用示例
"""
from novel_agent.llm_adapters import create_llm, ProviderType, LLMAdapterFactory


def basic_chat_example():
    """基础对话示例"""
    # 从环境变量读取API密钥
    llm = create_llm("alibaba", "your-api-key-here", model="qwen-plus-latest")

    # 简单对话
    response = llm.chat([
        ("system", "你是一个 helpful 的助手，用中文回答问题"),
        ("user", "请介绍一下Python编程语言的特点")
    ])

    print("AI回复:", response)


def multi_turn_chat():
    """多轮对话示例"""
    llm = create_llm("zhipu", "your-api-key", model="glm-4.7")

    messages = [
        ("system", "你是一个专业的技术顾问"),
        ("user", "什么是微服务架构？"),
    ]

    response1 = llm.chat(messages)
    print("第一轮:", response1)

    messages.append(("assistant", response1))
    messages.append(("user", "它有什么优缺点？"))

    response2 = llm.chat(messages)
    print("第二轮:", response2)


def list_models():
    """列出各服务商支持的模型"""
    print("支持的AI服务商和模型:")
    print("-" * 50)

    providers = LLMAdapterFactory.list_providers()
    for provider in providers:
        models = LLMAdapterFactory.get_available_models(provider)
        print(f"\n{provider.value.upper()}:")
        for model in models[:5]:  # 只显示前5个
            print(f"  - {model}")
        if len(models) > 5:
            print(f"  ... 还有 {len(models) - 5} 个模型")


def compare_providers():
    """对比不同服务商对同一问题的回答"""
    question = "用一句话解释什么是人工智能"

    providers_config = [
        ("alibaba", "your-key", "qwen-plus-latest"),
        ("zhipu", "your-key", "glm-4.7"),
        ("deepseek", "your-key", "deepseek-chat"),
    ]

    print(f"问题: {question}\n")

    for provider, key, model in providers_config:
        try:
            llm = create_llm(provider, key, model=model)
            response = llm.chat([("user", question)])
            print(f"[{provider.upper()} - {model}]")
            print(f"{response}\n")
        except Exception as e:
            print(f"[{provider.upper()}] 错误: {e}\n")


def advanced_params():
    """使用高级参数"""
    llm = create_llm("alibaba", "your-key", model="qwen-max-latest")

    # 创意写作 - 较高temperature
    creative = llm.chat(
        messages=[("user", "写一个科幻故事的开头")],
        temperature=0.9,
        max_tokens=500
    )
    print("创意版本:", creative)

    # 事实问答 - 较低temperature
    factual = llm.chat(
        messages=[("user", "Python是什么时候发布的？")],
        temperature=0.2,
        max_tokens=200
    )
    print("事实版本:", factual)


if __name__ == "__main__":
    print("=== 基础对话示例 ===")
    # basic_chat_example()

    print("\n=== 列出支持模型 ===")
    list_models()

    # print("\n=== 多轮对话 ===")
    # multi_turn_chat()

    # print("\n=== 服务商对比 ===")
    # compare_providers()

    # print("\n=== 高级参数使用 ===")
    # advanced_params()
