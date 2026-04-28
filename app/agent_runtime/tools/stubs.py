"""Deterministic stub tools for the experimental agent runtime boundary."""

from __future__ import annotations

from app.agent_runtime.models import ToolResult, ToolSpec
from app.agent_runtime.tool_registry import ToolRegistry


def _selected_sources_count(args: dict[str, object]) -> int:
    selected_sources = args.get("selected_sources")
    if isinstance(selected_sources, tuple):
        return sum(1 for item in selected_sources if isinstance(item, str))
    if isinstance(selected_sources, list):
        return sum(1 for item in selected_sources if isinstance(item, str))
    return 0


def _positive_int(args: dict[str, object], name: str, default: int) -> int:
    value = args.get(name)
    if type(value) is int and value >= 0:
        return value
    return default


def _search_kb(args: dict[str, object]) -> ToolResult:
    sources_count = max(_selected_sources_count(args), 1)
    citations_count = 2
    return ToolResult.success(
        result_summary={
            "operation": "search",
            "status": "ok",
            "retrieved_count": 3,
            "evidence_count": 2,
            "citations_count": citations_count,
            "sources_count": sources_count,
        },
        citations_count=citations_count,
    )


def _chat_with_evidence(_args: dict[str, object]) -> ToolResult:
    citations_count = 2
    return ToolResult.success(
        result_summary={
            "operation": "chat",
            "status": "ok",
            "support_status": "supported",
            "retrieved_count": 3,
            "citations_count": citations_count,
            "fallback_used": False,
            "warnings_count": 0,
            "trace_keys": ("operation", "final_citation_count"),
        },
        citations_count=citations_count,
    )


def _summarize_sources(_args: dict[str, object]) -> ToolResult:
    citations_count = 3
    return ToolResult.success(
        result_summary={
            "operation": "summarize",
            "status": "ok",
            "support_status": "supported",
            "retrieved_count": 4,
            "citations_count": citations_count,
            "output_format": "text",
            "mode": "basic",
            "fallback_used": False,
            "warnings_count": 0,
        },
        citations_count=citations_count,
    )


def _compare_sources(_args: dict[str, object]) -> ToolResult:
    citations_count = 4
    return ToolResult.success(
        result_summary={
            "operation": "compare",
            "status": "ok",
            "support_status": "supported",
            "common_points_count": 1,
            "differences_count": 2,
            "conflicts_count": 0,
            "citations_count": citations_count,
            "retrieved_count": 4,
            "warnings_count": 0,
        },
        citations_count=citations_count,
    )


def _list_sources(args: dict[str, object]) -> ToolResult:
    return ToolResult.success(
        result_summary={
            "operation": "list_sources",
            "status": "ok",
            "sources_count": max(_selected_sources_count(args), 2),
            "filter_applied": _selected_sources_count(args) > 0,
        },
    )


def _inspect_source_chunks(args: dict[str, object]) -> ToolResult:
    limit = _positive_int(args, "limit", 10)
    offset = _positive_int(args, "offset", 0)
    return ToolResult.success(
        result_summary={
            "operation": "inspect_source",
            "status": "ok",
            "total_chunks": 12,
            "returned_chunks": min(limit, 3),
            "limit": limit,
            "offset": offset,
        },
    )


def build_stub_tool_registry() -> ToolRegistry:
    """Build a planner-safe registry of deterministic stub tools."""

    registry = ToolRegistry()
    registry.register(ToolSpec(name="search_kb", description="Stub knowledge-base search."), _search_kb)
    registry.register(ToolSpec(name="chat_with_evidence", description="Stub grounded chat."), _chat_with_evidence)
    registry.register(ToolSpec(name="summarize_sources", description="Stub source summarization."), _summarize_sources)
    registry.register(ToolSpec(name="compare_sources", description="Stub source comparison."), _compare_sources)
    registry.register(ToolSpec(name="list_sources", description="Stub source listing."), _list_sources)
    registry.register(
        ToolSpec(
            name="inspect_source_chunks",
            description="Stub source chunk inspection.",
            safe_for_planner=False,
        ),
        _inspect_source_chunks,
    )
    return registry
