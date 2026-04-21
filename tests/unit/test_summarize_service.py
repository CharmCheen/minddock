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
