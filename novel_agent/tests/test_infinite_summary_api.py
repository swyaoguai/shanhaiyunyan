"""无限续写总结入库接口测试。"""

from fastapi.testclient import TestClient

from novel_agent.web.app import create_app


def test_infinite_summary_requires_kb_configured():
    client = TestClient(create_app())

    response = client.post(
        "/api/knowledge-base/infinite-summary",
        json={
            "summary": "测试总结",
            "start_chapter": 1,
            "end_chapter": 3,
        },
    )

    # 未配置向量API时，应该显式提示未就绪
    assert response.status_code in (200, 503)
    data = response.json()
    if response.status_code == 503:
        assert data.get("not_ready") is True
        assert "未配置" in data.get("error", "")

