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


def test_validator_detects_ai_style_sentences():
    validator = ContentValidator()
    content = (
        "这一切都让他明白，自己已经没有退路。"
        "显然，他赌对了。"
        "这意味着敌人已经摸到了门外。"
        "而这只是开始。"
    )

    result = validator.validate(content, chapter_number=5)
    types = {v.violation_type for v in result.violations}

    assert ViolationType.SUMMARY_SENTENCE in types
    assert ViolationType.JUDGMENT_SENTENCE in types
    assert ViolationType.EXPLANATORY_SENTENCE in types
    assert ViolationType.CLIFFHANGER_CLICHE in types


def test_validator_auto_fixes_ai_style_sentences():
    validator = ContentValidator()
    content = (
        "这一切都让他明白，自己已经没有退路。\n"
        "显然，他赌对了。\n"
        "这意味着敌人已经摸到了门外。\n"
        "他不知道的是，窗外已经有人拔刀。"
    )

    result = validator.validate(content, chapter_number=6, auto_fix=True)

    assert result.auto_fixed is True
    assert result.fixed_content is not None
    assert "这一切都让" not in result.fixed_content
    assert "显然，" not in result.fixed_content
    assert "这意味着" not in result.fixed_content
    assert "他不知道的是" not in result.fixed_content
    assert "窗外已经有人拔刀" in result.fixed_content


def test_validator_detects_high_frequency_trope_overuse():
    validator = ContentValidator()
    content = (
        "夜风冰冷，刀锋也冰冷。"
        "那股刺骨的寒意顺着门缝往里钻。"
        "他心中一紧，抬头时只见檐下风声凛冽。"
        "那双嘴角上扬的脸，在烛火里更显冰冷。"
    )

    result = validator.validate(content, chapter_number=7)
    trope_violations = [v for v in result.violations if v.violation_type == ViolationType.HIGH_FREQUENCY_TROPE]

    assert trope_violations


def test_validator_detects_consecutive_abstract_endings():
    validator = ContentValidator()
    content = (
        "门外的脚步停住了。这一切都让他意识到，屋里已经不安全了。\n\n"
        "桌上的烛火晃了一下。这意味着真正的追兵已经摸到院门口了。"
    )

    result = validator.validate(content, chapter_number=8)
    density_violations = [v for v in result.violations if v.violation_type == ViolationType.ABSTRACT_ENDING_DENSITY]

    assert density_violations


def test_validator_detects_mechanical_emotion_templates():
    validator = ContentValidator()
    content = (
        "他心中一紧，握刀的手慢了半拍。"
        "门轴一响，他瞳孔一缩，呼吸一滞。"
        "对面的人只是抬了抬眼，他的脸色微变。"
    )

    result = validator.validate(content, chapter_number=9)
    emotion_violations = [v for v in result.violations if v.violation_type == ViolationType.MECHANICAL_EMOTION]

    assert emotion_violations


def test_validator_detects_four_char_stacking():
    validator = ContentValidator()
    content = (
        "院中一片鸦雀无声，四周杀气腾腾。"
        "风声鹤唳之间，众人若隐若现。"
        "那股意味深长的笑，让人不寒而栗。"
    )

    result = validator.validate(content, chapter_number=10)
    four_char_violations = [v for v in result.violations if v.violation_type == ViolationType.FOUR_CHAR_STACKING]

    assert four_char_violations


def test_validator_detects_repetitive_wording():
    validator = ContentValidator()
    content = (
        "那道脚步声越来越近，像是踩在门槛上。"
        "他听着那道脚步声越来越近，手心慢慢出汗。"
        "等他抬头时，那道脚步声越来越近，已经停在门外。"
    )

    result = validator.validate(content, chapter_number=11)
    repetitive_violations = [v for v in result.violations if v.violation_type == ViolationType.REPETITIVE_WORDING]

    assert repetitive_violations


def test_validator_detects_symmetric_parallelism():
    validator = ContentValidator()
    content = "他看见血，他看见火，他看见那扇门后的人影。"

    result = validator.validate(content, chapter_number=12)
    parallel_violations = [v for v in result.violations if v.violation_type == ViolationType.SYMMETRIC_PARALLELISM]

    assert parallel_violations


def test_validator_detects_paragraph_start_rhythm():
    validator = ContentValidator()
    content = (
        "他站在院门前，没说话。\n\n"
        "他看着台阶上的血，还是没说话。\n\n"
        "他抬手推门，门轴发出一声轻响。"
    )

    result = validator.validate(content, chapter_number=13)
    rhythm_violations = [v for v in result.violations if v.violation_type == ViolationType.PARAGRAPH_START_RHYTHM]

    assert rhythm_violations
