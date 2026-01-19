"""
WebSocket实时推送模块
提供实时进度更新、状态通知等功能
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..constants import WEBSOCKET_CONFIG

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """WebSocket消息类型"""
    # 系统消息
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    
    # 进度消息
    PROGRESS = "progress"
    STAGE_CHANGE = "stage_change"
    CHAPTER_COMPLETE = "chapter_complete"
    
    # 状态消息
    STATUS_UPDATE = "status_update"
    WORKFLOW_STATE = "workflow_state"
    
    # 通知消息
    NOTIFICATION = "notification"
    ALERT = "alert"


@dataclass
class WebSocketMessage:
    """WebSocket消息"""
    type: MessageType
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp
        }, ensure_ascii=False)


@dataclass
class ClientConnection:
    """客户端连接"""
    websocket: WebSocket
    client_id: str
    connected_at: str
    subscriptions: Set[str] = field(default_factory=set)
    
    async def send(self, message: WebSocketMessage):
        """发送消息"""
        if self.websocket.client_state == WebSocketState.CONNECTED:
            try:
                await self.websocket.send_text(message.to_json())
            except Exception as e:
                logger.warning(f"Failed to send message to {self.client_id}: {e}")


class ConnectionManager:
    """
    WebSocket连接管理器
    
    功能：
    - 管理多个客户端连接
    - 支持订阅/发布模式
    - 广播消息
    - 心跳检测
    """
    
    def __init__(self):
        self.active_connections: Dict[str, ClientConnection] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> client_ids
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = WEBSOCKET_CONFIG.HEARTBEAT_INTERVAL
    
    async def connect(
        self, 
        websocket: WebSocket, 
        client_id: Optional[str] = None
    ) -> ClientConnection:
        """
        接受新连接
        
        Args:
            websocket: WebSocket连接
            client_id: 客户端ID，如果不提供则自动生成
            
        Returns:
            ClientConnection对象
        """
        await websocket.accept()
        
        # 生成或使用提供的client_id
        if not client_id:
            import uuid
            client_id = str(uuid.uuid4())[:8]
        
        # 创建连接记录
        connection = ClientConnection(
            websocket=websocket,
            client_id=client_id,
            connected_at=datetime.now().isoformat()
        )
        
        self.active_connections[client_id] = connection
        
        # 发送连接成功消息
        await connection.send(WebSocketMessage(
            type=MessageType.CONNECTED,
            payload={
                "client_id": client_id,
                "message": "Connected successfully"
            }
        ))
        
        logger.info(f"WebSocket client connected: {client_id}")
        
        # 启动心跳（如果还没启动）
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        return connection
    
    def disconnect(self, client_id: str):
        """断开连接"""
        if client_id in self.active_connections:
            connection = self.active_connections[client_id]
            
            # 从所有订阅中移除
            for topic in connection.subscriptions:
                if topic in self.subscriptions:
                    self.subscriptions[topic].discard(client_id)
            
            del self.active_connections[client_id]
            logger.info(f"WebSocket client disconnected: {client_id}")
    
    def subscribe(self, client_id: str, topic: str):
        """
        订阅主题
        
        Args:
            client_id: 客户端ID
            topic: 主题名称
        """
        if client_id in self.active_connections:
            self.active_connections[client_id].subscriptions.add(topic)
            
            if topic not in self.subscriptions:
                self.subscriptions[topic] = set()
            self.subscriptions[topic].add(client_id)
            
            logger.debug(f"Client {client_id} subscribed to {topic}")
    
    def unsubscribe(self, client_id: str, topic: str):
        """
        取消订阅
        
        Args:
            client_id: 客户端ID
            topic: 主题名称
        """
        if client_id in self.active_connections:
            self.active_connections[client_id].subscriptions.discard(topic)
            
            if topic in self.subscriptions:
                self.subscriptions[topic].discard(client_id)
    
    async def send_personal(
        self, 
        client_id: str, 
        message: WebSocketMessage
    ):
        """
        发送个人消息
        
        Args:
            client_id: 客户端ID
            message: 消息
        """
        if client_id in self.active_connections:
            await self.active_connections[client_id].send(message)
    
    async def broadcast(
        self, 
        message: WebSocketMessage,
        exclude: Optional[Set[str]] = None
    ):
        """
        广播消息给所有连接
        
        Args:
            message: 消息
            exclude: 排除的客户端ID集合
        """
        exclude = exclude or set()
        
        for client_id, connection in self.active_connections.items():
            if client_id not in exclude:
                await connection.send(message)
    
    async def publish(
        self, 
        topic: str, 
        message: WebSocketMessage
    ):
        """
        发布消息到主题
        
        Args:
            topic: 主题名称
            message: 消息
        """
        if topic in self.subscriptions:
            for client_id in self.subscriptions[topic]:
                if client_id in self.active_connections:
                    await self.active_connections[client_id].send(message)
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.active_connections:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                # 发送心跳
                heartbeat = WebSocketMessage(
                    type=MessageType.HEARTBEAT,
                    payload={"timestamp": datetime.now().isoformat()}
                )
                
                # 检查连接状态
                disconnected = []
                for client_id, connection in self.active_connections.items():
                    try:
                        if connection.websocket.client_state == WebSocketState.CONNECTED:
                            await connection.send(heartbeat)
                        else:
                            disconnected.append(client_id)
                    except Exception:
                        disconnected.append(client_id)
                
                # 清理断开的连接
                for client_id in disconnected:
                    self.disconnect(client_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        return {
            "active_connections": len(self.active_connections),
            "topics": list(self.subscriptions.keys()),
            "clients": [
                {
                    "id": cid,
                    "connected_at": conn.connected_at,
                    "subscriptions": list(conn.subscriptions)
                }
                for cid, conn in self.active_connections.items()
            ]
        }


# 全局连接管理器
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """获取全局连接管理器"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


# ==================== 进度回调适配器 ====================

class WebSocketProgressCallback:
    """
    WebSocket进度回调适配器
    
    将工作流进度转换为WebSocket消息并推送给订阅者
    """
    
    def __init__(self, topic: str = "novel_progress"):
        self.topic = topic
        self.manager = get_connection_manager()
    
    async def __call__(self, data: Dict[str, Any]):
        """
        进度回调
        
        Args:
            data: 进度数据
        """
        # 确定消息类型
        stage = data.get("stage", "")
        if stage == "chapter_complete":
            msg_type = MessageType.CHAPTER_COMPLETE
        elif "progress" in data:
            msg_type = MessageType.PROGRESS
        else:
            msg_type = MessageType.STAGE_CHANGE
        
        # 创建消息
        message = WebSocketMessage(
            type=msg_type,
            payload=data
        )
        
        # 发布到主题
        await self.manager.publish(self.topic, message)
        
        # 同时广播（确保所有客户端收到）
        await self.manager.broadcast(message)


# ==================== WebSocket路由设置 ====================

def setup_websocket_routes(app):
    """
    设置WebSocket路由
    
    Args:
        app: FastAPI应用
    """
    manager = get_connection_manager()
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """主WebSocket端点"""
        connection = await manager.connect(websocket)
        
        try:
            while True:
                # 接收消息
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    action = message.get("action")
                    
                    if action == "subscribe":
                        topic = message.get("topic", "default")
                        manager.subscribe(connection.client_id, topic)
                        await connection.send(WebSocketMessage(
                            type=MessageType.NOTIFICATION,
                            payload={"message": f"Subscribed to {topic}"}
                        ))
                    
                    elif action == "unsubscribe":
                        topic = message.get("topic", "default")
                        manager.unsubscribe(connection.client_id, topic)
                        await connection.send(WebSocketMessage(
                            type=MessageType.NOTIFICATION,
                            payload={"message": f"Unsubscribed from {topic}"}
                        ))
                    
                    elif action == "ping":
                        await connection.send(WebSocketMessage(
                            type=MessageType.HEARTBEAT,
                            payload={"message": "pong"}
                        ))
                    
                    else:
                        # 未知操作
                        await connection.send(WebSocketMessage(
                            type=MessageType.ERROR,
                            payload={"message": f"Unknown action: {action}"}
                        ))
                        
                except json.JSONDecodeError:
                    await connection.send(WebSocketMessage(
                        type=MessageType.ERROR,
                        payload={"message": "Invalid JSON"}
                    ))
                    
        except WebSocketDisconnect:
            manager.disconnect(connection.client_id)
    
    @app.websocket("/ws/{client_id}")
    async def websocket_with_id(websocket: WebSocket, client_id: str):
        """带客户端ID的WebSocket端点"""
        connection = await manager.connect(websocket, client_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    action = message.get("action")
                    
                    if action == "subscribe":
                        topic = message.get("topic", "default")
                        manager.subscribe(client_id, topic)
                    
                    elif action == "unsubscribe":
                        topic = message.get("topic", "default")
                        manager.unsubscribe(client_id, topic)
                    
                except json.JSONDecodeError:
                    pass
                    
        except WebSocketDisconnect:
            manager.disconnect(client_id)
    
    # 添加WebSocket状态API
    @app.get("/api/ws/stats")
    async def get_websocket_stats():
        """获取WebSocket连接统计"""
        return manager.get_stats()
    
    logger.info("WebSocket routes setup complete")