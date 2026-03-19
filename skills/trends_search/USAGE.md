# 热点搜索 Skill 使用指南

## 快速开始

### 1. 在 Agent 中使用

```python
from novel_agent.agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def search_trends(self):
        # 获取微博热搜
        result = self.use_skill("trends_search", "get_weibo_trending", limit=10)
        
        if result["success"]:
            for item in result["data"]:
                print(f"{item['rank']}. {item['title']}")
```

### 2. 直接调用服务

```python
from skills.trends_search.scripts.trends_service import get_service

# 获取服务实例
service = get_service()

# 调用方法
result = service.get_zhihu_trending(limit=5)
print(result)
```

## 完整示例

### 示例 1: 获取多平台热点

```python
def get_multi_platform_trends():
    """获取多个平台的热点"""
    from skills.trends_search.scripts.trends_service import get_service
    
    service = get_service()
    platforms = [
        ("微博", "get_weibo_trending"),
        ("知乎", "get_zhihu_trending"),
        ("抖音", "get_douyin_trending")
    ]
    
    all_trends = {}
    for name, method in platforms:
        result = getattr(service, method)(limit=5)
        if result["success"]:
            all_trends[name] = result["data"]
    
    return all_trends
```

### 示例 2: 在 Coordinator 中使用

```python
class Coordinator(BaseAgent):
    def analyze_hot_topics(self, platforms: List[str], limit: int = 10):
        """分析热点话题"""
        method_map = {
            "weibo": "get_weibo_trending",
            "zhihu": "get_zhihu_trending",
            "toutiao": "get_toutiao_trending"
        }
        
        results = []
        for platform in platforms:
            if platform in method_map:
                result = self.use_skill(
                    "trends_search",
                    method_map[platform],
                    limit=limit
                )
                if result["success"]:
                    results.extend(result["data"])
        
        return results
```

### 示例 3: 错误处理

```python
def safe_get_trends(platform: str = "weibo", limit: int = 10):
    """安全获取热点数据"""
    from skills.trends_search.scripts.trends_service import get_service
    
    service = get_service()
    method_name = f"get_{platform}_trending"
    
    try:
        if not hasattr(service, method_name):
            return {"success": False, "error": f"不支持的平台: {platform}"}
        
        method = getattr(service, method_name)
        result = method(limit=limit)
        
        if not result["success"]:
            print(f"获取失败: {result.get('error')}")
            return {"success": False, "data": []}
        
        return result
        
    except Exception as e:
        print(f"异常: {e}")
        return {"success": False, "error": str(e)}
```

### 示例 4: 数据聚合分析

```python
def aggregate_trends(limit: int = 20):
    """聚合分析多平台热点"""
    from skills.trends_search.scripts.trends_service import get_service
    from collections import Counter
    
    service = get_service()
    
    # 获取多平台数据
    platforms = ["weibo", "zhihu", "toutiao"]
    all_titles = []
    
    for platform in platforms:
        method = getattr(service, f"get_{platform}_trending")
        result = method(limit=limit)
        
        if result["success"]:
            all_titles.extend([item["title"] for item in result["data"]])
    
    # 简单的关键词提取（实际应用中可以使用更复杂的NLP方法）
    keywords = []
    for title in all_titles:
        keywords.extend(title.split())
    
    # 统计高频词
    counter = Counter(keywords)
    top_keywords = counter.most_common(10)
    
    return {
        "total_trends": len(all_titles),
        "top_keywords": top_keywords,
        "platforms": platforms
    }
```

## API 参考

### 通用参数

所有方法都支持以下参数：

- `limit` (int, 可选): 返回的热点条数，默认 10

### 返回格式

成功时：
```python
{
    "success": True,
    "data": [
        {
            "rank": 1,
            "title": "热点标题",
            "hot": "热度值",
            "url": "详情链接"
        }
    ],
    "count": 10
}
```

失败时：
```python
{
    "success": False,
    "error": "错误信息"
}
```

## 最佳实践

### 1. 使用单例模式

```python
# 推荐：使用 get_service() 获取单例
service = get_service()

# 不推荐：每次都创建新实例
# service = TrendsSearchService()
```

### 2. 添加重试机制

```python
import time

def get_trends_with_retry(platform: str, max_retries: int = 3):
    """带重试的获取热点"""
    from skills.trends_search.scripts.trends_service import get_service
    
    service = get_service()
    method = getattr(service, f"get_{platform}_trending")
    
    for i in range(max_retries):
        result = method(limit=10)
        if result["success"]:
            return result
        
        if i < max_retries - 1:
            time.sleep(2 ** i)  # 指数退避
    
    return {"success": False, "error": "重试次数已用尽"}
```

### 3. 缓存结果

```python
from functools import lru_cache
import time

@lru_cache(maxsize=128)
def cached_get_trends(platform: str, timestamp: int):
    """缓存热点数据（按时间戳）"""
    from skills.trends_search.scripts.trends_service import get_service
    
    service = get_service()
    method = getattr(service, f"get_{platform}_trending")
    return method(limit=10)

# 使用（每5分钟更新一次）
current_time = int(time.time() / 300)  # 5分钟为单位
result = cached_get_trends("weibo", current_time)
```

## 常见问题

### Q: 为什么某些平台获取失败？

A: 可能的原因：
1. 网络连接问题
2. 平台 API 变更
3. 请求频率限制
4. 需要代理访问

### Q: 如何提高请求成功率？

A: 建议：
1. 添加请求间隔
2. 使用代理
3. 实现重试机制
4. 更新 User-Agent

### Q: 数据更新频率如何？

A: 实时获取，每次调用都会请求最新数据。建议在应用层实现缓存机制。

## 故障排查

### 1. 导入错误

```python
# 确保项目根目录在 sys.path 中
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
```

### 2. 编码问题

```python
# Windows 系统需要设置 UTF-8 编码
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

### 3. 网络超时

```python
# 调整超时时间
service = get_service()
service.timeout = 30  # 设置为 30 秒
```

## 更多资源

- [TrendRadar 项目](https://github.com/sansan0/TrendRadar)
- [项目文档](README.md)
- [API 说明](SKILL.md)