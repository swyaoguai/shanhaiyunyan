"""
世界观管理器
管理小说的世界设定
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..utils.atomic_write import atomic_write_json

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

    def ensure_loaded(self) -> bool:
        """
        如果内存中未持有世界观但磁盘上已经有 worldbuilding.json，
        则尝试重新加载一次；返回最终是否持有世界观。

        用于防御某些执行路径只落盘没有同步内存态的情况。
        """
        if self.world is not None:
            return True
        if not self.project_dir:
            return False
        try:
            self._load_world()
        except Exception as exc:
            logger.warning(f"[WorldManager] ensure_loaded 失败: {exc}")
            return False
        return self.world is not None

    def apply_payload(self, data: Any) -> bool:
        """
        从任意世界观载荷（dict / list / {'world': ...} / {'raw_content': ...}）
        重建内存态。返回是否成功构建出 WorldSetting。
        """
        try:
            self._apply_world_payload(data)
        except Exception as exc:
            logger.warning(f"[WorldManager] apply_payload 失败: {exc}")
            return False
        return self.world is not None

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

    def get_world_context(self, compact: bool = True) -> str:
        """
        获取世界观上下文(用于注入到Agent)

        Returns:
            格式化的世界观信息
        """
        if not self.world:
            return "暂无世界观设定"

        if compact:
            rules = self.world.rules[:3] if self.world.rules else []
            factions = self.world.factions[:2] if self.world.factions else []
            lines = [
                f"【世界】{self.world.name}",
                f"- 类型：{self.world.world_type}",
            ]
            if self.world.power_system:
                lines.append(f"- 力量体系：{self._compact_value(self.world.power_system)}")
            if self.world.geography:
                lines.append(f"- 地理环境：{self._compact_value(self.world.geography)}")
            if factions:
                faction_text = "；".join(
                    f"{str(item.get('name') or '势力').strip()}：{str(item.get('description') or '').strip()}"
                    for item in factions if isinstance(item, dict)
                )
                lines.append(f"- 主要势力：{faction_text}")
            if rules:
                lines.append(f"- 核心规则：{'；'.join(str(rule).strip() for rule in rules if str(rule).strip())}")
            return "\n".join(lines)

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

    @staticmethod
    def _compact_value(value: Any, max_len: int = 80) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.strip()
        else:
            text = json.dumps(value, ensure_ascii=False)
        return text[:max_len] + ("..." if len(text) > max_len else "")

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
                self._apply_world_payload(data)
            except Exception as e:
                logger.warning(f"Failed to load world: {e}")

    @staticmethod
    def _coerce_world_setting(raw: Any) -> Optional[WorldSetting]:
        """标准化世界观主结构。"""
        if not isinstance(raw, dict):
            return None

        if set(raw.keys()) == {"raw_content"}:
            raw_content = str(raw.get("raw_content") or "").strip()
            if raw_content:
                return WorldSetting(
                    name="世界观设定",
                    world_type="条目式设定",
                    rules=[],
                    magic_system=raw_content,
                )

        if "name" not in raw and "world_name" not in raw and "world_type" not in raw:
            return None

        return WorldSetting(
            name=str(raw.get("name") or raw.get("world_name") or "未命名世界").strip() or "未命名世界",
            world_type=str(raw.get("world_type") or "通用").strip() or "通用",
            power_system=raw.get("power_system") if isinstance(raw.get("power_system"), dict) else {},
            geography=raw.get("geography") if isinstance(raw.get("geography"), dict) else {},
            history=raw.get("history") if isinstance(raw.get("history"), list) else [],
            factions=raw.get("factions") if isinstance(raw.get("factions"), list) else [],
            rules=[str(rule).strip() for rule in raw.get("rules", []) if str(rule).strip()] if isinstance(raw.get("rules"), list) else [],
            culture=raw.get("culture") if isinstance(raw.get("culture"), dict) else {},
            technology_level=str(raw.get("technology_level") or "").strip(),
            magic_system=str(raw.get("magic_system") or "").strip(),
            timeline=str(raw.get("timeline") or "").strip(),
        )

    @staticmethod
    def _build_world_from_rows(rows: List[Any]) -> Optional[WorldSetting]:
        """将前端保存的条目式世界设定转换为兼容结构。"""
        normalized_rules: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("title") or "").strip()
            description = str(row.get("description") or row.get("content") or "").strip()
            text = "：".join(part for part in [name, description] if part)
            if text:
                normalized_rules.append(text)

        if not normalized_rules:
            return None

        return WorldSetting(
            name="项目世界观",
            world_type="条目式设定",
            rules=normalized_rules,
        )

    def _apply_world_payload(self, data: Any) -> None:
        """兼容多种世界观存储结构。"""
        self.world = None
        self.locations = {}
        self.items = {}
        self.events = []

        if isinstance(data, list):
            self.world = self._build_world_from_rows(data)
            return

        if not isinstance(data, dict):
            raise ValueError("Unsupported world payload format")

        world_data = data.get("world", data)
        if isinstance(world_data, list):
            self.world = self._build_world_from_rows(world_data)
        else:
            self.world = self._coerce_world_setting(world_data)
            if self.world is None and world_data:
                logger.warning(f"[WorldManager] 无法识别的世界观数据结构，已跳过: keys={list(world_data.keys()) if isinstance(world_data, dict) else type(world_data)}")

        self.locations = data.get("locations", {}) if isinstance(data.get("locations"), dict) else {}
        self.items = data.get("items", {}) if isinstance(data.get("items"), dict) else {}
        self.events = data.get("events", []) if isinstance(data.get("events"), list) else []

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

        atomic_write_json(world_file, data)

    def export_for_llm(self) -> Dict[str, Any]:
        """导出为LLM可用的格式"""
        return {
            "world": asdict(self.world) if self.world else {},
            "locations": self.locations,
            "items": self.items,
            "events": self.events
        }


# 模块职责说明：管理小说世界设定，包括力量体系、地理环境、势力和历史事件。
