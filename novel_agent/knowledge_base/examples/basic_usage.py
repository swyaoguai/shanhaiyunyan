"""
知识库基本使用示例

运行前请确保:
1. 安装依赖: pip install chromadb httpx
2. 设置环境变量: SILICONFLOW_API_KEY=your_api_key

运行方式:
    python -m novel_agent.knowledge_base.examples.basic_usage
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from novel_agent.knowledge_base import KnowledgeBase


def main():
    # ============ 初始化知识库 ============
    print("=" * 50)
    print("初始化知识库...")
    
    # 生产环境需要配置 SILICONFLOW_API_KEY 环境变量
    # 或在 novel_agent/data/knowledge_base_config.json 中配置
    kb = KnowledgeBase(
        project_id="demo_novel",
        use_mock_embeddings=False  # 禁止使用模拟服务
    )
    
    print(f"知识库初始化完成！")
    
    # ============ 添加章节 ============
    print("\n" + "=" * 50)
    print("添加章节内容...")
    
    # 添加第一章
    result1 = kb.add_chapter(
        chapter_id="chapter_1",
        title="第一章 命运的开端",
        content="""
        夜幕降临，古老的青云山笼罩在一片朦胧的月色之中。
        
        张小凡站在山门前，望着远处层叠的山峰，心中充满了对未来的期待。
        作为一个刚入门的弟子，他知道自己的修炼之路才刚刚开始。
        
        "小凡，该去领取法器了。"师兄的声音从身后传来。
        
        张小凡转过身，看到师兄陈师兄正朝他走来。陈师兄是青云门的内门弟子，
        已经修炼了十年有余，在门中颇有声望。
        
        "是，师兄。"张小凡恭敬地回答，跟着陈师兄向藏经阁走去。
        
        藏经阁位于青云山的东侧，是一座七层高的古老建筑。
        据说这里收藏着青云门历代祖师留下的功法秘籍和各种珍贵法器。
        """,
        chapter_number=1,
        metadata={"location": "青云山", "main_character": "张小凡"}
    )
    
    print(f"第一章添加结果: 成功={result1.success}, 字数={result1.word_count}, 分块={result1.chunk_count}")
    
    # 添加第二章
    result2 = kb.add_chapter(
        chapter_id="chapter_2",
        title="第二章 藏经阁的秘密",
        content="""
        藏经阁内灯火通明，无数书架整齐地排列着。
        
        张小凡跟着陈师兄穿过一排排书架，来到了一个隐秘的角落。
        这里存放着专门给新入门弟子使用的入门法器。
        
        "小凡，选一件适合你的法器吧。"陈师兄说道。
        
        张小凡仔细地看着眼前的法器，有剑、有扇、有笔、有珠...
        每一件都散发着淡淡的灵光。
        
        突然，他的目光被角落里一根不起眼的木棍吸引住了。
        那木棍通体漆黑，没有任何装饰，看起来普普通通。
        但张小凡莫名地感到一阵亲切。
        
        "我选这个。"张小凡指着那根木棍说道。
        
        陈师兄愣了一下，随后笑道："你倒是眼光独特。这根'烧火棍'在这里放了好几十年，
        从来没有人选过它。既然你喜欢，那就拿去吧。"
        """,
        chapter_number=2,
        metadata={"location": "藏经阁", "main_character": "张小凡"}
    )
    
    print(f"第二章添加结果: 成功={result2.success}, 字数={result2.word_count}, 分块={result2.chunk_count}")
    
    # 添加第三章
    result3 = kb.add_chapter(
        chapter_id="chapter_3",
        title="第三章 初次修炼",
        content="""
        回到住处后，张小凡开始了他的第一次修炼。
        
        按照门规，新弟子需要先修炼最基础的《青云心法》入门篇。
        这套心法虽然简单，却是青云门所有功法的基础。
        
        张小凡盘膝坐下，将那根木棍放在身前，开始按照心法中描述的方法运转气息。
        
        奇怪的是，当他开始修炼时，那根木棍竟然微微发出了一丝温热。
        这让张小凡感到十分惊讶，因为按照常理，普通的木棍是不会有这种反应的。
        
        "难道这根棍子真的有什么特别之处？"张小凡心中暗想。
        
        但无论他如何尝试，都无法引发更多的变化。
        最终，他只能暂时放下这个疑问，专心修炼心法。
        
        就这样，张小凡开始了他在青云门的修炼生活。
        每天天不亮就起床练功，日落后还要研读经书。
        虽然辛苦，但他从未有过一丝懈怠。
        """,
        chapter_number=3,
        metadata={"location": "弟子住处", "main_character": "张小凡"}
    )
    
    print(f"第三章添加结果: 成功={result3.success}, 字数={result3.word_count}, 分块={result3.chunk_count}")
    
    # ============ 检索测试 ============
    print("\n" + "=" * 50)
    print("检索测试...")
    
    # 语义检索
    print("\n【向量语义检索】查询: '张小凡的法器是什么'")
    response = kb.vector_search("张小凡的法器是什么", top_k=3)
    print(f"找到 {response.total} 条结果, 耗时 {response.took_ms}ms")
    for i, result in enumerate(response.results):
        print(f"  [{i+1}] 分数={result.score:.3f}, 来源={result.chapter_id}")
        print(f"      内容: {result.document[:80]}...")
    
    # 全文检索
    print("\n【全文关键词检索】查询: '烧火棍'")
    response = kb.fulltext_search("烧火棍", top_k=3)
    print(f"找到 {response.total} 条结果, 耗时 {response.took_ms}ms")
    for i, result in enumerate(response.results):
        print(f"  [{i+1}] 分数={result.score:.3f}, 来源={result.chapter_id}")
        if result.highlight:
            print(f"      高亮: {result.highlight}")
    
    # 混合检索
    print("\n【混合检索】查询: '青云门的藏经阁'")
    response = kb.search("青云门的藏经阁", top_k=3, search_type="hybrid")
    print(f"找到 {response.total} 条结果, 耗时 {response.took_ms}ms")
    for i, result in enumerate(response.results):
        print(f"  [{i+1}] 分数={result.score:.3f}, 来源={result.chapter_id}")
        print(f"      内容: {result.document[:80]}...")
    
    # 带章节过滤的检索
    print("\n【带章节过滤的检索】查询: '张小凡', 只搜索第一章")
    response = kb.search("张小凡", top_k=3, chapter_filter=["chapter_1"])
    print(f"找到 {response.total} 条结果")
    
    # ============ 章节导航 ============
    print("\n" + "=" * 50)
    print("章节导航...")
    
    # 获取目录
    toc = kb.get_table_of_contents()
    print("\n【目录】")
    for item in toc:
        print(f"  第{item['chapter_number']}章: {item['title']} ({item['word_count']}字)")
    
    # 获取章节信息
    chapter = kb.get_chapter("chapter_2")
    if chapter:
        print(f"\n【章节信息】")
        print(f"  ID: {chapter.chapter_id}")
        print(f"  标题: {chapter.title}")
        print(f"  字数: {chapter.word_count}")
        print(f"  分块数: {chapter.chunk_count}")
    
    # 导航
    next_ch = kb.get_next_chapter("chapter_1")
    if next_ch:
        print(f"\n【导航】第一章的下一章是: {next_ch.title}")
    
    # ============ 统计信息 ============
    print("\n" + "=" * 50)
    print("统计信息...")
    
    stats = kb.get_statistics()
    print(f"  章节数: {stats['chapter_count']}")
    print(f"  总字数: {stats['total_words']}")
    print(f"  总分块数: {stats['total_chunks']}")
    print(f"  向量数: {stats['vector_count']}")
    
    # ============ 清理 ============
    print("\n" + "=" * 50)
    print("关闭知识库...")
    kb.close()
    print("完成！")


if __name__ == "__main__":
    main()