"""Runtime helpers for project-scoped knowledge-base instances."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import get_data_dir
from .knowledge_base.config import KnowledgeBaseConfig

logger = logging.getLogger(__name__)


def knowledge_base_config_path(data_dir: Optional[Path] = None) -> Path:
    """Return the persisted knowledge-base settings path."""

    return Path(data_dir or get_data_dir()) / "knowledge_base_config.json"


def load_knowledge_base_settings(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load saved knowledge-base settings, returning an empty dict on failure."""

    path = knowledge_base_config_path(data_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"[KnowledgeRuntime] Failed to load knowledge settings: {exc}")
        return {}


def has_embedding_config(settings: Optional[Dict[str, Any]] = None) -> bool:
    """Whether the settings/env contain enough information to build embeddings."""

    payload = settings or {}
    provider = str(
        payload.get("embedding_provider")
        or os.getenv("KB_EMBEDDING_PROVIDER")
        or os.getenv("EMBEDDING_PROVIDER")
        or "api"
    ).lower()
    if provider in {"local", "local_onnx"}:
        model_dir = str(payload.get("onnx_model_dir") or os.getenv("KB_ONNX_MODEL_DIR") or "").strip()
        return bool(model_dir)
    if provider == "nvidia":
        return bool(str(payload.get("nvidia_api_key") or os.getenv("NVIDIA_API_KEY") or "").strip())
    return bool(str(payload.get("siliconflow_api_key") or os.getenv("SILICONFLOW_API_KEY") or "").strip())


def build_knowledge_base_config(
    project_id: str,
    *,
    settings: Optional[Dict[str, Any]] = None,
    data_dir: Optional[Path] = None,
) -> KnowledgeBaseConfig:
    """Build a KnowledgeBaseConfig from saved settings plus environment fallback."""

    payload = dict(settings or load_knowledge_base_settings(data_dir))
    config = KnowledgeBaseConfig.from_env(project_id=project_id)

    if data_dir:
        config.data_dir = str(Path(data_dir) / "knowledge_base")
        config.__post_init__()

    provider = str(payload.get("embedding_provider") or config.embedding_provider or "api").lower()
    config.embedding_provider = provider

    if "siliconflow_api_key" in payload:
        config.siliconflow.api_key = str(payload.get("siliconflow_api_key") or "")
    if payload.get("siliconflow_base_url"):
        config.siliconflow.base_url = str(payload.get("siliconflow_base_url"))
    if payload.get("siliconflow_model"):
        config.siliconflow.model = str(payload.get("siliconflow_model"))
    if payload.get("siliconflow_embedding_dim"):
        try:
            config.siliconflow.embedding_dim = int(payload.get("siliconflow_embedding_dim"))
        except (TypeError, ValueError):
            pass

    if payload.get("onnx_model_dir"):
        config.local_onnx.model_dir = str(payload.get("onnx_model_dir"))
    if payload.get("onnx_model_file"):
        config.local_onnx.model_file = str(payload.get("onnx_model_file"))
    if payload.get("onnx_tokenizer_dir"):
        config.local_onnx.tokenizer_dir = str(payload.get("onnx_tokenizer_dir"))
    if payload.get("onnx_max_length"):
        try:
            config.local_onnx.max_length = int(payload.get("onnx_max_length"))
        except (TypeError, ValueError):
            pass
    if payload.get("onnx_threads") not in (None, ""):
        try:
            config.local_onnx.threads = int(payload.get("onnx_threads"))
        except (TypeError, ValueError):
            pass
    if payload.get("onnx_pooling"):
        config.local_onnx.pooling = str(payload.get("onnx_pooling"))

    if payload.get("chunk_size"):
        try:
            config.chunking.chunk_size = int(payload.get("chunk_size"))
        except (TypeError, ValueError):
            pass
    if payload.get("chunk_overlap") is not None:
        try:
            config.chunking.chunk_overlap = int(payload.get("chunk_overlap"))
        except (TypeError, ValueError):
            pass
    if payload.get("default_top_k"):
        try:
            config.retrieval.default_top_k = int(payload.get("default_top_k"))
        except (TypeError, ValueError):
            pass
    if payload.get("vector_weight") is not None:
        try:
            config.retrieval.vector_weight = float(payload.get("vector_weight"))
        except (TypeError, ValueError):
            pass
    if payload.get("fulltext_weight") is not None:
        try:
            config.retrieval.fulltext_weight = float(payload.get("fulltext_weight"))
        except (TypeError, ValueError):
            pass
    if payload.get("chapter_search_mode"):
        config.retrieval.chapter_search_mode = str(payload.get("chapter_search_mode"))
    if "summary_search_enabled" in payload:
        config.retrieval.summary_search.enabled = bool(payload.get("summary_search_enabled"))

    return config


def create_project_knowledge_base(
    project_id: str,
    *,
    data_dir: Optional[Path] = None,
    use_mock_embeddings: bool = False,
):
    """Create a project KnowledgeBase using saved settings when present."""

    settings = load_knowledge_base_settings(data_dir)
    if not use_mock_embeddings and not has_embedding_config(settings):
        raise ValueError("知识库向量 provider 未配置")

    from .knowledge_base import KnowledgeBase

    config = build_knowledge_base_config(project_id, settings=settings, data_dir=data_dir)
    return KnowledgeBase(project_id=project_id, config=config, use_mock_embeddings=use_mock_embeddings)


def sync_knowledge_runtime_to_router(project_id: str, *, data_dir: Optional[Path] = None) -> bool:
    """Refresh the in-memory router/coordinator knowledge-base instance."""

    try:
        kb = create_project_knowledge_base(project_id, data_dir=data_dir, use_mock_embeddings=False)
    except Exception as exc:
        logger.info(f"[KnowledgeRuntime] Knowledge runtime not ready: {exc}")
        return False

    try:
        from .web.dependencies import get_coordinator, get_router_agent

        router_agent = get_router_agent()
        old_kbs = []
        for owner in (router_agent, get_coordinator()):
            old_kb = getattr(owner, "knowledge_base", None) if owner is not None else None
            if old_kb is not None and old_kb is not kb and old_kb not in old_kbs:
                old_kbs.append(old_kb)

        if router_agent and hasattr(router_agent, "set_knowledge_base"):
            router_agent.set_knowledge_base(kb)

        coordinator = get_coordinator()
        if coordinator and hasattr(coordinator, "set_knowledge_base"):
            coordinator.set_knowledge_base(kb)
        for old_kb in old_kbs:
            close = getattr(old_kb, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return True
    except Exception as exc:
        logger.warning(f"[KnowledgeRuntime] Failed to refresh runtime KB: {exc}")
        return False
