# 更新日志

## [v1.1.0] - 2026-03-19

### 🎉 重大更新

#### 架构重构
- **模块化路由系统**：将 3744 行的单体 `app.py` 重构为 297 行，拆分为 14 个独立路由模块
- **依赖注入**：新增 `dependencies.py` 统一管理全局依赖
- **中间件系统**：引入标准化的中间件架构

#### 核心组件增强
- **协调器 (Coordinator)**：新增 848 行功能代码，增强工作流编排能力
- **路由智能体 (RouterAgent)**：新增 419 行代码，改进意图识别和工具调用
- **通信器 (Communicator)**：重构 335 行代码，优化消息处理流程

### ✨ 新增功能

#### Skill 系统
- 新增 `agent_reach` Skill：网络搜索功能
- 新增 `trends_search` Skill：热点趋势搜索
- 完整的 Skill 开发文档和示例

#### 安全增强
- 日志净化器：自动过滤敏感信息（API 密钥、密码等）
- 频率限制中间件：防止 API 滥用
- CORS 配置：更安全的跨域访问控制

#### LLM 适配器
- 支持多个国内 LLM 提供商：
  - 阿里云（通义千问）
  - 百度（文心一言）
  - DeepSeek
  - 字节跳动（豆包）
  - 讯飞星火
  - MiniMax
  - 月之暗面（Moonshot）
  - 智谱 AI

#### 辅助功能
- 辅助记忆系统 (`aux_memory.py`)
- 自动备份功能
- 资源管理器
- 原子写入工具（防止文件损坏）

### 🔄 变更

#### 破坏性变更
- **端口变更**：默认端口从 8000 改为 5656（支持自动回退）
- **MCP 移除**：MCP 功能迁移到 Skill 系统
  - 删除 `mcp_manager.py`
  - 删除 `mcp_config.json`
- **服务重命名**：`letta_service.py` → `wensi_service.py`

#### API 变更
- 路由模块化，内部实现重构（端点路径保持兼容）
- 新增多个 API 端点：
  - `/api/aux-memory/*`：辅助记忆 API
  - `/api/skills/*`：Skill 管理 API
  - `/api/backup/*`：备份管理 API
  - `/api/resources/*`：资源管理 API

### 🗑️ 移除

#### 清理工作
- 删除 11 个备份文件（`app.py.backup*`）
- 删除临时工作流文件（`.workflow/active/WFS-*`）
- 删除废弃的截图文件
- 删除版本标记文件（`0.110.0`, `4.0.0`）

#### 废弃功能
- MCP Manager（已迁移到 Skill 系统）
- Letta Service（重命名为 Wensi Service）

### 🐛 修复

- 修复热点平台 API 只返回抖音和头条
- 修复 Copilot 头部显示问题
- 修复 app-trends.js 缓存问题（更新版本号）
- 修复 Communicator 中的 MCP 调用（迁移到 Skill）

### 📝 文档

#### 新增文档
- `MIGRATION_GUIDE.md`：v1.0 → v1.1 迁移指南
- `docs/implemented/skills/MCP迁移到Skill完整方案.md`
- `docs/design/skills/Skill系统集成方案.md`
- `docs/design/skills/Agent与Skill集成方案.md`
- `docs/current/备份与资料库功能说明.md`
- `docs/implemented/skills/Skill系统扩展设计.md`
- `docs/archive/legacy/智能Agent路由与创作流程规范.md`
- `docs/design/workflow/长篇小说创作流程与Agent调用规范.md`

#### 更新文档
- `README.md`：更新端口说明和项目结构
- 多个审查报告和优化记录

### 📦 依赖更新

新增依赖：
```
# requirements.txt 中新增
chromadb  # 知识库向量存储
# 其他依赖保持不变
```

### 🧪 测试

新增测试文件：
- `test_agent_config_effective.py`
- `test_atomic_write_*.py`
- `test_aux_memory*.py`
- `test_backup_import_security.py`
- `test_content_validator.py`
- `test_continuous_writer_trends.py`
- `test_coordinator_trends.py`
- `test_core_business.py`
- `test_infinite_summary_api.py`
- `test_knowledge_routes.py`
- `test_mode_import_memory.py`
- `test_plot_thread_state_machine.py`
- `test_project_manager_reload.py`
- `test_project_state_routes.py`
- `test_router_intents.py`
- `test_session_id_security.py`
- `test_trends_routes.py`
- `test_wensi_integration.py`

删除测试文件：
- `test_letta_integration.py`（已重命名为 `test_wensi_integration.py`）

### 📊 统计

- **文件变更**：237 个文件
- **代码新增**：+47,852 行
- **代码删除**：-45,591 行
- **净变化**：+2,261 行
- **app.py 精简**：3,744 → 297 行（减少 92%）

### 🔗 相关链接

- [迁移指南](./MIGRATION_GUIDE.md)
- [GitHub 仓库](https://github.com/swyaoguai/wscz)
- [提交历史](https://github.com/swyaoguai/wscz/commit/cc0ed22)

---

## [v1.0.0] - 2026-03-18

### 初始版本

- 基础的多智能体小说创作系统
- Web UI 界面
- 知识库功能
- MCP 工具集成
- 基础的 Agent 协作

---

**版本命名规则：** 遵循 [语义化版本](https://semver.org/lang/zh-CN/)
- 主版本号：不兼容的 API 修改
- 次版本号：向下兼容的功能性新增
- 修订号：向下兼容的问题修正
