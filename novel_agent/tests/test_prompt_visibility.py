from fastapi.testclient import TestClient

from novel_agent.prompts.prompt_manager import get_prompt_manager
from novel_agent.web.app import create_app


def test_prompt_manager_lists_only_user_visible_agents():
    agents = get_prompt_manager().list_agents()
    names = {item["name"] for item in agents}

    assert "communicator" in names
    assert "worldbuilder" in names
    assert "outliner" in names
    assert "continuous_writer" in names

    assert "ContextStrategy" not in names
    assert "ContentReader" not in names
    assert "FileNaming" not in names
    assert "SummaryOrchestrator" not in names


def test_prompt_manager_lists_advanced_agents_when_enabled():
    agents = get_prompt_manager().list_agents(include_advanced=True)
    names = {item["name"] for item in agents}

    assert "ContentExpansion" in names
    assert "SummaryOrchestrator" in names


def test_prompt_routes_reject_hidden_agents():
    client = TestClient(create_app())

    response = client.get("/api/v1/prompts/ContextStrategy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "不可访问" in payload["error"]

    visible = client.get("/api/v1/prompts/communicator")
    assert visible.status_code == 200


def test_prompt_routes_allow_advanced_agents_when_enabled():
    client = TestClient(create_app())

    response = client.get("/api/v1/prompts/SummaryOrchestrator?include_advanced=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
