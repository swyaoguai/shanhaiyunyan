"""
向量化服务模块

调用硅基流动API进行文本向量化。
支持：
- 单文本/批量向量化
- 重试机制
- 缓存（可选）
"""

import logging
import time
import hashlib
from typing import Optional, Union
from dataclasses import dataclass

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from ..config import SiliconFlowConfig, NVIDIAConfig

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """向量化结果"""
    embedding: list[float]
    token_count: int
    model: str


class EmbeddingService:
    """
    向量化服务
    
    封装硅基流动API，提供文本向量化功能。
    """
    
    def __init__(self, config: Optional[SiliconFlowConfig] = None):
        """
        初始化向量化服务
        
        Args:
            config: 硅基流动API配置
        """
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx未安装，请运行: pip install httpx")
        
        self.config = config or SiliconFlowConfig()
        self._client: Optional[httpx.Client] = None
        self._cache: dict[str, list[float]] = {}  # 简单内存缓存
        
        self._validate_config()
        self._initialize_client()
    
    def _validate_config(self):
        """验证配置"""
        if not self.config.api_key:
            raise ValueError(
                "缺少硅基流动API密钥，请设置环境变量 SILICONFLOW_API_KEY "
                "或在配置中提供 api_key"
            )
    
    def _initialize_client(self):
        """初始化HTTP客户端"""
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.config.timeout
        )
        logger.info(f"向量化服务初始化完成: model={self.config.model}")
    
    def embed(
        self,
        text: str,
        use_cache: bool = True
    ) -> list[float]:
        """
        将单个文本转换为向量
        
        Args:
            text: 待向量化的文本
            use_cache: 是否使用缓存
        
        Returns:
            向量列表
        """
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        
        # 检查缓存
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                logger.debug(f"从缓存获取向量: {cache_key[:16]}...")
                return self._cache[cache_key]
        
        # 调用API
        result = self._call_api([text])
        embedding = result[0]
        
        # 存入缓存
        if use_cache:
            self._cache[cache_key] = embedding
        
        return embedding
    
    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        use_cache: bool = True
    ) -> list[list[float]]:
        """
        批量将文本转换为向量
        
        Args:
            texts: 待向量化的文本列表
            batch_size: 每批处理的数量
            use_cache: 是否使用缓存
        
        Returns:
            向量列表的列表
        """
        if not texts:
            return []
        
        # 过滤空文本
        valid_texts = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not valid_texts:
            return [[]] * len(texts)
        
        # 检查缓存，分离需要计算的文本
        results: dict[int, list[float]] = {}
        texts_to_embed: list[tuple[int, str]] = []
        
        for idx, text in valid_texts:
            if use_cache:
                cache_key = self._get_cache_key(text)
                if cache_key in self._cache:
                    results[idx] = self._cache[cache_key]
                    continue
            texts_to_embed.append((idx, text))
        
        # 批量处理未缓存的文本
        if texts_to_embed:
            for i in range(0, len(texts_to_embed), batch_size):
                batch = texts_to_embed[i:i + batch_size]
                batch_texts = [t for _, t in batch]
                batch_indices = [idx for idx, _ in batch]
                
                try:
                    embeddings = self._call_api(batch_texts)
                    
                    for idx, text, embedding in zip(batch_indices, batch_texts, embeddings):
                        results[idx] = embedding
                        if use_cache:
                            cache_key = self._get_cache_key(text)
                            self._cache[cache_key] = embedding
                            
                except Exception as e:
                    logger.error(f"批量向量化失败: {e}")
                    raise
        
        # 按原始顺序组装结果
        final_results = []
        for i in range(len(texts)):
            if i in results:
                final_results.append(results[i])
            else:
                final_results.append([])  # 空文本返回空向量
        
        return final_results
    
    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """
        调用硅基流动API
        
        Args:
            texts: 文本列表
        
        Returns:
            向量列表
        """
        payload = {
            "model": self.config.model,
            "input": texts,
            "encoding_format": "float"
        }
        
        # 如果配置了维度，添加到请求中
        if self.config.embedding_dim:
            payload["dimensions"] = self.config.embedding_dim
        
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                response = self._client.post("/embeddings", json=payload)
                response.raise_for_status()
                
                data = response.json()
                
                # 解析响应
                embeddings = []
                for item in sorted(data["data"], key=lambda x: x["index"]):
                    embeddings.append(item["embedding"])
                
                logger.debug(f"API调用成功: {len(texts)}个文本, "
                           f"token使用: {data.get('usage', {}).get('total_tokens', 'N/A')}")
                
                return embeddings
                
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"API调用失败 (尝试 {attempt + 1}/{self.config.max_retries}): "
                             f"状态码 {e.response.status_code}")
                
                # 处理特定错误
                if e.response.status_code == 401:
                    raise ValueError("API密钥无效或已过期") from e
                elif e.response.status_code == 429:
                    # 速率限制，等待后重试
                    wait_time = min(2 ** attempt, 60)
                    logger.info(f"触发速率限制，等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                elif e.response.status_code >= 500:
                    # 服务器错误，等待后重试
                    time.sleep(1)
                else:
                    raise
                    
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"API调用超时 (尝试 {attempt + 1}/{self.config.max_retries})")
                time.sleep(1)
                
            except Exception as e:
                last_error = e
                logger.error(f"API调用异常: {e}")
                raise
        
        raise RuntimeError(f"API调用失败，已重试{self.config.max_retries}次") from last_error
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用文本的MD5哈希作为缓存键
        content = f"{self.config.model}:{self.config.embedding_dim}:{text}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def clear_cache(self) -> int:
        """
        清空缓存
        
        Returns:
            清空的缓存条目数
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"已清空 {count} 条缓存")
        return count
    
    def get_cache_size(self) -> int:
        """返回缓存条目数"""
        return len(self._cache)
    
    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            "model": self.config.model,
            "embedding_dim": self.config.embedding_dim,
            "max_tokens": self.config.max_tokens,
            "base_url": self.config.base_url,
        }
    
    def close(self):
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class NVIDIAEmbeddingService:
    """
    NVIDIA NeMo Retriever 向量化服务
    
    使用 OpenAI SDK 调用 NVIDIA API 生成高质量文本向量。
    """
    
    # NVIDIA 嵌入模型维度映射
    MODEL_DIMENSIONS = {
        "nvidia/llama-3.2-nemoretriever-300m-embed-v1": 2048,
        "nvidia/nv-embed-v1": 4096,
        "nvidia/nv-embedqa-e5-v5": 1024,
        "nvidia/nv-embedqa-mistral-7b-v2": 4096,
    }
    
    def __init__(self, config: Optional[NVIDIAConfig] = None):
        """
        初始化 NVIDIA 向量化服务
        
        Args:
            config: NVIDIA API配置
        """
        self.config = config or NVIDIAConfig()
        self._cache: dict[str, list[float]] = {}
        
        self._validate_config()
        self._initialize_client()
    
    def _validate_config(self):
        """验证配置"""
        if not self.config.api_key:
            raise ValueError(
                "缺少NVIDIA API密钥，请设置环境变量 NVIDIA_API_KEY "
                "或在配置中提供 api_key"
            )
    
    def _initialize_client(self):
        """初始化 OpenAI SDK 客户端"""
        from openai import OpenAI
        
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        # 更新维度
        self.config.embedding_dim = self.MODEL_DIMENSIONS.get(
            self.config.model, 2048
        )
        
        logger.info(f"NVIDIA向量化服务初始化完成: model={self.config.model}, dim={self.config.embedding_dim}")
    
    def embed(
        self,
        text: str,
        use_cache: bool = True,
        input_type: Optional[str] = None
    ) -> list[float]:
        """
        将单个文本转换为向量
        
        Args:
            text: 待向量化的文本
            use_cache: 是否使用缓存
            input_type: 输入类型 ("query" 或 "passage")，默认使用配置值
        
        Returns:
            向量列表
        """
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        
        effective_input_type = input_type or self.config.input_type
        
        # 检查缓存
        if use_cache:
            cache_key = self._get_cache_key(text, effective_input_type)
            if cache_key in self._cache:
                logger.debug(f"从缓存获取向量: {cache_key[:16]}...")
                return self._cache[cache_key]
        
        # 调用API
        result = self._call_api([text], effective_input_type)
        embedding = result[0]
        
        # 存入缓存
        if use_cache:
            self._cache[cache_key] = embedding
        
        return embedding
    
    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        use_cache: bool = True,
        input_type: Optional[str] = None
    ) -> list[list[float]]:
        """
        批量将文本转换为向量
        
        Args:
            texts: 待向量化的文本列表
            batch_size: 每批处理的数量
            use_cache: 是否使用缓存
            input_type: 输入类型 ("query" 或 "passage")
        
        Returns:
            向量列表的列表
        """
        if not texts:
            return []
        
        effective_input_type = input_type or self.config.input_type
        
        # 过滤空文本
        valid_texts = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not valid_texts:
            return [[]] * len(texts)
        
        # 检查缓存，分离需要计算的文本
        results: dict[int, list[float]] = {}
        texts_to_embed: list[tuple[int, str]] = []
        
        for idx, text in valid_texts:
            if use_cache:
                cache_key = self._get_cache_key(text, effective_input_type)
                if cache_key in self._cache:
                    results[idx] = self._cache[cache_key]
                    continue
            texts_to_embed.append((idx, text))
        
        # 批量处理未缓存的文本
        if texts_to_embed:
            for i in range(0, len(texts_to_embed), batch_size):
                batch = texts_to_embed[i:i + batch_size]
                batch_texts = [t for _, t in batch]
                batch_indices = [idx for idx, _ in batch]
                
                try:
                    embeddings = self._call_api(batch_texts, effective_input_type)
                    
                    for idx, text, embedding in zip(batch_indices, batch_texts, embeddings):
                        results[idx] = embedding
                        if use_cache:
                            cache_key = self._get_cache_key(text, effective_input_type)
                            self._cache[cache_key] = embedding
                            
                except Exception as e:
                    logger.error(f"批量向量化失败: {e}")
                    raise
        
        # 按原始顺序组装结果
        final_results = []
        for i in range(len(texts)):
            if i in results:
                final_results.append(results[i])
            else:
                final_results.append([])
        
        return final_results
    
    def _call_api(self, texts: list[str], input_type: str) -> list[list[float]]:
        """
        调用NVIDIA API (使用 OpenAI SDK)
        
        Args:
            texts: 文本列表
            input_type: 输入类型
        
        Returns:
            向量列表
        """
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                response = self._client.embeddings.create(
                    input=texts,
                    model=self.config.model,
                    encoding_format="float",
                    extra_body={
                        "input_type": input_type,
                        "truncate": self.config.truncate
                    }
                )
                
                embeddings = [item.embedding for item in response.data]
                
                logger.debug(f"NVIDIA API调用成功: {len(texts)}个文本, "
                           f"token使用: {response.usage.total_tokens if response.usage else 'N/A'}")
                
                return embeddings
                
            except Exception as e:
                last_error = e
                error_str = str(e)
                logger.warning(f"NVIDIA API调用失败 (尝试 {attempt + 1}/{self.config.max_retries}): {error_str}")
                
                if "401" in error_str:
                    raise ValueError("NVIDIA API密钥无效或已过期") from e
                elif "429" in error_str:
                    wait_time = min(2 ** attempt, 60)
                    logger.info(f"触发速率限制，等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                elif "500" in error_str or "502" in error_str or "503" in error_str:
                    time.sleep(1)
                else:
                    if attempt == self.config.max_retries - 1:
                        raise
                    time.sleep(1)
        
        raise RuntimeError(f"NVIDIA API调用失败，已重试{self.config.max_retries}次") from last_error
    
    def _get_cache_key(self, text: str, input_type: str) -> str:
        """生成缓存键"""
        content = f"{self.config.model}:{input_type}:{text}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def clear_cache(self) -> int:
        """清空缓存"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"已清空 {count} 条缓存")
        return count
    
    def get_cache_size(self) -> int:
        """返回缓存条目数"""
        return len(self._cache)
    
    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            "model": self.config.model,
            "embedding_dim": self.config.embedding_dim,
            "input_type": self.config.input_type,
            "base_url": self.config.base_url,
        }
    
    def close(self):
        """关闭客户端"""
        self._client = None
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MockEmbeddingService(EmbeddingService):
    """
    模拟向量化服务
    
    用于测试，不需要真实的API调用。
    """
    
    def __init__(self, embedding_dim: int = 1024):
        """
        初始化模拟服务
        
        Args:
            embedding_dim: 向量维度
        """
        self.embedding_dim = embedding_dim
        self._cache = {}
        # 创建模拟配置
        self.config = SiliconFlowConfig(
            api_key="mock_key",
            model="mock_model",
            embedding_dim=embedding_dim
        )
        logger.info(f"使用模拟向量化服务: dim={embedding_dim}")
    
    def _validate_config(self):
        pass
    
    def _initialize_client(self):
        pass
    
    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """生成模拟向量"""
        import random
        
        embeddings = []
        for text in texts:
            # 使用文本哈希作为随机种子，保证相同文本生成相同向量
            seed = hash(text) % (2 ** 32)
            random.seed(seed)
            embedding = [random.random() for _ in range(self.embedding_dim)]
            # 归一化
            norm = sum(x ** 2 for x in embedding) ** 0.5
            embedding = [x / norm for x in embedding]
            embeddings.append(embedding)
        
        return embeddings
    
    def close(self):
        pass