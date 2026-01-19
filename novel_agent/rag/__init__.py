"""
RAG检索模块
提供向量存储和语义检索功能
"""

from .embeddings import EmbeddingProvider, LocalEmbedding, APIEmbedding, get_embedding_provider
from .vector_store import SimpleVectorStore, SearchResult
from .retriever import NovelRetriever

__all__ = [
    "EmbeddingProvider",
    "LocalEmbedding", 
    "APIEmbedding",
    "get_embedding_provider",
    "SimpleVectorStore",
    "SearchResult",
    "NovelRetriever"
]
