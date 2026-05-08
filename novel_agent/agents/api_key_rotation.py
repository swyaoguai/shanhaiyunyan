"""Runtime API key rotation for OpenAI-compatible providers."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Set

import httpx

from ..agent_config import APIKeyEntry

logger = logging.getLogger(__name__)


class KeyUseResult(str, Enum):
    SUCCESS = "success"
    AUTH_FAILURE = "auth_failure"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class KeyRuntimeState:
    failure_count: int = 0
    disabled_until: float = 0.0
    permanently_disabled: bool = False
    last_error: str = ""
    last_used_at: float = 0.0
    last_result: str = ""

    def is_in_cooldown(self, now: Optional[float] = None) -> bool:
        return bool(self.disabled_until and self.disabled_until > (now or time.time()))


def is_api_key_rotation_enabled() -> bool:
    """Feature flag for rollout safety."""
    value = os.getenv("ENABLE_API_KEY_ROTATION", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def preview_key(key: str) -> str:
    if not key:
        return ""
    return key[:8] + "****" if len(key) > 8 else "****"


class APIKeyRotationService:
    """In-memory key selection and health tracking."""

    def __init__(self) -> None:
        self._states: Dict[str, Dict[str, KeyRuntimeState]] = {}
        self._cursors: Dict[str, int] = {}

    def reset(self) -> None:
        self._states.clear()
        self._cursors.clear()

    def get_state(self, config_id: str, key_id: str) -> KeyRuntimeState:
        return self._states.setdefault(config_id, {}).setdefault(key_id, KeyRuntimeState())

    def get_next_key(
        self,
        config_id: str,
        entries: Iterable[APIKeyEntry],
        exclude_key_ids: Optional[Set[str]] = None,
    ) -> Optional[APIKeyEntry]:
        """Return the next healthy key using round-robin order."""
        key_entries = [entry for entry in entries if entry and entry.key and entry.is_enabled]
        if not key_entries:
            return None

        excluded = set(exclude_key_ids or set())
        now = time.time()
        candidates = []
        for entry in key_entries:
            if entry.id in excluded:
                continue
            state = self.get_state(config_id, entry.id)
            if state.permanently_disabled or state.is_in_cooldown(now):
                continue
            candidates.append(entry)

        if not candidates:
            return None

        cursor = self._cursors.get(config_id, 0)
        selected = candidates[cursor % len(candidates)]
        self._cursors[config_id] = (cursor + 1) % max(len(candidates), 1)

        state = self.get_state(config_id, selected.id)
        state.last_used_at = now
        return selected

    def report_key_result(
        self,
        config_id: str,
        key_id: str,
        result: KeyUseResult,
        error: Optional[BaseException | str] = None,
    ) -> KeyRuntimeState:
        state = self.get_state(config_id, key_id)
        state.last_result = result.value
        state.last_error = str(error or "")[:500]

        if result == KeyUseResult.SUCCESS:
            state.failure_count = 0
            state.disabled_until = 0.0
            state.permanently_disabled = False
            state.last_error = ""
            return state

        if result in {
            KeyUseResult.AUTH_FAILURE,
            KeyUseResult.FORBIDDEN,
            KeyUseResult.QUOTA_EXHAUSTED,
        }:
            state.failure_count += 1
            state.permanently_disabled = True
            return state

        if result == KeyUseResult.RATE_LIMITED:
            state.failure_count += 1
            state.disabled_until = time.time() + 60
            return state

        if result == KeyUseResult.SERVER_ERROR:
            state.failure_count += 1
            cooldown = 300 if state.failure_count >= 2 else 60
            state.disabled_until = time.time() + cooldown
            return state

        if result == KeyUseResult.NETWORK_ERROR:
            # Network errors are recorded for diagnostics but do not punish keys.
            return state

        state.failure_count += 1
        return state

    def health_snapshot(self, config_id: str) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        snapshot: Dict[str, Dict[str, Any]] = {}
        for key_id, state in self._states.get(config_id, {}).items():
            snapshot[key_id] = {
                "failure_count": state.failure_count,
                "cooldown_seconds": max(0, int(state.disabled_until - now)) if state.disabled_until else 0,
                "permanently_disabled": state.permanently_disabled,
                "last_error": state.last_error,
                "last_used_at": state.last_used_at,
                "last_result": state.last_result,
            }
        return snapshot


def _status_code_from_error(error: BaseException) -> Optional[int]:
    for attr in ("status_code", "status"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_key_error(error: BaseException) -> KeyUseResult:
    """Classify provider errors into key health outcomes."""
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return KeyUseResult.NETWORK_ERROR

    error_type = type(error).__name__.lower()
    error_text = str(error or "").lower()
    status_code = _status_code_from_error(error)

    if "timeout" in error_type or "timeout" in error_text:
        return KeyUseResult.NETWORK_ERROR
    if "connection" in error_type or "connect" in error_text or "dns" in error_text:
        return KeyUseResult.NETWORK_ERROR

    if status_code == 401:
        return KeyUseResult.AUTH_FAILURE
    if status_code == 403:
        return KeyUseResult.FORBIDDEN
    if status_code == 429:
        return KeyUseResult.RATE_LIMITED
    if status_code == 402:
        return KeyUseResult.QUOTA_EXHAUSTED
    if status_code and 500 <= status_code <= 599:
        return KeyUseResult.SERVER_ERROR

    if any(marker in error_text for marker in ("insufficient_quota", "quota exhausted", "billing", "quota")):
        return KeyUseResult.QUOTA_EXHAUSTED
    if "rate limit" in error_text or "too many requests" in error_text:
        return KeyUseResult.RATE_LIMITED
    if "unauthorized" in error_text or "invalid api key" in error_text or "invalid_api_key" in error_text:
        return KeyUseResult.AUTH_FAILURE
    if "forbidden" in error_text or "permission denied" in error_text:
        return KeyUseResult.FORBIDDEN

    return KeyUseResult.UNKNOWN


_rotation_service: Optional[APIKeyRotationService] = None


def get_api_key_rotation_service() -> APIKeyRotationService:
    global _rotation_service
    if _rotation_service is None:
        _rotation_service = APIKeyRotationService()
    return _rotation_service
