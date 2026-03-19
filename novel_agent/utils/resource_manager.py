"""
资料库管理模块

管理项目的资料文件,包括文档、参考资料、图片等
"""

import json
import logging
import shutil
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ResourceFile:
    """资料文件"""
    id: str
    project_id: str
    filename: str
    original_filename: str
    file_type: str  # document/reference/image/other
    mime_type: str
    file_size: int
    file_path: str
    description: str = ""
    tags: List[str] = None
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResourceManager:
    """资料库管理器"""
    
    # 文件类型映射
    FILE_TYPE_MAPPING = {
        "document": [".txt", ".md", ".doc", ".docx", ".pdf", ".rtf"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
        "reference": [".json", ".yaml", ".yml", ".xml", ".csv"],
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        from ..constants import get_data_dir
        self.data_dir = Path(data_dir or get_data_dir())
    
    def _get_project_resources_dir(self, project_id: str) -> Path:
        """获取项目资料库目录"""
        resources_dir = self.data_dir / "projects" / project_id / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        return resources_dir
    
    def _get_metadata_file(self, project_id: str) -> Path:
        """获取资料元数据文件"""
        return self._get_project_resources_dir(project_id) / "metadata.json"
    
    def _load_metadata(self, project_id: str) -> Dict[str, ResourceFile]:
        """加载资料元数据"""
        metadata_file = self._get_metadata_file(project_id)
        
        if not metadata_file.exists():
            return {}
        
        try:
            data = json.loads(metadata_file.read_text(encoding="utf-8"))
            return {
                file_id: ResourceFile(**file_data)
                for file_id, file_data in data.items()
            }
        except Exception as e:
            logger.warning(f"Failed to load resource metadata: {e}")
            return {}
    
    def _save_metadata(self, project_id: str, metadata: Dict[str, ResourceFile]) -> None:
        """保存资料元数据"""
        metadata_file = self._get_metadata_file(project_id)
        
        data = {
            file_id: resource.to_dict()
            for file_id, resource in metadata.items()
        }
        
        metadata_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def _detect_file_type(self, filename: str) -> str:
        """检测文件类型"""
        ext = Path(filename).suffix.lower()
        
        for file_type, extensions in self.FILE_TYPE_MAPPING.items():
            if ext in extensions:
                return file_type
        
        return "other"
    
    def _generate_file_id(self) -> str:
        """生成文件ID"""
        import uuid
        return f"res_{uuid.uuid4().hex[:12]}"
    
    def add_resource(
        self,
        project_id: str,
        source_path: Path,
        file_type: Optional[str] = None,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> ResourceFile:
        """
        添加资料文件
        
        Args:
            project_id: 项目ID
            source_path: 源文件路径
            file_type: 文件类型(可选,自动检测)
            description: 描述
            tags: 标签
            
        Returns:
            资料文件对象
        """
        if not source_path.exists():
            raise ValueError(f"Source file not found: {source_path}")
        
        # 生成文件ID和目标路径
        file_id = self._generate_file_id()
        original_filename = source_path.name
        
        # 检测文件类型
        if file_type is None:
            file_type = self._detect_file_type(original_filename)
        
        # 创建类型子目录
        resources_dir = self._get_project_resources_dir(project_id)
        type_dir = resources_dir / file_type
        type_dir.mkdir(exist_ok=True)
        
        # 保留原始扩展名
        ext = source_path.suffix
        target_filename = f"{file_id}{ext}"
        target_path = type_dir / target_filename
        
        # 复制文件
        shutil.copy2(source_path, target_path)
        
        # 获取文件信息
        file_size = target_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(original_filename)
        
        # 创建资料对象
        resource = ResourceFile(
            id=file_id,
            project_id=project_id,
            filename=target_filename,
            original_filename=original_filename,
            file_type=file_type,
            mime_type=mime_type or "application/octet-stream",
            file_size=file_size,
            file_path=str(target_path.relative_to(resources_dir)),
            description=description,
            tags=tags or []
        )
        
        # 保存元数据
        metadata = self._load_metadata(project_id)
        metadata[file_id] = resource
        self._save_metadata(project_id, metadata)
        
        logger.info(f"Resource added: {file_id} ({original_filename})")
        
        return resource
    
    def list_resources(
        self,
        project_id: str,
        file_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[ResourceFile]:
        """
        列出资料文件
        
        Args:
            project_id: 项目ID
            file_type: 文件类型过滤
            tags: 标签过滤
            
        Returns:
            资料文件列表
        """
        metadata = self._load_metadata(project_id)
        resources = list(metadata.values())
        
        # 按文件类型过滤
        if file_type:
            resources = [r for r in resources if r.file_type == file_type]
        
        # 按标签过滤
        if tags:
            tag_set = set(tags)
            resources = [
                r for r in resources
                if tag_set.intersection(set(r.tags))
            ]
        
        # 按创建时间倒序排序
        resources.sort(key=lambda r: r.created_at, reverse=True)
        
        return resources
    
    def get_resource(self, project_id: str, file_id: str) -> Optional[ResourceFile]:
        """获取资料文件信息"""
        metadata = self._load_metadata(project_id)
        return metadata.get(file_id)
    
    def get_resource_path(self, project_id: str, file_id: str) -> Optional[Path]:
        """获取资料文件的实际路径"""
        resource = self.get_resource(project_id, file_id)
        if not resource:
            return None
        
        resources_dir = self._get_project_resources_dir(project_id)
        return resources_dir / resource.file_path
    
    def update_resource(
        self,
        project_id: str,
        file_id: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[ResourceFile]:
        """更新资料文件信息"""
        metadata = self._load_metadata(project_id)
        resource = metadata.get(file_id)
        
        if not resource:
            return None
        
        if description is not None:
            resource.description = description
        
        if tags is not None:
            resource.tags = tags
        
        resource.updated_at = datetime.now().isoformat()
        
        self._save_metadata(project_id, metadata)
        
        return resource
    
    def delete_resource(self, project_id: str, file_id: str) -> bool:
        """删除资料文件"""
        metadata = self._load_metadata(project_id)
        resource = metadata.get(file_id)
        
        if not resource:
            return False
        
        # 删除实际文件
        file_path = self.get_resource_path(project_id, file_id)
        if file_path and file_path.exists():
            file_path.unlink()
        
        # 删除元数据
        del metadata[file_id]
        self._save_metadata(project_id, metadata)
        
        logger.info(f"Resource deleted: {file_id}")
        
        return True
    
    def get_statistics(self, project_id: str) -> Dict[str, Any]:
        """获取资料库统计信息"""
        resources = self.list_resources(project_id)
        
        stats = {
            "total_count": len(resources),
            "total_size": sum(r.file_size for r in resources),
            "by_type": {},
            "recent_files": []
        }
        
        # 按类型统计
        for resource in resources:
            file_type = resource.file_type
            if file_type not in stats["by_type"]:
                stats["by_type"][file_type] = {
                    "count": 0,
                    "size": 0
                }
            stats["by_type"][file_type]["count"] += 1
            stats["by_type"][file_type]["size"] += resource.file_size
        
        # 最近文件(前10个)
        stats["recent_files"] = [
            {
                "id": r.id,
                "filename": r.original_filename,
                "file_type": r.file_type,
                "created_at": r.created_at
            }
            for r in resources[:10]
        ]
        
        return stats


# 全局单例
_resource_manager: Optional[ResourceManager] = None


def get_resource_manager() -> ResourceManager:
    """获取资料库管理器全局实例"""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager


# 模块职责说明：管理项目的资料文件,包括文档、参考资料、图片等