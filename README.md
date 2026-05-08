<div align="center">
  <img src="logo.png" alt="山海·云烟 Logo" width="128" height="128">
  
  # 山海·云烟
  
  **基于多Agent协作的AI小说创作系统**
  
  [![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
  [![Version](https://img.shields.io/badge/version-1.0-brightgreen.svg)](./CHANGELOG.md)
</div>

---

基于 Karpathy LLM Wiki 模式的知识系统 + Coordinator-Worker 多Agent协作架构，提供完整的小说创作工作流。

> **📢 山海·云烟 v1.0**
> 引入 LLM Wiki 知识系统，资料库和知识中心升级为预编译wiki页面。
> 提示词系统修复，用户自定义提示词立即生效。

## ✨ 功能特点

### 🤖 多Agent协作系统
- **世界观构建Agent** - 自动生成完整的小说世界观设定（力量体系、地理环境、势力分布等）
- **大纲规划Agent** - 智能规划故事结构、章节安排和情节走向
- **章节撰写Agent** - 高质量的章节内容生成，支持上下文感知和知识库检索
- **润色优化Agent** - 文字润色、风格统一和表达优化
- **质量评估Agent** - 自动检测剧情漏洞、角色一致性和逻辑问题
- **无限续写Agent** - 支持灵感驱动的故事续写，自动维护剧情一致性
- **沟通助手Agent** - 多轮对话收集创作需求，自动触发工具调用

### 📖 Wiki 知识系统
基于 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 模式，将知识从"临时检索"升级为"预编译wiki"。

- **三层架构** - Raw Sources（原始文档）→ Wiki（LLM生成的结构化页面）→ Schema（规则与目标）
- **两步链式摄取** - LLM先分析源文档结构，再生成wiki页面，质量远高于单步摄取
- **4信号知识图谱** - 直接链接(×3) + 来源重叠(×4) + Adamic-Adar(×1.5) + 类型亲和度(×1)
- **[[wikilink]]双向链接** - 页面间交叉引用，自动维护正向和反向链接
- **多阶段检索管道** - 分词搜索 → 向量语义搜索 → 图谱扩展 → 预算控制 → 上下文组装
- **SHA256增量缓存** - 跳过未变化的文件，节省LLM调用成本
- **Lint质量检查** - 死链接、孤立页面、过时内容、空页面检测
- **Review审核系统** - LLM标记待审核项，异步人工处理

### 🎯 创作辅助
- **Copilot助手** - AI写作助手，支持 @ 引用角色、章节和设定
- **提示词系统** - 内置提示词 + 自定义提示词配置（修改后立即生效）
- **热点融合** - 自动搜索抖音/头条热点，融入创作内容
- **短篇创作** - 支持短篇小说的独立创作流程

### 📊 统计与分析
- **Token统计** - 实时追踪API调用量和成本
- **写作仪表板** - 进度跟踪、质量评分、写作习惯分析

### 📤 导出功能
- 短篇成稿支持导出 TXT、Markdown、DOCX
- 小说转剧本结果支持导出 TXT、Markdown、DOCX
- 项目备份支持 ZIP 导出和导入

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Web UI (FastAPI + Jinja2)                │
├─────────────────────────────────────────────────────────────┤
│                  Coordinator (协调器 + 状态机)                │
│    ┌───────────┬───────────┬───────────┬───────────┐        │
│    │Worldbuilder│ Outliner │ChapterWriter│ Polisher│        │
│    │  (世界观)  │  (大纲)  │  (撰写)    │  (润色)  │        │
│    └─────┬─────┴─────┬─────┴─────┬─────┴─────┬────┘        │
│          │           │           │           │              │
│    ┌─────▼───────────▼───────────▼───────────▼────┐        │
│    │         Message Bus (消息总线 + 能力注册表)     │        │
│    └─────────────────────┬───────────────────────┘        │
├──────────────────────────┼──────────────────────────────────┤
│              Wiki 知识系统 (Karpathy LLM Wiki 模式)          │
│    ┌──────────────┬──────────────┬──────────────┐          │
│    │  WikiStore   │ WikiGraph    │ WikiRetriever│          │
│    │ (页面存储)   │ (4信号图谱)  │ (多阶段检索) │          │
│    ├──────────────┼──────────────┼──────────────┤          │
│    │ WikiIngest   │ WikiLinter   │ WikiReview   │          │
│    │ (两步摄取)   │ (质量检查)   │ (审核系统)   │          │
│    └──────────────┴──────────────┴──────────────┘          │
├─────────────────────────────────────────────────────────────┤
│                  Context Manager (上下文管理)                │
│    ┌──────────────┬──────────────┬──────────────┐          │
│    │CharacterManager│WorldManager │ContextManager│          │
│    └──────────────┴──────────────┴──────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求
- Python 3.10+
- 至少准备一种可用的模型 API 配置：
  - OpenAI Chat
  - OpenAI Responses
  - Anthropic

### 安装

```bash
git clone https://github.com/swyaoguai/wscz.git
cd wscz
pip install -r requirements.txt
```

### 配置模型

启动软件后进入「设置」，在「全局 API 配置」中新增配置。API 类型支持：

| API 类型 | 说明 |
|----------|------|
| OpenAI Chat | 使用 OpenAI Chat Completions 兼容接口 |
| OpenAI Responses | 使用 OpenAI Responses 接口 |
| Anthropic | 使用 Anthropic Messages 接口 |

知识库向量检索也在「设置 → 知识库配置」中选择，可以使用硅基流动线上嵌入模型，也可以安装本地 ONNX 模型包。

### 启动

```bash
# Windows
启动山海·云烟.bat

# Linux/Mac
python run.py
```

默认访问 http://localhost:5656

### 运行测试

```bash
python -m pytest
```

## 📁 项目结构

```
novel_agent/
├── agents/                 # Agent实现
│   ├── base_agent.py       # Agent基类（LLM调用、回调、重试、提示词管理集成）
│   ├── worldbuilder.py     # 世界观构建Agent
│   ├── outliner.py         # 大纲规划Agent
│   ├── chapter_writer.py   # 章节撰写Agent（知识库集成）
│   ├── polisher.py         # 润色优化Agent
│   ├── evaluator.py        # 质量评估Agent
│   ├── continuous_writer.py# 无限续写Agent（持久化会话、热点融合）
│   ├── communicator.py     # 用户对话Agent（意图识别、工具调用）
│   ├── router_agent.py     # 路由智能体
│   └── message_bus.py      # Agent间消息总线
│
├── wiki/                   # Wiki知识系统
│   ├── wiki_types.py       # 数据模型（WikiPage, Frontmatter, WikiGraph）
│   ├── wiki_store.py       # 页面存储 + 双向链接 + SHA256缓存
│   ├── wiki_index.py       # purpose.md/schema.md/index.md/overview.md
│   ├── wiki_graph.py       # 4信号知识图谱 + 图谱扩展检索
│   ├── wiki_ingest.py      # 两步链式摄取管道 + 持久化队列
│   ├── wiki_retriever.py   # 多阶段检索（分词→向量→图谱→预算→组装）
│   ├── wiki_lint.py        # Lint质量检查
│   ├── wiki_review.py      # Review审核系统
│   ├── wiki_migrate.py     # 旧数据迁移
│   └── wiki_adapter.py     # LibraryService兼容适配器
│
├── context/                # 上下文管理
│   ├── context_manager.py  # 上下文压缩与同步
│   ├── character_manager.py# 角色档案管理
│   └── world_manager.py    # 世界观设定管理
│
├── knowledge_base/         # 知识库系统（向量+全文检索）
│   ├── data_layer/         # ChromaDB向量存储 + SQLite FTS5
│   ├── logic_layer/        # 向量化、分块、章节识别
│   └── application_layer/  # 混合检索、导航、统一模型
│
├── workflow/               # 工作流管理
│   ├── coordinator.py      # 主协调器（状态机、检查点）
│   ├── collab_services.py  # 协作服务（上下文策略、扩写、摘要）
│   └── routing_policy.py   # 路由策略
│
├── prompts/                # 提示词系统
│   ├── prompt_manager.py   # 提示词管理器（自定义提示词热重载）
│   └── *.md                # 各Agent的提示词模板
│
├── llm_adapters/           # LLM适配器（多提供商支持）
│   ├── deepseek.py         # DeepSeek
│   ├── zhipu.py            # 智谱AI
│   ├── moonshot.py         # 月之暗面
│   ├── doubao.py           # 字节豆包
│   └── ...                 # 阿里、百度、讯飞、MiniMax
│
├── web/                    # Web应用
│   ├── app.py              # FastAPI主应用
│   ├── routes/             # 路由模块（14个独立模块）
│   ├── static/             # 前端资源（JS/CSS）
│   └── templates/          # HTML模板
│
├── utils/                  # 工具模块
│   ├── token_stats.py      # Token使用统计
│   ├── retry.py            # 重试机制（指数退避、熔断器）
│   ├── metrics.py          # 指标收集
│   └── atomic_write.py     # 原子写入（防止文件损坏）
│
├── config.py               # 全局配置
├── constants.py            # 常量定义
├── project_manager.py      # 项目管理器（多项目隔离）
└── memory_manager.py       # 记忆管理器
```

## ⚙️ 配置说明

### 全局API配置

系统支持在 Web UI 的设置页面配置全局 API，也可以为每个 Agent 单独配置不同的模型。

| API 类型 | 需要填写 |
|----------|----------|
| OpenAI Chat | API Base URL、API Key、模型名 |
| OpenAI Responses | API Base URL、API Key、模型名 |
| Anthropic | API Base URL、API Key、模型名 |

设置页也支持为不同 Agent 指定不同 API 配置、模型、温度和最大 token 数。

### 知识库嵌入模型配置

知识库检索需要先把文本转成向量。项目现在支持两种方式：线上硅基流动和本地 ONNX。用户不需要手动编辑 `.env`；打开软件后进入「设置 → 知识库配置」，在「嵌入模型来源」里选择即可。保存后程序会自动写入配置文件。

如果本地模型包和硅基流动都已经配置好，实际使用哪一个只看「嵌入模型来源」当前选项：

- 选择「本地模型包」：使用已安装的 ONNX 模型。
- 选择「硅基流动线上模型」：使用硅基流动 API。

#### 方式一：本地 ONNX 模型

适合离线使用，不消耗线上 API 额度。推荐模型包为 `embedding-model-bge-small-zh-v1.5.zip`。在设置页点击「安装模型包」，选择这个 zip，程序会自动解压、检测并启用。

安装后的目录结构为：

```text
novel_agent/models/embedding/default/
├── model.onnx
├── tokenizer.json
├── tokenizer_config.json
├── special_tokens_map.json
├── vocab.txt
├── config.json
└── metadata.json
```

`.env` 配置：

```env
KB_EMBEDDING_PROVIDER=local_onnx
KB_ONNX_MODEL_DIR=novel_agent/models/embedding/default
KB_ONNX_MODEL_FILE=model.onnx
KB_ONNX_POOLING=cls
```

#### 方式二：硅基流动线上嵌入模型

适合不想下载本地模型、或希望直接使用线上向量模型的场景。在设置页选择「硅基流动线上模型」，填写 API Key，选择模型后保存即可。

对应配置如下，通常不需要用户手动编辑：

```env
KB_EMBEDDING_PROVIDER=api
SILICONFLOW_API_KEY=你的硅基流动Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3
SILICONFLOW_EMBEDDING_DIM=1024
```

可选模型：

| 模型 | 维度 | 说明 |
|------|------|------|
| `BAAI/bge-m3` | 1024 | 推荐，多语言，通用检索 |
| `BAAI/bge-large-zh-v1.5` | 1024 | 中文优化 |
| `BAAI/bge-large-en-v1.5` | 1024 | 英文优化 |

从本地 ONNX 切到硅基流动，或从硅基流动切回本地 ONNX 后，建议重建知识库索引。不同模型的向量维度和分布可能不同，旧索引继续混用会影响检索效果，维度不同还可能导致向量库写入失败。

### 支持的 API 类型

项目当前在设置页支持三种 API 类型：

| API 类型 | 用途 |
|----------|------|
| OpenAI Chat | 适用于 Chat Completions 兼容接口 |
| OpenAI Responses | 适用于 Responses 接口 |
| Anthropic | 适用于 Anthropic Messages 接口 |

### Skill 配置

```bash
# 以 trends_search 为例
cd skills/trends_search
cp config.example.json config.json
```

可用 Skills：
- `agent_reach`: 网络搜索功能
- `trends_search`: 热点趋势搜索（抖音、头条）

## 🎮 使用指南

### 1. 配置模型
进入「设置」，新增一个 API 配置，选择 API 类型并填写 API Base URL、API Key 和模型名。保存后可以测试连接。

### 2. 创建或选择项目
在项目入口创建项目。项目数据会按项目隔离保存。

### 3. 进入写作工作区
在写作区可以编辑章节，也可以使用右侧 Copilot 对话，让它基于当前项目资料协助创作、修改或整理内容。

### 4. 使用资料与知识库
资料库用于管理角色、世界观、物品、事件线等项目资料。知识库用于导入文档、分块索引和语义检索；嵌入模型来源可在「设置 → 知识库配置」中切换。

### 5. 使用专项工具
可以进入「无限续写」「短篇创作」「小说转剧本」「热点趋势」「Token 统计」等模块处理对应任务。

## 🔧 开发说明

### 代码结构特点
- **分层架构**：数据层/逻辑层/应用层分离
- **异步优先**：核心LLM调用全部使用async/await
- **线程安全**：关键数据结构使用threading.Lock保护
- **提示词管理**：用户自定义提示词通过PromptManager热重载，立即生效
- **消息总线**：Agent间通过消息总线通信，支持流式任务

### 运行测试
```bash
python -m pytest novel_agent/tests/ -v
```

## 📄 License

MIT License
