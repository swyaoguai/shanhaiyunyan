# -*- coding: utf-8 -*-
"""
知识库混入类

为多Agent协作模式提供统一的知识库访问接口
支持增强的知识库功能：动态搜索、约束检测、上下文压缩
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class KnowledgeBaseMixin:
    """
    知识库混入类
    
    为Agent提供统一的知识库访问能力：
    - 高级搜索（动态权重、重排序）
    - 剧情约束检索
    - 死亡角色检测
    - 写作上下文获取
    
    使用方法：
    class MyAgent(BaseAgent, KnowledgeBaseMixin):
        def __init__(self):
            super().__init__(...)
            self.init_knowledge_mixin()
    """
    
    # 类属性
    _knowledge_base = None
    _constraint_store = None
    _use_advanced_search: bool = True
    _cached_dead_characters: List[str] = []
    
    def init_knowledge_mixin(self, knowledge_base=None):
        """
        初始化知识库混入
        
        Args:
            knowledge_base: 知识库实例
        """
        self._knowledge_base = knowledge_base
        self._constraint_store = None
        self._use_advanced_search = True
        self._cached_dead_characters = []
        
        if knowledge_base:
            self._init_constraint_store()
    
    def _init_constraint_store(self):
        """初始化剧情约束存储"""
        if not self._knowledge_base:
            return
        
        try:
            from ..knowledge_base.logic_layer.plot_constraints import PlotConstraintStore
            self._constraint_store = PlotConstraintStore(self._knowledge_base)
            
            # 加载已有的死亡角色
            dead_chars = self._constraint_store.get_death_constraints()
            self._cached_dead_characters = list(dead_chars)
            
            if self._cached_dead_characters:
                agent_name = getattr(self, 'name', 'Agent')
                logger.info(f"[{agent_name}] 从知识库加载了 {len(self._cached_dead_characters)} 个死亡角色")
                
        except Exception as e:
            agent_name = getattr(self, 'name', 'Agent')
            logger.warning(f"[{agent_name}] 剧情约束存储初始化失败: {e}")
            self._constraint_store = None
    
    def set_knowledge_base(self, kb) -> None:
        """
        设置知识库实例
        
        Args:
            kb: 知识库实例
        """
        self._knowledge_base = kb
        if kb:
            self._init_constraint_store()
        
        agent_name = getattr(self, 'name', 'Agent')
        logger.info(f"[{agent_name}] 知识库已配置")
    
    @property
    def knowledge_base(self):
        """获取知识库实例"""
        return self._knowledge_base
    
    @property
    def has_knowledge_base(self) -> bool:
        """是否已配置知识库"""
        return self._knowledge_base is not None
    
    def get_dead_characters(self) -> List[str]:
        """
        获取所有已死亡角色
        
        Returns:
            死亡角色列表
        """
        dead_chars = set(self._cached_dead_characters)
        
        # 尝试从知识库获取最新数据
        if self._knowledge_base:
            try:
                # 尝试使用高级接口
                if hasattr(self._knowledge_base, 'get_dead_characters'):
                    kb_dead = self._knowledge_base.get_dead_characters()
                    dead_chars.update(kb_dead)
                elif self._constraint_store:
                    kb_dead = self._constraint_store.get_death_constraints()
                    dead_chars.update(kb_dead)
            except Exception as e:
                agent_name = getattr(self, 'name', 'Agent')
                logger.warning(f"[{agent_name}] 获取死亡角色失败: {e}")
        
        return list(dead_chars)
    
    def add_dead_character(self, character_name: str) -> None:
        """
        添加死亡角色
        
        Args:
            character_name: 角色名
        """
        if character_name and character_name not in self._cached_dead_characters:
            self._cached_dead_characters.append(character_name)
            agent_name = getattr(self, 'name', 'Agent')
            logger.info(f"[{agent_name}] 记录角色死亡: {character_name}")
    
    async def search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        use_advanced: bool = None,
        include_constraints: bool = True
    ) -> Dict[str, Any]:
        """
        搜索知识库
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            use_advanced: 是否使用高级搜索
            include_constraints: 是否包含约束
        
        Returns:
            搜索结果字典
        """
        if not self._knowledge_base:
            return {
                "relevant_content": [],
                "constraints": [],
                "dead_characters": []
            }
        
        use_advanced = use_advanced if use_advanced is not None else self._use_advanced_search
        result = {
            "relevant_content": [],
            "constraints": [],
            "dead_characters": self.get_dead_characters()
        }
        
        try:
            if use_advanced and hasattr(self._knowledge_base, 'advanced_search'):
                # 使用高级搜索
                search_resp = self._knowledge_base.advanced_search(
                    query=query,
                    top_k=top_k,
                    use_dynamic_weights=True,
                    rerank=True,
                    compress_context=True
                )
                
                for r in search_resp.results:
                    result["relevant_content"].append({
                        "content": r.content if hasattr(r, 'content') else r.document[:300],
                        "score": r.score,
                        "chapter": r.metadata.get("chapter_id") if hasattr(r, 'metadata') else None
                    })
            else:
                # 使用基础搜索
                search_resp = self._knowledge_base.search(
                    query=query,
                    top_k=top_k
                )
                
                for r in search_resp.results:
                    result["relevant_content"].append({
                        "content": r.document[:300] if hasattr(r, 'document') else str(r)[:300],
                        "score": r.score if hasattr(r, 'score') else 0.0
                    })
            
            # 获取约束
            if include_constraints:
                if hasattr(self._knowledge_base, 'get_active_constraints'):
                    constraints = self._knowledge_base.get_active_constraints()
                    result["constraints"] = [
                        {"type": c.constraint_type, "description": c.title, "entities": c.entities}
                        for c in constraints[:5]
                    ]
                elif self._constraint_store:
                    constraints = self._constraint_store.search_constraints(query[:200], top_k=5)
                    result["constraints"] = constraints
                    
        except Exception as e:
            agent_name = getattr(self, 'name', 'Agent')
            logger.warning(f"[{agent_name}] 知识库搜索失败: {e}")
        
        return result
    
    async def get_writing_context(
        self,
        query: str,
        current_chapter: int = 0,
        max_tokens: int = 2000
    ) -> Dict[str, Any]:
        """
        获取写作上下文
        
        一站式获取写作所需的所有上下文信息
        
        Args:
            query: 当前写作相关的查询
            current_chapter: 当前章节号
            max_tokens: 最大token数
        
        Returns:
            写作上下文字典
        """
        if not self._knowledge_base:
            return {
                "relevant_content": [],
                "constraints": [],
                "dead_characters": self.get_dead_characters(),
                "total_tokens_estimate": 0
            }
        
        try:
            # 尝试使用高级接口
            if hasattr(self._knowledge_base, 'get_context_for_writing'):
                return self._knowledge_base.get_context_for_writing(
                    query=query,
                    current_chapter=current_chapter,
                    max_tokens=max_tokens,
                    include_constraints=True
                )
        except Exception as e:
            agent_name = getattr(self, 'name', 'Agent')
            logger.warning(f"[{agent_name}] get_context_for_writing 失败: {e}")
        
        # 回退到基础搜索
        return await self.search_knowledge(query, top_k=5, include_constraints=True)
    
    def extract_constraints_from_content(
        self,
        content: str,
        chapter_id: str,
        chapter_number: int,
        title: str = ""
    ) -> List[Dict[str, Any]]:
        """
        从内容中提取并存储剧情约束
        
        Args:
            content: 章节内容
            chapter_id: 章节ID
            chapter_number: 章节序号
            title: 章节标题
        
        Returns:
            提取的约束列表
        """
        if not self._constraint_store:
            return []
        
        try:
            constraints = self._constraint_store.extract_and_store(
                content=content,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                title=title
            )
            
            # 更新死亡角色缓存
            for constraint in constraints:
                if constraint.constraint_type == "character_death":
                    for entity in constraint.entities:
                        self.add_dead_character(entity)
            
            agent_name = getattr(self, 'name', 'Agent')
            if constraints:
                logger.info(f"[{agent_name}] 提取了 {len(constraints)} 个剧情约束")
            
            return [
                {
                    "type": c.constraint_type,
                    "description": c.description,
                    "entities": c.entities
                }
                for c in constraints
            ]
            
        except Exception as e:
            agent_name = getattr(self, 'name', 'Agent')
            logger.warning(f"[{agent_name}] 提取剧情约束失败: {e}")
            return []
    
    def build_constraint_prompt(self) -> str:
        """
        构建约束提示词
        
        生成包含死亡角色和活跃约束的提示词片段
        
        Returns:
            约束提示词
        """
        parts = []
        
        # 死亡角色
        dead_chars = self.get_dead_characters()
        if dead_chars:
            parts.append("[已死亡角色 - 绝对禁止复活！]")
            parts.append("以下角色已在之前的章节中死亡，绝对不能让他们以活人身份出现：")
            for char in sorted(dead_chars):
                parts.append(f"  ❌ {char}")
            parts.append("")
        
        # 活跃约束
        if self._knowledge_base and hasattr(self._knowledge_base, 'get_active_constraints'):
            try:
                constraints = self._knowledge_base.get_active_constraints()
                if constraints:
                    parts.append("[重要剧情约束]")
                    for c in constraints[:5]:
                        parts.append(f"  - {c.title}")
                    parts.append("")
            except Exception:
                pass
        
        return "\n".join(parts)
    
    async def save_chapter_to_knowledge_base(
        self,
        chapter_id: str,
        title: str,
        content: str,
        chapter_number: int,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        保存章节到知识库
        
        包括：存储章节内容、提取剧情约束
        
        Args:
            chapter_id: 章节ID
            title: 章节标题
            content: 章节内容
            chapter_number: 章节序号
            metadata: 附加元数据
        
        Returns:
            是否成功
        """
        if not self._knowledge_base:
            return False
        
        try:
            # 存储章节
            self._knowledge_base.add_chapter(
                chapter_id=chapter_id,
                title=title,
                content=content,
                chapter_number=chapter_number,
                metadata=metadata or {}
            )
            
            # 提取约束
            self.extract_constraints_from_content(
                content=content,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                title=title
            )
            
            agent_name = getattr(self, 'name', 'Agent')
            logger.info(f"[{agent_name}] 章节 {chapter_number} 已保存到知识库")
            return True
            
        except Exception as e:
            agent_name = getattr(self, 'name', 'Agent')
            logger.error(f"[{agent_name}] 保存章节到知识库失败: {e}")
            return False


class SharedKnowledgeContext:
    """
    共享知识上下文
    
    用于多Agent协作时共享知识库状态
    """
    
    def __init__(self, knowledge_base=None):
        """
        初始化共享上下文
        
        Args:
            knowledge_base: 知识库实例
        """
        self.knowledge_base = knowledge_base
        self.dead_characters: List[str] = []
        self.active_constraints: List[Dict[str, Any]] = []
        self.chapter_summaries: Dict[int, str] = {}
        self.character_states: Dict[str, Dict[str, Any]] = {}
        
        # 从知识库加载初始状态
        if knowledge_base:
            self._load_initial_state()
    
    def _load_initial_state(self):
        """从知识库加载初始状态"""
        try:
            if hasattr(self.knowledge_base, 'get_dead_characters'):
                self.dead_characters = self.knowledge_base.get_dead_characters()
            
            if hasattr(self.knowledge_base, 'get_active_constraints'):
                constraints = self.knowledge_base.get_active_constraints()
                self.active_constraints = [
                    {"type": c.constraint_type, "description": c.title, "entities": c.entities}
                    for c in constraints
                ]
        except Exception as e:
            logger.warning(f"[SharedKnowledgeContext] 加载初始状态失败: {e}")
    
    def record_death(self, character: str, chapter: int):
        """记录角色死亡"""
        if character not in self.dead_characters:
            self.dead_characters.append(character)
            logger.info(f"[SharedKnowledgeContext] 记录角色死亡: {character} (第{chapter}章)")
    
    def add_constraint(self, constraint: Dict[str, Any]):
        """添加约束"""
        self.active_constraints.append(constraint)
    
    def update_chapter_summary(self, chapter: int, summary: str):
        """更新章节摘要"""
        self.chapter_summaries[chapter] = summary
    
    def update_character_state(self, character: str, state: Dict[str, Any]):
        """更新角色状态"""
        self.character_states[character] = state
    
    def get_context_for_chapter(self, chapter: int) -> Dict[str, Any]:
        """
        获取特定章节的上下文
        
        Args:
            chapter: 章节号
        
        Returns:
            章节上下文
        """
        # 获取前几章的摘要
        recent_summaries = {}
        for ch in range(max(1, chapter - 3), chapter):
            if ch in self.chapter_summaries:
                recent_summaries[ch] = self.chapter_summaries[ch]
        
        return {
            "dead_characters": self.dead_characters.copy(),
            "active_constraints": self.active_constraints.copy(),
            "recent_summaries": recent_summaries,
            "character_states": self.character_states.copy()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dead_characters": self.dead_characters,
            "active_constraints": self.active_constraints,
            "chapter_summaries": self.chapter_summaries,
            "character_states": self.character_states
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], knowledge_base=None) -> "SharedKnowledgeContext":
        """从字典创建"""
        ctx = cls(knowledge_base=knowledge_base)
        ctx.dead_characters = data.get("dead_characters", [])
        ctx.active_constraints = data.get("active_constraints", [])
        ctx.chapter_summaries = data.get("chapter_summaries", {})
        ctx.character_states = data.get("character_states", {})
        return ctx