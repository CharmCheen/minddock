"""Unit tests for the unified retrieval pipeline (RetrievalPipeline)."""

from __future__ import annotations

import pytest
from typing import Callable

from app.rag.retrieval_models import RetrievedChunk
from app.rag.postprocess import Compressor, Reranker
from app.services.search_service import SearchService
from app.application.events import RetrievalPipelineProgressPayload, RetrievalPipelineCompletedPayload
from app.workflows.unified_pipeline import (
    RetrievalPipeline,
    UnifiedWorkflowState,
    _SequentialGraph,
)


class FakeSearchService(SearchService):
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits

    def retrieve(self, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:
        return self._hits


class FakeSearchServiceWithCalls(SearchService):
    """Returns different hit lists per call to simulate retry behavior."""

    def __init__(self, *call_results: list[RetrievedChunk]) -> None:
        self._call_results = list(call_results)
        self._call_index = 0
        self.calls: list[dict] = []

    def retrieve(self, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        if self._call_index < len(self._call_results):
            result = self._call_results[self._call_index]
            self._call_index += 1
            return result
        return []


class FakeReranker(Reranker):
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return list(reversed(hits))


class FakeCompressor(Compressor):
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits[:1]


def _make_hit(text: str = "hit", chunk_id: str = "c1", distance: float = 0.1) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        doc_id="d1",
        chunk_id=chunk_id,
        source="kb/doc.md",
        source_type="file",
        title="doc",
        section="Storage",
        location="Storage",
        ref="doc > Storage",
        page=None,
        anchor=None,
        distance=distance,
    )


class EventCollector:
    def __init__(self) -> None:
        self.events: list[RetrievalPipelineProgressPayload | RetrievalPipelineCompletedPayload] = []

    def emit(self, payload: RetrievalPipelineProgressPayload | RetrievalPipelineCompletedPayload) -> None:
        self.events.append(payload)


# -----------------------------------------------------------------------------
# Stream path tests (event_emitter provided)
# -----------------------------------------------------------------------------


def test_stream_path_emits_events_in_order() -> None:
    hits = [_make_hit("a", "c1"), _make_hit("b", "c2")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    collector = EventCollector()
    state = pipeline.run(query="q", top_k=5, event_emitter=collector.emit)

    stages = [e.stage if hasattr(e, "stage") else "retrieval_pipeline_completed" for e in collector.events]
    assert stages == [
        "retrieval_started",
        "retrieval_completed",
        "rerank_completed",
        "compress_completed",
        "retrieval_pipeline_completed",
    ]

    # Verify final counts on the completion payload
    completed = collector.events[-1]
    assert isinstance(completed, RetrievalPipelineCompletedPayload)
    assert completed.retrieved_hits == 2
    assert completed.reranked_hits == 2
    assert completed.compressed_hits == 1
    assert completed.total_ms >= 0

    # Verify intermediate payloads carry correct counts
    assert collector.events[1].retrieved_hits == 2
    assert collector.events[2].retrieved_hits == 2
    assert collector.events[2].reranked_hits == 2
    assert collector.events[3].retrieved_hits == 2
    assert collector.events[3].reranked_hits == 2
    assert collector.events[3].compressed_hits == 1

    # Final state matches
    assert state["hits"] == hits
    assert state["reranked_hits"] == list(reversed(hits))
    assert state["compressed_hits"] == list(reversed(hits))[:1]


def test_stream_path_final_state_matches_invoke() -> None:
    hits = [_make_hit("a", "c1")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )

    invoke_state = pipeline.run(query="q", top_k=5, event_emitter=None)

    collector = EventCollector()
    stream_state = pipeline.run(query="q", top_k=5, event_emitter=collector.emit)

    assert stream_state == invoke_state


def test_empty_retrieval_emits_stable_event_order_with_zero_counts() -> None:
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService([]),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    collector = EventCollector()
    state = pipeline.run(query="q", top_k=5, event_emitter=collector.emit)

    stages = [e.stage if hasattr(e, "stage") else "retrieval_pipeline_completed" for e in collector.events]
    # Empty retrieval triggers one retry, so we expect two retrieve→rerank→compress cycles
    assert stages == [
        "retrieval_started",
        "retrieval_completed",
        "rerank_completed",
        "compress_completed",
        "retrieval_completed",
        "rerank_completed",
        "compress_completed",
        "retrieval_pipeline_completed",
    ]

    for e in collector.events[:-1]:
        assert e.retrieved_hits == 0
        assert e.reranked_hits == 0
        assert e.compressed_hits == 0

    completed = collector.events[-1]
    assert isinstance(completed, RetrievalPipelineCompletedPayload)
    assert completed.retrieved_hits == 0
    assert completed.reranked_hits == 0
    assert completed.compressed_hits == 0

    assert state["hits"] == []
    assert state["reranked_hits"] == []
    assert state["compressed_hits"] == []
    assert state["retry_count"] == 1
    assert state["quality_ok"] is False


# -----------------------------------------------------------------------------
# Quality check / retry tests
# -----------------------------------------------------------------------------


def test_chat_quality_sufficient_does_not_retry() -> None:
    hits = [_make_hit("a", "c1")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="总结 storage", top_k=5, task_type="chat", event_emitter=None)
    assert state["quality_ok"] is True
    assert state["retry_count"] == 0
    assert state["hits"] == hits


class PassThroughCompressor(Compressor):
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


def test_summarize_quality_sufficient_does_not_retry() -> None:
    hits = [_make_hit("a", "c1"), _make_hit("b", "c2")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=PassThroughCompressor(),
    )
    state = pipeline.run(query="总结 storage", top_k=5, task_type="summarize", event_emitter=None)
    assert state["quality_ok"] is True
    assert state["retry_count"] == 0


def test_summarize_insufficient_diversity_triggers_retry() -> None:
    """summarize with 1 compressed hit but >1 original hits should trigger retry."""
    hits = [_make_hit("a", "c1"), _make_hit("b", "c2")]
    # First call returns hits, second call also returns hits (simulating retry still not enough)
    svc = FakeSearchServiceWithCalls(hits, hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="总结 storage", top_k=5, task_type="summarize", event_emitter=None)
    # After retry, still only 1 compressed hit because FakeCompressor returns hits[:1]
    assert state["retry_count"] == 1
    assert state["quality_ok"] is False
    assert "Insufficient diversity for summarize" in state["quality_reasons"]


def test_zero_hits_triggers_exactly_one_retry() -> None:
    svc = FakeSearchServiceWithCalls([], [])
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="q", top_k=5, event_emitter=None)
    assert state["retry_count"] == 1
    assert len(svc.calls) == 2
    assert state["quality_ok"] is False


def test_retry_uses_expanded_query() -> None:
    """Instruction words should be stripped from the query on retry."""
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="总结 storage 区别", top_k=5, event_emitter=None)
    assert state["retry_count"] == 1
    # Second call should use the expanded (stripped) query
    assert svc.calls[1]["query"] == "storage"
    assert state["expanded_query"] == "storage"


def test_retry_increases_top_k_within_bounds() -> None:
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="q", top_k=5, event_emitter=None)
    assert state["retry_count"] == 1
    # retry_top_k = min(max(5 + 3, int(5 * 1.5)), 20) = min(8, 7) = 8
    assert svc.calls[1]["top_k"] == 8

    # Test upper bound
    svc2 = FakeSearchServiceWithCalls([], hits)
    pipeline2 = RetrievalPipeline(
        search_service=svc2,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    pipeline2.run(query="q", top_k=20, event_emitter=None)
    assert svc2.calls[1]["top_k"] == 20


def test_retry_keeps_filters_unchanged() -> None:
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    filters = {"section": "Storage"}
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    pipeline.run(query="q", top_k=5, filters=filters, event_emitter=None)
    assert svc.calls[0]["filters"] == filters
    assert svc.calls[1]["filters"] == filters


def test_retry_count_bounded_at_one() -> None:
    """Even with consistently empty results, only one retry is attempted."""
    svc = FakeSearchServiceWithCalls([], [], [])
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="q", top_k=5, event_emitter=None)
    assert state["retry_count"] == 1
    assert len(svc.calls) == 2


def test_low_confidence_flagged_for_weak_distances() -> None:
    hits = [_make_hit("a", "c1", distance=1.5), _make_hit("b", "c2", distance=2.0)]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="q", top_k=5, event_emitter=None)
    assert state["low_confidence"] is True
    assert "All retrieval distances are weak (>= 1.5)" in state["quality_reasons"]
    assert state["quality_ok"] is True  # low_confidence alone does not trigger retry


def test_final_quality_reasons_and_reflection_present_when_insufficient() -> None:
    svc = FakeSearchServiceWithCalls([], [])
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    state = pipeline.run(query="q", top_k=5, event_emitter=None)
    assert state["quality_ok"] is False
    assert state["quality_reasons"]
    assert state["reflection"]["attempt"] == 2  # initial + 1 retry
    assert state["reflection"]["reasons"]


def test_no_retry_event_order_unchanged_for_sufficient_evidence() -> None:
    hits = [_make_hit("a", "c1")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    collector = EventCollector()
    pipeline.run(query="q", top_k=5, event_emitter=collector.emit)
    stages = [e.stage if hasattr(e, "stage") else "retrieval_pipeline_completed" for e in collector.events]
    assert stages == [
        "retrieval_started",
        "retrieval_completed",
        "rerank_completed",
        "compress_completed",
        "retrieval_pipeline_completed",
    ]
    assert sum(1 for s in stages if s == "retrieval_pipeline_completed") == 1


def test_retry_path_emits_understandable_sequence_and_one_final_completion() -> None:
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    collector = EventCollector()
    pipeline.run(query="q", top_k=5, event_emitter=collector.emit)
    stages = [e.stage if hasattr(e, "stage") else "retrieval_pipeline_completed" for e in collector.events]
    # One retry = two retrieve→rerank→compress cycles + one final completion
    assert stages.count("retrieval_started") == 1
    assert stages.count("retrieval_completed") == 2
    assert stages.count("rerank_completed") == 2
    assert stages.count("compress_completed") == 2
    assert stages.count("retrieval_pipeline_completed") == 1
    assert stages[-1] == "retrieval_pipeline_completed"


# -----------------------------------------------------------------------------
# Fallback _SequentialGraph tests
# -----------------------------------------------------------------------------


def test_fallback_sequential_graph_invoke_returns_final_state() -> None:
    hits = [_make_hit("a", "c1"), _make_hit("b", "c2")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    fallback = _SequentialGraph(pipeline)
    initial: UnifiedWorkflowState = {
        "query": "q",
        "top_k": 5,
        "filters": None,
        "hits": [],
        "reranked_hits": [],
        "compressed_hits": [],
    }
    state = fallback.invoke(initial)
    assert state["hits"] == hits
    assert state["reranked_hits"] == list(reversed(hits))
    assert state["compressed_hits"] == list(reversed(hits))[:1]


def test_fallback_sequential_graph_stream_yields_langgraph_shapes() -> None:
    hits = [_make_hit("a", "c1"), _make_hit("b", "c2")]
    pipeline = RetrievalPipeline(
        search_service=FakeSearchService(hits),
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    fallback = _SequentialGraph(pipeline)
    initial: UnifiedWorkflowState = {
        "query": "q",
        "top_k": 5,
        "filters": None,
        "hits": [],
        "reranked_hits": [],
        "compressed_hits": [],
    }
    updates = list(fallback.stream(initial))

    assert updates == [
        {"retrieve": {"hits": hits}},
        {"rerank": {"reranked_hits": list(reversed(hits))}},
        {"compress": {"compressed_hits": list(reversed(hits))[:1]}},
        {
            "quality_check": {
                "quality_ok": True,
                "quality_reasons": [],
                "low_confidence": False,
                "reflection": {"attempt": 1, "reasons": [], "low_confidence": False},
            }
        },
    ]


def test_fallback_conditional_retry_when_quality_fails() -> None:
    """Fallback must loop back through query_expand → retrieve when quality fails."""
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    fallback = _SequentialGraph(pipeline)
    initial: UnifiedWorkflowState = {
        "query": "总结 storage",
        "top_k": 5,
        "filters": None,
        "hits": [],
        "reranked_hits": [],
        "compressed_hits": [],
    }
    state = fallback.invoke(initial)
    assert state["retry_count"] == 1
    assert state["quality_ok"] is True  # second attempt succeeded
    assert state["hits"] == hits


def test_fallback_stream_includes_retry_nodes() -> None:
    hits = [_make_hit("a", "c1")]
    svc = FakeSearchServiceWithCalls([], hits)
    pipeline = RetrievalPipeline(
        search_service=svc,
        reranker=FakeReranker(),
        compressor=FakeCompressor(),
    )
    fallback = _SequentialGraph(pipeline)
    initial: UnifiedWorkflowState = {
        "query": "总结 storage",
        "top_k": 5,
        "filters": None,
        "hits": [],
        "reranked_hits": [],
        "compressed_hits": [],
    }
    updates = list(fallback.stream(initial))
    node_names = [list(u.keys())[0] for u in updates]
    assert node_names == [
        "retrieve",
        "rerank",
        "compress",
        "quality_check",
        "query_expand",
        "retrieve",
        "rerank",
        "compress",
        "quality_check",
    ]
