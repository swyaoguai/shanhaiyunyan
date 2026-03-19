"""
摘要索引检索模块（无向量RAG）

基于LLM语义理解的检索方案，使用摘要作为索引而非向量嵌入。
适用于小规模数据集（<200条），提供更精准的语义匹配。

核心原理：
1. 文档添加时：使用LLM为每个条目生成简短摘要
2. 检索时：将所有摘要组织成索引提示词，让LLM选择最相关的条目ID
3. 返回结果：读取被选中条目的原始内容

优点：
- 语义理解更准确，避免向量相似度的局限性
- 无需配置向量化服务
- 适合角色、世界观等结构化小数据

缺点：
- 每次检索消耗LLM Token（约等于摘要总字数）
- 不适合大规模数据（>200条）
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SummaryEntry:
    """摘要条目"""
    entry_id: str  # 唯一标识
    category: str  # 分类：character, world, item, etc.
    name: str  # 条目名称
    summary: str  # LLM生成的摘要
    original_content: str  # 原始完整内容
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id,
            "category": self.category,
            "name": self.name,
            "summary": self.summary,
            "original_content": self.original_content,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SummaryEntry":
        return cls(**data)


class SummaryIndex:
    """
    摘要索引类 - 无向量RAG核心实现
    
    使用方式：
    ```python
    index = SummaryIndex(project_id="my_project", llm_caller=my_llm_function)
    
    # 添加条目（自动生成摘要）
    await index.add_entry(
        entry_id="char_001",
        category="character",
        name="李逍遥",
        content="李逍遥是仙剑奇侠传的主角，性格豪爽..."
    )
    
    # 检索相关条目
    results = await index.retrieve("谁是主角的青梅竹马", top_k=3)
    ```
    """
    
    def __init__(
        self, 
        project_id: str,
        llm_caller: callable = None,
        db_path: str = None,
        max_summary_length: int = 50,
        cache_enabled: bool = True
    ):
        """
        初始化摘要索引
        
        Args:
            project_id: 项目ID
            llm_caller: LLM调用函数，签名: async def llm_caller(prompt: str) -> str
            db_path: SQLite数据库路径，默认使用项目数据目录
            max_summary_length: 每条摘要最大字数
            cache_enabled: 是否缓存摘要（避免重复生成）
        """
        self.project_id = project_id
        self.llm_caller = llm_caller
        self.max_summary_length = max_summary_length
        self.cache_enabled = cache_enabled
        
        # 设置数据库路径
        if db_path:
            self.db_path = Path(db_path)
        else:
            from ...constants import get_data_dir
            self.db_path = get_data_dir() / "summary_index" / project_id / "index.db"
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._cache: Dict[str, SummaryEntry] = {}
        
        # 初始化数据库
        self._init_db()
        
        # 加载缓存
        if cache_enabled:
            self._load_cache()
    
    def _init_db(self):
        """初始化SQLite数据库"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summary_entries (
                entry_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                summary TEXT NOT NULL,
                original_content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category ON summary_entries(category)
        """)
        
        conn.commit()
        conn.close()
    
    def _load_cache(self):
        """从数据库加载所有条目到内存缓存"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM summary_entries")
        rows = cursor.fetchall()
        
        for row in rows:
            entry = SummaryEntry(
                entry_id=row[0],
                category=row[1],
                name=row[2],
                summary=row[3],
                original_content=row[4],
                created_at=row[5],
                updated_at=row[6]
            )
            self._cache[entry.entry_id] = entry
        
        conn.close()
        logger.info(f"[SummaryIndex] 加载了 {len(self._cache)} 条摘要索引")
    
    async def _generate_summary(self, name: str, content: str, category: str) -> str:
        """使用LLM生成摘要"""
        if not self.llm_caller:
            # 如果没有配置LLM，使用简单截断
            return content[:self.max_summary_length] + ("..." if len(content) > self.max_summary_length else "")
        
        prompt = f"""请为以下{category}内容生成一个简短摘要，不超过{self.max_summary_length}字。
摘要应包含最关键的特征和信息，便于后续检索匹配。

【名称】{name}

【内容】
{content[:1000]}

【要求】
- 摘要长度不超过{self.max_summary_length}字
- 包含关键特征、身份、关系等信息
- 使用简洁的描述性语言
- 不要使用"该角色"等指代词，直接使用名称

请直接输出摘要内容，不要有其他说明："""
        
        try:
            summary = await self.llm_caller(prompt)
            # 清理摘要
            summary = summary.strip()
            if len(summary) > self.max_summary_length:
                summary = summary[:self.max_summary_length]
            return summary
        except Exception as e:
            logger.error(f"[SummaryIndex] 生成摘要失败: {e}")
            return content[:self.max_summary_length]
    
    async def add_entry(
        self,
        entry_id: str,
        category: str,
        name: str,
        content: str,
        summary: str = None
    ) -> SummaryEntry:
        """
        添加条目到索引
        
        Args:
            entry_id: 唯一标识
            category: 分类
            name: 名称
            content: 原始内容
            summary: 可选的预设摘要，如果不提供则自动生成
            
        Returns:
            创建的SummaryEntry对象
        """
        # 如果没有提供摘要，自动生成
        if not summary:
            summary = await self._generate_summary(name, content, category)
        
        now = datetime.now().isoformat()
        entry = SummaryEntry(
            entry_id=entry_id,
            category=category,
            name=name,
            summary=summary,
            original_content=content,
            created_at=now,
            updated_at=now
        )
        
        # 保存到数据库
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO summary_entries 
            (entry_id, category, name, summary, original_content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entry.entry_id, entry.category, entry.name, entry.summary, 
              entry.original_content, entry.created_at, entry.updated_at))
        
        conn.commit()
        conn.close()
        
        # 更新缓存
        if self.cache_enabled:
            self._cache[entry_id] = entry
        
        logger.info(f"[SummaryIndex] 添加条目: {name} ({category})")
        return entry
    
    async def update_entry(
        self,
        entry_id: str,
        name: str = None,
        content: str = None,
        regenerate_summary: bool = True
    ) -> Optional[SummaryEntry]:
        """更新条目"""
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        if name:
            entry.name = name
        if content:
            entry.original_content = content
            if regenerate_summary:
                entry.summary = await self._generate_summary(
                    entry.name, content, entry.category
                )
        
        entry.updated_at = datetime.now().isoformat()
        
        # 更新数据库
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE summary_entries 
            SET name=?, summary=?, original_content=?, updated_at=?
            WHERE entry_id=?
        """, (entry.name, entry.summary, entry.original_content, 
              entry.updated_at, entry_id))
        
        conn.commit()
        conn.close()
        
        # 更新缓存
        if self.cache_enabled:
            self._cache[entry_id] = entry
        
        return entry
    
    def delete_entry(self, entry_id: str) -> bool:
        """删除条目"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM summary_entries WHERE entry_id=?", (entry_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        # 更新缓存
        if self.cache_enabled and entry_id in self._cache:
            del self._cache[entry_id]
        
        return deleted
    
    def get_entry(self, entry_id: str) -> Optional[SummaryEntry]:
        """获取单个条目"""
        if self.cache_enabled and entry_id in self._cache:
            return self._cache[entry_id]
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM summary_entries WHERE entry_id=?", (entry_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return SummaryEntry(
                entry_id=row[0],
                category=row[1],
                name=row[2],
                summary=row[3],
                original_content=row[4],
                created_at=row[5],
                updated_at=row[6]
            )
        return None
    
    def get_entries_by_category(self, category: str) -> List[SummaryEntry]:
        """获取某分类下的所有条目"""
        if self.cache_enabled:
            return [e for e in self._cache.values() if e.category == category]
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM summary_entries WHERE category=?", (category,))
        rows = cursor.fetchall()
        conn.close()
        
        return [SummaryEntry(
            entry_id=row[0],
            category=row[1],
            name=row[2],
            summary=row[3],
            original_content=row[4],
            created_at=row[5],
            updated_at=row[6]
        ) for row in rows]
    
    def get_all_entries(self) -> List[SummaryEntry]:
        """获取所有条目"""
        if self.cache_enabled:
            return list(self._cache.values())
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM summary_entries")
        rows = cursor.fetchall()
        conn.close()
        
        return [SummaryEntry(
            entry_id=row[0],
            category=row[1],
            name=row[2],
            summary=row[3],
            original_content=row[4],
            created_at=row[5],
            updated_at=row[6]
        ) for row in rows]
    
    def build_index_prompt(self, categories: List[str] = None) -> str:
        """
        构建摘要索引提示词
        
        将所有摘要组织成结构化格式，供LLM在检索时参考。
        
        Args:
            categories: 可选的分类过滤列表
            
        Returns:
            格式化的索引提示词
        """
        entries = self.get_all_entries()
        
        if categories:
            entries = [e for e in entries if e.category in categories]
        
        if not entries:
            return ""
        
        # 按分类组织
        by_category: Dict[str, List[SummaryEntry]] = {}
        for entry in entries:
            if entry.category not in by_category:
                by_category[entry.category] = []
            by_category[entry.category].append(entry)
        
        # 构建索引文本
        lines = ["【资料索引】"]
        
        category_names = {
            "character": "角色",
            "world": "世界观设定",
            "item": "物品道具",
            "location": "地点场景",
            "event": "事件",
            "other": "其他"
        }
        
        for category, cat_entries in by_category.items():
            cat_name = category_names.get(category, category)
            lines.append(f"\n## {cat_name}")
            for entry in cat_entries:
                lines.append(f"- [{entry.entry_id}] {entry.name}: {entry.summary}")
        
        return "\n".join(lines)
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        categories: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检索最相关的条目
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            categories: 可选的分类过滤
            
        Returns:
            检索结果列表，每个结果包含 entry_id, name, content, score
        """
        entries = self.get_all_entries()
        
        if categories:
            entries = [e for e in entries if e.category in categories]
        
        if not entries:
            return []
        
        if not self.llm_caller:
            # 没有LLM时使用简单关键词匹配
            return self._simple_keyword_match(query, entries, top_k)
        
        # 构建检索提示词
        index_text = self.build_index_prompt(categories)
        
        prompt = f"""你是一个精确的信息检索助手。根据用户查询，从以下资料索引中选择最相关的条目。

{index_text}

【用户查询】
{query}

【任务】
从上述索引中选择最相关的条目（最多{top_k}个），按相关度从高到低排序。
只返回条目ID列表，用逗号分隔，不要有其他说明。

例如：char_001,world_003,item_002

请输出选中的条目ID："""
        
        try:
            response = await self.llm_caller(prompt)
            
            # 解析返回的ID列表
            selected_ids = [id.strip() for id in response.strip().split(",") if id.strip()]
            selected_ids = selected_ids[:top_k]
            
            # 获取完整内容
            results = []
            for i, entry_id in enumerate(selected_ids):
                entry = self.get_entry(entry_id)
                if entry:
                    results.append({
                        "entry_id": entry.entry_id,
                        "category": entry.category,
                        "name": entry.name,
                        "content": entry.original_content,
                        "summary": entry.summary,
                        "score": 1.0 - (i * 0.1)  # 简单的排名分数
                    })
            
            logger.info(f"[SummaryIndex] 检索到 {len(results)} 个相关条目")
            return results
            
        except Exception as e:
            logger.error(f"[SummaryIndex] 检索失败: {e}")
            # 降级到关键词匹配
            return self._simple_keyword_match(query, entries, top_k)
    
    def _simple_keyword_match(
        self, 
        query: str, 
        entries: List[SummaryEntry], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """简单的关键词匹配（降级方案）"""
        query_terms = set(query.lower())
        
        scored_entries = []
        for entry in entries:
            # 计算匹配分数
            text = (entry.name + entry.summary + entry.original_content).lower()
            score = sum(1 for term in query_terms if term in text) / len(query_terms) if query_terms else 0
            scored_entries.append((entry, score))
        
        # 排序并返回
        scored_entries.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {
                "entry_id": entry.entry_id,
                "category": entry.category,
                "name": entry.name,
                "content": entry.original_content,
                "summary": entry.summary,
                "score": score
            }
            for entry, score in scored_entries[:top_k]
            if score > 0
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        entries = self.get_all_entries()
        
        by_category: Dict[str, int] = {}
        total_summary_chars = 0
        
        for entry in entries:
            by_category[entry.category] = by_category.get(entry.category, 0) + 1
            total_summary_chars += len(entry.summary)
        
        return {
            "total_entries": len(entries),
            "by_category": by_category,
            "total_summary_chars": total_summary_chars,
            "estimated_tokens_per_query": total_summary_chars // 2  # 粗略估计
        }
    
    def clear(self):
        """清空所有数据"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM summary_entries")
        conn.commit()
        conn.close()
        
        self._cache.clear()
        logger.info("[SummaryIndex] 已清空所有数据")