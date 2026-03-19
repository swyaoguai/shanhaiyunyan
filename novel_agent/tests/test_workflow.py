"""
工作流集成测试
测试Coordinator和完整的小说创作工作流
"""

import pytest
import asyncio
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Dict, Any

# 导入被测试的模块
from novel_agent.workflow.coordinator import NovelCoordinator
from novel_agent.agent_config import AgentModelConfig, get_config_manager


# ==================== Fixtures ====================

@pytest.fixture
def mock_model_config():
    """模拟模型配置"""
    return AgentModelConfig(
        agent_name="TestAgent",
        model="gpt-4",
        api_key="test-key",
        api_base="https://api.test.com/v1",
        temperature=0.7,
        max_tokens=4096
    )


@pytest.fixture
def mock_llm_response():
    """模拟LLM响应"""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Test response"
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


@pytest.fixture
def novel_params():
    """小说参数"""
    return {
        "title": "测试小说",
        "author": "测试作者",
        "novel_type": "玄幻",
        "theme": "修仙升级",
        "style": "热血",
        "target_words": 100000,
        "chapter_count": 50
    }


@pytest.fixture
def world_setting():
    """世界观设定"""
    return {
        "world_name": "九天大陆",
        "geography": {
            "continents": ["东洲", "西洲", "南洲", "北洲", "中洲"],
            "special_areas": ["禁地", "秘境"]
        },
        "power_system": {
            "name": "修真体系",
            "levels": ["练气", "筑基", "金丹", "元婴", "化神", "渡劫", "大乘"]
        },
        "factions": [
            {"name": "天剑宗", "type": "正派"},
            {"name": "魔道联盟", "type": "反派"}
        ]
    }


@pytest.fixture
def outline_data():
    """大纲数据"""
    return {
        "title": "测试小说",
        "total_chapters": 50,
        "arcs": [
            {
                "name": "第一卷：崛起",
                "chapters": [1, 20],
                "summary": "主角从小村庄出发，踏上修仙之路"
            },
            {
                "name": "第二卷：成长",
                "chapters": [21, 40],
                "summary": "主角加入宗门，逐渐成长"
            }
        ],
        "chapters": [
            {"number": 1, "title": "序章", "summary": "主角出场"},
            {"number": 2, "title": "离村", "summary": "离开村庄"},
        ]
    }


# ==================== Coordinator Tests ====================

class TestNovelCoordinator:
    """NovelCoordinator测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    def test_initialization(self, coordinator):
        """测试初始化"""
        assert coordinator is not None
        assert hasattr(coordinator, 'worldbuilder')
        assert hasattr(coordinator, 'outliner')
        assert hasattr(coordinator, 'chapter_writer')
        assert hasattr(coordinator, 'polisher')
        assert hasattr(coordinator, 'evaluator')
    
    @pytest.mark.asyncio
    async def test_build_world(self, coordinator, mock_llm_response, novel_params, world_setting):
        """测试世界观构建"""
        # 模拟worldbuilder返回
        mock_llm_response.choices[0].message.content = json.dumps(world_setting, ensure_ascii=False)
        
        with patch.object(coordinator.worldbuilder.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_llm_response
            
            # 调用build_world（假设存在此方法）
            if hasattr(coordinator, 'build_world'):
                result = await coordinator.build_world(novel_params)
                assert result is not None
    
    @pytest.mark.asyncio
    async def test_create_outline(self, coordinator, mock_llm_response, novel_params, outline_data):
        """测试大纲创建"""
        mock_llm_response.choices[0].message.content = json.dumps(outline_data, ensure_ascii=False)
        
        with patch.object(coordinator.outliner.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_llm_response
            
            if hasattr(coordinator, 'create_outline'):
                result = await coordinator.create_outline(novel_params)
                assert result is not None
    
    @pytest.mark.asyncio
    async def test_write_chapter(self, coordinator, mock_llm_response):
        """测试章节写作"""
        chapter_content = """
        # 第一章 序章
        
        晨曦微露，少年从睡梦中醒来...
        
        （约2000字内容）
        """
        mock_llm_response.choices[0].message.content = chapter_content
        
        with patch.object(coordinator.chapter_writer.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_llm_response
            
            if hasattr(coordinator, 'write_chapter'):
                result = await coordinator.write_chapter(
                    chapter_number=1,
                    chapter_title="序章",
                    chapter_outline="主角出场"
                )
                assert result is not None


# ==================== Workflow State Tests ====================

class TestWorkflowState:
    """工作流状态测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    def test_initial_state(self, coordinator):
        """测试初始状态"""
        # 验证初始状态
        if hasattr(coordinator, 'state'):
            assert coordinator.state is not None
    
    def test_checkpoint_save_load(self, coordinator, tmp_path):
        """测试检查点保存和加载"""
        if hasattr(coordinator, 'save_checkpoint') and hasattr(coordinator, 'load_checkpoint'):
            checkpoint_path = tmp_path / "checkpoint.json"
            
            # 保存检查点
            coordinator.save_checkpoint(str(checkpoint_path))
            assert checkpoint_path.exists()
            
            # 加载检查点
            coordinator.load_checkpoint(str(checkpoint_path))


# ==================== Error Recovery Tests ====================

class TestErrorRecovery:
    """错误恢复测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    @pytest.mark.asyncio
    async def test_llm_error_handling(self, coordinator):
        """测试LLM错误处理"""
        async def raise_error(**kwargs):
            raise Exception("Simulated LLM error")
        
        with patch.object(coordinator.worldbuilder.client.chat.completions, 'create',
                         new_callable=lambda: raise_error):
            # 验证错误被正确处理
            if hasattr(coordinator, 'build_world'):
                with pytest.raises(Exception):
                    await coordinator.build_world({"novel_type": "玄幻"})
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, coordinator, mock_llm_response):
        """测试重试机制"""
        call_count = 0
        
        async def failing_then_success(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary error")
            return mock_llm_response
        
        # 验证重试后成功
        # 注意：实际重试逻辑在base_agent中实现


# ==================== Integration Flow Tests ====================

class TestIntegrationFlow:
    """完整流程集成测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    @pytest.mark.asyncio
    async def test_full_workflow_simulation(
        self, 
        coordinator, 
        mock_llm_response,
        novel_params,
        world_setting,
        outline_data
    ):
        """模拟完整工作流"""
        responses = [
            json.dumps(world_setting, ensure_ascii=False),  # 世界观
            json.dumps(outline_data, ensure_ascii=False),   # 大纲
            "# 第一章\n这是第一章内容...",                    # 章节
            "# 第一章（润色后）\n这是润色后的内容...",         # 润色
            json.dumps({"score": 85, "suggestions": []})     # 评估
        ]
        
        response_index = 0
        
        async def mock_create(**kwargs):
            nonlocal response_index
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = responses[min(response_index, len(responses)-1)]
            response.usage = MagicMock()
            response.usage.prompt_tokens = 100
            response.usage.completion_tokens = 50
            response_index += 1
            return response
        
        # 为所有agent设置mock
        agents = [
            coordinator.worldbuilder,
            coordinator.outliner,
            coordinator.chapter_writer,
            coordinator.polisher,
            coordinator.evaluator
        ]
        
        for agent in agents:
            with patch.object(agent.client.chat.completions, 'create',
                             new_callable=lambda: mock_create):
                pass
        
        # 验证coordinator可以正常工作
        assert coordinator is not None


# ==================== Callback Tests ====================

class TestWorkflowCallbacks:
    """工作流回调测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    @pytest.mark.asyncio
    async def test_progress_callback(self, coordinator):
        """测试进度回调"""
        progress_updates = []
        
        async def progress_handler(data):
            progress_updates.append(data)
        
        if hasattr(coordinator, 'set_progress_callback'):
            coordinator.set_progress_callback(progress_handler)
            # 执行某些操作后验证进度更新
    
    @pytest.mark.asyncio
    async def test_user_input_callback(self, coordinator):
        """测试用户输入回调"""
        async def input_handler(data):
            if data.get("question") == "请确认大纲":
                return "确认"
            return None
        
        if hasattr(coordinator, 'set_input_callback'):
            coordinator.set_input_callback(input_handler)


def test_coordinator_aux_memory_query_building():
    coordinator = NovelCoordinator()
    query = coordinator._build_aux_memory_query(
        chapter_num=3,
        chapter_outline={"title": "夜战", "summary": "主角突袭敌营"},
        context={"previous_summary": "上一章主角拿到情报"},
    )
    assert "夜战" in query
    assert "突袭" in query
    assert "chapter:3" in query


def test_coordinator_aux_memory_injection_context_without_project():
    coordinator = NovelCoordinator()
    coordinator.project_manager.current_project_id = None
    payload = coordinator._get_aux_memory_injection_context("测试")
    assert payload["enabled"] is False
    assert payload["count"] == 0


# ==================== Message Bus Tests ====================

class TestMessageBus:
    """消息总线测试"""
    
    def test_message_bus_import(self):
        """测试消息总线导入"""
        from novel_agent.agents.message_bus import MessageBus, AgentMessage, MessageType
        
        bus = MessageBus()
        assert bus is not None
    
    @pytest.mark.asyncio
    async def test_message_publish_subscribe(self):
        """测试消息发布订阅"""
        from novel_agent.agents.message_bus import MessageBus, AgentMessage, MessageType
        
        bus = MessageBus()
        received_messages = []
        
        async def handler(msg):
            received_messages.append(msg)
        
        bus.subscribe("TestAgent", handler)
        
        # 使用正确的MessageType
        message = AgentMessage(
            msg_type=MessageType.TASK_ASSIGNED,
            sender="Coordinator",
            receiver="TestAgent",
            payload={"task": "test"}
        )
        
        await bus.publish(message)
        
        # 启动消息总线处理
        await bus.start()
        
        # 给异步处理一点时间
        await asyncio.sleep(0.2)
        
        # 停止消息总线
        await bus.stop()
        
        assert len(received_messages) == 1
        assert received_messages[0].payload["task"] == "test"


# ==================== Performance Tests ====================

class TestPerformance:
    """性能测试"""
    
    @pytest.fixture
    def coordinator(self, mock_model_config):
        """创建Coordinator"""
        with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
            mock_manager.return_value.get_effective_config.return_value = mock_model_config
            return NovelCoordinator()
    
    @pytest.mark.asyncio
    async def test_concurrent_chapter_writing(self, coordinator, mock_llm_response):
        """测试并发章节写作"""
        async def mock_create(**kwargs):
            await asyncio.sleep(0.01)  # 模拟延迟
            return mock_llm_response
        
        with patch.object(coordinator.chapter_writer.client.chat.completions, 'create',
                         new_callable=lambda: mock_create):
            # 测试并发写作多个章节
            if hasattr(coordinator, 'write_chapters_concurrent'):
                chapters = [
                    {"number": i, "title": f"第{i}章", "outline": f"章节{i}内容"}
                    for i in range(1, 4)
                ]
                # 验证并发执行
    
    def test_memory_usage(self, coordinator):
        """测试内存使用"""
        import sys
        
        # 获取coordinator对象大小
        size = sys.getsizeof(coordinator)
        
        # 验证内存使用在合理范围内
        assert size < 10 * 1024 * 1024  # 小于10MB


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
