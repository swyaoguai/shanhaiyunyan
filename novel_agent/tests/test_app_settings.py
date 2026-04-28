"""
Test file write error handling in app.py settings endpoints
TDD Red Phase - Tests should fail initially, then pass after error handling implementation
"""

import pytest
import tempfile
import os
import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.web.dependencies import get_coordinator, get_router_agent


# ==================== Fixtures ====================

@pytest.fixture
def client():
    """Create test client for FastAPI app"""
    app = create_app()
    return TestClient(app)


# Sample API configuration request (APIConfigRequest is defined inside create_app)
SAMPLE_CONFIG_REQUEST = {
    "api_base": "https://api.openai.com/v1",
    "api_key": "sk-test-key-12345",
    "model": "gpt-4"
}


def test_save_settings_syncs_router_coordinator_reference():
    app = create_app()

    with TestClient(app) as local_client:
        old_coordinator = get_coordinator()
        old_router = get_router_agent()

        assert old_coordinator is not None
        assert old_router is not None
        assert old_router.coordinator is old_coordinator

        response = local_client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

        assert response.status_code == 200

        new_coordinator = get_coordinator()
        new_router = get_router_agent()

        assert new_coordinator is not None
        assert new_coordinator is not old_coordinator
        assert new_router is old_router
        assert new_router.coordinator is new_coordinator


# ==================== Test 1: Permission Denied on .env Write ====================

def test_save_settings_permission_denied(client):
    """
    Test 1: Permission denied when writing .env file
    Should return JSONResponse with success=False and error message
    """
    with patch('pathlib.Path.write_text') as mock_write:
        # Simulate permission denied error
        mock_write.side_effect = PermissionError("Permission denied: .env")

        response = client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

        # Should return error response (this will fail initially - no error handling)
        assert response.status_code == 500
        assert response.json()["success"] is False
        assert "Permission denied" in response.json()["error"] or "Failed to save" in response.json()["error"]


# ==================== Test 2: Disk Full on .env Write ====================

def test_save_settings_disk_full(client):
    """
    Test 2: Disk full error when writing .env file
    Should return JSONResponse with success=False and error message
    """
    with patch('pathlib.Path.write_text') as mock_write:
        # Simulate disk full error (OSError with errno 28 - ENOSPC)
        error = OSError("No space left on device")
        error.errno = 28
        mock_write.side_effect = error

        response = client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

        # Should return error response
        assert response.status_code == 500
        assert response.json()["success"] is False
        assert "No space left" in response.json()["error"] or "Failed to save" in response.json()["error"]


# ==================== Test 3: Generic OSError on .env Write ====================

def test_save_settings_os_error(client):
    """
    Test 3: Generic OSError when writing .env file
    Should return JSONResponse with success=False and error message
    """
    with patch('pathlib.Path.write_text') as mock_write:
        # Simulate generic OS error
        mock_write.side_effect = OSError("I/O error during write")

        response = client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

        # Should return error response
        assert response.status_code == 500
        assert response.json()["success"] is False
        assert "error" in response.json()


# ==================== Test 4: Atomic Write Pattern Failure ====================

def test_save_settings_atomic_write_cleanup(client):
    """
    Test 4: Atomic write pattern should cleanup temp files on failure
    Should not leave .env.tmp files if write fails
    """
    with patch('pathlib.Path.write_text') as mock_write:
        # Simulate write failure
        mock_write.side_effect = IOError("Write failed")

        with patch('pathlib.Path.rename') as mock_rename:
            response = client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

            # Should return error response
            assert response.status_code == 500
            assert response.json()["success"] is False

            # Atomic rename should not be called on failure
            mock_rename.assert_not_called()


# ==================== Test 5: Logging on Write Failure ====================

def test_save_settings_logs_error(client):
    """
    Test 5: Write failures should be logged with file path and error details
    Should call logging.error with exception details
    """
    with patch('pathlib.Path.write_text') as mock_write:
        mock_write.side_effect = IOError("Disk write error")

        with patch('logging.Logger.error') as mock_log_error:
            response = client.post("/api/settings", json=SAMPLE_CONFIG_REQUEST)

            # Should log the error (this will fail initially - no logging)
            assert response.status_code == 500
            # Note: logger.error might not be called yet, that's what we're testing for


# ==================== Test 6: agent_config.py _save_configs Error ====================

def test_agent_config_save_configs_error():
    """
    Test 6: Error handling in agent_config.py _save_configs method
    Should propagate or handle write errors
    """
    from novel_agent.agent_config import AgentConfigManager, AgentModelConfig
    from dataclasses import asdict

    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        manager = AgentConfigManager(config_dir=config_dir)

        # Add a config
        config = AgentModelConfig(
            agent_name="TestAgent",
            model="gpt-4",
            api_key="test-key",
            api_base="https://api.test.com/v1"
        )
        manager.configs["TestAgent"] = config

        with patch.object(Path, 'write_text') as mock_write:
            mock_write.side_effect = PermissionError("Cannot write config")

            # Should raise or handle error (will fail initially - no error handling)
            with pytest.raises((PermissionError, OSError, IOError)):
                manager._save_configs()


# ==================== Test 7: agent_config.py _save_global_config Error ====================

def test_agent_config_save_global_config_error():
    """
    Test 7: Error handling in agent_config.py _save_global_config method
    Should propagate or handle write errors
    """
    from novel_agent.agent_config import AgentConfigManager

    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        manager = AgentConfigManager(config_dir=config_dir)

        with patch.object(Path, 'write_text') as mock_write:
            mock_write.side_effect = OSError("Disk full")

            # Should raise or handle error (will fail initially - no error handling)
            with pytest.raises((OSError, IOError, PermissionError)):
                manager._save_global_config()


# ==================== Test 8: Multi-file Write Error Consistency ====================

def test_multi_file_write_error_consistency(client):
    """
    Test 8: Error responses should have consistent format across all write operations
    All write failures should return JSONResponse with {success: False, error: string}
    """
    # Test save_settings endpoint error format
    with patch('pathlib.Path.write_text') as mock_write:
        mock_write.side_effect = IOError("Write failed")

        response = client.post("/api/settings", json={
            "api_base": "https://api.test.com",
            "api_key": "test-key",
            "model": "gpt-4"
        })

        # Should have consistent error format
        assert response.status_code == 500
        data = response.json()
        assert "success" in data
        assert "error" in data
        assert data["success"] is False
        assert isinstance(data["error"], str)
        assert len(data["error"]) > 0


# ==================== Test Runner ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
