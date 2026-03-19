# Communicator 集成改进建议

## 问题描述

当前 `communicator.py` 中的 `_format_trends` 方法输出格式较简单，且不支持流式输出。

## 改进方案

### 1. 优化格式化输出

在 `novel_agent/agents/communicator.py` 的 `_format_trends` 方法（第570行）中改进：

```python
def _format_trends(self, trends: List[Dict], platform: str) -> str:
    """格式化热点结果为文本 - 改进版"""
    platform_name = TRENDS_PLATFORMS.get(platform, platform)
    
    # 使用更好的排版
    lines = [
        f"\n{'='*50}",
        f"📊 **{platform_name}热榜** (实时更新)",
        f"{'='*50}\n"
    ]
    
    for i, item in enumerate(trends[:10], 1):
        title = item.get("title") or item.get("name") or item.get("content", "")
        
        # 清理XML标签
        if "<" in str(title):
            import re
            title = re.sub(r'<[^>]+>', '', str(title)).strip()
        
        # 获取热度
        hot = item.get("hot") or item.get("hotValue") or item.get("heat") or ""
        if hot and ("<" in str(hot) or ">" in str(hot)):
            hot = self._extract_from_xml(str(hot), "popularity") or ""
        
        if not title:
            continue
        
        # 格式化输出
        if i <= 3:
            # 前三名特殊显示
            emoji = ["🥇", "🥈", "🥉"][i-1]
            lines.append(f"{emoji} **{title}**")
            if hot:
                lines.append(f"   热度: {hot}")
        else:
            # 其他排名
            lines.append(f"\n{i}. {title}")
            if hot:
                lines.append(f"   热度: {hot}")
    
    lines.append(f"\n{'='*50}")
    lines.append(f"💡 提示: 这些热点可以作为创作灵感参考")
    
    return "\n".join(lines)
```

### 2. 添加流式输出支持

在 `_process_trends_search` 方法中添加流式输出：

```python
async def _process_trends_search(self, reply: str, user_message: str) -> tuple:
    """处理热点搜索 - 支持流式输出"""
    trends_data = None
    
    # ... 现有的检测逻辑 ...
    
    if platform and platform in TRENDS_PLATFORMS:
        try:
            logger.info(f"[Communicator] 搜索热点: {platform}")
            
            # 先发送加载提示（流式）
            await self.stream_message("🔍 正在获取热点数据...")
            
            trends = await self.search_trends(platform)
            
            if trends:
                trends_data = {
                    "platform": platform,
                    "platform_name": TRENDS_PLATFORMS.get(platform, platform),
                    "items": trends[:10]
                }
                
                # 流式输出热点结果
                trends_text = self._format_trends(trends[:10], platform)
                
                # 逐行流式输出
                for line in trends_text.split('\n'):
                    await self.stream_message(line)
                    await asyncio.sleep(0.05)  # 模拟打字效果
                
                # 更新回复
                if search_match:
                    reply = reply.replace(search_match.group(0), trends_text)
                else:
                    reply = f"{reply}\n\n{trends_text}"
                    
        except Exception as e:
            logger.error(f"[Communicator] 热点搜索失败: {e}", exc_info=True)
            error_msg = f"\n\n⚠️ 热点搜索失败: {str(e)}"
            await self.stream_message(error_msg)
            
            if search_match:
                reply = reply.replace(search_match.group(0), error_msg)
            else:
                reply = f"{reply}{error_msg}"
    
    return reply, trends_data
```

### 3. 添加流式消息方法

在 `CommunicatorAgent` 类中添加：

```python
async def stream_message(self, text: str) -> None:
    """
    流式输出消息
    
    Args:
        text: 要输出的文本
    """
    if hasattr(self, 'message_bus') and self.message_bus:
        await self.message_bus.publish({
            "type": "stream",
            "sender": self.name,
            "content": text,
            "timestamp": time.time()
        })
```

### 4. 更丰富的格式化选项

```python
def _format_trends_rich(self, trends: List[Dict], platform: str, style: str = "default") -> str:
    """
    格式化热点结果 - 支持多种样式
    
    Args:
        trends: 热点列表
        platform: 平台名称
        style: 格式样式 (default, compact, detailed)
    """
    platform_name = TRENDS_PLATFORMS.get(platform, platform)
    
    if style == "compact":
        # 紧凑模式
        lines = [f"📊 {platform_name}: "]
        for i, item in enumerate(trends[:5], 1):
            title = self._clean_title(item.get("title", ""))
            lines.append(f"{i}. {title}")
        return "\n".join(lines)
    
    elif style == "detailed":
        # 详细模式
        lines = [
            f"\n╔{'═'*48}╗",
            f"║ 📊 {platform_name}热榜 - 实时更新{' '*10}║",
            f"╚{'═'*48}╝\n"
        ]
        
        for i, item in enumerate(trends[:10], 1):
            title = self._clean_title(item.get("title", ""))
            hot = item.get("hot", "")
            url = item.get("url", "")
            
            if i <= 3:
                emoji = ["🥇", "🥈", "🥉"][i-1]
                lines.append(f"{emoji} {title}")
            else:
                lines.append(f"{i:2d}. {title}")
            
            if hot:
                lines.append(f"    🔥 热度: {hot}")
            if url:
                lines.append(f"    🔗 {url}")
            lines.append("")
        
        lines.append(f"{'─'*50}")
        lines.append("💡 这些热点可以作为创作灵感参考\n")
        return "\n".join(lines)
    
    else:
        # 默认模式（当前实现）
        return self._format_trends(trends, platform)

def _clean_title(self, title: str) -> str:
    """清理标题中的XML标签和特殊字符"""
    if not title:
        return ""
    
    import re
    # 移除XML标签
    title = re.sub(r'<[^>]+>', '', str(title))
    # 移除多余空白
    title = re.sub(r'\s+', ' ', title)
    return title.strip()
```

## 使用示例

### 基础使用
```python
# 在 communicator.py 中
trends_text = self._format_trends(trends[:10], platform)
```

### 使用不同样式
```python
# 紧凑模式 - 适合快速预览
trends_text = self._format_trends_rich(trends, platform, style="compact")

# 详细模式 - 适合深入了解
trends_text = self._format_trends_rich(trends, platform, style="detailed")
```

### 流式输出
```python
# 逐行流式输出
for line in trends_text.split('\n'):
    await self.stream_message(line)
    await asyncio.sleep(0.05)
```

## Web界面集成

在前端 JavaScript 中处理流式输出：

```javascript
// 监听流式消息
eventSource.addEventListener('stream', (event) => {
    const data = JSON.parse(event.data);
    
    // 逐行添加到聊天界面
    appendMessageLine(data.content);
});

function appendMessageLine(line) {
    const messageDiv = document.getElementById('current-message');
    messageDiv.innerHTML += line + '<br>';
    
    // 自动滚动
    messageDiv.scrollIntoView({ behavior: 'smooth' });
}
```

## 配置选项

可以在 `config.py` 中添加配置：

```python
# 热点显示配置
TRENDS_CONFIG = {
    "default_style": "default",  # default, compact, detailed
    "max_items": 10,
    "show_hot_value": True,
    "show_url": False,
    "enable_streaming": True,
    "stream_delay": 0.05  # 秒
}
```

## 注意事项

1. **流式输出**需要前端支持 Server-Sent Events (SSE)
2. **格式化样式**应该根据用户偏好或上下文自动选择
3. **性能考虑**：大量热点数据时避免过度格式化
4. **编码问题**：确保所有文本都是UTF-8编码

## 实施步骤

1. 在 `communicator.py` 中添加改进的格式化方法
2. 添加流式输出支持（如果需要）
3. 更新前端代码以支持新格式
4. 添加配置选项
5. 测试不同场景下的显示效果

## 相关文件

- `novel_agent/agents/communicator.py` - 主要修改文件
- `novel_agent/web/routes/chat.py` - 可能需要更新流式输出
- `novel_agent/web/static/app-chat.js` - 前端显示逻辑
- `novel_agent/config.py` - 添加配置选项