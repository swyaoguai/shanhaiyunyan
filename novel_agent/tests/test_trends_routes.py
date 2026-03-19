"""Tests for trends route tool mapping and normalization."""

import json

from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.web.routes import trends as trends_routes


class _FakeText:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, content=None, is_error: bool = False):
        self.content = content or []
        self.isError = is_error


def test_trends_search_uses_underscore_tool_and_parses_xml(monkeypatch):
    def fake_get_service():
        class FakeService:
            def get_toutiao_trending(self, limit=10):
                return {
                    "success": True,
                    "platform": "toutiao",
                    "data": [
                        {"title": "测试热点A", "hot": "999", "url": "https://example.com/a"}
                    ]
                }
        return FakeService()

    monkeypatch.setattr(trends_routes, "_get_skill_service", fake_get_service)

    client = TestClient(create_app())
    response = client.post("/api/trends/search", json={"platform": "toutiao", "limit": 5})
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["trends"][0]["title"] == "测试热点A"
    assert payload["trends"][0]["hot"] == "999"
    assert payload["trends"][0]["url"] == "https://example.com/a"


def test_trends_search_returns_failure_when_all_tool_candidates_fail(monkeypatch):
    def fake_get_service():
        class FakeService:
            def get_douyin_trending(self, limit=10):
                return {"success": False, "error": "Method not found"}
        return FakeService()

    monkeypatch.setattr(trends_routes, "_get_skill_service", fake_get_service)

    client = TestClient(create_app())
    response = client.post("/api/trends/search", json={"platform": "douyin", "limit": 5})
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is False
    assert payload["trends"] == []


def test_trends_search_parses_json_payload(monkeypatch):
    def fake_get_service():
        class FakeService:
            def get_weibo_trending(self, limit=10):
                return {
                    "success": True,
                    "platform": "weibo",
                    "data": [
                        {"title": "测试热点B", "hotValue": 12345, "url": "https://example.com/b"}
                    ]
                }
        return FakeService()

    monkeypatch.setattr(trends_routes, "_get_skill_service", fake_get_service)

    client = TestClient(create_app())
    response = client.post("/api/trends/search", json={"platform": "weibo", "limit": 5})
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["trends"][0]["title"] == "测试热点B"
