"""
上下文管理器
实现"慢学AI"的Agentic Context Engineering理念
- Context Reduction: 可逆压缩vs不可逆摘要（增强：LLM智能摘要）
- Context Isolation: 各Agent独立上下文
- Context Synchronization: 跨Agent状态同步
- Context Caching: 上下文缓存优化
"""

import json
import hashlib
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..constants import WRITING_CONFIG, CONTEXT_PRIORITY, MESSAGE_BUS_CONFIG
from ..utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class ContextItem:
    """上下文项"""
    key: str
    value: Any
    category: str  # world, character, plot, chapter
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: int = 1
    compressed: bool = False  # 是否已压缩
    original_length: int = 0  # 原始长度（用于统计）
    
    def get_size(self) -> int:
        """获取值的大小（字符数）"""
        if isinstance(self.value, str):
            return len(self.value)
        return len(json.dumps(self.value, ensure_ascii=False))


@dataclass
class CompressionResult:
    """压缩结果"""
    original_text: str
    compressed_text: str
    original_length: int
    compressed_length: int
    compression_ratio: float
    method: str
    key_info_preserved: bool = True


# LLM摘要生成器类型
LLMSummarizer = Callable[[str, int], Awaitable[str]]


class ContextManager:
    """
    上下文管理器
    
    核心职责：
    1. 管理各类上下文信息的存储和检索
    2. 根据Agent类型提供相关上下文
    3. 压缩长上下文防止token溢出（支持LLM智能摘要）
    4. 跨Agent同步关键信息
    5. 上下文缓存和去重
    """
    
    def __init__(
        self,
        project_dir: Optional[Path] = None,
        llm_summarizer: Optional[LLMSummarizer] = None,
        max_context_tokens: int = WRITING_CONFIG.MAX_CONTEXT_TOKENS
    ):
        """
        初始化上下文管理器
        
        Args:
            project_dir: 项目目录，用于持久化存储
            llm_summarizer: LLM摘要生成函数（用于智能压缩）
            max_context_tokens: 最大上下文token数
        """
        self.project_dir = project_dir
        self.contexts: Dict[str, ContextItem] = {}
        self.history: List[Dict] = []  # 操作历史
        self.llm_summarizer = llm_summarizer
        self.max_context_tokens = max_context_tokens
        
        # 压缩缓存（避免重复压缩）
        self._compression_cache: Dict[str, str] = {}
        self._MAX_COMPRESSION_CACHE_SIZE = 200
        
        # 上下文优先级配置（使用常量）
        self.priority_weights = {
            "world": CONTEXT_PRIORITY.WORLD,
            "character": CONTEXT_PRIORITY.CHARACTER,
            "plot": CONTEXT_PRIORITY.PLOT,
            "chapter": CONTEXT_PRIORITY.CHAPTER,
            "sync": CONTEXT_PRIORITY.SYNC,
            "general": CONTEXT_PRIORITY.GENERAL
        }
        
        if project_dir:
            self._load_contexts()
        
        logger.info(f"ContextManager initialized (max_tokens: {max_context_tokens})")
    
    def set_llm_summarizer(self, summarizer: LLMSummarizer) -> None:
        """设置LLM摘要生成器"""
        self.llm_summarizer = summarizer
        logger.info("LLM summarizer set")
    
    def save(self, key: str, value: Any, category: str = "general") -> None:
        """
        保存上下文
        
        Args:
            key: 键名
            value: 值
            category: 类别
        """
        if key in self.contexts:
            # 更新现有项
            item = self.contexts[key]
            item.value = value
            item.updated_at = datetime.now().isoformat()
            item.version += 1
        else:
            # 创建新项
            item = ContextItem(
                key=key,
                value=value,
                category=category
            )
        
        self.contexts[key] = item
        self.history.append({
            "action": "save",
            "key": key,
            "timestamp": datetime.now().isoformat()
        })
        
        if self.project_dir:
            self._persist_contexts()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取上下文
        
        Args:
            key: 键名
            default: 默认值
            
        Returns:
            上下文值
        """
        item = self.contexts.get(key)
        return item.value if item else default
    
    def get_by_category(self, category: str) -> Dict[str, Any]:
        """
        按类别获取所有上下文
        
        Args:
            category: 类别名
            
        Returns:
            该类别的所有上下文
        """
        return {
            key: item.value
            for key, item in self.contexts.items()
            if item.category == category
        }
    
    def get_relevant_context(
        self, 
        agent_type: str, 
        current_task: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据Agent类型和当前任务获取相关上下文
        (Context Isolation的实现)
        
        Args:
            agent_type: Agent类型
            current_task: 当前任务描述
            
        Returns:
            相关上下文字典
        """
        relevant = {}
        
        # 不同Agent需要不同的上下文
        agent_context_map = {
            "Worldbuilder": ["world"],
            "Outliner": ["world", "character", "plot"],
            "ChapterWriter": ["world", "character", "plot", "chapter"],
            "Polisher": ["chapter", "character"],
            "Evaluator": ["world", "character", "plot", "chapter"]
        }
        
        categories = agent_context_map.get(agent_type, ["general"])
        
        for category in categories:
            category_contexts = self.get_by_category(category)
            relevant.update(category_contexts)
        
        return relevant
    
    def compress_context(
        self,
        content: str,
        method: str = "reversible",
        max_length: int = WRITING_CONFIG.CONTEXT_COMPRESS_MAX_LENGTH
    ) -> str:
        """
        压缩上下文（同步版本）
        (Context Reduction的实现)
        
        Args:
            content: 原始内容
            method: 压缩方法 - "reversible"(可逆), "summary"(摘要), "extract"(提取关键信息)
            max_length: 最大长度
            
        Returns:
            压缩后的内容
        """
        if len(content) <= max_length:
            return content
        
        # 检查缓存
        cache_key = self._get_cache_key(content, method, max_length)
        if cache_key in self._compression_cache:
            val = self._compression_cache.pop(cache_key)
            self._compression_cache[cache_key] = val
            return val
        
        if method == "reversible":
            result = self._compress_reversible(content, max_length)
        elif method == "extract":
            result = self._compress_extract(content, max_length)
        else:
            result = self._compress_simple(content, max_length)
        
        # 缓存结果
        self._set_compression_cache(cache_key, result)
        return result
    
    async def compress_context_smart(
        self,
        content: str,
        max_length: int = WRITING_CONFIG.CONTEXT_COMPRESS_MAX_LENGTH,
        preserve_keys: Optional[List[str]] = None
    ) -> CompressionResult:
        """
        智能压缩上下文（使用LLM生成摘要）
        
        Args:
            content: 原始内容
            max_length: 最大长度
            preserve_keys: 需要保留的关键信息类型
            
        Returns:
            压缩结果
        """
        original_length = len(content)
        
        if original_length <= max_length:
            return CompressionResult(
                original_text=content,
                compressed_text=content,
                original_length=original_length,
                compressed_length=original_length,
                compression_ratio=1.0,
                method="none"
            )
        
        # 检查缓存
        cache_key = self._get_cache_key(content, "smart", max_length)
        if cache_key in self._compression_cache:
            cached = self._compression_cache.pop(cache_key)
            self._compression_cache[cache_key] = cached
            return CompressionResult(
                original_text=content,
                compressed_text=cached,
                original_length=original_length,
                compressed_length=len(cached),
                compression_ratio=len(cached) / original_length,
                method="smart_cached"
            )
        
        # 如果有LLM摘要器，使用智能摘要
        if self.llm_summarizer:
            try:
                compressed = await self._llm_compress(content, max_length, preserve_keys)
                self._set_compression_cache(cache_key, compressed)
                
                return CompressionResult(
                    original_text=content,
                    compressed_text=compressed,
                    original_length=original_length,
                    compressed_length=len(compressed),
                    compression_ratio=len(compressed) / original_length,
                    method="llm_summary"
                )
            except Exception as e:
                logger.warning(f"LLM compression failed, falling back: {e}")
        
        # 降级到提取关键信息
        compressed = self._compress_extract(content, max_length)
        self._set_compression_cache(cache_key, compressed)
        
        return CompressionResult(
            original_text=content,
            compressed_text=compressed,
            original_length=original_length,
            compressed_length=len(compressed),
            compression_ratio=len(compressed) / original_length,
            method="extract_fallback"
        )
    
    async def _llm_compress(
        self,
        content: str,
        max_length: int,
        preserve_keys: Optional[List[str]] = None
    ) -> str:
        """使用LLM压缩内容"""
        preserve_info = ""
        if preserve_keys:
            preserve_info = f"\n必须保留的信息类型：{', '.join(preserve_keys)}"
        
        prompt = f"""请将以下内容压缩为不超过{max_length}字的摘要，保留所有关键信息：
{preserve_info}

内容：
{content}

要求：
1. 保留人物名称、地点、关键事件
2. 保留伏笔和重要细节
3. 保留数字、日期等具体信息
4. 用简洁的语言概括
5. 输出不要超过{max_length}字"""

        result = await self.llm_summarizer(prompt, max_length)
        return result[:max_length]  # 确保不超长
    
    def _compress_reversible(self, content: str, max_length: int) -> str:
        """可逆压缩：保留首尾"""
        head_len = max_length * 2 // 5
        tail_len = max_length * 2 // 5
        omitted = len(content) - head_len - tail_len
        
        head = content[:head_len]
        tail = content[-tail_len:]
        
        return f"{head}\n\n[...省略 {omitted} 字符...]\n\n{tail}"
    
    def _compress_extract(self, content: str, max_length: int) -> str:
        """提取关键信息"""
        # 按段落分割
        paragraphs = content.split('\n\n')
        if not paragraphs:
            paragraphs = content.split('\n')
        
        # 关键信息模式
        key_patterns = [
            '主角', '配角', '反派', '世界', '设定',
            '第一', '第二', '第三', '开始', '结束',
            '重要', '关键', '核心', '主要', '目标',
            '能力', '技能', '装备', '地点', '时间'
        ]
        
        # 评分并排序段落
        scored_paragraphs = []
        for p in paragraphs:
            if not p.strip():
                continue
            score = sum(1 for pattern in key_patterns if pattern in p)
            # 首尾段落加分
            if p == paragraphs[0]:
                score += 2
            if p == paragraphs[-1]:
                score += 1
            scored_paragraphs.append((score, p))
        
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
        
        # 选取高分段落直到达到长度限制
        result_parts = []
        current_length = 0
        for score, p in scored_paragraphs:
            if current_length + len(p) + 2 > max_length:
                break
            result_parts.append(p)
            current_length += len(p) + 2
        
        if not result_parts:
            return content[:max_length]
        
        return '\n\n'.join(result_parts)
    
    def _compress_simple(self, content: str, max_length: int) -> str:
        """简单截取"""
        return content[:max_length - 3] + "..."
    
    def _get_cache_key(self, content: str, method: str, max_length: int) -> str:
        """生成缓存键"""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"{method}_{max_length}_{content_hash}"
    
    def sync_context(
        self, 
        source_agent: str, 
        target_agent: str, 
        updates: Dict[str, Any]
    ) -> None:
        """
        跨Agent同步上下文
        (Context Synchronization的实现)
        
        Args:
            source_agent: 源Agent
            target_agent: 目标Agent
            updates: 需要同步的更新内容
        """
        for key, value in updates.items():
            sync_key = f"{target_agent}_{key}"
            self.save(sync_key, value, category="sync")
        
        self.history.append({
            "action": "sync",
            "from": source_agent,
            "to": target_agent,
            "keys": list(updates.keys()),
            "timestamp": datetime.now().isoformat()
        })
    
    def get_chapter_context(self, chapter_number: int) -> Dict[str, Any]:
        """
        获取指定章节的上下文
        
        Args:
            chapter_number: 章节号
            
        Returns:
            章节相关上下文
        """
        context = {
            "world": self.get("world", {}),
            "characters": self.get("characters", []),
        }
        
        # 获取前一章的摘要
        if chapter_number > 1:
            prev_summary = self.get(f"chapter_{chapter_number - 1}_summary", "")
            context["previous_summary"] = prev_summary
        
        # 获取当前章节大纲
        chapter_outline = self.get(f"chapter_{chapter_number}_outline", "")
        context["chapter_outline"] = chapter_outline
        
        return context
    
    def save_chapter_result(
        self, 
        chapter_number: int, 
        content: str, 
        summary: str
    ) -> None:
        """
        保存章节结果
        
        Args:
            chapter_number: 章节号
            content: 章节内容
            summary: 章节摘要
        """
        self.save(f"chapter_{chapter_number}_content", content, "chapter")
        self.save(f"chapter_{chapter_number}_summary", summary, "chapter")
    
    def _load_contexts(self) -> None:
        """从文件加载上下文"""
        context_file = self.project_dir / "context.json"
        if context_file.exists():
            try:
                data = json.loads(context_file.read_text(encoding="utf-8"))
                for key, item_data in data.get("contexts", {}).items():
                    # 兼容旧版本配置，添加新字段的默认值
                    if 'compressed' not in item_data:
                        item_data['compressed'] = False
                    if 'original_length' not in item_data:
                        item_data['original_length'] = 0
                    self.contexts[key] = ContextItem(**item_data)
                self.history = data.get("history", [])
                logger.info(f"Loaded {len(self.contexts)} context items")
            except Exception as e:
                logger.warning(f"Failed to load contexts: {e}")
    
    def _persist_contexts(self) -> None:
        """持久化上下文到文件"""
        if not self.project_dir:
            return
        
        self.project_dir.mkdir(parents=True, exist_ok=True)
        context_file = self.project_dir / "context.json"
        
        data = {
            "contexts": {
                key: asdict(item)
                for key, item in self.contexts.items()
            },
            "history": self.history[-MESSAGE_BUS_CONFIG.HISTORY_LIMIT:]  # 只保留最近N条历史
        }
        
        atomic_write_json(context_file, data)

    def _set_compression_cache(self, key: str, value: str) -> None:
        if len(self._compression_cache) >= self._MAX_COMPRESSION_CACHE_SIZE:
            oldest = next(iter(self._compression_cache), None)
            if oldest is not None:
                del self._compression_cache[oldest]
        self._compression_cache[key] = value

    def export_all(self) -> Dict[str, Any]:
        """导出所有上下文"""
        return {
            key: item.value
            for key, item in self.contexts.items()
        }
    
    def clear(self) -> None:
        """清空所有上下文"""
        self.contexts.clear()
        self._compression_cache.clear()
        self.history.append({
            "action": "clear",
            "timestamp": datetime.now().isoformat()
        })
        
        # 持久化清空操作
        if self.project_dir:
            self._persist_contexts()
    
    # ==================== 高级功能 ====================
    
    async def get_optimized_context(
        self,
        agent_type: str,
        max_tokens: Optional[int] = None,
        current_task: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取优化后的上下文（自动压缩以适应token限制）
        
        Args:
            agent_type: Agent类型
            max_tokens: 最大token数（默认使用配置值）
            current_task: 当前任务描述
            
        Returns:
            优化后的上下文
        """
        # 注意：max_tokens可能为0，这是有效值，不能用or判断
        max_tokens = max_tokens if max_tokens is not None else self.max_context_tokens
        
        # 获取相关上下文
        relevant = self.get_relevant_context(agent_type, current_task)
        
        # 估算当前大小（简单按字符数估算）
        total_size = sum(
            len(str(v)) for v in relevant.values()
        )
        
        # 如果超出限制，需要压缩
        # 假设1个token约等于2个中文字符
        max_chars = max_tokens * 2
        
        if total_size <= max_chars:
            return relevant
        
        # 按优先级压缩
        optimized = {}
        remaining_chars = max_chars
        
        # 按优先级排序
        sorted_items = sorted(
            relevant.items(),
            key=lambda x: self._get_priority(x[0]),
            reverse=True
        )
        
        for key, value in sorted_items:
            value_str = str(value) if not isinstance(value, str) else value
            value_len = len(value_str)
            
            if value_len <= remaining_chars:
                optimized[key] = value
                remaining_chars -= value_len
            else:
                # 需要压缩
                if remaining_chars > WRITING_CONFIG.HISTORY_TRUNCATE_LENGTH:  # 至少保留摘要
                    if self.llm_summarizer:
                        result = await self.compress_context_smart(
                            value_str,
                            max_length=remaining_chars
                        )
                        optimized[key] = result.compressed_text
                    else:
                        optimized[key] = self.compress_context(
                            value_str,
                            method="extract",
                            max_length=remaining_chars
                        )
                    remaining_chars = 0
                break
        
        return optimized
    
    def _get_priority(self, key: str) -> float:
        """获取上下文键的优先级"""
        item = self.contexts.get(key)
        if item:
            return self.priority_weights.get(item.category, CONTEXT_PRIORITY.GENERAL)
        
        # 根据键名推断类别
        for category, weight in self.priority_weights.items():
            if category in key.lower():
                return weight
        return CONTEXT_PRIORITY.GENERAL
    
    def get_stats(self) -> Dict[str, Any]:
        """获取上下文统计信息"""
        total_size = sum(item.get_size() for item in self.contexts.values())
        by_category: Dict[str, int] = {}
        
        for item in self.contexts.values():
            by_category[item.category] = by_category.get(item.category, 0) + 1
        
        return {
            "total_items": len(self.contexts),
            "total_size_chars": total_size,
            "by_category": by_category,
            "compression_cache_size": len(self._compression_cache),
            "history_length": len(self.history)
        }


# 模块职责说明：实现Agentic Context Engineering，管理上下文的存储、压缩、同步和检索。
