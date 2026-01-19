"""
角色管理器
管理小说中的角色档案
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Character:
    """角色数据结构"""
    name: str
    role: str  # 主角/配角/反派/龙套
    description: str
    personality: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    background: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)
    arc: str = ""  # 角色成长弧线
    first_appearance: int = 0  # 首次出场章节
    status: str = "active"  # active/deceased/missing


class CharacterManager:
    """
    角色管理器
    
    职责：
    1. 管理角色档案的CRUD
    2. 追踪角色关系网络
    3. 记录角色成长变化
    4. 提供角色相关上下文
    """
    
    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = project_dir
        self.characters: Dict[str, Character] = {}
        
        if project_dir:
            self._load_characters()
    
    def add_character(self, character: Character) -> None:
        """添加角色"""
        self.characters[character.name] = character
        self._save_characters()
    
    def get_character(self, name: str) -> Optional[Character]:
        """获取角色"""
        return self.characters.get(name)
    
    def update_character(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新角色信息"""
        if name not in self.characters:
            return False
        
        char = self.characters[name]
        for key, value in updates.items():
            if hasattr(char, key):
                setattr(char, key, value)
        
        self._save_characters()
        return True
    
    def get_all_characters(self) -> List[Character]:
        """获取所有角色"""
        return list(self.characters.values())
    
    def get_characters_by_role(self, role: str) -> List[Character]:
        """按角色类型获取"""
        return [c for c in self.characters.values() if c.role == role]
    
    def get_character_context(self, names: Optional[List[str]] = None) -> str:
        """
        获取角色上下文(用于注入到Agent)
        
        Args:
            names: 指定角色名列表，为空则返回所有
            
        Returns:
            格式化的角色信息字符串
        """
        if names:
            chars = [self.characters[n] for n in names if n in self.characters]
        else:
            chars = list(self.characters.values())
        
        if not chars:
            return "暂无角色档案"
        
        result = []
        for char in chars:
            info = f"""【{char.name}】
- 定位：{char.role}
- 简介：{char.description}
- 性格：{', '.join(char.personality)}
- 能力：{', '.join(char.abilities)}
- 背景：{char.background}
- 成长线：{char.arc}"""
            result.append(info)
        
        return "\n\n".join(result)
    
    def add_relationship(self, char1: str, char2: str, relation: str) -> None:
        """添加角色关系"""
        if char1 in self.characters:
            self.characters[char1].relationships[char2] = relation
        if char2 in self.characters:
            # 添加反向关系描述
            reverse_relation = self._get_reverse_relation(relation)
            self.characters[char2].relationships[char1] = reverse_relation
        
        self._save_characters()
    
    def _get_reverse_relation(self, relation: str) -> str:
        """获取反向关系描述"""
        reverse_map = {
            "父亲": "儿子/女儿",
            "母亲": "儿子/女儿",
            "师傅": "徒弟",
            "徒弟": "师傅",
            "朋友": "朋友",
            "敌人": "敌人",
            "恋人": "恋人",
            "上司": "下属",
            "下属": "上司"
        }
        return reverse_map.get(relation, f"{relation}的对象")
    
    def _load_characters(self) -> None:
        """从文件加载角色"""
        if not self.project_dir:
            return
        
        char_file = self.project_dir / "characters.json"
        if char_file.exists():
            try:
                data = json.loads(char_file.read_text(encoding="utf-8"))
                for name, char_data in data.items():
                    self.characters[name] = Character(**char_data)
            except Exception as e:
                logger.warning(f"Failed to load characters: {e}")
    
    def _save_characters(self) -> None:
        """保存角色到文件"""
        if not self.project_dir:
            return
        
        self.project_dir.mkdir(parents=True, exist_ok=True)
        char_file = self.project_dir / "characters.json"
        
        data = {
            name: asdict(char)
            for name, char in self.characters.items()
        }
        
        char_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def export_for_llm(self) -> List[Dict[str, Any]]:
        """导出为LLM可用的格式"""
        return [asdict(char) for char in self.characters.values()]


# 模块职责说明：管理小说角色档案，包括角色CRUD、关系网络追踪和角色上下文提供。
