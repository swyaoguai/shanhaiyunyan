# 迁移指南：v1.0 → v1.1

## 概述

v1.1 版本进行了大规模架构重构，将单体应用转变为模块化架构。本指南帮助您从 v1.0 平滑迁移到 v1.1。

## 破坏性变更

### 1. 默认端口变更

**变更内容：**
- 旧版本：默认端口 `8000`
- 新版本：默认端口 `5656`（支持自动回退）

**影响范围：**
- 现有部署配置
- 反向代理配置（Nginx、Apache 等）
- 防火墙规则
- 客户端连接地址

**迁移方案：**

**方案 1：使用新端口（推荐）**
```bash
# 直接使用新端口
python run.py
# 访问 http://localhost:5656
```

**方案 2：保持旧端口**
```bash
# 通过环境变量指定端口
export PORT=8000
python run.py
```

或在代码中修改：
```python
# run.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # 指定端口
```

### 2. MCP 功能迁移到 Skill 系统

**变更内容：**
- 移除：`novel_agent/utils/mcp_manager.py`
- 移除：`mcp_config.json`
- 新增：Skill 系统（`skills/` 目录）

**影响范围：**
- 使用 MCP 工具调用的代码
- MCP 配置文件

**迁移方案：**

**旧代码（MCP）：**
```python
from novel_agent.utils.mcp_manager import mcp_manager

# 调用 MCP 工具
result = await mcp_manager.call_tool("server_name", "tool_name", args)
```

**新代码（Skill）：**
```python
from novel_agent.agents.communicator import Communicator

# 使用 Skill 系统
communicator = Communicator()
result = await communicator.call_skill("skill_name", args)
```

**可用的 Skill：**
- `agent_reach`：网络搜索功能（替代 MCP 搜索工具）
- `trends_search`：热点趋势搜索（替代 MCP 趋势工具）

**配置迁移：**
```bash
# 1. 查看可用 Skill
ls skills/

# 2. 配置 Skill（以 trends_search 为例）
cd skills/trends_search
cp config.example.json config.json
# 编辑 config.json 填入 API 密钥

# 3. 安装依赖
pip install -r requirements.txt
```

### 3. 服务重命名：Letta → Wensi

**变更内容：**
- 旧文件：`novel_agent/letta_service.py`
- 新文件：`novel_agent/wensi_service.py`

**影响范围：**
- 导入 Letta 服务的代码

**迁移方案：**

**旧代码：**
```python
from novel_agent.letta_service import LettaService

service = LettaService()
```

**新代码：**
```python
from novel_agent.wensi_service import WensiService

service = WensiService()
```

### 4. API 路由结构调整

**变更内容：**
- 路由从单体 `app.py` 拆分到 `novel_agent/web/routes/` 模块

**影响范围：**
- 直接导入路由函数的代码
- API 端点路径（大部分保持兼容）

**迁移方案：**

API 端点路径基本保持不变，但内部实现已模块化：

```
旧结构：app.py（3744 行）
新结构：
  ├── routes/agents.py      # Agent 相关 API
  ├── routes/chat.py        # 聊天 API
  ├── routes/knowledge.py   # 知识库 API
  ├── routes/projects.py    # 项目管理 API
  ├── routes/settings.py    # 设置 API
  └── ...
```

**如果您直接导入了路由函数：**
```python
# 旧代码
from novel_agent.web.app import some_route_function

# 新代码
from novel_agent.web.routes.chat import some_route_function
```

## 新增功能

### 1. 模块化路由系统

路由现在按功能模块组织，便于维护和扩展：

```
novel_agent/web/routes/
├── __init__.py           # 路由注册
├── agents.py             # Agent 管理
├── aux_memory.py         # 辅助记忆
├── chat.py               # 聊天交互
├── continuous_write.py   # 连续写作
├── knowledge.py          # 知识库
├── novel.py              # 小说管理
├── pages.py              # 页面路由
├── projects.py           # 项目管理
├── prompts.py            # 提示词管理
├── settings.py           # 设置
├── skills.py             # Skill 管理
├── token_stats.py        # Token 统计
└── trends.py             # 热点趋势
```

### 2. 增强的安全特性

- **日志净化**：自动过滤敏感信息（API 密钥、密码等）
- **频率限制**：防止 API 滥用
- **CORS 配置**：更安全的跨域访问控制

### 3. 依赖注入系统

新增 `dependencies.py` 模块，统一管理全局依赖：

```python
from novel_agent.web.dependencies import get_coordinator, get_router_agent

# 在路由中使用
@router.get("/status")
async def get_status(coordinator = Depends(get_coordinator)):
    return coordinator.get_status()
```

### 4. 中间件系统

新增中间件支持：

```
novel_agent/web/middleware/
├── __init__.py
└── rate_limit.py         # 频率限制中间件
```

## 配置更新

### 环境变量

新增环境变量支持：

```bash
# .env 文件
PORT=5656                    # 服务端口
LOG_LEVEL=INFO              # 日志级别
ENABLE_CORS=true            # 启用 CORS
RATE_LIMIT_ENABLED=true     # 启用频率限制
```

### 配置文件

知识库配置路径保持不变：
```
novel_agent/data/knowledge_base_config.json
```

## 升级步骤

### 1. 备份数据

```bash
# 备份项目数据
cp -r projects/ projects_backup/
cp -r novel_agent/data/ data_backup/
```

### 2. 更新代码

```bash
# 拉取最新代码
git pull origin master

# 或下载最新版本
# 解压并替换文件
```

### 3. 更新依赖

```bash
# 安装新依赖
pip install -r requirements.txt
```

### 4. 迁移配置

```bash
# 如果使用了 MCP，迁移到 Skill
# 1. 查看 skills/ 目录下的可用 Skill
# 2. 复制配置模板并填写
cd skills/trends_search
cp config.example.json config.json
# 编辑 config.json
```

### 5. 更新部署配置

如果使用反向代理，更新端口配置：

**Nginx 示例：**
```nginx
# 旧配置
location / {
    proxy_pass http://localhost:8000;
}

# 新配置
location / {
    proxy_pass http://localhost:5656;
}
```

### 6. 测试运行

```bash
# 启动服务
python run.py

# 检查日志确认启动成功
# 访问 http://localhost:5656
```

### 7. 验证功能

- [ ] 登录系统
- [ ] 创建/打开项目
- [ ] 测试聊天功能
- [ ] 测试知识库功能
- [ ] 测试连续写作功能
- [ ] 测试 Skill 调用（如果使用）

## 常见问题

### Q1: 启动后提示端口被占用

**A:** 系统会自动尝试其他端口。查看控制台输出的实际端口号：
```
INFO: 端口 5656 被占用，尝试端口 5657
INFO: Application startup complete
INFO: Uvicorn running on http://0.0.0.0:5657
```

### Q2: MCP 工具无法使用

**A:** MCP 已迁移到 Skill 系统。请按照上述"MCP 功能迁移"部分进行迁移。

### Q3: 导入错误：找不到模块

**A:** 检查导入路径是否更新：
```python
# 错误
from novel_agent.letta_service import LettaService

# 正确
from novel_agent.wensi_service import WensiService
```

### Q4: API 请求返回 404

**A:** 检查端口是否正确。新版本默认端口为 5656。

### Q5: 知识库功能异常

**A:** 确认 ChromaDB 已安装：
```bash
pip install chromadb
```

## 回滚方案

如果遇到无法解决的问题，可以回滚到 v1.0：

```bash
# 1. 恢复代码
git checkout 7669c2a  # v1.0 最后一个提交

# 2. 恢复数据（如果有备份）
rm -rf projects/
cp -r projects_backup/ projects/

# 3. 重新安装依赖
pip install -r requirements.txt

# 4. 启动服务
python run.py
```

## 获取帮助

如果遇到问题：

1. 查看日志文件：`logs/` 目录
2. 查看启动错误：`startup_error.txt`
3. 提交 Issue：[GitHub Issues](https://github.com/swyaoguai/wscz/issues)
4. 查看文档：`docs/` 目录

## 更新日志

详细的更新内容请查看：
- [更新说明.md](./更新说明.md)
- [Git 提交历史](https://github.com/swyaoguai/wscz/commits/master)

---

**最后更新：** 2026-03-19
**适用版本：** v1.0 → v1.1
