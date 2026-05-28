"""
Agent模型配置数据结构和管理器
支持每个Agent独立配置API和模型
支持全局默认API配置（多配置管理）
"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict, field

from .constants import LLM_DEFAULTS, get_app_root, get_data_dir
from .utils.llm_params import normalize_max_tokens
from .utils.atomic_write import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_API_PRESET_ID = "preset-tsc5"
LEGACY_API_PRESET_NAME = "预设接口"
DEFAULT_API_PRESET_NAME = "探索仓API"
DEFAULT_API_PRESET_BASE = "https://api.tsc5.top/v1"
IMAGE_API_FORMATS = {
    "auto",
    "openai_images",
    "qwen_images",
    "gemini_native",
    "responses",
    "chat_completions",
}


def _is_tsc5_api_base(api_base: str) -> bool:
    return "tsc5.top" in str(api_base or "").lower()


def _is_legacy_tsc5_api_base(api_base: str) -> bool:
    return "test.tsc5.top" in str(api_base or "").lower()


def _normalize_versioned_openai_base_url(api_base: str) -> str:
    base_url = str(api_base or "").strip().rstrip("/")
    if not base_url:
        return ""
    last_segment = base_url.rsplit("/", 1)[-1].lower()
    if not re.fullmatch(r"v\d+(\.\d+)?", last_segment):
        base_url = f"{base_url}/v1"
    return base_url


def _normalize_api_base_for_config(api_base: str, *, config_id: str = "") -> str:
    base_url = str(api_base or "").strip()
    if config_id == DEFAULT_API_PRESET_ID and _is_legacy_tsc5_api_base(base_url):
        return DEFAULT_API_PRESET_BASE
    if config_id == DEFAULT_API_PRESET_ID or _is_tsc5_api_base(base_url):
        return _normalize_versioned_openai_base_url(base_url)
    return base_url


def normalize_image_api_format(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "": "auto",
        "images_generations": "openai_images",
        "image_generations": "openai_images",
        "openai_image_generations": "openai_images",
        "openai": "openai_images",
        "qwen": "qwen_images",
        "gemini": "gemini_native",
        "gemini_images": "gemini_native",
        "openai_responses": "responses",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in IMAGE_API_FORMATS else "auto"


def _default_agent_config_dir() -> Path:
    """Return writable config dir, using portable external data when frozen."""
    return get_data_dir()


def _legacy_agent_config_dir() -> Path:
    """Legacy in-package data dir used by older development builds."""
    return Path(__file__).parent / "data"


@dataclass
class APIKeyEntry:
    """单个 API Key 条目，支持同 provider 下多 key 轮询。"""

    id: str = ""
    key: str = ""
    remark: str = ""
    is_enabled: bool = True
    created_at: str = ""

    def __post_init__(self):
        self.id = str(self.id or "").strip() or str(uuid.uuid4())[:8]
        self.key = str(self.key or "").strip()
        self.remark = str(self.remark or "").strip()
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()

    @property
    def preview(self) -> str:
        """返回安全展示用 key preview，不泄漏完整 key。"""
        if not self.key:
            return ""
        return self.key[:8] + "****" if len(self.key) > 8 else "****"

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "remark": self.remark,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at,
            "key_set": bool(self.key),
            "key_preview": self.preview,
        }


def _coerce_api_key_entries(entries: Any) -> List[APIKeyEntry]:
    """兼容从 JSON/Pydantic/dataclass 还原 key entries。"""
    if not entries:
        return []
    coerced: List[APIKeyEntry] = []
    for item in entries:
        if isinstance(item, APIKeyEntry):
            coerced.append(item)
            continue
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        elif hasattr(item, "dict"):
            item = item.dict()
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        if "enabled" in payload and "is_enabled" not in payload:
            payload["is_enabled"] = payload.pop("enabled")
        allowed = {"id", "key", "remark", "is_enabled", "created_at"}
        coerced.append(APIKeyEntry(**{k: v for k, v in payload.items() if k in allowed}))
    return coerced


class APIKeyPoolMixin:
    """Shared helpers for config objects that expose an API key pool."""

    api_key: str
    api_keys: List[APIKeyEntry]

    def normalize_key_pool(self) -> None:
        self.api_key = str(getattr(self, "api_key", "") or "").strip()
        self.api_keys = _coerce_api_key_entries(getattr(self, "api_keys", []))
        if not self.api_keys and self.api_key:
            self.api_keys = [
                APIKeyEntry(
                    id="legacy",
                    key=self.api_key,
                    remark="legacy api_key",
                    is_enabled=True,
                )
            ]
        if self.api_keys and not self.api_key:
            primary = self.get_primary_key()
            if primary:
                self.api_key = primary

    def set_primary_key(self, api_key: str) -> None:
        key = str(api_key or "").strip()
        self.api_key = key
        self.api_keys = _coerce_api_key_entries(getattr(self, "api_keys", []))
        if not key:
            return
        if not self.api_keys:
            self.api_keys = [
                APIKeyEntry(
                    id="legacy",
                    key=key,
                    remark="legacy api_key",
                    is_enabled=True,
                )
            ]
            return
        self.api_keys[0].key = key
        self.api_keys[0].is_enabled = True

    def get_enabled_key_entries(self) -> List[APIKeyEntry]:
        self.api_keys = _coerce_api_key_entries(getattr(self, "api_keys", []))
        return [entry for entry in self.api_keys if entry.is_enabled and entry.key]

    def get_primary_key(self) -> str:
        enabled = self.get_enabled_key_entries()
        if enabled:
            return enabled[0].key
        for entry in self.api_keys:
            if entry.key:
                return entry.key
        return str(getattr(self, "api_key", "") or "").strip()

    def has_auth(self) -> bool:
        return bool(self.get_primary_key())


@dataclass
class APIConfigItem(APIKeyPoolMixin):
    """单个API配置项"""
    id: str = ""
    name: str = ""
    api_base: str = ""
    api_key: str = ""
    api_keys: List[APIKeyEntry] = field(default_factory=list)
    models: List[str] = field(default_factory=list)  # 支持多个模型
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    created_at: str = ""
    api_type: str = "openai_chat"  # 可选值: "openai_chat", "openai_responses", "anthropic"
    image_api_format: str = "auto"
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()
        self.api_base = _normalize_api_base_for_config(self.api_base, config_id=self.id)
        self.image_api_format = normalize_image_api_format(self.image_api_format)
        self.normalize_key_pool()
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.has_auth() and self.models)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（隐藏API Key）"""
        return {
            "id": self.id,
            "name": self.name,
            "api_base": self.api_base,
            "api_key_set": bool(self.api_key),
            "api_key_preview": self.api_key[:8] + "****" if len(self.api_key) > 8 else "",
            "api_keys": [entry.to_public_dict() for entry in self.api_keys],
            "models": self.models,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
            "api_type": self.api_type,
            "image_api_format": self.image_api_format,
        }


@dataclass
class MultiAPIConfig:
    """多API配置管理"""
    configs: List[APIConfigItem] = field(default_factory=list)
    active_config_id: str = ""
    active_model: str = ""
    
    def get_active_config(self) -> Optional[APIConfigItem]:
        """获取当前激活的配置"""
        if not self.active_config_id:
            return self.configs[0] if self.configs else None
        for config in self.configs:
            if config.id == self.active_config_id:
                return config
        return self.configs[0] if self.configs else None
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        active = self.get_active_config()
        return bool(active and active.is_configured() and self.active_model)
    
    def get_effective_model(self) -> str:
        """获取当前有效的模型"""
        active = self.get_active_config()
        if not active:
            return ""
        # 如果active_model在当前配置的模型列表中，返回它
        if self.active_model and self.active_model in active.models:
            return self.active_model
        # 否则返回第一个模型
        return active.models[0] if active.models else ""


@dataclass
class GlobalAPIConfig(APIKeyPoolMixin):
    """全局默认API配置（向后兼容）"""
    api_base: str = ""
    api_key: str = ""
    api_keys: List[APIKeyEntry] = field(default_factory=list)
    model: str = ""
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    api_type: str = "openai_chat"  # 可选值: "openai_chat", "openai_responses", "anthropic"

    def __post_init__(self):
        self.api_base = _normalize_api_base_for_config(self.api_base)
        self.normalize_key_pool()

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.has_auth() and self.model)


@dataclass
class AgentModelConfig(APIKeyPoolMixin):
    """单个Agent的模型配置"""
    agent_name: str = ""
    api_config_id: str = ""
    api_base: str = ""
    api_key: str = ""
    api_keys: List[APIKeyEntry] = field(default_factory=list)
    model: str = ""
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    enabled: bool = True
    description: str = ""
    use_global: bool = True  # 是否使用全局配置
    api_type: str = "openai_chat"  # 可选值: "openai_chat", "openai_responses", "anthropic"

    def __post_init__(self):
        self.api_base = _normalize_api_base_for_config(self.api_base, config_id=self.api_config_id)
        self.normalize_key_pool()

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.has_auth() and self.model)


class AgentConfigManager:
    """
    Agent配置管理器
    管理所有Agent的独立模型配置
    支持全局默认API配置
    """
    
    # 预定义的Agent列表及其描述
    AGENT_DEFINITIONS = {
        "Router": {
            "display_name": "智能路由助手",
            "description": "主 Agent，负责识别用户真实意图、清洗上下文、选择目标助手并生成可执行交接，避免把讨论请求误判为写入任务。",
            "recommended_models": ["gpt-5.4", "gpt-4", "deepseek-chat"],
            "default_temperature": 0.2
        },
        "Communicator": {
            "display_name": "创作沟通助手",
            "description": "专业的需求分析专家，擅长通过结构化对话深入理解用户的创作意图、风格偏好和具体需求。能够识别隐含需求，提出针对性问题，确保收集到完整准确的创作信息。",
            "recommended_models": ["gpt-4", "gpt-3.5-turbo", "deepseek-chat"],
            "default_temperature": 0.8
        },
        "Worldbuilder": {
            "display_name": "世界观设定师",
            "description": "资深的世界观设计专家，精通构建完整、自洽、富有深度的虚构世界。能够设计复杂的社会体系、权力结构、文化背景、历史脉络和独特的世界规则，确保世界观的逻辑性和可扩展性。",
            "recommended_models": ["gpt-4", "claude-3-opus", "claude-3-sonnet"],
            "default_temperature": 0.8
        },
        "Outliner": {
            "display_name": "全书大纲规划师",
            "description": "经验丰富的故事架构师，擅长设计引人入胜的故事结构。能够规划完整的情节线、设置合理的冲突节奏、安排精妙的伏笔铺垫，确保故事的逻辑连贯性和戏剧张力。",
            "recommended_models": ["gpt-4-turbo", "gpt-4", "claude-3-opus"],
            "default_temperature": 0.7
        },
        "ChapterWriter": {
            "display_name": "章节正文写手",
            "description": "专业的内容创作者，精通将大纲转化为生动的章节内容。擅长场景描写、人物刻画、对话设计和情节推进，能够保持风格一致性，创作出引人入胜的章节内容。",
            "recommended_models": ["gpt-4", "claude-3-sonnet", "claude-3-opus"],
            "default_temperature": 0.8
        },
        "Polisher": {
            "display_name": "正文润色师",
            "description": "资深的文字编辑专家，擅长优化文字表达、提升语言质量。能够识别并修正语法错误、改善句式结构、增强文字感染力，同时保持原有风格和意境。",
            "recommended_models": ["gpt-4", "gpt-4-turbo", "claude-3-sonnet"],
            "default_temperature": 0.6
        },
        "Evaluator": {
            "display_name": "质检评估师",
            "description": "严谨的内容审核专家，具备敏锐的逻辑分析能力。能够系统性地检测内容中的逻辑漏洞、情节矛盾、人物行为不一致等问题，并提供详细的改进建议。",
            "recommended_models": ["gpt-4", "gpt-4-turbo", "claude-3-opus"],
            "default_temperature": 0.3
        },
        "ContinuousWriter": {
            "display_name": "无限续写正文写手",
            "description": "富有创造力的长篇创作专家，擅长基于已有内容进行连续性创作。能够保持故事连贯性、维持人物性格一致性、推进情节发展，创作出自然流畅的续写内容。",
            "recommended_models": ["gpt-4", "claude-3-opus", "gemini-pro"],
            "default_temperature": 0.8
        },
        "CharacterBuilder": {
            "display_name": "角色构建师",
            "description": "专业角色设定师，负责根据讨论内容与世界观生成结构化角色卡草稿，适合定义主角、反派与关键配角的人设。",
            "recommended_models": ["gpt-5.4", "gpt-4", "claude-3-opus"],
            "default_temperature": 0.4
        },
        "EventlineBuilder": {
            "display_name": "事件线构建师",
            "description": "负责从大纲与讨论中提炼主线、支线和人物线，生成可追踪的事件线结构。",
            "recommended_models": ["gpt-5.4", "gpt-4", "claude-3-opus"],
            "default_temperature": 0.5
        },
        "DetailOutlineBuilder": {
            "display_name": "细纲构建师",
            "description": "负责把章节大纲进一步细化为场景目标、冲突和推进要点，形成可执行细纲。",
            "recommended_models": ["gpt-5.4", "gpt-4", "claude-3-opus"],
            "default_temperature": 0.5
        },
        "ChapterSettingBuilder": {
            "display_name": "章纲设定师",
            "description": "负责生成章节写作设定卡，包括本章目标、关键事件与结尾钩子。",
            "recommended_models": ["gpt-5.4", "gpt-4", "claude-3-opus"],
            "default_temperature": 0.5
        },
        "ContentExpansion": {
            "display_name": "正文扩写师",
            "description": "高级辅助 Agent，用于在不破坏原意的前提下扩写内容与补足细节。",
            "recommended_models": ["gpt-4", "gpt-4-turbo", "claude-3-sonnet"],
            "default_temperature": 0.7
        },
        "SummaryOrchestrator": {
            "display_name": "摘要编排器",
            "description": "高级辅助 Agent，用于整理、压缩和编排长上下文摘要，适合开发者精调。",
            "recommended_models": ["gpt-4", "gpt-4-turbo", "claude-3-sonnet"],
            "default_temperature": 0.4
        }
    }

    USER_VISIBLE_AGENT_NAMES = {
        "Router",
        "Communicator",
        "Worldbuilder",
        "Outliner",
        "ChapterWriter",
        "Polisher",
        "ContinuousWriter",
        "CharacterBuilder",
        "EventlineBuilder",
        "DetailOutlineBuilder",
        "ChapterSettingBuilder",
    }

    ADVANCED_AGENT_NAMES = {
        "Evaluator",
        "ContentExpansion",
        "SummaryOrchestrator",
    }
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件存储目录
        """
        should_migrate_legacy = config_dir is None
        self.config_dir = Path(config_dir) if config_dir is not None else _default_agent_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "agent_configs.json"
        self.global_config_file = self.config_dir / "global_api_config.json"
        if should_migrate_legacy:
            self._migrate_legacy_config_files()
        global_config_existed = self.global_config_file.exists()
        self.configs: Dict[str, AgentModelConfig] = {}
        self.global_config: GlobalAPIConfig = GlobalAPIConfig()
        self.multi_config: MultiAPIConfig = MultiAPIConfig()
        self._load_configs()
        self._load_global_config()
        self._install_default_api_preset_if_needed(global_config_existed=global_config_existed)

    def _migrate_legacy_config_files(self) -> None:
        """Copy existing config files from the old package data dir when needed."""
        legacy_dir = _legacy_agent_config_dir()
        if legacy_dir.resolve() == self.config_dir.resolve():
            return

        for filename in ("agent_configs.json", "global_api_config.json"):
            target = self.config_dir / filename
            source = legacy_dir / filename
            if target.exists() or not source.exists():
                continue
            try:
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                logger.info("Migrated legacy agent config file to writable data dir: %s", target)
            except Exception as exc:
                logger.warning("Failed to migrate legacy agent config file %s: %s", source, exc)

    @staticmethod
    def _normalize_config_max_tokens(max_tokens: Any, *, source: str) -> int:
        """Normalize persisted max_tokens values to a provider-safe range."""
        return normalize_max_tokens(max_tokens, source=source)
    
    def _load_configs(self) -> None:
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                for name, cfg_data in data.items():
                    # 兼容旧版本配置，添加use_global字段
                    if 'use_global' not in cfg_data:
                        cfg_data['use_global'] = True
                    cfg_data['max_tokens'] = self._normalize_config_max_tokens(
                        cfg_data.get('max_tokens'),
                        source=f"AgentConfig:{name}",
                    )
                    self.configs[name] = AgentModelConfig(**cfg_data)
            except Exception as e:
                logger.warning(f"Failed to load agent configs: {e}")
        
        # 确保所有预定义的Agent都有配置
        for agent_name, definition in self.AGENT_DEFINITIONS.items():
            if agent_name not in self.configs:
                self.configs[agent_name] = AgentModelConfig(
                    agent_name=agent_name,
                    description=definition["description"],
                    temperature=definition.get("default_temperature", 0.7),
                    use_global=True
                )
    
    def _load_global_config(self) -> None:
        """从文件加载全局API配置"""
        if self.global_config_file.exists():
            try:
                data = json.loads(self.global_config_file.read_text(encoding="utf-8"))
                
                # 检查是否是新的多配置格式
                if "configs" in data:
                    # 新格式：多配置
                    configs = []
                    for cfg_data in data.get("configs", []):
                        cfg_data["max_tokens"] = self._normalize_config_max_tokens(
                            cfg_data.get("max_tokens"),
                            source=f"GlobalAPIConfig:{cfg_data.get('name') or 'unnamed'}",
                        )
                        configs.append(APIConfigItem(**cfg_data))
                    self.multi_config = MultiAPIConfig(
                        configs=configs,
                        active_config_id=data.get("active_config_id", ""),
                        active_model=data.get("active_model", "")
                    )
                    preset_changed = self._normalize_builtin_api_preset()
                    # 同时更新兼容的global_config
                    self._sync_global_from_multi()
                    if preset_changed:
                        self._save_global_config()
                else:
                    # 旧格式：单配置（向后兼容）
                    data["max_tokens"] = self._normalize_config_max_tokens(
                        data.get("max_tokens"),
                        source="GlobalAPIConfig:legacy",
                    )
                    self.global_config = GlobalAPIConfig(**data)
                    # 迁移到新格式
                    self._migrate_to_multi_config()
            except Exception as e:
                logger.warning(f"Failed to load global API config: {e}")

    def _normalize_builtin_api_preset(self) -> bool:
        """Keep the built-in relay config label current without overwriting custom values."""
        changed = False
        for config in self.multi_config.configs:
            if config.id == DEFAULT_API_PRESET_ID and config.name in ("", LEGACY_API_PRESET_NAME):
                config.name = DEFAULT_API_PRESET_NAME
                changed = True
            normalized_base = _normalize_api_base_for_config(config.api_base, config_id=config.id)
            if normalized_base != config.api_base:
                config.api_base = normalized_base
                changed = True
        return changed
    
    def _migrate_to_multi_config(self) -> None:
        """将旧的单配置迁移到多配置格式"""
        if self.global_config.is_configured():
            config_item = APIConfigItem(
                name="默认配置",
                api_base=self.global_config.api_base,
                api_key=self.global_config.api_key,
                api_keys=self.global_config.api_keys,
                models=[self.global_config.model] if self.global_config.model else [],
                temperature=self.global_config.temperature,
                max_tokens=self.global_config.max_tokens,
                api_type=self.global_config.api_type,
            )
            self.multi_config = MultiAPIConfig(
                configs=[config_item],
                active_config_id=config_item.id,
                active_model=self.global_config.model
            )
            # 保存新格式
            self._save_global_config()
    
    def _sync_global_from_multi(self) -> None:
        """从多配置同步到兼容的global_config"""
        active = self.multi_config.get_active_config()
        if active:
            self.global_config = GlobalAPIConfig(
                api_base=active.api_base,
                api_key=active.api_key,
                api_keys=active.api_keys,
                model=self.multi_config.get_effective_model(),
                temperature=active.temperature,
                max_tokens=active.max_tokens,
                api_type=active.api_type
            )

    def _install_default_api_preset_if_needed(self, *, global_config_existed: bool) -> None:
        """Create the built-in API preset only for fresh installs."""
        if global_config_existed or self.multi_config.configs:
            return

        preset = APIConfigItem(
            id=DEFAULT_API_PRESET_ID,
            name=DEFAULT_API_PRESET_NAME,
            api_base=DEFAULT_API_PRESET_BASE,
            api_key="",
            api_keys=[],
            models=[],
            temperature=LLM_DEFAULTS.TEMPERATURE,
            max_tokens=LLM_DEFAULTS.MAX_TOKENS,
            api_type="openai_chat",
        )
        self.multi_config = MultiAPIConfig(
            configs=[preset],
            active_config_id=preset.id,
            active_model="",
        )
        self._sync_global_from_multi()
        self._save_global_config()
    
    def _save_configs(self) -> None:
        """保存配置到文件"""
        data = {
            name: asdict(cfg)
            for name, cfg in self.configs.items()
        }
        try:
            old_content = self.config_file.read_text(encoding="utf-8") if self.config_file.exists() else None
            atomic_write_json(
                self.config_file,
                data,
                old_content=old_content,
                ensure_ascii=False,
                indent=2,
            )
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to save agent configs to {self.config_file}: {e}")
            raise
    
    def _save_global_config(self, sync_env: bool = False) -> None:
        """
        保存全局API配置到文件（使用多配置格式）
        
        Args:
            sync_env: 是否同步更新.env文件（仅在应用配置时为True）
        """
        for cfg in self.multi_config.configs:
            cfg.api_base = _normalize_api_base_for_config(cfg.api_base, config_id=cfg.id)
        data = {
            "configs": [asdict(cfg) for cfg in self.multi_config.configs],
            "active_config_id": self.multi_config.active_config_id,
            "active_model": self.multi_config.active_model
        }
        try:
            old_content = self.global_config_file.read_text(encoding="utf-8") if self.global_config_file.exists() else None
            atomic_write_json(
                self.global_config_file,
                data,
                old_content=old_content,
                ensure_ascii=False,
                indent=2,
            )
            # 只在明确指定时才同步.env文件（避免编辑非激活配置时误同步）
            if sync_env:
                self._sync_to_env_file()
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to save global API config to {self.global_config_file}: {e}")
            raise
    
    def get_global_config(self) -> GlobalAPIConfig:
        """获取全局API配置（兼容接口）"""
        self._sync_global_from_multi()
        return self.global_config
    
    def _sync_to_env_file(self) -> None:
        """将当前激活的配置同步到.env文件"""
        try:
            # 获取当前激活的配置
            active = self.multi_config.get_active_config()
            if not active:
                logger.warning("No active config to sync to .env file")
                return
            
            # 获取.env文件路径
            env_path = get_app_root() / ".env"
            
            # 读取现有.env内容
            env_content = {}
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_content[key.strip()] = value.strip()
            
            # 更新API配置相关的环境变量
            env_content["OPENAI_API_BASE"] = active.api_base
            env_content["OPENAI_API_KEY"] = active.get_primary_key()
            env_content["OPENAI_MODEL"] = self.multi_config.get_effective_model()
            
            # 确保其他必要的环境变量存在
            env_content.setdefault("HOST", "0.0.0.0")
            env_content.setdefault("PORT", "8000")
            env_content.setdefault("DEBUG", "false")
            env_content.setdefault("MAX_TOKENS", str(active.max_tokens))
            env_content.setdefault("TEMPERATURE", str(active.temperature))
            
            # 写入.env文件
            lines = [f"{k}={v}" for k, v in env_content.items()]
            env_path.write_text("\n".join(lines), encoding="utf-8")
            
            logger.info(f"Synced active config to .env file: {active.name} ({active.api_base})")
        except Exception as e:
            logger.error(f"Failed to sync config to .env file: {e}")
            # 不抛出异常，避免影响配置保存
    
    def get_multi_config(self) -> MultiAPIConfig:
        """获取多API配置"""
        return self.multi_config
    
    def set_global_config(self, api_base: str = "", api_key: str = "",
                          model: str = "", temperature: float = LLM_DEFAULTS.TEMPERATURE,
                          max_tokens: int = LLM_DEFAULTS.MAX_TOKENS) -> GlobalAPIConfig:
        """设置全局API配置（兼容接口，更新当前激活的配置）"""
        normalized_max_tokens = self._normalize_config_max_tokens(max_tokens, source="GlobalAPIConfig:set")
        active = self.multi_config.get_active_config()
        if active:
            # 更新现有配置
            active.api_base = _normalize_api_base_for_config(api_base, config_id=active.id)
            active.set_primary_key(api_key)
            if model and model not in active.models:
                active.models.append(model)
            active.temperature = temperature
            active.max_tokens = normalized_max_tokens
            self.multi_config.active_model = model
        else:
            # 创建新配置
            config_item = APIConfigItem(
                name="默认配置",
                api_base=api_base,
                api_key=api_key,
                models=[model] if model else [],
                temperature=temperature,
                max_tokens=normalized_max_tokens
            )
            self.multi_config.configs.append(config_item)
            self.multi_config.active_config_id = config_item.id
            self.multi_config.active_model = model
        
        self._sync_global_from_multi()
        self._save_global_config()
        return self.global_config
    
    # ===== 多配置管理方法 =====
    
    def add_api_config(self, name: str, api_base: str, api_key: str,
                       models: List[str], temperature: float = LLM_DEFAULTS.TEMPERATURE,
                       max_tokens: int = LLM_DEFAULTS.MAX_TOKENS,
                       api_type: str = "openai_chat",
                       image_api_format: str = "auto",
                       api_keys: Optional[List[APIKeyEntry]] = None) -> APIConfigItem:
        """添加新的API配置"""
        normalized_max_tokens = self._normalize_config_max_tokens(max_tokens, source=f"APIConfig:add:{name}")
        config_item = APIConfigItem(
            name=name,
            api_base=_normalize_api_base_for_config(api_base),
            api_key=api_key,
            api_keys=api_keys or [],
            models=models,
            temperature=temperature,
            max_tokens=normalized_max_tokens,
            api_type=api_type,
            image_api_format=normalize_image_api_format(image_api_format),
        )
        self.multi_config.configs.append(config_item)
        
        # 如果是第一个配置，自动激活
        if len(self.multi_config.configs) == 1:
            self.multi_config.active_config_id = config_item.id
            if models:
                self.multi_config.active_model = models[0]
        
        self._sync_global_from_multi()
        self._save_global_config()
        return config_item
    
    def update_api_config(self, config_id: str, **kwargs) -> Optional[APIConfigItem]:
        """更新API配置，如果是激活配置则同步到.env"""
        for config in self.multi_config.configs:
            if config.id == config_id:
                for key, value in kwargs.items():
                    if hasattr(config, key):
                        if key == "max_tokens":
                            value = self._normalize_config_max_tokens(
                                value,
                                source=f"APIConfig:update:{config.name or config.id}",
                            )
                        if key == "api_base":
                            value = _normalize_api_base_for_config(value, config_id=config.id)
                        if key == "image_api_format":
                            value = normalize_image_api_format(value)
                        if key == "api_key":
                            config.set_primary_key(value)
                        elif key == "api_keys":
                            config.api_keys = _coerce_api_key_entries(value)
                            config.api_key = config.get_primary_key()
                        else:
                            setattr(config, key, value)
                self._sync_global_from_multi()
                # 如果更新的是当前激活的配置，同步到.env文件
                is_active = (config_id == self.multi_config.active_config_id)
                self._save_global_config(sync_env=is_active)
                return config
        return None
    
    def delete_api_config(self, config_id: str) -> bool:
        """删除API配置"""
        for i, config in enumerate(self.multi_config.configs):
            if config.id == config_id:
                self.multi_config.configs.pop(i)
                # 如果删除的是激活配置，切换到第一个
                if self.multi_config.active_config_id == config_id:
                    if self.multi_config.configs:
                        self.multi_config.active_config_id = self.multi_config.configs[0].id
                        if self.multi_config.configs[0].models:
                            self.multi_config.active_model = self.multi_config.configs[0].models[0]
                    else:
                        self.multi_config.active_config_id = ""
                        self.multi_config.active_model = ""
                self._sync_global_from_multi()
                self._save_global_config()
                return True
        return False
    
    def set_active_config(self, config_id: str, model: str = "") -> bool:
        """设置激活的配置和模型，并同步到.env文件"""
        for config in self.multi_config.configs:
            if config.id == config_id:
                self.multi_config.active_config_id = config_id
                # 验证模型是否在列表中
                if model and model in config.models:
                    self.multi_config.active_model = model
                elif config.models:
                    self.multi_config.active_model = config.models[0]
                else:
                    self.multi_config.active_model = ""
                self._sync_global_from_multi()
                # 应用配置时同步到.env文件
                self._save_global_config(sync_env=True)
                return True
        return False
    
    def add_model_to_config(self, config_id: str, model: str) -> bool:
        """向配置添加模型"""
        for config in self.multi_config.configs:
            if config.id == config_id:
                if model not in config.models:
                    config.models.append(model)
                    self._save_global_config()
                return True
        return False
    
    def remove_model_from_config(self, config_id: str, model: str) -> bool:
        """从配置移除模型"""
        for config in self.multi_config.configs:
            if config.id == config_id:
                if model in config.models:
                    config.models.remove(model)
                    # 如果移除的是当前激活的模型，切换到第一个
                    if self.multi_config.active_model == model:
                        if config.models:
                            self.multi_config.active_model = config.models[0]
                        else:
                            self.multi_config.active_model = ""
                    self._sync_global_from_multi()
                    self._save_global_config()
                return True
        return False
    
    def list_api_configs(self) -> List[Dict[str, Any]]:
        """列出所有API配置"""
        result = []
        for config in self.multi_config.configs:
            config_dict = config.to_dict()
            config_dict["is_active"] = config.id == self.multi_config.active_config_id
            result.append(config_dict)
        return result

    def _get_api_config_by_id(self, config_id: str) -> Optional[APIConfigItem]:
        """根据配置ID查找多API配置项。"""
        target = str(config_id or "").strip()
        if not target:
            return None
        for config in self.multi_config.configs:
            if config.id == target:
                return config
        return None
    
    def get_effective_config(self, agent_name: str) -> AgentModelConfig:
        """
        获取Agent的有效配置
        如果Agent使用全局配置且全局已配置，则返回合并后的配置
        """
        config = self.get_config(agent_name)
        self._sync_global_from_multi()
        global_auth_configured = bool(self.global_config.api_base and self.global_config.has_auth())
        selected_api_config = self._get_api_config_by_id(config.api_config_id) if not config.use_global else None

        # 如果Agent选择使用全局配置，且全局配置已设置
        if config.use_global and global_auth_configured:
            # 全局模型为空时，回退到 Agent 自身模型，避免"测试可用但聊天缺模型/缺Key"
            effective_model = self.global_config.model or config.model
            return AgentModelConfig(
                agent_name=config.agent_name,
                api_config_id=self.multi_config.active_config_id or config.api_config_id,
                api_base=self.global_config.api_base,
                api_key=self.global_config.get_primary_key(),
                api_keys=self.global_config.api_keys,
                model=effective_model,
                temperature=self.global_config.temperature if self.global_config.model else config.temperature,
                max_tokens=self.global_config.max_tokens if self.global_config.model else config.max_tokens,
                enabled=config.enabled,
                description=config.description,
                use_global=True,
                api_type=self.global_config.api_type
            )

        # 独立配置优先按 api_config_id 解析真实 API 配置，避免仅靠 api_base 误匹配。
        if not config.use_global and selected_api_config:
            merged_api_base = selected_api_config.api_base or config.api_base
            merged_api_key = selected_api_config.get_primary_key() or config.get_primary_key()
            merged_api_keys = selected_api_config.api_keys or config.api_keys
            merged_api_type = selected_api_config.api_type or config.api_type

            selected_model = config.model
            if not selected_model:
                selected_model = selected_api_config.models[0] if selected_api_config.models else ""

            if global_auth_configured:
                merged_api_base = merged_api_base or self.global_config.api_base
                merged_api_key = merged_api_key or self.global_config.get_primary_key()
                merged_api_keys = merged_api_keys or self.global_config.api_keys
                selected_model = selected_model or self.global_config.model

            if (
                merged_api_base != config.api_base or
                merged_api_key != config.get_primary_key() or
                selected_model != config.model or
                merged_api_type != config.api_type
            ):
                return AgentModelConfig(
                    agent_name=config.agent_name,
                    api_config_id=config.api_config_id,
                    api_base=merged_api_base,
                    api_key=merged_api_key,
                    api_keys=merged_api_keys,
                    model=selected_model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    enabled=config.enabled,
                    description=config.description,
                    use_global=False,
                    api_type=merged_api_type
                )

        # 独立配置缺失关键字段时，回退使用全局配置补齐缺失值，避免认证失败。
        if not config.use_global and global_auth_configured:
            merged_api_base = config.api_base or self.global_config.api_base
            merged_api_key = config.get_primary_key() or self.global_config.get_primary_key()
            merged_api_keys = config.api_keys or self.global_config.api_keys
            merged_model = config.model or self.global_config.model

            if (
                merged_api_base != config.api_base or
                merged_api_key != config.get_primary_key() or
                merged_model != config.model
            ):
                return AgentModelConfig(
                    agent_name=config.agent_name,
                    api_config_id=config.api_config_id,
                    api_base=merged_api_base,
                    api_key=merged_api_key,
                    api_keys=merged_api_keys,
                    model=merged_model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    enabled=config.enabled,
                    description=config.description,
                    use_global=False,
                    api_type=config.api_type or self.global_config.api_type
                )

        return config
    
    def get_config(self, agent_name: str) -> AgentModelConfig:
        """获取Agent配置"""
        if agent_name not in self.configs:
            definition = self.AGENT_DEFINITIONS.get(agent_name, {})
            self.configs[agent_name] = AgentModelConfig(
                agent_name=agent_name,
                description=definition.get("description", ""),
                temperature=definition.get("default_temperature", 0.7)
            )
        return self.configs[agent_name]
    
    def set_config(self, agent_name: str, config: AgentModelConfig) -> None:
        """设置Agent配置"""
        config.agent_name = agent_name
        self.configs[agent_name] = config
        self._save_configs()
    
    def update_config(self, agent_name: str, **kwargs) -> AgentModelConfig:
        """更新Agent配置的部分字段"""
        config = self.get_config(agent_name)
        for key, value in kwargs.items():
            if hasattr(config, key):
                if key == "max_tokens":
                    value = self._normalize_config_max_tokens(value, source=f"AgentConfig:update:{agent_name}")
                setattr(config, key, value)
        self._save_configs()
        return config
    
    def is_user_visible_agent(self, agent_name: str) -> bool:
        return str(agent_name or "").strip() in self.USER_VISIBLE_AGENT_NAMES

    def is_advanced_agent(self, agent_name: str) -> bool:
        return str(agent_name or "").strip() in self.ADVANCED_AGENT_NAMES

    def list_agents(self, *, include_advanced: bool = False) -> List[Dict]:
        """列出所有Agent及其配置状态"""
        result = []
        global_configured = self.global_config.is_configured()
        
        for agent_name in self.AGENT_DEFINITIONS:
            if not self.is_user_visible_agent(agent_name):
                if not include_advanced or not self.is_advanced_agent(agent_name):
                    continue
            config = self.get_config(agent_name)
            definition = self.AGENT_DEFINITIONS[agent_name]
            
            # 判断是否已配置：使用全局且全局已配置，或者自身已配置
            is_configured = (config.use_global and global_configured) or config.is_configured()
            
            # 显示当前使用的模型
            if config.use_global and global_configured:
                current_model = f"📌 {self.global_config.model}" if self.global_config.model else "(全局未设置模型)"
                api_base = f"📌 {self.global_config.api_base}" if self.global_config.api_base else "(全局未设置)"
            else:
                current_model = config.model or "(未配置)"
                api_base = config.api_base or "(未配置)"
            
            # 获取有效的temperature和max_tokens
            # 注意：temperature和max_tokens可能为0，这是有效值，不能用or判断
            if config.use_global and global_configured:
                effective_temperature = config.temperature if config.temperature is not None else self.global_config.temperature
                effective_max_tokens = config.max_tokens if config.max_tokens is not None else self.global_config.max_tokens
            else:
                effective_temperature = config.temperature
                effective_max_tokens = config.max_tokens
            
            result.append({
                "name": agent_name,
                "display_name": definition.get("display_name", agent_name),
                "description": definition["description"],
                "recommended_models": definition["recommended_models"],
                "is_configured": is_configured,
                "current_model": current_model,
                "model": config.model,  # 新增：原始的 model 字段，用于前端回显
                "api_config_id": config.api_config_id,
                "api_base": config.api_base,  # 修复：使用原始的 api_base，不带前缀
                "api_type": config.api_type,
                "use_global": config.use_global,
                "global_configured": global_configured,
                "temperature": effective_temperature,
                "max_tokens": effective_max_tokens,
                "visibility": "advanced" if self.is_advanced_agent(agent_name) and not self.is_user_visible_agent(agent_name) else "user",
            })
        return result
    
    def copy_config_to_all(self, source_agent: str) -> None:
        """将一个Agent的配置复制到所有Agent"""
        source = self.get_config(source_agent)
        for agent_name in self.AGENT_DEFINITIONS:
            if agent_name != source_agent:
                config = self.get_config(agent_name)
                config.api_config_id = source.api_config_id
                config.api_base = source.api_base
                config.api_key = source.api_key
                config.model = source.model
                config.api_type = source.api_type
        self._save_configs()


# 全局实例
_config_manager: Optional[AgentConfigManager] = None


def get_config_manager() -> AgentConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = AgentConfigManager()
    return _config_manager
