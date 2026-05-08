from novel_agent.content_sanitizer import humanize_structured_value, strip_internal_author_markers


def test_strip_internal_author_markers_removes_plot_thread_comments():
    assert strip_internal_author_markers("正文内容\n\n<!-- PLOT_THREAD:main -->") == "正文内容"


def test_humanize_structured_value_does_not_emit_raw_json_for_worldbuilding():
    payload = {
        "continents": ["东玄洲", "西漠荒原"],
        "environment": "灵气充裕但分布不均",
        "key_locations": [
            {"name": "合欢宗", "significance": "故事起点"},
            {"name": "古修洞府", "significance": "主角机缘"},
        ],
    }

    text = humanize_structured_value(payload)

    assert "东玄洲" in text
    assert "合欢宗" in text
    assert "灵气充裕但分布不均" in text
    assert '"continents"' not in text
    assert "{" not in text
    assert "}" not in text


def test_humanize_structured_value_decodes_json_strings():
    text = humanize_structured_value('{"environment": "灵气紊乱", "continents": ["东玄洲"]}')

    assert "灵气紊乱" in text
    assert "东玄洲" in text
    assert '"environment"' not in text


def test_humanize_structured_value_localizes_worldbuilding_schema_keys():
    text = humanize_structured_value(
        {
            "levels": ["器徒", "器士", "器师"],
            "cultivation method": "吞噬法器并炼化为自身修为",
            "special abilities": "万器归宗、抽象破法",
            "limitations": "过度依赖吞噬会导致根基虚浮",
        }
    )

    assert "境界层级：器徒、器士、器师" in text
    assert "修炼方式：吞噬法器并炼化为自身修为" in text
    assert "特殊能力：万器归宗、抽象破法" in text
    assert "限制与代价：过度依赖吞噬会导致根基虚浮" in text
    assert "levels" not in text
    assert "cultivation method" not in text
    assert "special abilities" not in text
    assert "limitations" not in text


def test_humanize_structured_value_localizes_saved_text_labels():
    text = humanize_structured_value(
        "器噬之道； levels: 器徒、器士； cultivation method: 吞噬法器； "
        "special abilities: 万器归宗； limitations: 根基虚浮"
    )

    assert "境界层级：器徒、器士" in text
    assert "修炼方式：吞噬法器" in text
    assert "特殊能力：万器归宗" in text
    assert "限制与代价：根基虚浮" in text
    assert "levels:" not in text
    assert "cultivation method:" not in text
    assert "special abilities:" not in text
    assert "limitations:" not in text


def test_humanize_structured_value_preserves_user_supplied_names():
    text = humanize_structured_value({"world_name": "山海·云烟", "description": "用户明确指定的世界名"})

    assert "山海·云烟" in text
    assert "用户明确指定的世界名" in text
