"""
Deprecated prompt security compatibility module.

Project prompts are public and configurable, so prompt-protection instructions
are no longer injected into model requests and prompt-related user questions
are no longer blocked locally.
"""

from typing import List, Optional, Tuple


SECURITY_PROTOCOL = ""
SECURITY_RESPONSE = ""


class SecurityGuard:
    """No-op compatibility wrapper for older imports."""

    def __init__(self):
        self.compiled_patterns: List[object] = []

    def detect_threat(self, user_input: str) -> Tuple[bool, Optional[str]]:
        return False, None

    def get_security_response(self) -> str:
        return SECURITY_RESPONSE

    def inject_security_protocol(self, system_prompt: str) -> str:
        return system_prompt

    def filter_user_message(self, user_message: str) -> Tuple[str, bool]:
        return user_message, False

    def add_custom_patterns(self, patterns: List[str], category: str = "custom"):
        return None


_security_guard: Optional[SecurityGuard] = None


def get_security_guard() -> SecurityGuard:
    global _security_guard
    if _security_guard is None:
        _security_guard = SecurityGuard()
    return _security_guard


def check_security(user_input: str) -> Tuple[bool, str]:
    return True, user_input


def inject_protocol(system_prompt: str) -> str:
    return system_prompt


__all__ = [
    "SecurityGuard",
    "SECURITY_PROTOCOL",
    "SECURITY_RESPONSE",
    "get_security_guard",
    "check_security",
    "inject_protocol",
]
