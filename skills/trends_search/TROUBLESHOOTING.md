# 故障排查指南

## 常见问题

### 1. JSON解析失败 "Expecting value: line 1 column 1"

**原因：**
- 响应内容编码问题
- 响应被压缩但未正确解压
- 响应内容为空或格式错误

**解决方案：**
已在代码中添加自动编码检测和修复：
```python
# 确保正确的编码
if response.encoding is None or response.encoding == 'ISO-8859-1':
    response.encoding = 'utf-8'
```

### 2. 控制台显示乱码

**原因：**
Windows控制台默认使用GBK编码，而数据是UTF-8编码

**解决方案：**
这是显示问题，不影响实际功能。数据在程序内部是正确的UTF-8格式。

**验证方法：**
```python
from skills.trends_search.scripts.trends_service import get_service

service = get_service()
result = service.get_toutiao_trending(5)

if result["success"]:
    for item in result["data"]:
        # 数据本身是正确的UTF-8
        print(item["title"].encode('utf-8').decode('utf-8'))
```

### 3. 403 Forbidden 错误

**原因：**
- 平台反爬虫机制
- 缺少必要的请求头
- IP被限制

**解决方案：**
- 代码已实现自动重试（最多2次）
- 添加了随机延迟避免频繁请求
- 使用完整的浏览器请求头

**建议：**
- 优先使用稳定平台（今日头条、知乎、百度）
- 避免短时间内大量请求
- 如需频繁使用，考虑添加代理

### 4. 请求超时

**原因：**
- 网络连接问题
- 目标服务器响应慢

**解决方案：**
- 默认超时时间：15秒
- 可以调整：`service.timeout = 30`

### 5. 微博热搜失败率高

**原因：**
微博有最严格的反爬虫机制，需要完整的Cookie和会话状态

**建议：**
使用其他更稳定的平台：
- ✓ 今日头条（推荐）
- ✓ 知乎
- ✓ 百度
- ✓ 36氪

## 平台稳定性对比

| 平台 | 稳定性 | 说明 |
|------|--------|------|
| 今日头条 | ⭐⭐⭐⭐⭐ | 最稳定，推荐使用 |
| 知乎 | ⭐⭐⭐⭐ | 较稳定 |
| 百度 | ⭐⭐⭐⭐ | 较稳定 |
| 36氪 | ⭐⭐⭐⭐ | 稳定 |
| 少数派 | ⭐⭐⭐ | 一般 |
| IT之家 | ⭐⭐⭐ | 一般 |
| 微博 | ⭐⭐ | 不稳定，需要登录 |
| 抖音 | ⭐⭐ | 不稳定 |

## 调试技巧

### 1. 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from skills.trends_search.scripts.trends_service import get_service
service = get_service()
result = service.get_toutiao_trending(5)
```

### 2. 检查响应内容

```python
import requests

url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.toutiao.com/'
}

response = requests.get(url, headers=headers, timeout=15)
print(f"Status: {response.status_code}")
print(f"Encoding: {response.encoding}")
print(f"Content-Type: {response.headers.get('Content-Type')}")
print(f"Content length: {len(response.content)}")
print(f"First 200 chars: {response.text[:200]}")
```

### 3. 测试单个平台

```python
from skills.trends_search.scripts.trends_service import get_service

service = get_service()

# 测试今日头条
result = service.get_toutiao_trending(5)
print(f"Success: {result['success']}")
if result['success']:
    print(f"Got {result['count']} items")
else:
    print(f"Error: {result.get('error')}")
```

## 性能优化建议

### 1. 使用缓存

```python
from functools import lru_cache
import time

@lru_cache(maxsize=128)
def cached_get_trends(platform: str, timestamp: int):
    """缓存5分钟"""
    from skills.trends_search.scripts.trends_service import get_service
    service = get_service()
    method = getattr(service, f"get_{platform}_trending")
    return method(limit=10)

# 使用
current_time = int(time.time() / 300)  # 5分钟为单位
result = cached_get_trends("toutiao", current_time)
```

### 2. 并发请求

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

def get_platform_trends(platform: str):
    from skills.trends_search.scripts.trends_service import get_service
    service = get_service()
    method = getattr(service, f"get_{platform}_trending")
    return platform, method(limit=10)

async def get_multi_platform_trends():
    platforms = ["toutiao", "zhihu", "baidu"]
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, get_platform_trends, platform)
            for platform in platforms
        ]
        results = await asyncio.gather(*tasks)
    
    return dict(results)

# 使用
# results = asyncio.run(get_multi_platform_trends())
```

## 联系支持

如果问题仍未解决：

1. 检查网络连接
2. 确认依赖已安装：`pip install -r requirements.txt`
3. 查看详细日志
4. 尝试其他平台
5. 提交Issue到项目仓库

## 更新日志

### v1.0.0 (2026-03-13)
- 初始版本
- 支持10+平台
- 添加自动重试机制
- 修复编码问题
- 改进错误处理