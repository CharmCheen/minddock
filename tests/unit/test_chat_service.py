"""Unit tests for ChatService."""

import logging

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.runtime import RuntimeRequest, RuntimeResponse
from app.services.chat_service import ChatService
from app.services.service_models import ChatServiceResult


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.last_filters: RetrievalFilters | None = None
        self.calls = 0

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        self.calls += 1
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
        self.last_prompt: object | None = None
        self.last_query = ""
        self.last_evidence: list[dict[str, object]] = []

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        self.last_inputs = request.inputs
        self.last_prompt = request.prompt
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


def test_chat_refuses_out_of_scope_question_before_retrieval() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="MindDock stores chunks in Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                distance=0.1,
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

    result = service.chat(query="你是什么模型", top_k=3)

    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "out_of_scope"
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.support_status == "insufficient_evidence"
    assert result.metadata.refusal_reason == "out_of_scope"
    assert result.metadata.issues[0].code == "out_of_scope"
    assert search_service.calls == 0
    assert runtime.last_inputs is None


def test_chat_refuses_when_retrieved_evidence_does_not_match_query() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="MindDock stores chunks in Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                distance=0.1,
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

    result = service.chat(query="retention policy audit logs", top_k=3)

    assert result.answer == INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.issues[0].code == "evidence_query_mismatch"
    assert result.metadata.retrieval_stats.retrieved_hits == 1
    assert result.metadata.retrieval_stats.returned_hits == 0
    assert search_service.calls == 1
    assert runtime.last_inputs is None


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


def test_chat_reranks_direct_answer_evidence_ahead_of_generic_context() -> None:
    query = "\u4ec0\u4e48\u662fRAG\uff0c\u5b83\u89e3\u51b3\u4e86\u4ec0\u4e48\u95ee\u9898"
    generic = RetrievedChunk(
        text="RAG systems include naive RAG, advanced RAG, modular RAG, and graph RAG variants.",
        doc_id="d1",
        chunk_id="generic",
        source="survey.pdf",
        distance=0.1,
    )
    direct = RetrievedChunk(
        text=(
            "Retrieval-augmented generation (RAG) mitigates hallucination and outdated knowledge "
            "by retrieving relevant knowledge from provided documents before generation."
        ),
        doc_id="d2",
        chunk_id="direct",
        source="rag.pdf",
        distance=0.2,
    )
    runtime = FakeRuntime()
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query=query, top_k=2, precomputed_hits=[generic, direct])

    assert result.citations[0].chunk_id == "direct"
    assert runtime.last_evidence[0]["chunk_id"] == "direct"


def test_chat_prompt_requires_evidence_synthesis_and_misalignment_refusal() -> None:
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    formatted = service._format_prompt_for_debug(
        service._build_prompt(),
        {
            "query": "what is RAG",
            "evidence_block": "[1] Retrieval augments generation with external context.",
        },
    )

    assert "Answer only from the provided evidence" in formatted
    assert "not clearly aligned with the question" in formatted
    assert "Synthesize all relevant evidence items" in formatted
    assert "do not rely on the first item" in formatted


def test_chat_debug_logs_formatted_prompt(caplog) -> None:
    service = ChatService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text="MindDock stores chunks in Chroma.",
                    doc_id="d1",
                    chunk_id="c1",
                    source="kb/doc.md",
                    distance=0.2,
                )
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.chat_service"):
        result = service.chat(query="where is data stored", top_k=3, debug=True)

    assert result.metadata.retrieved_count == 1
    assert "Formatted chat prompt:" in caplog.text
    assert "Question:\nwhere is data stored" in caplog.text
    assert "MindDock stores chunks in Chroma." in caplog.text
