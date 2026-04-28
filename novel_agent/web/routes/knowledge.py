"""
知识库API路由模块

包含知识库配置、测试、文件导入、统计和清理等功能。
"""

import os
import json
import time
import httpx
import shutil
import sqlite3
import datetime
import logging
import re
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ...constants import SERVER_DEFAULTS
from ...utils.atomic_write import atomic_write_text
from ..models.requests import (
    KnowledgeBaseConfigRequest,
    TestEmbeddingRequest,
    ImportFileRequest,
    CreateCategoryRequest,
    ClearKnowledgeBaseRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _sanitize_summary_text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(normalized) > 8000:
        normalized = normalized[:8000].rstrip()
    return normalized


def _build_summary_title(summary: str, start_chapter: int, end_chapter: int) -> str:
    first_line = (summary.splitlines()[0] if summary else "").strip()
    if first_line:
        first_line = re.sub(r"\s+", " ", first_line)
        first_line = first_line[:40]
    range_part = f"第{start_chapter}-{end_chapter}章"
    return f"剧情总结 {range_part}" + (f" - {first_line}" if first_line else "")


def _atomic_write_text(path: Path, content: str, old_content: str = None) -> None:
    """原子写入文本文件（临时文件替换，失败时可回滚）"""
    try:
        atomic_write_text(path, content, old_content=old_content)
    except Exception as exc:
        logger.error(f"[Knowledge] 原子写入失败: {exc}")
        raise


@router.get("/knowledge-base/config")
async def get_knowledge_base_config():
    """获取知识库配置"""
    config_path = Path(__file__).parent.parent.parent / "data" / "knowledge_base_config.json"
    
    default_config = {
        "siliconflow_api_key": os.getenv("SILICONFLOW_API_KEY", ""),
        "siliconflow_base_url": os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
        "siliconflow_model": os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3"),
        "siliconflow_embedding_dim": int(os.getenv("SILICONFLOW_EMBEDDING_DIM", "1024")),
        "chunk_size": 500,
        "chunk_overlap": 50,
        "vector_weight": 0.7,
        "fulltext_weight": 0.3,
        "default_top_k": 5,
        # 检索策略配置
        "summary_search_enabled": False,  # 摘要索引检索（无向量RAG）
        "chapter_search_mode": "hybrid"   # 章节检索模式
    }
    
    if config_path.exists():
        try:
            saved_config = json.loads(config_path.read_text(encoding="utf-8"))
            default_config.update(saved_config)
        except Exception as e:
            logger.warning(f"[Knowledge] 读取知识库配置失败，使用默认值: {e}")
    
    api_key = default_config.get("siliconflow_api_key", "")
    return JSONResponse({
        "siliconflow_api_key": api_key[:8] + "****" if len(api_key) > 8 else "",
        "siliconflow_api_key_set": bool(api_key),
        "siliconflow_base_url": default_config.get("siliconflow_base_url", ""),
        "siliconflow_model": default_config.get("siliconflow_model", ""),
        "siliconflow_embedding_dim": default_config.get("siliconflow_embedding_dim", 1024),
        "chunk_size": default_config.get("chunk_size", 500),
        "chunk_overlap": default_config.get("chunk_overlap", 50),
        "vector_weight": default_config.get("vector_weight", 0.7),
        "fulltext_weight": default_config.get("fulltext_weight", 0.3),
        "default_top_k": default_config.get("default_top_k", 5),
        "is_configured": bool(api_key),
        # 检索策略配置
        "summary_search_enabled": default_config.get("summary_search_enabled", False),
        "chapter_search_mode": default_config.get("chapter_search_mode", "hybrid")
    })


@router.post("/knowledge-base/config")
async def save_knowledge_base_config(request: KnowledgeBaseConfigRequest):
    """保存知识库配置"""
    config_path = Path(__file__).parent.parent.parent / "data" / "knowledge_base_config.json"
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    
    existing_config = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Knowledge] 读取现有知识库配置失败: {e}")
    
    api_key = request.siliconflow_api_key
    if api_key.endswith("****"):
        api_key = existing_config.get("siliconflow_api_key", "")
    
    new_config = {
        "siliconflow_api_key": api_key,
        "siliconflow_base_url": request.siliconflow_base_url,
        "siliconflow_model": request.siliconflow_model,
        "siliconflow_embedding_dim": request.siliconflow_embedding_dim,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
        "vector_weight": request.vector_weight,
        "fulltext_weight": request.fulltext_weight,
        "default_top_k": request.default_top_k,
        # 检索策略配置
        "summary_search_enabled": request.summary_search_enabled,
        "chapter_search_mode": request.chapter_search_mode
    }
    
    config_path.parent.mkdir(parents=True, exist_ok=True)

    old_config_content = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    old_env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else None

    try:
        _atomic_write_text(
            config_path,
            json.dumps(new_config, ensure_ascii=False, indent=2),
            old_content=old_config_content
        )

        # 更新.env文件
        env_content = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_content[key.strip()] = value.strip()

        if api_key:
            env_content["SILICONFLOW_API_KEY"] = api_key
        env_content["SILICONFLOW_BASE_URL"] = request.siliconflow_base_url
        env_content["SILICONFLOW_EMBEDDING_MODEL"] = request.siliconflow_model
        env_content["SILICONFLOW_EMBEDDING_DIM"] = str(request.siliconflow_embedding_dim)

        # 保留已有无关键，避免全量覆写导致环境变量丢失
        env_content.setdefault("OPENAI_API_KEY", "")
        env_content.setdefault("OPENAI_API_BASE", "")
        env_content.setdefault("OPENAI_MODEL", "gpt-4")
        env_content.setdefault("SILICONFLOW_API_KEY", "")
        env_content.setdefault("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        env_content.setdefault("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
        env_content.setdefault("SILICONFLOW_EMBEDDING_DIM", "1024")
        env_content.setdefault("HOST", "0.0.0.0")
        env_content.setdefault("PORT", str(SERVER_DEFAULTS.PORT))
        env_content.setdefault("DEBUG", "false")
        env_content.setdefault("MAX_TOKENS", "4096")
        env_content.setdefault("TEMPERATURE", "0.7")

        lines = [f"{k}={v}" for k, v in env_content.items()]
        _atomic_write_text(env_path, "\n".join(lines), old_content=old_env_content)

        return JSONResponse({"success": True, "message": "知识库配置已保存"})
    except Exception as e:
        logger.error(f"[Knowledge] 保存知识库配置失败: {e}")
        return JSONResponse({
            "success": False,
            "error": f"保存失败: {e}"
        }, status_code=500)


@router.post("/knowledge-base/test-embedding")
async def test_embedding_connection(request: TestEmbeddingRequest = None):
    """测试向量化服务连接"""
    config_path = Path(__file__).parent.parent.parent / "data" / "knowledge_base_config.json"
    
    is_masked = False
    if request and request.api_key:
        masked_patterns = ["••••••••", "********", "****"]
        is_masked = any(request.api_key.endswith(p) or request.api_key == p for p in masked_patterns)
    
    if request and request.api_key and not is_masked:
        api_key = request.api_key
        base_url = request.api_base or "https://api.siliconflow.cn/v1"
        model = request.model or "BAAI/bge-m3"
    else:
        api_key = os.getenv("SILICONFLOW_API_KEY", "")
        base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        model = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
        
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                api_key = config.get("siliconflow_api_key", api_key)
                base_url = config.get("siliconflow_base_url", base_url)
                model = config.get("siliconflow_model", model)
            except Exception as e:
                logger.warning(f"[Knowledge] 加载知识库配置失败: {e}")
    
    if not api_key:
        return JSONResponse({
            "success": False,
            "error": "未配置硅基流动API密钥"
        })
    
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "input": ["测试文本"],
                    "encoding_format": "float"
                }
            )
            
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                data = response.json()
                embedding_dim = len(data.get("data", [{}])[0].get("embedding", []))
                return JSONResponse({
                    "success": True,
                    "message": "向量化服务连接成功！",
                    "model": model,
                    "embedding_dim": embedding_dim,
                    "response_time": response_time
                })
            elif response.status_code == 401:
                return JSONResponse({
                    "success": False,
                    "error": "API密钥无效或已过期"
                })
            else:
                return JSONResponse({
                    "success": False,
                    "error": f"请求失败 (HTTP {response.status_code}): {response.text[:200]}"
                })
                
    except httpx.TimeoutException:
        return JSONResponse({
            "success": False,
            "error": "连接超时，请检查网络或API地址"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"连接失败: {str(e)}"
        })


@router.post("/knowledge-base/import-file")
async def import_file_to_knowledge(request: ImportFileRequest):
    """导入文件到资料库"""
    import re
    
    try:
        filename = request.filename
        title = request.title or filename.rsplit('.', 1)[0] if '.' in filename else filename
        content = request.content
        
        if request.split_mode == "paragraph":
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            items = []
            for i, para in enumerate(paragraphs):
                if len(para) > 20:
                    items.append({
                        "id": f"{int(time.time() * 1000)}_{i}",
                        "name": f"{title} - 片段{i+1}",
                        "description": para[:100] + "..." if len(para) > 100 else para,
                        "details": para,
                        "source_file": filename,
                        "created_at": datetime.datetime.now().isoformat()
                    })
            return JSONResponse({
                "success": True,
                "items": items,
                "count": len(items),
                "message": f"已解析 {len(items)} 个段落"
            })
        elif request.split_mode == "chapter":
            chapter_pattern = r'(?:^|\n)(#{1,3}\s+.+|第[一二三四五六七八九十百千万\d]+章.*)(?:\n|$)'
            parts = re.split(chapter_pattern, content)
            
            items = []
            current_title = title
            current_content = ""
            
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                
                if re.match(r'^#{1,3}\s+', part) or re.match(r'^第[一二三四五六七八九十百千万\d]+章', part):
                    if current_content:
                        items.append({
                            "id": f"{int(time.time() * 1000)}_{len(items)}",
                            "name": current_title,
                            "description": current_content[:100] + "..." if len(current_content) > 100 else current_content,
                            "details": current_content,
                            "source_file": filename,
                            "created_at": datetime.datetime.now().isoformat()
                        })
                    current_title = part.lstrip('#').strip()
                    current_content = ""
                else:
                    current_content += part + "\n"
            
            if current_content:
                items.append({
                    "id": f"{int(time.time() * 1000)}_{len(items)}",
                    "name": current_title,
                    "description": current_content[:100] + "..." if len(current_content) > 100 else current_content,
                    "details": current_content.strip(),
                    "source_file": filename,
                    "created_at": datetime.datetime.now().isoformat()
                })
            
            return JSONResponse({
                "success": True,
                "items": items,
                "count": len(items),
                "message": f"已解析 {len(items)} 个章节"
            })
        else:
            item = {
                "id": str(int(time.time() * 1000)),
                "name": title,
                "description": content[:200] + "..." if len(content) > 200 else content,
                "details": content,
                "source_file": filename,
                "created_at": datetime.datetime.now().isoformat()
            }
            return JSONResponse({
                "success": True,
                "items": [item],
                "count": 1,
                "message": f"已导入文件: {filename}"
            })
            
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}",
            "items": [],
            "count": 0
        })


@router.post("/knowledge-base/infinite-summary")
async def save_infinite_summary(request: dict):
    """保存无限续写阶段剧情总结到知识库。"""
    from ...project_manager import get_project_manager

    pm = get_project_manager()
    project_id = pm.current_project_id
    if not project_id:
        return JSONResponse({"success": False, "error": "请先选择一个项目"}, status_code=400)

    summary_text = _sanitize_summary_text(str(request.get("summary", "")))
    if not summary_text:
        return JSONResponse({"success": False, "error": "summary 不能为空"}, status_code=400)

    try:
        start_chapter = int(request.get("start_chapter", 0))
    except (TypeError, ValueError):
        start_chapter = 0
    try:
        end_chapter = int(request.get("end_chapter", 0))
    except (TypeError, ValueError):
        end_chapter = 0

    if start_chapter <= 0 or end_chapter <= 0 or end_chapter < start_chapter:
        return JSONResponse({"success": False, "error": "章节区间非法"}, status_code=400)

    chapter_title = _build_summary_title(summary_text, start_chapter, end_chapter)
    chapter_id = str(request.get("chapter_id", "")).strip()
    if not chapter_id:
        chapter_id = f"iw_summary_{start_chapter}_{end_chapter}_{int(time.time())}"

    metadata = {
        "type": "infinite_summary",
        "source": "infinite_write",
        "start_chapter": start_chapter,
        "end_chapter": end_chapter,
        "created_at": datetime.datetime.now().isoformat(),
    }

    config_path = Path(__file__).parent.parent.parent / "data" / "knowledge_base_config.json"
    has_api_key = False
    if config_path.exists():
        try:
            kb_config = json.loads(config_path.read_text(encoding="utf-8"))
            has_api_key = bool((kb_config.get("siliconflow_api_key") or "").strip())
        except Exception as e:
            logger.warning(f"[Knowledge] 读取知识库配置失败: {e}")

    if not has_api_key:
        return JSONResponse(
            {
                "success": False,
                "error": "知识库向量API未配置，剧情总结存储暂不可用",
                "not_ready": True,
            },
            status_code=503,
        )

    try:
        from ...knowledge_base import KnowledgeBase

        kb = KnowledgeBase(project_id=project_id, use_mock_embeddings=False)
        result = kb.add_chapter(
            chapter_id=chapter_id,
            title=chapter_title,
            content=summary_text,
            chapter_number=end_chapter,
            metadata=metadata,
        )
        kb.close()

        return JSONResponse({
            "success": True,
            "chapter_id": chapter_id,
            "title": chapter_title,
            "stored_chunks": getattr(result, "chunk_count", 0),
            "message": "剧情总结已写入知识库",
        })
    except Exception as e:
        logger.error(f"[Knowledge] 保存无限续写总结失败: {e}")
        return JSONResponse({"success": False, "error": f"保存失败: {e}"}, status_code=500)


@router.post("/knowledge-base/categories")
async def create_knowledge_category(request: CreateCategoryRequest):
    """创建新的资料分类"""
    category_id = f"db-custom-{int(time.time() * 1000)}"
    category_key = f"custom_{int(time.time() * 1000)}"
    
    return JSONResponse({
        "success": True,
        "category": {
            "id": category_id,
            "key": category_key,
            "name": request.name,
            "icon": request.icon,
            "builtin": False
        }
    })


@router.get("/knowledge-base/search")
async def search_knowledge_nodes(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50), node_type: str | None = None):
    """搜索知识节点。"""
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择一个项目"}, status_code=400)
    try:
        from ...knowledge_base import KnowledgeBase
        kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=True)
        results = kb.knowledge_api.search_nodes(q, limit=limit, node_type=node_type)
        kb.close()
        return JSONResponse({"success": True, "results": results, "count": len(results)})
    except Exception as e:
        logger.error(f"[Knowledge] 搜索知识节点失败: {e}")
        return JSONResponse({"success": False, "error": f"搜索失败: {e}"}, status_code=500)


@router.get("/knowledge-base/node/{node_id}")
async def get_knowledge_node(node_id: str):
    """获取知识节点详情。"""
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择一个项目"}, status_code=400)
    try:
        from ...knowledge_base import KnowledgeBase
        kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=True)
        node = kb.knowledge_api.get_node(node_id)
        neighbors = kb.knowledge_api.get_node_neighbors(node_id)
        kb.close()
        if not node:
            return JSONResponse({"success": False, "error": "节点不存在"}, status_code=404)
        return JSONResponse({"success": True, "node": node, "neighbors": neighbors})
    except Exception as e:
        logger.error(f"[Knowledge] 获取知识节点失败: {e}")
        return JSONResponse({"success": False, "error": f"获取失败: {e}"}, status_code=500)


@router.post("/knowledge-base/update-node")
async def update_knowledge_node(payload: dict):
    """更新知识节点。"""
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    if not pm.current_project_id:
        return JSONResponse({"success": False, "error": "请先选择一个项目"}, status_code=400)
    node_id = str(payload.get("node_id") or "").strip()
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    metadata = payload.get("metadata") or {}
    if not node_id or not title:
        return JSONResponse({"success": False, "error": "缺少节点ID或标题"}, status_code=400)
    try:
        from ...knowledge_base import KnowledgeBase
        kb = KnowledgeBase(project_id=pm.current_project_id, use_mock_embeddings=True)
        existing = kb.knowledge_api.get_node(node_id)
        if not existing:
            kb.close()
            return JSONResponse({"success": False, "error": "节点不存在"}, status_code=404)
        existing_meta = existing.get("metadata") or {}
        if isinstance(metadata, dict):
            existing_meta.update(metadata)
        existing_meta["summary_text"] = summary
        existing_meta["title"] = title
        existing_meta["links"] = existing.get("links_out", [])
        result = kb.knowledge_api.update_chapter(node_id, title=title, metadata=existing_meta)
        kb.close()
        return JSONResponse({"success": result.success, "node_id": node_id, "error": result.error})
    except Exception as e:
        logger.error(f"[Knowledge] 更新知识节点失败: {e}")
        return JSONResponse({"success": False, "error": f"更新失败: {e}"}, status_code=500)


@router.get("/knowledge-base/stats")
async def get_knowledge_base_stats():
    """获取知识库统计信息"""
    from ...project_manager import get_project_manager
    pm = get_project_manager()
    
    if not pm.current_project_id:
        return JSONResponse({
            "configured": False,
            "message": "请先选择一个项目"
        })
    
    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
    
    stats = {
        "configured": False,
        "project_id": pm.current_project_id,
        "chapter_count": 0,
        "chunk_count": 0,
        "vector_count": 0,
        "storage_size_mb": 0,
        "chapters": []
    }
    
    if data_dir.exists():
        stats["configured"] = True
        
        total_size = 0
        for f in data_dir.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
        stats["storage_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        db_path = data_dir / "knowledge.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chapters'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM chapters")
                    stats["chapter_count"] = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT chapter_id, title, chapter_number FROM chapters ORDER BY chapter_number")
                    stats["chapters"] = [
                        {"chapter_id": row[0], "title": row[1], "chapter_number": row[2]}
                        for row in cursor.fetchall()
                    ]
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM chunks")
                    stats["chunk_count"] = cursor.fetchone()[0]
                
                conn.close()
            except Exception as e:
                logger.warning(f"[Knowledge] 获取知识库统计信息失败: {e}")
        
        chroma_dir = data_dir / "chroma"
        if chroma_dir.exists():
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(chroma_dir))
                collection = client.get_or_create_collection("novel_knowledge")
                stats["vector_count"] = collection.count()
            except Exception as e:
                logger.warning(f"[Knowledge] 统计向量数量失败(可忽略): {e}")
    
    return JSONResponse(stats)


@router.post("/knowledge-base/clear")
async def clear_knowledge_base(request: ClearKnowledgeBaseRequest):
    """清除知识库数据"""
    from ...project_manager import get_project_manager
    import logging
    logger = logging.getLogger(__name__)
    
    pm = get_project_manager()
    
    if not pm.current_project_id:
        return JSONResponse({
            "success": False,
            "error": "请先选择一个项目"
        })
    
    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
    
    if not data_dir.exists():
        return JSONResponse({
            "success": True,
            "message": "知识库为空，无需清除"
        })
    
    try:
        if request.clear_all:
            shutil.rmtree(data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)
            
            return JSONResponse({
                "success": True,
                "message": f"已清除项目 {pm.current_project_id} 的所有知识库数据"
            })
        
        elif request.chapter_ids:
            deleted_count = 0
            db_path = data_dir / "knowledge.db"
            chroma_dir = data_dir / "chroma"
            
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                for chapter_id in request.chapter_ids:
                    cursor.execute("DELETE FROM chapters WHERE chapter_id = ?", (chapter_id,))
                    cursor.execute("DELETE FROM chunks WHERE chapter_id = ?", (chapter_id,))
                    
                    try:
                        cursor.execute("DELETE FROM chunks_fts WHERE chapter_id = ?", (chapter_id,))
                    except sqlite3.Error as e:
                        logger.debug(f"[Knowledge] 删除FTS数据失败(可忽略): {e}")
                    
                    deleted_count += cursor.rowcount
                
                conn.commit()
                conn.close()
            
            if chroma_dir.exists():
                try:
                    import chromadb
                    client = chromadb.PersistentClient(path=str(chroma_dir))
                    collection = client.get_or_create_collection("novel_knowledge")
                    
                    for chapter_id in request.chapter_ids:
                        collection.delete(where={"chapter_id": chapter_id})
                except Exception as e:
                    logger.warning(f"从向量库删除失败: {e}")
            
            return JSONResponse({
                "success": True,
                "message": f"已清除 {len(request.chapter_ids)} 个章节的知识库数据",
                "deleted_chapters": request.chapter_ids
            })
        
        else:
            return JSONResponse({
                "success": False,
                "error": "请指定清除全部（clear_all=True）或提供章节ID列表（chapter_ids）"
            })
            
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"清除失败: {str(e)}"
        })


@router.delete("/knowledge-base/chapter/{chapter_id}")
async def delete_knowledge_chapter(chapter_id: str):
    """删除知识库中的单个章节"""
    from ...project_manager import get_project_manager
    
    pm = get_project_manager()
    
    if not pm.current_project_id:
        raise HTTPException(status_code=400, detail="请先选择一个项目")
    
    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "knowledge_base" / pm.current_project_id
    db_path = data_dir / "knowledge.db"
    chroma_dir = data_dir / "chroma"
    
    deleted = False
    
    try:
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chapters WHERE chapter_id = ?", (chapter_id,))
            chapter_deleted = cursor.rowcount > 0
            cursor.execute("DELETE FROM chunks WHERE chapter_id = ?", (chapter_id,))
            deleted = chapter_deleted
            conn.commit()
            conn.close()
        
        if chroma_dir.exists():
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(chroma_dir))
                collection = client.get_or_create_collection("novel_knowledge")
                collection.delete(where={"chapter_id": chapter_id})
            except Exception as e:
                logger.warning(f"[Knowledge] 删除向量库章节失败(可忽略): {e}")
        
        if deleted:
            return JSONResponse({
                "success": True,
                "message": f"章节 {chapter_id} 已从知识库删除"
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "章节不存在"
            })
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
