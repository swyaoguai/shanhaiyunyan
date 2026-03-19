"""
写作统计仪表板模块
提供写作进度、Token使用、质量评分等统计分析
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import threading

from ..constants import COST_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class WritingSession:
    """写作会话记录"""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    chapters_written: int = 0
    words_written: int = 0
    tokens_used: int = 0
    api_calls: int = 0
    errors: int = 0


@dataclass
class ChapterStats:
    """章节统计"""
    chapter_number: int
    title: str
    word_count: int
    writing_time: float  # 秒
    tokens_in: int = 0
    tokens_out: int = 0
    revision_count: int = 0
    quality_score: float = 0
    created_at: str = ""


@dataclass
class DailyStats:
    """每日统计"""
    date: str
    chapters_written: int = 0
    words_written: int = 0
    tokens_used: int = 0
    api_calls: int = 0
    writing_time: float = 0
    average_quality: float = 0


@dataclass
class ProjectStats:
    """项目统计"""
    project_id: str
    project_name: str
    total_chapters: int = 0
    completed_chapters: int = 0
    total_words: int = 0
    total_tokens: int = 0
    total_api_calls: int = 0
    total_writing_time: float = 0
    average_quality: float = 0
    start_date: str = ""
    last_update: str = ""


class WritingDashboard:
    """
    写作统计仪表板
    
    功能：
    - 实时写作进度跟踪
    - Token使用分析
    - 质量评分历史
    - 写作习惯分析
    - 多项目统计对比
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        from ..constants import PATH_DEFAULTS
        self.data_dir = data_dir or Path(PATH_DEFAULTS.STATS_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据存储
        self._sessions: Dict[str, WritingSession] = {}
        self._chapter_stats: Dict[str, List[ChapterStats]] = defaultdict(list)
        self._daily_stats: Dict[str, DailyStats] = {}
        self._project_stats: Dict[str, ProjectStats] = {}
        
        # 当前活动会话
        self._active_session: Optional[str] = None
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 加载历史数据
        self._load_data()
    
    def _load_data(self):
        """加载历史数据"""
        stats_file = self.data_dir / "dashboard_stats.json"
        if stats_file.exists():
            try:
                data = json.loads(stats_file.read_text(encoding="utf-8"))
                
                for sid, sdata in data.get("sessions", {}).items():
                    self._sessions[sid] = WritingSession(**sdata)
                
                for pid, chapters in data.get("chapters", {}).items():
                    self._chapter_stats[pid] = [ChapterStats(**ch) for ch in chapters]
                
                for date, ddata in data.get("daily", {}).items():
                    self._daily_stats[date] = DailyStats(**ddata)
                
                for pid, pdata in data.get("projects", {}).items():
                    self._project_stats[pid] = ProjectStats(**pdata)
                    
            except Exception as e:
                logger.warning(f"Failed to load dashboard data: {e}")
    
    def _save_data(self):
        """保存数据"""
        stats_file = self.data_dir / "dashboard_stats.json"
        
        data = {
            "sessions": {sid: asdict(s) for sid, s in self._sessions.items()},
            "chapters": {pid: [asdict(ch) for ch in chs] 
                        for pid, chs in self._chapter_stats.items()},
            "daily": {d: asdict(s) for d, s in self._daily_stats.items()},
            "projects": {pid: asdict(p) for pid, p in self._project_stats.items()}
        }
        
        stats_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def start_session(self, project_id: str) -> str:
        """开始写作会话"""
        with self._lock:
            session_id = f"{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            self._sessions[session_id] = WritingSession(
                session_id=session_id,
                start_time=datetime.now().isoformat()
            )
            
            self._active_session = session_id
            logger.info(f"Writing session started: {session_id}")
            
            return session_id
    
    def end_session(self, session_id: Optional[str] = None):
        """结束写作会话"""
        with self._lock:
            sid = session_id or self._active_session
            if sid and sid in self._sessions:
                self._sessions[sid].end_time = datetime.now().isoformat()
                self._save_data()
                logger.info(f"Writing session ended: {sid}")
            
            if sid == self._active_session:
                self._active_session = None
    
    def record_chapter(
        self,
        project_id: str,
        chapter_number: int,
        title: str,
        word_count: int,
        writing_time: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        quality_score: float = 0
    ):
        """记录章节完成"""
        with self._lock:
            # 章节统计
            chapter_stat = ChapterStats(
                chapter_number=chapter_number,
                title=title,
                word_count=word_count,
                writing_time=writing_time,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                quality_score=quality_score,
                created_at=datetime.now().isoformat()
            )
            self._chapter_stats[project_id].append(chapter_stat)
            
            # 更新会话统计
            if self._active_session and self._active_session in self._sessions:
                session = self._sessions[self._active_session]
                session.chapters_written += 1
                session.words_written += word_count
                session.tokens_used += tokens_in + tokens_out
                session.api_calls += 1
            
            # 更新每日统计
            today = datetime.now().strftime("%Y-%m-%d")
            if today not in self._daily_stats:
                self._daily_stats[today] = DailyStats(date=today)
            
            daily = self._daily_stats[today]
            daily.chapters_written += 1
            daily.words_written += word_count
            daily.tokens_used += tokens_in + tokens_out
            daily.api_calls += 1
            daily.writing_time += writing_time
            
            # 更新平均质量
            chapter_count = daily.chapters_written
            daily.average_quality = (
                (daily.average_quality * (chapter_count - 1) + quality_score) 
                / chapter_count
            )
            
            # 更新项目统计
            self._update_project_stats(
                project_id, word_count, tokens_in + tokens_out, 
                writing_time, quality_score
            )
            
            self._save_data()
    
    def _update_project_stats(
        self,
        project_id: str,
        words: int,
        tokens: int,
        time_spent: float,
        quality: float
    ):
        """更新项目统计"""
        if project_id not in self._project_stats:
            self._project_stats[project_id] = ProjectStats(
                project_id=project_id,
                project_name=project_id,
                start_date=datetime.now().isoformat()
            )
        
        stats = self._project_stats[project_id]
        stats.completed_chapters += 1
        stats.total_words += words
        stats.total_tokens += tokens
        stats.total_api_calls += 1
        stats.total_writing_time += time_spent
        stats.last_update = datetime.now().isoformat()
        
        # 更新平均质量
        stats.average_quality = (
            (stats.average_quality * (stats.completed_chapters - 1) + quality)
            / stats.completed_chapters
        )
    
    def record_error(self, error_type: str = "unknown"):
        """记录错误"""
        with self._lock:
            if self._active_session and self._active_session in self._sessions:
                self._sessions[self._active_session].errors += 1
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """获取仪表板摘要"""
        with self._lock:
            # 今日统计
            today = datetime.now().strftime("%Y-%m-%d")
            today_stats = self._daily_stats.get(today, DailyStats(date=today))
            
            # 本周统计
            week_stats = self._get_period_stats(days=7)
            
            # 本月统计
            month_stats = self._get_period_stats(days=30)
            
            # 活跃项目
            active_projects = [
                asdict(p) for p in self._project_stats.values()
                if p.completed_chapters > 0
            ]
            
            # 最近会话
            recent_sessions = sorted(
                self._sessions.values(),
                key=lambda s: s.start_time,
                reverse=True
            )[:5]
            
            return {
                "today": asdict(today_stats),
                "week": week_stats,
                "month": month_stats,
                "active_projects": active_projects,
                "recent_sessions": [asdict(s) for s in recent_sessions],
                "total_projects": len(self._project_stats),
                "total_chapters": sum(p.completed_chapters for p in self._project_stats.values()),
                "total_words": sum(p.total_words for p in self._project_stats.values()),
                "total_tokens": sum(p.total_tokens for p in self._project_stats.values())
            }
    
    def _get_period_stats(self, days: int) -> Dict[str, Any]:
        """获取指定时间段的统计"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        total_chapters = 0
        total_words = 0
        total_tokens = 0
        total_time = 0
        total_quality = 0
        days_with_data = 0
        
        for date_str, stats in self._daily_stats.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                if start_date <= date <= end_date:
                    total_chapters += stats.chapters_written
                    total_words += stats.words_written
                    total_tokens += stats.tokens_used
                    total_time += stats.writing_time
                    if stats.average_quality > 0:
                        total_quality += stats.average_quality
                        days_with_data += 1
            except ValueError:
                continue
        
        return {
            "chapters": total_chapters,
            "words": total_words,
            "tokens": total_tokens,
            "writing_time": total_time,
            "average_quality": total_quality / days_with_data if days_with_data > 0 else 0,
            "days": days
        }
    
    def get_project_details(self, project_id: str) -> Dict[str, Any]:
        """获取项目详细统计"""
        with self._lock:
            if project_id not in self._project_stats:
                return {"error": "Project not found"}
            
            stats = self._project_stats[project_id]
            chapters = self._chapter_stats.get(project_id, [])
            
            # 章节质量趋势
            quality_trend = [
                {"chapter": ch.chapter_number, "quality": ch.quality_score}
                for ch in sorted(chapters, key=lambda x: x.chapter_number)
            ]
            
            # 字数分布
            word_distribution = [
                {"chapter": ch.chapter_number, "words": ch.word_count}
                for ch in sorted(chapters, key=lambda x: x.chapter_number)
            ]
            
            # Token使用趋势
            token_trend = [
                {
                    "chapter": ch.chapter_number,
                    "tokens_in": ch.tokens_in,
                    "tokens_out": ch.tokens_out
                }
                for ch in sorted(chapters, key=lambda x: x.chapter_number)
            ]
            
            return {
                "stats": asdict(stats),
                "chapters": [asdict(ch) for ch in chapters],
                "quality_trend": quality_trend,
                "word_distribution": word_distribution,
                "token_trend": token_trend,
                "average_chapter_length": stats.total_words // max(stats.completed_chapters, 1),
                "average_writing_time": stats.total_writing_time / max(stats.completed_chapters, 1)
            }
    
    def _collect_weekday_stats(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, int]]:
        """收集按星期分组的写作统计"""
        weekday_stats = defaultdict(lambda: {"chapters": 0, "words": 0})
        
        for date_str, stats in self._daily_stats.items():
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                if start_date <= date <= end_date:
                    weekday = date.strftime("%A")
                    weekday_stats[weekday]["chapters"] += stats.chapters_written
                    weekday_stats[weekday]["words"] += stats.words_written
            except ValueError:
                continue
        
        return weekday_stats
    
    def _collect_hourly_stats(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[int, Dict[str, int]]:
        """收集按小时分组的会话统计"""
        hourly_stats = defaultdict(lambda: {"sessions": 0, "chapters": 0})
        
        for session in self._sessions.values():
            try:
                start = datetime.fromisoformat(session.start_time)
                if start_date <= start <= end_date:
                    hour = start.hour
                    hourly_stats[hour]["sessions"] += 1
                    hourly_stats[hour]["chapters"] += session.chapters_written
            except ValueError:
                continue
        
        return hourly_stats
    
    def _find_best_writing_time(
        self,
        weekday_stats: Dict[str, Dict[str, int]],
        hourly_stats: Dict[int, Dict[str, int]]
    ) -> tuple:
        """找出最佳写作时间（小时和星期几）"""
        best_hour = 0
        best_day = "N/A"
        
        if hourly_stats:
            best_hour = max(hourly_stats.items(), key=lambda x: x[1]["chapters"])[0]
        
        if weekday_stats:
            best_day = max(weekday_stats.items(), key=lambda x: x[1]["words"])[0]
        
        return best_hour, best_day
    
    def get_writing_habits(self, days: int = 30) -> Dict[str, Any]:
        """分析写作习惯"""
        with self._lock:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 收集统计数据
            weekday_stats = self._collect_weekday_stats(start_date, end_date)
            hourly_stats = self._collect_hourly_stats(start_date, end_date)
            
            # 找出最佳写作时间
            best_hour, best_day = self._find_best_writing_time(weekday_stats, hourly_stats)
            
            return {
                "weekday_stats": dict(weekday_stats),
                "hourly_stats": {str(k): v for k, v in sorted(hourly_stats.items())},
                "best_writing_hour": best_hour,
                "best_writing_day": best_day,
                "analysis_period_days": days
            }
    
    def get_token_analysis(self) -> Dict[str, Any]:
        """Token使用分析"""
        with self._lock:
            total_tokens_in = 0
            total_tokens_out = 0
            
            for chapters in self._chapter_stats.values():
                for ch in chapters:
                    total_tokens_in += ch.tokens_in
                    total_tokens_out += ch.tokens_out
            
            # 估算成本（基于配置的价格）
            estimated_cost = (
                total_tokens_in * COST_CONFIG.GPT4_INPUT_COST +
                total_tokens_out * COST_CONFIG.GPT4_OUTPUT_COST
            ) / 1000
            
            return {
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "total_tokens": total_tokens_in + total_tokens_out,
                "estimated_cost_usd": round(estimated_cost, 2),
                "average_tokens_per_chapter": (
                    (total_tokens_in + total_tokens_out) // 
                    max(sum(len(chs) for chs in self._chapter_stats.values()), 1)
                )
            }


# 全局仪表板实例
_dashboard: Optional[WritingDashboard] = None
_dashboard_lock = threading.Lock()


def get_dashboard() -> WritingDashboard:
    """获取全局仪表板实例"""
    global _dashboard
    with _dashboard_lock:
        if _dashboard is None:
            _dashboard = WritingDashboard()
        return _dashboard


# 模块职责说明：提供写作进度跟踪、Token使用分析、质量评分历史和写作习惯分析功能。