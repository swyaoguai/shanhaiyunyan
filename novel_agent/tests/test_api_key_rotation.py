import time

from novel_agent.agent_config import APIKeyEntry, APIConfigItem
from novel_agent.agents.api_key_rotation import (
    APIKeyRotationService,
    KeyUseResult,
    classify_key_error,
)


class _StatusError(Exception):
    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message or str(status_code))
        self.status_code = status_code


def test_api_config_item_migrates_legacy_key_to_key_pool():
    cfg = APIConfigItem(
        id="cfg",
        name="legacy",
        api_base="https://example.com/v1",
        api_key="sk-legacy",
        models=["demo"],
    )

    assert cfg.get_primary_key() == "sk-legacy"
    assert cfg.get_enabled_key_entries()[0].id == "legacy"
    public = cfg.to_dict()
    assert public["api_keys"][0]["key_preview"] == "sk-legac****"
    assert "sk-legacy" not in str(public)


def test_rotation_round_robin_and_exclude():
    service = APIKeyRotationService()
    entries = [
        APIKeyEntry(id="a", key="key-a"),
        APIKeyEntry(id="b", key="key-b"),
        APIKeyEntry(id="c", key="key-c"),
    ]

    assert service.get_next_key("cfg", entries).id == "a"
    assert service.get_next_key("cfg", entries).id == "b"
    assert service.get_next_key("cfg", entries, exclude_key_ids={"c"}).id == "a"


def test_rotation_disables_auth_failure_and_cools_rate_limit():
    service = APIKeyRotationService()
    entries = [
        APIKeyEntry(id="bad", key="bad-key"),
        APIKeyEntry(id="slow", key="slow-key"),
        APIKeyEntry(id="good", key="good-key"),
    ]

    service.report_key_result("cfg", "bad", KeyUseResult.AUTH_FAILURE, "401")
    service.report_key_result("cfg", "slow", KeyUseResult.RATE_LIMITED, "429")

    assert service.get_next_key("cfg", entries).id == "good"

    slow_state = service.get_state("cfg", "slow")
    slow_state.disabled_until = time.time() - 1

    assert service.get_next_key("cfg", entries).id == "slow"


def test_network_error_does_not_disable_key():
    service = APIKeyRotationService()
    service.report_key_result("cfg", "a", KeyUseResult.NETWORK_ERROR, "timeout")
    state = service.get_state("cfg", "a")

    assert state.permanently_disabled is False
    assert state.disabled_until == 0
    assert state.failure_count == 0


def test_classify_key_error_status_codes():
    assert classify_key_error(_StatusError(401)) == KeyUseResult.AUTH_FAILURE
    assert classify_key_error(_StatusError(403)) == KeyUseResult.FORBIDDEN
    assert classify_key_error(_StatusError(429)) == KeyUseResult.RATE_LIMITED
    assert classify_key_error(_StatusError(500)) == KeyUseResult.SERVER_ERROR
    assert classify_key_error(Exception("insufficient_quota")) == KeyUseResult.QUOTA_EXHAUSTED
