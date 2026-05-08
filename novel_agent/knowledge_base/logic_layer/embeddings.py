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
from pathlib import Path
from typing import Any, Optional, Union
from dataclasses import dataclass

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from ..config import SiliconFlowConfig, NVIDIAConfig, LocalOnnxConfig

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
            "provider": "api",
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
            "provider": "nvidia",
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


class LocalOnnxEmbeddingService:
    """
    本地 ONNX 向量化服务。

    约定模型目录中包含 model.onnx 和 tokenizer.json，或提供可被
    transformers.AutoTokenizer 读取的 tokenizer 文件。
    """

    def __init__(
        self,
        config: Optional[LocalOnnxConfig] = None,
        *,
        session: Any = None,
        tokenizer: Any = None,
    ):
        self.config = config or LocalOnnxConfig()
        self._cache: dict[str, list[float]] = {}
        self._session = session
        self._tokenizer = tokenizer
        self._input_names: set[str] = set()

        self._validate_config(skip_files=bool(session and tokenizer))
        self._initialize_runtime()

    def _validate_config(self, *, skip_files: bool = False) -> None:
        if skip_files:
            return
        model_dir = Path(self.config.model_dir or "")
        model_path = model_dir / (self.config.model_file or "model.onnx")
        if not self.config.model_dir:
            raise ValueError("缺少本地 ONNX 模型目录，请设置 KB_ONNX_MODEL_DIR")
        if not model_path.exists():
            raise ValueError(f"本地 ONNX 模型文件不存在: {model_path}")

    def _initialize_runtime(self) -> None:
        if self._session is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise ImportError("onnxruntime 未安装，请运行: pip install onnxruntime") from exc

            model_path = Path(self.config.model_dir) / (self.config.model_file or "model.onnx")
            session_options = ort.SessionOptions()
            if self.config.threads:
                session_options.intra_op_num_threads = int(self.config.threads)
                session_options.inter_op_num_threads = int(self.config.threads)
            self._session = ort.InferenceSession(
                str(model_path),
                sess_options=session_options,
                providers=["CPUExecutionProvider"],
            )

        self._input_names = {getattr(item, "name", "") for item in self._session.get_inputs()}

        if self._tokenizer is None:
            tokenizer_dir = Path(self.config.tokenizer_dir or self.config.model_dir)
            tokenizer_json = tokenizer_dir / "tokenizer.json"
            if tokenizer_json.exists():
                try:
                    from tokenizers import Tokenizer
                except ImportError as exc:
                    raise ImportError("tokenizers 未安装，请运行: pip install tokenizers") from exc
                tokenizer = Tokenizer.from_file(str(tokenizer_json))
                tokenizer.enable_truncation(max_length=int(self.config.max_length))
                tokenizer.enable_padding()
                self._tokenizer = tokenizer
            else:
                try:
                    from transformers import AutoTokenizer
                except ImportError as exc:
                    raise ImportError(
                        "缺少 tokenizer.json，且 transformers 未安装；请安装 tokenizers 或 transformers"
                    ) from exc
                self._tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir))

        logger.info(
            "本地 ONNX 向量化服务初始化完成: model=%s, max_length=%s",
            self.config.model_name,
            self.config.max_length,
        )

    def embed(self, text: str, use_cache: bool = True) -> list[float]:
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        return self.embed_batch([text], use_cache=use_cache)[0]

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        use_cache: bool = True,
    ) -> list[list[float]]:
        if not texts:
            return []

        results: dict[int, list[float]] = {}
        pending: list[tuple[int, str]] = []
        for idx, text in enumerate(texts):
            clean = str(text or "").strip()
            if not clean:
                results[idx] = []
                continue
            cache_key = self._get_cache_key(clean)
            if use_cache and cache_key in self._cache:
                results[idx] = self._cache[cache_key]
                continue
            pending.append((idx, clean))

        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            batch_texts = [text for _, text in batch]
            embeddings = self._embed_uncached_batch(batch_texts)
            for (idx, text), embedding in zip(batch, embeddings):
                results[idx] = embedding
                if use_cache:
                    self._cache[self._get_cache_key(text)] = embedding

        return [results.get(i, []) for i in range(len(texts))]

    def _embed_uncached_batch(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        inputs = self._tokenize(texts)
        attention_mask = np.asarray(inputs.pop("__attention_mask"), dtype=np.float32)
        outputs = self._session.run(None, inputs)
        if not outputs:
            raise RuntimeError("ONNX embedding 模型未返回输出")

        hidden = np.asarray(outputs[0], dtype=np.float32)
        if hidden.ndim == 3:
            if str(self.config.pooling or "mean").lower() == "cls":
                pooled = hidden[:, 0, :]
            else:
                mask = np.expand_dims(attention_mask, axis=-1)
                summed = (hidden * mask).sum(axis=1)
                counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
                pooled = summed / counts
        elif hidden.ndim == 2:
            pooled = hidden
        else:
            pooled = hidden.reshape((hidden.shape[0], -1))

        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-12, a_max=None)
        normalized = pooled / norms
        self.config.embedding_dim = int(normalized.shape[1])
        return normalized.astype(float).tolist()

    def _tokenize(self, texts: list[str]) -> dict[str, Any]:
        import numpy as np

        if hasattr(self._tokenizer, "encode_batch"):
            encodings = self._tokenizer.encode_batch(texts)
            input_ids = [encoding.ids for encoding in encodings]
            attention_mask = [encoding.attention_mask for encoding in encodings]
            token_type_ids = [getattr(encoding, "type_ids", [0] * len(encoding.ids)) for encoding in encodings]
            arrays = {
                "input_ids": np.asarray(input_ids, dtype=np.int64),
                "attention_mask": np.asarray(attention_mask, dtype=np.int64),
                "token_type_ids": np.asarray(token_type_ids, dtype=np.int64),
            }
        else:
            arrays = self._tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=int(self.config.max_length),
                return_tensors="np",
            )

        feed: dict[str, Any] = {}
        for name, value in dict(arrays).items():
            if name in self._input_names:
                feed[name] = value
        if not feed:
            raise RuntimeError(f"无法匹配 ONNX 输入名: {sorted(self._input_names)}")
        if "attention_mask" in dict(arrays):
            feed["__attention_mask"] = dict(arrays)["attention_mask"]
        else:
            feed["__attention_mask"] = np.ones_like(feed["input_ids"], dtype=np.int64)
        return feed

    def _get_cache_key(self, text: str) -> str:
        content = f"{self.config.model_name}:{self.config.max_length}:{self.config.pooling}:{text}"
        return hashlib.md5(content.encode()).hexdigest()

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_size(self) -> int:
        return len(self._cache)

    def get_model_info(self) -> dict:
        return {
            "provider": "local_onnx",
            "model": self.config.model_name,
            "embedding_dim": self.config.embedding_dim,
            "model_dir": self.config.model_dir,
            "max_length": self.config.max_length,
        }

    def close(self):
        self._session = None


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

    def get_model_info(self) -> dict:
        return {
            "provider": "mock",
            "model": self.config.model,
            "embedding_dim": self.embedding_dim,
        }
