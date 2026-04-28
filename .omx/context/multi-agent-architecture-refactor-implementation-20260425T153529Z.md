# Context Snapshot: multi-agent-architecture-refactor-implementation

- Task statement: 按 `C:\Users\wen\Desktop\AGENT\多Agent架构改造方案.md` 对 `novel_agent/workflow/` 下长篇创作多 Agent 协作模式实施架构改造。
- Desired outcome: 在不影响 Router / Communicator / ContinuousWriter / 短篇与剧本模式的前提下，落地统一执行入口、显式路由规则、统一上下文合同，以及运行时状态拆分。
- Snapshot lineage: 复用并延续 `.omx/context/multi-agent-architecture-refactor-review-20260425T135921Z.md` 的评审结论，补充为实施导向上下文。

## Known facts / evidence

- 改造文档明确边界只覆盖 `novel_agent/workflow/` 的多 Agent 协作模式，不改 `RouterAgent`、`CommunicatorAgent`、`ContinuousWriter`、`BaseAgent`、`MessageBus`。见 `多Agent架构改造方案.md`。
- `NovelCoordinator.__init__()` 当前直接实例化 worldbuilder/outliner/chapter_writer/polisher/evaluator/character_builder 与 5 个 helper，并统一注册到能力注册表，说明编排、注册、生命周期已耦合。见 `novel_agent/workflow/coordinator.py:151-226`。
- `set_knowledge_base()` 当前显式遍历 11 个对象逐个注入知识库，进一步说明 Coordinator 持有过多运行时细节。见 `novel_agent/workflow/coordinator.py:293-316`。
- `create_novel()` 主流程仍直接调用 `worldbuilder.execute()`、`character_builder.execute()`、`outliner.execute()`，尚未统一走执行入口。见 `novel_agent/workflow/coordinator.py:2396-2477`。
- `_run_autonomous_task()` 已同时承担任务池登记、候选查询、agent 选择、fallback、广播、运行时任务池落盘等职责，是最接近 Dispatcher 的现有提取点。见 `novel_agent/workflow/coordinator.py:2705-2985`。
- `_execute_chapter_task_market()` 通过 `working_context = dict(base_context)` 加上条件分支与 `working_context.update(loaded_context)` 拼装上下文，说明上下文 source-of-truth 与 merge 规则不稳定。见 `novel_agent/workflow/coordinator.py:2119-2263`。
- `AgentCapabilityRegistry` 当前是“能力声明 + 候选排序 + agent 实例容器”的全局单例，但没有 stage / required_context / fallback 决策语义。见 `novel_agent/agents/capability_registry.py:11-128`。
- `collab_sub_agents.py` 中 `ContextStrategyAgent`、`ContentReaderAgent`、`ContentExpansionAgent`、`FileNamingAgent`、`SummaryOrchestratorAgent` 都继承 `_SimpleAgent -> BaseAgent`，因此会继承 OpenAI client 初始化成本。见 `novel_agent/agents/collab_sub_agents.py:18-27`, `novel_agent/agents/collab_sub_agents.py:289-590`, `novel_agent/agents/base_agent.py:100-151`。
- 现有测试已覆盖 `_run_autonomous_task()`、章节任务市场、summary_orchestrate、content_read/permanent_memory 等基础行为，适合作为迁移护栏。见 `novel_agent/tests/test_supervised_collab_foundation.py` 与 `novel_agent/tests/test_workflow.py`。

## Constraints

- 需遵守文档声明的边界：仅改长篇多 Agent 协作模式。
- 对外接口 `create_novel` / `execute_project_ready_tasks` / `set_knowledge_base` / pause-resume-cancel 应保持兼容。
- 迁移应渐进式进行，旧 helper 与旧链路允许短期兼容或 deprecated 过渡。
- 现有 pytest 用例是主要回归护栏，新增改造需补充面向 Dispatcher / Routing / ExecutionContext 的测试。

## Unknowns / open questions

- `CheckpointManager` / `MemorySyncManager` 是否应直接复用现有 Coordinator 私有方法，还是首轮仅做薄封装后续再继续下沉。
- `TaskPool` 与 `contracts.py` 的上下文字段扩展是以 metadata 兼容补充为主，还是引入新的 envelope/context 模型并逐步替换。
- 新 Dispatcher 第一阶段是否要接管世界观/角色/大纲主流程，还是先从章节任务市场与 `_run_autonomous_task()` 路径切入。

## Likely codebase touchpoints

- `novel_agent/workflow/coordinator.py`
- `novel_agent/workflow/__init__.py`
- `novel_agent/workflow/contracts.py`
- `novel_agent/workflow/task_pool.py`
- `novel_agent/agents/capability_registry.py`
- `novel_agent/agents/collab_sub_agents.py`
- `novel_agent/tests/test_supervised_collab_foundation.py`
- `novel_agent/tests/test_workflow.py`
