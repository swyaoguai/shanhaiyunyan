"""
世界观管理器
管理小说的世界设定
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorldSetting:
    """世界设定数据结构"""
    name: str
    world_type: str  # 玄幻/科幻/都市等
    power_system: Dict[str, Any] = field(default_factory=dict)
    geography: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, str]] = field(default_factory=list)
    factions: List[Dict[str, Any]] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    culture: Dict[str, Any] = field(default_factory=dict)
    technology_level: str = ""
    magic_system: str = ""
    timeline: str = ""


class WorldManager:
    """
    世界观管理器
    
    职责：
    1. 管理世界设定的各个方面
    2. 确保设定一致性
    3. 提供世界观上下文
    """
    
    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = project_dir
        self.world: Optional[WorldSetting] = None
        self.locations: Dict[str, Dict] = {}  # 地点详情
        self.items: Dict[str, Dict] = {}  # 重要物品
        self.events: List[Dict] = []  # 历史事件
        
        if project_dir:
            self._load_world()
    
    def set_world(self, world: WorldSetting) -> None:
        """设置世界观"""
        self.world = world
        self._save_world()
    
    def update_world(self, updates: Dict[str, Any]) -> None:
        """更新世界观属性"""
        if not self.world:
            self.world = WorldSetting(name="未命名世界", world_type="通用")
        
        for key, value in updates.items():
            if hasattr(self.world, key):
                setattr(self.world, key, value)
        
        self._save_world()
    
    def add_location(self, name: str, details: Dict[str, Any]) -> None:
        """添加地点"""
        self.locations[name] = details
        self._save_world()
    
    def add_item(self, name: str, details: Dict[str, Any]) -> None:
        """添加重要物品"""
        self.items[name] = details
        self._save_world()
    
    def add_event(self, event: Dict[str, str]) -> None:
        """添加历史事件"""
        self.events.append(event)
        self._save_world()
    
    def get_world_context(self) -> str:
        """
        获取世界观上下文(用于注入到Agent)
        
        Returns:
            格式化的世界观信息
        """
        if not self.world:
            return "暂无世界观设定"
        
        context = f"""【世界名称】{self.world.name}

【世界类型】{self.world.world_type}

【力量体系】
{json.dumps(self.world.power_system, ensure_ascii=False, indent=2) if self.world.power_system else "未设定"}

【地理环境】
{json.dumps(self.world.geography, ensure_ascii=False, indent=2) if self.world.geography else "未设定"}

【主要势力】
{self._format_factions()}

【世界规则】
{chr(10).join(f"- {rule}" for rule in self.world.rules) if self.world.rules else "未设定"}

【文化习俗】
{json.dumps(self.world.culture, ensure_ascii=False, indent=2) if self.world.culture else "未设定"}
"""
        return context
    
    def _format_factions(self) -> str:
        """格式化势力信息"""
        if not self.world or not self.world.factions:
            return "未设定"
        
        result = []
        for faction in self.world.factions:
            name = faction.get("name", "未知势力")
            desc = faction.get("description", "")
            result.append(f"- {name}: {desc}")
        
        return "\n".join(result)
    
    def get_power_system_context(self) -> str:
        """获取力量体系上下文"""
        if not self.world or not self.world.power_system:
            return "无力量体系设定"
        
        return json.dumps(self.world.power_system, ensure_ascii=False, indent=2)
    
    def check_consistency(self, content: str) -> List[str]:
        """
        检查内容与世界观的一致性
        
        Args:
            content: 待检查的内容
            
        Returns:
            不一致的问题列表
        """
        # 简单实现：检查是否违反世界规则
        issues = []
        
        if self.world and self.world.rules:
            for rule in self.world.rules:
                # 这里可以用LLM来做更智能的检查
                # 简单实现先跳过
                pass
        
        return issues
    
    def _load_world(self) -> None:
        """从文件加载世界观"""
        if not self.project_dir:
            return
        
        # 优先加载worldbuilding.json (与coordinator.py保持一致)
        world_file = self.project_dir / "worldbuilding.json"
        # 向后兼容：如果worldbuilding.json不存在，尝试加载旧的world.json
        if not world_file.exists():
            world_file = self.project_dir / "world.json"
        
        if world_file.exists():
            try:
                data = json.loads(world_file.read_text(encoding="utf-8"))
                # 兼容两种数据格式
                if "world" in data:
                    self.world = WorldSetting(**data["world"])
                elif "name" in data or "world_type" in data:
                    # 直接是WorldSetting格式
                    self.world = WorldSetting(**data)
                self.locations = data.get("locations", {})
                self.items = data.get("items", {})
                self.events = data.get("events", [])
            except Exception as e:
                logger.warning(f"Failed to load world: {e}")
    
    def _save_world(self) -> None:
        """保存世界观到文件"""
        if not self.project_dir:
            return
        
        self.project_dir.mkdir(parents=True, exist_ok=True)
        # 使用worldbuilding.json (与coordinator.py保持一致)
        world_file = self.project_dir / "worldbuilding.json"
        
        data = {
            "world": asdict(self.world) if self.world else None,
            "locations": self.locations,
            "items": self.items,
            "events": self.events
        }
        
        world_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def export_for_llm(self) -> Dict[str, Any]:
        """导出为LLM可用的格式"""
        return {
            "world": asdict(self.world) if self.world else {},
            "locations": self.locations,
            "items": self.items,
            "events": self.events
        }


# 模块职责说明：管理小说世界设定，包括力量体系、地理环境、势力和历史事件。
