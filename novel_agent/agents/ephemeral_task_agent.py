"""Task-scoped temporary agent used for emergency routing gaps."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional
from uuid import uuid4

from .base_agent import AgentCapability, BaseAgent


class EphemeralTaskAgent(BaseAgent):
    """A short-lived agent that is registered for exactly one task dispatch."""

    def __init__(
        self,
        *,
        task_type: str,
        stage: str = "",
        title: str = "",
        reason: str = "",
    ) -> None:
        self.task_type = str(task_type or "ad_hoc_task").strip() or "ad_hoc_task"
        self.stage = str(stage or "").strip()
        self.title = str(title or self.task_type).strip()
        self.reason = str(reason or "").strip()
        safe_task = re.sub(r"[^A-Za-z0-9_]+", "_", self.task_type).strip("_") or "task"
        self.instance_id = uuid4().hex[:8]
        super().__init__(
            name=f"Ephemeral_{safe_task}_{self.instance_id}",
            prompt_file=None,
        )

    def _get_default_prompt(self) -> str:
        return (
            "你是一个任务级临时Agent，只处理当前明确分派的突发任务。"
            "你必须保持范围克制，优先给出可验证、可回退的结果；"
            "不要自行扩大任务范围，不要假装已经修改文件。"
        )

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_name=self.name,
            capabilities=["task_scoped_recovery", self.task_type],
            accept_task_types=[self.task_type],
            required_inputs=[],
            produced_outputs=["response", "analysis"],
            priority=5,
            max_concurrency=1,
            metadata={
                "route_target_kind": "ephemeral_agent",
                "display_name": "临时任务助手",
                "purpose": "在没有可用固定路由目标时完成一次性补位处理",
                "risk_level": "task_scoped",
                "visibility": "internal",
                "execution_backend": self.__class__.__name__,
                "lifecycle": "task_scoped",
                "stage": self.stage,
                "reason": self.reason,
            },
        )

    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "task_type": self.task_type,
            "stage": self.stage,
            "title": self.title,
            "reason": self.reason,
            "input_data": input_data or {},
            "context_keys": sorted((context or {}).keys()) if isinstance(context, dict) else [],
        }
        prompt = (
            "请处理以下一次性突发任务，输出 JSON，字段包括 success、response、analysis。\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        response = await self.call_llm(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = str(response or "").strip()
        return {
            "success": True,
            "agent": self.name,
            "response": text,
            "analysis": text,
            "ephemeral": True,
        }
