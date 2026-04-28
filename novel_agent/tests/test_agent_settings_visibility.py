from novel_agent.agent_config import get_config_manager
from novel_agent.web.app import create_app
from fastapi.testclient import TestClient


def test_agent_config_manager_lists_only_user_visible_agents_by_default():
    manager = get_config_manager()
    agents = manager.list_agents()
    names = {item["name"] for item in agents}

    assert "Communicator" in names
    assert "Worldbuilder" in names
    assert "Outliner" in names
    assert "CharacterBuilder" in names

    assert "ContentExpansion" not in names
    assert "SummaryOrchestrator" not in names


def test_agent_config_manager_lists_advanced_agents_when_enabled():
    manager = get_config_manager()
    agents = manager.list_agents(include_advanced=True)
    names = {item["name"] for item in agents}

    assert "ContentExpansion" in names
    assert "SummaryOrchestrator" in names


def test_agents_route_supports_advanced_toggle():
    client = TestClient(create_app())

    default_response = client.get("/api/v1/agents")
    assert default_response.status_code == 200
    default_names = {item["name"] for item in default_response.json()["agents"]}
    assert "ContentExpansion" not in default_names

    advanced_response = client.get("/api/v1/agents?include_advanced=true")
    assert advanced_response.status_code == 200
    advanced_names = {item["name"] for item in advanced_response.json()["agents"]}
    assert "ContentExpansion" in advanced_names
