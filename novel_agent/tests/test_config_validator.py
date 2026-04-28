"""
测试配置验证器
"""

import pytest
from pathlib import Path
from novel_agent.web.config_validator import ConfigValidator, validate_startup_config, ConfigValidationError


def test_config_validator_initialization():
    """测试配置验证器初始化"""
    validator = ConfigValidator()
    assert validator.errors == []
    assert validator.warnings == []


def test_validate_all_returns_tuple():
    """测试 validate_all 返回正确的元组"""
    validator = ConfigValidator()
    result = validator.validate_all()

    assert isinstance(result, tuple)
    assert len(result) == 3
    is_valid, errors, warnings = result
    assert isinstance(is_valid, bool)
    assert isinstance(errors, list)
    assert isinstance(warnings, list)


def test_validate_paths():
    """测试路径验证"""
    validator = ConfigValidator()
    validator._validate_paths()

    # 应该没有错误（路径会自动创建）
    assert len(validator.errors) == 0


def test_validate_knowledge_base_missing_config():
    """测试知识库配置缺失的情况"""
    validator = ConfigValidator()
    validator._validate_knowledge_base()

    # 应该有警告（配置文件可能不存在或未配置）
    # 但不应该有错误
    assert len(validator.errors) == 0


def test_validate_llm_config():
    """测试 LLM 配置验证"""
    validator = ConfigValidator()
    validator._validate_llm_config()

    # 可能有错误或警告，取决于环境配置
    # 这里只验证不会抛出异常
    assert isinstance(validator.errors, list)
    assert isinstance(validator.warnings, list)


def test_validate_skills():
    """测试 Skill 配置验证"""
    validator = ConfigValidator()
    validator._validate_skills()

    # 应该不会抛出异常
    assert isinstance(validator.warnings, list)


def test_validate_skills_auto_bootstraps_missing_config(tmp_path):
    """缺失的 Skill 配置应从示例自动创建。"""
    app_dir = tmp_path / "novel_agent"
    (app_dir / "data").mkdir(parents=True, exist_ok=True)

    skill_dir = tmp_path / "skills" / "demo_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
    example_content = '{\n  "enabled": true\n}\n'
    (skill_dir / "config.example.json").write_text(example_content, encoding="utf-8")

    validator = ConfigValidator(app_dir=app_dir, project_root=tmp_path)
    validator._validate_skills()

    config_path = skill_dir / "config.json"
    assert config_path.exists()
    assert config_path.read_text(encoding="utf-8") == example_content
    assert any("已根据示例自动创建" in warning for warning in validator.warnings)


def test_validate_port():
    """测试端口验证"""
    validator = ConfigValidator()
    validator._validate_port()

    # 应该不会抛出异常
    assert isinstance(validator.warnings, list)


def test_validate_startup_config_with_errors(monkeypatch):
    """测试启动配置验证（有错误的情况）"""
    def mock_validate_all(self):
        self.errors = ["测试错误"]
        self.warnings = []
        return False, self.errors, self.warnings

    monkeypatch.setattr(ConfigValidator, "validate_all", mock_validate_all)

    with pytest.raises(ConfigValidationError):
        validate_startup_config()


def test_validate_startup_config_with_warnings(monkeypatch):
    """测试启动配置验证（只有警告的情况）"""
    def mock_validate_all(self):
        self.errors = []
        self.warnings = ["测试警告"]
        return True, self.errors, self.warnings

    monkeypatch.setattr(ConfigValidator, "validate_all", mock_validate_all)

    # 应该不抛出异常
    result = validate_startup_config()
    assert result is True


def test_validate_startup_config_success(monkeypatch):
    """测试启动配置验证（成功的情况）"""
    def mock_validate_all(self):
        self.errors = []
        self.warnings = []
        return True, self.errors, self.warnings

    monkeypatch.setattr(ConfigValidator, "validate_all", mock_validate_all)

    result = validate_startup_config()
    assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
