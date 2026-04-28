"""Bounded tool registry for the experimental agent runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent_runtime.models import ToolHandler, ToolResult, ToolSpec


@dataclass
class ToolRegistry:
    """In-memory registry for planner-safe experimental tools."""

    _tools: dict[str, tuple[ToolSpec, ToolHandler]] = field(default_factory=dict)

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Duplicate tool registered: {spec.name}")
        self._tools[spec.name] = (spec, handler)

    def get(self, name: str) -> ToolSpec | None:
        entry = self._tools.get(name)
        return None if entry is None else entry[0]

    def list_tools(self) -> tuple[ToolSpec, ...]:
        return tuple(entry[0] for entry in self._tools.values())

    def invoke(
        self,
        name: str,
        args: dict[str, object],
        *,
        planner_safe_only: bool = False,
    ) -> ToolResult:
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult.failure("unknown_tool")
        spec, handler = entry
        if planner_safe_only and not spec.safe_for_planner:
            return ToolResult.failure("planner_unsafe_tool")
        try:
            result = handler(dict(args))
        except Exception:
            return ToolResult.failure("handler_error")
        return ToolResult(
            ok=result.ok,
            result_summary=dict(result.result_summary),
            citations_count=result.citations_count,
            payload=result.payload,
            error=result.error,
        )
