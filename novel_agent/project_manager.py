"""
项目管理器
管理多个小说项目，实现数据隔离
"""

import json
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Project:
    """小说项目"""
    id: str
    name: str
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    word_count: int = 0
    chapter_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


class ProjectManager:
    """
    项目管理器
    管理多个小说项目的创建、列表、删除和切换
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        from .constants import get_data_dir
        self.data_dir = data_dir or get_data_dir()
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir = self.data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.data_dir / "projects.json"
        self.projects: Dict[str, Project] = {}
        self.current_project_id: Optional[str] = None
        self._load_projects()
    
    def _load_projects(self) -> None:
        """从文件加载项目列表"""
        if self.meta_file.exists():
            try:
                data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                for proj_id, proj_data in data.get("projects", {}).items():
                    self.projects[proj_id] = Project(**proj_data)
                self.current_project_id = data.get("current_project_id")
            except Exception as e:
                logger.warning(f"Failed to load projects: {e}")
        
        # 如果没有项目，创建默认项目
        if not self.projects:
            default = self.create_project("我的第一本小说", "开始你的创作之旅")
            self.current_project_id = default.id
    
    def _save_projects(self) -> None:
        """保存项目列表到文件"""
        data = {
            "projects": {p.id: asdict(p) for p in self.projects.values()},
            "current_project_id": self.current_project_id
        }
        self.meta_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def _get_project_dir(self, project_id: str) -> Path:
        """获取项目数据目录"""
        proj_dir = self.projects_dir / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir
    
    def create_project(self, name: str, description: str = "") -> Project:
        """创建新项目"""
        project_id = str(uuid.uuid4())[:8]
        project = Project(
            id=project_id,
            name=name,
            description=description
        )
        self.projects[project_id] = project
        
        # 创建项目目录结构
        proj_dir = self._get_project_dir(project_id)
        (proj_dir / "chapters").mkdir(exist_ok=True)
        
        # 初始化空数据文件
        (proj_dir / "outline.json").write_text("[]", encoding="utf-8")
        (proj_dir / "characters.json").write_text("[]", encoding="utf-8")
        (proj_dir / "worldbuilding.json").write_text("[]", encoding="utf-8")
        (proj_dir / "items.json").write_text("[]", encoding="utf-8")
        
        self._save_projects()
        return project
    
    def list_projects(self) -> List[Dict]:
        """列出所有项目"""
        return [
            {
                **asdict(p),
                "is_current": p.id == self.current_project_id
            }
            for p in sorted(
                self.projects.values(),
                key=lambda x: x.updated_at,
                reverse=True
            )
        ]
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """获取指定项目"""
        return self.projects.get(project_id)
    
    def get_current_project(self) -> Optional[Project]:
        """获取当前项目"""
        if self.current_project_id:
            return self.projects.get(self.current_project_id)
        return None
    
    def switch_project(self, project_id: str) -> bool:
        """切换当前项目"""
        if project_id in self.projects:
            self.current_project_id = project_id
            self._save_projects()
            return True
        return False
    
    def update_project(self, project_id: str, **kwargs) -> Optional[Project]:
        """更新项目信息"""
        project = self.projects.get(project_id)
        if project:
            for key, value in kwargs.items():
                if hasattr(project, key) and key not in ['id', 'created_at']:
                    setattr(project, key, value)
            project.updated_at = datetime.now().isoformat()
            self._save_projects()
        return project
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目及其所有数据（包括知识库）"""
        if project_id not in self.projects:
            return False
        
        # 不能删除最后一个项目
        if len(self.projects) <= 1:
            return False
        
        # 删除项目目录
        proj_dir = self.projects_dir / project_id
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
        
        # 删除知识库目录
        kb_dir = self.data_dir.parent / "data" / "knowledge_base" / project_id
        if kb_dir.exists():
            shutil.rmtree(kb_dir)
            logger.info(f"已删除项目 {project_id} 的知识库数据")
        
        del self.projects[project_id]
        
        # 如果删除的是当前项目，切换到其他项目
        if self.current_project_id == project_id:
            self.current_project_id = list(self.projects.keys())[0]
        
        self._save_projects()
        return True
    
    # ===== 项目数据操作 =====
    
    def get_project_data_path(self, data_type: str) -> Path:
        """获取当前项目的数据文件路径"""
        if not self.current_project_id:
            raise ValueError("No current project")
        
        proj_dir = self._get_project_dir(self.current_project_id)
        
        if data_type == "outline":
            return proj_dir / "outline.json"
        elif data_type == "characters":
            return proj_dir / "characters.json"
        elif data_type == "worldbuilding":
            return proj_dir / "worldbuilding.json"
        elif data_type == "items":
            return proj_dir / "items.json"
        elif data_type == "chapters":
            return proj_dir / "chapters"
        else:
            raise ValueError(f"Unknown data type: {data_type}")
    
    def load_project_data(self, data_type: str) -> List[Dict]:
        """加载当前项目的数据"""
        try:
            path = self.get_project_data_path(data_type)
            if path.exists() and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load {data_type}: {e}")
        return []
    
    def save_project_data(self, data_type: str, data: List[Dict]) -> None:
        """保存当前项目的数据"""
        path = self.get_project_data_path(data_type)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        # 更新项目修改时间
        if self.current_project_id:
            self.update_project(self.current_project_id)


# 全局实例
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """获取全局项目管理器实例"""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager


# 模块职责说明：管理多个小说项目的创建、切换、删除和数据隔离，实现项目级数据持久化。
