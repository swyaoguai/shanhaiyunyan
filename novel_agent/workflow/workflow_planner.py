"""Planner for serial multi-agent creative workflows."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


CATEGORY_ORDER = [
    "worldbuilding",
    "characters",
    "outline",
    "items",
    "eventlines",
    "detail_settings",
    "chapter_settings",
    "chapter_summary",
    "chapters",
]

BUILTIN_CATEGORY_DEFINITIONS = [
    {"key": "outline", "name": "大纲", "aliases": ["故事大纲", "章节大纲", "总纲"]},
    {"key": "characters", "name": "角色档案", "aliases": ["角色卡", "人设卡", "人物卡", "人物档案", "角色设定", "人物设定"]},
    {"key": "worldbuilding", "name": "世界观设定", "aliases": ["世界观", "世界设定", "世界设定集"]},
    {"key": "items", "name": "道具物品", "aliases": ["道具", "物品", "装备", "法宝", "线索物"]},
    {"key": "eventlines", "name": "事件线", "aliases": ["剧情线", "主线", "支线", "事件链"]},
    {"key": "detail_settings", "name": "细纲设定", "aliases": ["细纲", "详细大纲", "分场细纲"]},
    {"key": "chapter_settings", "name": "章纲设定", "aliases": ["章纲", "章节设定", "章节规划"]},
    {"key": "chapter_summary", "name": "正文摘要", "aliases": ["章节摘要", "正文总结", "剧情摘要"]},
    {"key": "chapters", "name": "正文章节", "aliases": ["正文", "章节正文", "章节"]},
]

AGENT_BY_CATEGORY = {
    "worldbuilding": "Worldbuilder",
    "characters": "CharacterBuilder",
    "outline": "Outliner",
    "items": "ProjectDataBuilder",
    "eventlines": "EventlineBuilder",
    "detail_settings": "DetailOutlineBuilder",
    "chapter_settings": "ChapterSettingBuilder",
    "chapter_summary": "ProjectDataBuilder",
    "chapters": "ChapterWriter",
}

OUTPUT_BY_CATEGORY = {
    "worldbuilding": "worldbuilding",
    "characters": "characters",
    "outline": "outline",
    "chapters": "chapters",
}


@dataclass
class WorkflowTask:
    task_id: str
    task_type: str
    target_agent: str
    input_refs: List[str] = field(default_factory=list)
    output_type: str = ""
    status: str = "pending"
    retry_count: int = 0
    max_retries: int = 1
    review_required: bool = True
    user_confirmation_required: bool = False
    title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowPlan:
    plan_id: str
    operation: str
    target_categories: List[str]
    tasks: List[WorkflowTask] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["tasks"] = [task.to_dict() for task in self.tasks]
        return payload


def _normalized_categories(extra_categories: Optional[Iterable[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    categories: List[Dict[str, Any]] = [dict(item) for item in BUILTIN_CATEGORY_DEFINITIONS]
    for item in extra_categories or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("id") or "").strip()
        if not key:
            continue
        categories.append({
            "key": key,
            "name": str(item.get("name") or key).strip(),
            "aliases": [str(alias) for alias in item.get("aliases") or [] if str(alias).strip()],
        })
    return categories


def detect_target_categories(
    message: str,
    *,
    explicit_categories: Optional[Iterable[str]] = None,
    knowledge_categories: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[str]:
    """Detect requested built-in or custom project data categories from text."""

    detected: List[str] = []
    for category in explicit_categories or []:
        key = str(category or "").strip()
        if key and key not in detected:
            detected.append(key)

    text = str(message or "").strip()
    if text:
        for category in _normalized_categories(knowledge_categories):
            key = str(category.get("key") or "").strip()
            if not key:
                continue
            needles = [key, str(category.get("name") or ""), *list(category.get("aliases") or [])]
            if any(needle and re.search(re.escape(str(needle)), text, re.IGNORECASE) for needle in needles):
                if key not in detected:
                    detected.append(key)

    if not detected and text:
        if "世界" in text and any(token in text for token in ("角色", "人设", "人物")):
            detected.extend(["worldbuilding", "characters"])

    order_map = {key: index for index, key in enumerate(CATEGORY_ORDER)}
    return sorted(detected, key=lambda key: order_map.get(key, len(order_map)))


def build_workflow_plan(
    *,
    user_request: str,
    operation: str = "create",
    target_categories: Optional[Iterable[str]] = None,
    knowledge_categories: Optional[Iterable[Dict[str, Any]]] = None,
) -> WorkflowPlan:
    """Build a serial creative workflow plan from a natural-language request."""

    categories = detect_target_categories(
        user_request,
        explicit_categories=target_categories,
        knowledge_categories=knowledge_categories,
    )
    plan = WorkflowPlan(
        plan_id="plan-creative-serial",
        operation=str(operation or "create").strip() or "create",
        target_categories=categories,
        tasks=[],
    )
    plan.tasks.append(
        WorkflowTask(
            task_id="prepare_context",
            task_type="prepare_context",
            target_agent="Coordinator",
            output_type="workflow_context",
            review_required=False,
            title="准备创作上下文",
        )
    )
    previous_ref = "workflow_context"
    for category in categories:
        target_agent = AGENT_BY_CATEGORY.get(category, "ProjectDataBuilder")
        output_type = OUTPUT_BY_CATEGORY.get(category, category)
        task_id = f"{plan.operation}_{category}"
        title = f"生成{_category_display_name(category, knowledge_categories)}"
        plan.tasks.append(
            WorkflowTask(
                task_id=task_id,
                task_type=category,
                target_agent=target_agent,
                input_refs=[previous_ref],
                output_type=output_type,
                status="pending",
                review_required=True,
                title=title,
            )
        )
        previous_ref = output_type
    return plan


def _category_display_name(category: str, knowledge_categories: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    for item in _normalized_categories(knowledge_categories):
        if str(item.get("key") or "").strip() == category:
            return str(item.get("name") or category).strip()
    return category
