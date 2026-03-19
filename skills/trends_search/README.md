# 热点搜索 Skill

基于 [TrendRadar](https://github.com/sansan0/TrendRadar) 项目实现的多平台热点趋势数据获取 Skill。

## 功能特性

- 支持 10+ 主流平台热点数据获取
- 统一的数据格式返回
- 自动错误处理和日志记录
- 单例模式服务实例

## 支持平台

| 平台 | 方法名 | 说明 |
|------|--------|------|
| 微博 | `get_weibo_trending` | 微博热搜榜 |
| 知乎 | `get_zhihu_trending` | 知乎热榜 |
| 百度 | `get_baidu_trending` | 百度热搜 |
| 抖音 | `get_douyin_trending` | 抖音热点 |
| 今日头条 | `get_toutiao_trending` | 今日头条热榜 |
| 36氪 | `get_36kr_trending` | 36氪快讯 |
| 少数派 | `get_sspai_trending` | 少数派热门 |
| IT之家 | `get_ithome_trending` | IT之家热榜 |
| 澎湃新闻 | `get_thepaper_trending` | 澎湃新闻热榜 |
| 今日热榜 | `get_tophub_trending` | 聚合多平台 |

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用示例

### 在 Agent 中使用

```python
# 获取微博热搜前10条
result = agent.use_skill("trends_search", "get_weibo_trending", limit=10)

if result["success"]:
    for item in result["data"]:
        print(f"{item['rank']}. {item['title']} - 热度: {item['hot']}")
```

### 直接使用服务

```python
from skills.trends_search.scripts.trends_service import get_service

service = get_service()

# 获取知乎热榜
result = service.get_zhihu_trending(limit=5)
print(result)
```

## 返回数据格式

所有方法返回统一格式：

```python
{
    "success": True,  # 是否成功
    "data": [         # 热点数据列表
        {
            "rank": 1,           # 排名
            "title": "标题",      # 标题
            "hot": "热度值",      # 热度（可能为空字符串）
            "url": "链接地址"     # 详情链接
        }
    ],
    "count": 10       # 返回条数
}
```

失败时返回：

```python
{
    "success": False,
    "error": "错误信息"
}
```

## 配置

在 `novel_agent/data/skills_config.json` 中启用此 Skill：

```json
{
    "enabled_skills": {
        "trends_search": true
    }
}
```

## 注意事项

1. 部分平台可能需要代理访问
2. 请求频率过高可能被限制
3. 网页结构变化可能导致解析失败
4. 建议添加请求间隔和重试机制

## 数据来源

本 Skill 基于以下开源项目：
- [TrendRadar](https://github.com/sansan0/TrendRadar) - 多平台热点聚合

## License

MIT License