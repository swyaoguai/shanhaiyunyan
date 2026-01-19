# -*- coding: utf-8 -*-
"""
剧情约束管理模块

自动从章节内容中提取关键剧情约束，存储到知识库中。
在续写时检索这些约束，防止剧情设定逻辑出错。

约束类型：
- character_death: 角色死亡（禁止复活）
- character_status: 角色状态变化（受伤、失忆、能力丧失等）
- character_power: 角色能力/境界等级
- important_event: 重要事件
- world_rule: 世界规则/设定（力量体系、禁忌、法则）
- relationship: 角色关系变化
- item_status: 重要物品状态
- secret_revealed: 已揭露的秘密
- promise_oath: 承诺/誓言
- location_change: 地点/领地归属变化
- timeline: 重要时间节点
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ConstraintType(Enum):
    """约束类型"""
    CHARACTER_DEATH = "character_death"
    CHARACTER_STATUS = "character_status"
    CHARACTER_POWER = "character_power"
    IMPORTANT_EVENT = "important_event"
    WORLD_RULE = "world_rule"
    RELATIONSHIP = "relationship"
    ITEM_STATUS = "item_status"
    SECRET_REVEALED = "secret_revealed"
    PROMISE_OATH = "promise_oath"
    LOCATION_CHANGE = "location_change"
    TIMELINE = "timeline"


@dataclass
class PlotConstraint:
    """剧情约束"""
    constraint_id: str
    constraint_type: str
    description: str
    chapter_id: str
    chapter_number: int
    severity: str = "high"  # high, medium, low
    entities: List[str] = field(default_factory=list)  # 涉及的实体（角色名、物品名等）
    context: str = ""  # 原文上下文
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotConstraint":
        return cls(**data)


class PlotConstraintExtractor:
    """
    剧情约束提取器
    
    从章节文本中自动提取关键剧情约束。
    使用规则匹配和关键词检测。
    确保剧情设定逻辑一致性。
    """
    
    # 死亡相关关键词
    DEATH_KEYWORDS = [
        r'(?:死了|死亡|丧生|殒命|阵亡|牺牲|命丧|身亡|毙命|气绝|断气)',
        r'(?:杀死|杀害|击杀|斩杀|灭杀|诛杀|弑|杀掉)',
        r'(?:葬身|陨落|归西|驾崩|薨|殁)',
        r'(?:不治身亡|魂归天外|一命呜呼)',
    ]
    
    # 状态变化关键词
    STATUS_KEYWORDS = [
        r'(?:重伤|昏迷|失忆|失明|残疾|瘫痪|中毒)',
        r'(?:废掉|废除|封印|剥夺).*(?:修为|功力|能力)',
        r'(?:被困|囚禁|封印|镇压)',
        r'(?:怀孕|有孕|身怀六甲)',
        r'(?:失去|丧失).*(?:记忆|神智|理智)',
    ]
    
    # 能力/境界变化关键词
    POWER_KEYWORDS = [
        r'(?:突破|晋级|进阶|晋升).*(?:境|级|层|阶|段)',
        r'(?:修为|境界|实力).*(?:提升|增长|大进|暴涨)',
        r'(?:领悟|悟透|参透|掌握).*(?:法则|大道|神通|秘法)',
        r'(?:觉醒|激发|开启).*(?:血脉|天赋|潜能)',
        r'(?:筑基|金丹|元婴|化神|渡劫|大乘|飞升)',
        r'(?:一品|二品|三品|四品|五品|六品|七品|八品|九品)',
        r'(?:练气|筑基|结丹|元婴|化神|炼虚|合道|大乘)',
    ]
    
    # 重要事件关键词
    EVENT_KEYWORDS = [
        r'(?:宣战|开战|结盟|背叛|投降)',
        r'(?:灭门|覆灭|毁灭|沦陷)',
        r'(?:突破|晋级|进阶|觉醒|契约)',
        r'(?:揭露|发现|得知).*(?:真相|秘密|身世)',
        r'(?:继承|传承|获得).*(?:衣钵|法宝|传承)',
        r'(?:大战|决战|激战|血战)',
    ]
    
    # 关系变化关键词
    RELATIONSHIP_KEYWORDS = [
        r'(?:结婚|成亲|拜堂|订婚)',
        r'(?:分手|决裂|反目|仇敌)',
        r'(?:拜师|收徒|结义|认亲)',
        r'(?:收为|认作|成为).*(?:弟子|徒弟|义子|义女)',
        r'(?:情敌|对头|死敌|宿敌)',
    ]
    
    # 世界规则/设定关键词
    WORLD_RULE_KEYWORDS = [
        r'(?:绝对|永远|从不|不可能).*(?:不能|无法|禁止)',
        r'(?:天道|法则|规则).*(?:规定|限制|约束)',
        r'(?:禁忌|禁区|禁地).*(?:不可|不能|绝不)',
        r'(?:只有|唯有|必须).*(?:才能|方可|方能)',
        r'(?:传说|相传|古籍记载)',
        r'(?:修炼|修行|修仙).*(?:法则|体系|等级)',
    ]
    
    # 物品状态关键词
    ITEM_KEYWORDS = [
        r'(?:法宝|神器|灵器|宝物).*(?:损毁|破碎|消失|被夺)',
        r'(?:获得|得到|炼制|铸造).*(?:法宝|神器|灵器)',
        r'(?:丹药|灵丹|妙药).*(?:炼成|服下|失效)',
        r'(?:功法|秘籍|典籍).*(?:获得|失落|传授)',
    ]
    
    # 秘密揭露关键词
    SECRET_KEYWORDS = [
        r'(?:原来|竟然|没想到|居然).*(?:是|就是)',
        r'(?:真相|秘密|身世|来历).*(?:揭开|暴露|大白)',
        r'(?:得知|发现|知道).*(?:真相|秘密|实情)',
        r'(?:隐藏|隐瞒).*(?:身份|过去|真相)',
        r'(?:告知|告诉|透露).*(?:真相|秘密|实情)',
    ]
    
    # 承诺/誓言关键词
    PROMISE_KEYWORDS = [
        r'(?:发誓|起誓|立誓|誓言)',
        r'(?:承诺|保证|答应|许诺)',
        r'(?:约定|契约|盟约)',
        r'(?:绝不|永不|永远不会)',
    ]
    
    # 地点/领地变化关键词
    LOCATION_KEYWORDS = [
        r'(?:攻占|占领|夺取|沦陷).*(?:城|宗|门|派|国)',
        r'(?:迁移|离开|前往|抵达).*(?:城|宗|门|派|域)',
        r'(?:建立|创建|成立).*(?:势力|宗门|组织)',
        r'(?:覆灭|灭亡|毁灭).*(?:宗门|门派|势力)',
    ]
    
    # 时间节点关键词
    TIMELINE_KEYWORDS = [
        r'(?:三年|五年|十年|百年|千年)(?:后|前|之后|之前)',
        r'(?:一个月|三个月|半年)(?:后|前|之后|之前)',
        r'(?:明天|后天|三日|七日)(?:后|之后)',
        r'(?:大比|大会|盛典|祭祀).*(?:开始|举行|结束)',
    ]
    
    def __init__(self):
        """初始化提取器"""
        # 编译正则表达式
        self._death_patterns = [re.compile(p, re.UNICODE) for p in self.DEATH_KEYWORDS]
        self._status_patterns = [re.compile(p, re.UNICODE) for p in self.STATUS_KEYWORDS]
        self._power_patterns = [re.compile(p, re.UNICODE) for p in self.POWER_KEYWORDS]
        self._event_patterns = [re.compile(p, re.UNICODE) for p in self.EVENT_KEYWORDS]
        self._relationship_patterns = [re.compile(p, re.UNICODE) for p in self.RELATIONSHIP_KEYWORDS]
        self._world_rule_patterns = [re.compile(p, re.UNICODE) for p in self.WORLD_RULE_KEYWORDS]
        self._item_patterns = [re.compile(p, re.UNICODE) for p in self.ITEM_KEYWORDS]
        self._secret_patterns = [re.compile(p, re.UNICODE) for p in self.SECRET_KEYWORDS]
        self._promise_patterns = [re.compile(p, re.UNICODE) for p in self.PROMISE_KEYWORDS]
        self._location_patterns = [re.compile(p, re.UNICODE) for p in self.LOCATION_KEYWORDS]
        self._timeline_patterns = [re.compile(p, re.UNICODE) for p in self.TIMELINE_KEYWORDS]
        
        # 人名识别模式（简化版，匹配常见中文人名格式）
        self._name_pattern = re.compile(
            r'(?:他|她|它|其|那个|这个)?'
            r'([一-龥]{2,4}(?:子|儿|哥|姐|叔|婶|爷|奶|公|母|先生|小姐)?)'
        )
    
    def extract_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """
        从章节内容中提取约束
        
        Args:
            content: 章节内容
            chapter_id: 章节ID
            chapter_number: 章节序号
        
        Returns:
            提取到的约束列表
        """
        constraints = []
        
        # 提取死亡约束（最高优先级）
        death_constraints = self._extract_death_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(death_constraints)
        
        # 提取状态变化约束
        status_constraints = self._extract_status_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(status_constraints)
        
        # 提取能力/境界变化约束
        power_constraints = self._extract_power_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(power_constraints)
        
        # 提取重要事件约束
        event_constraints = self._extract_event_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(event_constraints)
        
        # 提取关系变化约束
        relationship_constraints = self._extract_relationship_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(relationship_constraints)
        
        # 提取世界规则约束
        world_rule_constraints = self._extract_world_rule_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(world_rule_constraints)
        
        # 提取物品状态约束
        item_constraints = self._extract_item_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(item_constraints)
        
        # 提取秘密揭露约束
        secret_constraints = self._extract_secret_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(secret_constraints)
        
        # 提取承诺/誓言约束
        promise_constraints = self._extract_promise_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(promise_constraints)
        
        # 提取地点/领地变化约束
        location_constraints = self._extract_location_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(location_constraints)
        
        # 提取时间线约束
        timeline_constraints = self._extract_timeline_constraints(
            content, chapter_id, chapter_number
        )
        constraints.extend(timeline_constraints)
        
        logger.info(f"[PlotConstraint] 从章节 {chapter_number} 提取到 {len(constraints)} 个约束")
        return constraints
    
    def _extract_death_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取死亡约束"""
        constraints = []
        
        for pattern in self._death_patterns:
            for match in pattern.finditer(content):
                # 获取上下文（前后各50字）
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                # 尝试从上下文中提取人名
                entities = self._extract_names(context)
                
                if entities:
                    constraint = PlotConstraint(
                        constraint_id=f"death_{chapter_id}_{match.start()}",
                        constraint_type=ConstraintType.CHARACTER_DEATH.value,
                        description=f"角色死亡: {', '.join(entities)}",
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        severity="high",
                        entities=entities,
                        context=context.strip()
                    )
                    constraints.append(constraint)
        
        return constraints
    
    def _extract_status_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取状态变化约束"""
        constraints = []
        
        for pattern in self._status_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                if entities:
                    constraint = PlotConstraint(
                        constraint_id=f"status_{chapter_id}_{match.start()}",
                        constraint_type=ConstraintType.CHARACTER_STATUS.value,
                        description=f"状态变化: {match.group()}",
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        severity="medium",
                        entities=entities,
                        context=context.strip()
                    )
                    constraints.append(constraint)
        
        return constraints
    
    def _extract_event_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取重要事件约束"""
        constraints = []
        
        for pattern in self._event_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"event_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.IMPORTANT_EVENT.value,
                    description=f"重要事件: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="medium",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_relationship_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取关系变化约束"""
        constraints = []
        
        for pattern in self._relationship_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                if len(entities) >= 2:  # 关系变化至少涉及两个实体
                    constraint = PlotConstraint(
                        constraint_id=f"rel_{chapter_id}_{match.start()}",
                        constraint_type=ConstraintType.RELATIONSHIP.value,
                        description=f"关系变化: {match.group()}",
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        severity="medium",
                        entities=entities,
                        context=context.strip()
                    )
                    constraints.append(constraint)
        
        return constraints
    
    def _extract_power_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取能力/境界变化约束"""
        constraints = []
        
        for pattern in self._power_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"power_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.CHARACTER_POWER.value,
                    description=f"能力/境界变化: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="high",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_world_rule_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取世界规则约束"""
        constraints = []
        
        for pattern in self._world_rule_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 80)
                end = min(len(content), match.end() + 80)
                context = content[start:end]
                
                constraint = PlotConstraint(
                    constraint_id=f"rule_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.WORLD_RULE.value,
                    description=f"世界规则/设定: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="high",
                    entities=[],
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_item_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取物品状态约束"""
        constraints = []
        
        for pattern in self._item_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"item_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.ITEM_STATUS.value,
                    description=f"物品状态: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="medium",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_secret_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取秘密揭露约束"""
        constraints = []
        
        for pattern in self._secret_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 80)
                end = min(len(content), match.end() + 80)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"secret_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.SECRET_REVEALED.value,
                    description=f"秘密揭露: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="high",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_promise_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取承诺/誓言约束"""
        constraints = []
        
        for pattern in self._promise_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 80)
                end = min(len(content), match.end() + 80)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"promise_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.PROMISE_OATH.value,
                    description=f"承诺/誓言: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="high",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_location_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取地点/领地变化约束"""
        constraints = []
        
        for pattern in self._location_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                entities = self._extract_names(context)
                
                constraint = PlotConstraint(
                    constraint_id=f"location_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.LOCATION_CHANGE.value,
                    description=f"地点/领地变化: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="medium",
                    entities=entities,
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_timeline_constraints(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int
    ) -> List[PlotConstraint]:
        """提取时间线约束"""
        constraints = []
        
        for pattern in self._timeline_patterns:
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                context = content[start:end]
                
                constraint = PlotConstraint(
                    constraint_id=f"timeline_{chapter_id}_{match.start()}",
                    constraint_type=ConstraintType.TIMELINE.value,
                    description=f"时间节点: {match.group()}",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    severity="medium",
                    entities=[],
                    context=context.strip()
                )
                constraints.append(constraint)
        
        return constraints
    
    def _extract_names(self, text: str) -> List[str]:
        """从文本中提取人名（简化版）"""
        # 常见非人名词汇过滤
        stop_words = {
            '这个', '那个', '什么', '怎么', '为什么', '如果', '但是', '然后',
            '已经', '就是', '可以', '不能', '没有', '什么', '自己', '他们',
            '我们', '你们', '大家', '所有', '一切', '一些', '几个', '很多'
        }
        
        names = []
        for match in self._name_pattern.finditer(text):
            name = match.group(1)
            if name and len(name) >= 2 and name not in stop_words:
                # 额外过滤：排除常见动词、形容词开头的词
                if not any(name.startswith(c) for c in ['是', '有', '在', '被', '把', '让']):
                    names.append(name)
        
        # 去重并保持顺序
        seen = set()
        unique_names = []
        for name in names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)
        
        return unique_names[:5]  # 最多返回5个名字


class PlotConstraintStore:
    """
    剧情约束存储
    
    将约束存储到知识库中，并提供检索接口。
    """
    
    def __init__(self, knowledge_base):
        """
        初始化约束存储
        
        Args:
            knowledge_base: 知识库实例
        """
        self.knowledge_base = knowledge_base
        self.extractor = PlotConstraintExtractor()
        
        # 约束缓存
        self._constraints_cache: Dict[str, List[PlotConstraint]] = {}
    
    def extract_and_store(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int,
        title: str = ""
    ) -> List[PlotConstraint]:
        """
        从章节内容提取约束并存储
        
        Args:
            content: 章节内容
            chapter_id: 章节ID
            chapter_number: 章节序号
            title: 章节标题
        
        Returns:
            提取到的约束列表
        """
        # 提取约束
        constraints = self.extractor.extract_constraints(
            content, chapter_id, chapter_number
        )
        
        if not constraints:
            return []
        
        # 构建约束摘要文本
        constraint_text = self._build_constraint_text(constraints, chapter_number, title)
        
        # 存储到知识库作为特殊章节
        try:
            self.knowledge_base.add_chapter(
                chapter_id=f"constraints_{chapter_id}",
                title=f"【剧情约束】第{chapter_number}章",
                content=constraint_text,
                chapter_number=chapter_number * 10000,  # 使用大数使约束排在后面
                metadata={
                    "type": "plot_constraints",
                    "source_chapter": chapter_id,
                    "constraint_count": len(constraints),
                    "constraint_types": list(set(c.constraint_type for c in constraints))
                }
            )
            logger.info(f"[PlotConstraint] 存储了 {len(constraints)} 个约束")
        except Exception as e:
            logger.error(f"[PlotConstraint] 存储约束失败: {e}")
        
        # 更新缓存
        self._constraints_cache[chapter_id] = constraints
        
        return constraints
    
    def _build_constraint_text(
        self,
        constraints: List[PlotConstraint],
        chapter_number: int,
        title: str
    ) -> str:
        """构建约束文本"""
        lines = [f"=== 第{chapter_number}章 {title} 关键剧情设定 ===\n"]
        
        # 按类型分组
        death_constraints = [c for c in constraints if c.constraint_type == ConstraintType.CHARACTER_DEATH.value]
        status_constraints = [c for c in constraints if c.constraint_type == ConstraintType.CHARACTER_STATUS.value]
        power_constraints = [c for c in constraints if c.constraint_type == ConstraintType.CHARACTER_POWER.value]
        event_constraints = [c for c in constraints if c.constraint_type == ConstraintType.IMPORTANT_EVENT.value]
        relationship_constraints = [c for c in constraints if c.constraint_type == ConstraintType.RELATIONSHIP.value]
        world_rule_constraints = [c for c in constraints if c.constraint_type == ConstraintType.WORLD_RULE.value]
        item_constraints = [c for c in constraints if c.constraint_type == ConstraintType.ITEM_STATUS.value]
        secret_constraints = [c for c in constraints if c.constraint_type == ConstraintType.SECRET_REVEALED.value]
        promise_constraints = [c for c in constraints if c.constraint_type == ConstraintType.PROMISE_OATH.value]
        location_constraints = [c for c in constraints if c.constraint_type == ConstraintType.LOCATION_CHANGE.value]
        timeline_constraints = [c for c in constraints if c.constraint_type == ConstraintType.TIMELINE.value]
        
        if death_constraints:
            lines.append("【角色生死 - 不可更改】")
            for c in death_constraints:
                entities_str = ', '.join(c.entities) if c.entities else "未知角色"
                lines.append(f"  ❌ {entities_str} 已死亡")
                lines.append(f"     来源: {c.context[:80]}...")
            lines.append("")
        
        if power_constraints:
            lines.append("【能力/境界等级】")
            for c in power_constraints:
                entities_str = ', '.join(c.entities) if c.entities else "相关角色"
                lines.append(f"  ⬆ {entities_str}: {c.description}")
            lines.append("")
        
        if world_rule_constraints:
            lines.append("【世界规则/设定】")
            for c in world_rule_constraints:
                lines.append(f"  📜 {c.context[:100]}...")
            lines.append("")
        
        if secret_constraints:
            lines.append("【已揭露的秘密】")
            for c in secret_constraints:
                entities_str = ', '.join(c.entities) if c.entities else ""
                lines.append(f"  🔓 {entities_str}: {c.context[:80]}...")
            lines.append("")
        
        if promise_constraints:
            lines.append("【承诺/誓言】")
            for c in promise_constraints:
                entities_str = ', '.join(c.entities) if c.entities else ""
                lines.append(f"  🤝 {entities_str}: {c.context[:80]}...")
            lines.append("")
        
        if status_constraints:
            lines.append("【角色状态变化】")
            for c in status_constraints:
                entities_str = ', '.join(c.entities) if c.entities else ""
                lines.append(f"  - {entities_str}: {c.description}")
            lines.append("")
        
        if relationship_constraints:
            lines.append("【关系变化】")
            for c in relationship_constraints:
                entities_str = ', '.join(c.entities) if c.entities else ""
                lines.append(f"  👥 {entities_str}: {c.description}")
            lines.append("")
        
        if item_constraints:
            lines.append("【重要物品状态】")
            for c in item_constraints:
                lines.append(f"  📦 {c.description}")
            lines.append("")
        
        if location_constraints:
            lines.append("【地点/势力变化】")
            for c in location_constraints:
                lines.append(f"  🏰 {c.description}")
            lines.append("")
        
        if event_constraints:
            lines.append("【重要事件】")
            for c in event_constraints:
                lines.append(f"  ⚡ {c.description}")
            lines.append("")
        
        if timeline_constraints:
            lines.append("【时间节点】")
            for c in timeline_constraints:
                lines.append(f"  ⏰ {c.description}")
            lines.append("")
        
        return "\n".join(lines)
    
    def search_constraints(
        self,
        query: str = "",
        constraint_types: Optional[List[str]] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        检索剧情约束
        
        Args:
            query: 检索查询（可选，为空则返回所有约束）
            constraint_types: 约束类型过滤
            top_k: 返回数量
        
        Returns:
            约束列表
        """
        try:
            # 使用特定查询检索约束
            search_query = query or "剧情约束 角色死亡 重要事件"
            
            results = self.knowledge_base.search(
                query=search_query,
                top_k=top_k * 2,  # 多取一些，后面过滤
                search_type="hybrid"
            )
            
            constraints = []
            for result in results.results:
                # 只返回约束类型的文档
                if result.metadata.get("type") == "plot_constraints":
                    constraints.append({
                        "document": result.document,
                        "chapter_id": result.metadata.get("source_chapter"),
                        "constraint_count": result.metadata.get("constraint_count", 0),
                        "constraint_types": result.metadata.get("constraint_types", []),
                        "score": result.score
                    })
            
            return constraints[:top_k]
            
        except Exception as e:
            logger.error(f"[PlotConstraint] 检索约束失败: {e}")
            return []
    
    def get_death_constraints(self) -> List[str]:
        """
        获取所有死亡角色列表
        
        Returns:
            死亡角色名列表
        """
        dead_characters = set()
        
        try:
            results = self.knowledge_base.search(
                query="角色死亡 死了 阵亡 牺牲",
                top_k=50,
                search_type="fulltext"
            )
            
            for result in results.results:
                if result.metadata.get("type") == "plot_constraints":
                    # 从文档内容中提取死亡角色
                    content = result.document
                    if "【角色死亡" in content:
                        # 提取角色名
                        lines = content.split("\n")
                        for line in lines:
                            if line.strip().startswith("- ") and ":" in line:
                                names_part = line.split(":")[0].replace("- ", "").strip()
                                for name in names_part.split(","):
                                    name = name.strip()
                                    if name:
                                        dead_characters.add(name)
            
        except Exception as e:
            logger.error(f"[PlotConstraint] 获取死亡角色失败: {e}")
        
        return list(dead_characters)
    
    def get_all_constraints_summary(self) -> str:
        """
        获取所有约束的摘要
        
        Returns:
            约束摘要文本
        """
        try:
            results = self.knowledge_base.search(
                query="剧情约束",
                top_k=100,
                search_type="fulltext"
            )
            
            summaries = []
            for result in results.results:
                if result.metadata.get("type") == "plot_constraints":
                    summaries.append(result.document)
            
            if summaries:
                return "\n\n".join(summaries)
            
            return ""
            
        except Exception as e:
            logger.error(f"[PlotConstraint] 获取约束摘要失败: {e}")
            return ""