# Context Snapshot

- Task statement: 优化“短篇创作模式”，不再只支持词条驱动，而是支持“灵感 + 仿写 + 新梗融合”创作。
- Desired outcome: 形成可执行需求，明确输入模式、边界、兼容策略与验收标准，再交给后续规划/实现。
- Stated solution: 从仅 `keywords` 启动的短篇流程，升级为可接受多种创作素材的启动与生成链路。
- Probable intent hypothesis: 用户希望短篇创作入口从“标签填空式”升级为更贴近真实创作工作流的“灵感孵化 + 风格借鉴 + 新梗重组”模式，同时保留现有短篇固定面板体验。

## Known facts / evidence

- 当前短篇状态机入口只接受 `keywords`，并在缺失时直接报错“至少提供 1 个有效词条”。`novel_agent/short_story_service.py:1109`
- 当前能力声明与交互点都围绕“导语五选一 / 大纲确认 / 书名五选一”，未声明灵感或仿写输入。`novel_agent/short_story_service.py:1804`
- API 启动请求模型只有 `keywords / target_total_words / chapter_word_target / category / tone`。`novel_agent/web/models/requests.py:460`
- 前端创建工作流时，只从 `#short-story-keywords` 解析词条并提交到 `/api/short-story/workflow/start`。`novel_agent/web/static/short-story/short-story-events.js:30`
- 路由层提示文案仍是“检测到您要进行短篇词条创作”。`novel_agent/agents/router_agent.py:1075`
- 现有系统中“灵感”能力已存在于无限续写链路，可作为参考模式。`novel_agent/agents/continuous_writer.py:210`

## Constraints

- 这是 brownfield 改造，需兼容现有短篇工作流、前端固定面板和 API。
- 现有“词条驱动”能力大概率不能回归破坏。
- 深访模式本轮只做澄清，不直接实施。

## Unknowns / open questions

- “灵感”具体指一句话脑洞、剧情梗概、场景片段、人物关系，还是都支持。
- “仿写”具体是风格借鉴、结构借鉴、题材借鉴，还是对参考文本做受控改写。
- “融合新梗”是自动生成组合方案，还是让用户明确输入多个来源后再融合。
- 词条模式是否保留为并列入口，还是被更高层“创作素材”模型吸收。
- 用户最在意的是输入体验、生成质量，还是可控性/合规边界。

## Decision-boundary unknowns

- OMX 是否可以自行定义新的输入 schema。
- OMX 是否可以自行重构前端交互为多标签页/多输入区。
- OMX 是否可以自行决定仿写的合规策略与相似度约束。

## Likely codebase touchpoints

- `novel_agent/short_story_service.py`
- `novel_agent/web/models/requests.py`
- `novel_agent/web/routes/short_story.py`
- `novel_agent/web/static/short-story/short-story-events.js`
- `novel_agent/web/static/short-story/short-story-render.js`
- `novel_agent/agents/router_agent.py`
