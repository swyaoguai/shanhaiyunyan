# Deep Interview Spec: Multi-Agent Architecture Refactor Review

## Metadata

- Profile: `standard`
- Rounds: `7`
- Final Ambiguity: `0.19`
- Threshold: `0.20`
- Context Type: `brownfield`
- Proposal File: `C:\Users\wen\Desktop\AGENT\多Agent架构改造方案.md`
- Context Snapshot: `.omx/context/multi-agent-architecture-refactor-review-20260425T135921Z.md`
- Transcript: `.omx/interviews/multi-agent-architecture-refactor-review-20260425T141427Z.md`

## Clarity Breakdown

| Dimension | Score |
|---|---:|
| Intent | 0.84 |
| Outcome | 0.86 |
| Scope | 0.78 |
| Constraints | 0.66 |
| Success Criteria | 0.82 |
| Context | 0.82 |

## Intent

评审当前《多Agent架构改造方案》是否真正解决长篇创作协作模式中的核心问题，并补充更合适的改造建议，使后续演进更稳、更可扩展。

## Desired Outcome

得到一份面向长篇创作多Agent协作模式的架构结论：

1. 现方案哪些方向合理
2. 哪些点还不够，可能“拆了但没治本”
3. 应优先增加哪些补强设计，才能真正改善：
   - 任务分配到正确子Agent/任务节点
   - 分发后的上下文、缓存、记忆不丢

## In-Scope

- `novel_agent/workflow/` 下长篇创作多Agent协作模式
- `NovelCoordinator` 的职责与拆分方向
- 统一调度入口 / AgentDispatcher 是否合理
- 子Agent能力选择机制
- 章节任务市场中的上下文传递链路
- memory / cache / previous_summary / loaded_context / permanent_memory 等协作态数据的契约化

## Out-of-Scope / Non-goals

- 无限续写模式
- 短篇创作模式
- 剧本创作模式
- 追求“全系统统一运行时”
- 当前优先级中的性能/资源浪费优化

## Decision Boundaries

OMX 可以在不再单独确认的前提下，按以下边界进行后续评审/规划：

1. 默认多Agent长期只服务长篇创作，不扩到其他创作模式
2. 默认优先解决调度正确性与上下文完整性，不以性能优化为第一目标
3. 默认允许建议触及：
   - `coordinator.py`
   - `capability_registry.py`
   - 任务调度层
   - 协作上下文载体
4. 默认不要求把 Router / Communicator / ContinuousWriter 统一到同一运行时

## Constraints

- 要基于当前仓库事实评审，不能只停留在概念图
- 不能把“拆模块”误当作“解决调度正确性”
- 建议应偏长期可扩展，但不要越界到无关模式
- 用户更关注系统真实稳定，而不是优先建设可观测 UI

## Testable Acceptance Criteria

一个“合理的改造方案”至少应满足：

1. **调度正确性**
   - 任务分配不再只依赖松散 capability 匹配
   - 能显式区分：
     - task type
     - stage
     - required context
     - fallback policy
   - 章节级任务市场与主创作流程的分配规则一致，不出现“两套选人逻辑”

2. **上下文完整性**
   - 分发前后的上下文载体统一
   - `working_context.update(...)` 这种隐式拼装减少
   - `loaded_context`、`previous_summary`、`aux_memory`、`permanent_memory` 有清晰的 source-of-truth 和 merge 规则

3. **运行时边界清晰**
   - Dispatcher 负责什么，不负责什么，必须写清
   - Service 与 Agent 的边界明确，不再混入 capability 调度

4. **可演进性**
   - 后续新增一个子Agent或新协作步骤时，不需要再次把逻辑塞回 `Coordinator`

## Assumptions Exposed + Resolutions

| Assumption | Resolution |
|---|---|
| 只要引入 `AgentDispatcher` 就能治本 | 不成立；Dispatcher 只是承载点，关键仍是调度决策与上下文契约 |
| 多Agent统一运行时应覆盖所有创作模式 | 不成立；长期仅限长篇创作协作模式 |
| helper 降级为 service 的价值主要是省资源 | 部分成立；但更重要的是厘清“参与调度的对象”和“普通工具对象”的边界 |

## Pressure-pass Findings

- 用户最初表述偏“统一调用层 + 拆 Coordinator”。
- 压问后确认真正最痛的根因是：
  1. 分错 Agent / 分错任务
  2. 分配后上下文全丢
- 所以后续改造建议必须优先：
  - 调度策略显式化
  - 上下文契约显式化

## Brownfield Evidence vs Inference

### Evidence

- `NovelCoordinator` 直接实例化并注册 11 个对象：`novel_agent/workflow/coordinator.py:168-226`
- `set_knowledge_base()` 逐个注入对象：`novel_agent/workflow/coordinator.py:293-316`
- 主流程里既有直接 `execute()`，也有 `_run_autonomous_task()`：`novel_agent/workflow/coordinator.py:2396-2477`、`2705-2925`
- 章节任务市场通过 `working_context`、`loaded_context`、`permanent_memory` 等分散更新上下文：`novel_agent/workflow/coordinator.py:2128-2259`
- helper 继承 `BaseAgent` 并触发 OpenAI client 初始化：`novel_agent/agents/collab_sub_agents.py:21-27`、`novel_agent/agents/base_agent.py:100-151`

### Inference

- 当前方案若只做“统一入口”，可能改善结构，但未必足够改善“分错任务”和“上下文丢失”
- `capability_registry` 全局单例在长期演进中，可能让“协作运行时”和“其他模式”边界继续模糊

## Technical Context Findings

1. `_run_autonomous_task()` 已经像半个 dispatcher，但仍内嵌在 coordinator 中，职责过重  
   参考：`novel_agent/workflow/coordinator.py:2705-2925`
2. `get_candidate_agents_for_task()` 只是 registry 透传，说明“候选查找”和“最终调度决策”还没真正分层  
   参考：`novel_agent/workflow/coordinator.py:3619-3621`
3. 上下文目前是过程变量式传递，不是契约对象式传递  
   参考：`novel_agent/workflow/coordinator.py:2128-2259`
4. helper/service 现在被当成 agent 注册，容易污染“谁能接任务”的判断空间  
   参考：`novel_agent/workflow/coordinator.py:214-225`、`novel_agent/agents/collab_sub_agents.py:289-635`

## Review Output Contract

后续评审/规划应输出：

1. 当前方案的“合理 / 不足 / 风险”三段式结论
2. 至少一组补强建议，重点覆盖：
   - 调度规则层
   - 上下文契约层
   - Agent / Service 边界层
3. 如果进入下一阶段，优先 handoff 到：
   - `$ralplan`：出正式 PRD / 技术设计 / 测试规范

## Condensed Transcript

见：`.omx/interviews/multi-agent-architecture-refactor-review-20260425T141427Z.md`
