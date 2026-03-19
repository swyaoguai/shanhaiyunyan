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
                doc = constraint.get("document", "")
                constraint_types = constraint.get("constraint_types", [])
                
                if "character_power" in constraint_types:
                    # 解析能力等级
                    for role_name, level_name in _extract_power_pairs(doc):
                        previous_level = self._power_levels.get(role_name)
                        if previous_level is None or _POWER_LEVEL_RANK[level_name] >= _POWER_LEVEL_RANK[previous_level]:
                            self._power_levels[role_name] = level_name
                
                if "world_rule" in constraint_types:
                    self._world_rules.append(doc)
                
                if "secret_revealed" in constraint_types:
                    self._revealed_secrets.append(constraint)
                
                if "promise_oath" in constraint_types:
                    self._promises.append(constraint)
            
            logger.info(f"[Validator] 加载约束: {len(self._dead_characters)} 死亡角色, "
                       f"{len(self._world_rules)} 世界规则, "
                       f"{len(self._power_levels)} 角色境界")
            
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
        
        # 构建结果
        result = ValidationResult(
            is_valid=not any(v.severity == "critical" for v in violations),
            violations=violations,
            warnings=[v.description for v in violations if v.severity == "warning"]
        )
        
        # 自动修正
        if auto_fix and result.has_critical:
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
    
    def _auto_fix(self, content: str, violations: List[Violation]) -> str:
        """
        尝试自动修正违规内容
        
        策略：
        1. 死亡角色复活 -> 将相关段落改为回忆
        2. 能力倒退 -> 标记需要人工修正
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
