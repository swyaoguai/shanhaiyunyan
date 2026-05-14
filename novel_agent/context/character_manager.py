"""
角色管理器
管理小说中的角色档案
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class Character:
    """角色数据结构"""
    name: str
    role: str  # 主角/配角/反派/龙套
    description: str
    age: str = ""
    gender: str = ""
    identity: str = ""
    occupation: str = ""
    appearance: str = ""
    personality: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    inventory: List[str] = field(default_factory=list)
    development_history: List[Dict[str, Any]] = field(default_factory=list)
    background: str = ""
    motivation: str = ""
    goals: List[str] = field(default_factory=list)
    habits: List[str] = field(default_factory=list)
    speaking_style: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)
    arc: str = ""  # 角色成长弧线
    notes: str = ""
    tags: List[str] = field(default_factory=list)
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

    def sync_development_from_text(self, content: str, chapter_number: int = 0) -> Dict[str, List[str]]:
        """从章节正文中同步明确写出的角色成长事件。"""
        text = str(content or "").strip()
        if not text or not self.characters:
            return {}

        updates: Dict[str, List[str]] = {}
        changed = False
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()]
        names = sorted(self.characters.keys(), key=len, reverse=True)
        trigger_pattern = re.compile(r"(学会了?|习得了?|掌握了?|领悟了?|练成了?|觉醒了?|获得了?|参透了?|突破了?)")

        for sentence in sentences:
            if not trigger_pattern.search(sentence):
                continue
            matched_names = [name for name in names if name and name in sentence]
            if not matched_names:
                continue
            ability = self._extract_ability_name_from_sentence(sentence)
            if not ability:
                continue
            for name in matched_names:
                character = self.characters.get(name)
                if not character:
                    continue
                if ability not in character.abilities:
                    character.abilities.append(ability)
                    updates.setdefault(name, []).append(ability)
                    changed = True
                note = f"第{chapter_number}章获得/掌握：{ability}" if chapter_number else f"获得/掌握：{ability}"
                if note not in character.notes:
                    character.notes = (character.notes + "\n" + note).strip() if character.notes else note
                    changed = True
                if self._append_development_event(
                    character,
                    {
                        "chapter_number": chapter_number,
                        "event_type": "ability",
                        "title": ability,
                        "description": note,
                    },
                ):
                    changed = True

        item_updates = self._sync_inventory_from_text(text, chapter_number=chapter_number)
        if item_updates:
            changed = True

        if changed:
            self._save_characters()
        return updates

    def _sync_inventory_from_text(self, content: str, chapter_number: int = 0) -> Dict[str, List[str]]:
        """从正文中同步明确写出的角色持有物/道具事件。"""
        if not content or not self.characters:
            return {}

        updates: Dict[str, List[str]] = {}
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", content) if item.strip()]
        names = sorted(self.characters.keys(), key=len, reverse=True)
        trigger_pattern = re.compile(r"(?:获得了?|得到了?|拿到了?|拾得|夺得|持有|佩戴|装备|带着|握住)")

        for sentence in sentences:
            if not trigger_pattern.search(sentence):
                continue
            matched_names = [name for name in names if name and name in sentence]
            if not matched_names:
                continue
            item_name = self._extract_item_name_from_sentence(sentence)
            if not item_name:
                continue
            for name in matched_names:
                character = self.characters.get(name)
                if not character:
                    continue
                if item_name not in character.inventory:
                    character.inventory.append(item_name)
                    updates.setdefault(name, []).append(item_name)
                note = f"第{chapter_number}章获得/持有：{item_name}" if chapter_number else f"获得/持有：{item_name}"
                if self._append_development_event(
                    character,
                    {
                        "chapter_number": chapter_number,
                        "event_type": "item",
                        "title": item_name,
                        "description": note,
                    },
                ):
                    updates.setdefault(name, [])
        return updates

    @staticmethod
    def _extract_ability_name_from_sentence(sentence: str) -> str:
        text = str(sentence or "")
        trigger = re.search(r"(?:学会了?|习得了?|掌握了?|领悟了?|练成了?|觉醒了?|获得了?|参透了?|突破了?)", text)
        if not trigger:
            return ""
        tail = text[trigger.end():]
        tail = re.sub(r"^[的了一门一种一招新的\s，,：:]+", "", tail)
        suffix_pattern = (
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,16}?"
            r"(?:剑法|刀法|枪法|拳法|掌法|心法|功法|身法|步法|阵法|符法|术法|法术|秘术|神通|天赋|能力|技能|术|诀|法|剑|刀|拳|掌|步|咒|符))"
        )
        match = re.search(suffix_pattern, tail)
        if match:
            return match.group(1).strip("，,。；;、 的了")
        fallback = re.split(r"[，,。；;、\s]", tail, maxsplit=1)[0].strip("的了")
        return fallback[:16] if len(fallback) >= 2 else ""

    @staticmethod
    def _extract_item_name_from_sentence(sentence: str) -> str:
        text = str(sentence or "")
        trigger = re.search(r"(?:获得了?|得到了?|拿到了?|拾得|夺得|持有|佩戴|装备|带着|握住)", text)
        if not trigger:
            return ""
        tail = text[trigger.end():]
        tail = re.sub(r"^[的了一件一枚一把一柄一个一只新的\s，,：:]+", "", tail)
        suffix_pattern = (
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,18}?"
            r"(?:剑|刀|枪|弓|令|令牌|玉佩|玉簪|簪|戒|戒指|珠|丹|符|符箓|印|书|卷|卷轴|甲|衣|袍|冠|钥匙|匣|盒|镜|灯|铃|鼎|炉|药|器|法宝|装备|道具))"
        )
        match = re.search(suffix_pattern, tail)
        if match:
            return match.group(1).strip("，,。；;、 的了")
        return ""

    @staticmethod
    def _append_development_event(character: Character, event: Dict[str, Any]) -> bool:
        title = str(event.get("title") or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        chapter_number = CharacterManager._safe_int(event.get("chapter_number"), 0)
        if not title:
            return False
        for existing in character.development_history:
            if not isinstance(existing, dict):
                continue
            if (
                str(existing.get("title") or "").strip() == title
                and str(existing.get("event_type") or "").strip() == event_type
                and CharacterManager._safe_int(existing.get("chapter_number"), 0) == chapter_number
            ):
                return False
        character.development_history.append({
            "chapter_number": chapter_number,
            "event_type": event_type or "note",
            "title": title,
            "description": str(event.get("description") or title).strip(),
        })
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
            personality = "、".join(char.personality[:5]) if char.personality else "未设定"
            goals = "、".join(char.goals[:3]) if char.goals else "未设定"
            relationships = (
                "、".join(f"{name}({relation})" for name, relation in list(char.relationships.items())[:4])
                if char.relationships else
                "未设定"
            )
            abilities = "、".join(char.abilities[:6]) if char.abilities else "未设定"
            inventory = "、".join(char.inventory[:6]) if char.inventory else "未设定"
            latest_growth = "未记录"
            if char.development_history:
                latest_items = []
                for event in char.development_history[-3:]:
                    if not isinstance(event, dict):
                        continue
                    chapter = self._safe_int(event.get("chapter_number"), 0)
                    title = str(event.get("title") or "").strip()
                    if title:
                        latest_items.append(f"第{chapter}章 {title}" if chapter else title)
                if latest_items:
                    latest_growth = "、".join(latest_items)
            status_tag = f"\n- 状态：{char.status}" if char.status != "active" else ""
            info = f"""【{char.name}】
- 定位：{char.role}
- 身份：{char.identity or char.occupation or "未设定"}
- 简介：{char.description}
- 性格：{personality}
- 技能/能力：{abilities}
- 持有物：{inventory}
- 目标：{goals}
- 关系：{relationships}
- 近期成长：{latest_growth}
- 成长线：{char.arc}{status_tag}"""
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
                normalized = self._normalize_character_payload(data)
                for name, char_data in normalized.items():
                    self.characters[name] = Character(**char_data)
            except Exception as e:
                logger.warning(f"Failed to load characters: {e}")

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _split_text_list(value: Any) -> List[str]:
        """将字符串或列表统一为字符串列表。"""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,，、/|\n]+", value) if part.strip()]
        return []

    @staticmethod
    def _normalize_relationships(value: Any) -> Dict[str, str]:
        """统一关系字段格式。"""
        if isinstance(value, dict):
            return {
                str(name).strip(): str(relation).strip()
                for name, relation in value.items()
                if str(name).strip() and str(relation).strip()
            }
        if isinstance(value, list):
            result: Dict[str, str] = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                target = str(item.get("target") or item.get("name") or "").strip()
                relation = str(item.get("relation") or item.get("description") or "").strip()
                if target and relation:
                    result[target] = relation
            return result
        if isinstance(value, str):
            result: Dict[str, str] = {}
            for line in value.splitlines():
                text = str(line).strip()
                if not text:
                    continue
                if "：" in text:
                    target, relation = text.split("：", 1)
                elif ":" in text:
                    target, relation = text.split(":", 1)
                else:
                    continue
                target = target.strip()
                relation = relation.strip()
                if target and relation:
                    result[target] = relation
            return result
        return {}

    @staticmethod
    def _normalize_development_history(value: Any) -> List[Dict[str, Any]]:
        """统一角色成长记录格式。"""
        result: List[Dict[str, Any]] = []

        def add_event(raw: Any) -> None:
            if isinstance(raw, dict):
                title = str(raw.get("title") or raw.get("name") or raw.get("event") or "").strip()
                description = str(raw.get("description") or raw.get("detail") or raw.get("notes") or title).strip()
                if not title and description:
                    title = description[:40]
                if not title:
                    return
                result.append({
                    "chapter_number": CharacterManager._safe_int(raw.get("chapter_number") or raw.get("chapter"), 0),
                    "event_type": str(raw.get("event_type") or raw.get("type") or "note").strip() or "note",
                    "title": title,
                    "description": description,
                })
                return
            text = str(raw or "").strip()
            if text:
                result.append({
                    "chapter_number": 0,
                    "event_type": "note",
                    "title": text[:40],
                    "description": text,
                })

        if isinstance(value, list):
            for item in value:
                add_event(item)
        elif isinstance(value, str):
            for line in value.splitlines():
                add_event(line)
        return result

    def _coerce_character_data(self, raw: Any, fallback_name: str = "") -> Optional[Dict[str, Any]]:
        """兼容旧版列表结构并标准化角色数据。"""
        if not isinstance(raw, dict):
            return None

        name = str(raw.get("name") or raw.get("title") or fallback_name).strip()
        if not name:
            return None

        description = str(raw.get("description") or raw.get("content") or "").strip()
        role = str(raw.get("role") or raw.get("type") or "未分类").strip() or "未分类"

        return {
            "name": name,
            "role": role,
            "description": description,
            "age": str(raw.get("age") or "").strip(),
            "gender": str(raw.get("gender") or "").strip(),
            "identity": str(raw.get("identity") or raw.get("position") or raw.get("identity_label") or "").strip(),
            "occupation": str(raw.get("occupation") or raw.get("profession") or raw.get("job") or "").strip(),
            "appearance": str(raw.get("appearance") or raw.get("look") or "").strip(),
            "personality": self._split_text_list(raw.get("personality") or raw.get("traits")),
            "abilities": self._split_text_list(raw.get("abilities") or raw.get("skills") or raw.get("skillset")),
            "inventory": self._split_text_list(
                raw.get("inventory")
                or raw.get("item_refs")
                or raw.get("items")
                or raw.get("possessions")
            ),
            "development_history": self._normalize_development_history(
                raw.get("development_history")
                or raw.get("growth_history")
                or raw.get("growth_stages")
                or raw.get("development")
            ),
            "background": str(raw.get("background") or "").strip(),
            "motivation": str(raw.get("motivation") or raw.get("drive") or "").strip(),
            "goals": self._split_text_list(raw.get("goals") or raw.get("goal")),
            "habits": self._split_text_list(raw.get("habits") or raw.get("habit")),
            "speaking_style": str(raw.get("speaking_style") or raw.get("speech_style") or "").strip(),
            "relationships": self._normalize_relationships(raw.get("relationships")),
            "arc": str(raw.get("arc") or "").strip(),
            "notes": str(raw.get("notes") or raw.get("details") or "").strip(),
            "tags": self._split_text_list(raw.get("tags")),
            "first_appearance": self._safe_int(raw.get("first_appearance"), 0),
            "status": str(raw.get("status") or "active").strip() or "active",
        }

    def _normalize_character_payload(self, data: Any) -> Dict[str, Dict[str, Any]]:
        """兼容 dict/list 两种角色存储结构。"""
        normalized: Dict[str, Dict[str, Any]] = {}

        payload = data.get("characters") if isinstance(data, dict) and "characters" in data else data

        if isinstance(payload, dict):
            for name, raw in payload.items():
                char_data = self._coerce_character_data(raw, fallback_name=str(name))
                if char_data:
                    normalized[char_data["name"]] = char_data
            return normalized

        if isinstance(payload, list):
            for raw in payload:
                char_data = self._coerce_character_data(raw)
                if char_data:
                    normalized[char_data["name"]] = char_data
            return normalized

        raise ValueError("Unsupported characters payload format")
    
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
        
        atomic_write_json(char_file, data)
    
    def export_for_llm(self) -> List[Dict[str, Any]]:
        """导出为LLM可用的格式"""
        return [asdict(char) for char in self.characters.values()]


# 模块职责说明：管理小说角色档案，包括角色CRUD、关系网络追踪和角色上下文提供。
