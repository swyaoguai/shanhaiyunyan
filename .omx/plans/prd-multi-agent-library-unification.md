# PRD: Multi-Agent Library Unification

## Metadata
- Created: 2026-04-17
- Scope: 多 Agent 创作模式资料模型统一
- Source context:
  - `.omx/specs/deep-interview-multi-agent-library-unification.md`
  - `.omx/interviews/multi-agent-library-unification-20260417T013000Z.md`

---

## 1. Problem Statement

当前多 Agent 创作模式中，**会被后续引用的资料**分散在两套模型里：

1. **项目主数据**
   - `outline`
   - `characters`
   - `eventlines`
   - `detail_settings`
   - `chapter_settings`
   - `worldbuilding`
   - `items`

2. **资料库分类 UI**
   - `knowledgeCategories`
   - `outline_settings`
   - 各种自定义资料库分类

这种拆分导致几个明显问题：

- “真正的大纲”在 `outline.json`，但资料库里又有一个 `outline_settings`
- 用户会误以为资料库里的“大纲设定”就是真正大纲
- 多 Agent 后续引用时，并不是统一从资料库主体系读取
- 自定义资料库分类和项目数据分类不在一个统一模型内
- 前端模块入口与底层数据结构不一致，维护成本高

---

## 2. Product Goal

把**多 Agent 创作模式里所有会被后续引用的内容**统一纳入**资料库主体系**，形成**单一可引用知识源**。

但同时保留：

- **章节正文**：仍然以文件为主
- **现有模块入口**：继续保留写作 / 资料库 / 世界观等入口，不强制变成单页资料库

---

## 3. Final User Intent

### 3.1 必须统一进资料库主体系的内容
- 大纲
- 细纲
- 章纲
- 角色卡
- 事件线
- 世界观
- 道具物品
- 用户自定义的新资料库分类
- 其他多 Agent 后续会引用的结构化资料

### 3.2 章节正文
- 正文仍然主要保存为文件
- 但正文的**摘要 / 索引 / 元信息**必须进入资料库体系，供后续统一调用

### 3.3 前端
- 继续保留现有多模块入口
- 只是底层统一到资料库模型，不改成只剩资料库入口

### 3.4 模式范围
- **第一优先级**：多 Agent 创作模式
- **第二优先级**：无限续写、小说转剧本等也会引用资料的模式
- **第三优先级**：短篇创作、长期记忆桥接

当前阶段用户最关心的是：**多 Agent 创作模式相关、且会被后续引用的内容必须统一到资料库主体系**。  
其他模式不要求第一阶段全部重构完成，但后续应逐步接到同一套统一资料架构上。

---

## 4. Non-Goals

- 不把章节全文改成资料库主存储
- 不保留“真正大纲”和“资料库大纲设定”两套并存的长期结构
- 不强制把所有模块 UI 合并成一个资料库页
- 不在迁移第一阶段就删光全部旧接口；需要兼容期
- 不把 Aux Memory 继续保留为与主资料库并列的第二套核心资料系统

---

## 5. Brownfield Evidence

### 5.1 项目数据类型当前定义
`novel_agent/web/routes/projects.py:31-40`

- `outline`
- `worldbuilding`
- `characters`
- `items`
- `eventlines`
- `outline_settings`
- `detail_settings`
- `chapter_settings`

### 5.2 outline 当前是独立真实大纲
`novel_agent/project_manager.py:228-229`

- `outline` -> `outline.json`

### 5.3 前端项目数据直接分别加载
`novel_agent/web/static/app-project.js:234-261`

- `outline`
- `worldbuilding`
- `characters`
- `items`
- `eventlines`
- `outline_settings`
- `detail_settings`
- `chapter_settings`

### 5.4 资料库 UI 里有“大纲设定”
`novel_agent/web/static/app-core.js:31-38`

- `outline_settings` 被当成内置资料库分类

### 5.5 outline_settings 当前结构并不是常规大纲结构
`novel_agent/web/static/app-knowledge.js:339-347`

`summaryKeys` 只引用 3 个字段，但实际 `fields` 数组有 5 项：
- `name`（必填）
- `goal`
- `conflict`
- `hook`
- `notes`

这个结构是"大纲设定条目"的表单 schema，不是真正的分卷/分章大纲结构。

### 5.6 detail / chapter settings 已经是结构化资料
`novel_agent/web/static/app-knowledge.js:349-369`

### 5.7 项目资料构建器目前只有 detail / chapter，没有 outline_settings builder
`novel_agent/agents/project_data_builders.py:137-158`

### 5.8 memory_manager 通过旧 project_data 路径读取资料
`novel_agent/memory_manager.py:100-119`

- `_sync_worldbuilding()` → `load_project_data("worldbuilding")` → 直接读 `worldbuilding.json`
- `_sync_outline()` → `load_project_data("outline")` → 直接读 `outline.json`
- `_sync_characters()` → `load_project_data("characters")` → 直接读 `characters.json`

三条同步路径全部绕过资料库主体系，直接从旧 project-data 文件摘要后写入 Wensi Agent 记忆块。统一资料层建立后，这些读取路径都需要切换。

---

## 6. Target Architecture

### 6.1 核心原则

1. **单一资料源**：所有可引用创作资料统一进入资料库主模型
2. **文件与知识分离**：正文文件继续保留，但引用型信息进入资料库
3. **保留现有入口**：写作/资料库/世界观等模块继续存在
4. **渐进迁移**：通过兼容层完成过渡，避免一次性重构过大
5. **模式分层接入**：先完成多 Agent 主链，再把其他模式接入同一资料层
6. **Aux Memory 降级并入**：长期记忆能力保留，但不再作为平行主系统存在

---

### 6.2 新的统一资料模型

新增一个统一概念层，建议命名：

- `library_entries`
或
- `project_knowledge_entries`

每条记录建议至少具备：

```json
{
  "id": "uuid-or-stable-id",
  "entry_type": "outline|detail_outline|chapter_setting|character|eventline|world|item|chapter_summary|custom",
  "title": "标题",
  "summary": "摘要",
  "content_structured": {},
  "source_type": "generated|manual|imported|derived",
  "source_ref": {
    "project_data_type": "outline",
    "chapter_number": 3,
    "file_path": "chapters/003_xxx.md"
  },
  "tags": [],
  "builtin": true,
  "category_key": "outline",
  "updated_at": "ISO timestamp",
  "created_at": "ISO timestamp"
}
```

---

### 6.3 ID 生成与并发策略

#### ID 规则

| 场景 | ID 格式 | 示例 |
|------|---------|------|
| 迁移旧数据 | `{entry_type}_{index}` | `character_0`, `outline_0` |
| 新建条目 | `{entry_type}_{uuid4_short}` | `character_a3f8b2c1` |
| 章节摘要 | `chapter_summary_{chapter_number}` | `chapter_summary_3` |

- UUID short = UUID4 前 8 位，碰撞概率在单项目内可忽略
- 迁移时按旧文件中的数组顺序分配 index，保证幂等（多次迁移产生相同 ID）

#### 并发写入策略

复用现有 `atomic_write_json` + 进程内锁机制：

1. **进程内**：`library_service` 持有项目级 `threading.RLock`，所有读写操作在锁内执行
2. **跨进程**：复用 `_file_lock` 文件锁模式（与 `SessionStore` 一致），锁文件为 `library.json.lock`
3. **多 Agent 并发**：Agent 通过 `library_service` 的公共 API 写入，由 service 层串行化

### 6.4 统一后的内容映射

#### 一、唯一真大纲

旧：
- `outline`
- `outline_settings`

新：
- 只保留一份真正大纲：`entry_type = outline`
- `outline_settings` 从产品概念上移除

#### 二、细纲

旧：
- `detail_settings`

新：
- `entry_type = detail_outline`

#### 三、章纲

旧：
- `chapter_settings`

新：
- `entry_type = chapter_setting`

#### 四、角色卡

旧：
- `characters`

新：
- `entry_type = character`

#### 五、事件线

旧：
- `eventlines`

新：
- `entry_type = eventline`

#### 六、世界观 / 道具

旧：
- `worldbuilding`
- `items`

新：
- `entry_type = world`
- `entry_type = item`

#### 七、章节正文

旧：
- `chapters/*.md`

新：
- 正文仍保留文件
- 另外新增：
  - `entry_type = chapter_summary`
  - 用于保存章节摘要 / 关键事件 / 出场角色 / 钩子 / 关键词 / 索引

#### 八、用户自定义资料库分类

旧：
- 前端 `knowledgeCategories`
- 本地存储 / 项目 state 分散

新：
- 分类元信息进入统一项目级后端状态
- 分类条目也进入统一资料模型

#### 九、Aux Memory

旧：
- 独立前端中心
- 独立后端 API
- 独立 category / item / retrieve / injection 体系

新：
- 不再作为与主资料库并列的第二套核心架构
- 改造成统一记忆架构中的**自由记忆层 / 长期偏好层 / 软约束层**
- 主要承载：
  - 偏好（preference）
  - 事实（fact）
  - 约束（constraint）
  - 风格（style）
  - 碎片化情节灵感（plot / other）
- 这些内容仍然可用于注入和检索，但在概念上属于统一资料体系的子层，而不是独立王国

---

## 7. Storage Strategy

### 7.1 Canonical storage

建议把统一资料模型变成**canonical source of truth**。

旧文件：
- `outline.json`
- `characters.json`
- `eventlines.json`
- `detail_settings.json`
- `chapter_settings.json`
- `worldbuilding.json`
- `items.json`

在迁移期可以继续存在，但应逐步改造成：

- **兼容视图 / 派生缓存**
- 而不是长期独立真相

#### 7.1.1 统一资料层存储形态

统一资料层自身的持久化格式：

**方案：单文件 `library.json`**（推荐）

```
data/projects/<project_id>/library.json
```

理由：
1. 当前项目数据已全部使用单文件 JSON（`outline.json`、`characters.json` 等），保持一致
2. 项目级别数据量有限（通常 < 500 条 entries），单文件无性能瓶颈
3. 已有 `atomic_write_json` 保证写入原子性
4. 备份/恢复时只需处理一个文件

文件内部结构：

```json
{
  "version": 1,
  "entries": [
    { "id": "...", "entry_type": "...", ... }
  ],
  "categories_meta": [
    { "key": "custom_xxx", "name": "用户自定义分类", "icon": "...", "builtin": false }
  ]
}
```

#### 7.1.2 旧文件生命周期

| Phase | 旧文件角色 | 备注 |
|-------|-----------|------|
| Phase 1 | **Canonical source** | 统一层从旧文件初始化，旧文件仍是真相 |
| Phase 2 | **读路径切换** | 统一层成为读真相，旧文件通过 adapter 同步更新 |
| Phase 3 | **写路径切换** | 统一层成为写真相，旧文件变为派生缓存 |
| Phase 4-5 | **兼容缓存** | 旧 API 端点仍可返回旧格式，但数据来自统一层投影 |

> **注意**：旧文件在 Phase 5 完成前不删除，以保证回滚安全。

---

### 7.2 Chapter body

保留：
- `chapters/*.md`

新增配套知识条目：
- `chapter_summary`
- `chapter_entities`
- `chapter_index`

### 7.3 兼容期双写一致性保障

在 Phase 2-3 过渡期间，新旧两套存储共存。一致性规则：

1. **写入方向单一**：每个 Phase 只有一个 canonical writer
   - Phase 1-2：旧路径写入 → adapter 同步到统一层
   - Phase 3+：统一层写入 → adapter 投影到旧文件
2. **禁止双向写入**：同一数据类型在同一 Phase 内，只允许从一端写入
3. **旧 API 拦截**：Phase 3 之后，旧 `/api/project-data/{type}` PUT 端点改为代理到统一层写入，再投影回旧文件，而非直接写旧文件
4. **一致性校验**：adapter 投影后比对 entry count，不一致时 log warning

### 7.4 章节摘要生成策略

`chapter_summary` 条目的生成时机：

| 触发场景 | 行为 | 优先级 |
|----------|------|--------|
| 章节写完（Coordinator / ContinuousWriter） | 自动生成摘要条目，提取关键事件、出场角色、章末钩子 | Phase 3 必做 |
| 用户手动编辑正文 | 不自动更新；提供"刷新摘要"按钮 | Phase 4 |
| 历史章节批量回填 | 提供一次性命令 / API，对已有章节批量生成摘要 | Phase 3 可选 |

生成内容最小集：
- `summary`：≤300 字的章节摘要
- `key_events`：关键事件列表
- `appearing_characters`：出场角色
- `ending_hook`：章末悬念/钩子

### 7.5 读取性能策略

统一资料层按项目加载全量 `library.json`，在内存中按 `entry_type` 建立索引：

```python
self._by_type: Dict[str, List[LibraryEntry]] = defaultdict(list)
```

- **冷启动**：首次读取加载全文件，构建内存索引（预期 < 50ms / 500 条）
- **热路径**：按 type 过滤直接走内存索引，无需重复 I/O
- **缓存失效**：与 `SessionStore` 一致，使用文件指纹（mtime + size）判断外部修改
- **大项目上限**：如果单项目 entries > 2000 条，log warning 并建议用户归档旧数据

不引入分页查询；当前项目规模（通常 < 200 条活跃 entries）不需要。

---

## 8. Frontend Model Strategy

### 8.1 现有模块保留

继续保留：
- 写作模块
- 资料库模块
- 世界观入口
- 角色入口
- 长期记忆入口（可暂时保留）

但它们读取的底层数据统一改为：

- 统一资料模型
- 或统一资料模型的 adapter 输出

---

### 8.2 资料库分类重构

#### 需要移除或重定义
- `outline_settings`

#### 建议新的内置分类

```text
characters        -> 角色卡
worldbuilding     -> 世界观
items             -> 道具物品
eventlines        -> 事件线
outline           -> 大纲
detail_outline    -> 细纲
chapter_setting   -> 章纲
chapter_summary   -> 正文摘要/索引
```

注意：
- `outline` 应正式进入资料库分类体系
- `outline_settings` 应下线

---

## 9. Backend Migration Plan

### Phase 1 — 引入统一资料层（不破坏旧逻辑）

#### 新增
- 统一资料 service / repository
- type 映射规则
- 从现有 project data 生成统一 library entries 的 adapter

#### 涉及文件
- `novel_agent/project_manager.py`
- `novel_agent/web/routes/projects.py`
- `novel_agent/context/context_manager.py`
- `novel_agent/memory_manager.py`
- 可能新增：
  - `novel_agent/library_service.py`
  - `novel_agent/library_types.py`
  - `novel_agent/library_mappers.py`

#### 目标
- 先不删旧数据
- 能从统一资料层读取所有多 Agent 需要的引用资料

---

### Phase 2 — 读路径统一

让以下调用优先走统一资料层：

- 多 Agent 检索引用
- memory manager 摘要同步
- context manager 的 plot / character / world 读取
- copilot mention / knowledge lookup
- Aux Memory 注入前的统一检索入口

#### 涉及文件
- `novel_agent/memory_manager.py`
- `novel_agent/context/context_manager.py`
- `novel_agent/agents/router_agent.py`
- `novel_agent/workflow/coordinator.py`
- `novel_agent/agents/continuous_writer.py`（通过 `knowledge_base` 间接读取角色、死亡角色、剧情约束；KB 数据源切换后需验证兼容性）
- `novel_agent/web/static/app-copilot.js`
- `novel_agent/aux_memory.py`
- `novel_agent/web/routes/aux_memory.py`

---

### Phase 3 — 写路径统一

把这些写入统一到资料层：

- 大纲生成
- 细纲生成
- 章纲生成
- 角色卡生成
- 世界观 / 事件线 / 道具
- 正文生成后的摘要索引提取
- Aux Memory 的 category / item 最终也写入统一记忆模型或通过 adapter 映射进去

#### 涉及文件
- `novel_agent/agents/router_agent.py`
- `novel_agent/agents/project_data_builders.py`
- `novel_agent/workflow/coordinator.py`
- `novel_agent/agents/chapter_writer.py`
- 可能新增章节摘要构建器 / 派生器

---

### Phase 4 — UI 切换到底层统一模型

#### 涉及文件
- `novel_agent/web/static/app-core.js`
- `novel_agent/web/static/app-project.js`
- `novel_agent/web/static/app-knowledge.js`
- `novel_agent/web/static/app-nav.js`
- `novel_agent/web/static/app-copilot.js`
- `novel_agent/web/static/app-aux-memory.js`

#### 目标
- 保持原入口
- 但不再让 `outline_settings` 和 `outline` 概念并存

---

### Phase 5 — 兼容清理

#### 处理
- `outline_settings` 下线
- 旧 JSON 输出变为 compatibility view
- 前后端全部文案改为统一语义

---

## 10. File-by-File Change List

### A. 必改

#### `novel_agent/project_manager.py`
- 新增统一资料路径 / 统一资料读写
- 保留旧 `get_project_data_path()` 兼容
- 增加 chapter summary/index 的持久化支持

#### `novel_agent/web/routes/projects.py`
- 提供统一资料 API
- 旧 `/project-data/...` 改为兼容视图层
- 新增 outline -> library category 的规范化逻辑

#### `novel_agent/web/static/app-core.js`
- 重定义内置资料库分类
- 移除 `outline_settings` 的内置概念
- 加入 `outline` 正式资料库分类

#### `novel_agent/web/static/app-project.js`
- 项目数据加载逻辑改为统一资料模型驱动
- `outline_settings` 逐步移除

#### `novel_agent/web/static/app-knowledge.js`
- 修改 schema：
  - 去掉 `outline_settings`
  - 加入真正 `outline`
  - 统一 detail/chapter/summary 类型显示

#### `novel_agent/agents/router_agent.py`
- 大纲 / 细纲 / 章纲 / 角色卡 / 事件线 / 世界观生成后统一写入资料层
- 保持对旧文件的兼容输出

#### `novel_agent/agents/project_data_builders.py`
- 新增真正 outline library entry 生成器，或调整现有 builder 输出层
- 明确 detail/chapter 的 entry_type

#### `novel_agent/workflow/coordinator.py`
- 所有引用上下文改为从统一资料层组装
- 不再直接假设某些数据只存在旧 project-data 文件里

#### `novel_agent/aux_memory.py`
- 从独立长期记忆服务演进为统一记忆架构的自由记忆子层
- 保留 preference / fact / constraint / style / plot 等能力
- 但不再作为与主资料库并列的独立核心域

#### `novel_agent/web/routes/aux_memory.py`
- API 保留兼容层
- 后续读写接到统一记忆模型或其 adapter

#### `novel_agent/web/static/app-aux-memory.js`
- UI 可以保留
- 但文案与底层数据来源应转向统一记忆架构

---

### B. 应改

#### `novel_agent/memory_manager.py`
- outline / characters / world 等摘要同步应从统一资料层读取

#### `novel_agent/context/context_manager.py`
- context categories 需要适配新的 unified library read model

#### `novel_agent/web/static/app-nav.js`
- 统计与导航数字来源切到统一资料模型或其 adapter

#### `novel_agent/web/static/app-copilot.js`
- mention / 引用入口应支持 unified library categories
- 正文相关引用优先读取 chapter_summary，而不是正文全文

---

### C. 可能新增

建议新增文件：

- `novel_agent/library_types.py`
- `novel_agent/library_service.py`
- `novel_agent/library_mappers.py`
- `novel_agent/chapter_summary_service.py`

---

## 11. Migration Rules

### 11.1 Outline migration
- 读取 `outline.json`
- 转成 `entry_type = outline`
- 资料库显示使用该 entry
- 旧 `outline_settings` 停止作为“大纲”使用

### 11.2 Detail / chapter settings migration
- 旧文件直接转成新 type

### 11.3 Character migration
- `characters.json` -> `entry_type = character`

### 11.4 Custom category migration
- 分类元信息收敛到项目级后端 state
- 条目进入统一资料层

### 11.5 Chapter summary migration
- 老章节正文不迁入全文
- 生成摘要条目时可按需补建 index

---

## 12. Acceptance Criteria

1. 系统中只有一份真正的大纲概念，并且它属于资料库主体系
2. `outline_settings` 不再被用户理解为真正大纲
3. 多 Agent 所需可引用资料统一从资料库主体系读取
4. 章节正文仍以文件为主
5. 章节摘要/索引/元信息可以被资料库统一调用
6. 前端模块入口保持不变
7. 用户自定义资料库分类可以进入统一资料体系
8. 自动保存策略仍然满足：
   - 非内置分类不能自动存
   - 必须手动选
9. Aux Memory 不再作为平行主架构存在，而是被清晰定义为统一记忆架构中的自由记忆子层
10. 多 Agent 模式优先接入统一资料层；其他模式可分阶段迁移，但最终不再各自维护割裂的引用资料真相

---

## 13. Risks

### Risk 1: 兼容期双写不一致
**Mitigation**
- 先建 canonical library layer
- 旧 project-data 通过 adapter 输出

### Risk 2: 旧 UI 假设太多
**Mitigation**
- 先改数据 adapter，不先大改 UI

### Risk 3: 自定义分类来源分散
**Mitigation**
- 优先统一分类元信息到项目级 state

### Risk 4: 章节摘要策略不稳定
**Mitigation**
- 第一阶段先只做最小摘要索引，不做复杂 NLP

### Risk 5: 迁移失败无法回退
**Mitigation**
- Phase 1 启动迁移前，自动将旧文件快照到 `data/projects/<id>/.library_backup/`
- 统一层写入失败时不删除旧文件，保证旧路径仍可工作
- 提供 `library_service.rollback(project_id)` 方法：删除 `library.json`，恢复快照
- Phase 5 清理兼容层时，保留最后一份快照至少 30 天

---

## 14. Recommended Execution Order

### Iteration 1
- 建统一资料模型
- 先完成 outline unification

### Iteration 2
- 接 detail / chapter / character / eventline / world / items

### Iteration 3
- 接 chapter summary / index

### Iteration 4
- 清理 UI 命名与 adapter
- 下线 `outline_settings`

### Iteration 5
- 接无限续写 / 小说转剧本等次级模式的资料引用
- 将 Aux Memory 并入统一记忆模型的子层

### Iteration 6
- 评估短篇创作与长期记忆中心是否还需要独立 UI 强曝光
- 若使用率低，可降级入口；若使用率高，则保留入口但共享统一底层

---

## 15. How This Document Should Drive Changes

后续改动必须遵循这份文档：

1. **先实现统一资料层**
2. **再切读路径**
3. **再切写路径**
4. **最后做 UI 清理**

禁止直接跳到 UI 改名而不处理底层模型，否则会继续制造“双真相”。

---

## 16. Next Action

建议下一步基于本 PRD 继续产出：

- **实施设计文档（Technical Design）**
  - 明确 unified library schema
  - 明确 adapter 策略
  - 明确旧接口兼容方式

然后再按该设计文档驱动代码改动。
