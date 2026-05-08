"""Rate limit middleware path policy tests."""

from unittest.mock import MagicMock

from novel_agent.web.middleware.rate_limit import RateLimitMiddleware
from novel_agent.settings import RateLimitSettings


def test_rate_limit_skips_versioned_read_only_ui_paths():
    """Versioned read-only UI endpoints should not trigger page-switch cooldowns."""
    middleware = RateLimitMiddleware(MagicMock())

    assert middleware._should_skip("/api/v1/knowledge-base/config", "GET") is True
    assert middleware._should_skip("/api/v1/knowledge-base/stats", "GET") is True
    assert middleware._should_skip("/api/v1/project-data/characters", "GET") is True
    assert middleware._should_skip("/api/v1/token-stats/summary", "GET") is True


def test_rate_limit_keeps_writes_and_llm_paths_limited():
    """Writes and LLM execution endpoints should remain rate limited."""
    middleware = RateLimitMiddleware(MagicMock())

    assert middleware._should_skip("/api/v1/knowledge-base/config", "POST") is False
    assert middleware._should_skip("/api/v1/chat", "POST") is False
    assert middleware._is_strict_path("/api/v1/chat") is True
    assert middleware._is_strict_path("/api/v1/continuous-write/start") is True


def test_rate_limit_settings_default_to_local_disabled():
    """Local desktop usage should not enable HTTP request throttling by default."""
    settings = RateLimitSettings(_env_file=None)

    assert settings.enabled is False
