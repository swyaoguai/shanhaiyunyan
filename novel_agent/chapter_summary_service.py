"""章节摘要生成服务"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent_config import AgentModelConfig, get_config_manager
from .agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

CHAPTER_SUMMARY_CONFIG_KEY = "chapter_summary_config"

SUMMARY_SCHEMA = {
    "chapter_number": "章节号（数字）",
    "summary_text": "200字以内的章节摘要",
    "key_events": "本章关键事件列表，每项不超过20字",
    "appearing_characters": "本章出场角色列表",
    "character_state_changes": "角色状态变化列表，例如关系、能力、立场、情绪变化",
    "foreshadowing": "本章埋下或推进的伏笔/线索列表",
    "open_threads": "本章结束后仍未解决、后续需要回收的剧情线列表",
    "ending_hook": "本章结尾留下的悬念/钩子",
    "links": "与角色、地点、物品、势力或事件线相关的 Wiki 双链标题列表",
}


async def generate_chapter_summary(
    chapter_number: int,
    title: str,
    content: str,
    api_config_id: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """
    使用 LLM 生成章节结构化摘要。

    Returns:
        dict with keys: chapter_number, summary_text, key_events,
        appearing_characters, ending_hook
    """
    config = _resolve_model_config(api_config_id, model)
    client = LLMClient(model_config=config, metrics_namespace="ChapterSummary")

    schema_desc = "\n".join(f"- {k}: {v}" for k, v in SUMMARY_SCHEMA.items())

    system_prompt = (
        "你是一个小说创作助手，负责为已完成的章节生成结构化摘要。"
        "摘要会写入 Wiki，供后续章节自动检索和剧情回填使用，必须特别标出伏笔和未回收线索。"
        "严格按 JSON 格式输出，不要添加任何解释或额外内容。"
        f"输出格式要求：\n{schema_desc}"
    )

    # 截取内容前 3000 字用于摘要，避免上下文过长
    truncated = content[:3000] if content else ""

    user_prompt = (
        f"请为以下章节生成结构化摘要。\n\n"
        f"章节号：第{chapter_number}章\n"
        f"标题：{title}\n\n"
        f"正文内容（可能不完整）：\n{truncated}"
    )

    try:
        response = await client.call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=800,
            stream=False,
        )

        parsed = _parse_summary_response(response)
        if parsed:
            parsed["chapter_number"] = chapter_number
            parsed.setdefault("title", f"第{chapter_number}章摘要")
            parsed.setdefault("links", [])
            parsed.setdefault("appearing_characters", [])
            parsed.setdefault("key_events", [])
            parsed.setdefault("character_state_changes", [])
            parsed.setdefault("foreshadowing", [])
            parsed.setdefault("open_threads", [])
            parsed.setdefault("ending_hook", "")
            parsed.setdefault("vector_text", _build_summary_vector_text(chapter_number, title, parsed))
            return parsed
    except Exception as e:
        logger.warning(f"LLM summary generation failed: {e}")

    # 降级：返回截断摘要
    return _fallback_summary(chapter_number, title, content)


def save_chapter_summary_to_library(
    chapter_number: int,
    summary_dict: Dict[str, Any],
    *,
    project_dir: Optional[Path] = None,
) -> bool:
    """将章节摘要保存到统一资料库，并同步生成 Markdown 笔记。"""
    try:
        from .library_service import get_library_service
        from .library_types import EntryType, LibraryEntry, SourceType, _now_iso

        resolved_project_dir = _resolve_project_dir(project_dir)
        svc = get_library_service(resolved_project_dir)
        if svc.is_degraded:
            return False

        entry_id = f"chapter_summary_{chapter_number}"
        title = summary_dict.get("title") or f"第{chapter_number}章摘要"
        links = _normalize_links(summary_dict.get("links") or [])
        characters = _as_list(summary_dict.get("appearing_characters"))
        key_events = _as_list(summary_dict.get("key_events"))
        state_changes = _as_list(summary_dict.get("character_state_changes"))
        foreshadowing = _as_list(summary_dict.get("foreshadowing"))
        open_threads = _as_list(summary_dict.get("open_threads"))
        summary_text = str(summary_dict.get("summary_text", "") or "").strip()

        entry = LibraryEntry(
            id=entry_id,
            entry_type=EntryType.CHAPTER_SUMMARY.value,
            title=str(title),
            summary=summary_text,
            content_structured={
                **dict(summary_dict),
                "links": links,
                "title": str(title),
            },
            source_type=SourceType.DERIVED.value,
            tags=["auto_summary", "chapter_summary"],
            relations=links,
            metadata={
                "chapter_number": chapter_number,
                "characters": characters,
                "key_events": key_events,
                "character_state_changes": state_changes,
                "foreshadowing": foreshadowing,
                "open_threads": open_threads,
            },
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

        saved = svc.upsert_entry(entry)
        normalized_summary = dict(summary_dict)
        normalized_summary.setdefault("title", str(title))
        normalized_summary.setdefault("vector_text", saved.summary or summary_text)
        normalized_summary.setdefault("links", links)
        _write_chapter_summary_markdown(resolved_project_dir, saved, normalized_summary)
        _write_chapter_summary_wiki(
            resolved_project_dir,
            saved,
            normalized_summary,
            store=getattr(svc, "_store", None),
        )
        return True
    except Exception as e:
        logger.warning(f"save_chapter_summary_to_library failed: {e}")
        return False


async def index_chapter_summary_vector(project_dir: Optional[Path], summary_dict: Dict[str, Any]) -> bool:
    """占位向量索引写入接口，后续接入向量库实现。"""
    try:
        if not project_dir:
            return False
        vector_dir = Path(project_dir) / "knowledge" / "vectors"
        vector_dir.mkdir(parents=True, exist_ok=True)
        chapter_number = int(summary_dict.get("chapter_number") or 0)
        payload = {
            "node_id": f"chapter_summary_{chapter_number}",
            "vector_text": str(summary_dict.get("vector_text") or summary_dict.get("summary_text") or "").strip(),
            "metadata": {
                "chapter_number": chapter_number,
                "title": str(summary_dict.get("title") or "").strip(),
                "links": _normalize_links(summary_dict.get("links") or []),
                "appearing_characters": _as_list(summary_dict.get("appearing_characters")),
                "foreshadowing": _as_list(summary_dict.get("foreshadowing")),
                "open_threads": _as_list(summary_dict.get("open_threads")),
            },
        }
        vector_file = vector_dir / f"chapter_{chapter_number:03d}.json"
        vector_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"index_chapter_summary_vector failed: {e}")
        return False


def get_auto_summary_enabled(project_id: str) -> bool:
    """检查项目是否启用了自动摘要生成。"""
    try:
        from .project_manager import get_project_manager
        pm = get_project_manager()
        prev = pm.load_project_state(CHAPTER_SUMMARY_CONFIG_KEY)
        return bool(prev.get("auto_summary_enabled") if prev else False)
    except Exception:
        return False


def set_auto_summary_enabled(project_id: str, enabled: bool) -> None:
    """设置项目的自动摘要开关状态。"""
    try:
        from .project_manager import get_project_manager
        pm = get_project_manager()
        pm.save_project_state(
            CHAPTER_SUMMARY_CONFIG_KEY,
            {"auto_summary_enabled": enabled}
        )
    except Exception as e:
        logger.warning(f"set_auto_summary_enabled failed: {e}")


def get_auto_summary_config(project_id: str) -> Dict[str, Any]:
    """获取项目的摘要配置。"""
    try:
        from .project_manager import get_project_manager
        pm = get_project_manager()
        state = pm.load_project_state(CHAPTER_SUMMARY_CONFIG_KEY)
        return state if state else {"auto_summary_enabled": False}
    except Exception:
        return {"auto_summary_enabled": False}


def _resolve_model_config(api_config_id: str, model: str) -> AgentModelConfig:
    manager = get_config_manager()
    api_base = ""
    api_key = ""
    temperature = 0.7
    max_tokens = 800
    resolved_model = (model or "").strip()

    api_type = "openai_chat"
    if api_config_id:
        multi = manager.get_multi_config()
        for cfg in multi.configs:
            if cfg.id == api_config_id:
                api_base = cfg.api_base
                api_key = cfg.api_key
                temperature = cfg.temperature
                max_tokens = cfg.max_tokens
                api_type = getattr(cfg, 'api_type', 'openai_chat') or 'openai_chat'
                if not resolved_model and cfg.models:
                    resolved_model = cfg.models[0]
                break

    if not api_base or not api_key:
        global_config = manager.get_global_config()
        api_base = api_base or global_config.api_base
        api_key = api_key or global_config.api_key
        if not resolved_model:
            resolved_model = global_config.model
        temperature = global_config.temperature or temperature
        max_tokens = global_config.max_tokens or max_tokens
        api_type = getattr(global_config, 'api_type', 'openai_chat') or api_type

    return AgentModelConfig(
        agent_name="ChapterSummary",
        api_config_id=api_config_id,
        api_base=api_base,
        api_key=api_key,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_type=api_type,
    )


def _parse_summary_response(response: str) -> Optional[Dict[str, Any]]:
    """从 LLM 响应中解析 JSON 摘要。"""
    text = response.strip()
    # 尝试提取 ```json ... ``` 包裹的内容
    for marker in ("```json", "```"):
        if marker in text:
            start = text.find(marker) + len(marker)
            end = text.rfind("```")
            if end > start:
                text = text[start:end].strip()
                break

    try:
        data = json.loads(text)
        # 规范化字段名（支持中文 key）
        result: Dict[str, Any] = {
            "chapter_number": data.get("chapter_number", 0),
            "summary_text": _str(data.get("summary_text") or data.get("摘要") or data.get("章节摘要", "")),
            "key_events": _list(data.get("key_events") or data.get("关键事件", [])),
            "appearing_characters": _list(data.get("appearing_characters") or data.get("出场角色", [])),
            "character_state_changes": _list(data.get("character_state_changes") or data.get("角色状态变化", [])),
            "foreshadowing": _list(data.get("foreshadowing") or data.get("伏笔") or data.get("线索", [])),
            "open_threads": _list(data.get("open_threads") or data.get("未回收线索") or data.get("遗留伏笔", [])),
            "ending_hook": _str(data.get("ending_hook") or data.get("结尾钩子", "")),
            "links": _list(data.get("links") or data.get("关联", [])),
        }
        return result
    except (json.JSONDecodeError, ValueError):
        return None


def _fallback_summary(chapter_number: int, title: str, content: str) -> Dict[str, Any]:
    """LLM 生成失败时的降级摘要。"""
    summary_text = (content or "")[:200] + ("..." if len(content or "") > 200 else "")
    return {
        "chapter_number": chapter_number,
        "title": f"第{chapter_number}章摘要",
        "summary_text": summary_text,
        "key_events": [],
        "appearing_characters": [],
        "character_state_changes": [],
        "foreshadowing": [],
        "open_threads": [],
        "ending_hook": "",
        "links": [],
        "vector_text": _build_summary_vector_text(chapter_number, title, {"summary_text": summary_text}),
    }


def _str(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return "; ".join(str(v).strip() for v in val if v)
    return str(val).strip()


def _list(val: Any) -> List[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if v]
    if isinstance(val, str):
        return [s.strip() for s in val.replace("；", ";").split(";") if s.strip()]
    return []


def _as_list(val: Any) -> List[str]:
    return _list(val)


def _build_summary_vector_text(chapter_number: int, title: str, payload: Dict[str, Any]) -> str:
    parts = [
        f"第{chapter_number}章",
        str(title or "").strip(),
        str(payload.get("summary_text") or "").strip(),
    ]
    for label, key in (
        ("关键事件", "key_events"),
        ("角色状态变化", "character_state_changes"),
        ("伏笔线索", "foreshadowing"),
        ("待回收线索", "open_threads"),
        ("结尾钩子", "ending_hook"),
    ):
        value = payload.get(key)
        if isinstance(value, list):
            text = "；".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value or "").strip()
        if text:
            parts.append(f"{label}: {text}")
    return " ".join(part for part in parts if part).strip()


def _normalize_links(val: Any) -> List[str]:
    items = _as_list(val)
    links: List[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if not text.startswith("[["):
            text = f"[[{text}]]"
        links.append(text)
    return list(dict.fromkeys(links))


def _resolve_project_dir(project_dir: Optional[Path]) -> Optional[Path]:
    if project_dir:
        return Path(project_dir)
    try:
        from .project_manager import get_project_manager
        pm = get_project_manager()
        return pm.get_project_data_path("outline").parent
    except Exception:
        return None


def _markdown_for_summary(entry: Any, summary_dict: Dict[str, Any]) -> str:
    title = str(getattr(entry, "title", "") or summary_dict.get("title") or "").strip()
    chapter_number = summary_dict.get("chapter_number") or summary_dict.get("chapter") or ""
    summary_text = str(summary_dict.get("summary_text") or "").strip()
    key_events = _as_list(summary_dict.get("key_events"))
    characters = _as_list(summary_dict.get("appearing_characters"))
    state_changes = _as_list(summary_dict.get("character_state_changes"))
    foreshadowing = _as_list(summary_dict.get("foreshadowing"))
    open_threads = _as_list(summary_dict.get("open_threads"))
    ending_hook = str(summary_dict.get("ending_hook") or "").strip()
    links = _normalize_links(summary_dict.get("links") or [])

    lines = [f"# {title or f'第{chapter_number}章摘要'}"]
    if summary_text:
        lines.extend(["", "## 摘要", summary_text])
    if characters:
        lines.extend(["", "## 角色", *[f"- {c if c.startswith('[[') else f'[[{c}]]'}" for c in characters]])
    if key_events:
        lines.extend(["", "## 关键事件", *[f"- {item}" for item in key_events]])
    if state_changes:
        lines.extend(["", "## 角色状态变化", *[f"- {item}" for item in state_changes]])
    if foreshadowing:
        lines.extend(["", "## 伏笔线索", *[f"- {item}" for item in foreshadowing]])
    if open_threads:
        lines.extend(["", "## 待回收线索", *[f"- {item}" for item in open_threads]])
    if ending_hook:
        lines.extend(["", "## 结尾钩子", ending_hook])
    if links:
        lines.extend(["", "## 关联", *[f"- {link}" for link in links]])
    lines.extend(["", "## 向量索引文本", str(summary_dict.get("vector_text") or summary_text)])
    return "\n".join(lines).strip() + "\n"


def _write_chapter_summary_markdown(project_dir: Optional[Path], entry: Any, summary_dict: Dict[str, Any]) -> None:
    if not project_dir:
        return
    try:
        base = Path(project_dir) / "knowledge" / "chapters"
        base.mkdir(parents=True, exist_ok=True)
        chapter_number = summary_dict.get("chapter_number") or 0
        file_path = base / f"chapter_{int(chapter_number):03d}.md"
        content = _markdown_for_summary(entry, summary_dict)
        file_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning(f"write markdown summary failed: {exc}")


def _write_chapter_summary_wiki(
    project_dir: Optional[Path],
    entry: Any,
    summary_dict: Dict[str, Any],
    *,
    store: Any = None,
) -> None:
    """把章节摘要写成 Wiki 章节页，供后续章节写作检索。"""
    if not project_dir:
        return
    try:
        from .wiki.wiki_types import Frontmatter, PageType, WikiPage

        title = str(getattr(entry, "title", "") or summary_dict.get("title") or "").strip()
        chapter_number = int(summary_dict.get("chapter_number") or 0)
        body = _markdown_for_summary(entry, summary_dict)
        characters = _as_list(summary_dict.get("appearing_characters"))
        key_events = _as_list(summary_dict.get("key_events"))
        foreshadowing = _as_list(summary_dict.get("foreshadowing"))
        open_threads = _as_list(summary_dict.get("open_threads"))
        summary_text = str(summary_dict.get("summary_text") or "").strip()
        links = _normalize_links(summary_dict.get("links") or [])
        frontmatter = Frontmatter(
            page_type=PageType.CHAPTER,
            title=title or f"第{chapter_number}章摘要",
            sources=[f"chapter_{chapter_number}"] if chapter_number else [],
            tags=["auto_summary", "chapter_summary"],
            chapter_number=chapter_number or None,
            entities=list(dict.fromkeys(characters + [link.strip("[]") for link in links])),
            word_count=len(summary_text) + sum(len(item) for item in key_events + foreshadowing + open_threads),
        )
        if store is None:
            from .wiki.wiki_compat import WikiCompatLayer
            compat = WikiCompatLayer(Path(project_dir))
            store = compat.store
        store.ensure_dirs()
        store.save_page(WikiPage(frontmatter=frontmatter, body=body))
    except Exception as exc:
        logger.warning(f"write wiki summary failed: {exc}")
