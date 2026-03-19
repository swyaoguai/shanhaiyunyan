# 网络资料研究 Skill

专为小说创作设计的网络资料搜索工具，整合了 Agent-Reach 的多平台访问能力。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 可选增强

```bash
# 视频字幕提取（推荐）
pip install yt-dlp

# 或者安装所有可选依赖
pip install yt-dlp beautifulsoup4 lxml
```

### 3. 启用 Skill

在 `novel_agent/data/skills_config.json` 中：

```json
{
    "enabled_skills": {
        "web_research": true
    }
}
```

## 使用场景

### 场景1：搜索创作资料

```python
from skills.web_research.scripts.web_research_service import get_service

service = get_service()

# 阅读网页内容
result = service.read_webpage("https://example.com/article")
print(result["content"])

# 提取视频字幕（用于素材收集）
result = service.extract_video_subtitle("https://www.bilibili.com/video/BV1xxx")
print(result["subtitle"])
```

### 场景2：追踪热点事件

```python
# 获取微博热搜
trends = service.search_trends("weibo", limit=10)
for item in trends["data"]:
    print(f"#{item['rank']} {item['title']} - {item['hot']}")

# 研究事件经过
result = service.research_event("某社会事件")
for item in result["timeline"]:
    print(f"{item['date']}: {item['event']}")
```

### 场景3：获取网络热梗

```python
# 搜索热梗
memes = service.search_memes(limit=20)
for meme in memes["data"]:
    print(f"{meme['term']}: {meme['meaning']}")

# 按关键词搜索
memes = service.search_memes(keyword="yyds")
```

### 场景4：综合研究

```python
# 综合搜索
result = service.comprehensive_search(
    query="2024流行语",
    sources=["weibo", "zhihu", "toutiao"]
)
print(result["summary"])

# 获取所有平台热点
all_trends = service.get_all_trends()
for platform, trends in all_trends["data"].items():
    print(f"\n=== {platform} ===")
    for item in trends[:5]:
        print(f"  {item['title']}")
```

## 功能详解

### 网页阅读 (`read_webpage`)

使用 Jina Reader 服务，将任意网页转换为干净的 Markdown 格式。

**特点**：
- 自动去除广告、导航栏
- 保留文章结构和链接
- 支持中文网页
- 无需 API Key

**示例**：
```python
result = service.read_webpage("https://mp.weixin.qq.com/s/xxx")
# 返回微信文章正文
```

### 视频字幕 (`extract_video_subtitle`)

使用 yt-dlp 提取视频字幕，支持：
- B站 (bilibili)
- YouTube
- 其他 1800+ 视频平台

**注意**：需要先安装 `yt-dlp`

```bash
pip install yt-dlp
```

### 热点搜索 (`search_trends`)

复用现有的 `trends_search` 服务，支持：
- 微博热搜
- 知乎热榜
- 抖音热点
- 今日头条
- 百度热搜
- 等更多...

### 事件研究 (`research_event`)

综合多个来源，梳理事件的来龙去脉。

**输出**：
- 时间线
- 相关热点
- 信息来源

### 热梗搜索 (`search_memes`)

从热点中提取可能的网络热梗。

**输出**：
- 热梗词汇
- 来源说明
- 热度指标

## 高级配置

### 配置文件位置

`novel_agent/data/skills_config.json`

### 完整配置示例

```json
{
    "enabled_skills": {
        "web_research": true
    },
    "skill_configs": {
        "web_research": {
            "cache_enabled": true,
            "cache_ttl": 3600,
            "timeout": 30,
            "max_retries": 3,
            "platforms": {
                "twitter": {
                    "enabled": true,
                    "cookies": "your_cookies_here"
                },
                "proxy": {
                    "enabled": true,
                    "http": "http://user:pass@ip:port"
                }
            }
        }
    }
}
```

### 解锁更多平台

| 平台 | 方法 | 说明 |
|------|------|------|
| Twitter/X | 配置 Cookie | 使用 Cookie-Editor 导出 |
| 小红书 | Docker + MCP | 参考 Agent-Reach 文档 |
| Reddit | 代理 | 需要住宅代理 |

## 与 trends_search 的关系

`web_research` 复用 `trends_search` 的热点获取能力，并增加了：

| 能力 | trends_search | web_research |
|------|--------------|--------------|
| 热点榜单 | ✅ | ✅（复用） |
| 网页阅读 | ❌ | ✅ |
| 视频字幕 | ❌ | ✅ |
| 事件研究 | ❌ | ✅ |
| 热梗搜索 | ❌ | ✅ |
| 综合搜索 | ❌ | ✅ |

建议：**两个 skill 同时启用**，`web_research` 会自动复用 `trends_search` 的服务。

## 常见问题

### Q: 网页阅读返回空内容？

A: 可能是网络问题或目标网站限制。尝试：
1. 检查网络连接
2. 使用代理
3. 等待几分钟后重试

### Q: 视频字幕提取失败？

A: 确保：
1. 已安装 `yt-dlp`
2. 视频确实有字幕
3. 不是会员专享内容

### Q: 热点数据获取失败？

A: 确保 `trends_search` skill 已启用且依赖已安装。

### Q: 如何获取更详细的事件信息？

A: 使用 `depth="deep"` 参数：
```python
result = service.research_event("某事件", depth="deep")
```

## 更新日志

### v1.0.0 (2024-03)
- 初始版本
- 整合 Agent-Reach 核心能力
- 复用 trends_search 服务
- 支持网页阅读、视频字幕、热点搜索、事件研究

## 相关链接

- [Agent-Reach](https://github.com/Panniantong/Agent-Reach) - 多平台访问能力
- [Jina Reader](https://r.jina.ai/) - 网页智能阅读
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频下载和字幕提取
- [TrendRadar](https://github.com/sansan0/TrendRadar) - 热点数据来源

## License

MIT License
