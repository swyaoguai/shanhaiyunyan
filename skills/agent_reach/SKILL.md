# Agent-Reach Skill

基于 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 项目实现的网络资料获取能力，专门为小说创作场景优化。

## 核心功能

**Agent-Reach 网络搜索**：
- ✅ **真实网络搜索** - 使用百度/Bing/DuckDuckGo等搜索引擎获取最新信息
- ✅ **智能内容提取** - 自动提取网页正文，去除广告和无关内容
- ✅ **多平台热点追踪** - 微博、知乎、抖音、B站等热点实时获取
- ✅ **视频内容提取** - B站、YouTube字幕自动提取
- ✅ **事件深度研究** - 综合多来源进行事件时间线分析

## 使用方式

### 在 Agent 中使用（推荐）

```python
# 1. 网络搜索（Agent-Reach核心功能）
result = agent.use_skill("agent_reach", "web_search", 
    query="唐朝长安城市布局", 
    max_results=10
)

# 2. 阅读网页内容
result = agent.use_skill("agent_reach", "read_webpage", 
    url="https://example.com/article"
)

# 3. 搜索热点
result = agent.use_skill("agent_reach", "search_trends", 
    platform="weibo", 
    limit=10
)

# 4. 事件研究
result = agent.use_skill("agent_reach", "research_event", 
    query="某事件的发展经过",
    depth="deep"
)

# 5. 综合搜索
result = agent.use_skill("agent_reach", "comprehensive_search", 
    query="2024年流行语"
)
```

### 直接使用服务

```python
from skills.agent_reach.scripts.web_research_service import get_service

service = get_service()

# 网络搜索
results = service.web_search("人工智能发展历史", max_results=10)
print(f"找到 {results['count']} 条结果")

# 阅读网页
content = service.read_webpage("https://example.com")
print(content['content'])

# 获取热搜
trends = service.search_trends("weibo", limit=10)
for item in trends["data"]:
    print(f"{item['rank']}. {item['title']}")
```

## 可用方法

### 1. `web_search` - 网络搜索 ⭐核心功能

**Agent-Reach 核心能力**：使用真实搜索引擎进行网络搜索

**参数**：
- `query` (str): 搜索关键词
- `max_results` (int): 最大结果数，默认10

**返回**：
```python
{
    "success": True,
    "query": "搜索词",
    "data": [
        {
            "title": "结果标题",
            "url": "链接地址",
            "snippet": "内容摘要",
            "source": "搜索引擎"
        }
    ],
    "count": 10,
    "engine": "baidu"
}
```

**用途**：获取最新网络信息，为小说创作提供真实素材

---

### 2. `read_webpage` - 阅读网页

**参数**：
- `url` (str): 网页URL

**返回**：
```python
{
    "success": True,
    "title": "文章标题",
    "content": "正文内容（Markdown格式）",
    "source": "来源URL"
}
```

**用途**：快速获取网页正文，自动去除广告和导航栏

---

### 3. `search_trends` - 搜索热点

**参数**：
- `platform` (str): 平台名称（weibo/zhihu/douyin/bilibili/toutiao）
- `limit` (int): 返回条数，默认10

**返回**：
```python
{
    "success": True,
    "platform": "weibo",
    "data": [
        {"rank": 1, "title": "热搜标题", "hot": "热度", "url": "链接"}
    ]
}
```

**用途**：快速了解当前热点话题

---

### 4. `research_event` - 事件研究

**参数**：
- `query` (str): 事件关键词
- `depth` (str): 研究深度（quick/deep），默认quick

**返回**：
```python
{
    "success": True,
    "query": "查询词",
    "timeline": [
        {"date": "时间", "event": "事件描述", "source": "来源"}
    ],
    "summary": "事件总结",
    "sources": ["参考来源列表"]
}
```

**用途**：深入理解事件来龙去脉，适合写现实题材

---

### 5. `extract_video_subtitle` - 提取视频字幕

**参数**：
- `url` (str): 视频URL（支持B站、YouTube）

**返回**：
```python
{
    "success": True,
    "title": "视频标题",
    "subtitle": "字幕内容",
    "duration": "视频时长",
    "source": "来源URL"
}
```

**用途**：从视频中提取文字素材

---

### 6. `search_memes` - 搜索网络热梗

**参数**：
- `keyword` (str): 热梗关键词（可选）
- `limit` (int): 返回条数，默认20

**返回**：
```python
{
    "success": True,
    "data": [
        {
            "term": "热梗词汇",
            "title": "相关标题",
            "snippet": "内容摘要",
            "url": "链接"
        }
    ]
}
```

**用途**：为角色对话添加时代感

---

### 7. `comprehensive_search` - 综合搜索

**参数**：
- `query` (str): 搜索关键词
- `sources` (list): 数据源列表（默认全部）

**返回**：
```python
{
    "success": True,
    "query": "搜索词",
    "results": {
        "web": [...],      # 网页搜索结果
        "social": [...],   # 社交媒体结果
        "news": [...],     # 新闻搜索结果
        "trending": [...]  # 热点趋势
    },
    "summary": "综合摘要"
}
```

**用途**：一次性从多个来源获取信息

---

## 配置

### 搜索引擎配置

在 `novel_agent/data/skills_config.json` 中配置：

```json
{
    "enabled_skills": {
        "agent_reach": true
    },
    "skill_configs": {
        "agent_reach": {
            "search_engine": "baidu",
            "api_key": "your_baidu_api_key",
            "secret_key": "your_baidu_secret_key",
            "cache_enabled": true,
            "timeout": 30
        }
    }
}
```

### 支持的搜索引擎

| 引擎 | 需要密钥 | 免费额度 | 推荐度 |
|------|---------|---------|--------|
| 百度搜索 | ✅ | 充足 | ⭐⭐⭐⭐⭐ |
| Bing搜索 | ✅ | 1000次/月 | ⭐⭐⭐⭐ |
| DuckDuckGo | ❌ | 无限 | ⭐⭐⭐ |

### 申请API密钥

- **百度搜索**: https://ai.baidu.com/
- **Bing搜索**: https://azure.microsoft.com/

## 小说创作应用场景

### 1. 历史考证
```python
# 搜索历史资料
results = agent.use_skill("agent_reach", "web_search",
    query="明朝服饰制度",
    max_results=5
)
```

### 2. 地理环境
```python
# 了解地理信息
results = agent.use_skill("agent_reach", "web_search",
    query="江南水乡建筑特点",
    max_results=5
)
```

### 3. 热点融入
```python
# 获取当前热点
trends = agent.use_skill("agent_reach", "search_trends",
    platform="weibo",
    limit=10
)
```

### 4. 事件参考
```python
# 研究真实事件
event = agent.use_skill("agent_reach", "research_event",
    query="某历史事件",
    depth="deep"
)
```

## 依赖

```bash
pip install requests beautifulsoup4 lxml
# 可选：视频字幕提取
pip install yt-dlp
```

## 注意事项

1. **网络环境**：部分平台可能需要代理
2. **请求频率**：避免过于频繁的请求
3. **内容版权**：获取的内容仅供创作参考
4. **API配额**：注意搜索引擎的免费额度限制

## 数据来源

本 Skill 基于以下开源项目：

- [Agent-Reach](https://github.com/Panniantong/Agent-Reach) - 多平台访问能力
- [Jina Reader](https://r.jina.ai/) - 网页智能阅读
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频字幕提取
- [TrendRadar](https://github.com/sansan0/TrendRadar) - 热点数据获取

## License

MIT License