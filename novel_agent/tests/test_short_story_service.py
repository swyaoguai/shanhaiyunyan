"""Tests for the built-in short story service."""

from novel_agent.short_story_service import (
    ShortStoryCreatorService,
    parse_chapters_from_full_text,
    parse_fusion_candidates,
    parse_material_analysis,
    parse_outline_payload,
    parse_story_tags,
    parse_synopsis_candidates,
    parse_title_candidates,
)


def _make_started_workflow(service):
    started = service.start_workflow(
        keywords=["旧相机", "失约", "雨夜"],
        target_total_words=4200,
    )
    workflow = started["data"]["workflow"]
    workflow = service.record_input_analysis(
        workflow,
        {
            "summary": "输入以词条为主，同时带有悬疑向创作意图。",
            "confidence": 0.92,
            "detected_material_types": ["keywords", "inspiration"],
            "keywords": ["旧相机", "失约", "雨夜"],
            "genre_hint": "其他",
            "borrowed_highlights": ["雨夜钩子", "照片反转"],
            "constraints": [],
            "warnings": [],
        },
    )["data"]["workflow"]
    workflow = service.register_fusion_candidates(
        workflow,
        [
            {"title": "暗房追索", "route": "悬疑追查", "hook": "失约的人藏进最后一张照片里。", "borrowed_structure": "雨夜回城→线索浮现→照片反转", "refresh_plan": "人物与案件背景全部换新", "premise": "周岚回城后在旧相机底片里看到失约真相。"},
            {"title": "迟来赴约", "route": "情感反转", "hook": "她等来的人没出现，却等来了一卷会说话的底片。", "borrowed_structure": "重逢未成→误会加深→真相和解", "refresh_plan": "关系设定换新", "premise": "旧底片把多年误会拉回雨夜。"},
            {"title": "雨夜旧案", "route": "暗黑揭秘", "hook": "每按下一次快门，都逼近一段被掩埋的旧案。", "borrowed_structure": "回城→追查→揭秘", "refresh_plan": "核心事件换新", "premise": "相机成为旧案线索的入口。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_fusion(workflow, 1)["data"]["workflow"]
    return workflow


def _advance_to_synopsis_stage(service, workflow, keywords):
    workflow = service.record_input_analysis(
        workflow,
        {
            "summary": "已识别为可直接生成融合方案的创作素材。",
            "confidence": 0.9,
            "detected_material_types": ["keywords"],
            "keywords": list(keywords),
            "genre_hint": "其他",
            "borrowed_highlights": [],
            "constraints": [],
            "warnings": [],
        },
    )["data"]["workflow"]
    workflow = service.register_fusion_candidates(
        workflow,
        [
            {"title": "方案一", "route": "路数一", "hook": "钩子一", "premise": "梗概一"},
            {"title": "方案二", "route": "路数二", "hook": "钩子二", "premise": "梗概二"},
            {"title": "方案三", "route": "路数三", "hook": "钩子三", "premise": "梗概三"},
        ],
    )["data"]["workflow"]
    return service.select_fusion(workflow, 1)["data"]["workflow"]


def test_short_story_capabilities_expose_workflow_metadata():
    service = ShortStoryCreatorService()

    result = service.get_capabilities()

    assert result["success"] is True
    assert result["module"] == "short_story"
    assert "generating_fusion_options" in result["states"]
    assert "generating_synopsis" in result["states"]
    assert len(result["steps"]) == 8
    assert result["chapter_word_target_range"] == [500, 3000]
    assert result["chapter_word_count_range"] == [400, 3100]
    assert result["chapter_plan_rules"][0]["mode"] == "dynamic_by_total_and_chapter_words"


def test_short_story_start_workflow_accepts_unified_source_input():
    service = ShortStoryCreatorService()

    workflow = service.start_workflow(
        source_input="灵感：雨夜重逢；参考旧相机、失约这个钩子。",
        target_total_words=4200,
        category="悬疑惊悚",
    )["data"]["workflow"]

    assert workflow["state"] == "analyzing_source_input"
    assert workflow["raw_input"].startswith("灵感：雨夜重逢")


def test_short_story_analysis_and_fusion_selection_advance_workflow():
    service = ShortStoryCreatorService()
    workflow = service.start_workflow(
        source_input="旧相机、失约、雨夜",
        target_total_words=4200,
    )["data"]["workflow"]

    workflow = service.record_input_analysis(
        workflow,
        parse_material_analysis(
            """{
              "summary": "输入包含词条与灵感。",
              "confidence": 0.88,
              "detected_material_types": ["keywords", "inspiration"],
              "keywords": ["旧相机", "失约", "雨夜"],
              "genre_hint": "悬疑惊悚",
              "borrowed_highlights": ["雨夜钩子"],
              "constraints": [],
              "warnings": []
            }""",
            fallback_source="旧相机、失约、雨夜",
            fallback_category="悬疑惊悚",
        ),
    )["data"]["workflow"]
    assert workflow["state"] == "generating_fusion_options"
    assert workflow["input_confidence"] == 0.88

    workflow = service.register_fusion_candidates(
        workflow,
        parse_fusion_candidates(
            """【方案一】
标题：暗房追索
路数：悬疑追查
钩子：失约的人藏进最后一张照片里。
借鉴骨架：雨夜回城→线索浮现→照片反转
内容换新：人物与案件背景全部换新
故事梗概：周岚回城后在旧相机底片里看到失约真相。

【方案二】
标题：迟来赴约
路数：情感反转
钩子：她等来的人没出现，却等来了一卷会说话的底片。
借鉴骨架：重逢未成→误会加深→真相和解
内容换新：人物关系与矛盾来源换新
故事梗概：旧底片把多年误会拉回雨夜。

【方案三】
标题：雨夜旧案
路数：暗黑揭秘
钩子：每按下一次快门，都逼近一段被掩埋的旧案。
借鉴骨架：回城→追查→揭秘
内容换新：案件背景和关键事件换新
故事梗概：相机成为旧案线索的入口。"""
        ),
    )["data"]["workflow"]
    assert workflow["state"] == "awaiting_fusion_selection"
    assert len(workflow["fusion_candidates"]) == 3

    workflow = service.select_fusion(workflow, 2)["data"]["workflow"]
    assert workflow["state"] == "generating_synopsis"
    assert workflow["selected_fusion_index"] == 2


def test_short_story_workflow_builds_prompts_and_completes():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)

    assert workflow["state"] == "generating_synopsis"
    assert workflow["selected_fusion_index"] == 1
    assert workflow["planned_chapters"] == 5
    assert workflow["chapter_word_min"] == 740
    assert workflow["chapter_word_max"] == 940

    synopsis_prompt = service.build_synopsis_prompt(workflow)
    assert "生成 5 条风格各异的故事导语" in synopsis_prompt["data"]["prompt"]

    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "雨夜里，带着旧相机回城的周岚发现一场被故意错开的告别。"},
            {"style": "温情向", "content": "一场迟到多年的重逢，让旧相机里的照片重新拥有了温度。"},
            {"style": "反转向", "content": "失约的人从未离开，只是换了一种方式在雨夜中出现。"},
            {"style": "暗黑向", "content": "旧相机拍下的最后一张照片，藏着失约背后的真相。"},
            {"style": "治愈向", "content": "她在雨夜洗出照片，也洗出那场失约真正的意义。"},
        ],
    )["data"]["workflow"]
    assert workflow["state"] == "awaiting_synopsis_selection"

    workflow = service.select_synopsis(workflow, 3)["data"]["workflow"]
    assert workflow["selected_synopsis_index"] == 3
    assert workflow["state"] == "generating_outline"

    outline_prompt = service.build_outline_prompt(workflow)
    assert "必须规划为 5 章" in outline_prompt["data"]["prompt"]
    assert "每章正文控制在 740~940 字左右，平均目标约 840 字" in outline_prompt["data"]["prompt"]
    assert "全文总字数目标不少于 4200 字" in outline_prompt["data"]["prompt"]

    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="周岚：摄影师；顾原：旧友。",
        timeline="同一雨夜至次日清晨。",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "归城", "summary": "周岚回城。", "characters": "周岚", "core_event": "她带着旧相机归来", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "失约", "summary": "线索浮现。", "characters": "周岚、顾原", "core_event": "她发现顾原失约另有原因", "narrative_function": "转折"},
            {"chapter_number": 3, "title": "冲洗", "summary": "真相逼近。", "characters": "周岚", "core_event": "她在暗房里找到关键照片", "narrative_function": "高潮"},
            {"chapter_number": 4, "title": "逼近", "summary": "完成追索。", "characters": "周岚", "core_event": "她拼起关键线索", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "回声", "summary": "完成和解。", "characters": "周岚", "core_event": "她理解那场失约", "narrative_function": "收束"},
        ],
    )["data"]["workflow"]
    assert workflow["state"] == "awaiting_outline_confirm"

    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    assert workflow["state"] == "writing_content"

    chapter_prompt = service.build_chapter_prompt(workflow, chapter_number=1)
    assert "字数控制在 740~940 字左右，目标约 840 字" in chapter_prompt["data"]["prompt"]
    assert "摘要：周岚回城。" in chapter_prompt["data"]["prompt"]
    assert "核心事件：她带着旧相机归来" in chapter_prompt["data"]["prompt"]
    assert "排版采用短句成段" in chapter_prompt["data"]["prompt"]
    assert "不要输出章节标题" in chapter_prompt["data"]["prompt"]

    for chapter_number, title in [(1, "归城"), (2, "失约"), (3, "转场"), (4, "逼近"), (5, "回声")]:
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=title,
            content=f"这是第{chapter_number}章正文，围绕旧相机、失约和雨夜展开，保证情节连贯。",
        )["data"]["workflow"]

    assert workflow["state"] == "quality_checking"

    qa_prompt = service.build_quality_check_prompt(workflow)
    qa_prompt_text = qa_prompt["data"]["prompt"] if "prompt" in qa_prompt["data"] else qa_prompt["data"]["batches"][0]["prompt"]
    assert "角色一致性" in qa_prompt_text

    workflow = service.record_quality_check(
        workflow,
        report="✅ 质量检查通过，无需修改。",
        passed=True,
    )["data"]["workflow"]
    assert workflow["state"] == "coherence_reviewing"

    review_prompt = service.build_coherence_review_prompt(workflow)
    review_prompt_text = review_prompt["data"]["prompt"] if "prompt" in review_prompt["data"] else review_prompt["data"]["batches"][0]["prompt"]
    assert "词条覆盖度" in review_prompt_text

    workflow = service.record_coherence_review(
        workflow,
        report="✅ 复审通过，正文定稿。",
        passed=True,
    )["data"]["workflow"]
    assert workflow["state"] == "generating_titles"

    title_prompt = service.build_title_prompt(workflow)
    assert "5 个候选书名" in title_prompt["data"]["prompt"]
    assert "冲突型" in title_prompt["data"]["prompt"]

    workflow = service.register_title_candidates(
        workflow,
        [
            {"title": "雨夜失约", "category": "直白点题"},
            {"title": "暗房回声", "category": "意象隐喻"},
            {"title": "谁没有赴约", "category": "悬念引导"},
            {"title": "迟来的照片", "category": "情感共鸣"},
            {"title": "雨落成像", "category": "诗意文艺"},
        ],
    )["data"]["workflow"]
    assert workflow["state"] == "awaiting_title_selection"

    workflow = service.select_title(workflow, 2)["data"]["workflow"]
    assert workflow["state"] == "assembling_output"
    assert workflow["selected_title"] == "暗房回声"

    workflow = service.record_story_tags(
        workflow,
        {
            "main_category": "悬疑惊悚",
            "plot_tags": ["推理", "民间奇闻"],
            "role_tags": ["医生"],
            "emotion_tags": ["惊悚"],
            "background_tags": ["现代"],
        },
    )["data"]["workflow"]
    assert workflow["story_tags"]["main_category"] == "悬疑惊悚"

    final_result = service.assemble_output(workflow)
    final_work = final_result["data"]["final_work"]

    assert final_result["data"]["workflow"]["state"] == "completed"
    assert "# 《暗房回声》" in final_work
    assert "**主分类**：悬疑惊悚" in final_work
    assert "**内容标签**：" in final_work
    assert "**词条标签**：旧相机 | 失约 | 雨夜" in final_work
    assert "## 导语" in final_work
    assert "## 正文" in final_work
    assert "### 1. 归城" in final_work


def test_quality_check_requires_all_planned_chapters():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "归城", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "失约", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "转场", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "逼近", "summary": "摘要4", "characters": "丁", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "回声", "summary": "摘要5", "characters": "戊", "core_event": "事件5", "narrative_function": "收束"},
        ],
    )["data"]["workflow"]
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]

    for chapter_number in range(1, 5):
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=f"{chapter_number}. 示例章节",
            content=f"这是第{chapter_number}章正文。",
        )["data"]["workflow"]

    incomplete = dict(workflow)
    incomplete["state"] = "quality_checking"

    try:
        service.build_quality_check_prompt(incomplete)
        assert False, "预期应阻止未写满章节时执行质检"
    except ValueError as exc:
        assert "暂时无法执行质量检查" in str(exc)
        assert "5" in str(exc)


def test_select_synopsis_again_after_initial_selection_resets_downstream_outputs():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]

    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow["outline_text"] = "旧大纲"
    workflow["outline_feedback"] = "旧反馈"
    workflow["outline_confirmed"] = True
    workflow["chapter_blueprints"] = [{"chapter_number": 1, "title": "第1章", "summary": "摘要", "characters": "甲", "core_event": "事件", "narrative_function": "铺垫"}]
    workflow["chapters"] = [{"chapter_number": 1, "title": "第1章", "content": "旧正文"}]
    workflow["quality_report"] = "旧质检"
    workflow["coherence_report"] = "旧复审"
    workflow["title_candidates"] = [{"index": 1, "title": "旧标题", "category": "直白点题"}]
    workflow["selected_title"] = "旧标题"
    workflow["selected_title_index"] = 1
    workflow["final_output"] = "旧成稿"
    workflow["warnings"] = ["大纲实际生成了 4 章，但当前计划应为 5 章。请调整或重生成大纲后再确认。"]

    workflow = service.select_synopsis(workflow, 4)["data"]["workflow"]

    assert workflow["state"] == "generating_outline"
    assert workflow["selected_synopsis_index"] == 4
    assert workflow["selected_synopsis"] == "第四条导语。"
    assert workflow["outline_text"] == ""
    assert workflow["outline_feedback"] == ""
    assert workflow["outline_confirmed"] is False
    assert workflow["chapter_blueprints"] == []
    assert workflow["chapters"] == []
    assert workflow["quality_report"] == ""
    assert workflow["coherence_report"] == ""
    assert workflow["title_candidates"] == []
    assert workflow["selected_title"] == ""
    assert workflow["selected_title_index"] is None
    assert workflow["final_output"] == ""
    assert workflow["warnings"] == []


def test_record_outline_keeps_target_planned_chapters_when_outline_count_mismatches():
    service = ShortStoryCreatorService()
    workflow = service.start_workflow(
        keywords=["离婚", "清算", "反击"],
        target_total_words=11000,
        chapter_word_target=1000,
    )["data"]["workflow"]
    workflow = _advance_to_synopsis_stage(service, workflow, ["离婚", "清算", "反击"])
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]

    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "丁", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "戊", "core_event": "事件5", "narrative_function": "高潮"},
            {"chapter_number": 6, "title": "第6章", "summary": "摘要6", "characters": "己", "core_event": "事件6", "narrative_function": "推进"},
            {"chapter_number": 7, "title": "第7章", "summary": "摘要7", "characters": "庚", "core_event": "事件7", "narrative_function": "推进"},
            {"chapter_number": 8, "title": "第8章", "summary": "摘要8", "characters": "辛", "core_event": "事件8", "narrative_function": "收束"},
        ],
    )["data"]["workflow"]

    assert workflow["planned_chapters"] == 11
    assert len(workflow["chapter_blueprints"]) == 8
    assert workflow["warnings"]
    assert "大纲实际生成了 8 章，但当前计划应为 11 章" in workflow["warnings"][-1]


def test_confirm_outline_rejects_outline_count_mismatch():
    service = ShortStoryCreatorService()
    workflow = service.start_workflow(
        keywords=["离婚", "清算", "反击"],
        target_total_words=11000,
        chapter_word_target=1000,
    )["data"]["workflow"]
    workflow = _advance_to_synopsis_stage(service, workflow, ["离婚", "清算", "反击"])
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "丁", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "戊", "core_event": "事件5", "narrative_function": "高潮"},
            {"chapter_number": 6, "title": "第6章", "summary": "摘要6", "characters": "己", "core_event": "事件6", "narrative_function": "推进"},
            {"chapter_number": 7, "title": "第7章", "summary": "摘要7", "characters": "庚", "core_event": "事件7", "narrative_function": "推进"},
            {"chapter_number": 8, "title": "第8章", "summary": "摘要8", "characters": "辛", "core_event": "事件8", "narrative_function": "收束"},
        ],
    )["data"]["workflow"]

    try:
        service.confirm_outline(workflow, approved=True)
        assert False, "预期应阻止章节数不匹配的大纲确认"
    except ValueError as exc:
        assert "当前大纲为 8 章" in str(exc)
        assert "应为 11 章" in str(exc)


def test_extract_and_apply_simple_quality_fixes_for_name_consistency():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 章节大纲\n...",
        character_table="沈青：主角\n陈浩：丈夫\n王桂芬：婆婆",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "沈青、陈浩", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "沈青、王桂芬", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "沈青", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "沈青", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "沈青", "core_event": "事件5", "narrative_function": "推进"},
        ],
    )["data"]["workflow"]
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    workflow = service.record_chapter(
        workflow,
        chapter_number=1,
        title="第1章",
        content="陈哲在门口拦住她，陈哲还想解释。",
    )["data"]["workflow"]
    workflow = service.record_chapter(
        workflow,
        chapter_number=2,
        title="第2章",
        content="王秀兰突然冲进门，沈青抬头看着王秀兰。",
    )["data"]["workflow"]
    for chapter_number in range(3, 6):
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=f"第{chapter_number}章",
            content=f"这是第{chapter_number}章正文。",
        )["data"]["workflow"]

    report = """# 分批质检报告

## 批次 1（第1-2章）
第1章：角色一致性 - 丈夫名字“陈哲”与角色表“陈浩”不符
第2章：逻辑合理性 - 王桂芬姓名前后不一致（王秀兰）
"""
    fixes = service.extract_simple_quality_fixes(workflow, report)

    assert [item["from_name"] for item in fixes] == ["陈哲", "王秀兰"]
    assert [item["to_name"] for item in fixes] == ["陈浩", "王桂芬"]

    applied = service.apply_simple_quality_fixes(workflow, report)["data"]
    revised = applied["revised_chapters"]

    assert applied["fixed_count"] == 2
    assert applied["replacement_count"] == 4
    assert revised[0]["content"] == "陈浩在门口拦住她，陈浩还想解释。"
    assert revised[1]["content"] == "王桂芬突然冲进门，沈青抬头看着王桂芬。"
    assert applied["workflow"]["state"] == "quality_checking"
    assert applied["workflow"]["quality_report"] == ""


def test_extract_simple_quality_fixes_supports_direct_name_and_role_descriptions():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="沈青：主角\n陈浩：丈夫\n王桂芬：婆婆",
        timeline="同一雨夜。",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "沈青、陈浩", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "沈青、王桂芬", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "沈青", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "第4章", "summary": "摘要4", "characters": "沈青", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "第5章", "summary": "摘要5", "characters": "沈青", "core_event": "事件5", "narrative_function": "推进"},
        ],
    )["data"]["workflow"]
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    workflow = service.record_chapter(
        workflow,
        chapter_number=1,
        title="第1章",
        content="陈哲在门口拦住她，陈哲还想解释。",
    )["data"]["workflow"]
    workflow = service.record_chapter(
        workflow,
        chapter_number=2,
        title="第2章",
        content="王秀兰突然冲进门，沈青抬头看着王秀兰。",
    )["data"]["workflow"]
    for chapter_number in range(3, 6):
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=f"第{chapter_number}章",
            content=f"这是第{chapter_number}章正文。",
        )["data"]["workflow"]

    report = """# 分批质检报告

## 批次 1（第1-3章）
第1章：逻辑合理性 - 角色“陈浩”在正文中被写作“陈哲”。
第2章：逻辑合理性 - 王桂芬名字前后不一致（王秀兰）
第3章：角色一致性 - 章节内丈夫名字从“陈哲”变更为“陈浩”，与角色表不符。

## 批次 2（第4-6章）
第4章：角色一致性 - 丈夫名字混用（陈哲/陈浩）
第5章：逻辑合理性 - 陈浩父亲名字前后不一致（陈哲）
第6章：逻辑合理性 - 赵姐称呼与大纲（赵姐）不符
"""
    fixes = service.extract_simple_quality_fixes(workflow, report)

    assert [item["chapter_number"] for item in fixes] == [1, 2, 3, 4]
    assert [item["from_name"] for item in fixes] == ["陈哲", "王秀兰", "陈哲", "陈哲"]
    assert [item["to_name"] for item in fixes] == ["陈浩", "王桂芬", "陈浩", "陈浩"]


def test_build_chapter_prompt_rejects_placeholder_blueprint():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
        ],
    )["data"]["workflow"]
    workflow["planned_chapters"] = 2
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    workflow["chapters"] = [
        {"chapter_number": 3, "title": "第3章", "content": "旧正文"},
    ]
    workflow["chapter_blueprints"].append(
        {"chapter_number": 3, "title": "第3章", "summary": "", "characters": "", "core_event": "", "narrative_function": "", "emotion_point": ""}
    )
    try:
        service.build_chapter_prompt(workflow, chapter_number=3)
        assert False, "预期应阻止占位章节蓝图继续生成正文"
    except ValueError as exc:
        assert "缺少有效章节蓝图" in str(exc)


def test_rollback_placeholder_blueprints_clears_bad_chapters_and_returns_to_outline():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
        ],
    )["data"]["workflow"]
    workflow["planned_chapters"] = 3
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    workflow["planned_chapters"] = 5
    workflow["chapter_blueprints"].extend([
        {"chapter_number": 4, "title": "第4章", "summary": "", "characters": "", "core_event": "", "narrative_function": "", "emotion_point": ""},
        {"chapter_number": 5, "title": "第5章", "summary": "", "characters": "", "core_event": "", "narrative_function": "", "emotion_point": ""},
    ])
    workflow["chapters"] = [
        {"chapter_number": 1, "title": "第1章", "content": "第一章"},
        {"chapter_number": 2, "title": "第2章", "content": "第二章"},
        {"chapter_number": 3, "title": "第3章", "content": "第三章"},
        {"chapter_number": 4, "title": "第4章", "content": "第四章"},
        {"chapter_number": 5, "title": "第5章", "content": "第五章"},
    ]
    workflow["quality_report"] = "旧质检"
    workflow["coherence_report"] = "旧复审"
    workflow["selected_title"] = "旧书名"
    workflow["final_output"] = "旧成稿"

    repaired = service.rollback_placeholder_blueprints(workflow)["data"]["workflow"]

    assert repaired["state"] == "awaiting_outline_confirm"
    assert repaired["planned_chapters"] == 3
    assert len(repaired["chapter_blueprints"]) == 3
    assert len(repaired["chapters"]) == 3
    assert repaired["repair_placeholder_numbers"] == [4, 5]
    assert repaired["manual_intervention_required"] is True
    assert repaired["quality_report"] == ""
    assert repaired["coherence_report"] == ""
    assert repaired["selected_title"] == ""
    assert repaired["final_output"] == ""
    assert "已清理第 4、5 章异常正文" in repaired["warnings"][-1]

    repaired["outline_text"] = """### 1. 第1章
- 摘要：摘要1
- 出场角色：甲
- 核心事件：事件1
- 叙事功能：铺垫

### 2. 第2章
- 摘要：摘要2
- 出场角色：乙
- 核心事件：事件2
- 叙事功能：推进

### 3. 第3章
- 摘要：摘要3
- 出场角色：丙
- 核心事件：事件3
- 叙事功能：推进

### 4. 第4章
- 摘要：摘要4
- 出场角色：丁
- 核心事件：事件4
- 叙事功能：推进

### 5. 第5章
- 摘要：摘要5
- 出场角色：戊
- 核心事件：事件5
- 叙事功能：收束
"""
    resumed = service.confirm_outline(repaired, approved=True)["data"]["workflow"]
    assert resumed["state"] == "writing_content"
    assert resumed["repair_placeholder_numbers"] == []
    assert resumed["manual_intervention_required"] is False
    assert resumed["planned_chapters"] == 5
    assert len(resumed["chapter_blueprints"]) == 5
    assert all("已清理第 " not in item for item in resumed["warnings"])


def test_confirm_outline_rejects_unresolved_repair_placeholder_chapters():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)
    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 章节大纲\n...",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "第1章", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "第2章", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "第3章", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
        ],
    )["data"]["workflow"]
    workflow["planned_chapters"] = 3
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]
    workflow["planned_chapters"] = 5
    workflow["repair_placeholder_numbers"] = [4, 5]
    workflow["state"] = "awaiting_outline_confirm"
    workflow["outline_confirmed"] = False
    workflow["outline_text"] = """### 1. 第1章
- 摘要：摘要1
- 出场角色：甲
- 核心事件：事件1
- 叙事功能：铺垫

### 2. 第2章
- 摘要：摘要2
- 出场角色：乙
- 核心事件：事件2
- 叙事功能：推进

### 3. 第3章
- 摘要：摘要3
- 出场角色：丙
- 核心事件：事件3
- 叙事功能：推进

### 4. 第4章
"""

    try:
        service.confirm_outline(workflow, approved=True)
        assert False, "预期应阻止缺失章节未补完时确认大纲"
    except ValueError as exc:
        assert "第 4、5 章" in str(exc)
        assert "填写有效摘要/事件信息" in str(exc)


def test_short_story_parsers_extract_candidates_and_outline():
    synopses = parse_synopsis_candidates(
        """【导语一】（悬疑向）
第一条。

【导语二】（治愈向）
第二条。

【导语三】（暗黑向）
第三条。

【导语四】（反转向）
第四条。

【导语五】（温情向）
第五条。"""
    )
    assert len(synopses) == 5
    assert synopses[0]["style"] == "悬疑向"

    titles = parse_title_candidates(
        """1. 《雨夜失约》—— 类型：直白点题 | 释义：点明冲突
2. 《暗房回声》—— 类型：意象隐喻 | 释义：回声感
3. 《谁没有赴约》—— 类型：悬念引导 | 释义：制造疑问
4. 《迟来的照片》—— 类型：情感共鸣 | 释义：情绪浓
5. 《雨落成像》—— 类型：诗意文艺 | 释义：更文艺"""
    )
    assert len(titles) == 5
    assert titles[1]["title"] == "暗房回声"

    story_tags = parse_story_tags(
        """{
  "main_category": "女性成长",
  "plot_tags": ["大女主", "打脸逆袭"],
  "role_tags": ["医生"],
  "emotion_tags": ["励志"],
  "background_tags": ["现代", "职场"]
}"""
    )
    assert story_tags["main_category"] == "女性成长"
    assert "大女主" in story_tags["all_tags"]
    assert len(story_tags["all_tags"]) >= 4

    outline = parse_outline_payload(
        """## 角色表
周岚 | 摄影师 | 与顾原是旧友

## 时间线
雨夜至次日清晨

## 章节大纲
### 1. 归城
- 摘要：回到旧地
- 出场角色：周岚
- 核心事件：归来
- 叙事功能：铺垫

### 2. 失约
- 摘要：发现异常
- 出场角色：周岚、顾原
- 核心事件：追查失约
- 叙事功能：推进"""
    )
    assert "摄影师" in outline["character_table"]
    assert "雨夜" in outline["timeline"]
    assert len(outline["chapter_blueprints"]) == 2
    assert outline["chapter_blueprints"][0]["chapter_number"] == 1
    assert outline["chapter_blueprints"][0]["title"] == "归城"

    chapters = parse_chapters_from_full_text(
        """### 1. 归城
第一段。

第二段。

### 2. 失约
第三段。"""
    )
    assert len(chapters) == 2
    assert chapters[0]["chapter_number"] == 1
    assert chapters[0]["title"] == "归城"


def test_outline_parser_accepts_non_bullet_and_alias_fields():
    outline = parse_outline_payload(
        """## 角色表
周岚 | 摄影师 | 与顾原是旧友

## 时间线
雨夜至次日清晨

## 章节大纲
### 1. 归城
摘要：回到旧地
出场人物：周岚
**核心事件**：归来
叙事功能：铺垫
【情绪节点】雨夜重返旧城的失落感

### 2. 失约
- **摘要**：发现异常
- 主要角色：周岚、顾原
- 关键事件：追查失约
- 剧情作用：推进"""
    )

    assert outline["chapter_blueprints"][0]["summary"] == "回到旧地"
    assert outline["chapter_blueprints"][0]["characters"] == "周岚"
    assert outline["chapter_blueprints"][0]["core_event"] == "归来"
    assert outline["chapter_blueprints"][0]["narrative_function"] == "铺垫"
    assert outline["chapter_blueprints"][0]["emotion_point"] == "雨夜重返旧城的失落感"
    assert outline["chapter_blueprints"][1]["characters"] == "周岚、顾原"
    assert outline["chapter_blueprints"][1]["core_event"] == "追查失约"
    assert outline["chapter_blueprints"][1]["narrative_function"] == "推进"


def test_short_story_warns_when_keywords_exceed_ten():
    service = ShortStoryCreatorService()

    workflow = service.start_workflow(
        keywords=[f"词条{i}" for i in range(1, 13)],
        target_total_words=8000,
    )["data"]["workflow"]

    assert workflow["planned_chapters"] == 8
    assert workflow["warnings"]
    assert workflow["chapter_word_min"] == 900
    assert workflow["chapter_word_max"] == 1100


def test_short_story_preserves_target_words_above_eight_thousand():
    service = ShortStoryCreatorService()

    workflow = service.start_workflow(
        keywords=["旧相机", "失约", "雨夜"],
        target_total_words=13000,
    )["data"]["workflow"]

    assert workflow["target_total_words"] == 13000
    assert workflow["planned_chapters"] == 13
    assert workflow["min_chapters"] == 13
    assert workflow["chapter_word_min"] == 900
    assert workflow["chapter_word_max"] == 1100


def test_short_story_supports_custom_chapter_word_target():
    service = ShortStoryCreatorService()

    workflow = service.start_workflow(
        keywords=["旧相机", "失约", "雨夜"],
        target_total_words=9000,
        chapter_word_target=1500,
    )["data"]["workflow"]

    assert workflow["target_total_words"] == 9000
    assert workflow["custom_chapter_word_target"] == 1500
    assert workflow["chapter_word_target"] == 1500
    assert workflow["chapter_word_min"] == 1400
    assert workflow["chapter_word_max"] == 1600
    assert workflow["planned_chapters"] == 6

    workflow = _advance_to_synopsis_stage(service, workflow, ["旧相机", "失约", "雨夜"])

    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]

    outline_prompt = service.build_outline_prompt(workflow)
    assert "每章正文控制在 1400~1600 字左右，平均目标约 1500 字" in outline_prompt["data"]["prompt"]


def test_editing_chapter_after_review_resets_downstream_outputs():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)

    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "归城", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "失约", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "转场", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "逼近", "summary": "摘要4", "characters": "丁", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "冲洗", "summary": "摘要5", "characters": "戊", "core_event": "事件5", "narrative_function": "高潮"},
        ],
    )["data"]["workflow"]
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]

    for chapter_number in range(1, 6):
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=f"{chapter_number}. 示例章节",
            content=f"这是第{chapter_number}章正文。",
        )["data"]["workflow"]

    workflow = service.record_quality_check(
        workflow,
        report="✅ 质量检查通过，无需修改。",
        passed=True,
    )["data"]["workflow"]
    workflow = service.record_coherence_review(
        workflow,
        report="✅ 复审通过，正文定稿。",
        passed=True,
    )["data"]["workflow"]
    workflow = service.register_title_candidates(
        workflow,
        [
            {"title": "题目一", "category": "直白点题"},
            {"title": "题目二", "category": "意象隐喻"},
            {"title": "题目三", "category": "悬念引导"},
            {"title": "题目四", "category": "情感共鸣"},
            {"title": "题目五", "category": "诗意文艺"},
        ],
    )["data"]["workflow"]
    workflow = service.select_title(workflow, 2)["data"]["workflow"]
    workflow = service.assemble_output(workflow)["data"]["workflow"]

    updated = service.record_chapter(
        workflow,
        chapter_number=2,
        title="2. 失约",
        content="这是修改后的第二章正文。",
    )["data"]["workflow"]

    assert updated["state"] == "quality_checking"
    assert updated["quality_report"] == ""
    assert updated["coherence_report"] == ""
    assert updated["title_candidates"] == []
    assert updated["selected_title"] == ""
    assert updated["selected_title_index"] is None
    assert updated["final_output"] == ""


def test_build_chapter_prompt_is_available_after_quality_and_coherence():
    service = ShortStoryCreatorService()
    workflow = _make_started_workflow(service)

    workflow = service.register_synopsis_candidates(
        workflow,
        [
            {"style": "悬疑向", "content": "第一条导语。"},
            {"style": "温情向", "content": "第二条导语。"},
            {"style": "反转向", "content": "第三条导语。"},
            {"style": "暗黑向", "content": "第四条导语。"},
            {"style": "治愈向", "content": "第五条导语。"},
        ],
    )["data"]["workflow"]
    workflow = service.select_synopsis(workflow, 1)["data"]["workflow"]
    workflow = service.record_outline(
        workflow,
        outline_text="## 角色表\n...\n## 时间线\n...\n## 章节大纲\n...",
        character_table="角色表",
        timeline="时间线",
        chapter_blueprints=[
            {"chapter_number": 1, "title": "归城", "summary": "摘要1", "characters": "甲", "core_event": "事件1", "narrative_function": "铺垫"},
            {"chapter_number": 2, "title": "失约", "summary": "摘要2", "characters": "乙", "core_event": "事件2", "narrative_function": "推进"},
            {"chapter_number": 3, "title": "转场", "summary": "摘要3", "characters": "丙", "core_event": "事件3", "narrative_function": "推进"},
            {"chapter_number": 4, "title": "逼近", "summary": "摘要4", "characters": "丁", "core_event": "事件4", "narrative_function": "推进"},
            {"chapter_number": 5, "title": "冲洗", "summary": "摘要5", "characters": "戊", "core_event": "事件5", "narrative_function": "高潮"},
        ],
    )["data"]["workflow"]
    workflow = service.confirm_outline(workflow, approved=True)["data"]["workflow"]

    for chapter_number in range(1, 6):
        workflow = service.record_chapter(
            workflow,
            chapter_number=chapter_number,
            title=f"{chapter_number}. 示例章节",
            content=f"这是第{chapter_number}章正文。",
        )["data"]["workflow"]

    assert workflow["state"] == "quality_checking"
    quality_prompt = service.build_chapter_prompt(workflow, chapter_number=2)["data"]["prompt"]
    assert "摘要：摘要2" in quality_prompt
    assert "核心事件：事件2" in quality_prompt

    workflow = service.record_quality_check(
        workflow,
        report="✅ 质量检查通过，无需修改。",
        passed=True,
    )["data"]["workflow"]
    assert workflow["state"] == "coherence_reviewing"

    coherence_prompt = service.build_chapter_prompt(workflow, chapter_number=2)["data"]["prompt"]
    assert "摘要：摘要2" in coherence_prompt
    assert "核心事件：事件2" in coherence_prompt
