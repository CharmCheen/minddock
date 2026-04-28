"""Deterministic planner for the experimental agent runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent_runtime.models import AgentRunRequest
from app.agent_runtime.tool_registry import ToolRegistry

MAX_AGENT_STEPS = 3


def clamp_max_steps(max_steps: int) -> int:
    return min(max(max_steps, 0), MAX_AGENT_STEPS)


@dataclass(frozen=True)
class RuleBasedPlanner:
    """Small deterministic planner that selects one safe tool."""

    def plan(self, request: AgentRunRequest, registry: ToolRegistry) -> tuple[str, ...]:
        if clamp_max_steps(request.max_steps) <= 0:
            return ()

        task_type = (request.task_type or "").strip().lower()
        if task_type == "compare" or len(request.selected_sources) >= 2:
            preferred = "compare_sources"
        elif task_type == "summarize":
            preferred = "summarize_sources"
        else:
            preferred = "chat_with_evidence"

        if self._planner_safe(registry, preferred):
            return (preferred,)
        if self._planner_safe(registry, "search_kb"):
            return ("search_kb",)
        return ()

    @staticmethod
    def _planner_safe(registry: ToolRegistry, name: str) -> bool:
        spec = registry.get(name)
        return spec is not None and spec.safe_for_planner is True
