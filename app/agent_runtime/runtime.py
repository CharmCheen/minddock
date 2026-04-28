"""Execution shell for the isolated experimental agent runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent_runtime.models import (
    AgentRunRequest,
    AgentRunResult,
    AgentStep,
    AgentTrace,
    JsonSafeValue,
)
from app.agent_runtime.planner import RuleBasedPlanner, clamp_max_steps
from app.agent_runtime.tool_registry import ToolRegistry


@dataclass(frozen=True)
class AgentRuntime:
    """Bounded tool-execution shell with no service wiring."""

    registry: ToolRegistry
    planner: RuleBasedPlanner = RuleBasedPlanner()

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        max_steps = clamp_max_steps(request.max_steps)
        planned_steps = self.planner.plan(request, self.registry)
        if max_steps <= 0 or not planned_steps:
            return self._result(
                planned_steps=planned_steps,
                stop_reason="no_plan",
                fallback_to_fixed_workflow=True,
            )

        steps: list[AgentStep] = []
        executed_tools: list[str] = []
        final_payload: object | None = None
        stop_reason = "completed"
        fallback_to_fixed_workflow = False

        for step_index, tool_name in enumerate(planned_steps[:max_steps], start=1):
            args_summary = self._args_summary(request)
            result = self.registry.invoke(tool_name, dict(args_summary), planner_safe_only=True)
            executed_tools.append(tool_name)
            final_payload = result.payload if result.ok else None
            step_stop_reason = None if result.ok else "tool_failed"
            steps.append(
                AgentStep(
                    step_index=step_index,
                    tool_name=tool_name,
                    args_summary=args_summary,
                    result_summary=dict(result.result_summary),
                    citations_count=result.citations_count,
                    stop_reason=step_stop_reason,
                )
            )
            if not result.ok:
                stop_reason = "tool_failed"
                fallback_to_fixed_workflow = True
                break

        if len(planned_steps) > max_steps and stop_reason == "completed":
            stop_reason = "max_steps_reached"

        return self._result(
            planned_steps=planned_steps,
            executed_tools=tuple(executed_tools),
            stop_reason=stop_reason,
            fallback_to_fixed_workflow=fallback_to_fixed_workflow,
            steps=tuple(steps),
            artifact=final_payload,
        )

    @staticmethod
    def _args_summary(request: AgentRunRequest) -> dict[str, JsonSafeValue]:
        return {
            "query": request.query,
            "task_type": request.task_type,
            "selected_sources": tuple(request.selected_sources),
            "selected_sources_count": len(request.selected_sources),
        }

    @staticmethod
    def _result(
        *,
        planned_steps: tuple[str, ...],
        stop_reason: str,
        fallback_to_fixed_workflow: bool,
        executed_tools: tuple[str, ...] = (),
        steps: tuple[AgentStep, ...] = (),
        artifact: object | None = None,
    ) -> AgentRunResult:
        trace = AgentTrace(
            planned_steps=planned_steps,
            executed_tools=executed_tools,
            tool_call_count=len(executed_tools),
            stop_reason=stop_reason,
            fallback_to_fixed_workflow=fallback_to_fixed_workflow,
            steps=steps,
        )
        return AgentRunResult(
            artifact=artifact,
            agent_trace=trace,
            fallback_to_fixed_workflow=fallback_to_fixed_workflow,
        )
