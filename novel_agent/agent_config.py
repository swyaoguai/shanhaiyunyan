"""
Agent模型配置数据结构和管理器
支持每个Agent独立配置API和模型
支持全局默认API配置（多配置管理）
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict, field

from .constants import LLM_DEFAULTS

logger = logging.getLogger(__name__)


@dataclass
class APIConfigItem:
    """单个API配置项"""
    id: str = ""
    name: str = ""
    api_base: str = ""
    api_key: str = ""
    models: List[str] = field(default_factory=list)  # 支持多个模型
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    created_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.api_key and self.models)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（隐藏API Key）"""
        return {
            "id": self.id,
            "name": self.name,
            "api_base": self.api_base,
            "api_key_set": bool(self.api_key),
            "api_key_preview": self.api_key[:8] + "****" if len(self.api_key) > 8 else "",
            "models": self.models,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at
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
class GlobalAPIConfig:
    """全局默认API配置（向后兼容）"""
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.api_key and self.model)


@dataclass
class AgentModelConfig:
    """单个Agent的模型配置"""
    agent_name: str
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS
    enabled: bool = True
    description: str = ""
    use_global: bool = True  # 是否使用全局配置
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_base and self.api_key and self.model)


class AgentConfigManager:
    """
    Agent配置管理器
    管理所有Agent的独立模型配置
    支持全局默认API配置
    """
    
    # 预定义的Agent列表及其描述
    AGENT_DEFINITIONS = {
        "Communicator": {
            "display_name": "沟通助手",
            "description": "与用户对话收集创作需求",
            "recommended_models": ["gpt-3.5-turbo", "deepseek-chat"],
            "default_temperature": 0.8
        },
        "Worldbuilder": {
            "display_name": "世界观构建",
            "description": "构建小说的世界设定",
            "recommended_models": ["gpt-4", "claude-3-opus"],
            "default_temperature": 0.8
        },
        "Outliner": {
            "display_name": "大纲规划",
            "description": "规划故事结构和章节大纲",
            "recommended_models": ["gpt-4-turbo", "gpt-4"],
            "default_temperature": 0.7
        },
        "ChapterWriter": {
            "display_name": "章节撰写",
            "description": "根据大纲生成章节内容",
            "recommended_models": ["gpt-4", "claude-3-sonnet"],
            "default_temperature": 0.8
        },
        "Polisher": {
            "display_name": "文字润色",
            "description": "优化文字质量和表达",
            "recommended_models": ["gpt-4", "gpt-3.5-turbo"],
            "default_temperature": 0.6
        },
        "Evaluator": {
            "display_name": "质量评估",
            "description": "检测内容质量和逻辑问题",
            "recommended_models": ["gpt-4", "gpt-4-turbo"],
            "default_temperature": 0.3
        },
        "ContinuousWriter": {
            "display_name": "无限续写",
            "description": "根据故事开头或灵感进行连续创作",
            "recommended_models": ["gpt-4", "claude-3-opus", "gemini-pro"],
            "default_temperature": 0.8
        }
    }
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件存储目录
        """
        self.config_dir = config_dir or Path(__file__).parent / "data"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "agent_configs.json"
        self.global_config_file = self.config_dir / "global_api_config.json"
        self.configs: Dict[str, AgentModelConfig] = {}
        self.global_config: GlobalAPIConfig = GlobalAPIConfig()
        self.multi_config: MultiAPIConfig = MultiAPIConfig()
        self._load_configs()
        self._load_global_config()
    
    def _load_configs(self) -> None:
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                for name, cfg_data in data.items():
                    # 兼容旧版本配置，添加use_global字段
                    if 'use_global' not in cfg_data:
                        cfg_data['use_global'] = True
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
                        configs.append(APIConfigItem(**cfg_data))
                    self.multi_config = MultiAPIConfig(
                        configs=configs,
                        active_config_id=data.get("active_config_id", ""),
                        active_model=data.get("active_model", "")
                    )
                    # 同时更新兼容的global_config
                    self._sync_global_from_multi()
                else:
                    # 旧格式：单配置（向后兼容）
                    self.global_config = GlobalAPIConfig(**data)
                    # 迁移到新格式
                    self._migrate_to_multi_config()
            except Exception as e:
                logger.warning(f"Failed to load global API config: {e}")
    
    def _migrate_to_multi_config(self) -> None:
        """将旧的单配置迁移到多配置格式"""
        if self.global_config.is_configured():
            config_item = APIConfigItem(
                name="默认配置",
                api_base=self.global_config.api_base,
                api_key=self.global_config.api_key,
                models=[self.global_config.model] if self.global_config.model else [],
                temperature=self.global_config.temperature,
                max_tokens=self.global_config.max_tokens
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
                model=self.multi_config.get_effective_model(),
                temperature=active.temperature,
                max_tokens=active.max_tokens
            )
    
    def _save_configs(self) -> None:
        """保存配置到文件"""
        data = {
            name: asdict(cfg)
            for name, cfg in self.configs.items()
        }
        try:
            self.config_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to save agent configs to {self.config_file}: {e}")
            raise
    
    def _save_global_config(self) -> None:
        """保存全局API配置到文件（使用多配置格式）"""
        data = {
            "configs": [asdict(cfg) for cfg in self.multi_config.configs],
            "active_config_id": self.multi_config.active_config_id,
            "active_model": self.multi_config.active_model
        }
        try:
            self.global_config_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to save global API config to {self.global_config_file}: {e}")
            raise
    
    def get_global_config(self) -> GlobalAPIConfig:
        """获取全局API配置（兼容接口）"""
        self._sync_global_from_multi()
        return self.global_config
    
    def get_multi_config(self) -> MultiAPIConfig:
        """获取多API配置"""
        return self.multi_config
    
    def set_global_config(self, api_base: str = "", api_key: str = "",
                          model: str = "", temperature: float = LLM_DEFAULTS.TEMPERATURE,
                          max_tokens: int = LLM_DEFAULTS.MAX_TOKENS) -> GlobalAPIConfig:
        """设置全局API配置（兼容接口，更新当前激活的配置）"""
        active = self.multi_config.get_active_config()
        if active:
            # 更新现有配置
            active.api_base = api_base
            active.api_key = api_key
            if model and model not in active.models:
                active.models.append(model)
            active.temperature = temperature
            active.max_tokens = max_tokens
            self.multi_config.active_model = model
        else:
            # 创建新配置
            config_item = APIConfigItem(
                name="默认配置",
                api_base=api_base,
                api_key=api_key,
                models=[model] if model else [],
                temperature=temperature,
                max_tokens=max_tokens
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
                       max_tokens: int = LLM_DEFAULTS.MAX_TOKENS) -> APIConfigItem:
        """添加新的API配置"""
        config_item = APIConfigItem(
            name=name,
            api_base=api_base,
            api_key=api_key,
            models=models,
            temperature=temperature,
            max_tokens=max_tokens
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
        """更新API配置"""
        for config in self.multi_config.configs:
            if config.id == config_id:
                for key, value in kwargs.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                self._sync_global_from_multi()
                self._save_global_config()
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
        """设置激活的配置和模型"""
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
                self._save_global_config()
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
    
    def get_effective_config(self, agent_name: str) -> AgentModelConfig:
        """
        获取Agent的有效配置
        如果Agent使用全局配置且全局已配置，则返回合并后的配置
        """
        config = self.get_config(agent_name)
        
        # 如果Agent选择使用全局配置，且全局配置已设置
        if config.use_global and self.global_config.is_configured():
            # 创建一个新的配置，使用全局配置的API信息
            # 使用配置的值，如果Agent配置使用全局配置则使用全局值
            effective_temperature = config.temperature if not config.use_global else self.global_config.temperature
            effective_max_tokens = config.max_tokens if not config.use_global else self.global_config.max_tokens
            
            return AgentModelConfig(
                agent_name=config.agent_name,
                api_base=self.global_config.api_base,
                api_key=self.global_config.api_key,
                model=self.global_config.model,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                enabled=config.enabled,
                description=config.description,
                use_global=True
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
                setattr(config, key, value)
        self._save_configs()
        return config
    
    def list_agents(self) -> List[Dict]:
        """列出所有Agent及其配置状态"""
        result = []
        global_configured = self.global_config.is_configured()
        
        for agent_name in self.AGENT_DEFINITIONS:
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
                "api_base": config.api_base,  # 修复：使用原始的 api_base，不带前缀
                "use_global": config.use_global,
                "global_configured": global_configured,
                "temperature": effective_temperature,
                "max_tokens": effective_max_tokens
            })
        return result
    
    def copy_config_to_all(self, source_agent: str) -> None:
        """将一个Agent的配置复制到所有Agent"""
        source = self.get_config(source_agent)
        for agent_name in self.AGENT_DEFINITIONS:
            if agent_name != source_agent:
                config = self.get_config(agent_name)
                config.api_base = source.api_base
                config.api_key = source.api_key
                config.model = source.model
        self._save_configs()


# 全局实例
_config_manager: Optional[AgentConfigManager] = None


def get_config_manager() -> AgentConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = AgentConfigManager()
    return _config_manager
