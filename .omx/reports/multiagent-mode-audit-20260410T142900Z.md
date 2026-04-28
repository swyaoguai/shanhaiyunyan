# Multi-Agent Audit Report

## Scope
- 审查对象：项目内与多 agent 模式相关的主链路与外围环节
- 交付目标：按优先级排序的问题清单
- 排除项：纯 UI 美化、纯文案优化

## Method
- 代码审查：
  - `novel_agent/web/routes/chat.py`
  - `novel_agent/agents/router_agent.py`
  - `novel_agent/workflow/coordinator.py`
  - `novel_agent/web/routes/novel.py`
  - `novel_agent/agents/communicator.py`
  - `novel_agent/tests/test_chat_routing_execution.py`
- 执行验证：
  - `python -m pytest novel_agent/tests/test_chat_routing_execution.py -q` ✅ `31 passed`
  - `python -m pytest novel_agent/tests/test_app_settings.py -q` ✅ `9 passed`
- 定向复现：
  - 复现 `NovelCoordinator.pause()/resume()/cancel()` 状态漂移
  - 复现 chat 路由执行完成后 `/chat/workflow-status` 文案状态与 snapshot 不一致
  - 复现 chat 路由创作后未初始化 `task_pool/collab_execution_trace`
  - 复现断点续作时“复用文件被标记为 updated”

## Priority Dimensions
- **实际使用影响**：对真实使用是否直接造成误导、失败或中断
- **隐藏错误风险**：是否容易在后续迭代或复杂场景中放大
- **主流程阻断程度**：是否影响 Router / Coordinator / workflow 主链路
- **修复复杂度 / 置信度**：修复难度与当前证据确定性

---

## P0-1 已确认：`/chat/workflow-status` 混用了“会话快照”和“全局协调器状态”，会把已完成流程显示成 `idle/paused`

- **分类**：已证实问题
- **实际使用影响**：高
- **隐藏错误风险**：高
- **主流程阻断程度**：高
- **修复复杂度 / 置信度**：中 / 高

### Evidence
- `novel_agent/web/routes/chat.py:1472-1504`
  - `get_chat_workflow_status()` 取的是**会话级** `workflow snapshot`
- `novel_agent/web/routes/chat.py:888-930`
  - `_format_workflow_status()` 又优先读取 **global coordinator.get_project_status()**
- 自定义复现结果：
  - `workflow.status = completed`
  - 但 `reply` 中仍显示 `当前创作状态：idle`

### Why this matters
- 同一接口同时返回：
  - 结构化 `workflow.status=completed`
  - 文案状态却可能是 `idle/paused/failed`
- 一旦存在多 session / 项目切换 / chat 路由自建执行链，这种混读会直接误导用户和前端显示。

### Likely root cause
- workflow snapshot 是**按 session**维护
- coordinator 状态是**全局实例**维护
- `/chat/workflow-status` 没有统一“谁是权威状态源”

---

## P0-2 已确认：`NovelCoordinator.resume()` / `cancel()` 不会修正 `workflow_state/checkpoint`，暂停后状态会卡死

- **分类**：已证实问题
- **实际使用影响**：高
- **隐藏错误风险**：高
- **主流程阻断程度**：高
- **修复复杂度 / 置信度**：低 / 高

### Evidence
- `novel_agent/workflow/coordinator.py:1111-1125`
  - `pause()` 调用了 `_update_checkpoint(state=WorkflowState.PAUSED)`
  - `resume()` 只改了 `self._paused = False`
  - `cancel()` 只改了 `self._cancelled = True`
- 复现输出：
  - `after_pause paused paused`
  - `after_resume paused paused`
  - `after_cancel paused paused True`

### Why this matters
- 恢复后状态仍可能显示 `paused`
- 取消后状态也可能继续显示 `paused`
- 这会直接污染 `/status`、workflow 可观测性以及前端控制逻辑

### Likely root cause
- 控制标志 `_paused/_cancelled` 与对外状态 `workflow_state/checkpoint` 没有同步维护

---

## P1-1 已确认：Chat 主入口绕过了正式协作执行链，导致 `task_pool` / `collab_execution_trace` 不生成

- **分类**：已证实问题 + 架构缺口
- **实际使用影响**：中高
- **隐藏错误风险**：高
- **主流程阻断程度**：中高
- **修复复杂度 / 置信度**：中 / 高

### Evidence
- Chat 路由走的是：
  - `novel_agent/web/routes/chat.py:1609-1645`
  - `novel_agent/agents/router_agent.py:2293-2614`
- 这条路径直接调用：
  - `generate_world`
  - `generate_outline`
  - `_write_single_chapter_internal / write_single_chapter`
- 但正式协作链在：
  - `novel_agent/web/routes/novel.py:92-118`
  - `novel_agent/web/routes/novel.py:228-240`
  - `novel_agent/workflow/coordinator.py:1204-1279`
  - `novel_agent/workflow/coordinator.py:1684-1820`
- 定向复现结果：
  - `creation_contract` ✅
  - `task_graph_draft` ✅
  - `task_pool` ❌ `None`
  - `collab_execution_trace` ❌ `None`

### Why this matters
- 现在最常见的 Copilot/chat 入口，并没有真正进入你项目里已经设计好的“正式多 agent 协作执行链”
- 导致主入口缺失：
  - task pool
  - collab execution trace
  - 项目 ready task 执行
  - 更完整的协作审计/扩展空间

### Likely root cause
- 项目存在两套“创作执行路径”
  1. `chat -> router` 的轻量直写路径
  2. `novel/create + confirm` 的正式协作路径
- 两条路径没有统一到同一个编排内核

---

## P1-2 已确认：当前测试会掩盖真实状态问题，关键断言只检查 snapshot，不检查最终展示状态

- **分类**：测试盲区
- **实际使用影响**：中
- **隐藏错误风险**：高
- **主流程阻断程度**：中
- **修复复杂度 / 置信度**：低 / 高

### Evidence
- `novel_agent/tests/test_chat_routing_execution.py:107-133`
  - `_FakeControlCoordinator.resume()` 会把状态手动改回 `writing`
  - `_FakeControlCoordinator.cancel()` 会把状态手动改成 `failed`
  - 这与真实 `NovelCoordinator` 行为不同
- `novel_agent/tests/test_chat_routing_execution.py:334-350`
  - 只断言 `status_payload["workflow"]["status"] == "completed"`
  - 没有断言 `status_payload["reply"]` 是否与之保持一致

### Why this matters
- 真实 bug 已能复现，但现有测试仍全绿
- 这意味着多 agent 主链路的可观测性回归保护不够

---

## P2-1 已确认：断点续作/复用现有文件时，未改动文件也会被记成 `updated`

- **分类**：已证实问题（观测准确性）
- **实际使用影响**：中
- **隐藏错误风险**：中
- **主流程阻断程度**：低
- **修复复杂度 / 置信度**：低 / 高

### Evidence
- `novel_agent/agents/router_agent.py:2016-2038`
  - 复用已有 `worldbuilding.json` 时直接计入 `updated_files`
- `novel_agent/agents/router_agent.py:2435-2449`
  - 复用已有章节文件时直接计入 `updated_files`
- 定向复现：
  - 返回中出现 `worldbuilding.json / outline.json / 001_第1章_旧城归来.md` 均被标为 `updated`
  - 但现有章节内容未变：`existing_chapter_mtime_preserved = True`

### Why this matters
- 会误导用户以为系统重写了已有内容
- 会污染 workflow “新增/更新”统计
- 对后续 diff、审计、问题定位不友好

---

## P2-2 优化空间：`/chat` 非流式路径在持锁状态下等待整条 router 执行链完成

- **分类**：优化建议 / 风险项
- **实际使用影响**：中
- **隐藏错误风险**：中
- **主流程阻断程度**：中
- **修复复杂度 / 置信度**：中 / 中

### Evidence
- `novel_agent/web/routes/chat.py:1584-1633`
  - `async with lock:` 内部直接 `await router_agent.route_and_respond(...)`

### Why this matters
- 长耗时多 agent 执行会占住同 session 的 chat 锁
- 虽然 `/status` 控制分支在锁前处理，但其他同 session 的交互/删除/恢复动作仍可能被放大等待

### Confidence note
- 这是基于代码路径的强风险判断，未做并发压测复现

---

## Suggested Order of Follow-up
1. **先统一 workflow 状态权威源**
   - 解决 P0-1、P0-2
2. **再统一 chat 与正式协作入口**
   - 解决 P1-1
3. **补测试回归保护**
   - 解决 P1-2
4. **最后修正观测与交互层细节**
   - 解决 P2-1、P2-2

## Net Assessment
- 多 agent 模式不是“完全不可用”，但当前已经出现**主入口路径分裂、状态源不一致、测试误报安全**这三类核心问题
- 真正的优化空间不在“再加更多 agent”，而在：
  - **统一执行内核**
  - **统一状态权威源**
  - **补上跨入口/跨状态的回归测试**
