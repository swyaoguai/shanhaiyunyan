# Multi-Agent 修复与后续风险汇总

## 本轮已完成修复

### 1. workflow 状态源统一
- 修复 `/chat/workflow-status` 混用 session snapshot 与全局 coordinator 状态的问题
- 现在优先展示 session 级 workflow snapshot，再补充 coordinator 的章节/项目统计

**主要文件**
- `novel_agent/web/routes/chat.py`

---

### 2. coordinator 暂停 / 恢复 / 取消状态一致性
- 修复 `pause/resume/cancel` 后 `workflow_state/checkpoint` 卡死在 `paused` 的问题
- 增加 `_last_active_workflow_state`
- `get_project_status()` 对外能正确暴露 `writing / paused / cancelled`

**主要文件**
- `novel_agent/workflow/coordinator.py`

---

### 3. chat 自动创作入口接入正式协作执行链
- 当 coordinator 支持正式协作执行且不是断点续作时：
  - chat 自动创作会进入 `task_pool + collab_execution_trace`
  - 不再只走轻量直写路径
- 断点续作仍保留旧路径，避免回归

**主要文件**
- `novel_agent/agents/router_agent.py`

---

### 4. 测试盲区补强
- 新增真实 `NovelCoordinator` 行为测试
- 新增 `/chat/workflow-status` 文案与结构化状态一致性测试
- 新增 chat 正式任务池路径测试

**主要文件**
- `novel_agent/tests/test_chat_routing_execution.py`

---

### 5. 复用文件状态误报修复
- 复用已有世界观 / 大纲 / 章节时，不再记为 `updated`
- 新增 `reused_files`
- workflow 状态文案新增“复用 N 项”

**主要文件**
- `novel_agent/agents/router_agent.py`
- `novel_agent/web/routes/chat.py`

---

### 6. 非流式 chat 长耗时锁占用优化
- `/chat` 在进入 `router_agent.route_and_respond(...)` 前释放 session lock
- 路由完成后重新加锁写会话历史与持久化
- 避免整条多 agent 执行链长期占用锁

**主要文件**
- `novel_agent/web/routes/chat.py`
- `novel_agent/tests/test_chat_routing_execution.py`

---

### 7. 控制命令状态判断补修
- `_handle_workflow_control()` 现在基于 coordinator 对外真实状态判断，而不是直接读裸 `workflow_state`
- 修复“已取消但仍能被当作 writing 再次 pause”的问题

**主要文件**
- `novel_agent/web/routes/chat.py`
- `novel_agent/tests/test_chat_routing_execution.py`

---

## 当前回归结果

- `python -m pytest novel_agent/tests/test_chat_routing_execution.py -q`
  - ✅ `38 passed`
- `python -m pytest novel_agent/tests/test_app_settings.py -q`
  - ✅ `9 passed`
- `python -m pytest novel_agent/tests/test_supervised_collab_foundation.py -k "initialize_task_pool_from_contract_persists_state or execute_project_ready_tasks_runs_world_and_outline_in_formal_task_pool or execute_project_ready_tasks_runs_first_write_chapter_in_formal_task_pool" -q`
  - ✅ `3 passed`

---

## 继续深挖后发现的剩余潜在问题

### R1. `/novel/create` 入口仍然保留旧的直接执行链，和 chat 正式协作链再次分叉

**级别**
- 中高风险 / 架构一致性问题

**证据**
- `novel_agent/web/routes/novel.py:92-118`
  - `/create` 仍直接调用 `coordinator.create_novel(...)`
- `novel_agent/web/routes/novel.py:197-240`
  - `/contract/confirm` 才会初始化 `task_pool` 并执行 `execute_project_ready_tasks(...)`
- `novel_agent/agents/router_agent.py`
  - chat 自动创作入口已经优先走正式 task pool

**影响**
- 现在至少还有两套创作主路径：
  1. chat 自动创作 → 正式 task pool
  2. `/novel/create` → 旧 `create_novel` 直连路径
- 会继续带来：
  - 状态模型不一致
  - trace / task_pool 覆盖不一致
  - 测试覆盖与实际行为分叉

**建议**
- 最终统一到单一创作编排内核

---

### R2. `chat_stream` 在流式结束后保存会话时，没有重新进入 session lock，存在并发复活已删除 session 的风险

**级别**
- 中风险 / 并发一致性风险

**证据**
- `novel_agent/web/routes/chat.py:1787-1804`
  - 流式前只在锁内做准备
- `novel_agent/web/routes/chat.py:1943-1973`
  - 流结束后直接 `store.save(...)`
  - 没有重新拿 lock，也没有确认 session 仍存在
- 对照非流式 `/chat`
  - 已优化为路由后重新加锁，再决定是否持久化

**潜在后果**
- 如果流式任务执行期间用户触发 `/chat/reset` 或删除会话：
  - 旧流结束后可能把会话重新写回磁盘

**建议**
- 参照非流式路径，把流式结束后的持久化也放回锁内，并检查 session 是否仍有效

---

### R3. 正式 task pool 在 chat 自动创作路径中默认尝试“一次跑完整部作品”，长书场景可能导致单请求过重

**级别**
- 中风险 / 可扩展性风险

**证据**
- `novel_agent/agents/router_agent.py:1529-1537`
  - `max_tasks` 直接取 task 总数
  - `max_chapter_tasks` 直接按 `volume_count * chapters_per_volume`

**潜在后果**
- 章节数很大时，单次 chat 请求可能变得过长
- 不利于：
  - 中断恢复
  - 前端超时控制
  - 分阶段用户确认

**建议**
- 后续考虑把 chat 自动创作改成“首批任务 + 续跑”模式，而不是默认整本直跑

---

## 建议的下一优先级
1. **R1** 统一 `/novel/create` 与 chat 创作入口
2. **R2** 修复 `chat_stream` 的流结束持久化并发风险
3. **R3** 控制 task pool 单次执行批量，降低超长请求风险

---

## 后续修复进展（本次继续推进）

### 已解决：R1 `/novel/create` 与 chat 创作入口分叉
- `/novel/create` 现在优先复用 Router 的正式协作执行链
- 会进入正式 `task_pool + collab_execution_trace`
- 已新增回归测试：`novel_agent/tests/test_novel_route_create.py`

### 已解决：R2 `chat_stream` 流结束后可能重存已 reset session
- 流式路由与普通流式路径现在都改为：
  - 流结束后重新进 lock
  - 仅当 session 仍处于 active 状态时才持久化
- 已新增回归测试覆盖 reset 后不应重存

### 当前主要剩余问题
- 暂未发现新的高优先级剩余问题；后续更适合转入扩展性与压力测试

### 已解决：R3 chat / formal task pool 默认一次跑完整本
- Router 正式协作执行链现在改为保守批量策略：
  - `max_tasks <= 4`
  - `max_chapter_tasks <= 2`
- 这样长书场景不再默认在单次请求里跑完整本
- 已补回归测试验证大项目会被限流到首批任务

### 深挖顺手修复：session lock 映射删除导致潜在 split-lock 并发风险
- `reset/delete/complete` 之前会直接 `pop` `_chat_session_locks`
- 在途请求后续重新取锁时，可能重新生成新锁，造成同 session 出现两把锁
- 现已改为：
  - 清理 session / workflow
  - **不再删除 lock 实例**
- 已补测试验证 reset/delete 后同一 session 复取锁仍是同一把锁

### 压力与并发回归补充
- 已新增并发/压力方向回归测试：
  - 同 session 并发 chat 仅初始化一次 agent
  - burst 创建 chat session 时 session_id 保持唯一
- 当前结论：
  - 暂未发现新的高优先级并发缺陷
  - 更深入的下一步应转向真实性能压测（请求时延、长任务吞吐、真实前端并发）

### 已补充：本地性能烟雾压测脚本
- 新增脚本：`novel_agent/tests/perf_chat_smoke.py`
- 自动产出：
  - `.omx/reports/perf-chat-smoke-*.json`
  - `.omx/reports/perf-chat-smoke-*.md`
- 当前压测覆盖：
  - burst session 创建
  - 同 session 顺序 chat
  - 同 session 并发 chat
  - `/novel/create` 正式协作链烟雾耗时

### 已补充：近端到端本地服务联调烟雾脚本
- 新增脚本：`novel_agent/tests/e2e_local_service_smoke.py`
- 自动产出：
  - `.omx/reports/e2e-local-service-smoke-*.json`
  - `.omx/reports/e2e-local-service-smoke-*.md`
- 覆盖：
  - 根页面 `/`
  - `/api/v1/status`
  - `/api/v1/projects`
  - `/api/v1/chat/sessions`
  - `/api/v1/chat/history`
  - `/api/v1/chat/workflow-status`
  - `/api/v1/chat/reset`
  - `/ws` WebSocket connected 首包
- 说明：
  - 当前沙箱里真实浏览器自动化被系统权限阻断，因此先用“真实服务 + HTTP + WebSocket”的近端到端方案替代

### 已补充：10 分钟本地真实服务 soak test
- 新增脚本：`novel_agent/tests/soak_local_service.py`
- 自动产出：
  - `.omx/reports/soak-local-service-*.json`
  - `.omx/reports/soak-local-service-*.md`
- 当前 600s 结果：
  - `status`: 594 次，0 失败
  - `projects`: 594 次，0 失败
  - `chat_sessions_list/create/history/workflow-status/reset`: 各 2308 次，0 失败
  - `websocket_connect`: 298 次，0 失败
- 结论：
  - 本地真实服务在 10 分钟持续 HTTP + WebSocket 混合压测下未出现高优先级稳定性问题

### 已补充：真实 API 环境端到端烟雾脚本
- 新增脚本：`novel_agent/tests/e2e_real_api_create_smoke.py`
- 自动产出：
  - `.omx/reports/e2e-real-api-smoke-*.json`
  - `.omx/reports/e2e-real-api-smoke-*.md`
- 覆盖：
  - 多项目创建与切换
  - WebSocket 订阅 `novel_progress`
  - `/api/v1/create` 最小创作链 SSE
  - `/api/v1/chat/workflow-status` 收尾状态观察
- 本次真实环境结果：
  - 请求已进入真实创作链
  - SSE 与 WebSocket 均收到真实阶段消息
  - 失败点在外部 API 网络连接：`https://ai-proxy-gateway-0zq8tap5.replit.app/v1`
- 顺带暴露的观察项：
  - `/api/v1/create` 的失败并不会反映到 `/api/v1/chat/workflow-status`
  - 若后续要统一可观测性，建议把 `/create` 路径也纳入统一 workflow snapshot 体系
