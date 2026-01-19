# 知识库系统 (Knowledge Base System)

## 架构概览

基于分层架构设计，实现向量检索 + 章节标记 + 全文搜索的MVP功能。

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层 (Application Layer)              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  统一检索接口    │  │  知识管理API    │  │  章节导航   │  │
│  │  (HybridSearch) │  │  (KnowledgeAPI) │  │  (Navigator)│  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      逻辑层 (Logic Layer)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   文本分块器     │  │   向量化服务    │  │  章节标记   │  │
│  │   (Chunker)     │  │  (Embeddings)   │  │  (Marker)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      数据层 (Data Layer)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   向量数据库     │  │   全文索引      │  │  元数据存储  │  │
│  │   (ChromaDB)    │  │ (SQLite FTS5)  │  │  (SQLite)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
knowledge_base/
├── __init__.py                 # 模块入口
├── README.md                   # 架构说明
├── config.py                   # 配置管理
│
├── data_layer/                 # 数据层
│   ├── __init__.py
│   ├── vector_store.py         # ChromaDB向量存储
│   ├── fulltext_store.py       # SQLite FTS5全文索引
│   └── metadata_store.py       # SQLite元数据存储
│
├── logic_layer/                # 逻辑层
│   ├── __init__.py
│   ├── chunker.py              # 文本分块器
│   ├── embeddings.py           # 向量化服务（硅基流动 bge-m3）
│   └── chapter_marker.py       # 章节标记管理
│
├── application_layer/          # 应用层
│   ├── __init__.py
│   ├── hybrid_search.py        # 混合检索接口
│   ├── knowledge_api.py        # 知识管理API
│   └── navigator.py            # 章节导航
│
└── tests/                      # 测试
    ├── __init__.py
    ├── test_data_layer.py
    ├── test_logic_layer.py
    └── test_application_layer.py
```

## 技术选型

| 组件 | 技术方案 | 说明 |
|------|---------|------|
| 向量数据库 | ChromaDB | 轻量级、Python原生、支持持久化 |
| 向量模型 | 硅基流动 bge-m3 | 多语言、8192 tokens上下文 |
| 全文搜索 | SQLite FTS5 | 轻量、无需额外服务 |
| 元数据存储 | SQLite | 章节信息、时间戳等 |

## 核心功能

### 1. 向量检索
- 语义相似度搜索
- Top-K结果返回
- 支持元数据过滤

### 2. 全文搜索
- 关键词精确匹配
- BM25排序
- 支持中文分词

### 3. 章节标记
- 自动章节识别
- 章节元数据管理
- 按章节范围检索

### 4. 混合检索
- 向量+全文融合
- 可配置权重
- 结果去重排序

## API设计

```python
# 初始化知识库
from knowledge_base import KnowledgeBase

kb = KnowledgeBase(
    project_id="my_novel",
    chroma_path="./data/chroma",
    sqlite_path="./data/knowledge.db",
    siliconflow_api_key="your_api_key"
)

# 添加章节内容
kb.add_chapter(
    chapter_id="chapter_1",
    title="第一章 开端",
    content="这是第一章的内容...",
    metadata={"word_count": 3000, "created_at": "2024-01-01"}
)

# 混合检索
results = kb.search(
    query="主角的身世",
    top_k=5,
    search_type="hybrid",  # "vector", "fulltext", "hybrid"
    chapter_filter=["chapter_1", "chapter_2"]  # 可选：限定章节
)

# 获取章节列表
chapters = kb.list_chapters()

# 获取章节摘要（未来扩展）
summary = kb.get_chapter_summary("chapter_1")
```

## 配置项

```python
# config.py
KNOWLEDGE_BASE_CONFIG = {
    # 硅基流动API配置
    "siliconflow": {
        "api_key": "YOUR_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "embedding_dim": 1024,  # 可选：512, 1024, 2048
    },
    
    # ChromaDB配置
    "chroma": {
        "persist_directory": "./data/chroma",
        "collection_name": "novel_knowledge",
    },
    
    # 分块配置
    "chunking": {
        "chunk_size": 500,      # 每块大约500字符
        "chunk_overlap": 50,    # 块之间重叠50字符
        "separator": "\n\n",    # 优先按段落分割
    },
    
    # 检索配置
    "retrieval": {
        "default_top_k": 5,
        "vector_weight": 0.7,   # 向量检索权重
        "fulltext_weight": 0.3, # 全文检索权重
    }
}