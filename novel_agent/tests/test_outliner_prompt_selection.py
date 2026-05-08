import pytest

from novel_agent.agents.outliner import OutlinerAgent


class RecordingOutliner(OutlinerAgent):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _render_custom_task_prompt(self, task_name: str, **variables):
        assert task_name == "create_outline"
        return "CUSTOM OUTLINE PROMPT"

    async def call_llm(self, messages, *args, **kwargs):
        self.calls.append(messages)
        return '{"title":"自定义大纲","global_outline":"按自定义提示词输出","chapters":[{"title":"第1章","summary":"开局"}]}'


@pytest.mark.asyncio
async def test_outliner_uses_custom_create_outline_prompt_before_builtin_chain():
    outliner = RecordingOutliner()

    result = await outliner.execute({"world": {"name": "测试世界"}, "plot_idea": "测试剧情"})

    assert result["prompt_source"] == "custom_task_prompt"
    assert outliner.calls == [[{"role": "user", "content": "CUSTOM OUTLINE PROMPT"}]]
    assert result["outline"]["global_outline"] == "按自定义提示词输出"
