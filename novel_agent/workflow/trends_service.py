"""Trends service for multi-platform hot topic search and balanced aggregation."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _normalize_trend_platforms(platforms: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for platform in platforms or []:
        value = str(platform or "").strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _extract_trend_tool_error(result: Any) -> str:
    if result is None:
        return ""
    if hasattr(result, "content") and result.content:
        first = result.content[0]
        text = getattr(first, "text", "")
        if isinstance(text, str):
            return text.strip()
    return ""


def _get_trend_tool_name(platform: str) -> str:
    mapping = {
        "douban": "get_douban_rank",
        "weread": "get_weread_rank",
        "zhihu": "get_zhihu_trending",
        "gcores": "get_gcores_new",
        "toutiao": "get_toutiao_trending",
        "netease": "get_netease_news_trending",
        "tencent": "get_tencent_news_trending",
        "thepaper": "get_thepaper_trending",
        "bilibili": "get_bilibili_rank",
        "douyin": "get_douyin_trending",
        "weibo": "get_weibo_trending",
        "36kr": "get_36kr_trending",
        "sspai": "get_sspai_rank",
        "ifanr": "get_ifanr_news",
        "juejin": "get_juejin_article_rank",
        "smzdm": "get_smzdm_rank",
    }
    normalized = str(platform or "").strip().lower()
    return mapping.get(normalized, f"get_{normalized}_trending")


def _build_trend_tool_candidates(platform: str) -> List[str]:
    normalized = str(platform or "").strip().lower()
    if not normalized:
        return []

    candidates: List[str] = []

    def _add(tool_name: str) -> None:
        if tool_name and tool_name not in candidates:
            candidates.append(tool_name)

    mapped = _get_trend_tool_name(normalized)
    _add(mapped)

    modern = f"get_{normalized}_trending"
    _add(modern)
    _add(modern.replace("_", "-"))

    if mapped:
        _add(mapped.replace("_", "-"))

    return candidates


def _select_balanced_trend_candidates(
    trends_data: List[Dict[str, Any]],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    if not trends_data or limit <= 0:
        return []

    platform_buckets: Dict[str, List[Dict[str, Any]]] = {}
    platform_order: List[str] = []

    for trend in trends_data:
        platform = str(trend.get("platform", "")).strip().lower()
        if platform not in platform_buckets:
            platform_buckets[platform] = []
            platform_order.append(platform)
        platform_buckets[platform].append(trend)

    merged: List[Dict[str, Any]] = []
    cursor = {platform: 0 for platform in platform_order}
    while len(merged) < limit:
        appended = False
        for platform in platform_order:
            idx = cursor[platform]
            items = platform_buckets.get(platform, [])
            if idx >= len(items):
                continue
            merged.append(items[idx])
            cursor[platform] = idx + 1
            appended = True
            if len(merged) >= limit:
                break
        if not appended:
            break

    return merged


def build_trends_prompt_block(trends_data: List[Dict[str, Any]], limit: int = 5) -> str:
    if not trends_data:
        return ""

    parts: List[str] = []
    parts.append("热点融合要求：")
    parts.append("请从热点候选中选择 1-2 条与当前剧情最契合的内容进行改编融入。")
    parts.append("不要原样照抄热点标题，不要写成新闻播报，要转化为角色动机/冲突/事件触发。")
    parts.append("")
    parts.append("[热点候选]")

    for trend in _select_balanced_trend_candidates(trends_data, limit=limit):
        title = str(trend.get("title", "")).strip()
        if not title:
            continue
        platform = str(trend.get("platform", "")).strip()
        hot = str(trend.get("hot", "")).strip()
        source = f"[{platform}]" if platform else ""
        heat = f"（热度:{hot}）" if hot else ""
        parts.append(f"- {source}{title}{heat}")

    parts.append("")
    return "\n".join(parts)


class TrendsService:
    """Multi-platform trends search service with balanced aggregation."""

    def __init__(self, worldbuilder: Any) -> None:
        self.worldbuilder = worldbuilder

    async def search_trends(
        self,
        platforms: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Collaboration mode hot topic search: multi-platform fallback + deduplication + balanced polling."""
        selected_platforms = _normalize_trend_platforms(platforms)
        total_limit = int(limit or 0)
        if not selected_platforms or total_limit <= 0:
            return []

        def _extract_tag(text: str, tag: str) -> str:
            if not text:
                return ""
            match = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
            return match.group(1).strip() if match else ""

        def _strip_xml(text: str) -> str:
            if not text:
                return ""
            return re.sub(r"<[^>]+>", "", text).strip()

        def _parse_trend_payload(payload: Any) -> List[Dict[str, str]]:
            rows: List[Dict[str, str]] = []
            if payload is None:
                return rows

            if isinstance(payload, list):
                for item in payload:
                    rows.extend(_parse_trend_payload(item))
                return rows

            if isinstance(payload, dict):
                for key in ("data", "list", "items", "result"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        rows.extend(_parse_trend_payload(value))
                        return rows

                title_val = payload.get("title") or payload.get("name") or payload.get("content") or ""
                if isinstance(title_val, (list, dict)):
                    rows.extend(_parse_trend_payload(title_val))
                    return rows

                title_text = str(title_val or "").strip()
                title = _extract_tag(title_text, "title") or _strip_xml(title_text) or title_text
                if title:
                    hot_val = (
                        payload.get("hot")
                        or payload.get("hotValue")
                        or payload.get("heat")
                        or payload.get("popularity")
                        or payload.get("score")
                        or ""
                    )
                    url_val = payload.get("url") or payload.get("link") or ""
                    rows.append(
                        {
                            "title": str(title),
                            "hot": str(hot_val or ""),
                            "url": str(url_val or ""),
                        }
                    )
                return rows

            if isinstance(payload, str):
                text = payload.strip()
                if not text:
                    return rows
                try:
                    parsed = json.loads(text)
                    rows.extend(_parse_trend_payload(parsed))
                    return rows
                except json.JSONDecodeError:
                    title = _extract_tag(text, "title") or _strip_xml(text) or text
                    if title:
                        rows.append(
                            {
                                "title": str(title),
                                "hot": _extract_tag(text, "popularity"),
                                "url": _extract_tag(text, "link"),
                            }
                        )
                return rows

            return rows

        try:
            seen_titles = set()
            platform_trends: Dict[str, List[Dict[str, Any]]] = {
                platform: [] for platform in selected_platforms
            }

            for platform in selected_platforms:
                tool_candidates = _build_trend_tool_candidates(platform)
                result = None
                used_tool = ""

                for tool_name in tool_candidates:
                    try:
                        current = self.worldbuilder.use_skill("trends_search", tool_name, limit=total_limit)
                    except Exception as call_error:
                        logger.debug(
                            f"[TrendsService] Hot tool call exception({platform}, {tool_name}): {call_error}"
                        )
                        continue

                    if not current or not current.get("success"):
                        error_msg = current.get("error", "") if current else "unknown error"
                        lowered_error = error_msg.lower()
                        if "not found" in lowered_error:
                            logger.debug(
                                f"[TrendsService] Hot tool not found, try next candidate: platform={platform}, tool={tool_name}"
                            )
                            continue
                        logger.debug(
                            f"[TrendsService] Hot tool call failed({platform}, {tool_name}): {error_msg}"
                        )
                        continue

                    if current and current.get("success"):
                        result = current
                        used_tool = tool_name
                        break

                if result is None:
                    logger.debug(
                        f"[TrendsService] No platform hot topics({platform}), candidate tools: {tool_candidates}"
                    )
                    continue

                if result and result.get("data"):
                    data_items = result.get("data", [])
                    for item in data_items:
                        title = str(item.get("title") or "").strip()
                        if not title or title in seen_titles:
                            continue
                        seen_titles.add(title)
                        platform_trends[platform].append(
                            {
                                "title": title,
                                "hot": str(item.get("热度", "") or ""),
                                "url": str(item.get("url", "") or ""),
                                "platform": platform,
                            }
                        )
                        if len(platform_trends[platform]) >= total_limit:
                            break

                logger.debug(
                    f"[TrendsService] Platform hot topics fetched: platform={platform}, tool={used_tool}, count={len(platform_trends[platform])}"
                )

            merged_candidates: List[Dict[str, Any]] = []
            for platform in selected_platforms:
                merged_candidates.extend(platform_trends.get(platform, []))
            return _select_balanced_trend_candidates(merged_candidates, limit=total_limit)
        except Exception as e:
            logger.warning(f"[TrendsService] Hot topic search failed: {e}")
            return []