"""
短篇创作服务。

将原先 Skill 内的短篇工作流迁移为项目内置服务，供固定面板和 API 直接调用。
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, AsyncGenerator


class ShortStoryStage(str, Enum):
    """短篇创作工作流状态。"""

    AWAITING_KEYWORDS = "awaiting_keywords"
    ANALYZING_SOURCE_INPUT = "analyzing_source_input"
    GENERATING_FUSION_OPTIONS = "generating_fusion_options"
    AWAITING_FUSION_SELECTION = "awaiting_fusion_selection"
    GENERATING_SYNOPSIS = "generating_synopsis"
    AWAITING_SYNOPSIS_SELECTION = "awaiting_synopsis_selection"
    GENERATING_OUTLINE = "generating_outline"
    AWAITING_OUTLINE_CONFIRM = "awaiting_outline_confirm"
    WRITING_CONTENT = "writing_content"
    QUALITY_CHECKING = "quality_checking"
    COHERENCE_REVIEWING = "coherence_reviewing"
    GENERATING_TITLES = "generating_titles"
    AWAITING_TITLE_SELECTION = "awaiting_title_selection"
    ASSEMBLING_OUTPUT = "assembling_output"
    COMPLETED = "completed"


@dataclass
class StepPolicy:
    """步骤配置。"""

    id: str
    name: str
    requires_user_input: bool
    max_retries: int
    auto_fix: bool = False


def _step_policies() -> List[StepPolicy]:
    return [
        StepPolicy("generate_fusion_options", "创意方案生成", True, 2),
        StepPolicy("generate_synopsis", "导语生成", True, 2),
        StepPolicy("generate_outline", "大纲生成", True, 2),
        StepPolicy("write_content", "正文创作", False, 2),
        StepPolicy("quality_check", "质量检查", False, 3, auto_fix=True),
        StepPolicy("coherence_review", "通篇复审", False, 2, auto_fix=True),
        StepPolicy("generate_titles", "书名生成", True, 2),
        StepPolicy("assemble_output", "组装输出", False, 1),
    ]


SHORT_STORY_MAIN_CATEGORIES = [
    "婚姻家庭",
    "女生生活",
    "男生生活",
    "现言甜宠",
    "虐心婚恋",
    "青春虐恋",
    "男生情感",
    "脑洞",
    "社会伦理",
    "女性成长",
    "悬疑惊悚",
    "古代言情",
    "玄幻仙侠",
    "宫斗宅斗",
    "男频衍生",
    "女频衍生",
    "年代",
    "纯爱",
    "其他",
]


def _normalize_main_category(value: Any, fallback: str = "其他") -> str:
    """Normalize a built-in or user-defined short-story main category."""

    fallback_text = re.sub(r"\s+", " ", str(fallback or "其他")).strip() or "其他"
    category = re.sub(r"\s+", " ", str(value or "").strip())
    if not category:
        category = fallback_text
    return category[:32] or "其他"


SHORT_STORY_TAG_GROUPS = {
    "plot_tags": [
        "追妻火葬场",
        "追夫火葬场",
        "真假千金",
        "先婚后爱",
        "打脸逆袭",
        "破镜重圆",
        "系统",
        "金手指",
        "大女主",
        "女性互助",
        "穿越",
        "重生",
        "暗恋",
        "婚恋",
        "权谋",
        "架空",
        "养崽文",
        "团宠",
        "无限流",
        "末日求生",
        "游戏动漫",
        "规则怪谈",
        "民间奇闻",
        "影视",
        "科幻",
        "推理",
        "直播",
    ],
    "role_tags": [
        "白月光",
        "霸总",
        "婆媳",
        "青梅竹马",
        "姐弟恋",
        "凤凰男",
        "校花校草",
        "女配",
        "医生",
        "替身",
        "病娇",
        "赘婿",
        "校霸",
        "影帝影后",
        "萌宝",
        "糙汉",
        "万人迷",
    ],
    "emotion_tags": [
        "先虐后甜",
        "甜宠",
        "虐文",
        "爽文",
        "救赎",
        "惊悚",
        "励志",
        "沙雕搞笑",
    ],
    "background_tags": [
        "家庭",
        "职场",
        "校园",
        "娱乐圈",
        "现代",
        "古代",
        "民国",
        "豪门世家",
    ],
}


INPUT_ANALYSIS_PROMPT_TEMPLATE = """你是一位短篇小说创作输入分析师。

【用户统一输入】
{source_input}

【用户指定主分类】
{category}

请识别这段输入里包含哪些创作素材类型，并输出一个 JSON 对象。允许识别的素材类型：
- keywords（词条/关键词）
- inspiration（灵感/脑洞/一句话想法）
- example_text（例文/仿写参考）
- genre_hint（题材/风格/主分类倾向）
- constraints（额外要求/限制）

输出要求：
1. 必须返回合法 JSON
2. confidence 取 0~1 的小数
3. detected_material_types 返回数组
4. keywords 返回提炼后的关键词数组
5. summary 用 80~150 字概括这段输入的创作意图
6. borrowed_highlights 提炼例文中值得借鉴的爽点/节奏/结构关键词
7. warnings 仅在输入明显含糊时给出提醒，没有则返回空数组

JSON 格式：
{{
  "summary": "...",
  "confidence": 0.86,
  "detected_material_types": ["keywords", "inspiration"],
  "keywords": ["词条1", "词条2"],
  "genre_hint": "{category}",
  "borrowed_highlights": ["爽点1", "节奏2"],
  "constraints": ["限制1"],
  "warnings": ["提醒1"]
}}"""

FUSION_OPTIONS_PROMPT_TEMPLATE = """你是一位专业的短篇小说策划编辑。

【用户统一输入】
{source_input}

【素材解析结果】
{analysis_summary}

【提炼关键词】
{keywords}

【主分类】
{category}

请基于以上信息，生成 3 个"不同风格"的创意方案，供用户先选最满意的一版。

要求：
1. 必须是同一批素材下的 3 条不同故事方向，不是同一方向换文风
2. 如果存在例文/仿写参考，默认强借鉴其爽点、节奏、结构骨架
3. 但人物、设定、关键事件必须明显换新，不能只是换名字
4. 每个方案都要突出“为什么读者会继续看”的钩子
5. 方案内容要短而狠，便于用户快速选择

输出格式：
【方案一】
标题：...
路数：...
钩子：...
借鉴骨架：...
内容换新：...
故事梗概：...

【方案二】
标题：...
路数：...
钩子：...
借鉴骨架：...
内容换新：...
故事梗概：...

【方案三】
标题：...
路数：...
钩子：...
借鉴骨架：...
内容换新：...
故事梗概：..."""

SYNOPSIS_PROMPT_TEMPLATE = """你是一位专业的短篇小说策划编辑。
用户提供了以下创作素材：
{keywords}

主分类：{category}

请根据这些素材，生成 5 条风格各异的故事导语。

要求：
1. 每条导语约 200 字（180~220字）
2. 5 条导语应覆盖不同的故事方向（如：悬疑、温情、反转、暗黑、治愈等）
3. 每条导语需包含：核心冲突、主要角色轮廓、整体基调
4. 核心素材必须在导语中得到体现
5. 导语应具有吸引力，让读者想要继续阅读
6. 故事气质要贴合“主分类”

请按以下格式输出：
【导语一】（XX 向）
{{内容}}

【导语二】（XX 向）
{{内容}}

【导语三】（XX 向）
{{内容}}

【导语四】（XX 向）
{{内容}}

【导语五】（XX 向）
{{内容}}"""

OUTLINE_PROMPT_TEMPLATE = """你是一位经验丰富的小说大纲策划师。

【创作词条】
{keywords}

【主分类】
{category}

【选定导语】
{selected_synopsis}

请根据以上信息，生成一份详细的短篇小说章节大纲。

要求：
1. 必须规划为 {planned_chapters} 章，不能少于也不能多于这个章节数
2. 每章正文控制在 {chapter_word_min}~{chapter_word_max} 字左右，平均目标约 {chapter_word_target} 字，允许上下浮动
3. 全文总字数目标不少于 {target_total_words} 字，合理上浮即可，不要明显偏离
4. 每章需包含：本章摘要（100-150字）、出场角色、核心事件、叙事功能、情绪节点
5. 在大纲开头列出：
   - 【角色表】：所有角色的姓名、身份、相互关系
   - 【时间线】：故事的时间跨度与关键时间节点
6. 确保起承转合完整，叙事节奏合理，章节分配要服务于总字数目标
7. 情节须与导语描述保持一致
8. **章节编号和标题**：
   - 使用阿拉伯数字编号（1. 2. 3.）
   - 标题直接使用核心事件的简短描述（3-6字）
   - 不要使用"第一章""第1章"等格式
   - 示例：`### 1. 重逢` `### 2. 误会加深` `### 3. 真相揭露`
9. **重点标注情绪节点**：根据主分类特点，在每章明确标注：
   - 爽点（如：打脸、逆袭、反转、揭秘）
   - 虐点（如：误会、背叛、失去、痛苦）
   - 转折点（如：身份揭露、真相大白、关系逆转）
   - 情绪高潮（如：冲突爆发、情感宣泄、决战时刻）
10. 章节篇幅不必机械平均，但整体规划必须能支撑上述总字数目标，不要把大纲写成明显字数不足的短骨架

输出格式：
【角色表】
| 角色 | 身份 | 关系 |
|------|------|------|

【时间线】
...

【章节大纲】
1. {{核心事件简述}}
- 摘要：...
- 出场角色：...
- 核心事件：...
- 叙事功能：...
- 情绪节点：【爽点/虐点/转折点】具体描述

2. {{核心事件简述}}
- 摘要：...
- 出场角色：...
- 核心事件：...
- 叙事功能：...
- 情绪节点：【爽点/虐点/转折点】具体描述

（以此类推）"""

CHAPTER_PROMPT_TEMPLATE = """你是一位优秀的短篇小说作家。

【创作背景】
- 词条：{keywords}
- 主分类：{category}
- 导语：{selected_synopsis}

【角色表】
{character_table}

【时间线】
{timeline}

【完整大纲】
{full_outline}

【已完成章节】
{previous_chapters_text}

【当前任务】
请撰写本章正文。
本章大纲要点：
{current_chapter_outline}

创作要求：
1. 字数控制在 {chapter_word_min}~{chapter_word_max} 字左右，目标约 {chapter_word_target} 字
2. **严格遵循本章大纲的情绪节点**（爽点/虐点/转折点），确保情绪张力到位
3. **以导语为核心**，所有情节推进必须围绕导语设定的核心冲突展开
4. 与前文保持风格统一、情节连贯
5. 角色姓名、关系、时间线不得出错
6. **减少环境描写**，重点放在对话、动作、心理活动和情绪冲突上
7. **强化情绪拉扯**：根据主分类特点，充分展现人物情绪起伏
   - 爽文：突出打脸、逆袭、碾压的快感
   - 虐文：深挖误会、痛苦、无奈的情绪
   - 甜宠：强化甜蜜互动、宠溺细节
8. 本章结尾自然衔接下一章（末章除外，末章需有收束感）
9. 排版采用短句成段，按动作、情绪或信息点自然换行，每段尽量 1~3 句，避免整段过长
10. **不要输出章节标题**，直接从正文第一句开始写

请直接输出本章正文，不要额外解释，不要输出章节标题。"""

QUALITY_CHECK_PROMPT_TEMPLATE = """你是一位严谨的文学编辑 / 质检审校员。

【角色表】
{character_table}

【时间线】
{timeline}

【章节大纲】
{full_outline}

【完整正文】
{all_chapters_text}

请快速检查以上短篇小说的核心问题：

## 检查清单（只检查关键问题）
### 1. 字数检查
- 标记不在 {chapter_word_min}~{chapter_word_max} 字范围内的章节

### 2. 角色一致性
- 角色名字是否有明显笔误或混用
- 角色关系是否有明显错误

### 3. 时间线一致性
- 是否有明显的时间顺序矛盾

### 4. 逻辑合理性
- 是否有明显的前后矛盾

输出格式（简洁）：
- 如无问题：✅ 质量检查通过，无需修改。
- 如有问题：
  第X章：问题类型 - 简要描述（不超过20字）
  第Y章：问题类型 - 简要描述（不超过20字）

注意：
1. 只列出最严重的问题，每章最多1个问题
2. 总共不超过15行
3. 不要重新生成完整正文
4. 系统会根据你的建议重新生成有问题的章节"""

BATCH_QUALITY_CHECK_PROMPT_TEMPLATE = """你是一位严谨的文学编辑 / 质检审校员。

【角色表】
{character_table}

【时间线】
{timeline}

【章节大纲】
{full_outline}

【当前批次正文（第{batch_start}章到第{batch_end}章）】
{batch_chapters_text}

请快速检查这批章节的核心问题：

## 检查清单（只检查关键问题）
### 1. 字数检查
- 标记不在 {chapter_word_min}~{chapter_word_max} 字范围内的章节

### 2. 角色一致性
- 角色名字是否有明显笔误或混用
- 角色关系是否有明显错误

### 3. 时间线一致性
- 是否有明显的时间顺序矛盾

### 4. 逻辑合理性
- 是否有明显的前后矛盾

输出格式（简洁）：
- 如无问题：✅ 本批次质量检查通过，无需修改。
- 如有问题：
  第X章：问题类型 - 简要描述（不超过20字）
  第Y章：问题类型 - 简要描述（不超过20字）

注意：
1. 只列出最严重的问题，每章最多1个问题
2. 总共不超过10行
3. 不要重新生成完整正文
4. 系统会根据你的建议重新生成有问题的章节"""

BATCH_COHERENCE_REVIEW_PROMPT_TEMPLATE = """你是一位资深的文学复审编辑。

【用户原始词条】
{keywords}

【主分类】
{category}

【选定导语】
{selected_synopsis}

【当前批次正文（第{batch_start}章到第{batch_end}章）】
{batch_chapters_text}

请快速进行通篇复审，重点审核：
1. 词条覆盖度：关键词条是否在正文中体现
2. 导语一致性：核心冲突、角色设定是否与导语一致
3. 主题统一性：全文主题和基调是否一致
4. 章节衔接：本批次章节之间的衔接是否自然

输出格式（简洁）：
- 如无问题：✅ 本批次复审通过。
- 如有问题：
  第X章：问题类型 - 简要描述（不超过20字）
  第Y章：问题类型 - 简要描述（不超过20字）

注意：
1. 只列出最严重的逻辑问题，每章最多1个问题
2. 总共不超过8行
3. 不要重新生成完整正文
4. 系统会根据你的建议进行后续处理"""

COHERENCE_REVIEW_PROMPT_TEMPLATE = """你是一位资深的文学复审编辑。

【用户原始词条】
{keywords}

【主分类】
{category}

【选定导语】
{selected_synopsis}

【当前正文（质检后版本）】
{revised_full_text}

请快速进行通篇复审，重点审核：
1. 词条覆盖度：关键词条是否在正文中体现
2. 导语一致性：核心冲突、角色设定是否与导语一致
3. 主题统一性：全文主题和基调是否一致
4. 首尾呼应：结局是否与开篇呼应

输出格式（简洁）：
- 如无问题：✅ 复审通过，正文定稿。
- 如有问题：
  第X章：问题类型 - 简要描述（不超过20字）
  第Y章：问题类型 - 简要描述（不超过20字）

注意：
1. 只列出最严重的逻辑问题，每章最多1个问题
2. 总共不超过10行
3. 不要重新生成完整正文
4. 系统会根据你的建议进行后续处理"""

TITLE_PROMPT_TEMPLATE = """你是一位擅长取爆款书名的短篇小说编辑。

【词条】
{keywords}

【主分类】
{category}

【导语】
{selected_synopsis}

【正文概要】
{body_excerpt}

请为这篇短篇小说生成 5 个候选书名。

要求：
1. 书名长度：8~15 字以内，要接地气、有噱头、能吸睛
2. 风格参考：
   - 冲突型：直接点出核心矛盾，如"恶婆婆竟把我攒的工资买房！"
   - 反转型：制造悬念和反差，如"离婚后，前夫跪求我回家"
   - 情绪型：直击读者情感，如"我拿命换来的孩子，他说不是他的"
   - 爽点型：突出逆袭爽感，如"被赶出家门后，我成了千万富婆"
   - 揭秘型：引发好奇心，如"结婚三年，我才知道他的真实身份"
3. 必须贴近导语核心冲突，但要用更吸引人的方式表达
4. 避免文艺腔，要用大白话、口语化表达
5. 可以适当使用感叹号增强语气

输出格式：
1. 《xxx》—— 类型：冲突型 | 释义：...
2. 《xxx》—— 类型：反转型 | 释义：...
3. 《xxx》—— 类型：情绪型 | 释义：...
4. 《xxx》—— 类型：爽点型 | 释义：...
5. 《xxx》—— 类型：揭秘型 | 释义：..."""

TAG_SELECTION_PROMPT_TEMPLATE = """你是一位短篇内容运营编辑，需要为作品确定平台分类和内容标签。

【主分类候选】
{main_categories}

【可选标签库】
- 情节标签：{plot_tags}
- 角色标签：{role_tags}
- 情绪标签：{emotion_tags}
- 背景标签：{background_tags}

【作品信息】
- 用户指定主分类：{category}
- 词条：{keywords}
- 书名：{title}
- 导语：{selected_synopsis}

【完整正文】
{full_text}

请严格执行：
1. 主分类固定使用“用户指定主分类”，不要改写。
   如果用户指定主分类不在候选列表中，也必须原样使用用户指定主分类。
2. 除主分类外，再从标签库中选出最贴切的 4 到 7 个标签，优先输出 7 个。
3. 不得自造标签，不得输出标签库之外的内容。
4. 标签尽量覆盖多个维度，但以贴合作品为准。
5. 只输出 JSON，不要附加解释。

JSON 格式：
{{
  "main_category": "女性成长",
  "plot_tags": ["大女主", "打脸逆袭"],
  "role_tags": ["医生"],
  "emotion_tags": ["励志"],
  "background_tags": ["现代", "职场"]
}}"""


def parse_synopsis_candidates(raw_text: str) -> List[Dict[str, Any]]:
    """从模型输出中解析导语候选。"""

    text = (raw_text or "").strip()
    if not text:
        return []

    pattern = re.compile(
        r"【导语([一二三四五12345])】(?:（(?P<style>[^）]+)）)?\s*(?P<content>.*?)(?=(?:\n\s*【导语[一二三四五12345]】)|\Z)",
        re.S,
    )
    parsed: List[Dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        content = match.group("content").strip()
        if not content:
            continue
        parsed.append(
            {
                "index": index,
                "style": (match.group("style") or "").strip(),
                "content": content,
            }
        )

    if len(parsed) == 5:
        return parsed

    blocks = [block.strip() for block in re.split(r"(?:\n\s*\n)+", text) if block.strip()]
    fallback: List[Dict[str, Any]] = []
    for index, block in enumerate(blocks[:5], start=1):
        cleaned = re.sub(r"^\d+[.)、]\s*", "", block).strip()
        if not cleaned:
            continue
        fallback.append({"index": index, "style": "", "content": cleaned})
    return fallback


def parse_material_analysis(raw_text: str, fallback_source: str = "", fallback_category: str = "其他") -> Dict[str, Any]:
    """从模型输出中解析统一输入分析结果。"""

    text = (raw_text or "").strip()
    data: Dict[str, Any] = {}
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    data = {}

    if not isinstance(data, dict):
        data = {}

    fallback_keywords = ShortStoryWorkflowStateMachine._normalize_keywords(fallback_source)
    detected = data.get("detected_material_types", [])
    if not isinstance(detected, list):
        detected = []
    normalized_detected = []
    seen_detected = set()
    for item in detected:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in seen_detected:
            normalized_detected.append(cleaned)
            seen_detected.add(cleaned)

    keywords = ShortStoryWorkflowStateMachine._normalize_keywords(data.get("keywords", fallback_keywords))
    if not normalized_detected:
        normalized_detected = ["keywords"] if keywords else ["inspiration"]

    borrowed_highlights = data.get("borrowed_highlights", [])
    if not isinstance(borrowed_highlights, list):
        borrowed_highlights = []
    constraints = data.get("constraints", [])
    if not isinstance(constraints, list):
        constraints = []
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    confidence = data.get("confidence", 0.66)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.66
    confidence = max(0.0, min(1.0, confidence))

    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = f"输入已解析为 {', '.join(normalized_detected)} 素材，准备进入创意方案生成。"

    genre_hint = str(data.get("genre_hint") or fallback_category or "其他").strip() or "其他"

    return {
        "summary": summary,
        "confidence": confidence,
        "detected_material_types": normalized_detected,
        "keywords": keywords,
        "genre_hint": genre_hint,
        "borrowed_highlights": [str(item).strip() for item in borrowed_highlights if str(item).strip()],
        "constraints": [str(item).strip() for item in constraints if str(item).strip()],
        "warnings": [str(item).strip() for item in warnings if str(item).strip()],
    }


def parse_fusion_candidates(raw_text: str) -> List[Dict[str, Any]]:
    """从模型输出中解析 3 个创意方案。"""

    text = (raw_text or "").strip()
    if not text:
        return []

    pattern = re.compile(
        r"【方案([一二三123])】\s*(?P<body>.*?)(?=(?:\n\s*【方案[一二三123]】)|\Z)",
        re.S,
    )
    parsed: List[Dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        body = match.group("body").strip()
        if not body:
            continue

        def _extract(label: str) -> str:
            field_match = re.search(rf"{label}\s*[：:]\s*(.+)", body)
            return (field_match.group(1) if field_match else "").strip()

        title = _extract("标题") or f"方案{index}"
        route = _extract("路数")
        hook = _extract("钩子")
        borrowed_structure = _extract("借鉴骨架")
        refresh_plan = _extract("内容换新")
        premise = _extract("故事梗概") or body
        parsed.append(
            {
                "index": index,
                "title": title,
                "route": route,
                "hook": hook,
                "borrowed_structure": borrowed_structure,
                "refresh_plan": refresh_plan,
                "premise": premise,
                "content": premise,
            }
        )

    if len(parsed) == 3:
        return parsed

    blocks = [block.strip() for block in re.split(r"(?:\n\s*\n)+", text) if block.strip()]
    fallback: List[Dict[str, Any]] = []
    for index, block in enumerate(blocks[:3], start=1):
        cleaned = re.sub(r"^\d+[.)、]\s*", "", block).strip()
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        title = lines[0].replace("标题：", "").replace("标题:", "").strip() if lines else f"方案{index}"
        hook = lines[1] if len(lines) > 1 else cleaned[:60]
        fallback.append(
            {
                "index": index,
                "title": title or f"方案{index}",
                "route": "",
                "hook": hook,
                "borrowed_structure": "",
                "refresh_plan": "",
                "premise": cleaned,
                "content": cleaned,
            }
        )
    return fallback


def parse_title_candidates(raw_text: str) -> List[Dict[str, Any]]:
    """从模型输出中解析书名候选。"""

    text = (raw_text or "").strip()
    if not text:
        return []

    pattern = re.compile(
        r"^\s*(\d+)[.)、]\s*(?:《)?(?P<title>[^》\n]+)(?:》)?\s*(?:[—\-–]+)?\s*(?:类型[:：]\s*(?P<category>[^|\n]+))?\s*(?:\|\s*释义[:：]\s*(?P<explanation>.+))?$",
        re.M,
    )
    parsed: List[Dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        title = (match.group("title") or "").strip()
        if not title:
            continue
        parsed.append(
            {
                "index": index,
                "title": title.replace("《", "").replace("》", ""),
                "category": (match.group("category") or "").strip(),
                "explanation": (match.group("explanation") or "").strip(),
            }
        )

    if len(parsed) == 5:
        return parsed

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fallback: List[Dict[str, Any]] = []
    for index, line in enumerate(lines[:5], start=1):
        cleaned = re.sub(r"^\d+[.)、]\s*", "", line).strip()
        title_match = re.search(r"《([^》]+)》", cleaned)
        title = title_match.group(1) if title_match else cleaned.split("—", 1)[0].split("-", 1)[0].strip()
        if not title:
            continue
        fallback.append({"index": index, "title": title, "category": "", "explanation": ""})
    return fallback


def parse_story_tags(raw_text: str, default_category: str = "") -> Dict[str, Any]:
    """从模型输出中解析主分类和内容标签。"""

    allowed_map = {group: set(items) for group, items in SHORT_STORY_TAG_GROUPS.items()}
    data: Dict[str, Any] = {}
    text = (raw_text or "").strip()

    if text:
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                data = {}

    main_category = _normalize_main_category(
        default_category or data.get("main_category") or "",
        default_category or "其他",
    )

    normalized: Dict[str, Any] = {"main_category": main_category}
    selected_all: List[str] = []
    selected_set = set()

    for group_name in ("plot_tags", "role_tags", "emotion_tags", "background_tags"):
        values = data.get(group_name)
        if not isinstance(values, list):
            values = []
        group_items: List[str] = []
        for value in values:
            tag = str(value or "").strip()
            if not tag or tag not in allowed_map[group_name] or tag in selected_set:
                continue
            group_items.append(tag)
            selected_all.append(tag)
            selected_set.add(tag)
        normalized[group_name] = group_items

    if len(selected_all) < 4 and text:
        for group_name in ("plot_tags", "role_tags", "emotion_tags", "background_tags"):
            for tag in SHORT_STORY_TAG_GROUPS[group_name]:
                if tag in selected_set:
                    continue
                if tag in text:
                    normalized[group_name].append(tag)
                    selected_all.append(tag)
                    selected_set.add(tag)
                if len(selected_all) >= 7:
                    break
            if len(selected_all) >= 7:
                break

    if len(selected_all) > 7:
        selected_all = selected_all[:7]
        selected_set = set(selected_all)
        for group_name in ("plot_tags", "role_tags", "emotion_tags", "background_tags"):
            normalized[group_name] = [tag for tag in normalized[group_name] if tag in selected_set]

    normalized["all_tags"] = selected_all
    return normalized


def parse_chapters_from_full_text(raw_text: str) -> List[Dict[str, Any]]:
    """从完整正文中解析章节。"""

    text = (raw_text or "").strip()
    if not text:
        return []

    chapters: List[Dict[str, Any]] = []
    for index, (label, title, content) in enumerate(_iter_chapter_sections(text), start=1):
        if not content:
            continue
        chapter_number = _coerce_chapter_number(label, index)
        chapters.append(
            {
                "chapter_number": chapter_number,
                "title": title or f"第{chapter_number}章",
                "content": content,
            }
        )
    return chapters


def parse_outline_payload(raw_text: str, planned_chapters: int = 0) -> Dict[str, Any]:
    """从模型输出中抽取角色表、时间线和章节蓝图。"""

    text = (raw_text or "").strip()
    character_table = _extract_markdown_section(text, "角色表") or "待补充"
    timeline = _extract_markdown_section(text, "时间线") or "待补充"
    chapter_blueprints = _extract_chapter_blueprints(text)

    if not chapter_blueprints and planned_chapters > 0:
        chapter_blueprints = [
            {
                "chapter_number": index,
                "title": f"第{index}章",
                "summary": "",
                "characters": "",
                "core_event": "",
                "narrative_function": "",
                "emotion_point": "",
            }
            for index in range(1, planned_chapters + 1)
        ]

    return {
        "outline_text": text,
        "character_table": character_table,
        "timeline": timeline,
        "chapter_blueprints": chapter_blueprints,
    }


def _extract_markdown_section(text: str, title: str) -> str:
    escaped_title = re.escape(title)
    pattern = re.compile(
        rf"^\s*##+\s*{escaped_title}\s*$\n?(?P<body>.*?)(?=^\s*##+\s+\S|\Z)",
        re.M | re.S,
    )
    match = pattern.search(text or "")
    if match:
        return match.group("body").strip()

    inline_pattern = re.compile(
        rf"【{escaped_title}】\s*(?P<body>.*?)(?=【\S+】|\Z)",
        re.S,
    )
    inline_match = inline_pattern.search(text or "")
    if inline_match:
        return inline_match.group("body").strip()
    return ""


def _extract_chapter_blueprints(text: str) -> List[Dict[str, Any]]:
    blueprints: List[Dict[str, Any]] = []
    for index, (label, title, body) in enumerate(_iter_chapter_sections(text), start=1):
        resolved_number = _coerce_chapter_number(label, index)
        resolved_title = title or f"第{resolved_number}章"
        blueprints.append(
            {
                "chapter_number": resolved_number,
                "title": resolved_title,
                "summary": _extract_bullet_value(body, ["摘要", "本章摘要"]),
                "characters": _extract_bullet_value(body, ["出场角色", "出场人物", "主要角色"]),
                "core_event": _extract_bullet_value(body, ["核心事件", "关键事件", "主要事件"]),
                "narrative_function": _extract_bullet_value(body, ["叙事功能", "剧情作用", "章节作用", "功能定位"]),
                "emotion_point": _extract_bullet_value(body, ["情绪节点", "情绪重点", "情绪爆点"]),
            }
        )
    return blueprints


def _ensure_chapter_blueprint_count(
    chapter_blueprints: Optional[Sequence[Dict[str, Any]]],
    planned_chapters: int = 0,
    existing_chapters: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen_numbers = set()

    for index, item in enumerate(chapter_blueprints or [], start=1):
        if not isinstance(item, dict):
            continue
        chapter_number = int(item.get("chapter_number") or item.get("number") or index)
        if chapter_number in seen_numbers:
            continue
        normalized.append(
            {
                "chapter_number": chapter_number,
                "title": str(item.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章",
                "summary": str(item.get("summary") or "").strip(),
                "characters": str(item.get("characters") or item.get("cast") or "").strip(),
                "core_event": str(item.get("core_event") or item.get("event") or "").strip(),
                "narrative_function": str(item.get("narrative_function") or item.get("purpose") or "").strip(),
                "emotion_point": str(item.get("emotion_point") or "").strip(),
            }
        )
        seen_numbers.add(chapter_number)

    chapter_titles = {}
    for item in existing_chapters or []:
        if not isinstance(item, dict):
            continue
        chapter_number = int(item.get("chapter_number") or item.get("number") or 0)
        if chapter_number <= 0:
            continue
        title = str(item.get("title") or "").strip()
        if title:
            chapter_titles[chapter_number] = title

    highest_existing = max(seen_numbers | set(chapter_titles.keys()) | ({int(planned_chapters)} if planned_chapters else set()), default=0)
    for chapter_number in range(1, highest_existing + 1):
        if chapter_number in seen_numbers:
            continue
        normalized.append(
            {
                "chapter_number": chapter_number,
                "title": chapter_titles.get(chapter_number) or f"第{chapter_number}章",
                "summary": "",
                "characters": "",
                "core_event": "",
                "narrative_function": "",
                "emotion_point": "",
            }
        )

    normalized.sort(key=lambda item: item["chapter_number"])
    return normalized


def _iter_chapter_sections(text: str) -> Iterable[tuple[str, str, str]]:
    pattern = re.compile(
        r"^\s*###\s*(?:(?:第)?(?P<label_cn>[一二三四五六七八九十百零\d]+)章(?:[：: ]*)|(?P<label_digit>\d+)[.、](?:\s*))(?P<title>[^\n]*)\n(?P<body>.*?)(?=^\s*###\s*(?:(?:第)?(?:[一二三四五六七八九十百零\d]+)章(?:[：: ]*)|\d+[.、](?:\s*))|\Z)",
        re.M | re.S,
    )
    for match in pattern.finditer(text or ""):
        yield (
            (match.group("label_digit") or match.group("label_cn") or "").strip(),
            (match.group("title") or "").strip(),
            (match.group("body") or "").strip(),
        )


def _extract_bullet_value(text: str, label: str | Sequence[str]) -> str:
    labels = [str(item).strip() for item in ([label] if isinstance(label, str) else list(label)) if str(item).strip()]
    if not labels:
        return ""

    escaped_labels = "|".join(re.escape(item) for item in labels)
    patterns = [
        re.compile(
            rf"(?mi)^[ \t>*-]*(?:\d+[.、)\-]\s*)?(?:\*\*)?(?:{escaped_labels})(?:\*\*)?\s*[：:]\s*(?P<value>.+?)\s*$"
        ),
        re.compile(
            rf"(?mi)^[ \t>*-]*(?:\d+[.、)\-]\s*)?【(?:{escaped_labels})】\s*(?P<value>.+?)\s*$"
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text or "")
        if match:
            return match.group("value").strip()
    return ""


def _coerce_chapter_number(value: str, fallback: int) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        return max(1, int(text))

    mapping = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if text in mapping:
        return mapping[text]
    if text.startswith("十") and len(text) == 2 and text[1] in mapping:
        return 10 + mapping[text[1]]
    if len(text) == 2 and text[0] in mapping and text[1] == "十":
        return mapping[text[0]] * 10
    if len(text) == 3 and text[0] in mapping and text[1] == "十" and text[2] in mapping:
        return mapping[text[0]] * 10 + mapping[text[2]]
    return fallback


def _strip_chapter_prefix(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"^(?:第?[一二三四五六七八九十百零\d]+章[：:、.\s-]*)", "", value)
    value = re.sub(r"^(?:\d+[.、:：\s-]*)", "", value)
    return value.strip()


def _format_chapter_heading(chapter_number: int, title: str) -> str:
    cleaned_title = _strip_chapter_prefix(title)
    if cleaned_title:
        return f"{chapter_number}. {cleaned_title}"
    return f"{chapter_number}."


def _clean_export_title(title: str) -> str:
    value = str(title or "").strip()
    if value.startswith("《") and value.endswith("》"):
        value = value[1:-1].strip()
    return value


def _clean_export_tag_list(main_category: str, tags: Sequence[str]) -> List[str]:
    merged: List[str] = []
    for item in [main_category, *list(tags or [])]:
        value = str(item or "").strip()
        if value and value not in merged:
            merged.append(value)
    return merged


def _clean_export_block(text: str, chapter_number: Optional[int] = None, strip_style_hint: bool = False) -> str:
    raw_lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: List[str] = []
    previous_blank = False
    chapter_heading_pattern = re.compile(
        rf"^\s*(?:#+\s*)?(?:{chapter_number}\s*[.、:：-].*|第?\s*[一二三四五六七八九十百零\d]+\s*章(?:\s*[：:、.\-]\s*.*)?)\s*$"
    ) if chapter_number is not None else None

    for index, raw_line in enumerate(raw_lines):
        line = raw_line.strip()
        if not line:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
                previous_blank = True
            continue

        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        if strip_style_hint:
            line = re.sub(r"[（(][^）)]*向[）)]", "", line)
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"[\\*_\-`~#\s]+", line):
            continue
        if line in {"导语", "正文"}:
            continue
        if index == 0 and chapter_heading_pattern and chapter_heading_pattern.match(line):
            continue

        cleaned_lines.append(line)
        previous_blank = False

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def _build_clean_export_lines_from_final_output(final_output: str) -> List[str]:
    raw_lines = str(final_output or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not any(line.strip() for line in raw_lines):
        return []

    title = ""
    tags: List[str] = []
    synopsis_lines: List[str] = []
    chapters: List[Dict[str, Any]] = []
    current_section = ""
    current_chapter: Optional[Dict[str, Any]] = None

    def push_tag(raw_value: str) -> None:
        for part in re.split(r"[、,，|]", str(raw_value or "")):
            value = str(part or "").strip()
            if value and value not in tags:
                tags.append(value)

    def flush_chapter() -> None:
        nonlocal current_chapter
        if current_chapter and current_chapter["lines"]:
            content = "\n".join(current_chapter["lines"]).strip()
            if content:
                chapters.append(
                    {
                        "chapter_number": current_chapter["chapter_number"],
                        "content": content,
                    }
                )
        current_chapter = None

    for raw_line in raw_lines:
        line = str(raw_line or "").strip()
        if not line:
            if current_chapter and current_chapter["lines"] and current_chapter["lines"][-1] != "":
                current_chapter["lines"].append("")
            elif current_section == "synopsis" and synopsis_lines and synopsis_lines[-1] != "":
                synopsis_lines.append("")
            continue

        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"《([^》]+)》", r"\1", line).strip()
        if not line or re.fullmatch(r"\\?[*_`~#-]+", line) or re.fullmatch(r"---+", line) or line == "（全文完）":
            continue

        match = re.match(r"^主分类：(.+)$", line)
        if match:
            push_tag(match.group(1))
            continue
        match = re.match(r"^内容标签：(.+)$", line)
        if match:
            push_tag(match.group(1))
            continue
        if re.match(r"^词条标签：", line):
            continue
        if line == "导语":
            flush_chapter()
            current_section = "synopsis"
            continue
        if line == "正文":
            flush_chapter()
            current_section = "body"
            continue

        chapter_match = re.match(r"^(\d+)\.\s*(.*)$", line)
        if chapter_match:
            flush_chapter()
            current_section = "body"
            current_chapter = {
                "chapter_number": int(chapter_match.group(1)),
                "lines": [],
            }
            continue

        if not title:
            title = line
            continue

        if current_section == "synopsis":
            synopsis_line = re.sub(r"[（(][^）)]*向[）)]", "", line).strip()
            if synopsis_line:
                synopsis_lines.append(synopsis_line)
            continue

        if current_chapter is not None:
            cleaned_line = line.replace(r"\*", "").rstrip()
            if cleaned_line:
                current_chapter["lines"].append(cleaned_line)

    flush_chapter()

    lines: List[str] = []
    if title:
        lines.append(title)
    if tags:
        lines.append(f"标签：{'、'.join(tags)}")
    synopsis = "\n".join(synopsis_lines).strip()
    if synopsis:
        lines.append(f"导语：{synopsis}")
    if lines and chapters:
        lines.append("")

    for chapter in chapters:
        lines.append(f"{int(chapter['chapter_number'])}.")
        lines.extend(str(chapter.get("content") or "").splitlines())
        lines.append("")

    while lines and not lines[-1]:
        lines.pop()
    return lines


def _coerce_chapter_word_target(value: object, fallback: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = int(fallback)
    return max(500, min(3000, parsed))


def _resolve_chapter_plan(target_total_words: int, chapter_word_target: Optional[int] = None) -> Dict[str, int | str]:
    target_words = max(3000, int(target_total_words or 5000))
    default_target = 800 if target_words < 8000 else 1000
    preferred_target = (
        _coerce_chapter_word_target(chapter_word_target, default_target)
        if chapter_word_target is not None
        else default_target
    )
    preferred_min = max(300, preferred_target - 100)
    preferred_max = min(5000, preferred_target + 100)

    candidate_counts = [
        count
        for count in range(1, max(1, target_words // max(preferred_min, 1)) + 2)
        if preferred_min <= (target_words / count) <= preferred_max
    ]
    if candidate_counts:
        planned_chapters = min(
            candidate_counts,
            key=lambda count: (
                abs((target_words / count) - preferred_target),
                abs((target_words / count) - round(target_words / count)),
                count,
            ),
        )
    else:
        planned_chapters = max(1, round(target_words / max(preferred_target, 1)))

    resolved_target = _coerce_chapter_word_target(round(target_words / max(planned_chapters, 1)), preferred_target)
    chapter_word_min = max(300, resolved_target - 100)
    chapter_word_max = min(5000, resolved_target + 100)
    total_word_upper = max(target_words, planned_chapters * chapter_word_max)
    chapter_count_requirement = (
        f"请按 {planned_chapters} 章规划，每章约 {chapter_word_min}~{chapter_word_max} 字，"
        f"全文目标不少于 {target_words} 字，可适度上浮至约 {total_word_upper} 字"
    )

    return {
        "target_words": target_words,
        "planned_chapters": int(planned_chapters),
        "min_chapters": int(planned_chapters),
        "chapter_word_target": resolved_target,
        "chapter_word_min": chapter_word_min,
        "chapter_word_max": chapter_word_max,
        "chapter_count_requirement": chapter_count_requirement,
        "target_words_upper": int(total_word_upper),
    }


class ShortStoryWorkflowStateMachine:
    """短篇创作工作流状态机。"""

    STATE_VERSION = "1.0"

    def __init__(self, payload: Optional[Dict[str, Any]] = None):
        self.state = self._normalize_state(payload)

    def snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(self.state)

    def start(
        self,
        keywords: Sequence[str] | str | None = None,
        target_total_words: int = 5000,
        chapter_word_target: Optional[int] = None,
        category: str = "其他",
        source_input: str = "",
    ) -> None:
        normalized_keywords = self._normalize_keywords(keywords or [])
        normalized_category = _normalize_main_category(category)
        raw_input = (source_input or "").strip()
        if not raw_input and normalized_keywords:
            raw_input = "、".join(normalized_keywords)
        if not raw_input:
            raise ValueError("请提供创作素材")

        plan = _resolve_chapter_plan(target_total_words, chapter_word_target)
        target_words = int(plan["target_words"])
        planned_chapters = int(plan["planned_chapters"])
        warnings: List[str] = []
        if len(normalized_keywords) > 10:
            warnings.append("词条数量超过 10 个，建议后续在导语确认阶段进行聚类或精简。")
        warnings.append(
            f"系统已按目标字数智能规划为 {planned_chapters} 章，建议每章约 {int(plan['chapter_word_min'])}~{int(plan['chapter_word_max'])} 字，全文不少于 {target_words} 字。"
        )

        self.state.update(
            {
                "version": self.STATE_VERSION,
                "state": ShortStoryStage.ANALYZING_SOURCE_INPUT.value,
                "raw_input": raw_input,
                "legacy_keywords": normalized_keywords,
                "input_analysis": {},
                "input_confidence": 0.0,
                "detected_material_types": [],
                "derived_keywords": normalized_keywords,
                "fusion_candidates": [],
                "selected_fusion": {},
                "selected_fusion_index": None,
                "keywords": normalized_keywords,
                "target_total_words": target_words,
                "custom_chapter_word_target": int(chapter_word_target) if chapter_word_target is not None else None,
                "planned_chapters": planned_chapters,
                "min_chapters": int(plan["min_chapters"]),
                "chapter_count_requirement": str(plan["chapter_count_requirement"]),
                "target_words_upper": int(plan["target_words_upper"]),
                "chapter_word_target": int(plan["chapter_word_target"]),
                "chapter_word_min": int(plan["chapter_word_min"]),
                "chapter_word_max": int(plan["chapter_word_max"]),
                "category": normalized_category,
                "tone": normalized_category,
                "warnings": warnings,
                "selected_synopsis": "",
                "selected_synopsis_index": None,
                "synopsis_candidates": [],
                "outline_text": "",
                "outline_feedback": "",
                "outline_confirmed": False,
                "repair_placeholder_numbers": [],
                "character_table": "",
                "timeline": "",
                "chapter_blueprints": [],
                "chapters": [],
                "quality_report": "",
                "coherence_report": "",
                "title_candidates": [],
                "selected_title": "",
                "selected_title_index": None,
                "story_tags": {
                    "main_category": normalized_category,
                    "plot_tags": [],
                    "role_tags": [],
                    "emotion_tags": [],
                    "background_tags": [],
                    "all_tags": [],
                },
                "final_output": "",
                "manual_intervention_required": False,
                "retry_counts": {
                    "quality_check": 0,
                    "coherence_review": 0,
                },
            }
        )

    def record_input_analysis(self, analysis: Dict[str, Any]) -> None:
        self._assert_state([ShortStoryStage.ANALYZING_SOURCE_INPUT])
        payload = analysis if isinstance(analysis, dict) else {}
        derived_keywords = self._normalize_keywords(payload.get("keywords", []))
        legacy_keywords = self._normalize_keywords(self.state.get("legacy_keywords", []))
        resolved_keywords = derived_keywords or legacy_keywords
        self.state["input_analysis"] = {
            "summary": str(payload.get("summary") or "").strip(),
            "genre_hint": str(payload.get("genre_hint") or "").strip(),
            "borrowed_highlights": [str(item).strip() for item in payload.get("borrowed_highlights", []) if str(item).strip()],
            "constraints": [str(item).strip() for item in payload.get("constraints", []) if str(item).strip()],
            "warnings": [str(item).strip() for item in payload.get("warnings", []) if str(item).strip()],
        }
        try:
            confidence = float(payload.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        self.state["input_confidence"] = max(0.0, min(1.0, confidence))
        material_types = payload.get("detected_material_types", [])
        if not isinstance(material_types, list):
            material_types = []
        self.state["detected_material_types"] = [str(item).strip() for item in material_types if str(item).strip()]
        self.state["derived_keywords"] = resolved_keywords
        self.state["keywords"] = resolved_keywords
        self.state["warnings"] = [
            item
            for item in self.state.get("warnings", [])
            if "素材识别" not in str(item)
        ]
        for warning in self.state["input_analysis"].get("warnings", []):
            self.state["warnings"].append(f"素材识别提示：{warning}")
        self.state["state"] = ShortStoryStage.GENERATING_FUSION_OPTIONS.value

    def register_fusion_candidates(self, candidates: Sequence[Any]) -> None:
        self._assert_state([ShortStoryStage.GENERATING_FUSION_OPTIONS])
        normalized = self._normalize_fusion_candidates(candidates, expected=3)
        self.state["fusion_candidates"] = normalized
        self.state["state"] = ShortStoryStage.AWAITING_FUSION_SELECTION.value

    def select_fusion(self, selection: int) -> None:
        allowed_states = {
            ShortStoryStage.AWAITING_FUSION_SELECTION,
            ShortStoryStage.GENERATING_SYNOPSIS,
            ShortStoryStage.AWAITING_SYNOPSIS_SELECTION,
            ShortStoryStage.GENERATING_OUTLINE,
            ShortStoryStage.AWAITING_OUTLINE_CONFIRM,
            ShortStoryStage.WRITING_CONTENT,
            ShortStoryStage.QUALITY_CHECKING,
            ShortStoryStage.COHERENCE_REVIEWING,
            ShortStoryStage.GENERATING_TITLES,
            ShortStoryStage.AWAITING_TITLE_SELECTION,
            ShortStoryStage.ASSEMBLING_OUTPUT,
            ShortStoryStage.COMPLETED,
        }
        current_state = ShortStoryStage(self.state["state"])
        if current_state not in allowed_states:
            self._assert_state([ShortStoryStage.AWAITING_FUSION_SELECTION])
        selected = self._select_by_one_based_index(self.state["fusion_candidates"], selection, "创意方案")
        if current_state != ShortStoryStage.AWAITING_FUSION_SELECTION:
            self.state["selected_synopsis"] = ""
            self.state["selected_synopsis_index"] = None
            self.state["synopsis_candidates"] = []
            self.state["outline_text"] = ""
            self.state["outline_feedback"] = ""
            self.state["outline_confirmed"] = False
            self.state["repair_placeholder_numbers"] = []
            self.state["character_table"] = ""
            self.state["timeline"] = ""
            self.state["chapter_blueprints"] = []
            self.state["chapters"] = []
            self.state["quality_report"] = ""
            self.state["coherence_report"] = ""
            self.state["title_candidates"] = []
            self.state["selected_title"] = ""
            self.state["selected_title_index"] = None
            self.state["final_output"] = ""
            self.state["manual_intervention_required"] = False
            self.state["retry_counts"]["quality_check"] = 0
            self.state["retry_counts"]["coherence_review"] = 0
            self.state["story_tags"] = self._normalize_story_tags(
                {"main_category": self.state.get("category", "其他")}
            )
        self.state["selected_fusion"] = selected
        self.state["selected_fusion_index"] = selection
        self.state["state"] = ShortStoryStage.GENERATING_SYNOPSIS.value

    def register_synopsis_candidates(self, candidates: Sequence[Any]) -> None:
        self._assert_state([ShortStoryStage.GENERATING_SYNOPSIS])
        normalized = self._normalize_named_candidates(candidates, expected=5, kind="导语")
        self.state["synopsis_candidates"] = normalized
        self.state["state"] = ShortStoryStage.AWAITING_SYNOPSIS_SELECTION.value

    def select_synopsis(self, selection: int) -> None:
        allowed_states = {
            ShortStoryStage.AWAITING_SYNOPSIS_SELECTION,
            ShortStoryStage.GENERATING_OUTLINE,
            ShortStoryStage.AWAITING_OUTLINE_CONFIRM,
            ShortStoryStage.WRITING_CONTENT,
            ShortStoryStage.QUALITY_CHECKING,
            ShortStoryStage.COHERENCE_REVIEWING,
            ShortStoryStage.GENERATING_TITLES,
            ShortStoryStage.AWAITING_TITLE_SELECTION,
            ShortStoryStage.ASSEMBLING_OUTPUT,
            ShortStoryStage.COMPLETED,
        }
        current_state = ShortStoryStage(self.state["state"])
        if current_state not in allowed_states:
            self._assert_state([ShortStoryStage.AWAITING_SYNOPSIS_SELECTION])
        selected = self._select_by_one_based_index(self.state["synopsis_candidates"], selection, "导语")
        if current_state != ShortStoryStage.AWAITING_SYNOPSIS_SELECTION:
            self.state["outline_text"] = ""
            self.state["outline_feedback"] = ""
            self.state["outline_confirmed"] = False
            self.state["repair_placeholder_numbers"] = []
            self.state["character_table"] = ""
            self.state["timeline"] = ""
            self.state["chapter_blueprints"] = []
            self.state["chapters"] = []
            self.state["quality_report"] = ""
            self.state["coherence_report"] = ""
            self.state["title_candidates"] = []
            self.state["selected_title"] = ""
            self.state["selected_title_index"] = None
            self.state["final_output"] = ""
            self.state["manual_intervention_required"] = False
            self.state["retry_counts"]["quality_check"] = 0
            self.state["retry_counts"]["coherence_review"] = 0
            self.state["story_tags"] = self._normalize_story_tags(
                {"main_category": self.state.get("category", "其他")}
            )
            self.state["warnings"] = [
                item
                for item in self.state.get("warnings", [])
                if "大纲实际生成了" not in str(item)
                and "缺少有效大纲蓝图" not in str(item)
                and "已清理第 " not in str(item)
            ]
        self.state["selected_synopsis"] = selected["content"]
        self.state["selected_synopsis_index"] = selection
        self.state["state"] = ShortStoryStage.GENERATING_OUTLINE.value

    def record_outline(
        self,
        outline_text: str,
        character_table: str = "",
        timeline: str = "",
        chapter_blueprints: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        self._assert_state([ShortStoryStage.GENERATING_OUTLINE])
        if not (outline_text or "").strip():
            raise ValueError("outline_text 不能为空")

        self.state["outline_text"] = outline_text.strip()
        self.state["character_table"] = (character_table or "").strip() or "待补充"
        self.state["timeline"] = (timeline or "").strip() or "待补充"
        normalized_blueprints = self._normalize_chapter_blueprints(chapter_blueprints)
        estimated_planned = int(self.state.get("planned_chapters") or 0)
        if self.state.get("repair_placeholder_numbers"):
            estimated_planned = max(estimated_planned, int(self.state.get("min_chapters") or 0))
        if normalized_blueprints:
            actual_planned = len(normalized_blueprints)
            self.state["chapter_blueprints"] = normalized_blueprints
            if actual_planned != estimated_planned:
                self.state["warnings"] = [
                    item
                    for item in self.state.get("warnings", [])
                    if "大纲实际生成了" not in str(item) and "请按 " not in str(item)
                ]
                self.state["warnings"].append(
                    f"大纲实际生成了 {actual_planned} 章，但当前计划应为 {estimated_planned} 章。请调整或重生成大纲后再确认。"
                )
        else:
            self.state["chapter_blueprints"] = normalized_blueprints
        self.state["state"] = ShortStoryStage.AWAITING_OUTLINE_CONFIRM.value

    def confirm_outline(self, approved: bool = True, feedback: str = "") -> None:
        self._assert_state([ShortStoryStage.AWAITING_OUTLINE_CONFIRM])
        if approved:
            self._assert_repair_placeholder_blueprints_resolved()
            self.state["outline_confirmed"] = True
            self.state["outline_feedback"] = ""
            self.state["repair_placeholder_numbers"] = []
            self.state["manual_intervention_required"] = False
            self.state["warnings"] = [
                item
                for item in self.state.get("warnings", [])
                if "缺少有效大纲蓝图" not in str(item) and "已清理第 " not in str(item)
            ]
            self.state["state"] = ShortStoryStage.WRITING_CONTENT.value
            return

        self.state["outline_confirmed"] = False
        self.state["outline_feedback"] = (feedback or "").strip()
        self.state["state"] = ShortStoryStage.GENERATING_OUTLINE.value

    def _assert_repair_placeholder_blueprints_resolved(self) -> None:
        required_numbers = [
            int(item)
            for item in self.state.get("repair_placeholder_numbers", [])
            if str(item).strip().isdigit() and int(item) > 0
        ]
        if not required_numbers:
            return

        unresolved = ShortStoryCreatorService._find_placeholder_blueprint_numbers(self.state, required_numbers)
        if unresolved:
            label = "、".join(str(item) for item in unresolved)
            raise ValueError(
                f"当前仍需补全第 {label} 章的大纲蓝图，请先在大纲中补回这些章节并填写有效摘要/事件信息，再确认大纲。"
            )

    def rollback_placeholder_blueprints(self, feedback: str = "") -> None:
        placeholder_numbers = ShortStoryCreatorService._find_placeholder_blueprint_numbers(self.state)
        if not placeholder_numbers:
            raise ValueError("当前不存在需要回退处理的异常章节。")

        valid_blueprints = [
            item
            for item in self.state.get("chapter_blueprints", [])
            if int(item.get("chapter_number") or 0) not in placeholder_numbers
        ]
        self.state["chapter_blueprints"] = self._normalize_chapter_blueprints(valid_blueprints)
        self.state["planned_chapters"] = len(self.state["chapter_blueprints"])
        self.state["chapters"] = [
            item
            for item in self.state.get("chapters", [])
            if int(item.get("chapter_number") or 0) not in placeholder_numbers
        ]
        self.state["repair_placeholder_numbers"] = list(placeholder_numbers)
        self.state["outline_confirmed"] = False
        self.state["state"] = ShortStoryStage.AWAITING_OUTLINE_CONFIRM.value
        self.state["manual_intervention_required"] = True
        self.state["quality_report"] = ""
        self.state["coherence_report"] = ""
        self.state["title_candidates"] = []
        self.state["selected_title"] = ""
        self.state["selected_title_index"] = None
        self.state["final_output"] = ""
        self.state["retry_counts"]["quality_check"] = 0
        self.state["retry_counts"]["coherence_review"] = 0

        missing_label = "、".join(str(item) for item in placeholder_numbers)
        default_feedback = (
            f"当前项目曾生成第 {missing_label} 章等缺少有效章节蓝图的异常章节。"
            f"请基于现有正文与大纲，重新规划后续章节，确保总章节数与大纲蓝图一致。"
        )
        self.state["outline_feedback"] = (feedback or "").strip() or default_feedback
        self.state["warnings"] = [
            item
            for item in self.state.get("warnings", [])
            if "缺少有效大纲蓝图" not in str(item) and "已清理第 " not in str(item)
        ]
        self.state["warnings"].append(
            f"已清理第 {missing_label} 章异常正文，并回退到大纲确认阶段。请先修正大纲，再继续生成后续章节。"
        )

    def record_chapter(self, chapter_number: int, title: str, content: str) -> None:
        self._assert_state(
            [
                ShortStoryStage.WRITING_CONTENT,
                ShortStoryStage.QUALITY_CHECKING,
                ShortStoryStage.COHERENCE_REVIEWING,
                ShortStoryStage.GENERATING_TITLES,
                ShortStoryStage.AWAITING_TITLE_SELECTION,
                ShortStoryStage.ASSEMBLING_OUTPUT,
                ShortStoryStage.COMPLETED,
            ]
        )
        current_stage = self.state["state"]
        chapter_number = max(1, int(chapter_number))
        normalized_title = (title or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
        normalized_content = (content or "").strip()
        if not normalized_content:
            raise ValueError("content 不能为空")

        chapter_payload = {
            "chapter_number": chapter_number,
            "title": normalized_title,
            "content": normalized_content,
            "word_count": self._count_story_chars(normalized_content),
        }

        remaining = [item for item in self.state["chapters"] if int(item.get("chapter_number", 0)) != chapter_number]
        remaining.append(chapter_payload)
        remaining.sort(key=lambda item: int(item.get("chapter_number", 0)))
        self.state["chapters"] = remaining

        if current_stage != ShortStoryStage.WRITING_CONTENT.value:
            self.state["quality_report"] = ""
            self.state["coherence_report"] = ""
            self.state["title_candidates"] = []
            self.state["selected_title"] = ""
            self.state["selected_title_index"] = None
            self.state["story_tags"] = self._normalize_story_tags(
                {"main_category": self.state.get("category", "其他")}
            )
            self.state["final_output"] = ""
            self.state["manual_intervention_required"] = False
            self.state["retry_counts"]["quality_check"] = 0
            self.state["retry_counts"]["coherence_review"] = 0

        expected_numbers = set(range(1, int(self.state.get("planned_chapters", 0)) + 1))
        current_numbers = {int(item.get("chapter_number", 0)) for item in remaining}
        if expected_numbers and expected_numbers.issubset(current_numbers):
            self.state["state"] = ShortStoryStage.QUALITY_CHECKING.value
        else:
            self.state["state"] = ShortStoryStage.WRITING_CONTENT.value

    def record_quality_check(
        self,
        report: str,
        passed: bool,
        revised_chapters: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        self._assert_state([ShortStoryStage.QUALITY_CHECKING])
        self.state["quality_report"] = (report or "").strip()
        if revised_chapters:
            self.state["chapters"] = self._normalize_written_chapters(revised_chapters)

        if passed:
            self.state["state"] = ShortStoryStage.COHERENCE_REVIEWING.value
            return

        self.state["retry_counts"]["quality_check"] += 1
        if self.state["retry_counts"]["quality_check"] >= 3:
            self.state["manual_intervention_required"] = True

    def record_coherence_review(
        self,
        report: str,
        passed: bool,
        final_chapters: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        self._assert_state([ShortStoryStage.COHERENCE_REVIEWING])
        self.state["coherence_report"] = (report or "").strip()
        if final_chapters:
            self.state["chapters"] = self._normalize_written_chapters(final_chapters)

        if passed:
            self.state["state"] = ShortStoryStage.GENERATING_TITLES.value
            return

        self.state["retry_counts"]["coherence_review"] += 1
        if self.state["retry_counts"]["coherence_review"] >= 2:
            self.state["manual_intervention_required"] = True
        self.state["state"] = ShortStoryStage.QUALITY_CHECKING.value

    def replace_chapters(self, chapters: Sequence[Dict[str, Any]]) -> None:
        self._assert_state(
            [
                ShortStoryStage.WRITING_CONTENT,
                ShortStoryStage.QUALITY_CHECKING,
                ShortStoryStage.COHERENCE_REVIEWING,
                ShortStoryStage.GENERATING_TITLES,
                ShortStoryStage.AWAITING_TITLE_SELECTION,
                ShortStoryStage.ASSEMBLING_OUTPUT,
                ShortStoryStage.COMPLETED,
            ]
        )
        current_stage = self.state["state"]
        self.state["chapters"] = self._normalize_written_chapters(chapters)

        if current_stage != ShortStoryStage.WRITING_CONTENT.value:
            self.state["quality_report"] = ""
            self.state["coherence_report"] = ""
            self.state["title_candidates"] = []
            self.state["selected_title"] = ""
            self.state["selected_title_index"] = None
            self.state["story_tags"] = self._normalize_story_tags(
                {"main_category": self.state.get("category", "其他")}
            )
            self.state["final_output"] = ""
            self.state["manual_intervention_required"] = False
            self.state["retry_counts"]["quality_check"] = 0
            self.state["retry_counts"]["coherence_review"] = 0

        expected_numbers = set(range(1, int(self.state.get("planned_chapters", 0)) + 1))
        current_numbers = {int(item.get("chapter_number", 0)) for item in self.state["chapters"]}
        if expected_numbers and expected_numbers.issubset(current_numbers):
            self.state["state"] = ShortStoryStage.QUALITY_CHECKING.value
        else:
            self.state["state"] = ShortStoryStage.WRITING_CONTENT.value

    def register_title_candidates(self, candidates: Sequence[Any]) -> None:
        self._assert_state([ShortStoryStage.GENERATING_TITLES])
        normalized = self._normalize_title_candidates(candidates)
        self.state["title_candidates"] = normalized
        self.state["state"] = ShortStoryStage.AWAITING_TITLE_SELECTION.value

    def select_title(self, selection: int) -> None:
        self._assert_state([ShortStoryStage.AWAITING_TITLE_SELECTION])
        selected = self._select_by_one_based_index(self.state["title_candidates"], selection, "书名")
        self.state["selected_title"] = selected["title"]
        self.state["selected_title_index"] = selection
        self.state["state"] = ShortStoryStage.ASSEMBLING_OUTPUT.value

    def record_story_tags(self, story_tags: Dict[str, Any]) -> None:
        self._assert_state([ShortStoryStage.ASSEMBLING_OUTPUT, ShortStoryStage.COMPLETED])
        normalized = self._normalize_story_tags(story_tags, self.state.get("category") or "其他")
        self.state["story_tags"] = normalized
        self.state["category"] = normalized["main_category"]
        self.state["tone"] = normalized["main_category"]

    def assemble_output(self) -> str:
        self._assert_state([ShortStoryStage.ASSEMBLING_OUTPUT, ShortStoryStage.COMPLETED])
        if not self.state.get("selected_title"):
            raise ValueError("尚未选择书名")
        if not self.state.get("selected_synopsis"):
            raise ValueError("尚未选择导语")
        if not self.state.get("chapters"):
            raise ValueError("尚无正文内容可组装")

        title = self.state["selected_title"]
        keywords_line = " | ".join(self.state.get("keywords", []))
        story_tags = self._normalize_story_tags(self.state.get("story_tags", {}), self.state.get("category") or "其他")
        main_category = story_tags.get("main_category") or self.state.get("category") or "其他"
        tag_line = " | ".join(story_tags.get("all_tags", []))
        synopsis = self.state["selected_synopsis"]
        chapter_blocks = []
        for chapter in self.state["chapters"]:
            chapter_blocks.append(
                f"### {_format_chapter_heading(int(chapter['chapter_number']), str(chapter.get('title') or '').strip())}\n{chapter['content']}"
            )

        final_output = (
            f"# 《{title}》\n"
            f"**主分类**：{main_category}\n"
            f"**内容标签**：{tag_line or '待生成'}\n"
            f"**词条标签**：{keywords_line}\n\n"
            f"---\n\n"
            f"## 导语\n{synopsis}\n\n"
            f"---\n\n"
            f"## 正文\n"
            f"{chr(10).join(chapter_blocks)}\n\n"
            f"---\n\n"
            f"（全文完）"
        )
        self.state["final_output"] = final_output
        self.state["state"] = ShortStoryStage.COMPLETED.value
        return final_output

    def _normalize_state(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = {
            "version": self.STATE_VERSION,
            "state": ShortStoryStage.AWAITING_KEYWORDS.value,
            "raw_input": "",
            "legacy_keywords": [],
            "input_analysis": {},
            "input_confidence": 0.0,
            "detected_material_types": [],
            "derived_keywords": [],
            "fusion_candidates": [],
            "selected_fusion": {},
            "selected_fusion_index": None,
            "keywords": [],
            "target_total_words": 5000,
            "custom_chapter_word_target": None,
            "planned_chapters": 6,
            "min_chapters": 6,
            "chapter_count_requirement": "",
            "target_words_upper": 5000,
            "chapter_word_target": 800,
            "chapter_word_min": 700,
            "chapter_word_max": 900,
            "category": "其他",
            "tone": "其他",
            "warnings": [],
            "synopsis_candidates": [],
            "selected_synopsis": "",
            "selected_synopsis_index": None,
            "outline_text": "",
            "outline_feedback": "",
            "outline_confirmed": False,
            "repair_placeholder_numbers": [],
            "character_table": "",
            "timeline": "",
            "chapter_blueprints": [],
            "chapters": [],
            "quality_report": "",
            "coherence_report": "",
            "title_candidates": [],
            "selected_title": "",
            "selected_title_index": None,
            "story_tags": {
                "main_category": "其他",
                "plot_tags": [],
                "role_tags": [],
                "emotion_tags": [],
                "background_tags": [],
                "all_tags": [],
            },
            "final_output": "",
            "manual_intervention_required": False,
            "retry_counts": {
                "quality_check": 0,
                "coherence_review": 0,
            },
        }
        if not isinstance(payload, dict):
            return base

        merged = copy.deepcopy(base)
        merged.update(payload)
        retry_counts = merged.get("retry_counts", {})
        if not isinstance(retry_counts, dict):
            retry_counts = {}
        merged["retry_counts"] = {
            "quality_check": int(retry_counts.get("quality_check", 0) or 0),
            "coherence_review": int(retry_counts.get("coherence_review", 0) or 0),
        }
        merged["raw_input"] = str(merged.get("raw_input") or "").strip()
        merged["legacy_keywords"] = self._normalize_keywords(merged.get("legacy_keywords", []))
        merged["derived_keywords"] = self._normalize_keywords(merged.get("derived_keywords", []))
        merged["keywords"] = self._normalize_keywords(merged.get("keywords", [])) or merged["derived_keywords"] or merged["legacy_keywords"]
        custom_chapter_word_target = merged.get("custom_chapter_word_target")
        if custom_chapter_word_target in ("", 0):
            custom_chapter_word_target = None
        plan = _resolve_chapter_plan(
            int(merged.get("target_total_words") or base["target_total_words"]),
            int(custom_chapter_word_target) if custom_chapter_word_target is not None else None,
        )
        merged["target_total_words"] = int(plan["target_words"])
        merged["custom_chapter_word_target"] = int(custom_chapter_word_target) if custom_chapter_word_target is not None else None
        has_existing_outline = bool(merged.get("chapter_blueprints")) or bool(merged.get("chapters"))
        merged["planned_chapters"] = int(merged.get("planned_chapters") or 0) if has_existing_outline else int(plan["planned_chapters"])
        if merged["planned_chapters"] <= 0:
            merged["planned_chapters"] = int(plan["planned_chapters"])
        merged["min_chapters"] = int(plan["planned_chapters"])
        merged["chapter_count_requirement"] = str(plan["chapter_count_requirement"])
        merged["target_words_upper"] = int(plan["target_words_upper"])
        merged["chapter_word_target"] = int(plan["chapter_word_target"])
        merged["chapter_word_min"] = int(plan["chapter_word_min"])
        merged["chapter_word_max"] = int(plan["chapter_word_max"])
        category = _normalize_main_category(merged.get("category") or merged.get("tone") or "其他")
        merged["category"] = category
        merged["tone"] = category
        merged["synopsis_candidates"] = self._normalize_named_candidates(
            merged.get("synopsis_candidates", []),
            expected=None,
            kind="导语",
        )
        merged["fusion_candidates"] = self._normalize_fusion_candidates(merged.get("fusion_candidates", []), expected=None)
        merged["selected_fusion"] = self._normalize_selected_fusion(merged.get("selected_fusion", {}))
        merged["chapter_blueprints"] = self._normalize_chapter_blueprints(merged.get("chapter_blueprints"))
        merged["chapters"] = self._normalize_written_chapters(merged.get("chapters"))
        merged["title_candidates"] = self._normalize_title_candidates(merged.get("title_candidates", []), strict=False)
        merged["story_tags"] = self._normalize_story_tags(merged.get("story_tags", {}), merged["category"])
        input_analysis = merged.get("input_analysis", {})
        if not isinstance(input_analysis, dict):
            input_analysis = {}
        merged["input_analysis"] = {
            "summary": str(input_analysis.get("summary") or "").strip(),
            "genre_hint": str(input_analysis.get("genre_hint") or "").strip(),
            "borrowed_highlights": [str(item).strip() for item in input_analysis.get("borrowed_highlights", []) if str(item).strip()],
            "constraints": [str(item).strip() for item in input_analysis.get("constraints", []) if str(item).strip()],
            "warnings": [str(item).strip() for item in input_analysis.get("warnings", []) if str(item).strip()],
        }
        material_types = merged.get("detected_material_types", [])
        if not isinstance(material_types, list):
            material_types = []
        merged["detected_material_types"] = [str(item).strip() for item in material_types if str(item).strip()]
        try:
            merged["input_confidence"] = max(0.0, min(1.0, float(merged.get("input_confidence", 0.0) or 0.0)))
        except (TypeError, ValueError):
            merged["input_confidence"] = 0.0
        repair_placeholder_numbers = merged.get("repair_placeholder_numbers", [])
        if not isinstance(repair_placeholder_numbers, list):
            repair_placeholder_numbers = []
        merged["repair_placeholder_numbers"] = sorted(
            {
                int(item)
                for item in repair_placeholder_numbers
                if str(item).strip().isdigit() and int(item) > 0
            }
        )
        return merged

    def _assert_state(self, expected: Iterable[ShortStoryStage]) -> None:
        allowed = {item.value for item in expected}
        current = str(self.state.get("state"))
        if current not in allowed:
            readable = ", ".join(sorted(allowed))
            raise ValueError(f"当前状态为 {current}，不能执行该操作。允许状态：{readable}")

    @staticmethod
    def _normalize_keywords(keywords: Sequence[str] | str) -> List[str]:
        if isinstance(keywords, str):
            raw_items = re.split(r"[\n,，、;；|/]+", keywords)
        else:
            raw_items = [str(item) for item in keywords]

        normalized: List[str] = []
        seen = set()
        for item in raw_items:
            cleaned = str(item or "").strip()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)
        return normalized

    @staticmethod
    def _normalize_fusion_candidates(candidates: Sequence[Any], expected: Optional[int]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(candidates or [], start=1):
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or f"方案{index}").strip() or f"方案{index}"
                route = str(item.get("route") or item.get("style") or "").strip()
                hook = str(item.get("hook") or "").strip()
                borrowed_structure = str(item.get("borrowed_structure") or "").strip()
                refresh_plan = str(item.get("refresh_plan") or "").strip()
                premise = str(item.get("premise") or item.get("content") or item.get("summary") or "").strip()
            else:
                title = f"方案{index}"
                route = ""
                hook = ""
                borrowed_structure = ""
                refresh_plan = ""
                premise = str(item or "").strip()
            if not premise:
                continue
            normalized.append(
                {
                    "index": index,
                    "title": title,
                    "route": route,
                    "hook": hook,
                    "borrowed_structure": borrowed_structure,
                    "refresh_plan": refresh_plan,
                    "premise": premise,
                    "content": premise,
                }
            )
        if expected is not None and len(normalized) != expected:
            raise ValueError(f"创意方案数量必须为 {expected} 条")
        return normalized

    @staticmethod
    def _normalize_selected_fusion(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        normalized = ShortStoryWorkflowStateMachine._normalize_fusion_candidates([payload], expected=None)
        return normalized[0] if normalized else {}

    @staticmethod
    def _normalize_named_candidates(
        candidates: Sequence[Any],
        expected: Optional[int],
        kind: str,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(candidates or [], start=1):
            if isinstance(item, dict):
                content = str(item.get("content") or item.get("text") or "").strip()
                style = str(item.get("style") or item.get("type") or "").strip()
            else:
                content = str(item or "").strip()
                style = ""
            if not content:
                continue
            normalized.append({"index": index, "style": style, "content": content, "kind": kind})
        if expected is not None and len(normalized) != expected:
            raise ValueError(f"{kind}候选数量必须为 {expected} 条")
        return normalized

    @staticmethod
    def _normalize_title_candidates(candidates: Sequence[Any], strict: bool = True) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(candidates or [], start=1):
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or "").strip()
                category = str(item.get("category") or item.get("type") or "").strip()
                explanation = str(item.get("explanation") or item.get("description") or "").strip()
            else:
                title = str(item or "").strip()
                category = ""
                explanation = ""
            if not title:
                continue
            normalized.append(
                {
                    "index": index,
                    "title": title.replace("《", "").replace("》", ""),
                    "category": category,
                    "explanation": explanation,
                }
            )
        if strict and len(normalized) != 5:
            raise ValueError("书名候选数量必须为 5 个")
        return normalized

    @staticmethod
    def _normalize_story_tags(story_tags: Optional[Dict[str, Any]], default_category: str = "其他") -> Dict[str, Any]:
        payload = story_tags if isinstance(story_tags, dict) else {}
        main_category = _normalize_main_category(payload.get("main_category") or default_category, default_category)

        normalized = {"main_category": main_category}
        all_tags: List[str] = []
        seen = set()
        for group_name, allowed in SHORT_STORY_TAG_GROUPS.items():
            values = payload.get(group_name, [])
            if not isinstance(values, list):
                values = []
            group_items: List[str] = []
            for value in values:
                tag = str(value or "").strip()
                if not tag or tag not in allowed or tag in seen:
                    continue
                group_items.append(tag)
                all_tags.append(tag)
                seen.add(tag)
                if len(all_tags) >= 7:
                    break
            normalized[group_name] = group_items
            if len(all_tags) >= 7:
                break
        normalized["all_tags"] = all_tags
        return normalized

    @staticmethod
    def _normalize_chapter_blueprints(chapter_blueprints: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen_numbers = set()
        for index, item in enumerate(chapter_blueprints or [], start=1):
            if not isinstance(item, dict):
                continue
            chapter_number = int(item.get("chapter_number") or item.get("number") or index)
            if chapter_number in seen_numbers:
                continue
            normalized.append(
                {
                    "chapter_number": chapter_number,
                    "title": str(item.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章",
                    "summary": str(item.get("summary") or "").strip(),
                    "characters": str(item.get("characters") or item.get("cast") or "").strip(),
                    "core_event": str(item.get("core_event") or item.get("event") or "").strip(),
                    "narrative_function": str(item.get("narrative_function") or item.get("purpose") or "").strip(),
                    "emotion_point": str(item.get("emotion_point") or "").strip(),
                }
            )
            seen_numbers.add(chapter_number)
        normalized.sort(key=lambda item: item["chapter_number"])
        return normalized

    @classmethod
    def _normalize_written_chapters(cls, chapters: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(chapters or [], start=1):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            chapter_number = int(item.get("chapter_number") or item.get("number") or index)
            title = str(item.get("title") or f"第{chapter_number}章").strip() or f"第{chapter_number}章"
            normalized.append(
                {
                    "chapter_number": chapter_number,
                    "title": title,
                    "content": content,
                    "word_count": int(item.get("word_count") or cls._count_story_chars(content)),
                }
            )
        normalized.sort(key=lambda item: item["chapter_number"])
        return normalized

    @staticmethod
    def _select_by_one_based_index(candidates: Sequence[Dict[str, Any]], selection: int, label: str) -> Dict[str, Any]:
        index = int(selection or 0)
        if index < 1 or index > len(candidates):
            raise ValueError(f"{label}选择编号必须在 1 到 {len(candidates)} 之间")
        return dict(candidates[index - 1])

    @staticmethod
    def _count_story_chars(text: str) -> int:
        return len(re.sub(r"\s+", "", text or ""))


class ShortStoryCreatorService:
    """短篇创作工作流服务。"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "success": True,
            "module": "short_story",
            "version": ShortStoryWorkflowStateMachine.STATE_VERSION,
            "states": [item.value for item in ShortStoryStage],
            "steps": [asdict(item) for item in _step_policies()],
            "interaction_points": ["创意方案三选一", "导语五选一", "大纲确认或调整", "书名五选一"],
            "target_total_words_range": [3000, 50000],
            "chapter_word_target_range": [500, 3000],
            "chapter_word_count_range": [400, 3100],
            "chapter_plan_rules": [
                {
                    "mode": "dynamic_by_total_and_chapter_words",
                    "description": "根据目标总字数和每章目标字数智能推导计划章节数，允许单章浮动，但整体规划不能明显低于目标字数。",
                    "chapter_word_tolerance": [-100, 100],
                    "total_words_must_not_be_below_target": True,
                },
            ],
            "main_categories": SHORT_STORY_MAIN_CATEGORIES,
            "custom_main_category_supported": True,
            "tag_groups": SHORT_STORY_TAG_GROUPS,
        }

    def start_workflow(
        self,
        keywords: Sequence[str] | str | None = None,
        target_total_words: int = 5000,
        chapter_word_target: Optional[int] = None,
        category: str = "其他",
        source_input: str = "",
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine()
        machine.start(
            keywords=keywords,
            target_total_words=target_total_words,
            chapter_word_target=chapter_word_target,
            category=category,
            source_input=source_input,
        )
        return {
            "success": True,
            "data": {
                "workflow": machine.snapshot(),
                "next_step": "analyze_input",
                "user_message": "请先识别输入素材，再生成 3 个创意方案供用户选择。",
            },
        }

    def build_input_analysis_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.ANALYZING_SOURCE_INPUT])
        state = machine.snapshot()
        prompt = INPUT_ANALYSIS_PROMPT_TEMPLATE.format(
            source_input=state.get("raw_input") or self._format_keywords(state.get("keywords", [])) or "待补充",
            category=state.get("category") or "其他",
        )
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "user_message": "系统会先识别素材类型与重点，再进入创意方案生成。",
            },
        }

    def record_input_analysis(self, workflow: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_input_analysis(analysis)
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": "generate_fusion_options"}}

    def build_fusion_options_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.GENERATING_FUSION_OPTIONS])
        state = machine.snapshot()
        analysis = state.get("input_analysis", {}) if isinstance(state.get("input_analysis"), dict) else {}
        prompt = FUSION_OPTIONS_PROMPT_TEMPLATE.format(
            source_input=state.get("raw_input") or self._format_keywords(state.get("keywords", [])) or "待补充",
            analysis_summary=analysis.get("summary") or "待补充",
            keywords=self._format_keywords(state.get("keywords", [])) or "待补充",
            category=state.get("category") or "其他",
        )
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "user_message": "请从 3 个不同故事方向中选择最满意的一版。",
            },
        }

    def register_fusion_candidates(self, workflow: Dict[str, Any], candidates: Sequence[Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.register_fusion_candidates(candidates)
        return {"success": True, "data": {"workflow": machine.snapshot(), "candidate_count": 3}}

    def select_fusion(self, workflow: Dict[str, Any], selection: int) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.select_fusion(selection)
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": "generate_synopsis"}}

    def get_workflow_status(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        state = machine.snapshot()
        return {
            "success": True,
            "data": {
                "state": state["state"],
                "planned_chapters": state["planned_chapters"],
                "written_chapters": len(state["chapters"]),
                "manual_intervention_required": state["manual_intervention_required"],
                "warnings": state["warnings"],
            },
        }

    def build_synopsis_prompt(self, workflow: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.GENERATING_SYNOPSIS])
        state = machine.snapshot()
        prompt = SYNOPSIS_PROMPT_TEMPLATE.format(
            keywords=self._format_keywords(state["keywords"]),
            category=state.get("category") or "其他",
        )
        prompt += f"\n\n【统一输入原文】\n{state.get('raw_input') or '待补充'}"
        if state.get("input_analysis"):
            prompt += f"\n\n【素材识别摘要】\n{state['input_analysis'].get('summary') or '待补充'}"
        if state.get("selected_fusion"):
            prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
        if (feedback or "").strip():
            prompt += f"\n\n【用户对导语的新要求】\n{feedback.strip()}"
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "user_message": "请从以上 5 条导语中选择最满意的一条（回复编号 1-5），或提出修改意见。",
            },
        }

    def register_synopsis_candidates(self, workflow: Dict[str, Any], candidates: Sequence[Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.register_synopsis_candidates(candidates)
        return {"success": True, "data": {"workflow": machine.snapshot(), "candidate_count": 5}}

    def select_synopsis(self, workflow: Dict[str, Any], selection: int) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.select_synopsis(selection)
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": "generate_outline"}}

    def build_outline_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.GENERATING_OUTLINE])
        state = machine.snapshot()
        prompt = OUTLINE_PROMPT_TEMPLATE.format(
            keywords=self._format_keywords(state["keywords"]),
            category=state.get("category") or "其他",
            selected_synopsis=state["selected_synopsis"],
            chapter_count_requirement=state.get("chapter_count_requirement") or _resolve_chapter_plan(
                int(state.get("target_total_words") or 5000),
                int(state.get("custom_chapter_word_target")) if state.get("custom_chapter_word_target") not in (None, "", 0) else None,
            )["chapter_count_requirement"],
            planned_chapters=int(state.get("planned_chapters") or 0),
            target_total_words=int(state.get("target_total_words") or 5000),
            chapter_word_target=state.get("chapter_word_target", 800),
            chapter_word_min=state.get("chapter_word_min", 700),
            chapter_word_max=state.get("chapter_word_max", 900),
        )
        if state.get("selected_fusion"):
            prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
        if state.get("outline_feedback"):
            prompt += f"\n\n【上一版调整意见】\n{state['outline_feedback']}"
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "user_message": "请确认这份大纲，或给出需要调整的方向。",
            },
        }

    def record_outline(
        self,
        workflow: Dict[str, Any],
        outline_text: str,
        character_table: str = "",
        timeline: str = "",
        chapter_blueprints: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_outline(
            outline_text=outline_text,
            character_table=character_table,
            timeline=timeline,
            chapter_blueprints=chapter_blueprints,
        )
        return {"success": True, "data": {"workflow": machine.snapshot()}}

    def confirm_outline(self, workflow: Dict[str, Any], approved: bool = True, feedback: str = "") -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        if approved:
            parsed = parse_outline_payload(machine.state.get("outline_text", ""), planned_chapters=0)
            if parsed.get("chapter_blueprints"):
                machine.state["outline_text"] = parsed["outline_text"]
                machine.state["chapter_blueprints"] = machine._normalize_chapter_blueprints(parsed["chapter_blueprints"])
                if parsed.get("character_table") and parsed["character_table"] != "待补充":
                    machine.state["character_table"] = parsed["character_table"]
                if parsed.get("timeline") and parsed["timeline"] != "待补充":
                    machine.state["timeline"] = parsed["timeline"]
            machine._assert_repair_placeholder_blueprints_resolved()
            planned = int(machine.state.get("planned_chapters") or 0)
            if machine.state.get("repair_placeholder_numbers"):
                planned = max(planned, int(machine.state.get("min_chapters") or 0))
            actual = len(machine.state.get("chapter_blueprints") or [])
            if planned > 0 and actual != planned:
                raise ValueError(f"当前大纲为 {actual} 章，但按目标字数规划应为 {planned} 章，请调整后再确认。")
            if planned > 0:
                machine.state["planned_chapters"] = planned
        machine.confirm_outline(approved=approved, feedback=feedback)
        next_step = "write_content" if approved else "generate_outline"
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": next_step}}

    def rollback_placeholder_blueprints(self, workflow: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.rollback_placeholder_blueprints(feedback=feedback)
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": "revise_outline"}}

    def extract_simple_quality_fixes(self, workflow: Dict[str, Any], report: str) -> List[Dict[str, Any]]:
        state = ShortStoryWorkflowStateMachine(workflow).snapshot()
        chapters_by_number = {
            int(item.get("chapter_number") or 0): item
            for item in self.normalize_chapters_payload(state.get("chapters", []))
        }
        known_names = self._extract_known_character_names(state)
        fixes: List[Dict[str, Any]] = []

        for raw_line in str(report or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("##") or line.startswith("✅") or "无需修改" in line:
                continue
            chapter_match = re.match(r"^第\s*(\d+)\s*章[:：]\s*(.+)$", line)
            if not chapter_match:
                continue
            chapter_number = int(chapter_match.group(1))
            if chapter_number not in chapters_by_number:
                continue
            issue_text = chapter_match.group(2).strip()
            fix = self._extract_simple_quality_fix_from_line(issue_text, chapter_number, known_names)
            if fix:
                fixes.append(fix)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in fixes:
            key = (item["chapter_number"], item["from_name"], item["to_name"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def apply_simple_quality_fixes(
        self,
        workflow: Dict[str, Any],
        report: str,
        chapters: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        state = machine.snapshot()
        chapter_payload = self.normalize_chapters_payload(chapters) if chapters else self.normalize_chapters_payload(state.get("chapters", []))
        state["chapters"] = chapter_payload
        fixes = self.extract_simple_quality_fixes(state, report)
        if not fixes:
            raise ValueError("当前质检报告中没有可自动修复的简单问题。")

        chapter_map = {int(item.get("chapter_number") or 0): dict(item) for item in chapter_payload}
        applied_fixes: List[Dict[str, Any]] = []
        for fix in fixes:
            chapter_number = int(fix["chapter_number"])
            chapter = chapter_map.get(chapter_number)
            if not chapter:
                continue
            content = str(chapter.get("content") or "")
            wrong_name = str(fix["from_name"] or "").strip()
            correct_name = str(fix["to_name"] or "").strip()
            if not wrong_name or not correct_name or wrong_name == correct_name or wrong_name not in content:
                continue
            replacements = content.count(wrong_name)
            chapter["content"] = content.replace(wrong_name, correct_name)
            applied = dict(fix)
            applied["replacement_count"] = replacements
            applied_fixes.append(applied)

        if not applied_fixes:
            raise ValueError("检测到了可修复规则，但正文中未找到对应可替换内容。")

        revised_chapters = sorted(chapter_map.values(), key=lambda item: int(item.get("chapter_number", 0)))
        machine.replace_chapters(revised_chapters)
        return {
            "success": True,
            "data": {
                "workflow": machine.snapshot(),
                "revised_chapters": revised_chapters,
                "applied_fixes": applied_fixes,
                "fixed_count": len(applied_fixes),
                "replacement_count": sum(int(item.get("replacement_count", 0)) for item in applied_fixes),
                "next_step": "quality_check",
            },
        }

    def build_chapter_prompt(
        self,
        workflow: Dict[str, Any],
        chapter_number: int,
        previous_chapters_text: str = "无",
        chapter_title: str = "",
        current_chapter_outline: str = "",
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state(
            [
                ShortStoryStage.WRITING_CONTENT,
                ShortStoryStage.QUALITY_CHECKING,
                ShortStoryStage.COHERENCE_REVIEWING,
                ShortStoryStage.GENERATING_TITLES,
                ShortStoryStage.AWAITING_TITLE_SELECTION,
                ShortStoryStage.ASSEMBLING_OUTPUT,
                ShortStoryStage.COMPLETED,
            ]
        )
        state = machine.snapshot()
        self._assert_chapter_has_valid_blueprint(state, chapter_number)
        blueprint = self._find_chapter_blueprint(state, chapter_number)
        title = (chapter_title or blueprint.get("title") or f"第{chapter_number}章").strip()
        chapter_heading = _format_chapter_heading(chapter_number, title)
        outline_lines = [
            f"摘要：{blueprint.get('summary', '').strip()}",
            f"出场角色：{blueprint.get('characters', '').strip()}",
            f"核心事件：{blueprint.get('core_event', '').strip()}",
            f"叙事功能：{blueprint.get('narrative_function', '').strip()}",
        ]
        # 添加情绪节点信息
        emotion_point = blueprint.get('emotion_point', '').strip()
        if emotion_point:
            outline_lines.append(f"情绪节点：{emotion_point}")
        
        resolved_outline = (current_chapter_outline or "\n".join([line for line in outline_lines if not line.endswith("：")])).strip() or "待补充"
        prompt = CHAPTER_PROMPT_TEMPLATE.format(
            keywords=self._format_keywords(state["keywords"]),
            category=state.get("category") or "其他",
            selected_synopsis=state["selected_synopsis"],
            character_table=state["character_table"] or "待补充",
            timeline=state["timeline"] or "待补充",
            full_outline=state["outline_text"] or "待补充",
            previous_chapters_text=(previous_chapters_text or "无").strip() or "无",
            chapter_word_target=state.get("chapter_word_target", 800),
            chapter_word_min=state.get("chapter_word_min", 700),
            chapter_word_max=state.get("chapter_word_max", 900),
            current_chapter_outline=resolved_outline,
        )
        if state.get("selected_fusion"):
            prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "chapter_number": chapter_number,
                "chapter_title": title,
                "chapter_heading": chapter_heading,
            },
        }

    def record_chapter(self, workflow: Dict[str, Any], chapter_number: int, title: str, content: str) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_chapter(chapter_number=chapter_number, title=title, content=content)
        snapshot = machine.snapshot()
        next_step = "quality_check" if snapshot["state"] == ShortStoryStage.QUALITY_CHECKING.value else "write_content"
        return {"success": True, "data": {"workflow": snapshot, "next_step": next_step}}

    def build_quality_check_prompt(self, workflow: Dict[str, Any], use_batch: bool = True, batch_size: int = 3) -> Dict[str, Any]:
        """构建质检提示词，支持分批处理"""
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.QUALITY_CHECKING])
        state = machine.snapshot()
        self._assert_full_chapter_set_ready(state, action_name="质量检查")
        self._assert_no_placeholder_blueprints(state, action_name="质量检查")
        
        chapters = state["chapters"]
        total_chapters = len(chapters)
        
        # 如果章节数少于等于batch_size，或者不使用分批，则使用完整质检
        if not use_batch or total_chapters <= batch_size:
            prompt = QUALITY_CHECK_PROMPT_TEMPLATE.format(
                character_table=state["character_table"] or "待补充",
                timeline=state["timeline"] or "待补充",
                full_outline=state["outline_text"] or "待补充",
                all_chapters_text=self.render_chapters(chapters),
                chapter_word_min=state.get("chapter_word_min", 700),
                chapter_word_max=state.get("chapter_word_max", 900),
            )
            return {
                "success": True,
                "data": {
                    "workflow": state,
                    "prompt": prompt,
                    "use_batch": False,
                    "total_batches": 1,
                }
            }
        
        # 分批处理：生成多个批次的提示词
        batches = []
        for i in range(0, total_chapters, batch_size):
            batch_chapters = chapters[i:i + batch_size]
            batch_start = batch_chapters[0]["chapter_number"]
            batch_end = batch_chapters[-1]["chapter_number"]
            
            batch_prompt = BATCH_QUALITY_CHECK_PROMPT_TEMPLATE.format(
                character_table=state["character_table"] or "待补充",
                timeline=state["timeline"] or "待补充",
                full_outline=state["outline_text"] or "待补充",
                batch_chapters_text=self.render_chapters(batch_chapters),
                batch_start=batch_start,
                batch_end=batch_end,
                chapter_word_min=state.get("chapter_word_min", 700),
                chapter_word_max=state.get("chapter_word_max", 900),
            )
            
            batches.append({
                "batch_index": len(batches),
                "batch_start": batch_start,
                "batch_end": batch_end,
                "prompt": batch_prompt,
                "chapter_count": len(batch_chapters),
            })
        
        return {
            "success": True,
            "data": {
                "workflow": state,
                "use_batch": True,
                "batch_size": batch_size,
                "total_batches": len(batches),
                "batches": batches,
            }
        }

    def record_quality_check(
        self,
        workflow: Dict[str, Any],
        report: str,
        passed: bool,
        revised_chapters: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_quality_check(report=report, passed=passed, revised_chapters=revised_chapters)
        snapshot = machine.snapshot()
        next_step = "coherence_review" if passed else "quality_check"
        return {"success": True, "data": {"workflow": snapshot, "next_step": next_step}}

    def build_coherence_review_prompt(self, workflow: Dict[str, Any], use_batch: bool = True, batch_size: int = 3) -> Dict[str, Any]:
        """构建复审提示词，支持分批处理"""
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.COHERENCE_REVIEWING])
        state = machine.snapshot()
        self._assert_full_chapter_set_ready(state, action_name="通篇复审")
        self._assert_no_placeholder_blueprints(state, action_name="通篇复审")
        
        chapters = state["chapters"]
        total_chapters = len(chapters)
        
        # 如果章节数少于等于batch_size，或者不使用分批，则使用完整复审
        if not use_batch or total_chapters <= batch_size:
            prompt = COHERENCE_REVIEW_PROMPT_TEMPLATE.format(
                keywords=self._format_keywords(state["keywords"]),
                category=state.get("category") or "其他",
                selected_synopsis=state["selected_synopsis"],
                revised_full_text=self.render_chapters(chapters),
            )
            if state.get("selected_fusion"):
                prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
            return {
                "success": True,
                "data": {
                    "workflow": state,
                    "prompt": prompt,
                    "use_batch": False,
                    "total_batches": 1,
                }
            }
        
        # 分批处理：生成多个批次的提示词
        batches = []
        for i in range(0, total_chapters, batch_size):
            batch_chapters = chapters[i:i + batch_size]
            batch_start = batch_chapters[0]["chapter_number"]
            batch_end = batch_chapters[-1]["chapter_number"]
            
            batch_prompt = BATCH_COHERENCE_REVIEW_PROMPT_TEMPLATE.format(
                keywords=self._format_keywords(state["keywords"]),
                category=state.get("category") or "其他",
                selected_synopsis=state["selected_synopsis"],
                batch_chapters_text=self.render_chapters(batch_chapters),
                batch_start=batch_start,
                batch_end=batch_end,
            )
            if state.get("selected_fusion"):
                batch_prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
            
            batches.append({
                "batch_index": len(batches),
                "batch_start": batch_start,
                "batch_end": batch_end,
                "prompt": batch_prompt,
                "chapter_count": len(batch_chapters),
            })
        
        return {
            "success": True,
            "data": {
                "workflow": state,
                "use_batch": True,
                "batch_size": batch_size,
                "total_batches": len(batches),
                "batches": batches,
            }
        }

    def record_coherence_review(
        self,
        workflow: Dict[str, Any],
        report: str,
        passed: bool,
        final_chapters: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_coherence_review(report=report, passed=passed, final_chapters=final_chapters)
        snapshot = machine.snapshot()
        next_step = "generate_titles" if passed else "quality_check"
        return {"success": True, "data": {"workflow": snapshot, "next_step": next_step}}

    def build_title_prompt(self, workflow: Dict[str, Any], body_excerpt: str = "", feedback: str = "") -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.GENERATING_TITLES])
        state = machine.snapshot()
        excerpt = (body_excerpt or self.build_excerpt(state["chapters"])).strip() or "待补充"
        prompt = TITLE_PROMPT_TEMPLATE.format(
            keywords=self._format_keywords(state["keywords"]),
            category=state.get("category") or "其他",
            selected_synopsis=state["selected_synopsis"],
            body_excerpt=excerpt,
        )
        if state.get("selected_fusion"):
            prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
        if (feedback or "").strip():
            prompt += f"\n\n【用户对书名的新要求】\n{feedback.strip()}"
        return {
            "success": True,
            "data": {
                "workflow": state,
                "prompt": prompt,
                "user_message": "请选择您最喜欢的书名（回复编号 1-5），或提出新的修改方向。",
            },
        }

    def register_title_candidates(self, workflow: Dict[str, Any], candidates: Sequence[Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.register_title_candidates(candidates)
        return {"success": True, "data": {"workflow": machine.snapshot(), "candidate_count": 5}}

    def select_title(self, workflow: Dict[str, Any], selection: int) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.select_title(selection)
        return {"success": True, "data": {"workflow": machine.snapshot(), "next_step": "assemble_output"}}

    def assemble_output(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        final_output = machine.assemble_output()
        snapshot = machine.snapshot()
        return {
            "success": True,
            "data": {
                "workflow": snapshot,
                "final_work": final_output,
                "title": snapshot["selected_title"],
                "story_tags": snapshot.get("story_tags", {}),
            },
        }

    def build_export_payload(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        state = machine.snapshot()
        title = str(state.get("selected_title") or "").strip()
        synopsis = str(state.get("selected_synopsis") or "").strip()
        chapters = self.normalize_chapters_payload(state.get("chapters", []))
        if not title:
            raise ValueError("尚未生成书名，暂时无法导出。")
        if not synopsis:
            raise ValueError("尚未选择导语，暂时无法导出。")
        if not chapters:
            raise ValueError("尚无正文内容可导出。")

        story_tags = ShortStoryWorkflowStateMachine._normalize_story_tags(
            state.get("story_tags", {}),
            str(state.get("category") or state.get("tone") or "其他").strip() or "其他",
        )
        return {
            "success": True,
            "data": {
                "title": title,
                "main_category": story_tags.get("main_category") or str(state.get("category") or "其他").strip() or "其他",
                "tags": list(story_tags.get("all_tags", [])),
                "keywords": list(state.get("keywords", [])),
                "synopsis": synopsis,
                "chapters": chapters,
                "final_output": str(state.get("final_output") or "").strip(),
            },
        }

    @staticmethod
    def render_export_markdown(payload: Dict[str, Any]) -> str:
        return ShortStoryCreatorService.render_export_text(payload)

    @staticmethod
    def render_export_text(payload: Dict[str, Any]) -> str:
        return "\n".join(ShortStoryCreatorService.build_clean_export_lines(payload)).strip() + "\n"

    @staticmethod
    def build_clean_export_lines(payload: Dict[str, Any]) -> List[str]:
        raw_lines = _build_clean_export_lines_from_final_output(payload.get("final_output", ""))
        if raw_lines:
            return raw_lines

        title = _clean_export_title(payload.get("title", ""))
        main_category = payload.get("main_category") or "其他"
        tags = _clean_export_tag_list(main_category, payload.get("tags", []))
        synopsis = _clean_export_block(payload.get("synopsis", ""), strip_style_hint=True)
        chapters = payload.get("chapters", [])

        lines: List[str] = []
        if title:
            lines.append(title)
        if tags:
            lines.append(f"标签：{'、'.join(tags)}")
        if synopsis:
            lines.append(f"导语：{synopsis}")
        if lines and chapters:
            lines.append("")

        for chapter in chapters:
            chapter_number = int(chapter.get("chapter_number") or 0)
            lines.append(f"{chapter_number}.")
            chapter_body = _clean_export_block(chapter.get("content", ""), chapter_number=chapter_number)
            if chapter_body:
                lines.extend(chapter_body.splitlines())
            lines.append("")

        while lines and not lines[-1]:
            lines.pop()
        return lines

    def build_story_tags_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine._assert_state([ShortStoryStage.ASSEMBLING_OUTPUT, ShortStoryStage.COMPLETED])
        state = machine.snapshot()
        prompt = TAG_SELECTION_PROMPT_TEMPLATE.format(
            main_categories="、".join(SHORT_STORY_MAIN_CATEGORIES),
            plot_tags="、".join(SHORT_STORY_TAG_GROUPS["plot_tags"]),
            role_tags="、".join(SHORT_STORY_TAG_GROUPS["role_tags"]),
            emotion_tags="、".join(SHORT_STORY_TAG_GROUPS["emotion_tags"]),
            background_tags="、".join(SHORT_STORY_TAG_GROUPS["background_tags"]),
            category=state.get("category") or "其他",
            keywords=self._format_keywords(state["keywords"]),
            title=state.get("selected_title") or "待定",
            selected_synopsis=state.get("selected_synopsis") or "待补充",
            full_text=self.render_chapters(state.get("chapters", [])),
        )
        if state.get("selected_fusion"):
            prompt += f"\n\n【已选创意方案】\n{self._format_selected_fusion(state)}"
        return {"success": True, "data": {"workflow": state, "prompt": prompt}}

    def record_story_tags(self, workflow: Dict[str, Any], story_tags: Dict[str, Any]) -> Dict[str, Any]:
        machine = ShortStoryWorkflowStateMachine(workflow)
        machine.record_story_tags(story_tags)
        return {"success": True, "data": {"workflow": machine.snapshot(), "story_tags": machine.snapshot().get("story_tags", {})}}

    @staticmethod
    def format_keywords(keywords: Sequence[str]) -> str:
        return "、".join(str(item).strip() for item in keywords if str(item).strip())

    @staticmethod
    def render_chapters(chapters: Sequence[Dict[str, Any]]) -> str:
        blocks = []
        for chapter in chapters:
            blocks.append(
                f"### {_format_chapter_heading(int(chapter['chapter_number']), str(chapter.get('title') or '').strip())}\n{chapter['content']}"
            )
        return "\n\n".join(blocks) or "待补充"

    @staticmethod
    def normalize_chapters_payload(chapters: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return ShortStoryWorkflowStateMachine._normalize_written_chapters(chapters)

    @classmethod
    def _assert_full_chapter_set_ready(cls, state: Dict[str, Any], action_name: str) -> None:
        planned = max(0, int(state.get("planned_chapters") or 0))
        chapters = cls.normalize_chapters_payload(state.get("chapters", []))
        chapter_numbers = {int(item.get("chapter_number") or 0) for item in chapters}
        expected_numbers = set(range(1, planned + 1))

        if planned <= 0:
            raise ValueError(f"尚未生成章节计划，暂时无法执行{action_name}。")

        if not expected_numbers.issubset(chapter_numbers):
            missing_numbers = sorted(expected_numbers - chapter_numbers)
            missing_label = "、".join(str(item) for item in missing_numbers)
            raise ValueError(f"当前共计划 {planned} 章，仍缺少第 {missing_label} 章，暂时无法执行{action_name}。")

    @classmethod
    def _find_placeholder_blueprint_numbers(cls, state: Dict[str, Any], chapter_numbers: Optional[Sequence[int]] = None) -> List[int]:
        blueprints = {
            int(item.get("chapter_number") or 0): item
            for item in _ensure_chapter_blueprint_count(state.get("chapter_blueprints", []), planned_chapters=0)
        }
        target_numbers = (
            [int(item) for item in chapter_numbers]
            if chapter_numbers is not None
            else [int(item.get("chapter_number") or 0) for item in cls.normalize_chapters_payload(state.get("chapters", []))]
        )
        placeholder_numbers: List[int] = []
        for chapter_number in target_numbers:
            blueprint = blueprints.get(int(chapter_number))
            if not blueprint:
                placeholder_numbers.append(int(chapter_number))
                continue
            if not any(
                str(blueprint.get(key) or "").strip()
                for key in ("summary", "characters", "core_event", "narrative_function", "emotion_point")
            ):
                placeholder_numbers.append(int(chapter_number))
        return sorted(set(placeholder_numbers))

    @classmethod
    def _assert_no_placeholder_blueprints(cls, state: Dict[str, Any], action_name: str) -> None:
        placeholder_numbers = cls._find_placeholder_blueprint_numbers(state)
        if placeholder_numbers:
            label = "、".join(str(item) for item in placeholder_numbers)
            raise ValueError(
                f"第 {label} 章缺少有效章节蓝图，暂时无法执行{action_name}。请先回到大纲阶段补全章节规划，再重写这些章节。"
            )

    @staticmethod
    def _extract_known_character_names(state: Dict[str, Any]) -> set[str]:
        names: set[str] = set()
        character_table = str(state.get("character_table") or "")
        for match in re.finditer(r"(?:^|[\n\r])\s*([\u4e00-\u9fa5]{2,4})\s*[:：]", character_table):
            names.add(match.group(1))

        for blueprint in _ensure_chapter_blueprint_count(state.get("chapter_blueprints", []), planned_chapters=0):
            raw_characters = str(blueprint.get("characters") or "")
            for candidate in re.split(r"[、，,/／|；;\s]+", raw_characters):
                cleaned = re.sub(r"（.*?）|\(.*?\)", "", candidate).strip()
                if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", cleaned):
                    names.add(cleaned)
        return names

    @classmethod
    def _extract_simple_quality_fix_from_line(
        cls,
        issue_text: str,
        chapter_number: int,
        known_names: set[str],
    ) -> Optional[Dict[str, Any]]:
        text = str(issue_text or "").strip()
        if not text:
            return None

        quoted_mismatch = re.search(r"[“\"](?P<wrong>[\u4e00-\u9fa5]{2,4})[”\"].*?角色表[“\"](?P<correct>[\u4e00-\u9fa5]{2,4})[”\"]", text)
        if quoted_mismatch:
            wrong_name = quoted_mismatch.group("wrong")
            correct_name = quoted_mismatch.group("correct")
            if wrong_name != correct_name:
                return {
                    "chapter_number": chapter_number,
                    "from_name": wrong_name,
                    "to_name": correct_name,
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        written_as_match = re.search(
            r"角色[“\"](?P<correct>[\u4e00-\u9fa5]{2,4})[”\"].*?被写作[“\"](?P<wrong>[\u4e00-\u9fa5]{2,4})[”\"]",
            text,
        )
        if written_as_match and written_as_match.group("correct") in known_names:
            correct_name = written_as_match.group("correct")
            wrong_name = written_as_match.group("wrong")
            if wrong_name != correct_name:
                return {
                    "chapter_number": chapter_number,
                    "from_name": wrong_name,
                    "to_name": correct_name,
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        typo_match = re.search(r"(?P<correct>[\u4e00-\u9fa5]{2,4})(?:名字|姓名)误写为[“\"]?(?P<wrong>[\u4e00-\u9fa5]{2,4})[”\"]?", text)
        if typo_match and typo_match.group("wrong") != typo_match.group("correct"):
            return {
                "chapter_number": chapter_number,
                "from_name": typo_match.group("wrong"),
                "to_name": typo_match.group("correct"),
                "reason": text,
                "fix_type": "name_consistency",
            }

        direct_name_mismatch = re.search(
            r"(?P<correct>[\u4e00-\u9fa5]{2,4})(?:名字|姓名)(?:前后不一致|出现矛盾)（(?P<other>[^）]+)）",
            text,
        )
        if direct_name_mismatch:
            correct_name = direct_name_mismatch.group("correct")
            other_candidates = [
                item.strip()
                for item in re.split(r"[/／、]", direct_name_mismatch.group("other"))
                if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", item.strip())
            ]
            wrong_names = [item for item in other_candidates if item != correct_name]
            if correct_name in known_names and len(wrong_names) == 1:
                return {
                    "chapter_number": chapter_number,
                    "from_name": wrong_names[0],
                    "to_name": correct_name,
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        subject_mismatch = re.search(r"(?P<subject>[^（()]{1,12})(?:名字|姓名)(?:前后不一致|出现矛盾)（(?P<other>[^）]+)）", text)
        if subject_mismatch:
            subject_text = subject_mismatch.group("subject")
            subject_known_names = [name for name in known_names if subject_text.strip() == name]
            if len(subject_known_names) == 1:
                correct_name = subject_known_names[0]
                other_candidates = [
                    item.strip()
                    for item in re.split(r"[/／、]", subject_mismatch.group("other"))
                    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", item.strip())
                ]
                wrong_names = [item for item in other_candidates if item != correct_name]
                if len(wrong_names) == 1:
                    return {
                        "chapter_number": chapter_number,
                        "from_name": wrong_names[0],
                        "to_name": correct_name,
                        "reason": text,
                        "fix_type": "name_consistency",
                    }

        change_to_match = re.search(
            r"从[“\"](?P<wrong>[\u4e00-\u9fa5]{2,4})[”\"].*?变更为[“\"](?P<correct>[\u4e00-\u9fa5]{2,4})[”\"]",
            text,
        )
        if change_to_match and change_to_match.group("correct") in known_names:
            correct_name = change_to_match.group("correct")
            wrong_name = change_to_match.group("wrong")
            if wrong_name != correct_name:
                return {
                    "chapter_number": chapter_number,
                    "from_name": wrong_name,
                    "to_name": correct_name,
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        mixed_names = re.search(r"（(?P<left>[\u4e00-\u9fa5]{2,4})[/／、](?P<right>[\u4e00-\u9fa5]{2,4})）", text)
        if mixed_names and ("名字" in text or "姓名" in text or "角色" in text):
            left = mixed_names.group("left")
            right = mixed_names.group("right")
            if left in known_names and right not in known_names:
                return {
                    "chapter_number": chapter_number,
                    "from_name": right,
                    "to_name": left,
                    "reason": text,
                    "fix_type": "name_consistency",
                }
            if right in known_names and left not in known_names:
                return {
                    "chapter_number": chapter_number,
                    "from_name": left,
                    "to_name": right,
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        quoted_names = []
        for item in re.findall(r"[“\"]([\u4e00-\u9fa5]{2,4})[”\"]", text):
            if item not in quoted_names:
                quoted_names.append(item)
        if "混用" in text and len(quoted_names) >= 2:
            known_candidates = [item for item in quoted_names if item in known_names]
            unknown_candidates = [item for item in quoted_names if item not in known_names]
            if len(known_candidates) == 1 and len(unknown_candidates) >= 1:
                return {
                    "chapter_number": chapter_number,
                    "from_name": unknown_candidates[0],
                    "to_name": known_candidates[0],
                    "reason": text,
                    "fix_type": "name_consistency",
                }

        return None


    @classmethod
    def _assert_chapter_has_valid_blueprint(cls, state: Dict[str, Any], chapter_number: int) -> None:
        placeholder_numbers = cls._find_placeholder_blueprint_numbers(state, [chapter_number])
        if placeholder_numbers:
            raise ValueError(
                f"第 {chapter_number} 章缺少有效章节蓝图，暂时不能生成本章。请先回到大纲阶段补全该章规划。"
            )

    @classmethod
    def build_excerpt(cls, chapters: Sequence[Dict[str, Any]]) -> str:
        if not chapters:
            return ""
        if len(chapters) == 1:
            return chapters[0]["content"][:300]
        excerpts = [chapters[0]["content"][:160], chapters[-1]["content"][:160]]
        if len(chapters) > 2:
            excerpts.insert(1, chapters[len(chapters) // 2]["content"][:160])
        return "\n...\n".join(item for item in excerpts if item)

    @staticmethod
    def _find_chapter_blueprint(state: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        for blueprint in state.get("chapter_blueprints", []):
            if int(blueprint.get("chapter_number", 0)) == int(chapter_number):
                return dict(blueprint)
        return {}

    def _format_keywords(self, keywords: Sequence[str]) -> str:
        return self.format_keywords(keywords)

    @staticmethod
    def _format_selected_fusion(state: Dict[str, Any]) -> str:
        fusion = state.get("selected_fusion", {}) if isinstance(state.get("selected_fusion"), dict) else {}
        if not fusion:
            return "待补充"
        lines = [
            f"标题：{fusion.get('title') or '待补充'}",
            f"路数：{fusion.get('route') or '待补充'}",
            f"钩子：{fusion.get('hook') or '待补充'}",
            f"借鉴骨架：{fusion.get('borrowed_structure') or '待补充'}",
            f"内容换新：{fusion.get('refresh_plan') or '待补充'}",
            f"故事梗概：{fusion.get('premise') or fusion.get('content') or '待补充'}",
        ]
        return "\n".join(lines)

    @staticmethod
    async def run_batch_quality_check_stream(
        batches: List[Dict[str, Any]],
        llm_call_func,
        on_batch_complete=None
    ) -> str:
        """
        分批执行质检，支持流式输出
        
        Args:
            batches: 批次列表，每个批次包含 prompt 等信息
            llm_call_func: LLM调用函数，应该返回 AsyncGenerator[str, None] 或 str
            on_batch_complete: 每批完成时的回调函数
            
        Returns:
            合并后的完整质检报告
        """
        all_reports = []
        
        for batch in batches:
            batch_index = batch["batch_index"]
            batch_start = batch["batch_start"]
            batch_end = batch["batch_end"]
            prompt = batch["prompt"]
            
            # 调用LLM（流式或非流式）
            result = await llm_call_func(prompt)
            
            # 处理流式响应
            if hasattr(result, '__aiter__'):
                chunks = []
                async for chunk in result:
                    chunks.append(chunk)
                batch_report = ''.join(chunks)
            else:
                batch_report = result
            
            all_reports.append(f"## 批次 {batch_index + 1}（第{batch_start}-{batch_end}章）\n{batch_report}")
            
            if on_batch_complete:
                on_batch_complete(batch_index, batch_report)
        
        # 合并所有报告
        if len(all_reports) == 1:
            return all_reports[0]
        
        # 多批次合并
        merged_report = "# 分批质检报告\n\n" + "\n\n".join(all_reports)
        
        # 检查是否所有批次都通过
        all_passed = all("✅" in report or "通过" in report for report in all_reports)
        if all_passed:
            merged_report += "\n\n## 总结\n✅ 所有批次质量检查通过，无需修改。"
        else:
            merged_report += "\n\n## 总结\n⚠️ 部分章节存在问题，请查看上述详细报告。"
        
        return merged_report

    @staticmethod
    def merge_batch_quality_reports(batch_reports: List[str]) -> str:
        """
        合并多个批次的质检报告
        
        Args:
            batch_reports: 批次报告列表
            
        Returns:
            合并后的完整报告
        """
        if not batch_reports:
            return "✅ 质量检查通过，无需修改。"
        
        if len(batch_reports) == 1:
            return batch_reports[0]
        
        # 提取所有问题
        all_issues = []
        for report in batch_reports:
            # 跳过通过的批次
            if "✅" in report and "通过" in report:
                continue
            
            # 提取问题行（格式：第X章：问题类型 - 描述）
            lines = report.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('第') and '章' in line and ('：' in line or ':' in line):
                    all_issues.append(line)
        
        # 生成合并报告
        if not all_issues:
            return "✅ 质量检查通过，无需修改。"
        
        merged = "质量检查发现以下问题：\n\n" + "\n".join(all_issues)
        return merged


_service_instance = None


def get_service() -> ShortStoryCreatorService:
    """获取服务实例。"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ShortStoryCreatorService()
    return _service_instance
