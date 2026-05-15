# 山海·云烟

一个本地运行的中文 AI 小说创作工作台。

它把“写小说”拆成几个真实可操作的工作区：项目、章节、资料库、Copilot、多 Agent 创作、无限续写、短篇创作、小说转剧本、知识库和 Wiki。应用默认跑在本机，数据默认写入仓库根目录下的 `data/`。

> 许可说明：本项目不是 MIT，也不是 OSI 意义上的开源项目。源码可见，允许非商业使用；商业使用、商业部署、SaaS 化、集成到收费产品或给客户交付，均需要事先取得书面授权。详见 [LICENSE](./LICENSE)。

## 现在它能做什么

### 写作项目

- 创建和切换多个小说项目。
- 管理章节、角色档案、世界观设定、物品、事件线、细纲、章纲和正文摘要。
- 将项目资料保存为本地 JSON 数据。
- 导入小说、导出备份、恢复备份。

### Copilot

- 在右侧面板和写作助手对话。
- 支持流式回复、会话列表、模型切换。
- 支持 `@` 引用角色、章节、世界观、设定等项目资料。
- 可以让助手整理资料、续写、润色、生成角色或进入创作流程。

### 多 Agent 创作

当前代码里实际存在并参与流程的创作角色包括：

- `WorldbuilderAgent`：世界观构建。
- `OutlinerAgent`：大纲规划。
- `ChapterWriterAgent`：章节撰写。
- `PolisherAgent`：文本润色。
- `EvaluatorAgent`：质量评估。
- `CharacterBuilderAgent`：角色档案生成。
- `ChapterSettingBuilderAgent`：章纲设定生成。
- `RouterAgent`：识别用户意图并把请求分发到对应流程。
- `NovelCoordinator`：协调创作状态、检查点、上下文和各 Agent。

这些能力主要通过 Web UI、Copilot 和 FastAPI 路由组合使用。

### 无限续写

- 新建或导入续写会话。
- 基于当前上下文继续生成章节。
- 用灵感、纠偏意见影响后续创作。
- 停止、恢复、同步、重写章节。
- 编辑章节内容。
- 标记死亡角色，减少后续误用。
- 导出 TXT、Markdown、DOCX。

### 短篇创作

短篇模块是一个独立流程，不是简单聊天框。它包含：

- 输入材料分析。
- 融合方案生成和选择。
- 梗概生成和选择。
- 大纲生成、确认、占位修复。
- 单章或全章生成。
- 质量检查、连贯性复审、简单修复。
- 标题和标签生成。
- 成稿组装与导出。

### 小说转剧本

- 上传或导入小说文本。
- 整体转换或按章节批次转换。
- 对失败或不满意的批次重新转换。
- 保存工作台状态。
- 导出 TXT、Markdown、DOCX。

### 资料库、知识库、Wiki

这三个概念在项目里不是同一个东西：

- 资料库：写作生产资料，如角色、世界观、事件线、章纲等。
- 知识库：文档导入、分块、向量检索、全文检索和章节索引。
- Wiki：页面化知识中心，支持页面、搜索、图谱、反向链接、lint、review 和 ingest。

知识库嵌入支持两种来源：

- 硅基流动 API 嵌入模型。
- 本地 ONNX 嵌入模型包。

### 设置

设置页目前包含：

- 主题和背景。
- 全局 API 配置。
- 多 API 配置和模型列表。
- 单 Agent 模型覆盖。
- 知识库嵌入来源。
- 正则替换规则。
- Skills 和热点配置。
- 备份、资源和写作相关配置。

主流程支持的模型接口类型：

- OpenAI Chat Completions 兼容接口。
- OpenAI Responses 接口。
- Anthropic Messages 接口。

## 它不是什么

- 它不是云服务，不提供多租户账号系统。
- 它不是已经加固好的公网服务。
- 它不是无需配置 API Key 的离线大模型应用。
- 它不是纯前端项目，必须运行 Python 后端。
- 它不是 MIT/Apache 这类宽松开源授权项目。

如果要部署给多人或开放到公网，需要自行补认证、HTTPS、权限、反向代理、备份和安全审计。

## 快速运行

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 准备配置文件

```bash
cp .env.example .env
```

PowerShell：

```powershell
Copy-Item .env.example .env
```

最小配置：

```env
OPENAI_API_KEY=你的 Key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
HOST=0.0.0.0
PORT=5656
```

也可以先启动应用，再进入「设置」添加 API 配置。

### 3. 启动

```bash
python run.py
```

Windows 也可以双击：

```text
启动山海·云烟.bat
```

默认访问：

```text
http://localhost:5656
```

如果 `5656` 被占用，启动脚本会自动尝试后续端口，以终端显示的地址为准。

## 常用命令

后端测试：

```bash
pytest
pytest novel_agent/tests
pytest novel_agent/knowledge_base/tests
```

前端测试：

```bash
npm install
npm run test:frontend
```

打包 Windows 便携版：

```bash
pip install pyinstaller
python build_portable.py
```

## 代码入口

```text
run.py
  启动入口。加载 .env，检查数据目录权限，寻找可用端口，启动 Uvicorn。

novel_agent/web/app.py
  FastAPI 应用工厂。注册中间件、静态资源、模板、生命周期和路由。

novel_agent/web/routes/
  Web API 路由。包含创作、聊天、设置、项目、知识库、Wiki、短篇、小说转剧本等模块。

novel_agent/web/templates/index.html
  主页面壳。按顺序加载前端静态脚本。

novel_agent/web/static/
  原生 JavaScript 前端模块。没有 React/Vue。

novel_agent/workflow/coordinator.py
  多 Agent 创作协调器。

novel_agent/agents/router_agent.py
  Copilot 请求和创作请求的意图路由。

novel_agent/project_manager.py
  多项目与项目数据文件管理。

novel_agent/knowledge_base/
  向量检索、全文检索、元数据和混合检索。

novel_agent/wiki/
  Wiki 页面存储、图谱、检索、lint、review 和迁移。
```

## 目录速览

```text
.
├── run.py
├── build_portable.py
├── clean_for_release.py
├── requirements.txt
├── package.json
├── novel_agent/
│   ├── agents/
│   ├── workflow/
│   ├── web/
│   ├── knowledge_base/
│   ├── wiki/
│   ├── prompts/
│   ├── context/
│   └── utils/
├── skills/
├── frontend-tests/
├── docs/
└── data/
```

## 本地数据

默认数据位置：

```text
data/
├── projects.json
├── projects/<project_id>/
├── stats/
├── sessions/
└── logs/
```

这些数据包含你的项目内容、会话、统计和日志，默认被 `.gitignore` 忽略。公开仓库前不要提交 `.env`、`data/`、日志、构建产物或私人项目素材。

## Skills

仓库包含本地 `skills/` 目录。当前默认配置涉及：

- `agent_reach`：网络搜索。
- `trends_search`：热点趋势搜索。

Skills 会由后端扫描 `skills/<skill>/SKILL.md` 和脚本服务加载。是否可用取决于本地配置和依赖。

## 打包说明

`build_portable.py` 会：

- 准备干净的发布数据副本。
- 使用 PyInstaller 打包 `run.py`。
- 打包静态资源、模板、提示词和 Skills。
- 使用 `logo.ico` 作为 Windows 图标。
- 生成便携版目录和压缩包。

打包脚本不会把你的开发环境 `data/` 直接塞进发布包。

## 贡献前先知道

- 前端脚本加载顺序很重要，见 `novel_agent/web/templates/index.html`。
- 修改设置功能时通常要同时看 `web/routes/settings.py` 和 `web/static/settings/*`。
- 修改项目资料库时通常要同时看 `web/routes/projects.py`、`library_service` 和 `web/static/app-knowledge.js`。
- 修改创作流程时通常要同时看 `RouterAgent`、`NovelCoordinator`、`workflow/` 和相关测试。
- 写入 JSON 时优先使用项目内原子写入工具，避免运行中损坏数据。

## 许可与商用

本项目使用自定义非商业源码许可，完整条款见 [LICENSE](./LICENSE)。

简单说：

- 可以个人学习、研究、评估、非商业创作。
- 可以为非商业目的复制、修改和分发，但必须保留许可证和署名。
- 不可以未经授权用于商业部署、商业集成、SaaS、客户项目、付费内容生产服务或打包售卖。
- 商业使用请先取得书面授权。

第三方依赖、图标、字体、模型文件和外部 API 服务仍受其各自条款约束。
