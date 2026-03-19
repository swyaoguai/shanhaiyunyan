# 热点搜索 Skill

## 功能描述

热点搜索 Skill 提供多平台热点趋势数据获取能力，支持以下平台：

- 微博热搜
- 知乎热榜
- 百度热搜
- 抖音热点
- 今日头条热榜
- 36氪快讯
- 少数派热门
- IT之家热榜
- 澎湃新闻热榜
- 今日热榜（聚合）

## 使用方法

通过 `use_skill` 方法调用：

```python
# 获取微博热搜
result = agent.use_skill("trends_search", "get_weibo_trending", limit=10)

# 获取知乎热榜
result = agent.use_skill("trends_search", "get_zhihu_trending", limit=10)

# 获取今日头条热榜
result = agent.use_skill("trends_search", "get_toutiao_trending", limit=10)
```

## 可用方法

### 1. get_weibo_trending
获取微博热搜榜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

**返回：**
```python
{
    "success": True,
    "data": [
        {
            "title": "热搜标题",
            "url": "链接地址",
            "hot": "热度值",
            "rank": 1
        }
    ]
}
```

### 2. get_zhihu_trending
获取知乎热榜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 3. get_baidu_trending
获取百度热搜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 4. get_douyin_trending
获取抖音热点

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 5. get_toutiao_trending
获取今日头条热榜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 6. get_36kr_trending
获取36氪快讯

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 7. get_sspai_trending
获取少数派热门

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 8. get_ithome_trending
获取IT之家热榜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 9. get_thepaper_trending
获取澎湃新闻热榜

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

### 10. get_tophub_trending
获取今日热榜（聚合多平台）

**参数：**
- `limit` (int, 可选): 返回条数，默认 10

## 依赖

- requests
- beautifulsoup4
- lxml

## 数据来源

基于 [TrendRadar](https://github.com/sansan0/TrendRadar) 项目实现