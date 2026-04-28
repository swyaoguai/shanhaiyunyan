## Task Statement
排查项目内多 agent 模式，确认是否仍有功能性优化空间与尚未发现的错误。

## Desired Outcome
形成一份可执行的排查规格：明确要审查的多 agent 流程、优先级、产出形式，以及后续是只出问题清单还是继续修复。

## Stated Solution
用户希望先进行深度澄清，再决定如何推进排查。

## Probable Intent Hypothesis
用户想降低多 agent 模式在真实使用中的隐性故障风险，同时识别还能提升稳定性、可观测性或协作效率的环节。

## Known Facts / Evidence
- 代码库为 brownfield 项目，存在明确的多 agent 架构与协调器：`novel_agent/workflow/coordinator.py`
- 路由入口与任务分发集中在 `novel_agent/agents/router_agent.py`
- Web 侧聊天/工作流状态编排集中在 `novel_agent/web/routes/chat.py`
- 已有相关回归测试：`novel_agent/tests/test_chat_routing_execution.py`
- 运行日志中出现多次 `show_in_multi_agent` 开关切换与 workflow status 访问记录：`agent.log`

## Constraints
- 当前处于 deep-interview 阶段，不直接实现修复
- 需要先明确目标边界、成功标准、非目标与可自主决策范围
- 用户请求聚焦“多 agent 模式”的功能优化与隐藏错误，而非整个项目泛化审计

## Unknowns / Open Questions
- 用户更看重“发现问题并排序”还是“直接给修复方案/落地改进”
- 多 agent 模式的目标范围是否仅限 Copilot + Router + Coordinator 主链路
- 优先关注真实用户故障、测试盲区、状态一致性，还是性能/可维护性
- 可接受的排查深度与交付形式尚未明确

## Decision-Boundary Unknowns
- 我是否可以只输出审计/诊断报告，还是需要进一步进入修复执行
- 我是否可以自行增加测试、运行现有测试、或做静态分析来支撑结论
- 我是否可以将“体验类优化”纳入，还是仅限功能正确性

## Likely Codebase Touchpoints
- `novel_agent/agents/router_agent.py`
- `novel_agent/workflow/coordinator.py`
- `novel_agent/web/routes/chat.py`
- `novel_agent/web/app.py`
- `novel_agent/tests/test_chat_routing_execution.py`
- `novel_agent/tests/test_app_settings.py`
