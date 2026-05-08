# API 文档

## 概述

本文档描述小说创作智能体系统的 REST API 接口。v1.0 版本采用模块化路由设计，所有 API 按功能分类组织。

**基础信息：**
- 基础 URL: `http://localhost:5656`
- 内容类型: `application/json`
- 字符编码: `UTF-8`

## 路由模块

### 1. 页面路由 (Pages)

**模块**: `novel_agent.web.routes.pages`

#### GET /
主页面

**响应**: HTML 页面

---

### 2. 聊天 API (Chat)

**模块**: `novel_agent.web.routes.chat`

#### POST /api/chat
发送聊天消息

**请求体**:
```json
{
  "message": "用户消息内容",
  "session_id": "会话ID（可选）"
}
```

**响应**:
```json
{
  "response": "AI 回复内容",
  "session_id": "会话ID",
  "intent": "识别的意图",
  "tools_used": ["使用的工具列表"]
}
```

#### GET /api/chat/sessions
获取聊天会话列表

**响应**:
```json
{
  "sessions": [
    {
      "session_id": "会话ID",
      "created_at": "创建时间",
      "last_active": "最后活跃时间",
      "message_count": 10
    }
  ]
}
```

#### DELETE /api/chat/sessions/{session_id}
删除聊天会话

**响应**:
```json
{
  "success": true,
  "message": "会话已删除"
}
```

---

### 3. 项目管理 API (Projects)

**模块**: `novel_agent.web.routes.projects`

#### GET /api/projects
获取项目列表

**响应**:
```json
{
  "projects": [
    {
      "id": "项目ID",
      "name": "项目名称",
      "description": "项目描述",
      "created_at": "创建时间",
      "updated_at": "更新时间"
    }
  ]
}
```

#### POST /api/projects
创建新项目

**请求体**:
```json
{
  "name": "项目名称",
  "description": "项目描述（可选）",
  "genre": "小说类型（可选）"
}
```

**响应**:
```json
{
  "success": true,
  "project_id": "新项目ID",
  "message": "项目创建成功"
}
```

#### GET /api/projects/{project_id}
获取项目详情

**响应**:
```json
{
  "id": "项目ID",
  "name": "项目名称",
  "description": "项目描述",
  "genre": "小说类型",
  "outline": "大纲内容",
  "chapters": [],
  "created_at": "创建时间",
  "updated_at": "更新时间"
}
```

#### PUT /api/projects/{project_id}
更新项目信息

**请求体**:
```json
{
  "name": "新项目名称（可选）",
  "description": "新描述（可选）",
  "genre": "新类型（可选）"
}
```

#### DELETE /api/projects/{project_id}
删除项目

**响应**:
```json
{
  "success": true,
  "message": "项目已删除"
}
```

#### POST /api/projects/{project_id}/reload
重新加载项目

**响应**:
```json
{
  "success": true,
  "message": "项目已重新加载"
}
```

---

### 4. 知识库 API (Knowledge)

**模块**: `novel_agent.web.routes.knowledge`

#### POST /api/knowledge/add
添加知识到知识库

**请求体**:
```json
{
  "content": "知识内容",
  "metadata": {
    "source": "来源",
    "type": "类型"
  }
}
```

**响应**:
```json
{
  "success": true,
  "doc_id": "文档ID",
  "message": "知识已添加"
}
```

#### POST /api/knowledge/search
搜索知识库

**请求体**:
```json
{
  "query": "搜索查询",
  "top_k": 5,
  "filters": {}
}
```

**响应**:
```json
{
  "results": [
    {
      "content": "知识内容",
      "score": 0.95,
      "metadata": {}
    }
  ]
}
```

#### DELETE /api/knowledge/{doc_id}
删除知识

**响应**:
```json
{
  "success": true,
  "message": "知识已删除"
}
```

#### GET /api/knowledge/config
获取知识库配置

**响应**:
```json
{
  "embedding_model": "模型名称",
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

#### PUT /api/knowledge/config
更新知识库配置

**请求体**:
```json
{
  "embedding_model": "新模型名称",
  "chunk_size": 1024
}
```

---

### 5. Agent 管理 API (Agents)

**模块**: `novel_agent.web.routes.agents`

#### GET /api/agents
获取可用 Agent 列表

**响应**:
```json
{
  "agents": [
    {
      "name": "outliner",
      "display_name": "大纲规划师",
      "description": "负责创建和优化小说大纲",
      "status": "active"
    }
  ]
}
```

#### POST /api/agents/{agent_name}/invoke
调用指定 Agent

**请求体**:
```json
{
  "input": "输入内容",
  "context": {}
}
```

**响应**:
```json
{
  "output": "Agent 输出",
  "metadata": {}
}
```

---

### 6. 连续写作 API (Continuous Write)

**模块**: `novel_agent.web.routes.continuous_write`

#### POST /api/continuous-write/start
开始连续写作

**请求体**:
```json
{
  "project_id": "项目ID",
  "chapter_id": "章节ID（可选）",
  "mode": "infinite",
  "config": {
    "target_words": 5000,
    "style": "descriptive"
  }
}
```

**响应**:
```json
{
  "success": true,
  "task_id": "任务ID",
  "message": "连续写作已启动"
}
```

#### GET /api/continuous-write/status/{task_id}
获取写作任务状态

**响应**:
```json
{
  "task_id": "任务ID",
  "status": "running",
  "progress": 0.45,
  "words_written": 2250,
  "estimated_time": 300
}
```

#### POST /api/continuous-write/stop/{task_id}
停止写作任务

**响应**:
```json
{
  "success": true,
  "message": "任务已停止"
}
```

---

### 7. Skill 管理 API (Skills)

**模块**: `novel_agent.web.routes.skills`

#### GET /api/skills
获取可用 Skill 列表

**响应**:
```json
{
  "skills": [
    {
      "name": "agent_reach",
      "display_name": "网络搜索",
      "description": "搜索网络信息",
      "version": "1.0.0",
      "configured": true
    }
  ]
}
```

#### POST /api/skills/{skill_name}/invoke
调用 Skill

**请求体**:
```json
{
  "action": "search",
  "params": {
    "query": "搜索内容"
  }
}
```

**响应**:
```json
{
  "success": true,
  "result": "Skill 执行结果"
}
```

#### GET /api/skills/{skill_name}/config
获取 Skill 配置

**响应**:
```json
{
  "api_key": "***",
  "enabled": true,
  "options": {}
}
```

#### PUT /api/skills/{skill_name}/config
更新 Skill 配置

**请求体**:
```json
{
  "api_key": "新的API密钥",
  "enabled": true
}
```

---

### 8. 设置 API (Settings)

**模块**: `novel_agent.web.routes.settings`

#### GET /api/settings
获取系统设置

**响应**:
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "***"
  },
  "writing": {
    "default_style": "descriptive",
    "auto_save": true
  }
}
```

#### PUT /api/settings
更新系统设置

**请求体**:
```json
{
  "llm": {
    "model": "gpt-4-turbo"
  }
}
```

**响应**:
```json
{
  "success": true,
  "message": "设置已更新"
}
```

---

### 9. 提示词管理 API (Prompts)

**模块**: `novel_agent.web.routes.prompts`

#### GET /api/prompts
获取提示词列表

**响应**:
```json
{
  "prompts": [
    {
      "id": "outliner",
      "name": "大纲规划提示词",
      "content": "提示词内容"
    }
  ]
}
```

#### GET /api/prompts/{prompt_id}
获取提示词详情

#### PUT /api/prompts/{prompt_id}
更新提示词

**请求体**:
```json
{
  "content": "新的提示词内容"
}
```

---

### 10. 辅助记忆 API (Aux Memory)

**模块**: `novel_agent.web.routes.aux_memory`

#### POST /api/aux-memory/add
添加辅助记忆

**请求体**:
```json
{
  "key": "记忆键",
  "value": "记忆内容",
  "category": "分类"
}
```

#### GET /api/aux-memory/{key}
获取辅助记忆

**响应**:
```json
{
  "key": "记忆键",
  "value": "记忆内容",
  "category": "分类",
  "created_at": "创建时间"
}
```

#### DELETE /api/aux-memory/{key}
删除辅助记忆

---

### 11. 热点趋势 API (Trends)

**模块**: `novel_agent.web.routes.trends`

#### GET /api/trends
获取热点趋势

**查询参数**:
- `platform`: 平台名称（douyin, toutiao）
- `limit`: 返回数量（默认 10）

**响应**:
```json
{
  "trends": [
    {
      "title": "热点标题",
      "url": "链接",
      "hot_value": "热度值",
      "platform": "douyin"
    }
  ]
}
```

---

### 12. Token 统计 API (Token Stats)

**模块**: `novel_agent.web.routes.token_stats`

#### GET /api/token-stats
获取 Token 使用统计

**响应**:
```json
{
  "total_tokens": 150000,
  "prompt_tokens": 100000,
  "completion_tokens": 50000,
  "cost": 0.75
}
```

---

## WebSocket API

### /ws/progress
实时进度推送

**连接**: `ws://localhost:5656/ws/progress`

**消息格式**:
```json
{
  "type": "progress",
  "task_id": "任务ID",
  "progress": 0.5,
  "message": "进度消息"
}
```

---

## 错误响应

所有 API 在出错时返回统一格式：

```json
{
  "error": "错误类型",
  "message": "错误描述",
  "details": "详细信息（可选）"
}
```

**HTTP 状态码**:
- `200`: 成功
- `400`: 请求错误
- `401`: 未授权
- `404`: 资源不存在
- `429`: 请求过于频繁
- `500`: 服务器错误

---

## 频率限制

为防止滥用，API 实施频率限制：

- 默认限制: 100 请求/分钟
- 超出限制返回 `429 Too Many Requests`

---

## 认证

当前版本暂不需要认证。未来版本将支持 API Key 认证。

---

**文档版本**: v1.0
**最后更新**: 2026-03-19
