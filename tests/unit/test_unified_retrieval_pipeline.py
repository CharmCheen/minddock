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


class FakeReranker(Reranker):
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return list(reversed(hits))


class FakeCompressor(Compressor):
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits[:1]


def _make_hit(text: str = "hit", chunk_id: str = "c1") -> RetrievedChunk:
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
        distance=0.1,
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
    assert stages == [
        "retrieval_started",
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
    ]
