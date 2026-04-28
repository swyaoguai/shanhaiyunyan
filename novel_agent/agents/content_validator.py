# -*- coding: utf-8 -*-
"""
内容验证器模块

除了通过提示词约束外，这是第二道防线：
在章节生成后验证内容是否违反已知的剧情设定，
如果违反则标记或自动修正。

验证方法：
1. 规则匹配检测 - 检测已知死亡角色是否以活人身份出现
2. 设定冲突检测 - 检测能力/境界是否倒退
3. 事实矛盾检测 - 检测已揭露秘密是否被遗忘
4. 语义相似度检测 - 使用向量相似度检测潜在冲突
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

_POWER_LEVELS_ORDER = [
    "练气", "筑基", "结丹", "金丹", "元婴",
    "化神", "炼虚", "合道", "大乘", "渡劫"
]
_POWER_LEVEL_RANK = {name: index for index, name in enumerate(_POWER_LEVELS_ORDER)}
_TIMELINE_BACKWARD_PATTERNS = [
    re.compile(r"(昨天|前日|前天).{0,16}(明天|次日|后天)"),
    re.compile(r"(刚刚|方才|先前).{0,16}(一个月前|半年前|多年前)"),
]
_TIMELINE_BACKWARD_HINTS = ["随后", "接着", "然后", "之后", "紧接着"]
_TIMELINE_PAST_HINTS = ["三天前", "一个月前", "半年前", "多年前", "当年"]
_ROLE_NAME_SUFFIXES = ["突破", "能力", "境界", "变化", "实力", "修为", "达到", "进入", "当前"]
_SENTENCE_END_CHARS = "。！？!?；;"
_SUMMARY_SENTENCE_PATTERNS = [
    re.compile(r"(这一切|这一幕|这一刻|这一夜|所有的这些|所有的这一切|所有的一切).{0,24}(让|令|使|说明|意味着)"),
    re.compile(r"(一切都|仿佛都|所有的.{0,8}都).{0,20}(说明|意味着|指向|让|令|使)"),
]
_JUDGMENT_SENTENCE_PATTERNS = [
    re.compile(r"(显然|无疑|毫无疑问|显而易见|可以说|不得不说|某种意义上)"),
]
_EXPLANATORY_SENTENCE_PATTERNS = [
    re.compile(r"(这意味着|这说明|也就是说|换句话说|说到底|归根结底|其实就是)"),
]
_CLIFFHANGER_SENTENCE_PATTERNS = [
    re.compile(r"(而这只是开始|这仅仅只是开始|他不知道的是|她不知道的是|命运的齿轮开始转动)"),
    re.compile(r"(真正的.{0,10}才刚刚开始|更大的风暴还在后面|一场.{0,12}(即将来临|正在逼近))"),
]
_HIGH_FREQUENCY_TROPE_TERMS = [
    "冰冷",
    "刺骨",
    "凛冽",
    "冰锥",
    "寒意",
    "心中一紧",
    "眉头一皱",
    "嘴角上扬",
    "命运的齿轮",
]
_MECHANICAL_EMOTION_TERMS = [
    "心中一紧",
    "瞳孔一缩",
    "呼吸一滞",
    "眉头微皱",
    "眉头一皱",
    "眸光一沉",
    "眼神一冷",
    "脸色微变",
    "倒吸了一口凉气",
]
_FOUR_CHAR_TROPE_TERMS = [
    "不动声色",
    "一言不发",
    "若有所思",
    "心惊肉跳",
    "杀气腾腾",
    "风声鹤唳",
    "不寒而栗",
    "汹涌澎湃",
    "铺天盖地",
    "密密麻麻",
    "鸦雀无声",
    "若隐若现",
    "意味深长",
    "不由自主",
    "脱口而出",
]
_REPETITION_STOP_TERMS = {
    "自己",
    "他们",
    "我们",
    "这里",
    "那里",
    "没有",
    "不会",
    "可以",
    "不是",
}
_PARAGRAPH_PREFIX_STOP_TERMS = {"但是", "然而", "只是", "于是", "随后", "然后", "此时"}


def _normalize_role_name(name: str) -> str:
    value = (name or "").strip("，。！？；：、\n\t ")
    for suffix in _ROLE_NAME_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            value = value[: -len(suffix)]
            break
    if len(value) < 2:
        return ""
    if len(value) > 8:
        value = value[-4:]
    return value


def _extract_power_pairs(text: str) -> List[Tuple[str, str]]:
    """从约束文本中提取“角色-境界”对。"""
    pairs: List[Tuple[str, str]] = []
    seen = set()

    for level in _POWER_LEVELS_ORDER:
        direct_pattern = re.compile(
            rf"([\u4e00-\u9fff]{{2,8}})(?:[^\n。！？；，]{{0,8}})(?:突破|晋升|达到|达|至|到|进入|是|为).{{0,4}}{re.escape(level)}"
        )
        for match in direct_pattern.finditer(text):
            name = _normalize_role_name(match.group(1) or "")
            if not name:
                continue
            key = (name, level)
            if key not in seen:
                pairs.append(key)
                seen.add(key)

        for match in re.finditer(re.escape(level), text):
            prefix = text[max(0, match.start() - 20): match.start()]
            tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", prefix)
            if not tokens:
                continue
            name = _normalize_role_name(tokens[-1])
            if not name:
                continue
            key = (name, level)
            if key not in seen:
                pairs.append(key)
                seen.add(key)

    return pairs


class ViolationType(Enum):
    """违规类型"""
    DEAD_CHARACTER_REVIVED = "dead_character_revived"  # 死亡角色复活
    POWER_REGRESSION = "power_regression"  # 能力倒退
    SECRET_FORGOTTEN = "secret_forgotten"  # 已揭秘密被遗忘
    RULE_VIOLATED = "rule_violated"  # 世界规则违反
    PROMISE_BROKEN = "promise_broken"  # 承诺未履行（无合理解释）
    RELATIONSHIP_CONFLICT = "relationship_conflict"  # 关系矛盾
    TIMELINE_ERROR = "timeline_error"  # 时间线错误
    ITEM_CONFLICT = "item_conflict"  # 物品状态冲突
    SUMMARY_SENTENCE = "summary_sentence"  # 概括总结句
    JUDGMENT_SENTENCE = "judgment_sentence"  # 作者判断句
    EXPLANATORY_SENTENCE = "explanatory_sentence"  # 解释句
    CLIFFHANGER_CLICHE = "cliffhanger_cliche"  # 套路钩子句
    HIGH_FREQUENCY_TROPE = "high_frequency_trope"  # 高频套路词
    ABSTRACT_ENDING_DENSITY = "abstract_ending_density"  # 连续抽象收尾句
    MECHANICAL_EMOTION = "mechanical_emotion"  # 机械情绪描写
    FOUR_CHAR_STACKING = "four_char_stacking"  # 四字词/成语堆砌
    REPETITIVE_WORDING = "repetitive_wording"  # 短距离重复词句
    SYMMETRIC_PARALLELISM = "symmetric_parallelism"  # 对称排比过密
    PARAGRAPH_START_RHYTHM = "paragraph_start_rhythm"  # 段首节奏过于整齐


@dataclass
class Violation:
    """违规记录"""
    violation_type: ViolationType
    severity: str  # critical, warning, info
    description: str
    evidence: str  # 违规内容片段
    suggestion: str  # 修正建议
    position: int = 0  # 在内容中的位置


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    auto_fixed: bool = False
    fixed_content: Optional[str] = None
    
    @property
    def has_critical(self) -> bool:
        return any(v.severity == "critical" for v in self.violations)
    
    @property
    def has_warnings(self) -> bool:
        return any(v.severity == "warning" for v in self.violations)


class ContentValidator:
    """
    内容验证器
    
    在章节生成后进行验证，检测是否违反已知的剧情设定。
    这是除提示词约束外的第二道防线。
    """
    
    def __init__(self, constraint_store=None, knowledge_base=None):
        """
        初始化验证器
        
        Args:
            constraint_store: 剧情约束存储
            knowledge_base: 知识库实例
        """
        self.constraint_store = constraint_store
        self.knowledge_base = knowledge_base
        
        # 缓存约束数据
        self._dead_characters: List[str] = []
        self._power_levels: Dict[str, str] = {}  # 角色 -> 当前境界
        self._revealed_secrets: List[Dict] = []
        self._world_rules: List[str] = []
        self._promises: List[Dict] = []
    
    def load_constraints(self):
        """从知识库加载约束数据"""
        if not self.constraint_store:
            return
        
        try:
            # 加载死亡角色
            self._dead_characters = self.constraint_store.get_death_constraints()
            self._power_levels = {}
            self._world_rules = []
            self._revealed_secrets = []
            self._promises = []
            
            # 加载其他约束
            all_constraints = self.constraint_store.search_constraints(top_k=100)
            
            for constraint in all_constraints:
                doc = str(constraint.get("document", "") or "")
                constraint_types = constraint.get("constraint_types", []) or []
                structured_lines = constraint.get("structured_lines", []) or []

                if "character_power" in constraint_types:
                    power_source_text = "\n".join(
                        str(item.get("payload") or "")
                        for item in structured_lines
                        if str(item.get("constraint_type") or "") == "character_power"
                    ).strip() or doc
                    for role_name, level_name in _extract_power_pairs(power_source_text):
                        previous_level = self._power_levels.get(role_name)
                        if previous_level is None or _POWER_LEVEL_RANK[level_name] >= _POWER_LEVEL_RANK[previous_level]:
                            self._power_levels[role_name] = level_name
                
                if "world_rule" in constraint_types:
                    world_rule_lines = [
                        str(item.get("payload") or "").strip()
                        for item in structured_lines
                        if str(item.get("constraint_type") or "") == "world_rule" and str(item.get("payload") or "").strip()
                    ]
                    if world_rule_lines:
                        self._world_rules.extend(world_rule_lines)
                    elif doc:
                        self._world_rules.append(doc)
                
                if "secret_revealed" in constraint_types:
                    secret_lines = [
                        item for item in structured_lines
                        if str(item.get("constraint_type") or "") == "secret_revealed"
                    ]
                    if secret_lines:
                        for item in secret_lines:
                            self._revealed_secrets.append({
                                **constraint,
                                "structured_line": item,
                            })
                    else:
                        self._revealed_secrets.append(constraint)
                
                if "promise_oath" in constraint_types:
                    promise_lines = [
                        item for item in structured_lines
                        if str(item.get("constraint_type") or "") == "promise_oath"
                    ]
                    if promise_lines:
                        for item in promise_lines:
                            self._promises.append({
                                **constraint,
                                "structured_line": item,
                            })
                    else:
                        self._promises.append(constraint)
            
            logger.info(f"[Validator] 加载约束: {len(self._dead_characters)} 死亡角色, "
                       f"{len(self._world_rules)} 世界规则, "
                       f"{len(self._power_levels)} 角色境界, "
                       f"{len(self._revealed_secrets)} 已揭露秘密, "
                       f"{len(self._promises)} 承诺誓言")
            
        except Exception as e:
            logger.error(f"[Validator] 加载约束失败: {e}")
    
    def validate(
        self,
        content: str,
        chapter_number: int = 0,
        auto_fix: bool = False
    ) -> ValidationResult:
        """
        验证章节内容
        
        Args:
            content: 章节内容
            chapter_number: 章节序号
            auto_fix: 是否自动修正
        
        Returns:
            验证结果
        """
        violations = []
        
        # 检测死亡角色复活
        death_violations = self._check_dead_characters(content)
        violations.extend(death_violations)
        
        # 检测能力倒退
        power_violations = self._check_power_regression(content)
        violations.extend(power_violations)
        
        # 检测时间线错误
        timeline_violations = self._check_timeline(content, chapter_number)
        violations.extend(timeline_violations)

        # 检测世界规则冲突
        world_rule_violations = self._check_world_rules(content)
        violations.extend(world_rule_violations)

        # 检测承诺/誓言冲突
        promise_violations = self._check_promises(content)
        violations.extend(promise_violations)

        # 检测关系冲突
        relationship_violations = self._check_relationships(content)
        violations.extend(relationship_violations)

        # 检测重要物品状态冲突
        item_violations = self._check_items(content)
        violations.extend(item_violations)

        # 检测机械化 AI 句式
        style_violations = self._check_ai_style(content)
        violations.extend(style_violations)
        
        # 构建结果
        result = ValidationResult(
            is_valid=not any(v.severity == "critical" for v in violations),
            violations=violations,
            warnings=[v.description for v in violations if v.severity == "warning"]
        )
        
        # 自动修正
        if auto_fix and violations:
            fixed_content = self._auto_fix(content, violations)
            if fixed_content != content:
                result.auto_fixed = True
                result.fixed_content = fixed_content
        
        if violations:
            logger.warning(f"[Validator] 检测到 {len(violations)} 个违规")
        
        return result
    
    def _check_dead_characters(self, content: str) -> List[Violation]:
        """检测死亡角色是否以活人身份出现"""
        violations = []
        
        # 回忆/闪回场景标记
        flashback_patterns = [
            r'【回忆开始】.*?【回忆结束】',
            r'回忆起.*?(?:往事|过去)',
            r'曾经.*?的时候',
            r'想起.*?(?:当年|过去)',
        ]
        
        # 编译回忆模式
        flashback_regions = []
        for pattern in flashback_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                flashback_regions.append((match.start(), match.end()))
        
        def is_in_flashback(pos: int) -> bool:
            """检查位置是否在回忆场景中"""
            return any(start <= pos <= end for start, end in flashback_regions)
        
        # 活人行为模式
        alive_patterns = [
            r'{name}(?:说道|道|笑道|冷笑|大喝|怒吼|点头|摇头)',
            r'{name}(?:走来|走去|站起|坐下|转身|离开|进入)',
            r'{name}(?:出手|攻击|反击|战斗|施展)',
            r'{name}(?:看着|盯着|凝视|注视)',
            r'(?:看向|望向|面对){name}',
        ]
        
        for char in self._dead_characters:
            if len(char) < 2:
                continue
            
            for pattern_template in alive_patterns:
                pattern = pattern_template.format(name=re.escape(char))
                
                for match in re.finditer(pattern, content):
                    # 检查是否在回忆场景中
                    if is_in_flashback(match.start()):
                        continue
                    
                    # 获取上下文
                    start = max(0, match.start() - 30)
                    end = min(len(content), match.end() + 30)
                    context = content[start:end]
                    
                    violations.append(Violation(
                        violation_type=ViolationType.DEAD_CHARACTER_REVIVED,
                        severity="critical",
                        description=f"死亡角色 '{char}' 以活人身份出现",
                        evidence=context,
                        suggestion=f"建议删除或改为回忆场景。可使用【回忆开始】...【回忆结束】标记",
                        position=match.start()
                    ))
        
        return violations
    
    def _check_power_regression(self, content: str) -> List[Violation]:
        """检测能力倒退（如境界下降）"""
        violations = []

        if not self._power_levels:
            return violations

        for role_name, current_level in self._power_levels.items():
            current_rank = _POWER_LEVEL_RANK.get(current_level)
            if current_rank is None:
                continue

            for level_name in _POWER_LEVELS_ORDER:
                lower_rank = _POWER_LEVEL_RANK[level_name]
                if lower_rank >= current_rank:
                    continue

                pattern = re.compile(rf"{re.escape(role_name)}.{{0,10}}{re.escape(level_name)}")
                for match in pattern.finditer(content):
                    start = max(0, match.start() - 30)
                    end = min(len(content), match.end() + 30)
                    evidence = content[start:end]
                    violations.append(Violation(
                        violation_type=ViolationType.POWER_REGRESSION,
                        severity="warning",
                        description=f"角色 '{role_name}' 境界可能倒退：当前约束为 {current_level}，文本出现 {level_name}",
                        evidence=evidence,
                        suggestion=f"请确认是否为回忆/伪装情节；若非，请保持境界不低于 {current_level}",
                        position=match.start(),
                    ))
                    break

        return violations
    
    def _check_timeline(self, content: str, chapter_number: int) -> List[Violation]:
        """检测时间线错误"""
        violations = []

        for pattern in _TIMELINE_BACKWARD_PATTERNS:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 30)
                end = min(len(content), match.end() + 30)
                evidence = content[start:end]
                violations.append(Violation(
                    violation_type=ViolationType.TIMELINE_ERROR,
                    severity="warning",
                    description=f"第{chapter_number}章时间表达可能冲突",
                    evidence=evidence,
                    suggestion="建议统一叙述顺序，避免同一句内先过去再未来的跳变",
                    position=match.start(),
                ))

        for past_hint in _TIMELINE_PAST_HINTS:
            for seq_hint in _TIMELINE_BACKWARD_HINTS:
                pattern = re.compile(rf"{re.escape(seq_hint)}.{{0,12}}{re.escape(past_hint)}")
                for match in pattern.finditer(content):
                    start = max(0, match.start() - 30)
                    end = min(len(content), match.end() + 30)
                    evidence = content[start:end]
                    violations.append(Violation(
                        violation_type=ViolationType.TIMELINE_ERROR,
                        severity="info",
                        description=f"第{chapter_number}章叙述顺序可能回跳",
                        evidence=evidence,
                        suggestion="如非回忆段，请改为顺序叙述；如是回忆，建议加【回忆开始/结束】标记",
                        position=match.start(),
                    ))

        return violations

    @staticmethod
    def _extract_constraint_payload(constraint: Dict[str, Any]) -> str:
        structured_line = constraint.get("structured_line") if isinstance(constraint, dict) else None
        if isinstance(structured_line, dict):
            payload = str(structured_line.get("payload") or "").strip()
            if payload:
                return payload
        return str((constraint or {}).get("document") or "").strip()

    def _check_world_rules(self, content: str) -> List[Violation]:
        """检测世界规则冲突。"""
        violations: List[Violation] = []
        negative_patterns = [
            re.compile(r"(竟然|居然|却|反而).{0,12}(可以|能够|能)"),
            re.compile(r"(打破|无视|违背|突破).{0,12}(规则|禁忌|法则|限制)"),
        ]

        for rule_text in self._world_rules[:20]:
            payload = str(rule_text or "").strip()
            if not payload:
                continue
            rule_key = payload.split("|", 1)[0].strip()
            if not rule_key:
                rule_key = payload[:24]
            if rule_key and rule_key in content:
                for pattern in negative_patterns:
                    around_pattern = re.compile(rf"{re.escape(rule_key[:12])}.{{0,20}}{pattern.pattern}")
                    match = around_pattern.search(content)
                    if match:
                        evidence = content[max(0, match.start() - 20): min(len(content), match.end() + 20)]
                        violations.append(Violation(
                            violation_type=ViolationType.RULE_VIOLATED,
                            severity="warning",
                            description=f"疑似出现世界规则冲突：{rule_key[:30]}",
                            evidence=evidence,
                            suggestion="请确认这是明确的破规剧情，若不是，请保持既有世界规则成立",
                            position=match.start(),
                        ))
                        break

        return violations

    def _check_promises(self, content: str) -> List[Violation]:
        """检测承诺/誓言相关冲突。"""
        violations: List[Violation] = []
        for constraint in self._promises[:20]:
            payload = self._extract_constraint_payload(constraint)
            if not payload:
                continue

            fragments = [frag.strip() for frag in re.split(r"[|，。；;]", payload) if frag.strip()]
            key_fragment = fragments[0] if fragments else payload[:30]
            if not key_fragment:
                continue

            deny_pattern = re.compile(rf"(违背|背弃|食言|反悔|没有做到|未能做到).{{0,16}}{re.escape(key_fragment[:12])}")
            match = deny_pattern.search(content)
            if match:
                evidence = content[max(0, match.start() - 20): min(len(content), match.end() + 20)]
                violations.append(Violation(
                    violation_type=ViolationType.PROMISE_BROKEN,
                    severity="warning",
                    description=f"疑似出现承诺/誓言冲突：{key_fragment[:30]}",
                    evidence=evidence,
                    suggestion="请确认是否存在合理的毁约原因；若无，请保持与既有承诺一致",
                    position=match.start(),
                ))

        return violations

    def _check_relationships(self, content: str) -> List[Violation]:
        """检测关系冲突。"""
        violations: List[Violation] = []
        relation_conflict_patterns = [
            re.compile(r"(仇人|死敌|宿敌).{0,12}(相爱|亲密|信任)"),
            re.compile(r"(恋人|夫妻|挚友).{0,12}(陌生|不认识|毫无关系)"),
        ]

        for pattern in relation_conflict_patterns:
            for match in pattern.finditer(content):
                evidence = content[max(0, match.start() - 20): min(len(content), match.end() + 20)]
                violations.append(Violation(
                    violation_type=ViolationType.RELATIONSHIP_CONFLICT,
                    severity="warning",
                    description="检测到显式关系表述冲突",
                    evidence=evidence,
                    suggestion="请确认人物关系是否发生过明确转折；若没有，请统一关系状态",
                    position=match.start(),
                ))

        return violations

    def _check_items(self, content: str) -> List[Violation]:
        """检测重要物品状态冲突。"""
        violations: List[Violation] = []
        item_conflict_patterns = [
            re.compile(r"(已经损毁|已经破碎|已经消失).{0,12}(再次出现|重新握在手中|完好无损)"),
            re.compile(r"(被夺走|遗失|失落).{0,12}(仍在手中|一直佩戴|随手取出)"),
        ]

        for pattern in item_conflict_patterns:
            for match in pattern.finditer(content):
                evidence = content[max(0, match.start() - 20): min(len(content), match.end() + 20)]
                violations.append(Violation(
                    violation_type=ViolationType.ITEM_CONFLICT,
                    severity="warning",
                    description="检测到重要物品状态前后矛盾",
                    evidence=evidence,
                    suggestion="请确认物品是否已经修复、找回或替换；若无，请统一物品状态",
                    position=match.start(),
                ))

        return violations

    @staticmethod
    def _iter_sentence_spans(text: str) -> List[Tuple[int, int, str]]:
        """按中文语义切分句子，返回 (start, end, sentence)。"""
        spans: List[Tuple[int, int, str]] = []
        start = 0

        for index, char in enumerate(text):
            if char not in _SENTENCE_END_CHARS:
                continue
            end = index + 1
            sent_start = start
            sent_end = end
            while sent_start < sent_end and text[sent_start].isspace():
                sent_start += 1
            while sent_end > sent_start and text[sent_end - 1].isspace():
                sent_end -= 1
            if sent_end > sent_start:
                spans.append((sent_start, sent_end, text[sent_start:sent_end]))
            start = end

        if start < len(text):
            sent_start = start
            sent_end = len(text)
            while sent_start < sent_end and text[sent_start].isspace():
                sent_start += 1
            while sent_end > sent_start and text[sent_end - 1].isspace():
                sent_end -= 1
            if sent_end > sent_start:
                spans.append((sent_start, sent_end, text[sent_start:sent_end]))

        return spans

    @staticmethod
    def _looks_like_dialogue(sentence: str) -> bool:
        stripped = (sentence or "").strip()
        return "“" in stripped and "”" in stripped

    def _check_ai_style(self, content: str) -> List[Violation]:
        """检测常见 AI 味句子。"""
        violations: List[Violation] = []
        abstract_sentence_spans: List[Tuple[int, int, str]] = []

        pattern_specs = [
            (
                ViolationType.SUMMARY_SENTENCE,
                _SUMMARY_SENTENCE_PATTERNS,
                "warning",
                "检测到概括总结句，容易出现作者代替读者下结论的 AI 味",
                "建议改成角色动作、现场反应或具体结果，少用抽象总结",
            ),
            (
                ViolationType.JUDGMENT_SENTENCE,
                _JUDGMENT_SENTENCE_PATTERNS,
                "warning",
                "检测到作者判断句，叙述容易显得生硬居高临下",
                "建议删去判断词，直接呈现事实、动作或人物反应",
            ),
            (
                ViolationType.EXPLANATORY_SENTENCE,
                _EXPLANATORY_SENTENCE_PATTERNS,
                "warning",
                "检测到解释句，容易把正文写成分析说明",
                "建议把解释改成情节表现，不要替读者总结含义",
            ),
            (
                ViolationType.CLIFFHANGER_CLICHE,
                _CLIFFHANGER_SENTENCE_PATTERNS,
                "warning",
                "检测到套路钩子句，悬念表达过于空泛",
                "建议改成具体异动、新信息或未完成动作，而不是口号式收尾",
            ),
        ]

        for start, _end, sentence in self._iter_sentence_spans(content):
            if len(sentence) < 4 or self._looks_like_dialogue(sentence):
                continue

            for violation_type, patterns, severity, description, suggestion in pattern_specs:
                if any(pattern.search(sentence) for pattern in patterns):
                    violations.append(Violation(
                        violation_type=violation_type,
                        severity=severity,
                        description=description,
                        evidence=sentence,
                        suggestion=suggestion,
                        position=start,
                    ))
                    if violation_type in {
                        ViolationType.SUMMARY_SENTENCE,
                        ViolationType.JUDGMENT_SENTENCE,
                        ViolationType.EXPLANATORY_SENTENCE,
                        ViolationType.CLIFFHANGER_CLICHE,
                    }:
                        abstract_sentence_spans.append((start, _end, sentence))
                    break

        trope_violations = self._check_high_frequency_tropes(content)
        violations.extend(trope_violations)
        mechanical_emotion_violations = self._check_mechanical_emotions(content)
        violations.extend(mechanical_emotion_violations)
        four_char_violations = self._check_four_char_stacking(content)
        violations.extend(four_char_violations)
        repetitive_wording_violations = self._check_repetitive_wording(content)
        violations.extend(repetitive_wording_violations)
        symmetric_parallelism_violations = self._check_symmetric_parallelism(content)
        violations.extend(symmetric_parallelism_violations)
        paragraph_start_violations = self._check_paragraph_start_rhythm(content)
        violations.extend(paragraph_start_violations)
        density_violations = self._check_abstract_ending_density(content, abstract_sentence_spans)
        violations.extend(density_violations)

        return violations

    def _check_high_frequency_tropes(self, content: str) -> List[Violation]:
        """检测 AI 高频套路词的过度使用。"""
        violations: List[Violation] = []
        term_hits: Dict[str, List[int]] = {}

        for term in _HIGH_FREQUENCY_TROPE_TERMS:
            matches = [m.start() for m in re.finditer(re.escape(term), content)]
            if matches:
                term_hits[term] = matches

        if not term_hits:
            return violations

        total_hits = sum(len(positions) for positions in term_hits.values())
        repeated_terms = {term: len(positions) for term, positions in term_hits.items() if len(positions) >= 3}

        if total_hits >= 5:
            evidence = "，".join(f"{term}x{len(positions)}" for term, positions in sorted(term_hits.items(), key=lambda item: (-len(item[1]), item[0]))[:4])
            first_position = min(positions[0] for positions in term_hits.values())
            violations.append(Violation(
                violation_type=ViolationType.HIGH_FREQUENCY_TROPE,
                severity="warning",
                description="检测到 AI 高频套路词密集出现，文风容易变得模板化",
                evidence=evidence,
                suggestion="建议替换一部分高频词，用更具体的动作、触感或场景细节承载情绪",
                position=first_position,
            ))

        for term, count in repeated_terms.items():
            violations.append(Violation(
                violation_type=ViolationType.HIGH_FREQUENCY_TROPE,
                severity="warning",
                description=f"高频套路词 '{term}' 重复 {count} 次，容易显得机械",
                evidence=term,
                suggestion=f"建议减少 '{term}' 的重复使用，改成具体反应或现场细节",
                position=term_hits[term][0],
            ))

        return violations

    def _check_mechanical_emotions(self, content: str) -> List[Violation]:
        """检测机械情绪描写模板的重复出现。"""
        violations: List[Violation] = []
        term_hits: Dict[str, List[int]] = {}

        for term in _MECHANICAL_EMOTION_TERMS:
            matches = [m.start() for m in re.finditer(re.escape(term), content)]
            if matches:
                term_hits[term] = matches

        if not term_hits:
            return violations

        total_hits = sum(len(positions) for positions in term_hits.values())
        repeated_terms = {term: len(positions) for term, positions in term_hits.items() if len(positions) >= 2}

        if total_hits >= 3:
            evidence = "，".join(
                f"{term}x{len(positions)}"
                for term, positions in sorted(term_hits.items(), key=lambda item: (-len(item[1]), item[0]))[:4]
            )
            first_position = min(positions[0] for positions in term_hits.values())
            violations.append(Violation(
                violation_type=ViolationType.MECHANICAL_EMOTION,
                severity="warning",
                description="检测到机械情绪描写模板密集出现，人物反应容易同质化",
                evidence=evidence,
                suggestion="建议把部分情绪模板改成更具体的动作、停顿、视线变化或现场细节",
                position=first_position,
            ))

        for term, count in repeated_terms.items():
            violations.append(Violation(
                violation_type=ViolationType.MECHANICAL_EMOTION,
                severity="warning",
                description=f"机械情绪模板 '{term}' 重复 {count} 次，容易显得程式化",
                evidence=term,
                suggestion=f"建议减少 '{term}' 的重复，改成更贴合场景的人物反应",
                position=term_hits[term][0],
            ))

        return violations

    def _check_four_char_stacking(self, content: str) -> List[Violation]:
        """检测四字词/成语堆砌。"""
        violations: List[Violation] = []
        term_hits: Dict[str, List[int]] = {}

        for term in _FOUR_CHAR_TROPE_TERMS:
            matches = [m.start() for m in re.finditer(re.escape(term), content)]
            if matches:
                term_hits[term] = matches

        if not term_hits:
            return violations

        total_hits = sum(len(positions) for positions in term_hits.values())
        repeated_terms = {term: len(positions) for term, positions in term_hits.items() if len(positions) >= 2}

        if total_hits >= 4:
            evidence = "，".join(
                f"{term}x{len(positions)}"
                for term, positions in sorted(term_hits.items(), key=lambda item: (-len(item[1]), item[0]))[:4]
            )
            first_position = min(positions[0] for positions in term_hits.values())
            violations.append(Violation(
                violation_type=ViolationType.FOUR_CHAR_STACKING,
                severity="warning",
                description="检测到四字词/成语密集出现，句子容易显得堆砌和套路化",
                evidence=evidence,
                suggestion="建议删减一部分四字词，改成更具体直接的动作、触感或场景描写",
                position=first_position,
            ))

        for term, count in repeated_terms.items():
            violations.append(Violation(
                violation_type=ViolationType.FOUR_CHAR_STACKING,
                severity="warning",
                description=f"四字词 '{term}' 重复 {count} 次，表达容易发腻",
                evidence=term,
                suggestion=f"建议减少 '{term}' 的重复，避免连续使用同类四字词",
                position=term_hits[term][0],
            ))

        return violations

    def _check_repetitive_wording(self, content: str) -> List[Violation]:
        """检测短距离重复词和重复句式。"""
        violations: List[Violation] = []

        token_hits: Dict[str, List[int]] = {}
        for match in re.finditer(r"[\u4e00-\u9fff]{4,24}", content):
            chunk = match.group(0)
            chunk_start = match.start()
            max_len = min(8, len(chunk))
            for length in range(4, max_len + 1):
                for index in range(0, len(chunk) - length + 1):
                    token = chunk[index:index + length]
                    if token in _REPETITION_STOP_TERMS:
                        continue
                    token_hits.setdefault(token, []).append(chunk_start + index)

        for token, positions in token_hits.items():
            if len(positions) < 3:
                continue
            for index in range(len(positions) - 2):
                if positions[index + 2] - positions[index] <= 100:
                    violations.append(Violation(
                        violation_type=ViolationType.REPETITIVE_WORDING,
                        severity="warning",
                        description=f"短距离内重复使用 '{token}'，表达容易显得机械",
                        evidence=token,
                        suggestion="建议替换其中一两处为更具体的动作、状态或同义表达",
                        position=positions[index],
                    ))
                    break

        sentence_prefixes: List[Tuple[int, str]] = []
        for start, _end, sentence in self._iter_sentence_spans(content):
            if self._looks_like_dialogue(sentence):
                continue
            normalized = re.sub(r"^[“\"'（(\s]+", "", sentence.strip())
            prefix = normalized[:4]
            if len(prefix) < 4:
                continue
            sentence_prefixes.append((start, prefix))

        for index in range(len(sentence_prefixes) - 2):
            first = sentence_prefixes[index]
            second = sentence_prefixes[index + 1]
            third = sentence_prefixes[index + 2]
            if first[1] == second[1] == third[1]:
                violations.append(Violation(
                    violation_type=ViolationType.REPETITIVE_WORDING,
                    severity="warning",
                    description=f"连续句子使用相同起手 '{first[1]}'，句式容易显得单调",
                    evidence=first[1],
                    suggestion="建议打散句式，调整其中至少一句的起手结构",
                    position=first[0],
                ))
                break

        return violations

    def _check_symmetric_parallelism(self, content: str) -> List[Violation]:
        """检测句内过于整齐的对称排比。"""
        violations: List[Violation] = []

        for start, _end, sentence in self._iter_sentence_spans(content):
            if self._looks_like_dialogue(sentence):
                continue

            clauses = [clause.strip() for clause in re.split(r"[，、；;]", sentence) if clause.strip()]
            if len(clauses) < 3:
                continue

            normalized_clauses = [re.sub(r"[^\u4e00-\u9fff]", "", clause) for clause in clauses]
            lengths = [len(clause) for clause in normalized_clauses if clause]
            if len(lengths) < 3:
                continue

            prefix_map: Dict[str, int] = {}
            for clause in normalized_clauses:
                if len(clause) < 3:
                    continue
                prefix = clause[:2]
                prefix_map[prefix] = prefix_map.get(prefix, 0) + 1

            dense_prefix = next((prefix for prefix, count in prefix_map.items() if count >= 3), "")
            nearly_equal_lengths = max(lengths) - min(lengths) <= 2

            if dense_prefix or nearly_equal_lengths:
                evidence = sentence
                reason = "连续分句起手过于一致" if dense_prefix else "并列分句长度过于整齐"
                violations.append(Violation(
                    violation_type=ViolationType.SYMMETRIC_PARALLELISM,
                    severity="warning",
                    description=f"检测到对称排比句偏密，{reason}，容易显得模型味过重",
                    evidence=evidence,
                    suggestion="建议打散其中一两处并列结构，改成动作、停顿或长短句交替",
                    position=start,
                ))

        return violations

    def _check_paragraph_start_rhythm(self, content: str) -> List[Violation]:
        """检测连续段落起手过于整齐。"""
        violations: List[Violation] = []
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", content) if paragraph.strip()]
        if len(paragraphs) < 3:
            return violations

        def _extract_rhythm_prefix(paragraph: str) -> str:
            normalized = re.sub(r"^[“\"'（(\s]+", "", paragraph or "")
            if not normalized:
                return ""
            if normalized[:1] in {"他", "她", "我", "你", "它", "这", "那"}:
                return normalized[:1]
            if len(normalized) >= 2:
                return normalized[:2]
            return normalized[:1]

        paragraph_prefixes: List[Tuple[int, str]] = []
        offset = 0
        for paragraph in paragraphs:
            idx = content.find(paragraph, offset)
            if idx < 0:
                idx = offset
            offset = idx + len(paragraph)
            prefix = _extract_rhythm_prefix(paragraph)
            if not prefix or prefix in _PARAGRAPH_PREFIX_STOP_TERMS:
                paragraph_prefixes.append((idx, ""))
                continue
            paragraph_prefixes.append((idx, prefix))

        active_run: List[Tuple[int, str]] = []
        for entry in paragraph_prefixes:
            position, prefix = entry
            if not prefix:
                if len(active_run) >= 3:
                    evidence = " / ".join(prefix_text for _, prefix_text in active_run[:3])
                    violations.append(Violation(
                        violation_type=ViolationType.PARAGRAPH_START_RHYTHM,
                        severity="warning",
                        description=f"连续 {len(active_run)} 个段落用相近起手，节奏显得过于整齐",
                        evidence=evidence,
                        suggestion="建议调整其中至少一段的开头，让段首动作、视角或节奏错开",
                        position=active_run[0][0],
                    ))
                active_run = []
                continue

            if not active_run or active_run[-1][1] == prefix:
                active_run.append(entry)
            else:
                if len(active_run) >= 3:
                    evidence = " / ".join(prefix_text for _, prefix_text in active_run[:3])
                    violations.append(Violation(
                        violation_type=ViolationType.PARAGRAPH_START_RHYTHM,
                        severity="warning",
                        description=f"连续 {len(active_run)} 个段落用相近起手，节奏显得过于整齐",
                        evidence=evidence,
                        suggestion="建议调整其中至少一段的开头，让段首动作、视角或节奏错开",
                        position=active_run[0][0],
                    ))
                active_run = [entry]

        if len(active_run) >= 3:
            evidence = " / ".join(prefix_text for _, prefix_text in active_run[:3])
            violations.append(Violation(
                violation_type=ViolationType.PARAGRAPH_START_RHYTHM,
                severity="warning",
                description=f"连续 {len(active_run)} 个段落用相近起手，节奏显得过于整齐",
                evidence=evidence,
                suggestion="建议调整其中至少一段的开头，让段首动作、视角或节奏错开",
                position=active_run[0][0],
            ))

        return violations

    def _check_abstract_ending_density(
        self,
        content: str,
        abstract_sentence_spans: List[Tuple[int, int, str]],
    ) -> List[Violation]:
        """检测连续段落使用抽象句收尾。"""
        if not abstract_sentence_spans:
            return []

        abstract_sentences = {sentence for _, _, sentence in abstract_sentence_spans}
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", content) if paragraph.strip()]
        if len(paragraphs) < 2:
            return []

        paragraph_endings: List[Tuple[int, str]] = []
        offset = 0
        for paragraph in paragraphs:
            idx = content.find(paragraph, offset)
            if idx < 0:
                idx = offset
            offset = idx + len(paragraph)
            sentence_spans = self._iter_sentence_spans(paragraph)
            if not sentence_spans:
                continue
            last_sentence = sentence_spans[-1][2]
            if self._looks_like_dialogue(last_sentence):
                continue
            if last_sentence in abstract_sentences:
                paragraph_endings.append((idx, last_sentence))

        if len(paragraph_endings) < 2:
            return []

        violations: List[Violation] = []

        paragraph_tail_states: List[Tuple[int, str] | None] = []
        offset = 0
        for paragraph in paragraphs:
            idx = content.find(paragraph, offset)
            if idx < 0:
                idx = offset
            offset = idx + len(paragraph)
            sentence_spans = self._iter_sentence_spans(paragraph)
            if not sentence_spans:
                paragraph_tail_states.append(None)
                continue
            last_sentence = sentence_spans[-1][2]
            if self._looks_like_dialogue(last_sentence) or last_sentence not in abstract_sentences:
                paragraph_tail_states.append(None)
                continue
            paragraph_tail_states.append((idx, last_sentence))

        active_run: List[Tuple[int, str]] = []
        for paragraph_state in paragraph_tail_states:
            if paragraph_state is None:
                if len(active_run) >= 2:
                    evidence = " / ".join(sentence for _, sentence in active_run[:3])
                    violations.append(Violation(
                        violation_type=ViolationType.ABSTRACT_ENDING_DENSITY,
                        severity="warning",
                        description=f"连续 {len(active_run)} 个段落使用抽象句收尾，悬念和节奏容易发空",
                        evidence=evidence,
                        suggestion="建议把其中至少一个段落改成具体动作、异动、对话或信息落点收尾",
                        position=active_run[0][0],
                    ))
                active_run = []
                continue

            active_run.append(paragraph_state)

        if len(active_run) >= 2:
            evidence = " / ".join(sentence for _, sentence in active_run[:3])
            violations.append(Violation(
                violation_type=ViolationType.ABSTRACT_ENDING_DENSITY,
                severity="warning",
                description=f"连续 {len(active_run)} 个段落使用抽象句收尾，悬念和节奏容易发空",
                evidence=evidence,
                suggestion="建议把其中至少一个段落改成具体动作、异动、对话或信息落点收尾",
                position=active_run[0][0],
            ))

        return violations

    @staticmethod
    def _find_sentence_bounds(content: str, position: int) -> Tuple[int, int]:
        """根据命中位置回溯句子边界。"""
        start = max(0, min(position, len(content)))
        end = start

        while start > 0 and content[start - 1] not in _SENTENCE_END_CHARS:
            start -= 1
        while end < len(content) and content[end] not in _SENTENCE_END_CHARS:
            end += 1
        if end < len(content):
            end += 1

        while start < end and content[start].isspace():
            start += 1
        while end > start and content[end - 1].isspace():
            end -= 1

        return start, end

    @staticmethod
    def _rewrite_style_sentence(sentence: str, violation_type: ViolationType) -> str:
        """对单句做轻量去机械化处理。"""
        fixed = sentence

        if violation_type == ViolationType.JUDGMENT_SENTENCE:
            fixed = re.sub(
                r"^(显然|无疑|毫无疑问|显而易见|可以说|不得不说|某种意义上(?:来说)?)[，,、：:\s]*",
                "",
                fixed,
                count=1,
            )
        elif violation_type == ViolationType.EXPLANATORY_SENTENCE:
            fixed = re.sub(
                r"^(这意味着|这说明|也就是说|换句话说|说到底|归根结底|其实就是)[，,、：:\s]*",
                "",
                fixed,
                count=1,
            )
        elif violation_type == ViolationType.SUMMARY_SENTENCE:
            fixed = re.sub(
                r"^(这一切|这一幕|这一刻|这一夜|所有的这些|所有的这一切|所有的一切|一切都|仿佛都)[，,、：:\s]*(都|也)?(让|令|使|说明|意味着)[，,、：:\s]*",
                "",
                fixed,
                count=1,
            )
        elif violation_type == ViolationType.CLIFFHANGER_CLICHE:
            fixed = re.sub(r"^(可)?(他|她)不知道的是[，,、：:\s]*", "", fixed, count=1)
            if fixed == sentence:
                if re.fullmatch(r"(而这只是开始|这仅仅只是开始|命运的齿轮开始转动)[。！？!?]?", fixed):
                    fixed = ""
                elif re.fullmatch(r"(真正的.{0,10}才刚刚开始|更大的风暴还在后面|一场.{0,12}(即将来临|正在逼近))[。！？!?]?", fixed):
                    fixed = ""

        fixed = fixed.strip()
        if fixed and fixed[-1] not in _SENTENCE_END_CHARS:
            fixed += "。"
        return fixed
    
    def _auto_fix(self, content: str, violations: List[Violation]) -> str:
        """
        尝试自动修正违规内容
        
        策略：
        1. 死亡角色复活 -> 将相关段落改为回忆
        2. AI 味句子 -> 删除套路前缀或空泛收束
        """
        fixed_content = content
        
        # 按位置降序排序，从后往前修正避免位置偏移
        sorted_violations = sorted(violations, key=lambda v: v.position, reverse=True)
        
        for violation in sorted_violations:
            if violation.violation_type == ViolationType.DEAD_CHARACTER_REVIVED:
                # 尝试将相关内容改为回忆
                evidence = violation.evidence
                
                # 找到这段内容的完整句子
                start_pos = fixed_content.find(evidence)
                if start_pos >= 0:
                    # 找句子边界
                    sent_start = fixed_content.rfind('。', 0, start_pos)
                    sent_start = sent_start + 1 if sent_start >= 0 else start_pos
                    
                    sent_end = fixed_content.find('。', start_pos + len(evidence))
                    sent_end = sent_end + 1 if sent_end >= 0 else start_pos + len(evidence)
                    
                    sentence = fixed_content[sent_start:sent_end]
                    
                    # 添加回忆标记
                    fixed_sentence = f"【回忆开始】{sentence}【回忆结束】"
                    
                    fixed_content = (
                        fixed_content[:sent_start] + 
                        fixed_sentence + 
                        fixed_content[sent_end:]
                    )
                    
                    logger.info(f"[Validator] 自动修正: 将涉及死亡角色的内容改为回忆场景")
            elif violation.violation_type in {
                ViolationType.SUMMARY_SENTENCE,
                ViolationType.JUDGMENT_SENTENCE,
                ViolationType.EXPLANATORY_SENTENCE,
                ViolationType.CLIFFHANGER_CLICHE,
            }:
                sent_start, sent_end = self._find_sentence_bounds(fixed_content, violation.position)
                if sent_end <= sent_start:
                    continue

                sentence = fixed_content[sent_start:sent_end]
                fixed_sentence = self._rewrite_style_sentence(sentence, violation.violation_type)
                if fixed_sentence == sentence:
                    continue

                fixed_content = fixed_content[:sent_start] + fixed_sentence + fixed_content[sent_end:]
                logger.info(f"[Validator] 自动修正: 弱化 AI 味句式 {violation.violation_type.value}")
        
        fixed_content = re.sub(r"\n{3,}", "\n\n", fixed_content)
        return fixed_content
    
    def get_validation_report(self, result: ValidationResult) -> str:
        """生成验证报告"""
        lines = ["=== 内容验证报告 ===\n"]
        
        if result.is_valid:
            lines.append("✅ 验证通过，未发现严重违规\n")
        else:
            lines.append("❌ 验证未通过，存在以下问题：\n")
        
        for v in result.violations:
            icon = "🔴" if v.severity == "critical" else "🟡"
            lines.append(f"{icon} [{v.violation_type.value}] {v.description}")
            lines.append(f"   证据: {v.evidence[:50]}...")
            lines.append(f"   建议: {v.suggestion}")
            lines.append("")
        
        if result.auto_fixed:
            lines.append("\n✏️ 已自动修正部分问题")
        
        return "\n".join(lines)


class PostGenerationProcessor:
    """
    生成后处理器
    
    整合多种后处理方法：
    1. 内容验证
    2. 自动修正
    3. 一致性评分
    4. 必要时触发重新生成
    """
    
    def __init__(
        self,
        validator: ContentValidator,
        max_regeneration_attempts: int = 2
    ):
        """
        初始化处理器
        
        Args:
            validator: 内容验证器
            max_regeneration_attempts: 最大重新生成次数
        """
        self.validator = validator
        self.max_regeneration_attempts = max_regeneration_attempts
    
    async def process(
        self,
        content: str,
        chapter_number: int,
        regenerate_callback=None
    ) -> Tuple[str, ValidationResult]:
        """
        处理生成的内容
        
        Args:
            content: 生成的章节内容
            chapter_number: 章节序号
            regenerate_callback: 重新生成的回调函数
        
        Returns:
            (处理后的内容, 验证结果)
        """
        # 加载最新约束
        self.validator.load_constraints()
        
        # 第一次验证
        result = self.validator.validate(content, chapter_number, auto_fix=True)
        
        if result.auto_fixed and result.fixed_content:
            content = result.fixed_content
            logger.info("[PostProcessor] 应用自动修正")
        
        # 如果仍有严重问题且有重新生成回调，尝试重新生成
        if result.has_critical and regenerate_callback:
            for attempt in range(self.max_regeneration_attempts):
                logger.warning(f"[PostProcessor] 尝试重新生成 (第 {attempt + 1} 次)")
                
                # 将违规信息添加到重新生成的提示中
                violation_hints = [
                    f"请避免: {v.description}" 
                    for v in result.violations 
                    if v.severity == "critical"
                ]
                
                new_content = await regenerate_callback(
                    extra_constraints=violation_hints
                )
                
                if new_content:
                    result = self.validator.validate(new_content, chapter_number)
                    if not result.has_critical:
                        content = new_content
                        logger.info("[PostProcessor] 重新生成成功，通过验证")
                        break
        
        return content, result
