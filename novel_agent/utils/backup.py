"""
项目备份与恢复模块

提供项目的完整备份、导出和导入功能
"""

import json
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    """备份元数据"""
    backup_id: str
    project_id: str
    project_name: str
    created_at: str
    backup_type: str  # full/partial
    version: str = "1.0"
    file_count: int = 0
    total_size: int = 0
    included_items: List[str] = None
    
    def __post_init__(self):
        if self.included_items is None:
            self.included_items = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProjectBackupService:
    """项目备份服务"""
    
    BACKUP_VERSION = "1.0"
    
    # 备份包含的项目
    BACKUP_ITEMS = {
        "worldbuilding": "worldbuilding.json",
        "outline": "outline.json",
        "characters": "characters.json",
        "items": "items.json",
        "chapters": "chapters/",
        "aux_memory": "aux_memory/",
        "resources": "resources/",
        "client_state": "client_state/",
        "mode_memory": "mode_memory/",  # 模式记忆(infinite_write, collab_write等)
    }
    
    # 需要从data目录备份的项目(不在项目目录内)
    EXTERNAL_BACKUP_ITEMS = {
        "knowledge_base": "knowledge_base/{project_id}/",  # 知识库(向量数据库)
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        from ..constants import get_data_dir
        self.data_dir = Path(data_dir or get_data_dir())
        self.backups_dir = self.data_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_project_dir(self, project_id: str) -> Path:
        """获取项目目录"""
        return self.data_dir / "projects" / project_id
    
    def _generate_backup_id(self) -> str:
        """生成备份ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _get_backup_path(self, backup_id: str) -> Path:
        """获取备份文件路径"""
        return self.backups_dir / f"backup_{backup_id}.zip"
    
    def _calculate_dir_size(self, directory: Path) -> int:
        """计算目录大小"""
        total = 0
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception as e:
            logger.warning(f"Failed to calculate size for {directory}: {e}")
        return total
    
    def create_backup(
        self,
        project_id: str,
        project_name: str,
        backup_type: str = "full",
        include_items: Optional[List[str]] = None,
        local_storage_data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        创建项目备份
        
        Args:
            project_id: 项目ID
            project_name: 项目名称
            backup_type: 备份类型 (full/partial)
            include_items: 要包含的项目列表(partial时使用)
            
        Returns:
            备份信息
        """
        project_dir = self._get_project_dir(project_id)
        
        if not project_dir.exists():
            raise ValueError(f"Project not found: {project_id}")
        
        # 生成备份ID
        backup_id = self._generate_backup_id()
        backup_path = self._get_backup_path(backup_id)
        
        # 确定要备份的项目
        if backup_type == "full":
            items_to_backup = list(self.BACKUP_ITEMS.keys())
        else:
            items_to_backup = include_items or []
        
        # 创建ZIP备份
        file_count = 0
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 添加项目目录内的文件
                for item_key in items_to_backup:
                    if item_key in self.BACKUP_ITEMS:
                        item_path = self.BACKUP_ITEMS[item_key]
                        source_path = project_dir / item_path
                        
                        if not source_path.exists():
                            continue
                        
                        if source_path.is_file():
                            # 单个文件
                            arcname = f"project/{item_path}"
                            zipf.write(source_path, arcname)
                            file_count += 1
                        elif source_path.is_dir():
                            # 目录
                            for file_path in source_path.rglob("*"):
                                if file_path.is_file():
                                    arcname = f"project/{file_path.relative_to(project_dir)}"
                                    zipf.write(file_path, arcname)
                                    file_count += 1
                    
                    # 添加外部数据(如知识库)
                    elif item_key in self.EXTERNAL_BACKUP_ITEMS:
                        item_path_template = self.EXTERNAL_BACKUP_ITEMS[item_key]
                        item_path = item_path_template.format(project_id=project_id)
                        source_path = self.data_dir / item_path
                        
                        if not source_path.exists():
                            continue
                        
                        if source_path.is_file():
                            arcname = f"external/{item_key}/{source_path.name}"
                            zipf.write(source_path, arcname)
                            file_count += 1
                        elif source_path.is_dir():
                            # 目录
                            for file_path in source_path.rglob("*"):
                                if file_path.is_file():
                                    arcname = f"external/{item_key}/{file_path.relative_to(source_path)}"
                                    zipf.write(file_path, arcname)
                                    file_count += 1
                
                # 保存localStorage数据
                if local_storage_data:
                    local_storage_json = json.dumps(local_storage_data, ensure_ascii=False, indent=2)
                    zipf.writestr("local_storage.json", local_storage_json)
                
                # 创建备份元数据
                metadata = BackupMetadata(
                    backup_id=backup_id,
                    project_id=project_id,
                    project_name=project_name,
                    created_at=datetime.now().isoformat(),
                    backup_type=backup_type,
                    version=self.BACKUP_VERSION,
                    file_count=file_count,
                    total_size=0,  # 稍后计算
                    included_items=items_to_backup
                )
                
                # 添加元数据到备份
                metadata_json = json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2)
                zipf.writestr("backup_metadata.json", metadata_json)
            
            # 计算备份大小
            backup_size = backup_path.stat().st_size
            metadata.total_size = backup_size
            
            logger.info(f"Backup created: {backup_path} ({file_count} files, {backup_size} bytes)")
            
            return {
                "success": True,
                "backup_id": backup_id,
                "backup_path": str(backup_path),
                "metadata": metadata.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # 清理失败的备份文件
            if backup_path.exists():
                backup_path.unlink()
            raise
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有备份"""
        backups = []
        
        for backup_file in self.backups_dir.glob("backup_*.zip"):
            try:
                with zipfile.ZipFile(backup_file, 'r') as zipf:
                    # 读取元数据
                    metadata_json = zipf.read("backup_metadata.json").decode('utf-8')
                    metadata = json.loads(metadata_json)
                    
                    # 添加文件信息
                    metadata["backup_file"] = backup_file.name
                    metadata["backup_path"] = str(backup_file)
                    metadata["file_size"] = backup_file.stat().st_size
                    
                    backups.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to read backup metadata from {backup_file}: {e}")
        
        # 按创建时间倒序排序
        backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return backups
    
    def get_backup_info(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """获取备份信息"""
        backup_path = self._get_backup_path(backup_id)
        
        if not backup_path.exists():
            return None
        
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                metadata_json = zipf.read("backup_metadata.json").decode('utf-8')
                metadata = json.loads(metadata_json)
                
                # 添加文件列表
                file_list = [name for name in zipf.namelist() if name != "backup_metadata.json"]
                metadata["files"] = file_list
                metadata["backup_path"] = str(backup_path)
                metadata["file_size"] = backup_path.stat().st_size
                
                return metadata
        except Exception as e:
            logger.error(f"Failed to get backup info: {e}")
            return None
    
    def restore_backup(
        self,
        backup_id: str,
        target_project_id: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        恢复备份
        
        Args:
            backup_id: 备份ID
            target_project_id: 目标项目ID(如果为None,使用原项目ID)
            overwrite: 是否覆盖现有文件
            
        Returns:
            恢复结果
        """
        backup_path = self._get_backup_path(backup_id)
        
        if not backup_path.exists():
            raise ValueError(f"Backup not found: {backup_id}")
        
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # 读取元数据
                metadata_json = zipf.read("backup_metadata.json").decode('utf-8')
                metadata = json.loads(metadata_json)
                
                # 确定目标项目ID
                project_id = target_project_id or metadata["project_id"]
                project_dir = self._get_project_dir(project_id)
                
                # 检查是否需要覆盖
                if project_dir.exists() and not overwrite:
                    raise ValueError(f"Project already exists: {project_id}. Use overwrite=True to replace.")
                
                # 创建项目目录
                project_dir.mkdir(parents=True, exist_ok=True)
                
                # 解压文件
                restored_files = 0
                for file_info in zipf.infolist():
                    if file_info.filename == "backup_metadata.json":
                        continue
                    
                    # 处理项目目录内的文件
                    if file_info.filename.startswith("project/"):
                        target_path = project_dir / file_info.filename[8:]
                    # 处理外部数据(如知识库)
                    elif file_info.filename.startswith("external/"):
                        # external/knowledge_base/xxx -> data/knowledge_base/{project_id}/xxx
                        parts = file_info.filename.split("/", 2)
                        if len(parts) >= 3:
                            external_type = parts[1]  # knowledge_base
                            relative_path = parts[2]  # 文件相对路径
                            
                            if external_type == "knowledge_base":
                                target_path = self.data_dir / "knowledge_base" / project_id / relative_path
                            else:
                                # 其他外部数据类型
                                target_path = self.data_dir / external_type / project_id / relative_path
                        else:
                            continue
                    else:
                        target_path = project_dir / file_info.filename
                    
                    # 创建父目录
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 解压文件
                    with zipf.open(file_info) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    
                    restored_files += 1
                
                # 读取localStorage数据(如果存在)
                local_storage_data = None
                if "local_storage.json" in zipf.namelist():
                    try:
                        local_storage_json = zipf.read("local_storage.json").decode('utf-8')
                        local_storage_data = json.loads(local_storage_json)
                    except Exception as e:
                        logger.warning(f"Failed to read localStorage data: {e}")
                
                logger.info(f"Backup restored: {project_id} ({restored_files} files)")
                
                return {
                    "success": True,
                    "project_id": project_id,
                    "restored_files": restored_files,
                    "metadata": metadata,
                    "local_storage_data": local_storage_data
                }
                
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            raise
    
    def delete_backup(self, backup_id: str) -> bool:
        """删除备份"""
        backup_path = self._get_backup_path(backup_id)
        
        if not backup_path.exists():
            return False
        
        try:
            backup_path.unlink()
            logger.info(f"Backup deleted: {backup_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return False
    
    def export_backup(self, backup_id: str, export_path: Path) -> bool:
        """
        导出备份到指定位置
        
        Args:
            backup_id: 备份ID
            export_path: 导出路径
            
        Returns:
            是否成功
        """
        backup_path = self._get_backup_path(backup_id)
        
        if not backup_path.exists():
            return False
        
        try:
            export_path = Path(export_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, export_path)
            logger.info(f"Backup exported to: {export_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export backup: {e}")
            return False
    
    def import_backup(self, backup_file: Path) -> str:
        """
        导入外部备份文件
        
        Args:
            backup_file: 备份文件路径
            
        Returns:
            导入后的备份ID
        """
        if not backup_file.exists():
            raise ValueError(f"Backup file not found: {backup_file}")
        
        try:
            # 验证备份文件
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                if "backup_metadata.json" not in zipf.namelist():
                    raise ValueError("Invalid backup file: missing metadata")
                
                metadata_json = zipf.read("backup_metadata.json").decode('utf-8')
                metadata = json.loads(metadata_json)
            
            # 生成新的备份ID
            backup_id = self._generate_backup_id()
            target_path = self._get_backup_path(backup_id)
            
            # 复制备份文件
            shutil.copy2(backup_file, target_path)
            
            logger.info(f"Backup imported: {backup_id} from {backup_file}")
            
            return backup_id
            
        except Exception as e:
            logger.error(f"Failed to import backup: {e}")
            raise


# 全局单例
_backup_service: Optional[ProjectBackupService] = None


def get_backup_service() -> ProjectBackupService:
    """获取备份服务全局实例"""
    global _backup_service
    if _backup_service is None:
        _backup_service = ProjectBackupService()
    return _backup_service


# 模块职责说明：提供项目的完整备份、导出、导入和恢复功能