"""Helpers for normalizing LLM request parameters."""

from __future__ import annotations

import logging
import re
from typing import Any, MutableMapping

from ..constants import LLM_DEFAULTS


logger = logging.getLogger(__name__)

PROVIDER_SAFE_MAX_TOKENS = 8192
_TEMPERATURELESS_MODEL_PATTERNS = (
    re.compile(r"claude-(?:opus|sonnet|haiku)-4", re.IGNORECASE),
    re.compile(r"claude-4", re.IGNORECASE),
)


def normalize_max_tokens(max_tokens: int | None, *, source: str = "LLM") -> int:
    """Clamp max_tokens to a provider-safe range and recover invalid values."""
    fallback = int(LLM_DEFAULTS.MAX_TOKENS)

    try:
        parsed = int(max_tokens if max_tokens is not None else fallback)
    except (TypeError, ValueError):
        logger.warning("[%s] Invalid max_tokens=%r, fallback to %s", source, max_tokens, fallback)
        return fallback

    if parsed < 1:
        logger.warning("[%s] Non-positive max_tokens=%s, fallback to %s", source, parsed, fallback)
        return fallback

    capped = min(parsed, PROVIDER_SAFE_MAX_TOKENS)
    if capped != parsed:
        logger.warning(
            "[%s] max_tokens=%s exceeds provider-safe limit, capped to %s",
            source,
            parsed,
            capped,
        )
    return capped


def should_omit_temperature_for_model(model: str) -> bool:
    """Return True when known model families reject explicit temperature."""
    model_name = str(model or "")
    return any(pattern.search(model_name) for pattern in _TEMPERATURELESS_MODEL_PATTERNS)


def add_temperature_param(
    params: MutableMapping[str, Any],
    *,
    model: str,
    temperature: float | None,
    source: str = "LLM",
) -> None:
    """Add temperature unless the selected model is known to reject it."""
    if should_omit_temperature_for_model(model):
        logger.info("[%s] Omit temperature for model=%s because the provider rejects this parameter.", source, model)
        return
    if temperature is not None:
        params["temperature"] = temperature


def is_temperature_parameter_error(error: Exception) -> bool:
    """Detect provider errors caused by unsupported/deprecated temperature."""
    error_text = str(error or "").lower()
    if "temperature" not in error_text:
        return False
    return any(
        token in error_text
        for token in (
            "deprecated",
            "unsupported",
            "not support",
            "not supported",
            "unknown",
            "unrecognized",
            "unexpected",
            "invalid",
            "not allowed",
        )
    )
