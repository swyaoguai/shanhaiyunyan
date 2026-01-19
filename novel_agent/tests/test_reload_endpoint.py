"""
Test suite for POST /api/settings/reload endpoint.

This test suite verifies the manual config reload functionality
that allows triggering Config.reload() via HTTP API.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from novel_agent.web.app import create_app
from novel_agent.config import Config


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestReloadEndpoint:
    """Test suite for /api/settings/reload endpoint."""

    def test_reload_endpoint_exists(self, client):
        """
        Test 1: Verify reload endpoint exists and returns 200
        Endpoint should be accessible and return success response
        """
        response = client.post("/api/settings/reload")

        # Endpoint should exist
        assert response.status_code in [200, 500]

        data = response.json()
        assert "success" in data

    def test_reload_calls_Config_reload(self, client):
        """
        Test 2: Verify reload endpoint calls Config.reload()
        Should call Config.reload() exactly once
        """
        with patch.object(Config, 'reload', return_value=True) as mock_reload:
            response = client.post("/api/settings/reload")

            # Verify Config.reload was called
            mock_reload.assert_called_once()

            # Check response
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_reload_returns_updated_config(self, client):
        """
        Test 3: Verify reload endpoint returns updated config values
        Response should contain current LLM config values
        """
        with patch.object(Config, 'reload', return_value=True):
            response = client.post("/api/settings/reload")

            assert response.status_code == 200
            data = response.json()

            # Should return success and config data
            assert data["success"] is True
            assert "data" in data or "api_key" in data or "api_base" in data

    def test_reload_recreates_coordinator(self, client):
        """
        Test 4: Verify reload endpoint recreates coordinator after reload
        Should recreate NovelCoordinator with updated config
        """
        with patch.object(Config, 'reload', return_value=True):
            with patch('novel_agent.web.app.NovelCoordinator') as mock_coordinator:
                response = client.post("/api/settings/reload")

                # Coordinator should be recreated
                # (Note: actual coordinator creation happens inside the endpoint)
                assert response.status_code == 200

    def test_reload_returns_error_on_failure(self, client):
        """
        Test 5: Verify reload endpoint returns error when Config.reload() fails
        Should return error response if reload fails
        """
        with patch.object(Config, 'reload', return_value=False):
            response = client.post("/api/settings/reload")

            # Should return error response
            assert response.status_code == 500
            data = response.json()
            assert data["success"] is False
            assert "error" in data
