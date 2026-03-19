# Skill系统扩展设计

## 一、设计原则：可扩展的Skill架构

### 核心理念
系统应该支持**动态添加新Skill**，而不需要大规模修改Router的核心逻辑。

### 设计目标
1. ✅ **易于扩展**：添加新Skill只需要注册，不需要修改Router
2. ✅ **统一接口**：所有Skill遵循相同的调用规范
3. ✅ **自动发现**：Router能自动识别可用的Skill
4. ✅ **智能匹配**：Router能根据用户意图自动选择合适的Skill

---

## 二、Skill注册系统

### Skill元数据定义

每个Skill都应该包含以下元数据：

```python
# Skill元数据结构
class SkillMetadata:
    """Skill元数据"""
    name: str              # Skill名称（唯一标识）
    display_name: str      # 显示名称（中文）
    description: str       # 功能描述
    category: str          # 分类（search/data/tool/creative等）
    keywords: List[str]    # 触发关键词
    parameters: Dict       # 参数定义
    examples: List[str]    # 使用示例
    priority: int          # 优先级（多个Skill匹配时使用）
```

### 示例：现有Skill的元数据

```python
# 1. 网络搜索Skill
web_search_skill = {
    "name": "web_search",
    "display_name": "网络搜索",
    "description": "搜索互联网上的信息、资料、文献",
    "category": "search",
    "keywords": ["搜索", "查找", "查询", "找一下", "有没有", "什么是"],
    "parameters": {
        "query": {"type": "string", "required": True, "description": "搜索查询"},
        "limit": {"type": "int", "default": 5, "description": "结果数量"}
    },
    "examples": [
        "搜索唐朝科举制度",
        "查一下修仙小说的境界划分",
        "什么是赛博朋克"
    ],
    "priority": 10
}

# 2. 热点搜索Skill
trends_search_skill = {
    "name": "trends_search",
    "display_name": "热点搜索",
    "description": "获取各平台的热点、热搜、流行话题",
    "category": "search",
    "keywords": ["热点", "热梗", "最近", "流行", "热搜", "话题", "热门"],
    "parameters": {
        "platforms": {"type": "list", "default": ["weibo", "zhihu"], "description": "平台列表"},
        "limit": {"type": "int", "default": 10, "description": "获取数量"}
    },
    "examples": [
        "最近有什么热梗",
        "微博热搜前10",
        "B站最近流行什么"
    ],
    "priority": 10
}

# 3. 知识库检索Skill
knowledge_base_skill = {
    "name": "knowledge_base",
    "display_name": "知识库检索",
    "description": "检索项目内的设定、章节、角色等信息",
    "category": "data",
    "keywords": ["主角", "角色", "设定", "世界观", "前文", "之前", "现在"],
    "parameters": {
        "scope": {"type": "list", "default": ["all"], "description": "检索范围"},
        "query": {"type": "string", "required": True, "description": "检索内容"}
    },
    "examples": [
        "主角现在什么境界",
        "之前提到过什么",
        "世界观中的力量体系"
    ],
    "priority": 15  # 优先级更高，因为是项目内信息
}
```

---

## 三、未来可能的Skill扩展

### 分类1：搜索类Skill

#### 1. 学术搜索Skill
```python
academic_search_skill = {
    "name": "academic_search",
    "display_name": "学术搜索",
    "description": "搜索学术论文、研究资料",
    "category": "search",
    "keywords": ["论文", "研究", "学术", "文献", "期刊"],
    "parameters": {
        "query": {"type": "string", "required": True},
        "source": {"type": "string", "default": "google_scholar"}
    },
    "examples": ["搜索关于AI的最新论文"],
    "priority": 8
}
```

#### 2. 图片搜索Skill
```python
image_search_skill = {
    "name": "image_search",
    "display_name": "图片搜索",
    "description": "搜索相关图片作为参考",
    "category": "search",
    "keywords": ["图片", "照片", "插图", "参考图"],
    "parameters": {
        "query": {"type": "string", "required": True},
        "count": {"type": "int", "default": 5}
    },
    "examples": ["搜索古代建筑图片"],
    "priority": 7
}
```

#### 3. 视频搜索Skill
```python
video_search_skill = {
    "name": "video_search",
    "display_name": "视频搜索",
    "description": "搜索相关视频资料",
    "category": "search",
    "keywords": ["视频", "影片", "纪录片"],
    "parameters": {
        "query": {"type": "string", "required": True},
        "platform": {"type": "string", "default": "bilibili"}
    },
    "examples": ["搜索唐朝历史纪录片"],
    "priority": 7
}
```

### 分类2：数据处理类Skill

#### 4. 数据分析Skill
```python
data_analysis_skill = {
    "name": "data_analysis",
    "display_name": "数据分析",
    "description": "分析项目数据，生成统计报告",
    "category": "data",
    "keywords": ["统计", "分析", "数据", "报告"],
    "parameters": {
        "data_type": {"type": "string", "required": True},
        "metrics": {"type": "list", "default": ["all"]}
    },
    "examples": ["分析各章节字数分布"],
    "priority": 8
}
```

#### 5. 文本对比Skill
```python
text_compare_skill = {
    "name": "text_compare",
    "display_name": "文本对比",
    "description": "对比两段文本的差异",
    "category": "data",
    "keywords": ["对比", "比较", "差异", "不同"],
    "parameters": {
        "text1": {"type": "string", "required": True},
        "text2": {"type": "string", "required": True}
    },
    "examples": ["对比修改前后的差异"],
    "priority": 8
}
```

### 分类3：创意辅助类Skill

#### 6. 名字生成Skill
```python
name_generator_skill = {
    "name": "name_generator",
    "display_name": "名字生成器",
    "description": "生成角色名、地名、技能名等",
    "category": "creative",
    "keywords": ["起名", "命名", "名字", "取名"],
    "parameters": {
        "type": {"type": "string", "required": True},  # character/place/skill
        "style": {"type": "string", "default": "chinese"}
    },
    "examples": ["生成一个古风角色名"],
    "priority": 9
}
```

#### 7. 情节生成Skill
```python
plot_generator_skill = {
    "name": "plot_generator",
    "display_name": "情节生成器",
    "description": "生成情节点子、冲突设计",
    "category": "creative",
    "keywords": ["情节", "点子", "灵感", "冲突"],
    "parameters": {
        "genre": {"type": "string", "required": True},
        "count": {"type": "int", "default": 5}
    },
    "examples": ["生成5个玄幻小说的情节点子"],
    "priority": 9
}
```

### 分类4：工具类Skill

#### 8. 翻译Skill
```python
translation_skill = {
    "name": "translation",
    "display_name": "翻译工具",
    "description": "翻译文本到指定语言",
    "category": "tool",
    "keywords": ["翻译", "translate"],
    "parameters": {
        "text": {"type": "string", "required": True},
        "target_lang": {"type": "string", "default": "zh"}
    },
    "examples": ["翻译这段英文"],
    "priority": 8
}
```

#### 9. 格式转换Skill
```python
format_convert_skill = {
    "name": "format_convert",
    "display_name": "格式转换",
    "description": "转换文本格式（Markdown/HTML/纯文本等）",
    "category": "tool",
    "keywords": ["转换", "格式", "导出"],
    "parameters": {
        "content": {"type": "string", "required": True},
        "from_format": {"type": "string", "required": True},
        "to_format": {"type": "string", "required": True}
    },
    "examples": ["将Markdown转为HTML"],
    "priority": 7
}
```

#### 10. 字数统计Skill
```python
word_count_skill = {
    "name": "word_count",
    "display_name": "字数统计",
    "description": "统计文本字数、段落数等",
    "category": "tool",
    "keywords": ["字数", "统计", "计数"],
    "parameters": {
        "content": {"type": "string", "required": True},
        "detailed": {"type": "bool", "default": False}
    },
    "examples": ["统计这章的字数"],
    "priority": 10
}
```

### 分类5：AI增强类Skill

#### 11. 情感分析Skill
```python
sentiment_analysis_skill = {
    "name": "sentiment_analysis",
    "display_name": "情感分析",
    "description": "分析文本的情感倾向",
    "category": "ai",
    "keywords": ["情感", "情绪", "氛围"],
    "parameters": {
        "text": {"type": "string", "required": True}
    },
    "examples": ["分析这段文字的情感"],
    "priority": 7
}
```

#### 12. 关键词提取Skill
```python
keyword_extract_skill = {
    "name": "keyword_extract",
    "display_name": "关键词提取",
    "description": "提取文本的关键词",
    "category": "ai",
    "keywords": ["关键词", "提取", "标签"],
    "parameters": {
        "text": {"type": "string", "required": True},
        "count": {"type": "int", "default": 10}
    },
    "examples": ["提取这章的关键词"],
    "priority": 7
}
```

---

## 四、Router的Skill发现机制

### 自动发现流程

```python
class SkillRegistry:
    """Skill注册中心"""
    
    def __init__(self):
        self.skills = {}  # 存储所有注册的Skill
        self.keyword_index = {}  # 关键词索引
        self.category_index = {}  # 分类索引
    
    def register_skill(self, skill_metadata):
        """注册新Skill"""
        name = skill_metadata["name"]
        self.skills[name] = skill_metadata
        
        # 建立关键词索引
        for keyword in skill_metadata["keywords"]:
            if keyword not in self.keyword_index:
                self.keyword_index[keyword] = []
            self.keyword_index[keyword].append(name)
        
        # 建立分类索引
        category = skill_metadata["category"]
        if category not in self.category_index:
            self.category_index[category] = []
        self.category_index[category].append(name)
    
    def find_skills_by_keywords(self, user_input):
        """根据用户输入查找匹配的Skill"""
        matched_skills = []
        
        for keyword, skill_names in self.keyword_index.items():
            if keyword in user_input:
                for skill_name in skill_names:
                    skill = self.skills[skill_name]
                    matched_skills.append({
                        "skill": skill,
                        "matched_keyword": keyword,
                        "priority": skill["priority"]
                    })
        
        # 按优先级排序
        matched_skills.sort(key=lambda x: x["priority"], reverse=True)
        return matched_skills
    
    def get_all_skills(self):
        """获取所有可用Skill"""
        return list(self.skills.values())
    
    def get_skills_by_category(self, category):
        """按分类获取Skill"""
        skill_names = self.category_index.get(category, [])
        return [self.skills[name] for name in skill_names]
```

### Router使用Skill注册中心

```python
class Router:
    """智能路由器"""
    
    def __init__(self):
        self.skill_registry = SkillRegistry()
        self._register_default_skills()
    
    def _register_default_skills(self):
        """注册默认Skill"""
        # 注册现有Skill
        self.skill_registry.register_skill(web_search_skill)
        self.skill_registry.register_skill(trends_search_skill)
        self.skill_registry.register_skill(knowledge_base_skill)
        # ... 其他Skill
    
    def analyze_user_input(self, user_input):
        """分析用户输入，决定调用哪些Skill"""
        # 1. 查找匹配的Skill
        matched_skills = self.skill_registry.find_skills_by_keywords(user_input)
        
        # 2. 如果有多个匹配，选择优先级最高的
        if matched_skills:
            selected_skills = self._select_best_skills(matched_skills, user_input)
            return selected_skills
        
        return []
    
    def _select_best_skills(self, matched_skills, user_input):
        """从匹配的Skill中选择最合适的"""
        # 可以根据更复杂的逻辑选择
        # 例如：考虑上下文、用户历史、Skill组合等
        return [matched_skills[0]["skill"]]  # 简化版：返回优先级最高的
```

---

## 五、添加新Skill的步骤

### 步骤1：定义Skill元数据

```python
# 新Skill：天气查询
weather_skill = {
    "name": "weather_query",
    "display_name": "天气查询",
    "description": "查询指定地点的天气信息",
    "category": "search",
    "keywords": ["天气", "气温", "下雨", "晴天"],
    "parameters": {
        "location": {"type": "string", "required": True, "description": "地点"},
        "date": {"type": "string", "default": "today", "description": "日期"}
    },
    "examples": [
        "查询北京的天气",
        "明天上海会下雨吗"
    ],
    "priority": 8
}
```

### 步骤2：实现Skill功能

```python
class WeatherSkill:
    """天气查询Skill实现"""
    
    async def execute(self, location: str, date: str = "today"):
        """执行天气查询"""
        # 调用天气API
        weather_data = await self._call_weather_api(location, date)
        
        return {
            "success": True,
            "data": weather_data,
            "message": f"{location}的天气：{weather_data['description']}"
        }
    
    async def _call_weather_api(self, location, date):
        """调用天气API（示例）"""
        # 实际实现
        pass
```

### 步骤3：注册Skill

```python
# 在系统启动时注册
router.skill_registry.register_skill(weather_skill)
```

### 步骤4：Router自动识别

```python
# 用户输入："北京今天天气怎么样？"
# Router自动识别：
# 1. 匹配关键词"天气"
# 2. 找到weather_query Skill
# 3. 提取参数：location="北京", date="today"
# 4. 调用Skill
# 5. 返回结果
```

---

## 六、Router系统提示词更新（支持动态Skill）

```markdown
## Skill调用能力（动态扩展）

你可以调用系统中注册的任何Skill工具。当前可用的Skill会动态更新。

### Skill发现机制
1. 分析用户输入中的关键词
2. 查找匹配的Skill
3. 根据优先级选择最合适的Skill
4. 如果有多个Skill匹配，可以组合使用

### 当前可用Skill列表
系统会自动提供当前所有可用Skill的列表，包括：
- Skill名称
- 功能描述
- 触发关键词
- 使用示例

### Skill调用原则
1. **关键词匹配**：根据用户输入的关键词自动匹配Skill
2. **优先级排序**：多个匹配时选择优先级高的
3. **组合使用**：复杂需求可以组合多个Skill
4. **透明告知**：调用任何Skill都要明确告知用户
5. **失败处理**：Skill调用失败时提供替代方案

### 新Skill适配
当系统添加新Skill时，你会自动获得该Skill的信息，无需更新提示词。
只需要：
1. 识别用户输入是否匹配新Skill的关键词
2. 按照统一的调用格式使用新Skill
3. 将Skill结果整合到回复中
```

---

## 七、优势总结

### 1. 可扩展性
- ✅ 添加新Skill只需注册，不需要修改Router核心代码
- ✅ Skill元数据包含所有必要信息
- ✅ Router自动发现和使用新Skill

### 2. 灵活性
- ✅ 支持任意数量的Skill
- ✅ 支持Skill组合使用
- ✅ 支持动态优先级调整

### 3. 可维护性
- ✅ 统一的Skill接口
- ✅ 清晰的元数据定义
- ✅ 集中的注册管理

### 4. 智能性
- ✅ 关键词自动匹配
- ✅ 优先级智能排序
- ✅ 上下文感知选择

---

## 八、实施建议

### 阶段1：建立Skill注册系统
1. 实现SkillRegistry类
2. 定义Skill元数据标准
3. 实现关键词索引

### 阶段2：迁移现有Skill
1. 将现有Skill转换为元数据格式
2. 注册到SkillRegistry
3. 测试自动发现功能

### 阶段3：更新Router
1. 集成SkillRegistry
2. 实现自动Skill匹配
3. 更新系统提示词

### 阶段4：扩展新Skill
1. 按需添加新Skill
2. 测试自动识别
3. 优化匹配算法

---

## 九、未来展望

### 可能的高级功能

1. **Skill学习**：根据用户使用频率自动调整优先级
2. **Skill推荐**：主动推荐用户可能需要的Skill
3. **Skill组合模板**：预定义常用的Skill组合
4. **Skill市场**：支持第三方Skill插件
5. **Skill版本管理**：支持Skill的版本更新和回滚

---

**总结**：通过Skill注册系统，我们实现了一个高度可扩展的架构。未来添加任何新Skill都只需要定义元数据并注册，Router会自动识别和使用，无需修改核心代码。