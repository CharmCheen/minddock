"""Minimal models for the experimental agent runtime skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

JsonPrimitive = str | int | float | bool | None
JsonSafeValue = JsonPrimitive | tuple["JsonSafeValue", ...] | dict[str, "JsonSafeValue"]


def sanitize_summary(value: object) -> JsonSafeValue | None:
    """Return a JSON-safe shallow summary, omitting unsupported objects."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        sanitized: dict[str, JsonSafeValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            safe_item = sanitize_summary(item)
            if safe_item is not None or item is None:
                sanitized[key] = safe_item
        return sanitized
    if isinstance(value, (list, tuple)):
        sanitized_items: list[JsonSafeValue] = []
        for item in value:
            safe_item = sanitize_summary(item)
            if safe_item is not None or item is None:
                sanitized_items.append(safe_item)
        return tuple(sanitized_items)
    return None


def sanitize_summary_mapping(value: dict[str, object] | None) -> dict[str, JsonSafeValue]:
    """Sanitize a summary mapping without stringifying unsupported values."""

    result: dict[str, JsonSafeValue] = {}
    for key, item in dict(value or {}).items():
        if not isinstance(key, str):
            continue
        safe_item = sanitize_summary(item)
        if safe_item is not None or item is None:
            result[key] = safe_item
    return result


@dataclass(frozen=True)
class AgentRunRequest:
    """Input for one bounded experimental agent runtime run."""

    query: str
    task_type: str | None = None
    filters: object | None = None
    max_steps: int = 3
    allow_llm_planner: bool = False
    selected_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentStep:
    """Sanitized record for one agent tool invocation."""

    step_index: int
    tool_name: str
    args_summary: dict[str, JsonSafeValue] = field(default_factory=dict)
    result_summary: dict[str, JsonSafeValue] = field(default_factory=dict)
    citations_count: int = 0
    stop_reason: str | None = None


@dataclass(frozen=True)
class AgentTrace:
    """Frontend-safe execution trace for the experimental agent runtime."""

    agent_mode: bool = True
    planned_steps: tuple[str, ...] = ()
    executed_tools: tuple[str, ...] = ()
    tool_call_count: int = 0
    stop_reason: str = "not_started"
    fallback_to_fixed_workflow: bool = False
    reflection_triggered: bool = False
    steps: tuple[AgentStep, ...] = ()


@dataclass(frozen=True)
class AgentRunResult:
    """Output from the isolated experimental agent runtime shell."""

    answer: str | None = None
    artifact: object | None = None
    citations: tuple[object, ...] = ()
    workflow_trace: dict[str, object] = field(default_factory=dict)
    agent_trace: AgentTrace = field(default_factory=AgentTrace)
    fallback_to_fixed_workflow: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Static metadata for one bounded agent runtime tool."""

    name: str
    description: str
    safe_for_planner: bool = True


@dataclass(frozen=True)
class ToolResult:
    """Result returned by a bounded agent runtime tool."""

    ok: bool
    result_summary: dict[str, JsonSafeValue] = field(default_factory=dict)
    citations_count: int = 0
    payload: object | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_summary", sanitize_summary_mapping(self.result_summary))

    @classmethod
    def success(
        cls,
        *,
        result_summary: dict[str, object] | None = None,
        citations_count: int = 0,
        payload: object | None = None,
    ) -> "ToolResult":
        return cls(
            ok=True,
            result_summary=sanitize_summary_mapping(result_summary),
            citations_count=citations_count,
            payload=payload,
        )

    @classmethod
    def failure(cls, error: str, *, result_summary: dict[str, object] | None = None) -> "ToolResult":
        return cls(ok=False, error=error, result_summary=sanitize_summary_mapping(result_summary))


ToolHandler = Callable[[dict[str, object]], ToolResult]
