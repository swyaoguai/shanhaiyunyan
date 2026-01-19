"""
消息总线
实现智能体间的消息通信机制

增强功能：
- 默认响应处理器：确保未处理的消息有默认响应
- 响应保证：死信队列消息自动触发默认处理
- 消息追踪：记录消息处理状态
"""

import asyncio
import uuid
import logging
from typing import Dict, Any, Callable, List, Optional, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..constants import MESSAGE_BUS_CONFIG, TIMEOUTS

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    # 任务相关
    TASK_ASSIGNED = "task_assigned"          # Coordinator分配任务
    TASK_COMPLETED = "task_completed"        # 子Agent完成任务
    TASK_FAILED = "task_failed"              # 子Agent失败
    TASK_PROGRESS = "task_progress"          # 任务进度更新
    
    # 上下文相关
    CONTEXT_UPDATED = "context_updated"      # 上下文更新
    CONTEXT_REQUEST = "context_request"      # 请求上下文
    
    # 协作相关
    NEED_REVIEW = "need_review"              # 请求评审
    REVIEW_COMPLETED = "review_completed"    # 评审完成
    
    # 用户交互
    USER_INPUT_REQUIRED = "user_input_required"  # 需要用户输入
    USER_INPUT_RECEIVED = "user_input_received"  # 收到用户输入
    
    # 系统消息
    AGENT_STARTED = "agent_started"          # Agent启动
    AGENT_STOPPED = "agent_stopped"          # Agent停止
    HEARTBEAT = "heartbeat"                  # 心跳


@dataclass
class AgentMessage:
    """Agent消息"""
    msg_type: MessageType
    sender: str                              # 发送者Agent名称
    receiver: str                            # 接收者（"coordinator"、"*" 广播、或具体Agent名）
    payload: Dict[str, Any]                  # 消息内容
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None           # 关联的原始消息ID
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: int = 0                        # 优先级（越高越优先）
    ttl: int = MESSAGE_BUS_CONFIG.DEFAULT_TTL  # 生存时间（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "payload": self.payload,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """从字典创建"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            msg_type=MessageType(data["msg_type"]),
            sender=data["sender"],
            receiver=data["receiver"],
            payload=data.get("payload", {}),
            reply_to=data.get("reply_to"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            priority=data.get("priority", 0)
        )


# 消息处理器类型
MessageHandler = Callable[[AgentMessage], Awaitable[Optional[AgentMessage]]]


# 默认响应处理器类型
DefaultHandler = Callable[[AgentMessage], Awaitable[Optional[AgentMessage]]]


class MessageBus:
    """
    智能体间消息总线
    
    实现功能：
    1. 发布/订阅模式
    2. 请求/响应模式
    3. 消息优先级
    4. 消息持久化（可选）
    5. 死信队列
    6. 默认响应处理器（确保消息必有响应）
    """
    
    def __init__(self, enable_persistence: bool = False):
        """
        初始化消息总线
        
        Args:
            enable_persistence: 是否启用消息持久化
        """
        self.subscribers: Dict[str, List[MessageHandler]] = {}
        self.type_subscribers: Dict[MessageType, List[MessageHandler]] = {}
        self.message_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.pending_replies: Dict[str, asyncio.Future] = {}
        self.dead_letters: List[AgentMessage] = []
        self.message_history: List[AgentMessage] = []
        self.enable_persistence = enable_persistence
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        
        # 默认响应处理器（确保消息必有响应）
        self._default_handler: Optional[DefaultHandler] = None
        
        # 消息处理统计
        self._stats = {
            "total_published": 0,
            "total_delivered": 0,
            "total_default_handled": 0,
            "total_dead_letters": 0
        }
        
        logger.info("MessageBus initialized")
    
    def set_default_handler(self, handler: DefaultHandler) -> None:
        """
        设置默认响应处理器
        
        当消息没有被任何订阅者处理时，会调用此处理器
        这确保了每个用户请求都有响应
        
        Args:
            handler: 默认处理函数
        """
        self._default_handler = handler
        logger.info("Default message handler registered")
    
    async def start(self):
        """启动消息处理器"""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        logger.info("MessageBus started")
    
    async def stop(self):
        """停止消息处理器"""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("MessageBus stopped")
    
    def subscribe(self, agent_name: str, handler: MessageHandler):
        """
        订阅特定Agent的消息
        
        Args:
            agent_name: Agent名称
            handler: 消息处理函数
        """
        if agent_name not in self.subscribers:
            self.subscribers[agent_name] = []
        self.subscribers[agent_name].append(handler)
        logger.debug(f"Agent '{agent_name}' subscribed to message bus")
    
    def subscribe_type(self, msg_type: MessageType, handler: MessageHandler):
        """
        订阅特定类型的消息
        
        Args:
            msg_type: 消息类型
            handler: 消息处理函数
        """
        if msg_type not in self.type_subscribers:
            self.type_subscribers[msg_type] = []
        self.type_subscribers[msg_type].append(handler)
        logger.debug(f"Subscribed to message type: {msg_type.value}")
    
    def unsubscribe(self, agent_name: str, handler: Optional[MessageHandler] = None):
        """
        取消订阅
        
        Args:
            agent_name: Agent名称
            handler: 特定处理函数（可选，不指定则移除所有）
        """
        if agent_name in self.subscribers:
            if handler:
                self.subscribers[agent_name] = [
                    h for h in self.subscribers[agent_name] if h != handler
                ]
            else:
                del self.subscribers[agent_name]
    
    async def publish(self, message: AgentMessage) -> None:
        """
        发布消息
        
        Args:
            message: 消息对象
        """
        # 使用负的优先级，因为PriorityQueue是最小堆
        priority = -message.priority
        await self.message_queue.put((priority, message.timestamp, message))
        
        if self.enable_persistence:
            self.message_history.append(message)
        
        self._stats["total_published"] += 1
        logger.debug(f"Message published: {message.msg_type.value} from {message.sender} to {message.receiver}")
    
    async def request(
        self,
        message: AgentMessage,
        timeout: float = TIMEOUTS.HTTP_LONG
    ) -> Optional[AgentMessage]:
        """
        发送请求并等待响应
        
        Args:
            message: 请求消息
            timeout: 超时时间（秒）
            
        Returns:
            响应消息，超时返回None
        """
        # 创建Future等待响应
        future: asyncio.Future = asyncio.Future()
        self.pending_replies[message.id] = future
        
        # 发布消息
        await self.publish(message)
        
        try:
            # 等待响应
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout: {message.id}")
            return None
        finally:
            self.pending_replies.pop(message.id, None)
    
    async def reply(self, original: AgentMessage, response: AgentMessage) -> None:
        """
        回复消息
        
        Args:
            original: 原始消息
            response: 响应消息
        """
        response.reply_to = original.id
        await self.publish(response)
        
        # 如果有等待的Future，完成它
        if original.id in self.pending_replies:
            self.pending_replies[original.id].set_result(response)
    
    async def _process_messages(self):
        """消息处理循环"""
        while self._running:
            try:
                # 获取消息（带超时以允许检查_running状态）
                try:
                    _, _, message = await asyncio.wait_for(
                        self.message_queue.get(),
                        timeout=TIMEOUTS.MESSAGE_QUEUE
                    )
                except asyncio.TimeoutError:
                    continue
                
                await self._dispatch_message(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def _dispatch_message(self, message: AgentMessage):
        """分发消息给订阅者"""
        delivered = False
        
        # 1. 检查是否是响应消息
        if message.reply_to and message.reply_to in self.pending_replies:
            self.pending_replies[message.reply_to].set_result(message)
            delivered = True
        
        # 2. 按接收者分发
        if message.receiver == "*":
            # 广播给所有订阅者
            for agent_name, handlers in self.subscribers.items():
                for handler in handlers:
                    try:
                        await handler(message)
                        delivered = True
                    except Exception as e:
                        logger.error(f"Handler error for {agent_name}: {e}")
        elif message.receiver in self.subscribers:
            # 发给特定Agent
            for handler in self.subscribers[message.receiver]:
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.error(f"Handler error for {message.receiver}: {e}")
        
        # 3. 按消息类型分发
        if message.msg_type in self.type_subscribers:
            for handler in self.type_subscribers[message.msg_type]:
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.error(f"Type handler error: {e}")
        
        # 4. 未投递的消息：尝试默认处理器
        if not delivered:
            if self._default_handler:
                try:
                    logger.info(f"Invoking default handler for undelivered message: {message.id}")
                    await self._default_handler(message)
                    delivered = True
                    self._stats["total_default_handled"] += 1
                except Exception as e:
                    logger.error(f"Default handler error: {e}")
            
            # 如果仍未处理，进入死信队列
            if not delivered:
                self.dead_letters.append(message)
                self._stats["total_dead_letters"] += 1
                logger.warning(f"Message not delivered, moved to dead letters: {message.id}")
        else:
            self._stats["total_delivered"] += 1
    
    def get_dead_letters(self) -> List[AgentMessage]:
        """获取死信队列中的消息"""
        return self.dead_letters.copy()
    
    def clear_dead_letters(self):
        """清空死信队列"""
        self.dead_letters.clear()
    
    def get_history(self, limit: int = MESSAGE_BUS_CONFIG.HISTORY_LIMIT) -> List[Dict[str, Any]]:
        """获取消息历史"""
        return [msg.to_dict() for msg in self.message_history[-limit:]]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "subscribers": list(self.subscribers.keys()),
            "type_subscribers": [t.value for t in self.type_subscribers.keys()],
            "pending_replies": len(self.pending_replies),
            "dead_letters": len(self.dead_letters),
            "history_size": len(self.message_history),
            "running": self._running,
            "has_default_handler": self._default_handler is not None,
            "message_stats": self._stats.copy()
        }


# 全局消息总线实例
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """获取全局消息总线实例"""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus():
    """
    重置全局消息总线
    
    注意：此函数会同步停止消息总线。如果在异步上下文中调用，
    建议先await message_bus.stop()再调用此函数。
    """
    global _message_bus
    if _message_bus:
        # 标记停止，防止处理器继续运行
        _message_bus._running = False
        
        # 尝试在运行中的事件循环中创建停止任务
        try:
            loop = asyncio.get_running_loop()
            # 创建停止任务（取消处理器任务）
            if _message_bus._processor_task and not _message_bus._processor_task.done():
                _message_bus._processor_task.cancel()
        except RuntimeError:
            # 没有运行中的事件循环，只需标记停止即可
            # 处理器任务会在下次检查 _running 时自动退出
            pass
    _message_bus = None


# ==================== 辅助函数 ====================

def create_task_message(
    sender: str,
    receiver: str,
    task_type: str,
    task_data: Dict[str, Any],
    priority: int = 0
) -> AgentMessage:
    """创建任务分配消息"""
    return AgentMessage(
        msg_type=MessageType.TASK_ASSIGNED,
        sender=sender,
        receiver=receiver,
        payload={
            "task_type": task_type,
            "task_data": task_data
        },
        priority=priority
    )


def create_completion_message(
    sender: str,
    task_id: str,
    result: Dict[str, Any],
    success: bool = True
) -> AgentMessage:
    """创建任务完成消息"""
    return AgentMessage(
        msg_type=MessageType.TASK_COMPLETED if success else MessageType.TASK_FAILED,
        sender=sender,
        receiver="coordinator",
        payload={
            "task_id": task_id,
            "result": result,
            "success": success
        }
    )


def create_context_update_message(
    sender: str,
    context_key: str,
    context_value: Any,
    category: str = "general"
) -> AgentMessage:
    """创建上下文更新消息"""
    return AgentMessage(
        msg_type=MessageType.CONTEXT_UPDATED,
        sender=sender,
        receiver="*",  # 广播
        payload={
            "key": context_key,
            "value": context_value,
            "category": category
        }
    )


def create_user_input_request(
    sender: str,
    question: str,
    options: Optional[List[str]] = None,
    input_type: str = "text"
) -> AgentMessage:
    """创建用户输入请求消息"""
    return AgentMessage(
        msg_type=MessageType.USER_INPUT_REQUIRED,
        sender=sender,
        receiver="coordinator",
        payload={
            "question": question,
            "options": options,
            "input_type": input_type
        },
        priority=MESSAGE_BUS_CONFIG.HIGH_PRIORITY
    )


# 模块职责说明：实现Agent间的消息通信机制，支持发布/订阅和请求/响应模式。