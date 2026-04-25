"""Unit tests for SummarizeService."""

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.runtime import RuntimeRequest, RuntimeResponse
from app.services.grounded_generation import build_context
from app.services.summarize_service import SummarizeService
from app.services.service_models import RetrievalPreparationResult, SummarizeServiceResult


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        return self._hits[:top_k]


class PassthroughReranker:
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class PassthroughCompressor:
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class FakeRuntime:
    runtime_name = "fake-runtime"
    provider_name = "fake-provider"

    def __init__(self) -> None:
        self.last_inputs: dict[str, object] | None = None
        self.last_query = ""
        self.last_evidence: list[dict[str, object]] = []

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        self.last_inputs = request.inputs
        self.last_query = request.fallback_query
        self.last_evidence = request.fallback_evidence
        return RuntimeResponse(
            text=f"summary for {len(request.fallback_evidence)} evidence",
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        text="MindDock stores chunks in Chroma.",
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        title="doc",
        section="Storage",
        location="Storage",
        ref="doc > Storage",
        page=None,
        anchor=None,
        distance=0.2,
    )


def _chunk_from_source(source: str, index: int) -> RetrievedChunk:
    return RetrievedChunk(
        text=f"Evidence {index} from {source}.",
        doc_id=source,
        chunk_id=f"{source}:{index}",
        source=source,
        title=source,
        section="Overview",
        ref=f"{source} > Overview",
        distance=0.2,
    )


def test_summarize_returns_summary_and_citations(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=[_chunk()],
            grounded_hits=[_chunk()],
            context=build_context([_chunk()]),
            citations=[],
        ),
    )
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.summarize(
        topic="storage design",
        top_k=3,
        filters=RetrievalFilters(sources=("kb/doc.md",), section="Storage"),
    )

    assert isinstance(result, SummarizeServiceResult)
    assert result.summary == "summary for 1 evidence"
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.grounded_answer.evidence[0].chunk_id == "c1"
    assert result.grounded_answer.evidence[0].freshness.value == "fresh"
    assert result.metadata.retrieved_count == 1
    assert result.metadata.timing.total_ms is not None
    assert result.metadata.retrieval_stats.returned_hits == 1
    assert result.citations[0].ref == "doc > Storage"
    assert result.citations[0].page is None
    assert result.citations[0].anchor is None
    assert result.metadata.mode == "basic"
    assert result.metadata.output_format == "text"
    assert result.structured_output is None
    assert "storage design" in str(runtime.last_inputs)
    assert "MindDock stores chunks in Chroma." in str(runtime.last_inputs)


def test_summarize_returns_insufficient_evidence_when_no_hits(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=[],
            grounded_hits=[],
            context=build_context([]),
            citations=[],
        ),
    )
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.summarize(topic="empty", top_k=3)

    assert result.summary == INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.metadata.retrieved_count == 0
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.issues[0].code == "insufficient_evidence"


def test_summarize_map_reduce_and_mermaid(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=[_chunk()],
            grounded_hits=[_chunk()],
            context=build_context([_chunk()]),
            citations=[],
        ),
    )
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.summarize(
        topic="storage design",
        top_k=3,
        mode="map_reduce",
        output_format="mermaid",
    )

    assert result.metadata.mode == "map_reduce"
    assert result.metadata.output_format == "mermaid"
    assert result.structured_output is not None
    assert result.structured_output.startswith("mindmap")


def test_summarize_diversifies_precomputed_evidence_by_source() -> None:
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )
    hits = [
        _chunk_from_source("a.md", 1),
        _chunk_from_source("a.md", 2),
        _chunk_from_source("a.md", 3),
        _chunk_from_source("b.md", 1),
        _chunk_from_source("c.md", 1),
        _chunk_from_source("d.md", 1),
    ]

    result = service.summarize(topic="summarize all docs", top_k=6, precomputed_hits=hits)

    sources = [citation.source for citation in result.citations]
    assert len(sources) == 4
    assert len(set(sources)) == 4
    assert runtime.last_evidence is not None
    assert len({str(item["source"]) for item in runtime.last_evidence}) == 4


def _make_chunk(text: str, index: int = 1, source: str = "doc.md") -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        doc_id=source,
        chunk_id=f"{source}:{index}",
        source=source,
        title=source,
        section="Section",
        ref=f"{source} > Section",
        distance=0.2,
    )


def test_summarize_long_evidence_is_truncated(monkeypatch) -> None:
    """A single chunk whose text exceeds _SUMMARY_SAFE_MAX_PER_CHUNK is per-chunk truncated."""
    # Single chunk with 4000-char text → exceeds 2500 per-chunk cap → per-chunk truncation fires
    long_text = "x" * 4000
    hits = [_make_chunk(long_text)]

    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=hits,
            grounded_hits=hits,
            context=build_context(hits),
            citations=[],
        ),
    )
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.summarize(topic="test truncation", top_k=3)

    assert isinstance(result.summary_context_truncated, bool)
    assert result.summary_context_truncated is True
    assert "summary_context_truncated" in (result.metadata.workflow_trace.get("trace_warnings") or ())
    # LLM was still called with evidence (truncated) — no exception raised
    assert "summary for" in result.summary


def test_summarize_small_doc_unchanged(monkeypatch) -> None:
    """Small documents do not trigger truncation."""
    hits = [_make_chunk("Short evidence text.")]
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=hits,
            grounded_hits=hits,
            context=build_context(hits),
            citations=[],
        ),
    )
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.summarize(topic="small doc", top_k=3)

    assert result.summary_context_truncated is False
    assert "truncated" not in str(result.metadata.workflow_trace.get("trace_warnings") or [])
    # Full evidence was passed to the LLM
    evidence_block = str(runtime.last_inputs.get("evidence_block") or "")
    assert "Short evidence text." in evidence_block


def test_summarize_large_document_safety(monkeypatch) -> None:
    """Summarizing a large document returns a response without crashing."""
    # Simulate many large chunks — more than _SUMMARY_EVIDENCE_LIMIT with dense content
    hits = [
        _make_chunk("a" * 3000, index=1, source="big.pdf"),
        _make_chunk("b" * 3000, index=2, source="big.pdf"),
        _make_chunk("c" * 3000, index=3, source="big.pdf"),
        _make_chunk("d" * 3000, index=4, source="big.pdf"),
    ]
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=hits,
            grounded_hits=hits,
            context=build_context(hits),
            citations=[],
        ),
    )
    runtime = FakeRuntime()
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    # Should not raise — just set truncation flag
    result = service.summarize(topic="large doc safety test", top_k=10)

    assert result.summary_context_truncated is True
    warnings = result.metadata.workflow_trace.get("trace_warnings") or ()
    assert "summary_context_truncated" in warnings
    # A summary was still produced
    assert result.summary is not None
    assert len(result.summary) > 0
