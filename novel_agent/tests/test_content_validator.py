"""内容验证器回归测试。"""

from novel_agent.agents.content_validator import ContentValidator, ViolationType


class DummyConstraintStore:
    def get_death_constraints(self):
        return ["张三"]

    def search_constraints(self, top_k=100):
        return [
            {
                "document": "李四能力/境界变化：李四突破至金丹，实力大进。",
                "constraint_types": ["character_power"],
            }
        ]


def test_validator_loads_power_levels_and_detects_regression():
    validator = ContentValidator(constraint_store=DummyConstraintStore())
    validator.load_constraints()

    result = validator.validate("李四如今竟然还是筑基修为。", chapter_number=12)
    types = [v.violation_type for v in result.violations]

    assert ViolationType.POWER_REGRESSION in types


def test_validator_detects_timeline_conflict_pattern():
    validator = ContentValidator()

    result = validator.validate("他昨天还在城里，明天却说刚刚经历了半年前的大战。", chapter_number=3)
    timeline_violations = [v for v in result.violations if v.violation_type == ViolationType.TIMELINE_ERROR]

    assert timeline_violations

