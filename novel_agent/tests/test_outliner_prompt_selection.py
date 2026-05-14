import json

import pytest

from novel_agent.agents.outliner import OutlinerAgent


def _valid_outline(volume_count=1):
    return {
        "title": "归墟录",
        "intro": "少年重返旧城追查旧案。",
        "story_synopsis": "林渡在宗门覆灭后回到旧城，借归墟秘术查清旧案并重建秩序。",
        "global_outline": (
            "书名：《归墟录》\n简介：少年重返旧城追查旧案。\n"
            "故事梗概：林渡在宗门覆灭后回到旧城，借归墟秘术查清旧案并重建秩序。\n"
            "一【力量体系】：归墟秘术以记忆与代价驱动。\n"
            "二【世界地图】：旧城、归墟遗址与宗门废墟彼此牵连。\n"
            "三【中心思想】：真相与责任必须同时承担。\n"
            "四【矛盾冲突】：旧王朝余党与新秩序之间的暗战。\n"
            "五【前期剧情】：林渡回城查案，逐步发现内鬼。\n"
            "六【叙事节奏】：压抑铺垫后逐步反击。\n"
            "七【小说卖点】：旧案反转、能力代价、群像复仇。\n"
            "八【角色设定】：林渡冷静克制，因旧案学会信任同伴。"
        ),
        "theme": "真相与责任",
        "main_conflict": "旧王朝余党试图掩盖宗门覆灭真相。",
        "selling_points": "旧案反转与压抑后的反击爽点。",
        "ending_direction": "林渡公开真相并建立新的守夜盟约。",
        "plot_threads": [
            {
                "id": "main",
                "title": "旧案追凶",
                "objective": "查清宗门覆灭真相",
                "scope": "全书",
            }
        ],
        "volumes": [
            {
                "volume_number": index,
                "volume_title": f"旧城归来{index}",
                "volume_summary": "林渡回到旧城，查出旧案第一层真相。",
                "core_conflict": "林渡与旧城守备之间的试探和冲突。",
                "protagonist_growth": "从独自复仇转向接受同伴协作。",
                "volume_climax": "林渡在旧城夜审中公开第一名内鬼。",
                "key_events": ["回城查案", "结识同盟", "夜审内鬼"],
                "foreshadowing": "归墟遗址中的空棺指向更高层黑手。",
            }
            for index in range(1, volume_count + 1)
        ],
        "notes": "后续章纲需要保持压抑递进。",
    }


class RecordingOutliner(OutlinerAgent):
    def __init__(self, responses):
        super().__init__()
        self.calls = []
        self.responses = list(responses)

    def _render_custom_task_prompt(self, task_name: str, **variables):
        assert task_name == "create_outline"
        return "CUSTOM OUTLINE PROMPT"

    async def call_llm(self, messages, *args, **kwargs):
        self.calls.append(messages)
        response = self.responses.pop(0) if self.responses else _valid_outline()
        return json.dumps(response, ensure_ascii=False)


@pytest.mark.asyncio
async def test_outliner_keeps_agent_protocol_when_custom_task_prompt_exists():
    outliner = RecordingOutliner([_valid_outline(volume_count=1)])

    result = await outliner.execute({
        "world": {"name": "测试世界"},
        "plot_idea": "测试剧情",
        "volume_count": 1,
    })

    assert result["prompt_source"] == "system_prompt_with_custom_task_prompt"
    assert len(outliner.calls) == 1
    prompt = outliner.calls[0][0]["content"]
    assert "CUSTOM OUTLINE PROMPT" in prompt
    assert "不能改变系统提示词规定的 JSON 字段" in prompt
    assert "禁止输出顶层 chapters" in prompt
    assert "不要输出作者署名" in prompt
    assert "title、author、intro" not in prompt
    assert result["outline"]["global_outline"].startswith("书名")


@pytest.mark.asyncio
async def test_outliner_retries_chapter_like_volumes_before_accepting_output():
    invalid_outline = {
        "title": "错点鸳鸯",
        "global_outline": "王瑾瑜设计画舫选夫，意外选中裴昭。",
        "volumes": [
            {
                "volume_number": index,
                "volume_title": "错点鸳鸯",
                "volume_summary": f"第{index}章事件被误写成卷。",
                "core_conflict": "婚约误会",
                "protagonist_growth": "开始动摇",
                "volume_climax": "误会升级",
                "key_events": [f"第{index}章事件"],
            }
            for index in range(1, 8)
        ],
    }
    outliner = RecordingOutliner([invalid_outline, _valid_outline(volume_count=1)])

    result = await outliner.execute({
        "world": {"name": "天齐"},
        "plot_idea": "画舫选夫误定婚约",
        "volume_count": 1,
    })

    assert result["success"] is True
    assert len(outliner.calls) == 2
    retry_prompt = outliner.calls[1][0]["content"]
    assert "上一次输出不符合 Outliner 协议" in retry_prompt
    assert "不要把章节事件拆成多个卷" in retry_prompt
    assert len(result["outline"]["volumes"]) == 1


@pytest.mark.asyncio
async def test_outliner_retries_chapter_like_key_events_without_chapter_markers():
    invalid_outline = _valid_outline(volume_count=1)
    invalid_outline["volumes"][0]["key_events"] = [
        "皇帝下旨赐婚，太子与商户女大婚",
        "新婚夜分房，两人误会加深",
        "女主整顿嫁妆铺子展露聪慧",
        "上元节同游西市，男主初显温柔",
        "国公府设计，女主意外卷入",
        "太后寿宴风波，男主当众护妻",
        "京郊别院敞开心扉",
        "联手应对最后危机",
    ]
    outliner = RecordingOutliner([invalid_outline, _valid_outline(volume_count=1)])

    result = await outliner.execute({
        "world": {"name": "承安朝"},
        "plot_idea": "赐婚甜宠",
        "volume_count": 1,
        "chapters_per_volume": 17,
    })

    assert result["success"] is True
    assert len(outliner.calls) == 2
    retry_prompt = outliner.calls[1][0]["content"]
    assert "key_events 数量过多" in retry_prompt
    assert "合并为 3-5 个卷级阶段事件" in retry_prompt


@pytest.mark.asyncio
async def test_outliner_retries_ai_author_and_duplicated_global_volume_text():
    invalid_outline = _valid_outline(volume_count=1)
    invalid_outline["author"] = "AI助手"
    invalid_outline["global_outline"] = (
        "书名：《归墟录》\n作者：AI助手\n简介：少年重返旧城追查旧案。\n"
        "故事梗概：林渡回城查案。\n一【力量体系】：归墟秘术。\n"
        "四【矛盾冲突】：旧王朝余党遮掩真相。"
    )
    invalid_outline["volumes"] = [
        {
            "volume_number": 1,
            "volume_title": "归墟录",
            "volume_summary": invalid_outline["global_outline"],
            "core_conflict": invalid_outline["global_outline"],
            "protagonist_growth": invalid_outline["global_outline"],
            "volume_climax": invalid_outline["global_outline"],
            "key_events": [invalid_outline["global_outline"]],
            "foreshadowing": "空棺伏笔指向幕后黑手。",
        }
    ]
    outliner = RecordingOutliner([invalid_outline, _valid_outline(volume_count=1)])

    result = await outliner.execute({
        "world": {"name": "旧城"},
        "plot_idea": "旧案追凶",
        "volume_count": 1,
    })

    assert result["success"] is True
    assert len(outliner.calls) == 2
    retry_prompt = outliner.calls[1][0]["content"]
    assert "不能写 AI 助手类署名" in retry_prompt
    assert "global_outline 与 volumes 内容高度重复" in retry_prompt
    assert "author" not in result["outline"]
