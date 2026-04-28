# 上线前 Checklist

> 用法：上线前逐项勾选。  
> 建议按顺序执行：**配置 → 功能 → 稳定性 → 观测性 → 风险确认**

---

## A. 基础配置

- [ ] 已确认生产环境使用的 Python / 运行时版本与当前验证环境一致
- [ ] 已确认 `.env` / 全局 API 配置 / Agent 配置均存在且为生产可用值
- [ ] 已确认外部模型 API 的 `api_base`、`api_key`、`model` 正确
- [ ] 已确认输出目录、项目目录、日志目录有写权限
- [ ] 已确认生产环境网络可以访问外部模型 API
- [ ] 已确认生产环境的代理 / 防火墙 / VPN 不会阻断模型请求

---

## B. 关键功能

### B1. chat 主链路
- [ ] `/api/v1/chat` 可正常返回结果
- [ ] `/api/v1/chat/stream` 可正常返回 SSE
- [ ] `/api/v1/chat/workflow-status` 能正确反映当前状态
- [ ] `pause / resume / cancel / status` 控制命令行为正确

### B2. 创作主入口
- [ ] `chat` 自动创作已走正式协作执行链
- [ ] `/api/v1/create` 已走正式协作执行链
- [ ] `/api/v1/create` 成功/失败都能反映到统一 workflow-status
- [ ] 断点续作仍可正常工作

### B3. 项目管理
- [ ] `/api/v1/projects` 可正常列出项目
- [ ] 新建项目可成功
- [ ] 项目切换可成功
- [ ] 项目切换后运行态能正确刷新
- [ ] reset / delete / complete 不会破坏会话锁与状态

---

## C. 文件与产物

- [ ] 世界观 / 大纲 / 章节 / 合集文件能正确落盘
- [ ] workflow 中 `created_files / updated_files / reused_files` 分类正确
- [ ] 复用已有文件不会再误报为 updated
- [ ] 文件下载与文件预览接口可用
- [ ] 路径安全限制仍然有效（不会允许越权访问项目外文件）

---

## D. 稳定性与回归

- [ ] 关键回归测试已通过：
  - [ ] `novel_agent/tests/test_chat_routing_execution.py`
  - [ ] `novel_agent/tests/test_novel_route_create.py`
  - [ ] `novel_agent/tests/test_app_settings.py`
- [ ] 正式协作链相关测试已通过
- [ ] 本地性能 smoke 已通过
- [ ] 多 session 并发回归已通过
- [ ] 10 分钟本地 soak 已通过

---

## E. 可观测性

- [ ] chat / create 两条创作入口的 workflow 状态可统一观测
- [ ] 出错时 `last_error` 能被记录和展示
- [ ] `current_agent / stage / last_progress` 能正常更新
- [ ] WebSocket `/ws` 可连接
- [ ] SSE 与 WebSocket 的进度信息可以看到
- [ ] `agent.log` / 运行日志可正常写入

---

## F. 性能与压测

- [ ] session 创建 burst 测试结果可接受
- [ ] 同 session 顺序 chat 延迟可接受
- [ ] 同 session 并发 chat 延迟可接受
- [ ] 多 session 并发 chat 延迟可接受
- [ ] 多 session mixed ops 可接受
- [ ] `/api/v1/create` 正式协作链 smoke 延迟可接受

---

## G. 真实环境验证

- [ ] 本地真实服务 HTTP 联调通过
- [ ] 本地真实服务 WebSocket 联调通过
- [ ] 真实 API 环境烟雾压测已执行
- [ ] 如果真实 API 烟雾失败，已确认失败点是外部 API，而不是本地编排
- [ ] 若要上线桌面端/浏览器端，已在目标环境完成真实浏览器联调

---

## H. 已知风险确认

- [ ] 已确认当前剩余风险是否可接受
- [ ] 已确认外部 API 网络可达性是否稳定
- [ ] 已确认真实浏览器权限限制不会影响目标部署场景
- [ ] 已确认是否需要再跑更长时间的真实 API soak test

---

## I. 发布决策

### 可以上线的最低条件
- [ ] 配置正确
- [ ] 核心回归通过
- [ ] 统一 workflow 可观测性通过
- [ ] 本地真实服务 smoke + soak 通过
- [ ] 真实 API 至少完成一轮烟雾验证

### 建议上线前额外完成
- [ ] 在目标生产网络里再跑一轮真实 API 烟雾压测
- [ ] 若产品依赖浏览器前端交互，完成真实浏览器联调
- [ ] 若预计高频使用，补做更长时间的真实 API soak

---

## J. 相关报告

- 初始排查：`.omx/reports/multiagent-mode-audit-20260410T142900Z.md`
- 修复汇总：`.omx/reports/multiagent-change-summary-20260410T153520Z.md`
- 最终总报告：`.omx/reports/multiagent-final-report-20260410T174609Z.md`
- 性能 smoke：`.omx/reports/perf-chat-smoke-20260410T163638Z.md`
- 本地服务联调：`.omx/reports/e2e-local-service-smoke-20260410T170546Z.md`
- 10 分钟 soak：`.omx/reports/soak-local-service-20260410T172623Z.md`
- 真实 API 烟雾：`.omx/reports/e2e-real-api-smoke-20260410T173344Z.md`
