"""
Letta 服务模块 (Stub)

这是一个 Letta 服务的 stub 实现，用于在 Letta 不可用时提供兼容接口。
当实际的 Letta 服务配置后，此模块将被替换为真正的实现。

模块职责说明：提供 Letta Agent 服务的接口封装，支持记忆管理和消息发送。
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LettaAgentConfig:
    """Letta Agent 配置"""
    name: str
    persona: str = ""
    human: str = ""
    model: str = "gpt-4"
    embedding_model: str = "text-embedding-ada-002"
    memory_human: str = ""
    memory_persona: str = ""
    memory_blocks: Dict[str, str] = field(default_factory=dict)


class LettaService:
    """
    Letta 服务封装
    
    这是一个 stub 实现，当 Letta 未配置或不可用时使用。
    提供基本的接口兼容性，但不执行实际的 Letta 操作。
    """
    
    def __init__(self, base_url: str = "", api_key: str = ""):
        """
        初始化 Letta 服务
        
        Args:
            base_url: Letta 服务器 URL
            api_key: API 密钥
        """
        self.base_url = base_url
        self.api_key = api_key
        self._is_available = False
        self._agents: Dict[str, Dict[str, Any]] = {}
        
        # 检查是否可用
        if base_url and api_key:
            self._check_availability()
    
    def _check_availability(self) -> None:
        """检查 Letta 服务是否可用"""
        # 在 stub 实现中，始终返回不可用
        self._is_available = False
        logger.info("Letta service is running in stub mode (not connected)")
    
    @property
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._is_available
    
    async def create_agent(
        self,
        name: str,
        config: Optional[LettaAgentConfig] = None
    ) -> Optional[str]:
        """
        创建 Letta Agent
        
        Args:
            name: Agent 名称
            config: Agent 配置
            
        Returns:
            Agent ID，如果创建失败返回 None
        """
        if not self._is_available:
            logger.warning(f"Letta not available, cannot create agent: {name}")
            return None
        
        # Stub 实现：返回一个假的 ID
        agent_id = f"stub_{name}_{id(config)}"
        self._agents[agent_id] = {
            "name": name,
            "config": config,
            "memory": {}
        }
        return agent_id
    
    async def delete_agent(self, agent_id: str) -> bool:
        """
        删除 Letta Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否删除成功
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False
    
    async def send_message(
        self,
        agent_id: str,
        message: str,
        role: str = "user"
    ) -> Optional[str]:
        """
        发送消息给 Letta Agent
        
        Args:
            agent_id: Agent ID
            message: 消息内容
            role: 发送者角色
            
        Returns:
            Agent 回复，如果失败返回 None
        """
        if not self._is_available:
            logger.warning(f"Letta not available, cannot send message to agent: {agent_id}")
            return None
        
        # Stub 实现：返回一个简单的回复
        return f"[Stub Reply] Message received: {message[:50]}..."
    
    async def get_memory(self, agent_id: str) -> Dict[str, str]:
        """
        获取 Agent 的记忆
        
        Args:
            agent_id: Agent ID
            
        Returns:
            记忆字典
        """
        if agent_id in self._agents:
            return self._agents[agent_id].get("memory", {})
        return {}
    
    async def update_memory(
        self,
        agent_id: str,
        block_name: str,
        content: str
    ) -> bool:
        """
        更新 Agent 的记忆块
        
        Args:
            agent_id: Agent ID
            block_name: 记忆块名称
            content: 记忆内容
            
        Returns:
            是否更新成功
        """
        if not self._is_available:
            logger.warning(f"Letta not available, cannot update memory for agent: {agent_id}")
            return False
        
        if agent_id in self._agents:
            if "memory" not in self._agents[agent_id]:
                self._agents[agent_id]["memory"] = {}
            self._agents[agent_id]["memory"][block_name] = content
            return True
        return False
    
    async def list_agents(self) -> List[Dict[str, Any]]:
        """
        列出所有 Agent
        
        Returns:
            Agent 列表
        """
        return [
            {"id": agent_id, **data}
            for agent_id, data in self._agents.items()
        ]
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Agent 信息
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent 信息
        """
        if agent_id in self._agents:
            return {"id": agent_id, **self._agents[agent_id]}
        return None


# 全局 Letta 服务实例
_letta_service: Optional[LettaService] = None


def get_letta_service() -> LettaService:
    """
    获取全局 Letta 服务实例
    
    Returns:
        LettaService 实例
    """
    global _letta_service
    if _letta_service is None:
        # 可以从环境变量或配置文件加载配置
        import os
        base_url = os.getenv("LETTA_BASE_URL", "")
        api_key = os.getenv("LETTA_API_KEY", "")
        _letta_service = LettaService(base_url=base_url, api_key=api_key)
    return _letta_service


def reset_letta_service() -> None:
    """重置全局 Letta 服务实例"""
    global _letta_service
    _letta_service = None