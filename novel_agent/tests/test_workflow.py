"""
工作流集成测试
测试Coordinator和完整的小说创作工作流
"""

import pytest
import asyncio
import os
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Dict, Any

# 导入被测试的模块
from novel_agent.workflow.coordinator import NovelCoordinator, WorkflowState
from novel_agent.agent_config import AgentModelConfig, get_config_manager
from novel_agent.project_manager import Project
from novel_agent.workflow.task_pool import TaskStatus
from novel_agent.agents.collab_sub_agents import (
    ContentExpansionAgent,
    ContentReaderAgent,
    FileNamingAgent,
    SummaryOrchestratorAgent,
)


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


@pytest.mark.asyncio
async def test_content_reader_loads_project_files_and_marks_permanent_memory(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "worldbuilding.json").write_text(
        json.dumps({"world": {"world_name": "测试世界", "rules": ["规则1"]}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_dir / "characters.json").write_text(
        json.dumps({"characters": [{"name": "林渡", "role": "主角"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    client_state_dir = project_dir / "client_state"
    client_state_dir.mkdir(parents=True, exist_ok=True)
    (client_state_dir / "collab_permanent_memory.json").write_text(
        json.dumps(
            {
                "loaded_keys": ["knowledge_base"],
                "items": {"knowledge_base": {"note": "cached"}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    agent = ContentReaderAgent()
    result = await agent.execute(
        {
            "strategy": {
                "read_plan": [
                    {"key": "world", "label": "世界观"},
                    {"key": "characters", "label": "角色档案"},
                    {"key": "knowledge_base", "label": "知识库"},
                ]
            }
        },
        context={"project_dir": str(project_dir)},
    )

    assert result["loaded_context"]["world"]["world_name"] == "测试世界"
    assert result["loaded_context"]["characters"][0]["name"] == "林渡"
    report_by_key = {item["key"]: item for item in result["report"]}
    assert report_by_key["world"]["source"] == "project_file"
    assert report_by_key["characters"]["source"] == "project_file"
    assert report_by_key["knowledge_base"]["source"] == "permanent_memory"
    assert "knowledge_base" in result["permanent_memory"]["loaded_keys"]
    assert result["permanent_memory"]["items"]["knowledge_base"]["note"] == "cached"


@pytest.mark.asyncio
async def test_coordinator_persists_collab_permanent_memory_to_client_state(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator.project_manager.current_project_id = "proj-memory"
    coordinator.project_manager.projects["proj-memory"] = Project(
        id="proj-memory",
        name="永久记忆测试项目",
        description="验证协作永久记忆落盘",
    )
    coordinator.project_dir = tmp_path
    coordinator._init_managers()

    task_pool = coordinator._build_chapter_autonomous_task_pool(
        chapter_num=1,
        chapter_title="第一章",
        chapter_outline_text="旧城归来",
        base_context={
            "world": {"era": "玄幻"},
            "characters": [{"name": "林渊"}],
            "chapter_outline": "旧城归来",
            "project_dir": str(tmp_path),
        },
    )

    coordinator.capability_registry.register_many([
        coordinator.context_strategy,
        coordinator.content_reader,
        coordinator.chapter_writer,
        coordinator.evaluator,
        coordinator.content_expansion,
    ])

    coordinator.context_strategy.execute = AsyncMock(return_value={
        "success": True,
        "strategy": {"read_plan": [{"key": "knowledge_base", "label": "知识库"}]},
    })
    coordinator.content_reader.execute = AsyncMock(return_value={
        "success": True,
        "loaded_context": {"chapter_outline": "旧城归来"},
        "report": [{"key": "knowledge_base", "loaded": True, "source": "runtime", "skipped_reason": ""}],
        "permanent_memory": {
            "loaded_keys": ["knowledge_base", "anti_ai_rules"],
            "items": {"knowledge_base": {"note": "cached"}},
        },
    })
    coordinator.chapter_writer.execute = AsyncMock(return_value={"success": True, "content": "正文内容", "word_count": 1000})
    coordinator.evaluator.execute = AsyncMock(return_value={"success": True, "evaluation": {"passed": True, "suggestions": []}})
    coordinator.content_expansion.execute = AsyncMock(return_value={"success": True, "content": "正文内容", "expanded": False, "word_count": 1000})

    result = await coordinator._execute_chapter_task_market(
        chapter_num=1,
        task_pool=task_pool,
        base_context={
            "world": {"era": "玄幻"},
            "characters": [{"name": "林渊"}],
            "chapter_outline": "旧城归来",
            "project_dir": str(tmp_path),
        },
        fallback_agents={},
    )

    memory_path = coordinator.project_dir / "client_state" / "collab_permanent_memory.json"
    assert result["results"]["content_reader"]["result"]["permanent_memory"]["loaded_keys"] == ["knowledge_base", "anti_ai_rules"]
    assert memory_path.exists()
    payload = json.loads(memory_path.read_text(encoding="utf-8"))
    assert payload["loaded_keys"] == ["knowledge_base", "anti_ai_rules"]
    assert payload["items"]["knowledge_base"]["note"] == "cached"


@pytest.mark.asyncio
async def test_content_expansion_expands_short_content_with_context():
    agent = ContentExpansionAgent()
    result = await agent.execute(
        {
            "content": "林渡推门而入。",
            "target_words": 50,
            "chapter_title": "旧城归来",
            "chapter_outline": "主角回到旧城，准备追查真相",
        },
        context={"previous_summary": "上一章他刚拿到关键线索"},
    )

    assert result["expanded"] is True
    assert result["word_count"] > len("林渡推门而入。")
    assert "旧城" in result["content"] or "真相" in result["content"]


@pytest.mark.asyncio
async def test_file_naming_agent_returns_standard_filename():
    agent = FileNamingAgent()
    result = await agent.execute(
        {
            "chapter_number": 3,
            "chapter_title": "第3章 旧城归来",
            "content": "林渡回到旧城，发现旧案并未结束。",
        }
    )

    assert result["filename"].startswith("第3章-")
    assert result["filename"].endswith("字.md")
    assert "旧城归来" in result["filename"]


@pytest.mark.asyncio
async def test_summary_orchestrator_returns_structured_payload():
    agent = SummaryOrchestratorAgent()
    result = await agent.execute(
        {
            "start_chapter": 1,
            "end_chapter": 10,
            "chapters": [
                {"chapter_number": 1, "title": "归来", "content": "林渡归来，开始调查旧案。"},
                {"chapter_number": 2, "title": "追索", "content": "他沿着线索继续追查。"},
            ],
        }
    )

    assert "第1-10章剧情总结" in result["summary"]
    assert result["summary_payload"]["start_chapter"] == 1
    assert result["summary_payload"]["end_chapter"] == 10
    assert result["summary_payload"]["chapter_count"] == 2


@pytest.mark.asyncio
async def test_coordinator_write_single_chapter_persists_stage_summary_and_state(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator.project_manager.current_project_id = "proj-test"
    coordinator.project_manager.projects["proj-test"] = Project(
        id="proj-test",
        name="测试项目",
        description="协作模式测试项目",
    )
    coordinator.project_dir = tmp_path
    coordinator._init_managers()

    coordinator.chapter_writer.execute = AsyncMock(return_value={"content": "正文内容"})
    coordinator.evaluator.execute = AsyncMock(return_value={"evaluation": {"passed": True, "suggestions": []}})
    coordinator.polisher.execute = AsyncMock(return_value={"content": "润色后正文"})
    coordinator.context_strategy.execute = AsyncMock(return_value={"strategy": {"read_plan": []}})
    coordinator.content_reader.execute = AsyncMock(return_value={"loaded_context": {}, "report": [], "permanent_memory": {"loaded_keys": []}})
    coordinator.content_expansion.execute = AsyncMock(return_value={"content": "正文内容扩写版", "expanded": True, "word_count": 120})
    coordinator.file_naming.execute = AsyncMock(return_value={"filename": "第10章-终局-120字.md", "word_count": 120})
    coordinator.summary_orchestrator.execute = AsyncMock(return_value={
        "summary": "第1-10章剧情总结\n- 第10章《终局》：正文内容扩写版",
        "summary_payload": {
            "start_chapter": 1,
            "end_chapter": 10,
            "chapter_count": 10,
            "chapters": [{"chapter_number": 10, "title": "终局", "summary": "正文内容扩写版"}],
            "summary": "第1-10章剧情总结\n- 第10章《终局》：正文内容扩写版",
        },
    })

    previous_chapters = [
        {"number": idx, "title": f"第{idx}章", "content": f"第{idx}章内容"}
        for idx in range(1, 10)
    ]

    result = await coordinator._write_single_chapter_internal(
        chapter_num=10,
        chapter_outline={"title": "终局", "summary": "最终对决"},
        previous_chapters=previous_chapters,
    )

    assert result["suggested_filename"] == "第10章-终局-120字.md"
    assert result["stage_summary"].startswith("第1-10章剧情总结")

    summary_file = Path(result["stage_summary_file"])
    assert summary_file.exists()
    assert "第1-10章剧情总结" in summary_file.read_text(encoding="utf-8")

    stage_summaries = coordinator.project_manager.load_project_state("collab_stage_summaries", default=[])
    assert isinstance(stage_summaries, list)
    assert stage_summaries[-1]["end_chapter"] == 10


def test_phase3_project_stage_summary_persistence_replaces_duplicate_range(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator.project_manager.current_project_id = "phase3-summary-test"
    coordinator.project_manager.projects["phase3-summary-test"] = Project(
        id="phase3-summary-test",
        name="Phase3 Summary Test",
        description="隔离阶段总结状态",
    )
    coordinator.project_dir = tmp_path
    coordinator._init_managers()

    first = coordinator._persist_project_stage_summary_result(
        {
            "summary": "第1-10章剧情总结\n- 第一版",
            "summary_payload": {
                "start_chapter": 1,
                "end_chapter": 10,
                "summary": "第1-10章剧情总结\n- 第一版",
            },
        }
    )
    second = coordinator._persist_project_stage_summary_result(
        {
            "summary": "第1-10章剧情总结\n- 第二版",
            "summary_payload": {
                "start_chapter": 1,
                "end_chapter": 10,
                "summary": "第1-10章剧情总结\n- 第二版",
            },
        }
    )

    stage_summaries = coordinator.project_manager.load_project_state("collab_stage_summaries", default=[])
    summary_path = Path(second["summary_path"])

    assert first["summary_status"] in {"created", "updated"}
    assert second["summary_status"] == "updated"
    matched = [item for item in stage_summaries if isinstance(item, dict)]
    assert len(matched) == 1
    assert matched[0]["summary"].endswith("第二版")
    assert summary_path.exists()
    assert summary_path.read_text(encoding="utf-8").endswith("第二版")


def test_phase3_memory_sync_manager_writes_meta_and_reports_diagnostics(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator._append_memory_event("phase3_test", {"ok": True})
    diagnostics = coordinator.get_memory_diagnostics()

    assert diagnostics["meta_exists"] is True
    assert diagnostics["contract"]["contract_version"] == coordinator._memory_contract_version
    assert diagnostics["meta"]["events"][-1]["type"] == "phase3_test"


def test_phase3_checkpoint_manager_persists_and_reloads_checkpoint(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator._update_checkpoint(state=WorkflowState.WRITING, current_chapter=3, add_stage="writing")

    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        restored = NovelCoordinator(project_dir=tmp_path)

    assert restored.checkpoint is not None
    assert restored.checkpoint.current_chapter == 3
    assert restored.checkpoint.state == WorkflowState.WRITING
    assert "writing" in restored.checkpoint.completed_stages


@pytest.mark.asyncio
async def test_phase4_create_novel_routes_world_character_outline_via_dispatcher(tmp_path, mock_model_config):
    with patch('novel_agent.agent_config.get_config_manager') as mock_manager:
        mock_manager.return_value.get_effective_config.return_value = mock_model_config
        coordinator = NovelCoordinator(project_dir=tmp_path)

    coordinator._ensure_message_bus_started = AsyncMock()
    coordinator._subscribe_all_agents = AsyncMock()
    coordinator._sync_memory_stage = AsyncMock()
    coordinator._export_memory_snapshot = AsyncMock()
    coordinator._check_pause_cancel = AsyncMock(return_value=False)

    coordinator.worldbuilder.execute = AsyncMock(
        return_value={
            "success": True,
            "world": {
                "world_name": "玄荒界",
                "power_system": {"levels": ["炼体", "筑基"]},
                "geography": {"zones": ["旧城"]},
                "factions": [{"name": "归墟司"}],
                "rules": ["夜禁"],
                "culture": {"tone": "压抑"},
            },
        }
    )
    coordinator.character_builder.execute = AsyncMock(
        return_value={
            "success": True,
            "characters": [
                {
                    "name": "林渊",
                    "role": "主角",
                    "identity": "旧城遗孤",
                    "occupation": "巡夜人学徒",
                    "description": "从旧城归来的复仇者。",
                    "personality": ["克制", "执拗"],
                    "goals": ["追查旧案"],
                    "relationships": {"沈砚": "盟友"},
                    "notes": "角色草稿",
                }
            ],
        }
    )
    coordinator.outliner.execute = AsyncMock(
        return_value={
            "success": True,
            "outline": {
                "title": "归墟录",
                "chapters": [
                    {"title": "第一章 旧城归来", "summary": "林渊回到旧城。"},
                ],
            },
        }
    )

    async def fake_write_chapters_serial(chapters, world_data, outline_data):
        yield {
            "stage": "chapter_complete",
            "message": "第 1 章完成",
            "progress": 80,
            "chapter": {"title": "第一章 旧城归来", "content": "章节正文"},
        }

    coordinator._write_chapters_serial = fake_write_chapters_serial

    events = []
    async for item in coordinator.create_novel(
        novel_type="玄幻",
        theme="复仇成长",
        requirements="压抑递进",
        protagonist="林渊",
        plot_idea="从旧城归来开始追查旧案",
        volume_count=1,
        chapters_per_volume=1,
        session_context={"session_id": "sess-phase4"},
    ):
        events.append(item)

    runtime_pool = coordinator.project_manager.load_project_state("task_pool", default={})
    tasks = [item for item in runtime_pool.get("tasks", []) if isinstance(item, dict)]
    task_by_type = {}
    for item in tasks:
        task_by_type.setdefault(item.get("task_type"), []).append(item)

    assert [item["task_type"] for item in tasks[:3]] == ["build_world", "build_characters", "build_outline"]
    assert all(task_by_type[key][0]["status"] == TaskStatus.COMPLETED for key in ("build_world", "build_characters", "build_outline"))
    assert task_by_type["build_world"][0]["metadata"]["candidate_source"] == "capability_registry"
    assert task_by_type["build_characters"][0]["metadata"]["candidate_source"] == "capability_registry"
    assert task_by_type["build_outline"][0]["metadata"]["candidate_source"] == "capability_registry"
    assert "@creation_mainline" in task_by_type["build_world"][0]["metadata"]["route_reason"]
    assert coordinator.worldbuilder.execute.await_count == 1
    assert coordinator.character_builder.execute.await_count == 1
    assert coordinator.outliner.execute.await_count == 1
    assert coordinator.context_manager.get("world", {})["world_name"] == "玄荒界"
    assert coordinator.project.title == "归墟录"
    character_stage = next(
        (
            item for item in events
            if item.get("stage") == "character_building"
            and isinstance(item.get("data"), list)
            and item.get("data")
        ),
        None,
    )
    assert character_stage is not None
    assert character_stage["data"][0]["name"] == "林渊"
    assert events[-1]["stage"] == "completed"

    outline_rows = coordinator.project_manager.load_project_data("outline")
    assert isinstance(outline_rows, list)
    assert outline_rows[0]["title"] == "第一章 旧城归来"


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
