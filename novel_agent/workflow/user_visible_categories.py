"""User-facing category keyword helpers for creative workflows."""

from __future__ import annotations

from typing import Dict, List


def category_keywords() -> Dict[str, List[str]]:
    return {
        "worldbuilding": ["世界观", "世界设定", "世界规则", "时代", "背景"],
        "characters": ["角色", "人物", "主角", "人设", "角色卡", "人物卡"],
        "outline": ["大纲", "主线", "剧情规划", "总纲"],
        "items": ["道具", "物品", "装备", "法宝"],
        "eventlines": ["事件线", "剧情线", "支线"],
        "detail_settings": ["细纲", "详细大纲", "分场"],
        "chapter_settings": ["章纲", "章节设定", "章节规划"],
        "chapter_summary": ["摘要", "总结"],
        "chapters": ["正文", "章节", "第"],
    }
