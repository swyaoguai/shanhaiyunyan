"""Helpers for normalizing LLM request parameters."""

from __future__ import annotations

import logging

from ..constants import LLM_DEFAULTS


logger = logging.getLogger(__name__)

PROVIDER_SAFE_MAX_TOKENS = 8192


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
