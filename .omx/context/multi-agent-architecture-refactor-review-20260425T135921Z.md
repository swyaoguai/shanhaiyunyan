# Context Snapshot: multi-agent-architecture-refactor-review

- Task statement: 评审 `多Agent架构改造方案.md`，判断方案是否合理，并提出进一步改造建议。
- Desired outcome: 得到一份基于现有代码事实的架构评审结论，并明确后续建议应偏向“稳妥落地”还是“长期演进”。
- Stated solution: 方案拟将 `NovelCoordinator` 从 3682 行拆到约 800 行，引入 `AgentDispatcher` 统一调度，降级 `collab_sub_agents.py` 中的伪 Agent 为 service，并抽离 checkpoint / memory sync 模块。
- Probable intent hypothesis: 用户想降低多 Agent 协作模式的复杂度与维护成本，同时避免对 Router / Communicator / ContinuousWriter 等独立模式造成影响。

## Known facts / evidence

- 方案文档限定改造范围在 `novel_agent/workflow/` 的多 Agent 协作模式，不动 Router / Communicator / ContinuousWriter。见 `多Agent架构改造方案.md:5-6`。
- `NovelCoordinator` 目前确实在 `__init__` 中直接实例化 11 个 agent/helper，并统一注册到能力注册表。见 `novel_agent/workflow/coordinator.py:168-226`。
- `set_knowledge_base()` 当前也显式向 11 个对象逐一注入知识库。见 `novel_agent/workflow/coordinator.py:293-316`。
- 协作执行路径确实存在统一不足：一部分流程直接 `worldbuilder.execute()` / `outliner.execute()`，另一部分走 `_run_autonomous_task()`。见 `novel_agent/workflow/coordinator.py:2396-2477`、`2705-2925`。
- `_run_autonomous_task()` 已经同时承担任务池登记、候选 agent 选择、生命周期广播、fallback、运行时任务池落盘等多种职责，说明“统一调用层”方向有代码依据。见 `novel_agent/workflow/coordinator.py:2717-2925`。
- `collab_sub_agents.py` 中的 helper 确实继承 `BaseAgent`，而 `BaseAgent` 初始化时会创建 `AsyncOpenAI` 客户端。见 `novel_agent/agents/collab_sub_agents.py:21-27`、`novel_agent/agents/base_agent.py:100-151`。
- `ContextStrategyAgent`、`ContentReaderAgent`、`ContentExpansionAgent`、`SummaryOrchestratorAgent` 等 helper 的 `execute()` 都是本地逻辑，没有直接调用 LLM。见 `novel_agent/agents/collab_sub_agents.py:289-635`。
- 能力注册表当前是全局单例，持有 agent 实例与 capability 元数据。见 `novel_agent/agents/capability_registry.py:11-155`。

## Constraints

- 评审应基于现有仓库事实，不假设不存在的运行时机制。
- 当前阶段是 deep-interview / 需求澄清，不直接改代码。
- 用户请求的是“方案合理性 + 更多建议”，尚未指明最优先的评审目标（风险、扩展性、性能、实施成本）。

## Unknowns / open questions

- 用户更看重这次改造的首要收益是什么：风险可控、长期扩展、性能资源、还是团队协作效率？
- 用户是否希望建议停留在当前方案的补强，还是允许提出更大范围的架构替代方案？
- 用户能接受的迁移成本与阶段性兼容复杂度上限是什么？

## Decision-boundary unknowns

- 我可以只做“方案评审+补强建议”，还是也应给出替代架构路线图？
- 建议是否可以触及 `capability_registry` 的单例边界、事件总线职责、任务池接口，还是要尽量局限于方案已列文件？

## Likely codebase touchpoints

- `novel_agent/workflow/coordinator.py`
- `novel_agent/agents/collab_sub_agents.py`
- `novel_agent/agents/base_agent.py`
- `novel_agent/agents/capability_registry.py`
- `novel_agent/workflow/task_pool.py`
- `novel_agent/workflow/contracts.py`
