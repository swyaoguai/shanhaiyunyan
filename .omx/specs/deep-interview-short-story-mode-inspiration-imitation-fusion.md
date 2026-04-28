# Deep Interview Spec: Short Story Unified Inspiration/Imitation/Fusion Mode

## Metadata
- Profile: standard
- Rounds: 12
- Final ambiguity: 19.4%
- Threshold: 20%
- Context type: brownfield
- Context snapshot: `.omx/context/short-story-mode-inspiration-imitation-fusion-20260410T144022Z.md`
- Transcript: `.omx/interviews/short-story-mode-inspiration-imitation-fusion-20260410T144022Z.md`

## Clarity breakdown

| Dimension | Score |
|---|---:|
| Intent | 0.84 |
| Outcome | 0.84 |
| Scope | 0.82 |
| Constraints | 0.70 |
| Success Criteria | 0.86 |
| Context | 0.82 |

Readiness gates:
- Non-goals: ✅
- Decision Boundaries: ✅
- Pressure pass: ✅

## Intent
把短篇创作从“词条填空式入口”升级成更贴近真实创作习惯的统一模式：用户无需判断自己提供的是词条、灵感还是例文，只要把素材贴进去，系统就能自动理解并给出可选创作方向。

## Desired Outcome
用户在一个统一输入框中输入任意创作素材后，系统先自动识别素材类型并生成 **3 个不同故事路数的融合方案**；用户选择最带感的一版后，再继续生成导语、大纲和正文。相比旧模式，首轮不再只是“5 条导语”，而是更有钩子、更利于判断是否值得继续写的方案层产物。

## In-Scope
- 将原“纯词条启动”升级为统一的新输入模式
- 单输入框承接混合素材：灵感、例文/仿写参考、题材、词条、其他要求
- 系统自动识别素材类型，不要求用户手动分栏
- 首轮生成 3 个融合方案
- 3 个融合方案必须是同一批素材下的 **3 条不同故事路数**
- 用户先选择方案，再生成导语、大纲、正文
- 当只有例文输入时，默认直接自动拆解并生成 3 案
- 仿写策略默认强借鉴：保留爽点、节奏、结构骨架
- 统一替代旧“词条模式”心智与入口

## Out-of-Scope / Non-goals
- 不保留旧的独立“纯词条模式”入口
- 不要求用户手动区分“灵感 / 例文 / 题材 / 词条”
- 不把 3 个方案做成“同一路数不同包装”
- 不以“只有导语”作为首轮核心展示
- 不接受只做表层替换的仿写：不能仅改人名或措辞

## Decision Boundaries
OMX may decide without confirmation:
- 统一输入框的具体 UI 文案和提示语
- 自动识别后内部素材 schema 的设计
- 3 个融合方案的具体展示字段结构
- 方案选中后导语、大纲、正文的承接实现细节
- 旧字段 `keywords` 向新统一输入模型的兼容迁移方式

OMX must preserve:
- 单输入框心智，不回退为多分栏必填
- 默认少打断，优先直接产出 3 案
- 3 案必须是不同故事路数
- 强借鉴仅限节奏与结构骨架，不得复用人物、设定、关键事件
- 成功标准之一是素材类型识别“比较准”，不能只是误打误撞还能出方案

## Constraints
- 这是 brownfield 改造，需兼容现有短篇服务、API、固定面板和状态机
- 当前入口与请求模型是 keywords-only，需要升级数据结构与前端交互
- 自动识别要足够可靠，否则不算达标
- 默认少追问：当输入信息不完整时，优先自动拆解并产出 3 案
- 仿写参考只能保留节奏与结构骨架；人物、设定、事件必须明显换新

## Testable acceptance criteria
1. 用户在统一输入框粘贴任意一种或混合素材（词条/灵感/例文/题材）时，都能正常启动流程。
2. 系统无需用户先选择输入类型，即可自动完成素材识别与结构化。
3. 首轮产物为 3 个融合方案，而不是旧式单纯导语候选。
4. 3 个融合方案之间存在明显的故事路数差异，而非仅风格包装不同。
5. 用户选定某一方案后，后续可顺畅生成导语、大纲、正文。
6. 仅提供例文时，系统仍能直接自动拆解并生成 3 个融合方案。
7. 对仿写参考生成的方案进行人工审查时，可看出节奏/结构借鉴，但人物、设定、关键事件明显换新。
8. 用户测试时无需先判断“该填词条还是灵感”，即可理解并完成输入。
9. 若素材识别准确率不足以稳定区分主要输入类型，则视为未达标。

## Assumptions exposed + resolutions
- Assumption: 用户真正不满的是“导语质量不够”。  
  Resolution: 更本质的问题是首轮展示缺乏“噱头”和继续读下去的动力，因此首轮产物上移到“融合方案层”。

- Assumption: 为了支持混合素材，必须增加多个输入区。  
  Resolution: 用户明确拒绝分栏输入，要求单输入框 + 自动识别。

- Assumption: 仿写应偏保守避免接近原作。  
  Resolution: 用户希望默认强借鉴，但限制在节奏与结构骨架层，不允许关键内容复刻。

- Assumption: 只要能产出 3 案，即使识别不准也算改进。  
  Resolution: 用户明确否定；素材识别准确性本身是重要验收项。

## Pressure-pass findings
- Revisited answer: “不能只靠导语 / 噱头就是吸引力”
- What changed: 从抽象的“要有噱头”压实为可执行产物——**首轮必须先出 3 个融合方案供选**，这是后续整个流程重构的核心。

## Brownfield evidence vs inference

### Repository-grounded evidence
- 当前状态机启动只接受 `keywords`，缺失时报错“至少提供 1 个有效词条”。`novel_agent/short_story_service.py:1109`
- API 启动请求字段只有 `keywords / target_total_words / chapter_word_target / category / tone`。`novel_agent/web/models/requests.py:460`
- 前端启动只读取 `#short-story-keywords` 并提交到 `/api/short-story/workflow/start`。`novel_agent/web/static/short-story/short-story-events.js:30`
- 现有能力声明与交互点仍围绕“导语五选一 / 大纲确认 / 书名五选一”。`novel_agent/short_story_service.py:1804`
- 系统中已有“灵感”处理先例可参考：`continuous_writer` 维护 inspirations。`novel_agent/agents/continuous_writer.py:210`

### Inference
- 统一新模式大概率会影响服务层状态机、请求模型、前端渲染与路由提示文案
- 为满足“识别要比较准”，后续规划中应专门设计“输入解析/素材分类”阶段，而不只是替换 prompt

## Technical context findings
- Likely touchpoints:
  - `novel_agent/short_story_service.py`
  - `novel_agent/web/models/requests.py`
  - `novel_agent/web/routes/short_story.py`
  - `novel_agent/web/static/short-story/short-story-events.js`
  - `novel_agent/web/static/short-story/short-story-render.js`
  - `novel_agent/agents/router_agent.py`
- Existing workflow is strongly coupled to keyword-driven startup; migration likely needs a new unified input field plus intermediate parse result in workflow state.

## Condensed transcript
See: `.omx/interviews/short-story-mode-inspiration-imitation-fusion-20260410T144022Z.md`
