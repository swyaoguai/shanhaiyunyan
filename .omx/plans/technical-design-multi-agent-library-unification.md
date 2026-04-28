# Technical Design: Multi-Agent Library Unification

## Metadata
- Created: 2026-04-17
- Based on:
  - `.omx/plans/prd-multi-agent-library-unification.md`
  - `.omx/specs/deep-interview-multi-agent-library-unification.md`
- Goal: 把多 Agent 创作模式中所有可引用资料统一进单一资料库主体系，并为其他模式逐步接入提供技术路径

---

## 1. Design Goals

### Primary
1. 建立**统一资料主模型**，作为多 Agent 模式唯一可引用知识源
2. 移除“真正大纲 vs 大纲设定”的双真相
3. 保留章节正文文件优先模型，同时提供资料库可引用摘要/索引
4. 保持现有 UI 模块入口，避免一次性重做产品结构

### Secondary
1. 为无限续写、小说转剧本等模式提供接入统一资料层的接口
2. 将 Aux Memory 降级并入统一记忆架构的“自由记忆子层”
3. 保持旧 `/api/project-data/*` 与旧 JSON 文件在迁移期可兼容

---

## 2. Non-Goals

1. 不在第一阶段删除所有旧 project-data 文件
2. 不把章节全文迁移进资料库主存储
3. 不在第一阶段重做所有 UI 模块交互
4. 不在第一阶段合并短篇/无限续写/多 Agent 的全部内部状态模型

---

## 3. Current Brownfield Split

## 3.1 Backend split
- `outline` 使用 `outline.json`，是当前真正大纲
- `characters` 使用 `characters.json`
- `eventlines` / `detail_settings` / `chapter_settings` 各自独立 JSON
- `outline_settings` 也是独立 JSON，但没有真正 builder 主链

## 3.2 Frontend split
- `store.projectData` 保存 project-data 结果
- `store.knowledgeCategories` 驱动资料库 UI 分类
- `app-knowledge.js` 用一套 schema 渲染分类编辑器
- `outline_settings` 被当成资料库分类，但不是写作链唯一大纲源

## 3.3 Memory split
- `memory_manager.py` 直接从旧 project-data 文件读摘要
- `context_manager.py` 按 world / character / plot / chapter 分类组织上下文
- `aux_memory.py` 维护另一套长期记忆分类/条目/注入系统

## 3.4 Knowledge base 子系统定位
- `novel_agent/knowledge_base/` 是**搜索索引层**，不是 source-of-truth
- 底层使用 ChromaDB (向量) + SQLite (全文) 做混合检索
- 数据来源：章节正文 → chunk → embed → 存入向量库
- **与 Library 关系**：Library 是 canonical source，KB 是消费者。Library 变更后可触发 KB 重新索引，但 KB 不反向写 Library
- 第一阶段不改动 KB 子系统

## 3.5 Context manager 独立持久化
- `context_manager.py` 持久化在 `context.json`，存储的是**运行时上下文摘要**（world/character/plot/chapter 四类）
- 不是原始资料，而是 Agent 运行时组装的压缩上下文
- **与 Library 关系**：context_manager 从 Library 读取原始资料生成摘要，但自身持久化独立
- 第一阶段暂不改动，Phase 4+ 再评估是否桥接

---

## 4. Target High-Level Architecture

```text
                        ┌──────────────────────────┐
                        │   Unified Library Layer  │
                        │  (canonical knowledge)   │
                        └────────────┬─────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │  Write Adapters  │       │   Read Adapters  │      │  Memory Adapters │
 │ project-data API │       │ UI / agent reads │      │ aux/context sync │
 └─────────────────┘       └─────────────────┘       └─────────────────┘
          │                          │                          │
          ▼                          ▼                          ▼
   outline.json, ...         app-knowledge/app-project      memory_manager,
   compatibility views       app-copilot/app-nav            coordinator, aux
```

### Canonical truth
- **Unified Library Layer**

### Compatibility surfaces
- `/api/project-data/*`
- old JSON files
- current UI module read patterns
- Aux Memory retrieve/injection APIs

---

## 5. Canonical Data Model

## 5.1 File layout

New canonical storage:

```text
data/projects/<project_id>/library.json
```

Recommended top-level structure:

```json
{
  "version": 1,
  "entries": [],
  "categories_meta": []
}
```

> **设计决策**：`indexes`（`by_type`、`by_id`）为纯内存结构，不持久化到 JSON。加载时从 `entries` 数组重建，避免数据冗余和一致性问题。

### Why single file
1. Current project-data already uses per-project JSON files
2. Expected scale is small enough
3. Atomic write utilities already exist
4. Backup/rollback simpler

---

## 5.2 Entry schema

```json
{
  "id": "outline_main",
  "entry_type": "outline",
  "title": "主线大纲",
  "summary": "故事主线概述",
  "content_structured": {},
  "source_type": "generated",
  "source_ref": {
    "legacy_data_type": "outline",
    "chapter_number": null,
    "file_path": null
  },
  "category_key": "outline",
  "builtin": true,
  "tags": [],
  "created_at": "2026-04-17T00:00:00",
  "updated_at": "2026-04-17T00:00:00"
}
```

### Required fields
- `id`
- `entry_type`
- `title`
- `summary`
- `content_structured`
- `source_type`
- `source_ref`
- `category_key`
- `builtin`
- `created_at`
- `updated_at`

### `category_key` vs `entry_type` 关系
- `entry_type` 是数据类型标识（enum），决定 `content_structured` 的 schema
- `category_key` 是 UI 分组标识，默认等于 `entry_type`，但 `custom` 类型可指定任意 `category_key`
- 例：`entry_type=custom, category_key="magic_system"` 表示用户自定义的魔法体系分类
- 内置类型的 `category_key` 必须与 `entry_type` 一致

### Optional fields
- `tags`
- `relations`
- `status`
- `score`
- `metadata`

---

## 5.3 Entry types

### Built-in canonical types
- `outline`
- `detail_outline`
- `chapter_setting`
- `character`
- `eventline`
- `world`
- `item`
- `chapter_summary`
- `custom`
- `free_memory`  ← for merged Aux Memory sublayer

### Explicitly removed concept
- `outline_settings`

It is replaced by:
- `outline` as the true library outline type

---

## 5.4 Type-specific `content_structured`

### 旧→新转换规则

| Legacy 格式 | Entry content_structured |
|---|---|
| `outline.json` (list of chapters) | `{"chapters": [...]}` 包裹进单个 outline entry |
| `outline.json` (dict with chapters key) | 直接作为 content_structured |
| `characters.json` (list) | 每个角色一个 character entry，content_structured = 原始 dict |
| `worldbuilding.json` (dict) | 单个 world entry，content_structured = 原始 dict |
| `items.json` (list) | 每个道具一个 item entry |
| `eventlines.json` (list) | 每条事件线一个 eventline entry |
| `detail_settings.json` (list) | 每条细纲一个 detail_outline entry |
| `chapter_settings.json` (list) | 每条章纲一个 chapter_setting entry |
| `outline_settings.json` (list) | 映射为 `entry_type=custom, category_key=outline_settings_legacy` |

### `outline`
```json
{
  "outline_kind": "novel",
  "chapters": [
    {
      "chapter_number": 1,
      "title": "旧城归来",
      "summary": "主角返回故地并发现线索",
      "arc": "序章/第一阶段",
      "key_turn": "发现仇人痕迹",
      "hook": "更大的阴谋浮现"
    }
  ]
}
```

### `detail_outline`
```json
{
  "chapter_number": 1,
  "scene_goal": "建立本章行动目标",
  "conflict": "目标与现实条件不匹配",
  "notes": "埋伏笔"
}
```

### `chapter_setting`
```json
{
  "chapter_number": 1,
  "chapter_goal": "建立行动目标",
  "key_event": "得知仇人线索",
  "ending_hook": "发现更大阴谋"
}
```

### `character`
```json
{
  "name": "林渡",
  "role": "主角",
  "identity": "宗门遗孤",
  "description": "少年剑修",
  "personality": ["克制", "执拗"],
  "goals": ["复仇", "重建秩序"],
  "relationships": {"苏晚": "旧识"}
}
```

### `chapter_summary`
```json
{
  "chapter_number": 3,
  "summary_text": "本章核心摘要",
  "key_events": ["潜入旧塔", "遭遇伏击"],
  "appearing_characters": ["林渡", "苏晚"],
  "ending_hook": "发现叛徒身份",
  "source_file": "chapters/003_旧塔.md"
}
```

### `free_memory`
```json
{
  "memory_type": "constraint|style|fact|preference|plot|other",
  "details": "不要过早暴露主角底牌",
  "score": 0.8,
  "enabled": true
}
```

---

## 6. Category Model

## 6.1 Built-in categories

Canonical category keys:

```text
outline
detail_outline
chapter_setting
character
eventline
world
item
chapter_summary
custom
free_memory
```

## 6.2 Frontend presentation mapping

| Current UI label | New category key | Notes |
|---|---|---|
| 角色档案 | `character` | keep label |
| 世界设定 | `world` | keep label |
| 道具物品 | `item` | keep label |
| 事件线 | `eventline` | keep label |
| 大纲 | `outline` | new official builtin |
| 细纲设定 | `detail_outline` | rename internally |
| 章纲设定 | `chapter_setting` | rename internally |
| 正文摘要 | `chapter_summary` | new builtin |
| 自由记忆 | `free_memory` | Aux Memory merged view |

## 6.3 Custom categories
- `categories_meta` becomes canonical project-level category metadata source
- existing frontend custom knowledge categories migrate here

---

## 7. Service Layer Design

## 7.1 New modules

### `novel_agent/library_types.py`
- dataclasses / schemas
- entry type enum
- category meta schema

### `novel_agent/library_service.py`
- load/save canonical `library.json`
- query by type / category / source
- upsert entries
- migration bootstrap
- projection to legacy payloads

### `novel_agent/library_mappers.py`
- old payload -> new entries
- new entries -> old payload

### `novel_agent/chapter_summary_service.py`
- generate chapter summary entries from chapter content

---

## 7.2 Library service API

Suggested methods:

```python
load_library(project_id) -> LibraryPayload
save_library(project_id, payload) -> None

list_entries(project_id, entry_type=None, category_key=None) -> List[LibraryEntry]
get_entry(project_id, entry_id) -> Optional[LibraryEntry]
upsert_entry(project_id, entry: LibraryEntry) -> LibraryEntry
upsert_entries(project_id, entries: List[LibraryEntry]) -> List[LibraryEntry]
delete_entry(project_id, entry_id) -> bool

list_categories(project_id) -> List[CategoryMeta]
upsert_category(project_id, category: CategoryMeta) -> CategoryMeta

project_legacy_data(project_id, data_type) -> Any
bootstrap_from_legacy(project_id) -> LibraryPayload
rollback(project_id) -> bool
```

---

## 7.3 REST API 端点

### Library CRUD 端点 (Phase 2-3)

```
GET  /api/v1/library/entries?entry_type=&category_key=  → 查询 entries
POST /api/v1/library/entries                             → 创建/更新 entry
GET  /api/v1/library/entries/{id}                        → 获取单个 entry
PUT  /api/v1/library/entries/{id}                        → 更新单个 entry
DELETE /api/v1/library/entries/{id}                      → 删除 entry
GET  /api/v1/library/categories                          → 列出所有分类
POST /api/v1/library/categories                          → 创建/更新分类
```

### 兼容层端点 (保留)

```
GET  /api/v1/project-data/{data_type}   → 从 library 投影到旧格式
POST /api/v1/project-data/{data_type}   → 写入旧文件 + 同步到 library
```

---

## 7.4 迁移触发机制

- **自动触发**：`LibraryService.load()` 检测 `library.json` 不存在时，自动执行 `_bootstrap_from_legacy()`
- **幂等性**：已存在 `library.json` 的项目跳过 bootstrap
- **备份**：bootstrap 前将所有旧 JSON 文件复制到 `.library_backup/` 目录
- **降级容错**：bootstrap 失败不阻止项目加载，设 `_degraded=True` 回退旧路径

---

## 7.5 library.json 版本升级策略

- `version` 字段标识 schema 版本，当前为 `1`
- `_maybe_migrate(payload)` 在 `load()` 后检查版本号
- 版本 < CURRENT 时执行顺序迁移（v1→v2→v3...）
- 每次迁移后 `save()` 并更新 `version`
- 未知高版本拒绝加载并 warning

---

## 7.6 错误降级策略

- `LibraryService` 持有 `is_degraded` 标志
- 触发条件：`save()` atomic write 失败、`load()` JSON 解析失败
- 降级行为：
  - 所有读路径回退到旧 `project_manager.load_project_data()`
  - 写路径仅写旧文件，跳过 library 同步
  - 日志输出 warning 级别告警
- 恢复：下次成功 `load()` 自动清除 degraded 状态

---

## 7.7 Concurrency / safety

### In-process
- project-level lock inside `library_service`

### Cross-process
- `library.json.lock`

### Writes
- all canonical writes go through `atomic_write_json`

### Backup
- before first migration:
  - `data/projects/<id>/.library_backup/*`

---

## 8. Compatibility Adapter Design

## 8.1 Old project-data API remains temporarily

`/api/project-data/{data_type}` stays alive, but after migration:
- reads from library projections
- writes proxy into library canonical layer

### Mapping table

| Legacy data_type | Canonical source |
|---|---|
| `outline` | entries where `entry_type = outline` |
| `characters` | `character` |
| `eventlines` | `eventline` |
| `detail_settings` | `detail_outline` |
| `chapter_settings` | `chapter_setting` |
| `worldbuilding` | `world` |
| `items` | `item` |
| `outline_settings` | deprecated / mapped to outline compatibility view during migration only |

## 8.2 Legacy file projections

Old files remain during migration:
- `outline.json`
- `characters.json`
- `eventlines.json`
- `detail_settings.json`
- `chapter_settings.json`
- `worldbuilding.json`
- `items.json`

But after Phase 3:
- they are written from canonical library projections
- not treated as primary truth

---

## 9. Backend File-by-File Design

## 9.1 `novel_agent/project_manager.py`

### Add
- `get_library_path()`
- helper for backup directory

### Change
- keep current `get_project_data_path()` for compatibility
- do not remove old paths yet

---

## 9.2 `novel_agent/web/routes/projects.py`

### Add
- new `/api/library/*` endpoints or equivalent
- migration bootstrap endpoint if needed internally

### Change
- `/project-data/*` becomes compatibility view
- `_normalize_builtin_project_data()` updated to understand canonical projections

---

## 9.3 `novel_agent/agents/router_agent.py`

### Change
- write all generated assets into canonical library entries
- maintain legacy file projection after write

Specific places:
- outline generation path
- character generation path
- eventline/detail/chapter setting generation path
- worldbuilding path

---

## 9.4 `novel_agent/agents/project_data_builders.py`

### Change
- output types should align with canonical type names
- add outline library builder or map coordinator outline output directly to canonical `outline`

---

## 9.5 `novel_agent/workflow/coordinator.py`

### Change
- context assembly should query canonical library layer
- not assume outline/characters/eventlines only exist as old files
- after chapter write, emit `chapter_summary` entry
- `_persist_project_ready_chapter_result` 中 outline 更新走 library → 投影

---

## 9.6 `novel_agent/memory_manager.py`

### Change
- `_sync_outline()` reads canonical `outline`
- `_sync_characters()` reads canonical `character`
- `_sync_worldbuilding()` reads canonical `world`
- 新增 `_load_from_library_or_legacy()` helper：优先从 library service 读取，失败回退旧路径

---

## 9.7 Knowledge base 关系定义

### 定位
- KB 是搜索索引层，Library 是 canonical source
- KB 不反向写 Library

### 当前交互
- 章节正文写入后 → chunk → embed → 存入 ChromaDB
- Router 可查询 KB 获取语义相关段落

### 未来交互（Phase 4+）
- Library entry 变更 → 触发 KB 重新索引相关 chunks
- Library 元数据可作为 KB 查询的 filter 条件

### 不变
- KB 的 data layer / logic layer / application layer 结构不动
- embedding 配置和 ChromaDB 存储不动

---

## 9.8 Context manager 桥接设计

### 当前状态
- `context_manager.py` 从 `context.json` 读写运行时上下文摘要
- 按 world / character / plot / chapter 四类组织

### Phase 1-3 不变
- context_manager 保持独立持久化
- 不直接从 Library 读取

### Phase 4+ 桥接方案
- context_manager 初始化时从 Library 读取原始资料构建初始摘要
- 运行时摘要仍存 `context.json`
- Library 变更后可触发 context 重建

---

## 9.9 `novel_agent/context/context_manager.py`

### Change
- context categories stay similar
- source switches to library service queries

---

## 9.10 `novel_agent/aux_memory.py`

### Change
- long-term target: adapter into `free_memory`
- keep retrieval / scoring / injection behavior
- stop treating aux-memory storage as separate top-level domain

### Transitional rule
- current API remains
- writes mirrored into canonical library as `free_memory`

---

## 9.11 `novel_agent/web/routes/aux_memory.py`

### Change
- remain compatible
- route create/update/delete through library-backed sublayer

---

## 10. Frontend File-by-File Design

## 10.1 `novel_agent/web/static/app-core.js`

### Change
- redefine builtin categories:
  - remove `outline_settings`
  - add `outline`
  - add `chapter_summary`
  - optionally add `free_memory`

### Keep
- module shell and navigation pattern

---

## 10.2 `novel_agent/web/static/app-project.js`

### Change
- project data load becomes:
  - canonical library read
  - or compatibility adapters sourced from canonical data

### Remove over time
- direct conceptual dependence on `outline_settings`

---

## 10.3 `novel_agent/web/static/app-knowledge.js`

### Change
- schema updates:
  - delete `outline_settings`
  - add true `outline`
  - add `chapter_summary`
  - map canonical internal names to user-facing labels

### Important
- library editor for `outline` must support normal outline structure, not current card schema

---

## 10.4 `novel_agent/web/static/app-copilot.js`

### Change
- mentions and references query canonical entries
- chapter references prefer `chapter_summary`

---

## 10.5 `novel_agent/web/static/app-nav.js`

### Change
- counters derive from canonical entries/projections

---

## 10.6 `novel_agent/web/static/app-aux-memory.js`

### Change
- UI can stay
- wording and data source move toward `free_memory`

---

## 11. Migration Plan

## Phase 1 — Bootstrap canonical layer

Deliverables:
- `library.json`
- service / types / mappers
- bootstrap from legacy files

No UI change required.

## Phase 2 — Read-path switch

Deliverables:
- memory_manager / coordinator / router / copilot read canonical layer

Still compatible with old APIs.

## Phase 3 — Write-path switch

Deliverables:
- canonical write on all generated assets
- legacy projection output
- chapter summaries emitted

### detail_settings 字段不一致处理
- 旧 `detail_settings.json` 中字段名不统一：有 `scene_goal` / `conflict` / `notes` 等
- 迁移时 `content_structured` 保留原始字段，不做 schema 强制对齐
- `entries_to_detail_settings()` 投影时原样返回 `content_structured`
- 未来 Phase 4 可标准化字段名，但 Phase 3 以兼容为优先

## Phase 4 — UI semantic cleanup

Deliverables:
- remove `outline_settings`
- add builtin `outline`
- library panel reflects true model

## Phase 5 — Non-multi-agent consumers

Deliverables:
- infinite write adapters
- novel-to-script adapters
- aux-memory merged sublayer

---

## 12. Testing Strategy

## 12.1 Unit tests
- library service CRUD
- mapper old→new / new→old
- migration bootstrap idempotence
- chapter summary generation

## 12.2 Integration tests
- project-data API still returns valid compatibility payloads
- generated outline writes canonical entry + legacy projection
- character generation writes canonical entry + legacy projection
- aux-memory create/update mirrored into `free_memory`

## 12.3 Frontend tests
- builtin categories updated correctly
- knowledge panel renders canonical `outline`
- no `outline_settings` main-category expectation remains
- copilot mention uses canonical data

## 12.4 Migration tests
- bootstrapping a project with existing `outline.json` / `characters.json` etc. creates correct canonical entries
- rollback restores old file layout if canonical write fails

---

## 13. Risks and Mitigations

### Risk: migration introduces triple sources of truth temporarily
Mitigation:
- clear phase ownership
- canonical writer only after Phase 3

### Risk: frontend assumptions around `outline_settings`
Mitigation:
- keep compatibility labels until UI cleanup phase

### Risk: Aux Memory merge breaks retrieval quality
Mitigation:
- preserve existing scorer and injection preview code
- only change persistence backing first

### Risk: chapter summary quality too weak
Mitigation:
- keep summary schema minimal in Phase 3
- improve later without blocking architecture shift

### Risk: 自动保存策略覆盖
Mitigation:
- 工作流自动保存（`workflow_auto_saver.py`）在保存 project data 时同步写 library
- `router_agent` 和 `coordinator` 的所有 `save_project_data()` 调用后紧跟 `library_service.upsert_from_legacy()`
- 失败时 try/except + warning log，不阻断主流程
- 文件指纹缓存机制避免不必要的重复加载

---

## 14. Recommended Execution Order

1. Build canonical library layer
2. Migrate outline first
3. Migrate character/eventline/detail/chapter/world/item
4. Add chapter summary/index
5. Update frontend category model
6. Merge Aux Memory as `free_memory`
7. Extend other modes

---

## 15. Implementation Gate

Before coding starts:
- this technical design is the source of truth
- any deviation must update this file first

During implementation:
- do not rename UI concepts before canonical model exists
- do not delete old compatibility paths before tests prove projections work

After implementation:
- update PRD + migration status

---

## 16. Implementation Status

| Phase | Status | Key Files |
|---|---|---|
| Phase 1 — 规范层 | **Done** | `library_types.py`, `library_service.py`, `library_mappers.py`, `project_manager.py` |
| Phase 2 — 读路径 | **Done** | `projects.py` GET routes, `memory_manager.py` |
| Phase 3 — 写路径 | **Done** | `router_agent.py`, `coordinator.py`, `projects.py` POST/PUT/DELETE routes |
| Phase 4 — UI 清理 | Planned | — |
| Phase 5 — 其他模式 | Planned | — |

### Phase 1-3 验证
- 33 个单元测试全部通过 (`test_library_service.py`)
- 199 个回归测试通过（1 个预有失败与本次无关）
- 新增 REST API: 8 个端点 (`/api/v1/library/*`)
- 降级策略: `is_degraded` 标志 + 自动回退旧路径

