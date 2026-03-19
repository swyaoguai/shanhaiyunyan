<div align="center">
  <img src="logo.png" alt="Novel Agent Logo" width="128" height="128">
  
  # 📚 小说创作Agent智能体 (Novel Agent)
  
  **基于多Agent协作的AI小说创作系统**
  
  [![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
  [![Version](https://img.shields.io/badge/version-1.1.0-brightgreen.svg)](./CHANGELOG.md)
</div>

---

采用 Coordinator-Worker 架构模式，提供完整的小说创作工作流。

> **📢 v1.1.0 重大更新**
> 架构全面重构，模块化路由系统，新增 Skill 系统。
> 从 v1.0 升级请查看 [迁移指南](./MIGRATION_GUIDE.md) | [更新日志](./CHANGELOG.md)

## ✨ 功能特点

### 🤖 多Agent协作系统
- **世界观构建Agent** - 自动生成完整的小说世界观设定（力量体系、地理环境、势力分布等）
- **大纲规划Agent** - 智能规划故事结构、章节安排和情节走向
- **章节撰写Agent** - 高质量的章节内容生成，支持上下文感知
- **润色优化Agent** - 文字润色、风格统一和表达优化
- **质量评估Agent** - 自动检测剧情漏洞、角色一致性和逻辑问题
- **无限续写Agent** - 支持灵感驱动的故事续写，自动维护剧情一致性

### 📖 知识库系统
- **三层架构设计** - 数据层/逻辑层/应用层分离，易于扩展
- **混合检索** - 支持向量语义检索 + 全文关键词检索
- **章节管理** - 自动章节识别、元数据提取和导航
- **智能分块** - 基于语义的文本分块策略

### 🎯 创作辅助
- **Copilot助手** - AI写作助手，支持 @ 引用角色、章节和设定
- **资料库管理** - 角色档案、世界设定、道具物品、事件线等分类管理
- **提示词系统** - 内置提示词 + 自定义提示词配置
- **安全守卫** - 防止提示词泄露的多层安全防护

### 📊 统计与分析
- **Token统计** - 实时追踪API调用量和成本
- **写作仪表板** - 进度跟踪、质量评分、写作习惯分析
- **LLM缓存** - 智能缓存减少重复调用

### 📤 导出功能
- 支持多种格式：TXT、Markdown、HTML、EPUB

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI (FastAPI)                      │
├─────────────────────────────────────────────────────────────┤
│                     Coordinator (协调器)                      │
│    ┌───────────┬───────────┬───────────┬───────────┐        │
│    │Worldbuilder│ Outliner │ChapterWriter│ Polisher│        │
│    │  (世界观)  │  (大纲)  │  (撰写)    │  (润色)  │        │
│    └─────┬─────┴─────┬─────┴─────┬─────┴─────┬────┘        │
│          │           │           │           │              │
│    ┌─────▼───────────▼───────────▼───────────▼────┐        │
│    │              Message Bus (消息总线)           │        │
│    └─────────────────────┬───────────────────────┘        │
├──────────────────────────┼──────────────────────────────────┤
│                 Context Manager (上下文管理)                  │
│    ┌──────────────┬──────────────┬──────────────┐          │
│    │CharacterManager│WorldManager │ContextManager│          │
│    │   (角色管理)   │ (世界观)   │  (上下文)    │          │
│    └──────────────┴──────────────┴──────────────┘          │
├─────────────────────────────────────────────────────────────┤
│                   Knowledge Base (知识库)                    │
│    ┌─────────────────────────────────────────────┐          │
│    │ Application Layer: HybridSearch, Navigator  │          │
│    ├─────────────────────────────────────────────┤          │
│    │ Logic Layer: Embeddings, Chunker, Marker    │          │
│    ├─────────────────────────────────────────────┤          │
│    │ Data Layer: VectorStore, FulltextStore      │          │
│    └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求
- Python 3.10+
- 支持 OpenAI 兼容 API 的服务（OpenAI、DeepSeek、硅基流动等）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，配置你的 API：
```env
# OpenAI兼容API配置（必填）
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# 知识库向量化配置（可选，用于知识库功能）
SILICONFLOW_API_KEY=your-siliconflow-api-key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

### 启动服务

**方式一：使用启动脚本（推荐）**
```bash
# Windows
启动小说Agent.bat

# Linux/Mac
python run.py
```

**方式二：直接运行**
```bash
python run.py
```

默认访问 http://localhost:5656 进入 Web UI（若端口被占用，系统会自动切换并在控制台提示实际端口）

## 📁 项目结构

```
novel_agent/
├── agents/                 # Agent实现
│   ├── base_agent.py       # Agent基类（LLM调用、回调、重试）
│   ├── worldbuilder.py     # 世界观构建Agent
│   ├── outliner.py         # 大纲规划Agent
│   ├── chapter_writer.py   # 章节撰写Agent
│   ├── polisher.py         # 润色优化Agent
│   ├── evaluator.py        # 质量评估Agent
│   ├── continuous_writer.py# 无限续写Agent
│   ├── communicator.py     # 用户对话Agent
│   └── message_bus.py      # Agent间消息总线
│
├── context/                # 上下文管理
│   ├── context_manager.py  # 上下文压缩与同步
│   ├── character_manager.py# 角色档案管理
│   └── world_manager.py    # 世界观设定管理
│
├── knowledge_base/         # 知识库系统
│   ├── data_layer/         # 数据存储层
│   │   ├── vector_store.py # ChromaDB向量存储
│   │   ├── fulltext_store.py# SQLite FTS5全文检索
│   │   └── metadata_store.py# 章节元数据存储
│   ├── logic_layer/        # 业务逻辑层
│   │   ├── embeddings.py   # 向量化服务（硅基流动API）
│   │   ├── chunker.py      # 智能文本分块
│   │   └── chapter_marker.py# 章节自动识别
│   └── application_layer/  # 应用接口层
│       ├── hybrid_search.py# 混合检索引擎
│       ├── knowledge_api.py# 知识库API
│       └── navigator.py    # 章节导航
│
├── workflow/               # 工作流管理
│   └── coordinator.py      # 主协调器（状态机、检查点）
│
├── prompts/                # 提示词系统
│   ├── prompt_manager.py   # 提示词管理器
│   ├── security_guard.py   # 安全守卫模块
│   ├── custom_prompts.json # 自定义提示词配置
│   └── *.md                # 各Agent的提示词模板
│
├── utils/                  # 工具模块
│   ├── token_stats.py      # Token使用统计
│   ├── cache.py            # LLM响应缓存
│   ├── retry.py            # 重试机制（指数退避、熔断器）
│   ├── metrics.py          # 指标收集
│   ├── exporter.py         # 多格式导出
│   ├── dashboard.py        # 写作统计仪表板
│   ├── validators.py       # 配置验证
│   └── mcp_manager.py      # MCP工具管理
│
├── web/                    # Web应用
│   ├── app.py              # FastAPI主应用
│   ├── static/             # 前端资源
│   │   ├── app-core.js     # 核心状态管理
│   │   ├── app-chapters.js # 章节管理
│   │   ├── app-copilot.js  # AI助手
│   │   ├── app-knowledge.js# 知识库界面
│   │   └── style.css       # 样式
│   └── templates/          # HTML模板
│
├── data/                   # 数据目录
│   ├── projects/           # 项目数据（多项目隔离）
│   ├── stats/              # 统计数据
│   └── knowledge_base/     # 知识库数据
│
├── config.py               # 全局配置
├── constants.py            # 常量定义
├── project_manager.py      # 项目管理器
├── memory_manager.py       # 记忆管理器
└── wensi_service.py        # Wensi服务（可选）
```

## ⚙️ 配置说明

### 全局API配置

系统支持在Web UI的设置页面配置全局API，也可以为每个Agent单独配置不同的模型。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `OPENAI_API_BASE` | API地址 | https://api.openai.com/v1 |
| `OPENAI_API_KEY` | API密钥 | - |
| `OPENAI_MODEL` | 模型名称 | gpt-4 |
| `MAX_TOKENS` | 最大Token数 | 4096 |
| `TEMPERATURE` | 温度参数 | 0.7 |

### 知识库配置

知识库使用硅基流动的向量化API，需要单独配置：

| 配置项 | 说明 |
|--------|------|
| `SILICONFLOW_API_KEY` | 硅基流动API密钥 |
| `SILICONFLOW_BASE_URL` | API地址 |
| `SILICONFLOW_EMBEDDING_MODEL` | 向量化模型（默认BAAI/bge-m3） |

### Skill 配置

v1.1 新增 Skill 系统，支持扩展功能：

```bash
# 配置 Skill（以 trends_search 为例）
cd skills/trends_search
cp config.example.json config.json
# 编辑 config.json 填入 API 密钥
```

可用 Skills：
- `agent_reach`: 网络搜索功能
- `trends_search`: 热点趋势搜索

详见 [Skill 系统文档](./docs/Skill系统集成方案.md)

## 📚 文档

- [API 文档](./docs/API.md) - REST API 接口说明
- [迁移指南](./MIGRATION_GUIDE.md) - v1.0 → v1.1 升级指南
- [更新日志](./CHANGELOG.md) - 版本更新记录
- [MCP 迁移](./docs/MCP迁移到Skill完整方案.md) - MCP 到 Skill 迁移
- [架构文档](./docs/) - 详细技术文档

## 🎮 使用指南

### 1. 创建项目
在Web UI左上角的项目选择器中创建新项目，每个项目独立存储数据。

### 2. 构建世界观
进入"世界设定"模块，填写小说类型、主题等信息，系统会自动生成世界观。

### 3. 规划大纲
在"写作"模块中创建章节，系统会根据世界观和前文自动规划情节。

### 4. 创作内容
- **手动撰写**：直接在编辑器中写作
- **AI续写**：点击"AI续写"按钮自动生成内容
- **无限续写**：进入"无限续写"模块，基于灵感自动创作

### 5. 使用Copilot
点击右侧Copilot面板，使用 `@角色名` 或 `@章节名` 引用内容进行对话。

## 🔧 开发说明

### 运行测试
```bash
pytest novel_agent/tests/
```

### 代码结构特点
- **分层架构**：数据层/逻辑层/应用层分离
- **依赖注入**：通过全局单例管理服务实例
- **异步优先**：核心LLM调用全部使用async/await
- **线程安全**：关键数据结构使用threading.Lock保护

## 📝 更新日志

### v1.0.0
- 完整的多Agent协作系统
- 知识库三层架构
- Web UI界面
- 无限续写功能
- Token统计和成本追踪
- 多格式导出支持

## 📄 License

MIT License

## 🙏 致谢

- 基于"慢学AI"视频内容构建
- 使用 OpenAI 兼容 API
- 向量化服务由硅基流动提供