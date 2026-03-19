"""
多服务商对比示例
"""
import asyncio
from novel_agent.llm_adapters import create_llm, ProviderType, LLMAdapterFactory


class ModelBenchmark:
    """模型对比测试"""

    def __init__(self):
        self.results = []

    async def test_single_provider(self, provider, key, model, question):
        """测试单个服务商"""
        try:
            llm = create_llm(provider, key, model=model)

            import time
            start = time.time()
            response = await llm.achat([("user", question)], max_tokens=500)
            elapsed = time.time() - start

            return {
                "provider": provider,
                "model": model,
                "response": response,
                "time": elapsed,
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "provider": provider,
                "model": model,
                "response": None,
                "time": None,
                "success": False,
                "error": str(e)
            }

    async def run_comparison(self, configs, questions):
        """运行对比测试"""
        for question in questions:
            print(f"\n{'=' * 60}")
            print(f"问题: {question}")
            print('=' * 60)

            tasks = [
                self.test_single_provider(p, k, m, question)
                for p, k, m in configs
            ]

            results = await asyncio.gather(*tasks)

            for r in results:
                if r["success"]:
                    print(f"\n[{r['provider']} - {r['model']}]")
                    print(f"耗时: {r['time']:.2f}s")
                    print(f"回复: {r['response'][:200]}...")
                else:
                    print(f"\n[{r['provider']}] 失败: {r['error']}")


async def feature_comparison():
    """特性对比测试"""

    # 不同特性的测试问题
    tests = {
        "代码能力": "写一个Python函数，计算斐波那契数列的第n项",
        "创意写作": "写一首关于秋天的七言绝句",
        "逻辑推理": "如果所有的A都是B，所有的B都是C，那么所有的A都是C吗？",
        "知识问答": "量子纠缠是什么？",
        "多语言": "Translate 'Hello, how are you?' to French, German, and Japanese",
    }

    configs = [
        ("alibaba", "your-key", "qwen-coder-plus"),
        ("deepseek", "your-key", "deepseek-coder"),
        ("zhipu", "your-key", "glm-4.7"),
    ]

    benchmark = ModelBenchmark()
    await benchmark.run_comparison(configs, list(tests.values()))


async def speed_comparison():
    """速度对比"""
    question = "用一句话回答：Python的优点是什么？"

    configs = [
        ("alibaba", "your-key", "qwen-turbo-latest"),
        ("alibaba", "your-key", "qwen-plus-latest"),
        ("zhipu", "your-key", "glm-4-flash"),
        ("deepseek", "your-key", "deepseek-chat"),
    ]

    print("速度对比测试 (同样的问题，各调用3次取平均)")
    print("-" * 60)

    for provider, key, model in configs:
        times = []
        llm = create_llm(provider, key, model=model)

        for i in range(3):
            import time
            start = time.time()
            try:
                await llm.achat([("user", question)], max_tokens=100)
                elapsed = time.time() - start
                times.append(elapsed)
            except Exception as e:
                print(f"  第{i+1}次调用失败: {e}")

        if times:
            avg_time = sum(times) / len(times)
            print(f"[{provider} - {model}] 平均响应时间: {avg_time:.2f}s")


async def context_length_test():
    """上下文长度测试"""

    # 生成不同长度的上下文
    contexts = {
        "短文本(1K)": "Python是一种编程语言。" * 50,
        "中文本(4K)": "人工智能是计算机科学的一个分支。" * 200,
        "长文本(16K)": "机器学习是AI的重要技术。" * 800,
    }

    configs = [
        ("moonshot", "your-key", "moonshot-v1-128k"),
        ("alibaba", "your-key", "qwen-max-latest"),
    ]

    question = "总结一下上面文本的主要内容"

    for context_name, context in contexts.items():
        print(f"\n{'=' * 60}")
        print(f"测试: {context_name} (约{len(context)}字符)")
        print('=' * 60)

        for provider, key, model in configs:
            try:
                llm = create_llm(provider, key, model=model)

                import time
                start = time.time()
                response = await llm.achat([
                    ("system", "你是一个总结助手"),
                    ("user", f"{context}\n\n{question}")
                ])
                elapsed = time.time() - start

                print(f"\n[{provider} - {model}]")
                print(f"耗时: {elapsed:.2f}s")
                print(f"回复: {response[:150]}...")
            except Exception as e:
                print(f"\n[{provider}] 错误: {e}")


def print_provider_info():
    """打印服务商信息"""
    print("支持的AI服务商")
    print("-" * 60)

    for provider in ProviderType:
        models = LLMAdapterFactory.get_available_models(provider)
        print(f"\n{provider.value.upper()}:")
        print(f"  模型数量: {len(models)}")
        print(f"  主要模型: {', '.join(models[:3])}")


if __name__ == "__main__":
    # 打印服务商信息
    print_provider_info()

    # 运行对比测试（需要设置正确的API密钥）
    # asyncio.run(feature_comparison())
    # asyncio.run(speed_comparison())
    # asyncio.run(context_length_test())
