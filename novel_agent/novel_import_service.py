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
        candidates = re.findall(r"[\u4e00-\u9fff]{2,4}", content)
        counter: Counter[str] = Counter()
        for candidate in candidates:
            if candidate in _CHARACTER_STOPWORDS:
                continue
            if len(set(candidate)) == 1:
                continue
            counter[candidate] += 1
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
