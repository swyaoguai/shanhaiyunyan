# Skill调用补充说明

## 一、Router的Skill调用能力

Router不仅要决定调用哪个Agent，还要决定是否需要调用Skill工具。

### 可用的Skill类型

| Skill名称 | 用途 | 调用时机 |
|----------|------|---------|
| **web_search** | 网络搜索 | 需要查找外部资料、文献、背景知识 |
| **trends_search** | 热点搜索 | 需要获取热点、热梗、流行话题 |
| **knowledge_base** | 知识库检索 | 查询项目内的设定、章节、角色信息 |
| **file_operations** | 文件操作 | 读取、保存、重命名文件 |

### Skill调用判断逻辑

```python
# Router的Skill判断伪代码
def analyze_skill_need(user_input):
    """分析用户输入，判断需要哪些Skill"""
    
    # 搜索类关键词
    search_keywords = ["搜索", "查找", "查询", "找一下", "有没有", "什么是", "查一下"]
    
    # 热点类关键词
    trend_keywords = ["热点", "热梗", "最近", "流行", "热搜", "话题", "热门"]
    
    # 知识库类关键词
    kb_keywords = ["主角", "角色", "设定", "世界观", "前文", "之前", "现在"]
    
    # 文献资料类关键词
    doc_keywords = ["历史", "文献", "资料", "背景", "考证", "朝代", "制度"]
    
    skills_needed = []
    
    # 判断是否需要热点搜索
    if any(kw in user_input for kw in trend_keywords):
        skills_needed.append({
            "skill": "trends_search",
            "reason": "用户需要热点信息",
            "platforms": ["weibo", "zhihu", "bilibili"]  # 默认平台
        })
    
    # 判断是否需要网络搜索
    if any(kw in user_input for kw in search_keywords + doc_keywords):
        skills_needed.append({
            "skill": "web_search",
            "reason": "用户需要外部资料",
            "query": extract_search_query(user_input)
        })
    
    # 判断是否需要知识库检索
    if any(kw in user_input for kw in kb_keywords):
        skills_needed.append({
            "skill": "knowledge_base",
            "reason": "用户查询项目内信息",
            "scope": ["characters", "world", "chapters"]
        })
    
    return skills_needed
```

---

## 二、Skill调用场景示例

### 场景1：搜索网络资料后创作

```
用户："帮我搜索一下唐朝的科举制度，然后写一章关于科举考试的内容"

Router分析：
  🔍 意图1：搜索外部资料
  🔍 意图2：创作章节内容
  
Router决策：
  📞 第一步：调用Skill: web_search
     🔎 搜索查询："唐朝科举制度 考试流程 内容"
     ⏳ 搜索中...
     ✅ 获取到5条相关资料
  
  📞 第二步：调用Agent: CreativeWriter
     📥 输入数据：
        - 搜索结果（唐朝科举背景知识）
        - 用户要求（写科举考试章节）
        - 现有上下文（世界观、前文等）
     🎯 任务：基于真实历史资料创作章节
     
  ⏭️ 预期：创作出有历史依据的精彩章节
```

### 场景2：融入热点梗

```
用户："最近有什么热梗？帮我融入到下一章"

Router分析：
  🔍 意图1：获取热点信息
  🔍 意图2：融入创作
  
Router决策：
  📞 第一步：调用Skill: trends_search
     🔥 平台：微博、知乎、B站
     📊 获取：前10条热点
     ⏳ 检索中...
     ✅ 获取到热点列表
  
  📞 第二步：筛选适合的热点
     🎯 标准：与小说类型契合、易于改编
     ✅ 筛选出3条可用热点
  
  📞 第三步：调用Agent: CreativeWriter
     📥 输入数据：
        - 筛选后的热点（3条）
        - 章节大纲
        - 融入指导（不要生硬，要自然改编）
     🎯 任务：将热点巧妙融入剧情
     
  ⏭️ 预期：创作出既有热点又不违和的内容
```

### 场景3：查询知识库后回答

```
用户："主角现在是什么境界？有什么能力？"

Router分析：
  🔍 意图：查询已有设定
  
Router决策：
  📞 调用Skill: knowledge_base
     🔎 查询范围：
        - 角色设定文件
        - 最近3章内容
        - 世界观力量体系
     ⏳ 检索中...
     ✅ 找到相关信息
  
  💬 直接回复：
     基于知识库信息整理回答：
     "根据设定和最近章节，主角目前是[境界]，
      拥有[能力1]、[能力2]等能力..."
     
  ⏭️ 不需要调用Agent，直接回复即可
```

### 场景4：多Skill组合使用

```
用户："写一章现代都市修仙的内容，要融入最近的热点，还要有真实的城市背景"

Router分析：
  🔍 意图：创作章节
  ⚠️ 需要多种信息：都市修仙设定 + 热点 + 城市背景
  
Router决策：
  📞 第一步：并行调用多个Skill
     🔎 Skill 1: web_search
        查询："都市修仙小说设定 常见套路"
     🔥 Skill 2: trends_search
        平台：微博、知乎
     🔎 Skill 3: web_search
        查询："[城市名]地标建筑 特色街道"
     ⏳ 并行执行中...
     ✅ 全部完成
  
  📞 第二步：整合信息
     📊 整合结果：
        - 都市修仙常见设定（5条）
        - 可用热点（3条）
        - 城市背景资料（详细）
  
  📞 第三步：调用Agent: CreativeWriter
     📥 输入数据：整合后的所有信息
     🎯 任务：创作真实感强、有热点的都市修仙章节
     
  ⏭️ 预期：高质量的都市修仙内容
```

### 场景5：Skill辅助决策

```
用户："继续写下去"

Router分析：
  🔍 意图：续写内容
  ⚠️ 需要确认：续写什么？从哪里续写？
  
Router决策：
  📞 第一步：调用Skill: knowledge_base
     🔎 查询：最近编辑的章节
     ⏳ 检索中...
     ✅ 找到：第8章（最后编辑）
  
  📞 第二步：读取第8章内容
     📄 获取：第8章完整内容
     📊 分析：字数、结尾位置
  
  📞 第三步：调用Agent: ContinuousWriter
     📥 输入数据：
        - 第8章内容
        - 续写目标字数
        - 上下文信息
     🎯 任务：从第8章结尾续写
     
  ⏭️ 预期：自然衔接的续写内容
```

---

## 三、Router系统提示词更新

### 添加Skill调用部分

```markdown
## Skill工具调用能力

你可以调用以下Skill工具来增强回复质量：

### 1. web_search（网络搜索）
**何时使用**：
- 用户明确要求搜索
- 需要外部资料、文献、背景知识
- 需要考证历史、地理、文化等信息

**调用格式**：
```
📞 调用Skill: web_search
🔎 搜索查询：[具体查询内容]
⏳ 搜索中...
```

**使用示例**：
- "搜索唐朝科举制度" → web_search("唐朝科举制度 考试流程")
- "查一下修仙小说的境界划分" → web_search("修仙小说境界体系")

### 2. trends_search（热点搜索）
**何时使用**：
- 用户要求融入热点、热梗
- 需要了解最近流行话题
- 需要时事热点作为创作素材

**调用格式**：
```
📞 调用Skill: trends_search
🔥 平台：[微博/知乎/B站等]
📊 数量：[获取条数]
⏳ 检索中...
```

**使用示例**：
- "最近有什么热梗" → trends_search(platforms=["weibo", "zhihu"])
- "融入热点" → trends_search(limit=10)

### 3. knowledge_base（知识库检索）
**何时使用**：
- 用户查询项目内的信息
- 需要了解角色、世界观、前文等
- 辅助决策（如：确定从哪里续写）

**调用格式**：
```
📞 调用Skill: knowledge_base
🔎 查询范围：[角色/世界观/章节等]
⏳ 检索中...
```

**使用示例**：
- "主角现在什么境界" → knowledge_base(scope=["characters", "chapters"])
- "之前提到过什么" → knowledge_base(scope=["chapters"])

### Skill调用原则
1. **优先使用Skill**：如果用户需求可以通过Skill满足，优先调用Skill
2. **透明告知**：调用Skill时明确告知用户正在做什么
3. **结果整合**：将Skill结果自然整合到回复或传递给Agent
4. **多Skill组合**：复杂需求可以组合使用多个Skill
5. **失败处理**：如果Skill调用失败，说明原因并提供替代方案
```

---

## 四、Agent接收Skill结果

### CreativeWriter接收Skill结果示例

```markdown
## 接收外部信息

你可能会收到来自Skill工具的外部信息：

### 1. 网络搜索结果
```json
{
  "skill": "web_search",
  "query": "唐朝科举制度",
  "results": [
    {
      "title": "唐朝科举制度详解",
      "content": "唐朝科举分为...",
      "source": "百度百科"
    }
  ]
}
```

**使用方式**：
- 作为背景知识参考
- 确保历史细节准确
- 不要照抄，要融入创作

### 2. 热点信息
```json
{
  "skill": "trends_search",
  "platform": "weibo",
  "trends": [
    {
      "title": "某某热点话题",
      "hot": "1234567",
      "description": "..."
    }
  ]
}
```

**使用方式**：
- 选择1-2条最契合的热点
- 改编融入，不要生硬照搬
- 转化为角色动机、冲突或事件

### 3. 知识库信息
```json
{
  "skill": "knowledge_base",
  "scope": "characters",
  "results": {
    "protagonist": {
      "name": "张三",
      "level": "金丹期",
      "abilities": ["御剑术", "雷法"]
    }
  }
}
```

**使用方式**：
- 严格遵守已有设定
- 保持角色一致性
- 不要与前文矛盾
```

---

## 五、实施要点

### 1. Router必须具备的能力
- ✅ 识别用户是否需要外部信息
- ✅ 判断应该调用哪个Skill
- ✅ 正确传递Skill结果给Agent
- ✅ 处理Skill调用失败的情况

### 2. Agent必须具备的能力
- ✅ 接收并理解Skill结果
- ✅ 将外部信息自然融入创作
- ✅ 区分外部信息和项目设定的优先级

### 3. 透明化要求
- ✅ 调用Skill时明确告知用户
- ✅ 显示Skill执行进度
- ✅ 说明为什么需要这个Skill
- ✅ 展示Skill返回的关键信息

---

## 六、完整流程示例

### 用户："帮我写一章融入最近热点的修仙内容"

```
🔍 Router分析：
   意图1：获取热点
   意图2：创作修仙章节
   
📞 Router决策：
   第一步：调用Skill
   
🔥 正在调用：trends_search
   平台：微博、知乎、B站
   数量：获取前10条
   ⏳ 检索中...
   
✅ Skill执行完成
   📊 获取到10条热点
   🎯 筛选出3条适合修仙题材的热点：
      1. [热点标题1]
      2. [热点标题2]
      3. [热点标题3]
   
📞 Router决策：
   第二步：调用Agent
   
✍️ 正在调用：CreativeWriter
   📥 输入数据：
      - 筛选后的热点（3条）
      - 章节大纲
      - 世界观设定
      - 前文摘要
   🎯 任务：创作融入热点的修仙章节
   ⏳ 创作中...
   
✅ CreativeWriter执行完成
   📝 已创作：第X章（2156字）
   🔥 融入热点：[热点1]改编为[剧情元素]
   ✅ 质量检查：通过
   
💾 已保存：第X章-[标题]-2156字.md

⏭️ 下一步建议：
   1. 查看创作内容
   2. 继续写下一章
   3. 对本章进行润色
```

---

## 七、总结

### 核心改进
1. **Router不仅调用Agent，还调用Skill**
2. **Skill为Agent提供外部信息支持**
3. **多Skill可以组合使用**
4. **所有调用都要透明化**

### 优势
- ✅ 创作内容更丰富（有外部资料支持）
- ✅ 可以融入热点（提升时效性）
- ✅ 知识库检索（保持一致性）
- ✅ 用户体验更好（知道系统在做什么）

### 实施优先级
**P0**：更新Router系统提示词，添加Skill调用能力
**P1**：更新CreativeWriter等核心Agent，支持接收Skill结果
**P2**：优化Skill调用的透明化输出