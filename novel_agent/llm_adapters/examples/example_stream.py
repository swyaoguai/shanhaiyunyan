"""
流式输出示例
"""
import asyncio
from novel_agent.llm_adapters import create_llm


async def stream_chat_example():
    """流式对话示例"""
    llm = create_llm("alibaba", "your-api-key", model="qwen-plus-latest")

    print("AI回复: ", end="", flush=True)

    async for chunk in llm.achat_stream([
        ("user", "写一首关于编程的诗")
    ]):
        print(chunk, end="", flush=True)

    print()  # 换行


async def stream_with_stats():
    """流式输出带统计信息"""
    llm = create_llm("moonshot", "your-key", model="kimi-k2-5")

    chunks = []
    print("生成中: ", end="", flush=True)

    async for chunk in llm.achat_stream([
        ("user", "解释什么是量子计算")
    ]):
        chunks.append(chunk)
        print(chunk, end="", flush=True)

    print(f"\n\n总字符数: {len(''.join(chunks))}")
    print(f"分块数量: {len(chunks)}")


async def interactive_stream():
    """交互式流式对话"""
    llm = create_llm("zhipu", "your-key", model="glm-4.7")

    print("交互式对话 (输入 'quit' 退出)")
    print("-" * 50)

    messages = []

    while True:
        user_input = input("\n你: ")
        if user_input.lower() == "quit":
            break

        messages.append(("user", user_input))

        print("AI: ", end="", flush=True)
        response_parts = []

        async for chunk in llm.achat_stream(messages):
            print(chunk, end="", flush=True)
            response_parts.append(chunk)

        response = "".join(response_parts)
        messages.append(("assistant", response))

        print()


async def multi_provider_stream():
    """多服务商流式对比"""
    providers = [
        ("alibaba", "key1", "qwen-plus-latest"),
        ("deepseek", "key2", "deepseek-chat"),
    ]

    question = "什么是神经网络？"

    for provider, key, model in providers:
        print(f"\n[{provider.upper()} - {model}]")
        print("-" * 30)

        try:
            llm = create_llm(provider, key, model=model)
            async for chunk in llm.achat_stream([("user", question)]):
                print(chunk, end="", flush=True)
            print()
        except Exception as e:
            print(f"错误: {e}")


async def stream_with_stop():
    """带停止条件的流式输出"""
    llm = create_llm("alibaba", "your-key", model="qwen-turbo-latest")

    # 设置停止词，当生成中包含"总之"时停止
    chunks = []
    stop_phrase = "总之"

    print("生成中 (将在遇到'总之'时停止): ", end="", flush=True)

    async for chunk in llm.achat_stream(
        [("user", "详细分析Python和Java的区别")],
        max_tokens=1000
    ):
        chunks.append(chunk)
        print(chunk, end="", flush=True)

        # 检查是否需要停止
        current_text = "".join(chunks)
        if stop_phrase in current_text:
            print(f"\n[检测到停止词 '{stop_phrase}'，提前结束]")
            break


if __name__ == "__main__":
    # 运行示例（取消注释来运行）

    # asyncio.run(stream_chat_example())
    # asyncio.run(stream_with_stats())
    # asyncio.run(interactive_stream())
    # asyncio.run(multi_provider_stream())
    # asyncio.run(stream_with_stop())

    print("请取消注释相应的函数来运行示例")
    print("注意: 需要设置正确的API密钥才能运行")
