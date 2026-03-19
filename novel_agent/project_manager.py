"""
濡炪倕婀卞ú鎵不閿涘嫭鍊為柛?
缂佺媴绱曢幃濠冨緞濮橆偊鍤嬮悘蹇撶箺椤曗晜銇勯崷顓熺獥闁挎稑鑻悿鍕偝閻楀牊娈堕柟璇″櫍濞堁呯矉?
"""

import json
import uuid
import shutil
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from .utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)
_PROJECT_STATE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class Project:
    """Project metadata."""
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
    濡炪倕婀卞ú鎵不閿涘嫭鍊為柛?
    缂佺媴绱曢幃濠冨緞濮橆偊鍤嬮悘蹇撶箺椤曗晜銇勯崷顓熺獥闁汇劌瀚崹鍗烆嚈閹巻鍋撴担绋跨仚閻炴稏鍔婇埀顑跨閸ㄥ綊姊介妶鍛闁告帒娲﹀畷?
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
        """Load project metadata from disk."""
        # 婵絽绻戦濂告煂瀹ュ牊绁伴梺顔挎閸樻稑銆掗崨顖楁晞闁告劕鎳庨悺銊╂晬瀹€鍕級闁稿繐绉靛Λ顐ｃ亜閸︻厽绐楁繛鍫濐儑閺嗏偓閻庝絻澹堥崵褔鎳樿箛鏃€娈堕柟璇″枤閻ゎ喚绮?
        self.projects = {}
        self.current_project_id = None

        if self.meta_file.exists():
            try:
                data = json.loads(self.meta_file.read_text(encoding="utf-8"))
                for proj_id, proj_data in data.get("projects", {}).items():
                    self.projects[proj_id] = Project(**proj_data)
                loaded_current_project_id = data.get("current_project_id")
                if loaded_current_project_id in self.projects:
                    self.current_project_id = loaded_current_project_id
            except Exception as e:
                logger.warning(f"Failed to load projects: {e}")

        # Fallback to first project when current_project_id is invalid
        if self.projects and not self.current_project_id:
            self.current_project_id = next(iter(self.projects.keys()))
        # Initialize a default project only when no projects exist
        if not self.projects:
            default = self.create_project("Default Project", "Start writing")
            self.current_project_id = default.id
    def _save_projects(self) -> None:
        """Persist project metadata to disk."""
        data = {
            "projects": {p.id: asdict(p) for p in self.projects.values()},
            "current_project_id": self.current_project_id
        }
        old_content = self.meta_file.read_text(encoding="utf-8") if self.meta_file.exists() else None
        atomic_write_json(
            self.meta_file,
            data,
            old_content=old_content,
            ensure_ascii=False,
            indent=2,
        )
    
    def _get_project_dir(self, project_id: str) -> Path:
        """闁兼儳鍢茶ぐ鍥ㄣ亜閸︻厽绐楅柡浣哄瀹撲線鎯勯鑲╃Э"""
        proj_dir = self.projects_dir / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir

    @staticmethod
    def _validate_state_key(state_key: str) -> str:
        key = (state_key or "").strip()
        if not _PROJECT_STATE_KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid project state key")
        return key
    
    def create_project(self, name: str, description: str = "") -> Project:
        """Create a new project."""
        project_id = str(uuid.uuid4())[:8]
        project = Project(
            id=project_id,
            name=name,
            description=description
        )
        self.projects[project_id] = project
        
        # 闁告帗绋戠紓鎾淬亜閸︻厽绐楅柣鈺婂枛缂嶅秶绱掗幘瀵糕偓?
        
        proj_dir = self._get_project_dir(project_id)
        (proj_dir / "chapters").mkdir(exist_ok=True)
        
        # 闁告帗绻傞～鎰板礌閺嶎偀鏁勯柡浣哄瀹撲線寮崶锔筋偨
        (proj_dir / "outline.json").write_text("[]", encoding="utf-8")
        (proj_dir / "characters.json").write_text("[]", encoding="utf-8")
        (proj_dir / "worldbuilding.json").write_text("[]", encoding="utf-8")
        (proj_dir / "items.json").write_text("[]", encoding="utf-8")
        
        self._save_projects()
        return project
    
    def list_projects(self) -> List[Dict]:
        """List all projects."""
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
        """Get project by id."""
        return self.projects.get(project_id)
    
    def get_current_project(self) -> Optional[Project]:
        """Get current project."""
        if self.current_project_id:
            return self.projects.get(self.current_project_id)
        return None
    
    def switch_project(self, project_id: str) -> bool:
        """Switch current project."""
        if project_id in self.projects:
            self.current_project_id = project_id
            self._save_projects()
            return True
        return False
    
    def update_project(self, project_id: str, **kwargs) -> Optional[Project]:
        """Update project fields."""
        project = self.projects.get(project_id)
        if project:
            for key, value in kwargs.items():
                if hasattr(project, key) and key not in ['id', 'created_at']:
                    setattr(project, key, value)
            project.updated_at = datetime.now().isoformat()
            self._save_projects()
        return project
    
    def delete_project(self, project_id: str) -> bool:
        """闁告帞濞€濞呭孩銇勯崷顓熺獥闁告瑥锕ら崣楣冨箥閳ь剟寮垫径瀣闁硅鍣槐娆撳礌閸涱喖顏柣顓滃劥閻︽垶鎯旈幙鍕"""
        if project_id not in self.projects:
            return False
        
        # 濞戞挸绉烽崗姗€宕氶悩缁樼彑闁哄牃鍋撻柛姘凹缁斿瓨绋夐鍫涒偓宥夋儎?
        
        if len(self.projects) <= 1:
            return False
        
        # 闁告帞濞€濞呭孩銇勯崷顓熺獥闁烩晩鍠栫紞?
        
        proj_dir = self.projects_dir / project_id
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
        
        # 闁告帞濞€濞呭酣鎯岄妷銊ф閹煎瓨鎸惧ú鎷屻亹?
        
        kb_dir = self.data_dir.parent / "data" / "knowledge_base" / project_id
        if kb_dir.exists():
            shutil.rmtree(kb_dir)
            logger.info(f"Deleted knowledge base data for project {project_id}")
        
        del self.projects[project_id]
        
        # 濠碘€冲€归悘澶愬礆閻樼粯鐝熼柣銊ュ濡叉瓕銇愰幘鍐差枀濡炪倕婀卞ú浼存晬鐏炶棄鐎奸柟骞垮灩閸╁矂宕楅張鐢甸搨濡炪倕婀卞ú?
        
        if self.current_project_id == project_id:
            self.current_project_id = list(self.projects.keys())[0]
        
        self._save_projects()
        return True
    
    # ===== 濡炪倕婀卞ú浼村极閻楀牆绁﹂柟鍨С缂?=====
    
    def get_project_data_path(self, data_type: str) -> Path:
        """Get current project data file path."""
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
        """Load current project data."""
        try:
            path = self.get_project_data_path(data_type)
            if path.exists() and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load {data_type}: {e}")
        return []
    
    def save_project_data(self, data_type: str, data: List[Dict]) -> None:
        """Save current project data."""
        path = self.get_project_data_path(data_type)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        # 闁哄洤鐡ㄩ弻濠冦亜閸︻厽绐楀ǎ鍥跺枟閺佸ジ寮崼鏇燂紵
        if self.current_project_id:
            self.update_project(self.current_project_id)


    # ===== Project Frontend State =====

    def get_project_state_path(self, state_key: str) -> Path:
        """Get the current project's frontend state file path."""
        if not self.current_project_id:
            raise ValueError("No current project")

        safe_key = self._validate_state_key(state_key)
        project_dir = self._get_project_dir(self.current_project_id)
        state_dir = project_dir / "client_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / f"{safe_key}.json"

    def load_project_state(self, state_key: str, default: Any = None) -> Any:
        """Load the current project's frontend state value."""
        path = self.get_project_state_path(state_key)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load project state {state_key}: {e}")
            return default

    def save_project_state(self, state_key: str, data: Any) -> None:
        """Save the current project's frontend state value."""
        path = self.get_project_state_path(state_key)
        old_content = path.read_text(encoding="utf-8") if path.exists() else None
        atomic_write_json(
            path,
            data,
            old_content=old_content,
            ensure_ascii=False,
            indent=2,
        )
        if self.current_project_id:
            self.update_project(self.current_project_id)

    def delete_project_state(self, state_key: str) -> bool:
        """Delete the current project's frontend state value."""
        path = self.get_project_state_path(state_key)
        if not path.exists():
            return False
        path.unlink()
        if self.current_project_id:
            self.update_project(self.current_project_id)
        return True


_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """Return the global project manager singleton."""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager


# 婵☆垪鈧櫕鍋ラ柤鍗炵焷閻鎷犵€涙ɑ顫栭柨娑欐皑椤撴悂鎮堕崱妤婃▼濞戞搩浜滈惃顒傛嫚閹绢喓鈧秹鎯勯鐐暠闁告帗绋戠紓鎾诲Υ娴ｇ鐎奸柟璇℃娇閳ь兛绀侀崹褰掓⒔閵堝懏瀚查柡浣哄瀹撲線姊鹃弮鍌ょ€查柨娑樿嫰閻ゅ嫰鎮虫导娣偓宥夋儎椤旈箖鐛撻柡浣哄瀹撲線骞愭担椋庣暯闁告牗鐗撻埀?


