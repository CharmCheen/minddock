"""Unit tests for the experimental agent runtime tool registry."""

import pytest

from app.agent_runtime import ToolRegistry, ToolResult, ToolSpec


def test_register_and_list_tools() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(name="search_kb", description="Search the knowledge base.")

    registry.register(spec, lambda args: ToolResult.success(result_summary={"ok": True}))

    assert registry.get("search_kb") == spec
    assert registry.list_tools() == (spec,)


def test_duplicate_tool_rejected() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(name="search_kb", description="Search the knowledge base.")
    registry.register(spec, lambda args: ToolResult.success())

    with pytest.raises(ValueError):
        registry.register(spec, lambda args: ToolResult.success())


def test_unknown_tool_returns_failure_result() -> None:
    result = ToolRegistry().invoke("missing_tool", {})

    assert result.ok is False
    assert result.error == "unknown_tool"


def test_planner_unsafe_tool_rejected_for_planner_safe_invocation() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="inspect_source_chunks", description="Inspect source chunks.", safe_for_planner=False),
        lambda args: ToolResult.success(result_summary={"called": True}),
    )

    result = registry.invoke("inspect_source_chunks", {}, planner_safe_only=True)

    assert result.ok is False
    assert result.error == "planner_unsafe_tool"


def test_handler_summary_is_sanitized_and_citation_count_preserved() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="search_kb", description="Search the knowledge base."),
        lambda args: ToolResult.success(
            result_summary={
                "message": "done",
                "count": 2,
                "nested": {"safe": True, "unsafe": object()},
                "items": ["a", object(), 3],
                "unsafe": object(),
            },
            citations_count=4,
            payload={"raw": "payload"},
        ),
    )

    result = registry.invoke("search_kb", {})

    assert result.ok is True
    assert result.citations_count == 4
    assert result.result_summary == {
        "message": "done",
        "count": 2,
        "nested": {"safe": True},
        "items": ("a", 3),
    }


def test_handler_exception_returns_stable_error_code() -> None:
    registry = ToolRegistry()

    def raises(_args):
        raise RuntimeError("secret stack trace details")

    registry.register(ToolSpec(name="search_kb", description="Search the knowledge base."), raises)

    result = registry.invoke("search_kb", {})

    assert result.ok is False
    assert result.error == "handler_error"
    assert "secret" not in str(result)
