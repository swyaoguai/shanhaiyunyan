# PRD: 短篇创作统一输入 + 融合方案模式

## Requirements Summary

基于已完成的 deep-interview 规格，本次改造把短篇创作从 **keywords-only** 流程升级为 **统一单输入框 + 自动识别素材类型 + 3 个融合方案预选** 的新模式。当前系统的入口、状态机、请求模型和提示词都围绕“创作词条 -> 5 条导语”设计：状态机起点与步骤枚举仍是 `AWAITING_KEYWORDS / GENERATING_SYNOPSIS` 等词条导向流程，`start()` 缺少关键词时会直接报错，启动请求模型也只有 `keywords` 字段，前端表单明确显示“创作词条”，并提示“先填词条，再直接点生成导语”。这些事实分别见 `novel_agent/short_story_service.py:17`, `novel_agent/short_story_service.py:1109`, `novel_agent/web/models/requests.py:460`, `novel_agent/web/static/short-story/short-story-render.js:423`, `novel_agent/web/static/short-story/short-story-render.js:448`。

用户已经明确边界：
- 不再保留独立“纯词条模式”，而是统一入口
- 用户只使用一个总输入框，系统自动识别素材类型
- 首轮核心产物从“导语候选”改为“3 个不同故事路数的融合方案”
- 用户选定方案后，再生成导语、大纲、正文
- 例文输入默认少打断，优先直接拆解并生成 3 案
- 仿写默认强借鉴，但仅限节奏与结构骨架；人物、设定、事件必须明显换新
- 关键验收不是“还能出结果”，而是素材类型识别要比较准确

## Brownfield Evidence

- 当前短篇能力声明仍暴露 7 步工作流，核心步骤是 `generate_synopsis -> generate_outline -> write_content`。`novel_agent/short_story_service.py:45`, `novel_agent/short_story_service.py:1804`
- 当前 synopsis prompt 明确要求“根据这些词条，生成 5 条风格各异的故事导语”。`novel_agent/short_story_service.py:151`
- 当前 outline prompt 直接依赖“创作词条 + 选定导语”。`novel_agent/short_story_service.py:183`
- 当前 workflow/start 路由只接 `keywords / target_total_words / chapter_word_target / category`。`novel_agent/web/routes/short_story.py:237`
- 当前前端状态持久化把草稿字段命名为 `draftKeywords`。`novel_agent/web/static/short-story/short-story-state.js:152`, `novel_agent/web/static/short-story/short-story-state.js:289`
- Router 仍把短篇请求解释为“短篇词条创作”，并提示“填入词条并生成 5 条导语”。`novel_agent/agents/router_agent.py:1068`
- 现有回归测试覆盖了完整短篇流程、固定入口引导、前端状态持久化与 placeholder 蓝图保护，可作为重构回归网。`novel_agent/tests/test_short_story_routes.py:120`, `novel_agent/tests/test_short_story_routes.py:889`, `novel_agent/tests/test_frontend_state_persistence.py:71`, `novel_agent/tests/test_frontend_state_persistence.py:109`

## Acceptance Criteria

1. 短篇面板首页只保留 **一个统一输入框**，不再出现“创作词条”单一心智文案。
2. 用户粘贴任意一种或混合素材（词条、灵感、例文、题材、其他要求）后，服务端能先完成素材识别与结构化，再启动 workflow。
3. 首轮接口与 UI 展示的是 **3 个融合方案**，且 3 案之间为不同故事路数，而非仅风格包装差异。
4. 用户选定某一方案后，后续仍能走导语、大纲、章节、质检、复审、书名、组装输出链路。
5. 当输入只有例文时，系统默认不先追问，直接自动拆解并生成 3 个融合方案。
6. 仿写生成结果默认保留节奏/结构骨架，但人工检查时人物、设定、关键事件必须明显换新。
7. 若素材识别结果置信度不足，应在 workflow 中留下可见的解析结果或 warning，便于用户理解系统如何解读输入。
8. Router 针对短篇请求的引导文案同步更新，不再强调“词条 -> 5 条导语”。
9. 现有短篇完整流程、前端状态持久化与路由测试需扩展或重写后保持通过。

## RALPLAN-DR Summary

### Principles
1. **统一输入心智优先**：用户不需要预判素材类型。
2. **方案层决策前置**：先选故事路数，再展开导语/大纲/正文。
3. **重构优先兼容现有后半程**：尽量复用现有 outline/chapter/review 链路。
4. **识别准确性是功能本身的一部分**：输入解析不是装饰层。
5. **强借鉴但内容重构**：保留骨架，不复刻关键内容。

### Decision Drivers
1. 用户明确要求统一入口并取消独立词条模式
2. 现有系统大部分复杂度集中在导语之后，适合在 workflow 前半段加新阶段而非整体推翻
3. 测试与前端状态已存在较多保护网，适合做渐进式状态机升级

### Viable Options

#### Option A — 在现有状态机前插入“输入解析 + 融合方案选择”阶段
**Approach:** 扩展 workflow/request/state/prompt，新增 `raw_input`、`input_analysis`、`fusion_candidates`、`selected_fusion`，在 synopsis 前增加解析与三案选择阶段。

**Pros**
- 最大化复用现有 outline/chapter/quality/title 流程
- 改造范围清晰，路由与前端可分步迁移
- 与现有测试结构最匹配，容易扩充回归用例

**Cons**
- 状态机枚举、前端步骤条、持久化结构都要升级
- synopsis / outline prompt 需要从“词条驱动”改写为“方案驱动”

#### Option B — 保留旧 workflow，不改状态机，只在 start 前做“统一输入预处理”
**Approach:** 增加一个预处理层，把混合输入转成旧的 `keywords + selected_synopsis` 风格，再喂给既有流程。

**Pros**
- 改动表面上更小
- 后端现有多数方法可继续使用

**Cons**
- 会把“3 个融合方案”硬塞进旧导语语义，概念混乱
- 很难满足用户要求的“首轮不是导语，而是三案”
- 容易留下双轨心智：表面统一，内部仍是词条模式

### Chosen Direction
选择 **Option A**。

### Invalidation Rationale for Alternatives
Option B 与用户边界直接冲突：它无法真正废除“词条模式”心智，也不适合作为“3 个不同故事路数”的首轮产物承载层。

## Architect Review (applied)

Architect concern 1: 前端持久化和 workflow state 现在以 `draftKeywords` 为中心，如果直接替换字段名会损坏历史草稿恢复。证据见 `novel_agent/web/static/short-story/short-story-state.js:157` 与 `novel_agent/web/static/short-story/short-story-state.js:213`。  
**Applied response:** 计划采用兼容迁移：新增 `draftSourceInput` / `raw_input`，保留对 legacy `draftKeywords` 的读取与一次性迁移。

Architect concern 2: 现有 synopsis / outline / chapter prompt 都以 `keywords` 和 `selected_synopsis` 为核心上下文。`novel_agent/short_story_service.py:151`, `novel_agent/short_story_service.py:183`, `novel_agent/short_story_service.py:243`。  
**Applied response:** 方案选定后生成一个结构化 `selected_fusion` 对象，作为 synopsis 与 outline 的上游来源，同时保留 `keywords` 作为可选派生字段而非唯一输入。

Architect concern 3: 步骤条与 section gating 当前围绕“生成导语”展开；新增步骤若处理不好会破坏 flags。`novel_agent/web/static/short-story/short-story-render.js:460`。  
**Applied response:** 先新增 pre-synopsis steps，再把原 synopsis section 改为“基于已选方案生成导语”，避免把 3 案塞进原导语 section。

## Critic Review (applied)

Critic issue 1: 仅说“自动识别素材类型”不够可测。  
**Applied response:** 将 acceptance criteria 明确为：支持单类或混合输入、低置信度时留下可见解析结果/warning、识别不准不算达标。

Critic issue 2: 原计划未覆盖 router 和测试回归。  
**Applied response:** 增加 router 文案升级、前端状态测试、服务/路由测试扩展为明确实现步骤。

Critic issue 3: 强借鉴边界存在误实现风险。  
**Applied response:** 增加专门的 fusion prompt 约束与人工审查式验证点。

**Verdict:** APPROVE after the above improvements.

## Implementation Steps

### Step 1 — 扩展统一输入数据模型与 workflow 阶段
- 在 `novel_agent/web/models/requests.py` 为 short-story start/request 增加统一输入字段，如 `source_input`、可选 `parsed_materials` / `analysis_feedback`，同时保留对 legacy `keywords` 的兼容读取。当前 request 仅有 `keywords`。`novel_agent/web/models/requests.py:460`
- 在 `novel_agent/short_story_service.py` 增加新阶段枚举，例如：
  - `ANALYZING_SOURCE_INPUT`
  - `AWAITING_FUSION_SELECTION`
  - 保留后续 synopsis/outline/content/review/title stages
- 扩展 workflow state：新增 `raw_input`, `input_analysis`, `input_confidence`, `detected_material_types`, `fusion_candidates`, `selected_fusion`, `legacy_keywords`
- 在 state normalize / snapshot / transition 中兼容 legacy workflows，确保旧草稿不会因缺字段崩溃。当前 normalize 逻辑围绕 keyword state 工作。`novel_agent/short_story_service.py:1103`

### Step 2 — 引入“输入解析 + 三案融合”服务层
- 在 `novel_agent/short_story_service.py` 新增：
  - 输入解析 prompt builder
  - 解析结果记录方法
  - 融合方案 prompt builder
  - 融合方案 register/select 方法
- 把现有 `SYNOPSIS_PROMPT_TEMPLATE` 从直接吃 `keywords` 改为吃 `selected_fusion + parsed_materials`；outline/chapter/title/tag prompts 同步改为优先依赖方案层上下文。当前模板仍直连 `keywords`。`novel_agent/short_story_service.py:151`, `novel_agent/short_story_service.py:183`, `novel_agent/short_story_service.py:243`, `novel_agent/short_story_service.py:432`, `novel_agent/short_story_service.py:467`
- 为强借鉴场景定义结构化约束字段，例如：
  - `borrowed_rhythm`
  - `borrowed_structure`
  - `must_refresh_characters`
  - `must_refresh_setting`
  - `must_refresh_events`

### Step 3 — 路由层改造为新前半程 API
- 在 `novel_agent/web/routes/short_story.py` 的 `/workflow/start` 中改为接收统一输入，并返回下一步为“analyze_input”而不是“generate_synopsis”。当前直接返回 `next_step: generate_synopsis`。`novel_agent/short_story_service.py:1841`
- 新增 API：
  - `/short-story/input/analyze`
  - `/short-story/fusion-options/generate`
  - `/short-story/fusion-options/select`
- 保留现有 `/synopsis/generate`、`/outline/generate` 等路径，但其前置状态改为必须已选 `selected_fusion`
- 统一错误提示，从“至少提供 1 个有效词条”改为“请提供创作素材”。当前错误文案在 `novel_agent/short_story_service.py:1117`

### Step 4 — 前端单输入框、步骤条与持久化迁移
- 在 `novel_agent/web/static/short-story/short-story-render.js`：
  - 把“创作词条” textarea 改为统一输入文案
  - 替换流程提醒“先填词条，再点生成导语”为“粘贴任意素材 -> 系统识别 -> 选择 3 个方案之一”
  - 在 stepbar/section 中新增“素材识别”“融合方案”两段
  - 为 3 个融合方案设计卡片区与选中态
- 在 `novel_agent/web/static/short-story/short-story-events.js`：
  - `ensureShortStoryWorkflowForSynopsis()` 重命名并改造成“ensure workflow for source input”
  - 起始提交不再 `parseShortStoryKeywords()`，而是提交 `source_input`
  - 事件链改为：start -> analyze -> fusion generate -> fusion select -> synopsis -> outline...
- 在 `novel_agent/web/static/short-story/short-story-state.js`：
  - 新增 `draftSourceInput` 等字段
  - 兼容读取旧 `draftKeywords`
  - 更新 persisted payload 与 project state key 下的数据结构

### Step 5 — 更新 Router 与文案体系
- 修改 `novel_agent/agents/router_agent.py`，短篇引导不再强调“短篇词条创作 / 填入词条并生成 5 条导语”。当前文案在 `novel_agent/agents/router_agent.py:1075`
- 将实体抽取从“发现词条”扩展到“可能是短篇统一素材输入”，即使没有“词条”字样，只要用户说短篇/微小说 + 提供内容，也能引导到固定入口
- 同步更新 capabilities 暴露的 interaction points 与 states。当前 capabilities 仍声明“导语五选一”。`novel_agent/short_story_service.py:1804`

### Step 6 — 回归测试与新增验证
- 更新/新增 service tests：
  - 统一输入启动成功
  - 输入解析结果写入 workflow
  - 3 个融合方案注册与选择
  - 方案选中后 synopsis/outline prompt 改为基于 selected_fusion
- 更新/新增 route tests：
  - `/workflow/start` 兼容 legacy keywords 与新 `source_input`
  - 新 analyze/fusion routes
  - router fixed-panel guidance 文案更新
- 更新/新增 frontend tests：
  - 单输入框渲染与 placeholder
  - 新 section gating
  - legacy `draftKeywords` 到 `draftSourceInput` 的恢复迁移
  - 3 个融合方案卡片交互

## Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| 旧草稿恢复失效 | 当前持久化字段以 `draftKeywords` 为核心 | 做一次性兼容迁移，并保留 legacy 读取分支 |
| 自动识别准确率不够 | 用户明确说识别不准不算成功 | 在解析结果中保存置信度与类型明细；加入专门测试夹具覆盖混合输入 |
| 3 案和导语语义重叠 | 容易造成流程重复、UI 拖沓 | 明确“方案=故事路数决策层”“导语=选定方案后的包装层” |
| 强借鉴实现跑偏成复刻 | 有合规与产品风险 | 在 fusion prompt 中显式约束“人物/设定/事件必须明显换新”，并做人工审查清单 |
| 路由与前端状态多点修改导致回归 | 短篇前端已拆成 state/api/render/events 多文件 | 依赖现有 bundle 测试和 DOM 测试做回归覆盖 |

## Verification Steps

1. **Service**
   - 运行 `pytest novel_agent/tests/test_short_story_service.py`
   - 新增断言：统一输入、解析阶段、三案选择、方案驱动 prompt
2. **Routes**
   - 运行 `pytest novel_agent/tests/test_short_story_routes.py`
   - 覆盖新 analyze/fusion routes 与 router 引导文案
3. **Frontend bundle regression**
   - 运行 `pytest novel_agent/tests/test_frontend_state_persistence.py`
   - 验证持久化字段迁移与 section gating
4. **Frontend DOM regression**
   - 运行 `npm.cmd run test:frontend -- settings-short-story.dom.test.js`
   - 验证单输入框、三案卡片、按钮交互与步骤区渲染
5. **Manual smoke**
   - 分别输入：纯词条、纯灵感、纯例文、混合素材
   - 确认都能产出 3 个不同故事路数的方案

## ADR

### Decision
采用 **在现有短篇状态机前插入“输入解析 + 融合方案选择”阶段** 的增量重构方案。

### Drivers
- 用户要求统一单输入框与自动识别
- 首轮必须先给 3 个不同故事路数
- 现有 outline/chapter/review 链路成熟，值得复用

### Alternatives Considered
- 保持旧 workflow，仅在 start 前做统一输入预处理
- 新旧双模式并存

### Why Chosen
该方案最符合用户边界，同时能保留后半程成熟链路，降低重写成本并最大化利用现有测试。

### Consequences
- 前端/后端状态模型会升级
- 需要新增前半程 API 与 workflow transitions
- prompt 体系从“关键词驱动”转为“方案驱动”

### Follow-ups
- 如果后续识别准确率仍不稳定，可追加轻量反馈机制或置信度提示
- 后续可把“强借鉴/弱借鉴”做成高级参数，但不应破坏默认单输入框心智

## Available-Agent-Types Roster

适合后续执行的角色：
- `architect` — 收敛 workflow/stage/data-model 设计
- `executor` — 服务层、路由层、前端实现
- `critic` — 审核方案是否偏离统一心智与强借鉴边界
- `test-engineer` — 补齐 pytest / DOM regression
- `designer` — 单输入框与 3 案卡片展示细节
- `verifier` — 验证 acceptance criteria 与回归范围

## Follow-up Staffing Guidance

### For `$ralph`
- Lane 1: service + request model + routes（reasoning: high）
- Lane 2: frontend state/render/events（reasoning: high）
- Lane 3: tests + verification（reasoning: medium）
- Ralph 适合在单 owner 下连续推进，因为该改造跨状态机与前端状态，接口契约连续性很重要。

### For `$team`
- Worker A: `novel_agent/short_story_service.py` + `web/models/requests.py`
- Worker B: `web/routes/short_story.py` + `agents/router_agent.py`
- Worker C: `web/static/short-story/*.js`
- Worker D: `novel_agent/tests/*short_story*` + `frontend-tests/settings-short-story.dom.test.js`
- Team 适合并行，但必须先冻结统一 workflow schema，再分 lane 落地。

## Launch Hints

- Ralph:
  - `$ralph .omx/plans/prd-short-story-unified-input-mode.md`
- Team:
  - `$team .omx/plans/prd-short-story-unified-input-mode.md`
  - 或 `omx team .omx/plans/prd-short-story-unified-input-mode.md`

## Team Verification Path

1. Team 完成后，先由测试 lane 提供：
   - 新旧输入模式回归证据
   - route/service/frontend test 通过记录
2. 再由 verifier/Ralph 做最终检查：
   - 单输入框是否真的替代旧词条心智
   - 3 个方案是否是不同故事路数
   - 识别准确性是否达到“比较准”的产品预期

## Applied Improvements Changelog
- 加入 legacy `draftKeywords` 迁移要求
- 加入 router 与前端文案同步要求
- 把“识别准确率”从模糊目标提升为明确验收项
- 增加强借鉴边界的专门验证点
