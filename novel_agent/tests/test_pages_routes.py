from fastapi.testclient import TestClient

from novel_agent.web.app import create_app


def test_index_page_renders_successfully():
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
