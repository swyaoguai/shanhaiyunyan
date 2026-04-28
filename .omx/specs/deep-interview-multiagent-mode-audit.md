# Deep Interview Spec: multiagent-mode-audit

## Metadata
- **Profile:** standard
- **Rounds:** 6
- **Final Ambiguity:** 17.8%
- **Threshold:** 20%
- **Context Type:** brownfield
- **Context Snapshot:** `.omx/context/multiagent-mode-audit-20260410T135629Z.md`
- **Transcript:** `.omx/interviews/multiagent-mode-audit-20260410T135629Z.md`

## Clarity Breakdown
| Dimension | Score | Notes |
|---|---:|---|
| Intent | 0.60 | 目标是系统性排查多 agent 模式并降低隐性故障风险 |
| Outcome | 0.92 | 交付为按优先级排序的问题清单 |
| Scope | 0.90 | 覆盖所有与多 agent 模式相关环节，并可顺带纳入发现的单 agent 问题 |
| Constraints | 0.92 | 允许测试、静态分析、日志排查、风险项标注 |
| Success | 0.90 | 可综合判断优先级，但需向用户解释不同排序维度 |
| Context | 0.80 | 主链路代码与现有测试触点已确认 |

## Intent
用户希望确认项目内多 agent 模式是否还存在可优化的功能环节和未暴露错误，并以问题清单形式获得可执行的排查结果。

## Desired Outcome
输出一份**按优先级排序的问题清单**，而不是直接修复；清单应能帮助用户识别：
- 多 agent 协作本身引入或放大的问题
- 在多 agent 排查过程中顺手发现的单 agent 问题
- 可附带列出的普通代码洁癖 / 重构建议

## In Scope
- `RouterAgent -> NovelCoordinator -> 子 Agent -> chat/workflow status` 主链路
- 与多 agent 模式有关的配置同步、状态一致性、日志可观测性、测试盲区
- 与多 agent 体验/正确性相关的外围实现
- 排查时顺手发现的单 agent 问题
- 与主任务无直接关系但值得列出的普通代码洁癖 / 重构建议

## Out of Scope / Non-goals
- 纯 UI 美化
- 纯文案措辞优化

## Decision Boundaries
OMX 可以在无需再次确认的前提下：
- 自主运行现有测试
- 做静态代码审查
- 结合日志与代码路径分析问题
- 将“已证实问题”和“未完全复现但有证据的风险项”分开标注
- 自行综合多维度完成问题优先级排序，但需向用户解释各维度分别代表什么

## Constraints
- 当前任务是**排查与规格澄清**，不是直接修复
- 优先级排序需要兼顾多个维度，而不是单一分数
- 问题清单需要覆盖 brownfield 现有实现，不应仅凭假设

## Testable Acceptance Criteria
完成物应至少满足：
1. 给出一份按优先级排序的问题清单
2. 每项问题尽量包含：现象/证据、影响范围、涉及模块、优先级原因
3. 对未完全复现的问题单独标为“风险项”或类似类别
4. 明确说明至少这些排序维度各自代表什么：
   - 实际使用影响
   - 隐藏错误风险
   - 对多 agent 主流程的阻断程度
   - 可选：修复复杂度 / 证据置信度
5. 覆盖与多 agent 模式相关的主链路与外围触点，而非只审单一文件

## Assumptions Exposed + Resolutions
- **假设：** 用户只想看多 agent 主链路  
  **结果：** 否，所有与多 agent 模式相关环节都要覆盖
- **假设：** 用户只想看多 agent 特有问题  
  **结果：** 否，顺手发现的单 agent 问题也可纳入
- **假设：** UI / 文案类项也要纳入  
  **结果：** 否，纯 UI 和纯文案暂不纳入
- **假设：** 只能出结论，不能运行测试或查日志  
  **结果：** 否，允许全部排查动作

## Pressure-pass Findings
- 通过反向追问确认“单 agent 问题是否纳入”，扩大了问题清单边界
- 通过收缩追问确认“非目标”，排除了纯 UI / 文案项

## Brownfield Evidence vs Inference Notes
- **Evidence**
  - `novel_agent/agents/router_agent.py`：RouterAgent 作为路由入口
  - `novel_agent/workflow/coordinator.py`：协调器-工作者多智能体协作与 workflow state
  - `novel_agent/web/routes/chat.py`：chat / workflow 状态对外暴露与主交互入口
  - `novel_agent/tests/test_chat_routing_execution.py`：现有多 agent 聊天与工作流回归测试
- **Inference**
  - 配置同步、日志可观测性、外围开关等可能对多 agent 行为产生影响，因此应纳入审查范围

## Technical Context Findings
- 存在明确的多 agent 架构与状态机/协调器设计
- Web 层与 Agent 层存在耦合点，容易出现状态同步或可观测性问题
- 已有测试可以作为排查基线，但可能存在盲区

## Recommended Issue-list Shape
建议后续问题清单至少含以下字段：
- 标题
- 分类（已证实 / 风险项 / 代码洁癖&重构建议）
- 相关模块
- 证据
- 影响
- 优先级
- 优先级解释（按“实际影响 / 隐藏风险 / 主流程阻断 / 修复复杂度或置信度”拆开说明）

## Condensed Transcript
见：`.omx/interviews/multiagent-mode-audit-20260410T135629Z.md`
