# -*- coding: utf-8 -*-
"""
无限续写会话持久化存储

解决以下问题：
1. 服务重启后会话数据丢失
2. 换模型后上下文不连贯
3. 章节间剧情不连续
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ChapterData:
    """章节数据"""
    chapter_number: int
    title: str
    content: str
    word_count: int
    summary: str = ""
    created_at: str = ""
    model_used: str = ""  # 记录使用的模型
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.summary and self.content:
            self.summary = self.content[:200] + "..." if len(self.content) > 200 else self.content


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    project_id: str = ""
    story_beginning: str = ""
    current_chapter: int = 0
    is_running: bool = False
    
    # 章节数据
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    
    # 用户输入
    inspirations: List[Dict[str, Any]] = field(default_factory=list)
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    
    # 角色和剧情追踪
    dead_characters: List[str] = field(default_factory=list)
    character_states: Dict[str, Dict] = field(default_factory=dict)
    plot_points: List[Dict[str, Any]] = field(default_factory=list)
    
    # 配置
    words_per_chapter: int = 2500
    trends_enabled: bool = False
    trends_platforms: List[str] = field(default_factory=list)
    
    # 元数据
    created_at: str = ""
    updated_at: str = ""
    last_model: str = ""  # 最后使用的模型
    model_history: List[str] = field(default_factory=list)  # 模型切换历史
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """从字典创建"""
        return cls(**data)
    
    def get_context_summary(self, max_chapters: int = 5) -> str:
        """
        获取上下文摘要，用于提示词构建
        
        确保即使换了模型也能保持连贯性
        """
        parts = []
        
        # 故事开头
        if self.story_beginning:
            parts.append(f"[故事起源]\n{self.story_beginning[:500]}...")
        
        # 已死亡角色（关键信息）
        if self.dead_characters:
            parts.append(f"[已死亡角色（绝对禁止复活）]\n" + ", ".join(self.dead_characters))
        
        # 重要剧情点
        if self.plot_points:
            important_plots = [p for p in self.plot_points if p.get("importance") == "high"]
            if important_plots:
                parts.append("[重要剧情节点]")
                for p in important_plots[-10:]:  # 最近10个重要节点
                    parts.append(f"- 第{p.get('chapter', '?')}章: {p.get('description', '')}")
        
        # 最近章节摘要
        if self.chapters:
            parts.append("[最近章节回顾]")
            recent = self.chapters[-max_chapters:]
            for ch in recent:
                ch_num = ch.get("chapter_number", "?")
                title = ch.get("title", "")
                summary = ch.get("summary", "")[:150]
                parts.append(f"第{ch_num}章 {title}: {summary}...")
        
        return "\n\n".join(parts)
    
    def get_last_chapter_content(self) -> str:
        """获取最后一章的完整内容，用于续写"""
        if self.chapters:
            return self.chapters[-1].get("content", "")
        return ""
    
    def add_chapter(self, chapter_data: Dict[str, Any], model: str = ""):
        """添加新章节"""
        if model:
            chapter_data["model_used"] = model
            if model != self.last_model:
                self.model_history.append(model)
            self.last_model = model
        
        self.chapters.append(chapter_data)
        self.current_chapter = len(self.chapters)
        self.updated_at = datetime.now().isoformat()


class SessionStore:
    """
    会话持久化存储
    
    将会话数据保存到JSON文件，确保：
    1. 服务重启后可恢复会话
    2. 换模型后保持上下文连贯
    3. 章节间剧情一致
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        初始化会话存储
        
        Args:
            storage_dir: 存储目录，默认为 data/sessions/
        """
        if storage_dir is None:
            storage_dir = Path(__file__).parent.parent / "data" / "sessions"
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._cache: Dict[str, SessionState] = {}
        
        logger.info(f"[SessionStore] 初始化完成，存储目录: {self.storage_dir}")
    
    def _get_session_path(self, session_id: str, project_id: str = "") -> Path:
        """获取会话文件路径"""
        # 使用项目ID作为子目录（如果有）
        if project_id:
            session_dir = self.storage_dir / project_id
        else:
            session_dir = self.storage_dir / "default"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / f"{session_id}.json"
    
    def save(self, state: SessionState) -> bool:
        """
        保存会话状态
        
        Args:
            state: 会话状态对象
        
        Returns:
            是否保存成功
        """
        try:
            state.updated_at = datetime.now().isoformat()
            
            # 更新缓存
            self._cache[state.session_id] = state
            
            # 写入文件
            path = self._get_session_path(state.session_id, state.project_id)
            data = state.to_dict()
            
            # 使用临时文件确保原子写入
            temp_path = path.with_suffix('.tmp')
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            temp_path.rename(path)
            
            logger.info(f"[SessionStore] 保存会话 {state.session_id}，共 {len(state.chapters)} 章")
            return True
            
        except Exception as e:
            logger.error(f"[SessionStore] 保存会话失败: {e}")
            return False
    
    def load(self, session_id: str, project_id: str = "") -> Optional[SessionState]:
        """
        加载会话状态
        
        Args:
            session_id: 会话ID
            project_id: 项目ID（可选）
        
        Returns:
            会话状态对象，不存在则返回None
        """
        # 先检查缓存
        if session_id in self._cache:
            logger.debug(f"[SessionStore] 从缓存加载会话 {session_id}")
            return self._cache[session_id]
        
        # 从文件加载
        path = self._get_session_path(session_id, project_id)
        
        if not path.exists():
            logger.debug(f"[SessionStore] 会话文件不存在: {path}")
            return None
        
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            state = SessionState.from_dict(data)
            
            # 更新缓存
            self._cache[session_id] = state
            
            logger.info(f"[SessionStore] 加载会话 {session_id}，共 {len(state.chapters)} 章")
            return state
            
        except Exception as e:
            logger.error(f"[SessionStore] 加载会话失败: {e}")
            return None
    
    def exists(self, session_id: str, project_id: str = "") -> bool:
        """检查会话是否存在"""
        if session_id in self._cache:
            return True
        path = self._get_session_path(session_id, project_id)
        return path.exists()
    
    def delete(self, session_id: str, project_id: str = "") -> bool:
        """删除会话"""
        try:
            # 从缓存删除
            if session_id in self._cache:
                del self._cache[session_id]
            
            # 删除文件
            path = self._get_session_path(session_id, project_id)
            if path.exists():
                path.unlink()
            
            logger.info(f"[SessionStore] 删除会话 {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"[SessionStore] 删除会话失败: {e}")
            return False
    
    def list_sessions(self, project_id: str = "") -> List[Dict[str, Any]]:
        """列出所有会话"""
        sessions = []
        
        if project_id:
            search_dirs = [self.storage_dir / project_id]
        else:
            search_dirs = list(self.storage_dir.iterdir()) if self.storage_dir.exists() else []
        
        for dir_path in search_dirs:
            if not dir_path.is_dir():
                continue
            
            for file_path in dir_path.glob("*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding='utf-8'))
                    sessions.append({
                        "session_id": data.get("session_id", file_path.stem),
                        "project_id": data.get("project_id", ""),
                        "current_chapter": data.get("current_chapter", 0),
                        "chapter_count": len(data.get("chapters", [])),
                        "is_running": data.get("is_running", False),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "last_model": data.get("last_model", ""),
                        "story_preview": data.get("story_beginning", "")[:100] + "..."
                    })
                except Exception as e:
                    logger.warning(f"[SessionStore] 读取会话信息失败 {file_path}: {e}")
        
        # 按更新时间排序
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return sessions
    
    def create_or_restore(
        self, 
        session_id: str,
        project_id: str = "",
        story_beginning: str = "",
        words_per_chapter: int = 2500
    ) -> SessionState:
        """
        创建或恢复会话
        
        如果会话已存在，返回已有会话（保持连贯性）
        如果不存在，创建新会话
        """
        # 尝试加载已有会话
        existing = self.load(session_id, project_id)
        if existing:
            logger.info(f"[SessionStore] 恢复已有会话 {session_id}，当前第 {existing.current_chapter} 章")
            return existing
        
        # 创建新会话
        state = SessionState(
            session_id=session_id,
            project_id=project_id,
            story_beginning=story_beginning,
            words_per_chapter=words_per_chapter
        )
        
        self.save(state)
        logger.info(f"[SessionStore] 创建新会话 {session_id}")
        return state
    
    def update_chapter(
        self,
        session_id: str,
        chapter_data: Dict[str, Any],
        model: str = "",
        project_id: str = ""
    ) -> bool:
        """
        更新或添加章节
        
        Args:
            session_id: 会话ID
            chapter_data: 章节数据
            model: 使用的模型名称
            project_id: 项目ID
        
        Returns:
            是否成功
        """
        state = self.load(session_id, project_id)
        if not state:
            logger.warning(f"[SessionStore] 会话不存在: {session_id}")
            return False
        
        state.add_chapter(chapter_data, model)
        return self.save(state)
    
    def get_context_for_continuation(
        self,
        session_id: str,
        project_id: str = "",
        include_full_last_chapter: bool = True
    ) -> Dict[str, Any]:
        """
        获取续写所需的上下文
        
        这是确保章节连贯性的核心方法
        
        Args:
            session_id: 会话ID
            project_id: 项目ID
            include_full_last_chapter: 是否包含最后一章的完整内容
        
        Returns:
            包含上下文信息的字典
        """
        state = self.load(session_id, project_id)
        if not state:
            return {}
        
        context = {
            "session_id": session_id,
            "current_chapter": state.current_chapter,
            "story_beginning": state.story_beginning,
            "context_summary": state.get_context_summary(),
            "dead_characters": state.dead_characters,
            "last_model": state.last_model,
            "model_history": state.model_history,
            "inspirations": [i for i in state.inspirations if i.get("chapter", 0) >= state.current_chapter],
            "corrections": [c for c in state.corrections if c.get("chapter", 0) >= state.current_chapter],
        }
        
        if include_full_last_chapter:
            context["last_chapter_content"] = state.get_last_chapter_content()
        
        # 最近章节数据（用于知识库检索）
        if state.chapters:
            context["recent_chapters"] = state.chapters[-3:]
        
        return context


# 全局实例
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取全局会话存储实例"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store