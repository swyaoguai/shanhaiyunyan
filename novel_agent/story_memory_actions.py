"""Story-memory query and follow-up actions used by chat routing."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


LOOKUP_HINTS = ("找", "查", "哪里", "哪章", "第几章", "忘记", "定位", "回顾")
BACKFILL_HINTS = ("回填", "回收", "收束", "兑现", "后续", "后面", "用上", "补上")
FORESHADOW_HINTS = ("伏笔", "线索", "悬念", "钩子", "暗线")


def is_story_memory_lookup(message: str) -> bool:
    text = str(message or "")
    return any(key in text for key in FORESHADOW_HINTS) and any(key in text for key in LOOKUP_HINTS)


def is_story_memory_backfill(message: str) -> bool:
    text = str(message or "")
    return any(key in text for key in FORESHADOW_HINTS) and any(key in text for key in BACKFILL_HINTS)


async def handle_story_memory_request(router_agent: Any, message: str) -> Optional[Dict[str, Any]]:
    if is_story_memory_backfill(message):
        candidates = _search_knowledge_base(getattr(router_agent, "knowledge_base", None), message, top_k=5)
        wiki_candidates = await _search_wiki(message, top_k=4)
        merged = _dedupe_candidates(candidates + wiki_candidates)
        eventline = _append_backfill_eventline(message, merged)
        return _build_router_result(
            response=_format_backfill_response(message, merged, eventline),
            action="foreshadowing_backfill",
            candidates=merged,
            eventline=eventline,
        )

    if is_story_memory_lookup(message):
        candidates = _search_knowledge_base(getattr(router_agent, "knowledge_base", None), message, top_k=8)
        wiki_candidates = await _search_wiki(message, top_k=6)
        merged = _dedupe_candidates(candidates + wiki_candidates)
        return _build_router_result(
            response=_format_lookup_response(message, merged),
            action="foreshadowing_lookup",
            candidates=merged,
        )

    return None


def _search_knowledge_base(knowledge_base: Any, query: str, *, top_k: int) -> List[Dict[str, Any]]:
    if not knowledge_base:
        return []
    try:
        response = knowledge_base.search(query=query, top_k=top_k)
    except Exception:
        return []

    candidates: List[Dict[str, Any]] = []
    for item in getattr(response, "results", []) or []:
        metadata = getattr(item, "metadata", None) or {}
        content = str(getattr(item, "document", "") or getattr(item, "content", "") or item).strip()
        if not content:
            continue
        chapter_id = str(metadata.get("chapter_id") or "").strip()
        chapter_number = _chapter_number(metadata.get("chapter_number")) or _chapter_number_from_id(chapter_id)
        candidates.append({
            "source": "knowledge_base",
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "title": str(metadata.get("title") or "").strip(),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "content": content,
        })
    return candidates


async def _search_wiki(query: str, *, top_k: int) -> List[Dict[str, Any]]:
    try:
        from .project_manager import get_project_manager
        from .wiki.wiki_compat import WikiCompatLayer

        pm = get_project_manager()
        if not pm.current_project_id:
            return []
        compat = WikiCompatLayer(pm.get_current_project_dir())
        result = await compat.retriever.retrieve(
            query=query[:1200],
            context_window=4000,
            top_k=top_k,
            include_graph=True,
            include_vector=False,
        )
    except Exception:
        return []

    candidates: List[Dict[str, Any]] = []
    for item in getattr(result, "results", []) or []:
        page = getattr(item, "page", None)
        if not page:
            continue
        body = str(getattr(page, "body", "") or "").strip()
        if not body:
            continue
        candidates.append({
            "source": "wiki",
            "chapter_id": "",
            "chapter_number": _chapter_number(getattr(page.frontmatter, "chapter_number", 0)),
            "title": str(getattr(page, "title", "") or getattr(page.frontmatter, "title", "") or "").strip(),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "content": body,
        })
    return candidates


def _append_backfill_eventline(message: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    from .project_manager import get_project_manager

    pm = get_project_manager()
    if not pm.current_project_id:
        return {}

    rows = pm.load_project_data("eventlines")
    if not isinstance(rows, list):
        rows = []

    source_chapters = [
        item.get("chapter_number")
        for item in candidates
        if _chapter_number(item.get("chapter_number")) > 0
    ]
    source_chapters = list(dict.fromkeys(source_chapters))[:5]
    now = datetime.now().isoformat()
    name = _short_title(message)
    row = {
        "id": f"foreshadow_backfill_{int(time.time())}",
        "name": f"伏笔回填：{name}",
        "type": "foreshadowing_backfill",
        "description": str(message or "").strip(),
        "status": "pending",
        "source": "chat",
        "source_chapters": source_chapters,
        "writer_guidance": _build_writer_guidance(message, source_chapters),
        "created_at": now,
        "updated_at": now,
    }
    rows.append(row)
    pm.save_project_data("eventlines", rows)

    try:
        from .library_service import get_library_service

        get_library_service().upsert_from_legacy("eventlines", rows)
    except Exception:
        pass
    return row


def _build_router_result(
    *,
    response: str,
    action: str,
    candidates: List[Dict[str, Any]],
    eventline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "response": response,
        "intent": {
            "type": "query_knowledge",
            "confidence": 0.98,
            "entities": {"story_memory_action": action},
        },
        "knowledge_results": candidates,
        "tool_results": None,
        "routed_to": "StoryMemory",
        "delegated_result": {
            "agent_name": "StoryMemory",
            "action": action,
            "candidates": candidates,
            "eventline": eventline or {},
            "is_complete": False,
        },
        "success": True,
        "routing_info": {
            "steps": [
                {"step": "story_memory", "status": "completed", "message": "已检索章节记忆并更新创作线索"}
            ],
            "duration": 0,
        },
    }


def _format_lookup_response(message: str, candidates: List[Dict[str, Any]]) -> str:
    if not candidates:
        return (
            "我没有在当前知识库里定位到足够明确的伏笔片段。"
            "建议先确认章节全文已经同步到知识库，或点设置里的“重建全文索引”。"
        )

    lines = ["我找到了几个可能相关的位置："]
    for index, item in enumerate(candidates[:5], start=1):
        chapter = _format_chapter_label(item)
        snippet = _snippet(item.get("content", ""))
        lines.append(f"{index}. {chapter}：{snippet}")
    lines.append("")
    lines.append("如果其中有你指的那条伏笔，可以直接说“把第X章这条伏笔回填”，我会把它登记为后续创作约束。")
    return "\n".join(lines)


def _format_backfill_response(message: str, candidates: List[Dict[str, Any]], eventline: Dict[str, Any]) -> str:
    lines = ["已把这条伏笔登记为后续回填任务。"]
    source_chapters = eventline.get("source_chapters") if isinstance(eventline, dict) else []
    if source_chapters:
        lines.append(f"关联来源章节：{', '.join(f'第{num}章' for num in source_chapters)}")
    elif candidates:
        lines.append("我找到了候选片段，但章节号不够明确，已先按聊天要求登记。")
    else:
        lines.append("当前没有定位到明确原文片段，已按你的要求先登记为待回收线索。")
    guidance = eventline.get("writer_guidance") if isinstance(eventline, dict) else ""
    if guidance:
        lines.append(f"写作约束：{guidance}")
    return "\n".join(lines)


def _dedupe_candidates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for item in sorted(items, key=lambda value: float(value.get("score", 0.0) or 0.0), reverse=True):
        key = (
            item.get("source"),
            item.get("chapter_number"),
            str(item.get("content", ""))[:80],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _chapter_number(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _chapter_number_from_id(chapter_id: str) -> int:
    match = re.search(r"(\d+)$", str(chapter_id or ""))
    return _chapter_number(match.group(1)) if match else 0


def _format_chapter_label(item: Dict[str, Any]) -> str:
    number = _chapter_number(item.get("chapter_number"))
    title = str(item.get("title") or "").strip()
    if number and title:
        return f"第{number}章《{title}》"
    if number:
        return f"第{number}章"
    return title or "未标明章节"


def _snippet(content: str, max_len: int = 140) -> str:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _short_title(message: str) -> str:
    text = re.sub(r"\s+", "", str(message or "伏笔").strip())
    text = re.sub(r"[，。！？、；:：\"'“”‘’（）()【】\\/\[\]{}<>|]+", "", text)
    return text[:24] or "待回收线索"


def _build_writer_guidance(message: str, source_chapters: List[int]) -> str:
    prefix = f"承接{', '.join(f'第{num}章' for num in source_chapters)}的伏笔，" if source_chapters else ""
    return f"{prefix}后续创作需要自然回收或呼应：{str(message or '').strip()}"
