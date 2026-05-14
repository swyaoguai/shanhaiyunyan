import json

from novel_agent.outline_utils import (
    build_global_outline_text,
    build_outline_overview_row,
    derive_chapter_seed_rows_from_outline,
    extract_eventlines_from_outline,
    extract_outline_chapter_rows,
    format_outline_volume_plan,
    merge_eventline_rows,
    normalize_outline_payload,
)
from novel_agent.web.routes.projects import _normalize_outline_rows


def test_raw_content_outline_is_parsed_into_overview_row():
    payload = {
        "raw_content": json.dumps(
            {
                "title": "山海·云烟",
                "global_outline": "书名：《山海·云烟》\n故事梗概：吴迪秘境逆袭。",
                "main_conflict": "抽象梗文化与合欢宗旧秩序的冲突。",
                "volumes": [
                    {
                        "volume_number": 1,
                        "volume_title": "秘境初啼",
                        "volume_summary": "吴迪入秘境并获得噬器能力。",
                        "chapters": [{"title": "不应进入主线大纲"}],
                    }
                ],
            },
            ensure_ascii=False,
        )
    }

    normalized = normalize_outline_payload(payload)
    row = build_outline_overview_row(payload, timestamp="2026-05-07T00:00:00")

    assert normalized["title"] == "山海·云烟"
    assert "吴迪秘境逆袭" in row["summary"]
    assert "第1卷：秘境初啼" in row["volume_plan"]
    assert "不应进入主线大纲" not in row["volume_plan"]
    assert row["conflicts"] == "抽象梗文化与合欢宗旧秩序的冲突。"


def test_truncated_raw_content_outline_can_be_recovered_loosely():
    payload = {
        "raw_content": '''{
  "title": "山海·云烟",
  "global_outline": "书名：《山海·云烟》
故事梗概：吴迪秘境逆袭。",
  "main_conflict": "抽象梗文化与合欢宗旧秩序的冲突。",
  "volumes": [
    {
      "volume_number": 1,
      "volume_title": "秘境初啼",
      "volume_summary": "吴迪入秘境并获得噬器能力。",
      "chapters": [
        {"title": "截断在这里"'''
    }

    row = build_outline_overview_row(payload, timestamp="2026-05-07T00:00:00")

    assert "吴迪秘境逆袭" in row["summary"]
    assert "第1卷：秘境初啼" in row["volume_plan"]
    assert "截断在这里" not in row["volume_plan"]


def test_global_outline_can_be_rebuilt_from_structured_fields():
    payload = {
        "title": "归墟录",
        "author": "AI助手",
        "theme": "少年在归墟中找回真相。",
        "main_conflict": "归墟遗民与旧王朝的冲突。",
    }

    text = build_global_outline_text(payload)

    assert "书名\n归墟录" in text
    assert "作者" not in text
    assert "AI助手" not in text
    assert "简介\n少年在归墟中找回真相。" in text
    assert "四、【矛盾冲突】\n归墟遗民与旧王朝的冲突。" in text


def test_internal_ai_author_line_is_stripped_from_global_outline():
    payload = {
        "global_outline": "书名：《归墟录》\n作者：AI助手\n简介：旧案重开。\n故事梗概：林渡回城查案。",
    }

    text = build_global_outline_text(payload)

    assert "书名：《归墟录》" in text
    assert "作者：AI助手" not in text


def test_placeholder_outline_rows_normalize_to_empty():
    rows = [
        {"chapter_number": index, "title": f"第{index}章", "summary": "待生成", "content": ""}
        for index in range(1, 4)
    ]

    assert _normalize_outline_rows(rows) == []


def test_volume_plan_uses_volume_level_fields_only():
    payload = {
        "volumes": [
            {
                "volume_number": 2,
                "volume_title": "宗门翻身",
                "core_conflict": "吴迪与执事阁公开对立。",
                "key_events": ["建立梗派", "击败王扒皮"],
                "chapters": [{"title": "第6章"}],
            }
        ]
    }

    plan = format_outline_volume_plan(payload)

    assert "第2卷：宗门翻身" in plan
    assert "吴迪与执事阁公开对立。" in plan
    assert "建立梗派、击败王扒皮" in plan
    assert "第6章" not in plan


def test_identical_global_outline_and_volume_plan_do_not_mirror_in_overview():
    same_text = "书名：《归墟录》\n简介：旧城追凶。\n故事梗概：林渡回城查案。"
    payload = [
        {
            "title": "主线大纲",
            "summary": same_text,
            "global_outline": same_text,
            "volume_plan": same_text,
        }
    ]

    row = build_outline_overview_row(payload, timestamp="2026-05-11T00:00:00")

    assert row["summary"] == same_text
    assert row["global_outline"] == same_text
    assert row["volume_plan"] == ""


def test_legacy_chapter_only_outline_builds_global_synopsis():
    payload = {
        "chapters": [
            {"title": "第1章 旧城归来", "summary": "吴迪踏入旧城，发现旧案线索。"},
            {"title": "第2章 血债", "summary": "旧案升级，主角被迫正面交锋。"},
        ]
    }

    row = build_outline_overview_row(payload, timestamp="2026-05-07T00:00:00")

    assert row["title"] == "主线大纲"
    assert "吴迪踏入旧城" in row["global_outline"]
    assert "旧案升级" in row["global_outline"]
    assert "第1章 旧城归来" not in row["global_outline"]


def test_eventlines_are_extracted_from_explicit_outline_threads():
    payload = {
        "plot_threads": [
            {
                "id": "auction_line",
                "title": "拍卖会支线",
                "objective": "拿到玄铁令",
                "participants": ["吴迪", "秦掌柜"],
                "start_chapter": 3,
                "target_return_chapter": 5,
                "max_consecutive_chapters": 2,
            }
        ],
        "volumes": [
            {
                "volume_number": 1,
                "volume_title": "秘境初啼",
                "foreshadowing": "黑匣子会在第二卷回收。",
            }
        ],
    }

    rows = extract_eventlines_from_outline(payload)

    assert rows[0]["thread_id"] == "auction_line"
    assert rows[0]["name"] == "拍卖会支线"
    assert rows[0]["start_chapter"] == 3
    assert rows[0]["target_return_chapter"] == 5
    assert rows[0]["participants"] == "吴迪、秦掌柜"
    assert any(row.get("source_scope") == "volume_foreshadowing" for row in rows)


def test_outline_eventline_merge_preserves_user_fields():
    existing = [
        {
            "thread_id": "auction_line",
            "name": "拍卖会支线",
            "description": "用户手动改过的版本",
            "status": "active",
        }
    ]
    generated = [
        {
            "thread_id": "auction_line",
            "name": "拍卖会支线",
            "description": "自动提取版本",
            "start_chapter": 3,
        },
        {
            "thread_id": "secret_box",
            "name": "黑匣子伏笔线",
            "description": "第二卷回收。",
        },
    ]

    merged = merge_eventline_rows(existing, generated)

    assert merged[0]["description"] == "用户手动改过的版本"
    assert merged[0]["start_chapter"] == 3
    assert merged[1]["thread_id"] == "secret_box"


def test_extract_chapters_does_not_promote_volume_key_events_by_default():
    """Outliner output must stay a global/volume outline unless a downstream
    chapter-setting stage explicitly asks to derive seed rows."""
    payload = {
        "title": "凝王府的甜宠日常",
        "volumes": [
            {
                "volume_number": 1,
                "volume_title": "初遇成婚",
                "volume_summary": "上元灯会初遇到大婚庆典。",
                "key_events": [
                    "上元灯会初遇，赵景渊暗中留下女主花灯",
                    "奉旨成婚，洞房夜尴尬互动",
                    "沈清欢用医术治愈赵景渊旧伤",
                ],
            }
        ],
    }

    rows = extract_outline_chapter_rows(payload, timestamp="2026-05-11T00:00:00")

    assert rows == []


def test_derive_chapter_seed_rows_promotes_volume_key_events_explicitly():
    payload = {
        "title": "凝王府的甜宠日常",
        "volumes": [
            {
                "volume_number": 1,
                "volume_title": "初遇成婚",
                "volume_summary": "上元灯会初遇到大婚庆典。",
                "key_events": [
                    "上元灯会初遇，赵景渊暗中留下女主花灯",
                    "奉旨成婚，洞房夜尴尬互动",
                    "沈清欢用医术治愈赵景渊旧伤",
                ],
            }
        ],
    }

    rows = derive_chapter_seed_rows_from_outline(payload, timestamp="2026-05-11T00:00:00")

    assert [row["chapter_number"] for row in rows] == [1, 2, 3]
    assert rows[0]["key_event"] == "上元灯会初遇，赵景渊暗中留下女主花灯"
    assert "上元灯会初遇" in rows[0]["summary"]
    assert rows[1]["key_event"] == "奉旨成婚，洞房夜尴尬互动"
    assert rows[2]["key_event"] == "沈清欢用医术治愈赵景渊旧伤"
    # 不同章节的 summary 必须各不相同，避免回归到"全书梗概被复制 N 份"。
    assert len({row["summary"] for row in rows}) == 3
    assert all(row.get("volume_title") == "初遇成婚" for row in rows)


def test_explicit_chapters_take_priority_over_key_events():
    """If a volume already declares chapters, key_events must not duplicate them."""
    payload = {
        "volumes": [
            {
                "volume_number": 1,
                "volume_title": "初遇成婚",
                "chapters": [
                    {"title": "第1章 灯会偶遇", "summary": "灯会偶遇引出婚约。"},
                    {"title": "第2章 奉旨成婚", "summary": "奉旨成婚开始磨合。"},
                ],
                "key_events": [
                    "不应被升级为章节的备注节拍",
                ],
            }
        ]
    }

    rows = extract_outline_chapter_rows(payload, timestamp="2026-05-11T00:00:00")

    assert len(rows) == 2
    assert all("不应被升级为章节的备注节拍" not in row["summary"] for row in rows)
    assert rows[0]["title"].startswith("第1章")
    assert rows[1]["title"].startswith("第2章")
