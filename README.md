# 山海·云烟 — 智能小说创作系统

<img src="./logo.png" alt="山海·云烟应用图标" width="96">

> 本地优先的中文 AI 小说创作工作台 | Local-first AI writing studio for Chinese fiction

**山海·云烟** 是一款面向中文小说创作者的本地 AI 写作应用。它把项目资料、章节正文、创作助手、多 Agent 流程、无限续写、短篇创作、小说转剧本、知识库与 Wiki 整合在同一个工作台中，适合用来管理长篇创作的设定、上下文和持续写作流程。

本仓库提供的是本地应用源码与 Windows 打包脚本。默认不提供云端账号、多用户权限、在线托管服务，也不面向公网部署。

📦 **下载发布版**：[GitHub Releases](https://github.com/swyaoguai/shanghaiyunyan/releases/latest)

---

## 为什么做这个项目

小说创作不是只让模型吐出一段正文。真正麻烦的地方往往在更长的链条里：角色有没有走样，世界观有没有前后矛盾，章节有没有接住前文，临时灵感能不能落到资料库，写到中段时还能不能快速找回那些细小但重要的设定。

山海·云烟希望解决的就是这一类问题：让 AI 不只是“回答问题”，而是进入一个有项目、有资料、有上下文、有检查点的创作环境。作者仍然掌握故事方向，工具负责整理资料、衔接流程、调用模型、检索设定和保存结果。

---

## 核心功能

### 项目资料管理

- 多项目管理，每个项目拥有独立数据目录
- 管理大纲、角色档案、世界观设定、道具物品、事件线、细纲设定、章纲设定、正文摘要和自定义资料
- 项目资料默认保存在本地 `data/projects/<project_id>/`
- 支持项目数据导入、导出、备份和恢复

### Copilot 创作助手

- 右侧 Copilot 面板支持多轮对话和流式输出
- 支持会话管理、快速切换模型、恢复历史会话
- 支持用 `@` 引用项目中的角色、章节和设定
- 可将合适的创作结果同步回资料库或章节内容
- 智能判断模式会根据用户意图选择聊天、资料生成、续写、润色或创作流程

### 本地多 Agent 创作流程

系统采用 Router + Coordinator + Worker 的本地多 Agent 架构：

- `RouterAgent`：判断用户意图并分流到对应能力
- `NovelCoordinator`：管理创作状态、检查点、上下文和任务执行
- `WorldbuilderAgent`：生成世界观
- `OutlinerAgent`：生成大纲和结构
- `ChapterWriterAgent`：撰写章节
- `PolisherAgent`：润色文本
- `EvaluatorAgent`：评估质量与一致性
- `CharacterBuilderAgent`：生成角色档案
- `ChapterSettingBuilderAgent`：生成章纲

### 无限续写

- 新建或导入续写会话
- 根据上下文继续写作
- 按灵感或纠偏意见调整方向
- 支持重写、编辑、同步章节
- 支持死亡角色标记，降低连续写作中的设定冲突
- 支持导出 TXT、Markdown、DOCX

### 短篇创作

短篇创作是分步骤工作流，而不是单次提示词：

- 分析输入材料
- 生成融合方案
- 生成梗概
- 生成大纲
- 生成章节
- 做质量检查和连贯性复审
- 生成标题与标签
- 组装并导出成稿

### 小说转剧本

- 导入小说文本
- 按整体或章节批次转换
- 对不满意的批次重新转换
- 导出 TXT、Markdown、DOCX

### 小说封面生成

- 根据项目资料和自定义元素生成封面提示词
- 支持封面模板、标题、作者名和画面元素配置
- 可调用 OpenAI 兼容图片接口生成封面
- 自动保存封面历史、原图和缩略图到当前项目目录

### 知识库与 Wiki

- 知识库支持文件导入、分块、向量检索、全文检索和章节索引
- Wiki 支持页面编辑、搜索、图谱、反向链接、lint、review 和 ingest
- 发布版默认内置本地 ONNX 向量模型，用于本地知识检索
- 仍可在设置中按需配置外部 Embedding API

### Skills 与热点检索

- 通过 `skills/` 目录加载本地 Skill
- 当前内置能力包括 `agent_reach` 和 `trends_search`
- 趋势模块支持获取与展示热点内容，用于选题、灵感和资料参考

---

## 桌面安装包

普通用户可以直接使用发布版安装包，无需安装 Python 或手动配置开发环境：

- 📥 [下载山海·云烟 Windows 安装包](https://github.com/swyaoguai/shanghaiyunyan/releases/latest)

从当前发布策略开始，正式发布只保留 **内含检索模型版**。该安装包会内置 `novel_agent/models/embedding/default` 下的本地 ONNX 向量模型，避免因为缺少本地检索模型导致知识库不可用。

> 本项目是本地单用户应用。安装包不会提供云同步账号、远程服务或多端同步能力。

### 常见问题排查

如果遇到启动失败、白屏、接口异常或模型调用异常，可以优先查看：

- 根目录 `startup_error.txt`
- 根目录或运行目录下的 `*.log`
- 应用内诊断接口导出的支持信息
- 启动终端中打印的实际访问地址与端口

默认端口是 `5656`。如果端口被占用，启动脚本会自动寻找后续可用端口，请以终端输出为准。

---

## 快速开始

### 环境要求

- Python 3.10+
- Windows 推荐 Python 3.11
- 可选：Inno Setup，用于生成最终安装包

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

最小配置示例：

```env
OPENAI_API_KEY=你的 API Key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4
HOST=0.0.0.0
PORT=5656
```

### 启动应用

```bash
python run.py
```

Windows 也可以双击：

```text
启动山海·云烟.bat
```

启动后访问：

```text
http://localhost:5656
```

---

## AI 配置

山海·云烟通过 OpenAI 兼容或 Anthropic 兼容接口调用模型。可以在 `.env` 中写入基础配置，也可以启动后在「设置」中管理 API。

当前主流程支持：

| API 类型 | 用途 |
| --- | --- |
| OpenAI Chat Completions | 常见 OpenAI 兼容接口与中转服务 |
| OpenAI Responses | 支持 Responses 格式的模型服务 |
| Anthropic Messages | 支持 Claude/Anthropic 格式的模型服务 |

设置页可以维护多个 API 配置、模型列表、激活配置，并为不同 Agent 指定不同模型。对于知识库检索，可使用发布包内置的本地 ONNX 向量模型，也可改用外部 Embedding API。

---

## 打包发布

正式发布构建：

```bash
python build_release.py
```

发布脚本会生成一个 Windows 安装 EXE：

```text
dist/山海·云烟_v<版本号>_内含检索模型版.exe
```

该构建会复制静态资源、页面模板、提示词、Skills、干净的发布数据副本和本地 ONNX 向量模型，并使用根目录的 `logo.ico` 作为应用图标。发布产物不生成 zip。

如果只是本地调试，`build_installer.py` 仍保留 `--without-onnx` 选项，但不再作为正式发布产物。

---

## 源码目录

```text
run.py
  应用启动入口。

novel_agent/web/app.py
  FastAPI 应用工厂与生命周期管理。

novel_agent/web/routes/
  Web API 路由。

novel_agent/web/static/
  原生 JavaScript 前端模块。

novel_agent/web/templates/index.html
  主页面模板。

novel_agent/agents/
  Router、创作 Agent、LLM 客户端和消息总线。

novel_agent/workflow/
  创作协调器、任务池、工作流和运行状态。

novel_agent/knowledge_base/
  向量检索、全文检索、元数据和混合检索。

novel_agent/wiki/
  Wiki 页面、图谱、检索、审核和迁移。

skills/
  本地 Skill 目录。

data/
  本地项目数据，默认不提交。
```

---

## 本地数据与隐私

山海·云烟默认把创作数据保存在本机。项目内容、章节、会话、统计、日志和知识库数据通常位于 `data/` 目录或安装包对应的数据目录。

请不要把以下内容上传到公开仓库：

- `.env`
- `data/`
- 日志文件
- 构建产物
- 私人项目素材
- 本地测试目录和测试配置
- GitHub Token、API Key 或其他凭证

使用 AI 功能时，你输入的文本、项目上下文和必要配置会发送到你选择的模型服务或中转接口。正式创作前请确认所使用服务的隐私政策、数据保留策略和模型训练规则。

如果要把本应用部署到局域网或公网，请自行增加认证、HTTPS、访问控制、备份和安全审计。

---

## 更新方式

### 安装包用户

前往 [Releases](https://github.com/swyaoguai/shanghaiyunyan/releases/latest) 下载最新安装包，覆盖安装即可。项目数据默认保存在本地数据目录中，正常覆盖安装不会主动删除你的创作数据。

### 源码用户

```bash
git pull origin master
pip install -r requirements.txt
python run.py
```

如果更新涉及前端静态资源、模型配置或数据结构，建议完整重启服务后再使用。

---

## 开源协议

本项目采用 [AGPL-3.0](LICENSE) 协议开源。

简单说：

- 你可以自由使用、修改、分发本项目
- 允许个人使用和商业使用
- 修改后的版本也必须以 AGPL-3.0 兼容方式开源
- 如果你将修改版作为网络服务提供，也需要向用户提供对应源代码
- 必须保留原始版权声明和许可证文本

第三方依赖、模型、图标、字体和外部 API 服务仍受其各自许可证或服务条款约束。

---

## 社区交流

- QQ 交流群：[点击加入](https://qm.qq.com/q/E25rrnPONy)
- 群号：`760758525`
- GitHub Issues：[问题反馈与功能建议](https://github.com/swyaoguai/shanghaiyunyan/issues)
