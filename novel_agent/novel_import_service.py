"""Novel import helpers and isolated memory builders for writing modes."""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

from .constants import get_data_dir
from .knowledge_base.logic_layer.chapter_marker import ChapterMarker
from .utils.atomic_write import atomic_write_json

SUPPORTED_IMPORT_EXTENSIONS = {".txt", ".md", ".docx"}
_SAFE_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_CHARACTER_STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "她们",
    "自己",
    "这个",
    "那个",
    "这里",
    "那里",
    "已经",
    "还是",
    "因为",
    "所以",
    "如果",
    "然后",
    "就是",
    "不是",
    "没有",
    "不会",
    "不能",
    "可能",
    "时候",
    "今天",
    "现在",
    "一个",
    "一种",
    "一些",
    "什么",
    "怎么",
    "为何",
    "为了",
    "之后",
    "之前",
    "主角",
    "配角",
}

_EVENT_KEYWORDS = (
    "说",
    "问",
    "看",
    "走",
    "来到",
    "进入",
    "离开",
    "发现",
    "决定",
    "遇到",
    "救",
    "杀",
    "战",
    "开始",
    "继续",
    "完成",
    "计划",
    "调查",
    "追查",
)

_HOOK_KEYWORDS = (
    "似乎",
    "也许",
    "尚未",
    "未曾",
    "不知道",
    "谜",
    "真相",
    "秘密",
    "疑问",
    "隐约",
)

_TIMELINE_PATTERNS = [
    re.compile(r"第[一二三四五六七八九十百千万\d]+[天年月章回]"),
    re.compile(r"[春夏秋冬][天季]"),
    re.compile(r"(清晨|早晨|上午|中午|下午|傍晚|夜晚|深夜|凌晨)"),
    re.compile(r"\d{1,2}点(?:\d{1,2}分)?"),
]

_LOCATION_SUFFIXES = (
    "城",
    "镇",
    "村",
    "国",
    "界",
    "域",
    "州",
    "郡",
    "府",
    "宫",
    "殿",
    "山",
    "峰",
    "谷",
    "海",
    "湖",
    "河",
    "岛",
    "塔",
    "楼",
    "阁",
    "林",
    "原",
    "关",
    "境",
    "秘境",
)

_FACTION_SUFFIXES = (
    "宗",
    "门",
    "派",
    "盟",
    "教",
    "会",
    "族",
    "军",
    "楼",
    "阁",
    "府",
)

_ITEM_SUFFIXES = (
    "剑",
    "刀",
    "枪",
    "灯",
    "珠",
    "令",
    "图",
    "书",
    "卷",
    "鼎",
    "印",
    "符",
    "甲",
    "衣",
    "戒",
    "瓶",
    "丹",
    "镜",
    "铃",
    "玉",
    "石",
    "钥",
    "牌",
)

_WORLD_RULE_KEYWORDS = (
    "修炼",
    "境界",
    "灵力",
    "法术",
    "魔法",
    "异能",
    "血脉",
    "禁忌",
    "系统",
    "科技",
    "规则",
    "代价",
)


class NovelImportService:
    """Shared import parser and mode-isolated memory writer."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or get_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._chapter_marker = ChapterMarker()

    def parse_novel_file(self, filename: str, raw_bytes: bytes) -> Dict[str, Any]:
        """Parse txt/md/docx payload into normalized chapters."""
        safe_name = (filename or "").strip()
        if not safe_name:
            raise ValueError("filename is required")

        ext = Path(safe_name).suffix.lower()
        if ext not in SUPPORTED_IMPORT_EXTENSIONS:
            raise ValueError("unsupported format, only txt/md/docx are allowed")

        text = self._extract_text(ext, raw_bytes)
        text = self._normalize_text(text)
        if not text.strip():
            raise ValueError("empty file content")

        default_title = Path(safe_name).stem or "Imported Novel"
        chapters = self._split_chapters(text, default_title=default_title)
        if not chapters:
            raise ValueError("unable to parse chapters")

        return {
            "filename": safe_name,
            "extension": ext,
            "content": text,
            "chapters": chapters,
        }

    def refresh_infinite_memory(
        self,
        project_id: str,
        session_id: str,
        chapters: Iterable[Dict[str, Any]],
        source_file: str = "runtime",
    ) -> Dict[str, Any]:
        """Rebuild and persist isolated memory for infinite-write mode."""
        memory = self.build_infinite_memory(
            project_id=project_id,
            session_id=session_id,
            source_file=source_file,
            chapters=chapters,
        )
        self.save_infinite_memory(project_id=project_id, session_id=session_id, payload=memory)
        return memory

    def refresh_collab_memory(
        self,
        project_id: str,
        chapters: Iterable[Dict[str, Any]],
        source_file: str = "runtime",
    ) -> Dict[str, Any]:
        """Rebuild and persist isolated memory for collaborative mode."""
        memory = self.build_collab_memory(
            project_id=project_id,
            source_file=source_file,
            chapters=chapters,
        )
        self.save_collab_memory(project_id=project_id, payload=memory)
        return memory

    def build_infinite_memory(
        self,
        project_id: str,
        session_id: str,
        source_file: str,
        chapters: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build structured continuity memory for infinite-write mode."""
        normalized = self._normalize_chapters(chapters)

        character_counter: Counter[str] = Counter()
        character_last_seen: Dict[str, int] = {}
        timeline_to_chapters: Dict[str, List[int]] = defaultdict(list)
        pending_hooks: List[Dict[str, Any]] = []

        chapter_memory: List[Dict[str, Any]] = []
        for chapter in normalized:
            chapter_number = chapter["chapter_number"]
            for name in chapter["characters"]:
                character_counter[name] += 1
                character_last_seen[name] = chapter_number

            for marker in chapter["timeline_markers"]:
                timeline_to_chapters[marker].append(chapter_number)

            for hook in chapter["open_hooks"]:
                pending_hooks.append({"chapter_number": chapter_number, "hook": hook})

            chapter_memory.append(
                {
                    "chapter_number": chapter_number,
                    "title": chapter["title"],
                    "summary": chapter["summary"],
                    "characters": chapter["characters"],
                    "key_events": chapter["key_events"],
                    "timeline_markers": chapter["timeline_markers"],
                    "open_hooks": chapter["open_hooks"],
                    "word_count": chapter["word_count"],
                }
            )

        character_index = [
            {
                "name": name,
                "appearances": count,
                "last_chapter": character_last_seen.get(name, 0),
            }
            for name, count in character_counter.most_common()
        ]
        timeline_index = [
            {"marker": marker, "chapters": sorted(set(chs))}
            for marker, chs in timeline_to_chapters.items()
        ]

        return {
            "mode": "infinite_write",
            "project_id": project_id,
            "session_id": session_id,
            "source_file": source_file,
            "updated_at": datetime.now().isoformat(),
            "chapter_count": len(normalized),
            "total_words": sum(ch["word_count"] for ch in normalized),
            "chapter_memory": chapter_memory,
            "character_index": character_index,
            "timeline_index": timeline_index,
            "pending_hooks": pending_hooks,
        }

    def build_collab_memory(
        self,
        project_id: str,
        source_file: str,
        chapters: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build structured collaborative memory for write/rewrite/review."""
        normalized = self._normalize_chapters(chapters)
        issue_cards: List[Dict[str, Any]] = []
        edit_tasks: List[Dict[str, Any]] = []
        chapter_cards: List[Dict[str, Any]] = []

        for chapter in normalized:
            chapter_number = chapter["chapter_number"]
            chapter_issues = self._build_collab_issues(chapter)

            chapter_cards.append(
                {
                    "chapter_number": chapter_number,
                    "title": chapter["title"],
                    "summary": chapter["summary"],
                    "key_events": chapter["key_events"],
                    "characters": chapter["characters"],
                    "timeline_markers": chapter["timeline_markers"],
                    "issue_count": len(chapter_issues),
                    "word_count": chapter["word_count"],
                }
            )

            for idx, issue in enumerate(chapter_issues, start=1):
                issue_id = f"ch{chapter_number:03d}-issue-{idx}"
                issue_cards.append(
                    {
                        "issue_id": issue_id,
                        "chapter_number": chapter_number,
                        "title": chapter["title"],
                        "severity": issue["severity"],
                        "problem": issue["problem"],
                        "suggestion": issue["suggestion"],
                    }
                )
                edit_tasks.append(
                    {
                        "task_id": f"{issue_id}-task",
                        "chapter_number": chapter_number,
                        "task": issue["suggestion"],
                        "status": "todo",
                    }
                )

        return {
            "mode": "collab_write",
            "project_id": project_id,
            "source_file": source_file,
            "updated_at": datetime.now().isoformat(),
            "chapter_count": len(normalized),
            "total_words": sum(ch["word_count"] for ch in normalized),
            "chapter_cards": chapter_cards,
            "issue_cards": issue_cards,
            "edit_tasks": edit_tasks,
        }

    def save_infinite_memory(self, project_id: str, session_id: str, payload: Dict[str, Any]) -> Path:
        """Persist isolated infinite-write memory file."""
        path = self._infinite_memory_path(project_id=project_id, session_id=session_id)
        old_content = path.read_text(encoding="utf-8") if path.exists() else None
        atomic_write_json(path, payload, old_content=old_content, ensure_ascii=False, indent=2)
        return path

    def load_infinite_memory(self, project_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._infinite_memory_path(project_id=project_id, session_id=session_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete_infinite_memory(self, project_id: str, session_id: str) -> bool:
        path = self._infinite_memory_path(project_id=project_id, session_id=session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def save_collab_memory(self, project_id: str, payload: Dict[str, Any]) -> Path:
        """Persist isolated collaborative memory file."""
        path = self._collab_memory_path(project_id=project_id)
        old_content = path.read_text(encoding="utf-8") if path.exists() else None
        atomic_write_json(path, payload, old_content=old_content, ensure_ascii=False, indent=2)
        return path

    def load_collab_memory(self, project_id: str) -> Optional[Dict[str, Any]]:
        path = self._collab_memory_path(project_id=project_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def chapters_from_outline(self, outline: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize outline items to chapter schema used by memory builders."""
        normalized: List[Dict[str, Any]] = []
        for index, chapter in enumerate(outline, start=1):
            if not isinstance(chapter, dict):
                continue
            chapter_number = self._positive_int(chapter.get("chapter_number") or chapter.get("number"), index)
            title = str(chapter.get("title") or f"Chapter {chapter_number}").strip() or f"Chapter {chapter_number}"
            content = str(chapter.get("content") or "").strip()
            summary = str(chapter.get("summary") or "").strip()

            hydrated = self._hydrate_chapter(
                chapter_number=chapter_number,
                title=title,
                content=content,
            )
            if summary:
                hydrated["summary"] = summary
            normalized.append(hydrated)
        return normalized

    def build_project_materials(
        self,
        project_id: str,
        source_file: str,
        chapters: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Reverse-extract project materials from imported novel chapters."""
        normalized = self._normalize_chapters(chapters)
        now = datetime.now().isoformat()
        source_title = Path(source_file or "导入小说").stem or "导入小说"
        character_stats = self._collect_character_stats(normalized)
        character_names = set(character_stats.keys())
        items = self._build_reverse_item_rows(normalized, character_names, now, source_file)

        return {
            "project_id": project_id,
            "source_file": source_file,
            "updated_at": now,
            "outline": self._build_reverse_outline(source_title, normalized, now),
            "characters": self._build_reverse_character_cards(character_stats, normalized, now, source_file),
            "worldbuilding": self._build_reverse_worldbuilding(
                source_title,
                normalized,
                character_names,
                items,
                now,
            ),
            "items": items,
            "chapter_summary": self._build_reverse_chapter_summaries(normalized, now, source_file),
            "eventlines": self._build_reverse_eventlines(normalized, character_stats, now, source_file),
        }

    def supplement_project_materials(
        self,
        project_manager: Any,
        source_file: str,
        chapters: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Fill missing project materials without overwriting user-authored data."""
        project_id = str(getattr(project_manager, "current_project_id", "") or "").strip()
        if not project_id:
            return {
                "success": False,
                "error": "no current project",
                "data_types": {},
                "total_added": 0,
                "total_updated": 0,
            }

        materials = self.build_project_materials(
            project_id=project_id,
            source_file=source_file,
            chapters=chapters,
        )
        summary: Dict[str, Any] = {
            "success": True,
            "source_file": source_file,
            "data_types": {},
            "total_added": 0,
            "total_updated": 0,
        }

        for data_type in ("outline", "characters", "worldbuilding", "items", "chapter_summary", "eventlines"):
            generated = materials.get(data_type)
            existing = project_manager.load_project_data(data_type)
            merged, stats = self._merge_material_payload(data_type, existing, generated)
            if stats["added"] or stats["updated"]:
                project_manager.save_project_data(data_type, merged)
                stats["changed"] = True
            summary["data_types"][data_type] = stats
            summary["total_added"] += stats["added"]
            summary["total_updated"] += stats["updated"]

        return summary

    def _merge_material_payload(self, data_type: str, existing: Any, generated: Any) -> tuple[Any, Dict[str, Any]]:
        if data_type == "outline":
            return self._merge_outline_payload(existing, generated)
        if data_type == "characters":
            return self._merge_character_payload(existing, generated)
        if data_type == "worldbuilding":
            return self._merge_worldbuilding_payload(existing, generated)
        if data_type in {"items", "eventlines"}:
            return self._merge_named_row_payload(existing, generated, name_keys=("name", "title"))
        if data_type == "chapter_summary":
            return self._merge_named_row_payload(existing, generated, name_keys=("chapter_number", "name", "title"))
        return generated, {"added": 0, "updated": 0, "total": 0, "changed": False}

    def _build_reverse_outline(self, source_title: str, chapters: List[Dict[str, Any]], now: str) -> Dict[str, Any]:
        total_words = sum(chapter.get("word_count", 0) for chapter in chapters)
        chapter_rows = []
        for chapter in chapters:
            key_events = chapter.get("key_events") if isinstance(chapter.get("key_events"), list) else []
            characters = chapter.get("characters") if isinstance(chapter.get("characters"), list) else []
            hooks = chapter.get("open_hooks") if isinstance(chapter.get("open_hooks"), list) else []
            chapter_rows.append(
                {
                    "chapter_number": chapter["chapter_number"],
                    "title": chapter["title"],
                    "summary": chapter["summary"],
                    "key_event": "；".join(str(event) for event in key_events[:3]),
                    "characters": [str(name) for name in characters[:8]],
                    "ending_hook": str(hooks[0]) if hooks else "",
                    "created_at": now,
                    "updated_at": now,
                    "created_from": "novel_import_reverse_extract",
                }
            )

        progression_lines = self._select_outline_progression_lines(chapter_rows)
        synopsis = " ".join(
            str(chapter.get("summary") or "").strip()
            for chapter in chapters[:8]
            if str(chapter.get("summary") or "").strip()
        )
        if len(synopsis) > 1200:
            synopsis = synopsis[:1199].rstrip() + "…"

        global_outline = "\n".join(
            line
            for line in [
                f"《{source_title}》导入后反向整理：共{len(chapters)}章，约{total_words}字。",
                "主线推进：",
                *progression_lines,
            ]
            if line
        ).strip()

        return {
            "title": source_title,
            "novel_title": source_title,
            "story_synopsis": synopsis,
            "global_outline": global_outline[:8000],
            "volume_plan": self._build_reverse_volume_plan(chapter_rows),
            "chapters": chapter_rows,
            "created_at": now,
            "updated_at": now,
            "created_from": "novel_import_reverse_extract",
        }

    @staticmethod
    def _select_outline_progression_lines(chapter_rows: List[Dict[str, Any]]) -> List[str]:
        if len(chapter_rows) <= 24:
            selected = chapter_rows
        else:
            selected = chapter_rows[:18] + chapter_rows[-6:]

        lines = []
        omitted = len(chapter_rows) - len(selected)
        for index, row in enumerate(selected):
            if omitted and index == 18:
                lines.append(f"...中间省略 {omitted} 章，可在章节列表中查看完整正文。")
            summary = str(row.get("summary") or row.get("key_event") or "").strip()
            if len(summary) > 120:
                summary = summary[:119].rstrip() + "…"
            lines.append(f"- 第{row.get('chapter_number')}章《{row.get('title')}》：{summary}")
        return lines

    @staticmethod
    def _build_reverse_volume_plan(chapter_rows: List[Dict[str, Any]]) -> str:
        if not chapter_rows:
            return ""
        chunk_size = 20
        lines = ["【导入小说分段规划】"]
        for chunk_index in range(0, len(chapter_rows), chunk_size):
            chunk = chapter_rows[chunk_index: chunk_index + chunk_size]
            start = chunk[0].get("chapter_number")
            end = chunk[-1].get("chapter_number")
            first_summary = str(chunk[0].get("summary") or "").strip()
            last_summary = str(chunk[-1].get("summary") or "").strip()
            summary = first_summary if first_summary == last_summary else "；".join(part for part in [first_summary, last_summary] if part)
            if len(summary) > 180:
                summary = summary[:179].rstrip() + "…"
            lines.append(f"第{chunk_index // chunk_size + 1}段：第{start}-{end}章")
            if summary:
                lines.append(f"- 概述：{summary}")
        return "\n".join(lines).strip()

    def _collect_character_stats(self, chapters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        chapter_names: Dict[int, List[str]] = {}

        for chapter in chapters:
            content = str(chapter.get("content") or "")
            names = self._refine_character_names(chapter.get("characters") or [], content)
            chapter_names[chapter["chapter_number"]] = names
            for name in names:
                record = stats.setdefault(
                    name,
                    {
                        "name": name,
                        "appearances": 0,
                        "chapters": [],
                        "events": [],
                        "hooks": [],
                        "relationships": Counter(),
                    },
                )
                record["appearances"] += 1
                record["chapters"].append(chapter["chapter_number"])
                for event in chapter.get("key_events") or []:
                    event_text = str(event).strip()
                    if event_text and name in event_text:
                        record["events"].append({"chapter_number": chapter["chapter_number"], "text": event_text})
                for hook in chapter.get("open_hooks") or []:
                    hook_text = str(hook).strip()
                    if hook_text and name in hook_text:
                        record["hooks"].append(hook_text)

        for names in chapter_names.values():
            for name in names:
                record = stats.get(name)
                if not record:
                    continue
                for other in names:
                    if other != name:
                        record["relationships"][other] += 1

        return dict(
            sorted(
                stats.items(),
                key=lambda item: (-item[1]["appearances"], item[1]["chapters"][0], item[0]),
            )
        )

    def _build_reverse_character_cards(
        self,
        character_stats: Dict[str, Dict[str, Any]],
        chapters: List[Dict[str, Any]],
        now: str,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        for index, (name, record) in enumerate(character_stats.items()):
            first_chapter = record["chapters"][0] if record["chapters"] else 0
            first_summary = self._chapter_summary_by_number(chapters, first_chapter)
            events = record.get("events") or []
            development_history = [
                {
                    "chapter_number": event["chapter_number"],
                    "event_type": "import_reverse_extract",
                    "title": event["text"][:30],
                    "description": event["text"],
                }
                for event in events[:8]
            ]
            relationship_counter: Counter[str] = record.get("relationships", Counter())
            relationships = {
                other: "同章出现/剧情相关"
                for other, _count in relationship_counter.most_common(8)
            }
            role = "主角" if index == 0 else "配角"
            cards.append(
                {
                    "name": name,
                    "role": role,
                    "description": (
                        f"从导入小说《{Path(source_file or '导入小说').stem}》反向提取。"
                        f"第{first_chapter}章首次出现，共在{record['appearances']}章中出现。"
                    ),
                    "identity": "导入小说角色",
                    "personality": [],
                    "abilities": [],
                    "inventory": [],
                    "development_history": development_history,
                    "background": first_summary,
                    "goals": record.get("hooks", [])[:3],
                    "relationships": relationships,
                    "notes": "由导入小说自动反推生成，请按需要人工校准。",
                    "tags": ["导入反推"],
                    "first_appearance": first_chapter,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    "source_file": source_file,
                }
            )
        return cards

    def _build_reverse_worldbuilding(
        self,
        source_title: str,
        chapters: List[Dict[str, Any]],
        character_names: set[str],
        item_rows: List[Dict[str, Any]],
        now: str,
    ) -> Dict[str, Any]:
        text = "\n".join(str(chapter.get("content") or "") for chapter in chapters)
        locations = self._extract_named_entities_by_suffix(text, _LOCATION_SUFFIXES, exclude=character_names, top_k=24)
        factions = self._extract_named_entities_by_suffix(text, _FACTION_SUFFIXES, exclude=character_names, top_k=16)
        rules = self._extract_rule_sentences(chapters)
        timeline_markers = []
        for chapter in chapters:
            for marker in chapter.get("timeline_markers") or []:
                marker = str(marker).strip()
                if marker and marker not in timeline_markers:
                    timeline_markers.append(marker)

        world_locations = {
            name: {
                "description": self._find_sentence_for_entity(text, name) or "导入小说中出现的地点。",
                "tags": ["导入反推"],
            }
            for name in locations
        }
        world_items = {
            item["name"]: {
                "description": item.get("description", ""),
                "details": item.get("details", ""),
                "tags": ["导入反推"],
            }
            for item in item_rows
        }
        events = [
            {
                "title": f"第{chapter['chapter_number']}章 {chapter['title']}",
                "description": chapter.get("summary", ""),
                "date": "、".join(chapter.get("timeline_markers") or []),
                "participants": chapter.get("characters") or [],
            }
            for chapter in chapters[:80]
            if chapter.get("summary")
        ]

        return {
            "world": {
                "name": f"{source_title}世界观",
                "world_name": f"{source_title}世界观",
                "world_type": "导入小说反向提取",
                "theme": self._build_theme_from_chapters(chapters),
                "geography": "；".join(locations[:12]),
                "timeline": "；".join(timeline_markers[:20]),
                "rules": rules,
                "factions": [
                    {
                        "name": faction,
                        "description": self._find_sentence_for_entity(text, faction) or "导入小说中出现的势力。",
                        "tags": ["导入反推"],
                    }
                    for faction in factions
                ],
                "requirements": "自动反推资料仅作为初稿，建议人工核对角色、地点、势力与规则。",
                "created_at": now,
                "updated_at": now,
            },
            "locations": world_locations,
            "items": world_items,
            "events": events,
        }

    def _build_reverse_item_rows(
        self,
        chapters: List[Dict[str, Any]],
        character_names: set[str],
        now: str,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        text = "\n".join(str(chapter.get("content") or "") for chapter in chapters)
        item_names = self._extract_named_entities_by_suffix(text, _ITEM_SUFFIXES, exclude=character_names, top_k=24)
        rows = []
        for name in item_names:
            sentence = self._find_sentence_for_entity(text, name)
            rows.append(
                {
                    "name": name,
                    "item_type": "未分类",
                    "description": sentence or "导入小说中出现的物品/线索。",
                    "details": sentence,
                    "status": "已出现",
                    "effects": [],
                    "history": [],
                    "tags": ["导入反推"],
                    "source_file": source_file,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return rows

    @staticmethod
    def _build_reverse_chapter_summaries(
        chapters: List[Dict[str, Any]],
        now: str,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        rows = []
        for chapter in chapters:
            rows.append(
                {
                    "chapter_number": chapter["chapter_number"],
                    "name": f"第{chapter['chapter_number']}章 {chapter['title']}",
                    "summary_text": chapter.get("summary", ""),
                    "key_events": chapter.get("key_events") or [],
                    "appearing_characters": chapter.get("characters") or [],
                    "ending_hook": (chapter.get("open_hooks") or [""])[0],
                    "source_file": source_file,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return rows

    @staticmethod
    def _build_reverse_eventlines(
        chapters: List[Dict[str, Any]],
        character_stats: Dict[str, Dict[str, Any]],
        now: str,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        participants = list(character_stats.keys())[:8]
        first_summary = str(chapters[0].get("summary") or "").strip() if chapters else ""
        last_summary = str(chapters[-1].get("summary") or "").strip() if chapters else ""
        conflict = "；".join(part for part in [first_summary, last_summary] if part)
        rows = []
        if conflict:
            rows.append(
                {
                    "name": "导入小说主线",
                    "participants": participants,
                    "conflict": conflict[:600],
                    "status": "推进中",
                    "notes": "由导入小说反向提取，可继续拆分为更细事件线。",
                    "source_file": source_file,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        hooks = []
        for chapter in chapters:
            for hook in chapter.get("open_hooks") or []:
                hook = str(hook).strip()
                if hook and hook not in hooks:
                    hooks.append(hook)
        for index, hook in enumerate(hooks[:5], start=1):
            rows.append(
                {
                    "name": f"悬念线索 {index}",
                    "participants": [name for name in participants if name in hook],
                    "conflict": hook,
                    "status": "推进中",
                    "notes": "导入文本中识别到的未解悬念。",
                    "source_file": source_file,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return rows

    def _merge_outline_payload(self, existing: Any, generated: Any) -> tuple[Any, Dict[str, Any]]:
        if self._is_empty_material_value(generated):
            return existing, {"added": 0, "updated": 0, "total": 0, "changed": False}
        if self._is_empty_material_value(existing):
            chapter_count = len(generated.get("chapters") or []) if isinstance(generated, dict) else 0
            return generated, {"added": max(1, chapter_count), "updated": 0, "total": chapter_count, "changed": True}

        if isinstance(existing, dict) and isinstance(generated, dict):
            merged = dict(existing)
            added = 0
            updated = 0
            for key in ("title", "novel_title", "story_synopsis", "global_outline", "volume_plan"):
                if self._is_empty_material_value(merged.get(key)) and not self._is_empty_material_value(generated.get(key)):
                    merged[key] = generated[key]
                    updated += 1
            existing_chapters = merged.get("chapters") if isinstance(merged.get("chapters"), list) else []
            merged_chapters, row_stats = self._merge_rows_by_key(existing_chapters, generated.get("chapters") or [], ("chapter_number", "title"))
            if row_stats["added"] or row_stats["updated"]:
                merged["chapters"] = merged_chapters
                added += row_stats["added"]
                updated += row_stats["updated"]
            return merged, {"added": added, "updated": updated, "total": len(merged.get("chapters") or []), "changed": bool(added or updated)}

        if isinstance(existing, list) and isinstance(generated, dict):
            overview_row = {
                "title": "主线大纲",
                "name": "主线大纲",
                "summary": generated.get("global_outline") or generated.get("story_synopsis") or "",
                "global_outline": generated.get("global_outline", ""),
                "volume_plan": generated.get("volume_plan", ""),
                "story_synopsis": generated.get("story_synopsis", ""),
                "novel_title": generated.get("novel_title", generated.get("title", "")),
                "created_from": "novel_import_reverse_extract",
            }
            generated_rows = [overview_row] + (generated.get("chapters") or [])
            return self._merge_named_row_payload(existing, generated_rows, name_keys=("chapter_number", "title", "name"))

        return existing, {"added": 0, "updated": 0, "total": 0, "changed": False}

    def _merge_character_payload(self, existing: Any, generated: Any) -> tuple[Any, Dict[str, Any]]:
        generated_rows = [row for row in generated if isinstance(row, dict)] if isinstance(generated, list) else []
        if not generated_rows:
            total = len(existing) if isinstance(existing, (list, dict)) else 0
            return existing, {"added": 0, "updated": 0, "total": total, "changed": False}

        existing_map = self._normalize_character_map(existing)
        added = 0
        updated = 0
        for row in generated_rows:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            if name not in existing_map:
                existing_map[name] = dict(row)
                added += 1
                continue
            if self._fill_missing_fields(existing_map[name], row):
                updated += 1

        if isinstance(existing, dict) and "characters" in existing:
            merged_payload = dict(existing)
            merged_payload["characters"] = existing_map
        elif isinstance(existing, list):
            merged_payload = list(existing_map.values())
        else:
            merged_payload = existing_map
        return merged_payload, {"added": added, "updated": updated, "total": len(existing_map), "changed": bool(added or updated)}

    def _merge_worldbuilding_payload(self, existing: Any, generated: Any) -> tuple[Any, Dict[str, Any]]:
        if not isinstance(generated, dict) or self._is_empty_material_value(generated):
            return existing, {"added": 0, "updated": 0, "total": 0, "changed": False}
        if self._is_empty_material_value(existing):
            total = 1 + len(generated.get("locations") or {}) + len(generated.get("items") or {}) + len(generated.get("events") or [])
            return generated, {"added": total, "updated": 0, "total": total, "changed": True}

        if isinstance(existing, list):
            rows = self._worldbuilding_payload_to_rows(generated)
            return self._merge_named_row_payload(existing, rows, name_keys=("name", "title"))
        if not isinstance(existing, dict):
            return existing, {"added": 0, "updated": 0, "total": 0, "changed": False}

        merged = dict(existing)
        added = 0
        updated = 0
        world = dict(merged.get("world")) if isinstance(merged.get("world"), dict) else {}
        generated_world = generated.get("world") if isinstance(generated.get("world"), dict) else {}
        if self._fill_missing_fields(world, generated_world):
            updated += 1
        merged["world"] = world

        for section in ("locations", "items"):
            target = dict(merged.get(section)) if isinstance(merged.get(section), dict) else {}
            source = generated.get(section) if isinstance(generated.get(section), dict) else {}
            for name, payload in source.items():
                if name not in target:
                    target[name] = payload
                    added += 1
                elif isinstance(target.get(name), dict) and isinstance(payload, dict) and self._fill_missing_fields(target[name], payload):
                    updated += 1
            merged[section] = target

        existing_events = merged.get("events") if isinstance(merged.get("events"), list) else []
        merged_events, event_stats = self._merge_rows_by_key(existing_events, generated.get("events") or [], ("title", "name"))
        if event_stats["added"] or event_stats["updated"]:
            merged["events"] = merged_events
            added += event_stats["added"]
            updated += event_stats["updated"]

        total = 1 + len(merged.get("locations") or {}) + len(merged.get("items") or {}) + len(merged.get("events") or [])
        return merged, {"added": added, "updated": updated, "total": total, "changed": bool(added or updated)}

    def _merge_named_row_payload(
        self,
        existing: Any,
        generated: Any,
        *,
        name_keys: tuple[str, ...],
    ) -> tuple[Any, Dict[str, Any]]:
        existing_rows = [dict(row) for row in existing if isinstance(row, dict)] if isinstance(existing, list) else []
        generated_rows = [dict(row) for row in generated if isinstance(row, dict)] if isinstance(generated, list) else []
        merged, stats = self._merge_rows_by_key(existing_rows, generated_rows, name_keys)
        stats["changed"] = bool(stats["added"] or stats["updated"])
        return merged, stats

    def _merge_rows_by_key(
        self,
        existing_rows: List[Dict[str, Any]],
        generated_rows: List[Dict[str, Any]],
        key_fields: tuple[str, ...],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        merged = [dict(row) for row in existing_rows]
        index_by_key: Dict[str, int] = {}
        for index, row in enumerate(merged):
            key = self._row_merge_key(row, key_fields)
            if key:
                index_by_key.setdefault(key, index)

        added = 0
        updated = 0
        for row in generated_rows:
            key = self._row_merge_key(row, key_fields)
            match_index = index_by_key.get(key) if key else None
            if match_index is None:
                if key:
                    index_by_key[key] = len(merged)
                merged.append(dict(row))
                added += 1
                continue
            if self._fill_missing_fields(merged[match_index], row):
                updated += 1
        return merged, {"added": added, "updated": updated, "total": len(merged)}

    @staticmethod
    def _row_merge_key(row: Dict[str, Any], key_fields: tuple[str, ...]) -> str:
        for key in key_fields:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return f"{key}:{text}"
        return ""

    def _fill_missing_fields(self, target: Dict[str, Any], source: Dict[str, Any]) -> bool:
        changed = False
        for key, value in source.items():
            if key in {"created_at", "updated_at"}:
                continue
            if self._is_empty_material_value(value):
                continue
            current = target.get(key)
            if self._is_empty_material_value(current):
                target[key] = value
                changed = True
                continue
            if isinstance(current, list) and isinstance(value, list):
                seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in current}
                for item in value:
                    fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
                    if fingerprint not in seen:
                        current.append(item)
                        seen.add(fingerprint)
                        changed = True
                continue
            if isinstance(current, dict) and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key not in current and not self._is_empty_material_value(sub_value):
                        current[sub_key] = sub_value
                        changed = True
        return changed

    @staticmethod
    def _is_empty_material_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) == 0
        return False

    def _normalize_character_map(self, payload: Any) -> Dict[str, Dict[str, Any]]:
        if isinstance(payload, dict) and "characters" in payload:
            payload = payload.get("characters")
        if isinstance(payload, dict):
            rows = []
            for name, row in payload.items():
                if isinstance(row, dict):
                    copied = dict(row)
                    copied.setdefault("name", str(name))
                    rows.append(copied)
            return {
                str(row.get("name") or "").strip(): row
                for row in rows
                if str(row.get("name") or "").strip()
            }
        if isinstance(payload, list):
            return {
                str(row.get("name") or "").strip(): dict(row)
                for row in payload
                if isinstance(row, dict) and str(row.get("name") or "").strip()
            }
        return {}

    @staticmethod
    def _worldbuilding_payload_to_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        world = payload.get("world") if isinstance(payload.get("world"), dict) else {}
        if world:
            rows.append(
                {
                    "name": world.get("name") or world.get("world_name") or "导入小说世界观",
                    "kind": "world",
                    "description": world.get("world_type") or "导入小说反向提取",
                    "details": world.get("theme") or world.get("requirements") or "",
                }
            )
            for key, label in (
                ("geography", "地理环境"),
                ("timeline", "时间线"),
            ):
                if world.get(key):
                    rows.append({"name": label, "kind": key, "description": world.get(key), "details": world.get(key)})
            for rule in world.get("rules") or []:
                rows.append({"name": "世界规则", "kind": "rule", "description": rule})
            for faction in world.get("factions") or []:
                if isinstance(faction, dict):
                    rows.append({
                        "name": faction.get("name") or "势力阵营",
                        "kind": "faction",
                        "description": faction.get("description", ""),
                        "details": faction.get("details", ""),
                    })
        for section, kind in (("locations", "location"), ("items", "item")):
            source = payload.get(section) if isinstance(payload.get(section), dict) else {}
            for name, row in source.items():
                rows.append({
                    "name": str(name),
                    "kind": kind,
                    "description": row.get("description", "") if isinstance(row, dict) else str(row),
                    "details": row.get("details", "") if isinstance(row, dict) else "",
                })
        for event in payload.get("events") or []:
            if isinstance(event, dict):
                rows.append({
                    "name": event.get("title") or event.get("name") or "历史事件",
                    "kind": "event",
                    "description": event.get("description", ""),
                    "details": event.get("details", ""),
                })
        return rows

    @staticmethod
    def _refine_character_names(raw_names: Iterable[Any], content: str) -> List[str]:
        refined = []
        for raw in raw_names:
            name = str(raw or "").strip()
            if not NovelImportService._looks_like_character_name(name):
                continue
            if name not in content:
                continue
            if name not in refined:
                refined.append(name)
        return refined[:12]

    @staticmethod
    def _looks_like_character_name(name: str) -> bool:
        if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name or ""):
            return False
        if name in _CHARACTER_STOPWORDS:
            return False
        if name.endswith(_LOCATION_SUFFIXES) or name.endswith(_FACTION_SUFFIXES) or name.endswith(_ITEM_SUFFIXES):
            return False
        return len(set(name)) > 1

    @staticmethod
    def _extract_named_entities_by_suffix(
        text: str,
        suffixes: tuple[str, ...],
        *,
        exclude: set[str],
        top_k: int,
    ) -> List[str]:
        counter: Counter[str] = Counter()
        suffix_pattern = "|".join(sorted((re.escape(item) for item in suffixes), key=len, reverse=True))
        pattern = re.compile(rf"[\u4e00-\u9fff]{{1,6}}(?:{suffix_pattern})")
        for match in pattern.findall(text or ""):
            name = NovelImportService._trim_named_entity_match(match, suffixes)
            if len(name) < 2 or name in exclude or name in _CHARACTER_STOPWORDS:
                continue
            if len(set(name)) == 1:
                continue
            counter[name] += 1
        return [name for name, _count in counter.most_common(top_k)]

    @staticmethod
    def _trim_named_entity_match(raw: str, suffixes: tuple[str, ...]) -> str:
        text = str(raw or "").strip()
        suffix = next((item for item in sorted(suffixes, key=len, reverse=True) if text.endswith(item)), "")
        if not suffix:
            return text
        stem = text[: -len(suffix)] if suffix else text
        for delimiter in (
            "进入",
            "来到",
            "前往",
            "返回",
            "离开",
            "遇见",
            "发现",
            "提醒",
            "修炼",
            "藏着",
            "有关",
            "在",
            "到",
            "入",
            "进",
            "与",
            "和",
            "向",
            "对",
            "说",
        ):
            if delimiter in stem:
                stem = stem.rsplit(delimiter, 1)[-1]
        stem = stem.strip()
        if len(stem) > 4:
            stem = stem[-4:]
        name = f"{stem}{suffix}".strip()
        if len(name) < 2:
            return ""
        if any(name.startswith(prefix) for prefix in ("修炼", "发现", "提醒", "进入", "来到", "有关")):
            return ""
        return name

    @staticmethod
    def _extract_rule_sentences(chapters: List[Dict[str, Any]], top_k: int = 12) -> List[str]:
        rules = []
        for chapter in chapters:
            for sentence in re.split(r"[。！？!?\n]+", str(chapter.get("content") or "")):
                text = sentence.strip()
                if len(text) < 8:
                    continue
                if any(keyword in text for keyword in _WORLD_RULE_KEYWORDS):
                    clipped = text[:120]
                    if clipped not in rules:
                        rules.append(clipped)
                if len(rules) >= top_k:
                    return rules
        return rules

    @staticmethod
    def _find_sentence_for_entity(text: str, entity: str) -> str:
        if not text or not entity:
            return ""
        for sentence in re.split(r"[。！？!?\n]+", text):
            stripped = sentence.strip()
            if entity in stripped:
                return stripped[:180]
        return ""

    @staticmethod
    def _build_theme_from_chapters(chapters: List[Dict[str, Any]]) -> str:
        summaries = [str(chapter.get("summary") or "").strip() for chapter in chapters[:6]]
        theme = " ".join(summary for summary in summaries if summary)
        if len(theme) > 600:
            theme = theme[:599].rstrip() + "…"
        return theme

    @staticmethod
    def _chapter_summary_by_number(chapters: List[Dict[str, Any]], chapter_number: int) -> str:
        for chapter in chapters:
            if int(chapter.get("chapter_number") or 0) == int(chapter_number or 0):
                return str(chapter.get("summary") or "").strip()
        return ""

    def _extract_text(self, extension: str, raw_bytes: bytes) -> str:
        if extension == ".docx":
            return self._extract_docx_text(raw_bytes)
        return self._decode_text_bytes(raw_bytes)

    @staticmethod
    def _decode_text_bytes(raw_bytes: bytes) -> str:
        encodings = ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16")
        for encoding in encodings:
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_docx_text(raw_bytes: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
                xml_bytes = archive.read("word/document.xml")
        except Exception as exc:
            raise ValueError("invalid docx file") from exc

        try:
            root = ElementTree.fromstring(xml_bytes)
        except Exception as exc:
            raise ValueError("cannot parse docx xml") from exc

        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: List[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            runs = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
            line = "".join(runs).strip()
            if line:
                paragraphs.append(line)
        return "\n".join(paragraphs)

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _split_chapters(self, text: str, default_title: str) -> List[Dict[str, Any]]:
        chapters: List[Dict[str, Any]] = []

        detected = self._chapter_marker.detect_chapters(text)
        for idx, mark in enumerate(detected, start=1):
            content = (mark.content or "").strip()
            if not content:
                continue
            chapter_number = self._positive_int(mark.chapter_number, idx)
            title = (mark.title or f"Chapter {chapter_number}").strip() or f"Chapter {chapter_number}"
            chapters.append(
                self._hydrate_chapter(
                    chapter_number=chapter_number,
                    title=title,
                    content=content,
                )
            )

        if len(chapters) >= 2:
            return chapters
        if len(chapters) == 1 and chapters[0]["word_count"] >= 300:
            return chapters

        markdown_chapters = self._split_markdown_chapters(text)
        if markdown_chapters:
            return markdown_chapters

        return [
            self._hydrate_chapter(
                chapter_number=1,
                title=default_title,
                content=text.strip(),
            )
        ]

    def _split_markdown_chapters(self, text: str) -> List[Dict[str, Any]]:
        heading_pattern = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(text))
        if not matches:
            return []

        chapters: List[Dict[str, Any]] = []
        for index, match in enumerate(matches, start=1):
            raw_title = (match.group(1) or "").strip()
            chapter_number, title = self._parse_heading_metadata(raw_title, index)
            content_start = match.end()
            content_end = matches[index].start() if index < len(matches) else len(text)
            content = text[content_start:content_end].strip()
            if not content:
                continue
            chapters.append(
                self._hydrate_chapter(
                    chapter_number=chapter_number,
                    title=title,
                    content=content,
                )
            )
        return chapters

    def _parse_heading_metadata(self, title: str, fallback_number: int) -> tuple[int, str]:
        chapter_number, parsed_title = self._chapter_marker._parse_chapter_title(title)
        normalized_number = self._positive_int(chapter_number, fallback_number)
        normalized_title = (parsed_title or title or f"Chapter {normalized_number}").strip()
        return normalized_number, normalized_title or f"Chapter {normalized_number}"

    def _hydrate_chapter(self, chapter_number: int, title: str, content: str) -> Dict[str, Any]:
        content = (content or "").strip()
        summary = self._build_summary(content)
        characters = self._extract_characters(content)
        events = self._extract_key_events(content)
        timeline_markers = self._extract_timeline_markers(content)
        open_hooks = self._extract_open_hooks(content)

        return {
            "chapter_number": chapter_number,
            "title": title or f"Chapter {chapter_number}",
            "content": content,
            "summary": summary,
            "word_count": self._count_words(content),
            "created_at": datetime.now().isoformat(),
            "important_events": "; ".join(events[:3]),
            "new_characters": ", ".join(characters[:5]),
            "characters": characters,
            "key_events": events,
            "timeline_markers": timeline_markers,
            "open_hooks": open_hooks,
        }

    def _normalize_chapters(self, chapters: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            chapter_number = self._positive_int(chapter.get("chapter_number"), index)

            title = str(chapter.get("title") or f"Chapter {chapter_number}").strip() or f"Chapter {chapter_number}"
            content = str(chapter.get("content") or "").strip()
            summary = str(chapter.get("summary") or "").strip() or self._build_summary(content)

            characters = chapter.get("characters")
            if not isinstance(characters, list):
                characters = self._extract_characters(content)
            key_events = chapter.get("key_events")
            if not isinstance(key_events, list):
                key_events = self._extract_key_events(content)
            timeline_markers = chapter.get("timeline_markers")
            if not isinstance(timeline_markers, list):
                timeline_markers = self._extract_timeline_markers(content)
            open_hooks = chapter.get("open_hooks")
            if not isinstance(open_hooks, list):
                open_hooks = self._extract_open_hooks(content)

            word_count = chapter.get("word_count")
            if isinstance(word_count, int) and word_count >= 0:
                normalized_word_count = word_count
            else:
                normalized_word_count = self._count_words(content)

            normalized.append(
                {
                    "chapter_number": chapter_number,
                    "title": title,
                    "content": content,
                    "summary": summary,
                    "characters": characters,
                    "key_events": key_events,
                    "timeline_markers": timeline_markers,
                    "open_hooks": open_hooks,
                    "word_count": normalized_word_count,
                }
            )

        normalized.sort(key=lambda row: row["chapter_number"])
        return normalized

    @staticmethod
    def _positive_int(value: Any, fallback: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = int(fallback)
        return number if number > 0 else int(fallback)

    @staticmethod
    def _build_summary(content: str, max_chars: int = 220) -> str:
        if not content:
            return ""
        sentences = re.split(r"(?<=[。！？!?])", content)
        picked: List[str] = []
        total = 0
        for sentence in sentences:
            stripped = sentence.strip()
            if not stripped:
                continue
            picked.append(stripped)
            total += len(stripped)
            if total >= max_chars or len(picked) >= 3:
                break
        summary = "".join(picked).strip()
        if not summary:
            summary = content[:max_chars].strip()
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"
        return summary

    @staticmethod
    def _extract_characters(content: str, top_k: int = 8) -> List[str]:
        if not content:
            return []
        counter: Counter[str] = Counter()

        context_patterns = (
            r"([\u4e00-\u9fff]{2,4})(?=(?:说|问|道|决定|提醒|发现|进入|离开|遇见|调查|追查|修炼|看见|看到|走向|回头|点头|摇头|笑|喊))",
            r"(?:和|与|跟|对|向|遇见|提醒)([\u4e00-\u9fff]{2,4})",
            r"([\u4e00-\u9fff]{2,4})(?:和|与|跟)",
        )
        for pattern in context_patterns:
            for candidate in re.findall(pattern, content):
                if NovelImportService._looks_like_character_name(candidate):
                    counter[candidate] += 5

        for run in re.findall(r"[\u4e00-\u9fff]{2,}", content):
            for size in (2, 3):
                if len(run) < size:
                    continue
                for start in range(0, len(run) - size + 1):
                    candidate = run[start:start + size]
                    if not NovelImportService._looks_like_character_name(candidate):
                        continue
                    counter[candidate] += 1

        for candidate in list(counter):
            if candidate in _CHARACTER_STOPWORDS:
                continue
            if len(set(candidate)) == 1:
                del counter[candidate]
        return [name for name, _ in counter.most_common(top_k)]

    @staticmethod
    def _extract_key_events(content: str, top_k: int = 6) -> List[str]:
        if not content:
            return []
        chunks = re.split(r"[。！？!?\n]+", content)
        events: List[str] = []
        for chunk in chunks:
            sentence = chunk.strip()
            if len(sentence) < 6:
                continue
            if not any(keyword in sentence for keyword in _EVENT_KEYWORDS):
                continue
            events.append(sentence[:80])
            if len(events) >= top_k:
                break
        return events

    @staticmethod
    def _extract_timeline_markers(content: str, top_k: int = 8) -> List[str]:
        if not content:
            return []
        found: List[str] = []
        for pattern in _TIMELINE_PATTERNS:
            for match in pattern.findall(content):
                marker = match if isinstance(match, str) else "".join(match)
                marker = marker.strip()
                if marker and marker not in found:
                    found.append(marker)
                if len(found) >= top_k:
                    return found
        return found

    @staticmethod
    def _extract_open_hooks(content: str, top_k: int = 6) -> List[str]:
        if not content:
            return []
        hooks: List[str] = []
        for sentence in re.split(r"[。！？!?\n]+", content):
            stripped = sentence.strip()
            if len(stripped) < 6:
                continue
            if "?" in sentence or "？" in sentence or any(key in stripped for key in _HOOK_KEYWORDS):
                hooks.append(stripped[:90])
                if len(hooks) >= top_k:
                    break
        return hooks

    @staticmethod
    def _count_words(content: str) -> int:
        if not content:
            return 0
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", content))
        latin_words = len(re.findall(r"[A-Za-z0-9_]+", content))
        return chinese_chars + latin_words

    @staticmethod
    def _safe_component(value: str, field_name: str, allow_empty: bool = False) -> str:
        text = (value or "").strip()
        if not text:
            if allow_empty:
                return ""
            raise ValueError(f"{field_name} cannot be empty")
        if not _SAFE_COMPONENT_PATTERN.fullmatch(text):
            raise ValueError(f"{field_name} contains invalid characters")
        return text

    def _infinite_memory_path(self, project_id: str, session_id: str) -> Path:
        safe_project = self._safe_component(project_id, "project_id", allow_empty=True) or "default"
        safe_session = self._safe_component(session_id, "session_id")
        path = (
            self.data_dir
            / "projects"
            / safe_project
            / "mode_memory"
            / "infinite_write"
            / f"{safe_session}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _collab_memory_path(self, project_id: str) -> Path:
        safe_project = self._safe_component(project_id, "project_id", allow_empty=True) or "default"
        path = (
            self.data_dir
            / "projects"
            / safe_project
            / "mode_memory"
            / "collab_write"
            / "memory.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _build_collab_issues(chapter: Dict[str, Any]) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        word_count = int(chapter.get("word_count") or 0)
        if word_count < 400:
            issues.append(
                {
                    "severity": "medium",
                    "problem": "chapter content is relatively short",
                    "suggestion": "expand action details or character interaction to improve readability",
                }
            )
        if not chapter.get("key_events"):
            issues.append(
                {
                    "severity": "medium",
                    "problem": "no clear key events detected",
                    "suggestion": "clarify one to three concrete events to improve chapter progression",
                }
            )
        if not chapter.get("characters"):
            issues.append(
                {
                    "severity": "low",
                    "problem": "no stable character signals detected",
                    "suggestion": "strengthen character names and relation mentions for collaboration consistency",
                }
            )
        summary = str(chapter.get("summary") or "")
        if len(summary) < 30:
            issues.append(
                {
                    "severity": "low",
                    "problem": "summary is too short",
                    "suggestion": "rewrite chapter summary to include setup, conflict, and outcome",
                }
            )
        return issues


_novel_import_service: Optional[NovelImportService] = None


def get_novel_import_service(data_dir: Optional[Path] = None) -> NovelImportService:
    """Return global singleton of novel import service."""
    global _novel_import_service
    if _novel_import_service is None:
        _novel_import_service = NovelImportService(data_dir=data_dir)
        return _novel_import_service

    if data_dir is not None:
        target_dir = Path(data_dir).resolve()
        current_dir = Path(_novel_import_service.data_dir).resolve()
        if target_dir != current_dir:
            _novel_import_service = NovelImportService(data_dir=target_dir)
    return _novel_import_service
