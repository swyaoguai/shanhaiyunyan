"""Local runtime hook registry for the multi-agent dispatcher."""

from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional


RuntimeHook = Callable[[Dict[str, Any], "RuntimeHookContext"], Any | Awaitable[Any]]


@dataclass
class RuntimeHookContext:
    """Small, serializable context object passed to local trusted hooks."""

    stage: str
    project_dir: str = ""
    task_id: str = ""
    task_type: str = ""
    agent_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeHookRegistry:
    """In-process hook registry.

    The first version deliberately accepts only Python callables registered by
    project code. It does not load external scripts or hot-reload extensions.
    """

    def __init__(self) -> None:
        self._hooks: Dict[str, List[RuntimeHook]] = {}

    def register(self, stage: str, hook: RuntimeHook) -> None:
        normalized_stage = str(stage or "").strip()
        if not normalized_stage:
            raise ValueError("stage is required")
        if not callable(hook):
            raise TypeError("hook must be callable")
        self._hooks.setdefault(normalized_stage, []).append(hook)

    def clear(self, stage: Optional[str] = None) -> None:
        if stage is None:
            self._hooks.clear()
            return
        self._hooks.pop(str(stage or "").strip(), None)

    def list_stages(self) -> List[str]:
        return sorted(self._hooks.keys())

    async def run(
        self,
        stage: str,
        event: Dict[str, Any],
        context: RuntimeHookContext,
    ) -> List[Any]:
        results: List[Any] = []
        for hook in list(self._hooks.get(str(stage or "").strip(), [])):
            result = hook(dict(event or {}), context)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results


_runtime_hook_registry = RuntimeHookRegistry()


def get_runtime_hook_registry() -> RuntimeHookRegistry:
    return _runtime_hook_registry


def make_runtime_hook_context(
    *,
    stage: str,
    project_dir: Path | str = "",
    task_id: str = "",
    task_type: str = "",
    agent_name: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> RuntimeHookContext:
    return RuntimeHookContext(
        stage=str(stage or "").strip(),
        project_dir=str(project_dir or ""),
        task_id=str(task_id or "").strip(),
        task_type=str(task_type or "").strip(),
        agent_name=str(agent_name or "").strip(),
        metadata=dict(metadata or {}),
    )
