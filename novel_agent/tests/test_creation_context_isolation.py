from novel_agent.agents.router_agent import RouterAgent


def test_creation_discussion_context_filters_internal_status_and_ui_chrome():
    router = RouterAgent()

    context = {
        "conversation_history": [
            {"role": "system", "content": "系统状态：不要写入故事"},
            {"role": "user", "content": "我要古代甜宠，女主机灵，男主清冷。"},
            {"role": "assistant", "content": "Outliner 正在执行: 生成大纲\n分卷规划\n返回列表"},
            {"role": "assistant", "content": "已确认：误选婚约是主线，前期先甜后虐。"},
        ],
        "collected_info": {
            "theme": "古代甜宠",
            "plot_idea": "画舫选夫误定婚约",
            "ui_panel_title": "全书大纲内容",
        },
    }

    discussion = router._build_discussion_context(context, "请开始创建")

    assert "我要古代甜宠" in discussion
    assert "已确认：误选婚约是主线" in discussion
    assert "theme: 古代甜宠" in discussion
    assert "plot_idea: 画舫选夫误定婚约" in discussion
    assert "Outliner 正在执行" not in discussion
    assert "分卷规划" not in discussion
    assert "返回列表" not in discussion
    assert "ui_panel_title" not in discussion
    assert "系统状态" not in discussion
