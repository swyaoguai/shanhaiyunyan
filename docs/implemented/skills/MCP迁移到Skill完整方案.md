# MCP 迁移到 Skill 完整方案

## 迁移目标

一次性将所有 MCP 功能迁移到 Skill 系统，完全移除 MCP 依赖。

## 迁移步骤

### 1. 创建替代 Skills

#### Skill 1: trends-search（热点搜索）
替代 trends-hub MCP 服务，提供：
- 微博热搜
- 今日头条
- 知乎热榜
- 抖音热点
- 百度热搜

#### Skill 2: web-search（网络搜索）
替代 web-search MCP 服务，提供：
- 网络搜索
- 内容查询

### 2. 修改受影响的文件

#### 需要删除的文件
- `novel_agent/utils/mcp_manager.py`

#### 需要修改的文件
1. `novel_agent/agents/base_agent.py`
   - 删除 `use_mcp_tool()` 方法
   - 删除 `get_available_mcp_tools()` 方法
   - 添加 `use_skill()` 方法

2. `novel_agent/agents/communicator.py`
   - 将 MCP 调用改为 Skill 调用
   - 删除 MCP_TOOL_NAMES 映射

3. `novel_agent/agents/continuous_writer.py`
   - 将 MCP 调用改为 Skill 调用

4. `novel_agent/agents/router_agent.py`
   - 将 MCP_TOOLS 改为 SKILLS
   - 修改工具调用逻辑

5. `novel_agent/workflow/coordinator.py`
   - 将 MCP 调用改为 Skill 调用

6. `novel_agent/web/routes/trends.py`
   - 将 MCP 调用改为 Skill 调用
   - 修改健康检查逻辑

7. `novel_agent/web/routes/projects.py`
   - 删除 mcp_config 相关代码

8. `novel_agent/__init__.py`
   - 更新文档说明

#### 需要修改的测试文件
- `novel_agent/tests/test_continuous_writer_trends.py`
- `novel_agent/tests/test_coordinator_trends.py`
- `novel_agent/tests/test_trends_routes.py`
- `novel_agent/tests/test_backup_import_security.py`

### 3. 新的架构

```
用户请求
    ↓
Agent 检测需要的功能
    ↓
调用对应的 Skill
    ↓
Skill 内部处理（可能调用 MCP，但对外透明）
    ↓
返回结果
```

### 4. 迁移后的优势

- ✅ 无需全局 MCP 配置
- ✅ 功能模块化，易于管理
- ✅ 可以独立启用/禁用功能
- ✅ 更容易测试和维护
- ✅ 打包更轻量

## 实施计划

1. 创建 trends-search Skill
2. 创建 web-search Skill（可选）
3. 修改所有 Agent 使用 Skill
4. 删除 mcp_manager.py
5. 更新测试
6. 验证功能

## 注意事项

- Skill 内部可以继续使用 MCP（如果需要），但对外完全透明
- 用户只需要启用 Skill，不需要配置 MCP
- 所有功能保持不变，只是调用方式改变