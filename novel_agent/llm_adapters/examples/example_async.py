"""
异步调用示例
"""
import asyncio
from novel_agent.llm_adapters import create_llm


async def basic_async_chat():
    """基础异步对话"""
    llm = create_llm("alibaba", "your-api-key", model="qwen-plus-latest")

    response = await llm.achat([
        ("user", "你好，请介绍一下异步编程")
    ])
    print("异步回复:", response)


async def parallel_requests():
    """并行请求多个服务商"""
    providers = [
        ("alibaba", "key1", "qwen-plus-latest"),
        ("zhipu", "key2", "glm-4.7"),
        ("deepseek", "key3", "deepseek-chat"),
    ]

    llms = [create_llm(p, k, model=m) for p, k, m in providers]
    question = "什么是机器学习？"

    # 并行发送请求
    tasks = [llm.achat([("user", question)]) for llm in llms]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for (provider, _, model), result in zip(providers, results):
        if isinstance(result, Exception):
            print(f"[{provider}] 错误: {result}")
        else:
            print(f"[{provider} - {model}]\n{result}\n")


async def batch_processing():
    """批量处理多个问题"""
    llm = create_llm("alibaba", "your-key", model="qwen-turbo-latest")

    questions = [
        "Python的list和tuple有什么区别？",
        "什么是装饰器？",
        "解释一下GIL",
        "如何优化Python性能？",
    ]

    tasks = [
        llm.achat([("user", q)], max_tokens=200)
        for q in questions
    ]

    results = await asyncio.gather(*tasks)

    for q, r in zip(questions, results):
        print(f"Q: {q}")
        print(f"A: {r}\n")


async def conversation_with_context():
    """带上下文的对话"""
    llm = create_llm("zhipu", "your-key", model="glm-4.7")

    messages = [("system", "你是一个Python专家")]

    questions = [
        "什么是生成器？",
        "如何使用它处理大数据？",
        "和列表推导式有什么区别？",
    ]

    for question in questions:
        messages.append(("user", question))
        response = await llm.achat(messages)
        messages.append(("assistant", response))

        print(f"Q: {question}")
        print(f"A: {response}\n")


if __name__ == "__main__":
    # 运行示例（取消注释来运行）

    # asyncio.run(basic_async_chat())
    # asyncio.run(parallel_requests())
    # asyncio.run(batch_processing())
    # asyncio.run(conversation_with_context())

    print("请取消注释相应的函数来运行示例")
    print("注意: 需要设置正确的API密钥才能运行")
