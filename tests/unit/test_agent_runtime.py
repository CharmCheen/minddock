"""Unit tests for the experimental agent runtime shell."""

import sys

from app.agent_runtime import AgentRunRequest, AgentRuntime, ToolRegistry, ToolResult, ToolSpec
from app.agent_runtime.tools import build_stub_tool_registry

FORBIDDEN_STUB_TRACE_KEYS = {
    "answer",
    "summary",
    "statement",
    "evidence",
    "chunks",
    "hits",
    "snippet",
    "prompt",
    "query_preview",
    "embedding",
    "distance",
    "document_body",
    "raw_text",
    "workflow_trace",
    "source_paths",
    "file_paths",
}


def _registry_with(*tool_names: str, safe: bool = True) -> ToolRegistry:
    registry = ToolRegistry()
    for name in tool_names:
        registry.register(
            ToolSpec(name=name, description=f"{name} tool", safe_for_planner=safe),
            lambda args, tool_name=name: ToolResult.success(
                result_summary={"tool": tool_name, "query": args.get("query"), "evidence": object()},
                citations_count=2,
                payload={"raw_evidence_text": "do not include in trace"},
            ),
        )
    return registry


def test_simple_chat_request_selects_chat_with_evidence() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence")).run(AgentRunRequest(query="hello", task_type="chat"))

    assert result.agent_trace.planned_steps == ("chat_with_evidence",)
    assert result.agent_trace.executed_tools == ("chat_with_evidence",)
    assert result.fallback_to_fixed_workflow is False


def test_compare_task_selects_compare_sources() -> None:
    result = AgentRuntime(_registry_with("compare_sources")).run(AgentRunRequest(query="compare", task_type="compare"))

    assert result.agent_trace.planned_steps == ("compare_sources",)


def test_two_selected_sources_select_compare_sources() -> None:
    result = AgentRuntime(_registry_with("compare_sources")).run(
        AgentRunRequest(query="what differs", selected_sources=("a.pdf", "b.pdf"))
    )

    assert result.agent_trace.planned_steps == ("compare_sources",)


def test_summarize_task_selects_summarize_sources() -> None:
    result = AgentRuntime(_registry_with("summarize_sources")).run(
        AgentRunRequest(query="summarize", task_type="summarize")
    )

    assert result.agent_trace.planned_steps == ("summarize_sources",)


def test_missing_preferred_tool_falls_back_to_search_kb() -> None:
    result = AgentRuntime(_registry_with("search_kb")).run(AgentRunRequest(query="hello", task_type="chat"))

    assert result.agent_trace.planned_steps == ("search_kb",)
    assert result.agent_trace.executed_tools == ("search_kb",)


def test_no_safe_tools_marks_fallback_with_no_calls() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence", safe=False)).run(
        AgentRunRequest(query="hello", task_type="chat")
    )

    assert result.fallback_to_fixed_workflow is True
    assert result.agent_trace.stop_reason == "no_plan"
    assert result.agent_trace.tool_call_count == 0


def test_max_steps_above_three_is_clamped() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence")).run(
        AgentRunRequest(query="hello", task_type="chat", max_steps=99)
    )

    assert result.agent_trace.tool_call_count == 1
    assert result.agent_trace.planned_steps == ("chat_with_evidence",)


def test_max_steps_zero_produces_no_calls_and_no_plan_stop_reason() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence")).run(
        AgentRunRequest(query="hello", task_type="chat", max_steps=0)
    )

    assert result.fallback_to_fixed_workflow is True
    assert result.agent_trace.stop_reason == "no_plan"
    assert result.agent_trace.tool_call_count == 0
    assert result.agent_trace.executed_tools == ()


def test_failed_tool_marks_fallback_safely() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="chat_with_evidence", description="Chat with evidence."),
        lambda args: ToolResult.failure("handler_error", result_summary={"detail": object(), "safe": "failed"}),
    )

    result = AgentRuntime(registry).run(AgentRunRequest(query="hello", task_type="chat"))

    assert result.fallback_to_fixed_workflow is True
    assert result.agent_trace.stop_reason == "tool_failed"
    assert result.agent_trace.steps[0].result_summary == {"safe": "failed"}


def test_raising_tool_marks_fallback_without_exception_details() -> None:
    registry = ToolRegistry()

    def raises(_args):
        raise RuntimeError("private failure details")

    registry.register(ToolSpec(name="chat_with_evidence", description="Chat with evidence."), raises)

    result = AgentRuntime(registry).run(AgentRunRequest(query="hello", task_type="chat"))

    assert result.fallback_to_fixed_workflow is True
    assert result.agent_trace.stop_reason == "tool_failed"
    assert result.agent_trace.steps[0].result_summary == {}
    assert "private failure details" not in str(result.agent_trace)


def test_agent_trace_omits_raw_payload_evidence_text_and_filters() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence")).run(
        AgentRunRequest(query="hello", task_type="chat", filters=object())
    )

    trace_text = str(result.agent_trace)
    assert "raw_evidence_text" not in trace_text
    assert "do not include" not in trace_text
    assert "filters" not in trace_text
    assert result.agent_trace.steps[0].args_summary == {
        "query": "hello",
        "task_type": "chat",
        "selected_sources": (),
        "selected_sources_count": 0,
    }


def test_allow_llm_planner_true_is_ignored() -> None:
    result = AgentRuntime(_registry_with("chat_with_evidence")).run(
        AgentRunRequest(query="hello", task_type="chat", allow_llm_planner=True)
    )

    assert result.agent_trace.planned_steps == ("chat_with_evidence",)
    assert result.agent_trace.executed_tools == ("chat_with_evidence",)


def test_importing_agent_runtime_does_not_import_existing_orchestrator_or_services() -> None:
    for module_name in list(sys.modules):
        if module_name.startswith("app.agent_runtime"):
            sys.modules.pop(module_name)
    sys.modules.pop("app.application.orchestrators", None)
    sys.modules.pop("app.services.chat_service", None)
    sys.modules.pop("app.services.summarize_service", None)
    sys.modules.pop("app.services.compare_service", None)
    sys.modules.pop("app.services.search_service", None)

    import app.agent_runtime  # noqa: F401

    assert "app.application.orchestrators" not in sys.modules
    assert "app.services.chat_service" not in sys.modules
    assert "app.services.summarize_service" not in sys.modules
    assert "app.services.compare_service" not in sys.modules
    assert "app.services.search_service" not in sys.modules


def test_stub_registry_routes_chat_to_chat_with_evidence() -> None:
    result = AgentRuntime(build_stub_tool_registry()).run(AgentRunRequest(query="hello", task_type="chat"))

    assert result.agent_trace.executed_tools == ("chat_with_evidence",)
    assert result.agent_trace.steps[0].result_summary["operation"] == "chat"


def test_stub_registry_routes_two_selected_sources_to_compare_sources() -> None:
    result = AgentRuntime(build_stub_tool_registry()).run(
        AgentRunRequest(query="compare", selected_sources=("left.pdf", "right.pdf"))
    )

    assert result.agent_trace.executed_tools == ("compare_sources",)
    assert result.agent_trace.steps[0].result_summary["operation"] == "compare"


def test_stub_registry_planner_does_not_select_inspect_source_chunks() -> None:
    result = AgentRuntime(build_stub_tool_registry()).run(AgentRunRequest(query="hello", task_type="unknown"))

    assert "inspect_source_chunks" not in result.agent_trace.planned_steps
    assert result.agent_trace.executed_tools == ("chat_with_evidence",)


def test_agent_trace_from_stub_run_contains_safe_counts_without_forbidden_keys() -> None:
    result = AgentRuntime(build_stub_tool_registry()).run(AgentRunRequest(query="hello", task_type="chat"))

    summary = result.agent_trace.steps[0].result_summary
    assert summary["operation"] == "chat"
    assert summary["status"] == "ok"
    assert summary["citations_count"] == 2
    assert FORBIDDEN_STUB_TRACE_KEYS.isdisjoint(summary)
