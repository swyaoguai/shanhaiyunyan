"""
知识库配置管理模块

提供知识库系统的所有配置项，支持从环境变量和配置文件加载。
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class SiliconFlowConfig:
    """硅基流动API配置"""
    api_key: str = field(default_factory=lambda: os.getenv("SILICONFLOW_API_KEY", ""))
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024  # 可选: 512, 1024, 2048
    max_tokens: int = 8192  # bge-m3支持的最大输入长度
    timeout: int = 30  # API请求超时时间（秒）
    max_retries: int = 3  # 最大重试次数


@dataclass
class NVIDIAConfig:
    """NVIDIA NeMo Retriever API配置"""
    api_key: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", ""))
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "nvidia/llama-3.2-nemoretriever-300m-embed-v1"
    embedding_dim: int = 2048  # llama-3.2-nemoretriever-300m-embed-v1 实际维度
    input_type: str = "query"  # "query" 用于查询, "passage" 用于文档
    truncate: str = "NONE"  # "NONE", "START", "END"
    timeout: int = 30
    max_retries: int = 3


@dataclass
class LocalOnnxConfig:
    """本地 ONNX embedding 模型配置。"""
    model_dir: str = field(default_factory=lambda: os.getenv("KB_ONNX_MODEL_DIR", ""))
    model_file: str = field(default_factory=lambda: os.getenv("KB_ONNX_MODEL_FILE", "model.onnx"))
    tokenizer_dir: str = field(default_factory=lambda: os.getenv("KB_ONNX_TOKENIZER_DIR", ""))
    model_name: str = field(default_factory=lambda: os.getenv("KB_ONNX_MODEL_NAME", "local_onnx"))
    embedding_dim: int = 0
    max_length: int = 512
    threads: Optional[int] = None
    pooling: str = "cls"  # "cls" 或 "mean"


@dataclass
class ChromaConfig:
    """ChromaDB向量数据库配置"""
    persist_directory: str = "./data/chroma"
    collection_name: str = "novel_knowledge"
    distance_metric: str = "cosine"  # 可选: "cosine", "l2", "ip"


@dataclass 
class SQLiteConfig:
    """SQLite存储配置"""
    db_path: str = "./data/knowledge.db"
    fts_tokenizer: str = "unicode61"  # FTS5分词器，支持中文


@dataclass
class ChunkingConfig:
    """文本分块配置"""
    chunk_size: int = 500  # 每块大约500字符
    chunk_overlap: int = 50  # 块之间重叠50字符
    min_chunk_size: int = 100  # 最小块大小
    separators: list = field(default_factory=lambda: ["\n\n", "\n", "。", "！", "？", ".", "!", "?"])


@dataclass
class SummarySearchConfig:
    """摘要索引检索配置（无向量RAG）
    
    使用LLM对每个条目生成摘要作为索引，检索时让LLM根据查询
    从摘要列表中选择最相关的条目ID，然后读取原始内容。
    
    优点：语义理解更准确，无需向量化服务
    缺点：每次检索消耗Token（约等于摘要总字数）
    """
    enabled: bool = False  # 默认关闭
    target_categories: list = field(default_factory=lambda: ["character", "world"])  # 适用分类
    max_entries: int = 200  # 最大条目数限制（超过则警告性能问题）
    summary_max_length: int = 50  # 每条摘要最大字数
    cache_summaries: bool = True  # 是否缓存摘要（避免重复生成）


@dataclass
class RetrievalConfig:
    """检索配置"""
    default_top_k: int = 5
    max_top_k: int = 50
    vector_weight: float = 0.7  # 向量检索权重
    fulltext_weight: float = 0.3  # 全文检索权重
    min_score_threshold: float = 0.1  # 最小相关性阈值
    
    # 检索策略配置
    chapter_search_mode: str = "hybrid"  # "hybrid", "vector", "fulltext"
    summary_search: SummarySearchConfig = field(default_factory=SummarySearchConfig)


@dataclass
class KnowledgeBaseConfig:
    """知识库总配置"""
    project_id: str = "default"
    data_dir: str = ""  # 将在__post_init__中设置
    embedding_provider: str = "siliconflow"  # "api"/"siliconflow", "nvidia", "local_onnx"
    
    siliconflow: SiliconFlowConfig = field(default_factory=SiliconFlowConfig)
    nvidia: NVIDIAConfig = field(default_factory=NVIDIAConfig)
    local_onnx: LocalOnnxConfig = field(default_factory=LocalOnnxConfig)
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    
    def __post_init__(self):
        """初始化后处理，设置项目相关路径"""
        # 动态获取数据目录
        if not self.data_dir:
            try:
                from ..constants import get_data_dir
                self.data_dir = str(get_data_dir() / "knowledge_base")
            except ImportError:
                self.data_dir = "./data/knowledge_base"
        
        # 创建数据目录
        project_data_dir = Path(self.data_dir) / self.project_id
        project_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 更新各组件路径
        self.chroma.persist_directory = str(project_data_dir / "chroma")
        self.sqlite.db_path = str(project_data_dir / "knowledge.db")
    
    @classmethod
    def from_env(cls, project_id: str = "default") -> "KnowledgeBaseConfig":
        """从环境变量创建配置"""
        config = cls(project_id=project_id)
        
        # 从环境变量覆盖嵌入提供商
        if provider := (os.getenv("KB_EMBEDDING_PROVIDER") or os.getenv("EMBEDDING_PROVIDER")):
            config.embedding_provider = provider
        
        # 从环境变量覆盖硅基流动配置
        if api_key := os.getenv("SILICONFLOW_API_KEY"):
            config.siliconflow.api_key = api_key
        if base_url := os.getenv("SILICONFLOW_BASE_URL"):
            config.siliconflow.base_url = base_url
        if model := os.getenv("SILICONFLOW_EMBEDDING_MODEL"):
            config.siliconflow.model = model
        if dim := os.getenv("SILICONFLOW_EMBEDDING_DIM"):
            config.siliconflow.embedding_dim = int(dim)
        
        # 从环境变量覆盖NVIDIA配置
        if api_key := os.getenv("NVIDIA_API_KEY"):
            config.nvidia.api_key = api_key
        if model := os.getenv("NVIDIA_EMBEDDING_MODEL"):
            config.nvidia.model = model
        if input_type := os.getenv("NVIDIA_INPUT_TYPE"):
            config.nvidia.input_type = input_type

        # 从环境变量覆盖本地 ONNX 配置
        if model_dir := os.getenv("KB_ONNX_MODEL_DIR"):
            config.local_onnx.model_dir = model_dir
        if model_file := os.getenv("KB_ONNX_MODEL_FILE"):
            config.local_onnx.model_file = model_file
        if tokenizer_dir := os.getenv("KB_ONNX_TOKENIZER_DIR"):
            config.local_onnx.tokenizer_dir = tokenizer_dir
        if model_name := os.getenv("KB_ONNX_MODEL_NAME"):
            config.local_onnx.model_name = model_name
        if max_length := os.getenv("KB_ONNX_MAX_LENGTH"):
            config.local_onnx.max_length = int(max_length)
        if threads := os.getenv("KB_ONNX_THREADS"):
            config.local_onnx.threads = int(threads)
        if pooling := os.getenv("KB_ONNX_POOLING"):
            config.local_onnx.pooling = pooling
            
        # 从环境变量覆盖数据目录
        if data_dir := os.getenv("KNOWLEDGE_BASE_DATA_DIR"):
            config.data_dir = data_dir
            config.__post_init__()  # 重新初始化路径
            
        return config
    
    def validate(self) -> list[str]:
        """验证配置有效性，返回错误列表"""
        errors = []
        provider = str(self.embedding_provider or "").strip().lower()
        
        # 根据选择的提供商验证API密钥
        if provider in {"api", "siliconflow"} and not self.siliconflow.api_key:
            errors.append("缺少硅基流动API密钥 (SILICONFLOW_API_KEY)")
        elif provider == "nvidia" and not self.nvidia.api_key:
            errors.append("缺少NVIDIA API密钥 (NVIDIA_API_KEY)")
        elif provider in {"local", "local_onnx"}:
            model_dir = Path(self.local_onnx.model_dir or "")
            model_file = self.local_onnx.model_file or "model.onnx"
            if not self.local_onnx.model_dir:
                errors.append("缺少本地 ONNX 模型目录 (KB_ONNX_MODEL_DIR)")
            elif not (model_dir / model_file).exists():
                errors.append(f"本地 ONNX 模型文件不存在: {model_dir / model_file}")
        
        if self.chunking.chunk_size < self.chunking.min_chunk_size:
            errors.append(f"chunk_size ({self.chunking.chunk_size}) 不能小于 min_chunk_size ({self.chunking.min_chunk_size})")
        
        if self.chunking.chunk_overlap >= self.chunking.chunk_size:
            errors.append(f"chunk_overlap ({self.chunking.chunk_overlap}) 必须小于 chunk_size ({self.chunking.chunk_size})")
        
        if not 0 <= self.retrieval.vector_weight <= 1:
            errors.append(f"vector_weight ({self.retrieval.vector_weight}) 必须在 0-1 之间")
        
        if not 0 <= self.retrieval.fulltext_weight <= 1:
            errors.append(f"fulltext_weight ({self.retrieval.fulltext_weight}) 必须在 0-1 之间")
            
        return errors


# 默认配置实例
default_config = KnowledgeBaseConfig.from_env()
