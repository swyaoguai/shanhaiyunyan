# LLM Wiki 知识系统改造方案

## 一、LLM Wiki 核心原理总结

### 1.1 核心理念

**传统RAG**：每次查询时从原始文档中检索片段，拼接后让LLM回答。知识是"临时编译"的。

**LLM Wiki模式**：LLM读取源文档后，**增量构建并维护一个持久化的wiki知识库**。知识是"预编译"的，查询时直接从编译好的wiki中检索。

> "Knowledge is compiled once and kept current, not re-derived on every query."

### 1.2 三层架构

```
Schema（规则层）
  - purpose.md（wiki的灵魂：目标、研究范围）
  - schema.md（结构规则：页面类型、格式）

Wiki（编译层）
  - LLM生成的结构化页面
  - [[wikilink]]跨引用
  - YAML frontmatter元数据
  - index.md（目录）+ log.md（操作日志）

Raw Sources（原始层）
  - 用户上传的原始文档（不可变）
  - PDF/DOCX/MD/TXT等
```

### 1.3 三个核心操作

| 操作 | 说明 |
|------|------|
| **Ingest（摄取）** | 读取源文档 → LLM分析 → 生成wiki页面 |
| **Query（查询）** | 从wiki中检索相关页面 → LLM回答 |
| **Lint（检查）** | 检测wiki质量问题（孤立页面、死链接、过时内容） |

### 1.4 关键创新点

#### 1.4.1 两步链式摄取（Two-Step Chain-of-Thought Ingest）

```
Step 1（分析）: LLM读取源文档 → 结构化分析
  - 关键实体、概念、论点
  - 与现有wiki内容的连接
  - 与现有知识的矛盾和张力
  - wiki结构建议

Step 2（生成）: LLM根据分析 → 生成wiki文件
  - 来源摘要页（含frontmatter: type, title, sources[]）
  - 实体页、概念页（含交叉引用）
  - 更新index.md、log.md、overview.md
  - 待审核项（供人工判断）
  - 深度研究搜索词
```

#### 1.4.2 4信号知识图谱

| 信号 | 权重 | 说明 |
|------|------|------|
| 直接链接 | ×3.0 | 通过`[[wikilink]]`链接的页面 |
| 来源重叠 | ×4.0 | 共享同一原始来源的页面（frontmatter `sources[]`） |
| Adamic-Adar | ×1.5 | 共享邻居的页面（按邻居度数加权） |
| 类型亲和度 | ×1.0 | 同类型页面的额外加分 |

#### 1.4.3 Louvain社区检测

- 自动发现知识聚类（基于链接拓扑）
- 凝聚度评分（实际边数/可能边数）
- 低凝聚度聚类（<0.15）标记警告

#### 1.4.4 多阶段检索管道

```
Phase 1: 分词搜索
  - 英文: 分词 + 停用词移除
  - 中文: CJK双字分词
  - 标题匹配加分

Phase 1.5: 向量语义搜索（可选）
  - 嵌入 via OpenAI兼容端点
  - LanceDB存储，余弦相似度

Phase 2: 图谱扩展
  - 搜索结果作为种子节点
  - 4信号相关性模型找相关页面
  - 2跳遍历（带衰减）

Phase 3: 预算控制
  - 可配置上下文窗口: 4K → 1M tokens
  - 按比例分配: 60% wiki页面, 20% 聊天历史, 5% 目录, 15% 系统提示

Phase 4: 上下文组装
  - 编号页面（完整内容，非摘要）
  - LLM按编号引用: [1], [2], etc.
```

#### 1.4.5 其他关键特性

- **purpose.md**：定义wiki的目标、关键问题、研究范围、演化论点
- **[[wikilink]]语法**：页面间交叉引用
- **YAML frontmatter**：每个页面的元数据（type, title, sources[], tags）
- **SHA256增量缓存**：源文件内容哈希，未变化的文件自动跳过
- **持久化摄取队列**：串行处理，崩溃恢复，失败自动重试
- **overview.md自动更新**：每次摄取后重新生成全局摘要
- **来源溯源**：每个wiki页面包含`sources:[]`字段，链接回原始来源

---

## 二、当前项目实现分析

### 2.1 资料库（LibraryService）

**文件**：`novel_agent/library_service.py`

**核心功能**：
- 单一`library.json`文件存储所有条目
- 条目类型：角色(character)、世界观(world)、大纲(outline)、章节摘要(chapter_summary)、自定义(custom)
- CRUD操作 + 旧文件兼容迁移
- Obsidian链接元数据提取（`[[wikilink]]`正则匹配）
- 线程安全（RLock）

**数据结构**：
```
LibraryEntry:
  - id, entry_type, category_key
  - title, summary
  - content_structured: dict  # 结构化内容
  - relations: list  # 关系列表
  - links_out, links_in: list  # 出入链接
  - vector_text: str  # 向量化文本
  - created_at, updated_at
```

**局限性**：
- 没有知识图谱（只有简单的links_out/links_in）
- 没有智能摄取（直接存储，无LLM分析）
- 没有社区检测
- 没有多阶段检索
- 没有purpose.md（无目标导向）
- 没有Lint质量检查
- 没有来源溯源（sources[]字段）

### 2.2 知识中心（KnowledgeBase）

**文件**：`novel_agent/knowledge_base/knowledge_base.py`

**核心功能**：
- ChromaDB向量存储 + SQLite全文存储 + 元数据存储
- 混合搜索（向量 + 全文）
- 高级搜索（动态权重、重排序、上下文压缩）
- 章节管理（添加/更新/删除/导航）
- 剧情约束系统（角色死亡、能力变化等）
- 写作上下文获取

**局限性**：
- 没有wiki结构（扁平文档存储）
- 没有知识图谱可视化
- 没有两步链式摄取
- 没有[[wikilink]]跨引用
- 没有YAML frontmatter
- 没有purpose.md
- 没有Lint/Review系统
- 没有社区检测

---

## 三、差异对比

| 维度 | LLM Wiki | 资料库 LibraryService | 知识中心 KnowledgeBase |
|------|----------|----------------------|----------------------|
| **核心理念** | 增量构建持久化wiki | 结构化条目存储 | 向量+全文混合检索 |
| **数据结构** | Markdown wiki页面 | JSON条目 | 向量+全文+元数据 |
| **知识组织** | 三层架构 | 扁平条目列表 | 扁平文档列表 |
| **知识图谱** | 4信号模型+Louvain | 简单links | 无 |
| **摄取管道** | 两步链式分析+生成 | 直接存储 | 直接存储+分块 |
| **检索管道** | 多阶段（分词→向量→图谱→预算） | 按类型过滤 | 混合搜索 |
| **跨引用** | [[wikilink]]语法 | relations字段 | 无 |
| **质量维护** | Lint+Review | 无 | 无 |
| **增量更新** | SHA256缓存 | 无 | 无 |
| **目标导向** | purpose.md | 无 | 无 |

---

## 四、改造方案

### 4.1 总体思路

**不直接替换**，而是**吸收LLM Wiki的核心原理**，改造现有系统：

1. **资料库** → 升级为"小说Wiki"，采用wiki页面结构
2. **知识中心** → 保留向量/全文检索能力，增加图谱和摄取管道
3. **新增**：purpose.md、知识图谱、两步摄取、Lint系统

### 4.2 分阶段实施

#### Phase 1：Wiki页面结构（基础）

**目标**：将资料库条目升级为wiki页面格式

**改造内容**：
1. 每个条目存储为独立的Markdown文件（而非JSON中的一个字段）
2. 添加YAML frontmatter（type, title, sources[], tags, created_at）
3. 支持[[wikilink]]语法（已有基础，需增强）
4. 添加index.md（目录）和overview.md（全局摘要）
5. 添加purpose.md（项目目标和创作意图）

**文件结构**：
```
project_dir/
├── purpose.md              # 创作目标、风格偏好、核心主题
├── wiki/
│   ├── index.md            # 内容目录
│   ├── overview.md         # 全局摘要（自动更新）
│   ├── log.md              # 操作日志
│   ├── characters/         # 角色页面
│   │   ├── 主角.md
│   │   └── 反派.md
│   ├── world/              # 世界观页面
│   │   ├── 力量体系.md
│   │   └── 地理设定.md
│   ├── plot/               # 剧情页面
│   │   ├── 主线.md
│   │   └── 支线A.md
│   ├── chapters/           # 章节摘要页面
│   │   ├── 第1章.md
│   │   └── 第2章.md
│   └── constraints/        # 剧情约束页面
│       ├── 角色死亡.md
│       └── 能力限制.md
├── raw/
│   └── sources/            # 原始来源（不可变）
└── .llm-wiki/              # 应用配置
    ├── chats/              # 聊天历史
    └── reviews/            # 待审核项
```

**Wiki页面示例**：
```markdown
---
type: character
title: 主角
sources: [outline.json, chapter_1.md, chapter_3.md]
tags: [主角, 修仙, 热血]
created_at: 2026-04-28T10:00:00
updated_at: 2026-04-28T15:00:00
---

# 主角

## 基本信息
- 姓名：林枫
- 年龄：18岁
- 身份：[[天玄宗]]外门弟子

## 性格特点
冷静、坚韧、善于隐忍

## 能力
- 当前境界：[[筑基期]]
- 主修功法：[[天玄功]]
- 特殊能力：[[剑意]]

## 人物关系
- 师傅：[[李长老]]
- 对手：[[张少]]
- 恋人：[[苏瑶]]

## 剧情轨迹
- 第1章：[[被欺凌]] → 获得[[系统]]
- 第3章：[[突破筑基]] → 震惊众人
```

#### Phase 2：两步链式摄取（核心）

**目标**：实现LLM分析+生成的两步摄取管道

**改造内容**：
1. 摄取管道：源文档 → Step1(LLM分析) → Step2(LLM生成wiki页面)
2. SHA256增量缓存：跳过未变化的文件
3. 持久化摄取队列：串行处理，崩溃恢复
4. 来源溯源：每个wiki页面的`sources[]`字段

**摄取流程**：
```
async def ingest(source_file):
    # 1. SHA256检查
    file_hash = sha256(source_file)
    if file_hash == get_cached_hash(source_file):
        return  # 跳过未变化的文件

    # 2. Step1: LLM分析
    analysis = await llm.analyze(
        source_content=read(source_file),
        existing_wiki=index.md,
        purpose=purpose.md,
        schema=schema.md
    )

    # 3. Step2: LLM生成wiki页面
    wiki_pages = await llm.generate_wiki_pages(
        analysis=analysis,
        existing_wiki=index.md,
        purpose=purpose.md
    )

    # 4. 写入文件
    for page in wiki_pages:
        write_wiki_page(page)

    # 5. 更新缓存
    update_hash_cache(source_file, file_hash)

    # 6. 更新知识图谱
    rebuild_knowledge_graph()
```

#### Phase 3：知识图谱（增强）

**目标**：实现4信号相关性模型和知识图谱

**改造内容**：
1. 4信号相关性计算（直接链接、来源重叠、Adamic-Adar、类型亲和度）
2. 知识图谱数据结构（节点+边）
3. 图谱扩展检索（2跳遍历+衰减）
4. Louvain社区检测（可选）

**相关性计算**：
```
def calculate_relevance(page_a, page_b):
    score = 0.0

    # 信号1: 直接链接
    if page_b.title in page_a.links_out:
        score += 3.0

    # 信号2: 来源重叠
    shared_sources = set(page_a.sources) & set(page_b.sources)
    score += len(shared_sources) * 4.0

    # 信号3: Adamic-Adar
    common_neighbors = get_common_neighbors(page_a, page_b)
    for neighbor in common_neighbors:
        score += 1.5 / log(get_degree(neighbor))

    # 信号4: 类型亲和度
    if page_a.type == page_b.type:
        score += 1.0

    return score
```

#### Phase 4：多阶段检索管道（优化）

**目标**：实现分词→向量→图谱→预算的多阶段检索

**改造内容**：
1. 分词搜索（已有，需增强中文分词）
2. 向量语义搜索（已有）
3. 图谱扩展检索（新增）
4. 预算控制（新增）
5. 上下文组装（优化）

#### Phase 5：Lint和Review系统（质量）

**目标**：实现wiki质量检查和异步审核

**Lint检查项**：
1. 孤立页面（degree ≤ 1）
2. 死链接（`[[wikilink]]`指向不存在的页面）
3. 过时内容（长时间未更新的页面）
4. 矛盾检测（同一实体在不同页面的描述冲突）
5. 缺失页面（被链接但不存在的页面）

**Review系统**：
- LLM在摄取时标记需要人工判断的项
- 预定义操作：创建页面、深度研究、跳过
- 用户在方便时处理审核项

---

## 五、实施优先级

| 阶段 | 内容 | 优先级 | 预估工作量 |
|------|------|--------|-----------|
| Phase 1 | Wiki页面结构 | 最高 | 3-5天 |
| Phase 2 | 两步链式摄取 | 最高 | 5-7天 |
| Phase 3 | 知识图谱 | 高 | 3-5天 |
| Phase 4 | 多阶段检索 | 中 | 2-3天 |
| Phase 5 | Lint和Review | 低 | 2-3天 |

**建议**：先实施 Phase 1 + Phase 2，这是LLM Wiki的核心价值所在。Phase 3-5可以后续迭代。

---

## 六、与现有系统的兼容性

### 6.1 资料库（LibraryService）

- **保留**：LibraryService作为底层存储引擎
- **升级**：每个LibraryEntry对应一个wiki页面文件
- **兼容**：旧的JSON格式通过迁移脚本转换为wiki页面

### 6.2 知识中心（KnowledgeBase）

- **保留**：向量存储和全文检索能力
- **增强**：wiki页面自动索引到知识中心
- **整合**：检索管道从知识中心获取结果，再通过图谱扩展

### 6.3 Agent系统

- **ChapterWriter**：从wiki获取写作上下文（替代现有的知识库检索）
- **ContinuousWriter**：摄取新章节到wiki（替代现有的add_chapter）
- **Evaluator**：使用Lint检查wiki质量
- **Communicator**：从wiki检索回答用户问题

---

## 七、技术依赖

### 必需
- 现有依赖（ChromaDB、SQLite）— 已有
- Markdown解析器（frontmatter提取）— 需新增（python-frontmatter）
- 知识图谱数据结构 — 需新增（networkx）

### 可选
- LanceDB（替代ChromaDB，性能更好）— 可选
- graphology（知识图谱可视化）— 前端需要
- Louvain社区检测算法 — 可选

---

## 八、风险和注意事项

1. **LLM调用成本**：两步摄取需要2次LLM调用/文件，比直接存储贵
2. **摄取速度**：大文件摄取可能需要较长时间
3. **wiki页面维护**：需要定期Lint检查，防止wiki腐化
4. **迁移成本**：现有数据需要迁移到wiki格式
5. **前端改造**：需要新的wiki浏览和编辑界面

---

## 九、总结

LLM Wiki的核心价值在于：**将知识从"临时检索"升级为"预编译wiki"**。

对于小说创作场景，这意味着：
- 角色、世界观、剧情不再是散落的JSON字段，而是相互链接的wiki页面
- 每次写作前，Agent从编译好的wiki中获取上下文，而非每次重新检索
- 知识图谱帮助发现角色关系、剧情矛盾、知识缺口
- 两步摄取确保知识质量（先分析再生成）

这是对现有资料库和知识中心的根本性升级，而非简单替换。