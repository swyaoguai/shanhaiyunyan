"""
Embedding模块
支持本地模型和API两种方式生成文本向量
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional
import numpy as np

from ..constants import (
    TIMEOUTS,
    EMBEDDING_CONFIG,
    API_ENDPOINTS
)

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Embedding提供者抽象基类"""
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        生成文本向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        pass
    
    @abstractmethod
    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        """同步版本的embed"""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass


class LocalEmbedding(EmbeddingProvider):
    """
    本地Embedding模型
    使用sentence-transformers，完全免费
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化本地Embedding模型
        
        Args:
            model_name: 模型名称
                - all-MiniLM-L6-v2: 轻量快速，384维
                - paraphrase-multilingual-MiniLM-L12-v2: 多语言支持
        """
        self.model_name = model_name
        self._model = None
        self._dimension = EMBEDDING_CONFIG.DIMENSION_LOCAL_DEFAULT  # 默认值
        logger.info(f"LocalEmbedding initialized with model: {model_name}")
    
    def _load_model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(f"Loaded embedding model: {self.model_name}, dim={self._dimension}")
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise ImportError("Please install sentence-transformers: pip install sentence-transformers")
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        """同步生成向量"""
        self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """异步生成向量（实际是同步执行）"""
        return self.embed_sync(texts)


class APIEmbedding(EmbeddingProvider):
    """
    使用API的Embedding
    兼容OpenAI API接口
    """
    
    def __init__(
        self,
        api_base: str = API_ENDPOINTS.OPENAI_BASE_URL,
        api_key: str = "",
        model: str = "text-embedding-ada-002"
    ):
        """
        初始化API Embedding
        
        Args:
            api_base: API地址
            api_key: API密钥
            model: 模型名称
        """
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self._dimension = EMBEDDING_CONFIG.DIMENSION_ADA_002  # OpenAI ada-002 默认
        
        # 根据模型调整维度
        if "3-small" in model:
            self._dimension = EMBEDDING_CONFIG.DIMENSION_3_SMALL
        elif "3-large" in model:
            self._dimension = EMBEDDING_CONFIG.DIMENSION_3_LARGE
        
        logger.info(f"APIEmbedding initialized: {model}")
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        """同步调用API"""
        import httpx
        
        response = httpx.post(
            f"{self.api_base}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "input": texts
            },
            timeout=TIMEOUTS.HTTP_LONG
        )
        
        if response.status_code == 200:
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        else:
            raise Exception(f"Embedding API error: {response.status_code}")
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """异步调用API"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": texts
                },
                timeout=TIMEOUTS.HTTP_LONG
            )
            
            if response.status_code == 200:
                data = response.json()
                return [item["embedding"] for item in data["data"]]
            else:
                raise Exception(f"Embedding API error: {response.status_code}")


class NVIDIAEmbedding(EmbeddingProvider):
    """
    NVIDIA NeMo Retriever Embedding
    使用 NVIDIA API 生成高质量文本向量
    通过 OpenAI SDK 调用，更加稳定可靠
    """
    
    # NVIDIA 嵌入模型维度映射
    MODEL_DIMENSIONS = {
        "nvidia/llama-3.2-nemoretriever-300m-embed-v1": 2048,
        "nvidia/nv-embed-v1": 4096,
        "nvidia/nv-embedqa-e5-v5": 1024,
        "nvidia/nv-embedqa-mistral-7b-v2": 4096,
    }
    
    def __init__(
        self,
        api_key: str = "",
        model: str = "nvidia/llama-3.2-nemoretriever-300m-embed-v1",
        input_type: str = "query",
        truncate: str = "NONE"
    ):
        """
        初始化 NVIDIA Embedding
        
        Args:
            api_key: NVIDIA API密钥 (以 nvapi- 开头)
            model: 模型名称
            input_type: 输入类型 ("query" 或 "passage")
            truncate: 截断策略 ("NONE", "START", "END")
        """
        from openai import OpenAI
        
        self.api_base = "https://integrate.api.nvidia.com/v1"
        self.api_key = api_key
        self.model = model
        self.input_type = input_type
        self.truncate = truncate
        
        # 使用 OpenAI SDK 客户端
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.api_base
        )
        
        # 根据模型设置维度
        self._dimension = self.MODEL_DIMENSIONS.get(model, 2048)
        
        logger.info(f"NVIDIAEmbedding initialized: {model}, dim={self._dimension}")
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        """同步调用 NVIDIA API (使用 OpenAI SDK)"""
        try:
            response = self._client.embeddings.create(
                input=texts,
                model=self.model,
                encoding_format="float",
                extra_body={
                    "input_type": self.input_type,
                    "truncate": self.truncate
                }
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            error_msg = f"NVIDIA Embedding API error: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """异步调用 NVIDIA API (实际使用同步，因为 OpenAI SDK 同步更稳定)"""
        return self.embed_sync(texts)


class SimpleLocalEmbedding(EmbeddingProvider):
    """
    简单的本地Embedding（无需额外依赖）
    使用TF-IDF + 哈希技巧生成向量
    适合轻量级使用场景
    """
    
    def __init__(self, dimension: int = EMBEDDING_CONFIG.DIMENSION_RANDOM):
        self._dimension = dimension
        logger.info(f"SimpleLocalEmbedding initialized, dim={dimension}")
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def _hash_text(self, text: str) -> List[float]:
        """使用简单的哈希方法生成向量"""
        import hashlib
        
        # 分词
        words = text.lower().split()
        
        # 初始化向量
        vector = np.zeros(self._dimension)
        
        for word in words:
            # 使用hash确定位置
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            pos = h % self._dimension
            # 使用另一个hash确定符号
            sign = 1 if (h >> 1) % 2 == 0 else -1
            vector[pos] += sign
        
        # 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector.tolist()
    
    def embed_sync(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_text(text) for text in texts]
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        return self.embed_sync(texts)


# 全局实例
_embedding_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider(
    use_local: bool = True,
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    provider: str = "openai"
) -> EmbeddingProvider:
    """
    获取Embedding提供者
    
    Args:
        use_local: 是否使用本地模型
        api_base: API地址（use_local=False时）
        api_key: API密钥（use_local=False时）
        model: 模型名称
        provider: API提供商 ("openai", "nvidia", "siliconflow")
        
    Returns:
        Embedding提供者实例
    """
    global _embedding_provider
    
    if use_local:
        try:
            # 尝试使用sentence-transformers
            _embedding_provider = LocalEmbedding()
        except ImportError:
            # 降级到简单实现
            logger.warning("sentence-transformers not available, using simple embedding")
            _embedding_provider = SimpleLocalEmbedding()
    else:
        if provider.lower() == "nvidia":
            _embedding_provider = NVIDIAEmbedding(
                api_key=api_key,
                model=model or "nvidia/llama-3.2-nemoretriever-300m-embed-v1"
            )
        else:
            _embedding_provider = APIEmbedding(
                api_base=api_base,
                api_key=api_key,
                model=model
            )
    
    return _embedding_provider


# 模块职责说明：提供多种Embedding实现（本地模型/API），支持文本向量化功能。