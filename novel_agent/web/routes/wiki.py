"""
Wiki 系统 API 路由

提供 Wiki 页面的 CRUD、搜索、图谱、Lint、Review 等接口。
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wiki", tags=["wiki"])


# ===== 请求模型 =====

class WikiPageCreate(BaseModel):
    title: str
    page_type: str = "custom"
    body: str = ""
    tags: list[str] = []
    sources: list[str] = []


class WikiPageUpdate(BaseModel):
    body: Optional[str] = None
    tags: Optional[list[str]] = None
    sources: Optional[list[str]] = None


class WikiSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    include_graph: bool = True
    include_vector: bool = True
    context_window: int = 8000


class WikiIngestRequest(BaseModel):
    content: str
    source_name: str = "manual_input"


class RelationshipGraphRequest(BaseModel):
    mode: str = "character"
    scope: str = "all"
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    center_id: Optional[str] = None


# ===== 辅助函数 =====

def _source_mode_from_tags(tags: Any) -> str:
    from ...source_modes import source_mode_from_tags

    return source_mode_from_tags(tags) or "unknown"


def _ensure_page_source_tags(tags: Any, default_source_mode: str = "manual") -> list[str]:
    from ...source_modes import ensure_source_tag, source_mode_from_tags

    tag_list = list(tags or []) if isinstance(tags, list) else []
    if source_mode_from_tags(tag_list):
        return tag_list
    return ensure_source_tag(tag_list, default_source_mode)

def _get_wiki_compat():
    """获取 Wiki 兼容层实例"""
    from novel_agent.project_manager import get_project_manager
    from novel_agent.wiki import WikiCompatLayer
    pm = get_project_manager()
    project_dir = pm.get_project_data_path("outline").parent
    return WikiCompatLayer(project_dir)


def _get_wiki_store():
    """获取 WikiStore 实例"""
    from novel_agent.project_manager import get_project_manager
    from novel_agent.wiki import WikiStore
    pm = get_project_manager()
    project_dir = pm.get_project_data_path("outline").parent
    return WikiStore(project_dir / "wiki")


def _get_project_manager_and_dir():
    from novel_agent.project_manager import get_project_manager
    pm = get_project_manager()
    if not pm.current_project_id:
        raise HTTPException(status_code=400, detail="当前没有项目")
    return pm, pm.get_current_project_dir()


def _relationship_graph_path(project_dir: Path) -> Path:
    graph_dir = project_dir / "wiki"
    graph_dir.mkdir(parents=True, exist_ok=True)
    return graph_dir / "relationship_graph.json"


def _load_relationship_graph(project_dir: Path) -> dict[str, Any]:
    path = _relationship_graph_path(project_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"[Wiki API] 读取关系图谱缓存失败: {exc}")
        return {}


def _save_relationship_graph(project_dir: Path, payload: dict[str, Any]) -> None:
    path = _relationship_graph_path(project_dir)
    old_content = path.read_text(encoding="utf-8") if path.exists() else None
    atomic_write_json(path, payload, old_content=old_content, ensure_ascii=False, indent=2)


def _positive_int(value: Any, fallback: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        return fallback
    return parsed if parsed > 0 else fallback


def _chapter_number(chapter: dict[str, Any], fallback: int) -> int:
    return _positive_int(chapter.get("chapter_number") or chapter.get("number"), fallback)


def _select_graph_chapters(chapters: list[dict[str, Any]], req: RelationshipGraphRequest) -> list[dict[str, Any]]:
    ordered = sorted(
        [row for row in chapters if str(row.get("content") or "").strip()],
        key=lambda row: _chapter_number(row, 999999),
    )
    if not ordered:
        return []

    scope = str(req.scope or "all").strip().lower()
    if scope == "current":
        return ordered[-1:]
    if scope == "first5":
        return ordered[:5]
    if scope == "first10":
        return ordered[:10]
    if scope == "first15":
        return ordered[:15]
    if scope == "range":
        start = _positive_int(req.chapter_start, 1)
        end = _positive_int(req.chapter_end, start)
        if end < start:
            start, end = end, start
        return [
            row for row in ordered
            if start <= _chapter_number(row, 0) <= end
        ]
    return ordered


GRAPH_STOP_NAMES = {
    "一个", "一种", "一下", "一声", "一眼", "一切", "所有", "这里", "那里", "这个", "那个",
    "他们", "她们", "我们", "你们", "自己", "众人", "少年", "少女", "男人", "女人", "老人",
    "时候", "地方", "东西", "事情", "声音", "目光", "脸色", "心中", "身后", "前方", "旁边",
    "第一", "第二", "第三", "小说", "章节", "主角", "角色", "人物", "没有", "不是", "只是",
    "只见", "看见", "听见", "知道", "觉得", "已经", "突然", "开始", "继续", "成功", "失败",
    "提升", "进入", "出来", "过去", "回来", "说道", "问道", "想到", "立即", "终于", "两人",
}

GRAPH_BAD_NAME_PARTS = (
    "只见", "已经", "突然", "开始", "继续", "成功", "失败", "提升", "进入", "出来", "过去",
    "回来", "说道", "问道", "想到", "看见", "听见", "似乎", "仿佛", "然后", "于是", "因为",
    "所以", "但是", "只是", "不是", "没有", "能够", "可以", "无法", "不能", "不会", "这是",
    "那是", "显然", "瞬间", "终于", "立刻", "正在", "依旧", "已经", "成为",
    "地将", "地把", "功地", "将镇", "提升至",
)

GRAPH_BAD_NAME_PREFIXES = (
    "的", "了", "在", "把", "被", "将", "向", "从", "对", "与", "和", "或", "却", "但", "可", "地",
    "又", "也", "都", "只", "便", "让", "给", "为", "以", "及", "并", "再", "更", "很", "最",
    "那", "这", "其", "他", "她", "它", "我", "你", "前", "后",
)

GRAPH_BAD_NAME_SUFFIXES = (
    "了", "着", "的", "地", "得", "过", "吗", "吧", "呢", "啊", "上", "下", "中", "里",
)

GRAPH_ENTITY_TYPES = {
    "character": "角色",
    "location": "地点",
    "item": "物件",
    "faction": "势力",
    "event": "事件",
    "power": "功法",
    "clue": "线索",
}

GRAPH_CATEGORY_KEYWORDS = {
    "location": ("城", "村", "镇", "山", "谷", "湖", "海", "河", "宫", "殿", "楼", "阁", "院", "站", "车站", "旅馆", "矿上", "家里", "旧城"),
    "item": ("剑", "刀", "令", "灯", "符", "药", "书", "信", "照片", "报纸", "夹子", "纸板", "钥匙", "玉佩", "面包"),
    "faction": ("宗", "门", "派", "族", "会", "盟", "公司", "王朝", "军", "队", "集团", "司"),
    "power": ("诀", "法", "术", "心法", "神通", "灵力"),
}

GRAPH_ENTITY_SUFFIXES = tuple(sorted(
    {keyword for keywords in GRAPH_CATEGORY_KEYWORDS.values() for keyword in keywords},
    key=len,
    reverse=True,
))

GRAPH_RELATION_KEYWORDS = [
    ("救", "救助"),
    ("杀", "杀害"),
    ("打", "冲突"),
    ("追", "追逐"),
    ("找", "寻找"),
    ("偷", "盗取"),
    ("骗", "欺骗"),
    ("告诉", "告知"),
    ("遇见", "相遇"),
    ("看见", "目击"),
    ("带", "同行"),
    ("给", "交付"),
    ("失踪", "失踪"),
    ("死亡", "死亡"),
    ("坠毁", "事故"),
    ("逃", "逃离"),
    ("回", "返回"),
    ("离开", "离开"),
    ("加入", "加入"),
]

GRAPH_EVENT_KEYWORDS = ("失踪", "死亡", "坠毁", "相遇", "战斗", "冲突", "救", "杀", "追", "逃", "发现", "离开", "返回", "出现", "消失", "告知", "背叛")


def _normalize_entity_name(value: Any) -> str:
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9·_-]", "", str(value or "").strip())
    return text[:18]


def _clean_entity_candidate(value: Any) -> str:
    name = _normalize_entity_name(value)
    if not name:
        return ""
    for separator in ("把", "将", "在", "向", "从", "对", "给", "与", "和", "跟", "进入", "至"):
        if separator in name and not name.startswith(separator):
            tail = name.rsplit(separator, 1)[-1]
            if len(tail) >= 2:
                name = tail
    for prefix in GRAPH_BAD_NAME_PREFIXES:
        while name.startswith(prefix) and len(name) > 2:
            name = name[len(prefix):]
    for suffix in GRAPH_BAD_NAME_SUFFIXES:
        while name.endswith(suffix) and len(name) > 2:
            name = name[:-len(suffix)]
    return name[:12]


def _is_noisy_entity_name(name: str, *, allow_seed: bool = False) -> bool:
    if not name:
        return True
    if allow_seed:
        return False
    if name in GRAPH_STOP_NAMES:
        return True
    if len(name) < 2 or len(name) > 8:
        return True
    if any(part in name for part in GRAPH_BAD_NAME_PARTS):
        return True
    if any(name.startswith(prefix) for prefix in GRAPH_BAD_NAME_PREFIXES):
        return True
    if any(name.endswith(suffix) for suffix in GRAPH_BAD_NAME_SUFFIXES):
        return True
    if re.search(r"(第[一二三四五六七八九十百千万零〇两\d]+|入门|外界|门口|房门|心中|眼前|耳边)", name):
        return True
    return False


def _iter_character_seed_names(raw: Any) -> list[str]:
    names: list[str] = []
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []
    for item in iterable:
        if isinstance(item, dict):
            for key in ("name", "姓名", "title"):
                name = _clean_entity_candidate(item.get(key))
                if name:
                    names.append(name)
                    break
        else:
            name = _clean_entity_candidate(item)
            if name:
                names.append(name)
    return names


def _guess_entity_type(name: str, character_names: set[str]) -> str:
    if name in character_names:
        return "character"
    for entity_type, keywords in GRAPH_CATEGORY_KEYWORDS.items():
        if any(name.endswith(keyword) for keyword in keywords):
            return entity_type
    for entity_type, keywords in GRAPH_CATEGORY_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return entity_type
    if len(name) in (2, 3) and not _is_noisy_entity_name(name):
        return "character"
    return "clue"


def _split_sentences(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"(?<=[。！？；;.!?])", text)
        if item.strip()
    ]


def _extract_candidate_names(text: str, character_names: set[str]) -> list[str]:
    seed_names = {
        _clean_entity_candidate(name)
        for name in character_names
        if _clean_entity_candidate(name)
    }
    candidates = set(seed_names)
    counts: Counter[str] = Counter()

    def add_candidate(raw: str, *, explicit: bool = False) -> None:
        name = _clean_entity_candidate(raw)
        if _is_noisy_entity_name(name, allow_seed=explicit or name in seed_names):
            return
        if explicit or name in seed_names or any(name.endswith(suffix) for suffix in GRAPH_ENTITY_SUFFIXES):
            counts[name] += 2 if explicit else 1

    for match in re.finditer(r"《([^》]{2,12})》|「([^」]{2,12})」|“([^”]{2,12})”|\[\[([^\]]{2,20})\]\]", text):
        add_candidate(next((group for group in match.groups() if group), ""), explicit=True)

    suffix_pattern = "|".join(re.escape(suffix) for suffix in GRAPH_ENTITY_SUFFIXES)
    for match in re.finditer(rf"[\u4e00-\u9fa5·]{{1,6}}(?:{suffix_pattern})", text):
        add_candidate(match.group(0))

    for sentence in _split_sentences(text):
        for match in re.finditer(r"([\u4e00-\u9fa5·]{2,3})(?=(?:说|问|答|看|走|拿|把|将|与|和|在|从|向|给|对|进入|发现|遇见|救|追|逃|杀|打))", sentence):
            add_candidate(match.group(1))
        for match in re.finditer(r"(?<=(?:和|与|跟|对|向|把|将|给))([\u4e00-\u9fa5·]{2,3})", sentence):
            add_candidate(match.group(1))

    for name, count in counts.items():
        if name in seed_names or count >= 2 or any(name.endswith(suffix) for suffix in GRAPH_ENTITY_SUFFIXES):
            candidates.add(name)

    filtered = {
        name for name in candidates
        if not any(name != other and len(name) <= 3 and name in other for other in candidates)
    }

    return sorted(filtered, key=lambda value: (-len(value), value))


def _relation_label(sentence: str) -> str:
    for keyword, label in GRAPH_RELATION_KEYWORDS:
        if keyword in sentence:
            return label
    return "共现"


def _event_title(chapter_number: int, sentence: str, index: int) -> str:
    clean = re.sub(r"\s+", "", sentence)
    clean = re.sub(r"[“”\"'‘’]", "", clean)
    if len(clean) > 18:
        clean = clean[:18]
    return clean or f"第{chapter_number}章事件{index}"


def _build_relationship_graph_payload(chapters: list[dict[str, Any]], req: RelationshipGraphRequest, character_seed_names: list[str]) -> dict[str, Any]:
    mode = str(req.mode or "character").strip().lower()
    if mode not in {"character", "event", "compass"}:
        mode = "character"

    character_names = {name for name in character_seed_names if name}
    full_text = "\n".join(str(row.get("content") or "") for row in chapters)
    candidates = _extract_candidate_names(full_text, character_names)

    node_map: dict[str, dict[str, Any]] = {}
    edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    def ensure_node(name: str, entity_type: str, chapter_number: int, snippet: str = "") -> dict[str, Any]:
        name = _normalize_entity_name(name)
        if not name:
            raise ValueError("empty node name")
        node_id = f"{entity_type}:{name}"
        node = node_map.setdefault(node_id, {
            "id": node_id,
            "label": name,
            "type": entity_type,
            "type_label": GRAPH_ENTITY_TYPES.get(entity_type, entity_type),
            "degree": 0,
            "chapters": [],
            "snippets": [],
            "summary": "",
        })
        if chapter_number and chapter_number not in node["chapters"]:
            node["chapters"].append(chapter_number)
        if snippet and len(node["snippets"]) < 3:
            node["snippets"].append(snippet[:90])
        return node

    def add_edge(source: str, target: str, label: str, chapter_number: int, snippet: str = "", edge_type: str = "co_occurrence") -> None:
        if not source or not target or source == target:
            return
        left, right = sorted([source, target])
        key = (left, right, label)
        edge = edge_map.setdefault(key, {
            "source": left,
            "target": right,
            "label": label,
            "type": edge_type,
            "weight": 0,
            "chapters": [],
            "snippets": [],
        })
        edge["weight"] += 1
        if chapter_number and chapter_number not in edge["chapters"]:
            edge["chapters"].append(chapter_number)
        if snippet and len(edge["snippets"]) < 2:
            edge["snippets"].append(snippet[:100])

    for chapter_index, chapter in enumerate(chapters, start=1):
        chapter_number = _chapter_number(chapter, chapter_index)
        title = str(chapter.get("title") or f"第{chapter_number}章").strip()
        content = str(chapter.get("content") or "")
        sentences = _split_sentences(content)
        chapter_entities: set[str] = set()

        for sentence in sentences[:260]:
            present_names = []
            for name in candidates[:160]:
                if name and name in sentence:
                    entity_type = _guess_entity_type(name, character_names)
                    try:
                        node = ensure_node(name, entity_type, chapter_number, sentence)
                        present_names.append(node["id"])
                        chapter_entities.add(node["id"])
                    except ValueError:
                        continue
            present_names = list(dict.fromkeys(present_names))[:8]
            if len(present_names) >= 2:
                label = _relation_label(sentence)
                for i, source in enumerate(present_names):
                    for target in present_names[i + 1:]:
                        add_edge(source, target, label, chapter_number, sentence)

        event_sentences = [sentence for sentence in sentences if any(keyword in sentence for keyword in GRAPH_EVENT_KEYWORDS)]
        for event_index, sentence in enumerate(event_sentences[:4], start=1):
            event_name = _event_title(chapter_number, sentence, event_index)
            event_node = ensure_node(f"第{chapter_number}章·{event_name}", "event", chapter_number, sentence)
            for entity_id in list(chapter_entities)[:10]:
                add_edge(event_node["id"], entity_id, _relation_label(sentence), chapter_number, sentence, "event_link")

        if not event_sentences and title:
            event_node = ensure_node(f"第{chapter_number}章·{title[:12]}", "event", chapter_number, title)
            for entity_id in list(chapter_entities)[:8]:
                add_edge(event_node["id"], entity_id, "出现", chapter_number, title, "event_link")

    event_nodes = sorted(
        [node for node in node_map.values() if node["type"] == "event"],
        key=lambda node: (min(node["chapters"] or [999999]), node["label"]),
    )
    for left, right in zip(event_nodes, event_nodes[1:]):
        add_edge(left["id"], right["id"], "推进", min(right["chapters"] or [0]), "", "timeline")

    nodes = list(node_map.values())
    edges = list(edge_map.values())
    degree_count: dict[str, int] = {}
    for edge in edges:
        degree_count[edge["source"]] = degree_count.get(edge["source"], 0) + 1
        degree_count[edge["target"]] = degree_count.get(edge["target"], 0) + 1
    for node in nodes:
        node["degree"] = degree_count.get(node["id"], 0)
        node["chapters"] = sorted(node["chapters"])
        node["summary"] = f"{node['type_label']}，出现于第{', '.join(map(str, node['chapters'][:5]))}章" if node["chapters"] else node["type_label"]

    if mode == "character":
        allowed = {"character", "faction", "location", "item", "power"}
    elif mode == "event":
        allowed = {"event", "character", "location", "clue"}
    else:
        allowed = {"character", "event", "location", "item", "faction", "power", "clue"}
    filtered_ids = {node["id"] for node in nodes if node["type"] in allowed}
    nodes = [node for node in nodes if node["id"] in filtered_ids]
    edges = [edge for edge in edges if edge["source"] in filtered_ids and edge["target"] in filtered_ids]

    nodes.sort(key=lambda node: (-int(node.get("degree") or 0), min(node.get("chapters") or [999999]), node["label"]))
    node_limit = 45 if mode == "character" else 55
    nodes = nodes[:node_limit]
    kept_ids = {node["id"] for node in nodes}
    edges = [edge for edge in edges if edge["source"] in kept_ids and edge["target"] in kept_ids]
    edges.sort(key=lambda edge: (-int(edge.get("weight") or 0), edge["label"]))
    edges = edges[:160]

    statistics = {
        "nodes": len(nodes),
        "edges": len(edges),
        "chapters": len(chapters),
        "characters": sum(1 for node in nodes if node["type"] == "character"),
        "events": sum(1 for node in nodes if node["type"] == "event"),
    }
    return {
        "mode": mode,
        "scope": req.scope,
        "center_id": req.center_id or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "nodes": nodes,
        "edges": edges,
        "statistics": statistics,
    }


# ===== 页面 CRUD =====

@router.get("/pages")
async def list_pages(
    page_type: Optional[str] = None,
    tags: Optional[str] = None,
):
    """列出所有 wiki 页面"""
    try:
        store = _get_wiki_store()
        from novel_agent.wiki import PageType
        pt = PageType(page_type) if page_type else None
        tag_list = tags.split(",") if tags else None
        pages = store.list_pages(page_type=pt, tags=tag_list)
        return JSONResponse({
            "success": True,
            "data": [
                {
                    "title": p.title,
                    "page_type": p.page_type.value,
                    "tags": p.tags,
                    "source_mode": _source_mode_from_tags(p.tags),
                    "sources": p.sources,
                    "word_count": len(p.body.replace(" ", "").replace("\n", "")),
                    "links_out": p.extract_wikilinks(),
                    "updated_at": p.frontmatter.updated_at,
                    "file_path": str(p.file_path) if p.file_path else None,
                }
                for p in pages
            ],
            "total": len(pages),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 列出页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/by-file")
async def get_page_by_file(file_path: str):
    """按文件路径获取 wiki 页面，用于空标题页面。"""
    try:
        store = _get_wiki_store()
        page = store.load_page_by_path(Path(file_path))
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {file_path}")

        backlinks = store.get_backlinks(page.title) if page.title else []

        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "page_type": page.page_type.value,
                "body": page.body,
                "tags": page.tags,
                "source_mode": _source_mode_from_tags(page.tags),
                "sources": page.sources,
                "entities": page.entities,
                "links_out": page.extract_wikilinks(),
                "links_in": [p.title for p in backlinks],
                "word_count": len(page.body.replace(" ", "").replace("\n", "")),
                "created_at": page.frontmatter.created_at,
                "updated_at": page.frontmatter.updated_at,
                "file_path": str(page.file_path) if page.file_path else None,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 按文件路径获取页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{title}")
async def get_page(title: str):
    """获取单个 wiki 页面"""
    try:
        store = _get_wiki_store()
        page = store.load_page(title)
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        
        # 获取双向链接
        backlinks = store.get_backlinks(title)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "page_type": page.page_type.value,
                "body": page.body,
                "tags": page.tags,
                "source_mode": _source_mode_from_tags(page.tags),
                "sources": page.sources,
                "entities": page.entities,
                "links_out": page.extract_wikilinks(),
                "links_in": [p.title for p in backlinks],
                "word_count": len(page.body.replace(" ", "").replace("\n", "")),
                "created_at": page.frontmatter.created_at,
                "updated_at": page.frontmatter.updated_at,
                "file_path": str(page.file_path) if page.file_path else None,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 获取页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pages")
async def create_page(data: WikiPageCreate):
    """创建 wiki 页面"""
    try:
        store = _get_wiki_store()
        from novel_agent.wiki import WikiPage, Frontmatter, PageType, now_iso
        
        pt = PageType(data.page_type) if data.page_type in [t.value for t in PageType] else PageType.CUSTOM
        
        page = WikiPage(
            frontmatter=Frontmatter(
                page_type=pt,
                title=data.title,
                tags=_ensure_page_source_tags(data.tags, "manual"),
                sources=data.sources,
                created_at=now_iso(),
                updated_at=now_iso(),
            ),
            body=data.body,
        )
        
        file_path = store.save_page(page)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "file_path": str(file_path),
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 创建页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pages/by-file")
async def update_page_by_file(file_path: str, data: WikiPageUpdate):
    """按文件路径更新 wiki 页面，用于空标题页面。"""
    try:
        store = _get_wiki_store()
        page = store.load_page_by_path(Path(file_path))
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {file_path}")

        if data.body is not None:
            page.body = data.body
        if data.tags is not None:
            page.frontmatter.tags = _ensure_page_source_tags(data.tags, "manual")
        if data.sources is not None:
            page.frontmatter.sources = data.sources
        
        file_path = store.save_page(page)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "file_path": str(file_path),
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 按文件路径更新页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pages/{title}")
async def update_page(title: str, data: WikiPageUpdate):
    """更新 wiki 页面"""
    try:
        store = _get_wiki_store()
        page = store.load_page(title)
        if not page:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        
        if data.body is not None:
            page.body = data.body
        if data.tags is not None:
            page.frontmatter.tags = _ensure_page_source_tags(data.tags, "manual")
        if data.sources is not None:
            page.frontmatter.sources = data.sources

        file_path = store.save_page(page)
        
        return JSONResponse({
            "success": True,
            "data": {
                "title": page.title,
                "file_path": str(file_path),
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 更新页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pages/by-file")
async def delete_page_by_file(file_path: str):
    """按文件路径删除 wiki 页面，用于空标题页面。"""
    try:
        store = _get_wiki_store()
        result = store.delete_page_by_path(Path(file_path))
        if not result:
            raise HTTPException(status_code=404, detail=f"页面不存在: {file_path}")
        return JSONResponse({"success": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 按文件路径删除页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pages/{title}")
async def delete_page(title: str):
    """删除 wiki 页面"""
    try:
        store = _get_wiki_store()
        result = store.delete_page(title)
        if not result:
            raise HTTPException(status_code=404, detail=f"页面不存在: {title}")
        return JSONResponse({"success": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 删除页面失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 搜索 =====

@router.post("/search")
async def search_wiki(data: WikiSearchRequest):
    """多阶段检索"""
    try:
        compat = _get_wiki_compat()
        result = await compat.retriever.retrieve(
            query=data.query,
            context_window=data.context_window,
            top_k=data.top_k,
            include_graph=data.include_graph,
            include_vector=data.include_vector,
        )
        return JSONResponse({
            "success": True,
            "data": result.to_dict(),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/text")
async def text_search(q: str, top_k: int = 10):
    """简单文本搜索"""
    try:
        store = _get_wiki_store()
        pages = store.search_by_text(q, top_k=top_k)
        return JSONResponse({
            "success": True,
            "data": [
                {
                    "title": p.title,
                    "page_type": p.page_type.value,
                    "summary": p.body[:200],
                    "tags": p.tags,
                    "source_mode": _source_mode_from_tags(p.tags),
                }
                for p in pages
            ],
        })
    except Exception as e:
        logger.error(f"[Wiki API] 文本搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 知识图谱 =====

@router.get("/graph")
async def get_graph():
    """获取知识图谱数据"""
    try:
        compat = _get_wiki_compat()
        pages = compat.store.list_pages()
        graph = compat.graph_builder.build_from_pages(pages)
        
        nodes = []
        for title, node in graph.nodes.items():
            nodes.append({
                "id": title,
                "label": title,
                "type": node.page_type.value,
                "degree": node.degree,
                "size": node.display_size,
                "tags": node.tags,
            })
        
        edges = []
        for edge in graph.edges:
            edges.append({
                "source": edge.source,
                "target": edge.target,
                "weight": round(edge.weight, 2),
                "signals": edge.signals,
                "color": edge.display_color,
            })
        
        stats = compat.graph_builder.get_statistics()
        
        return JSONResponse({
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "statistics": stats,
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/backlinks/{title}")
async def get_backlinks(title: str):
    """获取页面的反向链接"""
    try:
        store = _get_wiki_store()
        backlinks = store.get_backlinks(title)
        return JSONResponse({
            "success": True,
            "data": [p.title for p in backlinks],
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取反向链接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/insights")
async def get_graph_insights():
    """获取图谱洞察（意外连接、知识缺口）"""
    try:
        compat = _get_wiki_compat()
        pages = compat.store.list_pages()
        compat.graph_builder.build_from_pages(pages)
        
        surprising = compat.graph_builder.get_surprising_connections()
        gaps = compat.graph_builder.get_knowledge_gaps()
        
        return JSONResponse({
            "success": True,
            "data": {
                "surprising_connections": surprising[:10],
                "knowledge_gaps": gaps[:10],
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取图谱洞察失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationship-graph")
async def get_relationship_graph():
    """获取当前项目已缓存的小说关系图谱。"""
    try:
        _, project_dir = _get_project_manager_and_dir()
        payload = _load_relationship_graph(project_dir)
        return JSONResponse({
            "success": True,
            "data": payload or {
                "nodes": [],
                "edges": [],
                "statistics": {"nodes": 0, "edges": 0, "chapters": 0, "characters": 0, "events": 0},
                "generated_at": "",
                "mode": "character",
                "scope": "all",
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 获取小说关系图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relationship-graph/analyze")
async def analyze_relationship_graph(data: RelationshipGraphRequest):
    """从当前项目章节正文生成小说关系图谱。"""
    try:
        pm, project_dir = _get_project_manager_and_dir()
        chapters = pm.load_project_data("chapters")
        if not isinstance(chapters, list) or not chapters:
            return JSONResponse({
                "success": True,
                "data": {
                    "nodes": [],
                    "edges": [],
                    "statistics": {"nodes": 0, "edges": 0, "chapters": 0, "characters": 0, "events": 0},
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "mode": data.mode,
                    "scope": data.scope,
                    "message": "当前项目还没有可分析的章节正文。",
                },
            })

        selected_chapters = _select_graph_chapters(chapters, data)
        character_seed_names = _iter_character_seed_names(pm.load_project_data("characters"))
        payload = _build_relationship_graph_payload(selected_chapters, data, character_seed_names)
        _save_relationship_graph(project_dir, payload)

        return JSONResponse({"success": True, "data": payload})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Wiki API] 分析小说关系图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Lint =====

@router.get("/lint")
async def run_lint():
    """运行 Lint 质量检查"""
    try:
        compat = _get_wiki_compat()
        report = compat.linter.run_full_check()
        return JSONResponse({
            "success": True,
            "data": {
                "total_pages": report.total_pages,
                "total_links": report.total_links,
                "isolated_count": report.isolated_count,
                "dead_link_count": report.dead_link_count,
                "issues": [
                    {
                        "type": i.issue_type,
                        "severity": i.severity,
                        "page": i.page_title,
                        "description": i.description,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues
                ],
                "summary": report.summary(),
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] Lint 检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Review =====

@router.get("/reviews")
async def list_reviews(status: Optional[str] = None):
    """列出审核项"""
    try:
        compat = _get_wiki_compat()
        items = compat.review.list_items(status=status)
        return JSONResponse({
            "success": True,
            "data": [i.to_dict() for i in items],
            "pending_count": compat.review.get_pending_count(),
        })
    except Exception as e:
        logger.error(f"[Wiki API] 列出审核项失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reviews/{item_id}/approve")
async def approve_review(item_id: str, notes: str = ""):
    """批准审核项"""
    try:
        compat = _get_wiki_compat()
        item = compat.review.approve(item_id, notes)
        if not item:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return JSONResponse({"success": True, "data": item.to_dict()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reviews/{item_id}/reject")
async def reject_review(item_id: str, notes: str = ""):
    """拒绝审核项"""
    try:
        compat = _get_wiki_compat()
        item = compat.review.reject(item_id, notes)
        if not item:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return JSONResponse({"success": True, "data": item.to_dict()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 摄取 =====

@router.post("/ingest")
async def ingest_text(data: WikiIngestRequest):
    """摄取文本内容到 wiki"""
    try:
        compat = _get_wiki_compat()
        result = await compat.ingest.ingest_text(
            content=data.content,
            source_name=data.source_name,
        )
        return JSONResponse({
            "success": result.success,
            "data": {
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "duration": result.duration_seconds,
                "error": result.error,
            },
        })
    except Exception as e:
        logger.error(f"[Wiki API] 摄取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 统计 =====

@router.get("/stats")
async def get_stats():
    """获取 wiki 统计信息"""
    try:
        compat = _get_wiki_compat()
        stats = compat.get_statistics()
        return JSONResponse({
            "success": True,
            "data": stats,
        })
    except Exception as e:
        logger.error(f"[Wiki API] 获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 迁移 =====

@router.post("/migrate")
async def migrate_from_library():
    """从旧资料库迁移数据到 wiki"""
    try:
        compat = _get_wiki_compat()
        stats = compat.migrate_from_library()
        return JSONResponse({
            "success": True,
            "data": stats,
        })
    except Exception as e:
        logger.error(f"[Wiki API] 迁移失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
