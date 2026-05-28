"""
濡炪倕婀卞ú鎵不閿涘嫭鍊為柛?
缂佺媴绱曢幃濠冨緞濮橆偊鍤嬮悘蹇撶箺椤曗晜銇勯崷顓熺獥闁挎稑鑻悿鍕偝閻楀牊娈堕柟璇″櫍濞堁呯矉?
"""

import json
import uuid
import shutil
import logging
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from .utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)
_PROJECT_STATE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ProjectDeleteError(RuntimeError):
    """Raised when project files cannot be deleted safely."""

    def __init__(self, message: str, *, locked_path: Optional[Path] = None):
        super().__init__(message)
        self.locked_path = locked_path


def _is_windows_file_lock_error(exc: BaseException) -> bool:
    winerror = getattr(exc, "winerror", None)
    return winerror in {5, 32, 33}


def _rmtree_with_retry(path: Path, *, label: str, attempts: int = 6, delay: float = 0.2) -> None:
    """Remove a tree with short retries for Windows file-handle release latency."""
    if not path.exists():
        return

    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError as exc:
            last_error = exc
            if not _is_windows_file_lock_error(exc) or attempt == attempts - 1:
                break
            time.sleep(delay * (attempt + 1))
        except OSError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(delay * (attempt + 1))

    locked_path = Path(getattr(last_error, "filename", "") or path)
    raise ProjectDeleteError(
        f"{label}仍被系统或运行中的知识库占用，请稍等几秒后重试；如果仍失败，请重启应用后再删除。",
        locked_path=locked_path,
    ) from last_error


@dataclass
class Project:
    """Project metadata."""
    id: str
    name: str
    description: str = ""
    novel_type: str = ""
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
    濡炪倕婀卞ú鎵不閿涘嫭鍊為柛?
    缂佺媴绱曢幃濠冨緞濮橆偊鍤嬮悘蹇撶箺椤曗晜銇勯崷顓熺獥闁汇劌瀚崹鍗烆嚈閹巻鍋撴担绋跨仚閻炴稏鍔婇埀顑跨閸ㄥ綊姊介妶鍛闁告帒娲﹀畷?
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
        # 婵絽绻戦濂告煂瀹ュ牊绁伴梺顔挎閸樻稑銆掗崨顖楁晞闁告劕鎳庨悺銊╂晬瀹€鍕級闁稿繐绉靛Λ顐ｃ亜閸︻厽绐楁繛鍫濐儑閺嗏偓閻庝絻澹堥崵褔鎳樿箛鏃€娈堕柟璇″枤閻ゎ喚绮?
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
            default = self.create_project("默认项目", "开始创作你的小说")
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
        """闁兼儳鍢茶ぐ鍥ㄣ亜閸︻厽绐楅柡浣哄瀹撲線鎯勯鑲╃Э"""
        proj_dir = self.projects_dir / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir

    @staticmethod
    def _validate_state_key(state_key: str) -> str:
        key = (state_key or "").strip()
        if not _PROJECT_STATE_KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid project state key")
        return key
    
    def create_project(self, name: str, description: str = "", novel_type: str = "") -> Project:
        """Create a new project."""
        project_id = str(uuid.uuid4())[:8]
        project = Project(
            id=project_id,
            name=name,
            description=description,
            novel_type=str(novel_type or "").strip(),
        )
        self.projects[project_id] = project
        
        # 闁告帗绋戠紓鎾淬亜閸︻厽绐楅柣鈺婂枛缂嶅秶绱掗幘瀵糕偓?
        
        proj_dir = self._get_project_dir(project_id)
        (proj_dir / "chapters").mkdir(exist_ok=True)
        
        # 闁告帗绻傞～鎰板礌閺嶎偀鏁勯柡浣哄瀹撲線寮崶锔筋偨
        # 使用原子写入初始化 JSON 文件
        for filename in [
            "outline.json",
            "chapters.json",
            "characters.json",
            "worldbuilding.json",
            "items.json",
            "eventlines.json",
            "outline_settings.json",
            "detail_settings.json",
            "chapter_settings.json",
        ]:
            file_path = proj_dir / filename
            atomic_write_json(file_path, [], old_content=None, ensure_ascii=False, indent=2)
        
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
        """闁告帞濞€濞呭孩銇勯崷顓熺獥闁告瑥锕ら崣楣冨箥閳ь剟寮垫径瀣闁硅鍣槐娆撳礌閸涱喖顏柣顓滃劥閻︽垶鎯旈幙鍕"""
        if project_id not in self.projects:
            return False
        
        # 濞戞挸绉烽崗姗€宕氶悩缁樼彑闁哄牃鍋撻柛姘凹缁斿瓨绋夐鍫涒偓宥夋儎?
        
        if len(self.projects) <= 1:
            return False
        
        # 闁告帞濞€濞呭孩銇勯崷顓熺獥闁烩晩鍠栫紞?
        
        kb_dir = self.data_dir.parent / "data" / "knowledge_base" / project_id
        if kb_dir.exists():
            _rmtree_with_retry(kb_dir, label="知识库目录")
            logger.info(f"Deleted knowledge base data for project {project_id}")

        proj_dir = self.projects_dir / project_id
        _rmtree_with_retry(proj_dir, label="项目目录")
        
        # 闁告帞濞€濞呭酣鎯岄妷銊ф閹煎瓨鎸惧ú鎷屻亹?

        try:
            from .utils.token_stats import get_token_stats_store

            deleted_token_records = get_token_stats_store().reset_all(project_id=project_id)
            if deleted_token_records:
                logger.info(
                    "Deleted token stats for project %s: %s records",
                    project_id,
                    deleted_token_records,
                )
        except Exception as exc:
            logger.warning("Failed to delete token stats for project %s: %s", project_id, exc)
        
        del self.projects[project_id]
        
        # 濠碘€冲€归悘澶愬礆閻樼粯鐝熼柣銊ュ濡叉瓕銇愰幘鍐差枀濡炪倕婀卞ú浼存晬鐏炶棄鐎奸柟骞垮灩閸╁矂宕楅張鐢甸搨濡炪倕婀卞ú?
        
        if self.current_project_id == project_id:
            self.current_project_id = list(self.projects.keys())[0]
        
        self._save_projects()
        return True
    
    # ===== 濡炪倕婀卞ú浼村极閻楀牆绁﹂柟鍨С缂?=====
    
    def get_project_data_path(self, data_type: str) -> Path:
        """Get current project data file path."""
        if not self.current_project_id:
            raise ValueError("No current project")
        
        proj_dir = self._get_project_dir(self.current_project_id)
        normalized_data_type = str(data_type or "").strip()
        
        if normalized_data_type == "outline":
            return proj_dir / "outline.json"
        elif normalized_data_type == "characters":
            return proj_dir / "characters.json"
        elif normalized_data_type == "worldbuilding":
            return proj_dir / "worldbuilding.json"
        elif normalized_data_type == "items":
            return proj_dir / "items.json"
        elif normalized_data_type == "eventlines":
            return proj_dir / "eventlines.json"
        elif normalized_data_type == "outline_settings":
            return proj_dir / "outline_settings.json"
        elif normalized_data_type == "detail_settings":
            return proj_dir / "detail_settings.json"
        elif normalized_data_type == "chapter_settings":
            return proj_dir / "chapter_settings.json"
        elif normalized_data_type == "chapters":
            return proj_dir / "chapters.json"
        elif normalized_data_type == "chapter_summary":
            return proj_dir / "chapter_summary.json"
        elif normalized_data_type == "chapter_volumes":
            return proj_dir / "chapter_volumes.json"
        elif re.fullmatch(r"custom_[A-Za-z0-9_-]{1,80}", normalized_data_type):
            return proj_dir / f"{normalized_data_type}.json"
        else:
            raise ValueError(f"Unknown data type: {data_type}")

    def get_chapters_dir(self) -> Path:
        """Return current project's markdown chapter directory.

        Note:
            get_project_data_path("chapters") returns the structured chapters.json file.
            Markdown chapter files must be stored under the sibling chapters/ directory.
        """
        if not self.current_project_id:
            raise ValueError("No current project")
        proj_dir = self._get_project_dir(self.current_project_id)
        chapters_dir = proj_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        return chapters_dir

    def _get_chapters_clear_marker_path(self) -> Path:
        if not self.current_project_id:
            raise ValueError("No current project")
        return self._get_project_dir(self.current_project_id) / ".chapters_cleared"

    def get_library_path(self) -> Path:
        """返回当前项目的 library.json 路径"""
        proj_dir = self.projects_dir / self.current_project_id
        return proj_dir / "library.json"

    def get_library_backup_dir(self) -> Path:
        """返回当前项目的 library 备份目录"""
        proj_dir = self.projects_dir / self.current_project_id
        return proj_dir / ".library_backup"

    def get_current_project_dir(self) -> Path:
        """返回当前项目目录"""
        return self.projects_dir / self.current_project_id
    
    def load_project_data(self, data_type: str) -> List[Dict]:
        """Load current project data."""
        try:
            if data_type == "chapters":
                return self._load_chapters_data()
            path = self.get_project_data_path(data_type)
            if path.exists() and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load {data_type}: {e}")
        return []
    
    def save_project_data(self, data_type: str, data: List[Dict]) -> None:
        """Save current project data."""
        path = self.get_project_data_path(data_type)
        old_content = path.read_text(encoding="utf-8") if path.exists() else None
        atomic_write_json(
            path,
            data,
            old_content=old_content,
            ensure_ascii=False,
            indent=2,
        )
        if str(data_type or "").strip() == "chapters":
            clear_marker = self._get_chapters_clear_marker_path()
            if not data:
                clear_marker.write_text("1", encoding="utf-8")
            else:
                clear_marker.unlink(missing_ok=True)
        # 闁哄洤鐡ㄩ弻濠冦亜閸︻厽绐楀ǎ鍥跺枟閺佸ジ寮崼鏇燂紵
        if self.current_project_id:
            self.update_project(self.current_project_id)

    def _load_chapters_data(self) -> List[Dict]:
        """Load canonical chapter records, with legacy fallbacks."""
        if not self.current_project_id:
            return []

        proj_dir = self._get_project_dir(self.current_project_id)
        chapters_json = proj_dir / "chapters.json"
        json_rows: List[Dict] = []
        chapters_explicitly_cleared = False
        if chapters_json.exists() and chapters_json.is_file():
            try:
                payload = json.loads(chapters_json.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    json_rows = [row for row in payload if isinstance(row, dict)]
                    chapters_explicitly_cleared = not json_rows and self._get_chapters_clear_marker_path().exists()
            except Exception as exc:
                logger.warning(f"Failed to load chapters.json: {exc}")
        if chapters_explicitly_cleared:
            return []

        chapters_dir = proj_dir / "chapters"
        file_rows: List[Dict] = []
        if chapters_dir.exists() and chapters_dir.is_dir():
            for index, file_path in enumerate(sorted(chapters_dir.glob("*.md")), start=1):
                try:
                    content = file_path.read_text(encoding="utf-8").strip()
                except Exception as exc:
                    logger.warning(f"Failed to load chapter file {file_path}: {exc}")
                    continue
                chapter_number = self._extract_chapter_number(file_path.stem, index)
                title = self._clean_chapter_title(file_path.stem, chapter_number)
                file_rows.append({
                    "chapter_number": chapter_number,
                    "title": title,
                    "content": content,
                    "summary": content[:200],
                    "source_file": str(file_path),
                })
        if json_rows:
            merged_by_number: Dict[int, Dict] = {}
            for index, row in enumerate(json_rows, start=1):
                number = self._extract_chapter_number(
                    row.get("chapter_number") or row.get("number"),
                    index,
                )
                copied = dict(row)
                copied["chapter_number"] = number
                merged_by_number[number] = copied
            for index, row in enumerate(file_rows, start=1):
                number = self._extract_chapter_number(row.get("chapter_number"), index)
                target = merged_by_number.setdefault(number, dict(row))
                if not str(target.get("content") or "").strip() and str(row.get("content") or "").strip():
                    target.update(dict(row))
                    target["chapter_number"] = number
            return sorted(merged_by_number.values(), key=lambda row: int(row.get("chapter_number", 0) or 0))

        if file_rows:
            return sorted(file_rows, key=lambda row: int(row.get("chapter_number", 0) or 0))

        # Legacy compatibility: old builds stored chapter text inside outline rows.
        outline_path = proj_dir / "outline.json"
        chapter_rows: List[Dict] = []
        if outline_path.exists() and outline_path.is_file():
            try:
                outline_payload = json.loads(outline_path.read_text(encoding="utf-8"))
            except Exception:
                outline_payload = []
            outline_rows = outline_payload.get("chapters") if isinstance(outline_payload, dict) else outline_payload
            if isinstance(outline_rows, list):
                for index, row in enumerate(outline_rows, start=1):
                    if not isinstance(row, dict):
                        continue
                    content = str(row.get("content") or "").strip()
                    if not content:
                        continue
                    chapter_rows.append({
                        **row,
                        "chapter_number": self._extract_chapter_number(row.get("chapter_number") or row.get("number"), index),
                        "title": str(row.get("title") or row.get("name") or f"第{index}章").strip(),
                        "content": content,
                    })
        return chapter_rows

    @staticmethod
    def _extract_chapter_number(value: Any, fallback: int) -> int:
        text = str(value or "").strip()
        digit_match = re.search(r"\d+", text)
        if digit_match:
            try:
                number = int(digit_match.group(0))
                return number if number > 0 else fallback
            except ValueError:
                return fallback
        return fallback

    @staticmethod
    def _clean_chapter_title(stem: str, chapter_number: int) -> str:
        title = re.sub(r"-?\d+字$", "", str(stem or "")).strip("-_ ")
        title = re.sub(r"^\d+[-_ ]+", "", title).strip("-_ ")
        return title or f"第{chapter_number}章"


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


# 婵☆垪鈧櫕鍋ラ柤鍗炵焷閻鎷犵€涙ɑ顫栭柨娑欐皑椤撴悂鎮堕崱妤婃▼濞戞搩浜滈惃顒傛嫚閹绢喓鈧秹鎯勯鐐暠闁告帗绋戠紓鎾诲Υ娴ｇ鐎奸柟璇℃娇閳ь兛绀侀崹褰掓⒔閵堝懏瀚查柡浣哄瀹撲線姊鹃弮鍌ょ€查柨娑樿嫰閻ゅ嫰鎮虫导娣偓宥夋儎椤旈箖鐛撻柡浣哄瀹撲線骞愭担椋庣暯闁告牗鐗撻埀?
