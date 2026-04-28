"""
结构化输出协议测试
"""

import pytest
from novel_agent.agents.structured_output import (
    StructuredOutputValidator,
    StructuredOutputHelper
)
from novel_agent.prompts.prompt_manager import get_prompt_manager


class TestStructuredOutputValidator:
    """测试结构化输出验证器"""
    
    def test_check_linear_flow_violations(self):
        """测试线性流检测"""
        text = "首先，我们需要做A。然后，我们做B。接着，完成C。"
        violations = StructuredOutputValidator.check_linear_flow(text)
        assert len(violations) > 0
        assert any("首先" in v for v in violations)
    
    def test_check_linear_flow_clean(self):
        """测试无线性流的文本"""
        text = "我们需要完成以下任务：\n- 任务A\n- 任务B\n- 任务C"
        violations = StructuredOutputValidator.check_linear_flow(text)
        assert len(violations) == 0
    
    def test_check_noise_violations(self):
        """测试口语化噪音检测"""
        text = "根据搜索结果，我们发现了以下内容。总的来说，这是一个好方案。希望这对您有帮助。"
        violations = StructuredOutputValidator.check_noise(text)
        assert len(violations) > 0
    
    def test_check_noise_clean(self):
        """测试无噪音的文本"""
        text = "我们发现了以下内容：\n- 内容A\n- 内容B"
        violations = StructuredOutputValidator.check_noise(text)
        assert len(violations) == 0
    
    def test_check_structure_with_headers(self):
        """测试结构检测 - 有标题"""
        text = """# 核心结论
这是结论

# 详细分析
这是分析"""
        structure = StructuredOutputValidator.check_structure(text)
        assert structure["h1_count"] == 2
        assert structure["has_structure"] is True
    
    def test_check_structure_with_table(self):
        """测试结构检测 - 有表格"""
        text = """| 维度 | 方案A | 方案B |
|------|-------|-------|
| 性能 | 高 | 中 |"""
        structure = StructuredOutputValidator.check_structure(text)
        assert structure["table_count"] > 0
        assert structure["has_structure"] is True
    
    def test_check_structure_with_lists(self):
        """测试结构检测 - 有列表"""
        text = """1. 第一步
2. 第二步

- 要点A
- 要点B"""
        structure = StructuredOutputValidator.check_structure(text)
        assert structure["ordered_list_count"] == 2
        assert structure["unordered_list_count"] == 2
        assert structure["has_structure"] is True
    
    def test_validate_good_text(self):
        """测试验证 - 良好文本"""
        text = """# 核心结论

**这是一个优秀的方案**

## 详细分析

| 维度 | 评分 |
|------|------|
| 性能 | 高 |

## 实施步骤

1. **准备环境**：配置必要的工具
2. **执行部署**：按照流程部署

> 注意：需要管理员权限"""
        
        result = StructuredOutputValidator.validate(text)
        assert result["is_valid"] is True
        assert len(result["linear_flow_violations"]) == 0
        assert len(result["noise_violations"]) == 0
    
    def test_validate_bad_text(self):
        """测试验证 - 不良文本"""
        text = """首先，我们需要分析需求。然后，根据搜索结果，我们发现了一些问题。
接着，我们制定方案。总的来说，这是一个可行的方案。希望这对您有帮助。"""
        
        result = StructuredOutputValidator.validate(text)
        assert result["is_valid"] is False
        assert len(result["linear_flow_violations"]) > 0
        assert len(result["noise_violations"]) > 0
        assert len(result["suggestions"]) > 0

    def test_validate_json_output_good(self):
        """测试 JSON 型输出验证 - 合法 JSON"""
        text = """{
  "passed": true,
  "total_score": 88,
  "suggestions": ["补强第3段动作细节"],
  "issues": []
}"""
        result = StructuredOutputValidator.validate_json_output(
            text,
            required_fields=["passed", "total_score", "suggestions"],
        )
        assert result["is_valid"] is True
        assert result["missing_fields"] == []

    def test_validate_json_output_bad_with_markdown_and_missing_fields(self):
        """测试 JSON 型输出验证 - 混入 Markdown 且缺字段"""
        text = """# 评估结果
{"passed": true, "issues": []}"""
        result = StructuredOutputValidator.validate_json_output(
            text,
            required_fields=["passed", "total_score"],
        )
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0
        assert "total_score" in result["missing_fields"]

    def test_validate_prose_output_bad(self):
        """测试正文型输出反结构化违规检测"""
        text = """# 润色说明

1. 修改句式
2. 调整节奏

| 项目 | 内容 |
| --- | --- |
| 说明 | 示例 |"""
        result = StructuredOutputValidator.validate_prose_output(text)
        assert result["is_valid"] is False
        assert len(result["violations"]) > 0

    def test_validate_prose_output_good(self):
        """测试正文型输出正常文本"""
        text = "张少冲来。林枫眼神一凝，迎了上去。拳风炸开，碎石四溅。"
        result = StructuredOutputValidator.validate_prose_output(text)
        assert result["is_valid"] is True


class TestStructuredOutputHelper:
    """测试结构化输出辅助工具"""
    
    def test_format_comparison(self):
        """测试格式化对比表格"""
        items = [
            {"name": "方案A", "性能": "高", "成本": "低"},
            {"name": "方案B", "性能": "中", "成本": "中"}
        ]
        dimensions = ["性能", "成本"]
        
        result = StructuredOutputHelper.format_comparison(items, dimensions)
        assert "| 维度 | 方案A | 方案B |" in result
        assert "| 性能 | 高 | 中 |" in result
        assert "| 成本 | 低 | 中 |" in result
    
    def test_format_steps(self):
        """测试格式化步骤"""
        steps = [
            "准备环境：安装必要的工具",
            "配置参数：设置系统参数",
            "执行部署"
        ]
        
        result = StructuredOutputHelper.format_steps(steps)
        assert "1. **准备环境**：安装必要的工具" in result
        assert "2. **配置参数**：设置系统参数" in result
        assert "3. 执行部署" in result
    
    def test_format_explanation(self):
        """测试格式化解释"""
        items = ["要点A", "要点B", "要点C"]
        
        result = StructuredOutputHelper.format_explanation(items)
        assert "- 要点A" in result
        assert "- 要点B" in result
        assert "- 要点C" in result
    
    def test_add_conclusion_prefix(self):
        """测试添加核心结论前置"""
        result = StructuredOutputHelper.add_conclusion_prefix(
            "核心分析",
            "这是一个优秀的方案"
        )
        assert "# 核心分析" in result
        assert "**这是一个优秀的方案**" in result
    
    def test_add_warning_block(self):
        """测试添加警告块"""
        warnings = ["需要管理员权限", "可能影响性能"]
        
        result = StructuredOutputHelper.add_warning_block(warnings)
        assert "> 需要管理员权限" in result
        assert "> 可能影响性能" in result
    
    def test_add_warning_block_empty(self):
        """测试空警告列表"""
        result = StructuredOutputHelper.add_warning_block([])
        assert result == ""


class TestPromptLayerConsistency:
    """测试提示词分层与来源一致性"""
    
    def test_prompt_manager_prefers_builtin_prompt_file_for_worldbuilder(self):
        """测试 PromptManager 优先读取与运行时一致的文件提示词"""
        prompt = get_prompt_manager().get_system_prompt_raw("worldbuilder")
        assert "JSON型结构化输出协议" in prompt
        assert "只输出合法 JSON" in prompt
    
    def test_prompt_manager_prefers_builtin_prompt_file_for_polisher(self):
        """测试正文型模式通过文件提示词暴露豁免协议"""
        prompt = get_prompt_manager().get_system_prompt_raw("polisher")
        assert "正文型输出豁免协议" in prompt
        assert "只输出润色后的最终正文" in prompt
    
    def test_prompt_manager_prefers_builtin_prompt_file_for_communicator(self):
        """测试对话型模式通过文件提示词暴露按场景启用规则"""
        prompt = get_prompt_manager().get_system_prompt_raw("communicator")
        assert "对话型结构化输出协议" in prompt
        assert "轻量豁免场景" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])