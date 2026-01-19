"""
提示词管理模块

包含：
- PromptManager: 提示词管理器
- SecurityGuard: 安全守卫（防止提示词泄露）
"""

from .prompt_manager import (
    PromptManager,
    get_prompt_manager,
    reload_prompts,
    get_system_prompt,
    get_task_prompt,
    render_prompt,
    check_user_input_security,
    get_security_response,
    DEFAULT_PROMPTS,
)

from .security_guard import (
    SecurityGuard,
    get_security_guard,
    inject_protocol,
    check_security,
    SECURITY_PROTOCOL,
    SECURITY_RESPONSE,
)

__all__ = [
    # 提示词管理
    'PromptManager',
    'get_prompt_manager',
    'reload_prompts',
    'get_system_prompt',
    'get_task_prompt',
    'render_prompt',
    'check_user_input_security',
    'get_security_response',
    'DEFAULT_PROMPTS',
    # 安全守卫
    'SecurityGuard',
    'get_security_guard',
    'inject_protocol',
    'check_security',
    'SECURITY_PROTOCOL',
    'SECURITY_RESPONSE',
]