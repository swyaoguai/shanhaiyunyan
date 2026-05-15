<div align="center">
  <img src="logo.png" alt="山海·云烟 Logo" width="128" height="128">

  # 山海·云烟

  本地优先的中文 AI 小说创作工作台

  [![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
  [![License](https://img.shields.io/badge/License-Non--Commercial-red.svg)](./LICENSE)
</div>

山海·云烟是一个面向中文长篇、短篇和改编工作的 AI 写作工具。它不是云端 SaaS，而是一个可在本机运行的 FastAPI + 原生 Web 前端应用：项目、章节、资料库、会话和统计数据默认保存在本地 `data/` 目录中。

当前代码库的核心目标是把小说创作拆成可管理的工作区：项目资料、章节正文、世界观、角色档案、事件线、Copilot 对话、多 Agent 生成流程、知识库检索、短篇创作和小说转剧本工作台。

## 当前状态

- 主入口：`python run.py`
- 默认端口：`5656`，端口被占用时会自动尝试后续端口
- 前端形态：Jinja2 页面壳 + 模块化原生 JavaScript
- 后端形态：FastAPI 路由模块 + 项目本地 JSON/SQLite/向量库数据
- 主要使用场景：个人本机写作、素材整理、创作辅助和打包成 Windows 便携版
- 许可状态：源码可见，非商业使用；商业使用需要事先授权，详见 [LICENSE](./LICENSE)

注意：限制商用的许可证通常不属于 OSI 定义的“开源许可证”。本项目更准确地说是“源码可见的非商业授权项目”。

## 功能范围

### 项目与写作工作区

- 多项目管理：创建、切换、更新、删除小说项目。
- 项目资料库：内置大纲、角色档案、世界观设定、道具物品、事件线、细纲设定、章纲设定、正文摘要等分类。
- 章节管理：保存章节内容，并与项目资料、摘要和知识库同步。
- 项目状态存储：支持按项目保存工作流状态、面板状态和配置片段。
- 备份与恢复：支持项目备份导出、导入、备份列表、恢复和删除。

### Copilot 与多 Agent 创作

- 右侧 Copilot 面板支持多轮对话、流式响应、会话列表和模型快速切换。
- 支持 `@` 引用角色、章节、世界观和设定等项目资料。
- RouterAgent 会根据用户请求在聊天、创作、续写、润色、资料生成、知识查询等路径之间分流。
- NovelCoordinator 负责协调世界观构建、大纲规划、章节撰写、润色、质量评估等创作 Agent。
- 支持创作契约确认、工作流恢复、结果文件预览和下载。

### 多 Agent 生成流程

后端保留并使用以下创作角色：

- `WorldbuilderAgent`：生成或补全世界观设定。
- `OutlinerAgent`：生成主线大纲、卷纲、章节种子等结构。
- `ChapterWriterAgent`：基于上下文与项目资料生成章节。
- `PolisherAgent`：对正文进行润色和风格统一。
- `EvaluatorAgent`：评估文本质量、逻辑和一致性。
- `CharacterBuilderAgent`：生成或整理角色档案。
- `ChapterSettingBuilderAgent`：生成章纲设定。

这些能力通过 Web 路由、Copilot 路由和工作流协调器组合使用，而不是单独暴露成独立桌面程序。

### 无限续写

无限续写模块提供独立工作台，支持：

- 导入或开始续写会话。
- 按灵感、纠偏意见或当前上下文继续生成。
- 停止、恢复、同步和重新生成章节。
- 编辑生成章节，维护会话上下文。
- 标记死亡角色，避免后续误用。
- 导出 TXT、Markdown 或 DOCX。

### 短篇创作

短篇创作模块提供固定流程面板，后端接口覆盖：

- 输入材料分析。
- 融合方案生成与选择。
- 梗概生成与选择。
- 大纲生成、确认和占位修复。
- 单章或全章生成。
- 质量检查、连贯性复审和简单修复应用。
- 标题、标签生成。
- 成稿组装与 TXT、Markdown、DOCX 导出。

### 小说转剧本

小说转剧本工作台支持：

- 导入小说文本文件。
- 按整体或章节批次转换为剧本。
- 批次重转。
- 保存和恢复工作台状态。
- 导出 TXT、Markdown 或 DOCX。

### 资料库、知识库与 Wiki

项目里同时存在两类知识能力：

- 项目资料库：面向写作生产资料，保存角色、世界观、物品、事件线、细纲、章纲、正文摘要和自定义分类。
- 知识库：面向文档导入和检索，使用 ChromaDB 向量存储、SQLite 元数据和 SQLite FTS 全文检索。
- Wiki 知识中心：提供页面创建、编辑、删除、搜索、图谱、反向链接、lint、review、ingest 和从资料库迁移等接口与前端视图。

知识库嵌入配置支持：

- 硅基流动 API 嵌入模型。
- 本地 ONNX 模型包。

### 设置与模型配置

设置页包含以下实际配置面：

- 主题与背景。
- 全局 API 配置。
- 多 API 配置列表、激活配置和模型列表管理。
- 单 Agent 模型覆盖配置。
- 知识库嵌入来源配置。
- 正则规则配置。
- Skills 与热点配置。
- 备份与资料管理。
- 超时与写作相关设置。

当前主工作流支持的 API 类型包括：

- OpenAI Chat Completions 兼容接口。
- OpenAI Responses 接口。
- Anthropic Messages 接口。

模型列表可从远端 `/models` 接口获取，也可以在设置页手动维护。

### Skills 与热点

仓库包含本地 `skills/` 目录。当前默认配置会启用：

- `agent_reach`：网络搜索能力。
- `trends_search`：热点趋势搜索，面向抖音、头条等素材获取场景。

Skills 由后端扫描 `skills/<skill>/SKILL.md` 和脚本服务加载，具体是否可用取决于本地依赖和配置。

### Token、诊断与运行时

- Token 统计用于记录模型调用消耗。
- 诊断日志路由用于查看运行状态和错误信息。
- 本地运行时支持浏览器窗口心跳与关闭事件。
- 默认关闭 HTTP 请求频率限制，适合本机单用户使用；如果暴露到局域网或公网，建议在 `.env` 中启用限流并放在反向代理后。

## 快速开始

### 环境要求

- Python 3.10 或更高版本。
- Node.js 仅用于前端测试，不是运行 Web 应用的必需项。
- 至少准备一个可用的大模型 API Key，或使用兼容 OpenAI/Anthropic 协议的接口。

### 安装依赖

```bash
pip install -r requirements.txt
```

如需运行前端测试：

```bash
npm install
```

### 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

最小配置示例：

```env
OPENAI_API_KEY=你的 Key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
HOST=0.0.0.0
PORT=5656
```

也可以先启动应用，再在「设置」中新增全局 API 配置和模型列表。

### 启动应用

```bash
python run.py
```

Windows 用户也可以双击：

```text
启动山海·云烟.bat
```

启动后浏览器会尝试自动打开。如果没有自动打开，请访问终端里显示的地址，默认是：

```text
http://localhost:5656
```

## 常用命令

### 后端测试

```bash
pytest
pytest novel_agent/tests
pytest novel_agent/knowledge_base/tests
```

运行单个测试文件：

```bash
pytest novel_agent/tests/test_short_story_service.py
```

### 前端测试

```bash
npm run test:frontend
```

运行单个 Vitest 文件：

```bash
npx vitest run --pool threads --maxWorkers 1 frontend-tests/continuous-write.dom.test.js
```

### 打包 Windows 便携版

```bash
python build_portable.py
```

打包脚本会使用 PyInstaller，复制静态资源、模板、提示词、发布用干净数据副本和内置 Skills。打包前请确保已经安装 PyInstaller：

```bash
pip install pyinstaller
```

## 目录结构

```text
.
├── run.py                         # 本地开发和普通启动入口
├── build_portable.py              # Windows 便携版打包脚本
├── clean_for_release.py           # 发布前数据清理辅助脚本
├── requirements.txt               # Python 运行依赖
├── package.json                   # 前端测试依赖和脚本
├── novel_agent/
│   ├── agents/                    # 创作 Agent、Router、LLM 客户端、消息总线
│   ├── workflow/                  # 协调器、创作工作流、任务池、运行状态
│   ├── web/
│   │   ├── app.py                 # FastAPI 应用工厂
│   │   ├── routes/                # 页面、创作、聊天、设置、知识库等路由
│   │   ├── api/                   # 备份和资源管理 API
│   │   ├── static/                # 原生 JS/CSS 前端模块
│   │   └── templates/             # Jinja2 页面模板
│   ├── knowledge_base/            # 向量检索、全文检索、元数据和混合检索
│   ├── wiki/                      # Wiki 页面、图谱、检索、lint、review、迁移
│   ├── prompts/                   # 内置提示词与 PromptManager
│   ├── context/                   # 上下文、角色、世界观管理
│   ├── utils/                     # 原子写入、指标、Token 统计等工具
│   └── models/embedding/default/  # 可选本地 ONNX 嵌入模型目录
├── skills/                        # 本地 Skill 插件目录
├── frontend-tests/                # Vitest + jsdom 前端测试
├── docs/                          # 当前文档、设计文档、报告和归档
└── data/                          # 默认本地运行数据，已被 .gitignore 忽略
```

## 数据与隐私

- 默认数据目录是仓库根目录下的 `data/`。
- 多项目元数据存放在 `data/projects.json`。
- 单个项目内容存放在 `data/projects/<project_id>/`。
- 知识库、统计、会话、备份等也会写入本地数据目录。
- `.env`、`data/`、日志和构建产物不应提交到公开仓库。

本项目没有内置多用户认证系统，默认面向本机单用户使用。不要直接把服务暴露到公网；如果确实需要远程访问，请自行增加认证、HTTPS、反向代理、访问控制和备份策略。

## 开发说明

- 后端使用 FastAPI，路由注册在 `novel_agent/web/routes/__init__.py`。
- 前端不是 React/Vue，而是由 `index.html` 按顺序加载的原生 JS 模块。
- `app-core.js` 维护全局状态、模块切换和主初始化流程。
- 设置、资料库、Copilot、无限续写、短篇、小说转剧本、Wiki 都有各自的前端模块。
- 重要数据写入应优先使用项目内的原子写入工具，避免 JSON 文件损坏。
- 修改设置、项目资料或写作流程时，要同时关注后端路由、前端模块和已有测试。

## 许可

本项目采用自定义非商业源码许可：

- 允许个人学习、研究、评估和非商业创作使用。
- 禁止未经授权的商业使用、商业部署、商业集成、SaaS 化提供或销售。
- 如需商业使用，请先联系项目维护者取得书面授权。
- 第三方依赖、图标、模型文件和外部服务仍受其各自许可证或服务条款约束。

完整条款见 [LICENSE](./LICENSE)。
