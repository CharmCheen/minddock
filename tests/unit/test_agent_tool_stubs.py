"""Unit tests for experimental agent runtime stub tools."""

import json
import sys

from app.agent_runtime.models import JsonSafeValue
from app.agent_runtime.tools import build_stub_tool_registry

EXPECTED_TOOLS = {
    "search_kb",
    "chat_with_evidence",
    "summarize_sources",
    "compare_sources",
    "list_sources",
    "inspect_source_chunks",
}

EXPECTED_SUMMARY_KEYS = {
    "search_kb": {
        "operation",
        "status",
        "retrieved_count",
        "evidence_count",
        "citations_count",
        "sources_count",
    },
    "chat_with_evidence": {
        "operation",
        "status",
        "support_status",
        "retrieved_count",
        "citations_count",
        "fallback_used",
        "warnings_count",
        "trace_keys",
    },
    "summarize_sources": {
        "operation",
        "status",
        "support_status",
        "retrieved_count",
        "citations_count",
        "output_format",
        "mode",
        "fallback_used",
        "warnings_count",
    },
    "compare_sources": {
        "operation",
        "status",
        "support_status",
        "common_points_count",
        "differences_count",
        "conflicts_count",
        "citations_count",
        "retrieved_count",
        "warnings_count",
    },
    "list_sources": {
        "operation",
        "status",
        "sources_count",
        "filter_applied",
    },
    "inspect_source_chunks": {
        "operation",
        "status",
        "total_chunks",
        "returned_chunks",
        "limit",
        "offset",
    },
}

FORBIDDEN_KEYS = {
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


def _assert_json_safe(value: JsonSafeValue) -> None:
    json.dumps(value)
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_safe(item)
    elif isinstance(value, tuple):
        for item in value:
            _assert_json_safe(item)
    else:
        assert isinstance(value, (str, int, float, bool)) or value is None


def test_build_stub_tool_registry_registers_expected_tool_names() -> None:
    registry = build_stub_tool_registry()

    assert {tool.name for tool in registry.list_tools()} == EXPECTED_TOOLS


def test_planner_safe_tools_are_safe_for_planner() -> None:
    registry = build_stub_tool_registry()

    for name in EXPECTED_TOOLS - {"inspect_source_chunks"}:
        assert registry.get(name).safe_for_planner is True


def test_inspect_source_chunks_is_planner_unsafe() -> None:
    registry = build_stub_tool_registry()

    assert registry.get("inspect_source_chunks").safe_for_planner is False


def test_each_stub_returns_success_payload_none_and_expected_summary_keys() -> None:
    registry = build_stub_tool_registry()

    for name in EXPECTED_TOOLS:
        result = registry.invoke(name, {"selected_sources": ("left.pdf", "right.pdf"), "limit": 5, "offset": 1})
        assert result.ok is True
        assert result.payload is None
        assert set(result.result_summary) == EXPECTED_SUMMARY_KEYS[name]


def test_forbidden_keys_are_absent_from_all_summaries() -> None:
    registry = build_stub_tool_registry()

    for name in EXPECTED_TOOLS:
        result = registry.invoke(name, {"selected_sources": ("left.pdf", "right.pdf")})
        assert FORBIDDEN_KEYS.isdisjoint(result.result_summary)


def test_inspect_source_chunks_cannot_be_invoked_in_planner_safe_mode() -> None:
    result = build_stub_tool_registry().invoke("inspect_source_chunks", {}, planner_safe_only=True)

    assert result.ok is False
    assert result.error == "planner_unsafe_tool"


def test_stubs_do_not_import_services_or_application_modules() -> None:
    for module_name in list(sys.modules):
        if module_name.startswith("app.agent_runtime"):
            sys.modules.pop(module_name)
    sys.modules.pop("app.services", None)
    sys.modules.pop("app.application", None)

    from app.agent_runtime.tools import build_stub_tool_registry as imported_builder

    imported_builder()

    assert "app.services" not in sys.modules
    assert "app.application" not in sys.modules


def test_result_summaries_are_json_safe_primitive_only() -> None:
    registry = build_stub_tool_registry()

    for name in EXPECTED_TOOLS:
        result = registry.invoke(name, {"selected_sources": ("left.pdf", "right.pdf")})
        _assert_json_safe(result.result_summary)
