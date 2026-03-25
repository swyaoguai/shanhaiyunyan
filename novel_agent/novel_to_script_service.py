"""Novel-to-script conversion helpers."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .novel_import_service import NovelImportService

NOVEL_TO_SCRIPT_STATE_KEY = "novel_to_script_draft"
DEFAULT_SCRIPT_STYLE = "scene_block_webnovel_script"
DEFAULT_CONVERT_CONFIG = {
    "script_style": DEFAULT_SCRIPT_STYLE,
    "convert_mode": "auto",
    "scene_density": "medium",
    "dialogue_ratio": "medium",
    "keep_voice_style": True,
    "human_name_strategy": "keep_original",
}

SINGLE_PASS_MAX_WORDS = 15_000
CHAPTERWISE_MAX_WORDS = 80_000
BATCH_TARGET_WORDS = 12_000
BATCH_CHAPTER_LIMIT = 6
CHAPTER_SPLIT_WORDS = 18_000
INLINE_SPLIT_WORDS = 12_000

SCRIPT_STYLE_OPTIONS = [
    {"value": "scene_block_webnovel_script", "label": "网文场景台本"},
    {"value": "dialogue_enhanced_script", "label": "对话强化版"},
    {"value": "web_short_drama_script", "label": "网文短剧版"},
]

CONVERT_MODE_OPTIONS = [
    {"value": "auto", "label": "自动识别（推荐）"},
    {"value": "full_text", "label": "单次转换"},
    {"value": "chapterwise", "label": "按章节转换"},
    {"value": "batchwise", "label": "批量转换"},
]

DENSITY_OPTIONS = [
    {"value": "low", "label": "低"},
    {"value": "medium", "label": "中"},
    {"value": "high", "label": "高"},
]

DIALOGUE_RATIO_OPTIONS = deepcopy(DENSITY_OPTIONS)
HUMAN_NAME_OPTIONS = [
    {"value": "keep_original", "label": "保留原名"},
    {"value": "soft_correct", "label": "模糊修正"},
]

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.IGNORECASE)
_SCENE_SPLIT_RE = re.compile(r"(?=^【场景[^\n]+】)", re.MULTILINE)
_SCENE_HEADING_RE = re.compile(r"^【(?P<label>场景[^：:]+)[：:]\s*(?P<heading>.+?)】$")
_BEAT_LINE_RE = re.compile(r"^(?P<label>[^：:]+)[：:]\s*(?P<text>.*)$")
_QUALIFIED_LABEL_RE = re.compile(r"^(?P<label>[^（(]+?)(?:[（(](?P<qualifier>.+?)[）)])?$")


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _to_chinese_number(number: int) -> str:
    digits = "零一二三四五六七八九"
    units = ["", "十", "百", "千"]
    if number <= 0:
        return "零"
    if number < 10:
        return digits[number]

    parts: List[str] = []
    value = number
    unit_index = 0
    while value > 0:
        value, current = divmod(value, 10)
        if current:
            parts.append(f"{digits[current]}{units[unit_index]}")
        elif parts and not parts[-1].startswith("零"):
            parts.append("零")
        unit_index += 1

    text = "".join(reversed(parts)).replace("零零", "零").rstrip("零")
    if text.startswith("一十"):
        text = text[1:]
    return text or "零"


class NovelToScriptService:
    """Normalize source text and convert LLM output into a stable script payload."""

    def __init__(self, import_service: Optional[NovelImportService] = None):
        self.import_service = import_service or NovelImportService()

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "module": "novel_to_script",
            "project_state_key": NOVEL_TO_SCRIPT_STATE_KEY,
            "defaults": deepcopy(DEFAULT_CONVERT_CONFIG),
            "options": {
                "script_styles": deepcopy(SCRIPT_STYLE_OPTIONS),
                "convert_modes": deepcopy(CONVERT_MODE_OPTIONS),
                "scene_densities": deepcopy(DENSITY_OPTIONS),
                "dialogue_ratios": deepcopy(DIALOGUE_RATIO_OPTIONS),
                "human_name_strategies": deepcopy(HUMAN_NAME_OPTIONS),
            },
            "strategy": {
                "single_pass_max_words": SINGLE_PASS_MAX_WORDS,
                "chapterwise_max_words": CHAPTERWISE_MAX_WORDS,
                "batch_target_words": BATCH_TARGET_WORDS,
                "chapter_split_words": CHAPTER_SPLIT_WORDS,
            },
            "accepted_import_formats": ["txt", "md", "docx"],
        }

    def normalize_source(
        self,
        *,
        source_text: str = "",
        source_chapters: Optional[Iterable[Mapping[str, Any]]] = None,
        source_type: str = "paste",
        source_filename: str = "",
    ) -> Dict[str, Any]:
        normalized_type = "file" if str(source_type or "").strip().lower() == "file" else "paste"
        normalized_text = _normalize_text(source_text)
        normalized_chapters = self._normalize_source_chapters(source_chapters or [])

        if not normalized_chapters and normalized_text:
            parsed = self.import_service.parse_novel_file(
                filename=(source_filename or "inline.txt"),
                raw_bytes=normalized_text.encode("utf-8"),
            )
            normalized_chapters = self._normalize_source_chapters(parsed.get("chapters") or [])
            normalized_text = _normalize_text(parsed.get("content") or normalized_text)

        if not normalized_text and normalized_chapters:
            normalized_text = "\n\n".join(
                chapter["content"] for chapter in normalized_chapters if chapter["content"]
            ).strip()

        if not normalized_text:
            raise ValueError("请输入小说正文或先导入小说文件。")

        if not normalized_chapters:
            normalized_chapters = [
                {
                    "chapter_number": 1,
                    "title": "正文",
                    "content": normalized_text,
                    "word_count": len(re.sub(r"\s+", "", normalized_text)),
                }
            ]

        return {
            "source_type": normalized_type,
            "source_filename": (source_filename or "").strip(),
            "source_text": normalized_text,
            "source_chapters": normalized_chapters,
            "chapter_count": len(normalized_chapters),
            "word_count": len(re.sub(r"\s+", "", normalized_text)),
        }

    def normalize_config(self, raw_config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        config = deepcopy(DEFAULT_CONVERT_CONFIG)
        if raw_config:
            config.update(
                {
                    "script_style": str(raw_config.get("script_style") or config["script_style"]).strip(),
                    "convert_mode": str(raw_config.get("convert_mode") or config["convert_mode"]).strip(),
                    "scene_density": str(raw_config.get("scene_density") or config["scene_density"]).strip(),
                    "dialogue_ratio": str(raw_config.get("dialogue_ratio") or config["dialogue_ratio"]).strip(),
                    "keep_voice_style": bool(raw_config.get("keep_voice_style", config["keep_voice_style"])),
                    "human_name_strategy": str(
                        raw_config.get("human_name_strategy") or config["human_name_strategy"]
                    ).strip(),
                }
            )

        if config["script_style"] not in {item["value"] for item in SCRIPT_STYLE_OPTIONS}:
            config["script_style"] = DEFAULT_SCRIPT_STYLE
        if config["convert_mode"] not in {"auto", "full_text", "chapterwise", "batchwise"}:
            config["convert_mode"] = DEFAULT_CONVERT_CONFIG["convert_mode"]
        if config["scene_density"] not in {"low", "medium", "high"}:
            config["scene_density"] = DEFAULT_CONVERT_CONFIG["scene_density"]
        if config["dialogue_ratio"] not in {"low", "medium", "high"}:
            config["dialogue_ratio"] = DEFAULT_CONVERT_CONFIG["dialogue_ratio"]
        if config["human_name_strategy"] not in {"keep_original", "soft_correct"}:
            config["human_name_strategy"] = DEFAULT_CONVERT_CONFIG["human_name_strategy"]
        return config

    def analyze_source(self, source_payload: Mapping[str, Any]) -> Dict[str, Any]:
        chapters = self._normalize_source_chapters(source_payload.get("source_chapters") or [])
        word_count = _safe_int(source_payload.get("word_count"), 0)
        chapter_count = len(chapters)
        has_named_chapters = chapter_count > 1

        if word_count <= SINGLE_PASS_MAX_WORDS:
            recommended_mode = "full_text"
            reason = f"全文约 {word_count} 字，适合单次转换。"
        elif has_named_chapters and word_count <= CHAPTERWISE_MAX_WORDS:
            recommended_mode = "chapterwise"
            reason = (
                f"全文约 {word_count} 字，已识别 {chapter_count} 章，"
                "按章节转换更稳，失败时也更方便重试。"
            )
        else:
            recommended_mode = "batchwise"
            reason = (
                f"全文约 {word_count} 字，已超过单次稳定范围，"
                "建议自动分批转换并逐批保存结果。"
            )

        return {
            "word_count": word_count,
            "chapter_count": chapter_count,
            "has_named_chapters": has_named_chapters,
            "recommended_mode": recommended_mode,
            "recommended_mode_label": self._label_for_option(CONVERT_MODE_OPTIONS, recommended_mode),
            "reason": reason,
        }

    def plan_conversion(
        self,
        *,
        source_payload: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Dict[str, Any]:
        normalized_config = self.normalize_config(config)
        analysis = self.analyze_source(source_payload)
        requested_mode = normalized_config["convert_mode"]
        resolved_mode = requested_mode if requested_mode != "auto" else analysis["recommended_mode"]
        warnings: List[str] = []

        if requested_mode == "full_text" and analysis["word_count"] > SINGLE_PASS_MAX_WORDS:
            warnings.append(
                f"输入约 {analysis['word_count']} 字，超出单次稳定范围，已自动切换为批量转换。"
            )
            resolved_mode = "batchwise"

        batches = self._build_batches_for_mode(source_payload, resolved_mode)
        if resolved_mode == "chapterwise" and len(batches) > BATCH_CHAPTER_LIMIT and analysis["word_count"] > CHAPTERWISE_MAX_WORDS:
            warnings.append("章节数量较多，实际会逐章顺序转换并自动合并为一份完整剧本。")
        if resolved_mode == "batchwise" and len(batches) == 1 and analysis["word_count"] <= SINGLE_PASS_MAX_WORDS:
            resolved_mode = "full_text"

        return {
            "requested_mode": requested_mode,
            "requested_mode_label": self._label_for_option(CONVERT_MODE_OPTIONS, requested_mode),
            "resolved_mode": resolved_mode,
            "resolved_mode_label": self._label_for_option(CONVERT_MODE_OPTIONS, resolved_mode),
            "analysis": analysis,
            "warnings": warnings,
            "batch_count": len(batches),
            "batches": batches,
        }

    def build_messages(
        self,
        *,
        source_payload: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Dict[str, str]:
        normalized_config = self.normalize_config(config)
        chapters = self._normalize_source_chapters(source_payload.get("source_chapters") or [])
        source_text = _normalize_text(source_payload.get("source_text"))
        batch_number = _safe_int(source_payload.get("batch_number"), 0)
        batch_count = _safe_int(source_payload.get("batch_count"), 0)
        chapter_blocks = []
        for chapter in chapters:
            chapter_blocks.append(
                f"### 第{chapter['chapter_number']}章：{chapter['title']}\n{chapter['content']}"
            )
        source_block = "\n\n".join(chapter_blocks).strip() or source_text

        system_prompt = (
            "你是专业的中文小说改编编辑，负责把小说正文重写为“场景块台本”。"
            "请严格遵守指定格式，输出必须是 JSON 对象，不要附加解释。"
        )

        user_prompt = f"""
请把下面的小说内容转换为“可读、可演、可继续修改”的网文场景台本。

转换要求：
1. 目标风格：{self._label_for_option(SCRIPT_STYLE_OPTIONS, normalized_config['script_style'])}（{normalized_config['script_style']}）
2. 转换方式：{self._label_for_option(CONVERT_MODE_OPTIONS, normalized_config['convert_mode'])}
3. 场景密度：{self._label_for_option(DENSITY_OPTIONS, normalized_config['scene_density'])}
4. 对白占比：{self._label_for_option(DIALOGUE_RATIO_OPTIONS, normalized_config['dialogue_ratio'])}
5. 人名策略：{self._label_for_option(HUMAN_NAME_OPTIONS, normalized_config['human_name_strategy'])}
6. {"尽量保留原文人物语气和网文化表达。" if normalized_config['keep_voice_style'] else "可以在保留剧情的前提下适度调整表达。"}
7. 如果这是长篇分批转换，请只处理当前这一批的内容，不要杜撰未提供章节的剧情。

输出规范：
- 只输出一个 JSON 对象，顶层字段固定为 scenes、formatted_text、full_text。
- scenes 必须是数组。每个 scene 包含 scene_number、scene_label、heading、characters_text、environment_text、beats。
- beats 中每一项包含 type、label、text，可选 speaker、qualifier。
- formatted_text 必须严格接近以下连续文本模板，不要输出 Markdown 标题、列表符号或解释文字：
【场景一：地点 - 时间/天气】
人物：角色A（简介）、角色B（简介）
环境：场景环境描述
动作/旁白：开场动作与状态描述
角色名（内心独白，语气XXX）：内容
角色名（动作）：内容
闪回片段（快速切换，语气XXX）：内容
动作/音效：内容
- 场景之间空一行。
- 场景编号使用中文数字。
- 若原文没有明确章节，也要根据场景变化合理拆分。
- 不要输出镜头号、景别、分镜术语。

源文本统计：
- 总字数：{source_payload.get('word_count', 0)}
- 章节数：{source_payload.get('chapter_count', 0)}
{f"- 当前批次：第 {batch_number} / {batch_count} 批" if batch_number and batch_count else ""}

小说内容如下：
{source_block}
""".strip()

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

    def parse_conversion_result(self, raw_output: str) -> Dict[str, Any]:
        cleaned = _normalize_text(raw_output)
        if not cleaned:
            raise ValueError("转换结果为空，请重试。")

        payload = self._extract_json_payload(cleaned)
        if isinstance(payload, dict):
            return self._normalize_result_payload(payload, raw_output=cleaned)
        return self._normalize_result_payload({"formatted_text": cleaned, "full_text": cleaned}, raw_output=cleaned)

    def render_formatted_text(self, scenes: Iterable[Mapping[str, Any]]) -> str:
        blocks: List[str] = []
        for index, scene in enumerate(scenes, start=1):
            normalized = self._normalize_scene(scene, index)
            lines = [
                f"【{normalized['scene_label']}：{normalized['heading']}】",
                f"人物：{normalized['characters_text']}",
                f"环境：{normalized['environment_text']}",
            ]
            beats = normalized.get("beats") or []
            if beats:
                for beat in beats:
                    lines.append(self._render_beat_line(beat))
            else:
                lines.append("动作/旁白：待补充。")
            blocks.append("\n".join(lines).strip())
        return "\n\n".join(block for block in blocks if block).strip()

    def parse_formatted_text(self, formatted_text: str) -> List[Dict[str, Any]]:
        cleaned = _normalize_text(formatted_text)
        if not cleaned:
            return []

        blocks = [
            block.strip()
            for block in _SCENE_SPLIT_RE.split(cleaned)
            if block and block.strip()
        ]
        scenes: List[Dict[str, Any]] = []
        for index, block in enumerate(blocks, start=1):
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            heading_match = _SCENE_HEADING_RE.match(lines[0])
            if heading_match:
                scene_label = heading_match.group("label").strip()
                heading = heading_match.group("heading").strip()
                body_lines = lines[1:]
            else:
                scene_label = f"场景{_to_chinese_number(index)}"
                heading = lines[0].strip("【】")
                body_lines = lines[1:]

            characters_text = ""
            environment_text = ""
            beats: List[Dict[str, Any]] = []

            for line in body_lines:
                match = _BEAT_LINE_RE.match(line)
                if not match:
                    beats.append(
                        {
                            "type": "action_narration",
                            "label": "动作/旁白",
                            "text": line,
                        }
                    )
                    continue

                label = match.group("label").strip()
                text = match.group("text").strip()
                if label == "人物":
                    characters_text = text
                    continue
                if label == "环境":
                    environment_text = text
                    continue

                qualified = _QUALIFIED_LABEL_RE.match(label)
                base_label = qualified.group("label").strip() if qualified else label
                qualifier = qualified.group("qualifier").strip() if qualified and qualified.group("qualifier") else ""

                if base_label in {"动作/旁白", "动作/音效", "闪回片段"}:
                    beats.append(
                        {
                            "type": self._beat_type_from_label(base_label),
                            "label": base_label,
                            "text": text,
                            **({"qualifier": qualifier} if qualifier else {}),
                        }
                    )
                    continue

                beat = {
                    "type": "character_line",
                    "speaker": base_label,
                    "label": base_label,
                    "text": text,
                }
                if qualifier:
                    beat["qualifier"] = qualifier
                beats.append(beat)

            scenes.append(
                self._normalize_scene(
                    {
                        "scene_number": index,
                        "scene_label": scene_label,
                        "heading": heading,
                        "characters_text": characters_text,
                        "environment_text": environment_text,
                        "beats": beats,
                    },
                    index,
                )
            )

        return scenes

    def build_export_text(self, title: str, result: Mapping[str, Any]) -> str:
        content = _normalize_text(result.get("formatted_text") or result.get("full_text"))
        if not content:
            scenes = result.get("scenes") or []
            content = self.render_formatted_text(scenes)
        if not content:
            raise ValueError("当前没有可导出的转换结果。")

        normalized_title = _normalize_text(title) or "小说转剧本"
        return f"{normalized_title}\n\n{content}\n"

    def merge_batch_results(
        self,
        batch_results: Iterable[Mapping[str, Any]],
        *,
        plan: Mapping[str, Any],
    ) -> Dict[str, Any]:
        normalized_batches = self._normalize_batch_results(batch_results)
        merged_scenes: List[Dict[str, Any]] = []
        batch_summaries: List[Dict[str, Any]] = []
        scene_number = 1

        for index, batch in enumerate(normalized_batches, start=1):
            result = batch["result"]
            batch_summary = {
                "batch_number": index,
                "title": _normalize_text(batch.get("title")) or f"第 {index} 批",
                "word_count": _safe_int(batch.get("word_count"), 0),
                "scene_count": _safe_int(result.get("scene_count"), 0),
                "chapter_range": batch.get("chapter_range") or [],
            }
            batch_summaries.append(batch_summary)

            for scene in result.get("scenes") or []:
                normalized_scene = self._normalize_scene(scene, scene_number)
                normalized_scene["scene_number"] = scene_number
                normalized_scene["scene_label"] = f"场景{_to_chinese_number(scene_number)}"
                merged_scenes.append(normalized_scene)
                scene_number += 1

        formatted_text = self.render_formatted_text(merged_scenes)
        return {
            "scenes": merged_scenes,
            "scene_count": len(merged_scenes),
            "scene_outline": self._build_scene_outline(merged_scenes),
            "character_index": self._build_character_index(merged_scenes),
            "formatted_text": formatted_text,
            "full_text": formatted_text,
            "batch_summaries": batch_summaries,
            "batches": normalized_batches,
            "batch_count": len(batch_summaries),
            "resolved_mode": plan.get("resolved_mode"),
        }

    def merge_with_existing_batch(
        self,
        *,
        plan: Mapping[str, Any],
        existing_batches: Iterable[Mapping[str, Any]],
        replacement_batch: Mapping[str, Any],
    ) -> Dict[str, Any]:
        plan_batches = {int(batch.get("batch_number", 0) or 0): batch for batch in plan.get("batches") or []}
        normalized_existing = self._normalize_batch_results(existing_batches)
        by_number = {
            int(batch.get("batch_number", 0) or 0): batch
            for batch in normalized_existing
            if int(batch.get("batch_number", 0) or 0) > 0
        }
        replacement_number = int(replacement_batch.get("batch_number", 0) or 0)
        if replacement_number <= 0:
            raise ValueError("batch_number 无效，无法重转指定批次。")
        by_number[replacement_number] = self._normalize_batch_result(replacement_batch)

        merged_batches: List[Dict[str, Any]] = []
        for batch in plan.get("batches") or []:
            batch_number = int(batch.get("batch_number", 0) or 0)
            if batch_number in by_number:
                merged_batches.append(by_number[batch_number])
            elif batch_number in plan_batches:
                placeholder = dict(plan_batches[batch_number])
                placeholder["result"] = {
                    "scenes": [],
                    "scene_count": 0,
                    "character_index": [],
                    "scene_outline": [],
                    "formatted_text": "",
                    "full_text": "",
                    "raw_output": "",
                }
                merged_batches.append(self._normalize_batch_result(placeholder))

        return self.merge_batch_results(merged_batches, plan=plan)

    def _normalize_source_chapters(self, chapters: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, Mapping):
                continue
            content = _normalize_text(chapter.get("content"))
            title = _normalize_text(chapter.get("title")) or f"第{index}章"
            if not content:
                continue
            normalized.append(
                {
                    "chapter_number": _safe_int(chapter.get("chapter_number"), index) or index,
                    "title": title,
                    "content": content,
                    "word_count": _safe_int(chapter.get("word_count"), len(re.sub(r"\s+", "", content))),
                }
            )
        return normalized

    def _build_batches_for_mode(
        self,
        source_payload: Mapping[str, Any],
        mode: str,
    ) -> List[Dict[str, Any]]:
        chapters = self._normalize_source_chapters(source_payload.get("source_chapters") or [])
        source_text = _normalize_text(source_payload.get("source_text"))

        if mode == "full_text":
            return [self._build_batch_payload(chapters or [{
                "chapter_number": 1,
                "title": "正文",
                "content": source_text,
                "word_count": _safe_int(source_payload.get("word_count"), len(re.sub(r"\s+", "", source_text))),
            }], 1, 1)]

        if mode == "chapterwise":
            batches: List[Dict[str, Any]] = []
            for chapter in chapters:
                split_parts = self._split_large_chapter(chapter, CHAPTER_SPLIT_WORDS)
                batches.extend(split_parts)
            return self._attach_batch_sequence(batches)

        if chapters and len(chapters) > 1:
            grouped: List[List[Dict[str, Any]]] = []
            current: List[Dict[str, Any]] = []
            current_words = 0
            for chapter in chapters:
                chapter_parts = self._split_large_chapter(chapter, CHAPTER_SPLIT_WORDS)
                for part in chapter_parts:
                    part_words = _safe_int(part.get("word_count"), 0)
                    if current and (
                        current_words + part_words > BATCH_TARGET_WORDS
                        or len(current) >= BATCH_CHAPTER_LIMIT
                    ):
                        grouped.append(current)
                        current = []
                        current_words = 0
                    current.append(part)
                    current_words += part_words
            if current:
                grouped.append(current)
            return self._attach_batch_sequence([
                self._build_batch_payload(group, index + 1, len(grouped))
                for index, group in enumerate(grouped)
            ])

        inline_chunks = self._split_text_into_chunks(source_text, INLINE_SPLIT_WORDS)
        raw_batches = []
        for index, chunk in enumerate(inline_chunks, start=1):
            raw_batches.append(
                self._build_batch_payload(
                    [
                        {
                            "chapter_number": index,
                            "title": f"正文片段 {index}",
                            "content": chunk,
                            "word_count": len(re.sub(r"\s+", "", chunk)),
                        }
                    ],
                    index,
                    len(inline_chunks),
                )
            )
        return self._attach_batch_sequence(raw_batches)

    def get_batch_from_plan(self, plan: Mapping[str, Any], batch_number: int) -> Dict[str, Any]:
        for batch in plan.get("batches") or []:
            if int(batch.get("batch_number", 0) or 0) == int(batch_number):
                return dict(batch)
        raise ValueError(f"未找到第 {batch_number} 批转换计划。")

    def _split_large_chapter(self, chapter: Mapping[str, Any], target_words: int) -> List[Dict[str, Any]]:
        content = _normalize_text(chapter.get("content"))
        word_count = _safe_int(chapter.get("word_count"), len(re.sub(r"\s+", "", content)))
        if word_count <= target_words:
            return [dict(chapter)]

        chunks = self._split_text_into_chunks(content, target_words)
        parts: List[Dict[str, Any]] = []
        for index, chunk in enumerate(chunks, start=1):
            parts.append(
                {
                    "chapter_number": _safe_int(chapter.get("chapter_number"), 1),
                    "title": f"{_normalize_text(chapter.get('title')) or '正文'}（第{index}段）",
                    "content": chunk,
                    "word_count": len(re.sub(r"\s+", "", chunk)),
                    "source_chapter_number": _safe_int(chapter.get("chapter_number"), 1),
                }
            )
        return parts

    def _split_text_into_chunks(self, text: str, target_words: int) -> List[str]:
        cleaned = _normalize_text(text)
        if not cleaned:
            return []
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
        if not paragraphs:
            paragraphs = [part.strip() for part in cleaned.split("\n") if part.strip()]
        if not paragraphs:
            return [cleaned]

        chunks: List[str] = []
        current_parts: List[str] = []
        current_words = 0

        for paragraph in paragraphs:
            words = len(re.sub(r"\s+", "", paragraph))
            if current_parts and current_words + words > target_words:
                chunks.append("\n\n".join(current_parts).strip())
                current_parts = []
                current_words = 0
            current_parts.append(paragraph)
            current_words += words

        if current_parts:
            chunks.append("\n\n".join(current_parts).strip())
        return chunks or [cleaned]

    def _build_batch_payload(
        self,
        chapters: Iterable[Mapping[str, Any]],
        batch_number: int,
        batch_count: int,
    ) -> Dict[str, Any]:
        normalized_chapters = self._normalize_source_chapters(chapters)
        source_text = "\n\n".join(chapter["content"] for chapter in normalized_chapters if chapter["content"]).strip()
        chapter_numbers = [chapter["chapter_number"] for chapter in normalized_chapters]
        if chapter_numbers:
            if len(set(chapter_numbers)) == 1:
                title = normalized_chapters[0]["title"]
            else:
                title = f"第{chapter_numbers[0]}章 - 第{chapter_numbers[-1]}章"
        else:
            title = f"第 {batch_number} 批"

        return {
            "batch_number": batch_number,
            "batch_count": batch_count,
            "title": title,
            "source_text": source_text,
            "source_chapters": normalized_chapters,
            "chapter_count": len(normalized_chapters),
            "word_count": len(re.sub(r"\s+", "", source_text)),
            "chapter_range": chapter_numbers,
        }

    def _attach_batch_sequence(self, batches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        total = len(batches)
        normalized: List[Dict[str, Any]] = []
        for index, batch in enumerate(batches, start=1):
            next_batch = dict(batch)
            next_batch["batch_number"] = index
            next_batch["batch_count"] = total
            normalized.append(next_batch)
        return normalized

    def _normalize_batch_result(self, batch: Mapping[str, Any]) -> Dict[str, Any]:
        result = batch.get("result") if isinstance(batch, Mapping) else None
        normalized_result = (
            self._normalize_result_payload(result, raw_output=_normalize_text(result.get("raw_output") if isinstance(result, Mapping) else ""))
            if isinstance(result, Mapping)
            else {
                "scenes": [],
                "scene_count": 0,
                "character_index": [],
                "scene_outline": [],
                "formatted_text": "",
                "full_text": "",
                "raw_output": "",
            }
        )
        return {
            "batch_number": _safe_int(batch.get("batch_number"), 0),
            "batch_count": _safe_int(batch.get("batch_count"), 0),
            "title": _normalize_text(batch.get("title")) or "未命名批次",
            "source_text": _normalize_text(batch.get("source_text")),
            "source_chapters": self._normalize_source_chapters(batch.get("source_chapters") or []),
            "chapter_count": _safe_int(batch.get("chapter_count"), 0),
            "word_count": _safe_int(batch.get("word_count"), 0),
            "chapter_range": list(batch.get("chapter_range") or []),
            "result": normalized_result,
        }

    def _normalize_batch_results(self, batch_results: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        normalized = [
            self._normalize_batch_result(batch)
            for batch in batch_results
            if isinstance(batch, Mapping)
        ]
        normalized.sort(key=lambda item: int(item.get("batch_number", 0) or 0))
        return normalized

    def _extract_json_payload(self, raw_output: str) -> Optional[Dict[str, Any]]:
        candidates: List[str] = []
        block_match = _JSON_BLOCK_RE.search(raw_output)
        if block_match:
            candidates.append(block_match.group(1).strip())

        first_brace = raw_output.find("{")
        last_brace = raw_output.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidates.append(raw_output[first_brace:last_brace + 1].strip())

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _normalize_result_payload(self, payload: Mapping[str, Any], *, raw_output: str) -> Dict[str, Any]:
        scenes_raw = payload.get("scenes") or []
        scenes = [
            self._normalize_scene(scene, index)
            for index, scene in enumerate(scenes_raw, start=1)
            if isinstance(scene, Mapping)
        ]

        formatted_text = _normalize_text(payload.get("formatted_text"))
        full_text = _normalize_text(payload.get("full_text"))

        if not scenes and formatted_text:
            scenes = self.parse_formatted_text(formatted_text)
        if not scenes and full_text:
            scenes = self.parse_formatted_text(full_text)
        if scenes and not formatted_text:
            formatted_text = self.render_formatted_text(scenes)
        if not full_text:
            full_text = formatted_text or raw_output
        if not formatted_text:
            formatted_text = full_text

        character_index = self._build_character_index(scenes)
        scene_outline = self._build_scene_outline(scenes)

        return {
            "scenes": scenes,
            "scene_count": len(scenes),
            "character_index": character_index,
            "scene_outline": scene_outline,
            "formatted_text": formatted_text,
            "full_text": full_text,
            "raw_output": raw_output,
        }

    def _normalize_scene(self, scene: Mapping[str, Any], index: int) -> Dict[str, Any]:
        heading = _normalize_text(scene.get("heading")) or "未命名场景"
        scene_number = _safe_int(scene.get("scene_number"), index) or index
        scene_label = _normalize_text(scene.get("scene_label")) or f"场景{_to_chinese_number(scene_number)}"
        if not scene_label.startswith("场景"):
            scene_label = f"场景{scene_label}"

        beats_raw = scene.get("beats") or []
        beats: List[Dict[str, Any]] = []
        for beat in beats_raw:
            if not isinstance(beat, Mapping):
                continue
            beats.append(self._normalize_beat(beat))

        return {
            "scene_number": scene_number,
            "scene_label": scene_label,
            "heading": heading,
            "characters_text": _normalize_text(scene.get("characters_text")) or "待补充",
            "environment_text": _normalize_text(scene.get("environment_text")) or "待补充",
            "beats": beats,
        }

    def _normalize_beat(self, beat: Mapping[str, Any]) -> Dict[str, Any]:
        beat_type = _normalize_text(beat.get("type")) or "action_narration"
        label = _normalize_text(beat.get("label"))
        speaker = _normalize_text(beat.get("speaker"))
        qualifier = _normalize_text(beat.get("qualifier"))
        text = _normalize_text(beat.get("text"))

        if beat_type == "character_line":
            label = label or speaker or "角色"
        elif beat_type in {"fx_line", "flashback_line"}:
            label = label or ("动作/音效" if beat_type == "fx_line" else "闪回片段")
        else:
            label = label or "动作/旁白"

        normalized = {
            "type": beat_type,
            "label": label,
            "text": text or "待补充。",
        }
        if speaker:
            normalized["speaker"] = speaker
        if qualifier:
            normalized["qualifier"] = qualifier
        return normalized

    def _render_beat_line(self, beat: Mapping[str, Any]) -> str:
        beat_type = _normalize_text(beat.get("type"))
        label = _normalize_text(beat.get("label"))
        text = _normalize_text(beat.get("text")) or "待补充。"
        qualifier = _normalize_text(beat.get("qualifier"))
        speaker = _normalize_text(beat.get("speaker"))

        if beat_type == "character_line":
            prefix = speaker or label or "角色"
            if qualifier:
                prefix = f"{prefix}（{qualifier}）"
            return f"{prefix}：{text}"

        prefix = label or "动作/旁白"
        if qualifier:
            prefix = f"{prefix}（{qualifier}）"
        return f"{prefix}：{text}"

    def _label_for_option(self, options: Iterable[Mapping[str, Any]], value: str) -> str:
        for item in options:
            if item.get("value") == value:
                return str(item.get("label") or value)
        return value

    def _beat_type_from_label(self, label: str) -> str:
        if label == "动作/音效":
            return "fx_line"
        if label == "闪回片段":
            return "flashback_line"
        return "action_narration"

    def _build_character_index(self, scenes: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        index: Dict[str, Dict[str, Any]] = {}
        for scene in scenes:
            scene_number = _safe_int(scene.get("scene_number"), 0)
            raw_characters = _normalize_text(scene.get("characters_text"))
            for part in re.split(r"[，,、；;]\s*", raw_characters):
                token = part.strip()
                if not token or token == "待补充":
                    continue
                name = token
                description = ""
                if "（" in token and "）" in token:
                    left, _, right = token.partition("（")
                    name = left.strip() or token
                    description = right.rsplit("）", 1)[0].strip()
                card = index.setdefault(
                    name,
                    {
                        "name": name,
                        "description": description,
                        "scene_numbers": [],
                        "scene_count": 0,
                    },
                )
                if description and not card["description"]:
                    card["description"] = description
                if scene_number and scene_number not in card["scene_numbers"]:
                    card["scene_numbers"].append(scene_number)

        result = []
        for item in index.values():
            item["scene_numbers"].sort()
            item["scene_count"] = len(item["scene_numbers"])
            result.append(item)
        result.sort(key=lambda item: (-item["scene_count"], item["name"]))
        return result

    def _build_scene_outline(self, scenes: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        outline: List[Dict[str, Any]] = []
        for scene in scenes:
            outline.append(
                {
                    "scene_number": _safe_int(scene.get("scene_number"), 0),
                    "scene_label": _normalize_text(scene.get("scene_label")),
                    "heading": _normalize_text(scene.get("heading")),
                    "beat_count": len(scene.get("beats") or []),
                    "characters_text": _normalize_text(scene.get("characters_text")),
                }
            )
        return outline
