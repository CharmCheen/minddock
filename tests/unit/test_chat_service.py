"""Unit tests for ChatService."""

import logging
import pytest

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.postprocess import HeuristicReranker
from app.services.grounded_generation import HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.runtime import RuntimeRequest, RuntimeResponse
from app.services.chat_service import ChatService
from app.services.service_models import ChatServiceResult


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk], structured_hits: list[RetrievedChunk] | None = None) -> None:
        self._hits = hits
        self._structured_hits = structured_hits or []
        self.last_filters: RetrievalFilters | None = None
        self.last_top_k: int | None = None
        self.last_structured_filters: RetrievalFilters | None = None
        self.last_structured_top_k: int | None = None
        self.calls = 0
        self.structured_calls = 0

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        self.calls += 1
        self.last_filters = filters
        self.last_top_k = top_k
        return self._hits[:top_k]

    def retrieve_structured_reference_candidates(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        self.structured_calls += 1
        self.last_structured_filters = filters
        self.last_structured_top_k = top_k
        if filters is not None:
            return [
                hit
                for hit in self._structured_hits
                if filters.matches_metadata(
                    {
                        "source": hit.source,
                        "source_type": hit.source_type,
                        "section": hit.section,
                        "title": hit.title,
                        "page": hit.page,
                        **hit.extra_metadata,
                    }
                )
            ][:top_k]
        return self._structured_hits[:top_k]


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
    assert result.answer == HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert "没有在当前知识库中找到足够直接的证据" in result.answer
    assert "尝试" in result.answer
    assert "关键词" in result.answer
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.grounded_answer.evidence == ()
    assert result.metadata.retrieved_count == 0
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.support_status == "insufficient_evidence"
    assert result.metadata.refusal_reason == "no_relevant_evidence"
    assert result.metadata.issues[0].code == "insufficient_evidence"
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["operation"] == "chat"
    assert trace["final_candidate_count"] == 0
    assert trace["final_citation_count"] == 0
    assert trace["final_evidence_count"] == 0
    assert "no_citations" in trace["trace_warnings"]


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

    assert result.answer == HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert "没有在当前知识库中找到足够直接的证据" in result.answer
    assert "尝试" in result.answer
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.issues[0].code == "evidence_query_mismatch"
    assert result.metadata.retrieval_stats.retrieved_hits == 1
    assert result.metadata.retrieval_stats.returned_hits == 0
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["operation"] == "chat"
    assert trace["final_citation_count"] == 0
    assert "no_citations" in trace["trace_warnings"]
    assert search_service.calls == 1
    assert runtime.last_inputs is None


@pytest.mark.parametrize(
    ("query", "evidence_text", "missing_terms"),
    [
        (
            "How do I make a chocolate cake from scratch?",
            "This RAG paper explains how retrieval systems make generation more grounded from scratch.",
            ("chocolate", "cake"),
        ),
        (
            "What are the latest stock prices for Tesla and Apple?",
            "The latest RAG systems update retrieved context before answering user questions.",
            ("tesla", "apple"),
        ),
        (
            "What are the rules of chess and how does the knight move?",
            "The system applies rules to route retrieval requests across document chunks.",
            ("chess", "knight"),
        ),
        (
            "Explain the theory of general relativity in simple terms.",
            "The paper presents a theory of retrieval-augmented generation for knowledge-intensive tasks.",
            ("general", "relativity"),
        ),
    ],
)
def test_chat_evidence_gate_rejects_open_domain_questions_with_generic_overlap(
    query: str,
    evidence_text: str,
    missing_terms: tuple[str, ...],
) -> None:
    runtime = FakeRuntime()
    service = ChatService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text=evidence_text,
                    doc_id="rag-paper",
                    chunk_id="c1",
                    source="papers/rag.pdf",
                    title="RAG Survey",
                    distance=0.1,
                )
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query=query, top_k=3)

    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.support_status == "insufficient_evidence"
    assert result.metadata.issues[0].code == "evidence_query_mismatch"
    assert runtime.last_inputs is None
    trace = result.metadata.workflow_trace
    assert trace is not None
    gate = trace["evidence_gate"]
    assert gate["triggered"] is True
    assert gate["reason"] == "missing_core_query_terms"
    assert set(missing_terms).issubset(set(gate["missing_core_terms"]))


@pytest.mark.parametrize(
    ("query", "evidence_text", "expected_terms"),
    [
        (
            "What is the system design of Milvus?",
            "Milvus uses a distributed system design for vector search, with coordinators and query nodes.",
            ("milvus", "system", "design"),
        ),
        (
            "What are the key components of a RAG pipeline?",
            "A RAG pipeline includes retrieval, reranking, context construction, and generation components.",
            ("rag", "pipeline", "components"),
        ),
    ],
)
def test_chat_evidence_gate_allows_in_scope_questions(
    query: str,
    evidence_text: str,
    expected_terms: tuple[str, ...],
) -> None:
    runtime = FakeRuntime()
    service = ChatService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text=evidence_text,
                    doc_id="kb-doc",
                    chunk_id="c1",
                    source="papers/rag.pdf",
                    title="Knowledge Base Paper",
                    distance=0.1,
                )
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query=query, top_k=3)

    assert result.citations != []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.metadata.support_status == "supported"
    assert runtime.last_inputs is not None
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["evidence_gate"]["triggered"] is False
    assert set(expected_terms).intersection(set(trace["evidence_gate"]["overlap_terms"]))


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
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["operation"] == "chat"
    assert trace["requested_top_k"] == 3
    assert trace["final_candidate_count"] == 1
    assert trace["final_citation_count"] == 1
    assert trace["has_explicit_source_filter"] is True
    assert trace["selected_sources_count"] == 1
    assert trace["selected_sources_preview"] == ["kb/doc.md"]
    assert trace["final_sources"][0]["source"] == "kb/doc.md"
    assert search_service.last_filters == RetrievalFilters(sources=("kb/doc.md",), section="Storage")
    assert "where is data stored" in str(runtime.last_inputs)
    assert "MindDock stores chunks in Chroma." in str(runtime.last_inputs)


def test_chat_expands_internal_candidate_pool_but_returns_requested_top_k() -> None:
    hits = [
        RetrievedChunk(
            text=f"MindDock stores chunk {index} in Chroma for grounded retrieval.",
            doc_id=f"d{index}",
            chunk_id=f"c{index}",
            source=f"doc{index}.md",
            distance=0.1 + (index * 0.01),
        )
        for index in range(20)
    ]
    search_service = FakeSearchService(hits)
    runtime = FakeRuntime()
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query="where does MindDock store chunks", top_k=3)

    assert search_service.last_top_k == 15
    assert len(result.citations) == 3
    assert result.metadata.retrieval_stats.returned_hits == 3
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["requested_top_k"] == 3
    assert trace["internal_candidate_k"] == 15
    assert trace["internal_candidate_k"] >= trace["requested_top_k"]
    assert trace["final_citation_count"] <= 3


def test_chat_injects_structured_reference_lexical_candidate_before_rerank() -> None:
    dense_hits = [
        RetrievedChunk(
            text="Experiments compare Milvus throughput with several systems.",
            doc_id="milvus",
            chunk_id="exp",
            source="19_SIGMOD21_Milvus.pdf",
            section="EXPERIMENTS",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The abstract says Milvus provides more functionalities than competitors.",
            doc_id="milvus",
            chunk_id="abstract",
            source="19_SIGMOD21_Milvus.pdf",
            section="Abstract",
            distance=0.1,
        ),
    ]
    table_hit = RetrievedChunk(
        text="Table 1 highlights the main differences between Milvus and other systems.",
        doc_id="milvus",
        chunk_id="table1",
        source="19_SIGMOD21_Milvus.pdf",
        section="INTRODUCTION",
        page=1,
        distance=None,
    )
    search_service = FakeSearchService(dense_hits, structured_hits=[table_hit])
    service = ChatService(
        search_service=search_service,
        reranker=HeuristicReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(
        query="What differences are summarized in Table 1 of the Milvus paper?",
        top_k=2,
    )

    assert search_service.structured_calls == 1
    assert search_service.last_structured_top_k == 5
    assert any(citation.chunk_id == "table1" for citation in result.citations)
    assert len(result.citations) <= 2
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["structured_ref_intent_detected"] is True
    assert "structured_ref_lexical_injection" in trace["applied_rules"]


def test_chat_does_not_inject_structured_reference_for_plain_query() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="The Milvus paper presents a vector data management system.",
                doc_id="milvus",
                chunk_id="milvus",
                source="19_SIGMOD21_Milvus.pdf",
                distance=0.05,
            )
        ],
        structured_hits=[
            RetrievedChunk(
                text="Table 1 highlights differences.",
                doc_id="milvus",
                chunk_id="table1",
                source="19_SIGMOD21_Milvus.pdf",
            )
        ],
    )
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="What is the main topic of the Milvus paper?", top_k=1)

    assert search_service.structured_calls == 0
    assert result.citations[0].chunk_id == "milvus"


def test_chat_does_not_inject_for_table_without_number() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="The paper compares systems in experiments.",
                doc_id="milvus",
                chunk_id="dense",
                source="19_SIGMOD21_Milvus.pdf",
                distance=0.05,
            )
        ],
        structured_hits=[
            RetrievedChunk(
                text="Table 1 highlights differences.",
                doc_id="milvus",
                chunk_id="table1",
                source="19_SIGMOD21_Milvus.pdf",
            )
        ],
    )
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="What does the paper table compare?", top_k=1)

    assert search_service.structured_calls == 0
    assert result.citations[0].chunk_id == "dense"


def test_chat_structured_reference_injection_respects_source_filter() -> None:
    filters = RetrievalFilters(sources=("some_other.pdf",))
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="Some other PDF discusses Table 1 differences.",
                doc_id="other",
                chunk_id="other",
                source="some_other.pdf",
                distance=0.05,
            )
        ],
        structured_hits=[
            RetrievedChunk(
                text="Table 1 highlights the main differences between Milvus and other systems.",
                doc_id="milvus",
                chunk_id="table1",
                source="19_SIGMOD21_Milvus.pdf",
            )
        ],
    )
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(
        query="What differences are summarized in Table 1?",
        top_k=1,
        filters=filters,
    )

    assert search_service.structured_calls == 1
    assert search_service.last_structured_filters == filters
    assert result.citations[0].chunk_id == "other"


def test_chat_structured_reference_injection_falls_back_when_lexical_unavailable() -> None:
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="Dense evidence discusses Figure 14 results.",
                doc_id="milvus",
                chunk_id="dense",
                source="19_SIGMOD21_Milvus.pdf",
                distance=0.05,
            )
        ],
        structured_hits=[],
    )
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="What does Figure 14 show?", top_k=1)

    assert search_service.structured_calls == 1
    assert result.citations[0].chunk_id == "dense"


def test_chat_prioritizes_markdown_sources_for_explicit_local_docs_query() -> None:
    hits = [
        RetrievedChunk(
            text="A survey discusses RAG pipeline multi-step reasoning over web sources.",
            doc_id="paper",
            chunk_id="paper:41",
            source="15_arxiv_2501.pdf",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The local RAG pipeline steps are ingestion, chunking, embedding, retrieval, and generation.",
            doc_id="rag",
            chunk_id="rag:0",
            source="rag_pipeline.md",
            section="Overview",
            distance=0.2,
        ),
        RetrievedChunk(
            text="The local API docs explain that chat retrieves chunks before generating answers.",
            doc_id="api",
            chunk_id="api:2",
            source="api_usage.md",
            section="Chat Endpoint",
            distance=0.3,
        ),
    ]
    runtime = FakeRuntime()
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(
        query="What are the main steps in the RAG pipeline according to the local docs?",
        top_k=2,
        precomputed_hits=hits,
    )

    assert [citation.source for citation in result.citations] == ["rag_pipeline.md", "api_usage.md"]
    assert all(citation.source.endswith(".md") for citation in result.citations)
    assert len(result.citations) == 2
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["local_doc_intent_detected"] is True
    assert "local_doc_priority" in trace["applied_rules"]


def test_chat_does_not_prioritize_markdown_for_plain_pdf_query() -> None:
    hits = [
        RetrievedChunk(
            text="The Milvus paper presents a vector data management system for large-scale similarity search.",
            doc_id="milvus",
            chunk_id="milvus:0",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The local RAG pipeline docs describe ingestion, retrieval, and generation.",
            doc_id="rag",
            chunk_id="rag:0",
            source="rag_pipeline.md",
            distance=0.2,
        ),
    ]
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(
        query="What is the main topic of the Milvus paper?",
        top_k=2,
        precomputed_hits=hits,
    )

    assert result.citations[0].source == "19_SIGMOD21_Milvus.pdf"


def test_chat_respects_explicit_source_filter_over_local_docs_heuristic() -> None:
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )
    hits = [
        RetrievedChunk(text="Local docs explain the RAG pipeline.", doc_id="rag", chunk_id="rag:0", source="rag_pipeline.md"),
        RetrievedChunk(text="Milvus paper evidence.", doc_id="milvus", chunk_id="milvus:0", source="19_SIGMOD21_Milvus.pdf"),
    ]

    prioritized = service._prioritize_local_doc_hits(
        "What does this say according to the local docs?",
        hits,
        RetrievalFilters(sources=("19_SIGMOD21_Milvus.pdf",)),
    )

    assert prioritized == hits


def test_chat_falls_back_when_local_docs_query_has_no_markdown_candidates() -> None:
    hits = [
        RetrievedChunk(text="A PDF discusses RAG pipelines.", doc_id="p1", chunk_id="p1:0", source="paper_a.pdf"),
        RetrievedChunk(text="Another PDF discusses retrieval steps.", doc_id="p2", chunk_id="p2:0", source="paper_b.pdf"),
    ]
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    prioritized = service._prioritize_local_doc_hits(
        "What are the RAG pipeline steps according to the local docs?",
        hits,
        None,
    )

    assert prioritized == hits


def test_chat_source_consistency_keeps_structured_ref_with_named_paper_source() -> None:
    hits = [
        RetrievedChunk(
            text="Table 1 highlights the main differences between Milvus and other systems.",
            doc_id="milvus",
            chunk_id="milvus:23",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.05,
            extra_metadata={"retrieval_reason": "structured_ref_lexical"},
        ),
        RetrievedChunk(
            text="Another paper uses Table 1 to define answer relevance prompts.",
            doc_id="rag_eval",
            chunk_id="rag_eval:40",
            source="17_arxiv_2309.15217.pdf",
            distance=0.06,
            extra_metadata={"retrieval_reason": "structured_ref_lexical"},
        ),
        RetrievedChunk(
            text="Milvus is built on top of Faiss and compares with other vector systems.",
            doc_id="milvus",
            chunk_id="milvus:24",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.07,
        ),
    ]
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(
        query="What differences are summarized in Table 1 of the Milvus paper?",
        top_k=2,
        precomputed_hits=hits,
    )

    assert [citation.source for citation in result.citations] == [
        "19_SIGMOD21_Milvus.pdf",
        "19_SIGMOD21_Milvus.pdf",
    ]
    assert result.citations[0].chunk_id == "milvus:23"
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert any(rule in trace["applied_rules"] for rule in ("source_consistency_cap", "precompress_source_cap"))


def test_chat_source_consistency_uses_top_source_dominance_for_single_entity_query() -> None:
    hits = [
        RetrievedChunk(
            text="Milvus is a vector data management system for large scale similarity search.",
            doc_id="milvus",
            chunk_id="milvus:5",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The chat endpoint retrieves chunks before generating grounded answers.",
            doc_id="api",
            chunk_id="api:2",
            source="api_usage.md",
            distance=0.06,
        ),
        RetrievedChunk(
            text="Milvus supports vector similarity search and indexing for AI applications.",
            doc_id="milvus",
            chunk_id="milvus:38",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.07,
        ),
        RetrievedChunk(
            text="Example docs describe how citations are displayed in MindDock.",
            doc_id="example",
            chunk_id="example:1",
            source="example.md",
            distance=0.08,
        ),
    ]
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="What is Milvus?", top_k=2, precomputed_hits=hits)

    assert [citation.source for citation in result.citations] == [
        "19_SIGMOD21_Milvus.pdf",
        "19_SIGMOD21_Milvus.pdf",
    ]
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["final_sources"][0]["source"] == "19_SIGMOD21_Milvus.pdf"


def test_chat_source_consistency_does_not_single_source_cross_document_query() -> None:
    hits = [
        RetrievedChunk(
            text="The Milvus paper presents a vector data management system.",
            doc_id="milvus",
            chunk_id="milvus:5",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.05,
        ),
        RetrievedChunk(
            text="The local RAG pipeline docs describe ingestion, chunking, embeddings, and retrieval.",
            doc_id="rag",
            chunk_id="rag:0",
            source="rag_pipeline.md",
            distance=0.06,
        ),
        RetrievedChunk(
            text="Milvus uses a query engine, GPU engine, and storage engine.",
            doc_id="milvus",
            chunk_id="milvus:30",
            source="19_SIGMOD21_Milvus.pdf",
            distance=0.07,
        ),
    ]
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(
        query="Compare the Milvus paper with the local RAG pipeline docs.",
        top_k=3,
        precomputed_hits=hits,
    )

    assert {citation.source for citation in result.citations} == {
        "19_SIGMOD21_Milvus.pdf",
        "rag_pipeline.md",
    }


def test_chat_source_consistency_respects_explicit_source_filter() -> None:
    service = ChatService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )
    hits = [
        RetrievedChunk(text="Milvus paper evidence.", doc_id="milvus", chunk_id="milvus:0", source="19_SIGMOD21_Milvus.pdf"),
        RetrievedChunk(text="Filtered source evidence about Table 1.", doc_id="other", chunk_id="other:0", source="some_other.pdf"),
    ]

    reordered = service._apply_source_consistency_cap(
        "What differences are summarized in Table 1 of the Milvus paper?",
        hits,
        top_k=1,
        filters=RetrievalFilters(sources=("some_other.pdf",)),
    )

    assert reordered == hits


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


def test_chat_insufficient_evidence_response_is_helpful_and_citation_free() -> None:
    """Insufficient evidence response gives actionable suggestions without fabricating citations."""
    service = ChatService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text="weak content not useful",
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

    result = service.chat(query="test query with no real match", top_k=3)

    assert result.answer == HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "no_relevant_evidence"
    assert result.grounded_answer.evidence == ()
    assert "没有在当前知识库中找到足够直接的证据" in result.answer
    assert "尝试" in result.answer
    assert "关键词" in result.answer
    assert "Source Drawer" in result.answer or "Sources" in result.answer
    assert result.metadata.insufficient_evidence is True


def test_chat_grounded_answer_has_no_helpful_fallback_text() -> None:
    """When evidence is sufficient, answer should NOT contain fallback suggestion text."""
    hits = [
        RetrievedChunk(
            text="MindDock stores chunks in Chroma for grounded retrieval.",
            doc_id="d1",
            chunk_id="c1",
            source="kb/doc.md",
            distance=0.2,
        )
    ]
    runtime = FakeRuntime()
    service = ChatService(
        search_service=FakeSearchService(hits),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query="where does MindDock store chunks", top_k=3)

    assert result.answer != HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
    assert "没有在当前知识库中找到足够直接的证据" not in result.answer
    assert result.citations != []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.grounded_answer.refusal_reason is None


def test_chat_out_of_scope_not_overwritten_by_helpful_fallback() -> None:
    """Out-of-scope queries must still use the original refusal, not the helpful fallback."""
    search_service = FakeSearchService(
        [
            RetrievedChunk(
                text="MindDock stores data in Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                distance=0.1,
            )
        ]
    )
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=FakeRuntime(),
    )

    result = service.chat(query="你是什么模型", top_k=3)

    assert result.answer != HELPFUL_CHAT_INSUFFICIENT_EVIDENCE
    assert "尝试" not in result.answer
    assert result.citations == []
    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.grounded_answer.refusal_reason.value == "out_of_scope"
    assert result.metadata.issues[0].code == "out_of_scope"
    assert search_service.calls == 0


# ---------------------------------------------------------------------------
# Post-generation evidence gate tests
# ---------------------------------------------------------------------------


class RefusalRuntime:
    """Fake runtime that returns evidence-insufficient answers."""

    runtime_name = "fake-refusal-runtime"
    provider_name = "fake-provider"

    def __init__(self, refusal_text: str) -> None:
        self._text = refusal_text
        self.last_inputs: dict[str, object] | None = None

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        self.last_inputs = request.inputs
        return RuntimeResponse(
            text=self._text,
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


_IN_SCOPE_HITS = [
    RetrievedChunk(
        text="Milvus uses a distributed system design for vector search, with coordinators and query nodes.",
        doc_id="milvus-paper",
        chunk_id="c1",
        source="papers/milvus.pdf",
        title="Milvus",
        distance=0.1,
    ),
    RetrievedChunk(
        text="The query node handles search requests and coordinates with data nodes.",
        doc_id="milvus-paper",
        chunk_id="c2",
        source="papers/milvus.pdf",
        title="Milvus",
        distance=0.15,
    ),
]


@pytest.mark.parametrize(
    "refusal_text",
    [
        "The evidence is insufficient to answer the question. The provided text discusses unrelated topics.",
        "The evidence provided does not contain any information about this topic.",
        "Not enough evidence to provide a grounded answer.",
        "The evidence provided is insufficient to answer how to make a chocolate cake from scratch.",
    ],
)
def test_post_generation_gate_overrides_english_model_refusal(refusal_text: str) -> None:
    """When the LLM answer contains English refusal language, metadata must reflect insufficient evidence.

    Uses a query that passes the pre-generation evidence gate (terms overlap with Milvus evidence)
    but the LLM still returns refusal language.
    """
    service = ChatService(
        search_service=FakeSearchService(_IN_SCOPE_HITS),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=RefusalRuntime(refusal_text),
    )

    # Use a query that overlaps with Milvus evidence so pre-gen gate passes
    result = service.chat(query="What is the system design of Milvus?", top_k=3)

    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence", (
        f"Expected insufficient_evidence, got {result.grounded_answer.support_status.value}"
    )
    assert result.citations == [], f"Expected empty citations, got {len(result.citations)}"
    assert result.metadata.support_status == "insufficient_evidence"
    trace = result.metadata.workflow_trace
    assert trace is not None
    gate = trace["evidence_gate"]
    assert gate["triggered"] is True
    assert gate["action"] == "force_insufficient_evidence"
    assert "model_refused_due_to_insufficient_evidence" in gate["reason"]


def test_post_generation_gate_overrides_chinese_model_refusal() -> None:
    """When the LLM answer contains Chinese refusal language, metadata must reflect insufficient evidence."""
    refusal_text = "当前知识库中没有足够证据来回答这个问题。请尝试使用更接近原文的关键词重新提问。"
    service = ChatService(
        search_service=FakeSearchService(_IN_SCOPE_HITS),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=RefusalRuntime(refusal_text),
    )

    result = service.chat(query="法国的首都是哪里？", top_k=3)

    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "insufficient_evidence"
    assert result.citations == []
    assert result.metadata.support_status == "insufficient_evidence"
    trace = result.metadata.workflow_trace
    assert trace is not None
    gate = trace["evidence_gate"]
    assert gate["triggered"] is True
    assert gate["action"] == "force_insufficient_evidence"


def test_post_generation_gate_does_not_affect_in_scope_supported_answer() -> None:
    """In-scope questions with normal answers must keep supported status and citations."""
    normal_answer = "Milvus uses a distributed system design with coordinators and query nodes for vector search."
    service = ChatService(
        search_service=FakeSearchService(_IN_SCOPE_HITS),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=RefusalRuntime(normal_answer),
    )

    result = service.chat(query="What is the system design of Milvus?", top_k=3)

    assert result.grounded_answer is not None
    assert result.grounded_answer.support_status.value == "supported"
    assert result.citations != []
    assert result.metadata.support_status == "supported"
    trace = result.metadata.workflow_trace
    assert trace is not None
    gate = trace["evidence_gate"]
    assert gate["triggered"] is False
    assert gate["action"] == "allow_generation"


def test_post_generation_gate_records_evaluated_flag() -> None:
    """The evidence_gate trace must always include evaluated=True."""
    normal_answer = "Milvus uses a distributed system design with coordinators and query nodes."
    service = ChatService(
        search_service=FakeSearchService(_IN_SCOPE_HITS),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=RefusalRuntime(normal_answer),
    )

    result = service.chat(query="What is the system design of Milvus?", top_k=3)

    trace = result.metadata.workflow_trace
    assert trace is not None
    gate = trace["evidence_gate"]
    assert gate["evaluated"] is True
