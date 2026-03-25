"""Novel-to-script service tests."""

from novel_agent.novel_to_script_service import NovelToScriptService


def test_normalize_source_splits_pasted_text_into_chapters():
    service = NovelToScriptService()
    payload = service.normalize_source(
        source_type="paste",
        source_text=(
            "第1章 初遇\n"
            "林风在雨夜遇见旧友，决定连夜进城。\n"
            "第2章 异象\n"
            "城门口突然出现异光，所有人都停下脚步。"
        ),
        source_filename="",
    )

    assert payload["source_type"] == "paste"
    assert payload["chapter_count"] >= 2
    assert payload["source_chapters"][0]["title"] in {"第1章", "初遇"}


def test_parse_conversion_result_renders_formatted_text_from_structured_scenes():
    service = NovelToScriptService()
    result = service.parse_conversion_result(
        """
        {
          "scenes": [
            {
              "scene_number": 1,
              "scene_label": "场景一",
              "heading": "城门口 - 夜雨",
              "characters_text": "林风、苏晚",
              "environment_text": "雨水顺着青石板滑落。",
              "beats": [
                {"type": "action_narration", "label": "动作/旁白", "text": "林风撑伞站在城门下。"},
                {"type": "character_line", "speaker": "林风", "qualifier": "低声", "text": "今晚不太对劲。"},
                {"type": "fx_line", "label": "动作/音效", "text": "远处传来闷雷。"}
              ]
            }
          ]
        }
        """
    )

    assert result["scene_count"] == 1
    assert "【场景一：城门口 - 夜雨】" in result["formatted_text"]
    assert "林风（低声）：今晚不太对劲。" in result["formatted_text"]
    assert "动作/音效：远处传来闷雷。" in result["formatted_text"]
    assert result["character_index"][0]["name"] == "林风"
    assert result["scene_outline"][0]["heading"] == "城门口 - 夜雨"


def test_parse_conversion_result_falls_back_to_plain_text_scene_parsing():
    service = NovelToScriptService()
    raw_text = (
        "【场景一：废寺 - 深夜】\n"
        "人物：沈砚、阿禾\n"
        "环境：冷风卷过残破佛幡。\n"
        "动作/旁白：沈砚推门而入。\n"
        "沈砚（内心独白）：这里果然有人来过。\n"
        "闪回片段（快速切换）：白日里的火光一闪而过。\n"
        "动作/音效：木门发出刺耳的吱呀声。"
    )

    result = service.parse_conversion_result(raw_text)

    assert result["scene_count"] == 1
    assert result["scenes"][0]["beats"][1]["speaker"] == "沈砚"
    assert result["scenes"][0]["beats"][2]["type"] == "flashback_line"
    assert result["formatted_text"] == raw_text


def test_analyze_source_recommends_batch_mode_for_long_text():
    service = NovelToScriptService()
    payload = service.normalize_source(
        source_type="paste",
        source_text="\n\n".join([f"第{i}章\n" + ("内容" * 7000) for i in range(1, 8)]),
        source_filename="long.txt",
    )

    analysis = service.analyze_source(payload)
    plan = service.plan_conversion(source_payload=payload, config={"convert_mode": "auto"})

    assert analysis["recommended_mode"] == "batchwise"
    assert plan["resolved_mode"] == "batchwise"
    assert plan["batch_count"] >= 2


def test_plan_conversion_keeps_short_text_in_single_pass():
    service = NovelToScriptService()
    payload = service.normalize_source(
        source_type="paste",
        source_text="这是一个一万字以内的短文本片段。" * 200,
    )

    plan = service.plan_conversion(source_payload=payload, config={"convert_mode": "auto"})

    assert plan["resolved_mode"] == "full_text"
    assert plan["batch_count"] == 1


def test_merge_with_existing_batch_replaces_only_target_batch():
    service = NovelToScriptService()
    payload = service.normalize_source(
        source_type="paste",
        source_text="\n\n".join([f"第{i}章\n" + ("内容" * 7000) for i in range(1, 5)]),
    )
    plan = service.plan_conversion(source_payload=payload, config={"convert_mode": "auto"})
    assert plan["batch_count"] >= 2

    existing_batches = []
    for batch in plan["batches"]:
        existing_batches.append(
            {
                **batch,
                "result": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "scene_label": "场景一",
                            "heading": f"旧批次{batch['batch_number']}",
                            "characters_text": "甲",
                            "environment_text": "旧环境",
                            "beats": [{"type": "action_narration", "label": "动作/旁白", "text": "旧内容"}],
                        }
                    ]
                },
            }
        )

    replacement = {
        **plan["batches"][0],
        "result": {
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_label": "场景一",
                    "heading": "新批次1",
                    "characters_text": "乙",
                    "environment_text": "新环境",
                    "beats": [{"type": "action_narration", "label": "动作/旁白", "text": "新内容"}],
                }
            ]
        },
    }

    merged = service.merge_with_existing_batch(
        plan=plan,
        existing_batches=existing_batches,
        replacement_batch=replacement,
    )

    assert merged["batch_count"] == plan["batch_count"]
    assert merged["batches"][0]["result"]["scenes"][0]["heading"] == "新批次1"
    assert merged["batches"][1]["result"]["scenes"][0]["heading"].startswith("旧批次")
