"""Unit tests for ChatService."""

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.runtime import RuntimeRequest, RuntimeResponse
from app.services.chat_service import ChatService
from app.services.service_models import ChatServiceResult


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.last_filters: RetrievalFilters | None = None

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        self.last_filters = filters
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
            text=f"answer for {request.fallback_query} with {len(request.fallback_evidence)} evidence",
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


def test_chat_returns_insufficient_evidence_when_no_grounded_hits() -> None:
    service = ChatService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text="weak",
                    doc_id="d1",
                    chunk_id="c1",
                    source="doc.md",
                    distance=9.9,
                )
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="test", top_k=3)

    assert isinstance(result, ChatServiceResult)
    assert result.answer == INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.grounded_answer.evidence == ()
    assert result.metadata.retrieved_count == 0
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.support_status == "insufficient_evidence"
    assert result.metadata.refusal_reason == "no_relevant_evidence"
    assert result.metadata.issues[0].code == "insufficient_evidence"


def test_chat_returns_answer_and_citations_for_grounded_hits() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="MindDock stores chunks in Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                source_type="file",
                title="doc",
                section="Storage",
                location="Storage",
                ref="doc > Storage",
                page=None,
                anchor=None,
                distance=0.2,
            )
        ]
    )
    runtime = FakeRuntime()
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(
        query="where is data stored",
        top_k=3,
        filters=RetrievalFilters(sources=("kb/doc.md",), section="Storage"),
    )

    assert isinstance(result, ChatServiceResult)
    assert result.answer == "answer for where is data stored with 1 evidence"
    assert result.metadata.retrieved_count == 1
    assert result.metadata.timing.total_ms is not None
    assert result.metadata.retrieval_stats.returned_hits == 1
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.grounded_answer.refusal_reason is None
    assert result.grounded_answer.evidence[0].chunk_id == "c1"
    assert result.grounded_answer.evidence[0].source == "kb/doc.md"
    assert result.grounded_answer.evidence[0].score == 0.2
    assert result.grounded_answer.evidence[0].freshness.value == "fresh"
    assert result.citations[0].chunk_id == "c1"
    assert result.citations[0].source == "kb/doc.md"
    assert result.citations[0].section == "Storage"
    assert result.citations[0].location == "Storage"
    assert result.citations[0].ref == "doc > Storage"
    assert result.citations[0].page is None
    assert result.citations[0].anchor is None
    assert search_service.last_filters == RetrievalFilters(sources=("kb/doc.md",), section="Storage")
    assert "where is data stored" in str(runtime.last_inputs)
    assert "MindDock stores chunks in Chroma." in str(runtime.last_inputs)
