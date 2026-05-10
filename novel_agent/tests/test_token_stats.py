"""
Token统计模块测试
"""

import pytest
import tempfile
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# 添加模块路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from novel_agent.utils.token_stats import TokenStatsStore, TokenUsageRecord, extract_token_usage


class TestTokenStatsStore:
    """TokenStatsStore 测试类"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        # 清理 - Windows上可能需要稍等一下
        import time
        for _ in range(3):
            try:
                if os.path.exists(db_path):
                    os.unlink(db_path)
                break
            except PermissionError:
                time.sleep(0.1)
    
    @pytest.fixture
    def store(self, temp_db):
        """创建测试用的存储实例"""
        s = TokenStatsStore(db_path=temp_db)
        yield s
        # 测试结束后关闭连接
        s.close()
    
    def test_init_creates_tables(self, store):
        """测试初始化时创建表"""
        # 验证可以查询
        records = store.get_recent_records(limit=10)
        assert isinstance(records, list)
    
    def test_record_token_usage(self, store):
        """测试记录token使用"""
        record_id = store.record(
            agent_name="TestAgent",
            model="gpt-4",
            tokens_in=100,
            tokens_out=200,
            success=True,
            method="test_method",
            duration=1.5
        )
        
        assert record_id > 0
        
        # 验证记录
        records = store.get_recent_records(limit=1)
        assert len(records) == 1
        assert records[0]["agent_name"] == "TestAgent"
        assert records[0]["model"] == "gpt-4"
        assert records[0]["tokens_in"] == 100
        assert records[0]["tokens_out"] == 200
        assert records[0]["total_tokens"] == 300
    
    def test_get_summary(self, store):
        """测试获取统计摘要"""
        # 添加一些测试数据
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        store.record("Agent1", "gpt-4", 150, 250, False, "test", 2.0)
        
        summary = store.get_summary(days=7)
        
        assert summary["total_tokens"] == 850  # 300 + 150 + 400
        assert summary["call_count"] == 3
        assert summary["success_count"] == 2
        assert summary["model_count"] == 2
        assert summary["agent_count"] == 2
    
    def test_get_daily_stats(self, store):
        """测试获取每日统计"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        
        daily_stats = store.get_daily_stats(days=7)
        
        assert len(daily_stats) >= 1
        today = datetime.now().strftime('%Y-%m-%d')
        today_stat = next((s for s in daily_stats if s["date"] == today), None)
        assert today_stat is not None
        assert today_stat["total_tokens"] == 300
    
    def test_get_hourly_stats(self, store):
        """测试获取小时统计"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        
        hourly_stats = store.get_hourly_stats(hours=24)
        
        # 应该有24个小时的数据（包含填充的空数据）
        assert len(hourly_stats) >= 1
    
    def test_get_model_stats(self, store):
        """测试按模型统计"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-4", 150, 250, True, "test", 1.5)
        store.record("Agent1", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        model_stats = store.get_model_stats(days=7)
        
        assert len(model_stats) == 2
        
        gpt4_stat = next((s for s in model_stats if s["model"] == "gpt-4"), None)
        assert gpt4_stat is not None
        assert gpt4_stat["total_tokens"] == 700  # 300 + 400
        assert gpt4_stat["call_count"] == 2
    
    def test_get_agent_stats(self, store):
        """测试按Agent统计"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent1", "gpt-4", 150, 250, True, "test", 1.5)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        agent_stats = store.get_agent_stats(days=7)
        
        assert len(agent_stats) == 2
        
        agent1_stat = next((s for s in agent_stats if s["agent_name"] == "Agent1"), None)
        assert agent1_stat is not None
        assert agent1_stat["total_tokens"] == 700  # 300 + 400
        assert agent1_stat["call_count"] == 2
    
    def test_get_available_models(self, store):
        """测试获取可用模型列表"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        models = store.get_available_models()
        
        assert "gpt-4" in models
        assert "gpt-3.5" in models
    
    def test_get_available_agents(self, store):
        """测试获取可用Agent列表"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        agents = store.get_available_agents()
        
        assert "Agent1" in agents
        assert "Agent2" in agents
    
    def test_filter_by_model(self, store):
        """测试按模型筛选"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        summary = store.get_summary(days=7, model="gpt-4")
        
        assert summary["total_tokens"] == 300
        assert summary["call_count"] == 1
    
    def test_filter_by_agent(self, store):
        """测试按Agent筛选"""
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        store.record("Agent2", "gpt-3.5", 50, 100, True, "test", 0.5)
        
        summary = store.get_summary(days=7, agent_name="Agent1")
        
        assert summary["total_tokens"] == 300
        assert summary["call_count"] == 1

    def test_filter_by_project(self, store):
        """测试按项目筛选"""
        store.record("Agent1", "gpt-4", project_id="project-a", tokens_in=100, tokens_out=200, success=True, method="test", duration=1.0)
        store.record("Agent2", "gpt-4", project_id="project-b", tokens_in=50, tokens_out=100, success=True, method="test", duration=0.5)
        store.record("Agent3", "gpt-3.5", project_id="project-a", tokens_in=10, tokens_out=20, success=True, method="test", duration=0.2)

        summary = store.get_summary(days=7, project_id="project-a")
        models = store.get_available_models(project_id="project-a")
        model_stats = store.get_model_stats(days=7, project_id="project-a")

        assert summary["total_tokens"] == 330
        assert summary["call_count"] == 2
        assert summary["filter_project_id"] == "project-a"
        assert models == ["gpt-3.5", "gpt-4"]
        assert {row["model"] for row in model_stats} == {"gpt-3.5", "gpt-4"}

    def test_reset_project_only(self, store):
        """测试只重置指定项目统计"""
        store.record("Agent1", "gpt-4", project_id="project-a", tokens_in=100, tokens_out=200, success=True, method="test", duration=1.0)
        store.record("Agent2", "gpt-4", project_id="project-b", tokens_in=50, tokens_out=100, success=True, method="test", duration=0.5)

        deleted_count = store.reset_all(project_id="project-a")
        project_a_summary = store.get_summary(days=7, project_id="project-a")
        project_b_summary = store.get_summary(days=7, project_id="project-b")

        assert deleted_count == 1
        assert project_a_summary["call_count"] == 0
        assert project_b_summary["total_tokens"] == 150

    def test_legacy_schema_backfills_current_project(self, temp_db, monkeypatch):
        """测试旧数据库增加项目字段时回填当前项目"""
        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                """
                CREATE TABLE token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    agent_name TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    method TEXT DEFAULT '',
                    duration REAL DEFAULT 0.0
                )
                """
            )
            conn.execute(
                """
                INSERT INTO token_usage
                (timestamp, agent_name, model, tokens_in, tokens_out, total_tokens, success, method, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (datetime.now(), "Agent1", "gpt-4", 100, 200, 300, 1, "test", 1.0),
            )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr("novel_agent.utils.token_stats._get_current_project_id", lambda: "project-a")
        migrated_store = TokenStatsStore(db_path=temp_db)
        try:
            assert migrated_store.get_summary(days=7, project_id="project-a")["total_tokens"] == 300
            assert migrated_store.get_summary(days=7, project_id="project-b")["call_count"] == 0
        finally:
            migrated_store.close()
    
    def test_cleanup_old_records(self, store):
        """测试清理旧记录"""
        # 添加记录
        store.record("Agent1", "gpt-4", 100, 200, True, "test", 1.0)
        
        # 清理（保留1天内的记录）
        deleted_count = store.cleanup_old_records(days=1)
        
        # 由于刚添加，不应删除
        assert deleted_count == 0
        
        records = store.get_recent_records()
        assert len(records) == 1


class TestTokenUsageRecord:
    """TokenUsageRecord 测试类"""
    
    def test_record_creation(self):
        """测试创建记录"""
        record = TokenUsageRecord(
            agent_name="TestAgent",
            model="gpt-4",
            tokens_in=100,
            tokens_out=200
        )
        
        assert record.agent_name == "TestAgent"
        assert record.model == "gpt-4"
        assert record.tokens_in == 100
        assert record.tokens_out == 200
        assert record.total_tokens == 0  # 需要手动设置或计算
    
    def test_to_dict(self):
        """测试转换为字典"""
        record = TokenUsageRecord(
            agent_name="TestAgent",
            model="gpt-4",
            tokens_in=100,
            tokens_out=200,
            success=True
        )
        
        data = record.to_dict()
        
        assert data["project_id"] == ""
        assert data["agent_name"] == "TestAgent"
        assert data["model"] == "gpt-4"
        assert data["tokens_in"] == 100
        assert data["tokens_out"] == 200
        assert data["success"] is True


class TestTokenUsageExtraction:
    """Token usage payload extraction tests."""

    def test_extract_token_usage_supports_total_only_payload(self):
        """测试仅返回 total_tokens 的兼容接口会按估算输入拆分输出。"""
        tokens_in, tokens_out = extract_token_usage(
            {"total_tokens": 120},
            fallback_tokens_in=80,
            fallback_tokens_out=20,
        )

        assert tokens_in == 80
        assert tokens_out == 40


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
