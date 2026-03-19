"""
热点搜索 Skill 测试脚本
"""
import sys
import io
from pathlib import Path

# 设置标准输出为 UTF-8 编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from skills.trends_search.scripts.trends_service import get_service


def test_platform(service, platform_name: str, method_name: str):
    """测试单个平台"""
    print(f"\n{'='*60}")
    print(f"测试 {platform_name}")
    print(f"{'='*60}")
    
    try:
        method = getattr(service, method_name)
        result = method(limit=5)
        
        if result["success"]:
            print(f"[成功] 获取 {result['count']} 条数据")
            for item in result["data"]:
                print(f"  {item['rank']}. {item['title']}")
                if item['hot']:
                    print(f"     热度: {item['hot']}")
        else:
            print(f"[失败] {result.get('error', '未知错误')}")
    except Exception as e:
        print(f"[异常] {e}")


def main():
    """主测试函数"""
    print("开始测试热点搜索 Skill")
    print("="*60)
    
    service = get_service()
    
    # 测试所有平台
    platforms = [
        ("微博热搜", "get_weibo_trending"),
        ("知乎热榜", "get_zhihu_trending"),
        ("百度热搜", "get_baidu_trending"),
        ("抖音热点", "get_douyin_trending"),
        ("今日头条", "get_toutiao_trending"),
        ("36氪快讯", "get_36kr_trending"),
        ("少数派", "get_sspai_trending"),
        ("IT之家", "get_ithome_trending"),
        ("澎湃新闻", "get_thepaper_trending"),
        ("今日热榜", "get_tophub_trending"),
    ]
    
    success_count = 0
    for platform_name, method_name in platforms:
        try:
            test_platform(service, platform_name, method_name)
            success_count += 1
        except Exception as e:
            print(f"[错误] 测试 {platform_name} 时出错: {e}")
    
    print(f"\n{'='*60}")
    print(f"测试完成: {success_count}/{len(platforms)} 个平台测试成功")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()