"""Tests for trends route tool mapping and normalization."""

import json

from fastapi.testclient import TestClient

from novel_agent.web.app import create_app
from novel_agent.web.routes import trends as trends_routes
from skills.trends_search.scripts import trends_service


class _FakeText:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, content=None, is_error: bool = False):
        self.content = content or []
        self.isError = is_error


class _FakeResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200):
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.headers = {"Content-Type": "application/json"}
        self.content = text.encode("utf-8") if text else json.dumps(payload or {}).encode("utf-8")

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("no json", self.text, 0)
        return self._payload


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


def test_trends_status_includes_packaging_diagnostics(monkeypatch, tmp_path):
    skill_path = tmp_path / "trends_search"
    (skill_path / "scripts").mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# 热点搜索", encoding="utf-8")
    (skill_path / "scripts" / "trends_service.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(trends_routes, "_get_skill_path", lambda _name: skill_path)
    monkeypatch.setattr(trends_routes, "_get_skill_service", lambda: object())

    client = TestClient(create_app())
    response = client.get("/api/trends/status")
    assert response.status_code == 200

    payload = response.json()
    assert payload["available"] is True
    assert payload["diagnostics"]["skill_exists"] is True
    assert payload["diagnostics"]["skill_md_exists"] is True
    assert payload["diagnostics"]["service_exists"] is True
    assert payload["diagnostics"]["required_dependencies"]["requests"] is True


def test_trends_service_json_platforms_work_without_bs4(monkeypatch):
    service = trends_service.TrendsSearchService()

    monkeypatch.setattr(trends_service, "BeautifulSoup", None)
    monkeypatch.setattr(
        service,
        "_make_request",
        lambda url, method="GET", headers=None, **kwargs: _FakeResponse(
            payload={
                "data": [
                    {"Title": "头条测试热点", "HotValue": 321, "Url": "https://example.com/toutiao"}
                ]
            }
        ),
    )

    result = service.get_toutiao_trending(limit=1)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["data"][0]["title"] == "头条测试热点"


def test_trends_service_html_platforms_return_clear_error_without_bs4(monkeypatch):
    service = trends_service.TrendsSearchService()

    monkeypatch.setattr(trends_service, "BeautifulSoup", None)
    monkeypatch.setattr(
        service,
        "_make_request",
        lambda url, method="GET", headers=None, **kwargs: _FakeResponse(
            payload=None,
            text="<html><body><a>test</a></body></html>",
        ),
    )

    result = service.get_baidu_trending(limit=1)

    assert result["success"] is False
    assert "beautifulsoup4" in result["error"]
